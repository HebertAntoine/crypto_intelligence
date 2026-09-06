# DATA_SOURCES — Crypto Intelligence

État vérifié le **2026-09-04** depuis la machine du projet, par mesure directe
des codes HTTP et du contenu réellement retourné.

Légende :
- 🟢 **OPÉRATIONNEL** — testé, sans clé, intégré
- 🔑 **CLÉ REQUISE** — connecteur écrit, activé par une variable `.env`
- 🟠 **DÉGRADÉ** — source accessible mais partielle ou fragile
- 🔴 **BLOQUÉ** — la source refuse l'accès automatisé ; **aucun contournement**

---

## 1. Market data

| Source | Statut | Usage | Clé | Limites |
|---|---|---|---|---|
| **Binance** `api.binance.com` | 🟢 200 | OHLCV 15m/1h/4h/1d/1w, ticker 24h | non | 1200 req/min pondérées |
| **Coinbase** `api.coinbase.com` | 🟢 200 | prix spot, cross-check | non | ~10 req/s |
| **Kraken** `api.kraken.com` | 🟢 200 | OHLC de secours | non | ~1 req/s |
| **CoinGecko** `api.coingecko.com` | 🟢 200 | market cap, supply, dominance | non (gratuit) | 10–30 req/min — cache long obligatoire |

Chaîne configurée : `binance → coinbase → kraken`. Market cap : CoinGecko seul
(les exchanges ne la fournissent pas).

**Note honnête :** Binance peut être restreint selon la juridiction. Le fallback
Coinbase/Kraken n'est pas décoratif, il est réellement câblé dans le registre.

---

## 2. Dérivés

| Source | Statut | Usage | Clé |
|---|---|---|---|
| **Binance Futures** `fapi.binance.com` | 🟢 200 | funding rate, historique funding, open interest, `openInterestHist`, long/short ratio, taker buy/sell | non |
| **Bybit** `api.bybit.com` | 🔑 optionnel | seconde source funding/OI | non |
| **Coinglass** | 🔑 | liquidations agrégées multi-exchanges | `COINGLASS_API_KEY` |

**Liquidations :** Binance a fermé son flux public de liquidations agrégées.
Sans Coinglass, la métrique est marquée `UNAVAILABLE — provider not configured`.
Aucune estimation n'est fabriquée.

**SOL :** funding et OI disponibles sur `SOLUSDT` perpetual. Couverture équivalente à BTC/ETH.

---

## 3. ETF flows

| Source | Statut | Détail |
|---|---|---|
| **Farside Investors** | 🟢 **OPÉRATIONNEL** | 12 ETF BTC depuis 2024-01-11, 10 ETF ETH depuis 2024-07-23 |
| **Import CSV manuel** | 🟢 | `data/imports/etf/*.csv` — voie de secours et correction manuelle |
| **CoinGlass ETF** | 🔑 | `COINGLASS_API_KEY` |
| **SoSoValue** | 🔑 | `SOSOVALUE_API_KEY` |

### Point d'accès — vérification du 2026-09-04

Une première mesure avec le `User-Agent` par défaut de `curl` a renvoyé **HTTP 403**,
ce qui laissait penser à une protection anti-bot. Vérification faite, **le site
répond normalement (HTTP 200)** dès lors que le client s'identifie de façon
descriptive, ce que fait le projet via `HTTP_USER_AGENT`.

Ce n'est **pas** un contournement. Le connecteur :

1. envoie **une seule** requête, avec un `User-Agent` qui nomme honnêtement l'outil
   (même exigence que celle imposée par la SEC sur ses propres flux) ;
2. n'usurpe **jamais** l'identité d'un navigateur, ne fait **aucune** rotation
   d'UA, n'utilise **aucun** proxy, **aucun** navigateur headless, ne résout
   **aucun** challenge ;
3. si le site répond un jour `403` ou sert une page de challenge à cette
   identification honnête, le connecteur se marque `BLOCKED_BY_SOURCE` et
   **s'arrête définitivement** — l'import CSV prend alors le relais.

Données réellement récupérées et vérifiées :

- **BTC** : ARKB, BITB, BRRR, BTC, BTCO, BTCW, EZBC, FBTC, GBTC, HODL, IBIT, MSBT
- **ETH** : ETH, ETHA, ETHB, ETHE, ETHV, ETHW, EZET, FETH, QETH, TETH
- Flux du 2026-09-03 : BTC **+730.8 M$**, ETH **+141.4 M$**

Farside publie également une page « Solana ETF Flow », mais son URL exacte n'a
pas pu être confirmée (les chemins testés renvoient 404). `SOL` reste donc
déclaré sans ETF spot dans `config/assets.yaml` — rien n'est deviné.

### Import CSV (secours et correction manuelle)

Format attendu (`data/imports/etf/`) :

```csv
date,asset,ticker,flow_musd
2026-09-03,BTC,IBIT,412.5
2026-09-03,BTC,FBTC,88.1
2026-09-03,BTC,GBTC,-96.4
2026-09-03,ETH,ETHA,55.2
```

