# Project state — recovery audit

Reconstructed from the repository on 2026-09-06. Nothing here is taken from
memory; every line was verified against the code, the database, the research
outputs or the test suite.

## Headline

| | |
| --- | --- |
| **Last LOT actually finished** | **LOT 5** (Pattern Intelligence & Trader Knowledge) |
| **LOT currently open** | **LOT 6A** — planned in detail, **zero lines implemented** |
| Tests | **504 passed, 6 skipped** (not 436 — that figure was LOT 4) |
| Ruff | clean on `backend` and `tests` |
| Git | 8 commits, pushed to `origin/main`, working tree clean but for `config/scoring_candidate.yaml` |

The starting assumption ("LOT 4 finished, ~436 tests") is **out of date**.
LOT 5 was completed and reported, and six further commits added a Flutter
client and a Vercel deployment.

## What happened after LOT 5

| Commit | Effect |
| --- | --- |
| `c52b12d` | Flutter client + Docker/Vercel split |
| `0b42727` | Vercel FastAPI entrypoint |
| `70d7325` | **static API snapshots bundled into the app** (66 550 lines of JSON) |
| `5c6abe6` | **client prefers the static snapshot over a live call** |
| `432272c` | French mobile redesign of the Today screen |
| `decd4a7` | chart screen rework, `mobile_kit.dart`, LOT 6 plans committed |

## Feature table

Action values: KEEP · FINISH · FIX · VALIDATE · RESEARCH · DEPRECATE

| Feature | Planned | Implemented | Tested | Data available | Research executed | Production-ready | Action |
| --- | --- | --- | --- | --- | --- | --- | --- |
| **LOT 5 — structure** | | | | | | | |
| Causal swings (`pivot_time`/`confirmation_time`) | yes | yes | yes (mutation) | 9 y candles | yes | yes | KEEP |
| ATR-scaled zones | yes | yes | yes | 9 y | yes | yes | KEEP |
| Range intelligence | yes | yes | yes | 9 y | yes | yes | KEEP |
| Structural location | yes | yes | yes | 9 y | yes | yes | KEEP |
| Market structure (HH/HL/LH/LL, BOS/CHOCH) | yes | yes | yes | 9 y | yes | yes | KEEP |
| Pattern library (9 detectors) | yes | yes | yes | 9 y | yes | yes | KEEP |
| Structural cache (×680) | yes | yes | yes | — | — | yes | KEEP |
| **Multi-timeframe synthesis** | yes | **built during this session** — `engines/multi_timeframe.py` | yes | 15m 4 mo, 1h 1.2 y | no | yes | KEEP |
| **LOT 5 — knowledge** | | | | | | | |
| GoodCrypto educational claims | yes | yes (19 concepts, 38 claims) | yes | n/a | yes | yes | KEEP |
| Transcript parser (FR/EN) | yes | yes | yes | n/a | n/a | yes | KEEP |
| Temporal alignment | yes | yes | yes | n/a | n/a | yes | KEEP |
| Human example dataset | yes | yes (schema) | yes | **0 examples** | no | no | **RESEARCH** |
| Human vs algorithm | yes | yes | yes | 0 examples | INSUFFICIENT_DATA | no | **RESEARCH** |
| **Engines** | | | | | | | |
| EntryOpportunity | yes | **v1 only** — 5 inputs of the ~17 requested | yes | yes | no | partial | **FINISH** |
| Historical analogs | yes | **v1** — feature-matrix similarity only | partial | yes | no | partial | **FINISH** |
| Edge / Uncertainty | yes | yes | yes | yes | yes | yes | KEEP |
| Leverage / crowding / volatility | yes | yes | yes | 6 y | yes | yes | KEEP |
| Cross-asset / breadth / liquidity | yes | yes | yes | 10 y macro | partial | yes | VALIDATE |
| Liquidation risk | yes | yes (UNAVAILABLE path) | yes | none | n/a | yes | KEEP |
| **Research** | | | | | | | |
| Structural research | yes | yes | yes | 9 y | **yes, D1** | yes | KEEP |
| Marginal value (A/B/C ladder) | yes | yes | yes | 9 y | **yes** | yes | **FINISH** (ladder stops at C; D/E/F missing) |
| Claim validation | yes | yes | yes | 9 y | yes | yes | KEEP |
| LOT 4 replication | yes | yes | yes | 9 y | yes | yes | KEEP |
| Baselines | yes | yes | yes | 9 y | yes | yes | KEEP |
| **Purge / embargo** | LOT 6A | **NO** | no | n/a | no | **no** | **FIX — highest priority** |
| **Residualisation** | LOT 6A | **NO** | no | n/a | no | no | **FINISH** |
| **Pooling + clustering** | LOT 6A | **NO** | no | n/a | no | no | **FINISH** |
| **Power / MDE** | LOT 6A | **NO** | no | n/a | no | no | **FINISH** |
| **Baseline CI guards** | LOT 6A | **NO** | no | n/a | n/a | no | **FIX** |
| **Live** | | | | | | | |
| Shadow model (directional) | yes | yes | yes | **3 snapshots** | no | partial | RESEARCH |
| Structural shadow | yes | yes | yes | **1 snapshot** | no | partial | RESEARCH |
| Live track record | yes | yes | yes | 0 matured | TOO_EARLY | partial | RESEARCH |
| **Data families** | | | | | | | |
| Candles 1d/4h/1w | yes | yes | yes | 9 y / 2.8 y | yes | yes | KEEP |
| Candles 1h | yes | yes | yes | **1.2 y** | no | partial | VALIDATE |
| Candles 15m | yes | yes | yes | **12 000 bars, 4 months** (2026-05-04 →) | no | partial | VALIDATE |
| Funding | yes | yes | yes | 6.4 y | yes (INCONCLUSIVE) | yes | KEEP |
| Open interest (Bybit) | yes | yes | yes | 6 y | yes | yes | KEEP |
| Macro (10 series) | yes | yes | yes | 10 y | partial | yes | VALIDATE |
| ETF flows | yes | yes | yes | **4 months stored** | no | no | RESEARCH |
| DeFi TVL | yes | yes | yes | **4 months** | no | no | RESEARCH |
| Long/short ratio | yes | yes | yes | **4 days** | no | no | RESEARCH |
| BTC dominance | yes | live only | yes | **2 days** | no | no | RESEARCH |
| **DVOL (implied vol)** | LOT 6B | **NO** | no | 5.5 y obtainable | no | no | **FINISH** |
| **Stablecoin history** | LOT 6B | **NO** | no | 8.8 y obtainable | no | no | **FINISH** |
| **On-chain BTC history** | LOT 6B | **NO** | no | 5 y obtainable | no | no | **FINISH** |
| **Surface** | | | | | | | |
| API (5 route modules) | yes | yes | yes | — | — | yes | KEEP |
| CLI (20+ commands) | yes | yes | smoke | — | — | yes | KEEP |
| React frontend | yes | yes | build+typecheck | — | — | yes | KEEP |
| Flutter app | yes | yes | 19 tests | — | — | **see bug 1** | **FIX** |
| Docker image | yes | yes | CI smoke | — | — | yes | KEEP |

