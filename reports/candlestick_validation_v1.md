# Validation statistique — `candlestick_v1`

Commit de départ : `1617602`. Les définitions n'ont **pas** été touchées :
mesurer v1 telle quelle est la condition pour qu'une v2 signifie quelque chose.

## La question posée, et les deux qu'elle n'est pas

| Question | Réponse | Où |
|---|---|---|
| La forme est-elle un produit de l'arithmétique ? | permutation + bootstrap par blocs | PHASE 37 et ci-dessous |
| La bougie correspond-elle à sa définition ? | 35 tests de forme | PHASE 37 |
| **Ce qui suit apporte-t-il une information ?** | **contrôles appariés** | **ici** |

Les confondre est l'erreur que cette phase existe pour éviter. Le test de
permutation ne dit **pas** « le marteau fonctionne ». Il dit seulement à quel
point sa fréquence dépend de la structure de la série.

## Méthode

### Contrôles appariés

Un marteau apparaît **par définition** après une baisse. Comparer ses
rendements à ceux de toutes les bougies mesurerait surtout le rebond qui suit
une baisse — un effet réel, mais qui n'appartient pas au marteau.

Chaque occurrence est donc appariée à **jusqu'à dix** situations comparables
**sans** la figure :

| Variable d'appariement | Tolérance |
|---|---|
| Actif | identique |
| Unité de temps | identique |
| Percentile d'ATR sur 250 barres glissantes | ± 0,15 |
| Tendance préalable, en ATR sur 5 barres | ± 0,5 ATR |

Toutes causales : elles ne décrivent que ce qui précède la barre. Un
appariement qui lirait le futur choisirait les contrôles selon leur résultat.

Les barres portant **une** figure quelconque sont exclues du vivier : un
contrôle qui est lui-même un marteau ne contrôle rien.

### Le sens est déclaré avant la mesure

`EXPECTED_DIRECTION` vit dans la taxonomie, hors du module de mesure. Le
rendement directionnel vaut `rendement × sens attendu` : positif signifie « la
théorie a eu raison », pour une figure haussière comme pour une baissière.

Sans cela, on serait tenté de lire un rendement négatif après un marteau comme
« la figure marche à l'envers » — c'est-à-dire de choisir l'hypothèse après
avoir vu le résultat. Un test vérifie que le sens déclaré correspond à la
famille annoncée, pour les vingt figures.

Les cinq figures d'indécision — doji, toupie — ne sont **pas évaluées** : la
théorie ne leur prête aucun sens, donc un rendement directionnel n'aurait pas
de définition.

### Horizons et mesures

1, 3, 5, 10 et 20 barres. Pour chacun : rendement moyen et médian de la figure
et de ses contrôles, différence, taille d'effet (d de Cohen), intervalle à 95 %
**sur la différence**, test de Welch, MFE et MAE.

Aucune de ces valeurs n'entre dans la reconnaissance. Un test vérifie
qu'aucun composant de définition ne porte un nom évoquant le futur.

### Correction pour tests multiples

Vingt figures × quatre unités × trois actifs × cinq horizons : plusieurs
centaines de tests. Benjamini-Hochberg est appliqué **sur l'ensemble**, pas
figure par figure — corriger par figure laisserait passer par construction une
poignée de faux positifs, exactement ceux qu'on aurait envie de retenir.

### Taille d'échantillon

| N | Statut | Ce qu'on s'autorise |
|---|---|---|
| < 30 | `INSUFFICIENT_DATA` | rien |
| 30 – 99 | `EXPLORATORY` | regarder, pas conclure |
| ≥ 100 | `TESTABLE` | conclure sous réserve du hors-échantillon |

Un résultat très net sur sept cas n'est pas un résultat. `edge_state` réutilise
`PatternEdgeState`, l'énumération déjà présente dans le projet — aucune n'a été
créée.

## Le bootstrap par blocs renverse la conclusion précédente

