# LOT 6A — statistical foundations

**No code until this is validated.**

Guiding principle: improve inference before adding data. The question is no
longer "can we find more signals?" but "can we trust a signal when it
survives?"

---

## 0. The two defects, located precisely

### 0.1 No purge, and splits share their boundary

`research/structural_research.py::_walk_forward`:

```python
first_cut  = index[int(len(index) * 0.50)]
second_cut = index[int(len(index) * 0.75)]
windows = {
    "train":      (index[0],   first_cut),     # first_cut is the LAST train bar
    "validation": (first_cut,  second_cut),    # and also the FIRST validation bar
    "oos":        (second_cut, index[-1]),
}
```

Two distinct problems:

1. `first_cut` belongs to train **and** validation. The boundary bar is in both.
2. `forward` at bar *t* is computed from the price at *t+H*. Every training bar
   within *H* of `first_cut` therefore has a target built from validation-period
   prices. With H=30 and daily bars, **the last 30 training observations leak**.

At a 30-day horizon on a ~825-bar validation window, that is roughly 3.6% of the
test period's information present in training — concentrated exactly at the
boundary, where autocorrelation is highest.

### 0.2 `chronological_split` cannot purge

`research/stats.py:183` takes `(index, train, validation)` and no horizon. It has
no way to know what to purge. Any caller using it is unprotected by
construction.

---

## 1. Purge and embargo

### 1.1 Exact formula

Let observation *i* have feature timestamp `t_i` and a target spanning
`[t_i, t_i + H]` where H is the horizon **in bars of the study's own
timeframe**. Let the test fold span `[T_start, T_end]`. Let E be the embargo,
in bars.

An observation is **retained in train** if and only if both hold:

```
(1) PURGE    t_i + H  <  T_start          (target closes before the test opens)
(2) EMBARGO  t_i      >  T_end + E    OR   t_i + H < T_start
```

Written as the rejection rule actually implemented:

```
drop from train  ⟺  [t_i, t_i + H] ∩ [T_start, T_end] ≠ ∅        (purge)
                 ∨  t_i ∈ (T_end, T_end + E]                     (embargo)
```

Purge handles train-before-test. Embargo handles train-after-test, which occurs
in every walk-forward fold that is not the last one, and covers residual serial
correlation that outlives the target window itself.

**Worked example.** Daily bars, H = 30, E = 30, test = 2024-01-01 → 2024-03-31.

| Train bar | Target closes | Kept? | Why |
| --- | --- | --- | --- |
| 2023-11-15 | 2023-12-15 | yes | closes before test |
| 2023-12-05 | 2024-01-04 | **no** | target reaches into the test |
| 2023-12-31 | 2024-01-30 | **no** | purged |
| 2024-04-15 | 2024-05-15 | **no** | inside the embargo window |
| 2024-05-05 | 2024-06-04 | yes | past the embargo |

Bars purged per boundary: exactly H. Bars embargoed per boundary: exactly E.

### 1.2 Embargo default and its justification

Default `E = H`, configurable.

The rationale is not arbitrary: serial correlation in the *target* decays over
roughly its own construction window, so one horizon past the test end is the
natural scale. The default will be **verified empirically** — the
autocorrelation of the target at lag E must be below 0.05, and the value is
recorded in the output. If it is not, E is raised for that study and the report
says so.

### 1.3 What this will cost

Purging removes H bars per boundary. With three folds and H=30 that is ~120 bars
out of ~3300, roughly 4%. The cost is small; the correction is not optional.

**Expected consequence: some current out-of-sample confirmations will fail.**
That is the purpose. Any candidate that survives purging is worth more than the
same candidate before it.

---

## 2. Continuous residualisation (method B)

### 2.1 Why the discrete regime is not enough

Measured, in this repository, today:

| correlation of `regime(t)` with the return over | BTC | ETH | SOL |
| --- | --- | --- | --- |
| past 5 days | +0.35 | +0.34 | +0.36 |
| past 20 days | +0.62 | +0.60 | +0.57 |
| **past 40-60 days** | **+0.73** | **+0.73** | **+0.58** |

Five buckets summarising a two-month return. Two days sharing a label can be at
entirely different points of entirely different moves.

### 2.2 Method

Three steps, in this order:

1. **Fit the control model on TRAIN only.**
   `y = Xβ + ε` where y is the forward return and X the control matrix.
   Ridge regression, α selected on the training fold by internal purged CV, not
   on the test fold.

