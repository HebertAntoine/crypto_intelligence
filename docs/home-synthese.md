# Home : synthèse décisionnelle

La Home raconte la situation, puis laisse approfondir. Aucun moteur n'a été reconstruit : cette refonte agrège, hiérarchise, interprète et présente ce qui existait déjà.

## 1. Audit de l'existant, réutilisé tel quel

| Besoin de la mission | Déjà présent | Réutilisé pour |
|---|---|---|
| Décision et verrous | `decision_gates` (gates, `to_buy`, `to_worsen`) | verdict, ce qu'on attend, ce qui changerait la décision |
| Niveaux, structure, RSI | famille technique (moteur de structure) | première phrase du résumé, freins, niveaux |
| Macro par composant, avec signal et delta | famille macro | déclencheurs possibles et freins |
| Flux ETF, séries d'entrées, pression spot | famille flux | phrase « demande institutionnelle », rôle |
| Liquidations, funding, open interest | famille dérivés | amplificateur, levier |
| Cycle | famille cycle | contexte |
| Événements datés, importance, direction | `FutureEvent`, `EventCandidate` | contexte, calendrier, « attention ≠ sens » |
| Traduction en langage clair | `engines/interpretation.py` (refonte précédente) | cartes, détails, familles |
| Sources, fraîcheur, périodes | `MetricReading` | fiche détaillée d'une raison |

Nouveau fichier : `engines/situation.py` (le résumé et les rôles). Rien d'autre n'a été créé côté moteur.

## 2. Ordre de la Home

1. Actif et prix (24 h / 7 j)
2. **Décision** : ACHETER / ATTENDRE / VENDRE / DONNÉES INSUFFISANTES, avec l'horizon et une phrase courte
3. **🧭 Résumé de la situation** (4 à 6 phrases) + les rôles : déclencheurs possibles, amplificateur, ce qui freine, contexte
4. **🔎 Pourquoi ?** — 3 raisons au plus, chacune cliquable
5. **👀 Ce qu'on attend** — 1 à 3 conditions concrètes
6. **🔀 Ce qui changerait la lecture** — plus positif / plus prudent, invalidation
7. Fiabilité des données ≠ clarté du marché, horizon, « Attendre depuis… »
8. **Les familles** : Technique, Dérivés, Flux spot, Macro, Cycle, et 🐋 on-chain déclarée
9. **Événements à surveiller** (3 au plus)
10. **Analyses avancées** : « Pourquoi le marché monte ? », chaque ligne ouvrant sa page

## 3. Le résumé de la situation

Chaîne : ce que le prix vient de faire → avec quoi cela coïncide → ce que montrent les flux → ce qui a amplifié → ce qui freine → pourquoi la décision.

**Quatre rôles, jamais confondus :**

| Rôle | Ce que c'est | Exemple de formulation |
|---|---|---|
| Déclencheur possible | un facteur qui a bougé dans le même sens | « Ce mouvement coïncide avec la détente du pétrole, ce qui réduit la pression inflationniste attendue. » |
| Amplificateur | un effet mécanique qui prolonge un mouvement déjà en cours | « La fermeture forcée de positions vendeuses (61 M$ sur 24 h) a mécaniquement amplifié la hausse. » |
| Contexte | ce qui entoure : échéance à venir, cycle | « Adjudications du Trésor US dans 21 h » |
| Frein | ce qui empêche la confirmation | « un mouvement déjà étiré, un levier tendu » |

**Règles de langue :**
- « coïncide avec », « s'accompagne de », « peut contribuer à » pour une corrélation ;
- « a mécaniquement amplifié » réservé aux liquidations forcées, où le mécanisme est l'ordre lui-même, et seulement du bon côté (shorts liquidés pendant une hausse) ;
- aucun facteur aligné → « Aucune cause dominante ne ressort des données : plusieurs facteurs coïncident avec le mouvement sans qu'une explication unique puisse être établie » ;
- le mot « parce que » n'apparaît jamais dans le résumé (testé).

## 4. Au clic sur une raison

Une feuille s'ouvre avec :
- l'explication en langage clair ;
- les **données** (valeur, variation, période) ;
- **pourquoi cela compte** ;
- **ce que nous surveillons** ;
- l'**impact sur la décision** (POSITIF / NÉGATIF / MIXTE / INCONNU) et l'**horizon** ;
- la **source**, sa date et sa fraîcheur, avec « ⚠️ non actualisée » au-delà de deux jours.

Tout vient des lectures déjà calculées par les familles ; rien n'est recalculé pour l'affichage, et une mesure sans source n'est pas listée.

## 5. Événements : attention ≠ direction

Chaque échéance porte deux informations distinctes :
- **attention** : critique, élevée, modérée, faible ;
- **sens** : favorable, défavorable, partagé, ou « inconnu tant que le résultat n'est pas publié ».

Une décision de banque centrale peut donc être « Attention critique · sens inconnu ». Aucune règle automatique du type « baisse de taux = hausse » n'existe.

## 6. La famille 🐋 on-chain

Aucune source on-chain robuste n'est branchée aujourd'hui. Plutôt que de la masquer — ce qui laisserait croire que les baleines ont été mesurées et sont calmes — la carte est affichée et déclarée : « Source non branchée · Rien n'est déduit de l'activité des grandes adresses ». Elle redeviendra une famille mesurée dès qu'une source le permettra.

## 7. Tests

`tests/unit/test_situation.py` :
- le résumé nomme le mouvement, ses coïncidences, l'amplificateur, les freins et la décision ;
- chaque facteur garde son rôle (un amplificateur n'est jamais listé comme déclencheur) ;
- des liquidations du mauvais côté ne sont pas un amplificateur ;
- sans facteur aligné, aucune cause n'est revendiquée ;
- une séance ETF isolée n'est pas une tendance ;
- une échéance attendue est suivie de « puis la réaction du marché » ;
- six phrases au plus, jamais « parce que ».

`app/test/home_five_second_test.dart` : le résumé est affiché avant les raisons, les raisons avant ce qu'on attend, et une raison ouvre ses chiffres, ses sources et leur fraîcheur.

## 8. Les trois niveaux de lecture

- **10 secondes** : décision, phrase courte, résumé.
- **1 minute** : pourquoi, ce qu'on attend, ce qui changerait la décision.
- **5 à 10 minutes** : chaque raison et chaque famille ouvrent leur page détaillée.

## 9. Reste à faire

- Les catalyseurs propres à l'actif (réactions de marché déjà mesurées par `asset_catalysts`) ne sont pas encore repris dans le résumé : il faudrait les faire passer jusqu'au moteur de décision.
- Les pages Macro, ETF, Dérivés, On-chain et Technique commencent par « En bref » depuis la refonte précédente ; l'ordre de priorité interne des pages Macro (Fed, inflation, pétrole, taux…) reste à ajuster.
- La page Cycle garde sa mise en page propre.
