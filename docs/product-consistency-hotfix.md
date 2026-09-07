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

## Ce qui reste ouvert

- **Le backend n'est pas déployé.** L'app lit les instantanés embarqués et ne
  fait aucun appel réseau tant que `API_BASE_URL` est vide. Le prix « en
  direct » qu'affiche l'app vient donc de l'instantané au moment de son export,
  pas d'un flux continu. C'est le blocage produit le plus important et il
  demande une décision d'hébergement.
- **Textes anglais résiduels** venant des moteurs : `structural location`,
  `REINTEGRATION`, le texte d'invalidation. Une couche de présentation reste à
  écrire.
- **Improve / degrade / change structure** : la distinction demandée n'est pas
  faite. Une cassure haussière du haut de range est aujourd'hui rangée en
  « dégraderait », alors qu'elle invalide le range sans dégrader le marché.
- Analogues, breakout et funding s'affichent encore avec leur vocabulaire
  technique en première lecture.

757 tests backend, 93 Flutter, ruff et analyze propres.
