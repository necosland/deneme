"""Turnuva stratejileri. Hepsi long-only spot.
Kural: her fonksiyon mum KAPANISINDA bilinen bilgiyle pozisyon (0..1) uretir.
Backtest bu sinyali bir sonraki mumda uygular (lookahead yok).
Imza: fn(df, ctx, **param) -> pd.Series (index=df.index, deger 0..1)
ctx: {"ppy": yillik mum sayisi, "btc": BTC df (filtre icin)}
"""
import numpy as np
import pandas as pd


# ---------------- yardimci gostergeler ----------------
def ema(s, n):
    return s.ewm(span=n, adjust=False).mean()


def sma(s, n):
    return s.rolling(n).mean()


def wilder(s, n):
    return s.ewm(alpha=1 / n, adjust=False).mean()


def atr(df, n=14):
    c1 = df["close"].shift(1)
    tr = pd.concat([df["high"] - df["low"], (df["high"] - c1).abs(), (df["low"] - c1).abs()], axis=1).max(axis=1)
    return wilder(tr, n)


def rsi(c, n=14):
    d = c.diff()
    up = wilder(d.clip(lower=0), n)
    dn = wilder((-d).clip(lower=0), n)
    return 100 - 100 / (1 + up / dn.replace(0, np.nan))


def wma(s, n):
    n = int(n)
    w = np.arange(1, n + 1, dtype=float)
    v = s.to_numpy(dtype=float)
    out = np.full(len(v), np.nan)
    if len(v) >= n:
        conv = np.convolve(v, w[::-1], mode="valid") / w.sum()
        out[n - 1:] = conv
    return pd.Series(out, index=s.index)


