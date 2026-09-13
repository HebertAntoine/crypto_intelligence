# Lot 2 — Phases 1 à 4

Date de validation : 13 septembre 2026.

Périmètre volontairement arrêté après `DecisionDataQuality`. Aucun connecteur
FedWatch, moteur de surprise, nouveau provider whales, graphe causal, moteur de
convergence, résolveur Future de contradictions ou `DecisionEngineV2` n'a été lancé.

## Causes corrigées

### Marché périmé

La panne n'était pas un défaut des endpoints publics Binance : un appel réel a
réussi. La chaîne opérationnelle cumulait trois défauts :

- le service local avait été lancé avec `SCHEDULER_ENABLED=false` et le
  `docker-compose.yml` imposait également cette valeur ;
- au démarrage, l'analyse était planifiée avant les synchronisations OHLCV et
  dérivés, créant nécessairement un premier snapshot ancien ;
- le job rapide de marché écrivait uniquement `market_snapshots`, tandis que la
  décision lit les observations canoniques. De plus, le fingerprint et les
  familles décisionnelles ne suivaient pas `price.*`.

Le scheduler est réactivé, les collectes précèdent désormais l'analyse, le job
rapide persiste les observations de prix et l'identité d'analyse suit leurs
changements. Les unités 1h et 1w ont aussi un contrat de fraîcheur conforme à
leur cadence réelle.

### ETF contaminés

`data/imports/etf/example.csv` était le premier provider de la chaîne et son
succès empêchait d'atteindre Farside. Ses upserts avaient remplacé six lignes
réelles par une provenance `csv:example.csv`.

Les labels et chemins contenant les marqueurs sémantiques `example`, `fixture`,
`mock`, `sample` ou `test` sont maintenant rejetés à trois niveaux : import,
persistance et lecture/agrégation production. Farside et les providers licenciés
passent avant l'import manuel. L'exemple a été déplacé sous `fixtures/etf/` et
les six lignes contaminées ont été purgées de la base locale.

Le filtrage générique des fixtures est désormais effectué ligne par ligne : une
fixture voisine ne supprime plus les vraies observations macro, stablecoin ou
on-chain.

### DVOL

`ImpliedVolatilityReading.available` signifiait seulement qu'un historique
existait. Une DVOL ancienne rendait ainsi le positionnement disponible et
augmentait la confiance malgré une fraîcheur `UNAVAILABLE`.

La lecture porte maintenant `observed_at`, `age_seconds`, `freshness`,
`decision_status` et `usable_for_decision`. Seule une DVOL valide et fraîche
peut alimenter la couverture décisionnelle. L'historique ancien reste
consultable sous `AVAILABLE + STALE`, sans devenir une preuve courante.

## Horizons indépendants

| Horizon | Événements | Structure/technique | Contexte lent |
|---|---|---|---|
| 24h | fenêtre 24h + chocs récents 24h | 1h + 4h, Bollinger 1h | ETF et stablecoins exclus |
| 7j | fenêtre 7j + publications récentes 7j | 4h + 1j, Bollinger 4h | ETF, macro et liquidité admis s'ils sont frais |
| 30j | fenêtre 30j + publications récentes 30j | 1j + 1s, Bollinger 1j | macro, liquidité et tendance institutionnelle |

Les événements périmés sont exclus avant la construction des familles et avant
la décision. Un test construit des événements opposés par fenêtre et obtient
réellement `BUY`, `SELL` et `WAIT` sur les trois horizons, sans recopier un
snapshot.

## Inventaire des moteurs existants utiles

Les statuts ci-dessous concernent leur participation aux cinq familles
Future-First, pas leur simple présence sur une ancienne route.

| Moteur existant | Statut après Phase 3 | Rôle réel |
|---|---|---|
| `MacroAnalyzer` | `CONNECTED` | macro, seulement si ses observations sont fraîches |
| `StablecoinLiquidityAnalyzer` | `CONNECTED` | macro/liquidité 7j et 30j, jamais 24h |
| `InstitutionalFlowEngine` | `CONNECTED` | flux ETF 7j et 30j, avec fraîcheur/provenance |
| `LeverageCrowdingEngine` + `market_pressure` | `CONNECTED` | funding, OI, spot et positionnement court terme |
| `ImpliedVolatilityEngine` | `CONNECTED` | amplitude/positionnement si DVOL utilisable |
| `MarketStructureEngine` | `CONNECTED` | unités propres à chaque horizon |
| `VolatilityRegimeEngine` | `CONNECTED` | volatilité réalisée et amplitude |
| `ExpectedVolatilityEngine` | `CONNECTED` | squeeze Bollinger par horizon, amplitude uniquement |
| `GeopoliticalRiskEngine` | `CONNECTED` | événements géopolitiques concrets et sourcés |
| `WhaleAnalyzer` | `PARTIALLY_CONNECTED` | chemin prévu dans la pression, mais aucune source réelle configurée |
| `DerivativesAnalyzer` / agrégat multi-exchange | `PARTIALLY_CONNECTED` | infrastructure utilisée par ailleurs ; l'agrégat complet reste hors décision Future |
| `OnChainAnalyzer` | `PARTIALLY_CONNECTED` | calculé et audité en qualité, pas encore un signal directionnel des cinq familles |
| `CrossAssetAnalyzer` | `PARTIALLY_CONNECTED` | calculé et audité en qualité 30j, pas un vote directionnel |
| `ETFFlowAnalyzer` / `ETFSplitEngine` | `PARTIALLY_CONNECTED` | ancien pipeline ; Future utilise `InstitutionalFlowEngine` pour éviter le doublon |
| `MarketExpectationEngine` | `UNUSED` | réservé à la phase suivante, aucune attente inventée |
| `WhaleIntelligenceEngine` | `UNUSED` | réservé à la phase whales, aucune donnée synthétique |
| `ContradictionEngine` | `UNUSED` dans Future | réservé au résolveur Lot 2 demandé plus tard |
| `GeopoliticalRiskAnalyzer` historique | `UNUSED` dans Future | le moteur événementiel `GeopoliticalRiskEngine` est utilisé à sa place |
| `RegulatoryCatalystEngine` | `UNUSED` dans Future | les événements réglementaires canoniques alimentent actuellement la famille directement |

## `DecisionDataQuality`

La qualité est calculée indépendamment pour chaque actif et horizon. Elle ne
possède volontairement aucun score composite `x/100` :

- `coverage` compte les entrées applicables présentes **et utilisables** ;
- `freshness` publie l'état runtime détaillé de chaque entrée ;
- `source_quality` inventorie les sources nommées, URLs et tiers ;
- `critical_missing_inputs` liste le prix et les bougies minimales propres à
  l'horizon qui manquent ou sont périmés.

Un manque critique impose `INSUFFICIENT_DATA`, `NEUTRAL` et une confiance nulle,
même si toutes les familles calculées sont haussières. Les manques optionnels
produisent `PARTIAL` et restent nommés, notamment `whale_intelligence` et
`market_rate_expectations`.