2. **Compute residuals on TEST using the train-fitted β.**
   `r_test = y_test − X_test β̂_train`

3. **Test the signal against `r_test`.**
   Excess of `r_test` on signal days versus non-signal days.

**The ordering is the whole point.** Fitting the control model on the full
sample and then testing residuals is itself leakage: the fit absorbs part of the
signal, and the residual is contaminated by test-period information. This is a
common enough mistake that it gets its own CI test (§6, Test 5).

### 2.3 Control features

Chosen to target the measured confound directly — the regime is a 40-60 day
return summary, so lagged returns at several horizons are the primary controls.

| Control | Why it is here | PIT |
| --- | --- | --- |
| `return_1`, `return_5`, `return_20`, `return_60` | directly spans the window the regime label summarises | yes |
| `realised_vol_20`, `realised_vol_60` | volatility clustering drives both signal frequency and return dispersion | yes |
| `dist_ema200_pct` | position relative to the long trend, not captured by returns alone | yes |
| `adx_14` | trend strength versus chop; a range signal means something different in each | yes |

Eight controls. Deliberately not more.

Excluded and why:
- `rsi_14` — a bounded transform of the same returns already present;
- `funding_percentile` — only 6.4 y, would truncate studies to the shortest
  input; kept as an *optional* control, reported separately when used;
- anything not in the `FeatureRegistry` with `usable_for_backtest == True`.

**Every control must be point-in-time.** The residualisation step will assert
this against the registry and refuse to run otherwise — a non-PIT control would
launder future information into the residual, which is worse than no control.

Collinearity is expected among lagged returns. Ridge handles it; the condition
number and per-control VIF are reported so the reader can see how much the
controls overlap.

---

## 3. Multi-asset pooling

### 3.1 Model

```
y_{a,t} = α_a  +  β · signal_{a,t}  +  γ' · controls_{a,t}  +  ε_{a,t}
```

`α_a` are asset fixed effects. β is the pooled effect. The hypothesis is
`β = 0`.

### 3.2 Clustering, and why it is on date

BTC, ETH and SOL correlate around 0.8. Three assets producing an event on the
same day is close to **one** observation, not three. Standard errors are
therefore clustered on **date**, never on asset.

The cluster-robust variance:

```
V = (X'X)^{-1} ( Σ_d  X_d' ε_d ε_d' X_d ) (X'X)^{-1}
```

where the sum runs over unique dates *d* and `X_d`, `ε_d` stack all assets
observed on that date. This lets residuals correlate arbitrarily within a date
and assumes independence only across dates.

**This still is not enough on its own.** Dates are serially correlated through
overlapping targets, so date-clustering alone under-states the variance. The
inference therefore uses **date clusters combined with a block structure**:
clusters are non-overlapping blocks of H consecutive dates. This is coarser and
more conservative, and is the honest choice given overlapping windows.

### 3.3 Mandatory reporting

A pooled result must never hide a single-asset effect. Every pooled test reports:

- `n_raw_pooled`, and `n_per_asset`
- `n_unique_dates`
- `n_independent_blocks` (the actual cluster count)
- `effective_n`
- pooled β with its clustered CI
- **per-asset β**, and a heterogeneity test across assets
- an explicit flag when one asset carries the effect

Rule: if the pooled effect is significant but only one asset's β has the same
sign at a comparable magnitude, the verdict is **INCONCLUSIVE**, labelled
"single-asset effect presented as pooled".

---

## 4. `effective_n`

### 4.1 Current definition

```python
effective_n = min(episodes, n / horizon_bars)
```

Conservative and defensible, but ad hoc and blind to cross-asset dependence.

### 4.2 Proposed definition — the minimum of four

```
effective_n = min( n_episodes,
                   n / H,
                   n_independent_blocks,
                   n_variance_adjusted )
```

1. **`n_episodes`** — runs of occurrences separated by more than H. Unchanged.
2. **`n / H`** — overlap correction. Unchanged.
3. **`n_independent_blocks`** — NEW, for pooled tests: the number of
   non-overlapping H-bar date blocks containing at least one event. This is what
   stops three correlated assets from tripling the count.
4. **`n_variance_adjusted`** — NEW, from the target's own autocorrelation:

```
n_eff = n / ( 1 + 2 · Σ_{k=1}^{H} (1 − k/(H+1)) · ρ_k )
```

with ρ_k the lag-k autocorrelation of the target series (Newey-West / Bartlett
weights). This measures the actual dependence rather than assuming it equals the
horizon.

