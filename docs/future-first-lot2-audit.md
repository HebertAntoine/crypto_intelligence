# Audit Future-First — Lot 2 Data Coverage + Decision Intelligence

Statut : **Phase 0 uniquement — audit terminé, implémentation non commencée**  
Date : 13 septembre 2026  
Révision auditée : `d780b9bed852b2515630658376fa5ded45b5591e`

## 1. Périmètre et méthode

Cet audit porte sur le code réellement exécuté, la configuration effective et la base
locale `data/crypto_intel.db`. Il ne déduit pas l'état du produit à partir des seuls
documents d'architecture.

Vérifications effectuées :

- registre et chaînes de fallback des providers ;
- variables de configuration, contrôlées uniquement comme présentes/absentes, sans
  afficher de secret ;
- pipeline et jobs du scheduler ;
- schémas et contenu de la base SQLite en lecture seule ;
- construction du snapshot d'analyse, des cinq familles, du gate, des scénarios et de
  la décision ;
- contrats `/api/future/{symbol}`, `/why` et `/timeline` ;
- moteurs existants relatifs aux attentes, ETF, whales, énergie/géopolitique,
  volatilité, levier, liquidité, contradictions et qualité des données ;
- instantané réel BTC/ETH/SOL calculé depuis les données stockées à environ
  `2026-09-13 10:45 UTC` ;
- inventaire des tests existants.

Aucun dataset n'a été téléchargé, aucun entraînement n'a été lancé, aucun seuil et
aucune décision n'ont été modifiés. Aucun appel réseau supplémentaire n'a été requis
pour produire ce document.

Pour éviter toute ambiguïté, les termes employés ci-dessous ont le sens suivant :

- **implémenté** : une classe ou un connecteur existe dans le dépôt ;
- **configuré** : les paramètres nécessaires sont présents dans l'environnement ;
- **opérationnel** : le chemin collecte, persiste puis alimente réellement un moteur ;
- **LIVE** : la dernière donnée respecte sa cadence de fraîcheur au moment de l'audit ;
- **UNAVAILABLE** : aucune donnée utilisable n'est disponible ;
- **STALE** : des données existent, mais elles sont trop anciennes pour une décision
  courante.

## 2. Verdict exécutif

Le socle Lot Future-First est bien réel : modèle canonique `FutureEvent`, collecte
officielle, déduplication, cycle de vie, cinq slots constants, gate 48 heures, quatre
scénarios, trois horizons, API et clients. Il ne faut pas le recréer.

En revanche, le Lot 2 demandé n'est pas encore présent comme chaîne décisionnelle
intégrée. Plusieurs composants préparatoires existent et sont testés isolément
(`MarketExpectationEngine`, `InstitutionalFlowEngine`, `WhaleIntelligenceEngine`,
`GeopoliticalRiskEngine`, lecture DVOL et agrégateur dérivés multi-exchange), mais une
partie n'est jamais appelée par la décision Future-First.

L'état réellement observé est insuffisant pour qualifier la sortie de décision comme
LIVE :

- les trois actifs ont **zéro famille de données courantes** dans `DataCoverage` ;
- prix, OHLCV, funding, OI, spot, DVOL, ETF, on-chain et indices sont arrêtés entre le
  3 et le 9 septembre ;
- le calendrier officiel a été rafraîchi le 13 septembre et fournit les seules données
  véritablement récentes du snapshot Future-First ;
- aucune des 102 lignes `future_events` ne possède une distribution de marché, un
  timestamp de probabilité, un consensus, un résultat ou une surprise ;
- whales et liquidations réelles sont indisponibles faute de provider configuré ;
- le résultat courant est `WAIT / NEUTRAL / HIGH` pour BTC, ETH et SOL sur les trois
  horizons, malgré cette absence de données de marché courantes.

Les trois risques les plus urgents avant tout enrichissement fonctionnel sont :

1. **provenance contaminée** : des fixtures et un CSV nommé `example.csv` sont présents
   dans la base de production ;
2. **fraîcheur non bloquante** : une DVOL ancienne rend encore la famille
   positionnement « disponible » et la décision n'exige pas de prix/OHLCV courant ;
3. **fuite entre horizons** : les événements sont filtrés par horizon, mais les cinq
   familles, calculées sur la fenêtre de 30 jours, sont réutilisées à l'identique.

## 3. Réponses aux 20 questions obligatoires

### 3.1 Quels providers fonctionnent réellement ?

#### Providers sans clé et traces locales

