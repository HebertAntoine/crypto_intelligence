# Audit future-first — état réel avant migration

Date de l'audit : 2026-09-12. Cet audit est fondé sur le code et la base locale,
pas sur les documents d'architecture seuls.

## Périmètre trouvé

Le dépôt conserve bien l'architecture descendante demandée :

1. `providers/` collecte et normalise en `Observation` ;
2. `db/` stocke avec SQLAlchemy 2 et SQLite ;
3. `engines/` calcule sans LLM ;
4. `analysts/` et `reports/` synthétisent ;
5. FastAPI, Flutter et React présentent les résultats.

Les actifs de production restent BTC, ETH et SOL. Aucun moteur ne passe
d'ordre. Le LLM est optionnel et les décisions déterministes continuent de
fonctionner sans lui.

## Inventaire réel

### Acquisition

- Marché : Binance, Coinbase, Kraken et CoinGecko.
- Dérivés : Binance Futures, agrégation Binance/Bybit/OKX, CoinGlass optionnel.
- ETF : import CSV, CoinGlass, SoSoValue et Farside. Farside est un parseur de
  page protégé par une règle d'abandon propre sur blocage.
- Macro : FRED et ALFRED pour l'historique, Yahoo/Stooq pour les indices.
- On-chain/DeFi : Blockchain.info, Blockchair, Solana RPC et DeFiLlama.
- Actualités/réglementation : RSS publics configurés (Fed, SEC, CFTC,
  Treasury, White House et médias).
- Baleines : connecteurs optionnels Glassnode, CryptoQuant, Nansen et Arkham.
  Sans licence, la famille est explicitement indisponible.

Deux capacités déclarées dans `config/providers.yaml` n'ont toutefois aucun
provider construit par le registre : `macro.calendar` et `etherscan`.

### Persistance

La base locale contient 25 tables. Les principales sont `observations`,
`computations`, `reports`, `events`, `etf_flows`, `ohlcv`, `macro_series`,
`macro_releases`, `derivatives_history`, les snapshots immuables et les
résultats de recherche.

Le modèle `EventRow` existant ne couvre qu'un calendrier simple : type, nom,
institution, statut légal, date, importance, résumé, URL, source, actifs et
métadonnées. Il ne peut pas représenter proprement un événement non programmé
car `scheduled_at` est obligatoire. Il ne contient pas non plus les
anticipations, leur horodatage, le cycle de vie, la surprise, l'amplitude, la
chaîne causale ni les preuves demandées.

La migration retenue est donc additive : une table `future_events` devient la
source canonique riche ; `events` reste intacte comme contrat historique le
temps de faire migrer les lecteurs. Cela évite une migration destructive et
permet aux événements non programmés d'avoir `scheduled_at = NULL`.

### Moteurs et synthèse

Les moteurs actuels couvrent technique, structure, patterns, régime, timing,
ETF, dérivés, levier, volatilité réalisée et implicite, on-chain, liquidité,
macro, réglementation, news, géopolitique, baleines, analogues historiques,
contradictions, edge, opportunité d'entrée et opportunité d'achat.

`BuyOpportunityDecisionEngine/v2` existe sous forme de fonction déterministe
`engines.buy_opportunity.decide`. Il sait déjà plafonner une lecture à
`ATTENDRE` devant un événement macro critique dans les 24 heures. Ce garde est
cependant limité au calendrier macro statique : il ne traite ni l'incertitude
des scénarios, ni les anticipations de marché, ni les événements Tier 1 non
macro, ni plusieurs horizons.

`ChiefMarketAnalyst` produit trois scénarios central/haussier/baissier. Le mode
LLM peut encore attribuer des probabilités analytiques indicatives non issues
du marché. Le nouveau contrat devra autoriser une probabilité uniquement
lorsqu'elle possède une méthodologie ou une source horodatée, et ajouter un
scénario de risque extrême.

La direction et l'amplitude sont déjà séparées conceptuellement dans
`VolatilityRegimeEngine`, et les textes disent explicitement que la volatilité
ne donne pas le sens. Les bandes de Bollinger et leur largeur sont calculées,
mais aucun état `squeeze` prospectif indépendant de la direction n'est encore
émis.

### Les familles

Trois notions portent aujourd'hui le nom de famille :

- les domaines analytiques (technique, ETF, dérivés, on-chain, etc.) ;
- les 15 familles de couverture/fraîcheur de la page Today ;
- les cinq familles de pression : institutions, agressivité spot, dérivés,
  funding et baleines.

Aucune ne correspond aux cinq familles produit imposées :

