# LOT 2 — Phases 5 à 10 : contrats de décision prospective (mesures)

> **Collision de livrables.** Une autre session a produit
> `docs/future-first-lot2-phase5-10.md` (commit `b1bf99d`, 17:39) en écrasant une
> première version de ce document. Ce fichier porte donc un nom distinct pour ne
> rien détruire. Les deux rapports couvrent la même mission ; celui-ci est mesuré
> **après** la correction du garde-fou et s'en écarte sur un point factuel : le
> document commité décrit encore « BTC passe de SELL 24 h à BUY 7 j », ce qui
> n'est plus le comportement du code.

**Date d'exécution** : 13/09/2026, mesures à 17:29 (UTC+2)
**Périmètre** : phases 5A, 5B, 6, 7, 8, 9, 10A, 10B, 10C + quatre contrats
**État du moteur de production** : inchangé. Aucun des quatre contrats n'est
branché sur `BUY/WAIT/SELL`, conformément au §12.
**Tests** : 1372 passés, 15 ignorés (1317 avant ce lot, soit +55).

---

## 0. Écart entre la consigne et l'architecture trouvée

La consigne demandait d'« exécuter » neuf phases. Sept des neuf moteurs
**existaient déjà** et étaient branchés. Conformément à la règle « ne pas refaire
le projet de zéro », ils ont été **validés**, pas réécrits.

| Phase | Moteur | État trouvé | Action menée |
|---|---|---|---|
| 5A | `EventRiskGate` / `EventRiskEngine` | présents, gate jamais déclenché | défaut corrigé, 4 tests |
| 5B | `MarketExpectationEngine` | présent, 9 tests, **ne livre rien** | cause : licence CME |
| 6 | `EventSurpriseEngine` | présent, **0 importeur, 0 test** — code mort | 7 tests |
| 7 | `WhaleAnalyzer` / `WhaleObservation` | présent (594 l.), 0 test | 7 tests |
| 8 | `InstitutionalFlowEngine` | présent, 7 tests | incohérence d'affichage corrigée |
| 9 | `ExpectedVolatilityEngine` | présent, 0 test | 3 tests |
| 10A | `MarketCausalGraph` | présent, branché, 0 test | 3 tests |
| 10B | `SignalConvergenceEngine` | présent, branché, 0 test | 4 tests |
| 10C | `ContradictionResolver` | présent, branché, 0 test | 5 tests |
| — | les 4 contrats | **absents** | créés, 26 tests |

Six moteurs tournaient en production sans un seul test. C'est le principal
risque refermé par ce lot.

---

## 1. Le défaut central de la phase 5A

`EventRiskGate` portait une fenêtre **codée en dur à 48 heures**, indépendante de
l'horizon. Le FOMC du 16/09/2026 se situait à 74 h : hors fenêtre, donc
invisible. Pendant ce temps la décision affirmait couvrir 7 jours. Un ACHETER
sur 7 jours enjambait un événement critique non résolu sans que rien ne le
signale.

**Correction** : la fenêtre suit l'horizon, plancher de 48 h conservé pour tout
appel sans horizon — aucune régression sur les 19 tests préexistants.

| Horizon | Avant | Après | Garde-fou |
|---|---|---|---|
| 24 h | VENDRE | VENDRE *(inchangé)* | NOT_TRIGGERED |
| 7 j | ACHETER | **ATTENDRE** | TRIGGERED — FOMC dans 3,1 j |
| 30 j | ACHETER | **ATTENDRE** | TRIGGERED — FOMC + Personal Income |

Le biais reste `BULLISH` sur 7 j : le moteur ne prétend pas que le marché va
baisser, il refuse de se prononcer par-dessus un événement qu'il ne sait pas
valoriser. C'est la logique ATTENDRE du §10.

Deux corrections d'affichage ont accompagné : la phrase des flux mélangeait un
régime mesuré sur 20 séances et un cumul sur 5 séances (« inflow … −288 M$ »,
lu comme une contradiction alors que les deux chiffres étaient justes), et la
raison n°1 affichée était une famille **neutre**, donc non votante.

---

## 2. Les quatre contrats

`backend/crypto_intel/engines/decision_contracts.py`. Purs : aucune E/S, aucune
horloge implicite, aucune probabilité inventée.

### DecisionConfidence

Répond à « avons-nous de bonnes raisons de croire que c'est la meilleure
décision maintenant ? », **pas** à « quelle probabilité que ça monte ».

