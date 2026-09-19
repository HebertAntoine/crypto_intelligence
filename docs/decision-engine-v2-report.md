# Moteur de décision à six familles — rapport

Signaux analytiques internes à l'application, jamais des ordres d'exécution.

## 1. Audit de l'existant

| Élément | État trouvé | Suite |
|---|---|---|
| `FutureDecisionEngine`, 5 familles, `EventRiskGate`, validateur de cohérence, `EdgeEngine` | EXISTANT | Réutilisés ; leurs constats alimentent les nouveaux garde-fous |
| `ChiefMarketAnalyst` + analystes spécialisés (`analysts/`) | EXISTANT | Non modifiés (chemin rapport LLM) |
| `FutureEvent`, calendriers Fed / BLS / BEA / Trésor | EXISTANT | Réutilisés |
| Calendriers BCE et BoJ | **EXISTANT MAIS NON BRANCHÉ** — déclarés au registre, absents de `providers.yaml` et du collecteur : 0 événement en base | Branchés : 19 décisions BCE, 16 réunions BoJ |
| Calendrier BLS (dates CPI / emploi) | **DONNÉES INDISPONIBLES** — `bls.gov` renvoie 403 à ce serveur | Non contourné ; voir §5 |
| FRED (taux, CPI, liquidité) | **NON BRANCHÉ** — clé absente, CSV public injoignable ; les séries `macro.us10y`, `macro.cpi`… ne contenaient que des fixtures | Remplacé par les sources primaires officielles (§4) |
| Fixtures `MOCK FIXTURES` dans la base de production | **DONNÉES FACTICES** — 978 lignes, horodatées jusqu'à une semaine dans le futur, pouvant passer pour la dernière valeur | Supprimées après sauvegarde ; le mode mock utilise désormais une base séparée |
| Stockage point-in-time (`core/pointintime.py`, `history/store`) | EXISTANT — délais de publication, 9 ans de bougies, 6 ans de funding, OI Bybit, DVOL, macro Yahoo | Réutilisé pour la vue unique live / backtest |
| Flux ETF (`etf_flows`, 12 fonds BTC, 11 ETH, depuis 2024) | EXISTANT | Réutilisé ; aucun ETF pour SOL → non applicable |
| Structure de marché causale (`MarketStructureEngine`, swings) | EXISTANT | Réutilisé tel quel (live et backtest) |
| Indicateurs (RSI, ATR, Bollinger, moyennes, volatilité réalisée) | EXISTANT | Réutilisés |
| Baleines / flux on-chain | **INDISPONIBLE** — aucune source sans clé payante | Famille déclarée indisponible, rien n'est estimé |
| Liquidations | **INDISPONIBLE** | Déclarées indisponibles, rien n'est simulé |
| Décision 7 j interne et résumé par horizon | **INTERPRÉTATION INSUFFISANTE** — ne recevaient pas l'état d'avantage, contrairement à la route API | Corrigé |
| Gate d'événement | **INTERPRÉTATION INSUFFISANTE** — bloquait dès qu'un événement critique tombait dans l'horizon (la Fed bloquait 30 j presque en permanence) | Gate gradué (§6) |
| Passe complète de 19 h | Sautée quand la passe légère tenait le verrou | Corrigé la veille |

## 2. Ce qui a été ajouté

- **Sources officielles sans clé** (`providers/macro/official_us.py`) : Trésor US (courbe nominale 2 / 10 / 30 ans et courbe réelle 10 ans), Daily Treasury Statement (TGA), Fed de New York (RRP, EFFR), Fed H.4.1 (actif total, WALCL), BLS (CPI, CPI sous-jacent, chômage, emplois, salaires). Chaque point porte sa date de publication (`available_at`).
- **Rattrapage historique** (`crypto-intel backfill-official`) : taux 2019-2026, TGA 2019-2026 (deux formats du Trésor), RRP, EFFR, offre de stablecoins.
- **Vue point-in-time** (`engines/pit_view.py`) : une seule porte vers les données, pour le live et le backtest.
- **Configuration centrale** (`engines/decision_config.py`) : pondérations par horizon, familles critiques, seuils, échelles, fiches des métriques.
- **Six familles notées** (`engines/decision_families.py`) : Macro & banques centrales, Liquidité, ETF & flux spot, Dérivés, On-chain & baleines, Technique & structure.
- **Garde-fous et décision** (`engines/decision_gates.py`) : sept garde-fous ordonnés, explication, conditions pour changer, facteurs de la home.
- **Backtest** (`backtest/decision_backtest.py`).
- **Page « Analyse complète »** et **détail par famille** (`app/lib/screens/full_analysis_page.dart`).

