# LOT 5 — how structural claims are tested

## The rule that governs everything

**Pattern recognition is not predictive edge.** Every detection carries two
independent numbers:

| | Meaning | Range |
| --- | --- | --- |
| `recognition_confidence` | how cleanly the shape matches its definition | 0-100 |
| `edge_state` | whether that shape has been shown to precede anything | enum |

A double bottom at 91/100 with `NO_MEASURABLE_EDGE` is a coherent, common
result: we see it clearly and we cannot say what follows. The API returns both
on every pattern, and `test_every_pattern_carries_an_edge_state` fails the
build if one ever appears without the other.

## Detector reliability classes

Detection quality is declared up front rather than implied:

| Class | Meaning | Patterns |
| --- | --- | --- |
| DETERMINISTIC | geometry fully specified, no judgement | double top/bottom, triple top/bottom |
| HEURISTIC | specified, but thresholds are choices | head & shoulders, inverse H&S, triangles |
| HUMAN_LIKE | approximates what an analyst draws | (none yet) |
| EXPERIMENTAL | definition still too subjective to trust | wedges, flags |

Wedges and flags are EXPERIMENTAL because the same price action is drawn as a
wedge, a channel or a triangle by different analysts, and no threshold choice
here is defensible enough to call reliable. Eight solid definitions beat fifty
fragile ones.

## Causality

Every structure computed for time T uses only bars at or before T.

- **Swings** carry `pivot_time` AND `confirmation_time`. A pivot needs
  `lookback` further bars before it is knowable, so backtests filter on
  `confirmation_time`. Filtering on `pivot_time` imports five bars of future
  knowledge, silently.
- **Mutation tests** assert this directly: compute a structure, rewrite every
  bar after the cutoff by a factor of four, recompute, and require the earlier
  answer to be identical. Applied to swings, ranges, zones, market structure,
  patterns and location.
- **Caching is exact, not approximate.** Because a structure at bar i cannot
  change, a cached row is byte-identical to a fresh computation.
  `test_incremental_matches_full_recompute` verifies it.

## Zones, not levels

A support is a band, not a number. Zones are built by clustering confirmed
swings with an **ATR-scaled** tolerance, so "two comparable lows" means the
same structural thing on BTC at 90,000 and SOL at 95. A fixed percentage
tolerance is too wide for one and too narrow for the other.

Zone quality combines touch count, touch dispersion in ATR, median reaction
depth, close penetrations, age and recency.

## Baselines: the mistake that keeps recurring

This is the single most important methodological point in LOT 4 and LOT 5, and
it was made **twice** before being caught each time.

Testing a structural label against **zero** measures the market's upward
drift, not the label. Every bucket "works" in an asset that rose tenfold.

The obvious fix — comparing against "days in the same regime" — is **not a
fix** when implemented as `regimes.isin(regimes_where_the_event_occurs)`.
Structural labels occur in every regime, so that mask selects the entire
sample and the baseline is silently unconditional again. This produced 57 FDR
"survivors" on BTC before it was caught, and the giveaway was that the
`same_regime` and `same_regime_momentum` columns were numerically identical on
every single row.

The actual fix is **regime stratification**: compare inside each regime, then
weight those comparisons by how often the event appears there. On BTC range
bottoms this reversed the sign of the answer — 425 of 684 range-bottom events
occur in STRONGLY_BEARISH regimes, so the unconditional number was measuring
the regime, not the location.

## The filter chain

A structural label is admitted as an edge only if it clears every one of:

1. **FDR** — Benjamini-Hochberg at α=0.05 across the whole hypothesis family,
   with `expected_false_positives` always displayed.
2. **Effective sample ≥ 20** — `min(distinct episodes, n / horizon)`. Both
   corrections are needed: clustering alone ignores window overlap, overlap
   alone ignores repeated occurrences inside one episode.
3. **Effect size ≥ 0.50%** and **net of 0.20% friction**.
4. **Stability** — sign consistent in ≥70% of years. An effect confined to one
   era is UNSTABLE regardless of its p-value.
5. **Walk-forward** — chronological train/validation/OOS, with the
   out-of-sample split confirming sign and magnitude. Splits are never
   shuffled: a random split on overlapping forward returns leaks almost
   completely.

## Trader knowledge: three blocks, never merged

| Block | What it is | Can it override data? |
| --- | --- | --- |
| WHAT_TRADER_SAID | the claim, as made | never |
| WHAT_MARKET_DATA_SHOWED_AT_T | measurable at that instant | it IS the data |
| WHAT_HAPPENED_AFTER | the outcome | known only later |

Temporal alignment resolves to the **last CLOSED bar** before the analyst
spoke. A bar still forming was visible but its close did not exist.

Targets and invalidations are graded **only when the analyst actually stated
them**. Reconstructing a target afterwards grades an analysis against a goal
it never set.

## Source hierarchy

Tier 1 blockchain/protocol native · Tier 2 official API · Tier 3 specialist
provider · Tier 4 educational literature · Tier 5 human analysis · Tier 6
general media.

A source may override only a strictly higher tier number. Equal tiers
disagreeing is **reported, never resolved** — picking one arbitrarily hides
the conflict. Educational and human sources (4-6) can never override measured
data (1-3).

## Market episodes

Twenty videos about the same BTC range are one observation. When a range is
known it **is** the episode identity, with no time component: an earlier
version also bucketed time, and two analyses three days apart landed either
side of a boundary and counted as independent. Any bucket width has that edge.

Dropping time means the same price band revisited years later merges. That is
the safe direction: merging understates the effective sample, and every study
treats a smaller effective sample as less evidence, never more.
