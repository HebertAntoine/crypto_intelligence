# Architecture Market Intelligence

Mise à jour : 2026-10-30

## Principe

L'intégration étend l'application existante. Elle ne crée ni seconde application ni second moteur de décision. Les fournisseurs collectent, les moteurs calculent, les analystes agrègent, et le LLM ne peut que reformuler des conclusions structurées.

Le schéma suivant décrit les branchements réels, y compris les deux chemins qui restent encore parallèles :

```text
Sources autorisées / fichiers privés
                 |
                 v
          ProviderRegistry
                 |
                 v
 Observation / OHLCV / FutureEvent -----> SQLite + historique point-in-time
                 |                                      |
        +--------+---------+                            +------------------+
        |                  |                                               |
        v                  v                                               v
 pipeline principal   PointInTimeView                               preuves stockées
        |                  |                                               |
        v                  v                                               |
 moteurs + cinq       radar S01-S15 -----> API macro / Flutter / historique|
 familles future-first                                                   |
        |                                                                  |
        v                                                                  |
 analystes -> Chief -> scénarios -> décision/rapport                     |
                                                                           |
 texte/transcription -> extraction -> fact-check déterministe <-----------+
                                      |
                                      +--> rapports/imports Lexa
                                      +--> endpoint explicite
```

Limites structurantes : le radar S01–S15 n'est pas encore injecté comme objet dans le Chief; le fact-check ne filtre pas automatiquement tous les RSS/articles du pipeline principal.

## Frontières d'autorité

| Couche | Autorisée | Interdite |
|---|---|---|
| Provider | Récupérer, parser, dater, attribuer | Déduire une décision ou masquer une absence |
| Validation | Contrôler unité, temps, licence, nulls et conflits | Transformer une valeur absente en zéro |
| Moteur quantitatif | Calculer variation, percentile, état et preuves | Inventer observation, consensus ou causalité |
| Moteur événementiel | Gérer statut, importance, expiration et surprise | Présenter une proposition comme une décision adoptée |
| Fact-check | Résoudre entité/période, recalculer, classifier | Employer une preuve postérieure à la date limite |
| Analystes/Chief | Agréger conclusions et contradictions | Utiliser du texte non vérifié comme mesure financière |
| Décision | Appliquer gates et états observables | Déléguer l'état au LLM |
| LLM | Expliquer un contexte structuré | Créer chiffres, niveaux, probabilités ou scénarios autoritatifs |
| UI | Afficher dates, qualité, provenance et limites | Recalculer une décision financière |

## Contrats de données réels

### Observation générique

`Observation` contient un identifiant déterministe, actif, métrique, valeur originale, unité, timestamp UTC, provenance, fraîcheur, confiance, qualité, timeframe et `meta`.

Le contrat minimal demandé dans le cahier des charges n'est pas encore un schéma uniforme : `currency`, `frequency`, `publication_time`, `retrieved_at`, `revision_number`, `vintage_time`, `market_calendar`, `timezone`, `license_status`, `validation_status` et `quality_flags` sont portés par certains providers dans `meta`, mais pas par tous. Il ne faut donc pas présenter l'uniformisation comme achevée.

### Historique macro point-in-time

`MacroSeriesRow` ajoute provider, unité, URL source, identifiant de série, licence, métadonnées, publication/disponibilité, ingestion et version. `MacroVintageRow` conserve pour chaque version sa valeur et sa propre provenance : source, provider, unité, URL, licence, métadonnées, publication, disponibilité et ingestion. Une modification de provider ou de droits crée une frontière de version même lorsque la valeur ne change pas. La vue `PointInTimeView(as_of)` ne garde que la dernière version connue à l'instant demandé et réévalue les droits des lignes conservées.

Une publication absente reste absente. Pour une ancienne ligne sans publication, l'ingestion peut servir de disponibilité de repli; une observation macro ancienne sans publication ni ingestion exploitable est exclue plutôt que supposée connue.

### Bougies

Le stockage peut conserver et mettre à jour la barre en formation. `load_candles`, `candle_metadata` et les vues point-in-time calculent toutefois la clôture théorique de M15, H1, H4, D1 et W1 et excluent la barre tant que cet instant n'est pas atteint. Un `end` historique devient l'instant de visibilité lorsqu'aucun `as_of` explicite n'est fourni.

### Événement

`FutureEvent` sépare source, détection, publication, horaire planifié, statut, expiration, consensus, résultat, surprise, direction, horizon, confiance et preuves. Une probabilité de marché exige sa source et son timestamp. Une source sociale reste une piste de rang faible.

### Signal S01–S15

Chaque `Reading` sérialise identité, géographie, actifs, valeur courante/précédente, delta, métrique primaire, fenêtre, historique compact, percentile, observation, publication, prochaine échéance, source/URL, qualité, attention, direction, score, explication et invalidations. Les champs inconnus restent nuls ou `SOURCE_UNAVAILABLE`.

