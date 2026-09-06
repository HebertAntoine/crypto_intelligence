# LOT 5 — final report

504 tests pass, 6 skipped. Ruff clean on backend and tests. Frontend builds and
typechecks. CLI and API smoke-tested.

---

## 1. Audit: REUSE / EXTEND / REPLACE / DEPRECATE

Full table in [lot5-audit.md](lot5-audit.md). Summary:

- **REUSE** — `find_swings` (already causal), the whole knowledge/RAG stack,
  `benjamini_hochberg` and the stats helpers, `EdgeEngine`'s filter chain as
  the template for `PatternEdgeState`, `LeverageCrowdingEngine`,
  `VolatilityRegimeEngine`.
- **EXTEND** — `classify_structure` (added `last_confirmed_*`, BOS/CHOCH),
  `BreakoutQualityEngine`, `FeatureRegistry` (+4 structural features),
  `ShadowModel`, `pattern_validation`, alerts, `EntryTimingEngine` (candidates
  only, no weight changed).
- **REPLACE** — `cluster_levels`: its fixed `tolerance_pct=0.6` is not
  comparable across assets. Superseded by ATR-scaled zones. The original stays
  available so the LOT 4 replication runs against the original definition.
- **DEPRECATE** — none.

## 2. What was built

**`structure/`** — `swings.py` (causal pivots with `confirmation_time`),
`zones.py` (ATR-scaled bands with quality scoring), `ranges.py`,
`location.py`, `market_structure.py`, `patterns.py` (9 detectors),
`cache.py`.

**`trader_knowledge/`** — `models.py`, `educational.py` (19 concepts, 38
claims), `transcript.py` (bilingual parser), `alignment.py`, `dataset.py`.

**`research/`** — `structural_research.py`, `marginal_value.py`,
`replication.py`, `claim_validation.py`, `structural_shadow.py`,
`export_lot5.py`. **`core/sources.py`** — the tier hierarchy.

**Surface** — 12 API endpoints, 9 CLI commands, 2 frontend pages plus the
Today structure block.

## 3. Bugs found and fixed

1. **Overlapping range zones.** The detector accepted a "0.4 ATR wide range"
   whose boundaries crossed (SOL: 73.39-76.70 and 75.00-78.88) and reported a
   position of 14.06. Fixed with a minimum 2-ATR separation and
   non-overlap requirement.
2. **Touch counting counted bars, not events.** 120 "top touches" in 193 bars
   simply meant price spent its time up there. Fixed to count entries into the
   zone.
3. **Stale ranges reported as current.** A range price abandoned 17 bars ago
   was still being described. Now invalidated after 10 bars outside.
4. **The baseline bug, twice.** `regimes.isin(regimes_where_the_event_occurs)`
   selects the entire sample when an event occurs in every regime — so the
   "same-regime" baseline was silently unconditional. Present in
   `marginal_value`, `structural_research` AND `claim_validation`. The
   giveaway was that the `same_regime` and `same_regime_momentum` columns were
   numerically identical on every row. Fixed with regime stratification in all
   three. **This changed every headline number in the lot.**
5. **Stability annotated but not gated** in claim validation — an effect
   confined to one era could be reported SUPPORTED. Now gates the verdict:
   10 SUPPORTED became 2.
6. **Episode key was a constant.** `round(midpoint / (midpoint * 0.02))`
   simplifies to 50 for every input, so the range component distinguished
   nothing. Fixed with logarithmic bucketing, and the time component removed
   entirely (any bucket width splits two analyses that straddle its edge).
7. **Transcript parser reassigned prices by max/min**, overriding which term
   each number was attached to. Fixed with proximity-based attachment.
8. **`app.css` never imported** (carried over from LOT 4) — every LOT 4 style
   was inert. Found because the CSS bundle hash did not change between builds.
9. **pyarrow missing**, so the cache silently failed to write and every
   parquet export fell back. Installed, with a pickle fallback added.

## 4. Pattern library

| Class | Patterns | Why |
| --- | --- | --- |
| DETERMINISTIC | double top/bottom, triple top/bottom | geometry fully specified |
| HEURISTIC | H&S, inverse H&S, ascending/descending/symmetrical triangle | specified, thresholds are choices |
| EXPERIMENTAL | rising/falling wedge, bull/bear flag | the same price action is drawn three different ways by three analysts |

Nine detectors, not fifty. Wedges and flags ship as EXPERIMENTAL rather than
being presented as reliable.

## 5. LOT 4 replication (§45)

Detectors were written from their definitions and **not adjusted** to
reproduce LOT 4.

