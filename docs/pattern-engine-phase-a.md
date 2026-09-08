# PHASE A — audit, contrat, validateur, versioning

## A. Fichiers inspectés

`structure/patterns.py` (1164 l.), `structure/detection.py` (423), `structure/geometry.py`
(112), `structure/swings.py` (175), `structure/quality.py` (209), `structure/ranges.py`
(455), `structure/location.py` (264), `structure/market_structure.py` (253),
`structure/zones.py` (236), `structure/cache.py` (223), `structure/history_scan.py`,
`engines/technical/indicators.py`, `api/routes_lot2.py`, `db/base.py`,
`config/thresholds.yaml`, et les quatre fichiers de tests des figures.

## Correction de tes prémisses

Ta mission part de trois observations qui **ne sont plus vraies** :

| Ta prémisse | État réel |
|---|---|
| `triple_top` détecté sans géométrie | Géométrie complète depuis `7381d3e` |
| `bull_flag` détecté sans géométrie | Idem |
| `inverse H&S` détecté sans géométrie | Idem, et enrichi des deux aisselles |

**Aucun détecteur n'est muet.** Les 16 544 figures de l'historique portent toutes
une géométrie. Le LOT 6 de PHASE B (« compléter la géométrie de tous les
détecteurs ») est donc déjà fait.

## 1. Inventaire des détecteurs

Neuf fonctions produisent treize types de figures.

| Figure | Fonction | Classe | Version | Géométrie publiée | Neckline | Cassure | Invalidation | Cible |
|---|---|---|---|---|:-:|:-:|:-:|:-:|
| double_top | `_detect_double` | DETERMINISTIC | `double_v3` | 2 points, neckline, zone | ✅ | ✅ | ✅ | ❌ |
| double_bottom | `_detect_double` | DETERMINISTIC | `double_v3` | 2 points, neckline, zone | ✅ | ✅ | ✅ | ❌ |
| triple_top | `detect_triple` | DETERMINISTIC | `triple_v3` | 3 points, neckline, zone | ✅ | ✅ | ✅ | ❌ |
| triple_bottom | `detect_triple` | DETERMINISTIC | `triple_v3` | 3 points, neckline, zone | ✅ | ✅ | ✅ | ❌ |
| head_and_shoulders | `detect_head_and_shoulders` | HEURISTIC | `head_shoulders_v3` | 5 points, neckline inclinée, zone | ✅ | ✅ | ✅ | ❌ |
| inverse_head_and_shoulders | idem | HEURISTIC | `head_shoulders_v3` | 5 points, neckline inclinée, zone | ✅ | ✅ | ✅ | ❌ |
| symmetrical_triangle | `detect_triangle` | HEURISTIC | `triangle_v2` | 2 points projetés, 2 bornes, zone | ❌ | ✅ | ✅ | ❌ |
| ascending_triangle | idem | HEURISTIC | `triangle_v2` | idem | ❌ | ✅ | ✅ | ❌ |
| descending_triangle | idem | HEURISTIC | `triangle_v2` | idem | ❌ | ✅ | ✅ | ❌ |
| rising_wedge | `detect_wedge` | HEURISTIC | `wedge_v2` | 2 points projetés, 2 bornes | ❌ | ❌ | ✅ | ❌ |
| falling_wedge | idem | HEURISTIC | `wedge_v2` | idem | ❌ | ❌ | ✅ | ❌ |
| bull_flag | `detect_flag` | EXPERIMENTAL | `flag_v3` | 2 points, mât, zone | ❌ | ❌ | ✅ | ❌ |
| bear_flag | idem | EXPERIMENTAL | `flag_v3` | idem | ❌ | ❌ | ✅ | ❌ |

### Occurrences actuelles (balayage complet, BTC + ETH + SOL, 5 unités)

| Figure | 1 sem. | 1 j | 4 h | 1 h | 15 min | Total |
|---|---:|---:|---:|---:|---:|---:|
| bear_flag | 15 | 85 | 447 | 1 956 | 1 947 | **4 450** |
| bull_flag | 9 | 56 | 455 | 1 945 | 1 909 | **4 374** |
| double_top | 8 | 40 | 232 | 1 094 | 1 148 | **2 522** |
| double_bottom | 4 | 42 | 239 | 870 | 1 084 | **2 239** |
| inverse_head_and_shoulders | 0 | 15 | 104 | 451 | 435 | **1 005** |
| head_and_shoulders | 0 | 14 | 111 | 396 | 364 | **885** |
| triple_top | 3 | 5 | 25 | 199 | 270 | **502** |
| triple_bottom | 2 | 7 | 33 | 131 | 215 | **388** |
| symmetrical_triangle | 0 | 2 | 7 | 40 | 21 | **70** |
| rising_wedge | 0 | 1 | 3 | 28 | 26 | **58** |
| falling_wedge | 0 | 0 | 3 | 12 | 24 | **39** |
| ascending_triangle | 0 | 0 | 0 | 4 | 3 | **7** |
| descending_triangle | 0 | 0 | 1 | 1 | 3 | **5** |
| **TOTAL** | **41** | **267** | **1 660** | **7 127** | **7 449** | **16 544** |

