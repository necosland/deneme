# Elliott k=4 wave-3 forward paper test: pre-registration

Written 2026-11-21 09:2x TR (06:2x UTC), before the forward period starts. Paper only, no LLM, no real orders, cost 0 $.
Nothing below changes after the start. Any later change goes in a new section marked "CHANGED AFTER START" and the
forward result then counts as exploratory.

## Why
Backtest v2 (`kod_plan.md` last section, `KOD_SONUC.md`) failed overall. One exploratory slice looked good: zigzag
degree k=4, wave-3 setups (+0.245 R, t 4.1, n 328, both halves > 0). It was 1 of ~28 slices, so it is a hint, not
evidence. This test checks it on data that did not exist when it was found.

## Rule (identical to `kod_test.py backtest2`, restricted to k=4 and w3)
- Code: `algo/ofis/elliott_ileri.py` calls `kod_test.signals()` itself (V2=True, KS=(4.0,)) and keeps only kind w3.
  Trade management = `kod_test.sim()` logic (copy that also returns "still open"); verified identical on 2020-2026
  (1127/1127 trades, 0 mismatches).
- Data: Binance spot 4h closed bars, base volume; history from algo/cache (2019 ->) or Binance from listing, extended
  each run. Zigzag/ATR/RSI are causal; a pivot is usable only from its confirmation bar.
- Setup: zigzag k = 4.0 x ATR14, both directions (down impulse = short). On each confirmed pivot, the highest-score w3
  count with score >= 50 (`elliott_say.py` hard rules).
- Signal: first close beyond the w1 end (trigger) at or after the pivot confirmation bar and before the next pivot
  confirmation; no signal if price went below the w2 end or touched 1.0 x w1 (from w2 end) first.
- Entry: open of the bar after the signal bar. Skip if entry is not between stop and T1.
- Stop = w2 end. T1 = w2 end + 1.618 x w1, T2 = w2 end + 2.618 x w1 (targets may be unreachable, e.g. below 0 for
  a short; kept as is).
- Exit: half at T1, then stop to entry, rest at T2. Time stop 60 bars (close of bar 60). Stop and target in the same
  bar = stop first. Gap through stop = fill at bar open.
- One open trade per coin at a time (signals while open are skipped; ties: higher score first).
- Cost 0.1% per side (0.05% fee + 0.05% slippage), deducted in R. Size: fixed 1 R per trade.
- Note vs backtest: in the backtest k=4 trades were also blocked by open k=1.5/2.5 trades. Here only k=4 exists, so
  more k=4 trades fire. Same rule run k=4-only on 2020-2026 (12 backtest coins, exploratory, computed before start):
  1125 trades, +0.139 R, t 4.7; 2020-23 +0.206 R (n 614), 2024-26 +0.059 R (n 511, t 1.4). ~160 trades/year/12 coins.

## Universe, timing
- Coins (frozen, `veri/evren.json` 2026-11-20 21:40): BTC, ETH, BNB, XRP, SOL, TRX, HYPE, ZEC, DOGE, LINK (USDT).
- Start: signal bars that open at or after **2026-11-21 08:00 UTC** (first one closes 12:00 UTC). Earlier signals are ignored.
- Runs after each 4h round (hook at the end of `tur.py`); it recomputes the whole forward period from the start each run
  (idempotent), freezes entry/stop/targets of logged trades and logs a WARN if a recompute differs.
- Ledger: `defter/elliott_ileri.json` + `.csv` (separate from the office ledger), log `log/elliott_ileri.log`,
  status `elliott_ileri.md` + one line in DURUM.md.

## Evaluation (fixed now)
- Primary: the first 30 trades by close time, judged no earlier than day 56 (8 weeks). Mean R and 90% CI (t-dist).
  **PASS only if the CI lower bound > 0.** If 30 closed trades are not reached by day 365, judge what exists.
- Secondary (same bar): first 100 closed trades.
- Always reported, not part of pass/fail: BTC buy-and-hold over the same period (first signal-eligible bar open -> last
  close), win %, total R, long/short split.
- Power note: with sd ~1 R, n=30 needs mean ~> +0.31 R to pass; the backtest mean (+0.06..0.2 R) would likely not pass.
  A FAIL at 30 does not prove no edge; a PASS would be strong. The secondary 100 look is the realistic one.
- A pass does not make it a live office signal by itself; owner decides.

## Data-validity fix 2026-11-21 (not a rule change)
Short targets can go <= 0 or beyond a sane move when wave 1 is huge (seen: ZEC short T2 -561). `kod_test.cap_targets`
now clamps a short target to a 90% move from entry (`TARGET_CAP_PCT`), marks the trade `target_capped` and logs it
(`elliott_ileri.log`). Longs and normal targets are untouched; setup, entry, stop, scoring and evaluation are unchanged.
Already-logged trades keep their frozen values (WARN on recompute diff).
