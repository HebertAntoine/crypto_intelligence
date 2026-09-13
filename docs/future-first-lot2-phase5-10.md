# Future-first Lot 2 — Phases 5 à 10

Date de l'audit : 13 septembre 2026. Périmètre livré : attentes de marché,
surprise, baleines, risque événementiel et briques causales. Les décisions
existantes et leurs seuils n'ont pas été modifiés. `DecisionEngineV2` n'est pas
implémenté.

## 1. Comportement corrigé d'EventRisk

### Cause du `LOW` généralisé

Avant cette phase, le champ public `event_risk` sérialisait directement le
résultat de `EventRiskGate`. Or le gate ne cherche que les événements critiques,
à amplitude `HIGH/EXTREME`, incertains et situés dans les 48 prochaines heures.
En l'absence d'un tel événement imminent, son niveau était `LOW`, y compris
quand six ou huit événements matériels existaient dans l'horizon. Le résultat
était cohérent avec le gate, mais ne mesurait pas la quantité de risque demandée.

### Contrats désormais séparés

- `EventRiskEngine` répond à « quelle quantité de risque événementiel existe
  dans cet horizon ? » et n'impose aucune action.
- `EventRiskGate` répond à « faut-il forcer `WAIT` maintenant ? ».
- L'API expose `event_risk` et `event_risk_gate` séparément. Le moteur existant
  ne force `WAIT` que sur `event_risk_gate.active`.

Le calcul est général, sans cas spécial FOMC :

```text
proximité = 1 - distance_de_l'événement / durée_de_l'horizon
sévérité = 0,50 × importance + 0,35 × amplitude + 0,15 × incertitude
contribution = proximité × sévérité
matérialité = 1 - produit(1 - contribution_i)
```

Un événement hors horizon contribue zéro. Les événements 24 h, 7 j et 30 j
sont donc filtrés et pondérés indépendamment. Une attente absente ou périmée
vaut incertitude maximale, pas probabilité inventée. Les bornes de taxonomie
`LOW/MODERATE/HIGH/EXTREME` sont transparentes ; elles ne sont ni une
probabilité de marché ni une calibration décisionnelle. `EXTREME` exige aussi
au moins un événement à amplitude `EXTREME`.

Snapshot post-correction à 12:53–12:55 UTC :

| Actif | 24 h | 7 j | 30 j | Gate |
|---|---:|---:|---:|---|
| BTC | `LOW`, 0 événement, 0,000 | `HIGH`, 6, 0,963 | `HIGH`, 8, 0,999 | `NOT_TRIGGERED` |
| ETH | `LOW`, 0 événement, 0,000 | `HIGH`, 6, 0,963 | `HIGH`, 8, 0,999 | `NOT_TRIGGERED` |
| SOL | `LOW`, 0 événement, 0,000 | `HIGH`, 6, 0,963 | `HIGH`, 9, 0,999 | `NOT_TRIGGERED` |

Le FOMC était encore à environ 77 heures : matériel en 7 j et 30 j, mais hors
du gate de 48 heures. SOL possède en plus, dans le risque 30 j, un élément de
protocole non planifié issu d'une source Solana.

## 2. Méthode réelle choisie pour les attentes de marché

