# Replay test after the model's knowledge cutoff — pre-registration

Written 2026-11-21 before any paid call. Owner-approved, hard cost cap $40 (sum of `total_cost_usd` of every
`claude -p` call, pilot included). Paper only, no keys. Audit item: `DENETIM-2026-11-21.md` "Measurement plan" 7.

## Question
Do the office experts (and Rıza's rules) show any directional skill on price history the model has never seen?
Rough read in days, not proof. Expected verdict with this sample: mostly "inconclusive".

## Leakage control
- Expert model: `claude-sonnet-5-5` (frontmatter of every `trader-*.md`). Anthropic models overview
  (platform.claude.com/docs/en/about-claude/models/overview, read 2026-11-21): Sonnet 5.5 reliable knowledge
  cutoff Jun 2026, training data cutoff Jun 2026.
- Window: 4h closes 2026-07-01 00:00 → 2026-11-14 20:00 UTC (all after the training cutoff; last horizon ends
  before today).
- Dates hidden: every date string in snapshots, charts and calendar shifted by +1820 days (260 weeks; weekday and
  hour kept). Prices and symbols stay real (round-number levels matter to the experts). Experts are told dates are
  shifted and to use only the snapshot.
- Isolation: each call runs in its own round folder (`rounds/Rxx`, no date in the name) with `--add-dir` only the
  agent knowledge folder; no access to other rounds, the live ledger or results. Makro runs with Read only (no
  headline WebFetch: today's headlines would leak the future).
- Residual risk: real price levels can still remind the model of older (pre-cutoff) periods; Coin Metrics and FRED
  serve today's revised values for past dates; schedules (FOMC/BLS) were known in advance anyway.

## Sampling
- 45 slots: slot k asof = 2026-07-01 00:00 + (18k + k mod 6) × 4h (k = 0..44). Spacing 52-92 h (no adjacent
  rounds), hours cycle 00/04/08/12/16/20 UTC.
- Run order = van der Corput order of the slots (0, 22, 11, 33, 5, 28, 16, 39, ...), so any prefix is spread evenly over
  the window. Pilot = first 2 slots in that order. After the pilot, run the prefix that fits the cap; stop starting
  a new round when spent + 1.3 × max round cost seen > $40. The number actually run is reported.
- Regime label per round (for the mix report only): BTC 20-day return > +7% trend-up, < -7% trend-down, else range.
- Assets: BTCUSDT + ETHUSDT every round (no screener).

## Round = live office minus committee
- Snapshot built by `veri_topla.py` functions as of the 4h close (closed candles only), same fields and views
  (`tur.make_view`) as live. Experts: Tolga, Ekrem, Selin, Derya, Bora, Hakan (auto-flat without at_prz/reacted
  candidate, as live), Kerem (called every round: in a non-adjacent sample there is never a fresh previous macro
  block, live would call him too). Then Rıza. No committee. PREV=none, OPEN=none, fresh ledger and empty scores
  every round (rounds are independent).
- Reconstructed for the past: candles, structure, levels, harmonics, Elliott code count, AVWAP, charts; derivatives
  from Binance history (funding, premium index, futures taker buy/sell, OI and long/short ratios from
  data.binance.vision daily metrics); onchain (Coin Metrics), stablecoin supply (DefiLlama), Yahoo/FRED macro
  truncated at asof, Fear & Greed history, BTC ETF flows (Farside) if reachable, USD high-impact calendar rebuilt
  from official schedules (FOMC 2026 from federalreserve.gov, CPI/PPI/jobs/JOLTS from bls.gov 2026 schedule).
- Omitted (cannot be rebuilt): order book, our recorded liquidations/depth, options, Bybit, quarterly basis,
  CoinGecko global, Defne's gundem digest, headline check. Calendar lacks GDP/PCE/retail/ISM → blackout less
  frequent than live.
- Settings frozen: `ayar_frozen.json` = `ofis-ayar.json` copied 2026-11-21 09:39 TR (vote_rule ev, min_ev_r 0.15).

## Metrics
1. Direction accuracy per expert at the block's own horizon (office `defter.score_one`): directional hit = price
   moved the right way; flat hit = |move| < 1 × ATR4h. Context tags (against-long/short) scored too. Baselines:
   share of "up" outcomes at the same horizons (always-long), and the flat-band base rate.
2. Shadow trades: every valid directional block → 1R paper trade with office exits and costs (`defter.add_shadow`
   + `process_candles` on 1m candles, fees, slippage, funding, T1 half + stop to entry, horizon exit). Avg R,
   bootstrap 90% CI, fill rate.
3. EV-rule vote pass rate: share of directional blocks that are valid votes (`defter.vote_check`).
4. Rıza: decisions applied with office code (`apply_decisions` incl. code re-check, R5 calendar, caps) on one
   ledger running forward through the window in time order; final equity vs BTC buy-and-hold over the same span
   (first sampled asof → end), time-in-market %, exposure-matched BTC.
5. Calibration: confidence buckets vs realized "T1 before stop" from the block path, next to break-even 1/(1+RR).

## Pass bars (fixed now)
- Expert "edge signal": ≥ 15 directional blocks AND Wilson 90% lower bound of directional hit rate > 0.5 AND ≥ 10
  shadow trades with mean R > 0. "Negative signal": Wilson upper < 0.5, or ≥ 10 shadow trades with bootstrap 90%
  upper < 0. Else "inconclusive".
- Office: ≥ 5 filled trades and total R > 0 → "positive so far"; else "inconclusive". BTC comparison shown, not a bar.
- Parsing gate after pilot: ≥ 90% of expert blocks schema-valid, else fix the harness (never agent files) first.
- No re-runs of a round to "improve" a result; a failed call is logged and left failed.
