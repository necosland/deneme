"""Turnuva 4: KOMBINASYONLAR (rejim filtresi + giris zamanlamasi + cikis, oylama topluluklari).
Hepsi long-only spot, kaldiracsiz. Kural (tur 1-2 ile ayni): her fonksiyon mum KAPANISINDA bilinen bilgiyle
pozisyon (0..1) uretir; motor (lab.single_eval) bunu bir sonraki mumda uygular.
Imza: fn(df, ctx, **param) -> pd.Series.  ctx: ppy, ppd, btc (ayni aralik), eth {ppd: df}, fng.

Birimler (on-kayitli): rejim filtreleri (ADX haric) GUN cinsinden (ppd ile mum sayisina cevrilir; SMA200 = 200 gun);
giris/cikis gostergeleri tur 1-2 gibi MUM cinsinden (gunluk mumda ~6 kat yavas calisir).
Rejim filtresi her zaman CARPIMSAL: pozisyon = cekirdek pozisyon x rejim (0/1). Rejim kapaninca cikilir,
acilinca cekirdek hala long ise girilir (btc_filter_ema / ema_btcf ile ayni mantik).

Bloklar:
  Rejim : BTC200, COIN200, ADX (trend gucu), VOL (dusuk/yuksek oynaklik), ETHBTC (alt sezonu), FNG (asiri degil)
  Giris : Donchian kirilimi, EMA kesisimi, RSI geri cekilme, Fib %38-62, EMA'ya dokunma, Bollinger alt bant,
          sikisma kirilimi, hacim onayi
  Cikis : karsit sinyal, ATR iz suren stop, chandelier, zaman stopu
  Topluluk: n sinyalin ortalamasi (pozisyon = long olan sinyal orani) ya da cogunluk oyu.
"""
import numpy as np
import pandas as pd

from lab_strategies import (S, atr, btc_filter_ema, donchian, ema, ema_cross, keltner_breakout, machine,
                            macd, rsi, sma, sma_cross, supertrend, timed, tsmom, wilder)
from lab_strategies import SINGLE as R1
from lab_strategies2 import DAY, asof, squeeze_breakout, zigzag

# ---------------------------------------------------------------- yardimcilar


def days(ctx, d):
    return max(2, int(round(d * ctx["ppd"])))


def align(sig, df):
    """Baska indeksteki (BTC/ETH) 0/1 sinyali coinin mumlarina esle: t'de bilinen son deger."""
    s = pd.Series(np.asarray(sig, dtype=float), index=sig.index)
    return s.reindex(df.index, method="ffill").fillna(0.0)


def edge(cond):
    """Kosulun yeni olustugu mum (yanlis -> dogru gecisi)."""
    c = cond.fillna(False).astype(bool)
    return c & ~c.shift(1, fill_value=False)


def trail_machine(c, enter, a, m, stop=None):
    """Giris -> long; cikis: kapanis < (girisden beri en yuksek kapanis - m*ATR) ya da stop[i] (seviye) alti."""
    c = np.asarray(c, dtype=float).tolist()
    en = np.nan_to_num(np.asarray(enter, dtype=float)).astype(bool).tolist()
    a = np.asarray(a, dtype=float).tolist()
    st = None if stop is None else np.asarray(stop, dtype=float).tolist()
    pos = [0.0] * len(c)
    p, peak = 0.0, 0.0
    for i in range(len(c)):
        if p == 1.0:
            peak = max(peak, c[i])
            if c[i] < peak - m * a[i] or (st is not None and c[i] < st[i]):
                p = 0.0
        elif en[i]:
            p, peak = 1.0, c[i]
        pos[i] = p
    return np.array(pos)


def line_machine(c, enter, line):
    """Giris -> long; cikis: kapanis < line[i] (orn. chandelier cizgisi). Ayni mumda cikis + giris yok."""
    c = np.asarray(c, dtype=float).tolist()
    en = np.nan_to_num(np.asarray(enter, dtype=float)).astype(bool).tolist()
    ln = np.asarray(line, dtype=float).tolist()
    pos = [0.0] * len(c)
    p = 0.0
    for i in range(len(c)):
        if p == 1.0:
            if c[i] < ln[i]:
                p = 0.0
        elif en[i] and not c[i] < ln[i]:
            p = 1.0
        pos[i] = p
    return np.array(pos)


