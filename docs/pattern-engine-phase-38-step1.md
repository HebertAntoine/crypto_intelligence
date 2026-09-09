# PHASE 38 — première exécution : sources, licences, taxonomie, plan

Aucun entraînement lancé. Aucune donnée téléchargée. Aucun seuil de détecteur
touché.

## Préalable : les chandeliers ne décident plus rien, et c'est dans le code

Ta conclusion officielle — `DESCRIPTIVE_ONLY` — est gravée dans
`candlesticks/taxonomy.py` avec **la mesure qui la justifie** :

```python
USAGE = "DESCRIPTIVE_ONLY"
USAGE_EVIDENCE = "PHASE 37B : 216 dossiers, 1 040 tests, 0 POSITIVE_EDGE, …"
```

Et surtout, un test parcourt `engines/`, `analysts/`, `pipeline/`, `api/` et
`reports/` et **échoue** si l'un d'eux mentionne les chandeliers. Aujourd'hui
aucun ne le fait ; le jour où quelqu'un branche, la suite le dira. La contrainte
vit dans les tests, pas dans un commentaire — et elle porte sa raison, pour ne
pas être levée un jour sans qu'on sache pourquoi elle existait.

---

# A + B. Audit final et licences

Neuf sources, vérifiées le 9 septembre 2026 via les **API officielles** —
fichier `LICENSE` par l'API GitHub, `licenseName` par l'API Kaggle, carte de
modèle par l'API Hugging Face. Jamais depuis une description.

| Source | Type | Version vérifiée | Licence | Vérifiée | Statut |
|---|---|---|---|:-:|---|
| **crypto-chart-patterns** (Tyson Cung) | moteur de règles | commit `1601b0c8` | **MIT** | ✅ | **`TRAIN_ALLOWED`** |
| **Kaggle human-labeled OHLCV** | jeu OHLC | v3, 2025-03-26 | **CC BY 4.0** | ✅ | **`VALIDATION_ALLOWED`** |
| CandleEdge | moteur de règles | commit `75761e26` | MIT | ✅ | `REFERENCE_ONLY` |
| OHLC_Candlestick_Patterns | moteur de règles | commit `1c24789c` | MIT | ✅ | `REFERENCE_ONLY` |
| Lo, Mamaysky & Wang (2000) | référence | *J. Finance* 55(4) | article, NBER w7613 libre | ✅ | `REFERENCE_ONLY` |
| zeta-zetra/chart_patterns | moteur de règles | commit `44f8baa3` | **AUCUNE** | ✅ | `BLOCKED_PENDING_LICENSE` |
| FODUU YOLOv8 | modèle | 2025-04-02 | **non déclarée** + AGPL héritée | ✅ | `BLOCKED_PENDING_LICENSE` |
| Roboflow (2 jeux) | jeux d'images | **non vérifiable** | **non vérifiée** | ❌ | `BLOCKED_PENDING_LICENSE` |
| Stock-Pattern-Analysis | jeu OHLC | **non identifiée** | inconnue | ❌ | `BLOCKED_PENDING_LICENSE` |

Les licences sont vérifiées **au niveau du fichier**, avec l'attribution :

- `MIT License / Copyright (c) 2024 Tyson Cung`
- `The MIT License (MIT) / Copyright (c) 2026 Michael Schwartz`
- `MIT License / Copyright (c) 2026 bakunet`

Et pour les quatre volets que tu demandais séparément : **licence du code**,
**des données**, **des annotations**, **des poids**. Le seul dépôt retenu ne
livre **aucune donnée** — ses 6 Mo sont un carnet Jupyter de 2,5 Mo et cinq
fichiers Python. La licence du code couvre donc tout, et il n'y a pas de
licence d'annotations distincte à établir.

## Ce que j'ai découvert en lisant le code, pas la description

**`crypto-chart-patterns` n'est pas indépendant de nous au sens qui compte.**
Son détecteur fait :

```python
smooth_prices = prices['c'].rolling(window=smoothing).mean().dropna()
local_max = argrelextrema(smooth_prices.values, np.greater)[0]
```

Trois faits en découlent, et aucun n'était dans sa documentation :

