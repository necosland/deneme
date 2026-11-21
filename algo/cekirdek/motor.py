"""Core-system engine: point-in-time universe, signals, sizing, costs, funding, metrics.
Timing: bar index = OPEN time. Signal/weight at bar t uses data up to close(t) and earns bar t+1.
All indicators are computed per coin on that coin's own bars only (causal: ewm/rolling/shift)."""
import math
import pathlib
import sys
from statistics import NormalDist

import numpy as np
import pandas as pd

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from evren import PERP, SPOT, membership  # noqa: E402

CACHE = HERE / "cache"
IVD = {"1d": pd.Timedelta(days=1), "4h": pd.Timedelta(hours=4)}
BPD = {"1d": 1, "4h": 6}
WARMUP_DAYS = 60          # coin tradable after 60 days of its own Binance history
FEE, SLIP = 0.0005, 0.0005  # per side, perp taker + slippage (primary)
SPOT_COST = 0.0015          # per side, spot taker 0.10% + slippage 0.05% (sensitivity, no funding)
VOL_CAP = 0.50            # portfolio ex-ante vol cap (annualised) for cap=True
BAND = 0.25               # no-trade band: rebalance a coin only if |target-held| > 25% of |target|
DEV_START = pd.Timestamp("2019-01-07", tz="UTC")
DEV_END = pd.Timestamp("2024-01-01", tz="UTC")     # exclusive
N = NormalDist()


# ---------------------------------------------------------------- data
def _read(f):
    d = pd.read_csv(f, index_col=0)
    d.index = pd.to_datetime(d.index, utc=True, format="ISO8601")
    return d


def load(iv, end=None):
    """Panel dict close/high/low (time x coin) + funding (time x coin, rate summed into bars)."""
    raw = {}
    for coin, syms in SPOT.items():
        parts = [_read(CACHE / f"{s}_{iv}.csv") for s in syms if (CACHE / f"{s}_{iv}.csv").exists()]
        parts = [p for p in parts if len(p)]
        if not parts:
            continue
        d = parts[0]
        for p in parts[1:]:                       # ticker change: later symbol wins from its first bar
            d = pd.concat([d[d.index < p.index[0]], p])
        raw[coin] = d
    P = {f: pd.DataFrame({c: d[f] for c, d in raw.items()}).sort_index() for f in ["open", "high", "low", "close"]}
    # fill holes of <= 1 day inside a coin's life (exchange outages, BCHABC->BCH rename bar): flat bar at last close
    lim = 1 if iv == "1d" else 6
    c0 = P["close"]
    alive = c0.ffill().notna() & c0.bfill().notna()
    cf = c0.ffill(limit=lim).where(alive)
    hole = c0.isna() & cf.notna()
    for f in ("open", "high", "low"):
        P[f] = P[f].mask(hole, cf)
    P["close"] = cf
    if end is not None:
        P = {k: v.loc[:end - pd.Timedelta(seconds=1)] for k, v in P.items()}
    idx = P["close"].index
    fund = pd.DataFrame(0.0, index=idx, columns=P["close"].columns)
    live = pd.DataFrame(False, index=idx, columns=P["close"].columns)
    for coin in fund.columns:
        p = PERP.get(coin)
        f = CACHE / f"fund_{p}.csv" if p else None
        if not f or not f.exists():
            continue
        s = _read(f)["rate"]
        s.index = s.index.round("1min")          # Binance stamps carry ms jitter
        if not len(s):
            continue
        # event at time T is charged to the bar whose (open, close] contains T
        bar = (s.index - IVD[iv]).ceil(IVD[iv]) if iv == "4h" else (s.index - IVD[iv]).ceil("1D")
        agg = s.groupby(bar).sum()
        fund[coin] = agg.reindex(idx).fillna(0.0)
        live[coin] = (idx >= s.index[0] - IVD[iv]) & (idx <= s.index[-1])
    P["fund"], P["perp_live"] = fund, live
    return P


def eligibility(P, iv):
    c = P["close"]
    avail = c.notna()
    age_ok = avail.cumsum() > WARMUP_DAYS * BPD[iv]
    nxt = avail.shift(-1, fill_value=True)  # data ends next bar -> delisting known (announced) -> exit now
    mem = membership(c.index).reindex(columns=c.columns, fill_value=False)
    return avail & age_ok & nxt & mem


# ---------------------------------------------------------------- indicators (same as paper.py / lab_strategies)
def ema(s, n):
    return s.ewm(span=n, adjust=False).mean()


def sma(s, n):
    return s.rolling(n).mean()


def per_coin(P, fn):
    out = {}
    for c in P["close"].columns:
        m = P["close"][c].notna()
        out[c] = fn({k: P[k].loc[m, c] for k in ("high", "low", "close")}).reindex(P["close"].index)
    return pd.DataFrame(out).fillna(0.0)


def btc_series(P, fn):
    b = P["close"]["BTC"].dropna()
    return fn(b).reindex(P["close"].index).fillna(0.0)


