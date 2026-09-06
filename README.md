# Crypto Intelligence

Outil **personnel** d'analyse des marchés crypto — Bitcoin, Ethereum, Solana.

> Ce n'est pas une plateforme publique. Ce n'est pas un bot de trading.
> **Aucun ordre n'est jamais passé.** Le système collecte, structure, calcule,
> analyse et *explique* — la décision reste entièrement la tienne.

---

## Tendance et timing sont deux questions distinctes

C'est l'apport central de la V2 :

```
ETH
Market regime : STRONGLY_BULLISH     ← dans quel sens penche le marché ?
Entry timing  : WAIT                 ← est-ce un bon moment maintenant ?

→ tendance daily haussière, flux ETF positifs,
  mais RSI 1H élevé, prix à +5 % de son EMA20, résistance proche.
```

Les deux moteurs sont indépendants et entièrement déterministes (aucun LLM).
Détail dans [docs/regime-vs-timing.md](docs/regime-vs-timing.md).

## Le principe

Le pipeline est strictement ordonné, et chaque étage est indépendant du suivant :

```
DONNÉES BRUTES → normalisation → indicateurs → événements → analyse spécialisée
   → comparaison historique → agrégation → analyse IA → rapport argumenté
```

Le LLM n'intervient qu'à l'avant-dernière étape, sur une structure déjà calculée
et sourcée. **Il ne peut jamais inventer une donnée manquante** : trois garde-fous
le vérifient, dont un qui confronte chaque nombre cité aux valeurs réellement
fournies.

Quatre niveaux ne sont jamais confondus :

| Niveau | Exemple |
|---|---|
| **FAIT** | `BTC ETF net flow = +730.8 M$` (Farside, 2026-09-03) |
| **CALCUL** | moyenne 5 jours = +122.0 M$, accélération +132 % |
| **INTERPRÉTATION** | demande institutionnelle actuellement favorable |
| **HYPOTHÈSE** | peut soutenir le prix si les autres facteurs restent favorables |

Chaque conclusion remonte à ses preuves : le bouton **WHY ?** de l'interface
affiche la source, la valeur d'origine, l'horodatage et la fraîcheur.

---

## Installation

Prérequis : **Python ≥ 3.11**. Node.js est nécessaire uniquement pour le frontend.

```bash
cd crypto_intelligence
make install          # venv + dépendances Python + frontend + base de données
cp .env.example .env  # puis renseigne les clés que tu veux (toutes optionnelles)
```

Si Node.js n'est pas installé sur la machine, il peut l'être localement sans droits root :

```bash
mkdir -p ~/.local/opt && cd ~/.local/opt
curl -sL https://nodejs.org/dist/v22.14.0/node-v22.14.0-linux-x64.tar.xz | tar -xJ
mv node-v22.14.0-linux-x64 node22
```

Le `Makefile` détecte automatiquement `~/.local/opt/node22`.

---

## Lancement

```bash
make backfill   # une fois : importe ~9 ans d'historique (idempotent)
make serve      # API      → http://127.0.0.1:8100   (doc: /docs)
make frontend   # Interface → http://localhost:5273
```

Puis, pour que le système construise sa propre mémoire de marché :

```bash
make scheduler  # collecte périodique + snapshots + évaluation
```

Ou entièrement hors ligne, sans aucune clé :

```bash
make mock       # MOCK_MODE=true, tout tourne sur fixtures/
```

---

## Déploiement web

L'application se déploie en **une seule image** : le frontend React est
compilé puis servi par FastAPI, sur la même origine que l'API. Une seule
origine signifie aucune configuration CORS en production et aucun serveur web
supplémentaire à administrer.

```bash
docker compose up -d --build
# → http://localhost:8100    (UI + API + /docs)
```

Ou sans compose :

```bash
docker build -t crypto-intelligence .
docker run -d -p 127.0.0.1:8100:8100 \
  -v crypto-data:/app/data \
  --env-file .env \
  crypto-intelligence
```

### Ce qu'il faut savoir avant d'exposer le service

- **Il n'y a aucune authentification.** Le port est volontairement publié sur
  `127.0.0.1` dans `docker-compose.yml`. Mets un reverse proxy avec auth
  devant avant de l'ouvrir sur un réseau.
