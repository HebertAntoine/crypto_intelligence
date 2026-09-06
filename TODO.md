# TODO — Crypto Intelligence

Statut : `[x]` fait et testé · `[~]` architecture en place, extension prévue · `[ ]` à faire

---

## Priorité 1 — Architecture, stockage, provenance
- [x] Structure du projet, `pyproject.toml`, ruff, pytest
- [x] `Observation` / `Computation` / `Interpretation` / `Hypothesis`
- [x] Provenance obligatoire + `Freshness` calculée par classe de métrique
- [x] Base SQLite via SQLAlchemy 2.0 (ORM pur, migrable PostgreSQL)
- [x] Interface `BaseProvider` + registre + chaînes de fallback
- [x] Cache HTTP disque/mémoire à TTL
- [x] `MOCK_MODE` couvrant tout le pipeline
- [x] Configuration YAML externalisée (`assets`, `providers`, `scoring`, `thresholds`)
- [x] Logs structurés (structlog), exceptions maîtrisées
- [x] Chaîne d'explicabilité `/api/why/{id}`

## Priorité 2 — Market data
- [x] Provider Binance (OHLCV 15m/1h/4h/1d/1w + ticker 24h)
- [x] Fallbacks Coinbase et Kraken
- [x] CoinGecko (market cap, supply, dominance)
- [x] Variations 1h / 4h / 24h / 7j calculées depuis les barres
- [x] Fixtures mock pour les 3 actifs × 5 timeframes

## Priorité 3 — Analyse technique
- [x] EMA 20/50/100/200, SMA
- [x] RSI 14 (lissage de Wilder), MACD + signal + histogramme
- [x] Bollinger, ATR, volatilité réalisée
- [x] Volume relatif, moyenne, accélération
- [x] Structure HH/HL/LH/LL, régime uptrend/downtrend/range
- [x] Supports/résistances par clustering de swings
- [x] Divergences RSI et MACD (régulières + cachées)
- [x] Registre de figures chartistes extensible
- [x] Détecteurs implémentés et enregistrés (8) : double top, double bottom, range,
      breakout, fake breakout, head & shoulders, inverse head & shoulders,
      triangle (ascendant / descendant / symétrique)
- [ ] Détecteurs restants : wedge, flag, pennant
      → à écrire un par un dans `patterns/detectors.py` avec leurs tests
- [x] Moteur multi-timeframe + cohérence pondérée

## Priorité 4 — ETF flows
- [x] `ETFFlowAnalyzer` : par ETF, total, net, MM3/5/7, cumul, accélération, retournements, séries
- [x] Divergence flux / prix
- [x] Import CSV (`make import-etf`)
- [x] Connecteur Farside opérationnel — 12 ETF BTC (depuis 2024-01-11) et 10 ETF ETH
      (depuis 2024-07-23), une seule requête, User-Agent honnête, arrêt définitif
      si la source refuse un jour cette identification
- [x] Connecteurs Coinglass / SoSoValue derrière clé
- [ ] Saisie manuelle depuis l'interface web (formulaire dédié)

## Priorité 5 — Macro / régulation / news
- [x] FRED (taux, CPI, PCE, emploi) — clé gratuite
- [x] Yahoo Finance (SPX, NDX, DJI, DXY, VIX, or, pétrole, 10Y) sans clé
- [x] Stooq conservé en secours — détecte son challenge JS et le signale sans le contourner
- [x] Calendrier d'événements + pondération par `time_to_event`
- [x] RSS officiels SEC / Fed / CFTC / Treasury / White House
- [x] Classification du statut juridique (adopté / proposé / rumeur / …)
- [x] News engine : dédup, clustering par événement, hiérarchie de crédibilité
- [x] `GeopoliticalRiskAnalyzer` (LOW / MODERATE / HIGH / EXTREME + justification)
- [ ] Congress.gov (suivi législatif fin, CLARITY Act et successeurs)

## Priorité 6 — DeFi / stablecoins / on-chain
- [x] DeFiLlama : TVL chaînes, DEX volumes, fees
- [x] Stablecoins : supply totale, variations, répartition par chaîne
- [x] `StablecoinLiquidityAnalyzer` (expansion / contraction)
- [x] On-chain BTC : hashrate, difficulty, tx, fees
- [x] On-chain ETH : tx, adresses actives, fees
- [x] On-chain SOL : epoch, supply, TPS hors votes
- [x] RWA via catégorie DeFiLlama
- [ ] Bridge flows
- [ ] Exchange netflows fiables (nécessite Glassnode ou CryptoQuant)

