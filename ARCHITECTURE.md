# ARCHITECTURE — Crypto Intelligence

## 1. Vue d'ensemble

Cinq couches, dépendances **strictement descendantes**. Une couche ne connaît
jamais celle du dessus. La logique métier n'appelle jamais directement le réseau.

```
┌──────────────────────────────────────────────────────────────────┐
│ 5. PRÉSENTATION      frontend React/TS  ·  API FastAPI  ·  CLI   │
├──────────────────────────────────────────────────────────────────┤
│ 4. SYNTHÈSE          analysts/ · ChiefMarketAnalyst · reports/    │
│                      llm/ (interprétation seulement)              │
├──────────────────────────────────────────────────────────────────┤
│ 3. ANALYSE           engines/ — 100 % Python déterministe         │
│                      technical · etf · derivatives · onchain      │
│                      liquidity · macro · regulation · news        │
│                      historical · contradictions · scoring        │
│                      conviction · alerts                          │
├──────────────────────────────────────────────────────────────────┤
│ 2. PERSISTANCE       db/ — SQLAlchemy 2.0 → SQLite (→ PostgreSQL) │
│                      Observation · Report · Outcome · Knowledge   │
├──────────────────────────────────────────────────────────────────┤
│ 1. ACQUISITION       providers/ — HTTP, RSS, CSV, fixtures        │
│                      interfaces abstraites + registre             │
└──────────────────────────────────────────────────────────────────┘
```

**Règle d'or :** aucun `httpx`, aucun scraping, aucun parsing de format externe
en dehors de `providers/`. Les engines reçoivent uniquement des `Observation`
normalisées et ne savent pas d'où elles viennent.

---

## 2. Le modèle de données central

### 2.1 `Observation` — le FAIT

Toute donnée entrant dans le système devient une `Observation`. C'est le seul
point d'entrée.

```python
class Observation(BaseModel):
    id: str                      # hash déterministe (provider|asset|metric|ts)
    source: str                  # "Binance", "DeFiLlama", "SEC"
    provider: str                # "binance_spot" — l'implémentation exacte
    asset: Asset | None          # BTC / ETH / SOL / GLOBAL / None
    metric: str                  # "price.close", "etf.net_flow"
    value: float | str | dict    # la valeur ORIGINALE, non transformée
    unit: str                    # "USD", "USD_M", "pct", "count", "ratio"
    timestamp: datetime          # à quoi la donnée se rapporte (UTC)
    fetched_at: datetime         # quand nous l'avons récupérée (UTC)
    source_url: str | None
    freshness: Freshness         # calculée, jamais saisie
    confidence: float            # 0–100, qualité de la source
    quality: DataQuality
    meta: dict
```

`value` conserve **la valeur d'origine**. Toute transformation produit une
`Computation` distincte qui référence l'`Observation`. On peut donc toujours
remonter au chiffre brut publié par la source.

### 2.2 Les quatre niveaux épistémiques

```
Observation  (FAIT)          ← providers uniquement, jamais un LLM
     ↓ evidence_ids
Computation  (CALCUL)        ← engines, code déterministe, formule enregistrée
     ↓ evidence_ids
Interpretation (INTERPRÉTATION) ← analysts, règles + LLM
     ↓ evidence_ids
Hypothesis   (HYPOTHÈSE)     ← scénarios conditionnels, jamais affirmatifs
```

Chaque objet porte `evidence_ids: list[str]`. L'endpoint `/api/why/{id}` remonte
récursivement la chaîne jusqu'aux `Observation` sources — c'est le mécanisme
d'explicabilité (§32 du cahier des charges).

### 2.3 Fraîcheur

Calculée par `core/freshness.py`, jamais déclarée à la main. Les seuils dépendent
de la **classe de métrique** : un prix de 30 minutes est périmé, un flux ETF de
30 minutes est parfaitement frais.

```
LIVE  ·  MIN_15  ·  HOUR_1  ·  TODAY  ·  STALE  ·  UNAVAILABLE
```

---

## 3. Couche providers

### 3.1 Interface

```python
class BaseProvider(ABC):
    name: str
    source: str
    category: ProviderCategory
    requires_key: bool
    source_url: str

    async def available(self) -> ProviderStatus: ...
    async def fetch(self, request: FetchRequest) -> FetchResult: ...
```

