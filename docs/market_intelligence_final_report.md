# Rapport final — Market Intelligence / Lexa Moon

Date de clôture documentaire : 2026-10-30
Révision de départ auditée : `837c995`

Ce rapport décrit l'état réellement observé dans le dépôt. Les comptes de validation finale restent explicitement en attente tant que la campagne postérieure aux derniers changements n'est pas terminée. « Adaptateur connecté » signifie que le chemin applicatif existe; cela ne certifie ni un abonnement, ni un appel live réussi, ni un droit de redistribution. Les 122 snapshots JSON déjà modifiés par l'utilisateur et le classeur non suivi `Suivi_crypto_videos_maj_07-10-2026.xlsx` n'ont pas été réinitialisés, ajoutés à Git ou réécrits par ce lot.

## 1. Fonctionnalités qui existaient avant les modifications

- backend FastAPI, CLI, SQLite, migrations additives, `ProviderRegistry`, cache, retries et APScheduler;
- modèles d'observations, preuves, événements, calculs, rapports et historiques;
- cinq familles future-first, analystes spécialisés, `ChiefMarketAnalyst`, contradictions, conviction et `BuyOpportunityDecisionEngine`;
- prix, OHLCV, dérivés, liquidité, ETF, événements macro/réglementaires/crypto et analyse technique selon disponibilité;
- décisions conditionnelles, supports/résistances, breakouts, retests, invalidations et graphiques annotés;
- Flutter iOS/Android/Web et frontend React/Vite;
- domaine Lexa privé : saisie/transcription locale, citations, plans, niveaux, simulations de 100 € configurables, historique, import Excel et alertes in-app;
- export atomique de snapshots, services/timers systemd fournis et documentation de déploiement.

Ces briques ont été réutilisées. Le lot n'a créé ni seconde application, ni second moteur de décision.

Le dry-run en lecture seule du classeur utilisateur a retrouvé quatre feuilles, 19 cryptos, 35 analyses historiques et 19 plans courants. Son empreinte abrégée `66ab3e48…9cee62` correspond à l'import Lexa du 2026-10-07 19:12:02 : 54 analyses/54 vidéos avaient déjà été importées une fois et n'ont pas été dupliquées. Quatre cellules ambiguës et 38 plans restent à revalider.

## 2. Fonctionnalités ajoutées

- catalogue exact S01–S15 avec contrat enrichi, historique compact, score explicable, top cinq dynamique et groupes d'indépendance;
- routes API du radar macro, cinq cartes sur la page principale Flutter, liste des quinze, détail, source et graphique historique;
- provider Twelve Data conservant instrument, fuseau, observation, disponibilité, fréquence, devise, qualité et droits;
- backfill macro enrichi et vue point-in-time tenant compte publication, disponibilité, ingestion, vintage et licence, avec provenance propre à chaque version;
- moteur déterministe de vérification des affirmations, huit statuts obligatoires, endpoint dédié et intégration aux tests/imports Lexa;
- distinction close-to-close/recul depuis sommet et contrôle des formulations datées, opinions, prévisions, causalités et entités ambiguës;
- contrat complet d'exactement trois scénarios publics `base_case`, `bullish_case`, `bearish_case` : hypothèse, horizon, actifs, preuves confirmées, conditions, confirmations, invalidation, incertitudes et prudence;
- contrat de calibration obligatoire avant toute probabilité numérique de scénario ou d'hypothèse;
- diagnostic de risque global sur les trois fenêtres disjointes `1-7d`, `8-30d` et `31-90d`, sans probabilité ni recyclage du 30 jours;
- reçus Lexa et alertes générales avec statut in-app, motif, snapshot de preuve et déduplication transactionnelle; écran Flutter dédié pour Lexa;
- cycle durable de treize étapes aux huit créneaux UTC, avec `cycle_id`, transitions persistées, reprise et relance radar après publication majeure déjà collectée.

## 3. Fonctionnalités corrigées

