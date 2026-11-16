"""Saglamlik matrisi: varlik x zaman araligi x maliyet carpani.
Her hucre walk-forward OUT-OF-SAMPLE sonucudur; yaninda ayni donemin al-tut'u.
Ayrica 'sabit parametre' (optimizasyonsuz, 4h'de 20/100'un zaman esdegeri) satiri:
walk-forward secimi sabit parametreyi yenemiyorsa optimizasyon gurultu demektir.
Kullanim: python robustness.py"""
import pathlib

import pandas as pd

from backtest import FEE, SLIP, metrics, per_year, run
from data import fetch_ohlcv
from research import grid, scale_space, walk_forward
from strategies import STRATEGIES

SYMBOLS = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT"]
INTERVALS = ["1h", "4h", "1d"]
COST_MULT = [1, 2]
FIXED = {"ema_cross": {"fast": 20, "slow": 100}, "donchian": {"entry": 60, "exit": 20}}
OUT = pathlib.Path(__file__).parent / "results"


def main():
    rows = []
    for sym in SYMBOLS:
        for itv in INTERVALS:
            df = fetch_ohlcv(sym, itv)
            py = per_year(itv)
            bh = df["close"].pct_change().fillna(0.0)
            for name, (fn, space) in STRATEGIES.items():
                fixed = scale_space({k: [v] for k, v in FIXED[name].items()}, itv)
                fixed = {k: v[0] for k, v in fixed.items()}
                for m in COST_MULT:
                    fee, slip = FEE * m, SLIP * m
                    names, res = grid(df, fn, scale_space(space, itv), fee, slip)
                    oos_r, oos_h, _ = walk_forward(df, names, res, itv)
                    fr, fh = run(df, fn(df, **fixed), fee=fee, slip=slip)
                    s = metrics(oos_r, oos_h, py)
                    f = metrics(fr.loc[oos_r.index], fh, py)
                    b = metrics(bh.loc[oos_r.index], periods=py)
                    rows.append({
                        "sembol": sym, "aralik": itv, "strateji": name, "maliyet": f"{m}x",
                        "oos_basl": oos_r.index[0].date(),
                        "wf_sharpe": s["sharpe"], "wf_yillik": s["yillik_%"], "wf_dd": s["maxDD_%"],
                        "wf_islem": s["islem"],
                        "sabit_sharpe": f["sharpe"], "sabit_dd": f["maxDD_%"],
                        "bh_sharpe": b["sharpe"], "bh_yillik": b["yillik_%"], "bh_dd": b["maxDD_%"],
                    })
                    print(rows[-1], flush=True)

    t = pd.DataFrame(rows)
    OUT.mkdir(exist_ok=True)
    t.to_csv(OUT / "robustness.csv", index=False)
    pd.set_option("display.width", 250)
    print("\n", t.to_string(index=False))

    print("\n-- Ozet: kac hucrede strateji al-tut'u Sharpe'ta yeniyor? --")
    t["wf_yener"] = t.wf_sharpe > t.bh_sharpe
    t["dd_iyi"] = t.wf_dd > t.bh_dd
    print(t.groupby(["strateji", "maliyet"])[["wf_yener", "dd_iyi"]].agg(["sum", "count"]))
    print("\nOrtalama Sharpe farki (wf - al-tut):")
    print((t.wf_sharpe - t.bh_sharpe).groupby([t.strateji, t.maliyet, t.aralik]).mean().unstack().round(2))


if __name__ == "__main__":
    main()