`FetchResult` contient soit des `Observation`, soit un motif d'indisponibilité
explicite (`UNAVAILABLE`, `NOT_CONFIGURED`, `BLOCKED_BY_SOURCE`, `RATE_LIMITED`).
**Un provider ne lève jamais d'exception vers le métier** : il retourne un
résultat vide qualifié. C'est ce qui rend le système résistant aux pannes de
source sans jamais fabriquer de valeur.

### 3.2 Registre et substitution

`providers/registry.py` associe une **capacité** (`market.ohlcv`, `etf.flows`,
`defi.tvl`, …) à une **chaîne ordonnée de providers**. En cas d'échec du premier,
le suivant est essayé. En `MOCK_MODE`, le registre bascule intégralement sur les
providers `fixtures`.

Remplacer Binance par Kraken = une ligne dans `config/providers.yaml`.
Aucun code métier modifié.

### 3.3 Cache HTTP

`providers/http.py` : client `httpx.AsyncClient` partagé, TTL par capacité,
cache disque JSON dans `data/cache/`, backoff exponentiel (tenacity),
`User-Agent` identifiant honnêtement l'outil, respect des `429`/`Retry-After`.

---

## 4. Couche engines — le cœur déterministe

Aucun engine n'importe `llm/`. Ils sont tous testables hors ligne. C'est
délibéré : **le système doit produire une analyse complète même sans LLM**.

### 4.1 `engines/technical/`
```
indicators.py   EMA/SMA, RSI Wilder, MACD, Bollinger, ATR, vol réalisée, volume
structure.py    swings, HH/HL/LH/LL, régime (uptrend / downtrend / range)
levels.py       supports/résistances par clustering de swings + touches
divergence.py   divergences RSI et MACD (régulières et cachées)
patterns/       un détecteur = une classe enregistrée dans un registre
engine.py       orchestration → TechnicalSnapshot
```

Les détecteurs de figures retournent `None` plutôt qu'une figure douteuse.
Chacun expose un seuil de confiance minimal ; en dessous, rien n'est annoncé.
Sortie : `pattern`, `confidence`, `timeframe`, `confirmation_state`
(`FORMING` / `CONFIRMED` / `INVALIDATED`), `invalidation_level`.

### 4.2 `engines/mtf.py`
Analyse 15m / 1h / 4h / 1d / 1w, puis cohérence pondérée — poids croissants
vers les timeframes hautes (`config/scoring.yaml`). Une divergence entre TF
n'est pas moyennée : elle est signalée.

### 4.3 `engines/scoring.py` et `engines/conviction.py`
Chaque score est un `ScoreCard` :

```
score        −100 … +100
confidence   0 … 100
freshness    la pire fraîcheur des preuves utilisées
evidence_count
components   sous-scores détaillés, pour l'explicabilité
```

`MarketConvictionEngine` n'est **pas une moyenne**. Le poids effectif d'un score
est `poids_config × f(confidence) × g(freshness) × h(horizon)`. Un score +90 à
20 % de confiance pèse structurellement moins qu'un +40 à 95 %. Trois convictions
sont produites séparément (court / moyen / long terme) parce qu'un RSI 15 minutes
et une décision du FOMC n'agissent pas sur le même horizon.

### 4.4 `engines/contradictions.py`
Recherche de couples de signaux incompatibles selon des règles explicites
(prix ↑ + funding extrême + whales vers exchanges, etc.). Les contradictions sont
**remontées telles quelles** et réduisent la confiance globale — elles ne sont
jamais absorbées par une moyenne.

### 4.5 `engines/historical.py`
Vecteur de features normalisé (RSI, pente de tendance, vol, volume relatif,
funding, OI, flux ETF, régime macro). Similarité cosinus sur fenêtre glissante.

**Anti look-ahead :** la construction du vecteur à la date *t* n'utilise que des
barres `index <= t`, et les rendements futurs sont lus dans une structure
séparée, jamais réinjectés dans les features. Un test dédié le vérifie en
modifiant les barres futures et en contrôlant que le vecteur est inchangé.

---

## 5. Couche analystes

Dix analystes spécialisés, un domaine chacun, tous héritant de `BaseAnalyst` :

