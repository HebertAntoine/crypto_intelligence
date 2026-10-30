# Alertes et notifications

Mise à jour : 2026-10-30

## Deux domaines conservés

- `AlertEngine` gère les alertes générales de marché dans la base principale.
- Le notifier Lexa gère les plans et niveaux privés dans la base Lexa.

Ils ne sont pas fusionnés : leurs données, confidentialité et cycles de vie diffèrent.

## Notifications Lexa

`lexa_watch` évalue toutes les cinq minutes les plans `ACTIVE`, `WATCHING` ou `TRIGGERED`. Les types actuellement produits sont :

- `APPROACH`;
- `TOUCHED`;
- `CLOSE_SOON`;
- `CLOSED_BEYOND`;
- `CONFIRMATION_MISSING`;
- `CONFIRMED`;
- `TARGET`;
- `PLAN_UPDATED`;
- `INVALIDATED`;
- `EXPIRED` est défini dans les politiques, mais le générateur actuel ne l'ajoute pas explicitement dans `candidates()`.

## Anti-spam et concurrence

- clé de déduplication par actif, règle, niveau et, pour les clôtures, timestamp de bougie;
- cooldown par type;
- plafond de huit notifications par actif sur 24 heures;
- tri par priorité;
- aucun déclenchement rétroactif antérieur à l'ajout de l'analyse;
- transaction SQLite `BEGIN IMMEDIATE` autour du test de cooldown, du plafond et de l'insertion.

Cette transaction empêche deux workers locaux de persister simultanément la même alerte. Elle ne constitue pas un verrou distribué multi-base pour plusieurs hôtes.

## Reçu et preuve Lexa

Le listing expose : `notification_id`, `trigger_id`, `asset_id`, `analysis_id`, `created_at`, `delivered_at`, `delivery_status`, `reason`, `source_snapshot` et `read`.

Le snapshot contient le déclencheur, le type, l'actif, l'analyse, l'heure d'évaluation, le prix/source, puis, si applicable, le niveau, ses bornes, unité, distance et état. Pour une condition, il ajoute type, timeframe, opérateur, nombre de clôtures, statut d'évaluation et heure de l'événement.

Le sink in-app n'écrit `DELIVERED` qu'après insertion dans la boîte Lexa. Cela signifie « persisté dans l'application », pas « affiché par iOS » ni « lu par l'utilisateur ». `read_at` suit la lecture séparément.

## Interface

`LexaNotificationsScreen`, accessible depuis l'historique Lexa, affiche :

- nombre de non-lues;
- actif et type;
- message, heure locale et déclencheur;
- statut de remise et motif;
- chargement, erreur/réessai, état vide et pull-to-refresh;
- action « Tout marquer comme lu ».

Le snapshot de preuve est disponible dans l'API mais n'est pas déplié champ par champ dans l'écran actuel.

## Alertes générales

`AlertEngine` couvre notamment flux ETF, funding, open interest, breakout, divergence RSI, réglementation, FOMC/CPI, baleines, liquidité stablecoin, contradictions et changement de régime. Les alertes ont preuves et importance.

La persistance générale produit maintenant un reçu distinct mais de même forme traçable : `notification_id`, `trigger_id`, `asset_id`, `analysis_id`, `created_at`, `delivered_at`, `delivery_status`, `reason` et `source_snapshot`. `trigger_id` identifie la condition et `notification_id` l'occurrence exacte. Une reprise du même payload garde le même identifiant; une occurrence ultérieure après cooldown en reçoit un nouveau.

`save_alerts` ouvre une transaction SQLite immédiate, revérifie le cooldown sous verrou d'écriture, déduplique les retries exacts et n'accepte le reçu qu'avec l'alerte. Un lot contenant une ligne invalide est annulé atomiquement. Le statut général est `STORED` : il signifie que la boîte in-app a accepté la ligne, jamais qu'un canal externe l'a envoyée. Les anciennes lignes sont exposées avec un identifiant stable `legacy-alert-*` et un statut `UNKNOWN`, sans reconstruire des faits absents.

L'API `/alerts` expose le contrat complet. La vue globale React affiche importance, actif, titre/détail, motif, `notification_id`, `analysis_id`, statut, heure de remise et création. Le `source_snapshot` reste disponible dans l'API mais n'est pas déplié champ par champ dans la table. Les boîtes Lexa et générale restent séparées et il n'existe pas d'écran commun multi-domaine.

## Canaux non implémentés

- push iOS/Android;
- e-mail, SMS ou messagerie;
- accusé d'un fournisseur tiers;
- consentement et préférences par compte;
- retries, dead-letter queue et historique des tentatives externes.

Un canal externe devra persister chaque tentative et n'écrire `DELIVERED` qu'après acceptation explicite du fournisseur. Ni `STORED` général ni `DELIVERED` Lexa ne doivent être recyclés comme accusé d'un fournisseur push.

## Confidentialité

Les notifications Lexa restent dans la base privée et ne sont jamais exportées vers les snapshots publics. Les routes Lexa sont limitées au local/Tailscale; cette restriction ne remplace pas une authentification de compte pour un déploiement Internet.