Les drapeaux font **53 %** du total. Les triangles directionnels sont
quasi inexistants (12 sur 16 544) : leurs critères sont probablement trop
stricts, ou le cas ascendant/descendant est mal discriminé du symétrique.

## 2. Moteurs support

| Brique | Fichier | État |
|---|---|---|
| Pivots causaux | `swings.py` | `CausalSwing` porte `pivot_time` **et** `confirmation_time`. Solide, c'est ce qui rend le balayage historique honnête. |
| ATR / indicateurs | `engines/technical/indicators.py` | 20 fonctions : ATR, RSI, MACD, Bollinger, ADX, OBV, VWAP, volume relatif |
| Qualité géométrique | `quality.py` | `LineFit` (R² **et** résidu en ATR), `pivot_quality`, `symmetry_score`, `volume_trend_score` |
| Ranges | `ranges.py` | `RangeIntelligenceEngine`, comptage de touches, déviations |
| Zones S/R | `zones.py` | `build_zones`, scoring |
| Structure HH/HL/LH/LL | `market_structure.py` | `MarketStructureEngine` |
| Position dans le range | `location.py` | `StructuralLocationEngine`, 9 états |
| Cache | `cache.py` + `history_scan.py` | Deux caches distincts, versionnés |
| Volume dans les figures | — | **Utilisé uniquement par le biseau.** Divergence réelle avec la référence. |

### Historique disponible

| Unité | Barres (BTC) | Profondeur |
|---|---:|---|
| 1 sem. | 474 | 9,1 ans |
| 1 j | 3 310 | 9,1 ans |
| 4 h | 19 843 | 9,1 ans |
| 1 h | 79 305 | 9,1 ans |
| 15 min | 71 000 | 2,0 ans |

## 3. Tests existants

| Fichier | Tests | Couvre |
|---|---:|---|
| `test_pattern_detectors.py` | 16 | figures synthétiques, silence sur le bruit |
| `test_pattern_detection_model.py` | 23 | contrat publié, sérialisation de la géométrie |
| `test_history_scan.py` | 18 | causalité, identité, incrémental, bruit |
| `test_pattern_validation_confirmation.py` | 4 | signaux de confirmation |
| `test_pattern_geometry_validation.py` | **12 (nouveau)** | le validateur indépendant |

## 4. Architecture actuelle, et le problème principal

```
detectors (patterns.py)  ──►  StructuralPattern  ──►  history_scan  ──►  /chart
                                     │
                              from_structural()
                                     ▼
                              PatternDetection  ──►  (personne)
```

**`PatternDetection` dans `detection.py` implémente déjà presque tout ce que ta
mission demande au LOT 1 et au LOT 2 — et rien ne l'utilise.**

Il porte : `id` stable, `symbol`, `timeframe`, `pattern_type`, `family`,
`direction`, `start_time`, `end_time`, `detected_at`, `confirmed_at`, `status`
(6 états dont `BREAKOUT_PENDING` et `COMPLETED`), `recognition_confidence`,
`confidence_components`, `pattern_class`, `edge_state`, `breakout_level`,
`invalidation_level`, `target_level`, `geometry`, `confirmation_signals`,
`metadata`. Il a même un pont `from_structural()`.

Ses seuls consommateurs sont son propre fichier de tests et `quality.py`.
`/chart` publie `StructuralPattern.to_dict()`, le contrat étroit.

**Je n'ai donc pas conçu un nouveau contrat : j'ai comblé ce qui manquait au
contrat existant et je propose de le brancher.**

## 5-6. Contrat et géométrie — ce qui manquait, ajouté

| Champ demandé | Avant | Maintenant |
|---|---|---|
| `detector_version` | absent partout | ✅ `DETECTOR_VERSIONS`, 16 entrées, rempli par `detect_all` |
| `validation` | absent | ✅ verdict du validateur indépendant sur chaque figure |
| points en temps + prix | déjà le cas | inchangé — jamais d'index de barre |
| `role` sur chaque point | déjà le cas | enrichi : aisselles, mât |
| `breakout_state` distinct | conflé dans `status` | proposé, non branché (PHASE B) |
| `target_type` | absent | proposé, non branché (PHASE B) |

