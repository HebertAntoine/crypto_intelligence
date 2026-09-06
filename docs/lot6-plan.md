# LOT 6 — plan

**Nothing is implemented until this plan is agreed.** What follows is a
diagnostic based on inspection of the repository and live probing of every
candidate data source, then a proposal.

---

# Part 1 — Diagnostic

## 1.1 What the data actually contains

Measured, not assumed. Probed against the live APIs today.

| Family | Depth | Verdict |
| --- | --- | --- |
| Daily candles | 3306 bars (BTC/ETH, 9 y), 2216 (SOL) | usable |
| 4h candles | 6000 bars (2.8 y) | usable |
| 1h candles | 10000 bars (1.2 y) | thin |
| Funding | 7000 pts (6.4 y) | usable, already found INCONCLUSIVE |
| Open interest (Bybit) | 2223 pts (6 y) | usable |
| Macro (10 series) | 2514 pts (10 y) | usable, barely exploited |
| **ETF flows** | **344 rows since 2026-05-08** | **4 months — not studiable** |
| **DeFi TVL** | **248 rows since 2026-05-08** | **4 months** |
| **Long/short ratio** | **250 rows since 2026-09-02** | **4 days** |
| **BTC dominance** | **48 rows since 2026-09-04** | **2 days** |

The second half of that table is the important part. Several families the
project appears to "have" exist only as a live feed with no history. Any study
on them today would return INSUFFICIENT_DATA, and it would be dishonest to
present them as available.

## 1.2 What can actually be backfilled (probed live)

| Source | Depth obtained | Key needed |
| --- | --- | --- |
| **Deribit DVOL** (implied volatility) | **1993 pts → 2021-03-24 (5.5 y)**, BTC + ETH | no |
| **DefiLlama stablecoin supply** | **3204 pts → 2017-11-29 (8.8 y)** | no |
| **blockchain.info charts** (tx, hashrate, addresses) | **1815 pts (5 y)**, BTC only | no |
| Bybit account ratio (positioning) | 500 pts → 2025-04-25 (1.4 y) | no |
| Binance quarterly basis | 500 pts → 2025-04-24 (1.4 y) | no |
| Binance positioning / taker ratio | **31 days** | no |
| Liquidations | none | paid |

So of the families listed as candidates, **three have real depth and are
genuinely orthogonal**, two are too shallow to study honestly, and one remains
unavailable.

## 1.3 The methodological gap that matters more than any new data

The regime control is **coarse and lagging**, and I measured both.

`regime(t)` correlates with the past return over:

| window | BTC | ETH | SOL |
| --- | --- | --- | --- |
| 5 days | +0.35 | +0.34 | +0.36 |
| 20 days | +0.62 | +0.60 | +0.57 |
| **40-60 days** | **+0.73** | **+0.73** | **+0.58** |

The label is essentially a summary of the last two months, compressed into five
buckets. Stratifying on it therefore leaves substantial within-bucket
heterogeneity: two days in "STRONGLY_BULLISH" can be at completely different
points of completely different moves.

That is the real limit on every excess figure the project has produced. It is
not fixed by adding data.

### A hypothesis I tested and had to abandon

I suspected ETH `ABOVE_RANGE` (+4.04% at 7 days, the strongest surviving
result) was an artifact of breakouts occurring early in a regime episode, with
the lagging label not yet caught up. Measured:

- `ABOVE_RANGE` days sit at regime +1.58 versus a sample mean of −0.02, so the
  collinearity is real;
- median episode age 8 bars versus 4 for the whole sample, so breakouts *are*
  earlier in episodes;
- **but adding episode age to the stratification changes the excess from
  +4.79% to +4.64% at 7 days.** The confound does not explain the effect.

So my earlier caveat was wrong on its specific mechanism, and ABOVE_RANGE is
more durable than I claimed. It remains a single-asset result with an effective
sample near 35, which makes it the project's best **candidate** — not an
established edge.

## 1.4 Honest scoring of the gap to 7.5

| Capability | Now | Missing |
| --- | --- | --- |
| Confounder control | stratification on 5 coarse buckets | continuous residualisation; matched samples |
| Out-of-sample | chronological splits | **no purging or embargo** — train and test overlap by one horizon at the boundary |
| Statistical power | per-asset, effective_n 10-40 | pooling with date-clustered inference |
| Orthogonal families | price, funding, OI, structure | implied volatility, stablecoin liquidity, on-chain |
| Interactions | none | conditional and joint tests |
| Tradability | cost floor only | sizing, turnover, drawdown |

Points 2 and 3 are the ones that make current results fragile. Adding data
families to a framework that leaks at split boundaries and has 20 effective
observations produces more unreliable numbers, not fewer.

---

# Part 2 — Proposed LOT 6

**Theme: orthogonal information, and enough statistical power to judge it.**

Axis 1 is a prerequisite for Axis 2. Building Axis 2 first would repeat the
LOT 5 mistake at a larger scale.

---

## Axis 1 — Power and control (prerequisite, no new data)

