# LOT 6B — What the data already held can and cannot support

Run of 2026-09-07. Code `ee55c1470811c5af` over 42 research modules, git
`5e0878b`. numpy 2.5.2, pandas 3.0.5, scipy 1.18.1, scikit-learn 1.9.0.
Daily candles: BTC and ETH 3306 rows from 2017-08-17, SOL 2216 from 2020-08-11,
all to 2026-09-04.

**Verdict: NO_SIGNAL_SUPPORTED.** Twelve pre-registered pooled hypotheses, zero
survivors. The highest rung any claim reached is 4 of 7.

That was a possible outcome of this lot and it is the one that occurred. What
follows is mostly an account of *why* — and the most important finding is not
about the market at all.

---

## 1. The headline: the pipeline cannot see what it is looking for

Before trusting any negative result, the machinery producing it was tested
against known answers.

**Negative controls passed.** Two hundred random signals produced findings at
5.5%, and two hundred time-shuffled versions of a real signal at 4.0%, both
inside the 9.0% binomial tolerance. The stratified test does not manufacture
results from noise, and it responds to *when* a signal fires rather than to how
often. Every positive result this system has ever produced is worth that much.

**The positive control failed, and that is the finding.** An effect of known
size was inserted into the data and the pipeline was asked to recover it:

| Horizon | Empirical detection floor | Analytic MDE | Declared meaningful effect |
| --- | --- | --- | --- |
| 7 d | **3.0 %** | 3.25 % | 1.0 % |
| 14 d | **4.0 %** | 6.75 % | 1.5 % |
| 30 d | **8.0 %** | 15.37 % | 2.0 % |

At 30 days a planted 5% effect was recovered in magnitude (5.27% measured,
5.74% after residualisation) and still failed the significance bar. The
empirical floor and the analytic minimum detectable effect agree closely at 7
days — 3.0% against 3.25% — which is a genuine cross-check: two independent
methods, one simulated and one closed-form, converge on the same number.

**The consequence is severe and applies retroactively.** The system's declared
threshold for a meaningful effect is 1–2%. Its detection floor is 3–8%. Every
"no measurable edge" this project has ever reported is silent in exactly that
band. Those verdicts were never evidence of absence for effects of the size
worth having; they were the pipeline saying it could not see.

This does not mean an edge exists. It means the question was not answered, and
the earlier reports should have said so in those terms.

---

## 2. Pooling BTC and ETH — the lot's priority — did not rescue anything

The single-asset DVOL study ended with 18 effective observations on its best
result and a requirement of several hundred. Pooling was the only lever that
does not require waiting years. It was built, and it had never actually run:
`pooled_effect` existed with tests and no caller.

It runs now, four ways, and the answer is quantitative.

**Two assets are not two samples.** BTC and ETH forward returns correlate at
0.78 on average and 0.82 at the 30-day horizon. Under an equicorrelation
approximation, two series at ρ = 0.82 carry the information of **1.10
independent series, not 2**. Pooling raises the effective sample by about
10%. The row count doubles; the information does not.

Against a shortfall of roughly 40× that 10% is irrelevant. Pooling was worth
doing — it was the right question — and it is now measured rather than assumed.

**Results across the four methods** (12 hypotheses, 0 supported):

- 8 of 12 show no pooled effect under any method
- 4 of 12 are METHOD_DEPENDENT: the four estimates agree in sign, but only
  some reject zero, so significance rests on the pooling assumption
- **0 of 12 are ROBUST_ACROSS_METHODS**

The strongest, H1 options-expensive at 30 days, illustrates the problem
exactly. The four estimates are −6.9, −7.7, −5.9 and −5.6 — agreeing to within
32% of the effect — but their p-values are 0.34, 0.007, 0.098 and 0.023. Two
methods reject zero and two do not. Nothing about the data settles which pair
is right.

---

## 3. Robustness: what survives deleting a year, an asset, or a cycle

| Hypothesis | Overall | Leave-one-asset | Leave-one-year | Sign holds across cycles |
| --- | --- | --- | --- | --- |
| premium_cheap @30d | **ROBUST** | ROBUST | ROBUST | yes |
| premium_expensive @30d | FRAGILE | FRAGILE | ROBUST | yes |
| premium_expensive @14d | SIGN_FLIP | SIGN_FLIP | ROBUST | yes |
| premium_cheap @14d | FRAGILE | ROBUST | FRAGILE | yes |
| dvol_spike @7d | FRAGILE | ROBUST | ROBUST | no |
| dvol_compressed (all) | SIGN_FLIP | SIGN_FLIP | mixed | no |

Six of twelve change sign when a single asset, year or cycle is removed. One
survives everything: **H2, options cheap precedes higher returns, at 30 days**
— +3.87%, sign consistent in every cycle where it could be measured, robust to
removing either asset and any year. It is the single most durable thing in this
lot, and it still fails residualisation and remains underpowered.

