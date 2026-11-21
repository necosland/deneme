# Core trend system — result (Phase 1)

Run 2026-11-21. Paper research, no real money. Plan: `plan.md` (pre-registered, reviewer fixes logged there).
Raw tables: `dev_tablo.csv`, `holdout_tablo.csv`. Frozen pick + hashes: `secim.json`.

## Verdict
**None passed.** The dev pick `btc_filter_ema_4h | long-only | equal weight | vol cap` beat BTC on Sharpe and drawdown
in the holdout and was positive in 2 of 3 years, but failed the Deflated Sharpe bar (0.59 vs 0.95).
No runner-up is promoted: that would be selecting on the holdout. No `paper_spec.md` written.

## Pick vs bar (holdout 2024-01-01 → 2026-11-20, 1055 days)
| Test | Pick | BTC buy-and-hold | Pass |
|---|---|---|---|
| H1 Sharpe > BTC | 0.72 | 0.48 | yes |
| H2 maxDD shallower than BTC | −30.2% | −53.0% | yes |
| H3 DSR ≥ 0.95 (N = 247) | 0.59 | – | **no** |
| H4 positive in ≥ 2 of 3 years | 2024 +62.4%, 2025 −7.5%, 2026 +9.2% | +121.3%, −6.3%, −32.7% | yes |

Pick other holdout numbers: CAGR 18.7% (BTC 12.2%), total +64.1% (BTC +39.4%), 956 entries, in market 54% of days,
avg gross 33%. 2× cost Sharpe 0.60; spot execution (0.15%/side, no funding) Sharpe 0.77.
DSR sensitivity: N = 24 → 0.70, N = 931 (incl. carry configs) → 0.53. Required holdout Sharpe for DSR 0.95 at N = 247
was frozen before the run: **1.56**. No candidate reached even 1.0.

Dev BTC benchmark (2019-01-07 → 2023-12-31): Sharpe 1.04, CAGR 60.6%, maxDD −76.6%.

## All 24 candidates (Ho = holdout; vs BTC = holdout difference; DSR on holdout, N = 247)
Only the first-ranked dev-eligible row was allowed to count; the rest is reporting only.

| Candidate | Dev Sharpe | Dev CAGR % | Dev maxDD % | Dev trades | Dev in-mkt % | Ho Sharpe | Ho CAGR % | Ho maxDD % | Ho trades | Ho in-mkt % | Ho Sharpe − BTC | Ho DD − BTC (pp) | Ho DSR | Dev elig. |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| donchian_4h LO EW nocap | 0.97 | 26 | -28 | 1043 | 66 | 0.96 | 19 | -14 | 567 | 62 | +0.48 | +39 | 0.74 | no |
| donchian_4h LO EW cap | 1.17 | 28 | -23 | 1043 | 66 | 0.97 | 19 | -15 | 567 | 62 | +0.49 | +38 | 0.75 | yes |
| donchian_4h LO IV nocap | 1.04 | 27 | -25 | 1043 | 66 | 0.92 | 16 | -14 | 567 | 62 | +0.44 | +39 | 0.72 | no |
| donchian_4h LO IV cap | 1.23 | 29 | -21 | 1043 | 66 | 0.94 | 16 | -14 | 567 | 62 | +0.46 | +39 | 0.73 | yes |
| donchian_4h LS EW nocap | 0.69 | 25 | -48 | 1746 | 86 | 0.19 | 1 | -41 | 1233 | 93 | -0.29 | +12 | 0.25 | no |
| donchian_4h LS EW cap | 0.91 | 29 | -35 | 1746 | 86 | 0.34 | 6 | -34 | 1233 | 93 | -0.14 | +19 | 0.33 | no |
| donchian_4h LS IV nocap | 0.69 | 24 | -46 | 1746 | 86 | 0.23 | 3 | -38 | 1233 | 93 | -0.25 | +15 | 0.27 | no |
| donchian_4h LS IV cap | 0.94 | 30 | -34 | 1746 | 86 | 0.37 | 7 | -31 | 1233 | 93 | -0.11 | +22 | 0.35 | no |
| btc_filter_ema_4h LO EW nocap | 1.22 | 57 | -37 | 1557 | 59 | 0.63 | 17 | -36 | 956 | 54 | +0.15 | +17 | 0.52 | yes |
| **btc_filter_ema_4h LO EW cap (PICK)** | **1.33** | 48 | -29 | 1557 | 59 | **0.72** | 19 | -30 | 956 | 54 | +0.24 | +23 | **0.59** | yes |
| btc_filter_ema_4h LO IV nocap | 1.26 | 58 | -35 | 1557 | 59 | 0.73 | 19 | -31 | 956 | 54 | +0.25 | +22 | 0.59 | yes |
| btc_filter_ema_4h LO IV cap | 1.33 | 47 | -29 | 1557 | 59 | 0.82 | 20 | -27 | 956 | 54 | +0.34 | +26 | 0.65 | yes |
| btc_filter_ema_4h LS EW nocap | 0.92 | 51 | -42 | 2875 | 96 | 0.52 | 14 | -45 | 1912 | 100 | +0.04 | +8 | 0.45 | no |
| btc_filter_ema_4h LS EW cap | 1.23 | 60 | -27 | 2875 | 96 | 0.81 | 30 | -33 | 1912 | 100 | +0.33 | +20 | 0.65 | yes |
| btc_filter_ema_4h LS IV nocap | 0.91 | 48 | -42 | 2875 | 96 | 0.62 | 20 | -39 | 1912 | 100 | +0.15 | +14 | 0.52 | no |
| btc_filter_ema_4h LS IV cap | 1.20 | 57 | -26 | 2875 | 96 | 0.86 | 31 | -32 | 1912 | 100 | +0.38 | +21 | 0.67 | yes |
| ema_btcf_1d LO EW nocap | 0.92 | 34 | -48 | 790 | 53 | 0.38 | 7 | -40 | 586 | 57 | -0.10 | +13 | 0.36 | no |
| ema_btcf_1d LO EW cap | 1.00 | 30 | -38 | 790 | 53 | 0.43 | 9 | -36 | 586 | 57 | -0.05 | +17 | 0.39 | no |
| ema_btcf_1d LO IV nocap | 0.97 | 35 | -42 | 790 | 53 | 0.52 | 11 | -35 | 586 | 57 | +0.04 | +18 | 0.45 | no |
| ema_btcf_1d LO IV cap | 1.07 | 32 | -34 | 790 | 53 | 0.61 | 14 | -34 | 586 | 57 | +0.13 | +19 | 0.51 | no |
| ema_btcf_1d LS EW nocap | 0.65 | 24 | -70 | 1327 | 87 | 0.19 | -1 | -56 | 1056 | 94 | -0.29 | -3 | 0.25 | no |
| ema_btcf_1d LS EW cap | 0.95 | 36 | -46 | 1327 | 87 | 0.37 | 7 | -48 | 1056 | 94 | -0.11 | +5 | 0.35 | no |
| ema_btcf_1d LS IV nocap | 0.63 | 22 | -67 | 1327 | 87 | 0.31 | 5 | -49 | 1056 | 94 | -0.16 | +4 | 0.32 | no |
| ema_btcf_1d LS IV cap | 0.96 | 36 | -44 | 1327 | 87 | 0.49 | 12 | -46 | 1056 | 94 | +0.01 | +7 | 0.43 | no |

