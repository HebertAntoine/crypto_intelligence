# Pipeline de données

## Vue d'ensemble

```
providers/          →  Observation (FAIT)
engines/            →  Computation (CALCUL)
analysts/           →  Interpretation (INTERPRÉTATION)
chief + scenarios   →  Hypothesis (HYPOTHÈSE)
```

Chaque étage ne connaît que celui du dessous. Aucun appel réseau n'existe en
dehors de `providers/`.

## 1. Collecte

`Pipeline.collect_asset()` lance toutes les capacités **en parallèle** via
`asyncio.gather` — le goulot d'étranglement est la latence réseau, pas le calcul.

Chaque appel passe par le registre, qui essaie les providers dans l'ordre
configuré. Un provider ne lève jamais d'exception vers le métier : il retourne
un `FetchResult` qualifié.

```python
FetchStatus.OK                 # données présentes
FetchStatus.NOT_CONFIGURED     # clé API absente
FetchStatus.BLOCKED_BY_SOURCE  # la source refuse l'accès automatisé
FetchStatus.RATE_LIMITED
FetchStatus.NETWORK_ERROR
FetchStatus.PARSE_ERROR
FetchStatus.NO_DATA
```

C'est ce qui permet au rapport d'afficher *pourquoi* une donnée manque, plutôt
que de la faire disparaître silencieusement.

## 2. Normalisation

Toute donnée devient une `Observation` portant :

```
asset · metric · value (valeur ORIGINALE) · unit
timestamp (à quoi elle se rapporte) · fetched_at (quand on l'a lue)
source · provider · source_url · freshness · confidence · quality
```

L'`id` est un hash déterministe de `provider|asset|metric|timeframe|timestamp` :
recollecter la même donnée met à jour la ligne au lieu de la dupliquer.

## 3. Fraîcheur

Calculée, jamais déclarée. Les seuils dépendent de la **classe de métrique** et,
pour les séries à barres, de **l'intervalle** :

```python
compute_freshness(ts, "price")                          # bougie 15m
compute_freshness(ts, "price", interval_minutes=10080)  # bougie 1w
```

Sans le second appel, une bougie hebdomadaire ouverte il y a trois jours serait
classée `STALE` alors qu'elle est la bougie courante. Ce défaut existait dans une
première version et faussait la confiance technique de 88 % à 40 %.

## 4. Cache

`data/cache/` — TTL par capacité, configuré dans `providers.yaml` :
prix 60–300 s, dérivés 300 s, DeFi 1800 s, ETF 6 h, CoinGecko 600 s
(API gratuite très limitée).

## 5. Persistance

`repo.save_observations()` fait un upsert par id. La collecte est donc idempotente
et peut tourner en boucle sans gonfler la base.

## 6. Calcul

Les engines reçoivent des `Observation` et produisent des structures typées.
Ils sont **entièrement déterministes** et testables hors ligne : aucun n'importe
`llm/`. Le système produit une analyse complète même sans modèle configuré.

## 7. Agrégation

`ScoringEngine` transforme chaque analyse en `ScoreCard`
(score, confiance, fraîcheur, nombre de preuves), puis
`MarketConvictionEngine` pondère :

```
poids_effectif = poids_actif × f(confiance) × g(fraîcheur) × h(horizon)
```

## 8. Analyse IA

Les dix analystes produisent chacun une sortie structurée. Le
`ChiefMarketAnalyst` ne reçoit **que ces conclusions**, jamais les séries brutes.
Chaque appel est petit, ciblé et à schéma strict.

## 9. Rapport

`reports/renderer.py` produit le rapport texte. Toute donnée absente y apparaît
comme `UNAVAILABLE` accompagné de sa raison.

## Cadences du scheduler

| Tâche | Intervalle |
|---|---|
| Collecte complète | 15 min |
| Évaluation des rapports passés | 30 min |

Activation : `SCHEDULER_ENABLED=true`.
