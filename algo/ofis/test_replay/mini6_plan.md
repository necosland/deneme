# Mini-replay for fix 6 — pre-registration

Written 2026-11-21 ~11:50 TR, before any call of this test. Owner-approved change (fix 6 in
`C:\Users\pc\trader-ofis-egitim\HIC-ISLEM-YOK-2026-11-21.md`). Paper only, no keys, no live ledger/log writes.
No budget cap. Script: `mini6.py`; outputs under `mini6/`; results in `MINI6_SONUC.md`.

## Change under test
Method files of Selin (`trader-seviye\seviye-yontem.md`), Bora (`trader-senaryo\senaryo-yontem.md`), Tolga
(`trader-likidite\likidite-yontem.md`) in `C:\Users\pc\.claude\agent-bilgi\trader-ofis\`:
1. One named with-trend market-entry setup each (trend regime + price at/near a valid trigger; entry at last
   close, structural stop, net R:R to T1 >= `min_rr_t1` 1.5, owner-fixed).
2. Soft confirmations (rejection candle, 1.5x breakout volume, "1d mixed", other non-structural filters) become
   explicit confidence reductions; level, stop beyond structure and R:R stay hard gates.
No change to other experts, code or config.

## Design
- Rounds (8, cached snapshots and views, same as the 36-round replay): trend-up R06, R17, R19, R33; range R04,
  R12, R35, R40. Rounds with old votes from these experts: R04, R06, R17, R33, R35. R19 (strong trend, no old
  vote) and R12/R40 (range, no old vote) test whether the new setup speaks in trend and stays quiet in range.
- Experts: trader-seviye, trader-senaryo, trader-likidite only. Same prompts byte for byte (copied from
  `raw/Rxx/prompt_<expert>.txt`), same `replay.run_agent` (claude -p, agent frontmatter model
  `claude-sonnet-5-5`, Read only, round folder as cwd). No Riza, no other experts.
- Three arms, 48 blocks each (8 rounds x 2 assets x 3 experts):
  - `orig`: the blocks already in `raw/Rxx/blocks.json` (old files, first run).
  - `ctrl`: old files re-run now (run-to-run noise of the same files). Run BEFORE any file edit.
  - `new`: edited files. Run after the edit.
- Scoring: one pass over all arms with the same code (`defter.score_one`, `defter.vote_check`, `ortak.rr_cost`,
  `ortak.geometry_errors`, `defter.add_shadow` + `process_candles` on cached/fetched 1m candles, frozen settings
  `ayar_frozen.json`; 1R shadow per valid directional block, one shadow ledger per arm in time order).

## Metrics (per arm, per expert, trend vs range)
Directional count; market / limit / stop entries; setup names; confidence min / median / max; geometry-valid;
EV-pass (`vote_check`, vote_rule ev, min_ev_r 0.15); hit at horizon (`score_one`); path T1-first vs stop-first;
shadow filled / closed / R list / mean R; counter-regime share (`defter.counter_regime`).
Rule flags on every directional block (valid or not): net R:R to T1 < 1.5; stop < `min_stop_atr4h`; entry > 2 ATR;
stop not beyond any snapshot level (no pivot / level / VP / AVWAP / equal_hl / FVG price strictly between entry
and stop); for the new market setups: trend definition not met in the snapshot. Every flagged block and every
new valid market block is checked by hand against its rationale.

## Bars (fixed now)
- Speaks more: new directional count >= 2 x ctrl directional count, and >= 8 of 48.
- Not trigger-happy: new directional <= 40% of all blocks and <= 25% of range-round blocks; no new market block
  where its own trend definition fails; new confidence median <= 55 and no market block above 62.
- Rules: zero VALID new blocks with stop not beyond structure (after hand check) or net R:R < 1.5 (code rejects
  these anyway; an invalid one counts as a wasted speak, reported).
- Parsing: >= 90% of new blocks schema-valid or geometry-only invalid.
- Outcome (n tiny, report only, not a bar): hit at horizon and shadow R vs orig/ctrl. Exception: if new directional
  hit rate has Wilson 90% upper < 0.5 with n >= 8, verdict cannot be "keep".
- Verdict: all bars met -> keep. A rules bar broken by one expert -> adjust that expert (or revert it). Trigger-happy
  bar broken or parsing bar broken -> revert. Speaks-more bar missed only -> adjust (loosen) or keep with note.

## Limits
n = 48 blocks per arm, 8 moments; LLM output varies run to run (ctrl arm measures how much). Trend-up period only,
no trend-down rounds. Market-entry shadow fills are immediate, limit fills are not: shadow R compares different
fill mechanics. The new files are live for the office from the moment they are edited; if the verdict is revert,
they are restored from `_yedek` the same afternoon.