`premium_expensive @30d` is carried by ETH: −9.77 on ETH against −2.59 on BTC,
so removing ETH cuts the pooled effect from −7.7 to −2.6. Presenting it as a
cross-asset result would be wrong.

---

## 4. The funnel

| Stage | Surviving |
| --- | --- |
| Pre-registered | 12 |
| Testable | 12 |
| Significant under any pooling method | 4 |
| Significant under all four methods | 0 |
| Survives residualisation | 0 |
| Survives leave-one-out | 0 |

Chance alone at α = 0.05 would produce about 0.6 apparent findings from twelve
tests. Zero survivors is not fewer than chance would give — it is what a null
looks like.

One claim reaches level 4 (CONTROLLED) when the stages are counted
independently rather than nested; it fails the all-methods requirement, so it
does not appear in the nested funnel. Both numbers are reported.

---

## 5. Features: fewer independent questions than columns

Eighteen features collapse to sixteen correlation clusters — an 11% reduction,
smaller than expected. Only two pairs cluster: `dvol_change_30` with its
percentile, and `variance_premium` with its percentile, both at ρ = 0.935. The
highest redundancy is `variance_premium` at R² = 0.93 against all others.

The eight controls used throughout LOT 6A are genuinely distinct: no redundancy
above 0.74, eight separate clusters. That is a positive result for a control
set that had never been checked.

## 6. Ablation: nothing predicts 30-day returns

Out-of-sample R² of the full model across all five families: **−0.376**. It
does not beat predicting the training mean.

| Family | Loss when removed | Alone |
| --- | --- | --- |
| volatility | −0.012 | −0.045 |
| price | −0.018 | −0.008 |
| derivatives | −0.021 | −0.081 |
| trend | −0.032 | **+0.012** |
| implied volatility | −0.123 | −0.283 |

Every family *improves* the model when removed. Only `trend` (ADX) is
marginally positive on its own. The ablation code refuses to rank families when
the full model fails, because differences between two failing models are not
evidence for anything — the ordering above is printed for completeness and must
not be read as a ranking of usefulness.

This was re-run with train-only standardisation after the first version used
raw columns. Ridge penalises coefficients, so on columns spanning funding rates
near 0.0001 and DVOL near 100 the penalty falls on the small-scale features.
Standardising changed R² from −0.373 to −0.376: the conclusion is not an
artefact of scaling.

---

## 7. How much more data would settle this

For the best pooled candidate — a 2% effect at 30 days, sd ≈ 20% — the
requirement is about 795 effective observations against 18 held. At roughly 13
independent events per year, that is **60 more years**.

The four shortlisted claims are registered as prospective experiments. The
soonest could conclude in **16.7 years**.

This is the honest answer to "what would it take". These questions cannot be
settled by waiting, by pooling the two assets that have data, or by adding
features. Either the effects are much larger than assumed, or the sample must
widen across many more assets, or the questions should be retired.

---

## 8. Final signal table

| Claim | Level | Effect | Blocked at | Robustness | Decidable |
| --- | --- | --- | --- | --- | --- |
| H1 options expensive → lower returns @30d | 4 CONTROLLED | −6.55 % | ROBUST | FRAGILE (ETH-driven) | not in a useful timeframe |
| H2 options cheap → higher returns @30d | 3 STRATIFIED | +3.87 % | CONTROLLED | **ROBUST** | not in a useful timeframe |
| H3 IV rising sharply → lower returns @7d | 3 STRATIFIED | +0.72 % | CONTROLLED | FRAGILE | not in a useful timeframe |
| H3 IV rising sharply → lower returns @14d | 3 STRATIFIED | +0.36 % | CONTROLLED | SIGN_FLIP | not in a useful timeframe |
| All eight others | 1 OBSERVED | — | BASELINE_RELATIVE | — | — |

**Nothing is actionable.** Actionable requires level 6 with adequate power. The
highest reached is 4, and every claim is underpowered.

Note that H3's measured sign is *positive* while the hypothesis predicted
negative. It is listed because it passed a stratification test, not because it
supports the claim it was written to test.

---

## 9. Bugs found and fixed

Five defects, three of them mine, all now covered by tests.

1. **Open interest was never read.** The LOT 6A backfill wrote 6262 rows to
   `oi.contracts_bybit`; every research module read `oi.value`, which holds 99.
   Six years of open-interest depth had been collected and used by nothing.
   Fixed by selecting the longest available series and naming which metric it
   came from. The two are never spliced — they are in different units, and a
   level jump at the join would read as a real change in positioning.

