# Intégration Lexa — LOT 4 : l'onglet 🎬 LEXA (plans suivis)

## 1. Audit de l'existant, et ce qui a été réutilisé

| Besoin | Existant dans le dépôt | Décision |
|---|---|---|
| Événements, calendrier | `FutureEvent` + `/future/{asset}/timeline` (carte « À surveiller ») | **réutilisé** : les événements CRITICAL/HIGH à venir alimentent le calendrier Lexa et bloquent une action à moins de 24 h |
| Notifications | `engines/alerts.py` (dedup_key + cooldown) | **même mécanique**, stockée dans la base Lexa : la base principale alimente des instantanés publics |
| Bougies | toutes Binance spot (`history/backfill.py`) | **même source** (Binance spot `{ACTIF}USDT`), lue en direct pour avoir la bougie en cours et des clôtures exactes, pour toute crypto |
| Planificateur | `scheduler.py` (APScheduler) | **nouveau job** `lexa_watch` toutes les 5 min |
| Niveaux, simulation, stockage Lexa | `lexa/store.py`, `levels.py`, `simulation.py` (LOT 2) | **étendus** (versions, conditions, plan, exécutions, événements, notifications) |
| Transcription | `lexa/extraction.py` + `test_run.py` (LOT 3) | **branché** : un test validé s'importe en plan |
| Moteur principal | `ChiefMarketAnalyst`, `future_decision` | **lu à côté**, jamais modifié (voir §9) |
| UI « À surveiller » | `future_analysis_screen.dart` | **même langage visuel** : badges date/mois, `GlassPanel`, `ColorEmoji` |
| Règles de clôture | rien d'équivalent | **créé** : `lexa/closes.py` |
| Plans utilisateur | réglage de capital (LOT 2) | **étendu** en budget + montants par niveau (USER_PLAN) |

## 2. Architecture

```
saisie manuelle ─┐
test transcription validé ─┴─> repository (versions immuables)
                                   │
       Binance (bougies + prix) ──> plans.compute ──> statut, action, règles SI/ALORS,
       calendrier de l'app ──────>        │           budget, dates, historique
       notre moteur (BTC/ETH/SOL) ─> concordance (à côté, jamais mélangée)
                                   │
               service (vue d'ensemble, calendrier, historique, révisions)
                                   │
         routes /api/lexa/* (loopback) ──> onglet 🎬 LEXA (build privée)
         notifier (job 5 min) ──> notifications dédupliquées
```

Quatre catégories, jamais mélangées : **EXPLICIT / INFERRED** (ce que dit Lexa), **USER_PLAN** (ton budget), **MARKET_VALIDATION** (calculé en direct), et l'**interprétation de l'app** (statut, règles, toujours expliqué).

## 3. Fichiers

- **Backend, nouveaux :** `lexa/market.py`, `lexa/closes.py`, `lexa/plans.py`, `lexa/service.py`, `lexa/notifier.py`.
- **Backend, étendus :** `lexa/store.py`, `lexa/repository.py`, `lexa/test_run.py` (import), `api/routes_lexa.py`, `scheduler.py`.
- **App, nouveaux :** `lib/lexa/lexa_home.dart`, `lexa_plan_page.dart`, `lexa_ui.dart`.
- **App, réécrits ou étendus :** `lexa_screen.dart` (saisie), `lexa_client.dart`, `lexa_models.dart`, `lexa_test_screen.dart` (import), `main.dart` (navigation).
- **Tests :** `tests/unit/test_lexa_plans.py`, `app/test/lexa_test.dart` et sa fixture fictive, `tests/tools/generate_lexa_flutter_fixtures.py`.

## 4. Base de données (`data/lexa/lexa.db`, locale, 0600, ignorée par Git)