### 1.1 Residualisation-based control

Replace "compare within a bucket" with "remove the confounder, then test the
residual".

Regress forward return on the continuous confounders — trailing returns at
several horizons, realised volatility, funding percentile, OI change — and test
whether the signal explains any of the **residual**. This uses the confounders
at full resolution instead of compressing them into five buckets, and does not
shrink the sample the way finer stratification would.

Stratification is kept and reported alongside. When the two disagree, that
disagreement is the finding.

### 1.2 Purged and embargoed walk-forward

With a 30-day horizon, the last 30 training bars have outcomes that fall inside
the test period. Current splits do not remove them. Fix: purge observations
whose forward window crosses the boundary, then embargo a further h bars.

**Expected consequence: some current out-of-sample confirmations will fail.**
That is the point of doing it.

### 1.3 Multi-asset pooling with date-clustered inference

Pool BTC/ETH/SOL with asset fixed effects. Naively this triples the sample —
but crypto assets correlate around 0.8, so three assets on the same day are
close to one observation. Inference therefore clusters on **date**, not on
asset, and the reported effective sample reflects that.

This is the honest way to address the effective_n 10-40 limitation. It will
raise power somewhat, not threefold, and the report must say so.

### 1.4 Baseline-safety regression tests

Direct guards against the LOT 5 bug, run in CI:

- a baseline mask covering more than 95% of the sample **fails the test**;
- `same_regime` and `same_regime_momentum` producing identical values on every
  row **fails the test** (this was the actual symptom);
- a synthetic signal with a known zero effect, injected into each study, must
  return no edge — a study that finds one is broken;
- a synthetic signal with a known +2% effect must be recovered — a study that
  misses it is underpowered, and the test reports the power.

---

## Axis 2 — New orthogonal families

Only families with genuine depth are included.

### 2.1 Implied volatility and the variance risk premium — **priority 1**

| | |
| --- | --- |
| **Economic hypothesis** | Options markets price expected volatility. The gap between implied (DVOL) and subsequent realised volatility is the premium paid for insurance. When that premium is extreme, it reflects positioning and fear that spot price does not show. This is information from a *different market*, not a transform of the price series. |
| **Data needed** | Deribit DVOL index, BTC and ETH, daily |
| **Real availability** | **1993 points back to 2021-03-24 (5.5 y)**, probed today, no key, public endpoint |
| **Leakage risk** | Low. DVOL is a published index with a timestamp. Realised volatility must be computed over a strictly *past* window; the variance premium at t compares DVOL(t) with realised vol over [t−30, t], never forward. |
| **Confounders** | Volatility regime (already measured), realised volatility level, regime, funding. DVOL is mechanically correlated with realised vol, so the *spread* is the signal, not the level. |
| **Baseline** | Same-regime **and** same-realised-volatility-decile, plus residualisation on realised vol. Without that control the test measures volatility clustering. |
| **Validation** | Full chain: FDR, effective_n, stability by year, purged walk-forward, pooled BTC+ETH with date clustering |
| **Expected sample** | ~2000 daily obs per asset → effective_n ≈ 66 at 30 d, ≈ 280 at 7 d. **The best-powered new family available.** |
| **Compute cost** | Low. Two backfills, vectorised features. |
| **Potential value** | Highest. No existing family carries options-market information. SOL has no DVOL, so the study covers BTC and ETH only — stated up front. |

### 2.2 Stablecoin liquidity — **priority 2**

| | |
| --- | --- |
| **Economic hypothesis** | Stablecoin supply is the dry powder available to buy crypto. Net issuance is capital entering the system; contraction is capital leaving. This is a flow variable, structurally different from price, funding or positioning. |
| **Data needed** | DefiLlama aggregate stablecoin market cap, daily |
| **Real availability** | **3204 points back to 2017-11-29 (8.8 y)**, probed today, no key |
| **Leakage risk** | **Moderate and must be handled.** DefiLlama revises historical values as it adds chains and tokens. The series available today is **not** the series that was visible in 2019. Treat as `NOT_POINT_IN_TIME` unless a vintage can be reconstructed; otherwise restrict conclusions to the period since we began storing it, and label the rest RECONSTRUCTED. |
| **Confounders** | Stablecoin supply grows with the whole market, so it is strongly trending. Must be used as a *change* or a trailing percentile, never a level. Regime, and the 2020-21 growth era, dominate the raw series. |
| **Baseline** | Same-regime, residualised on trailing market return. Crucially: **the series is market-wide**, so testing it on three assets does **not** give three independent samples. Effective_n is governed by the single series. |
| **Validation** | Full chain, plus an explicit point-in-time audit before any conclusion |
| **Expected sample** | ~3200 obs but **one** series → effective_n ≈ 106 at 30 d regardless of how many assets are tested. Must not be inflated by asset count. |
| **Compute cost** | Very low |
| **Potential value** | High if the revision problem can be bounded; the hypothesis is economically clean and the depth is the best available. |

### 2.3 On-chain network activity — **priority 3**

