# Étape 1 — audit des sources externes

**Aucun téléchargement n'a eu lieu.** Ce document ne contient que des
vérifications faites sur les sources officielles, le 9 septembre 2026.

Méthode : API GitHub (`api.github.com/repos/...` et `/readme`), API Kaggle
(`kaggle.com/api/v1/datasets/list`), API Hugging Face
(`huggingface.co/api/models/...`), et pages officielles. Chaque fait ci-dessous
vient d'une de ces réponses, pas du texte de la mission.

---

## Tableau de synthèse

| Source | Type | Version / commit | Taille | Classes | OHLCV brut | Image | Géométrie | Origine du label | Licence | Usage commercial | Rôle proposé | Risque | Verdict |
|---|---|---|---|---|:-:|:-:|:-:|---|---|---|---|---|---|
| **A** Roboflow chart-pattern | IMAGE_DATASET | **non vérifiable** | ? | ? | non | oui | bbox/masque | DATASET_AUTHOR | **non vérifiée** | inconnu | — | accès bloqué | **BLOCKED_PENDING_LICENSE** |
| **B** Roboflow candlestick | IMAGE_DATASET | **non vérifiable** | ? | ? | non | oui | bbox | DATASET_AUTHOR | **non vérifiée** | inconnu | — | accès bloqué | **BLOCKED_PENDING_LICENSE** |
| **C** Human Labeled OHLCV | OHLC_DATASET | **v3**, 2025-03-26 | **9,5 Mo** | lignes/rayons | oui | non | lignes | HUMAN (auteur) | **CC BY 4.0** ✅ | oui, avec attribution | référence supports/trendlines | **synthétique** | **VALIDATION_ALLOWED** |
| **D** Stock-Pattern-Analysis | OHLC_DATASET | **introuvable** | ? | 4 | ? | ? | ? | ? | **inconnue** | inconnu | — | source non identifiée | **BLOCKED_PENDING_LICENSE** |
| **E** tysoncung/crypto-chart-patterns | RULE_ENGINE | `1601b0c8`, 2026-05-05 | 6,1 Mo | **17** | oui (Binance) | non | extrema | RULE_ENGINE | **MIT** ✅ | oui | **INDEPENDENT_DETECTOR_A** | faible | **TRAIN_ALLOWED** |
| **F** michaelsboost/CandleEdge | RULE_ENGINE | `75761e26`, 2026-05-25 | 5,4 Mo | chart + chandeliers | via import | non | tracés | RULE_ENGINE | **MIT** ✅ | oui | detector B *si porté* | **navigateur, pas Python** | **REFERENCE_ONLY** |
| **G** zeta-zetra/chart_patterns | RULE_ENGINE | `44f8baa3`, 2024-07-08 | 575 Ko | doubles, flags, ETE, triangles, fanions | oui | non | pivots | RULE_ENGINE | **AUCUNE** ❌ | **non** | — | pas de droit d'usage | **BLOCKED_PENDING_LICENSE** |
| **H** przemyslawbak/OHLC_Candlestick_Patterns | RULE_ENGINE | `1c24789c`, 2026-07-20 | 1,1 Mo | **37+37+9+9+2** | oui | non | non | RULE_ENGINE | **MIT** ✅ | oui | contrôle chandeliers | **écrit en C#** | **REFERENCE_ONLY** |
| **I** foduucom yolov8 | PRETRAINED_MODEL | 2025-04-02 | modèle `.pt` | **6** | non | oui | bbox | MODEL | **non déclarée** ❌ + AGPL-3.0 hérité | **non sans licence Entreprise** | — | **contamination AGPL** | **BLOCKED_PENDING_LICENSE** |
| **J** Lo, Mamaysky & Wang | ACADEMIC_REFERENCE | *J. Finance* 55(4) 1705-1765, 2000 | — | 10 figures | — | — | méthodologie | — | article, NBER w7613 en accès libre | méthode réimplémentable | **baseline scientifique** | aucun | **REFERENCE_ONLY** |

---

## 1. Sources réellement recommandées

### E — `tysoncung/crypto-chart-patterns` : la seule pleinement exploitable

C'est la meilleure source de tout ce lot, et de loin.

- **MIT**, confirmée par l'API GitHub. Dernier commit `1601b0c8`, 2026-05-05.
- **Python pur** : `pandas`, `numpy`, `scipy`, `matplotlib`. Aucune dépendance ML
  malgré une description GitHub trompeuse qui parle de « deep learning » — le
  README et le `requirements.txt` disent le contraire. **C'est bien un moteur de
  règles**, comme la mission le supposait.
- Il travaille sur **l'API Binance**, aux unités 1m → 1d. **Mêmes actifs, même
  source de données, mêmes unités que nous.** C'est ce qui en fait un
  comparateur valable plutôt qu'une curiosité.
