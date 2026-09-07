# Feature UI Coverage

Etat apres hotfix dynamique du 2026-09-07.

| Backend feature | Engine | API | Flutter | Screen | Status |
|---|---|---|---|---|---|
| Fast market price | `engines.market_price.market_price_snapshot` | `/api/market/price/{asset}`, embedded in `/api/today/{asset}` | `MarketPriceRead` | Aujourd'hui, Marches | UI_VISIBLE |
| Price provider fallback | `ProviderRegistry` + `market.ticker` chain | `/api/market/price/{asset}` | provider list in model | Details Aujourd'hui/Marches | UI_VISIBLE |
| EUR display | Coinbase direct EUR spot when available | `market_data.price_eur`, `fx_*` | `displayPrice`, `displayUnit` | Aujourd'hui, Marches | UI_VISIBLE |
| Price freshness | `core.freshness.compute_freshness` | `market_data.status`, `freshness`, `age_seconds` | `MarketPriceRead` | Aujourd'hui, Marches | UI_VISIBLE |
| Edge state | `EdgeEngine` | `/api/edge`, `/api/today/{asset}` | `EdgeState` | Toutes syntheses | UI_VISIBLE |
| Uncertainty | `UncertaintyEngine` | `/api/today/{asset}` | `TodayRead` | Aujourd'hui | UI_VISIBLE |
| Funding / OI / crowding | `LeverageCrowdingEngine` | `/api/leverage/{asset}`, `/api/today/{asset}` | `TodayRead` | Aujourd'hui, Marches | UI_VISIBLE |
| Multi-timeframe structure | `MultiTimeframeEngine` | `/api/multi-timeframe/{asset}` | `MultiTimeframeRead` | Marches | UI_VISIBLE |
| Range intelligence | Technical/range engines | `/api/structure/{asset}` | `StructureRead` | Graphique | UI_VISIBLE |
| OHLCV chart | History store + chart endpoint | `/api/chart/{asset}` | `ChartRead` | Graphique | UI_VISIBLE |
| Pattern detection | Technical/pattern engines | `/api/structure/{asset}`, `/api/chart/{asset}` | `DetectedPattern` + raw chart patterns | Graphique, Connaissances | UI_VISIBLE |
| Entry opportunity | `EntryOpportunityEngine` | `/api/entry-opportunity/{asset}` | `EntryOpportunity` | Graphique, Aujourd'hui summary timing | UI_VISIBLE |
| Daily intelligence report | `DailyReportEngine` | `/api/daily-report-v2` | `DailyReport` | Rapport | UI_VISIBLE |
| Research marginal value | LOT 6 research exports | `/api/research/marginal-value` | Map renderer | Recherche | UI_VISIBLE |
| Revalidation | LOT 6A research | `/api/research/revalidation` | Map renderer | Recherche | UI_VISIBLE |
| DVOL study | LOT 6A research | `/api/research/dvol` | Map renderer | Recherche | UI_VISIBLE |
| Evidence / power / pooling | LOT 6B endpoints | `/api/evidence`, `/api/power`, `/api/pooling` | API client + snapshots | Recherche | API_EXPOSED |
| Trader knowledge claims | Knowledge store/research | `/api/knowledge/educational-claims`, `/api/research/claim-validation` | Map renderer | Connaissances | UI_VISIBLE |
| Source hierarchy | Config/source tiers | `/api/sources/hierarchy` | Map renderer | Connaissances | UI_VISIBLE |
| Provider diagnostics | Provider registry | `/api/health` | Settings provenance panel | Aujourd'hui settings | UI_VISIBLE |

Decision rule: a backend feature should be marked `BACKEND_ONLY`,
`RESEARCH_ONLY`, `API_EXPOSED`, or `UI_VISIBLE`. New market-facing features
should not remain invisible without an explicit decision.

