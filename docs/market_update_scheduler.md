# Ordonnancement et mises à jour

Mise à jour : 2026-10-30

## Autorité d'exécution

Le scheduler est serveur. Il ne dépend pas de l'ouverture de Flutter. `crypto-intel.service` maintient FastAPI et APScheduler; `SCHEDULER_ENABLED=true` est le défaut du modèle de configuration et de `.env.example`. `MOCK_MODE=true` ne doit pas lancer la planification de production.

La présence des fichiers sous `deploy/` ne prouve pas que les unités sont installées, activées ou persistantes après déconnexion.

## Cadences APScheduler codées

| Job | Cadence |
|---|---:|
| ticker marché | 5 min |
| analyse complète par actif | 30 min |
| historique de décision | 30 min |
| OHLCV 15m/1h/4h/1d/1w | 60 min |
| funding, OI, ratios, DVOL | 60 min |
| expériences patterns | 60 min |
| évaluation des résultats | 60 min |
| ETF | 240 min |
| événements futurs | 360 min |
| surveillance Lexa | 5 min |
| surveillance des publications macro | 15 min |
| purge | 24 h |
| cycle serveur 13 étapes, dont radar S01–S15 | 00:00, 03:00, 06:00, 09:00, 12:00, 15:00, 18:00, 21:00 UTC |

Au démarrage, les premiers runs sont décalés : ticker, OHLCV, dérivés et sources globales précèdent la première analyse.

## Surveillance événementielle

Toutes les 15 minutes, `macro_watch` recherche dans la table des événements une publication majeure Fed/CPI/PCE/emploi/BCE/BoJ tombée dans les 90 dernières minutes. S'il en trouve une, il relance le classement macro sans attendre le prochain créneau de trois heures.

Ce mécanisme s'appuie sur un événement déjà collecté; ce n'est pas un webhook temps réel de l'institution.

## Robustesse implémentée

- `max_instances=1` empêche l'empilement du même job dans un seul scheduler;
- `coalesce=true` ramène un retard à une exécution;
- `misfire_grace_time=300` tolère un réveil tardif limité;
- les exceptions sont isolées par job et visibles dans l'état du scheduler;
- les identifiants/buckets rendent les écritures répétées idempotentes;
- le rapport `server_cycle_3h` persiste l'état du workflow et de chaque étape avant et après exécution;
- `/api/scheduler/status` expose le dernier rapport durable sous `three_hour_cycle`, sans le convertir en succès si son statut est dégradé ou en échec;
- les logs structurés marquent le début et la fin de chaque étape;
- une reprise dans le même bucket conserve les prérequis réussis, recommence au premier état non réussi et invalide le suffixe dépendant;
- un bucket déjà `SUCCESS` est relu sans nouvel appel externe; un `DEGRADED` ou `FAILED` n'est jamais annoncé comme succès;
- le client HTTP gère rate limiting, cache et retries;
- la politique de source ajoute backoff exponentiel, jitter et circuit breaker;
- les valeurs mensuelles gardent leur observation et leur publication;
- l'export statique utilise un staging et une promotion atomique.

`max_instances=1` est local au scheduler. Le runner ajoute un verrou asynchrone commun à ses instances dans le processus puis un `flock` non bloquant `data/.three_hour_cycle.lock` entre processus du même hôte. Les services de refresh systemd partagent, eux, `data/.refresh.lock`; les notifications Lexa protègent leur déduplication par transaction SQLite immédiate.

## systemd et snapshots

| Unité | Fonction |
|---|---|
| `crypto-intel.service` | API et APScheduler long-lived |
| `crypto-intel-light.timer` | passe légère toutes les 15 min |
| `crypto-intel-refresh.timer` | collecte/analyse/export à 07:00 et 19:00 locales |
| `crypto-intel-bybit-stream.service` | flux Bybit long-lived |

La passe complète construit collecte, analyse, snapshot de cycle, export Flutter et santé sous verrou. Un export incomplet ne remplace pas le précédent.

## Horodatages distincts

- exécution : quand le job a tourné;
- récupération : quand le provider a répondu;
- observation : période ou séance décrite;
- publication/disponibilité : premier instant utilisable;
- génération : quand le rapport a été construit.

Une exécution réussie sans publication nouvelle ne transforme pas une statistique mensuelle en nouvelle donnée.

## Cycle durable de trois heures

`macro_cycle` exécute les treize étapes dans l'ordre contractuel :

1. lire les dernières données disponibles;
2. planifier les sources échues en respectant les limites fournisseur;
3. collecter les nouvelles publications admissibles;
4. détecter les révisions;
5. recalculer les indicateurs concernés;
6. évaluer les événements encore actifs;
7. comparer le diagnostic précédent;
8. reclasser les signaux S01–S15;
9. réévaluer les scénarios;
10. réévaluer l'état des actifs;
11. produire une analyse seulement si les entrées ont changé ou si le rapport a vieilli;
12. enregistrer le rapport de cycle et le radar;
13. déclencher uniquement les notifications admises par leurs cooldowns.

`cycle_id` identifie le bucket UTC de trois heures. Le runner refuse toute liste qui ne contient pas exactement les étapes 1 à 13 et se sérialise par verrou asynchrone puis fichier sur l'hôte. Chaque étape expose `PENDING`, `RUNNING`, `SUCCESS`, `DEGRADED` ou `FAILED`, ses tentatives, heures, détail, données et erreurs. Le rapport conserve aussi l'historique des échecs et l'heure du dernier succès; un contrat persisté mal formé redémarre les étapes au lieu d'être promu à tort.

Limites : le `flock` ne devient pas un lease distribué multi-hôte. Les snapshots statiques publics sont toujours promus par la passe de publication existante; le cycle met à jour la base et les rapports servis par l'API, mais ne prétend pas qu'un appareil hors ligne a déjà reçu le nouvel export. L'activation réelle après redémarrage demeure une recette d'hôte.

## Installation et contrôles

```bash
mkdir -p ~/.config/systemd/user
cp deploy/crypto-intel.service deploy/crypto-intel-light.service \
  deploy/crypto-intel-light.timer deploy/crypto-intel-refresh.service \
  deploy/crypto-intel-refresh.timer ~/.config/systemd/user/
systemctl --user daemon-reload
systemctl --user enable --now crypto-intel.service crypto-intel-light.timer \
  crypto-intel-refresh.timer
```

Contrôler ensuite :

```bash
systemctl --user status crypto-intel.service crypto-intel-light.timer \
  crypto-intel-refresh.timer
journalctl --user -u crypto-intel.service -u crypto-intel-refresh.service
```

`loginctl enable-linger <utilisateur>` est nécessaire si le service doit survivre à la déconnexion; c'est une action d'administration à autoriser explicitement. Aucune recette hôte après redémarrage n'a été consignée dans ce lot.