Colonnes ajoutées (migration automatique `ALTER TABLE`) :
- `lexa_videos.video_url` ;
- `lexa_analyses` : `market_context`, `source_type`, `timestamp_start_s`, `timestamp_end_s`, `review_at`, `expires_at`, `status_override`, `status_reason`, `status_changed_at` ;
- `lexa_levels.basis`.

Tables créées :
- `lexa_conditions` (CloseCondition) : type, unité de temps, sens, clôtures requises, fenêtre de confirmation, description, origine ;
- `lexa_actions` : USER_PLAN, en EURO ou PERCENT ;
- `lexa_fills` : achats et ventes saisis par toi ;
- `lexa_plan_events` : remplacement d'un plan par une nouvelle vidéo ;
- `lexa_notifications`.

Types du brief : BUY = `BUY_ZONE`, STRONG_BUY = `REINFORCEMENT`, TAKE_PROFIT = `TARGET`/`TAKE_PROFIT`, plus SUPPORT, RESISTANCE, BREAKOUT, CONFIRMATION et INVALIDATION.

## 5. Endpoints (tous en 403 hors de 127.0.0.1, aucun dans l'export statique)

| Méthode | Route | Rôle |
|---|---|---|
| GET | `/api/lexa/overview` | à suivre + cartes par crypto |
| GET | `/api/lexa/plans/{asset}` | plan courant d'une crypto |
| GET | `/api/lexa/analyses/{id}/plan` | une version précise |
| GET | `/api/lexa/calendar` | dates en compartiments |
| GET | `/api/lexa/plans-history` | toutes les versions |
| GET | `/api/lexa/notifications` | notifications |
| POST | `/api/lexa/notifications/read` | marquer comme lues |
| POST | `/api/lexa/evaluate` | lancer la surveillance maintenant |
| PUT | `/api/lexa/analyses/{id}/user-plan` | budget et montants (USER_PLAN) |
| POST | `/api/lexa/analyses/{id}/fills` | exécution saisie par toi |
| DELETE | `/api/lexa/fills/{id}` | supprimer une exécution |
| POST | `/api/lexa/analyses/{id}/status` | invalider, terminer, rouvrir, réévaluer |
| POST | `/api/lexa/test-runs/{id}/import` | test validé → plans (valeurs vérifiées uniquement) |

## 6. Pages

**Page principale** (Plans & analyses) :
- en-tête avec 🔔, ➕ et 🧪 ;
- trois vues : **Actifs** (« 👀 À suivre » par date, puis « 📊 Plans actifs »), **Calendrier** et **Historique** ;
- filtres : Tout / BTC / ETH / SOL / XRP / Autres, puis Actifs / Terminés / Invalidés, puis Achat / Vente / Clôture / Objectif.

**Fiche crypto**, dans l'ordre du brief :
1. Que faire maintenant (statut, verdict, raison, action en attente)
2. Prochaine action
3. Niveaux en cartes (distance en direct, montant, état, condition de clôture avec compte à rebours, 🎬 minutage et citation, ✏️ Modifier)
4. Mon budget
5. Dates
6. Pourquoi ? (feuille avec les raisons et les règles SI/ALORS)
7. 🎬 Ce que dit Lexa, puis 🧠 Interprétation de l'application
8. 🔬 Validation par nos données
9. 🔄 Plan mis à jour
10. 🕒 Historique du plan
11. Versions

## 7. Dates

Tout est stocké en UTC et affiché à l'heure de Paris (`Europe/Paris`, changement d'heure géré). Les compartiments AUJOURD'HUI, DEMAIN, CETTE SEMAINE, PLUS TARD et PASSÉ sont calculés sur le jour à Paris.

Le calendrier contient :
- la publication de la vidéo et la date d'ajout de l'analyse ;
- les clôtures à attendre ;
- la réévaluation (7 jours par défaut) et la fin de validité (21 jours par défaut) ;
- les conditions déclenchées ;
- les événements de marché de l'app.

## 8. Clôtures (TOUCH ≠ CLOSE ≠ CONFIRMATION)