```
Technical · ETF · Derivatives · OnChain · Liquidity
Macro · Regulation · News · Whale · Historical
```

Chacun produit un `AnalystOutput` Pydantic : `score`, `confidence`, `findings`
(positifs / négatifs / neutres), `evidence_ids`, `missing_data`, `notes`.

`ChiefMarketAnalyst` reçoit **uniquement ces sorties structurées**, jamais les
données brutes, et cherche : convergences, divergences, contradictions, données
manquantes, catalyseurs, risques.

Cette séparation est ce qui évite le « prompt géant » : chaque appel LLM est
petit, ciblé, à schéma de sortie strict.

---

## 6. Couche LLM

```python
class LLMProvider(ABC):
    async def complete_json(self, prompt, schema: type[BaseModel],
                            *, temperature, max_tokens) -> BaseModel
```

Implémentations : Anthropic · OpenAI-compatible · Ollama (local) · Mock.
Sélection par `.env` (`LLM_PROVIDER`, `LLM_MODEL`, `LLM_API_KEY`) — changer de
modèle ne touche aucune ligne de logique métier.

**Trois garde-fous anti-hallucination** (`llm/validation.py`) :

1. Sortie non conforme au schéma Pydantic → rejet + retry avec l'erreur en retour.
2. Tout nombre cité par le modèle est confronté aux valeurs du contexte fourni ;
   un nombre absent du contexte invalide la réponse.
3. Le prompt système impose `UNAVAILABLE` / `STALE` / `INCONCLUSIVE` et interdit
   explicitement d'inventer prix, news, flux, chiffre macro, signal whale ou source.

Le système reste entièrement fonctionnel sans LLM configuré : les analystes
basculent sur leur mode règles et le rapport est produit sans section narrative.

---

## 7. Base de connaissances (RAG)

```
knowledge/{courses,transcripts,trading,bitcoin,ethereum,solana,macro,regulation}/
```

Ingestion → extraction (TXT/MD/PDF) → découpage avec recouvrement en conservant
la page → index SQLite FTS5 → recherche BM25 → passages cités.

Distinction imposée par le code : les documents personnels alimentent la table
`knowledge_chunks`, **jamais** la table `observations`. Un cours est une source
de *connaissance*, pas une source de *donnée temps réel*. Le lien entre les deux
est fait par `analysts/technical.py` : la donnée détecte la divergence RSI, le
cours explique ce qu'elle signifie, et le passage est cité.

---

## 8. Persistance

| Table | Rôle |
|---|---|
| `observations` | tous les faits, avec provenance complète |
| `computations` | calculs dérivés + formule |
| `reports` | rapport complet sérialisé, figé au moment T |
| `report_outcomes` | prix constatés à +1h/+4h/+24h/+3j/+7j/+30j |
| `knowledge_documents` / `knowledge_chunks` | base de connaissances + FTS5 |
| `alerts` | alertes générées, avec importance |
| `events` | calendrier macro/régulation |

Uniquement de l'ORM SQLAlchemy 2.0 — aucun SQL spécifique SQLite dans le métier.
Migration PostgreSQL = changement de `DATABASE_URL`. (L'index FTS5 est le seul
élément spécifique SQLite, isolé derrière l'interface `KnowledgeStore`.)

---

## 9. API et frontend

FastAPI expose les routes par domaine (`/api/assets`, `/api/technical`,
`/api/etf`, `/api/report`, `/api/why/{id}`, `/api/sources`, `/api/alerts`,
`/api/knowledge`, `/api/evaluation`…). Le frontend React/TypeScript/Vite ne
parle qu'à cette API, en thème sombre, sobre, orienté données. Pas
d'authentification en V1 : usage strictement local (`127.0.0.1`).

---

## 10. Exécution

- **Scheduler** APScheduler dans le process FastAPI, cadences par capacité
  (prix 5 min, dérivés 15 min, ETF 1 h, macro 1 h, news 30 min, on-chain 1 h).
- **CLI** `python -m crypto_intel.cli` : `collect`, `analyze`, `report`,
  `ingest-knowledge`, `import-etf`, `evaluate`, `serve`.
- **MOCK_MODE=true** : tout le pipeline tourne sur `fixtures/`, sans réseau ni clé.