- aucune bougie M15/H1/H4/D1/W1 non close n'entre dans les lectures analytiques; le stockage peut seulement mettre à jour la barre en formation;
- une valeur nulle/non finie ou un instrument inattendu est refusé, jamais remplacé par zéro;
- les lignes historiques devenues inadmissibles sont filtrées à la lecture, pas seulement à la collecte;
- Twelve Data, CoinGecko, tout contenu FRED, ses séries tierces et SEC échouent fermé lorsque droits, clé, attribution ou identité requise manquent;
- la publication n'est plus déduite de l'observation; valeur et provenance des révisions restent attachées à leur vintage;
- l'ancienne distribution heuristique de probabilités `central/bull/bear` a été supprimée;
- le LLM ne peut plus injecter librement petits entiers, pourcentages ou ratios, ni réutiliser le même nombre sous une métrique/unité incompatible; chaque constat doit citer une preuve exposée;
- les scénarios ne créent plus de conditions génériques pour une entrée ETF, dollar, liquidité, funding ou technique absente;
- « sol » en français n'est plus résolu comme SOL sans contexte crypto, tandis que le ticker explicite `SOL` reste reconnu;
- deux workers Lexa locaux ne peuvent plus persister simultanément la même notification.

## 4. Sources effectivement connectées

Les chaînes ci-dessous sont enregistrées dans le runtime et couvertes hors réseau. Leur disponibilité live dépend de l'hôte, des conditions du fournisseur et des réglages.

| Domaine | Chaîne/adapter connecté | Activation |
|---|---|---|
| Ticker crypto | Binance → Coinbase → Kraken | endpoints publics; disponibilité territoriale à contrôler |
| OHLCV crypto | Binance → Kraken | endpoints publics; bougies conservées par place |
| Dérivés | Binance Futures, Deribit | publics pour les capacités exposées |
| DeFi/liquidité | DeFiLlama | sans clé pour les endpoints utilisés |
| Macro US | U.S. Treasury, New York Fed, Fed H.4.1, BLS, FRED | sources officielles directes; FRED API/CSV uniquement avec autorisation de contenu documentée et, si requis, droit tiers |
| Banques centrales | Fed, BCE, BoJ | calendriers/publications officiels |
| Calendriers | FOMC, BLS, BEA, TreasuryDirect | parsing officiel; BEA calendrier seulement |
| Réglementation | SEC, CFTC, House, Senate, Congress.gov | SEC avec contact réel; Congress avec clé |
| Marchés inter-actifs | Twelve Data | clé et droit de redistribution explicite |
| Capitalisation/breadth | CoinGecko Pro | clé, droit commercial et attribution explicites |
| News | flux RSS configurés | métadonnées/liens, pas de paywall |

Aucun appel live avec l'ensemble des abonnements autorisés n'a été certifié pendant cette recette. Le registre détaillé est `market_data_source_registry.md`.

## 5. Sources non connectées et raison

- API de données EIA directe : aucun adaptateur; le Brent peut venir de FRED selon droits.
- API de données BEA directe : calendrier présent et PCE possible via FRED, mais pas de collecteur BEA complet.
- feed Cboe direct : absent; le VIX tiers reste soumis aux droits FRED/Twelve.
- panel S13 revenus, marges, trésorerie et CAPEX : SEC existe, mais aucun agrégateur directionnel normalisé n'est achevé.
- CME FedWatch : pas de scraping; indisponible sans URL API licenciée et clé.
- fournisseurs Coinglass, SoSoValue, Glassnode, CryptoQuant, Nansen, Arkham et Whale Alert : inactifs sans abonnement/clé.
- flux ETF Farside/CoinShares : droit de republication et automatisation à confirmer; aucun contournement anti-bot.
- EIA/BEA/Cboe ne sont pas remplacés silencieusement par une source non autorisée.

## 6. APIs nécessitant une clé

| Variable | Usage |
|---|---|
| `FRED_API_KEY` | accès aux séries FRED API; ne prouve pas le droit de contenu |
| `TWELVE_DATA_API_KEY` | indices, FX et VIX autorisés |
| `COINGECKO_API_KEY` | endpoint Pro de capitalisation/breadth; ne suffit pas sans droits et attribution |
| `CME_FEDWATCH_API_KEY` + `CME_FEDWATCH_API_URL` | anticipations CME licenciées |
| `CONGRESS_API_KEY` | Congress.gov |
| `ETHERSCAN_API_KEY` | fallback on-chain Ethereum |
| `COINGLASS_API_KEY`, `SOSOVALUE_API_KEY` | dérivés/ETF optionnels |
| `GLASSNODE_API_KEY`, `CRYPTOQUANT_API_KEY`, `NANSEN_API_KEY`, `ARKHAM_API_KEY`, `WHALE_ALERT_API_KEY` | données spécialistes optionnelles |
| `LLM_API_KEY` | LLM cloud optionnel; non nécessaire avec `none` ou Ollama |

