# Cohérence produit : ce que l'écran disait, et ce qui était vrai

Trois incohérences visibles, toutes réelles, toutes corrigées. Deux venaient de
la même erreur de code commise à deux endroits.

## 1. Le funding valait 24 et « n'était pas disponible »

L'écran affichait `NÉGATIF · p24` puis, dans l'explication,
`funding percentile unavailable`.

`EntryOpportunityEngine` énumérait `EXTREME_POSITIVE`, `EXTREME_NEGATIVE` et
`NEUTRAL`. `NEGATIVE` et `POSITIVE` — deux bandes parfaitement mesurées —
tombaient dans le `else` terminal, qui écrit dans `missing`.

Corrigé : une bande mesurée hors extrêmes produit désormais son propre facteur,
avec son percentile réel. Seul un percentile réellement absent (`None`) vaut
`missing`.

## 2. Un range comptait comme une lacune

La structure 1D valait `RANGE_STRUCTURE`, une lecture établie. Le code testait
`BULLISH` puis `BEARISH`, et tout le reste partait dans `missing` — d'où
« Lecture structurelle incomplète » sur une structure parfaitement lue, qui ne
penchait simplement d'aucun côté.

Corrigé : le range a sa branche et contribue zéro, ce qui est sa contribution
honnête. Il n'est plus compté comme absent.

**Le motif commun** : un `else` traitant « état valide non énuméré » comme
« donnée manquante ». Trois tests l'isolent, dont deux qui inspectent le code
plutôt que les données pour rester valables quand la base de test est vide.

Effet mesuré : les trois actifs passent de plusieurs entrées `missing` à
`missing: []`.

## 3. « Analyse hors ligne » au-dessus d'un prix en direct

Les deux affirmations étaient vraies. Le prix vient des providers en direct,
l'analyse d'un instantané. Un seul statut de page ne pouvait pas dire les deux.

Le payload expose maintenant un bloc `analysis` :

```
computed_at             quand l'analyse a été calculée
price_at_analysis       le prix sur lequel elle repose
live_price              le prix courant
price_drift_pct         l'écart entre les deux
stale_for_current_price vrai au-delà de 1,5 %
```

Le sous-titre choisit selon les deux couches :

| Prix | Analyse | Sous-titre |
| --- | --- | --- |
| direct | instantané | Prix en direct · analyse calculée à 21:46 |
| direct | direct | Données actualisées · analyse de 21:46 |
| instantané | instantané | Mode hors ligne · instantané du 7 sept. |

« Hors ligne » n'apparaît plus que si rien n'est joignable.

Chaque carte porte « Analyse calculée à hh:mm ». Si le prix s'est écarté de plus
de 1,5 % du prix d'analyse, la ligne passe en ambre et dit que l'actualisation
est recommandée — une décision ne peut pas être présentée au présent quand elle
décrit un prix que le marché a quitté.

## ETH favorable, BTC et SOL en attente : d'où vient la différence

La question posée était de vérifier que l'écart vient d'entrées réelles et non
d'un champ manquant. Après correction des deux bugs ci-dessus :

| Actif | Structure 1D | Localisation | Funding | État |
| --- | --- | --- | --- | --- |
| BTC | range (0) | haut de range (−25) | p24, penche bas (+4) | NEUTRAL → ATTENDRE |
| ETH | **haussière (+30)** | neutre (0) | normalisé (+8) | FAVORABLE → OPPORTUNITÉ |
| SOL | range (0) | haut de range (−25) | normalisé (+8) | NEUTRAL → ATTENDRE |

La différence est structurelle et mesurée : ETH a une structure daily haussière
là où BTC et SOL sont en range près du haut. Ce n'était pas un mapping.

## Couche de présentation

Les moteurs raisonnent en anglais : leurs enums sont des identifiants, pas du
texte. Le défaut était qu'ils traversaient l'app jusqu'à l'écran.

