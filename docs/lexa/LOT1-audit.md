# Intégration Lexa — LOT 1 : audit

Date : 21/09/2026. Aucun code n'a été modifié. Aucune tentative de connexion n'a été faite : seules les pages et le code client **publics** ont été lus.
Légende : ✅ CONSTATÉ · ⚠️ NON VÉRIFIÉ (nécessite ta session ou ta confirmation).

## 1. Architecture actuelle pertinente

| Élément | Constat |
|---|---|
| App Flutter | ✅ App **web**, 4 onglets (`BTC`, `ETH`, `SOL`, `Graphique`) dans `app/lib/main.dart` (`HomeShell`, `IndexedStack`, `MobileBottomNav`). |
| Données de l'app | ✅ Sans backend en production : l'app lit des **snapshots JSON** (`app/assets/api_snapshots/`) exportés par `scripts/export_flutter_static_api.py`. Un backend local peut servir la même API (`API_BASE_URL`). |
| Publication | ✅ Le dépôt `HebertAntoine/crypto_intelligence` est **public** (l'API GitHub répond sans authentification), et les 121 snapshots y sont versionnés. `crypto-intelligence.vercel.app` répond (appartenance ⚠️ non vérifiée, citée dans `docs/deployment.md`). |
| Backend | ✅ FastAPI + SQLite (SQLAlchemy, `backend/crypto_intel/db/base.py`), routes par module (`api/routes_*.py`), service `serve` sur le port 8100 **non installé**. |
| Prix | ✅ Côté app : flux Kraken en direct (`lib/live_prices/`). Côté backend : bougies Binance 1 h / 4 h / 1 j (`history/store.py`), utilisables pour le suivi des niveaux et les conditions de clôture. |
| LLM | ✅ Abstraction existante (`backend/crypto_intel/llm/providers.py`) avec un fournisseur **Ollama** ; `gemma3:12b` est installé localement. Aucune clé cloud configurée. |
| Transcription | ✅ GPU RTX 4070 SUPER (12 Go) disponible ; ⚠️ aucun moteur de transcription installé (faster-whisper absent), `ffmpeg` absent du système (une version Playwright est en cache). |
| Navigateur automatisable | ✅ Chromium Playwright en cache ; ⚠️ le paquet Python `playwright` n'est pas installé dans le projet. |
| Secrets | ✅ `.env` ignoré par Git (`.gitignore` : `.env`, `*.env`). Aucun trousseau (`keyring`) installé. |

## 2. Ce que « Lexa » recouvre réellement

| Service | Constat |
|---|---|
| **lexa-predicts.fr** | ✅ Application React (jeu de prédictions Bitcoin). Connexion par **email + mot de passe** (`/api/auth/login.php`), jeton stocké dans `localStorage` du navigateur. Ses vidéos sont une liste **YouTube publique** (`/api/youtube/videos.php`). Aucun parcours à code à 6 chiffres dans son code public. |
| **lexamooncrypto.fr** | ✅ Site WordPress. Le **Club Lexa Rocket** y est vendu via **LaunchPass** (paiement Stripe). |
| **Portail LaunchPass** | ✅ Connexion par email + **code d'accès** (champ `inputAccessCode` constaté). ⚠️ C'est probablement le parcours que tu décris, mais ce portail gère **l'abonnement** (paiement, résiliation), pas les vidéos. |
| **Contenus du club** | ✅ La page du club l'écrit : « Les contenus sont envoyés sur **DISCORD** ». ⚠️ Le format exact des vidéos dans Discord (fichier joint, lien YouTube non répertorié, autre hébergeur) n'est pas vérifiable sans ta session. |

## 3. Authentification Lexa

- ✅ Le parcours email + code existe côté **LaunchPass**, pas côté lexa-predicts.fr.
- ⚠️ Je n'ai pas pu confirmer que ce parcours donne accès à des **vidéos** : les éléments publics indiquent que les vidéos passent par Discord.
- **Question bloquante** : sur quelle adresse (URL) te connectes-tu avec email + code, et où lis-tu les vidéos ensuite ?

## 4. Persistance de session recommandée

Si un site web authentifié donne effectivement accès aux vidéos :

- Un **profil de navigateur dédié**, persistant, stocké **hors du dépôt** (`~/.local/share/crypto_intel/lexa/profile/`, droits 700), piloté par Playwright en mode visible.
- **Tu tapes toi-même** l'email et le code dans la vraie page du site ; le code n'est jamais lu, capturé, journalisé ni stocké.
- Les cookies restent dans ce profil : jamais copiés dans SQLite, dans Git ni dans les logs.
- Expiration : vérifiée en ouvrant une page authentifiée ; une redirection vers la connexion donne « 🟠 Session expirée ». Aucune tentative de prolongation.
- Le backend reste lié à `127.0.0.1` uniquement.

## 5. Lecteur vidéo

⚠️ **NON VÉRIFIÉ.** Rien dans le code public ne révèle de lecteur (pas de HLS, de DRM, de Vimeo ou de Mux dans lexa-predicts.fr ; le club renvoie à Discord). À constater avec ta session, sur une seule vidéo.

## 6. Faisabilité de la transcription

| Voie | Statut |
|---|---|
| Transcription locale (faster-whisper sur la RTX 4070) d'un fichier audio/vidéo **que tu fournis** | ✅ Techniquement faisable sur cette machine ; installation requise. Rien ne sort de la machine. |
| Extraction structurée avec `gemma3:12b` en local, contrôlée par un validateur (chaque valeur doit exister mot pour mot dans la transcription) | ✅ Faisable avec l'abstraction LLM existante. |
| Récupération automatique depuis Discord avec ton compte | ❌ **Non recommandé** : automatiser un compte utilisateur Discord (« self-bot ») est interdit par les conditions de Discord et expose ton compte à un bannissement. Un bot officiel exige d'être ajouté par l'administrateur du serveur. |
| Téléchargement automatique d'une vidéo YouTube non répertoriée | ⚠️ Contraire aux conditions de YouTube ; à ne faire que si Lexa l'autorise explicitement. |

## 7. Blocages et risques

1. **Source des vidéos** : Discord. Pas de voie automatisée conforme sans l'accord de l'administrateur du serveur.
2. **Publication publique** : le dépôt et les snapshots sont publics. Exporter les analyses Lexa comme le reste reviendrait à **publier un contenu payant**. Les données Lexa doivent rester **locales** : jamais dans `app/assets/api_snapshots/`, jamais dans Git.
3. **App statique** : la version publiée ne peut pas porter la connexion Lexa. L'onglet Lexa doit fonctionner avec le **backend local** (build local), et être absent de la version publique.
4. Aucune protection DRM constatée à ce stade, mais le lecteur n'a pas pu être examiné (point 5).

## 8. Méthode d'intégration recommandée

**Import supervisé et local**, en attendant ta réponse sur la source exacte :

```
Tu fournis la vidéo, l'audio, ou la transcription (fichier ou copier-coller)
  → transcription locale avec horodatages (faster-whisper, GPU)
  → extraction structurée locale (gemma3:12b) + validateur « rien d'inventé »
  → SQLite local, analyses immuables par vidéo
  → onglet 🎬 Lexa servi par le backend local uniquement
```

Si tu confirmes un site web où les vidéos se lisent normalement dans le navigateur, on ajoute la connexion email + code par profil de navigateur dédié (point 4), après avoir constaté le lecteur sur une vidéo.

## 9. Fichiers à modifier et à créer

| Fichier | Rôle |
|---|---|
| `app/lib/main.dart` | 5ᵉ onglet 🎬 Lexa, affiché seulement si `LEXA_ENABLED=true` (build local) |
| `app/lib/lexa/` (nouveau) | modèles, client, pages Liste / Date / Fiche crypto / Paramètres |
| `backend/crypto_intel/lexa/` (nouveau) | `session.py`, `videos.py`, `transcripts.py`, `extraction.py`, `validation.py`, `levels.py`, `simulation.py`, `repository.py` |
| `backend/crypto_intel/db/base.py` | tables Lexa |
| `backend/crypto_intel/api/routes_lexa.py` (nouveau) + `main.py` | API locale |
| `scripts/export_flutter_static_api.py` | **exclusion explicite** de toute route Lexa |
| `.gitignore` | `data/lexa/` |

## 10. Nouvelles tables et classes

Session : **hors SQLite** (profil de navigateur dédié).

| Table | Contenu clé |
|---|---|
| `lexa_videos` | `id`, `source_video_id`, `title`, `published_at`, `duration_s`, `source_kind` (fichier / lien / transcription), `status`, `imported_at` |
| `lexa_transcripts` | `video_id`, `engine`, `language`, `processed_at`, `text` |
| `lexa_transcript_segments` | `transcript_id`, `start_s`, `end_s`, `text` |
| `lexa_analyses` | analyse **immuable** par vidéo : `video_id`, `published_at`, `processed_at`, `extractor_version` |
| `lexa_asset_analyses` | `analysis_id`, `asset`, `price_at_video`, `scenario_state` |
| `lexa_levels` | `asset_analysis_id`, `type`, `value`, `unit`, `allocation_pct`, `timestamp_s`, `source_text`, `confidence`, `condition` (UNKNOWN par défaut), `original_value`, `corrected_value`, `corrected_at` |
| `lexa_level_states` | `level_id`, `state`, `first_touched_at`, `last_touched_at`, `confirmed_at`, `invalidated_at` |
| `lexa_settings` | capital simulé par crypto (100 € par défaut) |

## 11. Plan précis du LOT 2 (sous réserve de ta réponse)

1. Tables ci-dessus + migration `init_db`, dans une base Lexa **séparée** (`data/lexa/lexa.db`, ignorée par Git), pour que rien ne puisse partir dans un export public.
2. Modèles Pydantic backend + modèles Dart correspondants.
3. Onglet 🎬 Lexa derrière le drapeau `LEXA_ENABLED` (absent du build public), avec la page principale vide « Aucune vidéo importée » et la page ⚙️ Paramètres (capital par crypto).
4. Route API `/api/lexa/*` servie uniquement par le backend local, et test qui **échoue** si une route Lexa apparaît dans la liste d'export.
5. Tests : immuabilité d'une analyse, recalcul proportionnel des allocations (100 → 200 → 500 €), valeur corrigée qui conserve l'originale, condition de confirmation `UNKNOWN` par défaut.
6. Compilation, tests complets, documentation, commit séparé.