Commande : `make import-etf FILE=data/imports/etf/2026-09.csv`

Tant qu'aucune donnée n'est importée et qu'aucune clé n'est configurée, le
module ETF affiche `UNAVAILABLE`. **Il n'invente jamais un flux.**

---

## 4. On-chain — métriques adaptées par chaîne

Les trois blockchains ont des architectures différentes ; leur appliquer les
mêmes métriques serait une erreur d'analyse.

### Bitcoin (PoW, UTXO)
| Source | Statut | Métriques |
|---|---|---|
| **blockchain.info** | 🟢 200 | tx count 24h, hashrate, difficulty, fees, taille des blocs |
| **Blockchair** | 🟢 200 | adresses actives, tx volume, mempool, UTXO |
| **mempool.space** | 🟢 | fees recommandés, congestion |

Pertinent pour BTC : hashrate, difficulty, âge des UTXO, ratio pièces dormantes.
Non pertinent : « gas », TVL, staking.

### Ethereum (PoS, comptes, EIP-1559)
| Source | Statut | Métriques |
|---|---|---|
| **Blockchair** | 🟢 200 | tx count, adresses actives, fees |
| **beaconcha.in** | 🟢 | validateurs, staking, participation |
| **Etherscan** | 🔑 | `ETHERSCAN_API_KEY` — gas, supply, burn |
| **DeFiLlama** | 🟢 | TVL, DEX volume, fees protocoles |

Pertinent pour ETH : burn EIP-1559, issuance nette, gas, blobs, L2, TVL, staking ratio.
Non pertinent : hashrate, difficulty.

### Solana (PoH + PoS, haut débit)
| Source | Statut | Métriques |
|---|---|---|
| **RPC public** `api.mainnet-beta.solana.com` | 🟠 | epoch, supply, inflation, performance samples — **rate limité, usage parcimonieux** |
| **DeFiLlama** | 🟢 | TVL, DEX volume, fees |
| **Helius / QuickNode / Triton** | 🔑 | RPC fiable — `SOLANA_RPC_URL` |

Pertinent pour SOL : TPS réel (hors votes), priority fees, validateurs, stake activé,
incidents réseau. Le comptage brut de transactions est **trompeur** sur Solana
(les votes des validateurs dominent) — le code sépare explicitement les deux.

---

## 5. DeFi / TVL / Stablecoins / RWA

| Source | Statut | Endpoints |
|---|---|---|
| **DeFiLlama** `api.llama.fi` | 🟢 200 | `/v2/chains`, `/overview/dexs/{chain}`, `/overview/fees/{chain}`, `/protocols` |
| **DeFiLlama Stablecoins** `stablecoins.llama.fi` | 🟢 200 | `/stablecoins`, `/stablecoincharts/{chain}` |
| **DeFiLlama RWA** | 🟢 | catégorie `RWA` de `/protocols` |
| **RWA.xyz** | 🔑 | connecteur optionnel, inscription requise |

DeFiLlama est sans clé et couvre TVL, DEX volumes, fees, stablecoins par chaîne
et RWA. C'est la source la plus rentable du projet.

---

## 6. Macro

| Source | Statut | Données | Clé |
|---|---|---|---|
| **FRED** `api.stlouisfed.org` | 🔑 (gratuite) | DGS2, DGS10, DTWEXBGS, CPIAUCSL, PCEPI, UNRATE, PAYEMS, DFF | `FRED_API_KEY` — gratuite et immédiate |
| **Yahoo Finance** `query1.finance.yahoo.com` | 🟢 | ^GSPC, ^IXIC, ^DJI, DXY, VIX, or, pétrole, 10Y — sans clé |
| **Stooq** `stooq.com` | 🔴 **challenge JS** | Sert une preuve de travail JavaScript aux clients non-navigateur. **Non contourné** — remplacé par Yahoo Finance. |
| **US Treasury** fiscaldata | 🟢 | courbe des taux quotidienne |
| **Calendrier FOMC/CPI** | 🟢 | `config/macro_calendar.yaml` — dates officielles, tenues à jour à la main |

FRED renvoie `400` sans clé (vérifié) — c'est attendu. La clé est **gratuite**
et s'obtient en une minute : https://fredaccount.stlouisfed.org/apikeys
Sans elle : Yahoo Finance assure indices, DXY, VIX et le rendement 10Y ; les
taux directeurs, le CPI, le PCE et l'emploi restent `UNAVAILABLE`.

**Stooq** était la source initialement retenue. Elle renvoie désormais une page
de challenge JavaScript (preuve de travail SHA-256) aux clients non-navigateur.
Résoudre ce challenge serait exactement le type de contournement que ce projet
s'interdit : le connecteur détecte la page, retourne `BLOCKED_BY_SOURCE`, et
Yahoo Finance prend le relais. Le code Stooq est conservé au cas où la politique
du site changerait.

