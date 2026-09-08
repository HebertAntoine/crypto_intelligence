# LOT 1 — moteur temps/prix · LOT 1B — profondeur des données

---

## Correction préalable : je me suis mal fait comprendre

Tu as lu « 1W ≈ 8,6 jours » et « 15m ≈ 41 heures » comme des **profondeurs**.
C'étaient des **âges** — depuis combien de temps la dernière bougie datait.

La profondeur réelle, mesurée :

| Actif | 1w | 1d | 4h | 1h | 15m |
| --- | --- | --- | --- | --- | --- |
| BTC | **9,1 ans** (474) | 9,1 ans (3 310) | 2,7 ans (6 023) | 1,2 an (10 090) | **125 j** (12 173) |
| ETH | **9,1 ans** (474) | 9,1 ans (3 310) | 2,7 ans (6 023) | 1,2 an (10 090) | **125 j** (12 173) |
| SOL | **6,1 ans** (318) | 6,1 ans (2 220) | 2,7 ans (6 023) | 1,2 an (10 090) | **125 j** (12 173) |

Source : Binance spot klines, via `history/store`.

Ton objectif était « 4 à 6 ans » en hebdomadaire et « 30 à 90 jours » en
quinze minutes. **Les deux étaient déjà dépassés.** Aucun backfill
supplémentaire n'était nécessaire, et je n'en ai pas fait.

Le vrai défaut était la fraîcheur : `job_ohlcv_sync` ne couvrait que 1D, 4H et
1H. La bougie hebdomadaire accusait huit jours, la quinze minutes quarante-trois
heures. **Les cinq unités sont maintenant rafraîchies** ; après exécution, 15m
est à 0,0 h et 1w porte la bougie de la semaine en cours.

---

## LOT 1 — le moteur

### Fichiers

| Fichier | Rôle |
| --- | --- |
| `app/lib/chart/chart_viewport.dart` | **nouveau** — le repère temps ↔ x, prix ↔ y |
| `app/lib/chart/chart_layers.dart` | **nouveau** — les onze calques et leur visibilité |
| `app/lib/chart/candle_chart.dart` | **nouveau** — widget interactif et peintre |
| `app/lib/screens/chart_screen.dart` | ancien peintre retiré (263 lignes), moteur branché, barre de calques |
| `backend/crypto_intel/scheduler.py` | 1W et 15m ajoutées au rafraîchissement |
| `app/test/chart_viewport_test.dart` | **nouveau** — 25 tests |
| `app/test/candle_chart_test.dart` | **nouveau** — 15 tests |
| `tests/unit/test_no_fake_frontend_market_data.py` | garde-fous repointés et renforcés |

### Ce qui a remplacé quoi

L'ancien peintre calculait

```dart
final rawLow  = candles.map((c) => c.low).reduce(math.min);
final rawHigh = candles.map((c) => c.high).reduce(math.max);
```

sur **tout** le jeu, étalé sur la largeur du cadre. Aucune fenêtre, donc rien à
déplacer ni à zoomer, et toute annotation aurait été posée en pixels.

`ChartViewport` sépare le **jeu de données** de la **fenêtre visible** :

```
candles          toutes les bougies chargées
startIndex       première visible
visibleCount     combien le sont
plot             la zone de dessin, en pixels
```

Quatre conversions, et rien d'autre n'a le droit de calculer une position :

```
timeToX(DateTime) ↔ xToTime(double)
priceToY(double)  ↔ yToPrice(double)
```

`timeToX` passe par un **index fractionnaire** : recherche dichotomique dans
les horodatages, puis interpolation entre les deux bougies encadrantes. Une
géométrie de figure porte des horodatages réels — pas des index de barres — et
reste donc valable après un changement de fenêtre ou d'unité. Hors du jeu,
l'horodatage est **prolongé à la cadence moyenne** plutôt qu'écrasé sur le
bord : une neckline projetée sort de l'écran, elle ne se colle pas à la
dernière bougie.

### Échelle verticale

Calculée sur `visible`, jamais sur `candles`, avec 6 % de marge. Un test le
prouve avec un pic à 100 000 placé hors fenêtre : l'ancien peintre aurait
écrasé soixante bougies contre le bas du cadre.

### Interactions

| Geste | Effet |
| --- | --- |
| glissement horizontal | déplace `startIndex`, borné aux deux extrémités |
| pincement | modifie `visibleCount`, **borné à 15–300 bougies** |
| double tap | revient aux 80 dernières bougies |
| appui long | crosshair accroché à la bougie, avec OHLC et volume |

