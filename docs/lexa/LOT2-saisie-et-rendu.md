# Intégration Lexa — LOT 2 : saisie, rendu, suivi et simulation

## 1. Ce qui a été constaté après le LOT 1

- La plateforme vidéo réelle est « LexaMoon » : `lexa-predicts.fr/service-video/gateway/`.
- La connexion se fait sans mot de passe, avec un code à usage unique envoyé par e-mail. Le formulaire POST `/service-video/gateway/auth/login` porte les champs `_csrf` et `email`, et le site garde une session serveur.
- Le lecteur, le format (HLS ou autre), les DRM et les sous-titres **n'ont pas été vérifiés** : `public/js/app.js` ne les montre pas.
- Les CGV (`/service-video/gateway/cgv`) réservent le service à un **usage privé et personnel**. Elles interdisent :
  - toute copie, reproduction, redistribution ou diffusion du contenu ;
  - le partage d'accès ;
  - le contournement des mesures techniques de protection.

  Une infraction entraîne la résiliation sans remboursement.

## 2. Décision

Aucun enregistrement ni aucune transcription automatique des vidéos n'est construit **sans l'accord écrit de Lexa**. Télécharger le flux pour le transcrire, c'est le reproduire, et les CGV l'interdisent.

On retient donc cette méthode : le membre regarde la vidéo sur la plateforme officielle et note les niveaux annoncés, ce qui prend quelques secondes par crypto. L'application fait tout le reste :

- classement par date et par crypto ;
- suivi des niveaux ;
- simulation ;
- historique ;
- comparaison avec nos données.

Si Lexa donne son accord, un service de transcription pourra s'ajouter en amont sans rien changer à la suite (voir le brouillon au §6).

## 3. Confidentialité

Le contenu vient d'un abonnement personnel. Il ne doit jamais quitter la machine :

| Garantie | Où |
|---|---|
| Base séparée `data/lexa/lexa.db`, répertoire en 0700, ignorée par Git | `backend/crypto_intel/lexa/store.py`, `.gitignore` |
| Routes `/api/lexa/*` en 403 pour tout client non loopback | `backend/crypto_intel/api/routes_lexa.py` |
| Export statique qui refuse tout chemin `/lexa` | `scripts/export_flutter_static_api.py` (`assert_exportable`) |
| Onglet 🎬 Lexa absent de la build publique | `LEXA_ENABLED` (dart-define), testé |
| Aucun identifiant, OTP, cookie ni jeton stocké | aucune connexion automatique à Lexa n'existe |

## 4. Règles métier

- Une analyse Lexa est une **source externe**. Elle ne modifie jamais BUY / WAIT / SELL, ni les scores, ni les moteurs. La comparaison 🔍 affiche les deux lectures côte à côte.
- Une vidéo est immuable : une nouvelle vidéo est un nouveau scénario, et l'historique les garde tous.
- Une correction garde la valeur d'origine (`original_value`, `corrected_value`, `corrected_at`).
- Une valeur incertaine est marquée « ⚠️ À vérifier » (confiance LOW).
- Une condition de confirmation qui n'est pas dite dans la vidéo reste `UNKNOWN`. Un niveau touché sans condition ne passe **jamais** à 🚀 Confirmé.
- Les états possibles sont :
  - ⚪ Non surveillé (pas de prix) ;
  - ⏳ Non atteint ;
  - 🟢 Touché ;
  - 🚀 Confirmé (condition constatée sur bougies closes) ;
  - ⚠️ Testé puis reperdu ;
  - ⚠️ Invalidé ;
  - 🔴 Objectif atteint.
- Prix :
  - BTC, ETH et SOL viennent des bougies 1 h déjà stockées ;
  - les autres actifs viennent des klines publiques Binance `{ACTIF}USDT` (bougies closes uniquement) ;
  - sans prix, rien n'est inventé.
- Simulation :
  - le capital est réglable, 100 € par défaut, globalement ou par crypto ;
  - les allocations sont proportionnelles et les niveaux ne bougent pas ;
  - une allocation manquante est répartie à parts égales, et cette hypothèse est affichée ;
  - l'invalidation est signalée mais ne déclenche aucune vente ;
  - le change €/$ est supposé constant.

## 5. Utilisation

```bash
# Backend local (écoute sur 127.0.0.1 seulement)
PYTHONPATH=backend .venv/bin/python -m uvicorn crypto_intel.main:app --host 127.0.0.1 --port 8100

# Application avec l'onglet Lexa
cd app && ~/flutter/bin/flutter run -d chrome \
  --dart-define=LEXA_ENABLED=true --dart-define=API_BASE_URL=http://127.0.0.1:8100
```

Dans l'onglet 🎬 Lexa, ➕ ajoute une vidéo : titre, date, puis pour chaque crypto le prix dans la vidéo, la position et les niveaux (type, prix, % du capital ou % vendu, minutage `18:42`, condition, phrase de la vidéo). ⚙️ règle le capital.

## 6. Brouillon de demande à Lexa

> Objet : Transcription personnelle des vidéos LexaMoon
>
> Bonjour,
>
> Je suis abonné à LexaMoon. Pour mon usage strictement personnel, j'aimerais transcrire automatiquement les vidéos auxquelles mon abonnement donne accès, afin de retrouver les niveaux cités (zones, confirmations, objectifs) et de les suivre dans un outil privé qui tourne uniquement sur mon ordinateur.
>
> Rien ne serait partagé, publié ou redistribué, et les vidéos ne seraient pas conservées après transcription. Vos CGV interdisant la reproduction du contenu, je préfère vous demander votre accord écrit avant de le faire. Proposez-vous également un export texte, des sous-titres ou un résumé écrit des niveaux, qui éviterait toute transcription ?
>
> Merci d'avance,