## 3. Logique

**Mesures.** Chaque mesure publie valeur, unité, date, date de publication, source, niveau de source, fraîcheur, qualité, confiance, valeur précédente, variation absolue et en %. Au-delà de son âge maximal : `STALE`, affichée datée, jamais utilisée comme valeur actuelle. Absente : `UNAVAILABLE`. Inexistante pour l'actif (ETF SOL, DVOL SOL) : `NOT_APPLICABLE`, sans pénaliser la qualité. Une source sociale n'est jamais utilisée comme signal.

**Familles.** Chaque famille combine plusieurs composantes ; chacune apporte un signal entre −1 et +1 (`tanh(variation / échelle de l'horizon)`) et un poids. Score −100 → +100, état (de TRÈS DÉFAVORABLE à TRÈS FAVORABLE, MIXTE, INDÉTERMINÉ), confiance, qualité, raisons, contradictions, conditions d'invalidation, valeurs clés. Une composante sans donnée n'apporte ni signal ni poids : elle réduit la couverture, donc la confiance ; sous 40 % de couverture la famille est `INSUFFICIENT_DATA`.

- **Macro** : taux réel 10 ans (poids fort), 10 ans et 2 ans (partiellement la même information, poids réduits), dollar, VIX, Nasdaq, pétrole **seulement** au-delà d'un choc (4 % / 8 % / 15 % selon l'horizon), inflation sous-jacente (3 mois annualisés contre 12 mois, hors 24 h). Le chômage est affiché, non noté : son effet est ambigu.
- **Liquidité** : bilan de la Fed, TGA, RRP (atténué près de zéro), stablecoins. Régime (EXPANDING → CONTRACTING, UNCERTAIN) lu par l'accord des composantes, affichées séparément ; l'indicateur « bilan − TGA − RRP » est descriptif uniquement.
- **ETF & flux** : flux cumulés sur 1 / 5 / 20 séances, comparés à l'historique de l'actif lui-même (z-score), série en cours, accélération ; pression spot. Les flux BTC ne touchent jamais ETH ou SOL.
- **Dérivés** : jamais l'open interest seul. Régime lu sur prix × OI × funding : longs encombrés, nouveaux longs, rachat de shorts, nouveaux shorts, shorts encombrés, désendettement. Funding noté seulement aux extrêmes (percentile sur les règlements 8 h). DVOL et base affichés.
- **Technique** : moyennes mobiles adaptées à l'horizon (H1 / H4 / D1), RSI, ATR, volatilité réalisée, largeur de Bollinger, structure confirmée (TREND_UP / DOWN, RANGE, BREAKOUT / BREAKDOWN PENDING / CONFIRMED, UNCLEAR), supports et résistances, dominance BTC pour ETH et SOL.

**Horizons.** Trois analyses calculées séparément : fenêtres (1 / 7 / 30 j), unités de temps, échelles et pondérations différentes. Pondérations initiales (24 h : macro 20, liquidité 10, flux 15, dérivés 25, on-chain 10, technique 20 ; 7 j : 20 / 15 / 20 / 15 / 15 / 15 ; 30 j : 25 / 25 / 20 / 5 / 15 / 10), renormalisées sur les familles disponibles.

**Garde-fous, dans l'ordre** : qualité des données (familles critiques absentes → DONNÉES INSUFFISANTES) · fraîcheur (famille critique périmée → ATTENDRE) · risque événementiel · incertitude (confiance < 50 %, ou aucun avantage mesurable) · contradictions (familles fortes des deux côtés) · levier et risque extrême (longs encombrés contre un achat, shorts encombrés contre une vente, DVOL au-delà du 95ᵉ percentile) · décision.

