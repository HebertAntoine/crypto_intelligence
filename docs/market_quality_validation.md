# Qualité et validation Market Intelligence

Mise à jour : 2026-10-30

## Stratégie

La validation sépare :

1. tests unitaires déterministes hors réseau;
2. intégration API;
3. lint et contrôles de types;
4. tests, analyse et builds Flutter/React;
5. build conteneur et smoke HTTP;
6. qualification réseau/licence, qui exige les accès réels et les contrats autorisés.

`MOCK_MODE=true` est réservé aux tests. Une capacité sans fixture ne fabrique aucune donnée.

## Invariants couverts par l'intégration

- catalogue exact S01–S15 et top cinq dynamique;
- groupe d'indépendance empêchant le stress corrélé de monopoliser le top cinq;
- observation, publication, disponibilité, ingestion, vintage et provenance propre à chaque version distingués;
- Twelve Data, CoinGecko, tout contenu FRED, ses séries tierces et SEC fermés lorsque leurs clés, droits, attribution ou identité manquent;
- valeurs nulles, non finies, symboles, fuseaux, trous et bougies non closes M15/H1/H4/D1/W1 refusés;
- preuves postérieures à une affirmation exclues;
- Nasdaq ambigu, nom mal transcrit, causalité, prévision, opinion et péremption classifiés;
- variation mensuelle close-to-close et recul depuis sommet distingués;
- niveaux et allocations Lexa non promus en faits;
- garde sémantique simple des nombres et références de preuve LLM obligatoires;
- exactement trois scénarios publics, probabilités narratives interdites et probabilités de domaine soumises à calibration hors échantillon documentée;
- risque global exposé sur trois fenêtres disjointes avec échec fermé si la couverture est insuffisante;
- notifications Lexa et générales dédupliquées transactionnellement et reçus in-app traçables;
- cycle serveur limité à treize étapes ordonnées, avec état durable et reprise;
- Flutter affiche les nouveaux champs sans inventer une date de publication.

## Campagne finale à consolider

Les résultats du 2026-10-28 précédaient les derniers changements de droits FRED/CoinGecko, provenance par vintage, bougies closes, garde LLM, scénarios, risque, reçus généraux et cycle durable. Ils ne constituent donc pas une campagne finale de l'état présent et ne sont pas recopiés comme tels.

| Contrôle | Résultat observé | Portée/limite |
|---|---:|---|
| Backend `pytest -q` | **À RENSEIGNER APRÈS LE RUN FINAL** | Ne pas reprendre le total antérieur. |
| Flutter `flutter test` | **À RENSEIGNER APRÈS LE RUN FINAL** | Suite complète. |
| Flutter `flutter analyze` | **À RENSEIGNER APRÈS LE RUN FINAL** | Analyse statique complète. |
| Flutter `flutter build web` | **À RENSEIGNER APRÈS LE RUN FINAL** | Build Web final. |
| React `tsc --noEmit` | **À RENSEIGNER APRÈS LE RUN FINAL** | Typecheck complet. |
| React `npm run build` | **À RENSEIGNER APRÈS LE RUN FINAL** | Build de production. |
| Docker build + smoke | **À RENSEIGNER APRÈS LE RUN FINAL** | Health et SPA à vérifier sur un port isolé. |
| Ruff backend + tests | **À RENSEIGNER APRÈS LE RUN FINAL** | Suite complète. |
| MyPy ciblé sur les fichiers backend modifiés | **À RENSEIGNER APRÈS LE RUN FINAL** | Documenter la commande et la version Python. |
| MyPy sur tout le backend | **À RENSEIGNER SI RÉEXÉCUTÉ** | Ne pas déduire son état du contrôle ciblé. |
| `git diff --check` | **À RENSEIGNER APRÈS LE RUN FINAL** | Contrôle du diff remis. |

