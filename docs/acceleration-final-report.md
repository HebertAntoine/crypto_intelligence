# Acceleration report

## 1. State found at start

The starting assumption ("LOT 4 finished, ~436 tests") was out of date. The
repository showed **LOT 5 complete** with 504 tests, plus six further commits
adding a Flutter client and a Vercel deployment. Full inventory in
[project_state_recovery.md](project_state_recovery.md).

## 2. Last LOT actually finished

**LOT 5** — Pattern Intelligence & Trader Knowledge. **LOT 6A** was planned in
detail and had zero lines implemented.

## 3. Incomplete features found

Multi-timeframe synthesis (per-timeframe readings existed, no alignment
verdict) · EntryOpportunity at 5 of ~17 planned inputs · analog engine still a
plain feature-distance search · human example dataset empty · live shadow at 3
snapshots · DVOL, stablecoins and on-chain all verified obtainable and none
ingested · **the entire LOT 6A statistical layer**.

## 4-5. Bugs found and fixed

| # | Bug | Severity | Status |
| --- | --- | --- | --- |
| 1 | **The Flutter app is broken on `main`.** Commit `decd4a7` deleted `knowledge_screen.dart` but left the import and usage in `main.dart`. The app could not compile, so the Vercel build would fail. | blocking | fixed — screen rebuilt in the current `mobile_kit` style |
| 2 | **Frozen data presented as today's.** `client.dart::_get` returned bundled snapshots in the same shape as live responses; the UI could not tell them apart and never showed the age. On Vercel the app would display 2026-09-06 data as "Today" indefinitely. | high | fixed — `DataProvenance` on every response, staleness banner, 5 tests |
| 3 | Walk-forward splits shared their boundary bar and kept training rows whose targets reached into the test window. Measured on real BTC data: **8 / 15 / 31 leaking rows at H = 7 / 14 / 30**, i.e. 0.48% / 0.91% / 1.89% of the training set, plus 1 shared bar. | high | fixed — purge + embargo |
| 4 | `chronological_split` takes no horizon, so no caller could be protected. | high | superseded by `purged_walk_forward_folds` |
| 5 | **My own bug.** The first revalidation harness passed `n_blocks = len(folds) * 4`, a constant. It became the binding `effective_n` for 9 of 10 candidates regardless of their event counts, and would have reported all ten as INSUFFICIENT_DATA for a reason that was an artifact. | high | fixed — `count_independent_blocks` measures it; regression test added |
| 6 | **My own bug.** The effective-sample estimator counted "runs separated by more than the horizon" alongside `n/horizon` and the block count. All three measure the same overlap, so the minimum collapsed to 1 for any regularly recurring event — marking nearly every study INSUFFICIENT_DATA through an estimator artifact. | high | fixed — redefined as min(clusters, blocks); variance adjustment demoted to informational |
| 7 | Daily report called `HistoricalSimilarityEngine.analyze()` with the wrong arity and used a non-existent `upcoming_events`. | low | fixed |
| 8 | Two test-design flaws of my own: a synthetic "no true effect" dataset that contained a real effect, and a pooling comparison against the t-statistic of a different quantity. | medium | fixed |

An earlier estimate in the LOT 6A plan put the split leak at "roughly 3.6%".
The measured figure is 0.48-1.89% of the training set. The correction is right
on principle regardless of size, but the measured number is what is reported.

## 6. Data depth by family

| Family | Depth | Status |
| --- | --- | --- |
| Candles 1d | 3306 bars (9 y) | HISTORICAL_READY |
| Candles 4h | 6000 (2.8 y) | HISTORICAL_READY |
| Candles 1h | 10000 (1.2 y) | LIMITED_HISTORY |
| Candles 15m | 12000 (4 mo) | LIMITED_HISTORY |
| Funding | 7000 (6.4 y) | HISTORICAL_READY |
| Open interest (Bybit) | 2223 (6 y) | HISTORICAL_READY |
| Macro (10 series) | 2514 (10 y) | HISTORICAL_READY |
| **DVOL (new)** | **1993 (5.5 y), BTC + ETH** | **HISTORICAL_READY** |
| ETF flows | 344 rows (4 mo) | LIVE_ONLY |
| DeFi TVL | 248 (4 mo) | LIVE_ONLY |
| Long/short ratio | 250 (4 days) | LIVE_ONLY |
| BTC dominance | 48 (2 days) | LIVE_ONLY |
| Stablecoins | 8.8 y obtainable, not ingested | NOT_POINT_IN_TIME (revisions) |
| On-chain BTC | 5 y obtainable, not ingested | HISTORICAL_READY when ingested |
| Liquidations | none | UNAVAILABLE |
| DVOL for SOL | none | UNAVAILABLE — not substituted |