**Décision.** ACHETER : score ≥ +30, confiance ≥ 70 %, au moins 3 familles concordantes, aucun garde-fou bloquant. VENDRE : symétrique. Sinon ATTENDRE. Valeurs initiales, configurables, à valider par backtest. La confiance mesure la qualité et la cohérence des données ; elle n'est jamais présentée comme une probabilité.

## 4. Sources utilisées

| Famille | Source | Niveau |
|---|---|---|
| Taux nominaux et réels | U.S. Treasury, courbes quotidiennes | Officiel |
| TGA | U.S. Treasury, Daily Treasury Statement | Officiel |
| RRP, EFFR | Federal Reserve Bank of New York | Officiel |
| Bilan de la Fed | Federal Reserve, H.4.1 | Officiel |
| CPI, emploi, salaires | U.S. Bureau of Labor Statistics (API) | Officiel |
| Dollar, VIX, Nasdaq, S&P 500, pétrole WTI | Yahoo Finance | Données de marché |
| Stablecoins | DeFiLlama | Agrégateur |
| Flux ETF | Farside Investors | Agrégateur |
| Funding, OI, base, ratio long/short, bougies | Binance Futures / Binance | Exchange |
| OI historique | Bybit | Exchange |
| DVOL | Deribit | Exchange |
| Dominance BTC | CoinGecko | Agrégateur |
| Calendriers | Fed, BCE, BoJ, BEA, Trésor | Officiel |

## 5. Non disponible, et pourquoi

- **On-chain et baleines** (flux, réserves des plateformes, grosses transactions, MVRV, SOPR) : Glassnode, CryptoQuant et Whale Alert exigent une clé payante. Famille indisponible, exclue du calcul.
- **Liquidations** : aucune source publique fiable branchée.
- **Dates de publication du CPI et de l'emploi** : `bls.gov` refuse ce serveur (403) ; non contourné. Les valeurs arrivent par l'API BLS, mais le garde-fou événementiel ne voit pas venir un CPI ou un NFP.
- **PCE, Core PCE** : l'API BEA exige une clé ; la date de publication est connue (calendrier BEA), la valeur non.
- **Brent** : non disponible sans FRED ; le WTI le remplace.
- **Écarts de crédit** : FRED uniquement.
- **Historique du bilan de la Fed** : seule la publication courante du H.4.1 est lue ; l'historique se construit semaine après semaine.
- **ETF SOL** : aucun flux vérifié ; non applicable.

## 6. Garde-fou événementiel gradué

L'ancien gate bloquait dès qu'un événement critique non valorisé tombait dans l'horizon : sur 30 j, la Fed bloquait presque en permanence. Le nouveau pondère importance × proximité × amplitude × incertitude × exposition de l'actif. Au-delà de 0,6, blocage ; entre 0,3 et 0,6, blocage seulement si la confiance des autres signaux est sous 75 % ; en dessous, l'événement est signalé « à surveiller ». L'ancien gate reste calculé et publié. Aujourd'hui : PCE dans 11 j → risque 0,21, signalé, non bloquant.

## 7. Backtest (mars 2024 → août 2026, un pas par jour)

Même code que le live, données visibles seulement après leur publication. Le veto « aucun avantage mesurable » est **exclu** (c'est l'objet du test). Résultats bruts dans `data/backtests/decision_backtest_20260919.json`.

| Actif / horizon | ATTENDRE | ACHETER | VENDRE | ACHETER : rendement moyen / réussite | Toutes dates : moyenne / hausse |
|---|---|---|---|---|---|
| BTC 24 h | 826 | 52 | 24 | +0,01 % / 50 % | +0,04 % / 50 % |
| BTC 7 j | 841 | 41 | 20 | −0,01 % / 54 % | +0,32 % / 52 % |
| BTC 30 j | 840 | 39 | 23 | −1,74 % / 44 % | +1,31 % / 53 % |
| ETH 24 h | 860 | 37 | 5 | −0,50 % / 32 % | 0,00 % / 50 % |
| ETH 7 j | 868 | 29 | 5 | −0,28 % / 52 % | +0,14 % / 49 % |
| ETH 30 j | 872 | 18 | 12 | +21,2 % / 56 % | +0,82 % / 45 % |
| SOL 24 h | 857 | 37 | 8 | −0,23 % / 49 % | +0,03 % / 49 % |
| SOL 7 j | 849 | 46 | 7 | −2,02 % / 35 % | +0,29 % / 48 % |
| SOL 30 j | 865 | 34 | 3 | −11,1 % / 26 % | +0,63 % / 49 % |

