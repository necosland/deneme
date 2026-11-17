"""Sistem kutuphanesi (turnuva icin). Hepsi long-only spot.

Her sistem: fn(P, bpd, **params) -> DataFrame (zaman x sembol).
  kind="single": her coin icin 0..1 pozisyon; motor bunu esit agirlikla portfoye boler.
  kind="port"  : dogrudan portfoy agirligi (satir toplami <= 1).
P: load_panel() ciktisi (open/high/low/close/volume DataFrame'leri). bpd: gunluk mum sayisi.
Parametre gridleri GUN cinsinden (scaled) -> mum sayisina cevrilir; esikler cevrilmez.
Sinyal t kapanisinda bilinen veriyle uretilir; motor t+1 getirisini verir (lookahead yok)."""
import numpy as np
import pandas as pd


# ---------------------------------------------------------------- indikatorler
def ema(x, n):
    return x.ewm(span=n, adjust=False, min_periods=n).mean()


def sma(x, n):
    return x.rolling(n).mean()


def wilder(x, n):
    return x.ewm(alpha=1 / n, adjust=False, min_periods=n).mean()


def true_range(P):
    h, l, c1 = P["high"], P["low"], P["close"].shift(1)
    return np.maximum(np.maximum(h - l, (h - c1).abs()), (l - c1).abs())


def atr(P, n):
    return wilder(true_range(P), n)


def rsi(c, n):
    d = c.diff()
    up, dn = wilder(d.clip(lower=0), n), wilder((-d).clip(lower=0), n)
    return 100 - 100 / (1 + up / dn)


def latch(enter, exit_):
    """Giris/cikis sinyallerinden durum (cikis oncelikli). enter/exit bool DataFrame."""
    s = pd.DataFrame(np.nan, index=enter.index, columns=enter.columns)
    return s.mask(enter, 1.0).mask(exit_, 0.0).ffill().fillna(0.0)


def b(x):  # NaN -> False
    return x.fillna(False).astype(bool) if x.dtypes.iloc[0] == object else x


def realized_vol(c, n, bpd):
    return c.pct_change(fill_method=None).rolling(n).std() * np.sqrt(bpd * 365)