All four are reported. The **minimum** is the headline, because each captures a
different way the sample is smaller than it looks and none dominates the others.

---

## 5. Power, and distinguishing FAILED from underpowered

### 5.1 Minimum detectable effect

At significance α=0.05 and power 1−β=0.80, for a two-sample comparison:

```
MDE = (z_{0.975} + z_{0.80}) · σ · sqrt( 1/n_event_eff  +  1/n_baseline_eff )
    ≈ 2.802 · σ · sqrt( 1/n_e + 1/n_b )
```

σ is the pooled standard deviation of the forward return, and both n are
**effective**, not raw. Using raw n here would report a reassuring MDE for a test
that cannot actually detect anything.

### 5.2 The meaningful-effect threshold

Declared in advance, per horizon, as the effect that would matter economically
net of the 0.20% round-trip cost:

| Horizon | Meaningful effect |
| --- | --- |
| 7 days | 1.0% |
| 14 days | 1.5% |
| 30 days | 2.0% |

### 5.3 The rule

```
if p ≥ 0.05 and MDE ≤ meaningful_effect   →  FAILED       (adequately powered null)
if p ≥ 0.05 and MDE >  meaningful_effect  →  INSUFFICIENT_DATA (underpowered)
```

A null result is only evidence of absence when the test could have detected a
presence. `p > 0.05` is **never** mechanically converted into FAILED.

Every test reports: `n_raw`, `effective_n`, effect size, 95% CI, p-value,
q-value, statistical power at the meaningful effect, and MDE.

---

## 6. Verdict rules

| Verdict | Conditions |
| --- | --- |
| **SUPPORTED** | survives FDR **under both stratification and residualisation**; effective_n ≥ 30; \|effect\| ≥ floor and net of 0.20% friction; sign consistent in ≥70% of years; confirmed in **purged** out-of-sample; if pooled, not carried by a single asset |
| **INCONCLUSIVE** | the two methods disagree; **or** significant but failing exactly one practical filter; **or** a pooled effect carried by one asset |
| **FAILED** | null result **and** MDE ≤ meaningful effect (the test had the power to see it) |
| **INSUFFICIENT_DATA** | effective_n < 30; **or** MDE > meaningful effect; **or** the point-in-time status of any input is unestablished. Never convertible by adding assets or horizons. |

Both methods' results are **stored separately** in every export, so it is always
visible *why* a hypothesis passed or failed.

---

## 7. CI regression tests

Five families. The first four are those requested; the fifth guards the specific
mistake residualisation invites.

**Test 1 — near-universal baseline.**
A mask presented as a conditioned subgroup that covers >95% of the sample raises
a blocking error. *This is the test that would have caught the LOT 5 bug.*
Additionally: `same_regime` and `same_regime_momentum` producing identical values
on every row is an automatic failure — that was the actual observed symptom.

**Test 2 — synthetic stratification.**
Construct data where the regime fully determines the return and the event has
**zero** causal effect but occurs preferentially in bullish regimes. Assert: the
unconditioned test finds a false effect; the stratified and residualised tests
both remove it. A framework that cannot remove a confound it was built for is
broken.

**Test 3 — temporal leakage.**
Construct data where the target deliberately overlaps the split boundary and
carries information only there. Assert: naive walk-forward reports apparent
skill; purged + embargoed walk-forward reports none.

**Test 4 — cross-asset dependence.**
Three series with correlation ~0.8 and simultaneous events, with no true effect.
Assert: naive pooling reports inflated significance and an effective_n near 3×
the block count; date-block-clustered pooling does not.

**Test 5 — residualisation fitted on the wrong data.**
Assert that fitting the control model on the full sample and testing residuals
recovers a *spurious* effect that the train-only fit does not. This pins the
ordering of §2.2 so a future refactor cannot silently reverse it.

All five run in CI on every push.

---

## 8. Revalidation protocol

Pre-registered **before** any result is seen. All are reported regardless of
outcome; none may be dropped for being inconvenient.