- Familles détectées, d'après le README : ETE, ETE inversée, double sommet,
  double creux, triangles (asc./desc./sym.), biseaux (asc./desc.), drapeaux
  (haussier/baissier), canaux (asc./desc./horizontal), tasse avec anse.
  **17 types**, dont 5 que nous n'avons pas : les trois canaux, la tasse avec
  anse, et les fanions ne sont pas listés.
- Méthode annoncée : détection d'extrema locaux + analyse mathématique —
  la même famille d'approche que la nôtre, ce qui est à la fois un avantage
  (comparable) et une limite (les erreurs corrélées ne se verront pas).

**Rôle : `INDEPENDENT_DETECTOR_A`.** C'est la seule source qui permet
d'exécuter l'ÉTAPE 4 telle que la mission la décrit.

### C — Kaggle `human-labeled-synthetic-stock-market-data`

- **CC BY 4.0**, confirmée textuellement par l'API Kaggle
  (`"Attribution 4.0 International (CC BY 4.0)"`).
- **Version 3**, mise à jour 2025-03-26, **9,5 Mo**, 343 téléchargements,
  4 votes.
- Le sous-titre officiel dit lui-même : *« A growing dataset of **synthetically
  generated** financial charts and annotations »*, et l'un des tags est
  `synthetic`. **`data_domain = SYNTHETIC` est confirmé par la source**, pas
  supposé.

**Rôle : `VALIDATION_ALLOWED` seulement.** Des annotations humaines de
supports, résistances et trendlines sur des séries **fabriquées** peuvent servir
à vérifier qu'un détecteur de lignes se comporte raisonnablement. Elles ne
peuvent pas mesurer sa performance sur BTC.

### J — Lo, Mamaysky & Wang (2000)

Référence exacte vérifiée : *Foundations of Technical Analysis: Computational
Algorithms, Statistical Inference, and Empirical Implementation*, **Journal of
Finance 55(4), 1705-1765**. Version de travail NBER **w7613** en accès libre.

Méthode : **régression à noyau non paramétrique** pour lisser la série, puis
extraction des extrema, puis appariement de figures. C'est exactement la
baseline scientifique que demande la PHASE 38.

**Rôle : `REFERENCE_ONLY`** — méthodologie à réimplémenter, aucun code à copier.

---

## 2. Sources rejetées

### F — CandleEdge : bon projet, mauvais format

MIT confirmée. Mais l'API GitHub donne `"language": "HTML"` : c'est une
**application navigateur client-side**. Son README l'assume — *« running
directly in the browser »*, *« no machine learning black boxes »*.

Créée et poussée le **même jour** (2026-05-25), 4 étoiles. L'utiliser comme
`INDEPENDENT_DETECTOR_B` dans un pipeline Python demanderait de **porter du
JavaScript**, c'est-à-dire de réécrire ses règles — auquel cas ce n'est plus un
détecteur indépendant, c'est notre code inspiré du sien.

Par ailleurs sa fonction principale — « quelle a été la suite historique de
cette figure » — **recouvre ce que nous avons déjà construit** en PHASE C
(cassure, retest, résolution) et ce que prévoit la PHASE 32 (MFE/MAE).

**Verdict : `REFERENCE_ONLY`.** À lire pour ses définitions, pas à intégrer.

### H — OHLC_Candlestick_Patterns : bon, mais en C#

MIT confirmée, 37 étoiles, actif (2026-07-20). Mais `"language": "C#"`.

Et surtout, il couvre **37 figures haussières + 37 baissières de chandeliers** —
c'est-à-dire la **famille `CANDLESTICK_PATTERN`**, pas les grandes structures.
La mission le dit elle-même : ne jamais mélanger `HAMMER` et `DOUBLE_TOP`. Or
notre moteur ne détecte aujourd'hui **aucune figure de chandelier**.

**Verdict : `REFERENCE_ONLY`.** Il n'a rien à comparer avec ce que nous
produisons tant que la PHASE 37 n'existe pas.

---

## 3. Sources bloquées pour licence

### G — `zeta-zetra/chart_patterns` : **aucune licence**

C'est la perte la plus regrettable. 121 étoiles, **Python**, et il détecte
exactement nos familles : doubles, drapeaux, ETE, ETE inversée, triangles,
fanions. Ce serait le meilleur `INDEPENDENT_DETECTOR_B` possible.

Mais l'API GitHub renvoie `"license": null`. Sans licence explicite, le droit
d'auteur par défaut s'applique : **aucun droit d'usage, de copie ou de
modification n'est accordé**. Un dépôt public n'est pas un dépôt libre.

