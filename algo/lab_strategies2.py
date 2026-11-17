"""Turnuva 2 stratejileri (yeni aileler). Hepsi long-only spot, kaldiracsiz.
Kural (tur 1 ile ayni): her fonksiyon mum KAPANISINDA bilinen bilgiyle pozisyon (0..1) uretir;
motor (lab.single_eval / lab.portfolio_eval) bunu bir sonraki mumda uygular.
Imza: fn(df, ctx, **param) -> pd.Series   (tek varlik)
      fn(closes, ctx, **param) -> DataFrame (portfoy agirliklari)
ctx: ppy, ppd, btc (ayni araliktaki BTC df), fng (gunluk Series ya da None), funding (BTC fonlama Series ya da None).
Parametreler mum cinsinden (tur 1 gibi); gunluk mumda ayni sistem bu yuzden ~6 kat yavas calisir.

Takvim stratejileri pozisyonu "bir sonraki mumun zamani"na gore kurar: o mum t'deki karar ile tutulur,
ve takvim onceden bilinir (lookahead degil). Dis veri (FNG, fonlama) asof() ile gecikmeli eslenir.
"""
import hashlib
import math

import numpy as np
import pandas as pd

from lab_strategies import S, atr, ema, machine, rsi, sma, timed

DAY = pd.Timedelta(days=1)
HALVINGS = [pd.Timestamp(x, tz="UTC") for x in ("2012-11-28", "2016-07-09", "2020-05-11", "2024-04-20")]
_CACHE = {}


# ---------------- yardimcilar ----------------
def bar_td(idx):
    return pd.Series(idx).diff().median()


def next_times(df):
    """Her mumun ardindan gelen mumun acilis zamani (t'de tutulan pozisyonun kazandigi mum)."""
    return df.index + bar_td(df.index)


def key_of(df, *extra):
    h = hashlib.md5(np.ascontiguousarray(df["close"].to_numpy(dtype=float)).tobytes()).hexdigest()
    return (h, len(df), str(df.index[0]), str(df.index[-1])) + extra


def asof(series, index, lag, max_age=pd.Timedelta(days=2)):
    """series degerini (zaman damgasi + lag) <= mum ACILIS zamani olan mumlara esle.
    Mum acilisinda bilinen deger, kapanista kesin bilinir -> en az bir mum guvenli tampon.
    max_age'den eski deger kullanilmaz (veri kesilirse NaN -> nakit)."""
    s = series.dropna().copy()
    s.index = s.index + lag
    s = s[~s.index.duplicated(keep="last")].sort_index()
    out = s.reindex(index, method="ffill")
    t = pd.Series(s.index, index=s.index).reindex(index, method="ffill")
    return out.where((index - pd.DatetimeIndex(t)) <= max_age)


def daily_bars(df):
    agg = {"open": "first", "high": "max", "low": "min", "close": "last", "volume": "sum"}
    return df.resample("1D").agg(agg).dropna(subset=["close"])


def on_daily(df, fn):
    """fn'i gunluk mumda calistirir, sonucu alt araliga esler. Gun D'nin sinyali D'nin son alt mumunun
    kapanisinda (= gunluk kapanis) bilinir; o mumdan itibaren ileri tasinir. Eksik (bitmemis) gun hicbir
    alt muma eslenmez, cunku etiketi o gunun son alt mumunun zamani."""
    td = bar_td(df.index)
    if td >= DAY:
        return S(np.asarray(fn(df), dtype=float), df)
    d = daily_bars(df)
    p = pd.Series(np.asarray(fn(d), dtype=float), index=d.index)
    p.index = p.index + (DAY - td)
    return p.reindex(df.index, method="ffill").fillna(0.0)