def hma(s, n):
    return wma(2 * wma(s, n // 2) - wma(s, n), int(np.sqrt(n)))


def machine(enter, exit_):
    """Durum makinesi: duzken enter -> al, longken exit -> sat."""
    en = np.nan_to_num(np.asarray(enter, dtype=float)).astype(bool)
    ex = np.nan_to_num(np.asarray(exit_, dtype=float)).astype(bool)
    pos = np.zeros(len(en))
    p = 0.0
    for i in range(len(en)):
        if p == 0.0 and en[i]:
            p = 1.0
        elif p == 1.0 and ex[i]:
            p = 0.0
        pos[i] = p
    return pos


def timed(enter, hold):
    """enter gelince hold mum tut; tutarken yeni sinyal suresi uzatir."""
    en = np.nan_to_num(np.asarray(enter, dtype=float)).astype(bool)
    pos = np.zeros(len(en))
    left = 0
    for i in range(len(en)):
        if en[i]:
            left = hold
        pos[i] = 1.0 if left > 0 else 0.0
        left = max(left - 1, 0)
    return pos


def S(x, df):
    s = pd.Series(np.asarray(x, dtype=float), index=df.index)
    return s.fillna(0.0)


# ---------------- stratejiler ----------------
def ema_cross(df, ctx, fast, slow):
    c = df["close"]
    p = (ema(c, fast) > ema(c, slow)).astype(float)
    p.iloc[:slow] = 0.0
    return p


def sma_cross(df, ctx, fast, slow):
    c = df["close"]
    return S(sma(c, fast) > sma(c, slow), df)


def donchian(df, ctx, entry, exit):
    hh = df["high"].rolling(entry).max().shift(1)
    ll = df["low"].rolling(exit).min().shift(1)
    return S(machine(df["close"] > hh, df["close"] < ll), df)


def ma_filter(df, ctx, n):
    return S(df["close"] > sma(df["close"], n), df)


def tsmom(df, ctx, lb):
    return S(df["close"].pct_change(lb) > 0, df)


def tsmom_vote(df, ctx, base):
    c = df["close"]
    votes = [(c.pct_change(base * m) > 0).astype(float) for m in (1, 2, 4, 8)]
    v = sum(votes) / 4.0
    v.iloc[: base * 8] = 0.0
    return v


def macd(df, ctx, m):
    c = df["close"]
    line = ema(c, 12 * m) - ema(c, 26 * m)
    hist = line - ema(line, 9 * m)
    p = (hist > 0).astype(float)
    p.iloc[: 35 * m] = 0.0
    return p


def supertrend(df, ctx, n, mult):
    a = atr(df, n).to_numpy()
    hl2 = ((df["high"] + df["low"]) / 2).to_numpy()
    c = df["close"].to_numpy()
    ub, lb = hl2 + mult * a, hl2 - mult * a
    pos = np.zeros(len(c))
    fu, fl = ub.copy(), lb.copy()
    trend = 0
    for i in range(1, len(c)):
        if np.isnan(a[i]):
            continue
        fu[i] = ub[i] if (np.isnan(fu[i - 1]) or ub[i] < fu[i - 1] or c[i - 1] > fu[i - 1]) else fu[i - 1]
        fl[i] = lb[i] if (np.isnan(fl[i - 1]) or lb[i] > fl[i - 1] or c[i - 1] < fl[i - 1]) else fl[i - 1]
        if c[i] > fu[i - 1]:
            trend = 1
        elif c[i] < fl[i - 1]:
            trend = 0
        pos[i] = trend
    return S(pos, df)


def keltner_breakout(df, ctx, n, mult):
    c = df["close"]
    mid = ema(c, n)
    return S(machine(c > mid + mult * atr(df, n), c < mid), df)


def bb_breakout(df, ctx, n, k):
    c = df["close"]
    m, sd = sma(c, n), c.rolling(n).std()
    return S(machine(c > m + k * sd, c < m), df)


def rsi_mr(df, ctx, lo, trend):
    c = df["close"]
    r = rsi(c, 14)
    ok = (c > sma(c, trend)) if trend else pd.Series(True, index=df.index)
    return S(machine((r < lo) & ok, r > 55), df)


def bb_mr(df, ctx, n, k):
    c = df["close"]
    m, sd = sma(c, n), c.rolling(n).std()
    return S(machine(c < m - k * sd, c > m), df)


def connors_rsi2(df, ctx, lo, ma):
    c = df["close"]
    return S(machine((rsi(c, 2) < lo) & (c > sma(c, ma)), c > sma(c, 5)), df)


def turtle_atr_stop(df, ctx, entry, mult):
    """Donchian girisi + chandelier (iz suren) ATR stop cikisi."""
    c = df["close"].to_numpy()
    hh = df["high"].rolling(entry).max().shift(1).to_numpy()
    a = atr(df, 20).to_numpy()
    pos = np.zeros(len(c))
    p, peak = 0.0, 0.0
    for i in range(len(c)):
        if p == 0.0 and not np.isnan(hh[i]) and c[i] > hh[i]:
            p, peak = 1.0, c[i]
        elif p == 1.0:
            peak = max(peak, c[i])
            if c[i] < peak - mult * a[i]:
                p = 0.0
        pos[i] = p
    return S(pos, df)


def kama_trend(df, ctx, n):
    c = df["close"].to_numpy()
    out = np.full(len(c), np.nan)
    fsc, ssc = 2 / 3, 2 / 31
    for i in range(n, len(c)):
        ch = abs(c[i] - c[i - n])
        vol = np.abs(np.diff(c[i - n:i + 1])).sum()
        er = ch / vol if vol > 0 else 0
        sc = (er * (fsc - ssc) + ssc) ** 2
        prev = out[i - 1] if not np.isnan(out[i - 1]) else c[i - 1]
        out[i] = prev + sc * (c[i] - prev)
    return S(c > out, df)


def hma_slope(df, ctx, n):
    h = hma(df["close"], n)
    return S(h > h.shift(1), df)


def adx_trend(df, ctx, n, thr):
    up = df["high"].diff()
    dn = -df["low"].diff()
    pdm = np.where((up > dn) & (up > 0), up, 0.0)
    mdm = np.where((dn > up) & (dn > 0), dn, 0.0)
    a = atr(df, n)
    pdi = 100 * wilder(pd.Series(pdm, index=df.index), n) / a
    mdi = 100 * wilder(pd.Series(mdm, index=df.index), n) / a
    dx = 100 * (pdi - mdi).abs() / (pdi + mdi)
    adx = wilder(dx, n)
    p = ((pdi > mdi) & (adx > thr)).astype(float)
    p.iloc[: 3 * n] = 0.0
    return p


def ichimoku(df, ctx, scale):
    h, l, c = df["high"], df["low"], df["close"]
    t, k, b = 9 * scale, 26 * scale, 52 * scale
    tenkan = (h.rolling(t).max() + l.rolling(t).min()) / 2
    kijun = (h.rolling(k).max() + l.rolling(k).min()) / 2
    span_a = ((tenkan + kijun) / 2).shift(k)  # bulut k mum ileri cizilir -> bugun k mum onceki deger
    span_b = ((h.rolling(b).max() + l.rolling(b).min()) / 2).shift(k)
    top = np.maximum(span_a, span_b)
    bot = np.minimum(span_a, span_b)
    return S(machine((c > top) & (tenkan > kijun), c < bot), df)


def heikin_ashi(df, ctx, n):
    o, h, l, c = [ema(df[x], n) if n > 1 else df[x] for x in ("open", "high", "low", "close")]
    hc = ((o + h + l + c) / 4).to_numpy()
    ho = np.zeros(len(hc))
    ov, cv = o.to_numpy(), c.to_numpy()
    ho[0] = (ov[0] + cv[0]) / 2
    for i in range(1, len(hc)):
        ho[i] = (ho[i - 1] + hc[i - 1]) / 2
    pos = (hc > ho).astype(float)
    pos[: 3 * n] = 0.0
    return S(pos, df)


def range_expansion(df, ctx, k, hold):
    """Tek mumda k*ATR'den buyuk yukari hareket -> hold mum tut (momentum patlamasi)."""
    c = df["close"]
    sig = (c - c.shift(1)) > k * atr(df, 14).shift(1)
    return S(timed(sig, hold), df)


def linreg_tstat(df, ctx, n, thr):
    y = np.log(df["close"])
    t = pd.Series(np.arange(len(y), dtype=float), index=df.index)
    r = y.rolling(n).corr(t)
    tstat = r * np.sqrt(n - 2) / np.sqrt((1 - r ** 2).clip(lower=1e-12))
    return S(tstat > thr, df)


def obv_trend(df, ctx, n):
    c = df["close"]
    obv = (np.sign(c.diff()).fillna(0) * df["volume"]).cumsum()
    p = ((obv > ema(obv, n)) & (c > ema(c, n))).astype(float)
    p.iloc[:n] = 0.0
    return p


def vwap_trend(df, ctx, n):
    c, v = df["close"], df["volume"]
    vw = (c * v).rolling(n).sum() / v.rolling(n).sum()
    return S(c > vw, df)


def trend_lowvol(df, ctx, pair, q):
    """EMA kesisimi, ama yalnizca oynaklik son 1 yilin q yuzdeliginin altindaysa."""
    fast, slow = pair
    base = ema_cross(df, ctx, fast, slow)
    rv = df["close"].pct_change().rolling(42).std()
    lim = rv.rolling(int(ctx["ppy"]), min_periods=int(ctx["ppy"] // 2)).quantile(q)
    return S(base.astype(bool) & (rv < lim), df)


def psar(df, ctx, step, amax):
    h, l, c = df["high"].to_numpy(), df["low"].to_numpy(), df["close"].to_numpy()
    pos = np.zeros(len(c))
    up, af = True, step
    ep, sar = h[0], l[0]
    for i in range(1, len(c)):
        sar = sar + af * (ep - sar)
        if up:
            sar = min(sar, l[i - 1], l[i - 2] if i > 1 else l[i - 1])
            if l[i] < sar:
                up, sar, ep, af = False, ep, l[i], step
            elif h[i] > ep:
                ep, af = h[i], min(af + step, amax)
        else:
            sar = max(sar, h[i - 1], h[i - 2] if i > 1 else h[i - 1])
            if h[i] > sar:
                up, sar, ep, af = True, ep, h[i], step
            elif l[i] < ep:
                ep, af = l[i], min(af + step, amax)
        pos[i] = 1.0 if up else 0.0
    pos[:20] = 0.0
    return S(pos, df)


def stoch_pullback(df, ctx, trend, lo):
    c = df["close"]
    ll, hh = df["low"].rolling(14).min(), df["high"].rolling(14).max()
    k = 100 * (c - ll) / (hh - ll)
    m = sma(c, trend)
    return S(machine((c > m) & (k < lo), (k > 80) | (c < m)), df)


def btc_filter_ema(df, ctx, fast, slow):
    """Varligin kendi EMA trendi + BTC'nin EMA trendi ikisi de yukari."""
    own = ema_cross(df, ctx, fast, slow)
    b = ctx["btc"]
    bt = ema_cross(b, ctx, fast, slow).reindex(df.index).ffill().fillna(0.0)
    return own * bt


def voltarget_ema(df, ctx, pair, tv):
    fast, slow = pair
    base = ema_cross(df, ctx, fast, slow)
    rv = df["close"].pct_change().rolling(60).std() * np.sqrt(ctx["ppy"])
    size = (tv / rv).clip(upper=1.0)
    size = (size * 4).round() / 4  # 0.25'lik adimlar: kucuk degisimde islem yok
    return S(base * size, df)


def dip_buy(df, ctx, nd, hold):
    """Yukselen trendde (SMA200 ustu) nd ardisik dusus kapanisi -> hold mum tut."""
    c = df["close"]
    down = (c < c.shift(1)).astype(int)
    streak = down.rolling(nd).sum() == nd
    return S(timed(streak & (c > sma(c, 200)), hold), df)


def donchian_vote(df, ctx, base):
    """Birden fazla Donchian periyodunun ortalamasi (kademeli pozisyon)."""
    parts = [donchian(df, ctx, base * m, max(base * m // 2, 2)) for m in (1, 2, 4)]
    return sum(parts) / 3.0


# Tek varlik stratejileri: ad -> (fn, parametre izgarasi)
SINGLE = {
    "ema_cross": (ema_cross, {"fast": [10, 20, 50], "slow": [100, 150, 200]}),
    "sma_cross": (sma_cross, {"fast": [10, 20, 50], "slow": [100, 150, 200]}),
    "donchian": (donchian, {"entry": [20, 55, 100], "exit": [10, 20, 40]}),
    "ma_filter": (ma_filter, {"n": [50, 100, 200, 400]}),
    "tsmom": (tsmom, {"lb": [30, 90, 180, 360]}),
    "tsmom_vote": (tsmom_vote, {"base": [15, 30, 60]}),
    "macd": (macd, {"m": [1, 2, 3, 4]}),
    "supertrend": (supertrend, {"n": [10, 20], "mult": [2.0, 3.0, 4.0]}),
    "keltner_breakout": (keltner_breakout, {"n": [20, 50, 100], "mult": [1.0, 2.0]}),
    "bb_breakout": (bb_breakout, {"n": [20, 50, 100], "k": [1.0, 2.0]}),
    "rsi_mr": (rsi_mr, {"lo": [25, 30, 35], "trend": [0, 200]}),
    "bb_mr": (bb_mr, {"n": [20, 50], "k": [1.5, 2.0, 2.5]}),
    "connors_rsi2": (connors_rsi2, {"lo": [5, 10, 15], "ma": [100, 200]}),
    "turtle_atr_stop": (turtle_atr_stop, {"entry": [20, 55, 100], "mult": [2.0, 3.0, 4.0]}),
    "kama_trend": (kama_trend, {"n": [10, 20, 40, 80]}),
    "hma_slope": (hma_slope, {"n": [20, 50, 100, 200]}),
    "adx_trend": (adx_trend, {"n": [14, 28], "thr": [15, 20, 25]}),
    "ichimoku": (ichimoku, {"scale": [1, 2, 3]}),
    "heikin_ashi": (heikin_ashi, {"n": [1, 5, 10, 20]}),
    "range_expansion": (range_expansion, {"k": [1.0, 1.5, 2.0], "hold": [6, 12, 24]}),
    "linreg_tstat": (linreg_tstat, {"n": [50, 100, 200], "thr": [0.0, 2.0]}),
    "obv_trend": (obv_trend, {"n": [20, 50, 100, 200]}),
    "vwap_trend": (vwap_trend, {"n": [50, 100, 200, 400]}),
    "trend_lowvol": (trend_lowvol, {"pair": [(20, 100), (50, 200)], "q": [0.5, 0.7, 0.9]}),
    "psar": (psar, {"step": [0.01, 0.02], "amax": [0.1, 0.2]}),
    "stoch_pullback": (stoch_pullback, {"trend": [200, 400], "lo": [10, 20, 30]}),
    "btc_filter_ema": (btc_filter_ema, {"fast": [10, 20, 50], "slow": [100, 150, 200]}),
    "voltarget_ema": (voltarget_ema, {"pair": [(20, 100), (50, 200)], "tv": [0.5, 0.8]}),
    "dip_buy": (dip_buy, {"nd": [2, 3, 4], "hold": [3, 6, 12]}),
    "donchian_vote": (donchian_vote, {"base": [20, 40, 80]}),
}


# ---------------- portfoy (rotasyon) stratejisi ----------------
def xs_momentum(closes, ctx, lb, k):
    """Kesitsel momentum: lb mumluk getirisi en yuksek k varlik (getirisi > 0 olanlardan),
    her biri 1/k agirlik. Islem maliyeti icin her gun (ppd mumda bir) yeniden dengelenir."""
    mom = closes.pct_change(lb)
    rank = mom.rank(axis=1, ascending=False)
    w = ((rank <= k) & (mom > 0)).astype(float) / k
    step = ctx["ppd"]
    keep = np.arange(len(w)) % step == 0
    w = w.where(np.repeat(keep[:, None], w.shape[1], axis=1)).ffill().fillna(0.0)
    return w


PORTFOLIO = {
    "xs_momentum": (xs_momentum, {"lb": [42, 84, 180, 360], "k": [1, 2, 3]}),
}
