# LOT 6A audit, before LOT 6B

Verified against the repository, not against the previous reports.

## State

624 backend tests pass, 32 Flutter tests, ruff clean, both frontends build.
DVOL holds 1993 points per asset for BTC and ETH since 2021-03-24; SOL has
none and no proxy exists.

## Component status

| Component | Status | Detail |
| --- | --- | --- |
| Purged splits | **COMPLETE** | `purge_train_mask` + `purged_walk_forward_folds`, used by `revalidation` and `dvol_study` |
| Embargo | **COMPLETE** | defaults to one horizon, `verify_embargo` checks the target's autocorrelation at that lag |
| Residualisation | **COMPLETE** | train-only fit, test residuals, guarded by a CI test that fails if the order is reversed |
| Stratification | **COMPLETE** | regime-matched, with the >95% baseline-coverage guard |
| effective_n | **COMPLETE** | min(clusters, independent blocks); the variance adjustment is reported but does not bind |
| MDE / power | **PARTIAL** | MDE and power are computed, but nothing answers "how many more independent observations are needed" |
| DVOL | **COMPLETE** | ingested and studied, 24 pre-registered hypotheses |
| **Pooling** | **BUGGED IN PRACTICE** | `pooled_effect` exists with date-block clustering and per-asset heterogeneity, and is **never called outside the test suite**. The BTC+ETH pooling that LOT 6B calls priority 1 has never actually run. |
| **`structural_research::_walk_forward`** | **BUGGED** | still the original implementation: `first_cut` is both the last training bar and the first validation bar, and no purge. Never migrated to `purged_walk_forward_folds`. Every out-of-sample figure that module produces is affected. |
| Candidate registry | **MISSING** | candidates live as a literal list in `revalidation.py`, with no version, no status lifecycle, and nothing preventing a tested hypothesis from being edited |
| Preregistration | **PARTIAL** | hypotheses are declared in module source before running, which is honest but not enforced or versioned |
| Research snapshots | **PARTIAL** | outputs are written to `data/research/*.json` with a timestamp; no code, config or data hash |
| Baselines | **COMPLETE** | `baselines.py`, including the random baseline that beats buy-and-hold |
| Shadow / live | **PARTIAL** | recorders work; 3 directional and 1 structural snapshot, so nothing is evaluable |
| Point-in-time | **COMPLETE** | `FeatureRegistry` declares availability, mutation tests assert it |
| Data provenance | **COMPLETE** in the app (`DataProvenance`, staleness banner); **PARTIAL** in the API, which does not label snapshot age |

## Missing for LOT 6B

`hypothesis_registry` · `event_sampler` · `panel` · `cycles` · `redundancy` ·
`ablation` · `evidence`. None exist.

## What this changes about the LOT 6A conclusions

The revalidation and DVOL results stand: they used purged folds and
residualisation correctly. But **the pooled BTC+ETH question was never
answered** — the machinery was built and left unused. That is LOT 6B's first
task, and it is the only route to raising effective_n without waiting for time
to pass.