def zigzag(h, l, thr):
    """Nedensel ZigZag. Pivot, fiyat ondan thr kadar geri donunce ONAYLANIR (onay mumu i).
    Donus: [(tur 'H'/'L', fiyat, uc_mumu, onay_mumu), ...] onay sirasina gore."""
    piv = []
    d = 0
    hi = lo = ext = np.nan
    hi_i = lo_i = ei = 0
    for i in range(len(h)):
        t = thr[i]
        if np.isnan(t) or np.isnan(h[i]) or np.isnan(l[i]):
            continue
        if d == 0:
            if np.isnan(hi) or h[i] > hi:
                hi, hi_i = h[i], i
            if np.isnan(lo) or l[i] < lo:
                lo, lo_i = l[i], i
            if hi - lo >= t:
                if hi_i > lo_i:
                    piv.append(("L", lo, lo_i, i))
                    d, ext, ei = 1, hi, hi_i
                else:
                    piv.append(("H", hi, hi_i, i))
                    d, ext, ei = -1, lo, lo_i
        elif d == 1:
            if h[i] > ext:
                ext, ei = h[i], i
            elif ext - l[i] >= t:
                piv.append(("H", ext, ei, i))
                d, ext, ei = -1, l[i], i
        else:
            if l[i] < ext:
                ext, ei = l[i], i
            elif h[i] - ext >= t:
                piv.append(("L", ext, ei, i))
                d, ext, ei = 1, h[i], i
    return piv


# ---------------- 1-2. Elliott dalgasi (mekanik) ----------------
def _elliott(df, k, target):
    """Dalga 1 (L0->H1) + dalga 2 geri cekilme %38.2-78.6 (L2 > L0) -> fiyat H1'i kirinca al (dalga 3).
    Cikis: kapanis son onayli ZigZag dibinin altina inerse (dip yukseldikce stop yukselir) ya da
    hedef L2 + target*(H1-L0) gorulurse (target=0: hedef yok)."""
    h, l, c = (df[x].to_numpy(dtype=float) for x in ("high", "low", "close"))
    piv = zigzag(h, l, (k * atr(df, 14)).to_numpy())
    pos = np.zeros(len(c))
    p, stop, tgt, j = 0, np.nan, np.inf, 0
    conf, used = [], set()
    for i in range(len(c)):
        while j < len(piv) and piv[j][3] <= i:
            conf.append(piv[j])
            j += 1
        if p == 1:
            if conf and conf[-1][0] == "L" and conf[-1][1] > stop:
                stop = conf[-1][1]
            if c[i] < stop or c[i] >= tgt:
                p = 0
        if p == 0 and len(conf) >= 3:
            a, b, d = conf[-3:]
            if (a[0], b[0], d[0]) == ("L", "H", "L") and d[2] not in used:
                w1 = b[1] - a[1]
                retr = (b[1] - d[1]) / w1 if w1 > 0 else -1
                if d[1] > a[1] and 0.382 <= retr <= 0.786 and c[i] > b[1]:
                    p, stop = 1, d[1]
                    tgt = d[1] + target * w1 if target else np.inf
                    used.add(d[2])
        pos[i] = p
    return pos


def elliott_wave(df, ctx, k, target):
    return S(_elliott(df, k, target), df)


def elliott_wave_1d(df, ctx, k, target):
    return on_daily(df, lambda d: _elliott(d, k, target))


# ---------------- 3. Fibonacci geri cekilme ----------------
def fib_pullback(df, ctx, k, zone):
    """Yukselis trendinde (kapanis > SMA200) son bacak L0->H1; H1 onaylanip fiyat bacagin
    zone araligi kadar geri cekilince ve mum yukari kapaninca al. Cikis: H1'e donus (hedef) ya da L0 alti."""
    lo_r, hi_r = zone
    h, l, c = (df[x].to_numpy(dtype=float) for x in ("high", "low", "close"))
    trend = (df["close"] > sma(df["close"], 200)).to_numpy()
    piv = zigzag(h, l, (k * atr(df, 14)).to_numpy())
    pos = np.zeros(len(c))
    p, stop, tgt, j = 0, np.nan, np.nan, 0
    conf, used = [], set()
    for i in range(1, len(c)):
        while j < len(piv) and piv[j][3] <= i:
            conf.append(piv[j])
            j += 1
        if p == 1 and (c[i] < stop or c[i] >= tgt):
            p = 0
        if p == 0 and len(conf) >= 2 and trend[i]:
            a, b = conf[-2:]
            if (a[0], b[0]) == ("L", "H") and b[2] not in used and b[1] > a[1]:
                r = (b[1] - c[i]) / (b[1] - a[1])
                if lo_r <= r <= hi_r and c[i] > c[i - 1]:
                    p, stop, tgt = 1, a[1], b[1]
                    used.add(b[2])
        pos[i] = p
    return S(pos, df)


