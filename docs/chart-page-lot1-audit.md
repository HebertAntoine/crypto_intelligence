# Page « Intelligence graphique » — LOT 1, audit

Relevé du 8 septembre 2026 sur la base de production. Chaque chiffre vient
d'une exécution, pas d'une lecture de code.

---

## 1. Moteur graphique actuel

**Aucune librairie.** `pubspec.yaml` ne déclare que `http`,
`web_socket_channel` et `cupertino_icons`. Le graphique est un
`CustomPainter` écrit à la main : `_CandleChartPainter`, dans
`app/lib/screens/chart_screen.dart` (1 829 lignes au total).

Ce qu'il fait : grille, bougies, volume, axes.

Ce qu'il ne fait pas :

| Interaction demandée (§7) | État |
| --- | --- |
| pinch → zoom | **absent** |
| drag → déplacement temporel | **absent** |
| double tap → reset | **absent** |
| long press → crosshair | **absent** |
| OHLC au crosshair | **absent** |

Aucun `GestureDetector` n'est attaché au graphique.

**Cause structurelle** : le peintre n'a pas de notion de fenêtre. Il calcule

```dart
final rawLow  = candles.map((c) => c.low).reduce(math.min);
final rawHigh = candles.map((c) => c.high).reduce(math.max);
```

sur **toutes** les bougies, et les étale sur `chart.width`. Il n'existe donc
pas de repère temps/prix indépendant de la taille de l'écran — ce que le §53
exige pour que les annotations restent collées aux chandeliers. C'est le
blocage central : tout le reste en dépend.

Le §71 s'applique : il faut un vrai moteur de rendu avec fenêtre, pas des
`Positioned` sur un `Stack`.

---

## 2. Données OHLCV disponibles

Réelles, en base, par actif et unité :

| Unité | BTC | ETH | SOL | Âge | Travail planifié |
| --- | --- | --- | --- | --- | --- |
| 1w | 473 | 473 | 317 | **8,6 j** | **aucun** |
| 1d | 3 310 | 3 310 | 2 220 | 14,6 h | oui |
| 4h | 6 023 | 6 023 | 6 023 | 2,6 h | oui |
| 1h | 10 090 | 10 090 | 10 090 | 0,6 h | oui |
| 15m | 12 000 | 12 000 | 12 000 | **41,1 h** | **aucun** |

Les cinq unités du §3 existent. Deux ne sont pas rafraîchies : la
hebdomadaire, dont le §60 fait un cas d'usage principal, et la 15 minutes.

Modèle : `Candle {timestamp, open, high, low, close, volume}` — conforme au
§50.

---

## 3. Ce que `/chart` sert déjà

`GET /api/chart/{symbol}?timeframe=&period=&indicators=`

- bougies agrégées à la fenêtre demandée ;
- **overlays** : `ema20`, `ema50`, `ema200`, `bb_upper/middle/lower` ;
- **panneaux** : `rsi`, `macd`, `macd_signal`, `macd_hist` ;
- **niveaux** : supports et résistances avec `touches` et `strength` ;
- **marqueurs** : événements macro, réglementaires, gros flux ETF ;
- `summary` de la fenêtre.

Les indicateurs sont calculés sur une fenêtre élargie puis rognés, si bien
qu'une EMA200 a une valeur dès la première barre dessinée. C'est propre et
c'est à conserver.

Donc §32 (moyennes), §33 (Bollinger), §34 (volume), §36 (RSI) et §38 (MACD)
sont **déjà servis par le backend** ; il manque leur rendu.

---

## 4. Détecteurs de figures existants

Dans `structure/patterns.py` :

double_bottom · double_top · triple (top/bottom) · head_and_shoulders ·
inverse_head_and_shoulders · triangle · wedge (rising/falling) ·
bull_flag / bear_flag

Ils **fonctionnent sur les données réelles** :

| Actif | Unité | Détecté |
| --- | --- | --- |
| ETH | 4h | triple_top (68), double_top (67) |
| ETH | 1h | double_top (69) |
| SOL | 1d | bull_flag (100) |
| SOL | 4h | inverse_head_and_shoulders (81) |

Manquent par rapport au §1 : **tasse avec anse**, **pennant**, **canaux**,
**trendlines autonomes**, **Fibonacci**.