## Priorité 7 — IA et rapports
- [x] Abstraction `LLMProvider` (Anthropic / OpenAI / Ollama / mock)
- [x] Schémas Pydantic pour chaque sortie IA + retry sur invalidité
- [x] Garde-fou numérique : tout nombre cité doit exister dans le contexte
- [x] 10 analystes spécialisés + `ChiefMarketAnalyst`
- [x] Scores −100/+100 avec confidence, freshness, evidence_count
- [x] `MarketConvictionEngine` court / moyen / long terme
- [x] Scénarios (central / haussier / baissier) avec probabilité analytique indicative
- [x] Détection des contradictions
- [x] Rapport texte au format demandé (§28)
- [x] Système d'alertes avec importance INFO/WATCH/IMPORTANT/CRITICAL
- [x] Calendrier macro synchronisé du YAML vers la base et remonté comme catalyseurs
- [ ] Export PDF du rapport

## Priorité 8 — Base de connaissances
- [x] Ingestion TXT / MD / PDF
- [x] Découpage avec recouvrement, conservation document + page
- [x] Index FTS5 + recherche BM25
- [x] Citation des passages dans l'analyse
- [x] Fiches de connaissances structurelles versionnées BTC / ETH / SOL
- [ ] Embeddings vectoriels (interface `Retriever` déjà prête)
- [ ] Ingestion DOCX / EPUB / sous-titres SRT-VTT

