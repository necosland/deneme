"""Data for the core-system study. Public Binance data only, no keys.
Spot klines: reuse ../cache/{SYM}_{iv}.csv where present, top up missing head (from 2018-09-01) and tail
(to the latest CLOSED bar) from data-api.binance.vision. Funding: fapi.binance.com fundingRate (REST).
Everything downloaded is written to cekirdek/cache/ (gitignored). Run: python -I veri.py
Cleaning rules (fixed): drop non-positive prices; truncate a symbol at its first gap > 7 days
(handles LUNA -> LUNA 2.0 re-use of the ticker); drop the last bar if it is not closed."""
import concurrent.futures as cf
import pathlib
import sys
import time

import pandas as pd
import requests

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from evren import PERP, SPOT  # noqa: E402

OLD = HERE.parent / "cache"
CACHE = HERE / "cache"
KL = "https://data-api.binance.vision/api/v3/klines"
FR = "https://fapi.binance.com/fapi/v1/fundingRate"
START = pd.Timestamp("2018-09-01", tz="UTC")
START_BTC = pd.Timestamp("2017-08-01", tz="UTC")   # BTC needs 200d history for the SMA200 gate by 2019-01
IVD = {"1d": pd.Timedelta(days=1), "4h": pd.Timedelta(hours=4)}


def get(url, params):
    for k in range(5):
        try:
            r = requests.get(url, params=params, timeout=30)
            if r.status_code == 400:
                return []
            r.raise_for_status()
            return r.json()
        except requests.RequestException:
            if k == 4:
                raise
            time.sleep(2 * (k + 1))


def rest_klines(sym, iv, t0, t1):
    rows, cur, end = [], int(t0.timestamp() * 1000), int(t1.timestamp() * 1000)
    while cur < end:
        d = get(KL, dict(symbol=sym, interval=iv, startTime=cur, endTime=end, limit=1000))
        if not d:
            break
        rows += d
        cur = d[-1][0] + 1
        if len(d) < 1000:
            break
    if not rows:
        return pd.DataFrame(columns=["open", "high", "low", "close", "volume"])
    df = pd.DataFrame([r[:6] for r in rows], columns=["t", "open", "high", "low", "close", "volume"])
    df.index = pd.to_datetime(df.pop("t"), unit="ms", utc=True)
    return df.astype(float)


def clean(df, iv, now):
    df = df[~df.index.duplicated(keep="last")].sort_index()
    df = df[(df[["open", "high", "low", "close"]] > 0).all(axis=1)]
    df = df[df.index + IVD[iv] <= now]
    gaps = df.index.to_series().diff() > pd.Timedelta(days=7)
    if gaps.any():
        df = df.loc[:gaps.idxmax() - pd.Timedelta(seconds=1)]
    return df


def spot(sym, iv, now):
    start = START_BTC if sym == "BTCUSDT" else START
    old = OLD / f"{sym}_{iv}.csv"
    parts = []
    if old.exists():
        o = pd.read_csv(old, index_col=0, parse_dates=True)
        o.index = pd.to_datetime(o.index, utc=True)
        parts = [rest_klines(sym, iv, start, o.index[0] - pd.Timedelta(seconds=1)), o,
                 rest_klines(sym, iv, o.index[-1] + pd.Timedelta(seconds=1), now)]
    else:
        parts = [rest_klines(sym, iv, start, now)]
    df = clean(pd.concat([p for p in parts if len(p)]) if any(len(p) for p in parts) else parts[0], iv, now)
    df.to_csv(CACHE / f"{sym}_{iv}.csv")
    return sym, iv, len(df), (df.index[0], df.index[-1]) if len(df) else None


def funding(perp, now):
    rows, cur = [], int(pd.Timestamp("2019-09-01", tz="UTC").timestamp() * 1000)
    while cur < now.timestamp() * 1000:
        d = get(FR, dict(symbol=perp, startTime=cur, limit=1000))
        if not d:
            break
        rows += d
        cur = d[-1]["fundingTime"] + 1
        if len(d) < 1000:
            break
        time.sleep(0.2)
    s = pd.Series({pd.Timestamp(r["fundingTime"], unit="ms", tz="UTC"): float(r["fundingRate"]) for r in rows},
                  name="rate").sort_index()
    if len(s):
        g = s.index.to_series().diff() > pd.Timedelta(days=7)   # ticker re-use (LUNA) -> keep first life
        if g.any():
            s = s.loc[:g.idxmax() - pd.Timedelta(seconds=1)]
    s.to_frame().to_csv(CACHE / f"fund_{perp}.csv")
    return perp, len(s), (s.index[0], s.index[-1]) if len(s) else None


def main():
    CACHE.mkdir(exist_ok=True)
    now = pd.Timestamp.now(tz="UTC")
    syms = sys.argv[1:] or sorted({s for v in SPOT.values() for s in v})
    with cf.ThreadPoolExecutor(6) as ex:
        for r in ex.map(lambda a: spot(*a, now), [(s, iv) for s in syms for iv in IVD]):
            print(*r, flush=True)
        if not sys.argv[1:]:
            for r in ex.map(lambda p: funding(p, now), sorted({p for p in PERP.values() if p})):
                print(*r, flush=True)
    (CACHE / "_fetched_at.txt").write_text(str(now))


if __name__ == "__main__":
    main()
