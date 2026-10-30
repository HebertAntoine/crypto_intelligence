# Catalogue des quinze signaux macro et inter-marchés

Mise à jour : 2026-10-30

## Deux taxonomies distinctes

S01–S15 est un radar explicatif macro/inter-marchés. Il ne remplace pas les cinq familles future-first utilisées par la décision. Le radar possède ses routes et son affichage; son classement n'est pas encore injecté comme objet dans `ChiefMarketAnalyst`.

## Contrat sérialisé

Une lecture expose actuellement :

- identité : `signal_id`, `key`, `emoji`, `name`, `category`, `geographic_scope`, `associated_assets`, `channel`;
- diagnostic : `state`, `direction`, `attention`, alias `attention_level`, `importance`, `relevance_score`, `importance_reasons`, `summary`, `explanation`, `watching`;
- valeurs : `values`, `primary_metric`, `current_value`, `previous_value`, `delta`, `reference_window`, `historical_percentile`, `historical_series`;
- temps : `last_release`/`last_observation_at`, `last_publication_at`, `next_release`/`next_event_at`, `next_release_label`, `release_frequency`;
- preuve et qualité : `source`, `source_url`, `data_quality`, `invalidation_conditions`, `available`, `unavailable_reason`.

`AttentionLevel` et `EventDirection` sont indépendants. Une décision imminente peut être `CRITICAL` et `UNKNOWN`. Des entrées contradictoires peuvent donner `MIXED`. Une source absente donne `available=false` et `SOURCE_UNAVAILABLE`, jamais une neutralité fabriquée.

`current_value`, `previous_value` et `delta` correspondent à la `primary_metric` choisie, pas forcément à tout le composite. `historical_series` est limité aux 120 derniers points. La date de publication n'est jamais déduite de la date d'observation.

## Catalogue exact

| ID | Clé | Famille demandée | Entrées actuellement lues | Fenêtre/lecture | Base | Groupe d'indépendance |
|---|---|---|---|---|---:|---|
| S01 | `fed` | Politique Fed | borne cible, EFFR, FOMC, stress crédit contextuel | taux sur 3 mois; échéance | 55 | `US_MONETARY` |
| S02 | `inflation` | Inflation US | Core CPI, Core PCE | annuel et tendance sur 6 mois; pas de surprise sans consensus | 45 | `US_MONETARY` |
| S03 | `employment` | Emploi US | chômage, payrolls, claims | chômage sur 6 mois et variation mensuelle | 45 | `US_GROWTH` |
| S04 | `yields` | Taux obligataires | réel 10 ans, 2 ans, 10 ans | variation sur 30 jours | 45 | `US_MONETARY` |
| S05 | `oil` | Pétrole | Brent; WTI explicitement en repli | variation et rang empirique sur 30 jours | 25 | `ENERGY` |
| S06 | `credit` | Risque de crédit | spreads HY/IG | niveau, variation 30 jours, percentile | 40 | `FINANCIAL_STRESS` |
| S07 | `financial_stress` | Stress financier | NFCI, STLFSI4 | percentiles; `MIXED` en cas de désaccord | 40 | `FINANCIAL_STRESS` |
| S08 | `dollar` | Dollar et changes | DXY autorisé ou dollar large; FX en contexte | variation 30 jours, percentile | 35 | `FX` |
| S09 | `liquidity` | Liquidité US | bilan Fed, TGA, RRP | variation nette bilan − TGA − RRP sur 60 jours | 35 | `LIQUIDITY` |
| S10 | `us_index_divergence` | Divergence indices US | S&P 500, Nasdaq Composite, Dow, Russell 2000 | rendements 30 jours; au moins deux indices | 45 | `EQUITY_RISK` |
| S11 | `international_contagion` | Contagion internationale | S&P 500, Nikkei 225, Euro Stoxx 50 | concordance régionale sur 30 jours | 45 | `EQUITY_RISK` |
| S12 | `volatility` | Volatilité | VIX | percentile et variation sur 7 jours | 40 | `FINANCIAL_STRESS` |
| S13 | `earnings_ai` | Résultats et IA | événement SEC/émetteur daté | direction inconnue avant chiffres normalisés | 45 | `EARNINGS` |
| S14 | `ecb` | Politique BCE | taux de dépôt et calendrier | variation sur 180 jours | 55 | `EU_MONETARY` |
| S15 | `boj` | Politique BoJ | call rate et calendrier | variation sur 180 jours | 55 | `JP_MONETARY` |

