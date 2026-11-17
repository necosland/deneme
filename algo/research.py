"""Arastirma: tum-donem sonucu, parametre komsulugu, walk-forward (out-of-sample).
Kullanim: python research.py [SEMBOL] [ARALIK]"""
import itertools
import sys

import numpy as np
import pandas as pd

from backtest import BARS_PER_DAY, FEE, SLIP, metrics, per_year, run
from data import fetch_ohlcv
from strategies import STRATEGIES

TRAIN_DAYS, TEST_DAYS = 730, 180


def sharpe(r, periods):
    sd = r.std()
    return r.mean() / sd * np.sqrt(periods) if sd > 0 else -9


def scale_space(space, interval):
    """Grid 4h mum cinsinden tanimli; diger araliklarda ayni ZAMAN ufkunu kapsasin diye olcekle."""
    k = BARS_PER_DAY[interval] / 6
    return {n: sorted({max(2, int(round(v * k))) for v in vals}) for n, vals in space.items()}


def grid(df, fn, space, fee=FEE, slip=SLIP):
    names = list(space)
    res = {}
    for combo in itertools.product(*space.values()):
        p = dict(zip(names, combo))
        if p.get("fast", 0) >= p.get("slow", 1e9):
            continue
        r, h = run(df, fn(df, **p), fee=fee, slip=slip)
        res[combo] = (r, h)
    return names, res


def walk_forward(df, names, res, interval="4h"):
    bpd, py = BARS_PER_DAY[interval], per_year(interval)
    tr, te = TRAIN_DAYS * bpd, TEST_DAYS * bpd
    oos_r, oos_h, picks = [], [], []
    i = tr
    while i + te <= len(df):
        tr_idx, te_idx = df.index[i - tr:i], df.index[i:i + te]
        best = max(res, key=lambda k: sharpe(res[k][0].loc[tr_idx], py))
        oos_r.append(res[best][0].loc[te_idx])
        oos_h.append(res[best][1].loc[te_idx])
        picks.append((te_idx[0].date(), dict(zip(names, best))))
        i += te
    return pd.concat(oos_r), pd.concat(oos_h), picks


def main():
    symbol = sys.argv[1] if len(sys.argv) > 1 else "BTCUSDT"
    interval = sys.argv[2] if len(sys.argv) > 2 else "4h"
    py = per_year(interval)
    df = fetch_ohlcv(symbol, interval)
    print(f"{symbol} {interval}: {len(df)} mum, {df.index[0].date()} -> {df.index[-1].date()}")
    bh = df["close"].pct_change().fillna(0.0)

    for name, (fn, space) in STRATEGIES.items():
        print(f"\n===== {name} =====")
        names, res = grid(df, fn, scale_space(space, interval))

        print("-- Parametre komsulugu (tum donem Sharpe; komsular da iyi degilse tesadufe supheli bak) --")
        tab = pd.Series({k: round(sharpe(v[0], py), 2) for k, v in res.items()})
        tab.index = pd.MultiIndex.from_tuples(tab.index, names=names)
        print(tab.unstack().to_string())

        oos_r, oos_h, picks = walk_forward(df, names, res, interval)
        print("\n-- Walk-forward OUT-OF-SAMPLE (egitim 2 yil, test 6 ay, kayan) --")
        print("strateji:", metrics(oos_r, oos_h, py))
        print("al-tut  :", metrics(bh.loc[oos_r.index], periods=py))
        print("secilen parametreler:")
        for d, p in picks:
            print("  ", d, p)


if __name__ == "__main__":
    main()