1. **Il regarde 1 barre en avant.** `argrelextrema` d'ordre 1 compare chaque
   point à ses deux voisins : un maximum en `i` n'est connu qu'une fois `i+1`
   imprimée. Acceptable pour comparer des **formes** ; jamais pour produire une
   observation datée. Nos pivots, eux, portent un `confirmation_index` explicite.
2. **Il travaille sur les clôtures**, nous sur les hauts et les bas. Les pivots
   ne coïncideront pas exactement, et la comparaison devra tolérer cet écart
   plutôt que le compter comme un désaccord.
3. **Sa famille de méthode est voisine de la nôtre** — `SMOOTHED_EXTREMA`
   contre `CAUSAL_PIVOTS`. C'est exactement ce que ton LOT 6 met en garde : son
   accord sera une confirmation **faible**, parce que nos erreurs seront
   corrélées.

**Le risque AGPL dépasse la source concernée.** Ultralytics déclare que
l'AGPL-3.0 couvre les **modèles produits** par son code d'entraînement. Donc
entraîner `ChartPatternVision` avec Ultralytics rendrait **notre** modèle
AGPL — c'est-à-dire imposerait de publier ce projet entier. `torchvision`
(BSD) ou `timm` (Apache-2.0) évitent le problème. C'est une décision sur la
licence de ton produit, pas un détail d'outillage.

**Roboflow refuse l'accès automatisé.** `universe.roboflow.com` → HTTP 403,
`api.roboflow.com` → HTTP **401**. Le 401 est instructif : l'API existe et
attend une clé. C'est la voie légitime, et **toi seul peux créer ce compte**.
Aucun contournement n'a été tenté.

**La source D n'existe pas sous ce nom.** Quatre dépôts `Stock-Pattern-Analysis`
existent, **tous à 0 étoile et sans licence**, aucun ne correspondant à la
description. Il me faut l'URL exacte.

---

# C. Taxonomie canonique

`pattern_learning/ontology.py` — **22 noms canoniques**, exactement ceux que tu
as listés.

**La résolution ne compare jamais des chaînes.** `canonical()` fait passer
`H&S`, `M_Head`, `Channel Up`, `cup-and-handle`, `IHS`, `W_Bottom` et
`double_top` vers le même vocabulaire. Un nom inconnu renvoie **`None`** — pas
une supposition : deviner ferait entrer une figure mal identifiée dans une
comparaison, et le désaccord qui en résulterait serait attribué au marché
plutôt qu'à la table.

**Les deux taxonomies restent séparées, par construction.** `canonical("hammer")`
ne renvoie pas `None` : il **lève une exception**. C'est une erreur d'appel, pas
une donnée manquante, et la distinction compte — un `None` silencieux
ressemblerait à un nom inconnu.

Ce que notre moteur couvre :

| Détecté aujourd'hui (13) | Manquant (9) |
|---|---|
| doubles, triples, ETE et ETE inversée, trois triangles, deux biseaux, deux drapeaux | fanions ×2, canaux ×3, tasse avec anse, rectangle, arrondis ×2 |

Sur les neuf manquants, **un seul** est couvert par la source autorisée :
`crypto-chart-patterns` détecte les trois canaux et la tasse avec anse. Les
fanions et les arrondis ne sont couverts par **aucune** source utilisable.

**`MethodFamily`** est déclarée pour chaque moteur, d'après le code lu :

| Moteur | Famille |
|---|---|
| le nôtre | `CAUSAL_PIVOTS` |
| crypto-chart-patterns | `SMOOTHED_EXTREMA` |
| zeta-zetra (bloqué) | `CAUSAL_PIVOTS` |
| CandleEdge, OHLC_Candlestick_Patterns | `CANDLE_RULES` |
| FODUU (bloqué) | `VISION_MODEL` |
| Lo-Mamaysky-Wang | `KERNEL_SMOOTHING` |

---

# D. Plan d'ingestion

**Ce qui est possible aujourd'hui — environ 16 Mo.**

1. Cloner `crypto-chart-patterns` au commit `1601b0c8` dans
   `data/external/raw/`, **immuable**, avec SHA256 et `manifest.json`.
   Ne jamais l'importer dans le paquet : l'exécuter **hors** du produit, comme
   comparateur, sur nos propres bougies BTC/ETH/SOL.