## 7-12. What was built

**Statistical layer (LOT 6A)** — `research/inference.py`: purge/embargo with a
verified formula, train-only residualisation, pooled effects with date-block
clustering, `effective_sample_v2`, and the baseline-coverage guard.
`research/power.py`: minimum detectable effect, power, and verdict rules that
require **both** control methods.

**Engines** — `engines/multi_timeframe.py` (five timeframes, alignment,
explicit conflicts), `engines/implied_volatility.py` (DVOL, variance risk
premium), `engines/daily_report.py` (sixteen sections plus a contradiction
detector).

**Providers** — `providers/volatility/deribit.py`, paginating back to
2021-03-24.

**Research** — `research/revalidation.py` (ten pre-registered candidates),
`research/dvol_study.py` (24 pre-registered hypotheses).

## 13. Marginal validation — the decisive result

The ten LOT 4/5 survivors, re-tested under purged folds with both control
methods:

| Verdict | Count |
| --- | --- |
| SUPPORTED | **0** |
| INCONCLUSIVE | 7 |
| INSUFFICIENT_DATA | 3 |

**Every candidate fails the same way.** Stratification on the regime gives
p = 0.0000 to 0.0152; residualisation on continuous controls gives
p = 0.13 to 0.90. Not one falls below 0.05 under the second method.

| Candidate | Stratified | Residualised | eff_n | MDE |
| --- | --- | --- | --- | --- |
| ETH ABOVE_RANGE 7d | +4.04% (p<0.0001) | +1.78% (p=0.85) | 52 | 5.30% |
| ETH ABOVE_RANGE 14d | +5.55% (p<0.0001) | +3.21% (p=0.44) | 52 | 7.90% |
| BTC double_top 7d | −1.14% (p=0.015) | −0.67% (p=0.13) | 47 | 4.31% |
| BTC MID_RANGE 30d | −4.35% (p<0.0001) | −5.02% (p=0.90) | 72 | 8.34% |
| BTC RANGE_STRUCTURE 30d | −3.78% (p<0.0001) | −4.23% (p=0.33) | 63 | 8.92% |
| ETH MID_RANGE 7d | −1.60% (p=0.005) | −1.79% (p=0.37) | 121 | 3.48% |
| ETH TRANSITION 7d | −1.23% (p=0.006) | −1.93% (p=0.84) | 62 | 4.86% |

The interpretation: the LOT 5 effects were largely carried by the continuous
momentum and volatility information that a five-bucket regime label does not
capture. Once lagged returns at 1/5/20/60 days, realised volatility at two
windows, distance to the 200 EMA and ADX are removed on a training fold and
the residual tested out of sample, the effects do not survive.

**Every one of the ten is also UNDERPOWERED**: minimum detectable effects of
3.5% to 9.2% against meaningful thresholds of 0.7% to 2.0%. Even the survivors
of the sample-size filter could not have detected an effect worth having.

## 14-16. GoodCrypto, Lexa, human dataset

Unchanged from LOT 5 and still correct: 19 concepts and 38 claims ingested as
paraphrases with provenance, the bilingual transcript parser and temporal
alignment work, and the human example dataset remains **empty**, so every
human-vs-algorithm study returns INSUFFICIENT_DATA. No gold dataset was built
this session; that requires the user's own material.

## 17-18. Live shadow and track record

3 directional snapshots, 1 structural. Unchanged — only elapsed time fixes
this, and only if the scheduler runs. Track record correctly reports
TOO_EARLY.