def hma(x, n):
    w = lambda s, k: s.rolling(k).apply(lambda a: np.dot(a, np.arange(1, k + 1)) / (k * (k + 1) / 2), raw=True)
    h = max(2, n // 2)
    return w(2 * w(x, h) - w(x, n), max(2, int(np.sqrt(n))))


# ---------------------------------------------------------------- trend
def ema_cross(P, bpd, fast, slow):
    c = P["close"]
    return (ema(c, fast) > ema(c, slow)).astype(float)


def sma_cross(P, bpd, fast, slow):
    c = P["close"]
    return (sma(c, fast) > sma(c, slow)).astype(float)


def price_sma(P, bpd, n):
    c = P["close"]
    return (c > sma(c, n)).astype(float)


def tsmom(P, bpd, n):
    c = P["close"]
    return (c > c.shift(n)).astype(float)


def donchian(P, bpd, entry, exit):
    c = P["close"]
    return latch(c > P["high"].rolling(entry).max().shift(1), c < P["low"].rolling(exit).min().shift(1))


def macd(P, bpd, fast, slow, sig):
    c = P["close"]
    m = ema(c, fast) - ema(c, slow)
    return (m > ema(m, sig)).astype(float)


def supertrend(P, bpd, n, mult):
    c, hl2, a = P["close"].to_numpy(), ((P["high"] + P["low"]) / 2).to_numpy(), atr(P, n).to_numpy()
    up, lo = hl2 + mult * a, hl2 - mult * a
    out = np.zeros_like(c)
    for j in range(c.shape[1]):
        fu, fl, trend = np.nan, np.nan, 0
        for i in range(c.shape[0]):
            if np.isnan(a[i, j]) or np.isnan(c[i, j]):
                fu, fl, trend = np.nan, np.nan, 0
                continue
            pc = c[i - 1, j] if i else np.nan
            fu = up[i, j] if (np.isnan(fu) or up[i, j] < fu or pc > fu) else fu
            fl = lo[i, j] if (np.isnan(fl) or lo[i, j] > fl or pc < fl) else fl
            if c[i, j] > fu:
                trend = 1
            elif c[i, j] < fl:
                trend = 0
            out[i, j] = trend
    return pd.DataFrame(out, index=P["close"].index, columns=P["close"].columns)


def keltner(P, bpd, n, k):
    c, m = P["close"], ema(P["close"], n)
    return latch(c > m + k * atr(P, n), c < m)


def bb_breakout(P, bpd, n, k):
    c, m, sd = P["close"], sma(P["close"], n), P["close"].rolling(n).std()
    return latch(c > m + k * sd, c < m)


def adx_trend(P, bpd, n, thr):
    h, l = P["high"], P["low"]
    upm, dnm = h.diff(), -l.diff()
    pdm = upm.where((upm > dnm) & (upm > 0), 0.0)
    ndm = dnm.where((dnm > upm) & (dnm > 0), 0.0)
    tr = wilder(true_range(P), n)
    pdi, ndi = 100 * wilder(pdm, n) / tr, 100 * wilder(ndm, n) / tr
    dx = 100 * (pdi - ndi).abs() / (pdi + ndi)
    return ((wilder(dx, n) > thr) & (pdi > ndi)).astype(float)


def ichimoku(P, bpd, tenkan, kijun, senkou):
    h, l, c = P["high"], P["low"], P["close"]
    mid = lambda n: (h.rolling(n).max() + l.rolling(n).min()) / 2
    t, k = mid(tenkan), mid(kijun)
    sa, sb = ((t + k) / 2).shift(kijun), mid(senkou).shift(kijun)
    return ((c > np.maximum(sa, sb)) & (t > k)).astype(float)


def hma_slope(P, bpd, n):
    hm = hma(P["close"], n)
    return (hm > hm.shift(1)).astype(float)


def triple_ema(P, bpd, a, b_, c_):
    c = P["close"]
    e1, e2, e3 = ema(c, a), ema(c, b_), ema(c, c_)
    return ((e1 > e2) & (e2 > e3)).astype(float)


def vol_tsmom(P, bpd, n, target):
    c = P["close"]
    vol = realized_vol(c, 30 * bpd, bpd)
    return ((c > c.shift(n)) * (target / vol).clip(upper=1.0)).fillna(0.0)


def obv_trend(P, bpd, n):
    c, v = P["close"], P["volume"]
    obv = (np.sign(c.diff()).fillna(0) * v).cumsum()
    return ((obv > ema(obv, n)) & (c > ema(c, n))).astype(float)


def linreg_t(P, bpd, n, thr):
    y = np.log(P["close"])
    t = pd.Series(np.arange(len(y)) / len(y), index=y.index)
    mty = y.mul(t, axis=0).rolling(n).mean()
    my, mt = y.rolling(n).mean(), t.rolling(n).mean()
    cov = mty.sub(my.mul(mt, axis=0))
    var_t = t.rolling(n).var(ddof=0)
    r = (cov.div(np.sqrt(var_t), axis=0) / np.sqrt(y.rolling(n).var(ddof=0))).clip(-0.999999, 0.999999)
    tstat = r * np.sqrt((n - 2) / (1 - r ** 2))
    return (tstat > thr).astype(float)


def rsi_trend(P, bpd, n, band):
    r = rsi(P["close"], n)
    return latch(r > 50 + band, r < 50 - band)


def trend_lowvol(P, bpd, n, q):
    c = P["close"]
    vol = realized_vol(c, 30 * bpd, bpd)
    cap = vol.rolling(365 * bpd, min_periods=180 * bpd).quantile(q)
    return ((c > sma(c, n)) & (vol < cap)).astype(float)


def chandelier(P, bpd, entry, mult):
    c = P["close"]
    hh = P["high"].rolling(entry).max()
    return latch(c > hh.shift(1), c < hh - mult * atr(P, 14 * bpd))


def turtle_dual(P, bpd, m):
    d = lambda e, x: donchian(P, bpd, max(2, int(e * m * bpd)), max(2, int(x * m * bpd)))
    return 0.5 * d(20, 10) + 0.5 * d(55, 20)


# ---------------------------------------------------------------- mean reversion
def rsi2_mr(P, bpd, thr, trend_n):
    c = P["close"]
    enter = rsi(c, 2) < thr
    if trend_n:
        enter &= c > sma(c, trend_n)
    return latch(enter, c > sma(c, 5))


def bb_reversion(P, bpd, n, k):
    c, m, sd = P["close"], sma(P["close"], n), P["close"].rolling(n).std()
    return latch(c < m - k * sd, c > m)


def dip_buy(P, bpd, n_down, hold):
    c = P["close"]
    down = (c.diff() < 0).astype(float).rolling(n_down).sum() == n_down
    return down.astype(float).rolling(hold, min_periods=1).max()


def ibs(P, bpd, thr, trend_n):
    c, h, l = P["close"], P["high"], P["low"]
    enter = (c - l) / (h - l) < thr
    if trend_n:
        enter &= c > sma(c, trend_n)
    return enter.astype(float)


# ---------------------------------------------------------------- portfoy / rotasyon / rejim
def _rotation(P, bpd, n, k, gate=None):
    c = P["close"]
    mom = c / c.shift(n) - 1
    rank = mom.rank(axis=1, ascending=False)
    w = ((rank <= k) & (mom > 0)).astype(float) / k
    if gate is not None:
        w = w.mul(gate, axis=0)
    reb = np.arange(len(w)) % (7 * bpd) == 0  # haftalik rebalans
    return w.where(pd.Series(reb, index=w.index), np.nan).ffill().fillna(0.0)


def xs_rotation(P, bpd, n, k):
    return _rotation(P, bpd, n, k)


def btc_gate(P, f):
    btc = P["close"]["BTC"]
    return (btc > sma(btc, f)).astype(float)


def xs_rotation_btcf(P, bpd, n, k, f):
    return _rotation(P, bpd, n, k, btc_gate(P, f))


def ema_btcf(P, bpd, fast, slow, f):
    return ema_cross(P, bpd, fast, slow).mul(btc_gate(P, f), axis=0)


def btc_ema(P, bpd, fast, slow):
    w = pd.DataFrame(0.0, index=P["close"].index, columns=P["close"].columns)
    w["BTC"] = ema_cross(P, bpd, fast, slow)["BTC"]
    return w


# ---------------------------------------------------------------- kayit
# isim: (fn, kind, grid, scaled_params). scaled = gun -> mum cevrilecek parametreler.
D = "days"
SYSTEMS = {
    "ema_cross":     (ema_cross, "single", {"fast": [2, 3, 5, 8], "slow": [10, 17, 25, 33, 50]}, {"fast", "slow"}),
    "sma_cross":     (sma_cross, "single", {"fast": [3, 5, 10, 20], "slow": [20, 50, 100, 200]}, {"fast", "slow"}),
    "price_sma":     (price_sma, "single", {"n": [10, 20, 50, 100, 150, 200]}, {"n"}),
    "tsmom":         (tsmom, "single", {"n": [7, 14, 30, 60, 90, 120, 180]}, {"n"}),
    "donchian":      (donchian, "single", {"entry": [5, 10, 20, 40, 55], "exit": [3, 5, 10, 20]}, {"entry", "exit"}),
    "macd":          (macd, "single", {"fast": [3, 6, 12], "slow": [13, 26, 52], "sig": [3, 9]}, {"fast", "slow", "sig"}),
    "supertrend":    (supertrend, "single", {"n": [3, 7, 10, 20], "mult": [2, 3, 4]}, {"n"}),
    "keltner":       (keltner, "single", {"n": [10, 20, 50], "k": [1, 1.5, 2, 2.5]}, {"n"}),
    "bb_breakout":   (bb_breakout, "single", {"n": [10, 20, 50], "k": [1, 1.5, 2, 2.5]}, {"n"}),
    "adx_trend":     (adx_trend, "single", {"n": [7, 14, 28], "thr": [15, 20, 25, 30]}, {"n"}),
    "ichimoku":      (ichimoku, "single", {"tenkan": [2, 5, 9, 18], "kijun": [6, 13, 26, 52], "senkou": [52]}, {"tenkan", "kijun", "senkou"}),
    "hma_slope":     (hma_slope, "single", {"n": [5, 10, 20, 40]}, {"n"}),
    "triple_ema":    (triple_ema, "single", {"a": [2, 5, 10], "b_": [8, 20, 30], "c_": [25, 50, 100]}, {"a", "b_", "c_"}),
    "vol_tsmom":     (vol_tsmom, "single", {"n": [30, 60, 90, 120], "target": [0.3, 0.5, 0.8]}, {"n"}),
    "obv_trend":     (obv_trend, "single", {"n": [5, 10, 20, 50, 100]}, {"n"}),
    "linreg_t":      (linreg_t, "single", {"n": [14, 30, 60, 90], "thr": [0, 1, 2, 3]}, {"n"}),
    "rsi_trend":     (rsi_trend, "single", {"n": [7, 14, 28], "band": [2, 5, 10]}, {"n"}),
    "trend_lowvol":  (trend_lowvol, "single", {"n": [20, 50, 100], "q": [0.5, 0.7, 0.9]}, {"n"}),
    "chandelier":    (chandelier, "single", {"entry": [10, 20, 40, 55], "mult": [2, 3, 4]}, {"entry"}),
    "turtle_dual":   (turtle_dual, "single", {"m": [0.25, 0.5, 1, 2]}, set()),
    "rsi2_mr":       (rsi2_mr, "single", {"thr": [5, 10, 20, 30], "trend_n": [0, 50, 100, 200]}, {"trend_n"}),
    "bb_reversion":  (bb_reversion, "single", {"n": [5, 10, 20], "k": [1.5, 2, 2.5]}, {"n"}),
    "dip_buy":       (dip_buy, "single", {"n_down": [3, 4, 5], "hold": [3, 6, 12]}, set()),
    "ibs":           (ibs, "single", {"thr": [0.1, 0.2, 0.3], "trend_n": [0, 100]}, {"trend_n"}),
    "xs_rotation":   (xs_rotation, "port", {"n": [7, 14, 30, 60, 90], "k": [1, 3, 5]}, {"n"}),
    "xs_rot_btcf":   (xs_rotation_btcf, "port", {"n": [14, 30, 60, 90], "k": [1, 3, 5], "f": [50, 200]}, {"n", "f"}),
    "ema_btcf":      (ema_btcf, "single", {"fast": [3, 5], "slow": [17, 33], "f": [50, 100, 200]}, {"fast", "slow", "f"}),
    "btc_ema":       (btc_ema, "port", {"fast": [2, 3, 5, 8], "slow": [10, 17, 25, 33, 50]}, {"fast", "slow"}),
}


def valid(p):
    pairs = [("fast", "slow"), ("exit", "entry"), ("tenkan", "kijun"), ("kijun", "senkou"), ("a", "b_"), ("b_", "c_")]
    return all(p[x] < p[y] for x, y in pairs if x in p and y in p)