| Domaine | Implémentation réelle | État constaté | Utilisé par la décision Future-First |
|---|---|---|---|
| Spot/OHLCV | Binance, Coinbase, Kraken ; CoinGecko pour marché global/capitalisation | Binance et CoinGecko ont des données persistées, dernières observations le 8 septembre et dernières bougies le 9 ; Coinbase/Kraken sont des fallbacks sans trace utilisée dans la base auditée | Oui indirectement, mais les données sont anciennes |
| Dérivés | Binance Futures | Historique funding/OI/ratio présent, arrêté le 8 septembre | Oui via les moteurs historiques et `market_pressure`, si frais |
| Multi-exchange | appels publics Binance/Bybit/OKX | Agrégateur courant implémenté ; historique Bybit OI persisté ; endpoint séparé disponible | **Non** pour l'agrégat courant |
| Options | Deribit DVOL | 1 995 observations BTC et ETH, dernière le 8 septembre ; rien pour SOL par conception | Oui, mais avec un défaut de contrôle de fraîcheur |
| ETF | import CSV local, Farside, CoinGlass ETF, SoSoValue | historique Farside présent ; le premier provider actuel est le CSV local et court-circuite les fallbacks dès qu'il réussit | Oui via `InstitutionalFlowEngine`, seulement si frais |
| On-chain | Blockchain.info, Blockchair BTC/ETH, Solana RPC | observations réelles présentes jusqu'au 8 septembre | Le contexte les calcule, mais elles n'alimentent pas directement un slot dédié |
| DeFi/stablecoins | DeFiLlama, DeFiLlama RWA, DeFiLlama Stablecoins | observations réelles présentes jusqu'au 8 septembre | Prévu dans macro/liquidité, mais actuellement neutralisé par le filtre fixtures |
| Macro indices | Yahoo Finance, Stooq fallback | Yahoo a des historiques et observations ; Stooq est conservé mais documenté comme bloqué par challenge JS | Prévu dans macro/liquidité, actuellement neutralisé par le filtre fixtures |
| Macro FRED | FRED/ALFRED | code présent, clé absente | Non disponible |
| Calendriers officiels | Fed, BLS, BEA, TreasuryDirect | Fed, BEA et Treasury ont réussi la dernière collecte observée ; BLS a répondu `NO_DATA` | Oui |
| Réglementation | flux officiels, CFTC, House, Senate, Congress.gov | flux officiels et CFTC ont réussi ; House/Senate `NO_DATA` ; Congress.gov non configuré | Oui pour les événements effectivement collectés |
| Protocoles | Ethereum Foundation, Solana Foundation/Status | les deux ont réussi la dernière collecte observée | Oui |
| Géopolitique | extraction d'événements concrets depuis RSS configurés | provider exécuté, mais `NO_DATA` lors de la dernière collecte | Oui seulement si un événement concret est produit |
| Whales agrégées | Glassnode, CryptoQuant, Nansen, Arkham | aucune clé ; CryptoQuant/Nansen/Arkham ne sont que des connecteurs non vérifiés même avec une clé | Prévu dans l'ancien contexte, absent aujourd'hui |
| Transferts whales | Whale Alert | parser et provider présents, clé absente | **Non câblé** dans collecte/persistance/décision |
| Liquidations | CoinGlass | provider présent, clé absente | Non disponible ; aucune valeur n'est fabriquée |
| Attentes Fed | adaptateur CME/FedWatch licencié | URL et clé absentes | Les champs d'événement existent, mais aucune donnée réelle |

La dernière exécution officielle observée a enregistré 97 événements ou mises à jour ;
après déduplication et conservation de l'historique, la table en contient 102. Ses
statuts source étaient : Fed `OK`, BLS `NO_DATA`, BEA `OK`, Treasury `OK`, flux
réglementaires `OK`, CFTC `OK`, House `NO_DATA`, Senate `NO_DATA`, Congress
`NOT_CONFIGURED`, CME `NOT_CONFIGURED`, géopolitique `NO_DATA`, Ethereum `OK`, Solana
`OK`.

Anomalie de registre : `config/providers.yaml` déclare `etherscan` dans la chaîne
`onchain.eth`, mais aucune classe Etherscan n'est construite par `_provider_classes()`.
Ce fallback est donc silencieusement supprimé de la chaîne réelle.

Configuration effective au moment de l'audit : `MOCK_MODE=false` et scheduler activé.
Les clés FRED, Congress, CME, Glassnode, CryptoQuant, Nansen, Arkham, CoinGlass,
SoSoValue, Whale Alert et Etherscan sont toutes absentes.

### 3.2 Quelles données sont réellement LIVE ?

Au sens strict de la décision au moment de l'audit, aucune donnée de prix ou de marché
n'est LIVE. `DataCoverage` rapporte zéro entrée à jour pour les trois actifs.

Les seuls apports récents sont les événements officiels mis à jour le 13 septembre :

- Fed/FOMC ;
- BEA/PCE/GDP ;
- Treasury auctions ;
- deux événements réglementaires stockés ;
- événements protocolaires précédemment collectés.

Le prochain ensemble réellement visible dans la fenêtre courante comprend des
adjudications Treasury les 14, 15 et 17 septembre, le FOMC du 16 septembre, puis PCE
et GDP le 30 septembre. Le FOMC était à environ 79 heures au moment du snapshot, donc
hors du gate de 48 heures.

`core.data_health` considère les séries macro `OK` parce que leur cadence configurée
est hebdomadaire et que leur âge est d'environ 111 heures. Cela ne signifie pas
qu'elles sont LIVE : `DataCoverage` les classe `DELAYED`, et le moteur macro courant
les rejette pour une autre raison détaillée en section 3.13.

### 3.3 Quelles données sont UNAVAILABLE ?

Sont réellement indisponibles aujourd'hui :

- distributions de probabilités de marché et historique d'évolution des attentes ;
- surprise événementielle observée, y compris taux, communication et projections ;
- whales attribuées et transferts Whale Alert ;
- liquidations réelles ;
- ETF SOL dans les marchés actuellement suivis ;
- DVOL SOL, que Deribit ne publie pas ;
- Brent, inventaires EIA, production, données IEA/OPEP structurées et disruptions
  énergétiques quantitatives ;
- stress systémique structuré (STLFSI/NFCI/spreads de crédit/Treasury vol) ;
- métriques et état `AI_CAPEX_RISK` ;
- graphe causal, confirmations indépendantes, résolution Lot 2 des contradictions et
  qualité de données propre à la décision ;
- skew, put/call, term structure, expiries et concentration options ;
- séries stablecoins 30 et 90 jours dans le contrat actuel ;
- séries macro FRED faute de clé.

Les données stockées mais anciennes ne sont pas comptées comme LIVE. Elles restent
utiles pour l'historique et la recherche, pas pour affirmer un état présent.

### 3.4 Quelles familles utilisent encore peu de données ?

Les cinq familles existent exactement une fois, mais leurs adaptateurs restent
minimaux :