La méthode retenue pour la Fed est l'API REST FedWatch officielle et licenciée,
pas le HTML de la page publique. CME indique que le flux est dérivé des futures
30-Day Fed Funds, propose l'end-of-day à partir de 25 USD/mois, un flux
intraday toutes les 60 secondes et un historique depuis 2015 :
[CME FedWatch API](https://www.cmegroup.com/market-data/market-data-api/fedwatch-api.html).

Le connecteur `CmeFedWatchProvider` :

- exige simultanément `CME_FEDWATCH_API_URL` et `CME_FEDWATCH_API_KEY` ;
- accepte seulement une distribution complète, sourcée et timestampée ;
- refuse de réparer une distribution partielle ;
- normalise chaque ligne en `MarketProbability`, puis la fusionne avec
  l'événement officiel FOMC sans remplacer sa provenance primaire ;
- n'effectue aucun scraping HTML.

La reconstruction depuis les futures a été étudiée, mais pas implémentée. Les
données historiques CME DataMine sont des fichiers achetés et soumis à
entitlement, accessibles par API authentifiée :
[CME DataMine API](https://www.cmegroup.com/datamine/datamine-api.html).
Une reconstruction robuste demanderait aussi de figer les contrats, le taux
effectif déjà réalisé dans le mois, les dates de réunion et les règles de
transition entre fourchettes. Sans source live licenciée pour tous ces inputs,
elle serait une approximation opaque. Le cas reste donc `UNAVAILABLE`.

La redistribution et les produits dérivés de données CME peuvent nécessiter
une licence adaptée au cas d'usage :
[CME Derived Data Services](https://www.cmegroup.com/market-data/browse-data/derived-data.html).
Le projet ne suppose aucun droit de redistribution.

`MarketExpectationEngine` produit exactement : identifiant événement,
`observed_at`, issue la plus probable, distribution, probabilité de cette issue,
timestamp de probabilité, incertitude, source, méthode, fraîcheur et statut.
L'incertitude est l'entropie de Shannon normalisée. `market_probability` est la
probabilité maximale fournie par la source, jamais un nouveau chiffre calculé.
La fraîcheur par défaut est `LIVE` jusqu'à 15 minutes, `RECENT` jusqu'à 6 heures,
puis `STALE` ; l'âge maximal peut être explicitement adapté par appel.

## 3. Données réellement disponibles pour le priced-in

État de configuration contrôlé localement, sans afficher de secrets :

- aucune URL/clé CME FedWatch autorisée n'est configurée ;
- aucun événement du snapshot ne porte une distribution de marché complète ;
- les huit événements macro sont donc `MarketExpectation.UNAVAILABLE` sur les
  trois actifs et tous les horizons ;
- aucune probabilité n'a été reconstruite depuis un titre, un consensus textuel
  ou le HTML FedWatch ;
- DVOL BTC/ETH est une mesure de volatilité implicite, pas une probabilité
  d'issue macro, et n'est pas présenté comme du `priced-in` événementiel.

Conclusion : le moteur et le connecteur autorisé existent, mais les données
`priced-in` réellement utilisables dans le snapshot sont **zéro**.

## 4. EventSurpriseEngine

`EventSurpriseEngine` consomme une attente pré-événement valide et une issue
réellement observée. Les canaux sont séparés :

- `probability_surprise = 1 - P(issue réellement observée)` ;
- `numeric_surprise = actual_numeric - expected_numeric` lorsque l'unité est
  comparable ;
- `directional_surprise` n'existe que si un adaptateur de domaine fournit une
  table directionnelle explicite ;
- `communication_surprise`, `projections_surprise` et `guidance_surprise`
  restent des inputs structurés distincts ;
- `overall_surprise` résume la magnitude maximale des canaux disponibles et
  `overall_direction` leur signe net.

Le moteur ne contient aucune règle `rate hike = bearish` ou `rate cut = bullish`.
Une décision de taux conforme à 90 % peut donc produire une faible surprise de
taux, tandis qu'un communiqué plus restrictif peut produire une surprise de
communication négative. Aucun fournisseur d'issue post-événement n'étant encore
branché, la brique est prête et testée mais n'émet pas de surprise live.

## 5. Providers whales étudiés

Recherche effectuée sur les documentations et conditions officielles disponibles
le 13 septembre 2026.

| Provider | Accès et coût observé | Fréquence et historique | Méthodologie utile | Licence/stabilité |
|---|---|---|---|---|
| Whale Alert | Clé développeur. Alerts WebSocket : 29,95 USD/mois, usage personnel. REST Enterprise : 699 USD/mois. | Temps réel ; Enterprise 500 appels/minute et 90 jours ; historique complet sur Enterprise+ sur devis. | Transactions enrichies, prix et attribution `from/to`; BTC, ETH et SOL couverts. | Schéma JSON officiel et changelog : stabilité élevée, mais profondeur d'attribution dépend du plan. [Documentation officielle](https://developer.whale-alert.io/api-account/documentation). |
| CryptoQuant | Bearer token. On-chain à partir de Professional, affiché à 99 USD/mois ; Premium affiché à 799 USD/mois. | Professional : 120 appels/minute, 500k crédits/mois, un an ; Premium : 800/minute, historique complet. Résolution on-chain selon plan. | `exchange-whale-ratio` = dix plus gros inflows / inflows totaux ; flux exchanges et entités. | REST officiel stable, mais une métrique agrégée ne prouve pas une vente et les clusters doivent être archivés point-in-time. [API et plans](https://www.cryptoquant.com/apis), [définition du ratio](https://userguide.cryptoquant.com/api/btc-flow-indicator). |
| Glassnode | Clé API réservée au plan Professional avec add-on API ; tarif de l'add-on non public sur la documentation consultée. | Live + historique ; limite standard annoncée 600 requêtes/minute, crédits par combinaison de paramètres. | Inflow, outflow et balance d'exchange, séries agrégées. | Infrastructure officielle robuste ; accès et historique dépendent de l'entitlement. [Introduction API](https://docs.glassnode.com/basic-api/api), [crédits et limites](https://docs.glassnode.com/basic-api/api-credits). |
| Arkham | Accès sur demande/essai, clé et abonnement à crédits ; prix public précis non trouvé. | REST et données d'entités/transferts ; fréquence, limites et profondeur fixées par souscription. | Modèle entity-first, attribution assortie d'une confiance, labels évolutifs. | Bon candidat pour transferts attribués, mais schéma live non vérifié sans compte. Usage interne, non transférable et frais régis par la souscription. [Guide API](https://arkm.com/docs), [conditions API](https://arkm.com/api-terms-of-service). |

Le projet n'exige pas plusieurs abonnements. Chaque adaptateur est conditionnel
et l'agrégateur accepte zéro, un ou plusieurs fournisseurs.

## 6. Providers réellement utilisables

### Dans le code

- Whale Alert : connecteur REST Enterprise, découverte de hauteur par
  `/{blockchain}/status`, lecture `/{blockchain}/transactions`, normalisation
  BTC/ETH/SOL et conservation de l'attribution/provenance.
- CryptoQuant : connecteur conditionnel du ratio de dépôts baleines, Bearer
  token, fenêtres et limite explicites, avec caveat point-in-time.
- Glassnode : connecteur conditionnel existant pour inflow/outflow/balance.
- Arkham : présence déclarée, mais échec explicite `NOT_CONFIGURED` même avec
  une clé tant que le mapping n'a pas été validé contre un compte réel. Aucun
  schéma n'est deviné.

### Dans le runtime audité

Aucune clé Whale Alert, CryptoQuant, Glassnode ou Arkham n'est configurée.
Donc : zéro provider actif, `whale_intelligence = UNAVAILABLE`, aucune direction
de baleines injectée. Whale Alert serait le connecteur de transfert directement
utilisable après souscription/clé et test contractuel live ; CryptoQuant et
Glassnode sont utilisables pour leurs métriques agrégées après entitlement.

## 7. WhaleIntelligenceEngine

L'interface `WhaleProvider.normalize(payload)` retourne une liste de
`WhaleObservation`. Le modèle normalisé conserve : actif, heure, montant natif
nullable, montant USD nullable, entités, types d'entités, type de transaction,
provider, confiance et liste de provenances.

Types supportés : `WALLET`, `EXCHANGE`, `CUSTODY`, `ETF`, `MINER`, `PROTOCOL`,
`UNKNOWN`.

Interprétation :

- `WALLET -> EXCHANGE` : pression vendeuse **potentielle** ;
- `EXCHANGE -> WALLET/CUSTODY` : accumulation **potentielle** ;
- `EXCHANGE -> EXCHANGE`, `WALLET -> WALLET` et direction inconnue : neutres
  directionnellement ;
- une seule transaction ne peut pas déclencher un état `STRONG_*` ;
- `is_certainty` reste toujours faux.

Les sorties sont `STRONG_ACCUMULATION`, `ACCUMULATION`, `NEUTRAL`,
`DISTRIBUTION`, `STRONG_DISTRIBUTION` ou `UNAVAILABLE`. En l'absence de transfert
attribué, la sortie est `UNAVAILABLE`, jamais `NEUTRAL`.

La déduplication utilise `asset + transaction_hash + transaction_type` lorsque
le hash existe, sinon une empreinte stable des attributs disponibles. Les
provenances de doublons multi-provider sont fusionnées et le montant n'est
compté qu'une fois. Une correction complémentaire empêche désormais un montant
USD historique de masquer l'absence de `amount_asset` : le natif reste `null`.

## 8. Validation d'InstitutionalFlowEngine

Le moteur existant n'a pas été réécrit. Les fenêtres utilisent des séances
publiées, pas des jours calendaires remplis artificiellement. L'état de régime
reste fondé sur 20 séances si disponibles ; une séance isolée ne l'écrase pas.
Les sorties ajoutées sont le cumul 1 séance, la persistance, `FLOW_REVERSAL` et
la détérioration.

| Actif | 1 séance | 3 séances | 5 séances | 20 séances | Accélération/séance | Reversal | Persistance | État |
|---|---:|---:|---:|---:|---:|---|---|---|
| BTC | -13,2 M$ | -416,1 M$ | -288,1 M$ | +3 310,1 M$ | -424,97 M$ | `INFLOW_TO_OUTFLOW` | 4 sorties | `INFLOW`, détérioration vraie |
| ETH | +216,4 M$ | +221,2 M$ | +222,8 M$ | +1 920,5 M$ | +26,07 M$ | `NONE` | 1 entrée | `STRONG_INFLOW`, pas de détérioration |
| SOL | N/A | N/A | N/A | N/A | N/A | `UNAVAILABLE` | 0 | `UNAVAILABLE` |

La lecture BTC illustre précisément pourquoi le régime long ne doit pas être
confondu avec le flux actuel : le fond 20 séances reste positif mais le
retournement récent est mesuré. SOL reste N/A parce que le produit suivi
n'existe pas dans cette source ; il n'est pas transformé en neutre.

## 9. Validation volatility/options

L'intégration conserve les trois moteurs existants et leurs rôles :

- `VolatilityRegimeEngine` : ATR et volatilité réalisée ;
- `ImpliedVolatilityEngine` : DVOL et variance premium lorsqu'une série existe ;
- `ExpectedVolatilityEngine` : Bollinger bandwidth/squeeze et amplitude attendue.

Snapshot :

| Actif | ATR (% prix / percentile) | Réalisée 30 j annualisée | DVOL / percentile | Variance premium | Squeeze par horizon |
|---|---|---:|---|---:|---|
| BTC | 2,745 % / 10,7e | 48,43 % | 38,70 / 10,4e | -9,733 | 24 h non ; 7 j oui ; 30 j oui |
| ETH | 3,750 % / 10,7e | 75,39 % | 53,86 / 15,1e | -21,530 | 24 h non ; 7 j non ; 30 j oui |
| SOL | 4,537 % / 4,7e | 67,68 % | N/A | N/A | 24 h non ; 7 j oui ; 30 j oui |

DVOL disponible donne toujours `directional_bias=NEUTRAL` et
`direction_contribution=0`. Une DVOL élevée peut augmenter
`expected_movement`, jamais devenir automatiquement bearish. Un squeeze
Bollinger donne contribution directionnelle zéro mais amplitude attendue
positive. SOL sans indice DVOL Deribit reste entièrement N/A, valeurs
directionnelles incluses. `options_skew` et `term_structure` sont `null` pour
les trois actifs faute de séries configurées ; aucune approximation ne les
remplace.

## 10. MarketCausalGraph

Les modèles `CausalFactor`, `CausalEdge` et `CausalChain` imposent : identifiants
uniques, timestamps UTC, force/confiance bornées, provenance non vide, références
d'arêtes valides et absence de cycle. Les composantes faiblement connectées
forment des unités d'indépendance. Une arête n'existe que si un mécanisme a été
explicitement fourni ; la proximité ou le même signe ne suffisent pas.

Le moteur future actuel expose dans l'API un graphe de facteurs au niveau des
cinq familles. Aucun lien causal sourcé n'est encore fourni par le runtime :
les arêtes sont donc vides et `causal_chain_count=0` dans le snapshot. C'est
volontairement plus honnête que d'inventer une relation. Les tests couvrent la
chaîne Fed -> taux -> USD et démontrent qu'elle compte comme une confirmation,
pas trois.

## 11. SignalConvergenceEngine

La sortie expose : nombre de confirmations indépendantes, nombre de chaînes,
comptes bull/bear indépendants, force du mélange, réduction des confirmations
corrélées et détail des unités. Une composante causale compte au plus une fois ;
un facteur isolé reste sa propre unité. Les facteurs directionnels à confiance
effective nulle sont exclus du comptage.

Cette sortie est branchée dans l'API mais n'est pas consommée par la décision
existante. Dans le snapshot, les confirmations sont donc encore celles des
familles indépendantes faute d'arêtes live. La distinction est prête pour V2,
sans modifier V1.

## 12. ContradictionResolver

Les états sont `ALIGNED_BULLISH`, `ALIGNED_BEARISH`, `MIXED`,
`STRONGLY_MIXED`, `INSUFFICIENT_DATA`. La sortie contient les signaux de soutien,
les opposants, la famille dominante et les conflits indépendants. Elle ne
retourne aucune action.

Snapshot explicatif après exclusion des confiances nulles :

| Analyse | Résolution |
|---|---|
| BTC 24 h | `ALIGNED_BEARISH` : spot et positionnement bearish |
| BTC 7 j | `STRONGLY_MIXED` : flux institutionnels + technique bull contre positionnement bear |
| BTC 30 j | `STRONGLY_MIXED` : flux institutionnels bull contre positionnement bear |
| ETH 24 h | `ALIGNED_BEARISH` : spot et positionnement bearish |
| ETH 7 j / 30 j | `STRONGLY_MIXED` : flux institutionnels fortement bull contre positionnement bear |
| SOL 24 h / 7 j / 30 j | `ALIGNED_BEARISH` : spot et positionnement bearish ; technique de confiance nulle |

Deux défauts de présentation ont été corrigés sans effet sur les décisions :
un facteur à confiance zéro n'est plus un contre-signal, et il ne crée plus une
fausse `correlated_confirmation_reduction`.

## 13. Tests et validation

Tests obligatoires présents, avec les noms demandés : risque vs gate/proximité
et horizons, timestamps/missing/stale des attentes, trois canaux de surprise,
cinq cas baleines, reversal et journée isolée, Bollinger/DVOL/SOL, causalité,
convergence et contradictions. Deux régressions supplémentaires couvrent les
directions à confiance nulle et l'absence de quantité native Whale Alert.

Résultats finaux :

- ciblés Phases 5–10 + contrat API : **62 réussis en 1,04 s** ;
- future-first unitaire élargi : **84 réussis en 1,11 s** ;
- suite unitaire exhaustive en mode offline, hors fichier API bloqué :
  **1 198 réussis, 12 ignorés en 28,25 s** ;
- Ruff sur `backend` et `tests` : succès ;
- mypy ciblé sur 12 fichiers modifiés, Python 3.13 et imports externes ignorés :
  succès ; le `python_version=3.11` global rencontre sinon la syntaxe PEP 695
  d'une dépendance NumPy installée sous Python 3.13, pas une erreur des fichiers
  livrés ;
- build React (`tsc -b` + Vite) : succès, 64 modules ;
- Flutter : **308 tests réussis** ;
- `git diff --check` : succès.

La commande unitaire monolithique sans mode offline a été bornée à 15 minutes :
elle a atteint 53 % sans échec. Le ralentissement identifié est
`test_lot3_infra.py::TestHybridKnowledge::test_provenance_is_preserved`, qui
effectue des HEAD vers Hugging Face et applique des backoffs DNS ;
`HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1` le ramène à 2,84 s.

Sept tests de `tests/unit/test_lot6b_api.py` restent **non exécutés** : le
`TestClient` Starlette/AnyIO attend indéfiniment au démarrage avant le premier
appel. Le même problème bloque le groupe historique
`tests/integration/test_api_lot2.py`; le premier test isolé a été arrêté après
90 s. Le lifespan FastAPI appelé directement entre et sort en moins de 2 s :
le blocage se situe dans le portail de thread `TestClient`, avec FastAPI 0.141.1,
Starlette 1.6.0, AnyIO 4.15.0 et HTTPX 0.28.1. Ces tests ne sont pas déclarés
réussis et aucun échec fonctionnel d'endpoint n'a été observé.

## 14. Données encore UNAVAILABLE

- distributions `priced-in` de tous les événements : CME non souscrit/configuré ;
- issues post-événement live nécessaires à EventSurprise ;
- whale intelligence live : aucun provider payant configuré ;
- Arkham : mapping live volontairement non validé sans compte ;
- options skew BTC/ETH/SOL ;
- term structure options BTC/ETH/SOL ;
- DVOL/implied volatility SOL ;
- flux institutionnels/ETF SOL dans la source suivie : N/A, non applicable ;
- famille `catalysts_regulation` des neuf analyses : indisponible dans les
  fenêtres auditées ;
- arêtes causales live : aucune relation sourcée propagée vers le graphe.

## 15. Analyse détaillée des neuf décisions existantes

### Règle de décision à connaître

`FutureDecisionEngine` n'agrège pas les poids de la carte `MarketPressure`.
Il applique une priorité stricte : macro/catalyseurs (1), flux (2),
positionnement (3), technique (4). La première famille directionnelle
disponible de priorité supérieure détermine le biais. Les poids ci-dessous
expliquent la carte de pression, pas l'action future-first.

Les événements programmés communs sont : adjudications Treasury 13 et 26
semaines le 14 septembre, 6 semaines et 19 ans 11 mois le 15, FOMC critique
`HIGH` le 16, 9 ans 10 mois le 17, puis PCE critique `HIGH` et GDP le 30.
Il y en a 0 en 24 h, 6 en 7 j, 8 en 30 j. Les attentes de marché et baleines
sont manquantes partout ; le gate n'est déclenché nulle part.

### BTC — snapshot à 12:53:39 UTC, prix 76 738,79 USD, couverture 13/13

Valeurs communes : pression `SELL -27,0/100`. Institutions : poids 0,30,
score -28,81, contribution -9,60 ; latest -13,2 M$, 5 j -288,1 M$, 20 j
+3 310,1 M$. Spot : poids 0,25, ratio taker 0,4922, moyenne 5 j 0,4830,
base 90 j 0,4964, score -33,48, contribution -9,30. Dérivés : poids 0,20,
`LONG_LIQUIDATION`, OI 7 j -2,359 %, comptes longs 62,60 %, score -23,65,
contribution -5,26. Funding : poids 0,15, 0,0000539, percentile 37,8,
score -17,08, contribution -2,85. Baleines : poids théorique 0,10 mais retiré
du dénominateur car indisponible.

Structure : 1D bullish, 1W bearish, 4H/1H transition. Volatilité : ATR 2,745 %,
réalisée annualisée 48,43 %, DVOL 38,70 neutre directionnellement ; skew et
term structure absents.

| Horizon | Résultat et moteur déterminant | Facteurs, amplitude et oppositions |
|---|---|---|
| 24 h | `SELL / BEARISH / NORMAL`, confiance 0,49. Macro neutre ; flux bearish par agressivité spot, puis positionnement bearish. | 0 événement, risque `LOW`, gate off. Technique étiquetée bullish mais confiance 0 et squeeze faux : aucune contribution effective. Missing : catalyseurs, whales, attentes, skew/term. Le brief antérieur indiquait amplitude `HIGH`; le refresh live a fait disparaître le squeeze 1H et donne désormais `NORMAL`, sans changement de seuil ni d'action. |
| 7 j | `BUY / BULLISH / HIGH`, confiance 0,61. Le régime institutionnel `INFLOW` entre dans la famille flux de priorité 2 et domine. | 6 événements, risque 0,963 `HIGH`, gate off. Technique bullish 1D + squeeze, confiance 0,25, soutient. Positionnement bearish confiance 0,90 oppose. Contradiction `STRONGLY_MIXED`. Le 20 j positif coexiste avec reversal et détérioration récents : donnée dominante à nuancer. Missing identiques. |
| 30 j | `BUY / BULLISH / HIGH`, confiance 0,66. Même régime institutionnel de priorité 2. | 8 événements, risque 0,999 `HIGH`, gate off. Technique neutre, confiance 0,50, car 1D bull contre 1W bear ; squeeze n'ajoute que de l'amplitude. Positionnement bearish 0,90 oppose. Contradiction `STRONGLY_MIXED`. Missing identiques. |

### ETH — snapshot à 12:54:15 UTC, prix 2 476,03 USD, couverture 13/13

Pression `SLIGHT_SELL -18,5/100`. Institutions : poids 0,30, score +22,28,
contribution +7,43 ; 1 j +216,4 M$, 3 j +221,2 M$, 5 j +222,8 M$,
20 j +1 920,5 M$. Spot : poids 0,25, taker 0,4309, moyenne 5 j 0,4792,
base 90 j 0,4963, score -42,82, contribution -11,89. Dérivés : poids 0,20,
`NEW_SHORTS`, OI 7 j +3,858 %, comptes longs 75,17 %, score -49,15,
contribution -10,92. Funding : poids 0,15, 0,00005809, percentile 36,8,
score -18,48, contribution -3,08. Baleines indisponibles.

Structure : 1W/4H transition, 1D/1H range, aucun timeframe directionnel.
Volatilité : ATR 3,750 %, réalisée annualisée 75,39 %, DVOL 53,86 neutre ;
skew/term absents.

| Horizon | Résultat et moteur déterminant | Facteurs, amplitude et oppositions |
|---|---|---|
| 24 h | `SELL / BEARISH / NORMAL`, confiance 0,49. Sans flux ETF à cet horizon, spot bearish puis positionnement `NEW_SHORTS` bearish. | 0 événement, risque `LOW`, gate off. Technique porte un libellé bullish mais confiance 0, donc aucun contre-signal effectif. Missing : catalyseurs, whales, attentes, skew/term. |
| 7 j | `BUY / STRONGLY_BULLISH / HIGH`, confiance 0,56. `STRONG_INFLOW` institutionnel, priorité 2, domine. | 6 événements, risque 0,963 `HIGH`, gate off. Positionnement bearish 0,90 oppose à flux bull 0,90 ; technique confiance 0. Contradiction `STRONGLY_MIXED`. Les quatre fenêtres de flux sont positives, donc le fond économique est plus cohérent que BTC. Missing identiques. |
| 30 j | `BUY / STRONGLY_BULLISH / HIGH`, confiance 0,56. Même flux institutionnel. | 8 événements, risque 0,999 `HIGH`, gate off. Squeeze vrai augmente l'amplitude mais sa direction vaut zéro. Positionnement bearish oppose : `STRONGLY_MIXED`. Missing identiques. |

### SOL — snapshot à 12:55:06 UTC, prix 99,60 USD, couverture 11/11

Pression `SELL -49,2/100`, calculée sur 3/4 familles applicables. Institutions
ETF : N/A, retirées du dénominateur. Spot : poids 0,25, poids effectif 0,4167,
taker 0,4171, moyenne 5 j 0,4772, base 90 j 0,5003, score -57,96,
contribution -24,15. Dérivés : poids 0,20, effectif 0,3333, `NEW_SHORTS`,
OI 7 j +2,178 %, comptes longs 70,28 %, score -53,86, contribution -17,95.
Funding : poids 0,15, effectif 0,25, -0,000014, percentile 29,8, score -28,28,
contribution -7,07. Baleines indisponibles.

Structure : 1W/4H/1H transition, 1D range. Volatilité : ATR 4,537 %,
réalisée annualisée 67,68 %, DVOL N/A, skew/term absents.

| Horizon | Résultat et moteur déterminant | Facteurs, amplitude et oppositions |
|---|---|---|
| 24 h | `SELL / BEARISH / NORMAL`, confiance 0,49. Spot bearish de priorité 2 et positionnement bearish. | 0 événement, risque `LOW`, gate off. Technique bullish de confiance 0, non effective. Missing : catalyseurs, whales, attentes, toute volatilité implicite/options. ETF explicitement N/A. |
| 7 j | `SELL / BEARISH / HIGH`, confiance 0,56. Aucun ETF ne remplace le spot : flux et positionnement restent bearish. | 6 événements, risque 0,963 `HIGH`, gate off. Squeeze augmente l'amplitude, direction zéro ; aucune opposition effective. Contradiction `ALIGNED_BEARISH`. Missing identiques. |
| 30 j | `SELL / BEARISH / HIGH`, confiance 0,56. Même hiérarchie. | 8 macro + 1 élément protocole dans le risque, matérialité 0,999, gate off. Squeeze non directionnel ; aucune opposition effective. Missing identiques. |

## 16. Pourquoi le passage 24 h vers 7 j/30 j ?

### Pourquoi BTC passe-t-il de SELL 24H à BUY 7D ?

La divergence est d'abord une conséquence naturelle des horizons. À 24 h,
la famille flux n'utilise que l'agressivité spot récente, bearish. À 7 j, le
régime ETF/institutionnel sur 20 séances devient pertinent et `INFLOW`; cette
famille de priorité 2 détermine alors le biais avant le positionnement de
priorité 3. Le 1D bullish et le squeeze apportent aussi un soutien secondaire.

Mais le `BUY` est trop catégorique au regard des données actuelles : 3 j et 5 j
sont négatifs, quatre sorties persistent, l'accélération vaut -424,97 M$ par
séance et `INFLOW_TO_OUTFLOW`/détérioration sont vrais. Il ne s'agit pas d'un
poids numérique mal calibré dans la décision — les poids 0,30/0,25/etc. ne sont
pas utilisés par `FutureDecisionEngine` — mais d'un régime 20 séances trop
dominant dans une priorité stricte, aggravé par l'absence d'utilisation de la
résolution des contradictions. Conclusion : divergence économiquement
possible, horizon cohérent, mais signal BTC 7 j/30 j insuffisamment nuancé.

### Pourquoi ETH passe-t-il de SELL 24H à BUY 7D ?

Le mécanisme est le même, avec un fond plus solide : le 24 h reflète un taker
ratio très vendeur et de nouveaux shorts ; aux horizons 7/30 j, le régime ETF
devient `STRONG_INFLOW`. Contrairement à BTC, les cumuls 1/3/5/20 séances sont
tous positifs et l'accélération aussi. La divergence est donc économiquement
mieux justifiée et bien issue de l'indépendance des horizons.

Elle reste néanmoins `STRONGLY_MIXED` : positionnement bearish et flux
institutionnels bullish ont chacun 0,90 de confiance. V1 choisit malgré tout le
flux par priorité. V2 devra intégrer cette contradiction ou s'abstenir, mais
aucun seuil n'a été changé dans cette phase.

## 17. Défauts de logique découverts

Corrigés dans ce lot :

1. `event_risk` était en réalité le niveau du gate 48 h ; séparation effectuée.
2. Un facteur à confiance zéro pouvait être affiché comme contre-signal et
   gonfler la réduction corrélée ; il est désormais ignoré.
3. Un ancien payload whale uniquement en USD pouvait remplir artificiellement
   `amount_asset` avec des dollars ; il reste désormais `null`.
4. Une valeur whale inconnue pouvait être assimilée trop facilement à un wallet ;
   `UNKNOWN` reste inconnu, sauf libellé explicite « unknown wallet » conservé
   pour compatibilité historique.

Constats volontairement non corrigés avant V2 :

1. La décision par priorité ne consomme ni `FLOW_REVERSAL`, ni convergence, ni
   résolution des contradictions. C'est la cause du caractère catégorique des
   BUY BTC/ETH.
2. Le régime institutionnel 20 séances et le résumé 5 séances peuvent afficher
   simultanément `INFLOW` et un cumul négatif ; c'est factuellement exact mais
   demande une politique de détérioration dans V2.
3. La matérialité événementielle combine tous les événements listés. Des
   adjudications corrélées peuvent donc saturer le 30 j près de 1 ; le graphe
   causal n'est pas encore appliqué au risque. Le niveau `HIGH` est utile, la
   valeur 0,999 ne doit pas être lue comme une probabilité.
4. Le graphe live n'a aucune arête tant que les mécanismes sourcés ne sont pas
   propagés. Il empêche le double comptage lorsqu'une chaîne est fournie, mais
   ne déduit pas encore ces chaînes tout seul.
5. L'adaptateur CME est testé sur contrat synthétique représentatif, pas sur un
   compte entitled ; un test contractuel live est obligatoire avant production.
6. L'intégration Arkham demeure volontairement inactive sans validation réelle
   du schéma et de la licence.
7. Les tests `TestClient` historiques sont bloqués par la pile de test installée ;
   ce problème d'environnement/de dépendances doit être résolu séparément.

## 18. Plan proposé pour DecisionEngineV2 — non implémenté

1. Figer un contrat d'entrée point-in-time par horizon : qualité, fraîcheur,
   applicable/N/A, attentes, surprises, flux multi-fenêtres et provenance.
2. Transformer les observations atomiques en facteurs causaux, avec un registre
   explicite de mécanismes autorisés et des arêtes sourcées ; aucune arête par
   simple corrélation ou même direction.
3. Appliquer le gate critique avant tout score, puis utiliser `EventRisk` comme
   incertitude/amplitude, après regroupement causal des événements proches.
4. Construire des états institutionnels qui conservent simultanément régime,
   reversal, persistance et détérioration au lieu de choisir une seule fenêtre.
5. Faire de la convergence indépendante et des contradictions des entrées de
   décision réelles : un conflit fort doit réduire la conviction ou produire
   une abstention explicite, jamais être caché.
6. Séparer totalement direction, amplitude et confiance. DVOL, ATR et squeeze
   ne doivent jamais voter sur le signe.
7. Définir les règles/poids seulement par protocole de recherche pré-enregistré,
   walk-forward et calibration hors échantillon ; aucune optimisation destinée
   à retrouver les décisions souhaitées du snapshot.
8. Ajouter des tests de métamorphisme : une donnée manquante ne devient pas
   neutre, dupliquer une source ne renforce pas un signal, retourner un lien
   causal ne doit pas créer plusieurs confirmations.
9. Exécuter V2 en shadow mode à côté de V1, journaliser chaque divergence et
   attendre un nombre suffisant d'issues maturées avant toute promotion.
10. Corriger et verrouiller la pile `TestClient`, puis exiger suite unitaire et
    intégration exhaustives avant bascule.

**STOP : aucune ligne de `DecisionEngineV2`, aucun seuil décisionnel et aucune
décision existante n'ont été modifiés dans ce lot.**
