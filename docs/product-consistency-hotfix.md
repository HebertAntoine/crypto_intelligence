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