Corrigés à la source, en français : « Régime strongly bullish » →
« Régime fortement haussier » · « REINTEGRATION to the up through 81375.745,
24 bar(s) ago » → « Réintégration du range par le haut — mouvement de qualité
limitée (28/100), il y a 24 bougies en 4H » · « 4h price is near range top,
zone quality 62/100 » → « En 4h, le prix est proche du haut de son range
(qualité de zone 62/100) » · « 1d structure is UNCLEAR » →
« structure 1d indéterminée » · « UNAVAILABLE - aucun fournisseur… » →
phrase complète sans identifiant.

`app/lib/presentation/domain_labels.dart` rassemble les tables pour régime,
structure, localisation, cassure, funding, encombrement, volatilité, avantage,
configuration d'entrée, fraîcheur et niveau de preuve. Un état inconnu devient
lisible plutôt que brut — c'est un filet, pas une traduction.

`tests/unit/test_no_raw_enum_reaches_ui.py` interroge l'endpoint réel pour les
trois actifs et échoue sur tout SCREAMING_SNAKE_CASE ou phrase anglaise de
domaine. Il a trouvé deux fuites que j'avais manquées.

## Améliorer, dégrader, changer la structure

Trois catégories, plus deux. « La structure actuelle n'est plus valide » n'est
pas « la situation devient mauvaise ».

L'invalidation du range était versée telle quelle dans « ce qui dégraderait ».
Pour BTC, cela affichait « une clôture 4H au-dessus de 81 541,64 invaliderait
le range » comme une dégradation — alors que c'est une cassure haussière.

La direction est lue depuis l'état structurel (`NEAR_RANGE_TOP`), jamais depuis
la phrase du moteur. Une cassure par le haut va dans « changerait la
structure », avec la mention qu'elle est à confirmer par un retest ; une
cassure par le bas y va aussi et alimente en plus « dégraderait ».

## Analogues, funding, cassure : en première lecture

`Analogues: n effectif 8.0, médiane 2.88, MFE 3.68, MAE -1.33` devient
« Historique comparable trop limité — seulement 8 situations suffisamment
indépendantes ont été trouvées ». `24e percentile, variation 24 h -0.000006`
devient « Coût de portage nettement en dessous de sa normale : les positions
courtes paient les longs ». Les valeurs brutes restent dans `raw_value`, donc
dans les preuves.

## Tableau de cohérence

| Actif | Décision | Régime | Localisation | Funding | Dérive |
| --- | --- | --- | --- | --- | --- |
| BTC | ATTENDRE | Fortement haussier | proche du haut de range | NEGATIVE p24 | +0,50 % |
| ETH | OPPORTUNITÉ | Fortement haussier | neutre | NEUTRAL | +0,76 % |
| SOL | ATTENDRE | Fortement haussier | proche du haut de range | NEUTRAL | +0,52 % |

Les trois partagent le régime ; ce qui les sépare est la localisation
structurelle. Aucune valeur ne diffère entre les blocs d'un même instantané.

## Identité de l'analyse

Chaque endpoint recalculait ce dont il avait besoin. Deux appels séparés d'une
seconde pouvaient donc décrire deux instants sans que rien ne le dise : le
régime d'une exécution à côté du funding de la suivante. Aucun chiffre n'était
faux ; leur combinaison l'était.

Une analyse est maintenant une valeur qui porte un nom.

`AnalysisContextSnapshot` (`engines/analysis_context.py`) rassemble toutes les
lectures d'une même décision — régime, structure par unité de temps,
localisation, funding, open interest, encombrement, volatilité réalisée et
implicite, ETF, macro, edge, analogues, incertitude, couverture, pression,
entrée, timing et décision — et `analysis_id` la nomme.

