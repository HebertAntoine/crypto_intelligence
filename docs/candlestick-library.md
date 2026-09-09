# PHASE 37 — bibliothèque de figures de chandeliers

## Ce qui a été construit

Un paquet **entièrement séparé**, `backend/crypto_intel/candlesticks/`, qui ne
partage aucun type avec `structure/`.

```
candlesticks/
    taxonomy.py    20 figures, leurs familles, leur taille en barres
    anatomy.py     corps, ombres, amplitude, tendance préalable
    patterns.py    les détecteurs
    scan.py        balayage historique
    benchmark.py   le test nul par permutation
```

**20 figures** couvrant une, deux et trois barres :

| Barres | Figures |
|---:|---|
| 1 | doji, doji libellule, doji pierre tombale, marteau, pendu, marteau inversé, étoile filante, marubozu haussier, marubozu baissier, toupie |
| 2 | englobante haussière, englobante baissière, harami haussier, harami baissier, ligne perçante, couvert sombre |
| 3 | étoile du matin, étoile du soir, trois soldats blancs, trois corbeaux noirs |

## La séparation des deux taxonomies

Elle est **structurelle, pas documentaire** :

- deux paquets, deux énumérations, deux registres ;
- `CandlestickPattern` et les noms structurels sont disjoints, **vérifié par un
  test** qui échoue si un nom apparaît des deux côtés ;
- chaque détection publie `"taxonomy": "CANDLESTICK_PATTERN"` et une note qui
  interdit l'agrégation en toutes lettres ;
- `summarise()` refuse d'additionner les deux mondes.

La raison est mesurable, pas esthétique : un taux agrégé sur des figures d'une
barre et des figures de trois cents n'a aucun sens, et une matrice de confusion
qui compare un `HAMMER` à un `DOUBLE_TOP` compare deux objets qui ne peuvent pas
se substituer l'un à l'autre.

## Le point que la plupart des implémentations ratent

**Un marteau et un pendu ont exactement la même forme.** Seule la tendance qui
précède les distingue. Idem pour le marteau inversé et l'étoile filante.

Le contexte fait donc partie de la **définition**, pas de l'interprétation :

- la tendance est mesurée sur 5 barres **strictement antérieures**, en ATR
  (seuil 1,0 ATR) ;
- sans tendance nette, **aucun nom n'est émis** — la bougie est décrite mais
  pas nommée. Nommer sur la moitié d'une définition reviendrait à tirer au sort.

Trois tests figent ce comportement, dont le principal : **la même bougie,
à la même échelle**, devient `HAMMER` après une baisse et `HANGING_MAN` après
une hausse.

Un quatrième vérifie que la barre de la figure **n'entre jamais** dans le calcul
de sa propre tendance : une longue bougie créerait sinon la tendance qu'elle est
censée retourner.

## Deux écarts assumés aux définitions classiques

**Les gaps n'existent pas en crypto.** L'étoile du matin classique exige un trou
de cotation avant et après la bougie centrale. Sur un marché ouvert 24 h sur 24,
la clôture d'une barre est l'ouverture de la suivante. Exiger le gap ne
trouverait presque rien. Il est donc **facultatif mais enregistré** :
`components["gapped"]` dit s'il était là, pour qu'on puisse un jour mesurer si
sa présence change quelque chose.

**Les seuils sont déclarés en tête de module**, pas enfouis : corps d'un doji
≤ 10 % de l'amplitude, corps « petit » ≤ 34 %, ombre « longue » ≥ 60 %, ombre
négligeable ≤ 15 %, marubozu ≤ 5 %, corps « long » ≥ 0,5 ATR, pénétration ≥ 50 %.
Ce sont des **choix**, pas des mesures.

## Deux bugs trouvés par les tests

**Une bougie à quatre prix identiques devenait un marubozu.** Amplitude nulle →
`body_ratio()` renvoie 1 → la condition du marubozu était satisfaite par
accident. Ce n'est ni un doji parfait ni un marubozu : c'est une barre sans
information. Rejetée explicitement.

