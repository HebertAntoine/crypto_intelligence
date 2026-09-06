# LOT 4 — final report

Status: complete. 436 tests pass, 6 skipped, ruff clean, frontend builds,
CLI and API smoke-tested.

---

## 1. Data actually available

| Series | BTC | ETH | SOL | Point-in-time? |
| --- | --- | --- | --- | --- |
| Daily candles | 3306 (2017-08-17→) | 3306 | 2216 (2020-08-11→) | Yes |
| Funding rate | 7000 (2020-04-15→) | 7000 | 6622 | Yes |
| Open interest (Bybit) | **2223 (2020-08-05→)** | **2145** | **1894** | Yes |
| Open interest (Binance) | 31 days | 31 | 31 | Yes |
| Macro (10 series) | 2513-2515 points, 2016-09→ | — | — | Mixed |
| ETF flows | since 2024 | — | n/a | Yes |
| BTC dominance | live only | — | — | **No history** |
| Liquidations | **UNAVAILABLE** | UNAVAILABLE | UNAVAILABLE | n/a |
| ALFRED vintages | needs FRED_API_KEY | — | — | Yes when present |

The open-interest line is the headline change: **30 days became ~6 years**
through Bybit's public `endTime` pagination. Pagination terminated on its own
in 11-13 requests of a 40 budget, so these are Bybit's real limits.

## 2. What was built

**Providers** — `multi_exchange.py`: Binance, Bybit, OKX with OI-weighted
funding, Herfindahl concentration, >4σ venue-anomaly detection, deep OI
backfill.

**Engines** — `leverage.py` (funding percentiles, OI/price state machine,
crowding), `volatility.py`, `edge.py` (EdgeState, UncertaintyEngine, decision
summary), `cross_asset.py` (correlations, ratios, breadth, liquidity regime),
`breakout.py`, `liquidation.py`.

**Research** — `funding_conditioned.py`, `baselines.py`, `registry.py`
(FeatureRegistry + reproducible datasets), `drift.py` (shadow model +
SignalDriftEngine), `pattern_validation.py`.

**Surface** — 19 new API endpoints, 6 CLI commands (`today`, `backfill-oi`,
`funding-study`, `ml-dataset`, `research-patterns`, `baselines`), 2 frontend
pages plus the knowledge panel on Today.

## 3. Measured findings

### 3.1 Funding — INCONCLUSIVE on all three assets

The first pass tested each funding band against **zero** and found 55/68/56
cells surviving FDR. That was an artifact: all three assets rose strongly over
the sample, so every band looked positive, including the most negative one on
SOL (+10.27% at 30 days). The test was measuring buy-and-hold.

Re-tested against a **same-conditioning baseline**, survivors fell to
**3 / 15 / 9** of 225 cells each. The stability check then removed the rest:
the effect is positive in only 2/5 (BTC), 3/6 (ETH) and 4/6 (SOL) years, and
118 in-band days form ~3.9 independent windows once overlap is accounted for.
SOL's headline +27.91% comes almost entirely from 2021 (+76% excess in 23
days); 2020 was −87%.

**No weights changed.** The contrarian sign in the score is neither vindicated
nor refuted — it is untested.

### 3.2 Chart patterns — one survivor out of 23 tested

Eight detectors replayed bar by bar over full history (2606 detections on BTC,
2365 ETH, 1082 SOL), each compared to a **same-regime** baseline, FDR across
the whole grid, then filtered on effect size, effective sample and per-year
stability.

| | Raw significant | After FDR | After all filters |
| --- | --- | --- | --- |
| BTC | 8 | 6 | **1** |
| ETH | 9 | 2 | 0 |
| SOL | 13 | 13 | 0 |

**The one survivor: BTC `double_top` at 14 days**, excess −3.18% against its
same-regime baseline, p=3.0e-7, negative in 6 of 7 years (85.7% sign
consistency), effective n=21 from 316 raw occurrences. Direction matches the
textbook bearish reading. Caveats: effective n is barely above the threshold
of 20, and 2025 reverses (+6.1%).

**Notable negative finding:** BTC `inverse_head_and_shoulders` — traditionally
bullish — preceded **below-baseline** returns consistently (−1.9% at 7d, −3.4%
at 14d, 71-86% sign consistency). It fails only on effective sample (n≈11-12).
The textbook direction is contradicted, not confirmed.