`SEC_USER_AGENT` n'est pas une clé : il doit identifier honnêtement l'application avec une adresse de contact réelle.

## 7. APIs nécessitant une licence

- Twelve Data exige, en plus de la clé, `TWELVE_DATA_REDISTRIBUTION_AUTHORIZED=true` après revue du plan.
- CoinGecko reste désactivé sans clé Pro, `COINGECKO_COMMERCIAL_USE_AUTHORIZED=true` et `COINGECKO_ATTRIBUTION_CONFIGURED=true` simultanément.
- tout contenu FRED reste exclu sans `FRED_CONTENT_USE_AUTHORIZED=true`, drapeau qui doit correspondre à une autorisation documentée du cas d'usage;
- les séries FRED dont le contenu appartient à ICE BofA ou Cboe exigent en plus `FRED_THIRD_PARTY_REDISTRIBUTION_AUTHORIZED=true`;
- CME FedWatch ne doit être utilisé que via une API et un contrat adaptés;
- fournisseurs ETF, dérivés, baleines et on-chain commerciaux gardent leurs propres droits de cache, affichage et redistribution;
- accès gratuit ou visibilité publique ne signifient pas automatiquement droit de republication.

Les drapeaux techniques empêchent un usage accidentel; ils ne constituent pas une preuve juridique. Les références et la procédure d'activation figurent dans `market_data_licensing.md`.

## 8. Coûts éventuels à prévoir

Le dépôt ne fixe aucun tarif, car prix et droits changent selon volume, historique, SLA et redistribution. Les postes possibles sont :

- plans Twelve Data et CoinGecko commerciaux;
- CME FedWatch;
- Coinglass/SoSoValue et fournisseurs baleines/on-chain;
- hébergement long-lived, volume persistant, sauvegardes et supervision;
- proxy/authentification et éventuel fournisseur de push;
- LLM cloud si le chemin local/`none` n'est pas retenu;
- revue juridique des droits de redistribution.

Aucun montant n'est présenté comme actuel sans devis contractuel.

## 9. Fréquences réellement fonctionnelles

| Travail APScheduler | Cadence codée |
|---|---:|
| ticker | 5 min |
| analyse complète par actif + historique de décision | 30 min |
| OHLCV, dérivés, DVOL, expériences et outcomes | 60 min |
| ETF | 240 min |
| événements futurs | 360 min |
| surveillance Lexa | 5 min |
| surveillance publications macro | 15 min |
| cycle serveur 13 étapes, dont radar S01–S15 | 00, 03, 06, 09, 12, 15, 18 et 21 h UTC |
| purge | 24 h |

Ces cadences nécessitent un processus backend durable avec scheduler actif. Le cycle de trois heures exécute les treize étapes contractuelles, persiste son état et reprend au premier état non réussi dans le même bucket. Les timers systemd fournis ajoutent une passe légère toutes les 15 minutes et une passe complète à 07:00/19:00 locales. Le runner combine verrou de processus et `flock` sur l'hôte, mais pas de lease distribué entre plusieurs hôtes.

## 10. Signaux effectivement calculés

| ID | Famille | État réel |
|---|---|---|
| S01 | Politique Fed | calculable avec taux/calendrier disponibles |
| S02 | Inflation US | Core CPI/Core PCE et tendance |
| S03 | Emploi US | chômage, payrolls, claims selon données |
| S04 | Taux obligataires | 2 ans, 10 ans, réel 10 ans selon disponibilité |
| S05 | Pétrole | Brent, WTI en repli, variation/rang historique |
| S06 | Risque de crédit | HY/IG; droits tiers obligatoires |
| S07 | Stress financier | NFCI/STLFSI4 et conflits |
| S08 | Dollar et changes | DXY/dollar large et FX autorisés |
| S09 | Liquidité US | bilan Fed − TGA − RRP |
| S10 | Divergence indices US | au moins deux indices autorisés |
| S11 | Contagion internationale | US/Japon/Europe selon couverture |
| S12 | Volatilité | VIX autorisé, percentile/variation |
| S13 | Résultats et IA | événement daté; direction indisponible sans panel normalisé |
| S14 | Politique BCE | taux de dépôt et calendrier |
| S15 | Politique BoJ | call rate et calendrier |

Une famille indisponible reste visible avec sa raison et ne rejoint pas le top cinq. Le score d'attention n'est pas une probabilité ni une direction.