# ---------------- 4. Mum formasyonlari ----------------
def candles(df, ctx, pattern, hold):
    o, h, l, c = df["open"], df["high"], df["low"], df["close"]
    body, rng = (c - o).abs(), h - l
    engulf = (c.shift(1) < o.shift(1)) & (c > o) & (o <= c.shift(1)) & (c >= o.shift(1))
    lower, upper = np.minimum(o, c) - l, h - np.maximum(o, c)
    hammer = (lower >= 2 * body) & (upper <= 0.25 * rng) & (rng > 0) & (c < c.shift(6))
    sig = {"engulf": engulf, "hammer": hammer, "any": engulf | hammer}[pattern]
    return S(timed(sig & (c > sma(c, 200)), hold), df)


# ---------------- 5. Heikin-Ashi (guclu mum) ----------------
def ha_strong(df, ctx, n):
    """Tur 1'deki heikin_ashi'den farkli kural: n ardisik alt fitilsiz yukselis HA mumu -> al;
    ilk dusus HA mumu -> sat."""
    o, l = df["open"].to_numpy(), df["low"].to_numpy()
    hc = ((df["open"] + df["high"] + df["low"] + df["close"]) / 4).to_numpy()
    ho = np.zeros(len(hc))
    ho[0] = (o[0] + df["close"].iloc[0]) / 2
    for i in range(1, len(hc)):
        ho[i] = (ho[i - 1] + hc[i - 1]) / 2
    strong = pd.Series((hc > ho) & (l >= ho), index=df.index).astype(float)
    enter = strong.rolling(n).sum() == n
    p = machine(enter, hc < ho)
    p[:20] = 0.0
    return S(p, df)


