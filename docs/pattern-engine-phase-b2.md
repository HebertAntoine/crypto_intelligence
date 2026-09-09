# PHASE B2 — brancher `PatternDetection` dans `/chart`

## A. Fichiers modifiés

| Fichier | Nature |
|---|---|
| `structure/detection.py` | `detector_version` et `geometry_validation` ajoutés au contrat riche et au pont |
| `structure/history_scan.py` | `enrich_with_detection()`, migration additive |
| `pattern_validation/internal_geometry.py` | forme publiée renommée et alignée sur ta spécification |
| `api/routes_lot2.py` | enrichissement branché sur `/chart` |
| `tests/unit/test_pattern_identity_and_cache.py` | **nouveau**, 10 tests |
| `tests/unit/test_lot2_infra.py` | correction d'un test instable (voir M) |
| `app/assets/api_snapshots/chart__*.json` | 15 instantanés réexportés |

## B. `PatternDetection` avant / après

| Champ | Avant | Après |
|---|---|---|
| `id` (sha1 stable) | ✅ | ✅ |
| `symbol`, `timeframe` | ✅ | ✅ |
| `pattern_type`, `family`, `direction` | ✅ | ✅ |
| `start_time`, `end_time`, `detected_at`, `confirmed_at` | ✅ | ✅ |
| `status` (6 états) | ✅ | ✅ |
| `recognition_confidence`, `confidence_components` | ✅ | ✅ |
| `pattern_class`, `edge_state`, `edge_note` | ✅ | ✅ |
| `breakout_level`, `invalidation_level`, `target_level` | ✅ | ✅ |
| `geometry`, `confirmation_signals`, `metadata`, `notes` | ✅ | ✅ |
| **`detector_version`** | ❌ | ✅ ajouté |
| **`geometry_validation`** | ❌ | ✅ ajouté |

Rien n'était **redondant** au sens strict : `PatternDetection` est un
sur-ensemble de `StructuralPattern` plus le contexte (actif, fenêtre, identité).
Le recouvrement est voulu — c'est la même trouvaille publiée.

## C. Mapping `StructuralPattern` → `PatternDetection`

Une seule voie : `from_structural()`. Aucune seconde logique de conversion n'a
été écrite, conformément à ta consigne.

| Source | Destination | Transformation |
|---|---|---|
| `pattern.name` | `pattern_type` | identité |
| — | `family` | `family_for(name)` |
| `direction_if_textbook` | `direction` | cast d'énumération |
| `recognition_confidence` | idem | identité |
| `components` | `confidence_components` **+** `metadata` | scindé : les composantes du score d'un côté, les mesures brutes (distances ATR, comptes de barres) de l'autre |
| `state` (3 valeurs) | `status` (6 valeurs) | `_lifecycle_status()` ; ajoute `BREAKOUT_PENDING` quand le prix est à moins de N ATR du déclencheur |
| `key_levels["neckline"]` | `breakout_level` | défaut, surchargeable |
| `invalidation_level`, `invalidation_rule` | idem | identité |
| `detector_version` | idem | **repris du détecteur, jamais recalculé** |
| — | `id` | `make_pattern_id(symbol, tf, type, start, end)` |
| — | `geometry_validation` | verdict du validateur indépendant |

**Bug corrigé au passage** : `make_pattern_id` n'acceptait que des `datetime`,
alors que la charge utile porte des chaînes ISO. Sans normalisation, la même
occurrence aurait reçu deux identités selon le point d'appel — exactement ce
que l'id existe pour empêcher. Il accepte désormais les deux et normalise.

## D. JSON `/chart` — avant / après

**Avant** (commit `80ab95b`) — 24 clés par figure :

```
bars_span, bars_to_resolution, components, confirmation_time, detected_at,
direction_if_textbook, edge_note, edge_state, first_seen_at, geometry,
invalidation_level, invalidation_rule, key_levels, name, noise_ratio,
noise_verdict, notes, pattern_class, recognition_confidence, resolution,
resolved_at, span_end, span_start, state
```

**Après** — 32 clés. Les 24 précédentes sont **intactes**, huit s'ajoutent :

```json
{
  "id": "adbd250445eaeb63d2f7bc7d",
  "family": "REVERSAL",
  "lifecycle_state": "CONFIRMED",
  "detector_version": "double_v3",
  "breakout":     { "level": 7770.02, "state": "CLOSE_CONFIRMED" },
  "invalidation": { "level": 5286.98,
                    "rule": "a 1d close below 5286.98 would break both lows…" },
  "target":       { "level": null, "type": "NONE" },
  "geometry_validation": { "valid": true, "score": 100.0,
                           "checks_passed": 13, "checks_total": 13,
                           "rejection_reasons": [], "warnings": [], "note": "…" }
}
```

`target` est présent et explicitement nul : un consommateur doit pouvoir
distinguer « pas d'objectif » de « champ oublié ». Aucun détecteur n'en produit
encore — c'est PHASE C.

### Ce que la charge utile révèle immédiatement

Sur BTC 1 j, 95 figures :

| État de cassure | n |
|---|---:|
| `FAILED` | 55 |
| `CLOSE_CONFIRMED` | 28 |
| `NO_TRIGGER_DEFINED` | **12** |

