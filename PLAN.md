# PLAN — Crypto Intelligence

> Outil **personnel** d'analyse des marchés crypto (BTC / ETH / SOL).
> Ce n'est pas une plateforme publique, ce n'est pas un bot de trading,
> **aucun ordre n'est jamais passé**. Le système collecte, structure, calcule,
> analyse et *explique* pour aider à décider — la décision reste humaine.

---

## 1. Principe directeur

Le pipeline est strictement ordonné et chaque étage est indépendant du suivant :

```
DONNÉES BRUTES
  → normalisation        (Observation : source, valeur, unité, timestamp)
  → calcul d'indicateurs (Python déterministe, sans LLM)
  → extraction d'événements
  → analyse spécialisée  (un analyste par domaine)
  → comparaison historique
  → agrégation           (scores + conviction pondérée)
  → analyse IA           (interprétation d'une structure compacte et sourcée)
  → rapport final argumenté
```

**Le LLM n'intervient qu'à l'avant-dernière étape**, et uniquement sur des
structures déjà calculées, compactées et sourcées. Il ne voit jamais les
données brutes massives et **ne peut jamais inventer une donnée manquante**.

---

## 2. Séparation FAITS / CALCULS / INTERPRÉTATIONS / HYPOTHÈSES

C'est le socle du projet. Quatre types distincts, jamais confondus :

| Niveau | Type Python | Origine | Exemple |
|---|---|---|---|
| **FAIT** | `Observation` | Un provider externe | `BTC ETF net flow = +730.8 M$` (Farside, 2026-09-03) |
| **CALCUL** | `Computation` | Code Python déterministe | `moyenne 5j = +412 M$`, `accélération = +18 %` |
| **INTERPRÉTATION** | `Interpretation` | Un analyste (règles ou LLM) | `demande institutionnelle actuellement favorable` |
| **HYPOTHÈSE** | `Hypothesis` | Scénario conditionnel | `peut soutenir le prix si les autres facteurs restent favorables` |

Chaque niveau porte ses `evidence_ids` qui remontent jusqu'aux `Observation`
sources. C'est ce qui permet le bouton **WHY ?** de l'interface.

Un `Fact` ne peut jamais être produit par un LLM. Le code le refuse
(`llm/validation.py` rejette toute sortie contenant des valeurs numériques
non présentes dans le contexte fourni).

---

## 3. Ce qui est construit dans ce premier lot

Ordre d'exécution aligné sur les priorités demandées (§39 du cahier des charges).

### Priorité 1 — Architecture + stockage + provenance
- Modèles `Observation` / `Computation` / `Interpretation` / `Hypothesis`
- Base SQLite (SQLAlchemy 2.0), migrable PostgreSQL (aucun SQL spécifique SQLite dans la logique métier)
- `Provenance` obligatoire sur toute donnée : `source`, `provider`, `source_url`,
  `timestamp`, `fetched_at`, `freshness`, `confidence`
