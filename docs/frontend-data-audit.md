# Frontend Data Audit

Audit du hotfix dynamique du 2026-09-07. Objectif: chaque valeur marche affichee
par Flutter doit venir du backend ou etre explicitement indiquee indisponible /
snapshot.

| Page | UI field | Current source | Backend source | Dynamic? | Freshness | Problem | Fix |
|---|---|---|---|---|---|---|---|
| Aujourd'hui | Prix BTC/ETH/SOL | Avant: `_AssetMeta.price` hardcode; apres: `TodayRead.marketData` | `/api/today/{asset}` -> `market_data`, aussi `/api/market/price/{asset}` | Yes | `market_data.status`, `as_of`, `age_seconds` | BTC affichait `€52 840`, ETH `€2 210`, SOL `€128` sans provider | Supprime du code UI; affiche EUR si provider EUR, sinon USD, sinon `INDISPONIBLE` |
| Aujourd'hui | Variation 24h | Avant: `_AssetMeta.change` hardcode; apres: `MarketPriceRead.change24hPct` | Provider `market.ticker`; Binance expose `price.change_24h_pct` | Yes | `market_data.freshness` | `+2,4 %`, `+1,8 %` etaient des valeurs visuelles | Supprime du code UI; si absent: `24h N/A` |
| Aujourd'hui | Sous-titre live | `DataProvenance` du client | Reponse HTTP live ou snapshot integre | Yes | `LIVE` / snapshot date / stale | "Analyse des marches en temps reel" restait visible sur snapshot | Sous-titre dynamique: live, snapshot, perime ou age inconnu |
| Aujourd'hui | Direction du marche | `decision_summary.market_direction` | `/api/today/{asset}` -> `EdgeEngine` + regime reconstruit | Yes | Timestamp `decision_summary.generated_at` | OK, mais devait rester separe de l'edge | Conserve comme direction, jamais comme edge |
| Aujourd'hui | Edge mesurable | `edge.state`, counts | `/api/today/{asset}` -> `EdgeEngine` | Yes | Research stored run | OK | Badge separe; aucun BUY/SELL |
| Aujourd'hui | Crowding / positionnement / funding | `crowding`, `leverage_state`, `funding` | `/api/today/{asset}` -> `LeverageCrowdingEngine` | Yes | Provider/stored derivatives selon engine | Certaines lignes pouvaient ressembler a des recommandations | Info icons + bottom sheet avec source et etat |
| Aujourd'hui | Opportunite d'entree | `decision_summary.entry_timing` | `/api/today/{asset}` | Yes | Analytical cadence | Ancien label "Action recommandee" | Remplace par "Opportunite d'entree"; absence => `INDISPONIBLE` |
| Marches | Prix / 24h / freshness | `TodayRead.marketData` | `/api/today/{asset}` -> `market_data` | Yes | `status`, `as_of`, `age_seconds` | La page ne montrait pas clairement la donnee rapide | Ajoute prix, 24h, provider et freshness |
| Marches | MTF / contradictions | `MultiTimeframeRead` | `/api/multi-timeframe/{asset}` | Yes | Stored OHLCV cadence | OK | Affiche les timeframes disponibles et conflits |
| Marches | Volatilite implicite | `ImpliedVolatilityRead` | `/api/volatility/implied/{asset}` | Yes | DVOL provider/stored | SOL doit rester indisponible | SOL affiche indisponible, aucune substitution |
| Graphique | OHLCV | `ChartRead.candles` | `/api/chart/{asset}?timeframe=&period=` -> local history store | Yes | Candle timestamp relative au timeframe | Avant hotfix UI pouvait dessiner une serie synthetique | Supprime fallback synthetique; affiche `Bougies OHLCV indisponibles` |
| Graphique | Prix courant du chart | `ChartRead.summary.last_price` ou derniere bougie | `/api/chart/{asset}` | Yes | Candle freshness | OK si bougies presentes | Aucun prix invente quand bougies absentes |
| Graphique | Ranges / supports / resistances | `StructureRead.location.range` | `/api/structure/{asset}` -> RangeIntelligence/technical engine | Yes | Stored OHLCV cadence | OK | Dessine zones issues backend |
| Graphique | Pattern / state / confidence | `StructureRead.patterns` | `/api/structure/{asset}` | Yes | Stored OHLCV cadence | OK | State/confidence separes de l'edge |
| Graphique | Invalidation / objectif | Rule text / `key_levels` / range zone | `/api/entry-opportunity/{asset}` + `/api/structure/{asset}` | Partial | Analytical cadence | Le parser prenait le `4` de "4h"; objectifs hardcodes | Extraction robuste; objectif uniquement si fourni, sinon `INDISPONIBLE` |
| Rapport | Sections rapport | `DailyReport.sections` | `/api/daily-report-v2?asset=` | Yes | `generated_at` du rapport | OK | Sections expansibles, scroll mobile |
| Recherche | Marginal/revalidation/DVOL/structure/replication | Maps API | `/api/research/*`, `/api/evidence`, `/api/power`, `/api/pooling` | Yes | Stored research runs | Les nouveaux resultats doivent apparaitre sans codage manuel | Endpoints ajoutes aux snapshots statiques et au client |
| Connaissances | Hierarchie sources | Map API | `/api/sources/hierarchy` | Yes | Static/config backend | OK | Affiche provenance conceptuelle |
| Connaissances | Claims / validation / dataset | Maps API | `/api/knowledge/educational-claims`, `/api/research/claim-validation`, `/api/knowledge/dataset-quality` | Yes | Knowledge/research store | Peut etre vide | Empty states explicites |
| Toutes | Error/loading/empty | `FutureBuilder`, `ErrorView`, `LoadingView` | Toute route API | Yes | N/A | Ecran blanc interdit | Etats loading/error explicites; snapshot non masque |

## Hardcodes Supprimes

- `€52 840` pour BTC dans `app/lib/screens/today_screen.dart`
- `€2 210` pour ETH dans `app/lib/screens/today_screen.dart`
- `€128` pour SOL dans `app/lib/screens/today_screen.dart`
- `+2,4 %`, `+1,8 %`, `+3,1 %` dans `app/lib/screens/today_screen.dart`
- objectifs/invalidation graphiques hardcodes dans `app/lib/screens/chart_screen.dart`
- serie OHLCV synthetique dans `app/lib/screens/chart_screen.dart`

## Fallbacks Conserves

- Snapshots integres `app/assets/static_api/*.json`: autorises uniquement comme
  mode hors ligne. Le client expose `DataProvenance.snapshot`; la UI affiche une
  banniere et change le sous-titre.
- Labels pedagogiques et traductions: autorises, car ce ne sont pas des donnees
  de marche.