| Famille | Entrées réellement consommées | Limites actuelles |
|---|---|---|
| Macro & liquidité | événements macro/monétaires/énergie, `MacroAnalyzer`, `StablecoinLiquidityAnalyzer` | un événement suffit à rendre la famille disponible ; direction prise sur l'événement prioritaire ou le plus fort de macro/liquidité ; pas d'attentes de marché, surprise, énergie structurée ni risque systémique |
| Catalyseurs & réglementation | événements réglementation, ETF, protocole, géopolitique, systémique, autre | un événement suffit ; pas de `GeopoliticalRiskEngine` intégré, pas de sévérité/corroboration/source_count exploitée |
| Flux institutionnels & whales | ETF frais, sinon meilleur composant spot ou whales de `market_pressure` | Whale Intelligence n'est pas appelé ; ETF stale rejeté ; Coinbase premium absent ; un seul composant dominant est retenu |
| Positionnement & dérivés | meilleur composant dérivés/funding, ou simple présence DVOL/funding/OI | agrégat Binance/Bybit/OKX non utilisé ; DVOL seule peut rendre le slot disponible ; pas de `PositioningState`, skew, term structure ou risque de liquidation directionnel |
| Technique & volatilité | nombre d'unités haussières/baissières, régime et volatilité réalisée | snapshots stale rejetés ; `ExpectedVolatilityEngine` Bollinger existe mais n'est pas appelé ; la direction technique est un simple différentiel de comptes d'unités |

### 3.5 Comment les cinq familles sont-elles scorées ?

Il n'existe pas de somme pondérée finale des cinq familles.

La direction dominante suit une priorité fixe :

1. macro/liquidité et catalyseurs/réglementation ;
2. flux institutionnels/whales ;
3. positionnement/dérivés ;
4. technique/volatilité.

Parmi les familles disponibles et non neutres, le moteur trie d'abord cette priorité,
puis la confiance. Si deux familles du même niveau prioritaire s'opposent, aucune ne
domine et la direction devient neutre. Une contradiction venant d'un niveau inférieur
n'annule pas la famille prioritaire.

Règles internes observées :

- macro : direction du ou des événements les plus importants ; sinon plus forte valeur
  absolue entre `macro.strength` et `liquidity.strength`, sans somme ;
- catalyseurs : direction de l'événement le plus important ;
- flux : état ETF frais en priorité ; sinon composant whale, puis spot ;
- positionnement : composant ayant le plus grand score absolu ; la DVOL est seulement
  censée contribuer à l'amplitude ;
- technique : `(nombre unités haussières - nombre unités baissières) * 25`, avec le
  régime comme fallback.

La confiance finale vaut :

`moyenne(confiance des familles disponibles) × nombre_familles_disponibles / 5`.

Elle n'intègre pas explicitement la qualité de source, les données critiques manquantes,
la fraîcheur du prix, le nombre de chaînes causales indépendantes ou les contradictions.

### 3.6 Comment `EventRiskGate` fonctionne-t-il réellement ?

Le gate :

- utilise une fenêtre fixe de 48 heures ;
- ne retient que les événements `CRITICAL` dont l'amplitude vaut `HIGH` ou `EXTREME` ;
- accepte un événement planifié imminent, un événement non planifié actif/surprise,
  ou une publication récente encore dans sa fenêtre de décroissance ;
- considère l'événement incertain si l'incertitude globale est absente ou supérieure ou
  égale à 0,60, si la distribution de marché manque, ou si plusieurs scénarios existent
  sans issue au moins à 75 % ;
- retourne `WAIT` lorsqu'il est actif ;
- sait théoriquement être contourné par `favorable_in_all_material_scenarios=true`, mais
  le chemin de décision ne passe jamais cette valeur à `true`.

Le gate n'est pas actif dans l'instantané audité : le FOMC du 16 septembre est encore
à environ 79 heures. Son absence de probabilité l'activera à moins de 48 heures si les
autres critères restent vrais.

### 3.7 Comment les quatre scénarios sont-ils construits ?

Les quatre scénarios sont toujours présents : `base_case`, `bullish_case`,
`bearish_case`, `tail_risk_case`.

- le cas de base reprend la direction de la famille dominante et l'amplitude maximale ;
- son `event_chain` concatène le titre et jusqu'à deux éléments `causal_chain` des trois
  événements les plus importants de l'horizon ;
- les cas bullish, bearish et tail risk utilisent actuellement des chaînes narratives
  génériques, non des branches calculées depuis des facteurs concrets ;
- leur confiance est la moyenne des familles disponibles, ramenée à 75 % pour les cas
  alternatifs ;
- toutes les probabilités restent `null` par défaut ;
- une distribution externe n'est acceptée que si les quatre scénarios sont fournis,
  totalisent environ 1, et portent chacun source et timestamp.

Aucun appel de production ne fournit actuellement cette distribution. Le contrat évite
donc correctement d'inventer des probabilités, mais il ne produit pas encore les
scénarios causaux demandés.

Un ancien chemin `ChiefMarketAnalyst` fabrique encore trois probabilités heuristiques.
Il ne contrôle pas `/api/future`, mais il contredit la règle Lot 2 si une ancienne route
continue à l'exposer comme une probabilité décisionnelle.

### 3.8 Existe-t-il déjà une notion de priced-in ?

Oui, mais seulement comme brique isolée. `MarketExpectationEngine` expose
`expected_outcome`, `degree_priced`, entropie d'incertitude, asymétrie et méthode. Le
modèle `FutureEvent` sait stocker une distribution horodatée, et la déduplication sait
fusionner une distribution CME avec l'identité officielle Fed.

Cette notion n'est appelée ni par `analysis_context`, ni par `FutureDecisionEngine`, ni
par les routes Future. Elle n'influence donc pas la décision, l'explication ou la
timeline. Il n'existe pas non plus d'historique de l'évolution des attentes.

