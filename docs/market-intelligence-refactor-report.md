# Refonte de l'intelligence marché BTC / ETH / SOL

Date : 19/09/2026.

## 0. Audit (avant modification)

| Point | Constat |
|---|---|
| Moteurs fonctionnels | 6 familles scorées (point-in-time), 7 verrous, validation statistique (veto « pas d'avantage mesurable »), présentation séparée du calcul. |
| Sources connectées | Bougies Binance depuis 2017 (1 h / 4 h / 1 j), funding et OI (Binance, Bybit), DVOL Deribit, flux ETF Farside, taux et liquidité officiels US (Trésor, NY Fed, Fed H.4.1, BLS), calendriers Fed / BCE / BoJ. |
| Aucune clé API configurée | Alchemy, Helius, CME FedWatch, Glassnode, CryptoQuant, Whale Alert, Coinglass : indisponibles. Rien n'est simulé à leur place. |
| Valeurs calculées non utilisées | Taker ratio quotidien Binance (depuis 2017), exploité seulement en quotidien ; historique des halvings absent. |
| Erreurs d'interprétation corrigées | Résistance = dernier sommet confirmé, parfois **sous** le prix ; liquidations absentes ; aucune donnée banque centrale hors EFFR. |
| Unités | Niveaux techniques en $ (paire USDT), prix d'en-tête en € : chaque niveau affiché porte « $ ». |
| Provenance | Chaque mesure porte source, endpoint, horodatages (période / publication / collecte), unité, devise, qualité, confiance. Le nom du fournisseur n'est pas affiché à l'utilisateur. |

## 1. Six familles affichées

📊 Technique · 📈 Dérivés · 🪙 Flux spot · 🏛️ Macro & banques centrales · 🔄 Cycle Bitcoin / régime crypto · 🐋 Baleines & on-chain.
La liquidité reste un intrant du moteur, visible dans les données avancées de la Macro. Les flux ETF sont un sous-signal de contexte des flux spot (poids 0,35).

## 2. Nouvelles sources (sans clé, publiques ou officielles)

| Donnée | Source | Collecte |
|---|---|---|
| Achats / ventes agressifs horaires | Binance klines 1 h (quote et taker-buy quote), OKX rubik taker-volume 1 h (converti au prix de clôture horaire) | à chaque collecte (48 h glissantes ; 41 jours rétro-remplis) |
| Transactions spot en direct | Bybit `publicTrade` | service `crypto-intel-bybit-stream` (connexions sortantes uniquement) |
| Liquidations | Bybit `allLiquidation` | même service ; seules les heures couvertes ≥ 55 min comptent |
| Fed (fourchette cible), BCE (taux de dépôt), BoJ (taux au jour le jour, taux d'escompte de base) | NY Fed, ECB Data Portal, BoJ Time-Series API | collecte globale |
| Hauteur de bloc, halvings, rythme des blocs | mempool.space | collecte globale |

Anticipation du prochain taux : **aucune source de pricing (futures, OIS) n'est connectée**. L'application affiche « Anticipation de marché indisponible » et n'invente aucune valeur.

## 3. Moteurs ajoutés

- `engines/key_levels.py` : support clé et prochaine résistance tirés des grappes de pivots confirmés (4 h pour 24 h / 7 j, journalier pour 30 j), avec leur explication (« Résistance issue du sommet du 28/08/2026, testée 2 fois »).
- `spot_pressure` : pression acheteurs / vendeurs agrégée sur les plateformes couvrant ≥ 90 % de la fenêtre, comparée à son propre historique, tendance par rapport à la fenêtre précédente.
- `liquidation_totals` : 1 h / 4 h / 24 h, dominance longs / shorts, contexte de risque uniquement.
- `central_banks` : taux en vigueur, dernière décision (déduite de la série officielle, datée à la réunion), prochaine réunion, importance dynamique (CRITICAL à moins de 48 h).
- `engines/bitcoin_cycle.py` + famille `cycle` : phase descriptive tirée de plusieurs critères (écart à l'ATH, tendance 200 jours, rebond, halving). Pour ETH et SOL : régime Bitcoin et force relative face à BTC, jamais un cycle de halving propre.

## 4. Décision : verrous puis confirmations

Ordre : qualité des données → fraîcheur → risque événementiel → régime de marché → validation statistique → structure & point d'entrée → contradictions → levier → confirmation au comptant → décision finale.

- ACHETER exige une structure qui tient, une entrée non étirée et non collée à une résistance, un comptant non vendeur et au moins 3 familles concordantes **hors cycle**.
- VENDRE exige en plus une cassure structurelle, des vendeurs à l'initiative et un contexte macro ou régime dégradé.
- Le cycle ne compte jamais comme confirmation indépendante et son signal est plafonné (±0,4).
- Poids par horizon : le cycle pèse 2 % à 24 h, 5 % à 7 j, 15 % à 30 j ; le funding instantané ne pèse que 5 % à 30 j.
- Le veto « pas d'avantage mesurable → ATTENDRE » est inchangé ; aucun seuil existant n'a été modifié pour faire passer un test.

## 5. Validation finale (19/09/2026, 9 lectures)

Toutes les lectures sont ATTENDRE à cause du veto de validation, mais les raisons diffèrent réellement selon l'horizon, par exemple pour BTC :

- 24 h : résistance proche (81 479 $, à 0,2 %) et **vendeurs** à l'initiative au comptant (48 % d'achats agressifs).
- 7 j : **acheteurs** légèrement dominants (52 %), mais marché étiré (RSI 74) et résistance proche.
- 30 j : taux réels en forte hausse, rachat de shorts, cycle en « Post-ATH / récupération ».

ETH 7 j et SOL 7 j : longs encombrés (risque élevé).

## 6. Tests

`tests/unit/test_decision_presentation.py` (29 tests) couvre les dix régressions interdites du §29 ainsi que les niveaux clés, la couverture des plateformes, les liquidations partielles, les parseurs officiels, la vente conditionnée à une cassure et l'achat bloqué par des vendeurs au comptant.
Backend : 1901 réussis, 15 ignorés. Flutter : 382 réussis.