**Action possible :** ouvrir une issue demandant à l'auteur d'ajouter une
licence. C'est gratuit et cela débloquerait la meilleure source du lot. Je ne
l'ai pas fait — cela engage ton nom sur un dépôt public.

### I — FODUU YOLOv8 : double problème

**Premier problème.** L'API Hugging Face renvoie une carte de modèle **sans
champ `license`**, et la page ne l'indique pas davantage. 429 likes,
27 545 téléchargements par mois, et aucune licence déclarée.

**Second problème, plus grave.** Ultralytics publie YOLOv8 sous **AGPL-3.0**, et
sa licence **couvre les modèles produits par le code d'entraînement**. Un modèle
dérivé de YOLOv8 est donc AGPL-3.0 par défaut. Se conformer à l'AGPL-3.0
imposerait de **publier le code source complet de l'œuvre dérivée** — ce qui,
pour une dépendance de production, signifierait publier ce projet entier.

**Ce point dépasse la source I.** Il contraint la **PHASE 12** : si
`ChartPatternVision` est entraîné avec Ultralytics, **notre propre modèle
devient AGPL-3.0**. Une alternative existe — `torchvision` (BSD) ou `timm`
(Apache-2.0) — mais c'est une décision de projet, pas un détail d'outillage.

Accessoirement, ses 6 classes sont pauvres : `Head and shoulders bottom`,
`Head and shoulders top`, `M_Head`, `StockLine`, `Triangle`, `W_Bottom`.
`StockLine` n'est pas une figure. `M_Head` et `W_Bottom` sont des noms
alternatifs de double sommet et double creux. **mAP@0,5 = 0,614** — faible.

### A et B — Roboflow : **accès automatisé refusé**

`universe.roboflow.com` répond **HTTP 403** à toute requête automatisée, sur les
deux jeux. Je n'ai donc **pas pu vérifier** : ni la licence, ni la version, ni le
nombre d'images, ni la liste des classes.

Conformément à ta règle — aucun contournement, aucun scraping non autorisé — je
n'ai pas cherché à passer outre. Le chemin légitime est l'**API Roboflow avec
une clé de compte**, que tu es seul à pouvoir créer.

**Tant que ce n'est pas fait, les chiffres du prompt (3 498 images / 20 classes,
9 900 images / 26 classes, CC BY 4.0) restent invérifiés.** Mes recherches ont
trouvé d'autres jeux Roboflow portant des noms voisins mais des tailles très
différentes (43 images, 1 455 images), ce qui laisse penser qu'il existe
plusieurs jeux homonymes. **Se tromper de jeu serait facile.**

---

## 4. Chevauchements entre datasets

| | E | F | G | H | I |
|---|:-:|:-:|:-:|:-:|:-:|
| Doubles | ✅ | ✅ | ✅ | ❌ | ✅ (M_Head/W_Bottom) |
| Triples | ❌ | ? | ❌ | ❌ | ❌ |
| ETE / ETE inv. | ✅ | ✅ | ✅ | ❌ | ✅ |
| Triangles | ✅ | ✅ | ✅ | ❌ | ✅ (une seule classe) |
| Biseaux | ✅ | ✅ | ✅ | ❌ | ❌ |
| Drapeaux | ✅ | ✅ | ✅ | ❌ | ❌ |
| Fanions | ❌ | ✅ | ✅ | ❌ | ❌ |
| Canaux | ✅ | ❌ | ❌ | ❌ | ❌ |
| Tasse avec anse | ✅ | ❌ | ❌ | ❌ | ❌ |
| Chandeliers | ❌ | ✅ | ❌ | ✅ | ❌ |

Le recouvrement réel entre les sources **autorisées** est mince : seul E couvre
nos familles. Il n'y aura donc **pas de consensus à trois** au sens de la
PHASE 18 — au mieux un accord ou un désaccord entre deux moteurs.

## 5. Classes manquantes chez nous

Notre moteur détecte 13 types. Comparé à l'ontologie de la PHASE 4 :

| Manquant | Présent chez E ? | Commentaire |
|---|:-:|---|
| `BULL_PENNANT` / `BEAR_PENNANT` | ❌ | présent chez G (bloqué) |
| `ASCENDING_CHANNEL` / `DESCENDING_CHANNEL` / `HORIZONTAL_CHANNEL` | ✅ | E est la seule référence disponible |
| `CUP_HANDLE` | ✅ | idem |
| `RECTANGLE_RANGE` | ❌ | nous avons `RangeIntelligenceEngine`, non exposé comme figure |
| `ROUNDING_TOP` / `ROUNDING_BOTTOM` | ❌ | aucune source autorisée |
| Chandeliers (famille entière) | ❌ | H, mais en C# |

---

## 6. Plan d'ingestion proposé

Il est **beaucoup plus petit** que ce que la mission envisage, parce que la
plupart des sources ne survivent pas à la vérification.