Les douze sont les drapeaux, biseaux et triangles sans niveau de déclenchement.
Le problème que tu m'as demandé de corriger en PHASE C est maintenant **visible
dans les données** au lieu d'être implicite.

## E. Rétrocompatibilité

Migration strictement additive : **aucune clé supprimée, aucune renommée** dans
`structural_patterns[]`. Vérifié :

- `dart analyze` propre ;
- **308 tests Flutter passent**, dont les 31 gardes sur les instantanés livrés,
  sans qu'une seule ligne de Dart ait été modifiée ;
- les 15 instantanés réexportés sont relus par l'app existante.

Un consommateur qui ignore les huit nouvelles clés ne voit aucune différence.

## F. Tests de stabilité de l'identité

| Test | Ce qu'il fige |
|---|---|
| `test_a_new_candle_does_not_create_a_new_occurrence` | une bougie de plus ne recrée pas les figures |
| `test_the_id_is_derived_from_the_occurrence_not_from_the_clock` | `datetime` et chaîne ISO donnent le même id |
| `test_a_structurally_different_figure_gets_a_different_id` | comportement documenté quand la fenêtre change |
| `test_the_same_shape_on_two_assets_is_two_occurrences` | l'actif fait partie de l'identité |

## G. Tests de version et de cache

| Test | Ce qu'il fige |
|---|---|
| `test_the_cache_file_carries_the_version_in_its_name` | une nouvelle version **ignore** l'ancienne au lieu de l'écraser |
| `test_bumping_the_version_ignores_the_previous_scan` | le bug de PHASE A, figé : deux versions → deux entrées |
| `test_a_different_series_is_not_served_from_cache` | l'empreinte distingue deux séries de même longueur et même dernière barre |
| `test_the_benchmark_artefact_is_an_absolute_path` | le second bug de PHASE A |
| `test_it_resolves_the_same_from_any_directory` | idem, vérifié en changeant de répertoire |
| `test_a_missing_artefact_says_so_instead_of_looking_empty` | une absence porte sa raison |

La clé de cache contient : actif, unité, première barre, nombre de barres,
empreinte de trois clôtures intermédiaires, **et la version** (dans le nom du
fichier).

## H. Sérialisation de la validation géométrique

Nommage aligné sur ta consigne — `geometry_validation`, jamais
`pattern_validated` :

```json
"geometry_validation": {
  "valid": true, "score": 100.0,
  "checks_passed": 13, "checks_total": 13,
  "rejection_reasons": [], "warnings": [],
  "note": "Level 1 only: whether the drawing is consistent with the candles…"
}
```

La `note` voyage avec chaque figure et dit explicitement que ce champ ne parle
ni de prédiction ni de fréquence face au hasard.

## I-J. Tests exécutés et résultats

```
1055 tests backend        passés   (+10 nouveaux)
 308 tests Flutter        passés
  15 skipped              (réseau)
```

## K. Lint

`ruff check backend tests scripts` → **All checks passed**.
`dart analyze` → **No issues found**.

## L. Vérification de types

`mypy --python-version 3.13` sur `detection.py`, `history_scan.py` et
`pattern_validation/` → **0 erreur**.

Note d'outillage : `pyproject.toml` déclare `python_version = "3.11"` alors que
le projet tourne en 3.13, ce qui fait échouer `mypy` sur les stubs de numpy
avant même d'atteindre le code. Signalé, non modifié — fichier partagé avec une
autre session active.

## M. Problèmes découverts

**1. `make_pattern_id` n'acceptait que des `datetime`.** La charge utile porte
des chaînes ISO : l'identité aurait dépendu du point d'appel. Corrigé par
normalisation.

**2. Un test instable selon l'heure de la journée.**
`test_lot2_infra::test_save_is_idempotent` échouait. Ce n'est pas une
régression : je l'ai vérifié en rejouant la suite sur `HEAD` dans un worktree
isolé, où il échoue aussi. La cause : `test_analysis_identity` sème 120 bougies
hebdo SOL espacées de 168 h **à partir de l'heure courante** ; selon l'heure,
l'une d'elles tombe sur `2026-01-0X` et le premier enregistrement du test
n'était plus entièrement nouveau. Corrigé en déplaçant la base du test à 2001,
hors de portée des semis.

**3. Douze figures sans niveau de déclenchement** sur BTC 1 j — drapeaux,
biseaux, triangles. Elles ne peuvent structurellement jamais atteindre
`CONFIRMED`. C'est PHASE C.

**4. Aucun objectif théorique.** `target.level` est nul partout.

## Ce qui n'a pas été fait, volontairement

`PatternDetection` n'est pas encore l'objet **transporté** : `/chart` publie des
dictionnaires enrichis par le même pont, pas des instances sérialisées. La
raison est la compatibilité : basculer la sérialisation entière changerait
l'ordre et le nom des clés historiques, ce que tu as interdit. L'étape suivante
du plan de migration (`patterns_v2[]` en parallèle, puis retrait) reste
disponible quand le frontend sera prêt.

## Prochaine étape

PHASE C, comme convenu : donner une frontière de cassure — **possiblement
inclinée** — aux triangles, biseaux et drapeaux, brancher les six états, et
distinguer mèche et clôture.
