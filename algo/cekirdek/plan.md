# Core trend system — pre-registration (Phase 1)

Written 2026-11-21 before any number of this study was computed. Paper only, no real money.
Goal: pick ONE systematic trend-following system for the paper bot, or say none qualifies.

## Data
- Binance public spot klines (1d, 4h) + USDT-M perp funding (REST). Reuse `algo/cache`, top up into
  `algo/cekirdek/cache` (gitignored). Clean: drop non-positive prices; cut a symbol at its first gap > 7 days
  (LUNA ticker re-used for LUNA 2.0); only closed bars. Python run with `-I`.
- BTC fetched from 2017-08 (SMA200 ready by 2019-01); other coins from 2018-09.

## Universe (point-in-time, survivorship-free)
- CoinMarketCap historical snapshot, first Sunday of each January 2019–2026 (`evren.py`): top-20 by market cap,
  stablecoins and wrapped tokens removed. Active from snapshot date + 1 day to next snapshot + 1 day.
- Tradable only while the coin has Binance USDT spot data. Exchange tokens with no Binance market
  (LEO, HT, CRO, CEL, CC, "999") are dropped; BSV trades until its 2019-04 delisting; LUNA, MATIC, XMR, WAVES,
  EOS, MKR etc. stay in until their data ends.
- Coin needs 60 days of own Binance history before it can be traded.
- Delisting / data end: position closed at the last available close (delistings are announced in advance).
  Coin leaving the universe at a snapshot: closed at that bar's close.

## Periods
- Development: 2019-01-07 → 2023-12-31. All choices made here.
- Holdout: 2024-01-01 → last closed daily candle (2026-11-20). Run ONCE, after the pick is frozen in `secim.json`.
- Caveat stated up front: prior tournaments (local rounds 1–4, cloud round) used data through 2024 and 2025-11,
  and the three families were chosen from them. The holdout is therefore not virgin for the *family*; it is
  virgin for this study's structural choices. The DSR below charges for all prior trials to compensate.

## Candidates (fixed grid, 24 trials)
Families, parameters frozen at the paper-bot values (no parameter search here):
- `donchian_4h`: long on close > prior 100-bar high, exit on close < prior 10-bar low (4h bars).
  LS mirror: short on close < prior 100-bar low, cover on close > prior 10-bar high.
- `btc_filter_ema_4h`: long if EMA10 > EMA100 (4h) on the coin AND on BTC. LS: short if both below.
- `ema_btcf_1d`: long if EMA3 > EMA17 (daily) AND BTC close > BTC SMA200 (daily). LS: short if EMA3 < EMA17 AND BTC < SMA200.
Structural grid per family (2 × 2 × 2 = 8):
- Direction: long-only (LO) vs long/short (LS). Shorts only while the coin has a live USDT-M perp.
- Sizing: equal weight (EW: signal / N eligible) vs inverse-vol (IV: equal risk per coin,
  weight ∝ 1/σ30d, normalised over all eligible coins). Gross exposure ≤ 1 in both; no leverage.
- Portfolio cap: off vs on. On = scale the whole book down when ex-ante portfolio vol
  (trailing 60d daily covariance, known at the bar close) exceeds 50%/yr.
