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
| Drapeau haussier | 2 | 15 | 104 | 423 | 363 | **907** |
| Drapeau baissier | 1 | 7 | 88 | 362 | 353 | **811** |
| Double sommet | 5 | 13 | 73 | 298 | 333 | **722** |
| Double creux | 1 | 14 | 77 | 241 | 337 | **670** |
| ETE inversée | 0 | 9 | 63 | 253 | 212 | **537** |
| Épaule-tête-épaule | 0 | 8 | 55 | 233 | 172 | **468** |
| Triple sommet | 2 | 2 | 11 | 56 | 87 | **158** |
| Triple creux | 0 | 1 | 16 | 40 | 79 | **136** |
| Triangle symétrique | 0 | 1 | 4 | 18 | 8 | **31** |
| Biseau ascendant | 0 | 0 | 1 | 9 | 8 | **18** |
| Biseau descendant | 0 | 0 | 0 | 5 | 3 | **8** |
| Triangle descendant | 0 | 0 | 1 | 0 | 0 | **1** |
| Triangle ascendant | 0 | 0 | 0 | 0 | 1 | **1** |
| **TOTAL** | **11** | **70** | **493** | **1 938** | **1 956** | **4 468** |

Avant ce lot, la même colonne donnait **0 ou 1** — les détecteurs n'étaient
interrogés qu'une fois, au présent.

## BTC : couverture et profondeur

| Unité | Barres | Période couverte | Figures | Balayage à froid |
|---|---:|---|---:|---:|
| 1 sem. | 474 | 2017-08-14 → 2026-09-07 (**9,1 ans**) | 11 | 0,0 s |
| 1 j | 3 310 | 2017-08-17 → 2026-09-08 (**9,1 ans**) | 70 | 0,0 s |
| 4 h | 19 843 | 2017-08-17 → 2026-09-08 (**9,1 ans**) | 493 | 4,8 s |
| 1 h | 79 305 | 2017-08-17 → 2026-09-08 (**9,1 ans**) | 1 938 | 32,9 s |
| 15 min | 71 000 | 2024-09-09 → 2026-09-08 (2,0 ans) | 1 956 | 27,5 s |

L'historique local était plafonné à 120 jours en 15 min, 400 en 1 h et 900 en
4 h : c'est pour cela que le balayage trouvait neuf ans de figures en
quotidien et quatre mois en 15 min. Les barres manquantes ont été rapatriées
(**140 000 nouvelles lignes en 4 h, 182 000 en 1 h, 176 000 en 15 min**), et
`DEFAULT_DEPTH_DAYS` a été relevé pour que le planificateur les conserve.

Le 15 min s'arrête à deux ans volontairement : neuf ans feraient 316 000
barres par actif, pour des figures de 2018 sur un graphique de quinze minutes
qui n'apprennent rien sur aujourd'hui.

## Les trois actifs

| Actif | 1 sem. | 1 j | 4 h | 1 h | 15 min | Total |
|---|---:|---:|---:|---:|---:|---:|
| BTC | 11 | 70 | 493 | 1 938 | 1 956 | **4 468** |
| ETH | 9 | 87 | 460 | 2 013 | 1 865 | **4 434** |
| SOL | 5 | 41 | 328 | 1 398 | 1 885 | **3 657** |

**12 559 figures** au total, toutes traçables, toutes datées du moment où elles
sont devenues reconnaissables. SOL couvre 6,1 ans : c'est sa date de cotation
sur Binance, pas une lacune.

## Ce que voit l'écran

Le graphique ne dessine que les figures qui croisent la **fenêtre visible** —
en zoomant, il ne reste que ce qu'on regarde. Sous le graphique, une ligne dit
« 93 figures sur cette vue · 1 956 dans tout l'historique conservé », pour
qu'une vue serrée ne se lise jamais comme un marché sans figures.

Au plus quatre figures portent leur nom à l'écran, les plus récentes : nommer
cent soixante figures rendrait le graphique illisible.

| | Avant | Après |
|---|---:|---:|
| Figures servies à la vue BTC 4 h | 0 | 164 |
| Figures dans l'historique BTC 4 h | 0 | 493 |
| Profondeur visible en 1 sem. | 1 an | 9,1 ans |
| Zoom arrière maximal | 300 barres | le jeu entier |
| Réponse `/chart` à froid | — | 0,6 à 35 s |
| Réponse `/chart` à chaud | — | 0,5 à 1,4 s |

Le premier balayage d'une unité coûte jusqu'à 35 secondes. Il n'a lieu qu'une
fois : ensuite le cache reprend là où il s'est arrêté, et une nouvelle barre ne
rejoue que les pivots qui la suivent. Un test vérifie que reprendre et tout
rejouer donnent exactement la même liste — sans quoi le compte dériverait sans
que rien ne le dise.

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

**Le 15 min ne remonte qu'à deux ans.** Toutes les autres unités atteignent la
date de cotation Binance (14 août 2017 pour BTC et ETH, 10 août 2020 pour SOL).
Aller plus loin en 15 min demanderait ~320 appels et 316 000 lignes par actif ;
le balayage les traiterait sans changement de code, mais je n'y vois pas
d'intérêt : une figure de quinze minutes vieille de huit ans ne dit rien du
marché d'aujourd'hui.

**L'app n'affiche pas neuf ans sur toutes les unités.** Elle charge 3 400
barres en quotidien (neuf ans), 600 en hebdomadaire (tout), mais 6 000 en 4 h
(2,7 ans) et 4 000 en 1 h (5 mois). Charger neuf ans de 1 h serait 80 appels à
chaque ouverture du graphique. Le compte de l'historique complet reste affiché,
donc l'écart est dit plutôt que caché — mais il est réel.

**Aucun avantage n'a été mesuré.** 2 527 figures, c'est un échantillon, pas un
résultat. Savoir si une figure précède quoi que ce soit demande un protocole :
fenêtres indépendantes, correction multi-tests, hors-échantillon. C'est le
chantier LOT 6B, et il reste entier.

**Trois détecteurs restent rares** : biseaux et triangles ne produisent que
10 figures sur 2 527. Soit leurs critères sont trop stricts, soit ces formes sont
réellement rares. Je ne sais pas laquelle des deux, et je ne l'ai pas testé.

**Les libellés `notes` et `invalidation_rule` sont toujours en anglais.** Ils ne
sont donc pas affichés sur le graphique.
