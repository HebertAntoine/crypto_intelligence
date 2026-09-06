# LOT 5 — audit before modification

| Component | Location | Verdict | Why |
| --- | --- | --- | --- |
| `find_swings` | `engines/technical/structure.py` | **REUSE + EXTEND** | Already causal: excludes bars within `lookback` of the end, so an unconfirmed pivot is never emitted. Missing explicit `pivot_time` vs `confirmation_time` (§13). |
| `classify_structure` | same | **EXTEND** | Produces HH/HL/LH/LL and returns UNDETERMINED honestly. Needs `last_confirmed_*` exposure and BOS/CHOCH as descriptions. |
| `determine_trend` | same | **REUSE** | ADX-gated so a drifting range is not called a trend. Sound. |
| `cluster_levels` / `build_levels` | `engines/technical/levels.py` | **REPLACE** | Uses a fixed `tolerance_pct=0.6`, which is not comparable across assets or volatility regimes, and returns exact prices where zones are required (§11). |
| `Level` model | `core/models.py` | **EXTEND** | Single `price` float. Needs a zone (low/high) and quality components. |
| 8 pattern detectors | `patterns/detectors.py` | **EXTEND** | Work and are registered, but use fixed percentage tolerances and lack CANDIDATE/CONFIRMED/FAILED lifecycle. Kept as the LOT 4 baseline for replication (§45). |
| `PatternMatch` | `core/models.py` | **EXTEND** | Has confidence and confirmation state; needs recognition-vs-edge separation (§20) and zone levels. |
| `BreakoutQualityEngine` | `engines/breakout.py` | **EXTEND** | Six states and a 0-100 conviction score already. Needs retest depth, time outside, deviation linkage (§16, §17). |
| `HistoricalSimilarityEngine` | `engines/historical.py` | **EXTEND** | Feature matrix + forward returns exist. Needs effective-sample reporting and same-regime excess (§31). |
| `EntryTimingEngine` | `engines/entry_timing.py` | **EXTEND, no weight change** | Weighted factors with a documented cap fix. Structural features enter as CANDIDATES only (§33). |
| Knowledge / RAG | `knowledge/*` | **REUSE** | Ingest, FTS5, embeddings, hybrid retrieval with RRF all work. Trader and educational sources plug in as new document categories. |
| `FeatureRegistry` | `research/registry.py` | **EXTEND** | Point-in-time declarations, definition hashes, mutation-tested. Add structural features here (§57). |
| `ShadowModel` / `SignalDriftEngine` | `research/drift.py` | **EXTEND** | Records and resolves without acting. Extend the record to carry structure/pattern fields (§48). |
| `EdgeEngine` | `engines/edge.py` | **REUSE as the pattern** | Its filter chain (FDR → effective n → effect size → cost → stability) is exactly what `PatternEdgeState` needs (§30). |
| `pattern_validation` | `research/pattern_validation.py` | **EXTEND** | Already does same-regime baselines, FDR, episode clustering and per-year stability. Add walk-forward and richer baselines (§25, §28, §46). |
| `benjamini_hochberg`, `describe_returns`, `forward_returns`, `decompose_ic` | `research/stats.py` | **REUSE** | Correct and already used throughout. |
| `LeverageCrowdingEngine`, `VolatilityRegimeEngine`, `CrossAssetAnalyzer` | `engines/` | **REUSE** | Provide the conditioning variables the marginal-value study needs (§66). |
| Alerts | `engines/alerts.py` | **EXTEND** | Cooldown/dedup and state-change machinery in place; add structural alerts (§50). |

**DEPRECATE: none.** No component was found to be wrong enough to remove. The
only replacement is level clustering, whose fixed-percentage tolerance is
superseded by ATR-normalised zones — the old function stays available so the
LOT 4 replication study (§45) can run against the original definition.
