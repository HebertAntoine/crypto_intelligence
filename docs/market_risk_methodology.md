# Méthode de risque de marché

Mise à jour : 2026-10-30

## Systèmes réutilisés

Le projet ajoute un contrat de diagnostic global sans créer un second score directionnel. Il conserve :

- les cinq familles future-first : macro/liquidité, catalyseurs/réglementation, flux institutionnels/baleines, positionnement/dérivés, technique/volatilité;
- la hiérarchie de décision et ses gates;
- les horizons future-first `24h`, `7d` et `30d`;
- les convictions historiques `short`, `medium`, `long`;
- le risque événementiel, distinct de la direction attendue;
- le radar S01–S15 comme explication macro, sans le faire voter une seconde fois.

Une famille absente ne vaut pas zéro : elle devient `UNAVAILABLE`, réduit la couverture et peut conduire à `INDETERMINATE`. Une famille simplement marquée disponible n'est pas automatiquement utilisable : le diagnostic exige aussi une amplitude, au moins une provenance et une fraîcheur différente de `STALE`/`UNAVAILABLE`.

## Dimensions couvertes

| Dimension demandée | Couverture actuelle |
|---|---|
| Politique monétaire et inflation | famille macro/liquidité, calendrier, S01–S04/S14/S15 |
| Croissance et emploi | S03, événements et analyse macro |
| Crédit et liquidité | S06, S07, S09 |
| Actions et volatilité | S10–S12 et famille technique/volatilité |
| Géopolitique et réglementation | `FutureEvent` avec statut, source, importance et expiration |
| Positionnement crypto et levier | funding, open interest, ratios, liquidations et DVOL selon disponibilité |

S01–S15 et les cinq familles partagent certaines observations. Leur score ne doit donc pas être additionné comme s'il s'agissait de preuves indépendantes.

## Horizons globalement exposés

`GET /api/future/{symbol}/global-risk` renvoie exactement trois fenêtres disjointes :

| Contrat | Borne temporelle | Usage |
|---|---:|---|
| `1-7d` | `0 < échéance ≤ 7 jours` | risque court terme; un choc actif non planifié n'appartient qu'à cette fenêtre |
| `8-30d` | `7 jours < échéance ≤ 30 jours` | risque moyen terme |
| `31-90d` | `30 jours < échéance ≤ 90 jours` | événements plus lointains sans recycler la lecture 30 jours |

Les événements doivent provenir d'une source autorisée et rester `LIVE` ou `FRESH`. Une échéance n'entre que dans une fenêtre. L'API reconstruit les cinq familles pour 1–7 et 8–30 jours. Elle ne possède pas de projection validée des familles au-delà de 30 jours : elle transmet donc volontairement `None` à la fenêtre longue. Les événements 31–90 jours restent visibles, mais le niveau est `INDETERMINATE`; `30d` n'est jamais renommé `90d`.

## Risque événementiel

Pour chaque horizon, un événement dans la fenêtre reçoit :

```text
severity = 0,50 × importance + 0,35 × mouvement attendu + 0,15 × incertitude
contribution = proximité relative à l'horizon × severity
materiality = 1 - Π(1 - contribution)
```

Les barèmes internes vont de 0,20 à 1,00. Dans le moteur événementiel, `LOW`, `MODERATE`, `HIGH` et `EXTREME` qualifient la quantité de risque, pas une probabilité de rendement. Le contrat global traduit `EXTREME` en `CRITICAL` et ajoute `INDETERMINATE`. En l'absence de distribution de marché autorisée, l'incertitude vaut 1 : elle n'est pas remplacée par une probabilité inventée.

Limite : cette agrégation borne la somme, mais ne déduplique pas encore causalement plusieurs événements représentant le même choc. Le contrôle d'indépendance du top cinq macro ne résout pas ce problème dans le moteur d'événements.

## Décision et gates

La décision suit un ordre conservateur :

1. qualité et couverture des données;
2. risques systémiques et événementiels;
3. macro et liquidité;
4. flux et positionnement;
5. confirmation technique.

Un risque élevé ne prédit pas automatiquement une baisse. Un gate peut imposer l'attente lorsque l'incertitude rend une décision non robuste. Les seuils sont des paramètres d'ingénierie à valider hors échantillon.

## Contradictions et claims externes

Les preuves opposées sont conservées par le moteur de contradictions et peuvent plafonner la conviction. Une affirmation externe `CONTRADICTED`, `AMBIGUOUS`, `UNVERIFIABLE`, `OUTDATED`, `OPINION` ou `FORECAST` n'est pas convertie en observation financière par le fact-check.

Cette dernière garantie s'applique au endpoint de vérification et au chemin Lexa. Tous les RSS/articles du pipeline général ne passent pas encore par ce fact-check; la documentation ne prétend donc pas un filtrage universel.

## Contrat de sortie et couverture

Chaque `GlobalRiskDiagnosis` porte `risk_level`, `horizon`, `assessment_time`, `data_coverage`, `main_drivers`, `counter_signals`, `change_since_previous`, `evidence_ids` et `invalidation_conditions`. `data_coverage` distingue `available_families` de `usable_families`, expose leurs comptes, nomme les familles absentes, compte les événements autorisés et déclare ses limites. Il faut au moins trois des cinq familles utilisables pour publier un niveau déterminé; sinon le moteur échoue fermé avec `INDETERMINATE`.

Les facteurs événementiels indiquent les actifs affectés lorsqu'ils sont connus. React et Flutter/iPhone affichent les trois cartes, leur niveau, couverture, facteurs et limites; ils ne transforment pas ces niveaux en probabilités.

Le moteur sait comparer un niveau précédent fourni. La route courante ne lui transmet pas encore un historique de niveaux; `change_since_previous` y reste donc `NOT_AVAILABLE` plutôt que d'inventer une évolution.

Aucun niveau de risque n'est converti en probabilité. Une probabilité future serait admissible seulement avec cible définie, jeu hors échantillon, mesure de calibration, version du modèle et timestamp. Aucun modèle de ce type n'est branché aux trois scénarios du rapport.