### 3.9 Existe-t-il déjà une notion expectation/surprise ?

Partiellement : le même moteur calcule une surprise numérique comme
`1 - P(issue réalisée)` et, si les libellés sont numériques, une distance signée par
rapport à l'espérance pondérée.

Ce qui manque :

- objet persistant `MarketExpectation` avec historique point-in-time ;
- `EventSurpriseEngine` séparé ;
- fraîcheur/staleness des attentes ;
- comparaison `actual` versus `expected` dans le pipeline ;
- surprises de communication, dot plot/projections et forward guidance ;
- agrégation `overall_surprise` ;
- propagation à la décision et aux scénarios.

État de la base : 102 événements, zéro distribution, zéro timestamp de probabilité,
zéro consensus, zéro actual et zéro surprise.

### 3.10 Les ETF flows sont-ils réellement opérationnels ?

Le stockage et le moteur le sont, mais la collecte courante n'est pas saine.

- BTC : 7 279 lignes au total, du 11 janvier 2024 au 4 septembre 2026 ;
- ETH : 4 904 lignes, du 23 juillet 2024 au 3 septembre 2026 ;
- SOL : aucune donnée, explicitement non applicable dans les marchés suivis ;
- le moteur agrège par séance et calcule 3/5/20 séances, accélération et reversal ;
- une donnée stale n'alimente pas la famille Future-First.

Résultat historique calculé au moment de l'audit :

| Actif | État historique | Dernier jour | 3 séances | 5 séances | 20 séances | Fraîcheur |
|---|---:|---:|---:|---:|---:|---|
| BTC | `INFLOW` | +174,6 M$ | +1 006,5 M$ | +986,7 M$ | +3 443,8 M$ | `STALE` |
| ETH | `STRONG_INFLOW` | +123,9 M$ | +84,3 M$ | +274,0 M$ | +1 726,8 M$ | `STALE` |
| SOL | `INSUFFICIENT_DATA` | — | — | — | — | `UNAVAILABLE` |

Problème critique : la chaîne `etf.flows` commence par `etf_csv`. Le scheduler appelle
le registre et s'arrête au premier succès ; la présence de `data/imports/etf/example.csv`
empêche donc normalement d'atteindre Farside. Ce fichier a été importé le 13 septembre
et contribue au 3 septembre :

- BTC : 674,3 M$ sur un total journalier calculé de 730,8 M$ ;
- ETH : 119,7 M$ sur un total journalier de 123,9 M$.

Il n'y a pas de doublon exact `(asset, ticker, date)` : cette combinaison est justement
la clé d'upsert. Si une ligne Farside existait, l'import CSV a donc remplacé sa valeur et
son `import_source` ; sinon il a créé la ligne. La base actuelle ne permet plus de
distinguer ces deux cas. Cela n'en fait pas une donnée valide : un fichier d'exemple
local non vérifié influence réellement les fenêtres, l'accélération et l'état
institutionnel. Le champ `source_url` peut en outre rester celui de Farside après
l'overwrite, et des `evidence_ids` Farside sont associés à une provenance regroupée
incluant le CSV, ce qui rend le contrat de preuve trompeur.

### 3.11 Deribit est-il toujours présent ?

Oui : provider, backfill, job scheduler, stockage historique et
`ImpliedVolatilityEngine` existent. BTC et ETH possèdent chacun 1 995 jours/points de
DVOL jusqu'au 8 septembre ; SOL est correctement `NOT_APPLICABLE`.

Le moteur calcule niveau, percentile, évolution 30 jours, volatilité réalisée,
variance premium et compression. Il ne calcule pas skew, put/call, structure par terme,
expiries ou concentrations.

Défaut important : `ImpliedVolatilityReading` ne porte ni `observed_at` ni fraîcheur.
La simple présence d'un historique rend `available=true`. L'adaptateur des cinq
familles transforme alors une DVOL stale en famille positionnement disponible avec
confiance 0,75, tout en sérialisant `freshness=UNAVAILABLE`.

### 3.12 Funding/OI multi-exchange existants sont-ils bien utilisés ?

Non, seulement partiellement.

L'agrégateur public Binance/Bybit/OKX calcule funding pondéré par OI, moyenne simple,
dispersion, OI USD total, concentration Herfindahl, venue dominante et anomalie de
venue. Il est exposé par `/api/derivatives/aggregate/{symbol}`.

Le scheduler rafraîchit séparément Binance funding/OI et l'historique Bybit OI. La
décision Future-First ne demande jamais l'agrégat courant. `LeverageCrowdingEngine` et
`market_pressure` utilisent des morceaux de l'infrastructure — historique OI Bybit,
funding Binance, variation de prix et répartition de comptes Binance — mais pas funding
pondéré, total OI multi-venue, basis multi-venue, Herfindahl ni anomalie.

Les séries utilisées sont toutes stale au moment de l'audit. Aucune liquidation réelle
n'est disponible, et le code la laisse correctement absente.

### 3.13 Les stablecoins DefiLlama sont-ils toujours utilisés ?

Le provider, le pipeline et `StablecoinLiquidityAnalyzer` existent. La base contient
792 observations globales réelles provenant de `defillama_stables`, dont supply totale,
USDT/USDC/DAI, répartition Ethereum/Solana/Tron et variations 1/7 jours jusqu'au
8 septembre.

Pourtant, l'analyse courante retourne `UNAVAILABLE`. La cause est précise :
`_is_synthetic()` renvoie vrai si **une seule** observation de la liste vient d'une
fixture, puis `evidence_context()` vide toute la liste. Comme observations réelles et
fixtures cohabitent pour les mêmes préfixes, les données réelles stablecoins, macro et
on-chain sont toutes rejetées avec les fausses.

