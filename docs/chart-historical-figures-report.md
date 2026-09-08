# Balayage historique des figures — compte rendu

## Le problème

Les détecteurs lisaient `swings[-1]` et `swings[-2]` : **les deux derniers
pivots**. Posée une seule fois, au présent, la question « y a-t-il une figure ? »
ne peut renvoyer qu'une figure par détecteur. Neuf ans de bougies quotidiennes
donnaient donc le même petit lot que les quinze derniers jours, et le graphique
restait vide quel que soit le recul.

Ce n'était pas un problème de seuils. Assouplir les critères aurait produit des
figures fragiles au lieu de retrouver les vraies.

## Ce qui a été fait

**1. Un balayage historique.** Les mêmes détecteurs, les mêmes seuils, rejoués à
chaque pivot confirmé — c'est-à-dire à chaque instant où la réponse pouvait
changer. Une figure se définit par ses pivots : entre deux pivots, rien de
nouveau ne peut apparaître, donc scanner barre par barre coûterait vingt fois
plus pour la même liste.

**2. Cinq détecteurs muets ont reçu leur géométrie.** `head_and_shoulders`,
`inverse_head_and_shoulders`, `triple_top`, `triple_bottom`, `bull_flag` et
`bear_flag` reconnaissaient la forme sans jamais produire de quoi la dessiner :
73 % des figures étaient invisibles. Elles sont toutes traçables aujourd'hui.

**3. La fenêtre des figures suit ce que le graphique dessine.** Elle était
calée sur la période demandée (43 bougies en 4 h) alors que l'app charge ses
propres bougies : on voyait 166 jours de graphique avec des figures sur les
sept derniers.

**4. Les bougies remontent vraiment loin.** L'app en chargeait mille — un an en
hebdomadaire. Elle pagine maintenant : **9,1 ans en 1 j et 1 sem.**, soit tout
ce que Binance conserve pour BTCUSDT (première bougie le 14 août 2017).

**5. Le zoom arrière atteint le jeu entier.** Il était plafonné à 300 bougies :
les figures de 2018 étaient trouvées, servies, et hors d'atteinte.

## Résultat : BTC, figures par détecteur et par unité

| Figure | 1 sem. | 1 j | 4 h | 1 h | 15 min | Total |
|---|---:|---:|---:|---:|---:|---:|
| Drapeau haussier | 2 | 15 | 32 | 48 | 72 | **169** |
| Drapeau baissier | 1 | 7 | 29 | 59 | 71 | **167** |
| Double creux | 1 | 14 | 32 | 48 | 56 | **151** |
| Double sommet | 5 | 13 | 22 | 38 | 62 | **140** |
| ETE inversée | 0 | 9 | 14 | 28 | 44 | **95** |
| Épaule-tête-épaule | 0 | 8 | 19 | 28 | 29 | **84** |
| Triple sommet | 2 | 2 | 5 | 7 | 12 | **28** |
| Triple creux | 0 | 1 | 8 | 7 | 10 | **26** |
| Triangle symétrique | 0 | 1 | 2 | 1 | 3 | **7** |
| Biseau ascendant | 0 | 0 | 0 | 2 | 0 | **2** |
| Biseau descendant | 0 | 0 | 0 | 1 | 0 | **1** |
| **TOTAL** | **11** | **70** | **163** | **267** | **359** | **870** |

Avant ce lot, la même colonne donnait **0 ou 1**.

## BTC : couverture et devenir des figures

| Unité | Bougies | Profondeur | Figures | Déclencheur atteint | Invalidée | Ni l'un ni l'autre |
|---|---:|---|---:|---:|---:|---:|
| 1 sem. | 474 | 2017-08-14 → 2026-09-07 (**9,1 ans**) | 11 | 4 | 5 | 2 |
| 1 j | 3 310 | 2017-08-17 → 2026-09-08 (**9,1 ans**) | 70 | 29 | 35 | 6 |
| 4 h | 6 024 | 2023-12-10 → 2026-09-08 (2,7 ans) | 163 | 63 | 90 | 10 |
| 1 h | 10 094 | 2025-07-15 → 2026-09-08 (1,1 an) | 267 | 106 | 148 | 13 |
| 15 min | 12 189 | 2026-05-04 → 2026-09-08 (0,3 an) | 359 | 131 | 212 | 16 |