## 11. Écrans et navigations créés

- Flutter : carte des cinq signaux dans l'analyse future, page des quinze signaux, fiche signal avec valeur/précédent/delta, observation/publication, source ouvrable et historique;
- Flutter/iPhone et React Future : trois cartes de risque global `1-7d`, `8-30d`, `31-90d` avec niveau, couverture, facteurs et limites;
- Flutter Lexa : accès depuis l'historique vers la boîte de notifications, non-lues, reçu, motif, état vide/erreur et « tout marquer comme lu »;
- React : scénario enrichi sur la page actif avec horizon, actifs, preuves confirmées, conditions, confirmations, invalidation, incertitudes et prudence;
- API : endpoint explicite de vérification des claims, routes du radar macro, reçus complets `/alerts`, diagnostic `/future/{symbol}/global-risk` et dernier workflow durable sous `/api/scheduler/status`.

Les pages existantes d'actif, calendrier, graphiques, historique, sources et Lexa ont été conservées. La table React globale affiche identifiants, motif, statut et horodatages des reçus généraux, sans déplier le snapshot brut. Aucune recette complète sur iPhone physique, VoiceOver et Dynamic Type n'a été réalisée.

## 12. Tests exécutés

**Campagne finale post-modifications : À RENSEIGNER.** Les totaux de la campagne antérieure au 2026-10-30 ne sont pas repris comme résultat final, car ils précèdent les derniers changements de garde LLM, droits FRED/CoinGecko, provenance par vintage, bougies closes, scénarios, risque, reçus généraux et cycle durable.

Avant clôture, consigner uniquement les commandes terminées avec code de sortie connu pour : backend complet, Ruff, MyPy ciblé, Flutter tests/analyse/build, React typecheck/build, Docker build/smoke et `git diff --check`. La matrice détaillée T01–T30 se trouve dans `market_quality_validation.md`; son T30 reste en attente de cette consolidation. T26 reste partiel faute de recette après redémarrage sur l'hôte cible.

## 13. Échecs restants

- l'état final des suites complètes et le nombre d'éventuels skips ne sont pas encore consolidés; aucun ancien total ne doit être présenté comme actuel;
- l'état MyPy global doit être distingué du contrôle ciblé et documenté seulement s'il est réexécuté;
- toute commande qui affiche une progression sans rendre de code de sortie reste non comptabilisable;
- aucune recette live fournisseurs, redémarrage systemd, restauration de base ou notification push externe n'a été exécutée.

## 14. Limitations

- contrat minimal universel d'`Observation` encore réparti entre champs natifs et `meta` selon les anciens providers;
- radar S01–S15 affiché et historisé, mais pas injecté comme objet unique dans le Chief ou la décision;
- fact-check branché à Lexa et à une route explicite, pas en filtre obligatoire de tous les RSS/articles;
- contrat 31–90 jours présent, mais niveau volontairement `INDETERMINATE` tant qu'au moins trois familles propres à cette fenêtre ne sont pas disponibles;
- S13 incomplet et connecteurs directs EIA/BEA/Cboe absents;
- historique quantitatif disponible, mais aucune preuve générale de performance ou calibration de probabilités;
- trois scénarios future-first sur 24 h/7 j/30 j et scénarios Chief 8–30 jours; des rapports anciens peuvent ne pas porter le nouveau contrat complet;
- certains libellés déterministes hors Flutter restent en anglais; une francisation exhaustive n'est pas certifiée;
- API générale sans authentification de compte; local/loopback ou reverse proxy authentifié obligatoire;
- pas de séparation multi-compte qualifiée pour une exposition publique;
- notifications in-app uniquement, sans push OS/e-mail/SMS ni accusé tiers;
- cycle treize étapes durable par bucket, mais absence de verrou distribué multi-hôte et export statique Flutter encore séparé;
- accessibilité iPhone réelle non recettée; les conversions DST Europe/Paris et les clôtures Tokyo/New York sont couvertes par des tests déterministes, pas par une campagne live multi-fournisseurs.

## 15. Résultat de la vérification sur une vraie transcription

Condition non satisfaite : aucune transcription réelle, datée et authentifiée n'a été fournie.