Les campagnes ciblées exécutées pendant le développement se recoupent avec la suite complète; leurs nombres ne doivent pas être additionnés. Seuls des processus terminés avec code de sortie connu peuvent remplacer les marqueurs ci-dessus.

## Matrice d'acceptation T01–T30

« Automatisé » signifie qu'un ou plusieurs tests déterministes codent la couverture du comportement. Cela ne remplace pas le verdict de la campagne finale, encore en attente ci-dessus. « Partiel » signale en plus qu'une partie importante demande une recette sur hôte réel.

| ID | Exigence | Couverture vérifiable | Verdict et limite |
|---|---|---|---|
| T01 | Valeur nulle jamais inventée | `test_twelve_data_null_invalid_and_non_finite_values_are_never_filled`, `test_no_fabrication.py` | Automatisé. |
| T02 | Série mensuelle inchangée non présentée comme nouvelle | `test_a_monthly_figure_keeps_its_date_and_names_the_next_one`, fraîcheur par publication | Automatisé. |
| T03 | Révision conservée | `test_macro_revision_is_not_projected_before_its_vintage`, `test_macro_revision_keeps_each_vintages_own_provider_and_rights` | Automatisé; valeur et provenance point-in-time couvertes. Verdict final en attente de la suite consolidée. |
| T04 | Clôtures fournisseurs différentes non comparées naïvement | `test_same_local_date_from_different_exchanges_is_not_compared_as_one_close` | Automatisé : Tokyo et New York conservent des disponibilités UTC distinctes pour une même date locale. |
| T05 | Source hors ligne, diagnostic dégradé | `test_market_price_does_not_fabricate_when_providers_fail`, tests de health/source policy | Automatisé. |
| T06 | Limite API, backoff et cache | `test_backoff_grows_and_is_capped`, retries `HTTP_429`, circuit breaker et tests de cache | Automatisé. |
| T07 | Baisse mensuelle annoncée mais hausse mesurée | `test_false_monthly_drop_is_contradicted_by_point_in_time_closes` | Automatisé. |
| T08 | Nasdaq Composite/Nasdaq-100 ambigu | `test_bare_nasdaq_is_ambiguous_between_composite_and_nasdaq_100` | Automatisé. |
| T09 | Baisse conditionnelle de 30 % reste scénario | `test_conditional_thirty_percent_drop_stays_a_forecast` | Automatisé. |
| T10 | Causalité politique non démontrée signalée | `test_direct_political_causality_without_evidence_is_flagged` | Automatisé. |
| T11 | Nom mal reconnu non affirmé | `test_uncertain_transcribed_name_is_not_promoted_to_an_identity` | Automatisé. |
| T12 | Quinze familles, cinq cartes maximum | contrat/catalogue dans `test_macro_drivers.py` et widgets Flutter | Automatisé. |
| T13 | Top cinq recalculé | `test_the_top_five_is_recomputed_and_never_hard_coded` | Automatisé. |
| T14 | Pas de double comptage VIX/crédit/stress | `test_correlated_stress_signals_do_not_occupy_independent_top_slots` | Automatisé pour le radar; le moteur événementiel général garde une limite de déduplication causale. |
| T15 | Événement important sans direction reste `UNKNOWN` | `test_a_decision_due_tomorrow_is_critical_and_unknown` | Automatisé. |
| T16 | Contradictions peuvent produire `MIXED` | `test_an_easing_fed_inside_credit_stress_is_not_read_as_positive` et tests de contradiction | Automatisé sur les familles concernées. |
| T17 | Support touché sans clôture non confirmé | `test_1_touch_without_close_is_wait_close_never_confirmed` | Automatisé. |
| T18 | Zone invalidée, ancien diagnostic conservé | `test_an_invalidation_is_flagged_but_nothing_is_sold_without_a_rule`, `test_10_old_analyses_stay_in_the_history` | Automatisé. |
| T19 | Niveau vidéo garde origine et date | `test_evidence_is_the_transcript_at_the_right_time`, `test_reports_carry_timestamps_and_the_manual_comparison` | Automatisé sur fixtures. |
| T20 | Aucun niveau chiffré, aucun niveau inventé | `test_only_values_written_in_the_transcript_survive`, `test_9_no_price_means_nothing_is_deduced` | Automatisé. |
| T21 | Funding indisponible sans estimation | `test_no_fabrication.py`, contrats `UNAVAILABLE` | Automatisé. |
| T22 | Lisibilité iPhone compacte | widget tests 360 px, trois largeurs iPhone et contrat des trois cartes de risque | Automatisé en rendu; recette appareil, Dynamic Type et VoiceOver encore manuelle. |
| T23 | Détails accessibles sans surcharge | tests navigation/pages et limite des cinq cartes | Automatisé en widget. |
| T24 | UTC/Europe-Paris et changements d'heure | `test_utc_to_paris_conversion_handles_both_dst_transitions` | Automatisé : bascules printemps/automne, offsets et heure répétée (`fold`) couverts. |
| T25 | Fraîcheur réelle visible | `test_today_freshness.py`, `test_analysis_freshness.py`, widgets macro | Automatisé. |
| T26 | Tâche sans ouverture de l'app | scheduler serveur, `test_the_cycle_runs_on_the_clock`, `test_success_is_persisted_per_step_and_same_bucket_is_idempotent`, `test_failed_step_resumes_from_first_unfinished_and_keeps_history` | Partiel : cadence, état durable et reprise automatisés; activation systemd, reprise après crash réel et redémarrage hôte non certifiés. |
| T27 | Exécutions simultanées sans doublon | tests de déduplication Lexa/générale, `test_concurrent_runner_instance_is_skipped`, `test_host_lock_is_non_blocking_and_released`, staging | Automatisé en processus et entre processus du même hôte; pas de lease distribué multi-hôte. Verdict final en attente. |
| T28 | Notifications traçables | `test_alert_receipts.py`, reçus Lexa dans `test_lexa_plans.py`, widget Lexa et table React | Contrats API/snapshots automatisés et coordonnées principales visibles; snapshots bruts non dépliés. Verdict final en attente. |
| T29 | Analyse inchangée sans notification répétée | `test_5_two_videos_on_the_same_level_notify_once` et assertion « nothing new, nothing sent » | Automatisé. |
| T30 | Non-régression de tous les tests | campagnes backend/Flutter complètes | **EN ATTENTE DE LA CAMPAGNE FINALE**; ne reprendre ni ancien total ni ancien nombre de skips. |