Le zoom conserve le point d'ancrage : ce qui est sous le doigt y reste, à une
demi-bougie près — la fenêtre est discrète, pas continue.

Le crosshair est **borné au visible**. Sans cela, une abscisse à gauche du
cadre retombait arithmétiquement sur un index valide du jeu et désignait une
bougie qui n'est pas dessinée là. C'est le seul défaut que les tests ont
trouvé, et il est corrigé.

### Calques

Onze calques déclarés dans l'ordre de peinture : `grid`, `candles`, `volume`,
`indicators`, `levels`, `range`, `patternGeometry`, `eventMarkers`, `labels`,
`currentPrice`, `crosshair`. Six sont vides dans ce lot, l'architecture est en
place. Les calques structurels (bougies, prix, crosshair) ne se désactivent
pas : sans bougies il ne reste qu'une grille.

### Axes

Les bornes de prix sont « rondes » (1, 2, 2,5, 5 × puissance de dix) selon
l'amplitude visible. Le nombre d'étiquettes de dates s'adapte à la largeur —
une étiquette par 84 px — donc pas de chevauchement.

---

## Résultats réels

| Critère | Résultat |
| --- | --- |
| **A** 500 chargées, ~60 visibles | ✅ 500 / 80 par défaut |
| **B** pan vers l'historique | ✅ et retour au présent |
| **C** pinch change la fenêtre | ✅ borné 15–300 |
| **D** axe Y sur le visible | ✅ pic hors fenêtre sans effet |
| **E** double tap restaure | ✅ |
| **F** crosshair sélectionne | ✅ borné au visible |
| **G** OHLC exacts | ✅ comparés bougie par bougie |
| **H** géométrie stable après zoom | ✅ au niveau des coordonnées |
| **I** idem après pan | ✅ |
| **J** zones alignées | ⏳ LOT 3 |
| **K** RSI/MACD synchronisés | ⏳ LOT 6 |
| **L** 1W exploitable | ✅ 9,1 ans, à jour |
| **M** 15m exploitable | ✅ 125 jours, à jour |
| **N** aucun débordement | ✅ 4 tailles dont paysage |
| **O** analyzer propre | ✅ |

```
app     : 204 tests passés  (dont 40 nouveaux sur le moteur)
backend : 989 tests passés
dart analyze lib test : No issues found!
flutter build web --release : ✓ Built build/web
ruff check : All checks passed!
```

H et I sont validés au niveau du repère : un horodatage retrouve sa bougie
après zoom et après déplacement. Ils le seront **visuellement** au LOT 4,
quand une vraie `PatternGeometry` sera dessinée.

---

## Problèmes découverts

1. **Le crosshair débordait du visible** — corrigé, décrit ci-dessus.
2. **Trois helpers étaient enfermés dans l'ancien peintre**
   (`_timeframeLabel`, `_periodForTimeframe`) : retirer le peintre les
   emportait. Restaurés au niveau du fichier.
3. **Un garde-fou anti-synthétique cherchait le message d'état vide dans
   l'écran** ; il a suivi le moteur. Repointé, et renforcé d'un contrôle
   nouveau : l'écran ne doit plus contenir `reduce(math.min)`, c'est-à-dire ne
   plus calculer d'échelle sur l'ensemble des bougies.

---

## Ce que je n'ai pas validé

- **Le rendu visuel.** Je ne peux pas voir l'application tourner. Les tests
  rendent réellement le widget et manipulent de vrais gestes, mais l'aspect
  final est à ta vérification.
- **La fluidité 60 FPS.** Le peintre ne parcourt que les bougies visibles
  (au plus 300) et `shouldRepaint` compare la fenêtre par valeur, donc rien ne
  se repeint sans raison. Mais je n'ai pas mesuré sur un appareil.
- **Le mode paysage réel** : testé en 800×390, pas sur un téléphone tourné.

---

## Reste à faire

LOT 2 est en grande partie absorbé : bougies, volume, grille, axes et prix
courant sont dessinés et le graphique est branché. Restent le bouton plein
écran (LOT 7) et la validation visuelle.

La suite dans l'ordre convenu : **LOT 3** zones et structure depuis les
données backend, puis **LOT 4** le rendu générique de `PatternGeometry`, puis
**LOT 5** la validation sur `double_top` — la seule figure qui porte
aujourd'hui une géométrie complète.