L'identifiant est **adressé par le contenu**, pas alloué : c'est le hachage
d'une empreinte des entrées stockées (nombre de lignes et dernier horodatage
de chaque série), du calendrier macro programmé et d'un seau d'horloge de cinq
minutes. Deux processus lisant la même base tombent donc sur le même
identifiant sans partager d'état, et l'identifiant change exactement quand les
entrées changent.

Le cache conserve un instantané pendant un seau entier plutôt que de
recalculer au franchissement de l'horloge : sans cela, deux endpoints appelés à
une seconde d'intervalle de part et d'autre de :05 renvoyaient deux
identifiants, et le client devait traiter une paire parfaitement cohérente
comme un désaccord.

### Endpoints qui partagent l'identifiant

| Endpoint | Sert |
| --- | --- |
| `/today/{symbol}` | l'instantané complet et la page compacte |
| `/why/decision/{symbol}` | le raisonnement derrière le verdict affiché |
| `/edge/{symbol}` | l'état d'avantage de cet instantané |
| `/leverage/{symbol}` | funding, encombrement, état de levier |
| `/volatility/{symbol}` | volatilité réalisée |
| `/structure/{symbol}` | structure et localisation, quand l'unité demandée est couverte |
| `/structure/{symbol}/multi-timeframe` | 1S / 1J / 4H / 1H |
| `/entry-opportunity/{symbol}` | l'évaluation 4H de cet instantané |

Une unité de temps hors de l'analyse (15 m, par exemple) est calculée à la
demande et le dit en renvoyant `analysis_id: null` : elle n'appartient à aucune
analyse, et prétendre le contraire laisserait l'écran la combiner avec des
blocs qui, eux, en font partie.

### Le prix reste dehors

Le prix bouge à la seconde, l'analyse non. `price_at_analysis` est la dernière
clôture 4H — le prix sur lequel la lecture a réellement été calculée — et
`live_layer` joint le prix en direct par un écart explicite plutôt qu'en
fusionnant deux horloges. Un tick ne fabrique donc jamais une nouvelle analyse.

## Qui achète, qui vend

La carte affiche l'essentiel ; le détail s'ouvre au clic, famille par famille :
score normalisé, poids, apport reproductible au total, source, horodatage et
raison d'absence. Le total est une moyenne pondérée des familles qui ont
répondu, et la feuille montre la formule et la somme des apports pour qu'on
puisse la refaire.

**Une source absente n'est ni neutre ni zéro.** Elle sort du dénominateur et
reste listée avec la raison de son absence. La confondre avec « aucune
pression » tirait discrètement chaque score vers le neutre.

## Couverture des données

Nouvelle mesure, distincte de l'incertitude. L'incertitude décrit la solidité
de la conclusion ; la couverture décrit ce que nous avons pu observer.
« Incertitude 60/100 élevée » et « couverture 85 % bonne » ensemble est une
paire cohérente : nous avons vu la plupart des preuves, et elles ne concordent
pas.

Quatre classes, parce que « manquant » et « ça n'existe pas » sont deux
réponses différentes :

| Classe | Sens |
| --- | --- |
| `EXPECTED_AND_AVAILABLE` | attendue et présente |
| `EXPECTED_BUT_MISSING` | attendue et absente — un vrai trou |
| `NOT_APPLICABLE` | n'existe pas pour cet actif |
| `UNAVAILABLE_BY_DESIGN` | volontairement non collectée |

Les deux dernières sortent du dénominateur : Deribit ne publie pas d'indice
DVOL pour SOL et aucun ETF spot SOL n'est suivi, donc les compter contre SOL
signalerait un trou de données là où il y a un fait de marché.

## Défauts trouvés en chemin

- **La table de localisation comptait six entrées pour une énumération de
  neuf.** `AT_RANGE_TOP`, `AT_RANGE_BOTTOM`, `LOWER_THIRD` et `UPPER_THIRD`
  tombaient dans le repli : « le prix est AT_RANGE_TOP » atteignait
  l'utilisateur pendant que `NEAR_RANGE_TOP` s'affichait correctement. Le même
  écart existait côté Flutter. Chaque vocabulaire vit désormais une seule fois,
  dans `core/labels_fr.py`, lu par tous les producteurs de texte.