**Calendrier :** un fichier YAML plutôt qu'un scraping. Un chiffre publié dans
20 minutes et un chiffre vieux de 10 jours n'ont pas le même poids — le moteur
calcule `time_to_event` et pondère en conséquence.

---

## 7. Régulation et politique — flux officiels

| Institution | Flux | Statut |
|---|---|---|
| **SEC** | `sec.gov/news/pressreleases.rss` | 🟢 200 (User-Agent obligatoire) |
| **Federal Reserve** | `federalreserve.gov/feeds/press_all.xml` | 🟢 |
| **CFTC** | `cftc.gov/RSS/RSSGP/rssgp.xml` | 🟢 |
| **US Treasury** | `home.treasury.gov/.../press-releases.xml` | 🟢 |
| **White House** | `whitehouse.gov/feed/` | 🟢 |
| **Congress.gov** | API | 🔑 `CONGRESS_API_KEY` (gratuite) — suivi législatif |

La SEC **exige** un `User-Agent` nominatif (politique publique documentée). Il est
configurable via `SEC_USER_AGENT` dans `.env` — c'est une exigence de la source,
pas un contournement.

### Classification du statut juridique — obligatoire

Chaque événement réglementaire est classé, jamais implicitement :

```
ADOPTED · PROPOSED · RUMOR · POLITICAL_STATEMENT
CONSULTATION · VOTE_SCHEDULED · VOTE_HELD · REGULATORY_DECISION
```

Une proposition n'est **jamais** présentée comme une loi adoptée. La
classification s'appuie sur des motifs lexicaux explicites et, en cas de doute,
retourne `UNCERTAIN` plutôt qu'une supposition.

---

## 8. News

| Niveau | Sources | Poids |
|---|---|---|
| **1 — Officiel** | SEC, Fed, CFTC, Treasury, White House | 1.00 |
| **2 — Financier reconnu** | Reuters, Bloomberg, WSJ, FT, CNBC (RSS publics) | 0.80 |
| **3 — Crypto sérieux** | CoinDesk, The Block, Cointelegraph, Decrypt | 0.55 |
| **4 — Autres** | agrégateurs, blogs | 0.25 |

Le moteur **déduplique et cluster par événement** : une news reprise par 30 sites
compte pour **un** signal, dont le poids est celui de la source la plus crédible
du cluster. Un tweet anonyme et une déclaration de la Fed ne pèsent pas pareil,
structurellement.

Uniquement des flux RSS publics — aucun scraping d'article, aucun paywall franchi.

---

## 9. Whales — honnêteté requise

| Source | Statut | Clé |
|---|---|---|
| **Glassnode** | 🔑 | `GLASSNODE_API_KEY` (payant) |
| **CryptoQuant** | 🔑 | `CRYPTOQUANT_API_KEY` (payant) |
| **Nansen** | 🔑 | `NANSEN_API_KEY` (payant) |
| **Arkham** | 🔑 | `ARKHAM_API_KEY` |
| **Heuristique on-chain interne** | 🟠 | BTC/ETH : grosses transactions via Blockchair — **fiabilité faible, marquée comme telle** |

Les connecteurs sont écrits et testés contre des fixtures. Sans abonnement :
`UNAVAILABLE — provider not configured`.

Seuils « whale » définis **par actif** dans `config/assets.yaml` (BTC ≥ 100 BTC,
ETH ≥ 1 000 ETH, SOL ≥ 50 000 SOL) — pas de seuil universel arbitraire.

Tout signal whale porte un `reliability` explicite. **Aucun signal baleine n'est
produit en l'absence de source fiable.**

---

## 10. Récapitulatif — ce qui marche sans aucune clé

✅ Prix, OHLCV, variations, volumes (BTC/ETH/SOL, 5 timeframes)
✅ Toute l'analyse technique et multi-timeframe
✅ Funding, open interest, long/short ratio
✅ TVL, DEX volumes, fees, stablecoins par chaîne, RWA
✅ On-chain BTC (hashrate, difficulty, tx, fees) et ETH (tx, adresses, fees)
✅ Indices macro, DXY, VIX, or, pétrole via Yahoo Finance
✅ **Flux ETF BTC et ETH réels** via Farside (historique complet depuis 2024)
✅ Régulation et news via flux RSS officiels
✅ Scoring, conviction, contradictions, scénarios, rapport complet
✅ Base de connaissances personnelle (RAG local)
✅ MOCK_MODE intégral

🔑 Clés **gratuites** conseillées : `FRED_API_KEY`, `CONGRESS_API_KEY`, `ETHERSCAN_API_KEY`
🔑 Clés **payantes** optionnelles : Glassnode, CryptoQuant, Nansen, Coinglass, SoSoValue
🔴 **Stooq** : challenge anti-bot JavaScript, non contourné (Yahoo Finance utilisé à la place)
🔴 **Liquidations** : aucune source gratuite depuis la fermeture du flux public Binance