| | |
| --- | --- |
| **Economic hypothesis** | Transaction count, active addresses and hashrate measure actual network use and producer commitment, independent of the price at which coins change hands. |
| **Data needed** | blockchain.info charts: `n-transactions`, `n-unique-addresses`, `hash-rate` |
| **Real availability** | **1815 points (5 y)**, probed today, no key. **BTC only** — ETH and SOL would need separate sources and are out of scope for this lot. |
| **Leakage risk** | Low for hashrate and transaction count. Active addresses is a heuristic that changes definition over time; flag it. |
| **Confounders** | All three trend with adoption and with price itself. Activity rises *because* price rose. Must be detrended (trailing percentile or change) and residualised on past return, otherwise the study measures price with extra steps. |
| **Baseline** | Same-regime, residualised on trailing 30/60-day return |
| **Validation** | Full chain. Single asset, so no pooling. |
| **Expected sample** | ~1800 obs, one asset → effective_n ≈ 60 at 30 d |
| **Compute cost** | Low |
| **Potential value** | Moderate. The confounding with price is severe and may well leave nothing after control — which is a legitimate outcome. |

---

## Axis 3 — Declared insufficient, not tested as if viable

Documented in the report so their absence is visible rather than silently
skipped:

| Family | Depth | Declared |
| --- | --- | --- |
| Positioning (long/short, taker ratio) | 1.4 y best case (Bybit); 31 days on Binance | **INSUFFICIENT_DATA** — effective_n ≈ 17 at 30 d. Backfill and store now so a future lot can study it. |
| Basis / term structure | 1.4 y | **INSUFFICIENT_DATA** — same. Store now. |
| Liquidations | none free | **UNAVAILABLE** — unchanged since LOT 4 |
| ETF flows, DeFi TVL, dominance | 2 days to 4 months stored | **INSUFFICIENT_DATA** — the scheduler should be storing these; a lot from now they become studiable |

Storing them now is the point: depth is only obtainable by waiting, and waiting
only helps if collection has started.

---

## Axis 4 — Interactions (conditional on Axis 2 results)

Run **only** between families that individually clear the power threshold, and
with the hypothesis count declared in advance. Testing every pair of every
family is how a project manufactures findings.

Planned pairs, chosen because each has a stated mechanism:

1. Variance premium × crowding — is an extreme premium more informative when
   leverage is stretched?
2. Stablecoin issuance × regime — does capital inflow matter more in a
   drawdown?
3. Structure (ABOVE_RANGE) × variance premium — does the ETH breakout result
   survive when options positioning is controlled for?

Three hypotheses, declared here, corrected together with everything else.

---

# Part 3 — Verdict definitions

Fixed before any result is seen.

| Verdict | Requirements |
| --- | --- |
| **SUPPORTED** | survives FDR across the whole lot; effective_n ≥ 30; excess ≥ 0.5% and net of 0.20% friction; sign consistent in ≥ 70% of years; confirmed in **purged** out-of-sample; **and** survives residualisation as well as stratification |
| **INCONCLUSIVE** | statistically distinguishable but fails one of: effective sample, effect size, stability, or the two control methods disagree |
| **FAILED** | effect is absent, or its sign is opposite to the stated hypothesis, on an adequately powered sample |
| **INSUFFICIENT_DATA** | effective_n < 30, or the point-in-time status of the input is not established. **Never** convertible into any other verdict by adding assets or horizons. |

Two additions to LOT 5's rules:

- a result must survive **both** stratification and residualisation. Passing one
  and failing the other is INCONCLUSIVE, not SUPPORTED;
- the **power** of each test is reported alongside its p-value, so a FAILED
  verdict can be distinguished from an underpowered one.

---

# Part 4 — Expected outcome, stated in advance

So the result cannot be judged against a moving target:

- 3 new families × ~4 feature definitions × 5 horizons ≈ **60 primary
  hypotheses**, plus 3 declared interactions;
- at α=0.05 with FDR, roughly **3 false positives expected**;
- realistic expectation: **0 to 3 families produce a SUPPORTED result**;
- the most likely single outcome is that the variance risk premium survives on
  BTC and ETH and the other two do not;
- **an outcome of zero SUPPORTED is a valid result** and will be reported as
  such. It would still move the project forward, because Axis 1 makes every
  future result more trustworthy and Axis 3 starts the clock on data that
  cannot be obtained retroactively.

Regarding the score: Axis 1 alone is worth more than Axis 2, because it changes
the reliability of everything already measured and everything measured later.
If Axis 2 finds nothing and Axis 1 lands, the project has still improved.

---

# Part 5 — What this lot deliberately does not do

- No new indicators derived from price. That well is dry and LOT 5 measured it.
- No lowering of a threshold because a result disappeared.
- No conversion of INSUFFICIENT_DATA into a conclusion by pooling assets that
  share one underlying series.
- No machine learning. The dataset is being prepared for it; a model on 60
  effective observations would fit noise.
- No re-tuning of LOT 5 detectors to recover the SOL breakout result.