## Priorité 9 — Historique et évaluation
- [x] `HistoricalSimilarityEngine` + vecteur de features
- [x] Garde anti look-ahead + test dédié
- [x] Enregistrement figé de chaque rapport
- [x] Calcul différé des performances +1h/+4h/+24h/+3j/+7j/+30j
- [x] Statistiques : direction accuracy, calibration, score vs returns, par analyste
- [ ] Backtest complet sur historique long (nécessite d'accumuler des rapports)

## Priorité 10 — Whales
- [x] Architecture `WhaleAnalyzer` + seuils par actif
- [x] Connecteurs optionnels Glassnode / CryptoQuant / Nansen / Arkham
- [x] `UNAVAILABLE — provider not configured` sans abonnement
- [x] `reliability` explicite sur chaque signal
- [~] Heuristique interne grosses transactions (fiabilité faible, marquée)

## Frontend
- [x] React + TypeScript + Vite, thème sombre sobre
- [x] Dashboard 3 cartes BTC / ETH / SOL
- [x] Onglets par actif : Overview, Technical, ETF, Derivatives, On-chain, Liquidity, Macro, News, Whales, Historical, Sources
- [x] Vue GLOBAL MARKET
- [x] Panneau **WHY ?** (preuves d'une conclusion)
- [x] Badges de fraîcheur et `UNAVAILABLE` explicites
- [ ] Graphiques de prix interactifs (lightweight-charts)
- [ ] Vue diff entre deux rapports

## Tests
- [x] Indicateurs techniques (valeurs de référence)
- [x] Scoring et conviction
- [x] Normalisation et provenance
- [x] Fraîcheur
- [x] Calculs de flux ETF
- [x] Détection de contradictions
- [x] Anti look-ahead du moteur historique
- [x] Absence de données → jamais de valeur inventée
- [x] Endpoints API
- [x] Validation JSON des sorties LLM
- [x] Fixtures permettant de tourner **sans Internet**
- [x] 201 tests, exécution complète en 1.7 s sans réseau ni clé API
- [ ] Tests d'intégration réseau marqués `@pytest.mark.network`

## Sécurité et conformité
- [x] Aucun secret en dur, `.env` non versionné
- [x] Aucun contournement de paywall / anti-bot / authentification
- [x] Aucune donnée fictive hors `MOCK_MODE`
- [x] Aucun ordre de trading — aucune clé d'exchange en écriture

---

---

## Vérifié en conditions réelles le 2026-09-04

- Pipeline complet exécuté sur BTC, ETH et SOL avec données de marché réelles
- Farside : 7267 lignes BTC + 4904 lignes ETH parsées ; total BTC du 2026-09-03 = +730.8 M$
- 18 providers opérationnels sans aucune clé, 8 correctement signalés non configurés
- Backend + frontend lancés ensemble, dashboard et proxy fonctionnels
- Mode mock validé : les 3 actifs analysés sans réseau ni clé
- 201 tests au vert, ruff sans avertissement, TypeScript sans erreur, build de production réussi

---

# LOT 2 — livré le 2026-09-05

## Historisation et backfill
- [x] Backfill idempotent multi-sources (`make backfill`)
- [x] 9,0 ans de bougies daily BTC/ETH, 6,1 ans SOL
- [x] 6,4 ans de funding (bug de pagination corrigé : 500 → 7000 points)
- [x] 10 ans de macro sur 10 séries Yahoo
- [x] Snapshots à cadence différenciée (market 15min → ETF 1440min), idempotents par bucket
- [x] Scheduler robuste : coalesce, max_instances, reprise après redémarrage
- [x] `make coverage` documente la profondeur réelle par métrique
- [ ] Open interest limité à ~30 jours (limite de la source Binance, documentée)

## Tendance vs timing
- [x] `MarketRegimeEngine` multi-facteurs + 11 conditions de caractère
- [x] `EntryTimingEngine` déterministe, 11 familles de facteurs
- [x] Les deux axes sont indépendants et peuvent diverger
- [x] Zones dérivées de niveaux calculés, jamais d'objectif arbitraire
- [x] Événement macro imminent traité comme plafond (défaut trouvé par un test)
- [x] Bougie partielle exclue des comparaisons de volume

## Recherche quantitative
- [x] Étude ETF → prix futur, 7 horizons, 9 signaux
- [x] Contrôle contemporain (le test décisif : suivre ou précéder)
- [x] Correction Benjamini-Hochberg pour comparaisons multiples
- [x] Validation train / validation / out-of-sample chronologique
- [x] 15 event studies avec baseline sur fenêtre observable, MFE/MAE
- [x] Calibration des scores par bucket + test de monotonie
- [x] `make research` publie les résultats négatifs au même niveau
- [ ] Calibration sur rapports réels (attend l'accumulation de rapports)

## Interface
- [x] Page « Today » lisible en 10 secondes
- [x] Graphiques interactifs (lightweight-charts) 5 timeframes + overlays + marqueurs
- [x] ETF vs prix avec lag visuel sélectionnable et avertissement causalité
- [x] Page Calendar par proximité
- [x] Page Research affichant les résultats négatifs
- [x] Page Knowledge avec recherche et ré-indexation
- [x] Panneau WHY ? enrichi : facteurs, formule, données sources
- [ ] Graphiques de scores dans le temps (les snapshots sont là, la vue reste à faire)

## Alertes
- [x] Déduplication par `dedup_key` stable
- [x] Cooldown par type d'alerte
- [x] Alertes de changement d'état (régime, timing) encodant la transition
- [x] Chaque alerte porte son `reason`
- [x] Bug corrigé : les alertes n'étaient jamais persistées (TypeError avalé)

---

# LOT 3 — livré le 2026-09-05

## Audit et mesure
- [x] Audit par actif : poids, n, IC, monotonie, stabilité, verdict
- [x] **Décomposition IC intra-période vs globale** — invalide une conclusion du LOT 2
- [x] Détection de concentration (score coincé dans un bucket)
- [x] Cinq verdicts : USEFUL / WEAK / UNSTABLE / NO_MEASURABLE_VALUE / INSUFFICIENT_DATA

## Recherche quantitative
- [x] Walk-forward glissant + score de stabilité 0-100
- [x] Feature importance : IC, monotonie, permutation ridge, stabilité
- [x] ETF asymétrie : 5 catégories par percentile trailing, CI 95 %, FDR
- [x] Dérivés : bandes de percentiles par actif + seuils suggérés
- [x] Interactions prix × OI × funding (limitées par les 30 j d'OI)
- [x] Études conditionnées par régime
- [x] Champion / Challenger sur fenêtres OOS

## Moteurs
- [x] `ETFSplitEngine` : contexte vs prédictif
- [x] `RSIContextEngine` : lecture mesurée, pas scolaire
- [x] `EmpiricalTimingLayer` : analogues avec cascade exact-ish → relaxed → broad
- [x] Risk/reward par MFE/MAE historiques
- [x] `ANALYTICAL_CONFIDENCE` vs `EMPIRICAL_PROBABILITY`
- [x] DATA SAYS / KNOWLEDGE BASE SAYS

## Infrastructure
- [x] Snapshots de prédiction immuables + hash de contenu
- [x] Live performance séparée du backtest
- [x] Import CSV open interest
- [x] Embeddings locaux + retrieval hybride BM25 + vecteurs (RRF)
- [x] Export CSV / JSON / Markdown
- [x] 23 tests anti-fuite temporelle

## Non fait / limites assumées
- [ ] Séries macro « as originally released » (ALFRED) — limitation documentée
- [ ] OI au-delà de 30 jours sans import externe — limite de la source
- [ ] Calibration sur rapports live — attend l'accumulation de prédictions

## Prochaines étapes recommandées
1. Obtenir `FRED_API_KEY` (gratuite, 1 minute) → débloque taux, CPI, PCE, emploi
2. Importer un premier CSV de flux ETF → active le module ETF
3. Déposer les cours et PDF dans `knowledge/` puis `make ingest`
4. Configurer un `LLM_PROVIDER` (Ollama local suffit) → active les rapports narratifs
5. Laisser tourner le scheduler quelques jours → alimente l'évaluation et la similarité historique
6. Implémenter les détecteurs de figures restants, un par un, chacun avec ses tests