Les bases sont des poids d'ingénierie, pas des probabilités et pas une validation statistique d'un rendement futur.

## Score d'importance exact

Le score est additif puis borné entre 0 et 100. Il ne regarde pas le signe directionnel, sauf un petit bonus lorsque le signal est explicitement contradictoire.

| Composante | Points actuels |
|---|---:|
| Base banque centrale | +55 |
| Base macro ou taux | +45 |
| Base risque financier | +40 |
| Base liquidité ou FX | +35 |
| Base énergie | +25 |
| Prochain événement ≤ 6 h / 24 h / 3 j / 7 j | +40 / +30 / +18 / +8 |
| Publication récente selon la famille | +12 |
| Publication de plus de 45 jours | −10 |
| Observation sans date de publication vérifiée | −8 |
| Qualité `STALE` / `CONFLICTING` / `REVISED` | −15 / −25 / −3 |
| État ou direction modifié depuis le cycle précédent | +8 |
| Mouvement au moins au 95e / 85e percentile empirique | +25 / +15 |
| Direction `MIXED` | +5 |

Fenêtres de publication récente pertinentes : banque centrale 48 h, macro 30 h, taux/FX 12 h, risque financier 72 h, liquidité 36 h et énergie 24 h.

Seuils d'attention : `CRITICAL` à partir de 85, `HIGH` à partir de 70, `MODERATE` à partir de 50, `LOW` à partir de 30, sinon `NONE`.

## Qualité et fraîcheur

La qualité démarre à `UNVERIFIED`. Elle devient :

- `CONFLICTING` si observation/publication est future ou si des flags indiquent un conflit;
- `REVISED` si le numéro de révision est positif;
- `UNVERIFIED` en l'absence de publication explicite;
- `STALE` si la publication excède l'âge permis;
- `VALID` sinon.

Âges maximaux codés : quotidien 5 jours, hebdomadaire 14, mensuel 62, trimestriel 140, calendrier 240. Les libellés combinés `WEEKLY_MONTHLY` et `DAILY_WEEKLY` retombent actuellement sur le défaut de 45 jours : c'est une limite de calibration à corriger si des SLA plus fins sont requis.

## Sélection des cinq cartes

Les quinze lectures sont triées par score décroissant. Un premier passage prend au plus une lecture de chaque groupe d'indépendance; un second complète jusqu'à cinq si moins de cinq groupes sont disponibles. Ainsi, crédit, NFCI/STLFSI4 et VIX ne monopolisent pas automatiquement trois cartes comme trois causes distinctes.

Le catalogue complet reste accessible. Les événements réglementaires, géopolitiques, ETF et crypto-native conservent leurs modules; ils peuvent affecter l'analyse générale, mais ne prennent pas l'identité d'un signal S01–S15.

## Disponibilité réelle

- S01–S09, S14 et S15 sont calculables si les sources officielles correspondantes ont été collectées et restent admissibles; tout contenu FRED exige l'autorisation documentée configurée.
- S10–S12 dépendent de données d'indices autorisées; Twelve Data est désactivé sans clé et confirmation de droits, et les séries FRED tierces exigent les deux autorisations FRED applicables.
- S13 peut signaler une publication datée, mais ne mesure pas encore revenus, marges, cash-flow et CAPEX dans un panel directionnel.
- Une famille indisponible reste dans le tableau des quinze avec une raison; elle ne peut pas entrer dans le top cinq.