- **Monte un volume sur `/app/data`.** Sans lui, chaque reconstruction repart
  d'une base vide : historique, résultats de recherche et cache structurel
  disparaissent.
- **Aucune clé n'est nécessaire pour démarrer.** Chaque provider non configuré
  répond `UNAVAILABLE` explicitement plutôt que d'inventer une valeur. Copie
  `.env.example` vers `.env` pour activer ce que tu as.
- **Le scheduler est désactivé par défaut** (`SCHEDULER_ENABLED=false`), pour
  qu'un premier lancement ne déclenche rien d'inattendu.

### Premier remplissage

Le conteneur démarre avec une base vide. Pour importer l'historique :

```bash
docker compose exec app crypto-intel backfill
docker compose exec app crypto-intel research-structural
```

### Vérification

```bash
curl http://localhost:8100/api/health
```

L'image est vérifiée en CI : build, démarrage, `/api/health`, et le fait que
le SPA soit bien servi sur la même origine.

---

## Commandes

| Commande | Effet |
|---|---|
| `make serve` | lance l'API |
| `make frontend` | lance l'interface |
| `make mock` | API en mode hors-ligne complet |
| `make collect` | collecte et stocke les données (`ASSET=BTC` pour cibler) |
| `make analyze` | analyse complète en console |
| `make report` | rapport texte (`ASSET=ETH OUT=rapport.txt`) |
| `make ingest` | ingère tes cours depuis `knowledge/` |
| `make import-etf` | importe des flux ETF (`FILE=data/imports/etf/x.csv`) |
| `make evaluate` | confronte les rapports passés aux prix réellement observés |
| `make backfill` | importe l'historique (idempotent, `ASSET=` `TF=` `DAYS=`) |
| `make research` | études ETF, event studies, calibration des scores |
| `make daily` | rapport quotidien global (`OUT=daily.txt`) |
| `make scheduler` | collecte périodique + snapshots |
| `make coverage` | profondeur historique réellement disponible |
| `make audit` | verdict mesuré de chaque score, par actif |
| `make research-export` | études + export CSV / JSON / Markdown |
| `make import-oi` | import d'historique d'open interest |
| `make providers` | état de chaque source de données |
| `make test` | tests (hors ligne, sans clé) |
| `make check` | lint + tests + typecheck |
| `make stop` | arrête le backend |

---

## Configuration

Tout est externalisé — **aucun poids n'est codé en dur**.

```
config/
├── assets.yaml           actifs, seuils "whale", métriques on-chain par blockchain
├── scoring.yaml          pondérations par actif ET par horizon
├── thresholds.yaml       seuils d'interprétation (RSI, funding, ETF, fraîcheur…)
├── providers.yaml        chaînes de fallback des sources, flux RSS
└── macro_calendar.yaml   calendrier FOMC / CPI / NFP / PCE
```

Les pondérations **diffèrent volontairement d'un actif à l'autre** :

```yaml
BTC:  etf: 0.24   macro: 0.14   technical: 0.18   # dominé par les flux ETF
ETH:  etf: 0.15   onchain: 0.16 defi: 0.10        # écosystème on-chain
SOL:  etf: 0.00   technical: 0.26  onchain: 0.20  # pas d'ETF spot US
```

### Clés API

Toutes optionnelles. Sans clé, le provider affiche `UNAVAILABLE — provider not configured`.
**Aucune valeur n'est jamais inventée pour combler un trou.**

| Clé | Coût | Débloque |
|---|---|---|
| `FRED_API_KEY` | **gratuite** | 12 séries : Fed funds, 2Y, 10Y, courbe, CPI, Core CPI, PCE, Core PCE, chômage, NFP |
| `CONGRESS_API_KEY` | **gratuite** | suivi législatif détaillé |
| `ETHERSCAN_API_KEY` | **gratuite** | gas, supply, burn ETH |
| `GLASSNODE_API_KEY` | payante | flux whales fiables |
| `CRYPTOQUANT_API_KEY` | payante | flux exchange |
| `NANSEN_API_KEY` / `ARKHAM_API_KEY` | payantes | intelligence on-chain |
| `COINGLASS_API_KEY` | payante | liquidations agrégées |