Les deux exécutions conservées sont explicitement nommées « EXEMPLE FICTIF » et les tests utilisent des fixtures fictives. Elles valident extraction, provenance, fact-check, rapports et import sans écriture prématurée, mais ne mesurent pas la qualité sur une vraie vidéo. Aucun résultat fictif n'est présenté comme une validation réelle.

La recette finale exige un texte/transcript légalement obtenu, son URL ou identifiant, sa date de publication, puis une revue manuelle des claims, périodes, citations et niveaux avant import.

## 16. État des notifications

Le canal Lexa in-app possède le contrat et les tests dédiés suivants (verdict global encore soumis à la campagne finale) :

- transaction SQLite immédiate pour cooldown, plafond, déduplication et insertion;
- clé par actif/règle/niveau et timestamp de clôture lorsque pertinent;
- reçu `notification_id`, `trigger_id`, `asset_id`, `analysis_id`, création/remise, statut, motif et snapshot;
- `DELIVERED` signifie « persisté dans la boîte Lexa », pas « vu par iOS » ni « lu »;
- écran Flutter de contrôle et marquage lu.

`AlertEngine` général possède maintenant son propre reçu `notification_id`, `trigger_id`, `asset_id`, `analysis_id`, création/remise, statut, motif et snapshot. La transaction SQLite immédiate revérifie cooldown et retry exact avant insertion; `STORED` signifie uniquement « accepté par la boîte in-app ». Les anciennes lignes gardent un identifiant stable et `UNKNOWN` pour les faits absents. L'API expose le contrat et la table React affiche les coordonnées/statuts principaux, sans déplier le snapshot; les deux boîtes ne sont pas fusionnées. Aucun canal externe n'est implémenté.

## 17. État des tâches automatiques

APScheduler est codé côté serveur et ne dépend pas de l'ouverture de l'application. Le workflow de treize étapes tourne aux huit créneaux UTC; le watcher macro peut relancer le radar après une publication majeure déjà collectée. `cycle_id`, transitions persistées, reprise du suffixe, `max_instances=1`, coalescence, délai de misfire, cache, retries/backoff, circuit breaker, identifiants déterministes et exports atomiques limitent les doublons et les échecs.

Limites opérationnelles :

- `max_instances=1` est local au scheduler; le runner couvre aussi les autres processus du même hôte par `flock`, mais pas plusieurs hôtes;
- chaque source n'est collectée que si elle est due et admissible; une capacité sans droit reste indisponible;
- activation systemd, persistance après déconnexion/redémarrage et cycle réel sur l'hôte n'ont pas été certifiés;
- l'export statique Flutter garde son propre workflow de promotion; le `cycle_id` serveur ne prouve pas la réception par un appareil hors ligne.

## 18. Instructions de déploiement

- Copier `.env.example` vers `.env`; renseigner uniquement les clés disponibles et ne passer les drapeaux de droits à `true` qu'après revue contractuelle. En particulier, FRED exige `FRED_CONTENT_USE_AUTHORIZED` et parfois le drapeau tiers; CoinGecko exige clé Pro, droit commercial et attribution configurée; Twelve Data exige clé et droit de redistribution.
- Laisser `API_HOST=127.0.0.1` pour un usage local. Pour Internet, placer un reverse proxy HTTPS authentifié devant l'API avant toute ouverture réseau.
- Déploiement mono-hôte : `docker compose up -d --build`, puis vérifier `curl -fsS http://127.0.0.1:8100/api/health`.
- Initialiser les historiques si nécessaire avec `docker compose exec app crypto-intel backfill`; conserver un volume persistant sur `/app/data`.
- Sauvegarder et restaurer en recette `data/crypto_intel.db` et la base Lexa privée avant production.
- Pour Flutter Web : `cd app && flutter build web --release --dart-define=API_BASE_URL=https://backend.example`; pour mobile, utiliser la même URL HTTPS dans le `dart-define`.
- Pour systemd utilisateur, installer les unités de `deploy/`, exécuter `systemctl --user daemon-reload`, activer les services/timers, puis contrôler `systemctl --user status` et `journalctl --user`.
- Ne pas activer `loginctl enable-linger`, exposer l'API, importer le classeur privé ou diffuser une source sous licence sans autorisation opérateur explicite.
- Après déploiement : contrôler providers, quotas, 429, fraîcheur, cycle S01–S15, export, reçus de notification, redémarrage, sauvegarde/restauration et accessibilité réelle.

La procédure détaillée existante reste dans `docs/deployment.md`. Aucune opération de trading automatique n'est autorisée.