Lecture :

- Le moteur reste en ATTENDRE 91 à 97 % du temps et change d'avis sur 3 à 13 % des jours : il est stable.
- **Ses appels ACHETER ne battent pas la moyenne.** Le seul cas favorable (ETH 30 j, 18 appels) repose sur trop peu de cas pour conclure. Les appels VENDRE de BTC 7 j (75 % de réussite, 20 cas) sont encourageants mais tout aussi insuffisants.
- **La confiance n'est pas calibrée** : une confiance plus haute ne s'accompagne pas d'une meilleure réussite. Sur 30 j, la direction du score se trompe plus souvent qu'elle n'a raison.
- Conclusion : **le veto « aucun avantage mesurable → ATTENDRE » est justifié et reste actif.** Les pondérations et les seuils n'ont pas été ajustés sur ces résultats : ce serait optimiser sur le passé.

## 8. Tests

- `test_decision_engine_v2.py` (30) — les 13 cas du §21 : donnée périmée, donnée absente jamais neutre, valeur invisible avant publication, Fed future sans direction, événement critique proche, 24 h ≠ 30 j, OI seul ≠ VENDRE, longs encombrés, ETF BTC sans effet sur ETH / SOL, on-chain sans source, source sociale, renormalisation, contradictions, données critiques absentes, fraîcheur, score proche de zéro, trois familles concordantes, VENDRE symétrique, veto d'avantage, ordre des garde-fous, confiance ≠ probabilité, explications bornées, gate gradué (36 h, 3 semaines, 5 jours selon la confiance, hors horizon), et le contournement du veto d'avantage.
- `test_official_us_sources.py` (7) — formats réels des cinq sources, dont l'ancien format du TGA.
- `test_decision_backtest.py` (4) — rendement futur depuis la dernière clôture connue, horizon incomplet non noté, pas de vision du futur, métriques.
- Flutter : home (explication du moteur ligne pour ligne, facteurs dans l'ordre du moteur, chiffres affichés), page complète (décision, confiance, avertissement, six familles, garde-fous), détail de famille (mesures, dates, sources, « Pourquoi ça compte »), famille indisponible déclarée comme telle.

Résultats : backend **1 872 passés**, 15 ignorés ; Flutter **382 passés** ; ruff et analyzer propres.

## 9. Défauts corrigés en route

- Fixtures synthétiques dans la base de production (978 lignes, dates futures).
- Calendriers BCE et BoJ déclarés mais jamais collectés.
- TGA avant avril 2022 ignoré (autre format du Trésor).
- Percentile du funding : égalités comptées « en dessous », puis mélange des règlements 8 h avec les instantanés live.
- Open interest horaire limité à quelques semaines : repli sur l'historique Bybit.
- Veto d'avantage absent quand l'ancien gate avait déjà dit ATTENDRE : un ACHETER aurait pu passer sans avantage mesuré.
- Décision 7 j interne et résumé par horizon privés de l'état d'avantage.
- Variation en % d'une base proche de zéro (« +39 % »), désormais en points de base.
- Libellés : valeur de la TGA présentée comme niveau de liquidité, « Tendance » en double, titres d'événements en anglais.

## 10. Limites restantes

- Aucune composante n'a montré de pouvoir prédictif au backtest : l'état restera ATTENDRE tant que l'`EdgeEngine` ne mesure pas d'avantage.
- Pondérations, échelles et seuils sont des valeurs initiales, non calibrées.
- La confiance n'est pas calibrée (§7).
- Les événements futurs ne sont collectés que lorsque l'export démarre l'application ; le service API n'est pas actif en continu.
- Le graphique 15 min échoue dans l'export en processus (« Event loop is closed ») — préexistant.
