# Limites des données — à lire avant d'interpréter un backtest

Ce document liste les limites structurelles qui affectent la validité des
études. Elles ne sont pas des bugs : ce sont des propriétés des sources. Les
connaître évite de prendre un artefact pour une découverte.

---

## 1. Révisions macroéconomiques

**Le problème.** Le CPI, le PCE et les chiffres d'emploi sont **révisés** après
leur première publication. Une série historique téléchargée aujourd'hui contient
les valeurs **révisées**, pas celles connues au moment où le marché a réagi.

Trois dates distinctes existent en réalité :

| Date | Signification |
|---|---|
| `observation_date` | la période mesurée (ex. « CPI d'août ») |
| `release_date` | la première publication |
| `revision_date` | chaque correction ultérieure |

**Ce que le projet stocke.** La table `macro_series` ne conserve que
`timestamp` (la date d'observation) et `source`. **Ni FRED ni Yahoo, tels
qu'utilisés ici, ne fournissent la valeur telle que publiée à l'origine.**

FRED expose bien des séries « vintage » via son API ALFRED, mais elles ne sont
pas intégrées dans ce projet.

**Conséquence à assumer.** Tout backtest utilisant CPI, PCE ou NFP souffre d'un
biais de révision : le système « connaîtrait » une valeur que personne n'avait
le jour J. L'effet est faible pour les indices boursiers et le DXY (non révisés)
mais **réel pour l'inflation et l'emploi**.

**Ce qui a été fait.** Les études actuelles n'utilisent aucune série macro
révisée comme signal prédictif — elles reposent sur les prix, le funding, les
flux ETF et les indicateurs techniques, tous non révisés. La limite est
documentée ici plutôt que contournée par une approximation.

**Correctif possible (LOT 4).** Basculer sur ALFRED pour les séries révisées, en
stockant `release_date` en plus de `observation_date`.

---

## 2. Open interest : 30 jours

Binance publie environ **30 jours** d'historique d'open interest via
`openInterestHist`. Ce n'est pas une limite de pagination : l'API ne sert
simplement pas au-delà.

**Conséquence.** L'analyse des interactions prix × OI × funding repose sur ~30
observations. C'est **trop peu pour conclure**, et le moteur retourne
explicitement `INSUFFICIENT_DATA` plutôt qu'un résultat fragile.

Un feature `oi_change_7d` a produit un IC de −0.78 sur **17 observations** lors
d'une première exécution — un artefact spectaculaire qui aurait dominé le
classement sans le garde-fou ajouté depuis.

**Contournement légitime.** `data/imports/open_interest/` accepte un CSV d'un
fournisseur auquel tu as légitimement accès. Voir `docs/data-imports.md`.

---

## 3. Flux ETF : 2024 seulement

Les ETF spot BTC existent depuis janvier 2024, les ETF ETH depuis juillet 2024.
Toute étude ETF porte donc sur **moins de trois ans** et une seule phase de
marché.

**Conséquence.** Une relation stable sur cette fenêtre n'a jamais été testée en
bear market prolongé. La validation train/validation/OOS découpe une période
déjà courte en fragments encore plus courts.

---

## 4. Une seule histoire

Il n'existe qu'un historique du Bitcoin. Les fenêtres out-of-sample sont des
morceaux de cette même histoire, pas des échantillons indépendants.

**Conséquence.** Un résultat « validé hors échantillon » sur 130 jours reste
fragile. C'est pourquoi le score de stabilité pèse la **constance du signe entre
fenêtres** plus lourdement que la taille de l'effet.

---

## 5. Corrélation globale vs corrélation intra-période

**La limite la plus importante trouvée dans ce projet.**

Le score technique affichait un IC global de **+0.070** (p<0.0001, n=3257) — un
résultat apparemment solide. Décomposé par année :

```
2020 +0.129   2021 +0.015   2022 -0.173   2023 -0.097
2024 -0.013   2025 -0.034   2026 +0.074
```

Sur des fenêtres glissantes de 365 jours : **0 fenêtre sur 3 positive**.

**Explication.** Le score était plus élevé pendant les périodes globalement
haussières. La corrélation mesure donc une différence de **niveau entre
régimes**, pas une capacité à distinguer les bons jours des mauvais jours à
l'intérieur d'une période. Seule la seconde est exploitable.

**Ce qui a été fait.** `research/stats.py::decompose_ic` sépare les deux
composantes, et le moteur d'audit rétrograde automatiquement en
`NO_MEASURABLE_VALUE` tout score dont l'IC global n'est pas reproduit en
intra-période.

Cette correction invalide une conclusion du LOT 2.

---

## 6. Scores reconstruits ≠ scores enregistrés

La calibration rejoue la **logique actuelle** sur les bougies historiques. Elle
mesure si la logique porte de l'information — **pas** ce que le système aurait
affiché à l'époque.

Les résultats portent `source: reconstructed`. La calibration sur rapports réels
(`source: live_reports`) la remplacera à mesure que les prédictions immuables
s'accumulent.

---

## 7. Biais du survivant sur les sources

Farside publie les ETF **qui existent aujourd'hui**. Un fonds fermé n'y figure
pas. Binance liste les paires **encore cotées**. Ces absences sont invisibles
dans les données et impossibles à corriger sans une source historique complète.

---

## 8. Comparaisons multiples

Les grilles de test sont larges : 63 hypothèses pour l'étude ETF, 170 pour la
feature importance. À p<0.05, on attend respectivement ~3 et ~8 « découvertes »
par pur hasard.

Toutes les études appliquent une correction de Benjamini-Hochberg, et le
compteur non corrigé reste affiché pour montrer l'écart.