def chand_line(df, m, n=22):
    """Chandelier: son n mumun en yuksegi - m * ATR(n)."""
    return df["high"].rolling(n).max() - m * atr(df, n)


# ---------------------------------------------------------------- rejim filtreleri (0/1 Series)
def reg_btc(df, ctx, f=200):
    b = ctx["btc"]["close"]
    return align(b > sma(b, days(ctx, f)), df)


def reg_coin(df, ctx, f=200):
    c = df["close"]
    return S(c > sma(c, days(ctx, f)), df)


def _dmi(df, n):
    up, dn = df["high"].diff(), -df["low"].diff()
    pdm = pd.Series(np.where((up > dn) & (up > 0), up, 0.0), index=df.index)
    mdm = pd.Series(np.where((dn > up) & (dn > 0), dn, 0.0), index=df.index)
    a = atr(df, n)
    pdi, mdi = 100 * wilder(pdm, n) / a, 100 * wilder(mdm, n) / a
    adx = wilder(100 * (pdi - mdi).abs() / (pdi + mdi), n)
    warm = pd.Series(np.arange(len(df)) >= 3 * n, index=df.index)
    return adx.where(warm), pdi, mdi


def reg_adx(df, ctx, thr):
    """Trend gucu: ADX(14 MUM) > thr (yon bakmaz). Esikler 14 periyotluk ADX icin tanimli oldugundan
    bu filtre gun degil mum cinsinden (on-kayit notu)."""
    adx, _, _ = _dmi(df, 14)
    return S(adx > thr, df)


def reg_vol(df, ctx, mode):
    """Gerceklesen oynaklik (30 gun) son 1 yilin medyaninin altinda (low) ya da ustunde (high)."""
    rv = df["close"].pct_change().rolling(days(ctx, 30)).std()
    med = rv.rolling(days(ctx, 365), min_periods=days(ctx, 180)).median()
    return S(rv < med if mode == "low" else rv > med, df)


def reg_ethbtc(df, ctx, n):
    """Alt sezonu: ETH/BTC orani SMA(n gun) ustundeyse altcoinlere izin. BTC'nin kendisi hep serbest."""
    b = ctx["btc"]["close"]
    rel = (df["close"] / b.reindex(df.index)).dropna()
    if len(rel) and float(np.abs(rel - 1).max()) < 1e-12:  # bu varlik BTC
        return pd.Series(1.0, index=df.index)
    e = ctx["eth"][ctx["ppd"]]["close"]
    e = e[e.index <= b.index[-1]]
    ratio = (e / b.reindex(e.index)).dropna()
    return align(ratio > sma(ratio, days(ctx, n)), df)


def reg_fng(df, ctx, band):
    """Korku/Acgozluluk endeksi asiri degil: lo <= FNG <= hi. Gun D degeri D+1 00:00'dan itibaren (tur 2 gibi)."""
    lo, hi = band
    f = asof(ctx["fng"], df.index, DAY)
    return S((f >= lo) & (f <= hi), df)


# ---------------------------------------------------------------- tek bloklar (bilesenler)
def don(df, ctx, entry, exit):
    return donchian(df, ctx, entry, exit)


def ema_pair(df, ctx, pair):
    return ema_cross(df, ctx, *pair)


def btc200(df, ctx):
    return reg_btc(df, ctx, 200)


def coin200(df, ctx):
    return reg_coin(df, ctx, 200)


def adx_up(df, ctx, thr):
    """ADX rejiminin tek basina long kurali: ADX(14 mum) > thr ve +DI > -DI."""
    adx, pdi, mdi = _dmi(df, 14)
    return S((adx > thr) & (pdi > mdi), df)


def vol_alone(df, ctx, mode):
    return reg_vol(df, ctx, mode)


def ethbtc_alone(df, ctx, n):
    return reg_ethbtc(df, ctx, n)


def btcf_ema(df, ctx, pair):
    return btc_filter_ema(df, ctx, *pair)


def fng_alone(df, ctx, band):
    return reg_fng(df, ctx, band)


def _pb_rsi_entry(df, ctx, lo):
    c = df["close"]
    return edge((c > sma(c, days(ctx, 200))) & (rsi(c, 14) < lo))


