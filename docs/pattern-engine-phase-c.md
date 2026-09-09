# PHASE C — frontière de cassure et cycle de vie

## Le problème, en un chiffre

Avant : sur BTC en quotidien, **12 figures sur 95** sortaient en
`NO_TRIGGER_DEFINED`. Triangles, biseaux et drapeaux n'avaient aucun niveau à
franchir, donc ne pouvaient **structurellement jamais** être confirmés.

Après : **zéro**, sur les 1 968 figures des trois actifs en 1 sem. / 1 j / 4 h.

## Par famille

| Figure | Frontière | Type | Côté | Origine géométrique |
|---|---|---|---|---|
| double_top / double_bottom | neckline | HORIZONTAL | bas / haut | `geometry.neckline` |
| triple_top / triple_bottom | neckline | HORIZONTAL | bas / haut | `geometry.neckline` |
| head_and_shoulders | neckline | **LINE** | bas | droite entre les deux aisselles |
| inverse_head_and_shoulders | neckline | **LINE** | haut | idem |
| symmetrical_triangle | upper **et** lower | **LINE** | les deux | droites ajustées |
| ascending / descending_triangle | la borne du sens | **LINE** | haut / bas | droite ajustée |
| rising_wedge | lower | **LINE** | bas | droite ajustée |
| falling_wedge | upper | **LINE** | haut | droite ajustée |
| bull_flag | flag_top | HORIZONTAL | haut | haut de la zone de consolidation |
| bear_flag | flag_bottom | HORIZONTAL | bas | bas de la zone de consolidation |

Un triangle symétrique reçoit **ses deux bornes** : il peut casser des deux
côtés, et choisir un sens d'avance serait un pari, pas une mesure.

### La frontière inclinée est réellement inclinée

`BreakoutBoundary` porte deux extrémités et répond `price_at(instant)` :

```python
BreakoutBoundary(role="upper", kind=LINE, side=ABOVE,
                 start_time=…, start_price=10461.04,
                 end_time=…,   end_price=9432.16)
```

Elle est **prolongée** au-delà de son dernier point : c'est ce que fait un
opérateur qui trace une borne de triangle, et sans quoi une cassure survenue
après le dernier pivot serait jugée contre un niveau périmé.

Un test montre la conséquence concrète : le **même prix** casse un jour et pas
un autre, parce que la borne descend. Figer la droite en une horizontale prise
au dernier chandelier donnerait un niveau juste ce jour-là et faux le
lendemain.

### Ce qui n'est pas inventé

Les drapeaux reçoivent une frontière **horizontale**, tirée du haut ou du bas
de leur zone de consolidation. Nos détecteurs ne tracent pas les deux bornes du
canal d'un drapeau : en déduire une droite inclinée à partir de deux points
arbitraires serait une invention. Une figure sans géométrie exploitable reste
`NO_TRIGGER_DEFINED` — aucune frontière fabriquée.

## Logique de confirmation

```
clôture au-delà de la frontière + tampon   → CLOSE_CONFIRMED
mèche au-delà, clôture en deçà             → WICK_ONLY
clôture à moins de 0,5 ATR de la frontière → POTENTIAL
invalidation atteinte avant toute cassure  → INVALIDATED_FIRST
cassure puis retour de l'autre côté        → FAILED_BREAKOUT
rien dans l'horizon                        → NO_BREAKOUT
```

| Paramètre | Valeur | Pourquoi |
|---|---|---|
| Tampon de cassure | **0,15 ATR** | zéro accepterait un dépassement d'un centième, soit du bruit de cotation |
| Proximité (attente) | **0,5 ATR** | |
| Proximité de retest | **0,35 ATR** | |
| Fenêtre de retest | **12 barres** | |
| Horizon d'évaluation | **3 × la durée de la figure**, borné [20, 250] | voir ci-dessous |

### Mèche contre clôture

Une mèche **ne confirme jamais**. Elle est enregistrée séparément
(`first_wick_time`), parce qu'elle dit que le niveau a été touché — jamais
qu'il a été cassé. Sur BTC 1 j, **11 figures sur 95** sont en `WICK_ONLY` :
onze confirmations que l'ancienne logique aurait comptées à tort.

### L'horizon, et pourquoi il a fallu l'ajouter