SOL `breakout` initially showed +3.99% excess and passed FDR, but failed the
per-year stability gate (4/6 years, MIXED) and was rejected.

### 3.3 Baselines — a coin flip beats buy-and-hold

| BTC 30d | Mean return when active | Coverage |
| --- | --- | --- |
| ema_cross | +5.93% | 60.7% |
| **random** | **+5.60%** | 49.7% |
| always_long (buy & hold) | +4.88% | 100% |

A fixed-seed coin flip "beats" buy-and-hold on mean-return-when-active. This
is the calibration every future signal must be read against: beating zero is
automatic, and beating buy-and-hold on this metric is not much harder.

### 3.4 EdgeState — NO_MEASURABLE_EDGE everywhere

BTC 0 admitted / 3 rejected, ETH 0/15, SOL 0/9. Consistent with LOT 3, where
no domain reached USEFUL and Ridge out-of-sample R² was negative on all three.

### 3.5 Cross-asset (90d, on returns)

All three correlate most strongly with **gold** (+0.49 to +0.52, at the 99-100th
percentile of their own history) and inversely with the dollar (−0.44 to −0.50,
at the 0-4th percentile). Nasdaq correlation is moderate (+0.31 to +0.40).
Liquidity regime EXPANSION; breadth BROAD_PARTICIPATION (3/3 above both EMAs).

### 3.6 Current state

```
BTC is strongly bullish, but we currently hold no robust directional edge.
  Direction   STRONGLY_BULLISH (held 80% of last 20 days)
  Edge        NO_MEASURABLE_EDGE       Crowding  NORMAL (direction UNKNOWN)
  Volatility  LOW, stable              Funding   NEUTRAL p45.7
  Uncertainty HIGH 60/100              Actionable  False
```

## 4. Bugs found and fixed

1. **Drift-versus-zero testing** (funding study) — produced 55/68/56 false
   survivors. Replaced with baseline-relative Welch tests. This one invalidated
   the study's entire first output.
2. **Misleading dominance proxy** — normalising BTC/ETH/SOL to a common start
   reported SOL at 69.6% "dominance", which was cumulative performance since
   2020. Removed entirely rather than relabelled, and replaced with real
   CoinGecko dominance or an explicit UNAVAILABLE.
3. **`app.css` never imported** — every style added in LOT 4 was silently
   inert. Found by noticing the CSS bundle hash did not change between builds.
4. **numpy.bool serialisation** — breadth and breakout leaked numpy scalars
   into JSON, returning 500s on three endpoints.
5. **Liquidation UNKNOWN branch** — returned early without stating that actual
   liquidation volumes are unavailable.
6. **Pattern validation without a stability gate** — initially reported two
   MEASURABLE_EDGE results; adding the per-year check (the funding lesson)
   removed SOL breakout.

## 5. Remaining limitations

- **Liquidations UNAVAILABLE.** Binance withdrew the public aggregated stream;
  Coinglass needs a paid key. Cascade *conditions* are measured instead and
  labelled as conditions.
- **Dominance has no history**, so it cannot enter any backtest.
- **ALFRED vintages need `FRED_API_KEY`.** Without it, revised macro series
  stay `NOT_POINT_IN_TIME` and are excluded from backtests.
- **Live track record is empty** — 5 snapshots, 0 resolved outcomes. The
  shadow model now records on every run, but real drift detection needs ~30
  scored predictions per horizon, i.e. weeks of scheduler uptime.
- **Breadth covers three assets**, which is far too narrow to represent the
  market.
- **Effective sample is small everywhere.** Overlapping forward windows mean
  most studies have 3-40 independent observations, not the hundreds the raw
  counts suggest.
- **`code_version` reports "unknown"** — the repository has no commits, so
  dataset manifests cannot pin a revision.

## 6. Honest summary

Six years of open interest, 6.4 years of funding, 9 years of candles, 8 pattern
detectors and 23 pattern-horizon hypotheses produced **one** relationship that
survives every filter, on one asset, at one horizon, with an effective sample
of 21. Everything else is NO_MEASURABLE_EDGE.

That is the result. The system is built to keep reporting it until something
genuinely clears the bar.
