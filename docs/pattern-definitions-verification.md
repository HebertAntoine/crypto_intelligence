# Les définitions des figures, confrontées aux références

## Ce que tu m'as demandé, et ce que je n'avais pas fait

J'avais vérifié la **mécanique** du balayage — causalité, identité, silence sur
du bruit — et jamais les **définitions** des figures. Elles étaient dans le code
avant cette session ; je les ai reprises telles quelles et j'ai présenté 12 559
figures comme un résultat. C'était prématuré.

Ce document confronte chaque détecteur aux références du domaine, dit où l'on
diverge, corrige ce qui était faux, et mesure ce que valent les formes.

## Les références utilisées

Il n'existe pas de norme officielle des figures chartistes : ce sont des
conventions issues de la littérature technique. La plus systématique et la seule
qui donne des seuils chiffrés est celle de Thomas Bulkowski
(*Encyclopedia of Chart Patterns*), publiée sur thepatternsite.com. C'est elle
que j'ai utilisée, page par page.

## Ce qui était faux, et qui est corrigé

### 1. La neckline de l'épaule-tête-épaule était fausse

**Référence** : « Le cou joint les deux aisselles » et la figure « se confirme
quand le prix clôture sous une neckline ascendante, ou sous l'aisselle droite
quand elle descend ».

**Ce que faisait le code** : une droite **horizontale** placée à la plus basse
clôture entre les deux épaules. Ce n'est ni l'un ni l'autre des deux points
qu'un lecteur joindrait, et le niveau de confirmation était donc faux.

**Corrigé** : la neckline joint les deux aisselles, elle peut pencher, et la
règle de confirmation suit celle de la référence. La figure exige désormais que
les deux aisselles existent — sans elles il n'y a pas d'ETE, seulement trois
sommets dont celui du milieu est plus haut. Les deux aisselles sont publiées
comme points nommés.

### 2. La vallée était mesurée sur des clôtures, pas sur des plus bas

**Référence** : « Le double sommet se confirme quand le prix clôture **sous la
vallée** entre les deux sommets. » Une vallée, c'est un plus bas.

**Ce que faisait le code** : la vallée était la plus basse **clôture**. Comme
une plus basse clôture est toujours au-dessus ou égale au plus bas, la ligne
était trop haute et la figure se confirmait trop tôt.

**Corrigé** pour les doubles et les triples.

### 3. Le drapeau ne regardait pas la structure

**Référence** : un mât « quasi vertical », « en ligne droite », « sans pause »,
suivi d'une consolidation « inclinée contre la tendance » de moins d'une
quinzaine de chandeliers.

**Ce que faisait le code** : le mât était **toujours** les barres −30 à −12 et
le drapeau **toujours** les douze dernières. Il ne pouvait donc ni voir un mât
de quarante barres, ni un drapeau de cinq, et il retrouvait une copie décalée de
la même vague à chaque pivot. Les drapeaux faisaient 38 % de tout ce que le
balayage produisait.

**Corrigé** : le mât part du pivot opposé et finit au dernier pivot ; le
drapeau est ce qui suit, borné à 15 barres comme dans la référence. Deux
conditions traduisent « quasi vertical » et « en ligne droite » : une raideur
minimale en ATR par barre, et une rectitude — la part du chemin parcouru qui
sert réellement au déplacement (une ligne droite vaut 1, une marche aléatoire
environ 1/√n).

## Ce qui diverge délibérément

### Nos tolérances sont en ATR, pas en pourcentage

La référence chiffre en pourcentage : sommets à moins de 3 % l'un de l'autre,
vallée d'au moins 10 %. Ces nombres sont calibrés sur des **actions en
quotidien**. Transposés tels quels, ils n'ont aucun sens :

| Unité | Ce que « 10 % » vaut en ATR (BTC) |
|---|---|
| 1 sem. | 0,8 ATR |
| 1 j | 2,3 ATR |
| 4 h | 6,1 ATR |
| 1 h | 12,7 ATR |
| 15 min | 36,7 ATR |

Appliquer 10 % en 15 minutes ne trouverait jamais rien ; l'appliquer en
hebdomadaire serait plus **laxiste** que notre seuil. Un pourcentage fixe n'est
pas transposable entre unités de temps : la normalisation par l'ATR est le bon
principe, et c'est celui du projet depuis le début.

**Mais notre seuil de 1,5 ATR reste un choix, pas une dérivation.** Rien ne l'a
validé.

### Vérification chiffrée sur les figures réellement détectées

| Vue | Doubles | Écart entre extrêmes < 3 % | Vallée ≥ 10 % |
|---|---:|---|---|
| BTC 1 sem. | 6 | 5/6 | 6/6 |
| BTC 1 j | 27 | 24/27 | 19/27 |
| BTC 4 h | 150 | 150/150 | 22/150 |