Même après correction de provenance, les données du 8 septembre resteraient stale au
moment de cet audit. Le contrat actuel ne calcule que 1 et 7 jours, pas 30 et 90 jours.

### 3.14 Quelles données whales existent réellement ?

Deux architectures coexistent :

- `WhaleAnalyzer` pour les agrégats Glassnode : inflow exchange, outflow exchange,
  balance exchange ;
- `WhaleIntelligenceEngine` pour les transferts attribués Whale Alert et la taxonomie
  wallet/exchange.

Le second distingue wallet→exchange, exchange→wallet, exchange→exchange,
wallet→wallet, mint, burn et unknown. Il ne traite que les deux premiers comme
directionnels et interdit à un transfert unique de créer un état fort. Cela respecte
déjà une grande partie de la consigne.

Limites réelles :

- aucune clé, aucune ligne et aucun signal whale pour BTC/ETH/SOL ;
- le provider Whale Alert et le moteur ne sont appelés que par les tests, pas par le
  pipeline, le scheduler, la persistance ou la décision ;
- custody est ramené au groupe wallet, sans états distincts custody→exchange et
  exchange→custody ;
- aucun objet `WhaleTransferInterpretation` par transaction ;
- CryptoQuant, Nansen et Arkham refusent volontairement de deviner leurs endpoints :
  même avec clé, ils renvoient non configuré tant que le mapping n'a pas été vérifié ;
- pas d'Exchange Whale Ratio, Coinbase Premium ni wallet institutionnel identifié.

### 3.15 Quelle donnée pétrole existe réellement ?

Une seule série quantitative existe : `macro.oil_wti`, issue de Yahoo Finance
(`CL=F`) avec fallback Stooq. L'historique `macro_series` contient 2 514 lignes depuis
2016, dernière date le 4 septembre ; les observations de contexte vont au 8 septembre.

Il n'existe pas de Brent, inventaires EIA, production, données IEA/OPEP structurées,
volatilité pétrolière dédiée, ni `EnergyMacroEngine`. Le provider géopolitique sait
créer des événements énergie (infrastructure attaquée, chokepoint, pipeline, OPEP,
réserve stratégique) et une chaîne textuelle, mais aucun de ces événements n'est
actuellement présent.

### 3.16 Quelle donnée géopolitique existe réellement ?

Le chemin récent est fondé sur des événements concrets extraits de flux RSS, puis
normalisés en `FutureEvent`. Les reprises détectées sont dédupliquées et les chaînes de
transmission sont conservées. `GeopoliticalRiskEngine` existe et refuse le simple
sentiment générique.

Cependant :

- aucun événement géopolitique/énergie concret n'est stocké dans l'état audité ;
- `GeopoliticalRiskEngine` n'est utilisé que par ses tests, pas par la décision ;
- l'adaptateur Future consomme directement les événements et leur direction prédéfinie ;
- l'événement ne possède pas les champs structurés `severity`, `source_count`,
  `source_quality`, effets énergie/inflation/risk-off et régions demandés ;
- la signature de déduplication dépend notamment de l'heure, du lieu et des entités,
  souvent absents des RSS : deux reprises à des heures différentes peuvent échapper à
  la fusion, tandis que deux événements du même type dans la même heure peuvent être
  fusionnés à tort ;
- l'ancien `GeopoliticalRiskAnalyzer`, toujours dans le pipeline historique, reste un
  score regex de thèmes/titres. Ses rendements décroissants ne remplacent pas une
  véritable identité événementielle.

### 3.17 Quelles données macro historiques/live sont disponibles ?

La table historique contient environ dix ans de séries Yahoo pour Dow, DXY, or,
Nasdaq, WTI, S&P 500, taux 13 semaines/5 ans/10 ans et VIX, jusqu'au 4 septembre. Les
observations plus courtes du contexte vont jusqu'au 8 septembre. FRED/ALFRED, leurs
vintages et les modèles point-in-time existent, mais aucune clé FRED n'est configurée.

Les calendriers futurs Fed/BEA/Treasury sont actuels au 13 septembre. Le calendrier BLS
n'a produit aucune donnée lors de la collecte observée.

Dans le snapshot décisionnel, `MacroAnalyzer` retourne néanmoins `UNAVAILABLE`, car le
filtre global fixtures vide la liste réelle. La famille macro reste disponible grâce
aux événements futurs, pas grâce aux séries macro observées.

### 3.18 Comment BUY/WAIT/SELL est-il calculé ?

Le calcul exact est :

1. compléter exactement cinq slots ;
2. rechercher la famille directionnelle dominante selon la priorité décrite en 3.5 ;
3. prendre comme amplitude le maximum des amplitudes de toutes les familles et de tous
   les événements non passés ;
4. calculer la confiance par moyenne des familles × couverture ;
5. si moins de deux familles sont disponibles : `INSUFFICIENT_DATA` ;
6. sinon, si `EventRiskGate` est actif : `WAIT` ;
7. sinon direction bullish : `BUY` ;
8. sinon direction bearish : `SELL` ;
9. sinon : `WAIT`.

La sortie du moteur Future-First devient ensuite l'autorité du chemin
`buy_opportunity`, afin de garder les anciens contrats compatibles. Le LLM ne décide
pas cette sortie.

### 3.19 Qu'est-ce qui peut actuellement produire une fausse décision ?

Risques classés par sévérité :

