# LOT 4 — measured findings

Every number here came from a run against stored data. Negative results are
reported with the same prominence as positive ones.

## 1. Open-interest depth solved via Bybit (§6)

Binance's public endpoint serves ~30 days of OI history, which made every
LOT 3 open-interest study return `INSUFFICIENT_DATA`. Bybit's public
`/v5/market/open-interest` paginates by `endTime` and reaches far further
back. No authentication, no paywall, no rate-limit circumvention — the data
was simply held by a different venue.

| Asset | Rows | Coverage | Requests |
| --- | --- | --- | --- |
| BTC | 2223 | 2020-08-05 → 2026-09-05 | 13 |
| ETH | 2145 | 2020-10-22 → 2026-09-05 | 12 |
| SOL | 1894 | 2021-06-30 → 2026-09-05 | 11 |

Pagination stopped on its own — well inside the 40-request budget — so these
are Bybit's actual history limits, not an artificial cut-off. **Open interest
went from 30 days to roughly 6 years.**

## 2. Multi-exchange derivatives (§7)

`AggregatedDerivativesSnapshot` covers Binance, Bybit and OKX with
OI-weighted funding, a Herfindahl concentration index, and a venue-anomaly
flag that fires when one exchange's funding sits more than 4 standard
deviations from the cross-venue median. All three venues currently respond for
all three assets. Binance holds the largest OI share on each
(concentration 0.38–0.47).

## 3. The contrarian funding assumption: not confirmed, not refuted (§8, §9)

The score assumes high funding is contrarian (crowded longs → expect a
pullback). Testing funding percentile bands against forward returns:

- Against zero: every band positive → **artifact of market drift**, discarded.
- Against a same-conditioning baseline: high-funding days beat baseline by
  +1.92% (BTC), +2.19% (ETH), +10.28% (SOL) at 30 days.
- After FDR: 3 / 15 / 9 cells survive out of 225 each.
- After the stability check: **positive in only 2/5, 3/6 and 4/6 years**, with
  ~4 effective independent windows.

**Verdict: INCONCLUSIVE on all three assets.** The direction of the effect
opposes the assumption baked into the score, but the evidence is not strong
enough to justify flipping the sign. No weights were changed. The existing
contrarian sign is not vindicated either — it is simply untested.

## 4. EdgeState across the system (§24)

| Asset | State | Admitted | Rejected |
| --- | --- | --- | --- |
| BTC | NO_MEASURABLE_EDGE | 0 | 3 |
| ETH | NO_MEASURABLE_EDGE | 0 | 15 |
| SOL | NO_MEASURABLE_EDGE | 0 | 9 |

Consistent with LOT 3, where no domain reached `USEFUL` and the Ridge model's
out-of-sample R² was negative on all three assets.

## 5. Volatility regime (§17)

Currently LOW (BTC p20.9, ETH p15.6) and VERY_LOW (SOL p10.0), all stable.
Annualised realised volatility: BTC 47%, ETH 75%, SOL 64%. The engine is
verified directionless: identical shocks under opposite drift produce realised
volatility within 0.6% of each other.

## 6. Crowding (§11)

NORMAL on all three (BTC 42.6, ETH 32.7, SOL 40.8 out of 100). **Direction is
always reported UNKNOWN** — open interest counts contracts, not sides. Current
leverage states: BTC NEW_LONGS, ETH QUIET, SOL LONG_LIQUIDATION.

## 7. NFP intraday event study (§5)

Across 14 US employment reports, realised volatility *falls* after release
(post/pre ratio 0.90–0.98) and volume drops to 0.79–0.85× — consistent with
uncertainty resolving rather than the event injecting volatility.

## What this adds up to

Six years of open interest and 6.4 years of funding did not produce a single
admissible edge. That is the honest state of the system, and the pipeline is
built to keep saying so until something genuinely clears the bar.