**Un couvert sombre était capté comme harami.** Les deux définitions se
recouvraient et la première écrite gagnait. « Harami » veut dire « enceinte » :
la seconde bougie doit être **nettement** plus petite, pas seulement contenue.
Seuil ajouté à 50 % du corps précédent.

Un troisième cas n'était pas un bug mais une notation mal calibrée : la toupie
était systématiquement sous le plancher de confiance parce que son second terme
ne pouvait structurellement pas atteindre 1. Recalibré sur un seuil déclaré.

## Ce que ça détecte

**148 588 figures** sur BTC, ETH, SOL et cinq unités.

| Figure | Barres | 1 sem. | 1 j | 4 h | 1 h | 15 min | Total |
|---|---:|---:|---:|---:|---:|---:|---:|
| Toupie | 1 | 160 | 1 252 | 7 482 | 27 095 | 22 643 | **58 632** |
| Doji | 1 | 48 | 399 | 2 421 | 8 811 | 6 942 | **18 621** |
| Harami baissier | 2 | 34 | 195 | 1 141 | 4 028 | 4 617 | **10 015** |
| Harami haussier | 2 | 22 | 174 | 1 052 | 3 925 | 4 732 | **9 905** |
| Englobante baissière | 2 | 22 | 131 | 653 | 2 710 | 3 435 | **6 951** |
| Englobante haussière | 2 | 12 | 122 | 594 | 2 580 | 3 318 | **6 626** |
| Ligne perçante | 2 | 4 | 71 | 426 | 2 018 | 2 596 | **5 115** |
| Marubozu haussier | 1 | 7 | 59 | 235 | 1 428 | 3 272 | **5 001** |
| Couvert sombre | 2 | 13 | 78 | 427 | 1 867 | 2 356 | **4 741** |
| Marubozu baissier | 1 | 7 | 19 | 168 | 1 159 | 3 091 | **4 444** |
| Doji libellule | 1 | 5 | 40 | 396 | 1 526 | 1 473 | **3 440** |
| Doji pierre tombale | 1 | 10 | 34 | 284 | 1 275 | 1 398 | **3 001** |
| Étoile du matin | 3 | 4 | 35 | 159 | 718 | 988 | **1 904** |
| Marteau | 1 | 3 | 24 | 199 | 818 | 775 | **1 819** |
| Étoile du soir | 3 | 6 | 32 | 153 | 688 | 915 | **1 794** |
| Étoile filante | 1 | 0 | 27 | 142 | 706 | 736 | **1 611** |
| Trois corbeaux noirs | 3 | 1 | 18 | 88 | 402 | 835 | **1 344** |
| Pendu | 1 | 7 | 18 | 160 | 554 | 582 | **1 321** |
| Trois soldats blancs | 3 | 10 | 29 | 111 | 423 | 740 | **1 313** |
| Marteau inversé | 1 | 3 | 9 | 91 | 409 | 478 | **990** |
| **TOTAL** | | **378** | **2 766** | **16 382** | **63 140** | **65 922** | **148 588** |

BTC 54 138 · ETH 52 297 · SOL 42 153.

Par famille : indécision 77 253, retournement haussier 29 799, retournement
baissier 29 434, continuation haussière 6 314, continuation baissière 5 788.

**Ces 148 588 ne s'ajoutent jamais aux 16 544 structures chartistes.** Ce sont
deux comptes, deux taxonomies, deux échelles.

## Le test nul, et pourquoi il a fallu en changer

Pour les structures chartistes, on compare à une marche aléatoire de même
volatilité. **Pour les chandeliers, ce serait mesurer surtout la qualité du
générateur** : il faudrait inventer une distribution de corps et d'ombres, et
les rapports diraient autant sur ce choix que sur le marché. Un premier essai
l'a confirmé — les marubozus ressortaient à 0,09× et les dojis à 2,43×, deux
chiffres qui décrivaient mon générateur.

**Le test retenu est une permutation.** On garde les vraies bougies — chacune
intacte, corps et ombres ensemble — et on mélange leur ordre. La distribution
des formes est préservée exactement ; seule la séquence disparaît.

