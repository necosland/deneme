# Mini-replay fix 6 — results

2026-11-21. Plan: `mini6_plan.md` (written before any call). Script `mini6.py`; data `mini6/sonuc.json`,
`mini6/bloklar.csv`, `mini6/islemler.csv`, raw blocks `mini6/raw_ctrl|raw_new/Rxx/blocks.json`.
Paper only. No live ledger/log write. Cost: ctrl $3.81 + new $4.01 = $7.82 (48 calls, 0 errors, all
`claude-sonnet-5-5`, same turn counts as the original run).

## Setup
- Rounds: trend-up R06 R17 R19 R33, range R04 R12 R35 R40. Experts: Selin, Bora, Tolga. Prompts byte-identical to
  `raw/Rxx/prompt_*.txt`.
- Arms: `orig` = original replay blocks; `ctrl` = old files re-run today (noise); `new` = edited files.
- Edited (outside repo, `C:\Users\pc\.claude\agent-bilgi\trader-ofis\`): `trader-seviye\seviye-yontem.md`
  (`trend_level_market`), `trader-senaryo\senaryo-yontem.md` (`trend_hold_market`),
  `trader-likidite\likidite-yontem.md` (`trend_bos_market`); soft confirmations -> conf modifiers; evidence text moved
  verbatim to new `seviye-kanit.md`, `senaryo-kanit.md`, `likidite-kanit.md` (size cap), INDEX lines added,
  one line in `seviye-yt.md`. Backups `_yedek\*.1149`.

## Numbers (48 blocks per arm)

| Metric | orig | ctrl | new |
|---|---|---|---|
| Directional (all / valid) | 9 / 8 | 5 / 3 | 8 / 7 |
| Trend rounds / range rounds (valid) | 6 / 2 | 2 / 1 | 4 / 3 |
| Market / limit | 0 / 8 | 0 / 3 | 0 / 7 |
| Conf min / median / max | 36 / 40 / 42 | 42 / 42 / 45 | 33 / 38 / 42 |
| EV-pass | 7 | 3 | 7 |
| Hit at horizon (valid) | 6/8 | 2/3 | 5/7 |
| Path T1-first / stop-first | 5 / 2 | 1 / 1 | 5 / 2 |
| Counter-regime (BTC SMA200) | 5 | 2 | 5 |
| Shadow orders / filled | 8 / 4 | 3 / 2 | 7 / 3 |
| Shadow R | -1.20 -1.25 -1.14 -1.19 (sum -4.79) | -1.26 +1.10 (-0.16) | -1.07 -1.27 -1.15 (-3.49) |
| Schema-valid or geometry-only invalid | 48 | 46 | 47 |

Per expert, valid directional orig/ctrl/new: Selin 3/0/4, Bora 4/2/2, Tolga 1/1/1.

## Market setup
- 0 market blocks. All three experts named and checked their new setup in every trend slot (rationales cite it).
- Why it never qualified: net R:R to the first obstacle < 1.5 (R06 x3, R17 ETH, R19 BTC, R35 BTC 1.39); price
  1.6-2.7 ATR past the trigger (R17 x4, 4h RSI 92-95; R35 ETH); trigger older than 6 4h candles (R06 ETH, R12 BTC,
  R19 BTC); no trigger/BOS (R19, R35). Matches the diagnosis: at market the old stops/T1 gave median net R:R ~0.9.
- Binding constraint is the owner-fixed 1.5 floor with T1 = first obstacle, not the setup wording.

## Modifiers
- Applied and written as `MOD:`: Selin fade without rejection -10 (R04 BTC long conf 40, R33 BTC long conf 33;
  both now voice instead of flat), breakdown volume 0.99x -5 (R33 ETH); Tolga 1d mixed -5 (R04 BTC); Bora OI note
  (R19 ETH). Confidence fell rather than rose (median 38 vs 40-42): honest, near break-even + small margin.

## Rule flags
- Valid blocks with stop not beyond any snapshot level: 0 (code check), 0 (hand check of all 7 valid new blocks:
  stops beyond PWL/sweep low/LH/level + 0.25-0.5 ATR).
- Valid blocks with net R:R < 1.5: 0.
- Invalid directional: new 1 = Selin R35 ETH short, T1 2438 not beyond last close 2431 (new code check, fix 7);
  same block shape exists in orig (then rejected at net R:R 1.48). ctrl 2 = Selin R17, same T1 check.

## Bars (from plan)
- Speaks more (>= 2 x ctrl and >= 8): MISSED. 8 vs 10 needed; >= 8 met.
- Not trigger-happy: MET. 8/48 = 17%, range 4/24 = 17%, conf median 38, max 42, no market block.
- Rules: MET. Parsing: MET (47/48).
- Outcome veto (Wilson upper < 0.5): not triggered (5/7).

## Verdict: keep
- Plan rule: only the speaks-more bar missed -> adjust or keep with note. Keep, no loosening: the only loosening that
  would have produced market blocks here is a wider trigger window/distance, i.e. buying 2-3 ATR extended moves at
  4h RSI > 90. That is the trigger-happy direction.
- Noise is as large as the effect: same old files gave 9 then 5 directional blocks. 8 new is inside that band; this
  test cannot show more speaking, only that nothing broke.
- Next measurement is live: count `trend_*_market` blocks and `MOD:` lines in the live office over 1-2 weeks.

## Caveats
- Shadow scoring ran on office code changed 11:47 TR by another agent (order life = min(horizon, 24h), T1-beyond-
  close check). All arms were scored in one pass with that code, so orig differs from `SONUC.md` (4 fills, not 2).
- n = 48 per arm, 8 moments, no trend-down rounds. Shadow R compares 2-4 fills: no information.
- The edited files are live for the office since ~11:52 TR.