2. **A single sparse column silently emptied every frame.** `oi_change_30`
   arrived with 1 valid row in 1991, and the row-wise `dropna` reduced the
   analysis frame to zero rows. Every downstream stage reported
   "insufficient data" with no indication of the cause. Sparse columns are now
   dropped loudly, with their coverage recorded.

3. **The meta-analysis used iid standard errors** on overlapping windows and
   returned p = 3.5 × 10⁻¹³ from 18 genuinely independent events. Now clustered
   on date blocks: the same quantity comes back at p = 0.023, and I² falls from
   82% to 51%.

4. **A falsy-zero bug discarded the most significant results.**
   `payload.get("p_value") or payload.get("fallback")` treats `0.0` as absent,
   so a p-value of exactly zero — the strongest possible result — was recorded
   as having no p-value and counted as non-significant. Found by a test that
   planted a 12% effect and saw only one of four methods detect it. The same
   pattern was found and fixed in `rank_by_tractability`, where
   `years_to_decide == 0.0` (already decidable) sorted last.

5. **The old leaky walk-forward was still live.** In
   `structural_research.py`, `first_cut` was simultaneously the last training
   bar and the first validation bar, with no purge. Replaced with purged splits
   separated by horizon + embargo; verified at 61 days of separation for a
   30-day horizon.

The funnel was also non-monotonic — a later stage reported more survivors than
an earlier one, because stages were counted independently rather than nested.
Now nested by construction, with monotonicity asserted in the payload and in a
test.

---

## 10. Answers to the lot's questions

**A. Does an exploitable edge exist in the data currently held?**
Not one that can be demonstrated. Zero of twelve pooled hypotheses survive.
Out-of-sample R² is negative for every feature family. But "not demonstrated"
is weaker than "does not exist": the pipeline's detection floor is above the
threshold worth having, so effects in the 1–8% band would be invisible.

**B. Did pooling raise statistical power meaningfully?**
No, and the reason is measured. BTC and ETH correlate at 0.78–0.82, giving 1.10
effective independent series rather than 2 — about 10% more effective sample
against a 40× shortfall. Pooling was the correct thing to try and it is now
answered rather than assumed.

**C. Which claims survive the most demanding tests?**
One: H2, options cheap precedes higher returns at 30 days. Robust to removing
either asset, any year, and consistent in sign across every measurable cycle.
It fails residualisation and remains underpowered, so it stops at level 3.

**D. How many more observations are needed?**
About 795 effective observations against 18 held, at 13 per year: 60 years for
the best candidate, 16.7 years for the soonest shortlisted experiment. These
questions are not answerable by waiting.

**E. Is the research pipeline trustworthy?**
For positive results, yes — it does not manufacture findings from noise
(5.5% and 4.0% false-positive rates against a 9.0% tolerance). For negative
results, only above its detection floor. Below 3–8% depending on horizon, its
silence carries no information. That distinction should govern how every
previous report in this project is read.

**F. Is any feature family worth continuing to collect?**
On this evidence, none is justified by predictive value at 30 days: all five
improve out-of-sample R² when removed. Implied volatility is the most costly to
include (−0.123). Collection should continue for description and for the live
experiments, not because it predicts.

**G. Should the system move to machine learning?**
No. The readiness gate is not met and training would be indefensible. Linear
models on standardised features achieve R² = −0.376 out of sample; there is no
signal for a more flexible model to find, and a more flexible model would find
one anyway. Nothing here replaces `EntryOpportunity`, and nothing is promoted
automatically.

---

## 11. What should happen next

Not more features. The lot's own rule applies: if the controls leave zero
signals supported, the result is zero signals supported.

Three things are worth doing, in order:

1. **Fix the interpretation of every past negative result.** The detection
   floor means "no measurable edge" has been over-claimed throughout. Reports
   should state the floor alongside the verdict.
2. **Let the four registered live experiments run.** They are the only tests in
   this project not contaminated by having seen their own data. They will take
   years, and saying so now is better than checking hopefully each month.
3. **Widen the panel, or stop.** Two correlated assets cannot produce the
   sample these questions need. Twenty assets at ρ = 0.7 would give roughly 1.4
   effective series — better, still not enough. The honest conclusion is that
   daily-horizon directional prediction on this data is not a tractable
   question, and the system's value lies in description, risk framing and
   contradiction detection rather than in forecasting.

---

## Reproducing this

```
crypto-intel lot6b
```

Outputs `data/research/lot6b.json` and `data/research/dvol_pooled.json`.
The hypothesis registry lives in `data/research/hypothesis_registry.json` and
refuses to let a tested hypothesis be rewritten; a variant becomes a new
version and is counted as an additional test.

Tests: 678 backend (6 skipped), 41 Flutter. `crypto-intel lot6b` is deterministic given the
same data hashes.