**Étape 2a — la seule ingestion réellement possible aujourd'hui**

1. Cloner `tysoncung/crypto-chart-patterns` au commit `1601b0c8` dans
   `data/external/raw/`, **immuable**, avec SHA256 et `manifest.json`.
2. Ne pas l'importer dans le produit. L'exécuter **hors du paquet** comme
   comparateur, sur nos propres bougies BTC/ETH/SOL.
3. Consigner MIT et l'attribution dans `THIRD_PARTY_CODE.md`.

**Étape 2b — sous condition**

4. Kaggle source C : téléchargeable via l'API Kaggle officielle (compte requis).
   9,5 Mo. Marqué `SYNTHETIC` et `VALIDATION_ALLOWED` dès l'ingestion.

**Étape 2c — bloqué en attente de toi**

5. Roboflow A et B : nécessitent une clé d'API que je ne peux pas créer.
6. `zeta-zetra/chart_patterns` : nécessite une licence de l'auteur.
7. Source D : je ne l'ai pas identifiée. Il me faut l'URL exacte.

## 7. Espace disque estimé

| Élément | Taille |
|---|---|
| E, dépôt complet | 6,1 Mo |
| C, dataset Kaggle | 9,5 Mo |
| **Total immédiatement possible** | **~16 Mo** |
| A + B, si débloqués (≈13 400 images) | ~2 à 4 Go estimés |
| Rendus de nos propres OHLCV (PHASE 13) | ~1 à 3 Go selon la couverture |

**176 Go libres** sur le disque (80 % occupé). Aucune contrainte, même dans le
scénario complet.

## 8. Dépendances nécessaires

État réel vérifié :

| Composant | Présent | Note |
|---|---|---|
| GPU | ✅ **RTX 4070 SUPER, 12 Go** | largement suffisant pour de la vision |
| `torch` | ⚠️ **2.14.0+cpu** | **build CPU** — le GPU est inutilisable en l'état |
| `scikit-learn` | ✅ 1.9.0 | suffit pour le `PatternVerifier` numérique |
| `transformers`, `sentence-transformers` | ✅ | déjà là pour la base de connaissances |
| `Pillow`, `opencv` | ❌ | requis dès qu'on touche à l'image |
| `ultralytics` | ❌ | **et à éviter** — voir le point AGPL |
| `kaggle` | ❌ | requis pour la source C |

À installer **uniquement si les phases correspondantes sont validées** :
`pillow`, `kaggle`. Et `torch` en build CUDA seulement si la branche vision est
retenue.

## 9. Modifications prévues au projet

Aucune en ÉTAPE 1. Pour l'ÉTAPE 2, si tu la valides :

```
data/external/raw/          nouveau, immuable, hors git
data/external/processed/    nouveau, hors git
docs/THIRD_PARTY_CODE.md    nouveau
docs/THIRD_PARTY_DATASETS.md nouveau
scripts/fetch_pattern_sources.py  nouveau
backend/crypto_intel/pattern_learning/sources/  nouveau, registre
.gitignore                  ajouter data/external/
```

**Aucun fichier de `backend/crypto_intel/structure/` ni `api/` n'est touché.**

## 10. Aucun code métier modifié

Confirmé. Cette étape n'a produit que ce document.

---

## Ce que je te recommande, et pourquoi c'est plus étroit que la mission

Trois constats que la vérification impose :

**1. Une seule source utilisable.** Sur dix sources, une seule est à la fois
licenciée, dans le bon langage, et sur les bons actifs. Le « consensus externe »
de la PHASE 18 ne peut pas exister avec un seul comparateur — au mieux un
**accord ou un désaccord**, ce qui reste utile pour le *hard-case mining* de la
PHASE 20, mais n'est pas un vote.

**2. L'AGPL contamine la branche vision.** Entraîner avec Ultralytics rendrait
notre modèle AGPL-3.0. Ce n'est pas un détail : c'est une décision sur la
licence de ton produit.

**3. La branche vision est la plus faible du plan, et la moins vérifiable.**
Ses deux jeux de données sont inaccessibles, son modèle de référence n'a pas de
licence et plafonne à mAP 0,614, et elle introduirait un **second décalage de
domaine** — non seulement actions → crypto, mais aussi *style de rendu d'autrui*
→ *notre rendu*. Ta propre PHASE 26 prévoit de l'abandonner si elle n'améliore
rien ; je pense qu'elle mérite d'être **différée** plutôt que testée en premier.

**Ce qui n'a pas changé :** aucune de ces sources ne remplace le jeu annoté
humain. E donne un second avis, pas une vérité. Le goulot reste la PHASE D — les
300 à 500 cas que toi seul peux trancher.

Je m'arrête ici, comme demandé.
