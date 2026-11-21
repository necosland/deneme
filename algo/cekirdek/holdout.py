"""One-shot holdout. Needs secim.json (frozen pick). Refuses to run twice. Run: python -I holdout.py"""
import json
import pathlib
import sys

import pandas as pd

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import motor as M  # noqa: E402
from dev import HOLDOUT_END, dev_slice, fingerprint, table  # noqa: E402

H_START = pd.Timestamp("2024-01-01", tz="UTC")


def main():
    sel = json.load(open(HERE / "secim.json"))
    out, mark = HERE / "holdout_tablo.csv", HERE / "holdout_started.txt"
    if out.exists() or mark.exists():
        sys.exit("holdout already run once")
    fp = fingerprint()
    bad = [k for k in fp if fp[k] != sel["fingerprint"][k]]
    if bad:
        sys.exit(f"code/data changed since freeze: {bad}")
    mark.write_text(str(pd.Timestamp.now(tz="UTC")))
    d1 = M.load("1d")
    end = d1["close"].index[-1] + pd.Timedelta(days=1)          # end of last closed daily candle
    assert end == HOLDOUT_END == pd.Timestamp(sel["holdout_end_exclusive"]), end
    res, btc = M.run_all(end=end)
    res2, _ = M.run_all(end=end, cost_mult=2.0)
    spot, _ = M.run_all(end=end, spot_mode=True, only=[c["name"] for c in M.candidates() if not c["ls"]])
    hs = lambda s: s.loc[H_START:end - pd.Timedelta(seconds=1)]
    H, bm = table(res, btc, hs, res2, spot)
    D, _ = table(res, btc, dev_slice)
    dev_frozen = pd.read_csv(HERE / "dev_tablo.csv").set_index("name")
    H["dev_sharpe_fullrun"] = D.set_index("name").loc[H.name, "sharpe"].to_numpy()
    H["dev_sharpe_frozen"] = dev_frozen.loc[H.name, "sharpe"].to_numpy()
    for N in (sel["n_trials_total"], sel["n_with_carry"], 24):
        H[f"DSR_N{N}"] = [M.dsr(hs(res[n]["ret"]), N, sel["var_sr_daily"])[0] for n in H.name]
    sr0 = M.dsr(hs(res[H.name[0]]["ret"]), sel["n_trials_total"], sel["var_sr_daily"])[1]
    H["H1"] = H.sharpe > bm["sharpe"]
    H["H2"] = H["maxDD_%"] > bm["maxDD_%"]
    H["H3"] = H[f"DSR_N{sel['n_trials_total']}"] >= 0.95
    H["H4"] = H.pos_years >= 2
    H["all_pass"] = H.H1 & H.H2 & H.H3 & H.H4
    gap = (H.dev_sharpe_fullrun - H.dev_sharpe_frozen).abs().max()
    assert gap < 1e-9, f"dev metrics differ between dev-only and full-data run: {gap}"
    H.to_csv(out, index=False)
    pd.set_option("display.width", 250, "display.max_columns", 40)
    cols = ["name", "sharpe", "sharpe_2x", "sharpe_spot", "cagr_%", "maxDD_%", "ret_%", "trades", "time_in_mkt_%",
            "avg_gross_%", "years", f"DSR_N{sel['n_trials_total']}", "DSR_N24", "H1", "H2", "H3", "H4",
            "dev_sharpe_fullrun", "dev_sharpe_frozen"]
    pick = sel["pick"]
    if pick:
        r = H.set_index("name").loc[pick]
        print("VERDICT (frozen pick only):", pick, "PASS" if r.all_pass else "FAIL -> none passed",
              r[["sharpe", "maxDD_%", f"DSR_N{sel['n_trials_total']}", "pos_years", "H1", "H2", "H3", "H4"]].to_dict())
    else:
        print("VERDICT: no pick frozen on dev -> none")
    print("holdout end", end, "BTC holdout:", bm, "SR0 annualised (N=247):", round(sr0, 3))
    print()
    print("REPORTING ONLY (not eligible for selection):")
    print(H[cols].round(3).to_string())


if __name__ == "__main__":
    main()