- **Le texte d'invalidation du range et les détails de `EntryOpportunity`
  étaient restés anglais.** Traduits à la source.
- **Le garde-fou anti-enum ne mordait que par accident** : il ne trouvait du
  texte que si un autre module avait laissé des lignes en base avant lui. Il
  amorce maintenant son propre historique et lit toute la page.
- **Le libellé du bouton d'expansion faisait 35 caractères** et débordait la
  ligne à la largeur de référence — attrapé par les tests avant un téléphone.

## Revue statique écran par écran

Je ne peux pas voir l'application tourner et ne prétends pas l'avoir validée
visuellement. `tests/unit/test_screen_qa.py` contrôle ce qui est vérifiable sur
la source des huit écrans : aucun identifiant brut ni phrase anglaise dans les
chaînes réellement affichées, présence d'un état de chargement, d'erreur et de
vide, aucun bouton câblé sur rien, identité de l'analyse conservée côté client,
et aucun seuil de décision numérique dans la vue.

Le contrôle porte sur les arguments de `Text(...)` et les paramètres nommés
d'affichage, pas sur toute la source : les clés JSON et les identifiants de
moteur sont du vocabulaire interne et doivent y rester. Un test vérifie que
l'extracteur trouve effectivement des chaînes, faute de quoi une regex cassée
rendrait toute la revue verte par vacuité.

## Tests

- `tests/unit/test_analysis_identity.py` — identifiant partagé sur huit
  endpoints pour BTC / ETH / SOL, mêmes funding, structure, localisation, edge,
  incertitude et prix d'analyse ; identifiant reproductible à froid ; nouvel
  identifiant quand une entrée change ; continuité au franchissement d'un
  seau ; prix live hors de l'identité ; cohérence pression / explication.
- `tests/unit/test_today_page.py` — position structurelle à 0 / 0,5 / 1, range
  absent, distances aux niveaux, tri des catalyseurs, événement macro ≤ 24 h,
  couverture, `NOT_APPLICABLE`, périmé contre manquant, incertitude distincte
  de la couverture, divergence des unités de temps, régime haussier avec
  ATTENDRE, absence d'avantage démontré non lue comme baissière, conditions de
  changement, pression partielle et totale reproductible.
- `tests/unit/test_screen_qa.py` — la revue statique ci-dessus.
- `app/test/today_page_test.dart` — les mêmes propriétés rendues réellement.

## Ce qui reste ouvert

- **Le backend n'est pas déployé.** L'app lit les instantanés embarqués et ne
  fait aucun appel réseau tant que `API_BASE_URL` est vide. Le prix « en
  direct » qu'affiche l'app vient donc de l'instantané au moment de son export,
  pas d'un flux continu. C'est le blocage produit le plus important et il
  demande une décision d'hébergement.
- **`/evidence` et les endpoints de recherche ne portent pas d'`analysis_id`.**
  C'est délibéré : ils décrivent des études, pas une décision d'un instant. Les
  rattacher à un instantané suggérerait une fraîcheur qu'ils n'ont pas.
- **L'historique des verdicts est vide.** « Dernier changement de lecture » ne
  s'affiche qu'à partir de deux lectures enregistrées, et rien n'est
  reconstruit après coup. Le travail planifié `decision_track` les écrit toutes
  les trente minutes ; le bloc apparaîtra quand il aura tourné.
- **`EdgeEngine` renvoie `INSUFFICIENT_DATA` (0 testée) sur cette base.** La
  page l'affiche « aucune relation testée », distinct de « aucun avantage
  démontré ». C'est exact, mais cela signifie que la sortie de recherche n'est
  pas rattachée à cette base de production.

897 tests backend, ruff propre.