# ---------------------------------------------------------------- signals: +1 long, -1 short, 0 flat
def sig_donchian(P, ls, entry=100, exit_=10):
    def f(d):
        c, hh_e, ll_x = d["close"].to_numpy(), d["high"].rolling(entry).max().shift(1).to_numpy(), \
            d["low"].rolling(exit_).min().shift(1).to_numpy()
        ll_e, hh_x = d["low"].rolling(entry).min().shift(1).to_numpy(), d["high"].rolling(exit_).max().shift(1).to_numpy()
        pos, p = np.zeros(len(c)), 0.0
        for i in range(len(c)):
            if p == 1.0 and c[i] < ll_x[i]:
                p = 0.0
            elif p == -1.0 and c[i] > hh_x[i]:
                p = 0.0
            if p == 0.0:
                if c[i] > hh_e[i]:
                    p = 1.0
                elif ls and c[i] < ll_e[i]:
                    p = -1.0
            pos[i] = p
        return pd.Series(pos, index=d["close"].index)
    return per_coin(P, f)


def sig_btc_filter_ema(P, ls, fast=10, slow=100):
    up = per_coin(P, lambda d: (ema(d["close"], fast) > ema(d["close"], slow)).astype(float))
    dn = per_coin(P, lambda d: (ema(d["close"], fast) < ema(d["close"], slow)).astype(float))
    bu = btc_series(P, lambda b: (ema(b, fast) > ema(b, slow)).astype(float))
    bd = btc_series(P, lambda b: (ema(b, fast) < ema(b, slow)).astype(float))
    s = up.mul(bu, axis=0)
    return s - dn.mul(bd, axis=0) if ls else s


def sig_ema_btcf(P, ls, fast=3, slow=17, f=200):
    up = per_coin(P, lambda d: (ema(d["close"], fast) > ema(d["close"], slow)).astype(float))
    dn = per_coin(P, lambda d: (ema(d["close"], fast) < ema(d["close"], slow)).astype(float))
    bu = btc_series(P, lambda b: (b > sma(b, f)).astype(float))
    bd = btc_series(P, lambda b: (b < sma(b, f)).astype(float))
    s = up.mul(bu, axis=0)
    return s - dn.mul(bd, axis=0) if ls else s


FAMILIES = {"donchian_4h": (sig_donchian, "4h"), "btc_filter_ema_4h": (sig_btc_filter_ema, "4h"),
            "ema_btcf_1d": (sig_ema_btcf, "1d")}


