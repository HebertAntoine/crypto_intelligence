# Edge, direction, and why they are never the same number

## The distinction

Two questions look alike and are not:

1. **Where is the market going?** — answered by `MarketRegimeEngine`, from
   trend, structure, momentum and the domain scores.
2. **Have we demonstrated any ability to predict it?** — answered by
   `EdgeEngine`, from research output only.

The system answers them with separate engines that never read each other's
output. `EdgeState` does not know today's regime; the regime does not know
whether an edge was measured. This is enforced by
`test_edge_is_independent_of_market_direction`.

The normal result today is a strong direction alongside `NO_MEASURABLE_EDGE`,
which reads as:

> BTC is strongly bullish, but we currently hold no robust directional edge.

That is not a contradiction and not a bug. It says the trend is real and our
demonstrated ability to forecast it is not.

## What counts as an edge

A relationship is admitted only if it clears every one of these:

| Filter | Threshold | Why |
| --- | --- | --- |
| Multiple testing | survives Benjamini-Hochberg at α=0.05 across the whole study | testing 225 cells produces ~11 "significant" results from noise alone |
| Effective sample | ≥ 20 independent observations | overlapping forward windows inflate the raw row count |
| Effect size | ≥ 0.50% | statistical significance is not tradeable significance |
| Transaction cost | effect must exceed 0.20% round trip | an edge smaller than the fee is not an edge |
| Stability | positive in the majority of years, not one era | a single bull run can carry an entire "relationship" |

Failing any one filter means the evidence is recorded with its rejection
reason and **not** counted. The rejections are visible in the UI and the API;
they are not hidden.

## The drift trap

The first version of the funding study tested each bucket's forward return
against **zero**. Every bucket came out significantly positive at 30 days —
including the most negative funding bucket on SOL (+10.27%). The reason is
simply that BTC, ETH and SOL rose a great deal over the sample. Testing
against zero measures buy-and-hold, not the signal.

The corrected test compares each bucket to **the rest of the sample under the
same conditioning**, so the shared drift cancels. FDR survivors fell from
55/68/56 to 3/15/9. Both numbers are kept in the output; only the excess test
decides anything.

The lesson generalises: in a strongly trending asset, "this signal precedes
positive returns" is nearly content-free. The question is always whether it
precedes *better than average* returns.

## The independence trap

Funding bands persist for a day or two, and 30-day forward windows overlap
almost completely between consecutive days. So 118 in-band days on SOL are
really about **3.9 independent windows**. A t-test on n=118 assumes 118
independent draws and reports a p-value built on a sample it does not have.

`episode_analysis()` counts distinct episodes and per-year consistency, and
the conclusion is downgraded to `INCONCLUSIVE` when the effect is
concentrated. SOL's headline +27.91% excess at 30 days comes almost entirely
from 2021 (+76% excess over 23 days); 2020 was −87%.

## Uncertainty

`UncertaintyEngine` scores 0–100, where higher means less certain. The single
largest contributor is the absence of a measured edge (+40), which is
deliberate: a clean chart does not reduce uncertainty if nothing has been
demonstrated. Crowding raises it further, because crowding raises the cost of
being wrong even when the directional read is clear.

## Actionability

`actionable` is true only when `POSITIVE_EDGE` is measured **and** uncertainty
is below 55. As of this writing it is false for all three assets. The system
never emits BUY or SELL, and
`test_no_buy_or_sell_language_anywhere_in_the_summary` asserts that no order
language can appear in any decision summary for any edge state.
