# cekirdek_v1 — forward test, pre-registration

Written 2026-11-21, before the system has run a single live bar. Paper only, no real money.
Rules: `paper_spec.md`. Nothing below may be changed after the start; a change means a new test with a new name.

## Why this window matters
This is the **first clean out-of-sample window** for this system. The Phase 1 holdout (2024-01-01 → 2026-11-20)
was not virgin: earlier tournaments had already seen it when the family and parameters were chosen, which is
why the pick failed the Deflated Sharpe bar (0.59 vs 0.95). Every bar after the start below has been seen by no
study. The test can show the edge is still there, or not. It cannot overturn the DSR verdict: three to six months
are too short for that (a Sharpe estimate over 91 days has a standard error of about 2).

## Dates
- Start = the first workflow run that writes `systems.cekirdek_v1` into `algo/paper/state.json` on the default
  branch (`baslangic` field). Expected 2026-11-21/22, depending on when the code is deployed.
- Evaluation at start + 91 days (3 months). Check at start + 182 days (6 months).
- Universe refresh on the January 2027 snapshot (2027-01-03, `paper_spec.md`) is part of the plan, not a change.

## Measurement (from `algo/paper/ozsermaye.csv`, rows with `sistem = cekirdek_v1`)
- Equity: the `paper` column (net of fees and real slippage). `golge` is the shadow, `al_tut_btc` the benchmark
  (BTC bought at the start price, no cost).
- Daily return = change of the last row of each UTC day. Sharpe = mean / sd × √365. Max drawdown on all rows.
- In-market days = UTC days with a non-empty `acik` in any row.

## Success bar at 3 months (all must hold)
- S1 Sharpe of `paper` > Sharpe of `al_tut_btc` over the same rows.
- S2 max drawdown of `paper` shallower than that of `al_tut_btc`.
- S3 at least 20 in-market days. If S3 fails (the BTC filter kept the book in cash), the verdict is
  **inconclusive**, not pass; it is decided at 6 months on the full window with the same S1–S3.
- A flat book has Sharpe 0 by definition here (sd = 0 is read as 0).

Outcomes: pass → stays a paper candidate (any real-money step is a separate owner decision with its own plan);
fail → verdict "failed", the system keeps running for reporting only and cannot be upgraded later.

## Check at 6 months
Same S1–S3 over the whole 6-month window. A 3-month pass that fails here is withdrawn. An inconclusive 3-month
result is decided here; inconclusive again = failed.

## Kill rule (any time)
Drawdown of `paper` from its peak beyond **−46.4%** = 1.5 × the holdout spot worst (−31.0%, the dev spot worst
was −28.1%). `DURUM.md` flags it **OLDU**; the test ends as failed. If only the paper side crossed and the shadow
did not, the evaluation note says so: that is an execution problem, not the strategy.

## Paper vs shadow deviations
The shadow is the cekirdek backtest code run on the same bars. Any of these counts as a deviation and must be
explained in the evaluation note:
- V1 |paper / golge − 1| > 2% on any row.
- V2 after a run, a coin held by paper but not by the shadow (or the reverse). Expected only after missed runs.
- V3 a missed run: more than 8 h between consecutive cekirdek_v1 rows.
- V4 mean `kayma_%` per side over all cekirdek_v1 trades > 0.10% (the shadow assumes 0.05%).
- V5 the shadow differs from a fresh `motor.simulate` run over the forward window (live universe substituted
  for `evren.SNAP`, data topped up in a copy of the cache, not the frozen one) by more than 1e-6 relative.
Deviations do not change the verdict, which uses `paper`. If V1 or V5 is unexplained, the result is reported as
"unreliable" next to the verdict.

## What is reported at each check
Paper, shadow and BTC: return, Sharpe, max drawdown; in-market days; number of trades; V1–V5 counts;
S1–S3 and the verdict.