# ---------------------------------------------------------------- sizing
def coin_vol(P, iv):
    """trailing 30-day vol (annualised) of each coin, from that timeframe's own bars, known at close t."""
    r = P["close"].pct_change(fill_method=None)
    n = 30 * BPD[iv]
    return r.rolling(n, min_periods=n // 2).std() * math.sqrt(BPD[iv] * 365)


def daily_cov(Pd):
    """dict day -> annualised 60d covariance (pairwise, min 30 obs), from daily closes through that day."""
    r = Pd["close"].pct_change(fill_method=None)
    cv = r.rolling(60, min_periods=30).cov() * 365
    return cv


def weights(P, iv, sig, elig, sizing, cap, Pd=None):
    s = sig.where(elig, 0.0)
    s = s.where(~((s < 0) & ~P["perp_live"]), 0.0)        # short only where a perp exists
    n_el = elig.sum(axis=1).replace(0, np.nan)
    if sizing == "ew":
        w = s.div(n_el, axis=0)
    else:
        iv_ = 1 / coin_vol(P, iv).clip(lower=0.05)
        iv_ = iv_.where(elig)
        w = s * iv_.div(iv_.sum(axis=1), axis=0)
    w = w.fillna(0.0)
    if cap:
        cv = daily_cov(Pd)
        days = cv.index.get_level_values(0).unique()
        cols = list(Pd["close"].columns)
        W = w.reindex(columns=cols, fill_value=0.0)
        close_t = W.index + IVD[iv]
        day = (close_t.floor("1D") - pd.Timedelta(days=1))   # last daily bar fully closed by close(t)
        scale = np.ones(len(W))
        cache = {}
        Wv = W.to_numpy()
        for i, d in enumerate(day):
            if not Wv[i].any():
                continue
            if d not in cache:
                cache[d] = np.nan_to_num(cv.loc[d].reindex(index=cols, columns=cols).to_numpy()) if d in days else None
            S = cache[d]
            if S is None:
                continue
            v = math.sqrt(max(Wv[i] @ S @ Wv[i], 0.0))
            if v > VOL_CAP:
                scale[i] = VOL_CAP / v
        w = w.mul(scale, axis=0)
    return w


# ---------------------------------------------------------------- simulation with drift, band, costs, funding
def simulate(P, iv, w, elig, cost_side, use_funding):
    c = P["close"]
    r = c.pct_change(fill_method=None).fillna(0.0).to_numpy()
    F = P["fund"].to_numpy() if use_funding else np.zeros_like(r)
    live = P["perp_live"].to_numpy()
    W, E = w.to_numpy(), elig.to_numpy()
    T, K = W.shape
    h = np.zeros(K)
    net, gross_exp = np.zeros(T), np.zeros(T)
    for t in range(T):
        if t:  # bar t return on holdings set at close t-1
            R = float(h @ r[t])
            fund = float((h * live[t]) @ F[t])
            net[t] = R - fund
            denom = 1 + R
            h = h * (1 + r[t]) / denom if denom > 0 else np.zeros(K)
        tgt = W[t]
        trade = (np.sign(tgt) != np.sign(h)) | (np.abs(tgt - h) > BAND * np.abs(tgt))
        new = np.where(trade, tgt, h)
        # band must never create leverage, nor let the book sit >10% above the target gross (keeps the cap effective)
        if np.abs(new).sum() > 1.0 + 1e-9 or np.abs(new).sum() > 1.10 * np.abs(tgt).sum() + 1e-12:
            new = tgt
        net[t] -= np.abs(new - h).sum() * cost_side
        h = new
        gross_exp[t] = np.abs(h).sum()
    idx = c.index
    day = lambda x: (1 + pd.Series(x, index=idx)).resample("1D").prod() - 1
    return {"ret": day(net), "expo": pd.Series(gross_exp, index=idx).resample("1D").mean(),
            "inmkt": (pd.Series(gross_exp, index=idx) > 0).resample("1D").max()}


def entries_series(w):
    sg = np.sign(w)
    e = ((sg != sg.shift(1).fillna(0)) & (sg != 0)).sum(axis=1)
    return e.resample("1D").sum()


# ---------------------------------------------------------------- metrics
def sharpe(d):
    sd = d.std()
    return d.mean() / sd * math.sqrt(365) if sd > 0 and len(d) > 30 else float("nan")


def metrics(d, expo=None, inmkt=None, ent=None):
    d = d.dropna()
    eq = (1 + d).cumprod()
    yrs = len(d) / 365
    out = {"sharpe": sharpe(d), "cagr_%": (eq.iloc[-1] ** (1 / yrs) - 1) * 100,
           "maxDD_%": (eq / eq.cummax() - 1).min() * 100, "ret_%": (eq.iloc[-1] - 1) * 100}
    if expo is not None:
        out["avg_gross_%"] = expo.loc[d.index].mean() * 100
    if inmkt is not None:
        out["time_in_mkt_%"] = inmkt.loc[d.index].astype(float).mean() * 100
    if ent is not None:
        out["trades"] = int(ent.loc[d.index].sum())
    yr = (1 + d).groupby(d.index.year).prod() - 1
    out["years"] = {int(k): v * 100 for k, v in yr.items()}
    return out


def dsr(d, n_trials, var_sr):
    """Deflated Sharpe (Bailey & Lopez de Prado 2014). SR per period (daily), var_sr = variance of
    per-period SR across trials. Same formula as ../tournament.py."""
    d = d.dropna()
    T, sr = len(d), d.mean() / d.std()
    g3, g4 = d.skew(), d.kurt() + 3
    em = 0.5772156649
    sr0 = math.sqrt(var_sr) * ((1 - em) * N.inv_cdf(1 - 1 / n_trials) + em * N.inv_cdf(1 - 1 / (n_trials * math.e)))
    z = (sr - sr0) * math.sqrt(T - 1) / math.sqrt(max(1e-12, 1 - g3 * sr + (g4 - 1) / 4 * sr ** 2))
    return N.cdf(z), sr0 * math.sqrt(365)


# ---------------------------------------------------------------- candidates
def candidates():
    out = []
    for fam in FAMILIES:
        for ls in (False, True):
            for sizing in ("ew", "iv"):
                for cap in (False, True):
                    out.append({"name": f"{fam}|{'LS' if ls else 'LO'}|{sizing.upper()}|{'cap' if cap else 'nocap'}",
                                "fam": fam, "ls": ls, "sizing": sizing, "cap": cap})
    return out


def run_all(end=None, cost_mult=1.0, spot_mode=False, only=None, keep_w=False):
    """Returns {name: dict(ret, expo, inmkt, ent)} on data up to `end` (exclusive)."""
    panels = {iv: load(iv, end) for iv in ("1d", "4h")}
    Pd = panels["1d"]
    el = {iv: eligibility(panels[iv], iv) for iv in panels}
    res = {}
    for cnd in candidates():
        if only and cnd["name"] not in only:
            continue
        fn, iv = FAMILIES[cnd["fam"]]
        P = panels[iv]
        sig = fn(P, cnd["ls"])
        w = weights(P, iv, sig, el[iv], cnd["sizing"], cnd["cap"], Pd)
        if spot_mode:
            cost, fund = SPOT_COST * cost_mult, False
        else:
            cost, fund = (FEE + SLIP) * cost_mult, True
        s = simulate(P, iv, w, el[iv], cost, fund)
        res[cnd["name"]] = {"ret": s["ret"], "expo": s["expo"], "inmkt": s["inmkt"], "ent": entries_series(w)}
        if keep_w:
            res[cnd["name"]]["w"] = w
    btc = Pd["close"]["BTC"].pct_change(fill_method=None)
    return res, btc