Échelle de déductions auditables plutôt que moyenne pondérée, pour que chaque
mouvement soit nommable dans l'UI et rejouable en test :

- base = nombre de confirmations **indépendantes** (signaux corrélés comptés une fois) ;
- −2 contradictions fortes, −1 contradictions partielles ;
- −1 entrées périmées ou absentes ;
- −1 incertitude événementielle non valorisée ;
- −2 décision fragile, −1 décision modérée.

`numeric_score` reste `None` et `is_calibrated` reste `False` tant qu'aucune
étude de calibration n'existe. Le champ `not_a_probability` porte la distinction
du §3 jusque dans le contrat API.

> La production affiche aujourd'hui « Confiance 56 % ». Ce nombre est une
> moyenne de confiances de familles pondérée par la couverture. Il n'est pas
> calibré et ne doit pas être affiché en pourcentage.

### DecisionStability et RiskAsymmetry — et pourquoi ils renvoient UNKNOWN

Les deux contrats sont implémentés et testés mais **refusent de publier un
niveau sur les données actuelles**. C'est un constat d'architecture, pas une
limite des contrats.

`FutureScenarioEngine` ne *dérive* pas les scénarios, il les *estampille* :

- le `bullish_case` reçoit un biais haussier et le `bearish_case` un biais
  baissier **par construction** ;
- une **unique** valeur `expected_movement` est calculée puis appliquée aux deux ;
- le `tail_risk_case` est toujours `NEUTRAL` / `EXTREME`.

Conséquences mécaniques, vérifiées sur les 9 décisions :

- tout SELL serait renversé par le scénario haussier, tout BUY par le baissier
  → **FRAGILE constant** ;
- l'amplitude haussière ne peut jamais dépasser la baissière
  → **jamais FAVORABLE**, au mieux BALANCED ;
- sous garde-fou actif, tous les scénarios retombent sur ATTENDRE
  → **ROBUST constant**.

Une métrique vraie par construction n'est pas une mesure. Les deux moteurs
renvoient `UNKNOWN` avec un `unknown_reason` explicite, verrouillé par test.

### DecisionImpactAssessment

Assemble direction, ampleur, horizon, asymétrie, moteur principal, moteurs
secondaires, cas haussier / baissier / extrême, conditions d'invalidation.

`expected_range` reste `UNAVAILABLE` sauf si l'appelant fournit un intervalle
**avec sa base documentée** (`basis` : volatilité implicite, réalisée, ATR,
distribution historique). Un intervalle sans base lève une `ValueError`. Aucune
cible de prix n'est jamais synthétisée (§5).

---

## 3. FUTURE DECISION READINESS

Mesuré le 13/09/2026 à 17:29 sur l'API réelle. La décision de production n'a pas
été modifiée pendant cet audit (§13).

| Actif / horizon | Décision | Confiance candidate | Stabilité | Asymétrie | Garde-fou | Risque évén. | Confirm. indép. | Confiance affichée |
|---|---|---|---|---|---|---|---|---|
| BTC 24 h | SELL | **LOW** | UNKNOWN | UNKNOWN | non | LOW | 2 | 56 % |
| BTC 7 j | WAIT | **VERY_LOW** | UNKNOWN | UNKNOWN | oui | HIGH | 3 | 61 % |
| BTC 30 j | WAIT | **VERY_LOW** | UNKNOWN | UNKNOWN | oui | HIGH | 2 | 66 % |
| ETH 24 h | SELL | **LOW** | UNKNOWN | UNKNOWN | non | LOW | 2 | 56 % |
| ETH 7 j | WAIT | **VERY_LOW** | UNKNOWN | UNKNOWN | oui | HIGH | 2 | 56 % |
| ETH 30 j | WAIT | **VERY_LOW** | UNKNOWN | UNKNOWN | oui | HIGH | 2 | 56 % |
| SOL 24 h | SELL | **MEDIUM** | UNKNOWN | UNKNOWN | non | LOW | 3 | 61 % |
| SOL 7 j | WAIT | **VERY_LOW** | UNKNOWN | UNKNOWN | oui | HIGH | 2 | 56 % |
| SOL 30 j | WAIT | **VERY_LOW** | UNKNOWN | UNKNOWN | oui | HIGH | 2 | 56 % |

L'écart est systématique : là où l'app affiche 56 à 66 %, la confiance candidate
est LOW ou VERY_LOW dans 8 cas sur 9.