2. Consigner MIT et l'attribution dans `docs/THIRD_PARTY_CODE.md`.
3. Kaggle source C, 9,5 Mo, via l'API officielle (compte requis). Marqué
   `SYNTHETIC` et `VALIDATION_ALLOWED` **dès l'ingestion**, pour qu'aucune
   mesure de performance crypto ne s'appuie dessus par inadvertance.

**Ce qui attend une action de ta part.**

4. Roboflow : une clé d'API.
5. `zeta-zetra` : une licence de l'auteur. Une issue suffirait, et cela
   débloquerait la meilleure source du lot. Je ne l'ai pas ouverte — cela
   engage ton nom sur un dépôt public.
6. Source D : son URL exacte.

**Arborescence prévue** (rien n'est encore créé) :

```
data/external/raw/          immuable, hors git
data/external/processed/    hors git
scripts/fetch_pattern_sources.py
docs/THIRD_PARTY_CODE.md
docs/THIRD_PARTY_DATASETS.md
```

Aucun fichier de `structure/`, `candlesticks/` ou `api/` n'est touché.

---

# E. Moteurs externes réellement exploitables

**Un seul : `crypto-chart-patterns`.**

Et il faut être précis sur ce qu'il vaut. Il coche les bonnes cases — MIT,
Python, Binance, mêmes unités, quinze familles dont cinq qui nous manquent.
Mais il est de **famille voisine**, il **regarde une barre en avant**, et il
travaille sur les **clôtures**.

Conséquence directe sur ton plan :

> **Le consensus à trois voix de la PHASE 38 § 8 ne peut pas exister.**

Avec un seul comparateur, et de surcroît corrélé au nôtre, les cinq états
`STRONG_AGREEMENT` … `NO_EXTERNAL_EVIDENCE` se réduisent à trois utilisables :
accord, désaccord, ou aucune évidence externe. C'est **suffisant pour le hard
case mining** du § 9 — un désaccord reste le meilleur indicateur d'un cas
difficile — mais ce n'est **pas** une validation.

Une baseline réellement indépendante existe pourtant, et elle est gratuite :
**réimplémenter Lo-Mamaysky-Wang** (régression à noyau puis appariement). Sa
famille de méthode est *différente* de la nôtre, ce qui est précisément la
condition pour que son accord veuille dire quelque chose. C'est du code à
écrire, pas une licence à obtenir.

---

# Ce qui a été livré

| Élément | Détail |
|---|---|
| `pattern_learning/ontology.py` | 22 noms canoniques, alias, `MethodFamily`, séparation des taxonomies |
| `pattern_learning/sources.py` | 9 sources, licence vérifiée et **preuve** attachée à chacune |
| `candlesticks/taxonomy.py` | `USAGE = DESCRIPTIVE_ONLY` + la mesure qui le justifie |
| `test_pattern_ontology.py` | 35 tests |
| `test_candlestick_validation.py` | 3 tests de garde supplémentaires |

Dont deux gardes qui échoueront si le plan change sans qu'on s'en aperçoive :

- **une source dont la licence n'est pas vérifiée ne peut jamais être
  utilisable** — le refus est l'état par défaut ;
- **exactement une source est `TRAIN_ALLOWED`** — si ce compte change, le plan
  de consensus change avec lui, et le test le dira.

```
1173 tests backend        passés   (+38)
ruff check                propre
mypy --python-version 3.13  0 erreur sur les modules nouveaux
```

---

# Ce que je recommande avant l'étape suivante

**Trois questions te reviennent :**

1. **Ouvres-tu un compte Roboflow ?** Sans clé, les deux jeux d'images restent
   invérifiables, et toute la branche vision avec eux.
2. **Demandes-tu une licence à `zeta-zetra` ?** C'est le seul moyen d'obtenir un
   second moteur Python couvrant nos familles — et un fanion, que rien d'autre
   ne couvre.
3. **Acceptes-tu que le modèle visuel soit AGPL ?** Si non, il faudra
   `torchvision` ou `timm`, jamais Ultralytics.

**Et une recommandation de méthode.** Plutôt que d'attendre ces réponses, la
baseline Lo-Mamaysky-Wang est réimplémentable immédiatement, sans licence ni
téléchargement, et donnerait le second avis **réellement indépendant** qui
manque à tout le plan. Je pense que c'est la prochaine étape la plus utile.

Je m'arrête ici, comme demandé.