| # | Candidate | Origin | Current claim |
| --- | --- | --- | --- |
| 1 | ETH `ABOVE_RANGE` 3/7/14d | LOT 5 | +1.60 / +4.04 / +5.55% — best candidate |
| 2 | BTC `double_top` CONFIRMED 7d | LOT 4 + 5 | −1.14%, replicated across two detector definitions |
| 3 | BTC `MID_RANGE` 30d | LOT 5 | −4.35%, effective_n ≈ 22 |
| 4 | BTC `RANGE_STRUCTURE` 30d | LOT 5 | −3.78%, effective_n ≈ 23 |
| 5 | ETH `MID_RANGE` 7/14d | LOT 5 | −1.60 / −3.55% |
| 6 | ETH `TRANSITION` 7d | LOT 5 | −1.23% |
| 7 | ETH `double_top` FAILED 3d | LOT 5 | +2.76% |
| 8 | ETH `rising_wedge` 7/14d | LOT 5 | −2.13 / −3.18% |
| 9 | BTC `inverse_head_and_shoulders` 14d | LOT 4 + 5 | −4.38%, contradicts the textbook reading |
| 10 | Funding extreme bands | LOT 4 | INCONCLUSIVE — recheck under residualisation |

Each is re-run through: purged walk-forward → stratification → residualisation →
pooling where the label exists on more than one asset → power reporting → the
§6 verdict rules.

### ETH ABOVE_RANGE — status correction

Its status is formally updated. The earlier caveat — that the effect came from
breakouts occurring early in a regime episode while the lagging label had not
caught up — **is not confirmed**. Measured in this repository:

- `ABOVE_RANGE` days sit at regime +1.58 versus a sample mean of −0.02;
- median episode age is 8 bars versus 4 for the whole sample, so breakouts
  genuinely are earlier in episodes;
- **but adding episode age to the stratification moves the 7-day excess only
  from +4.79% to +4.64%.**

The mechanism I proposed was wrong. ABOVE_RANGE is therefore recorded as the
**project's best current candidate**, and explicitly **not** an established
edge: single asset, effective_n ≈ 35, stability not yet sufficient, other
confounders untested, and not yet run through purge + residualisation.

An honest possible outcome of LOT 6A is that it does not survive.

---

## 9. Files

### New

| Path | Contents |
| --- | --- |
| `backend/crypto_intel/research/inference.py` | `PurgedSplit`, `purged_walk_forward`, `residualise`, `pooled_effect`, `clustered_standard_errors`, `effective_sample_v2` |
| `backend/crypto_intel/research/power.py` | `minimum_detectable_effect`, `statistical_power`, `MEANINGFUL_EFFECT` table, `verdict_from_power` |
| `backend/crypto_intel/research/revalidation.py` | the ten pre-registered candidates and the re-run harness |
| `tests/unit/test_lot6_inference.py` | purge/embargo/residualisation/pooling unit tests |
| `tests/unit/test_lot6_guards.py` | the five CI regression tests of §7 |

### Modified

| Path | Change |
| --- | --- |
| `research/stats.py` | add `purged_chronological_split(index, horizon, embargo)`; keep `chronological_split` but mark it unsafe for overlapping targets and route callers away from it |
| `research/structural_research.py` | `_walk_forward` → `purged_walk_forward`; add the residualisation path; report both methods separately |
| `research/marginal_value.py` | same, plus pooled variant |
| `research/claim_validation.py` | same |
| `research/walkforward.py` | `build_windows` gains `horizon` and `embargo`, and purges |
| `research/registry.py` | expose the control-feature set and assert PIT status for controls |
| `api/routes_lot5.py` | expose the revalidation output |

Nothing in `structure/`, `engines/` or the frontend changes. This lot touches
inference only.

---

## 10. Order of work

1. Audit and document the current walk-forward defect with a failing test that
   demonstrates the leak numerically.
2. `inference.py`: purge + embargo, with unit tests.
3. Turn the audit test green.
4. `power.py`: MDE and power, with unit tests.
5. Residualisation, including the train-only fit and its guard test.
6. Pooling with date-block clustering.
7. `effective_sample_v2`.
8. The five CI guard tests.
9. Migrate the three research modules to the new inference.
10. Revalidate the ten pre-registered candidates.
11. Methodology report, and an updated verdict table for every previous finding.

**No new dataset is touched in 6A.** DVOL, stablecoins and on-chain wait for 6B.

---

## 11. What success looks like

Not "more SUPPORTED results". Success is:

- the leak in §0.1 demonstrated, then closed, with a test that fails if it
  returns;
- every previous finding re-reported with power alongside its p-value, so
  FAILED and underpowered stop looking alike;
- the two control methods reported separately and disagreements surfaced;
- pooled results that cannot hide a single-asset effect;
- five CI tests that make the LOT 4 and LOT 5 methodological errors
  non-reintroducible.

**If revalidation demotes every current candidate to INCONCLUSIVE, LOT 6A has
succeeded.** The project would then know that it previously had nothing solid —
which is more valuable than continuing to believe otherwise.