def pb_rsi_std(df, ctx, lo):
    """Klasik geri cekilme: yukselis trendinde (coin > SMA200 gun) RSI14 lo'nun altina iner -> al; RSI > 55 -> sat."""
    return S(machine(_pb_rsi_entry(df, ctx, lo), rsi(df["close"], 14) > 55), df)


def _fib(df, ctx, k, mode, m=None):
    """Tur 2 fib_pullback girisi (trend = coin > SMA200 GUN): son bacak L0->H1 onayli, fiyat bacagin
    %38.2-61.8'i geri cekilir ve mum yukari kapanir -> al. Cikis: L0 alti (stop) VE
    mode='target': H1'e donus;  mode='trail': kapanis < girisden beri zirve - m*ATR14 (hedef yok)."""
    h, l, c = (df[x].to_numpy(dtype=float) for x in ("high", "low", "close"))
    trend = (df["close"] > sma(df["close"], days(ctx, 200))).to_numpy()
    a = atr(df, 14).to_numpy()
    piv = zigzag(h, l, (k * atr(df, 14)).to_numpy())
    pos = np.zeros(len(c))
    p, stop, tgt, peak, j = 0, np.nan, np.nan, 0.0, 0
    conf, used = [], set()
    for i in range(1, len(c)):
        while j < len(piv) and piv[j][3] <= i:
            conf.append(piv[j])
            j += 1
        if p == 1:
            peak = max(peak, c[i])
            if c[i] < stop or (mode == "target" and c[i] >= tgt) or (mode == "trail" and c[i] < peak - m * a[i]):
                p = 0
        elif len(conf) >= 2 and trend[i]:
            x, y = conf[-2:]
            if (x[0], y[0]) == ("L", "H") and y[2] not in used and y[1] > x[1]:
                r = (y[1] - c[i]) / (y[1] - x[1])
                if 0.382 <= r <= 0.618 and c[i] > c[i - 1]:
                    p, stop, tgt, peak = 1, x[1], y[1], c[i]
                    used.add(y[2])
        pos[i] = p
    return pos


def fib_std(df, ctx, k):
    return S(_fib(df, ctx, k, "target"), df)


def _touch_entry(df, ctx, t):
    c = df["close"]
    e = ema(c, t)
    return edge((c > sma(c, days(ctx, 200))) & (df["low"] <= e) & (c > e))


def touch_timed(df, ctx, t):
    """Yukselis trendinde fitil EMA(t)'ye deger, kapanis ustunde -> al, 30 mum tut (zaman stopu)."""
    return S(timed(_touch_entry(df, ctx, t), 30), df)


def _bb_entry(df, ctx, k):
    c = df["close"]
    m, sd = sma(c, 20), c.rolling(20).std()
    return edge((c > sma(c, days(ctx, 200))) & (c < m - k * sd))


def bb_mr_trend(df, ctx, k):
    """Yukselis trendinde Bollinger(20) alt bandinin altinda kapanis -> al; orta bant ustu -> sat."""
    c = df["close"]
    return S(machine(_bb_entry(df, ctx, k), c > sma(c, 20)), df)


def squeeze(df, ctx, n):
    return squeeze_breakout(df, ctx, n, 0.25)