Trials: this study 24. Prior directional trials 167 (local) + 56 (cloud) = 223. **Total N = 247.**
(Carry study's 684 configs excluded: market-neutral, different question; DSR at N = 931 reported as sensitivity.)

## Execution and costs
- Signal at bar close t, trade at the same close, earn bar t+1. Weights drift with prices.
- No-trade band: a coin is re-sized only if its sign changes or |target − held| > 25% of |target|.
- Primary venue: USDT-M perps. Cost per side = taker 0.05% + slippage 0.05% = 0.10% of traded notional.
  Real funding charged on every perp position (long pays positive rate, short receives) for the bar that
  contains the funding timestamp. Before a coin's perp exists: spot, no funding, same cost.
- Sensitivities (reported, not used for the pick except rule D3): 2× costs; LO on spot at 0.15%/side, no funding.
- Benchmark: BTC spot buy-and-hold, no cost.

## Metrics
Daily returns (UTC). Sharpe = mean/sd × √365. CAGR, max drawdown on daily equity, total return, trades
(position entries incl. flips), time in market (% days with any position), avg gross exposure, calendar-year returns.

## Dev selection rule (dev data only)
Eligible if all hold on dev:
- D1 Sharpe > BTC buy-and-hold Sharpe.
- D2 max drawdown shallower than BTC's.
- D3 Sharpe at 2× costs > BTC buy-and-hold Sharpe.
- D4 positive return in ≥ 3 of the 5 dev calendar years (2019–2023).
Pick = highest dev Sharpe among eligible. If two are within 0.05 Sharpe, prefer the simpler:
LO over LS, EW over IV, no cap over cap, then fewer trades. No eligible candidate → "none", stop there
(holdout still run once for reporting only). The pick is written to `secim.json` before the holdout runs.

## Holdout success bar (fixed now, all must hold for the pick)
- H1 Sharpe > BTC buy-and-hold Sharpe (same window).
- H2 max drawdown shallower than BTC's.
- H3 Deflated Sharpe ≥ 0.95 on holdout daily returns, N = 247 trials, SR variance = cross-sectional variance
  of the 24 candidates' dev daily Sharpe (frozen in `secim.json`). Conservative on purpose: the family was
  chosen with earlier looks at 2024–2025 data.
- H4 positive return in ≥ 2 of the 3 holdout calendar years (2024, 2025, 2026 to date).
If the pick fails any test: result is "none passed". No fallback to the runner-up (that would select on the holdout).

## Integrity checks
- Truncation (lookahead) test on dev: run with data cut at 2022-07-01 and compare to the full dev run up to the cut.
- After the holdout run: dev metrics recomputed from the full-data run must match the dev-only run.
- Fresh reviewer (model fable) reads this plan and the code before the holdout; fixes logged below.

## Files
`evren.py` universe, `veri.py` data, `motor.py` engine, `dev.py` dev + freeze, `holdout.py` one-shot holdout.
Outputs: `dev_tablo.csv`, `secim.json`, `holdout_tablo.csv`, `SONUC.md`, `paper_spec.md` (only if a pick passes).

## Change log (reviewer findings and fixes)
Reviewer: fresh agent (model fable), given this plan and the code only, before any dev or holdout metric was computed.
Verdict: no high-severity issue (its own checks: weight-level truncation diff 0.0, funding sign/attribution,
drift/band/cost hand checks, DSR vs scipy all OK).
- M1 truncation test too weak (returns, last 2 days skipped, not gating) → now compares WEIGHTS on every bar up to
  three cuts (2020-03-15, 2022-05-10, 2023-07-01); `dev.py` aborts if max |Δw| > 1e-12.
- M2 H3 strictness depends on the grid's Sharpe dispersion → `dev.py` freezes the implied minimum holdout Sharpe for
  DSR ≥ 0.95 in `secim.json`, so the bar is visible before the run. Bar kept as registered (requested by owner).
  Variance now ddof=1.
- M3 "holdout mostly not virgin" → agreed, already stated above. Reviewer's proposed clean window (2025-12-01+) is
  NOT clean either: the cloud tournament reported holdout results for these families for 2025-11-16 → 2026-11-16.
  No virgin window exists; hence N = 247 is charged. Not adopted.
- M4 freeze only by file existence → `secim.json` now stores sha256 of evren/motor/dev/holdout/plan and of the cache;
  `holdout.py` refuses on any mismatch, writes a started-marker first, asserts end = 2026-11-21 00:00 UTC,
  and asserts dev Sharpes from the full-data run equal the frozen dev-only ones.
- L5 H2 (DD shallower than BTC) is weak for a gross ≤ 1 book; H3 is the binding test. Noted, bar unchanged.
- L6 holdout printout invited runner-up picking → verdict for the frozen pick printed first; the rest labelled reporting-only.
- L7 band could ignore cap scale-downs → book is fully rebalanced to target when held gross > 1.10 × target gross
  (also keeps gross ≤ 1: full rebalance if held gross > 1).
- L8 BCHABC→BCH rename left a one-bar hole (spurious round trip) → holes ≤ 1 day inside a coin's life are filled with a
  flat bar at the last close. LUNA's 2022-05 halt was not pre-announced; the exit-at-last-close rule flatters LS shorts
  there (≤ 1/19 weight). Kept, disclosed.
- L9 "999" in the 2020 snapshot verified: CMC rank 19 was a token literally named "999", not on Binance. Universe is the
  Binance-tradable subset of the top 20 (14–19 coins), dropped coins are not back-filled from rank 21+.
- L10 universe gated on spot data although venue is perps (XMR/MATIC/EOS/MKR leave at spot delisting). Ex-ante, stated.
- L11 yearly returns no longer rounded before the > 0 test; trades are counted from target sign changes (every one is
  executed). Pre-perp longs cost 0.10%/side (primary spec); spot sensitivity uses 0.15%.