Ma première version évaluait sur **tout le reste de la série**. Sur neuf ans,
le prix finit par franchir n'importe quel niveau : 37 % des figures sortaient
« invalidées » pour un mouvement survenu des années plus tard. Une figure qui
n'a rien produit dans un multiple de sa propre durée n'a rien produit.

### Le retest est un fait annexe, pas un état

Première version : `RETEST_HELD` remplaçait `CLOSE_CONFIRMED`, et ressortait
**707 fois contre 256** — le prix revient presque toujours frôler sa frontière
dans les douze barres suivantes, donc l'état principal était effacé. Désormais
le retest est publié à part (`retest_time`, `retest_held`) et **seul un échec**
change l'état : une cassure reprise dans l'autre sens n'était pas une cassure.

Sur les trois actifs : **606 retests tenus, 210 échoués**.

## États

`PatternStatus` est réutilisé tel quel — aucune énumération concurrente. Une
seule est nouvelle, `BreakoutState`, parce qu'aucune ne décrivait ce qui se
passe **à la frontière** : `PatternStatus` décrit la vie de la figure, pas le
détail de sa cassure. Les deux axes restent séparés — une figure peut être
invalidée sans qu'aucune cassure n'ait eu lieu.

Répartition réelle (1 968 figures) :

| BreakoutState | n | | PatternStatus | n |
|---|---:|---|---|---:|
| CLOSE_CONFIRMED | 839 | | CONFIRMED | 866 |
| INVALIDATED_FIRST | 599 | | INVALIDATED | 943 |
| FAILED_BREAKOUT | 210 | | BREAKOUT_PENDING | 132 |
| NO_BREAKOUT | 188 | | DETECTED | 27 |
| WICK_ONLY | 111 | | | |
| POTENTIAL | 21 | | | |
| **NO_TRIGGER_DEFINED** | **0** | | | |

`COMPLETED` reste inatteignable : il demande un objectif théorique, qu'aucun
détecteur ne produit encore.

## Exemples réels

Onze combinaisons demandées, onze trouvées dans l'historique.

**Frontière inclinée, cassure confirmée** — BTC 1 j, triangle symétrique
détecté le 2020-07-13 (confiance 76,4, `triangle_v2`). Borne haute de
**10 461,04 le 25 mai à 9 432,16 le 8 juillet**. Mèche le 15 juillet, puis
clôture au-delà le **21 juillet, 8 barres après**. → `CONFIRMED`.

**Frontière inclinée, faux breakout** — SOL 4 h, triangle symétrique détecté le
2022-09-05 20:00. Borne haute 33,23 → 32,35. Cassure une barre plus tard, puis
retest **non tenu** le 6 septembre 16:00. → `INVALIDATED`.

**Neckline inclinée** — BTC 1 j, épaule-tête-épaule du 2018-11-12. Neckline
**6 205,00 le 11 octobre → 6 245,02 le 31 octobre**, cassée en clôture le
14 novembre. → `CONFIRMED`.

**Biseau** — ETH 4 h, biseau descendant du 2025-12-19 12:00. Borne haute
3 446,21 → 2 975,55 ; cassure haussière une barre après. → `CONFIRMED`.
BTC 4 h, biseau ascendant du 2021-09-07 : borne basse 44 449 → 50 789, cassure
baissière. → `CONFIRMED`.

**Mèche seule** — BTC 1 j, drapeau haussier du 2022-07-25. Mèche au-dessus du
haut de consolidation le 29 juillet, aucune clôture au-delà.
→ `BREAKOUT_PENDING`, pas `CONFIRMED`.

**Attente** — BTC 1 j, drapeau baissier du 2018-09-13. Prix collé sous la
frontière, jamais franchie. → `BREAKOUT_PENDING`.

**Cassure puis échec** — BTC 1 sem., drapeau haussier du 2020-07-06
(confiance 97,0). Cassure 3 barres après, retest non tenu le 31 août.
→ `INVALIDATED`.

**Retest tenu** — BTC 1 sem., double sommet du 2021-12-13. Mèche sous la
neckline le 9 mai 2022, clôture confirmée le **6 juin, 25 barres après**,
retest **tenu** le 13 juin. → `CONFIRMED`.

