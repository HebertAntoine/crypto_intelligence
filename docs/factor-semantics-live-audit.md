# Audit sémantique des facteurs — direction, impact, tendance, confiance

**Date** : 13/09/2026 · **Périmètre** : sémantique affichée, design inchangé
**Tests** : backend 1417 passés / 15 ignorés (+25) · Flutter 333 passés (+4)
**Seuils** : aucun seuil de décision n'a été modifié.

---

## 1. Incohérences trouvées et causes exactes

### A. Une direction fabriquée à partir d'un label de régime

**Symptôme** : ETH affichait `technical = BULLISH` avec une **confiance de 0,0**
et un résumé disant « haussière sur 0 unité(s), baissière sur 0 ».

**Cause** ([future_context.py:441](../backend/crypto_intel/engines/future_context.py#L441)) :

```python
technical_score = (len(bullish) - len(bearish)) * 25 if bullish or bearish else None
if technical_score is None:
    regime_label = _value(getattr(regime, "regime", None), "UNDETERMINED")
    technical_score = 40 if "BULL" in regime_label else -40 if "BEAR" in regime_label else None
```

Quand **aucune** échelle de temps ne donne de direction, le moteur retombe sur
l'étiquette de régime et produit ±40, donc une direction franche — tandis que la
confiance, elle, reste calculée sur le nombre d'unités et vaut 0.

**Correction** : dans la couche normalisée, zéro échelle exploitable ⇒
`direction = UNKNOWN`, `impact = LOW`, `confidence = 0`. Le repli sur le régime
ne produit plus de direction.

### B. L'impact technique dérivé du seul décompte d'unités

**Symptôme** : « Tendance court terme porteuse · IMPACT ÉLEVÉ » alors qu'une
seule échelle de temps était haussière.

**Cause** : l'impact reprenait `expected_movement`, lui-même issu du régime de
volatilité, sans lien avec la convergence des preuves.

**Correction — barème documenté** :

| preuve | impact |
|---|---|
| échelles en conflit, ou direction neutre | LOW |
| une seule confirmation | **MODERATE** |
| 1 à 2 confirmations indépendantes | HIGH |
| 3 confirmations ou plus | VERY_HIGH |

Une confirmation indépendante = une échelle concordante **au-delà de la
première**, ou une confirmation qualitative (structure confirmée, volume
confirmant, cassure valide). Le nombre d'unités n'est jamais utilisé seul.

### C. Les flux ETF réduits à une seule direction

**Symptôme** : « Entrées nettes sur les ETF · POSITIF » avec « cumul 5 séances
−288,09 M$ ».

**Cause** : une seule propriété était publiée. Le régime (20 séances) donnait la
direction, la fenêtre courte n'était nulle part dans la sémantique.

**Correction** : `direction` et `trend` sont désormais deux lectures distinctes.

| cas | direction | tendance |
|---|---|---|
| 20 j positif, 5 j négatif | POSITIVE | **DETERIORATING** |
| 20 j négatif, 5 j négatif | NEGATIVE | STABLE |
| 20 j positif, 5 j positif | POSITIVE | STABLE |
| 20 j négatif, 5 j positif | NEGATIVE | **IMPROVING** |

Un régime contredit par sa propre fenêtre récente est plafonné à
`impact = MODERATE` : ce n'est plus un signal fort.

### D. Le positionnement lu sur l'open interest seul — **non confirmé**

L'audit du §7 devait vérifier que l'open interest n'était pas lu seul. Il ne
l'était pas : [market_pressure.py:690](../backend/crypto_intel/engines/market_pressure.py#L690)
classe déjà conjointement prix et OI en `NEW_LONGS` / `NEW_SHORTS` /
`SHORT_COVERING` / `LONG_LIQUIDATION`.

**Un écart subsiste** : `SHORT_COVERING` reçoit un score de **+25**, donc
`BULLISH`. Le §7 demande « pas bearish automatiquement », pas « bullish ». La
couche normalisée le classe **NEUTRAL** : des vendeurs sortent, des acheteurs
n'entrent pas. Le score interne n'a pas été touché — seule la sémantique publiée
l'est. Effet visible : ETH passe de `BEARISH` à `NEUTRAL` sur les trois horizons.

### E. UNKNOWN confondu avec NEUTRAL

`DirectionalBias` ne possède pas de valeur UNKNOWN : tout ce qui n'est pas
mesurable retombait sur `NEUTRAL`. Un FOMC non publié et un funding à son niveau
normal recevaient donc la même étiquette.

**Correction** : `FactorDirection` sépare les deux. NEUTRAL est une mesure —
la donnée a été lue et ne montre pas de biais. UNKNOWN est un aveu — l'issue n'a
pas eu lieu, ou l'instrument ne parle pas de direction.

### F. La compression de Bollinger pouvait porter une direction

**Correction** : `direction = UNKNOWN`, `impact_on_direction = "NONE"`,
`impact = HIGH` sur l'ampleur. L'UI affiche « DIRECTION INCERTAINE » et ne peut
plus dériver un sens de cette lecture.

---

## 2. Anciens statuts → nouveaux statuts

| actif / horizon | facteur | avant | après | justification |
|---|---|---|---|---|
| ETH 24h/7j/30j | technique | `BULLISH` conf 0,0 | **`UNKNOWN`**, LOW | 0 échelle exploitable; le repli sur le régime est supprimé |
| ETH 24h/7j/30j | positionnement | `BEARISH` | **`NEUTRAL`** | short covering: des vendeurs sortent, pas d'acheteurs qui entrent |
| BTC 7j | flux | `POSITIF` | **`POSITIVE` + `DETERIORATING`**, MODERATE | +3 310 M$ sur 20 séances, −288 M$ sur 5 |
| BTC 7j | technique | ÉLEVÉ | **MODÉRÉ** | une seule échelle concordante, aucune confirmation indépendante |
| BTC/SOL 7j/30j | volatilité | direction publiée | **`UNKNOWN`**, `impact_on_direction=NONE` | une compression ne donne jamais de sens |
| toutes | FOMC | — | `UNKNOWN` + `VERY_HIGH` | impact et direction sont indépendants |

---

## 3. Audit live des 9 combinaisons

#### BTC — 24h · décision **SELL** (confiance 0.61)

| facteur | direction | tendance | impact | confiance | fraîcheur | justification |
|---|---|---|---|---|---|---|
| positioning | **NEGATIVE** | DETERIORATING | MODERATE | 0.8 | RECENT | Le prix recule pendant que les positions à levier se ferment: des acheteur |
| technical | **NEGATIVE** | STABLE | MODERATE | 0.25 | LIVE | 0 échelle(s) haussière(s) contre 1 |
| volatility | **UNKNOWN** | UNKNOWN | LOW | 0.3 | UNAVAILABLE | Pas de compression marquée. |

#### BTC — 7d · décision **WAIT** (confiance 0.458)

| facteur | direction | tendance | impact | confiance | fraîcheur | justification |
|---|---|---|---|---|---|---|
| flows | **POSITIVE** | DETERIORATING | MODERATE | 0.9 | TODAY | 20 séances: +3 310.1 M$; 5 dernières séances: -288.1 M$ |
| positioning | **NEGATIVE** | DETERIORATING | MODERATE | 0.8 | RECENT | Le prix recule pendant que les positions à levier se ferment: des acheteur |
| technical | **POSITIVE** | STABLE | MODERATE | 0.25 | LIVE | 1 échelle(s) haussière(s) contre 0 |
| volatility | **UNKNOWN** | UNKNOWN | HIGH | 0.6 | UNAVAILABLE | Les bandes de Bollinger sont resserrées: un mouvement important est possib |

#### BTC — 30d · décision **WAIT** (confiance 0.495)

| facteur | direction | tendance | impact | confiance | fraîcheur | justification |
|---|---|---|---|---|---|---|
| flows | **POSITIVE** | DETERIORATING | MODERATE | 0.9 | TODAY | 20 séances: +3 310.1 M$; 5 dernières séances: -288.1 M$ |
| positioning | **NEGATIVE** | DETERIORATING | MODERATE | 0.8 | RECENT | Le prix recule pendant que les positions à levier se ferment: des acheteur |
| technical | **NEUTRAL** | UNKNOWN | LOW | 0.5 | LIVE | 1 échelle(s) haussière(s) contre 1 |
| volatility | **UNKNOWN** | UNKNOWN | HIGH | 0.6 | UNAVAILABLE | Les bandes de Bollinger sont resserrées: un mouvement important est possib |

#### ETH — 24h · décision **SELL** (confiance 0.56)

| facteur | direction | tendance | impact | confiance | fraîcheur | justification |
|---|---|---|---|---|---|---|
| positioning | **NEUTRAL** | STABLE | MODERATE | 0.8 | RECENT | Aucun changement de positionnement marqué. |
| technical | **UNKNOWN** | UNKNOWN | LOW | 0.0 | LIVE | Aucune échelle de temps ne donne de direction exploitable. |
| volatility | **UNKNOWN** | UNKNOWN | LOW | 0.3 | UNAVAILABLE | Pas de compression marquée. |

#### ETH — 7d · décision **WAIT** (confiance 0.42)

| facteur | direction | tendance | impact | confiance | fraîcheur | justification |
|---|---|---|---|---|---|---|
| flows | **POSITIVE** | STABLE | HIGH | 0.9 | TODAY | 20 séances: +1 920.5 M$; 5 dernières séances: +222.8 M$ |
| positioning | **NEUTRAL** | STABLE | MODERATE | 0.8 | RECENT | Aucun changement de positionnement marqué. |
| technical | **UNKNOWN** | UNKNOWN | LOW | 0.0 | LIVE | Aucune échelle de temps ne donne de direction exploitable. |
| volatility | **UNKNOWN** | UNKNOWN | LOW | 0.3 | UNAVAILABLE | Pas de compression marquée. |

#### ETH — 30d · décision **WAIT** (confiance 0.42)

| facteur | direction | tendance | impact | confiance | fraîcheur | justification |
|---|---|---|---|---|---|---|
| flows | **POSITIVE** | STABLE | HIGH | 0.9 | TODAY | 20 séances: +1 920.5 M$; 5 dernières séances: +222.8 M$ |
| positioning | **NEUTRAL** | STABLE | MODERATE | 0.8 | RECENT | Aucun changement de positionnement marqué. |
| technical | **UNKNOWN** | UNKNOWN | LOW | 0.0 | LIVE | Aucune échelle de temps ne donne de direction exploitable. |
| volatility | **UNKNOWN** | UNKNOWN | HIGH | 0.6 | UNAVAILABLE | Les bandes de Bollinger sont resserrées: un mouvement important est possib |

#### SOL — 24h · décision **SELL** (confiance 0.61)

| facteur | direction | tendance | impact | confiance | fraîcheur | justification |
|---|---|---|---|---|---|---|
| positioning | **NEGATIVE** | DETERIORATING | MODERATE | 0.8 | RECENT | Le prix recule pendant que les positions à levier augmentent: de nouvelles |
| technical | **NEGATIVE** | STABLE | MODERATE | 0.25 | LIVE | 0 échelle(s) haussière(s) contre 1 |
| volatility | **UNKNOWN** | UNKNOWN | LOW | 0.3 | UNAVAILABLE | Pas de compression marquée. |

#### SOL — 7d · décision **WAIT** (confiance 0.42)

| facteur | direction | tendance | impact | confiance | fraîcheur | justification |
|---|---|---|---|---|---|---|
| positioning | **NEGATIVE** | DETERIORATING | MODERATE | 0.8 | RECENT | Le prix recule pendant que les positions à levier augmentent: de nouvelles |
| technical | **UNKNOWN** | UNKNOWN | LOW | 0.0 | LIVE | Aucune échelle de temps ne donne de direction exploitable. |
| volatility | **UNKNOWN** | UNKNOWN | HIGH | 0.6 | UNAVAILABLE | Les bandes de Bollinger sont resserrées: un mouvement important est possib |

#### SOL — 30d · décision **WAIT** (confiance 0.42)

| facteur | direction | tendance | impact | confiance | fraîcheur | justification |
|---|---|---|---|---|---|---|
| positioning | **NEGATIVE** | DETERIORATING | MODERATE | 0.8 | RECENT | Le prix recule pendant que les positions à levier augmentent: de nouvelles |
| technical | **UNKNOWN** | UNKNOWN | LOW | 0.0 | LIVE | Aucune échelle de temps ne donne de direction exploitable. |
| volatility | **UNKNOWN** | UNKNOWN | HIGH | 0.6 | UNAVAILABLE | Les bandes de Bollinger sont resserrées: un mouvement important est possib |
---

## 4. Lecture de l'audit

**`flows` absent pour SOL** : aucune série institutionnelle exploitable pour cet
actif. L'absence est déclarée, aucune valeur n'est inventée.

**`flows` absent sur les horizons 24 h** : la famille retombe sur les
composantes de pression spot, qui ne fournissent pas de régime multi-séances.

**ETH `technical = UNKNOWN` partout** : c'est le correctif A. Avant, la même
donnée produisait `BULLISH`.

**`volatility` en `LOW` sur 24 h et `HIGH` sur 7 j/30 j** : la compression est
mesurée sur l'unité de temps de l'horizon; elle est présente sur les échelles
longues et absente sur la courte.

---

## 5. Fichiers modifiés

| fichier | objet |
|---|---|
| `backend/crypto_intel/engines/factor_semantics.py` | **nouveau** — les quatre lectures séparées |
| `backend/crypto_intel/engines/future_context.py` | publication des facteurs normalisés |
| `backend/crypto_intel/engines/future_decision.py` | `factors` dans le payload; conditions séparées achat/vente |
| `backend/crypto_intel/engines/analysis_context.py` | transmission de l'état de levier |
| `app/lib/api/future_models.dart` | `FutureFactorRead`, `conditionsToBuy/Sell` |
| `app/lib/screens/future_analysis_screen.dart` | direction + tendance + impact; raisons / contre-signaux |
| `tests/unit/test_factor_semantics.py` | **nouveau** — 25 tests |
| `app/test/decision_simplification_test.dart` | 4 tests ajoutés |

---

## 6. Limites assumées

**`directional_bias` des familles est inchangé.** La couche normalisée est
**additive** : elle publie une sémantique correcte à côté des familles, sans
toucher les scores qui alimentent la décision. Conséquence : sur ETH, la décision
continue d'être calculée avec `technical = BULLISH` alors que l'écran affiche
désormais `UNKNOWN`. Faire converger les deux modifierait la décision, ce que la
consigne exclut ici.

**`funding_state` n'est pas transmis** au calcul du positionnement : il n'existe
pas dans le contexte d'analyse. Il n'a pas été fabriqué. L'impact du
positionnement reste donc `MODERATE` là où un funding extrême l'aurait porté à
`HIGH`.

**Les catalyseurs restent `UNKNOWN`** tant que les anticipations de marché sont
indisponibles (licence CME). C'est le §2 appliqué : pas de biais prospectif sans
preuve.

## 7. STOP

Audit, corrections et tests livrés. Aucun seuil de décision modifié, aucune
donnée fabriquée.