La permutation simple donnait des rapports de 976× et sept figures à **zéro**
occurrence. J'avais écrit que ces chiffres ne devaient pas être lus comme des
découvertes. Le bootstrap par blocs le démontre.

Un bloc mobile conserve des tranches réelles de l'historique : à l'intérieur
d'un bloc, l'enchaînement des bougies survit — donc le regroupement de
volatilité aussi. Quatre tailles, **toutes rapportées** : choisir après coup
celle qui arrange serait le contraire d'une mesure.

| Figure | Barres | Réel /1000 | bloc 5 | bloc 10 | bloc 20 | **bloc 50** |
|---|---:|---:|---:|---:|---:|---:|
| Étoile du matin | 3 | 3,96 | 69,4× | 11,7× | 3,7× | **1,32×** |
| Trois corbeaux noirs | 3 | 2,04 | 72,7× | 14,4× | 4,8× | **1,85×** |
| Trois soldats blancs | 3 | 3,28 | — | 19,3× | 7,7× | **2,47×** |
| Étoile du soir | 3 | 3,62 | 21,3× | 4,9× | 2,2× | **1,62×** |
| Ligne perçante | 2 | 8,03 | 31,6× | 4,9× | 2,5× | **1,49×** |
| Couvert sombre | 2 | 8,82 | 6,5× | 4,2× | 2,5× | **1,53×** |
| Harami haussier | 2 | 19,68 | 8,8× | 3,9× | 2,2× | **1,38×** |
| Harami baissier | 2 | 22,05 | 2,8× | 2,0× | 1,8× | **1,31×** |
| Englobante haussière | 2 | 13,80 | 3,0× | 2,1× | 1,9× | **1,37×** |
| Englobante baissière | 2 | 14,81 | 0,9× | 1,3× | 1,5× | **1,28×** |
| Doji | 1 | 45,12 | 0,99× | 1,01× | 1,00× | **0,99×** |
| Toupie | 1 | 141,58 | 0,99× | 1,02× | 0,99× | **1,00×** |
| Marubozu haussier | 1 | 6,67 | 0,99× | 0,92× | 1,06× | **0,89×** |
| Marteau | 1 | 2,71 | 0,60× | 0,97× | 1,08× | **0,91×** |

**Le résultat.** Les rapports des figures multi-barres s'effondrent
monotoniquement quand les blocs s'allongent : 69× → 1,32× pour l'étoile du
matin, 72× → 1,85× pour les trois corbeaux. Les chiffres spectaculaires de la
permutation simple étaient **entièrement un artefact** de la destruction de la
mémoire locale. Avec des blocs de 50 barres, aucune figure multi-barres n'est
plus de 2,5 fois plus fréquente que dans un marché ayant la même dynamique
locale.

**Le contrôle tient.** Les figures d'une barre sans condition de tendance
restent à 1,00× sous les quatre tailles de blocs — comme sous la permutation.
Le test se valide donc sous les deux nuls.

**La dépendance à la taille de blocs est elle-même le résultat** : elle mesure
à quel point la conclusion repose sur l'hypothèse de mémoire. Toute figure
multi-barres y est sensible ; aucune figure d'une barre ne l'est.

---

# Résultats

**216 dossiers** — 18 figures directionnelles × 3 actifs × 4 unités —
**1 040 tests statistiques**.

## Le résultat principal

| État d'avantage | Dossiers |
|---|---:|
| `NO_MEASURABLE_EDGE` | **115** |
| `INSUFFICIENT_DATA` | **101** |
| `POSITIVE_EDGE` | **0** |
| `NEGATIVE_EDGE` | **0** |
| `UNSTABLE` | **0** |

**Aucune figure de chandelier n'a d'avantage démontré** contre des situations
de contexte comparable, sur BTC, ETH et SOL, en 1 sem., 1 j, 4 h et 1 h.

Ce n'est pas « les chandeliers ne marchent pas ». C'est : *avec ces
définitions, sur ces trois actifs, sur cet historique, comparées à des
situations de même volatilité et de même tendance préalable, elles ne
distinguent rien de mesurable.*