Trades = position entries incl. flips, summed over coins. In-mkt = % of days with any open position.
Dev rule: D1 Sharpe > BTC (1.04), D2 DD shallower, D3 2× cost Sharpe > BTC, D4 ≥ 3 of 5 positive years.
Pick = top dev Sharpe; LO/IV/cap at 1.329 was within 0.05 → simpler EW preferred (pre-registered tie-break).

## What the data says (descriptive, not a selection)
- Every long-only trend book beat BTC on drawdown in both periods. Edge over BTC on Sharpe is real-looking but
  small and not statistically separable from 247 tries.
- Dev ranking carried over only loosely: dev #1 family (btc_filter_ema) was mid-pack in holdout; donchian LO
  (dev 0.97–1.23) was the holdout best (0.92–0.97, DD −14%). Picking it now would be holdout selection.
- **Long/short hurt** in 12 of 12 like-for-like pairs in dev and 10 of 12 in holdout (exceptions: btc_filter_ema
  with cap). Shorting alts in a trend system is not worth it here (2025 whipsaw: −7% to −37%).
- **Portfolio vol cap helped** in 12 of 12 pairs in dev and 12 of 12 in holdout. The only structural choice that held.
- Inverse-vol vs equal weight: no consistent difference.
- Funding drags long books: spot execution (0.15%/side, no funding) beat perp execution (0.10%/side + funding)
  for every LO candidate in both periods. Long-only belongs on spot.
- ema_btcf_1d, the cloud round's favourite, was the weakest family in this survivorship-free, point-in-time test.

## Integrity checks
- Weight-level truncation test (3 cuts in dev): max |Δw| = 0.0.
- Dev Sharpes recomputed from the full-data run equal the frozen dev-only values (asserted).
- Code and cache sha256 frozen in `secim.json` before the holdout; verified at run time. Holdout run once
  (`holdout_started.txt`).

## Caveats
- **The holdout is not virgin.** Families and parameters came from earlier rounds that saw 2024–2026 data.
  That is why the DSR charges N = 247; it makes the bar very hard (needed Sharpe 1.56 over ~2.9 years).
- Universe from CoinMarketCap January snapshots, read via a web-fetch summariser, not hand-checked row by row.
  Binance-tradable subset only (14–19 coins); coins without a Binance market are dropped, not back-filled.
- Delisting exit at the last close assumes advance notice; LUNA's 2022 halt was not announced (minor effect, LS only).
- Funding from Binance REST; perp start/end inferred from the first/last funding stamp.
- 2026 is a partial year (to 2026-11-20). Holdout BTC path: +121%, −6%, −33%: one bull year, two weak ones.
- Parameters fixed at paper-bot values; no parameter robustness tested in this round.

## Recommendation
No new core system for the paper bot from this round. Keep the current paper systems running as they are and
treat them as unproven. If a single paper candidate is wanted anyway, the honest one is the frozen dev pick
(btc_filter_ema_4h, long-only, spot, equal weight, 50% vol cap), labelled "did not pass", not the holdout winner.