`PatternGeometry` porte déjà `points[]`, `trend_lines[]`, `zones[]`, `neckline`,
`breakout_area`. Manquent `invalidation_line` et `target_line` — ce sont
aujourd'hui des scalaires dans `key_levels`, pas des droites.

## 7. `pattern_validation/` — architecture retenue

```
pattern_validation/
    __init__.py            les cinq niveaux, déclarés et jamais mélangés
    internal_geometry.py   NIVEAU 1 — implémenté
    (à venir) structural.py     NIVEAU 2
    (à venir) external/          NIVEAU 3
    (à venir) benchmark.py       NIVEAU 4
```

### Le validateur est indépendant par construction

Il ne reçoit **que** la géométrie publiée et les bougies. Il n'a aucun accès à
l'état interne du détecteur et ne rejoue pas sa logique : il repart du dessin et
demande si le prix le confirme. C'est ce qui lui permet d'attraper une erreur
que le détecteur ne peut pas voir en se relisant.

Treize contrôles, en trois familles :

- **contre les bougies** — chaque point nommé tombe-t-il sur sa barre, et à
  l'extrême qu'il prétend décrire ? (le contrôle le plus fort ; il utilise
  `kind` — `pivot`, `close`, `projected` — pour savoir quoi comparer)
- **cohérence interne** — ordre chronologique, pas de doublon d'horodatage,
  zones dont le haut est au-dessus du bas, droites qui ne finissent pas avant
  de commencer
- **contre la définition** — tête au-delà des deux épaules, aisselles entre
  épaule et tête, neckline entre les deux extrêmes, mât orienté comme le
  drapeau l'annonce

Il est appelé **sur les barres disponibles à la détection**, pas sur la série
complète : valider avec des bougies postérieures importerait du futur dans un
verdict censé décrire l'instant de la détection.

### Ce qu'il a trouvé, dont deux erreurs à lui

Premier passage : **1 184 rejets sur 16 544**. Analyse :

- 1 005 ETE inversées rejetées → **bug du validateur**. Il traitait « head » et
  « épaules » comme des sommets dans tous les cas ; dans une ETE inversée ce
  sont des creux et les aisselles des sommets. La polarité dépend de la figure.
- 179 triangles et biseaux rejetés → **bug du validateur**. Leurs points sont
  `kind="projected"` : posés sur la droite ajustée, ils ne tombent sur aucun
  extrême. Exiger qu'ils en touchent un était faux.

Après correction : **16 544 / 16 544 valides**.

Un validateur qui accepte tout ne vaut rien, donc je l'ai attaqué : neuf
corruptions délibérées de géométries réelles — sommet déplacé de 5 ATR, points
en désordre, point requis manquant, point sur aucune bougie, zone inversée,
neckline au-dessus des sommets, géométrie vide, ETE sans tête dominante,
drapeau haussier à mât descendant. **9 / 9 attrapées**, la figure intacte
passe. Ces neuf cas sont maintenant des tests permanents.

## 9. Stockage des observations — schéma proposé

Aucune table n'existe pour les figures. Les 19 tables actuelles incluent
`prediction_snapshots` / `prediction_outcomes`, dont la docstring pose le bon
principe : *« la prédiction est un fait enregistré à T, le résultat un fait
enregistré plus tard ; les mettre dans une ligne inviterait à modifier la
prédiction en même temps que son résultat »*. Je propose la même séparation.

```
pattern_observations                 pattern_outcomes
  id            (sha1 stable)          id
  asset, timeframe                     observation_id  ─┐
  pattern_type                         horizon_bars     │ 1..n
  detector_version                     mfe_pct          │
  detected_at                          mae_pct          │
  pattern_start, pattern_end           close_return_pct │
  recognition_confidence               reached_target   │
  confidence_components (JSON)         reached_invalid  │
  geometry (JSON)                      evaluated_at     │
  confirmation_state                                   ─┘
  geometry_valid, geometry_score
  noise_ratio, noise_verdict
  external_validation (JSON)
  content_hash
```

Non créé en PHASE A : ta consigne était de ne pas tout implémenter d'un coup,
et une table sans producteur ni consommateur serait du poids mort.

## 10. Métriques de benchmark

Pour chaque `(pattern_type, detector_version)` :

- precision, recall, F1 sur le jeu annoté — **priorité à la precision**, comme
  tu l'as demandé
- matrice de confusion entre familles proches
- calibration par tranche de `recognition_confidence` (50-60, 60-70, …)
- **rapport au hasard** — déjà implémenté et publié
- taux de validité géométrique — déjà implémenté
- N par actif et par unité, jamais agrégé sans le détail

## 11. Problèmes techniques trouvés

