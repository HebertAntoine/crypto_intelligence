# Audit du système existant — Market Intelligence

Date de référence du cahier des charges : 2026-10-26
Audit mis à jour : 2026-10-30
Révision de départ observée : `837c995` (`main`)

## Portée et prudence de lecture

Cet audit distingue trois choses : la présence d'un module dans le dépôt, son fonctionnement couvert par des tests, et son activation réelle sur un hôte avec réseau, clés et droits. Un adaptateur qui compile n'est pas une source de production certifiée. Une unité systemd fournie n'est pas une unité installée.

Le worktree comportait avant la mission 122 snapshots JSON modifiés sous `app/assets/api_snapshots/` et le classeur non suivi `Suivi_crypto_videos_maj_07-10-2026.xlsx`. Ils appartiennent à l'utilisateur et n'ont pas été réinitialisés, ajoutés à Git ou réécrits par ce lot.

## Matrice obligatoire de l'existant avant modification

Dans la colonne « Fonctionnelle », « Oui » signifie qu'un chemin exécutable et testé existait, pas qu'il satisfaisait déjà l'intégralité du nouveau cahier des charges.

| Fonction | Déjà présente | Fonctionnelle | Réutilisable | Modification nécessaire |
|---|---|---|---|---|
| Analyse macro | Oui | Oui | Oui | Conserver `MacroAnalyzer`; ajouter le catalogue exact S01–S15 et une lecture point-in-time plus stricte. |
| Analyse crypto | Oui | Oui | Oui | Conserver les analystes par actif et sécuriser les entrées macro/licences. |
| Signaux | Oui | Oui | Oui | Les cinq familles future-first existaient, mais pas les quinze familles macro/inter-marchés exactes ni leur top cinq dédié. |
| Prix | Oui | Oui | Oui | Distinguer ticker de présentation, stockage d'une barre en formation et bougie close utilisable; retirer les fallbacks sans droits établis. |
| Événements | Oui | Oui | Oui | Le cycle de vie était riche; il manquait la vérification d'affirmations de texte libre. |
| Décisions | Oui | Oui | Oui | Conserver `BuyOpportunityDecisionEngine`, les gates et les cinq familles; ne pas créer un second vote. |
| Graphiques | Oui | Oui | Oui | Maintenir les niveaux sourcés, les conditions de clôture et la distinction Lexa/moteur interne. |
| Historique | Oui | Oui | Oui | Conserver publication, ingestion, licence et provenance par vintage macro; enrichir les reçus de notification. |
| Lexa Moon | Oui | Oui | Oui | Ajouter un fact-check point-in-time des affirmations de marché sans fusionner celles-ci avec les niveaux du plan. |
| Scénarios | Oui | Oui | Oui | Supprimer les probabilités heuristiques et rendre les conditions plus explicitement dépendantes des preuves disponibles. |
| Notifications | Oui | Oui, in-app | Oui | Rendre déduplication et reçu atomiques; ajouter l'écran de contrôle. Aucun push externe n'existait. |
| Tâches automatiques | Oui | Oui si processus actif | Oui | Aligner le radar macro sur les huit créneaux UTC et rendre durable le workflow ordonné de treize étapes. |

## Architecture trouvée

### Backend et moteurs

Le backend FastAPI, la CLI et APScheduler vivent dans `backend/crypto_intel/`. `ProviderRegistry` associe une capacité à une chaîne ordonnée de fournisseurs; en `MOCK_MODE`, seules les fixtures explicitement prévues sont utilisées. Les objets `Observation`, `Computation`, `FutureEvent`, les historiques SQLAlchemy/SQLite et les moteurs déterministes alimentent les analystes spécialisés puis `ChiefMarketAnalyst`.

Deux classifications préexistantes ne doivent pas être confondues :

- les cinq familles future-first utilisées par la décision : macro/liquidité, catalyseurs/réglementation, flux/baleines, positionnement/dérivés, technique/volatilité;
- les quinze familles S01–S15, ajoutées comme radar macro/inter-marchés explicatif.

Le radar S01–S15 possède ses routes, son historique et son affichage. Il n'est toutefois pas injecté comme un objet unique dans `ChiefMarketAnalyst` ou dans la décision future-first. Plusieurs de ses observations sont aussi consommées par `MacroAnalyzer`, mais ce partage de données n'est pas une intégration du classement S01–S15 dans la décision.

### Stockage

La base principale par défaut est `data/crypto_intel.db`. Elle contient observations, calculs, rapports, résultats, événements, OHLCV, séries/vintages macro, dérivés, snapshots et décisions. Les migrations observées sont additives.

Le modèle générique `Observation` ne porte pas encore nativement tous les champs minimaux demandés : plusieurs restent dans `meta`. Le chemin macro historique enrichi conserve désormais provider, unité, URL, identifiant de série, statut de licence, publication/disponibilité, ingestion et révisions. Cette amélioration n'uniformise pas rétroactivement tous les anciens providers.

Lexa utilise `data/lexa/lexa.db`, séparée, privée et ignorée par Git.

### Interfaces

- Flutter (`app/`) reste l'interface principale iOS/Android/Web. Elle lit l'API ou les snapshots statiques; le WebSocket Kraken ne sert qu'à la présentation live.
- React/Vite (`frontend/`) est une interface web alternative servie par FastAPI après build.
- Les deux interfaces Future exposent maintenant les trois cartes de risque global; React expose aussi les coordonnées principales des reçus d'alertes générales.
- Les données Lexa sont exclues des snapshots publics.

### Lexa et classeur historique