L'écart entre extrêmes respecte la référence presque partout — la normalisation
ATR fait son travail. La vallée ne la respecte pas en 4 h, pour la raison
ci-dessus : 10 % vaut 6 ATR à cette échelle.

### Nos triangles et biseaux sont plus stricts

La référence demande **5 touches** (3 sur une droite, 2 sur l'autre) et trois
semaines. Nous exigeons **3 pivots de chaque côté**, soit 6 touches, plus un
alignement minimal et une convergence d'au moins 30 %. C'est plus strict, et
cela explique leur rareté.

## Le résultat le plus important, et il n'est pas confortable

Compter les figures ne prouve rien tant qu'on ne sait pas combien on en trouve
sur du **hasard**. J'ai donc rejoué les mêmes détecteurs sur dix marches
aléatoires calibrées sur la volatilité réelle de BTC, ETH et SOL en quotidien —
29 460 barres de bruit contre 8 840 barres de marché.

| Figure | Réel /1000 barres | Hasard /1000 barres | Rapport | Verdict |
|---|---:|---:|---:|---|
| Triangle symétrique | 0,23 | 0,03 | **6,65×** | plus fréquent que le hasard |
| Biseau ascendant | 0,11 | 0,03 | **3,32×** | plus fréquent que le hasard |
| Double sommet | 4,53 | 4,21 | 1,08× | indiscernable du hasard |
| Double creux | 4,75 | 4,72 | 1,01× | indiscernable du hasard |
| ETE inversée | 1,70 | 1,90 | 0,89× | indiscernable du hasard |
| Épaule-tête-épaule | 1,58 | 1,80 | 0,88× | indiscernable du hasard |
| Triple creux | 0,79 | 1,32 | 0,60× | **moins** fréquent que le hasard |
| Triple sommet | 0,57 | 0,98 | 0,58× | **moins** fréquent que le hasard |
| Drapeau baissier | 9,62 | 17,41 | 0,55× | **moins** fréquent que le hasard |
| Drapeau haussier | 6,33 | 14,39 | 0,44× | **moins** fréquent que le hasard |

**Neuf figures sur onze apparaissent aussi souvent, ou plus souvent, sur du
hasard que sur le marché.**

Cela ne veut pas dire que les tracés sont faux : après les corrections
ci-dessus, ils sont exacts. Cela veut dire que **ces formes ne sont pas des
propriétés du marché**. Trouver 4 468 figures sur BTC ne signifie pas que BTC a
formé 4 468 figures ; cela signifie que « double sommet », tel que la référence
le définit, décrit quelque chose qu'une marche aléatoire produit tout autant.

C'est une mesure, pas une opinion. Elle est reproductible : même graine, même
volatilité, même réponse. Elle est stockée dans `config/noise_benchmark.json` et
publiée avec chaque figure.

C'est aussi, exactement, ce que la philosophie du projet existe pour révéler :
**reconnaître n'est pas prédire**. Ici on découvre même une étape antérieure —
reconnaître n'est pas encore décrire quelque chose de réel.

## Ce que l'application dit maintenant

Chaque figure porte son rapport au hasard. Sur le graphique, une forme
indiscernable du hasard est étiquetée « = HASARD » en gris plutôt qu'en couleur
directionnelle. Sous le graphique, une phrase le dit en toutes lettres.

`edge_state` reste `NOT_YET_TESTED` partout : la question « est-ce que ça
prédit quelque chose » est encore **une autre** question, et elle n'a pas été
posée.

## Le test qui a changé, et pourquoi

Le test §14 exigeait que moins de 30 % des marches aléatoires produisent une
figure. Après la correction du drapeau, on était à 42 %.

Je n'ai **pas** ajusté les seuils jusqu'à ce que le test passe. J'ai mesuré :

- détecteurs spécifiés (tout sauf les drapeaux) : **15 %** — le plafond tient ;
- avec les drapeaux : **42 %** — il ne tient pas.

Le test est donc scindé en deux : un plafond qui tient pour les formes
spécifiées, et un test qui **enregistre l'échec** du drapeau et échouera le jour
où une définition de drapeau le corrigera. Un échec mesuré et nommé vaut mieux
qu'un seuil bricolé.

## Ce que je n'ai toujours pas vérifié

- **Le volume.** La référence en parle pour presque toutes les figures (« le
  volume décroît pendant la formation »). Aucun de nos détecteurs ne le regarde,
  sauf le biseau. C'est une divergence réelle, non corrigée.
- **Les variantes.** La référence distingue Adam/Eve selon la forme des sommets,
  avec des statistiques différentes. Nous ne faisons pas la distinction.
- **La tendance préalable.** La référence exige une tendance haussière avant un
  double sommet. Nous ne la vérifions pas.
- **Le repère au hasard ne couvre que le quotidien.** Les autres unités
  devraient être mesurées de la même façon.