## Particularité du bac à sable

Le `TestClient` FastAPI peut attendre dans le bac à sable de cette session lorsque le réveil inter-thread `asyncio.call_soon_threadsafe` est bloqué. Les campagnes concernées ont donc été exécutées hors sandbox lorsque nécessaire. Une série de points sans code de sortie du wrapper n'est jamais comptée comme une campagne réussie; seuls les retours terminés avec statut connu figurent ci-dessus.

## Validation historique

`PointInTimeView`, les vintages macro et les résultats de rapports permettent des replays sans look-ahead. Les révisions postérieures doivent être exclues des décisions anciennes. Le projet contient évaluation d'outcomes, recherches structurelles et expériences prospectives; cela ne constitue ni une preuve générale de performance, ni une calibration à 90/95 %.

## Contrôles restant obligatoires avant production

- test réseau de chaque source avec le plan réellement autorisé;
- vérification d'activation systemd et d'un cycle après redémarrage;
- sauvegarde et restauration des deux bases;
- test de charge, quotas et erreurs 429 sur l'infrastructure cible;
- test d'accessibilité sur iPhone réel, Dynamic Type et VoiceOver;
- proxy HTTPS authentifié avant toute exposition réseau;
- revue juridique avant redistribution publique;
- recette sur une transcription réelle dont l'origine et la date sont authentifiées.

Le rapport final est la source de vérité pour la dernière campagne exécutée sur la révision remise.