1. Macro & liquidité ;
2. Catalyseurs & réglementation ;
3. Flux institutionnels & baleines ;
4. Positionnement & dérivés ;
5. Technique & volatilité.

Il faut donc créer une vue d'agrégation de ces données existantes, avec cinq
slots constants. Une famille absente devra rester `UNAVAILABLE`, jamais être
convertie en zéro ou en neutre.

### Fraîcheur et provenance

Le backend possède deux vocabulaires de fraîcheur :

- `core.enums.Freshness` pour les observations ;
- `core.usability.Freshness` pour l'aptitude d'une famille à alimenter la page.

Les deux sont calculés à partir des timestamps. Flutter recalcule aussi l'âge
des snapshots embarqués et refuse leur libellé `LIVE` figé. Le principe est
correct, mais la nouvelle API devra exposer uniformément `observed_at`,
`fetched_at`, `age_seconds` et `freshness_status` au runtime.

La provenance brute est forte pour les `Observation`. La table `events` est
moins complète et plusieurs entrées n'ont actuellement aucune URL source.

### Scheduler, alertes et historique

APScheduler actualise prix, analyses, décisions, OHLCV, dérivés, ETF,
expériences et évaluations. Aucun job ne collecte encore un calendrier futur
officiel, FedWatch, les votes réglementaires ou les événements protocolaires.

Les alertes possèdent déjà déduplication, cooldown et transitions d'état. Leur
déduplication vise toutefois les alertes, pas les événements multisuources.

L'historique point-in-time, les vintages macro, les snapshots immuables et les
contrôles anti-look-ahead existent et doivent être conservés.

### API et interfaces

FastAPI expose notamment `/api/assets`, `/api/today/{asset}`, `/api/calendar`,
`/api/events`, `/api/why/*`, les graphiques, la recherche et les diagnostics.
Les contrats existants seront conservés ; les nouveaux champs et endpoints
seront additifs.

Flutter (`app/`) possède déjà trois onglets : Aujourd'hui, Marchés et
Graphique. La page Aujourd'hui contient une carte d'opportunité cliquable et
un détail des raisons. Elle charge toutefois les trois actifs simultanément au
lieu d'avoir une analyse sélectionnée BTC/ETH/SOL future-first.

React/Vite (`frontend/`) possède onze entrées de navigation et reste le
frontend compilé servi par FastAPI. Il faut soit le réduire à Marchés / Analyse
/ Graphiques, soit décider explicitement que Flutter devient le client
principal. Pendant la migration, les deux clients liront le même contrat API.

### Tests de référence

La suite couvre déjà fraîcheur, provenance, absence de fabrication, pression,
ETF, baleines, décisions, cohérence d'écran, snapshots et anti-look-ahead.
Dans l'état audité, `pytest -q` échoue dès la collecte de deux tests LOT 6B car
ils importent `backend.crypto_intel` tandis que `pythonpath` ne contient que
`backend`. Une exécution de référence avec `PYTHONPATH=.:backend` est donc
nécessaire pour mesurer les échecs réels.

## Écarts critiques observés dans les données

Le calendrier de production est codé dans `config/macro_calendar.yaml`, sans
URL de preuve. La base contient déjà plusieurs versions simultanées des mêmes
publications (par exemple CPI, PCE et NFP à deux dates distinctes), car la
synchronisation insère un nouvel identifiant lorsque la date change mais ne
résout pas l'ancienne entrée. Afficher ces lignes comme `KNOWN` est incompatible
avec le nouveau cahier des charges.

Les dernières observations générales de la base auditée datent du 8 septembre
2026 et les derniers flux ETF du 4 septembre 2026. Leur présence ne doit donc
jamais être assimilée à leur actualité.

## Migration par lots

- Lot B : modèle canonique `FutureEvent`, table additive, repository,
  déduplication événementielle, cycle de vie, source tier et fraîcheur runtime.
- Lots C-D : providers officiels Fed/BLS/BEA/Treasury puis SEC/CFTC/Congress et
  protocoles ; suppression du YAML daté du chemin production.
- Lot E : anticipations et surprises, avec horodatage obligatoire de toute
  distribution de probabilité.
- Lots F-I : énergie/géopolitique, flux institutionnels, baleines, options et
  squeeze Bollinger directionnellement neutre.
- Lots J-L : scénarios 24 h/7 j/30 j, hiérarchie des signaux, `EventRiskGate`
  et intégration à la décision existante.
- Lots M-P : contrat API future-first, Marchés/Analyse/Graphiques, détail
  « Pourquoi ? » et timeline.
- Lots Q-R : tests demandés, builds, validation BTC/ETH/SOL et contrôle des
  données réellement disponibles.