Les heures de clôture sont celles de Binance, en UTC :
- 1 h : à l'heure pile ;
- 4 h : 00, 04, 08, 12, 16 et 20 h ;
- journalière : 00:00 UTC, soit 02:00 à Paris l'été et 01:00 l'hiver ;
- hebdomadaire : lundi 00:00 UTC.

La bougie en cours n'est jamais comptée comme une clôture.

| Statut | Signification |
|---|---|
| WAITING | niveau pas encore atteint |
| TOUCHED_NOT_CLOSED | prix au-delà, bougie ouverte : ⏳ Attente clôture, compte à rebours |
| CLOSED_ABOVE / CLOSED_BELOW | clôtures au-delà, pas encore le nombre requis ou fenêtre de maintien en cours |
| CONFIRMED | condition remplie |
| FAILED | touché mais clôture revenue de l'autre côté, ou cassure perdue dans la fenêtre |
| INVALIDATED | scénario invalidé |

Sans condition dite dans la vidéo, un contact reste un contact : jamais « confirmé ».

## 9. Niveaux, statuts et moteur principal

**Statuts du brief** (toujours emoji + texte) :
- 🟢 ACHAT PLANIFIÉ, ZONE D'ACHAT ATTEINTE, CONFIRMATION HAUSSIÈRE ;
- 🟠 ATTENDRE, ATTENDRE CLÔTURE, À SURVEILLER, CONFIRMATION MANQUANTE, ENTRE DEUX NIVEAUX ;
- 🔴 PRISE DE PROFIT, VENTE PLANIFIÉE, INVALIDATION ;
- 🔵 PLAN ACTIF ;
- ⚪ PLAN TERMINÉ ;
- ⚫ PLAN EXPIRÉ.

Plus ⚪ PLAN REMPLACÉ et ⚪ PRIX INDISPONIBLE.

**Verdict principal :** ACHETER, ATTENDRE, PRENDRE DES PROFITS, PLAN INVALIDÉ, PLAN TERMINÉ ou PLAN EXPIRÉ.

**Niveau atteint ≠ action.** Dans la zone d'achat, le verdict passe à ATTENDRE avec « 🟠 Action en attente » dans les cas suivants :
- un événement CRITICAL tombe dans les 24 h ;
- la réévaluation est dépassée ;
- l'invalidation a été touchée sans condition précisée ;
- notre moteur est en VENDRE, ou les familles rouges dominent.

**Moteur principal.** Le ChiefMarketAnalyst ne lit jamais Lexa : sa sortie est exportée publiquement, et y injecter Lexa ferait fuiter un contenu privé. Le contexte « analyste externe » est donc construit uniquement dans `/api/lexa/*`, par comparaison :
- concordance descriptive 🟢 Forte, 🟠 Partielle, 🔴 Faible ou ⚪ Données insuffisantes, sans aucun pourcentage ;
- divergence affichée quand Lexa dit ACHETER alors que notre moteur ne dit pas ACHETER.

## 10. Versions

Chaque vidéo crée une nouvelle version, et l'ancienne passe **SUPERSEDED**, conservée dans l'historique. La relation est calculée ainsi :

| Relation | Cas |
|---|---|
| CONFIRMS | mêmes niveaux à 0,3 % près |
| UPDATES | niveaux modifiés, même sens |
| REPLACES | aucun niveau commun |
| CONTRADICTS | sens opposé, ou invalidation au-dessus de l'ancienne entrée |

Le bloc « 🔄 Plan mis à jour » liste chaque changement (ancienne valeur → nouvelle). La raison affichée est celle de la nouvelle analyse, sinon « non précisée ».

