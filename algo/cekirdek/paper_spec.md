# cekirdek_v1 — paper spec (Phase 1 frozen pick, forward test)

Written 2026-11-21. Paper only, fake USDT, no orders, no keys. Owner-approved as an **unproven candidate**:
the pick failed holdout H3 (DSR 0.59 < 0.95, see `SONUC.md`). This spec does not change that verdict.
Pre-registered forward test: `ileri_plan.md`.

## Source of the rules
- Frozen pick in `secim.json`: `btc_filter_ema_4h | LO | EW | cap`, run on **spot** (the SONUC spot variant:
  0.15% per side, no funding). Long-only books lost to funding on perps in every test, so spot.
- `algo/paper.py` imports the frozen `cekirdek/motor.py` (sha256 in `secim.json`) for the signal
  (`sig_btc_filter_ema`), sizing and vol cap (`weights`), and constants (`WARMUP_DAYS`, `BAND`, `VOL_CAP`,
  `SPOT_COST`). Only the universe source and the live data window are paper-side code.

## Rules (identical to the backtest)
1. Data: Binance spot USDT klines, 4h for signals, 1d for the covariance. Bar index = open time; only closed bars.
   Holes of ≤ 1 day inside a coin's life are filled with a flat bar at the last close (as `motor.load`).
2. Signal per coin at the close of 4h bar t: 1 if EMA10 > EMA100 of the coin's own 4h closes AND EMA10 > EMA100
   of BTC's 4h closes, else 0. EMA = `ewm(span=n, adjust=False)`. No shorts.
3. Eligible at bar t: coin is in the universe (below), has a close at t, and has more than 360 own 4h bars
   (60 days). Paper fetches the last 1000 4h bars, so long-listed coins always pass; new listings wait 60 days.
4. Weight = signal / N, N = number of eligible coins at t (BTC included). Gross ≤ 1, no leverage.
5. Vol cap: ex-ante vol = √(wᵀΣw), Σ = 60-day rolling covariance of daily returns (pairwise, min 30 obs) × 365,
   using daily bars fully closed by the 4h bar's close. If > 50%/yr, all weights × 0.50 / vol.
6. No-trade band: a coin is resized only if its sign changes or |target − held| > 25% of |target|. If the result
   has gross > 1 or > 1.10 × target gross, the whole book is set to target.
7. A coin that leaves the universe, or whose Binance data stops, gets target 0 and is sold.

## Universe (point-in-time)
- Rule (same as the backtest): CoinMarketCap historical snapshot, top 20 by market cap after removing stablecoins
  and wrapped/liquid-staking tokens, then the subset that trades on Binance spot vs USDT. No back-fill from rank 21+.
- Start list, from the CMC weekly snapshot of **2026-11-15** (latest before start), active from 2026-11-16:
  BTC, ETH, BNB, XRP, SOL, TRX, HYPE, ZEC, DOGE, LINK, ADA, XLM, BCH, NEAR, LTC, AVAX, UNI (17).
  Out: LEO and CC (no Binance market), XMR (Binance spot status BREAK, delisted 2024). Stablecoins removed:
  USDT, USDC, USDe, DAI. HYPE listed on Binance spot 2026-09-24, so it becomes eligible about 2026-11-23.
- Refresh: once a year. In the first week of January add the CMC snapshot of the first Sunday of January
  (next: 2027-01-03) to `CEK_UNIVERSE` in `paper.py`, same filter, active from the next day. No other changes.
- Why not keep the Jan-2026 list the backtest was using: it is 10 months stale (SUI and HBAR are no longer top 20;
  NEAR and UNI are). A snapshot dated before the start is still point-in-time, and from January 2027 the rule is
  exactly the backtest's. Monthly refreshes were not tested, so they are not used.
- Source check: ranks 1–20 read from the CMC page on 2026-11-21; ranks 17–20 of the non-stable list (LTC, CC,
  AVAX, UNI) come from the page's unranked tail and agree with CoinGecko on 2026-11-21. CoinGecko also ranks
  FIGR_HELOC and WBT in its top 20; CMC does not. Neither trades on Binance. CMC is kept because the backtest
  used it. Binance status checked with `exchangeInfo` on 2026-11-21.

## Execution
- Paper: one fill per run (the workflow runs about 10 min after each 4h close) at the last closed bar's target.
  Live ticker price, fee 0.10% per side, real slippage = live price vs bar close (logged as `kayma_%`).
  Sells before buys; buys scaled down pro rata if cash is short because of fees. If a run is missed, the paper
  book jumps straight to the latest target.
- Shadow (`golge`): backtest accounting on every 4h bar since the previous run, filled at the bar close,
  0.15% per side, no funding; same step as `motor.simulate` (drift, band, cost).
- Start: 1000 fake USDT, all cash. Benchmarks: `al_tut_btc` (BTC from the start price, no cost) and
  `al_tut_6coin` (same 6-coin basket as the other paper systems).
- Files: same as the other systems. `state.json` → `systems.cekirdek_v1` (`nakit`, `adet` units per coin,
  `golge.deger`, `golge.h` weights, `evren` snapshot used, `tepe`, `son_mum`), rows in `islemler.csv` and
  `ozsermaye.csv` with `sistem = cekirdek_v1`. `acik` lists coin:weight%.
- Kill line in `DURUM.md`: drawdown from peak below 1.5 × −31.0% = −46.4% (−31.0% = holdout spot maxDD).
- Isolation: an error in cekirdek_v1 is written to `DURUM.md` as HATA and does not stop the other three systems.

## Verification (2026-11-21, dry run `python paper.py --dry`, no files written)
- Weights: paper code on live-fetched data with the Jan-2026 universe vs `motor.run_all(spot_mode=True)` on the
  cekirdek cache, 599 bars 2026-08-13 → 2026-11-21 04:00 (276 with positions): max |Δw| 1.4e-17, 0 sign mismatches.
- Shadow: the incremental shadow (runs every 1–3 bars) vs `motor.simulate` on the cache, from a flat bar at
  2026-08-18 to 2026-11-21 04:00 (572 bars): 1241.0758 vs 1241.0758 (relative diff −2e-16).
- Current state at 2026-11-21 04:00: BTC EMA10 59,791 < EMA100 68,369, so the BTC filter is off and the book is
  **all cash**. No coin in the live universe has its own EMA10 > EMA100 either.