Le domaine Lexa possédait déjà la saisie de transcriptions, la transcription audio locale, les citations horodatées, plans, niveaux, conditions, clôtures, simulations, comparaison au moteur interne, import Excel et notifications in-app.

Le classeur présent comporte `Dashboard`, `Ordres_actifs`, `Historique` et `Matrice_dates`. Un dry-run strictement en lecture seule a retrouvé 19 cryptos, 35 analyses historiques, 19 plans courants, 68 niveaux d'achat, 28 zones, 18 confirmations, 74 objectifs, une invalidation et 13 supports. Il a aussi signalé quatre cellules ambiguës et 38 plans à revalider : ces valeurs ne sont donc pas déclarées actuelles.

L'empreinte abrégée observée (`66ab3e48…9cee62`) correspond à l'entrée `lexa_imports` du 2026-10-07 19:12:02. Le classeur avait déjà été importé exactement une fois, en 54 analyses/54 vidéos Excel; la déduplication évite un second import. Le fichier original reste hors Git et n'a pas été modifié.

## Sources et dépendances trouvées

Des adaptateurs existent notamment pour Binance, Coinbase, Kraken, CoinGecko, Binance Futures, Deribit, FRED, BLS, U.S. Treasury, New York Fed, Fed H.4.1, BCE, BoJ, Twelve Data, calendriers officiels, SEC EDGAR, Congress.gov, RSS, DeFiLlama et plusieurs fournisseurs commerciaux optionnels.

Les absences importantes sont des connecteurs directs vers l'API EIA, l'API de données BEA et un feed Cboe direct. Le calendrier BEA existe, le PCE est lu via FRED, et le VIX n'est disponible que via FRED tiers ou Twelve Data lorsque les droits sont confirmés.

Les états par fournisseur sont détaillés dans `market_data_source_registry.md`; les droits dans `market_data_licensing.md`.

## Ordonnancement trouvé

APScheduler ne vit que dans un processus backend durable. Les jobs vont de 5 minutes à 24 heures; le radar S01–S15 est cadencé à 00:00, 03:00, 06:00, 09:00, 12:00, 15:00, 18:00 et 21:00 UTC. Des unités systemd fournissent aussi une passe légère toutes les 15 minutes et une passe complète à 07:00/19:00 locales avec verrou et publication atomique.

Le lot ajoute un workflow serveur durable de treize étapes sur les huit buckets UTC. Il possède un `cycle_id` stable, persiste chaque transition et reprend au premier état non réussi. Un verrou asynchrone couvre le processus et un `flock` couvre les workers du même hôte. Ce contrat rend l'exécution d'un bucket idempotente; il ne constitue pas un lease distribué multi-hôte et ne signifie pas qu'un client Flutter hors ligne a déjà reçu l'export.

## Corrections et ajouts constatés dans ce lot

- catalogue exact S01–S15, contrat enrichi, historique compact et top cinq dynamique;
- groupes d'indépendance pour limiter les doublons de stress;
- fournisseur Twelve Data à double opt-in, exclusion Yahoo/Stooq du chemin de production;
- CoinGecko Pro désactivé sans clé, droit commercial et attribution tous confirmés;
- FRED désactivé sans autorisation documentée du contenu, avec garde additionnelle pour ICE BofA/Cboe;
- appels SEC bloqués tant que `SEC_USER_AGENT` ne contient pas un contact réel et non factice;
- filtre de droits au moment de la lecture des lignes conservées;
- conservation de la provenance, publication, disponibilité et licence propres à chaque vintage macro;
- exclusion point-in-time des bougies en formation sur M15/H1/H4/D1/W1;
- fact-check déterministe point-in-time, endpoint API et branchement aux tests/imports Lexa;
- protection numérique et sémantique simple des sorties LLM, références de preuve obligatoires et rejet des probabilités narratives;
- exactement trois scénarios publics `base_case`, `bullish_case`, `bearish_case`, sans probabilité heuristique;
- reçus de notifications Lexa et générales, avec déduplication transactionnelle et statuts in-app distincts;
- diagnostic de risque sur `1-7d`, `8-30d` et `31-90d`, le dernier restant indéterminé sans familles dédiées;
- cycle durable de treize étapes aligné sur les huit créneaux UTC.

## Lacunes restantes

- Aucun transcript réel et authentifié n'a été fourni. Les deux exécutions conservées sont explicitement intitulées « EXEMPLE FICTIF ».
- Le fact-check général n'est branché qu'à Lexa et à un endpoint explicite; les flux RSS ne passent pas tous par ce moteur avant le pipeline principal.
- Le radar S01–S15 n'est pas encore une entrée directe du Chief ou du moteur de décision.
- S13 reste non directionnel sans panel normalisé de revenus, marges, trésorerie et CAPEX.
- Le contrat global expose bien 31–90 jours, mais son niveau reste `INDETERMINATE` tant qu'au moins trois familles propres à cette fenêtre ne sont pas disponibles; seuls les événements réellement datés y sont alors listés.
- L'API générale n'implémente pas d'authentification de compte; elle doit rester sur loopback ou derrière un proxy authentifié.
- Les notifications sont in-app seulement; il n'existe ni push OS, ni e-mail, ni accusé tiers.
- L'activation effective de systemd, un cycle complet après redémarrage, la restauration des bases et les appels live avec abonnements autorisés n'ont pas été certifiés par la seule présence du code. Le verrou du cycle n'est pas distribué entre plusieurs hôtes.

Le détail des validations exécutées et non exécutées figure dans `market_quality_validation.md`.