## Bugs found during this audit

**Bug 1 — the Flutter app serves frozen data with no staleness signal.**
`app/lib/api/client.dart::_get` tries a bundled JSON snapshot *before* the
network whenever `baseUrl` is empty, and returns it in the same shape as a live
response. The UI cannot tell the difference and never displays the snapshot's
age. On Vercel — where `baseUrl` is empty by design — the app will show
2026-09-06 data labelled "Today" indefinitely. For a project whose stated
purpose is a system that knows what it knows, this is the most serious defect
present. Severity: high. Action: FIX.

**Bug 2 — `chronological_split` cannot purge.**
`research/stats.py:183` takes no horizon argument, so no caller can be
protected. Documented in the LOT 6A plan; still open.

**Bug 3 — walk-forward splits share their boundary bar and do not purge.**
`research/structural_research.py::_walk_forward`: `first_cut` is simultaneously
the last training bar and the first validation bar, and training targets within
H bars of the cut are built from validation prices. Every out-of-sample
confirmation currently reported is affected.

**Bug 4 — `config/scoring_candidate.yaml` modified and uncommitted**, with no
record of why. Needs review before it silently changes a challenger weight.

## What is genuinely missing to move forward

Ranked by value, not by order in the plan:

1. **Statistical foundations (LOT 6A)** — purge, embargo, residualisation,
   pooling, power. Not started. Every existing OOS claim rests on a leaky
   split, so this gates the trustworthiness of everything already measured.
2. **Staleness honesty in the app** — bug 1.
3. **Multi-timeframe synthesis** — readings exist per timeframe; the alignment
   and conflict verdict does not.
4. **EntryOpportunity V2** — 5 of ~17 planned inputs.
5. **Analog engine V2** — still a plain feature-distance search.
6. **Live data accumulation** — 3 and 1 snapshots respectively. Only time fixes
   this, and only if collection runs.
7. **New orthogonal families** (DVOL 5.5 y, stablecoins 8.8 y, on-chain 5 y) —
   all verified obtainable, none ingested.

## Decision taken

Work proceeds in this order, and the reasoning is recorded because it departs
slightly from the phase numbering in the request: **LOT 6A first**, because
adding EntryOpportunity inputs, analogs or new data families on top of a leaky
walk-forward would produce more results that cannot be trusted. The audit found
the foundation defect is real and unaddressed; fixing it changes the meaning of
every number the project has produced.


## Correction to this audit

The first inventory pass reported no 15-minute candles. A second check found
**36 000 rows across the three assets**, roughly four months deep
(2026-05-04 onward). The most likely explanation is that the API server left
running earlier in the session collected them between the two queries. The
table above has been corrected; four months is enough to display but not to
research at that timeframe.

This is recorded rather than quietly edited, because an audit that silently
changes its own findings is not an audit.