### Changer de modèle IA

```bash
LLM_PROVIDER=anthropic   # ou openai, ollama, mock, none
LLM_MODEL=claude-opus-5
LLM_API_KEY=...
```

Ollama fonctionne en local sans clé. **Sans LLM, tout le reste fonctionne** :
scores, indicateurs, contradictions, scénarios et rapport sont produits par le
code déterministe ; seule la narration est désactivée.

---

## Ta base de connaissances

Dépose tes cours, PDF, notes et transcriptions dans `knowledge/` :

```
knowledge/{courses,transcripts,trading,bitcoin,ethereum,solana,macro,regulation}/
```

puis `make ingest`. Formats : **TXT, MD, PDF**.

Le sous-dossier devient la catégorie du document. L'indexation utilise SQLite
FTS5 (BM25) — aucun modèle à télécharger, tout reste local.

**Distinction imposée par le code** : tes documents alimentent la table
`knowledge_chunks`, jamais `observations`. Un cours est une source de
*connaissance*, pas de *donnée temps réel*. Le lien se fait à l'analyse : la
donnée détecte la divergence RSI sur ETH 4H, ton cours explique ce qu'elle
signifie, et le passage utilisé est cité.

---

## Flux ETF

`data/imports/etf/*.csv` :

```csv
date,asset,ticker,flow_musd
2026-09-03,BTC,IBIT,454.0
2026-09-03,BTC,GBTC,8.2
```

Puis `make import-etf`. Une cellule vide reste une donnée manquante — elle n'est
jamais convertie en zéro, ce qui fausserait toutes les moyennes.

---

## Étendre le projet

### Ajouter une source
1. Créer une classe dans `backend/crypto_intel/providers/<catégorie>/`, héritant de `BaseProvider`.
2. Déclarer ses `capabilities` et retourner des `Observation` normalisées.
3. L'enregistrer dans `_provider_classes()` de `providers/registry.py`.
4. L'ajouter à la chaîne voulue dans `config/providers.yaml`.

Aucune logique métier n'est touchée. Remplacer Binance par Kraken = une ligne de YAML.

### Ajouter une crypto
1. Une entrée dans `config/assets.yaml` (symboles, seuil whale, métriques on-chain **pertinentes pour sa blockchain**).
2. Une entrée de pondérations dans `config/scoring.yaml`.
3. Ajouter le symbole à l'enum `Asset` dans `core/enums.py`.

