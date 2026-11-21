# Ekrem LLM filter test: pre-registration (written before any run)

Date: 2026-11-21 ~01:50 local. Written after Ekrem's role rewrite (elliott-yontem.md 2026-11-21) and before any LLM call.
Any later change to metric, rule or pass bar goes into a section "CHANGED AFTER" and makes that result exploratory.

## Question
Does Ekrem, used as a filter on the code's w3/w5 candidates, pick trades that do better than (2) taking every code setup
at the same points and (3) random entries with the same geometry?

## Data
- `noktalar.json`: 210 cut points, BTC/ETH 4h, 2020-2026. `_key_*` fields never shown to Ekrem.
- Input per point = live "elliott" view rebuilt at the cut from `algo/cache` (4h last 500 bars, 1d closed days last 400):
  ctx (last_close, ATR14 1d/4h, RSI14 1d/4h, SMA200 1d, EMA20/50/200 1d, EMA20/50 4h, chg 24h/7d),
  structure 1d + 4h (veri_topla.structure), elliott (elliott_say.analyze), candles 1w(12)/1d(30)/4h(30).
  Omitted vs live (stated to Ekrem): charts, 1h data, levels, fvg, equal_hl, vp, avwap, macro, derivs.
- Hiding: prices scaled so last 4h close = 1000; volume not shown; dates shifted by a whole number of weeks so every
  cut sits in year 2001; symbol replaced by a neutral code. No bar after the cut.
- Batching: up to 6 points per `claude -p --agent trader-elliott` call (Read only). Any two points in one call are
  > 460 days apart (400-day 1d window + 60-bar outcome), so no call contains a cut and its future.

## Trade construction (same for Ekrem and for baseline 2)
- Ekrem block long/short is checked with office `geometry_errors` (min_rr_t1 1.5, min_stop_atr4h 0.5, entry within
  2 x ATR4h) using the scaled prices; failing block = flat (as live). Prices mapped back with the scale factor.
- Entry: market = next bar open. stop/limit = must fill on the next bar (pending order lives one run), stop fills at
  max(open, price) for long (mirror for short), limit at min(open, price). No fill = no trade.
- Exit = kod_test.py `sim`: 50% at T1, stop to entry, rest at T2, time stop 60 bars (close), stop first if same bar.
  Single target = full exit at T1. Cost 0.1%/side (0.2% round trip) in R.
- Baseline (2) "code setups": at every point where the code's PRIMARY state is w3_setup or w5_setup (105 points):
  confirmed -> market; unconfirmed -> stop entry at trigger (next bar only); stop = invalidation (w3) / stop_tight
  (w5); T1 = first code target with R:R >= 1.5 from entry estimate (last close or trigger), T2 = next code target;
  must pass the same geometry check. Also reported: (2b) same but only points where Ekrem traded vs skipped.
- Baseline (3) random: for each Ekrem trade, 200 reps of a random entry bar in the same asset and same period half
  (2020-23 / 2024-26), same direction, same stop %, T1 %, T2 %. Report mean avg R and p = share of reps >= Ekrem avg R.

## Metrics
n, win% (R > 0), avg R, total R, t = mean/(sd/sqrt n) for (1) Ekrem, (2) code setups, (3) random mean.
Ekrem flat rate on non-setup points (code primary not w3_setup/w5_setup); expected >= 90%.
Ekrem trade rate on setup points. Cost (sum of `total_cost_usd`).

## Pass bar (pre-set)
Ekrem filter "passes" only if ALL: n >= 10, avg R > 0, avg R > (2) avg R, random p < 0.05, non-setup flat rate >= 90%.
Pass = worth live paper tracking, NOT proof (n will be small; repo standard for proof is t > 3, not reachable here).
Otherwise "not shown". With n < 10 the result is "too few trades to judge".

## Limits
- Hard cost cap $12 total; stop and report if reached. 6-point pilot first (parsing check), pilot points count in the
  final result only if the role files did not change after the pilot.
- Paper only, no keys, no orders. Not edited: tur.py, veri_topla.py, elliott_say.py, defter.py, komite.py, ofis-ayar.json.

## CHANGED AFTER (run notes, no metric/pass-bar change)
- After the 6-point pilot (parsing OK, all flat, $0.33) the method file got 6 extra rules (coordinator request: log-scale
  ratios, broken count = flat, book T1, guidelines only tie-break, hidden divergence = hint, office 1% risk). So the
  pilot is excluded; the full run used all 210 points with the final files.
- Full run: 205/210 answered; 5 lost (N015, N064, N079, N119, N125) when the account session limit was hit at the end.

## 2026-11-21 08:5x: v2 run "full2" (pre-registered before any v2 LLM call)
- Changes vs v1 (owner approved): (a) elliott_say: overlap/diagonal flag is now per count (primary and each alt carry
  their own `flags`; scan-wide `diagonal_like_overlap` removed). (b) w3 targets = [1.618 x w1, 2.618 x w1] from w2 end,
  1.0 x w1 moved to `t_min`; primary also gets `rr_t1`. (c) Ekrem's elliott-yontem.md updated to match (untested).
- Inputs rebuilt with `hazirla` from the same noktalar.json (v1 inputs archived: snap_llm_v1\, llm_meta_v1.json,
  llm_sonuc_v1.json). All 210 points, including the 5 lost in v1.
- 6-point pilot (tag pilot2) for parsing; pilot answers count only if role files do not change after it; then tag full2.
- Baseline (2) uses the new code targets (same rule: first target with R:R >= 1.5). Baseline (3) unchanged.
- Same metrics and same pass bar as above. Cost cap: $12 for v2 calls (v1 spend not counted). Session-limit errors = stop.
- Run notes v2: pilot2 6/6 parsed ($0.32), role files unchanged after pilot -> pilot counts. full2 204/204 ($9.51). Fixed
  snapshot code collision (N015/N208 shared one code in v1; codes now 8 hex). No metric/pass-bar change.