## 19. DVOL

Ingested (1993 points, 2021-03-24 onward, BTC and ETH; SOL UNAVAILABLE and not
substituted). Current reading: implied volatility sits **8.4 points below**
30-day realised on BTC and **21.5 below** on ETH, a premium at the **8th
percentile** of its own history — options are pricing volatility cheaply
relative to what has occurred.

24 pre-registered hypotheses tested:

| Verdict | Count |
| --- | --- |
| SUPPORTED | **0** |
| INCONCLUSIVE | 3 |
| INSUFFICIENT_DATA | 21 |

11 raw significant, 10 survive FDR, 1.2 false positives expected. The most
promising is **ETH "options expensive" at 30 days: −10.16% stratified
(p<0.0001), −11.14% residualised (p=0.025), matching hypothesis H1** — and it
fails on effective_n = 18. It is the single most interesting candidate the
project now has, and it is not established.

## 20-21. Stablecoins and on-chain

Not ingested this session. Both verified obtainable (8.8 y and 5 y). The
statistical layer took priority, and the revalidation result justifies that
ordering: adding families to the previous framework would have produced more
effects that dissolve under residualisation.

## 22-23. Frontend

Flutter app repaired and building. Knowledge screen rebuilt. Provenance banner
added. React frontend still builds. Both typecheck clean.

## 24. Daily report V2

Sixteen sections in reading order, with MEASURED EDGE placed immediately after
ENTRY OPPORTUNITY, an UNAVAILABLE line with a reason wherever data is missing,
and a **contradiction detector** that fires when the daily regime and the
weekly structure disagree — as they currently do on BTC.

## 25-26. Research findings, including negative ones

- **0 SUPPORTED out of 34 pre-registered tests** (10 revalidations + 24 DVOL).
- Every LOT 5 structural effect dissolves under continuous residualisation.
- Every test in both studies is underpowered against a meaningful effect.
- The variance risk premium on ETH is the best remaining candidate and is not
  established.
- The regime label correlates **+0.73 with the past 40-60 day return** and only
  +0.35 with the past 5 days: it is a lagging two-month summary, which is
  precisely why residualising on continuous returns changes the answers.
- A hypothesis I tested and abandoned: ETH ABOVE_RANGE was **not** explained by
  regime-episode age (+4.79% → +4.64% when controlled). My earlier caveat was
  wrong about its mechanism; residualisation is what removes it.

## 27. Effective samples

Every result now reports `clusters`, `independent_blocks` and a variance
adjustment, with the minimum binding. Real values range from 18 to 121 — far
below what the raw counts of 51 to 1374 suggest.

## 28. ML readiness

Dataset infrastructure exists (`FeatureRegistry`, 16 declared features, all
point-in-time, mutation-tested). **No challenger was run**, correctly: with
effective samples of 18-121 and every test underpowered, a model would fit
noise. The precondition stated in the plan is not met.

## 30. Tests

| Suite | Count |
| --- | --- |
| Backend | **575 passed, 6 skipped** (was 504) |
| Flutter | **26 passed** (was 19) |
| LOT 6A guards | 29, including the five requested families plus two for my own estimator bugs |

Ruff clean. React build clean. Flutter analyze, test and web build clean. CLI
and API smoke-tested.

## 31. Limitations

The human dataset is empty. Live track record has 3 snapshots. Stablecoins and
on-chain are unexploited. SOL has no implied-volatility source. Liquidations
remain unavailable. Every current study is underpowered — that is the binding
constraint, not the absence of ideas.

## 32. Next highest-value tasks

1. **Nothing that adds hypotheses.** The framework now says clearly that the
   samples cannot support them.
2. **Pooling across BTC and ETH for DVOL** — implemented but not yet applied;
   it is the only route to raising effective_n without waiting.
3. **Stablecoin and on-chain ingestion**, with their point-in-time limits
   documented up front.
4. **Let the scheduler run.** ETF flows, dominance, positioning and the live
   track record can only be obtained by waiting, and waiting only helps if
   collection is running.