# ---------------- 6-9. Mevsimsellik ----------------
def _slot_rank(df, slot_now, slot_next, nslots, L, k):
    """Her slotun son L gunluk ortalama mum getirisi (t dahil, t'ye kadar bilinen). Siradaki mumun slotu
    ilk k slot icindeyse ve ortalamasi > 0 ise t'de pozisyon al."""
    ppd = max(1, int(round(DAY / bar_td(df.index))))
    r = df["close"].pct_change()
    win = int(L * ppd)
    M = pd.DataFrame({s: r.where(slot_now == s).rolling(win, min_periods=max(10, win // (3 * nslots))).mean()
                      for s in range(nslots)}, index=df.index)
    R = M.rank(axis=1, ascending=False)
    rows = np.arange(len(df))
    nxt = np.asarray(slot_next)
    m_next = M.to_numpy()[rows, nxt]
    r_next = R.to_numpy()[rows, nxt]
    return S((r_next <= k) & (m_next > 0), df)


def season_hour(df, ctx, L, k):
    """Gun ici saat etkisi (4 saatlik 6 dilim). Gunluk mumda anlamsiz (tek dilim)."""
    td = bar_td(df.index)
    nslots = max(1, int(round(DAY / td)))
    hours = lambda ix: (ix.hour // max(1, int(td / pd.Timedelta(hours=1)))) % nslots if nslots > 1 else np.zeros(len(ix), int)
    return _slot_rank(df, np.asarray(hours(df.index)), np.asarray(hours(next_times(df))), nslots, L, k)


def season_dow(df, ctx, L, k):
    """Haftanin gunu etkisi: son L gunde en iyi k gun (getirisi > 0) tutulur."""
    return _slot_rank(df, np.asarray(df.index.dayofweek), np.asarray(next_times(df).dayofweek), 7, L, k)


def turn_of_month(df, ctx, before, after):
    nt = next_times(df)
    d, dim = nt.day, nt.days_in_month
    return S((d <= after) | (d > dim - before), df)


def weekend(df, ctx, mode):
    wd = next_times(df).dayofweek
    return S(wd >= 5 if mode == "weekend" else wd < 5, df)


# ---------------- 10-11. Oynaklik sikismasi ----------------
def squeeze_breakout(df, ctx, n, q):
    """Bollinger genisligi son 1 yilin q yuzdeliginin altina indikten sonraki 6 mum icinde ust banda
    kirilim -> al; orta bandin altinda -> sat."""
    c = df["close"]
    m, sd = sma(c, n), c.rolling(n).std()
    width = 4 * sd / m
    ppy = int(ctx["ppy"])
    lim = width.rolling(ppy, min_periods=ppy // 2).quantile(q)
    squeezed = (width < lim).astype(float).rolling(6, min_periods=1).max().shift(1) > 0
    return S(machine(squeezed & (c > m + 2 * sd), c < m), df)


def nr_breakout(df, ctx, n, hold):
    """NR-n: son n mumun en dar araligi; sonraki mum onun tepesini kirarsa al, hold mum tut."""
    rng = df["high"] - df["low"]
    nr = rng <= rng.rolling(n).min()
    sig = nr.shift(1, fill_value=False) & (df["close"] > df["high"].shift(1))
    return S(timed(sig, hold), df)


# ---------------- 12. Kalman trend ----------------
def kalman_trend(df, ctx, qs, z):
    """Log fiyata yerel dogrusal trend modeli (seviye + egim). Filtrelenmis egim / std > z ise tut."""
    y = np.log(df["close"].to_numpy(dtype=float))
    rv = pd.Series(y).diff().rolling(500, min_periods=100).var().to_numpy()
    F = np.array([[1.0, 1.0], [0.0, 1.0]])
    x = np.array([y[0], 0.0])
    P = np.eye(2)
    out = np.zeros(len(y))
    for i in range(1, len(y)):
        R = rv[i - 1]
        if np.isnan(R) or np.isnan(y[i]):
            x = np.array([y[i] if not np.isnan(y[i]) else x[0], 0.0])
            continue
        x = F @ x
        P = F @ P @ F.T + np.diag([0.01 * R, qs * R])
        sk = P[0, 0] + R
        K = P[:, 0] / sk
        x = x + K * (y[i] - x[0])
        P = P - np.outer(K, P[0, :])
        out[i] = 1.0 if x[1] / math.sqrt(max(P[1, 1], 1e-18)) > z else 0.0
    out[:200] = 0.0
    return S(out, df)


# ---------------- 13. HMM rejim ----------------
def _hmm_fit(x, iters=25):
    """2 durumlu Gauss HMM, Baum-Welch (olcekli ileri-geri). Yalniz verilen (gecmis) pencereye uyar."""
    mu = np.array([x.mean(), x.mean()])
    sd = np.array([x.std() * 0.6, x.std() * 1.6])
    A = np.array([[0.97, 0.03], [0.03, 0.97]])
    pi = np.array([0.5, 0.5])
    n = len(x)
    for _ in range(iters):
        B = np.exp(-0.5 * ((x[:, None] - mu) / sd) ** 2) / sd + 1e-300
        b0, b1 = B[:, 0].tolist(), B[:, 1].tolist()
        a00, a01, a10, a11 = A[0, 0], A[0, 1], A[1, 0], A[1, 1]
        al0, al1, sc = [0.0] * n, [0.0] * n, [0.0] * n
        f0, f1 = pi[0] * b0[0], pi[1] * b1[0]
        s = f0 + f1
        al0[0], al1[0], sc[0] = f0 / s, f1 / s, s
        for t in range(1, n):
            f0 = (al0[t - 1] * a00 + al1[t - 1] * a10) * b0[t]
            f1 = (al0[t - 1] * a01 + al1[t - 1] * a11) * b1[t]
            s = f0 + f1
            al0[t], al1[t], sc[t] = f0 / s, f1 / s, s
        be0, be1 = [1.0] * n, [1.0] * n
        for t in range(n - 2, -1, -1):
            u0, u1 = b0[t + 1] * be0[t + 1], b1[t + 1] * be1[t + 1]
            be0[t] = (a00 * u0 + a01 * u1) / sc[t + 1]
            be1[t] = (a10 * u0 + a11 * u1) / sc[t + 1]
        al = np.column_stack([al0, al1])
        be = np.column_stack([be0, be1])
        g = al * be
        g /= g.sum(axis=1, keepdims=True)
        M = al[:-1, :, None] * A[None] * (B[1:] * be[1:])[:, None, :]
        M /= M.sum(axis=(1, 2), keepdims=True)
        xi = M.sum(axis=0)
        A = xi / xi.sum(axis=1, keepdims=True)
        pi = g[0]
        w = g.sum(axis=0)
        mu = (g * x[:, None]).sum(axis=0) / w
        sd = np.sqrt((g * (x[:, None] - mu) ** 2).sum(axis=0) / w).clip(min=1e-6)
    return mu, sd, A


def _hmm_filter(x, mu, sd, A, p0):
    """Ileri filtre: out[t] yalniz x[0..t] ile hesaplanir."""
    B = np.exp(-0.5 * ((x[:, None] - mu) / sd) ** 2) / sd + 1e-300
    b0, b1 = B[:, 0].tolist(), B[:, 1].tolist()
    a00, a01, a10, a11 = A[0, 0], A[0, 1], A[1, 0], A[1, 1]
    out = np.zeros((len(x), 2))
    p, q = p0
    for t in range(len(x)):
        f0 = (p * a00 + q * a10) * b0[t]
        f1 = (p * a01 + q * a11) * b1[t]
        s = f0 + f1
        p, q = f0 / s, f1 / s
        out[t] = (p, q)
    return out


def hmm_bull_prob(df):
    """Her 180 gunde bir, onceki 730 gunun mum getirileriyle (yalniz gecmis) 2 durumlu HMM kurulur;
    sonraki 180 gun icin ileri-filtre (yalniz t'ye kadar veri) ile 'yukselis' durumu olasiligi."""
    k = key_of(df, "hmm")
    if k in _CACHE:
        return _CACHE[k]
    ppd = max(1, int(round(DAY / bar_td(df.index))))
    x = np.log(df["close"]).diff().to_numpy()
    n = len(x)
    out = np.full(n, np.nan)
    step, train, first = 180 * ppd, 730 * ppd, 365 * ppd
    R = first
    while R < n:
        lo = max(1, R - train)
        xt = x[lo:R]
        xt = xt[~np.isnan(xt)]
        if len(xt) > 200:
            mu, sd, A = _hmm_fit(xt)
            bull = int(np.argmax(mu))
            seg = np.nan_to_num(x[lo:min(R + step, n)])
            f = _hmm_filter(seg, mu, sd, A, np.array([0.5, 0.5]))
            out[R:min(R + step, n)] = f[R - lo:, bull]
        R += step
    s = pd.Series(out, index=df.index)
    _CACHE[k] = s
    return s


def hmm_regime(df, ctx, thr, trend):
    pb = hmm_bull_prob(df)
    c = df["close"]
    ok = (c > sma(c, trend)) if trend else pd.Series(True, index=df.index)
    return S((pb > thr) & ok, df)


# ---------------- 14-15. Makine ogrenmesi (walk-forward icinde egitim) ----------------
def ml_features(df):
    c, v = df["close"], df["volume"]
    lr = np.log(c).diff()
    F = pd.DataFrame({f"r{n}": np.log(c / c.shift(n)) for n in (1, 3, 6, 12, 24, 48)}, index=df.index)
    F["vol24"] = lr.rolling(24).std()
    F["volr"] = F["vol24"] / lr.rolling(120).std()
    F["d50"] = np.log(c / sma(c, 50))
    F["d200"] = np.log(c / sma(c, 200))
    F["rsi"] = rsi(c, 14) / 100
    lv = np.log(v + 1)
    F["vz"] = lv - lv.rolling(50).mean()
    hr, dw = df.index.hour.to_numpy(), df.index.dayofweek.to_numpy()
    F["hs"], F["hc"] = np.sin(2 * np.pi * hr / 24), np.cos(2 * np.pi * hr / 24)
    F["ds"], F["dc"] = np.sin(2 * np.pi * dw / 7), np.cos(2 * np.pi * dw / 7)
    return F


def ml_prob(df, model, h):
    """Her 180 gunde yeniden egitim. Egitim ornegi s'nin etiketi (c[s+h] > c[s]) karar aninda (R) tamamen
    bilinmeli: s + h <= R - 1. Tahmin R..R+180gun-1 mumlarina; o mumlarin ozellikleri yalniz gecmisten."""
    k = key_of(df, model, h)
    if k in _CACHE:
        return _CACHE[k]
    from sklearn.ensemble import HistGradientBoostingClassifier
    from sklearn.linear_model import LogisticRegression
    from sklearn.pipeline import make_pipeline
    from sklearn.preprocessing import StandardScaler

    ppd = max(1, int(round(DAY / bar_td(df.index))))
    F = ml_features(df).replace([np.inf, -np.inf], np.nan)
    X = F.to_numpy()
    c = df["close"].to_numpy(dtype=float)
    y = np.full(len(c), np.nan)
    y[:-h] = (c[h:] > c[:-h]).astype(float)
    ok = ~np.isnan(X).any(axis=1)
    n = len(c)
    out = np.full(n, np.nan)
    step, train, first = 180 * ppd, 730 * ppd, 365 * ppd
    R = first
    while R < n:
        idx = np.arange(max(0, R - train), R - h)  # s <= R-h-1
        idx = idx[ok[idx] & ~np.isnan(y[idx])]
        if len(idx) > 300 and len(np.unique(y[idx])) == 2:
            if model == "logit":
                m = make_pipeline(StandardScaler(), LogisticRegression(C=0.1, max_iter=500))
            else:
                m = HistGradientBoostingClassifier(max_iter=150, learning_rate=0.05, max_depth=3,
                                                   min_samples_leaf=200, random_state=0)
            m.fit(X[idx], y[idx])
            te = np.arange(R, min(R + step, n))
            te = te[ok[te]]
            if len(te):
                out[te] = m.predict_proba(X[te])[:, 1]
        R += step
    s = pd.Series(out, index=df.index)
    _CACHE[k] = s
    return s


def ml_logit(df, ctx, h, thr):
    return S(ml_prob(df, "logit", h) > thr, df)


def ml_gbm(df, ctx, h, thr):
    return S(ml_prob(df, "gbm", h) > thr, df)


# ---------------- 19-20. Hacim ----------------
def vol_spike_breakout(df, ctx, k, n, hold):
    c, v = df["close"], df["volume"]
    spike = v > k * v.rolling(50).mean().shift(1)
    brk = c > df["high"].rolling(n).max().shift(1)
    return S(timed(spike & brk, hold), df)


def vol_divergence(df, ctx, n, hold):
    """Fiyat n mumun yeni dibini yapar ama OBV yapmaz (satis baskisi zayifliyor) -> al, hold mum tut."""
    c, v = df["close"], df["volume"]
    obv = (np.sign(c.diff()).fillna(0) * v).cumsum()
    sig = (c < c.rolling(n).min().shift(1)) & (obv > obv.rolling(n).min().shift(1))
    return S(timed(sig, hold), df)


# ---------------- 21-23. Dis veri ----------------
def fng_contrarian(df, ctx, lo, hi):
    """Korku/acgozluluk endeksi lo altinda (asiri korku) al, hi ustunde sat.
    Gun D degeri D+1 00:00'dan itibaren kullanilir (1 gun gecikme)."""
    f = asof(ctx["fng"], df.index, DAY)
    return S(machine(f < lo, f > hi), df)


def fng_trend(df, ctx, n):
    f = ctx["fng"]
    sig = (f > f.rolling(n).mean()).astype(float).where(f.rolling(n).mean().notna())
    return S(asof(sig, df.index, DAY), df)


def funding_contrarian(df, ctx, n, q):
    """BTC vadeli fonlama orani (son n kaydin ortalamasi) son 1 yilin q yuzdeligini asarsa (kalabalik long)
    nakit; degilse tut. Kayit fundingTime aninda bilinir; mum acilisina gore eslenir."""
    fr = ctx["funding"]
    fa = fr.rolling(n).mean()
    lim = fa.rolling(3 * 365, min_periods=180).quantile(q)
    sig = (fa <= lim).astype(float).where(lim.notna())
    return S(asof(sig, df.index, pd.Timedelta(0)), df)


# ---------------- 24. Halving dongusu ----------------
def halving_cycle(df, ctx, months):
    nt = next_times(df)
    inside = np.zeros(len(nt), dtype=bool)
    for hv in HALVINGS:
        inside |= (nt >= hv) & (nt < hv + pd.DateOffset(months=months))
    return S(inside, df)


# ---------------- 25. Coklu zaman dilimi ----------------
def mtf_trend(df, ctx, n, m):
    """Gunluk trend (gunluk kapanis > gunluk EMA n) VE alt aralikta kapanis > EMA m."""
    daily = on_daily(df, lambda d: (d["close"] > ema(d["close"], n)).astype(float).to_numpy()
                     * (np.arange(len(d)) >= n))
    c = df["close"]
    return S((daily > 0) & (c > ema(c, m)), df)


# ---------------- 26-28. Diger ----------------
def variance_ratio_gate(df, ctx, w, q):
    """Varyans orani > 1 (getiriler ayni yone devam ediyor) ve kapanis > SMA(w)."""
    lc = np.log(df["close"])
    r1, rq = lc.diff(), lc - lc.shift(q)
    vr = rq.rolling(w).var() / (q * r1.rolling(w).var())
    return S((vr > 1) & (df["close"] > sma(df["close"], w)), df)


def near_high(df, ctx, n, x):
    """Kapanis son n mumun zirvesine x orani kadar yakinsa tut."""
    return S(df["close"] >= (1 - x) * df["high"].rolling(n).max(), df)


def btc_leadlag(df, ctx, k, hold):
    """BTC son mumda k*oynaklik ustu yukselirse coini hold mum tut (BTC onde, altlar arkadan gelir)."""
    b = ctx["btc"]["close"]
    br = b.pct_change()
    sig = (br > k * br.rolling(42).std().shift(1)).reindex(df.index).fillna(False)
    return S(timed(sig, hold), df)


SINGLE2 = {
    "elliott_wave": (elliott_wave, {"k": [3, 5, 8], "target": [0, 1.618, 2.618]}),
    "elliott_wave_1d": (elliott_wave_1d, {"k": [2, 3, 5], "target": [0, 1.618, 2.618]}),
    "fib_pullback": (fib_pullback, {"k": [3, 5, 8], "zone": [(0.382, 0.618), (0.5, 0.786)]}),
    "candles": (candles, {"pattern": ["engulf", "hammer", "any"], "hold": [6, 12, 24]}),
    "ha_strong": (ha_strong, {"n": [1, 2, 3]}),
    "season_hour": (season_hour, {"L": [90, 180, 365], "k": [1, 2, 3]}),
    "season_dow": (season_dow, {"L": [180, 365, 730], "k": [2, 3, 4]}),
    "turn_of_month": (turn_of_month, {"before": [1, 2, 3], "after": [2, 3, 5]}),
    "weekend": (weekend, {"mode": ["weekend", "weekday"]}),
    "squeeze_breakout": (squeeze_breakout, {"n": [20, 50], "q": [0.1, 0.25]}),
    "nr_breakout": (nr_breakout, {"n": [4, 7], "hold": [6, 12, 24]}),
    "kalman_trend": (kalman_trend, {"qs": [1e-5, 1e-4, 1e-3], "z": [0.0, 1.0]}),
    "hmm_regime": (hmm_regime, {"thr": [0.5, 0.7], "trend": [0, 200]}),
    "ml_logit": (ml_logit, {"h": [1, 6], "thr": [0.5, 0.55]}),
    "ml_gbm": (ml_gbm, {"h": [1, 6], "thr": [0.5, 0.55]}),
    "vol_spike_breakout": (vol_spike_breakout, {"k": [2, 3], "n": [20, 55], "hold": [6, 24]}),
    "vol_divergence": (vol_divergence, {"n": [20, 50], "hold": [6, 12, 24]}),
    "fng_contrarian": (fng_contrarian, {"lo": [20, 25, 30], "hi": [50, 65, 80]}),
    "fng_trend": (fng_trend, {"n": [7, 14, 30]}),
    "funding_contrarian": (funding_contrarian, {"n": [3, 9], "q": [0.5, 0.7, 0.9]}),
    "halving_cycle": (halving_cycle, {"months": [12, 15, 18]}),
    "mtf_trend": (mtf_trend, {"n": [50, 100, 200], "m": [20, 50]}),
    "variance_ratio_gate": (variance_ratio_gate, {"w": [180, 360], "q": [6, 24]}),
    "near_high": (near_high, {"n": [360, 1080], "x": [0.05, 0.1, 0.2]}),
    "btc_leadlag": (btc_leadlag, {"k": [1, 2], "hold": [1, 3, 6]}),
}
NEEDS = {"fng_contrarian": "fng", "fng_trend": "fng", "funding_contrarian": "funding"}


# ---------------- 16-18. Portfoy stratejileri ----------------
def _daily_rebalance(w, ppd):
    """Gunde bir yeniden dengeleme: gunun ilk (00:00 UTC) mumunda; veri boslugunda faz kaymaz."""
    keep = np.asarray(w.index.hour == 0) if ppd > 1 else np.ones(len(w), dtype=bool)
    return w.where(np.repeat(keep[:, None], w.shape[1], axis=1)).ffill().fillna(0.0)


def eth_btc_rot(closes, ctx, n, m):
    """ETH/BTC orani EMA(n) ustundeyse ETH, degilse BTC; secilen kendi EMA(m) ustunde degilse nakit."""
    w = pd.DataFrame(0.0, index=closes.index, columns=closes.columns)
    if "BTCUSDT" not in closes or "ETHUSDT" not in closes:
        return w
    b, e = closes["BTCUSDT"], closes["ETHUSDT"]
    ratio = e / b
    strong = ratio > ema(ratio, n)
    w["ETHUSDT"] = (strong & (e > ema(e, m))).astype(float)
    w["BTCUSDT"] = (~strong & (b > ema(b, m))).astype(float)
    w.iloc[: max(n, m)] = 0.0
    return _daily_rebalance(w, ctx["ppd"])


def xs_reversal(closes, ctx, lb, k):
    """Kisa vadeli tersine donus: son lb mumda EN COK dusen k coin, gunluk yeniden dengeleme."""
    r = closes.pct_change(lb, fill_method=None)
    rank = r.rank(axis=1, ascending=True)
    w = (rank <= k).astype(float) / k
    return _daily_rebalance(w, ctx["ppd"])


def xs_lowvol(closes, ctx, lb, k):
    """En dusuk oynaklikli k coin, gunluk yeniden dengeleme."""
    vol = closes.pct_change(fill_method=None).rolling(lb).std()
    rank = vol.rank(axis=1, ascending=True)
    w = (rank <= k).astype(float) / k
    return _daily_rebalance(w, ctx["ppd"])


PORTFOLIO2 = {
    "eth_btc_rot": (eth_btc_rot, {"n": [42, 84, 180], "m": [100, 200]}),
    "xs_reversal": (xs_reversal, {"lb": [6, 18, 42], "k": [1, 2, 3]}),
    "xs_lowvol": (xs_lowvol, {"lb": [42, 180], "k": [1, 2, 3]}),
}