- Registre de providers + interfaces abstraites (remplacement d'une source sans toucher au métier)
- `MOCK_MODE` couvrant l'ensemble de l'application

### Priorité 2 — Market data BTC / ETH / SOL
- Binance (OHLCV, principal), Coinbase + Kraken (fallback/cross-check), CoinGecko (market cap)
- Timeframes 15m / 1h / 4h / 1d / 1w
- Cache disque + mémoire avec TTL par timeframe

### Priorité 3 — Analyse technique
- `TechnicalAnalysisEngine` **100 % indépendant du LLM**
- Tendance (EMA 20/50/100/200, SMA), momentum (RSI 14, MACD), volatilité
  (Bollinger, ATR, vol réalisée), volume (relatif, accélération)
- Structure de marché (HH/HL/LH/LL), niveaux (supports/résistances, swings)
- Divergences RSI et MACD
- Figures chartistes : architecture extensible à base de détecteurs enregistrés,
  chacun retournant `pattern / confidence / timeframe / confirmation_state / invalidation_level`
- Moteur multi-timeframe avec pondération croissante vers les TF hautes

### Priorité 4 — ETF flows
- `ETFFlowAnalyzer` : flux par ETF, total, net, moyennes 3/5/7j, cumul,
  accélération, retournements, séries consécutives, divergence flow/prix
- Source Farside : **connecteur poli qui s'arrête si la source est protégée**
  (elle renvoie actuellement HTTP 403). Aucun contournement.
- Voie fiable retenue : **import CSV / manuel** dans `data/imports/etf/`

### Priorité 5 — Macro / régulation / news
- Macro : FRED (clé gratuite), Stooq (indices/DXY sans clé), calendrier d'événements
- Régulation : flux RSS officiels SEC / Federal Reserve / CFTC / Treasury / White House
- Classification stricte du **statut juridique** : adopté / proposé / rumeur /
  déclaration / consultation / vote prévu / vote effectué / décision réglementaire
- News engine : agrégation multi-sources, déduplication, clustering par événement,
  hiérarchie de crédibilité des sources

### Priorité 6 — DeFi / stablecoins / on-chain
- DeFiLlama : TVL par chaîne, DEX volumes, fees, stablecoins par chaîne, RWA
- On-chain : métriques **adaptées à chaque blockchain** (jamais les mêmes
  métriques appliquées mécaniquement à BTC, ETH et SOL)

### Priorité 7 — IA + rapports
- Abstraction `LLMProvider` (Anthropic / OpenAI / Ollama / mock)
- Analystes spécialisés produisant chacun une sortie **structurée Pydantic**
- `ChiefMarketAnalyst` recevant les conclusions, pas les données brutes
- Scoring −100 → +100 avec `confidence`, `freshness`, `evidence_count`
- `MarketConvictionEngine` : court / moyen / long terme, séparément
- Scénarios avec « probabilité analytique indicative »
- Rapport final au format demandé (§28)

### Priorité 8 — Base de connaissances personnelle
- Ingestion TXT / MD / PDF depuis `knowledge/`
- Découpage sémantique, index full-text (SQLite FTS5), citation des passages
- RAG : la connaissance de cours éclaire les données marché, elle ne les remplace jamais

### Priorité 9 — Similarité historique + évaluation
- `HistoricalSimilarityEngine` avec vecteur de features, **anti look-ahead strict**
- Enregistrement de chaque rapport + calcul différé des performances +1h → +30j
- Statistiques : direction accuracy, calibration, score vs future returns, par régime, par analyste

### Priorité 10 — Whales
- Architecture complète + connecteurs optionnels (Glassnode / CryptoQuant / Nansen / Arkham)
- Sans abonnement : `UNAVAILABLE — provider not configured`. **Aucune valeur inventée.**

---

## 4. Décisions d'ingénierie prises

| Sujet | Décision | Raison |
|---|---|---|
| Base de données | SQLite + SQLAlchemy 2.0 ORM | Outil personnel ; ORM pur → migration PostgreSQL par simple changement d'URL |
| Async | `httpx.AsyncClient` pour les providers, sessions DB synchrones | Le parallélisme utile est sur le réseau, pas sur SQLite |
| Indicateurs techniques | Implémentés et testés à la main (pandas/numpy) | `TA-Lib` exige une compilation C ; des indicateurs testés valent mieux qu'une dépendance fragile |
| Recherche knowledge | SQLite FTS5 (BM25) | Zéro dépendance externe, zéro modèle d'embedding à télécharger ; interface `Retriever` abstraite pour brancher des embeddings plus tard |
| Frontend | React + TypeScript + Vite | Demandé ; Node installé localement dans `~/.local/opt/node22` (pas de sudo disponible) |
| Scheduler | APScheduler intégré au process FastAPI | Suffisant pour un usage local mono-utilisateur |
| Farside | Connecteur + détection du blocage + import CSV | La source renvoie 403 ; contourner serait une violation des règles du projet |

---

## 5. Règles non négociables

1. Aucun ordre de trading, aucune exécution, aucune connexion à un compte d'échange.
2. Aucun secret en dur ; tout passe par `.env` (non versionné) et `.env.example`.
3. Aucun contournement de paywall, de protection anti-bot ou d'authentification.
4. Aucune donnée fictive en dehors de `MOCK_MODE=true`.
5. Donnée absente → `UNAVAILABLE`. Donnée trop vieille → `STALE`. Preuves
   insuffisantes → `INCONCLUSIVE`. Jamais de valeur de remplissage.
6. Une proposition de loi n'est jamais présentée comme une loi adoptée.
7. Une probabilité non issue d'un modèle calibré est nommée
   « probabilité analytique indicative ».
8. Aucune fonctionnalité annoncée comme fonctionnelle sans avoir été testée.

---

## 6. Critère d'acceptation du premier lot

Lancer le backend et le frontend, ouvrir le dashboard, et voir pour BTC, ETH et SOL :
prix réels, indicateurs techniques calculés, données ETF (ou `UNAVAILABLE` explicite),
métriques DeFi/on-chain gratuites, news/événements, scores avec confiance,
rapport synthétique, provenance cliquable — et le tout fonctionnant également
hors ligne en `MOCK_MODE=true`.