### Le constat le plus important

**`flows_whales` est la famille dominante dans les 9 décisions sur 9.**

`macro_liquidity` est `NEUTRAL` dans les 9 (donc écartée par `_dominant_family`),
`catalysts_regulation` est `UNAVAILABLE` dans les 9. L'échelle de priorité
descend invariablement jusqu'aux flux ETF, qui décident seuls. Le positionnement
est `BEARISH` dans 9 cas sur 9 et n'est **jamais** consulté.

Autrement dit : toute la direction de l'application repose sur une seule
famille, et cette famille est **rétrospective** — flux ETF publiés en J+1,
régime mesuré sur 20 séances passées.

### Détail par profil

#### Profil A — 24 h (BTC, ETH, SOL) : SELL, confiance LOW à MEDIUM

- **Pourquoi la décision existe** : `flows_whales` baissier, seule famille non
  neutre de priorité 2. Aucun événement critique dans la fenêtre de 24 h.
- **Part du passé** : flux ETF (J+1), open interest, structure technique. **Tout.**
- **Part du futur** : adjudications du Trésor à 13 et 26 semaines, MEDIUM, sans
  effet directionnel. Contribution réelle : nulle.
- **Moteurs contributeurs** : flux, positionnement, technique. **Dominant** : flux.
- **Contradictions** : `ALIGNED_BEARISH` pour les trois actifs — les familles
  disponibles vont dans le même sens.
- **Événement pouvant invalider** : FOMC du 16/09, hors horizon 24 h.
- **Asymétrie** : non calculable (scénarios estampillés).
- **Données manquantes** : `catalysts_regulation`, `market_rate_expectations`,
  `whale_intelligence`.
- **Confiance candidate** : LOW (BTC, ETH), MEDIUM (SOL, 3 confirmations).

#### Profil B — 7 j et 30 j, BTC et ETH : WAIT sous garde-fou, biais haussier

- **Pourquoi la décision existe** : le garde-fou se déclenche sur le FOMC du
  16/09 (CRITICAL, forte amplitude, issue non valorisée), à 3,1 jours.
- **Part du passé** : le biais haussier sous-jacent — flux ETF, +3 310 M$ sur
  20 séances pour BTC.
- **Part du futur** : le FOMC, et pour 30 j le Personal Income and Outlays à
  16,8 jours. Seule contribution prospective réelle, et elle agit comme frein,
  jamais comme direction.
- **Contradictions** : `STRONGLY_MIXED` — flux haussiers contre positionnement
  baissier, sans arbitrage possible faute de valorisation de l'événement.
- **Événement pouvant invalider** : la publication du FOMC elle-même.
- **Confiance candidate** : VERY_LOW. Trois déductions se cumulent
  (contradiction forte, entrées manquantes, incertitude non valorisée).

#### Profil C — 7 j et 30 j, SOL : WAIT sous garde-fou, biais baissier

Identique au profil B, sauf que flux et positionnement sont tous deux baissiers
(`ALIGNED_BEARISH`). ATTENDRE ne vient donc pas d'une contradiction mais
uniquement du garde-fou. C'est le cas décrit au §10 : biais baissier assumé,
mais SELL maintenant offre un mauvais rapport risque/rendement avant un
événement non valorisé.

---

## 4. Question obligatoire (§14)

Pour les six décisions à 7 j et 30 j :

- **Scénario central** : le FOMC sort conforme à ce qui est déjà valorisé, le
  biais de fond (haussier BTC/ETH, baissier SOL) reprend la main.
- **Scénario favorable** : issue plus accommodante que valorisé, flux
  institutionnels amplifiés.
- **Scénario défavorable** : issue plus restrictive que valorisé, dénouement du
  positionnement long encombré.
- **Risque extrême** : cascade de liquidations sur dénouement du levier.
- **Invalidation** : publication du FOMC, retournement durable des flux ETF,
  rétablissement de `catalysts_regulation`.

**Limite à assumer** : ces quatre lignes emploient le mot « valorisé » alors
qu'**aucune valorisation n'est disponible**. Les scénarios sont nommés mais non
quantifiés, et leurs quatre `probability` valent `null` sur les neuf décisions.
Tant que ce point n'est pas levé, le §14 ne peut recevoir qu'une réponse
qualitative.

---

## 5. Le verrou unique : une seule source bloque toute la chaîne prospective