| Finding | LOT 4 | LOT 5 | Verdict |
| --- | --- | --- | --- |
| BTC double_top @14d | −3.18%, eff_n 21 | −2.59%, eff_n **43**, p=1.9e-7 | **REPLICATED** (81% of magnitude, double the effective sample) |
| BTC inverse H&S @14d | −3.44%, eff_n 11 | −4.38%, eff_n 13, p=1.6e-6 | **REPLICATED** — still contradicts the textbook bullish reading |
| SOL breakout @7d | +3.99% | detector never fires | **DISAPPEARED** — the LOT 5 library has no `breakout` pattern; breakouts are handled by `BreakoutQualityEngine`. A definitional gap, not a refutation. |

One caveat the larger sample exposes: double_top's year-by-year sign
consistency falls from 6/7 (LOT 4) to 5/9. The effect size replicates; the
stability claim weakens.

## 6. Educational claims (§24)

36 testable claim-asset pairs, FDR across all 108 hypotheses.

| Verdict | Count |
| --- | --- |
| NOT_SUPPORTED | 33 |
| SUPPORTED | 2 |
| CONTRADICTED | 1 |
| UNTESTABLE (no detector) | 9 |

- **SUPPORTED**: ETH rising_wedge (−3.18% @14d) and ETH falling_wedge
  (+1.55% @14d). Both rest on **EXPERIMENTAL** detectors, so the detection
  itself is unreliable — weak support at best.
- **CONTRADICTED**: BTC triple_bottom. Claimed bullish; measured −2.49% @14d
  against a regime-matched baseline.

Before the baseline and stability fixes this read 10 SUPPORTED. The corrected
number is 2.

## 7. Structural research results

Regime-stratified, FDR across the whole family, then effective sample, effect
size, friction, year stability and walk-forward.

| Asset | Hypotheses | Raw p<0.05 | Survive FDR | Expected false positives | **Pass every filter** |
| --- | --- | --- | --- | --- | --- |
| BTC | 170 | 71 | 53 | 8.5 | **3** |
| ETH | 170 | 52 | 34 | 8.5 | **5** |
| SOL | 165 | 57 | 44 | 8.2 | **0** |

The eight survivors:

| Asset | Label | Horizon | Excess vs regime-matched |
| --- | --- | --- | --- |
| BTC | MID_RANGE | 30d | −4.35% |
| BTC | RANGE_STRUCTURE | 30d | −3.78% |
| BTC | double_top CONFIRMED | 7d | −1.14% |
| ETH | ABOVE_RANGE | 3/7/14d | +1.60 / +4.04 / +5.55% |
| ETH | MID_RANGE | 7/14d | −1.60 / −3.55% |
| ETH | TRANSITION | 7d | −1.23% |
| ETH | double_top FAILED | 3d | +2.76% |
| ETH | rising_wedge | 7/14d | −2.13 / −3.18% |

**Caveats that matter.** ETH `ABOVE_RANGE` is the strongest result in the
project, and it is also the most suspect: "price just broke above its range"
is momentum, and the regime label is derived from lagging EMA/ADX, so a fresh
breakout sits ahead of its own regime classification. The control may not
fully remove what it is meant to remove. BTC MID_RANGE and RANGE_STRUCTURE
survive only at 30 days with effective samples of 22-23, barely over the
threshold.

## 8. Performance (§56)

Bar-by-bar replay of nine years across every detector takes ~490s per full
research run. The cache makes interactive use viable: **×680 speedup** on a
warm cache, and incremental updates are byte-identical to a full recompute
(asserted by test). Invalidated by detector version, feature version or config
change.

## 9. Tests

| Suite | Count |
| --- | --- |
| Total | **504 passed, 6 skipped** |
| LOT 5 causality/mutation/robustness | 31 |
| LOT 5 trader knowledge | 22 |
| LOT 5 API | 15 |

Mutation tests rewrite every bar after a cutoff by ×4 and require the earlier
answer to be identical — applied to swings, zones, ranges, market structure,
patterns and location. All pass.

## 10. Limitations

- **Human example dataset is empty.** Every human-vs-algorithm study returns
  INSUFFICIENT_DATA. The pipeline, parser, alignment, correction versioning
  and quality dashboard all work; they have nothing to chew on yet. Target
  remains 50-100 well-aligned examples.
- **Layer D (human annotations) untested** for the same reason.
- **Live structural track record has 3 snapshots.** Weeks of scheduler uptime
  are needed before any LIVE_CONFIRMS / LIVE_CONTRADICTS verdict.
- **4h and 15m timeframes not exhaustively studied** — a full 4h replay is
  ~19k bars per asset and was cut for compute. D1 is complete.
- **Effective samples remain small.** Most families sit at 10-40 independent
  observations, not the hundreds the raw counts suggest.
- **`code_version` is "unknown"** — the repository still has no commits.
- **BOS/CHOCH are implemented as descriptions only** and have not been tested
  for predictive content.