## Un seul test sur 1 040 survit à la correction globale

| | |
|---|---|
| Figure | **Englobante baissière**, BTC, 1 j, horizon 20 barres |
| Occurrences | N = 43 (dossier : 45) |
| Contrôles appariés | 439 |
| Rendement directionnel de la figure | **+4,36 %** |
| Rendement des contrôles | **−6,00 %** |
| Différence | **+10,36 %** |
| Taille d'effet | d = 0,61 |
| IC 95 % sur la différence | [+5,99 %, +14,74 %] |
| p | 1,8 × 10⁻⁵ |
| **État retenu** | **`INSUFFICIENT_DATA`** |

Lecture : vingt jours après une englobante baissière, le prix a **baissé** de
4,4 % ; dans des contextes comparables **sans** la figure, il a **monté** de
6,0 %. L'écart est net et l'effet est de taille moyenne.

**Et pourtant le dossier est classé `INSUFFICIENT_DATA`**, parce que N = 45
< 100. C'est la règle de taille d'échantillon qui refuse de le promouvoir, et
c'est le système qui fonctionne comme prévu. Un seul survivant sur 1 040 tests
est **exactement ce qu'on attend du hasard** avec une correction à 5 % : la
correction laisse passer ce qu'elle est censée laisser passer.

## Le hors-échantillon achève la question

Le rendement directionnel à 5 barres, mesuré sur trois fenêtres chronologiques
disjointes (50 % / 25 % / 25 %) :

| | Dossiers |
|---|---:|
| **Le signe s'inverse** entre les fenêtres | **87** |
| Le signe tient sur les trois | 29 |
| Total suivi (N ≥ 30) | 116 |

**Trois quarts des effets apparents changent de sens selon la période.** Un
effet qui s'inverse n'est pas un avantage faible : c'est du bruit qu'on a
regardé sous un seul angle.

Les 29 signes stables sont eux-mêmes minces — les plus nets portent sur
n = 13 à 30 occurrences dans la fenêtre de test.

## Le cas de référence : le marteau

*« Le Hammer est-il utile sur BTC 4H ? »*

**HAMMER — `candlestick_v1`**

| | |
|---|---|
| Définition | petit corps en haut, ombre basse ≥ 60 % de l'amplitude, ombre haute ≤ 15 %, **après une baisse ≥ 1 ATR** |
| Occurrences BTC 4 h | **N = 72** |
| Statut d'échantillon | `EXPLORATORY` |
| Comparaison | 720 contrôles de volatilité et tendance comparables |
| 1 barre | −0,051 % (p = 0,82) |
| 3 barres | −0,499 % (p = 0,20) |
| **5 barres** | **−0,918 %** (d = −0,22, p = 0,108) |
| Hors-échantillon | non testé — N < 30 par fenêtre |
| **Avantage** | **`NO_MEASURABLE_EDGE`** |

Sur les trois actifs et quatre unités :

| Actif | Unité | N | Statut | 5 barres | Avantage |
|---|---|---:|---|---:|---|
| BTC | 1 sem. | 1 | insuffisant | — | `INSUFFICIENT_DATA` |
| BTC | 1 j | 8 | insuffisant | −5,04 % (p = 0,34) | `INSUFFICIENT_DATA` |
| BTC | 4 h | 72 | exploratoire | −0,92 % (p = 0,11) | `NO_MEASURABLE_EDGE` |
| BTC | 1 h | 267 | **testable** | +0,12 % (p = 0,35) | `NO_MEASURABLE_EDGE` |
| ETH | 4 h | 78 | exploratoire | +0,21 % (p = 0,75) | `NO_MEASURABLE_EDGE` |
| ETH | 1 h | 344 | **testable** | −0,06 % (p = 0,63) | `NO_MEASURABLE_EDGE` |
| SOL | 1 j | 7 | insuffisant | **+5,35 %** (p = 0,23) | `INSUFFICIENT_DATA` |
| SOL | 4 h | 49 | exploratoire | −0,80 % (p = 0,46) | `NO_MEASURABLE_EDGE` |
| SOL | 1 h | 207 | **testable** | −0,13 % (p = 0,59) | `NO_MEASURABLE_EDGE` |