| # | Problème | Gravité | État |
|---|---|---|---|
| 1 | `PatternDetection` complet et inutilisé | structurel | documenté, branchement en PHASE B |
| 2 | Aucune figure ne produit d'objectif théorique | fonctionnel | à faire (LOT 24) |
| 3 | Biseaux sans zone de cassure, contrairement aux triangles | incohérence | à faire |
| 4 | Drapeaux sans niveau de cassure → jamais `CONFIRMED` | fonctionnel | à faire |
| 5 | `SCAN_VERSION` non incrémenté après changement de détecteurs | **correctness** | **corrigé** — le cache servait les anciennes règles |
| 6 | `ARTEFACT` en chemin relatif au répertoire courant | **correctness** | **corrigé** — le rapport au hasard arrivait vide |
| 7 | Triangles ascendant/descendant : 12 occurrences sur 16 544 | suspect | à instrumenter |
| 8 | Volume ignoré par tous les détecteurs sauf le biseau | divergence référence | à faire |
| 9 | Trois états seulement (`CANDIDATE`/`CONFIRMED`/`FAILED`) | contrat | 6 états existent dans `PatternStatus`, non branchés |
| 10 | Les tests écrivent dans `data/cache/figures/` à la racine | hygiène | à isoler |
| 11 | `pyproject.toml` déclare `python_version = "3.11"` alors que le projet tourne en 3.13 : `mypy` échoue sur les stubs de numpy avant même de vérifier le code | outillage | signalé, non modifié (fichier partagé) |

### Vérification de types

`mypy --python-version 3.13` : **0 erreur** dans les modules nouveaux
(`pattern_validation/`, `history_scan.py`, `noise_benchmark.py`). 17 erreurs
préexistantes ailleurs (`history/store.py` 14, `ranges.py` 5, `location.py` 4,
`patterns.py` 3) — hors périmètre de cette phase, non touchées.

## 12. Plan de migration sans casser `/chart`

`/chart` publie aujourd'hui `structural_patterns[]` au format `StructuralPattern`.
Trois étapes additives, aucune suppression :

1. **fait** — `detector_version` et `validation` ajoutés à la charge utile. Un
   consommateur qui les ignore ne voit aucune différence.
2. **PHASE B** — ajouter `patterns_v2[]` au format `PatternDetection` **à côté**
   de `structural_patterns[]`. Les deux coexistent le temps que le frontend
   migre.
3. **PHASE C** — retirer `structural_patterns[]` une fois qu'aucun consommateur
   ne le lit.

## G. Résultats des tests

```
1045 tests backend          passés
  12 nouveaux                validateur géométrique
 304 tests Flutter           passés
ruff check                   propre
dart analyze                 propre
```

## M. Lookahead — vérifié

Trois garanties, toutes testées :

- les pivots portent `confirmation_time` et le contexte est tronqué à la barre
  de détection ;
- le balayage d'un préfixe est un préfixe du balayage complet
  (`test_a_scan_of_a_prefix_is_a_prefix_of_the_scan`) ;
- la validation géométrique tourne sur `df[:detection_index+1]`.

## N. Validation externe

**Indisponible.** Aucun fournisseur intégré, et je n'en ai intégré aucun :
ta consigne interdit de contourner une protection, et les conditions d'accès
d'Autochartist, TradingView et TrendSpider n'ont pas été établies. L'architecture
est prévue (`pattern_validation/external/`) mais vide. C'est le LOT 26, et il
commence par de la recherche de licences, pas par du code.

## O. Limites

- Le validateur ne vérifie que le **niveau 1**. Une figure géométriquement
  valide peut être sans intérêt — et neuf formes sur onze le sont, d'après le
  repère au hasard.
- Aucun jeu annoté manuellement n'existe : precision et recall sont donc
  **incalculables** aujourd'hui. Le 100 % de validité géométrique ne dit
  **rien** de la precision.
- Le repère au hasard ne couvre que le quotidien.
- `PatternDetection` reste débranché.

## P. Prochaine étape recommandée

Pas PHASE B telle qu'écrite — elle est déjà faite. Je propose :

1. **Brancher `PatternDetection`** dans `/chart` en parallèle (étape 2 du plan
   de migration) : c'est ce qui débloque les six états, l'identité stable et
   les niveaux de cassure.
2. **Donner une cassure et un objectif** aux drapeaux, biseaux et triangles —
   sans quoi ils ne peuvent jamais être confirmés ni suivis.
3. **Créer le jeu annoté** (LOT 30-31), en commençant par les *hard negatives* :
   c'est la seule voie vers precision/recall, et sans lui tout le reste se
   mesure contre rien.

Le point 3 est le vrai goulot d'étranglement. Tout le reste est de l'ingénierie ;
celui-là demande du jugement humain, et c'est le tien.