## Tests

**25 nouveaux** dans `test_breakout_lifecycle.py` :

| Groupe | Ce qu'il fige |
|---|---|
| Frontière inclinée | lecture au bon instant, prolongement, le même prix casse un jour et pas l'autre |
| Mèche vs clôture | mèche ≠ cassure, tampon ATR, symétrie haut/bas |
| Les quatre cas du triangle | aucune cassure, mèche, clôture confirmée, faux breakout — sur borne **inclinée** |
| Attente | prix collé à une borne qui converge ≠ « rien ne se passe » |
| Drapeaux et biseaux | sens de cassure correct, un biseau directionnel n'offre qu'un côté |
| Rien n'est inventé | pas de géométrie → pas de frontière → `NO_TRIGGER_DEFINED` |
| Horizon | l'horizon suit la taille de la figure ; un mouvement au-delà ne compte pas |
| **Anti-lookahead** | voir ci-dessous |

### Anti-lookahead

| Test | Garantie |
|---|---|
| `test_the_boundary_comes_only_from_geometry` | `boundaries_for` **ne reçoit aucun prix** — propriété de signature, vérifiée pour qu'elle ne se perde pas à la prochaine refonte |
| `test_truncating_the_future_never_changes_a_past_verdict` | couper les barres postérieures ne change ni l'état ni le nombre de barres jusqu'à l'événement |
| `test_a_verdict_before_the_event_says_nothing_happened_yet` | avant la cassure, l'état n'est pas `CONFIRMED` |
| `test_invalidation_is_checked_before_any_later_breakout` | une figure invalidée ne peut pas être « sauvée » par la suite |

Rien de tout cela n'entre dans `recognition_confidence` : la frontière se
déduit de la géométrie connue à la détection, ce que le prix en fait est un
**résultat**, calculé séparément et jamais réinjecté dans le score.

## Un test qui a échoué pour la bonne raison

Ma fixture « aucune cassure » attendait `NO_BREAKOUT` ; le code répondait
`POTENTIAL`. Le code avait raison : à la cinquième barre le triangle avait
convergé et le prix était **collé** à la borne. J'ai corrigé l'attente et
ajouté un test dédié — confondre « rien ne se passe » avec « la figure se
décide » ferait passer pour calme le moment le plus important.

## Charge utile

Deux clés s'ajoutent, toujours en additif — 33 clés par figure, aucune retirée :

```json
"breakout_outcome": { "state": "CLOSE_CONFIRMED", "boundary": {…},
                      "level_at_event": 9587.4, "event_time": "…",
                      "bars_to_event": 8, "first_wick_time": "…",
                      "retest_time": "…", "retest_held": true, "note": "…" },
"breakout": { "state": …, "level": …, "boundary": {…}, "event_time": …,
              "bars_to_event": …, "first_wick_time": …, "retest_time": …,
              "retest_held": … }
```

`level` est le niveau **au moment de l'événement**, pas un prix figé : la
frontière d'un triangle bouge à chaque barre.

## Résultats

```
1080 tests backend        passés   (+25)
 308 tests Flutter        passés   (aucune ligne de Dart modifiée)
ruff check                propre
dart analyze              propre
mypy                      0 erreur dans breakout.py
```

## Limites

- **`COMPLETED` inatteignable** — aucun objectif théorique n'est produit.
- **Les drapeaux n'ont pas de canal ajusté** — leur frontière est horizontale
  faute de géométrie pour faire mieux. Une vraie borne de drapeau demanderait
  que le détecteur trace les deux droites du canal.
- **Les paramètres sont des choix.** 0,15 ATR de tampon, horizon à 3× la durée,
  12 barres de retest : rien ne les a validés. Ils sont déclarés en constantes
  nommées plutôt que dispersés, et c'est tout ce qu'on peut en dire aujourd'hui.
- **Aucun avantage n'est mesuré.** 839 cassures confirmées ne disent pas que
  les cassures marchent. `edge_state` reste `NOT_YET_TESTED`.

## Prochaine étape

PHASE D — l'outil de review et le premier échantillon stratifié. C'est le vrai
goulot : sans vérité terrain humaine, precision et recall restent incalculables,
et tout ce qui précède se mesure contre rien.