### Ajouter un indicateur
1. Une fonction dans `engines/technical/indicators.py` (retourner `NaN` sur la période d'amorçage, jamais une valeur de remplissage).
2. Un test avec une valeur de référence externe.
3. Le brancher dans `engines/technical/engine.py`.

### Ajouter une figure chartiste
1. Une classe dans `engines/technical/patterns/detectors.py` héritant de `PatternDetector`.
2. Retourner `None` dès que la géométrie ne correspond pas vraiment.
3. L'enregistrer dans `register_all()`, ses seuils dans `config/thresholds.yaml`.

---

## Tests

```bash
make test     # 201 tests, hors ligne, sans clé API
```

Ils couvrent notamment :
- les indicateurs, **validés contre les valeurs de référence de Wilder** ;
- le scoring et le fait qu'un signal peu fiable ne domine jamais ;
- la fraîcheur et la distinction absence / ancienneté ;
- les calculs de flux ETF et les divergences flux/prix ;
- la détection des contradictions ;
- **l'absence de look-ahead** dans le moteur historique (vérifiée en mutant les barres futures) ;
- le fait qu'aucun moteur n'invente une valeur quand la donnée manque ;
- les endpoints de l'API ;
- la validation des sorties JSON du LLM et le garde-fou anti-hallucination.

---

## Ce que la recherche a mesuré

`make research` ne cherche pas à confirmer des intuitions. Résultats réels :

- Les flux ETF corrèlent **+0.41 avec le rendement du jour même** sur BTC, mais
  quasiment rien avec les rendements futurs à 1–7 jours : **ils suivent le prix
  plutôt qu'ils ne le précèdent**.
- Sur ETH, **aucun** signal ETF ne survit à la correction pour comparaisons
  multiples — les 10 « significatifs » bruts étaient du bruit.
- Le **score ETF n'a aucun pouvoir prédictif mesurable** (p=0.67 sur BTC),
  alors qu'il pèse 0.24 dans la conviction BTC.
- Le **score technique fonctionne** sur BTC et SOL : corrélation significative
  et surtout **monotone** — un score plus élevé correspond bien à un meilleur
  résultat.
- Le **score dérivés est quasi constant** (99 % des jours en « neutre ») : il ne
  discrimine rien en l'état.

**Le LOT 3 va plus loin, et le résultat est plus dur :**

- Le score technique avait un IC global de +0.070 (p<0.0001). Décomposé par
  année, il devient **négatif en intra-période** — il séparait les époques
  haussières des baissières, pas les bons jours des mauvais. Verdict revu en
  `NO_MEASURABLE_VALUE`.
- **Aucun domaine n'est classé USEFUL** sur aucun des trois actifs.
- Un modèle ridge sur 26 features a un **R² hors échantillon négatif** (−0.09 à
  −0.14) : ensemble, les features expliquent moins qu'une constante.
- Le seuil « funding extrême » de la config n'est franchi que **0,04 % à 0,09 %
  des jours** — d'où un score dérivés neutre 97-99 % du temps.
- L'asymétrie ETF pressentie au LOT 2 **ne se confirme pas** avec une
  méthodologie plus stricte.
- Ce qui survit : **RSI suracheté en tendance forte** précède une
  surperformance (BTC +2.28pp n=311, SOL +8.25pp n=168, FDR) — l'inverse de la
  règle scolaire.

Méthodologie et garde-fous : [docs/research-methodology.md](docs/research-methodology.md)
· limites : [docs/data-limitations.md](docs/data-limitations.md).

## Documentation

| Fichier | Contenu |
|---|---|
| [PLAN.md](PLAN.md) | philosophie, décisions d'ingénierie, règles non négociables |
| [ARCHITECTURE.md](ARCHITECTURE.md) | les cinq couches et le modèle de données |
| [DATA_SOURCES.md](DATA_SOURCES.md) | chaque source, son état vérifié, ses limites |
| [TODO.md](TODO.md) | ce qui est fait, ce qui reste |
| [docs/regime-vs-timing.md](docs/regime-vs-timing.md) | tendance vs timing d'entrée |
| [docs/research-methodology.md](docs/research-methodology.md) | anti look-ahead, FDR, validation temporelle |
| [docs/data-limitations.md](docs/data-limitations.md) | révisions macro, OI 30 j, IC gonflé, biais |
| [docs/data-imports.md](docs/data-imports.md) | formats d'import CSV (OI, ETF) |
| [docs/](docs/) | pipeline, scoring, sources, base de connaissances |

---

## Architecture de déploiement

```
                    ┌──────────────────────────────┐
   navigateur  ───►  │  FastAPI (uvicorn) :8100     │
                    │                              │
                    │  /            → SPA React    │
                    │  /chart, ...  → SPA (router) │
                    │  /api/*       → API          │
                    │  /docs        → OpenAPI      │
                    └──────────────┬───────────────┘
                                   │
                          volume /app/data
                    (SQLite, cache structurel,
                     recherche, snapshots live)
```

Une seule image, un seul processus, un seul port. Le frontend est compilé au
`docker build` (étage Node) puis copié dans l'image Python ; il n'y a pas de
Node dans l'image finale.

---

## Ce que le système ne fait pas

- Il ne passe **aucun ordre** et ne détient aucune clé d'échange en écriture.
- Il ne contourne **aucun** paywall, protection anti-bot ou authentification.
  Une source qui refuse l'accès automatisé est signalée, jamais forcée.
- Il ne génère **aucune donnée fictive** en dehors de `MOCK_MODE=true`.
- Il ne présente **jamais** une proposition de loi comme une loi adoptée.
- Il ne prétend pas prédire les événements géopolitiques ; il évalue le risque
  porté par ceux qui ont déjà eu lieu.
- Il ne donne **aucun conseil en investissement**.
