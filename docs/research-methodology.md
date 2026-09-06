# Méthodologie de recherche

Ce document décrit comment les études quantitatives sont conduites, et surtout
**les garde-fous** qui empêchent le système de se raconter des histoires.

---

## 1. Le principe : mesurer, pas supposer

Un indicateur n'est pas retenu parce qu'il « semble logique ». Il est mesuré.
Découvrir qu'un signal est inutile est un résultat, pas un échec — et ces
résultats négatifs sont affichés au même niveau que les positifs, dans
`make research` comme dans la page Research.

---

## 2. Aucun look-ahead

C'est la contrainte structurante.

### Séparation physique des structures

Les features et les rendements futurs vivent dans **deux DataFrames distincts**.
Une feature ne peut donc pas contenir une valeur future par accident :

```python
signals = build_signals(flows)          # rolling() uniquement → regarde en arrière
fwd     = forward_returns(close, [1,7]) # shift(-n) → regarde en avant
joined  = signals.join(fwd)             # jonction : signal en t, rendement après t
```

### Seuils d'événements calculés en glissant

Un événement « flux ETF extrême » est défini par un **percentile sur 252 jours
glissants**, pas sur l'historique complet :

```python
flow > flow.rolling(252, min_periods=60).quantile(0.90)
```

Utiliser le percentile de tout l'historique laisserait fuiter le futur dans la
**définition même** de l'événement — une erreur discrète et fatale.

### Vérification par mutation

Un test modifie les 30 à 60 dernières barres et vérifie qu'**aucune** valeur de
feature antérieure ne change. Si une feature bougeait, elle lirait le futur.

---

## 3. Le contrôle contemporain

Chaque étude de décalage calcule aussi la corrélation **du même jour**. C'est le
contrôle qui rend le résultat interprétable :

| Contemporain | Horizons futurs | Lecture |
|---|---|---|
| fort | plats | le signal **suit** le prix |
| fort | forts | le signal accompagne ET précède |
| faible | forts | le signal **précède** réellement |

Mesuré sur BTC : contemporain **+0.408**, horizons 1–7 jours ≈ 0.

---

## 4. Comparaisons multiples

9 signaux × 7 horizons = **63 hypothèses**. À p<0.05, environ **3 résultats
« significatifs » sont attendus par pur hasard**.

La correction **Benjamini-Hochberg** (contrôle du taux de fausses découvertes)
est donc appliquée, et c'est elle qui alimente le drapeau `significant`. Le
`significant_raw` non corrigé reste exposé, pour montrer l'écart.

Résultat mesuré :

| Actif | p<0.05 bruts | attendus par hasard | survivent à la FDR |
|---|---|---|---|
| BTC | 8 | 3.2 | **3** |
| ETH | 10 | 3.2 | **0** |

Sans cette correction, on aurait « trouvé » 10 signaux sur ETH. Il n'y en a aucun.

---

## 5. Validation temporelle

Découpage **chronologique**, jamais aléatoire — un tirage aléatoire mélange
passé et futur dans une série temporelle :

```
train 60 %  |  validation 20 %  |  out-of-sample 20 %
```

Le critère retenu n'est pas « significatif en OOS » mais **stabilité du signe**
entre les trois fenêtres. Un signal qui change de signe est un artefact, quelle
que soit sa p-value.

---

## 6. Baseline sur la fenêtre observable

Un événement ETF n'existe que depuis 2024. Le comparer à une baseline
2017–2026 mesurerait l'écart entre deux époques de marché, pas l'effet de
l'événement.

La baseline est donc restreinte à la fenêtre où l'événement est **observable**,
déduite des données requises et non du masque (les détecteurs remplissent les
jours manquants par `False`, ce qui effacerait la trace).

Effet concret : baseline BTC à 7 jours = **+1.07 %** sur 9 ans, mais **+0.64 %**
sur la fenêtre ETF.

---

## 7. Taille d'échantillon

Aucune significativité n'est revendiquée sous **30 observations**. En dessous,
le résultat est marqué `reliable_sample: false` et accompagné d'une note.

Chaque résultat expose `n`. Un taux de réussite de 62 % sur 9 observations est
du bruit, et l'interface le dit.

---

## 8. Chemin, pas seulement destination

Les études d'événements rapportent **MFE** (excursion favorable maximale) et
**MAE** (excursion adverse maximale) en plus du rendement final. Un +2 % qui est
d'abord passé par −8 % n'est pas la même chose qu'un +2 % linéaire.

---

## 9. Reconstruction de scores : limite assumée

La calibration rejoue la **logique actuelle** sur les bougies historiques. Cela
mesure si la logique a une valeur prédictive — **pas** ce que le système aurait
dit à l'époque.

Les résultats sont explicitement étiquetés `source: reconstructed`. La
calibration sur rapports réels (`source: live_reports`) la remplacera à mesure
que les rapports s'accumulent.

---

## 10. Aucun poids modifié automatiquement

La couche de calibration **mesure**. Elle ne réécrit jamais `config/scoring.yaml`.
Un test le vérifie en inspectant le code source du module.

Changer une pondération reste une décision humaine, et elle ne doit pas être
prise sur une poignée d'observations.

---

## Ce que la méthodologie ne peut pas corriger

- **Une seule histoire.** Il n'existe qu'un historique du Bitcoin. Un résultat
  out-of-sample sur 130 jours reste fragile.
- **Régimes changeants.** 2017–2021 et 2024–2026 sont des marchés différents ;
  un signal stable sur l'un peut disparaître sur l'autre.
- **Biais du survivant sur les sources.** Farside publie les ETF qui existent
  aujourd'hui.
- **Corrélation ≠ causalité.** Un Spearman de 0.14 explique environ 2 % de la
  variance. C'est très peu, et l'affichage le rappelle.