| Sévérité | Risque | Effet possible |
|---|---|---|
| Critique | Le prix 4H et les données critiques peuvent être stale sans forcer `INSUFFICIENT_DATA` | BUY/SELL/WAIT présenté comme décision présente à partir d'un marché vieux de plusieurs jours |
| Critique | `example.csv` est le premier provider ETF et contribue aux agrégats | régime, accélération ou reversal institutionnel erroné dès que les données redeviennent jugées fraîches |
| Élevée | DVOL ancienne reste `available` sans timestamp/freshness | famille positionnement fictivement disponible, confiance et couverture gonflées |
| Élevée | Snapshot de familles 30 jours réutilisé pour 24h/7j/30j | événement lointain ou amplitude 30j contamine 24h ; décisions copiées de fait |
| Élevée | Un événement officiel suffit à une famille confiance 1,0 | qualité de source confondue avec confiance de l'implication analytique |
| Élevée | Fixtures mélangées aux données réelles font supprimer toute une liste | fausse indisponibilité macro/liquidité/on-chain et perte de signaux réels |
| Élevée | `GeopoliticalRiskEngine`, Whale Intelligence, Market Expectation, Bollinger et agrégat multi-exchange ne sont pas branchés | le moteur ignore des informations pourtant collectables ou déjà calculables |
| Élevée | La contradiction des familles de moindre priorité ne peut pas forcer WAIT | BUY ou SELL possible malgré opposition matérielle inter-familles |
| Moyenne | amplitude = maximum global sans decay spécifique | `HIGH` peut persister sur un horizon où le catalyseur n'est pas pertinent |
| Moyenne | événement protocolaire récent/decaying traité `RECENT` avec confiance source 1,0 | catalyseur neutre ancien compte comme famille pleinement disponible |
| Moyenne | `unavailable_reason` reste renseigné pour des familles `AVAILABLE` | contrat incohérent, UI et audits difficiles à interpréter |
| Moyenne | certains facteurs dérivés utilisent `as_of=now` malgré des données anciennes | provenance temporelle trop optimiste dans l'ancien écran d'explication |
| Moyenne | anciennes routes/scénarios LLM peuvent encore afficher des probabilités heuristiques | contradiction avec « aucune probabilité inventée » hors API Future |

### 3.20 Existe-t-il des doubles comptages entre familles ?

Le moteur actuel évite une partie du double comptage par construction : il choisit une
famille dominante au lieu de sommer cinq scores ; au sein de macro il prend la valeur
la plus forte plutôt qu'une somme ; dans les flux, l'état ETF dédié remplace le
composant institutionnel de `market_pressure` ; positionnement prend le composant le
plus fort ; l'amplitude utilise un maximum.

Il n'existe toutefois **aucune garantie causale** :

- aucun `CausalFactor`, `CausalEdge`, `CausalChain` structuré ou `MarketCausalGraph` ;
- aucune lignée permettant de dire que guerre, pétrole, inflation, taux et risk-off
  représentent une seule chaîne ;
- aucun `independent_confirmation_count` ni `causal_chain_count` ;
- les familles disponibles contribuent toutes à la confiance de couverture, même si
  leurs preuves dérivent d'une même cause ;
- les unités techniques corrélées augmentent la confiance selon leur simple nombre ;
- l'ancien pipeline pondéré peut encore additionner des domaines corrélés dans ses
  propres sorties.

Conclusion : aucun double comptage direct n'a été identifié dans le choix de direction
Future actuel, mais le système ne sait ni prouver l'indépendance ni éviter le
double/triple comptage lorsque le Lot 2 ajoutera davantage de signaux. Le graphe causal
doit précéder le moteur de convergence.

## 4. Instantané réel BTC / ETH / SOL avant Lot 2

Instantanés calculés depuis la base locale entre `10:45:01` et `10:45:22 UTC` le
13 septembre 2026 :

| Actif | Prix affiché (dernière clôture 4H) | Couverture générale | Familles Future | Décision 24h / 7j / 30j | Confiance | Event risk |
|---|---:|---|---|---|---:|---|
| BTC | 79 108,00 | 11/13 présentes, **0 à jour**, 11 stale | 2/5 | WAIT / WAIT / WAIT, NEUTRAL, HIGH | 0,35 | LOW |
| ETH | 2 492,52 | 11/13 présentes, **0 à jour**, 11 stale | 2/5 | WAIT / WAIT / WAIT, NEUTRAL, HIGH | 0,35 | LOW |
| SOL | 103,85 | 9/11 présentes, **0 à jour**, 9 stale | 2/5 | WAIT / WAIT / WAIT, NEUTRAL, HIGH | 0,40 | LOW |

Le prix affiché n'est pas un prix du 13 septembre : il provient de la dernière bougie
4H du 9 septembre à 08:00 UTC.

Familles qui expliquent les deux slots « disponibles » :

- BTC/ETH : macro grâce au calendrier officiel, puis positionnement uniquement parce
  que l'historique DVOL stale est encore marqué disponible ;
- SOL : macro grâce au calendrier officiel, puis catalyseur grâce à un événement
  protocolaire ;
- flux/whales et technique/volatilité sont indisponibles pour les trois ;
- le positionnement SOL est indisponible.

Les trois vues d'horizon sont identiques parce que le snapshot de familles reste le
même. Ce résultat constitue un constat de l'état avant Lot 2, pas une recommandation de
marché.

## 5. Contradictions avec la consigne Lot 2