Le +5,35 % sur SOL en quotidien est le genre de chiffre qui ferait un titre.
Il repose sur **sept occurrences**. C'est précisément pourquoi le statut
d'échantillon existe.

Sur les trois échantillons réellement testables — 1 h, 207 à 344 occurrences —
l'effet vaut **+0,12 %, −0,06 %, −0,13 %**. Les signes ne s'accordent même pas
entre actifs.

## Vue d'ensemble par figure (5 barres, toutes vues)

| Figure | N total | Vues | Diff. min | Diff. max | Signes |
|---|---:|---:|---:|---:|---|
| Harami baissier | 5 398 | 12 | −4,18 % | +15,23 % | 6+ / 6− |
| Harami haussier | 5 173 | 12 | −4,07 % | +5,69 % | 5+ / 7− |
| Englobante baissière | 3 516 | 12 | −33,23 % | +3,57 % | 5+ / 7− |
| **Englobante haussière** | 3 308 | 12 | −13,58 % | −0,00 % | **0+ / 12−** |
| Ligne perçante | 2 517 | 10 | −16,55 % | +0,46 % | 3+ / 7− |
| Couvert sombre | 2 385 | 12 | −22,28 % | +27,65 % | 7+ / 5− |
| Doji libellule | 1 965 | 10 | −3,08 % | +14,70 % | 5+ / 5− |
| Marubozu haussier | 1 728 | 11 | −9,42 % | +2,73 % | 6+ / 5− |
| Doji pierre tombale | 1 603 | 12 | −10,30 % | +3,41 % | 7+ / 5− |
| Marteau | 1 041 | 9 | −5,04 % | +5,34 % | 4+ / 5− |
| Étoile du matin | 916 | 11 | −11,86 % | +3,50 % | 5+ / 6− |
| Étoile du soir | 879 | 12 | −20,93 % | +6,43 % | 7+ / 5− |
| **Trois soldats blancs** | 572 | 11 | −0,78 % | +17,87 % | **8+ / 3−** |
| Trois corbeaux noirs | 508 | 9 | −3,29 % | +5,74 % | 5+ / 4− |

Presque toutes oscillent autour de zéro avec des signes partagés. Deux méritent
d'être notées, et pour des raisons opposées.

**L'englobante haussière est négative sur les douze vues.** Douze fois sur
douze, le prix fait moins bien après la figure qu'après un contexte comparable
sans elle. Aucun de ces tests ne survit à la correction globale, et
l'amplitude va de −0,00 % à −13,58 % — mais l'unanimité du signe est le fait le
plus notable de tout ce tableau. **Ce n'est pas un signal de vente** : c'est une
piste, et elle contredit la théorie, ce qui la rend d'autant plus suspecte
d'artefact.

**Les trois soldats blancs sont positifs 8 fois sur 11**, avec un maximum de
+17,87 %. Aucun test ne survit non plus.

## Ce qui dépend fortement de quoi

**De l'unité de temps** — massivement :

| Unité | Occurrences | Dossiers testables (N ≥ 100) |
|---|---:|---:|
| 1 sem. | 170 | **0 / 54** |
| 1 j | 1 115 | **0 / 54** |
| 4 h | 6 479 | 21 / 54 |
| 1 h | 27 234 | **54 / 54** |

**Aucune figure de chandelier n'est testable en quotidien ni en hebdomadaire**
sur cet historique. Les analyses les plus citées de la littérature portent
justement sur ces unités-là — et nous n'avons pas de quoi les trancher.

**De l'actif** — peu : BTC 26, ETH 25, SOL 24 dossiers testables. Les
occurrences se répartissent équitablement.

## Résumé demandé