`StructuralPattern` sépare déjà `recognition_confidence` (forme) de
`edge_state` (avantage démontré) — exactement la distinction du §44 et du §45.
Elle est acquise, il ne faut pas la perdre.

---

## 5. La trouvaille décisive

`structure/geometry.py` définit `PatternGeometry` : points nommés
(`left_shoulder`, `head`…), droites avec rôle et prolongement, zones,
neckline, zone de cassure. Sa docstring dit :

> « Un frontend qui détient ceci et les bougies peut reconstruire exactement
> ce que le détecteur a vu. »

C'est précisément ce que demandent les §20 à §29.

**Mais `/chart` ne la sérialisait pas.** Il envoyait `pattern, confidence,
state, direction, invalidation, start_index, end_index, notes` — des index de
barres, pas des coordonnées. Le graphique ne pouvait rien tracer.

**Corrigé dans cette passe** : `/chart` sert désormais
`structural_patterns`, géométrie comprise, calculée sur les vraies barres de
l'unité demandée (jamais sur les barres agrégées pour l'affichage).

Résultat mesuré après correction :

| Figure | Points | Droites | Neckline | Zones |
| --- | --- | --- | --- | --- |
| double_top (ETH 4h) | 2 | 1 | oui | 1 |
| double_top (ETH 1h) | 2 | 1 | oui | 1 |
| triple_top (ETH 4h) | 0 | 0 | non | 0 |
| bull_flag (SOL 1d) | 0 | 0 | non | 0 |
| inverse_head_and_shoulders (SOL 4h) | 0 | 0 | non | 0 |

**Une figure sur cinq est dessinable.** Les autres détectent correctement mais
ne remplissent pas leur géométrie. C'est un travail de détecteur, pas
d'affichage.

---

## 6. Deux systèmes de figures coexistent

`/chart` appelait `TechnicalAnalysisEngine().analyze()` → `snapshot.patterns`,
un système distinct de `structure/patterns.py` → `detect_all()`. Le premier n'a
pas de géométrie, le second oui. Les deux sont désormais servis ; à terme il
faudra choisir, et c'est le second qui porte la séparation forme/avantage.

---

## 7. Défauts d'affichage constatés (§55)

Vérifiables sur la source, sans voir tourner l'app :

- le graphique occupe une hauteur fixe modeste ; le §5 demande 500-650 px ;
- pas de bouton plein écran (§6) ;
- pas de barre de calques (§40) ;
- aucun overlay dessiné en dehors des bougies et du volume, alors que le
  backend en sert huit.

---

## 8. Ce qui est faisable sans nouvelle donnée

Tout le §1 sauf le volume profile, qui demande une agrégation par niveau de
prix non calculée aujourd'hui.

Fibonacci (§31), position dans le range (§15), milieu de range (§16), objectif
théorique (§30) et invalidation (§29) se calculent depuis les swings et les
ranges déjà détectés.

---

## 9. Séquence proposée

1. **Moteur de rendu** — fenêtre temps/prix, pan, zoom, double-tap, crosshair,
   architecture en calques (§52, §53, §71). Rien d'autre n'est possible avant.
2. **Calques de base** — bougies, volume, axes, prix courant, grille (§8-§11).
3. **Zones** — supports, résistances, range, position, milieu (§12-§16).
4. **Figures** — dessin depuis `PatternGeometry`, plus remplissage de la
   géométrie manquante des trois détecteurs muets.
5. **Indicateurs** — moyennes, Bollinger, puis panneaux RSI et MACD (§32-§39).
6. **Nouveaux détecteurs** — tasse avec anse, canaux, trendlines, pennant,
   avec les tests anti-faux-positifs du §69.
7. **Plein écran, calques, légende, priorité des annotations** (§6, §40, §42,
   §57).

---

## 10. Ce que je n'ai pas vérifié

- Le rendu visuel actuel : je ne peux pas voir l'application tourner. Les
  défauts du §55 que tu décris (texte coupé, chevauchements) sont pris pour
  acquis, je ne les ai pas reproduits.
- Les performances de pan/zoom : rien à mesurer tant que le moteur n'existe
  pas.