### Risque global

`GET /api/future/{symbol}/global-risk` expose trois fenêtres non chevauchantes `1-7d`, `8-30d` et `31-90d` avec niveau, instant, couverture, facteurs, contre-signaux, évolution, preuves et invalidations. Le moteur réutilise les cinq familles et les événements autorisés; une famille ne compte dans le seuil que si elle possède amplitude, provenance et fraîcheur utilisables. Il ne crée ni score directionnel ni probabilité. Faute de projection des cinq familles au-delà de 30 jours, le niveau long terme reste `INDETERMINATE`, tout en listant les événements 31–90 jours réellement disponibles et leurs actifs affectés.

### Affirmation

`Claim` porte texte original/normalisé, type, entités, valeur, unité, période, causalité, instant source, preuves, valeur recalculée, méthode, statut, confiance et notes. Les huit statuts sont `CONFIRMED`, `PARTIALLY_CONFIRMED`, `CONTRADICTED`, `UNVERIFIABLE`, `AMBIGUOUS`, `OUTDATED`, `OPINION` et `FORECAST`.

## Chemins analytiques

### Pipeline principal

```text
collecte par capacité
→ persistance
→ moteurs macro/crypto/technique/flux/événements
→ analystes spécialisés
→ conviction + contradictions + régime/timing
→ Chief et trois scénarios déterministes
→ décision, rapport, alertes et historique
```

### Radar S01–S15

```text
PointInTimeView(as_of)
→ quinze lecteurs exacts
→ enrichissement du contrat et qualité
→ score d'attention explicable, distinct de la direction
→ contrôle par groupe d'indépendance
→ top cinq + catalogue complet
→ API, Flutter et snapshot de cycle
```

Les événements géopolitiques, réglementaires et crypto-native restent dans leurs modules dédiés; ils ne sont pas renommés en S01–S15.

### Fact-check et Lexa

```text
transcription / texte fourni
→ extraction conservatrice
→ modalité, entité, période et mesure
→ preuves stockées connues à min(source_timestamp, as_of)
→ variation close-to-close ou drawdown de période
→ statut + confiance + preuves
→ rapport de test puis import Lexa validé
```

Les niveaux de prix Lexa sont vérifiés par le validateur de plan, pas promus en faits de marché. Les fact-checks de portée `MARCHÉ` sont conservés avec chaque actif importé. Une affirmation contradictoire est visible, mais le chemin général qui empêcherait tout RSS contradictoire d'atteindre le Chief n'existe pas encore.

## Droits au moment de la lecture

Le chemin `macro.indices` n'utilise que Twelve Data et exige une clé ainsi que le drapeau explicite de droits. CoinGecko et son calcul de breadth exigent une clé Pro, le droit commercial et l'attribution configurée. Tous les contenus FRED exigent `FRED_CONTENT_USE_AUTHORIZED`; une série ICE BofA/Cboe exige en plus le droit tiers. Yahoo/Stooq restent des adaptateurs legacy hors chaîne. Ces politiques sont réévaluées lors de chaque lecture du cache : désactiver un droit empêche une ancienne ligne de continuer à influencer l'analyse.

## Orchestration et cohérence

APScheduler tourne dans le backend durable. `max_instances=1`, `coalesce`, les backoffs et les identifiants déterministes limitent les doublons. Les passes systemd partagent un verrou et l'export public utilise un staging atomique.

Le job de trois heures exécute désormais les treize étapes ordonnées du cahier des charges. Son `cycle_id` est l'identité stable du bucket UTC; l'état du workflow et de chaque étape est persisté avant/après exécution et exposé par `/api/scheduler/status`. Une reprise recommence au premier état non réussi et recalcule le suffixe dépendant; un bucket déjà réussi est idempotent. Un état `DEGRADED` ou `FAILED` n'est jamais publié comme succès.

Le runner partage un verrou asynchrone entre ses instances dans le processus et un `flock` non bloquant entre processus du même hôte. Le rapport durable rend le bucket idempotent, mais ne constitue pas un lease distribué entre plusieurs hôtes. L'export statique Flutter reste géré par la passe de publication existante; le cycle serveur met à jour les données et rapports que l'API sert, sans prétendre qu'un client hors ligne a déjà téléchargé le nouvel export.

## Sécurité et déploiement

Les secrets restent côté serveur et Lexa reste hors des exports publics. Les routes Lexa sont limitées au local/Tailscale, mais l'API générale n'a pas d'authentification applicative. Avant toute exposition Internet : reverse proxy HTTPS authentifié, autorisation des routes mutables, sauvegardes chiffrées, rétention et logs expurgés sont requis.

FastAPI/SQLite/APScheduler exigent un processus durable et un disque persistant. Flutter peut être statique; le backend ne doit pas être traité comme une fonction serverless éphémère.