« Déclencheur atteint » et « invalidée » sont des **faits** sur chaque instance :
le prix a franchi en clôture le niveau que le détecteur avait nommé, dans un sens
ou dans l'autre. Ce n'est pas un avantage statistique, et `edge_state` reste
`NOT_YET_TESTED` partout. Le rapport 131/212 sur le 15 min ne dit pas que les
figures échouent : il dit que sur cette unité, sur ces quatre mois, ces
instances-là ont plus souvent touché leur invalidation d'abord. Rien de plus.

## Les trois actifs

| Actif | 1 sem. | 1 j | 4 h | 1 h | 15 min | Total |
|---|---:|---:|---:|---:|---:|---:|
| BTC | 11 | 70 | 163 | 267 | 359 | **870** |
| ETH | 9 | 87 | 152 | 263 | 330 | **841** |
| SOL | 5 | 41 | 146 | 268 | 356 | **816** |

**2 527 figures** au total, toutes traçables, toutes datées du moment où elles
sont devenues reconnaissables.

## Pourquoi ces nombres sont utilisables

**Causalité.** Chaque rejeu ne voit que les barres jusqu'à son propre point de
détection. Une figure datée de 2019 était reconnaissable en 2019, avec les
données de 2019. C'est ce qui permettra plus tard de compter ces figures comme
des observations plutôt que comme de la décoration — un scan qui regarde en avant
gonflerait tout.

Un test le vérifie directement : le balayage d'un préfixe de la série doit être
un préfixe du balayage complet. Les barres qui s'impriment ensuite ne changent
rien à ce qui a été trouvé avant.

**Identité.** La même forme reste « les deux derniers pivots » pendant plusieurs
barres, donc elle est redétectée à chaque fois. Ce sont une figure, pas douze.
Elles sont regroupées sur leurs pivots, puis les recouvrements de plus de 80 %
sont écartés — nécessaire pour les drapeaux, dont le mât est une fenêtre
glissante qui produit une copie décalée à chaque pivot.

**Pas de figure sur du bruit.** Un test lance le balayage sur une marche
aléatoire de 1 200 barres et échoue au-delà de 6 figures pour 100 barres.
Interroger les détecteurs plus souvent ne doit pas leur faire dire oui plus
souvent.

## Ce qui n'est pas résolu

**Les 10 ans ne sont atteints qu'en 1 j et 1 sem.** Les autres unités sont
limitées par ce qui est stocké localement, pas par le balayage :

| Unité | Aujourd'hui | Possible | Coût du rattrapage |
|---|---|---|---|
| 4 h | 2,7 ans | 9,1 ans | ~20 appels Binance |
| 1 h | 1,1 an | 9,1 ans | ~80 appels |
| 15 min | 0,3 an | 9,1 ans | ~320 appels, ~316 000 lignes |

Le balayage les trouvera dès que l'historique sera là — aucun code à changer.

**Aucun avantage n'a été mesuré.** 2 527 figures, c'est un échantillon, pas un
résultat. Savoir si une figure précède quoi que ce soit demande un protocole :
fenêtres indépendantes, correction multi-tests, hors-échantillon. C'est le
chantier LOT 6B, et il reste entier.

**Trois détecteurs restent rares** : biseaux et triangles ne produisent que
10 figures sur 2 527. Soit leurs critères sont trop stricts, soit ces formes sont
réellement rares. Je ne sais pas laquelle des deux, et je ne l'ai pas testé.

**Les libellés `notes` et `invalidation_rule` sont toujours en anglais.** Ils ne
sont donc pas affichés sur le graphique.