def _sqz_entry(df, ctx, n):
    """Tur 2 squeeze_breakout ile ayni giris (q=0.25)."""
    c = df["close"]
    m, sd = sma(c, n), c.rolling(n).std()
    width = 4 * sd / m
    ppy = int(ctx["ppy"])
    lim = width.rolling(ppy, min_periods=ppy // 2).quantile(0.25)
    squeezed = (width < lim).astype(float).rolling(6, min_periods=1).max().shift(1) > 0
    return squeezed & (c > m + 2 * sd)


def sqz_chand(df, ctx, n, m):
    return S(line_machine(df["close"], _sqz_entry(df, ctx, n), chand_line(df, m)), df)


def don_chand(df, ctx, entry, m):
    hh = df["high"].rolling(entry).max().shift(1)
    return S(line_machine(df["close"], df["close"] > hh, chand_line(df, m)), df)


def donz_window(df, w):
    """Zarattini tarzi tek pencere (GUN): kapanis, onceki w gunun en yuksek KAPANISINI gecerse al;
    iz suren stop = max(onceki stop, (w gunluk en yuksek + en dusuk kapanis)/2); kapanis stop altinda -> sat."""
    c = df["close"]
    hh_prev = c.rolling(w).max().shift(1).to_numpy()
    mid = ((c.rolling(w).max() + c.rolling(w).min()) / 2).to_numpy()
    cv = c.to_numpy(dtype=float)
    pos = np.zeros(len(cv))
    p, stop = 0, -np.inf
    for i in range(len(cv)):
        if p == 1:
            stop = max(stop, mid[i])
            if cv[i] < stop:
                p = 0
        elif not np.isnan(hh_prev[i]) and cv[i] > hh_prev[i]:
            p, stop = 1, mid[i]
        pos[i] = p
    return pos


ZWIN = [5, 10, 20, 30, 60, 90, 150, 250, 360]


def donz_single(df, ctx, w):
    return S(donz_window(df, days(ctx, w)), df)


# topluluk uyeleri (s = hiz carpani; lookback'ler s ile carpilir)
def m_ema(df, ctx, s):
    return ema_cross(df, ctx, int(round(20 * s)), int(round(100 * s)))


def m_sma(df, ctx, s):
    return sma_cross(df, ctx, int(round(20 * s)), int(round(100 * s)))


def m_don(df, ctx, s):
    return donchian(df, ctx, int(round(55 * s)), int(round(20 * s)))


def m_macd(df, ctx, s):
    return macd(df, ctx, max(1, int(round(2 * s))))


def m_st(df, ctx, s):
    return supertrend(df, ctx, int(round(10 * s)), 3.0)


def m_tsmom(df, ctx, s):
    return tsmom(df, ctx, int(round(90 * s)))


def m_kelt(df, ctx, s):
    return keltner_breakout(df, ctx, int(round(50 * s)), 2.0)


def m_pbrsi(df, ctx):
    return pb_rsi_std(df, ctx, 40)


def m_bbmr(df, ctx):
    return bb_mr_trend(df, ctx, 2.0)


MEMBERS = {"ema": m_ema, "sma": m_sma, "don": m_don, "macd": m_macd, "st": m_st, "tsmom": m_tsmom,
           "kelt": m_kelt, "pbrsi": m_pbrsi, "bbmr": m_bbmr}
NOSCALE = {"pbrsi", "bbmr"}


def _ens(df, ctx, names, s, vote=None):
    parts = [MEMBERS[n](df, ctx) if n in NOSCALE else MEMBERS[n](df, ctx, s) for n in names]
    tot = sum(p.clip(0, 1).fillna(0.0) for p in parts)
    if vote is None:
        return tot / len(parts)
    return (tot >= vote).astype(float)


TREND5 = ["ema", "sma", "don", "macd", "st"]
DIV4 = ["ema", "don", "tsmom", "pbrsi"]
DIV7 = ["ema", "don", "tsmom", "macd", "kelt", "pbrsi", "bbmr"]


# ---------------------------------------------------------------- KOMBINASYONLAR
def btc200_x_don(df, ctx, entry, exit):
    return don(df, ctx, entry, exit) * reg_btc(df, ctx)


def coin200_x_don(df, ctx, entry, exit):
    return don(df, ctx, entry, exit) * reg_coin(df, ctx)


def adx_x_don(df, ctx, entry, exit, thr):
    return don(df, ctx, entry, exit) * reg_adx(df, ctx, thr)


def vol_x_don(df, ctx, entry, exit, mode):
    return don(df, ctx, entry, exit) * reg_vol(df, ctx, mode)


def ethbtc_x_ema(df, ctx, pair, n):
    return ema_pair(df, ctx, pair) * reg_ethbtc(df, ctx, n)


def fng_x_btcfema(df, ctx, pair, band):
    return btcf_ema(df, ctx, pair) * reg_fng(df, ctx, band)


def dual200_x_don(df, ctx, entry, exit):
    return don(df, ctx, entry, exit) * reg_btc(df, ctx) * reg_coin(df, ctx)


def adx_x_ema(df, ctx, pair, thr):
    return ema_pair(df, ctx, pair) * reg_adx(df, ctx, thr)


def pb_rsi_trail(df, ctx, lo, m):
    return S(trail_machine(df["close"], _pb_rsi_entry(df, ctx, lo), atr(df, 14), m), df)


def pb_rsi_trail_btc200(df, ctx, lo, m):
    return pb_rsi_trail(df, ctx, lo, m) * reg_btc(df, ctx)


def pb_fib_trail(df, ctx, k, m):
    return S(_fib(df, ctx, k, "trail", m), df)


def pb_touch_chand(df, ctx, t, m):
    return S(line_machine(df["close"], _touch_entry(df, ctx, t), chand_line(df, m)), df)


def pb_bb_trail(df, ctx, k, m):
    return S(trail_machine(df["close"], _bb_entry(df, ctx, k), atr(df, 14), m), df)


def pb_rsi_time(df, ctx, lo, hold):
    return S(timed(_pb_rsi_entry(df, ctx, lo), hold), df)


def sqz_chand_btc200(df, ctx, n, m):
    return sqz_chand(df, ctx, n, m) * reg_btc(df, ctx)


def don_volconf(df, ctx, entry, exit, k):
    c, v = df["close"], df["volume"]
    hh = df["high"].rolling(entry).max().shift(1)
    ll = df["low"].rolling(exit).min().shift(1)
    conf = v > k * v.rolling(50).mean().shift(1)
    return S(machine((c > hh) & conf, c < ll), df)


def don_chand_btc200(df, ctx, entry, m):
    return don_chand(df, ctx, entry, m) * reg_btc(df, ctx)


def ens_trend5_avg(df, ctx, s):
    return _ens(df, ctx, TREND5, s)


def ens_trend5_vote(df, ctx, s):
    return _ens(df, ctx, TREND5, s, vote=3)


def ens_div4_avg(df, ctx, s):
    return _ens(df, ctx, DIV4, s)


def ens_div7_avg(df, ctx, s):
    return _ens(df, ctx, DIV7, s)


def ens_div7_vote(df, ctx, s):
    return _ens(df, ctx, DIV7, s, vote=4)


def ens_trend5_avg_btc200(df, ctx, s):
    return ens_trend5_avg(df, ctx, s) * reg_btc(df, ctx)


def ens_donz_multi(df, ctx):
    """Zarattini-Pagani-Barbon tarzi: 9 pencerenin (5..360 gun) Donchian pozisyonlarinin ortalamasi.
    Oynaklik hedefleme ve kaldirac YOK (spot, long-only)."""
    return S(sum(donz_window(df, days(ctx, w)) for w in ZWIN) / len(ZWIN), df)


# ---------------------------------------------------------------- KAYIT (on-kayit: RAPOR4.md "Plan")
DON_G = {"entry": [55, 100], "exit": [20, 40]}
PAIR_G = {"pair": [(20, 100), (50, 200)]}
SCALE_G = {"s": [0.5, 1.0, 2.0]}

COMPONENTS = {
    "DON": (don, DON_G),
    "EMA": (ema_pair, PAIR_G),
    "BTC200": (btc200, {}),
    "COIN200": (coin200, {}),
    "ADX_UP": (adx_up, {"thr": [20, 25]}),
    "VOL": (vol_alone, {"mode": ["low", "high"]}),
    "ETHBTC": (ethbtc_alone, {"n": [50, 100]}),
    "BTCF_EMA": (btcf_ema, PAIR_G),
    "FNG": (fng_alone, {"band": [(20, 80), (25, 75)]}),
    "PB_RSI_STD": (pb_rsi_std, {"lo": [35, 40]}),
    "FIB_STD": (fib_std, {"k": [3, 5]}),
    "TOUCH_TIMED": (touch_timed, {"t": [20, 50]}),
    "BB_MR_TREND": (bb_mr_trend, {"k": [1.5, 2.0]}),
    "SQUEEZE": (squeeze, {"n": [20, 50]}),
    "SQZ_CHAND": (sqz_chand, {"n": [20, 50], "m": [3.0, 4.0]}),
    "DON_CHAND": (don_chand, {"entry": [55, 100], "m": [3.0, 4.0]}),
    "DONZ_SINGLE": (donz_single, {"w": ZWIN}),
    "M_EMA": (m_ema, SCALE_G),
    "M_SMA": (m_sma, SCALE_G),
    "M_DON": (m_don, SCALE_G),
    "M_MACD": (m_macd, SCALE_G),
    "M_ST": (m_st, SCALE_G),
    "M_TSMOM": (m_tsmom, SCALE_G),
    "M_KELT": (m_kelt, SCALE_G),
    "M_PBRSI": (m_pbrsi, {}),
    "M_BBMR": (m_bbmr, {}),
}
# Tur 1 kazananlari, tur 1 ile BIREBIR ayni fonksiyon ve izgara (yeni deneme sayilmaz).
R1_WINNERS = ["donchian", "btc_filter_ema", "keltner_breakout", "sma_cross", "ema_cross"]
R1_COMPONENTS = {f"R1_{n}": R1[n] for n in R1_WINNERS}

# ad -> (fn, izgara, bilesenler, gerekce)
COMBOS = {
    "btc200_x_don": (btc200_x_don, DON_G, ["DON", "BTC200"],
                     "Donchian'in zararlari ayi piyasasindaki sahte kirilimlardan; BTC rejimi onlari keser."),
    "coin200_x_don": (coin200_x_don, DON_G, ["DON", "COIN200"],
                      "Ayni fikir, coinin kendi uzun trendiyle: uzun trend asagiyken kirilimlara girme."),
    "adx_x_don": (adx_x_don, {**DON_G, "thr": [20, 25]}, ["DON", "ADX_UP"],
                  "Kirilimlar trendli piyasada calisir; ADX yatay piyasayi ayiklar."),
    "vol_x_don": (vol_x_don, {**DON_G, "mode": ["low", "high"]}, ["DON", "VOL"],
                  "Kirilimin basarisi oynaklik rejimine bagli olabilir; hangi rejim oldugunu walk-forward secer."),
    "ethbtc_x_ema": (ethbtc_x_ema, {**PAIR_G, "n": [50, 100]}, ["EMA", "ETHBTC"],
                     "Altcoin trendleri para BTC'den cikarken (ETH/BTC yukari) daha guclu; BTC serbest."),
    "fng_x_btcfema": (fng_x_btcfema, {**PAIR_G, "band": [(20, 80), (25, 75)]}, ["BTCF_EMA", "FNG"],
                      "Asiri acgozlulukte tepe, asiri korkuda cokus riski; duygu asiriyken trende guvenme."),
    "dual200_x_don": (dual200_x_don, DON_G, ["DON", "BTC200", "COIN200", "btc200_x_don", "coin200_x_don"],
                      "Hem piyasa (BTC) hem coin uzun trendde iken kirilim: iki bagimsiz onay."),
    "adx_x_ema": (adx_x_ema, {**PAIR_G, "thr": [20, 25]}, ["EMA", "ADX_UP"],
                  "EMA kesisimi yatayda testere yer; ADX trend gucu yoksa disarida tutar."),
    "pb_rsi_trail": (pb_rsi_trail, {"lo": [35, 40], "m": [3.0, 5.0]}, ["PB_RSI_STD", "COIN200"],
                     "Trendde ucuzdan gir (RSI dibi), ama erken satma: trend takipcisi gibi iz suren stopla cik."),
    "pb_rsi_trail_btc200": (pb_rsi_trail_btc200, {"lo": [35, 40], "m": [3.0, 5.0]},
                            ["PB_RSI_STD", "COIN200", "BTC200", "pb_rsi_trail"],
                            "Ayni, ustune piyasa rejimi: coin trendde ama piyasa ayidaysa dip alma."),
    "pb_fib_trail": (pb_fib_trail, {"k": [3, 5], "m": [3.0, 5.0]}, ["FIB_STD", "COIN200"],
                     "Fib geri cekilmesi iyi giris fiyati verir; hedefte satmak yerine trendi iz suren stopla tasi."),
    "pb_touch_chand": (pb_touch_chand, {"t": [20, 50], "m": [3.0, 4.0]}, ["TOUCH_TIMED", "COIN200"],
                       "Trendde ortalamaya dokunus klasik ekleme noktasi; chandelier trend bitene kadar tutar."),
    "pb_bb_trail": (pb_bb_trail, {"k": [1.5, 2.0], "m": [3.0, 5.0]}, ["BB_MR_TREND", "COIN200"],
                    "Bollinger alti asiri satim, trend icinde firsat; orta bantta degil iz suren stopla cik."),
    "pb_rsi_time": (pb_rsi_time, {"lo": [35, 40], "hold": [12, 36]}, ["PB_RSI_STD", "COIN200"],
                    "Dipten donus belirli surede biter; RSI>55 cikisi yerine sabit sure tut."),
    "sqz_chand_btc200": (sqz_chand_btc200, {"n": [20, 50], "m": [3.0, 4.0]}, ["SQUEEZE", "BTC200", "SQZ_CHAND"],
                         "Sikisma sonrasi kirilim buyuk hareket baslatir; BTC rejimi yonu, chandelier kari korur."),
    "don_volconf": (don_volconf, {**DON_G, "k": [1.5, 2.0]}, ["DON"],
                    "Hacimle desteklenmeyen kirilim sahte olabilir; hacim onayi sahte kirilimlari eler."),
    "don_chand_btc200": (don_chand_btc200, {"entry": [55, 100], "m": [3.0, 4.0]},
                         ["DON", "BTC200", "DON_CHAND", "btc200_x_don"],
                         "Kirilim girisi + oynakliga gore iz suren cikis + piyasa rejimi: klasik kaplumbaga + filtre."),
    "ens_trend5_avg": (ens_trend5_avg, SCALE_G, ["M_EMA", "M_SMA", "M_DON", "M_MACD", "M_ST"],
                       "5 trend sinyalinin ortalamasi: tek sinyalin hatasi digerleriyle yumusar, pozisyon kademeli."),
    "ens_trend5_vote": (ens_trend5_vote, SCALE_G, ["M_EMA", "M_SMA", "M_DON", "M_MACD", "M_ST"],
                        "Ayni 5 sinyal, cogunluk oyu (en az 3/5): tam pozisyon, daha az gurultu."),
    "ens_div4_avg": (ens_div4_avg, SCALE_G, ["M_EMA", "M_DON", "M_TSMOM", "M_PBRSI"],
                     "Farkli turler (trend, kirilim, momentum, geri cekilme) farkli zamanlarda kazanir."),
    "ens_div7_avg": (ens_div7_avg, SCALE_G, ["M_EMA", "M_DON", "M_TSMOM", "M_MACD", "M_KELT", "M_PBRSI", "M_BBMR"],
                     "7 cesitli sinyalin ortalamasi: en genis cesitlendirme."),
    "ens_div7_vote": (ens_div7_vote, SCALE_G, ["M_EMA", "M_DON", "M_TSMOM", "M_MACD", "M_KELT", "M_PBRSI", "M_BBMR"],
                      "Ayni 7 sinyal, cogunluk oyu (en az 4/7)."),
    "ens_trend5_avg_btc200": (ens_trend5_avg_btc200, SCALE_G, ["ens_trend5_avg", "BTC200"],
                              "Trend toplulugunun ustune piyasa rejimi."),
    "ens_donz_multi": (ens_donz_multi, {}, ["DONZ_SINGLE"],
                       "Zarattini vd. (2025): 9 pencereli Donchian toplulugu; tek en iyi pencereyi secmekten saglam mi?"),
}

# Walk-forward topluluklari: her uye KENDI tur 1 izgarasiyla walk-forward edilir, OOS pozisyonlari ortalanir.
WF_COMBOS = {
    "ens_r1win_wf": (R1_WINNERS, None, [f"R1_{n}" for n in R1_WINNERS],
                     "Tur 1'in 5 kazananinin (hepsi walk-forward) esit ortalamasi."),
    "ens_r1win_wf_btc200": (R1_WINNERS, "BTC200", ["ens_r1win_wf", "BTC200"],
                            "Ayni topluluk x BTC>SMA200 rejimi."),
}

ALL_FNS = {**{k: v for k, v in COMPONENTS.items()}, **R1_COMPONENTS,
           **{k: (v[0], v[1]) for k, v in COMBOS.items()}}
NEEDS = {"FNG": "fng", "fng_x_btcfema": "fng"}