| Demande Lot 2 | État réel | Décision d'architecture |
|---|---|---|
| Étendre l'existant | Plusieurs briques existent déjà | Les renforcer et les câbler ; ne pas les recréer |
| EVENT / EXPECTATION / PRICING / SURPRISE | EVENT existe ; le reste est isolé ou vide | Ajouter persistance point-in-time et orchestration autour de `MarketExpectationEngine` |
| Surprise taux/communication/projections | surprise numérique minimale seulement | Créer un moteur composite sans relation taux→direction codée en dur |
| Institutionnels 1/3/5/20, tendance, accélération, reversal, persistence | 3/5/20, accélération et reversal existent ; pas 1d/persistence explicite | Étendre `InstitutionalFlowEngine` et assainir la collecte |
| Whale interpretation complète | taxonomie et agrégat partiels existent | Ajouter interprétation par transfert, custody et câblage optionnel |
| EnergyMacroEngine | absent | Créer à partir de sources primaires, conserver WTI comme prix de marché |
| GeopoliticalCatalystEngine événementiel | provider et moteur précurseur existent | Étendre `GeopoliticalRiskEngine`, enrichir schéma/dédup et le brancher |
| VolatilityExpectationEngine | DVOL et Bollinger neutre existent séparément | Composer les moteurs existants, ajouter options disponibles |
| PositioningState multi-exchange | agrégateur et moteurs leverage existent séparément | Créer l'adaptateur décisionnel sur l'agrégat, pas une nouvelle collecte parallèle |
| CryptoLiquidity 7/30/90 | DefiLlama 1/7 existe | Étendre stockage/engine, réparer le filtrage de provenance |
| SystemicRisk + AI capex | absent | Nouveau domaine, optionnel et non directionnel seul |
| Graphe causal/convergence | absent | À créer avant Decision V2 |
| ContradictionResolver | ancien `ContradictionEngine` existe hors Future | L'étendre vers les cinq familles et le brancher |
| Horizons indépendants | événements filtrés mais familles partagées | Recalculer facteurs, decay, scénarios et qualité par horizon |
| Invalidation spécifique | texte générique | Produire des conditions structurées depuis facteurs et seuils observés |
| Timeline attente/surprise | champs absents du payload | Étendre additivement le contrat |
| DecisionDataQuality | couverture générale seulement | Ajouter qualité décisionnelle et cap de confiance |

## 6. Plan exact d'implémentation proposé

Le plan ci-dessous préserve le modèle `FutureEvent`, les cinq familles, les routes et
les garde-fous Lot 1. Chaque étape doit être livrée avec migration additive, test
anti-fabrication, freshness runtime et provenance.

### Étape A — Assainir les entrées critiques avant d'ajouter des signaux

1. Empêcher toute fixture ou fichier `example*` d'entrer dans un runtime
   `MOCK_MODE=false` ; déplacer les exemples hors du répertoire scanné en production.
2. Modifier le filtre synthétique pour exclure observation par observation, sans jeter
   les données réelles voisines.
3. Définir une identité ETF unique `(asset, ticker, date)` indépendante de la source,
   une règle d'autorité et une quarantaine pour imports manuels non vérifiés.
4. Séparer le provider d'import manuel de la chaîne automatique ; faire de Farside ou
   d'un provider licencié vérifié le chemin courant, avec `UNAVAILABLE` si tous
   échouent.
5. Ajouter `observed_at`, `age_seconds` et `freshness` aux lectures DVOL ; interdire à
   une DVOL stale de rendre une famille disponible.
6. Exiger prix/OHLCV critiques courants pour BUY/SELL ; sinon
   `INSUFFICIENT_DATA`, sans modifier les seuils directionnels existants.
7. Corriger les contrats incohérents (`AVAILABLE` avec `unavailable_reason`, `as_of=now`
   sur une mesure ancienne).

Fichiers principaux : `providers/registry.py`, `config/providers.yaml`,
`providers/etf/*`, `db/repo.py`, `engines/analysis_context.py`,
`engines/implied_volatility.py`, `engines/future_context.py`.

### Étape B — Attentes de marché et surprise point-in-time

1. Étendre `MarketExpectationEngine` au lieu de le remplacer.
2. Ajouter un modèle/table `MarketExpectation` append-only avec event_id, observed_at,
   distribution, source/tier, méthodologie et fraîcheur ; conserver chaque évolution.
3. Valider d'abord le contrat légal/technique d'une source officielle ou licenciée.
   Garder CME/FedWatch optionnel ; sans URL/clé/distribution complète : `UNAVAILABLE`.
4. Créer `EventSurpriseEngine` avec quatre sorties séparées : rate, communication,
   projection, overall ; aucune règle fixe hike=bad/cut=good.
5. Associer actual/consensus/communication seulement à des publications officielles et
   à leur timestamp de disponibilité, pour éviter le look-ahead.
6. Propager expectation/pricing/surprise à la timeline, aux scénarios, au gate et aux
   explications.

Fichiers : `future_events/models.py`, modèles DB/repository,
`engines/market_expectation.py`, nouveau `engines/event_surprise.py`, collectors et
routes Future.

### Étape C — Renforcer les moteurs de données existants

1. Institutionnels : ajouter `flow_1d`, tendance et persistence à
   `InstitutionalFlowEngine`; garder 3/5/20, accélération et reversal ; rendre SOL
   disponible seulement si une vraie source le couvre.
2. Whales : brancher `whales.transfers` dans scheduler/persistance, enrichir la
   taxonomie custody, produire `WhaleTransferInterpretation`, puis agréger sans traiter
   montant brut comme direction. Documenter coût, clé, couverture, historique,
   attribution et licence de chaque provider avant activation.
3. Énergie : créer `EnergyMacroEngine` sur WTI/Brent et sources EIA/IEA/OPEP
   autorisées, avec inventaires/production/disruptions et une contribution conditionnée
   par la chaîne inflation/taux/conditions financières.
4. Géopolitique : étendre le modèle concret avec sévérité, canaux, régions, effets,
   source_count/quality ; renforcer la déduplication cross-source ; appeler le moteur
   prospectif depuis le contexte Future.
5. Volatilité : composer DVOL, realized vol, ATR et Bollinger existants dans
   `VolatilityExpectationEngine`; ajouter skew/term structure/expiries uniquement si une
   source réelle les fournit ; contribution Bollinger directionnelle strictement zéro.