### Le test se valide lui-même

Une figure d'une barre sans condition de tendance doit ressortir à **1,00×** :
sa fréquence ne dépend que de la distribution des formes.

| Témoin | Rapport |
|---|---:|
| Doji | 0,99× |
| Doji libellule | 0,96× |
| Doji pierre tombale | 1,01× |
| Marubozu haussier | 1,00× |
| Marubozu baissier | 0,96× |
| Toupie | 1,00× |

**Écart maximal : 0,04.** C'est le contrôle qui passe, pas une découverte — et
un test permanent échoue si cet écart dépasse 0,15.

### Ce que le test dit, et ce qu'il ne peut pas dire

| Figure | Barres | Tendance | Réel /1000 | Mélangé /1000 | Rapport |
|---|---:|---|---:|---:|---:|
| Étoile filante | 1 | UP | 3,05 | 2,29 | 1,33× |
| Marteau | 1 | DOWN | 2,71 | 2,90 | **0,94×** |
| Pendu | 1 | UP | 2,04 | 2,73 | **0,75×** |
| Marteau inversé | 1 | DOWN | 1,02 | 1,85 | **0,55×** |
| Englobante haussière | 2 | DOWN | 13,80 | 0,01 | 976× |
| Harami baissier | 2 | UP | 22,05 | 0,10 | 223× |
| Ligne perçante, couvert sombre, étoiles, soldats, corbeaux | 2-3 | — | — | **0,00** | — |

**Le résultat solide.** Les figures conditionnées par la tendance ne sont **pas
plus fréquentes** qu'après une séquence mélangée — 0,55× à 1,33×. La conjonction
« forme + tendance » n'a donc rien de particulier : de vraies tendances ne
précèdent pas ces bougies plus souvent que des séries de hausses ou de baisses
survenues au hasard.

**Le résultat qu'il ne faut PAS surinterpréter.** Sept figures multi-barres
n'apparaissent **jamais** en 70 744 barres mélangées, et deux autres ressortent
à 976× et 223×. Cela ne dit pas qu'elles sont remarquables : cela dit qu'elles
exigent que des bougies consécutives se ressemblent. Or le **regroupement de
volatilité** est le fait stylisé le plus robuste de la finance. Mélanger le
détruit, et n'importe quelle figure de deux ou trois barres devient quasi
impossible.

Le code refuse donc de les présenter comme des résultats : leur champ
`interpretable` vaut `false` et leur verdict est `REQUIRES_SEQUENCE`. **Un test
permanent échoue** si une figure multi-barres est un jour marquée lisible.

Mesurer correctement celles-là demanderait un test nul qui **préserve le
regroupement de volatilité** — bootstrap par blocs, ou simulation calibrée sur
un GARCH. Ce n'est pas fait, et je ne prétends pas l'avoir fait.

## Vérifications

```
35 tests nouveaux         dont le marteau/pendu, les deux bugs, l'anti-lookahead
1115 tests backend        passés
ruff check                propre
mypy --python-version 3.13  0 erreur dans candlesticks/
```

Anti-lookahead : une détection ne change pas quand on retire les barres
postérieures, et la tendance préalable ne lit jamais la barre de la figure.

## Limites

- **Aucun avantage mesuré.** `edge_state` vaut `NOT_YET_TESTED` sur les 148 588.
  Ces figures sont détectées, pas validées.
- **Les seuils sont des choix.** 10 %, 34 %, 60 %, 0,5 ATR : déclarés, versionnés
  (`candlestick_v1`), jamais mesurés.
- **Le test nul est muet sur les figures multi-barres.** C'est dit dans le code,
  dans l'artefact, et vérifié par un test.
- **Aucune géométrie dessinable.** Une figure de chandeliers publie ses
  horodatages de barres, pas de `PatternGeometry`. Suffisant pour surligner les
  bougies concernées ; insuffisant pour tracer autre chose.
- **Rien n'est branché sur `/chart`.** Le module existe et se mesure ; il
  n'apparaît nulle part dans l'application.
