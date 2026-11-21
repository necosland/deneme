"""Development run (data cut at 2023-12-31) + freeze the pick. Run: python -I dev.py"""
import hashlib
import json
import math
import pathlib
import sys

import numpy as np
import pandas as pd

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import motor as M  # noqa: E402

N_TOTAL, N_WITH_CARRY = 247, 931
HOLDOUT_END = pd.Timestamp("2026-11-21", tz="UTC")   # exclusive: last closed daily candle is 2026-11-20
HASHED = ["evren.py", "motor.py", "dev.py", "holdout.py", "plan.md"]


def fingerprint():
    h = {f: hashlib.sha256((HERE / f).read_bytes()).hexdigest() for f in HASHED}
    m = hashlib.sha256()
    for f in sorted((HERE / "cache").glob("*.csv")):
        m.update(f.name.encode())
        m.update(f.read_bytes())
    h["cache"] = m.hexdigest()
    return h


def dev_slice(s):
    return s.loc[M.DEV_START:M.DEV_END - pd.Timedelta(seconds=1)]


def table(res, btc, sl, res2=None, spot=None):
    rows = []
    bm = M.metrics(sl(btc))
    for name, r in res.items():
        m = M.metrics(sl(r["ret"]), r["expo"], r["inmkt"], r["ent"])
        row = {"name": name, **{k: v for k, v in m.items() if k != "years"},
               "pos_years": sum(v > 0 for v in m["years"].values()), "n_years": len(m["years"]),
               "years": m["years"], "btc_sharpe": bm["sharpe"], "btc_maxDD_%": bm["maxDD_%"]}
        if res2 is not None:
            row["sharpe_2x"] = M.sharpe(sl(res2[name]["ret"]))
        if spot is not None and name in spot:
            row["sharpe_spot"] = M.sharpe(sl(spot[name]["ret"]))
        rows.append(row)
    return pd.DataFrame(rows), bm


def truncation_test():
    """Weights computed on data cut at `cut` must equal the full-dev weights on every bar up to the cut
    (incl. the last one). Any one-bar lookahead shows up here."""
    worst = 0.0
    for cut in (pd.Timestamp("2020-03-15", tz="UTC"), pd.Timestamp("2022-05-10", tz="UTC"),
                pd.Timestamp("2023-07-01", tz="UTC")):
        a, _ = M.run_all(end=cut, keep_w=True)
        b, _ = M.run_all(end=M.DEV_END, keep_w=True)
        for k in a:
            x = a[k]["w"]
            y = b[k]["w"].reindex(index=x.index, columns=x.columns)
            worst = max(worst, float((x - y).abs().max().max()))
    return worst


def min_sharpe_for_dsr(var_sr, n, T, target=0.95):
    """Annualised holdout Sharpe needed for DSR >= target (normal returns approximation)."""
    sr0 = M.dsr(pd.Series([0.01, -0.01] * 10), n, var_sr)[1] / math.sqrt(365)
    return (sr0 + M.N.inv_cdf(target) / math.sqrt(T - 1)) * math.sqrt(365)


def main():
    out = HERE / "secim.json"
    if out.exists():
        sys.exit("secim.json exists: pick already frozen")
    leak = truncation_test()
    if leak > 1e-12:
        sys.exit(f"truncation test failed: max |dw| = {leak}")
    res, btc = M.run_all(end=M.DEV_END)
    res2, _ = M.run_all(end=M.DEV_END, cost_mult=2.0)
    spot, _ = M.run_all(end=M.DEV_END, spot_mode=True, only=[c["name"] for c in M.candidates() if not c["ls"]])
    T, bm = table(res, btc, dev_slice, res2, spot)
    T["D1"] = T.sharpe > bm["sharpe"]
    T["D2"] = T["maxDD_%"] > bm["maxDD_%"]
    T["D3"] = T.sharpe_2x > bm["sharpe"]
    T["D4"] = T.pos_years >= 3
    T["eligible"] = T.D1 & T.D2 & T.D3 & T.D4
    sr_daily = [dev_slice(res[n]["ret"]).mean() / dev_slice(res[n]["ret"]).std() for n in T.name]
    var_sr = float(np.var(sr_daily, ddof=1))
    T["DSR_dev_N24"] = [M.dsr(dev_slice(res[n]["ret"]), 24, var_sr)[0] for n in T.name]
    T["DSR_dev_N247"] = [M.dsr(dev_slice(res[n]["ret"]), N_TOTAL, var_sr)[0] for n in T.name]
    T = T.sort_values("sharpe", ascending=False).reset_index(drop=True)

    pick = None
    el = T[T.eligible].copy()
    if len(el):
        top = el.sharpe.max()
        near = el[el.sharpe >= top - 0.05].copy()
        near["k"] = [(("|LS|" in n), ("|IV|" in n), n.endswith("|cap"), t) for n, t in zip(near.name, near.trades)]
        pick = sorted(zip(near.k, near.name))[0][1]

    T.to_csv(HERE / "dev_tablo.csv", index=False)
    t_hold = (HOLDOUT_END - pd.Timestamp("2024-01-01", tz="UTC")).days
    json.dump({"pick": pick, "var_sr_daily": var_sr, "n_trials_total": N_TOTAL, "n_with_carry": N_WITH_CARRY,
               "holdout_end_exclusive": str(HOLDOUT_END),
               "implied_min_holdout_sharpe_for_DSR95": min_sharpe_for_dsr(var_sr, N_TOTAL, t_hold),
               "fingerprint": fingerprint(),
               "btc_dev": {k: v for k, v in bm.items()}, "truncation_max_abs_diff": leak,
               "frozen_at_utc": str(pd.Timestamp.now(tz="UTC"))}, open(out, "w"), indent=1, default=str)
    pd.set_option("display.width", 250, "display.max_columns", 30)
    cols = ["name", "sharpe", "sharpe_2x", "sharpe_spot", "cagr_%", "maxDD_%", "trades", "time_in_mkt_%",
            "avg_gross_%", "pos_years", "DSR_dev_N24", "DSR_dev_N247", "eligible"]
    print(T[cols].round(3).to_string())
    print("BTC dev:", bm)
    print("var_sr_daily", var_sr, "truncation max |dw|", leak,
          "implied min holdout Sharpe (DSR .95, N=247):", round(min_sharpe_for_dsr(var_sr, N_TOTAL, t_hold), 2))
    print("PICK:", pick)


if __name__ == "__main__":
    main()