**Cycle de vie d'une analyse :**
- ACTIVE : plan suivi, aucun niveau atteint ni proche ;
- WATCHING : un niveau est proche, ou une clôture est en attente ;
- TRIGGERED : une entrée, une confirmation ou un objectif a été atteint ;
- COMPLETED : tous les objectifs atteints, ou marqué terminé par toi ;
- INVALIDATED : condition d'invalidation remplie, ou marqué invalidé par toi ;
- SUPERSEDED : remplacée par une nouvelle vidéo ;
- EXPIRED : validité dépassée. Aucune alerte n'est alors envoyée, et « J'ai réévalué » prolonge le plan.

## 11. Notifications

Les messages possibles :
- approche d'un niveau (à 1,5 % ou moins) ;
- niveau touché ;
- clôture dans moins d'une heure ;
- clôture au-delà d'un niveau ;
- confirmation validée ;
- confirmation toujours manquante ;
- objectif atteint ;
- nouvelle analyse qui modifie le plan ;
- plan invalidé.

Contre le spam :
- La clé porte la crypto et le **niveau**, pas l'analyse : deux vidéos sur le même niveau donnent une seule notification.
- Un délai de silence s'applique par type.
- Au plus 8 notifications par crypto et par 24 h, les plus importantes d'abord.
- Rien pour un plan expiré, remplacé ou terminé, ni pour un fait antérieur à l'ajout de l'analyse.

L'envoi passe par des « sinks » : in-app aujourd'hui, push branchable plus tard.

## 12. Tests

`tests/unit/test_lexa_plans.py` couvre les 10 cas obligatoires :
1. touché, bougie non clôturée : ATTENDRE CLÔTURE ;
2. clôture au-dessus : condition déclenchée ;
3. nouvelle analyse : l'ancienne passe SUPERSEDED, avec le détail des changements ;
4. niveau atteint après expiration : aucune alerte ;
5. deux vidéos sur le même niveau : une seule notification ;
6. Lexa ACHETER alors que notre moteur dit ATTENDRE : divergence visible ;
7. montants : USER_PLAN, jamais attribués à Lexa ;
8. niveaux : ils viennent de l'analyse seule ;
9. pas de prix ou vidéo illisible : rien n'est déduit ;
10. l'historique est conservé.

S'y ajoutent : la fenêtre de confirmation, les heures de clôture été/hiver, les routes en loopback et l'import d'un test.

**Valeurs fictives uniquement.** Le dépôt est public : aucun niveau Lexa n'y est versé. Les anciens tests contenant des niveaux d'une analyse ont été convertis en valeurs fictives (×1,7, pour garder les mêmes écarts relatifs). Ils restent visibles dans l'historique Git des commits 9180163 et 4185573 ; réécrire l'historique d'un dépôt public est une décision à prendre à part.

## 13. Sur l'iPhone (site habituel)

- Le site public (Vercel) affiche l'onglet 🎬 LEXA, mais il ne contient aucune donnée Lexa. Il lit tes plans sur ton PC, à l'adresse Tailscale privée `https://debian-server.tail484b42.ts.net:8443`, qu'on peut changer avec `LEXA_BASE_URL` dans Vercel.
- Hors de Tailscale, l'onglet affiche seulement « active Tailscale ». Le backend n'accepte les requêtes (en-têtes CORS) que de ce site et du poste local.
- Côté PC, une commande à lancer une fois, avec mot de passe administrateur : `sudo tailscale serve --bg --https=8443 http://127.0.0.1:8100`. Pour annuler : `sudo tailscale serve --https=8443 off`.

## 14. Reste à faire

- Une vraie transcription Lexa pour le test de validation (LOT 3). Rien n'est automatisé avant ta validation.
- Notifications push hors de l'app : il suffit d'ajouter un sink ; aujourd'hui, elles s'affichent dans l'app.
- Les événements cités par Lexa elle-même, dates à interpréter : ils sont extraits par le test, mais pas encore placés au calendrier.
- La comparaison fine de ses niveaux avec nos propres supports et résistances, pour BTC, ETH et SOL.
