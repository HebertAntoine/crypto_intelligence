# D'où viennent réellement les données, aujourd'hui

Question posée : pourquoi le téléphone affiche-t-il un prix « en direct » alors
que le backend n'est pas déployé ? Réponse tracée dans le code, pas supposée.

## Les trois chemins actuels

```
                          ┌─ WebSocket Kraken ──────────► prix, toutes les 0,5 s
                          │   (appel direct depuis Flutter)
  Téléphone ── Vercel ────┤
   (Flutter web)          ├─ assets embarqués ──────────► analyse complète, figée
                          │   (api_snapshots/*.json)      à l'export
                          │
                          └─ /api/... même origine ─────► 404 : Vercel ne sert
                              (tenté seulement si            aucun backend
                               API_BASE_URL non vide)
```

**Le prix** vient de `app/lib/live_prices/live_price_service.dart`, qui ouvre
`wss://ws.kraken.com/v2` et souscrit à BTC/EUR, ETH/EUR, SOL/EUR. C'est un
appel direct au provider, sans passer par notre API. Il fonctionne parce qu'il
ne dépend d'aucun backend.

**L'analyse** vient des instantanés embarqués dans le bundle Flutter. Le client
les lit *avant* toute requête réseau lorsque `API_BASE_URL` est vide, ce qui est
le cas sur Vercel : `_useStaticSnapshotFirst = baseUrl.isEmpty`. Aucun appel
HTTP n'est tenté.

**Le backend** n'est joignable de nulle part. Il écoute sur `127.0.0.1:8100`,
en loopback. `docs/deployment.md` explique pourquoi il ne peut pas tourner sur
Vercel : il lui faut un disque et un processus long.

## Ce que cela implique

Le prix bouge en continu, l'analyse est figée à l'export. Les deux sont vrais,
et c'est précisément la contradiction que la page affichait. Elle est désormais
énoncée : « Prix en direct · analyse calculée à 20:19 », plus la dérive entre le
prix d'analyse et le prix courant.

## L'appel direct à Kraken : à conserver ou à migrer ?

L'architecture visée est `Flutter → notre API → providers`. L'appel direct la
contredit. Il a toutefois une justification défendable, écrite dans le fichier :
un WebSocket public fournit trois paires sans que l'app interroge notre HTTP
toutes les demi-secondes.

Trois observations honnêtes :

- c'est **un seul** provider, en lecture seule, sur un endpoint public, sans clé
  ni secret. Ce n'est pas « quinze providers appelés depuis le front ».
- il ne contourne aucune limitation et ne dépend d'aucune authentification.
- il rend l'app utilisable sans backend, ce qui est aujourd'hui le seul mode
  de fonctionnement réel.

Recommandation : le garder tant que le backend n'est pas déployé, et le migrer
derrière l'API ensuite — un flux serveur permet d'agréger plusieurs venues et
d'appliquer la même médiane que `market_price_snapshot`, ce que le client ne
fait pas. Aucun autre appel direct n'existe : la recherche dans `app/lib`
ne trouve que celui-ci.

## Le prix affiché n'est pas celui de l'analyse

`market_price_snapshot` calcule une médiane sur Binance, Coinbase et Kraken,
avec la paire EUR directe de Coinbase. Le flux Kraken du téléphone est une
source unique. Les deux coexistent :

- la carte affiche le flux Kraken, étiqueté « LIVE · Kraken » ;
- l'analyse repose sur `price_at_analysis`, issu de la dernière bougie 4H ;
- l'écart entre les deux est calculé et affiché au-delà de 1,5 %.

## Options de déploiement du backend

Aucune n'est appliquée : cela demande une décision d'hébergement.

| Option | Pour | Contre |
| --- | --- | --- |
| VPS public + TLS | contrôle complet, scheduler et SQLite fonctionnent | à administrer et à sécuriser soi-même |
| Tunnel Cloudflare vers la machine Debian | pas d'ouverture de port entrant, TLS fourni, une infra du même type existe déjà chez toi | la machine doit rester allumée |
| Railway / Render / Fly.io | déploiement direct d'une image FastAPI, TLS inclus | disque persistant à configurer, coût mensuel |
| Vercel serverless | déjà en place pour le front | incompatible : pas de processus long, pas de disque |

**Recommandée : le tunnel.** Elle n'expose aucun port entrant, fournit TLS, et
une architecture comparable tourne déjà sur cette machine. Il resterait à
définir `CORS_ORIGINS` sur l'URL Vercel et `API_BASE_URL` côté build.

Rien n'a été déployé. Ouvrir la machine Debian sur Internet est une décision
qui t'appartient, et je ne la prends pas sans que tu la valides.

## En attendant : les instantanés

Tant que le backend n'est pas joignable, la fraîcheur de l'app dépend
entièrement de la fréquence des exports. Le script existe :

```
python scripts/export_flutter_static_api.py --base-url http://127.0.0.1:8100
```

Il faut le lancer avec le backend local en marche, puis committer et laisser
Vercel reconstruire. Ce n'est pas automatisé, et tant que ça ne l'est pas, un
instantané peut vieillir sans que personne s'en aperçoive — sauf que la page le
dit maintenant, ce qui est déjà le minimum.
