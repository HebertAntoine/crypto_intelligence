# Détection de figures — critères, cycle de vie, limites

Document de référence du moteur `structure/patterns.py`, seul moteur de figures
du projet depuis le LOT 4. Il répond au §14 du cahier des charges : *documenter
précisément quand un pattern est considéré en formation, détecté, confirmé,
invalidé*, et quels critères il doit franchir.

## 1. Pourquoi ce durcissement

Rejoué barre par barre sur l'historique quotidien complet, le moteur d'origine
signalait au moins une figure sur **73 à 82 % des bougies**, avec des confiances
descendant à **0,1/100**. Un détecteur qui trouve quelque chose quatre fois sur
cinq ne transporte aucune information : le §14 demandait explicitement l'inverse.

Mesure après durcissement, même protocole (fenêtre 200 barres, pas de 3) :

| Actif / TF | Avant | Après |
|---|---|---|
| ETH 1d | 82,3 % | 32,0 % |
| ETH 4h | 81,9 % | 27,0 % |
| SOL 4h | 78,2 % | 26,7 % |
| SOL 1d | 73,4 % | 25,7 % |
| BTC 1d | — | 26,6 % |
| BTC 4h | — | 28,2 % |

La part de bougies reste une métrique trompeuse : une figure demeure visible
pendant des dizaines de barres, donc elle est comptée des dizaines de fois. Le
nombre pertinent est celui des **figures distinctes**. Sur BTC 1d, 8,5 ans :

| | Figures | Par an | Bougies concernées |
|---|---|---|---|
| Détecteurs durcis (LOT 4) | 25 | **2,9** | 11,9 % |
| Détecteurs non durcis | 62 | 7,3 | 17,2 % |

## 2. Les gates, dans l'ordre où ils s'appliquent

Tous les seuils vivent dans `config/thresholds.yaml`, section `structure_patterns`,
et sont modifiables sans toucher au code. Toutes les tolérances sont exprimées en
ATR, donc elles signifient la même chose sur BTC à 90 000 et sur SOL à 95.

### Communs à tous les détecteurs

| Gate | Rôle |
|---|---|
| `min_confidence` (55) | Plancher global. En dessous, **rien n'est annoncé** — pas annoncé discrètement. |
| Pivots causaux | Un pivot n'existe qu'une fois confirmé par `lookback` barres supplémentaires (`swings.py`). Aucun repainting. |

### Double top / double bottom

| Gate | Valeur | Rôle |
|---|---|---|
| `min_bars` / `max_bars` | 12 / 250 | Deux creux à un an d'écart ne forment pas une figure. Le plafond manquait entièrement. |
| `extreme_tolerance_atr` | 0,7 | Écart maximal entre les deux extrêmes. |
| `min_reaction_atr` | 1,5 | Réaction minimale entre eux, sinon c'est une seule base large. |
| `min_pivot_quality` | 40 | Les deux extrêmes doivent avoir provoqué une vraie réaction, pas un frémissement. |
| `min_confidence` | 58 | |

### Triangles (ascendant, descendant, symétrique)

| Gate | Valeur | Rôle |
|---|---|---|
| `min_pivots` | 3 par borne | |
| `min_alignment` | 55 | **Le gate qui manquait** : l'ancien code passait `polyfit` sur trois points sans jamais mesurer leur distance à la droite obtenue. N'importe quels trois swings devenaient une trendline. |
| `min_convergence` | 0,35 | Les bornes doivent se resserrer d'au moins 35 %. |
| `flat_slope_atr` | 0,015 | En dessous, une borne est horizontale. La classification se fait sur *quelle borne est plate*, pas sur un ratio entre deux pentes. |
| largeur ≥ 1,5 ATR | | Une figure plus étroite qu'un ATR est du bruit habillé en géométrie. |

### Wedges (rising, falling)

Mêmes gates que le triangle, avec `min_alignment` à 60 et `min_convergence` à
0,30, plus l'exigence que **les deux pentes soient de même signe** et toutes deux
significativement écartées de l'horizontale.

## 3. Cycle de vie

Deux échelles cohabitent, volontairement.

`PatternState` (ce que le détecteur peut décider seul) :

| État | Signification |
|---|---|
| `CANDIDATE` | La forme est présente, le déclencheur n'est pas atteint. |
| `CONFIRMED` | Le déclencheur a été franchi en clôture. |
| `FAILED` | Le niveau d'invalidation a été atteint à la place. |

`PatternStatus` (le cycle publié, `structure/detection.py`) :

| Statut | Condition |
|---|---|
| `FORMING` | Forme incomplète, trop peu de pivots pour s'engager. |
| `DETECTED` | Géométrie complète, tous les gates franchis. |
| `BREAKOUT_PENDING` | Le prix est à moins de 0,25 ATR du déclencheur sans l'avoir clôturé au-delà. |
| `CONFIRMED` | Clôture au-delà du déclencheur. |
| `INVALIDATED` | Niveau d'invalidation atteint. |
| `COMPLETED` | Objectif théorique atteint après confirmation. |

**La forme seule ne confirme jamais.** `CONFIRMED` exige le franchissement, et
`detected_at` reste distinct de `confirmed_at` — c'est ce qui rend un backtest
honnête possible (§15).

`BREAKOUT_PENDING` est la seule nuance ajoutée hors du détecteur, parce qu'elle
demande le prix courant et un ATR. Sans eux, le statut reste `DETECTED` plutôt
que d'être deviné.

## 4. Traçabilité

Chaque figure publie ses composantes nommées, et la confiance est leur moyenne
simple — recalculable par n'importe qui à partir de ce qui est affiché à côté.
`PatternDetection.components_explain_confidence()` le vérifie, et le payload
expose `confidence_is_explained`.

Exemple pour un double top : `extreme_agreement`, `reaction_depth`,
`time_separation`, `pivot_quality`.

## 5. Limites connues

- **Quatre détecteurs ne sont pas encore durcis** : `head_and_shoulders`,
  `inverse_head_and_shoulders`, `bull_flag`, `bear_flag`. Ils produisent
  aujourd'hui 7,3 figures par an sur BTC 1d contre 2,9 pour les six durcis, et
  **ne fournissent aucune géométrie** — ils ne sont donc pas dessinables sur le
  graphique. Les flags restent classés `EXPERIMENTAL`.
- **Le wedge est passé d'`EXPERIMENTAL` à `HEURISTIC`** parce que sa définition
  est désormais spécifiée (bornes ajustées, alignement minimal, pentes en ATR
  par barre) et donc reproductible. Les seuils restent des choix : c'est
  exactement ce que `HEURISTIC` signifie.
- **`edge_state` vaut `NOT_YET_TESTED`** pour toutes les figures en direct. La
  recherche existe (`research/pattern_validation.py`) mais n'est pas rebranchée
  sur la détection : reconnaissance et avantage mesuré restent séparés, et
  aucune des deux ne doit être lue comme l'autre.
- Les seuils sont **calibrés à la main**, pas optimisés sur les données — ce qui
  est délibéré : les optimiser sur l'historique disponible reviendrait à
  surajuster le seul échantillon dont nous disposons.