`CMEFedWatchProvider` exige `CME_FEDWATCH_API_KEY` et `CME_FEDWATCH_API_URL`
(licence commerciale). Non configurés, le provider déclare `UNAVAILABLE` — le
comportement correct, la consigne interdisant le contournement des protections.

Conséquences en cascade, toutes vérifiées :

1. `market_expectations` : 9/9 décisions, 100 % `UNAVAILABLE` ;
2. `EventSurpriseEngine` ne peut rien produire — il exige une distribution
   pré-événement et retourne `UNAVAILABLE` sans elle. D'où son statut de code
   mort : il est correct, il n'a simplement jamais eu d'entrée ;
3. les probabilités de scénario restent `null` ;
4. le garde-fou ne peut jamais se rouvrir : `_uncertain()` ne rend `False` que
   si la probabilité dominante dépasse 0,75, ce qui exige une distribution ;
5. la direction événementielle est impossible sans tomber dans la règle
   interdite « hausse = baissier ».

**Piste alternative sous licence propre, à instruire** : Kalshi est un marché
réglementé (CFTC) exposant une API publique de probabilités d'événements macro,
et la NY Fed publie le *Survey of Primary Dealers*. Ni l'un ni l'autre n'a été
implémenté ni téléchargé : ce sont des candidats à auditer au sens de l'étape
« sources », pas des acquis.

---

## 6. Ce que DecisionEngineV2 devra faire de ces éléments

Dans cet ordre, chaque étape conditionnant la suivante.

**V2.1 — Dériver les scénarios au lieu de les estampiller.**
Prérequis absolu : sans cela, `DecisionStability` et `RiskAsymmetry` resteront
`UNKNOWN` par construction. Chaque scénario doit porter sa propre amplitude,
issue de la volatilité implicite, réalisée, de l'ATR ou d'une distribution
historique d'événements — jamais d'une valeur commune recopiée.

**V2.2 — Remplacer l'échelle de priorité par une convergence pondérée.**
Aujourd'hui `_dominant_family` retient **une** famille et ignore les autres : le
positionnement baissier des 9 décisions n'est jamais pesé. V2 doit consommer
`SignalConvergence` (déjà calculé, désormais testé) : le nombre de confirmations
indépendantes doit peser, et deux signaux partageant une cause ne comptent
qu'une fois.

**V2.3 — Faire du niveau de confiance une sortie de premier rang.**
`DecisionConfidence` remplace le flottant `decision_confidence` affiché en
pourcentage. L'UI affiche le niveau et les facteurs, jamais un nombre non
calibré. `numeric_score` n'apparaît que le jour où une calibration existe.

**V2.4 — Faire de l'asymétrie une condition de BUY/SELL.**
Conformément au §8 : un biais légèrement haussier avec une asymétrie défavorable
doit produire ATTENDRE. Impossible tant que V2.1 n'est pas faite.

**V2.5 — Brancher `EventSurpriseEngine` sur l'écart attendu/réalisé.**
La direction événementielle ne vient jamais du type d'événement mais de l'écart
entre le valorisé et le réalisé, via un adaptateur explicite. Les tests
`test_direction_appears_only_through_an_explicit_adapter` et
`test_the_same_adapter_with_opposite_signs_flips_the_reading` verrouillent le
fait que le signe vit dans l'adaptateur, jamais dans le moteur.

**V2.6 — Publier le contrat UI du §15.**
`DecisionImpactAssessment` fournit déjà les champs de la maquette. Il manque le
niveau de confiance textuel (V2.3) et l'asymétrie (V2.4) pour la remplir sans
inventer une seule valeur.

### Ordre de dépendance

```
Licence CME (ou alternative auditée)
        │
        ├──> market_expectations disponibles
        │         ├──> EventSurprise exploitable        (V2.5)
        │         ├──> probabilités de scénario
        │         └──> réouverture du garde-fou 30 j
        │
        └──> V2.1 scénarios dérivés
                  ├──> DecisionStability calculable
                  ├──> RiskAsymmetry calculable          (V2.4)
                  └──> DecisionConfidence discriminante  (V2.3)
```

Tant que la racine n'est pas levée, V2 pourra améliorer la **présentation** et
la **pondération** (V2.2, V2.3), mais pas rendre l'application réellement
prospective : elle continuera de lire le présent et de freiner devant le futur.

---

## 7. STOP

Fin de la phase 10C. Le moteur de décision n'est pas remplacé. Les quatre
contrats sont calculables et testés, non branchés.