6. Positionnement : faire consommer à un nouvel adaptateur `PositioningState` le
   snapshot Binance/Bybit/OKX existant, ses percentiles, basis, HHI et anomalies ;
   distinguer crowding et direction de liquidation potentielle, sans inventer de volume
   liquidé.
7. Liquidité crypto : étendre DefiLlama aux fenêtres 7/30/90, dynamiques USDT/USDC et
   liquidité exchange seulement si mesurée ; ne jamais en faire seul un signal d'entrée.
8. Systémique : ajouter `SystemicRiskEngine` avec stress financier, spreads, courbe,
   VIX/Treasury vol/concentration ; sous-module AI capex strictement fondé sur données
   financières sourcées et incapable de déclencher SELL seul.

### Étape D — Causalité, convergence et contradictions

1. Créer les contrats `CausalFactor`, `CausalEdge`, `CausalChain` et
   `MarketCausalGraph`, avec identifiants de preuve et relations `source`, `derived_from`
   et `confirms`.
2. Transformer les sorties des moteurs en facteurs causaux sans perdre le lien vers les
   observations et événements.
3. Dédupliquer les dérivés d'une même chaîne avant agrégation ; par exemple un choc
   énergie et ses conséquences inflation/taux ne comptent qu'une confirmation causale.
4. Créer `SignalConvergenceEngine` et exposer `independent_confirmation_count` et
   `causal_chain_count`.
5. Étendre l'ancien `ContradictionEngine` en `ContradictionResolver` pour les cinq
   familles, avec état `SIGNALS_MIXED`, explication des deux côtés et capacité à forcer
   WAIT lorsqu'une contradiction forte est établie.

Cette étape doit précéder tout nouveau calcul global ; autrement l'ajout des sources
créera précisément le double comptage que le Lot 2 interdit.

### Étape E — Decision Engine V2 et horizons indépendants

1. Étendre le moteur Future ou ajouter une façade compatible `DecisionEngineV2` ; ne
   pas supprimer `buy_opportunity`.
2. Produire direction, amplitude, event risk, causalité, contradiction, convergence et
   qualité dans un contrat unique.
3. Ajouter les nuances `SLIGHTLY_BEARISH/SLIGHTLY_BULLISH` et mapper additivement les
   niveaux de risque demandés sans casser les anciennes valeurs.
4. Calculer séparément chaque horizon : requête des événements, fenêtres des facteurs,
   decay, graphes, scénarios, contradiction, qualité et décision. Ne partager que le
   même timestamp/fingerprint, pas un snapshot analytique 30 jours.
5. Créer `DecisionDataQuality` avec couverture, freshness, qualité source et inputs
   critiques manquants ; utiliser ce résultat pour plafonner la confiance et refuser
   BUY/SELL en absence de données critiques.
6. Produire `decision_invalidation` depuis les facteurs concrets et leurs conditions de
   renversement, au maximum trois conditions réellement actionnables.

### Étape F — API et interfaces

1. Étendre de façon additive `/api/future/{symbol}` avec attentes, surprises, causal
   chains, convergence, contradictions, data quality et invalidations.
2. Limiter `/why` à trois-cinq facteurs réellement décisionnels et trois conditions
   d'invalidation, avec timestamp et provenance de chaque élément.
3. Ajouter à `/timeline` heure locale, market expectation et potential surprise ;
   conserver `null/UNAVAILABLE` sans vraie distribution.
4. Mettre à jour React et Flutter sur le même contrat, avec états explicites
   LIVE/STALE/UNAVAILABLE et sans fallback fictif.
5. Auditer ou retirer de l'usage décisionnel toute ancienne probabilité heuristique.

### Étape G — Validation obligatoire

Ajouter les tests demandés par la consigne, notamment : attentes pricées/non attendues
et stale, surprise, reversal ETF, taxonomie whale, causalité pétrole, dédup géopolitique,
Bollinger neutre, amplification de volatilité, crowding long/short, contraction
stablecoin, anti-double-comptage, convergence indépendante, contradictions, qualité,
indépendance des horizons, invalidation, provenance, absence de fabrication, absence de
fixtures, fraîcheur et anti-look-ahead.

Puis exécuter :

- suite backend complète, lint et typage ciblé ;
- type-check/build React ;
- analyse/tests Flutter ;
- audit manuel LIVE BTC/ETH/SOL 24h/7j/30j, avec vérification source par source et
  réponse explicite à la question de l'information qu'un analyste raisonnable aurait
  vue mais que le moteur manque.

Le livrable d'implémentation `docs/future-first-lot2-implementation.md` et l'audit LIVE
`docs/lot2-live-decision-audit.md` ne doivent être créés qu'après cette implémentation,
pas pendant la Phase 0.

## 7. Ordre de réalisation et critères de passage

Ordre recommandé : **A → B → C → D → E → F → G**.

Critères pour quitter chaque étape :

- aucune fixture/import d'exemple dans le chemin production ;
- aucune donnée stale ne peut rendre une famille courante disponible ;
- toute probabilité a une source, une méthode et un `observed_at` ;
- toute donnée absente reste `UNAVAILABLE` ;
- un signal dérivé ne compte pas comme confirmation indépendante ;
- une contradiction matérielle reste visible et peut influencer l'action ;
- les sorties 24h/7j/30j sont recalculées indépendamment ;
- aucune dépendance payante n'est obligatoire ;
- la totalité des garde-fous et tests Lot 1 reste verte.

## 8. Conclusion de Phase 0

Le Lot 2 doit être une extension du socle actuel, mais il ne peut pas commencer par
ajouter davantage de sources au score. Il doit commencer par assainir provenance et
fraîcheur, puis rendre opérationnelles les briques déjà présentes, avant d'introduire
le graphe causal, la convergence et Decision Engine V2.

**STOP Phase 0 : aucune implémentation fonctionnelle n'est effectuée dans cet audit.**