**Figures avec signal potentiel** — aucune au sens strict. Deux pistes à
surveiller, ni l'une ni l'autre significative après correction :
l'**englobante haussière** (négative 12/12, contre la théorie) et les **trois
soldats blancs** (positifs 8/11).

**Figures sans avantage mesurable** — 115 dossiers, dont **toutes** celles qui
sont réellement testables : marteau, pendu, étoile filante, marteau inversé,
haramis, englobantes, ligne perçante, couvert sombre, étoiles, soldats et
corbeaux en 1 h sur les trois actifs.

**Figures à données insuffisantes** — 101 dossiers, soit toutes les unités
quotidienne et hebdomadaire, plus la moitié du 4 h.

**Dépendance forte à l'unité** — totale : 0 dossier testable au-dessus de 4 h.

**Dépendance forte à l'actif** — faible.

---

# Ce que cette phase n'a pas fait

- **Aucun seuil n'a été touché.** 10 %, 34 %, 60 %, 0,5 ATR : `candlestick_v1`
  est mesurée telle quelle. Une v2 réglée sur ces résultats ne voudrait rien
  dire.
- **Aucun signal de décision n'a été branché.** Le moteur d'opportunité, le
  timing et la conviction globale sont inchangés. Cette phase produit des
  **preuves**, pas des ordres.
- **Rien n'est branché sur `/chart`.** Les 148 588 occurrences historiques n'y
  apparaissent pas.
- **GARCH n'a pas été fait.** Le bootstrap par blocs suffisait à renverser la
  conclusion précédente, et il ne dépend d'aucun modèle paramétrique.
- **15 min non évalué** — le calcul des contrôles appariés y devient trop
  coûteux à cette échelle. Ce n'est pas une lacune de méthode mais de temps
  machine, et c'est l'unité où le bruit de microstructure domine de toute façon.

# Limites que je ne masque pas

- **Les tolérances d'appariement sont des choix** : ± 0,15 de percentile d'ATR,
  ± 0,5 ATR de tendance. Trop serré, aucun contrôle ; trop lâche, on compare
  des contextes différents. Rien ne les a validées.
- **L'appariement ne contrôle que deux variables.** Volume, position dans le
  range, régime de marché plus large : non contrôlés.
- **Le test de Welch suppose des observations indépendantes.** Des occurrences
  rapprochées dans le temps ne le sont pas. Le projet possède
  `event_sampler.sample_independent_events` ; il n'est pas branché ici, et
  l'ignorer rend les p-valeurs **optimistes**. Comme le résultat est déjà
  « rien », cette limite ne change pas la conclusion — elle la renforcerait.
- **Un seul horizon suivi en hors-échantillon** (5 barres), pour rester lisible.

# Vérifications

```
55 tests candlesticks     dont 20 nouveaux pour cette phase
1135 tests backend        passés
ruff check                propre
mypy --python-version 3.13  0 erreur sur candlesticks/
```

Anti-lookahead, quatre garanties testées : aucun composant de définition ne
porte de mesure future ; une détection est inchangée quand on retire les barres
postérieures ; les variables d'appariement calculées sur un préfixe sont
identiques à celles de la série complète ; un contrôle n'est jamais lui-même
une figure détectée.

# Réponse à la question de départ

*« Une figure de chandelier correctement reconnue apporte-t-elle une
information statistique sur ce qui se produit ensuite ? »*

**Sur ce périmètre, non.** 216 dossiers, 1 040 tests, zéro avantage démontré,
un seul test survivant à la correction — et son dossier est trop mince pour
compter. Trois quarts des effets apparents s'inversent selon la période
observée.

Et la question précédente s'éclaire aussi : le bootstrap par blocs montre que
les fréquences spectaculaires des figures multi-barres étaient un artefact du
test nul. Une fois la mémoire locale préservée, aucune n'est plus de 2,5 fois
plus fréquente qu'attendu.

C'est un résultat négatif, obtenu proprement. Il vaut mieux que 148 588
détections présentées comme une réussite.
