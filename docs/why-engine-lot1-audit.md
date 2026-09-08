# LOT 1 — Audit de l'existant

Relevé du 8 septembre 2026, sur la base de production et le backend en cours
d'exécution. Chaque chiffre vient d'une requête, pas d'une lecture de code.

---

## 1. Architecture actuelle

```
providers/            fetch brut, par capacité, avec chaîne de repli
  ├ market/           binance_spot, coinbase_spot, kraken_spot, coingecko
  ├ derivatives/      binance_futures, multi_exchange (bybit), coinglass*
  ├ etf/              farside, csv_import, coinglass_etf*
  ├ macro/            yahoo_finance, stooq, fred*, alfred*
  ├ onchain/          blockchain_info, blockchair, solana_rpc
  ├ volatility/       deribit (DVOL)
  ├ news/             rss (news + réglementation)
  └ whales/           glassnode*, cryptoquant*, nansen*, arkham*   (* = clé requise)
        ↓
history/store.py      séries longues: candles, derivatives, macro_series
db/repo.py            observations ponctuelles, ETF, snapshots
        ↓
engines/              regime, structure, leverage, volatility, edge, macro,
                      news, onchain, liquidity, market_pressure, entry_*
        ↓
engines/analysis_context.py     AnalysisContextSnapshot + analysis_id
        ↓
engines/today_view.py           projection de la page compacte
        ↓
api/routes_lot4.py /today       payload unique
        ↓
scripts/export_flutter_static_api.py   → app/assets/api_snapshots/*.json
        ↓
Flutter (baseUrl vide → lit les instantanés embarqués)
```

**Cadences** : `market` 5 min, `analysis` 30 min, `decision_track` 30 min,
`ohlcv_sync` 60 min, `derivatives_sync` 60 min, `etf_sync` 240 min,
`evaluate` 60 min, `purge` 1440 min. Le planificateur ne vit que dans le
processus API.

**Hors ligne** : `baseUrl` vide ⇒ l'app lit `assets/api_snapshots/`. Aucun
appel réseau sauf le prix live, qui ouvre directement `wss://ws.kraken.com/v2`.

---

## 2. Inventaire des données (§41)

`STATUS` : OK = dans sa cadence · RETARD = présente mais au-delà · ABSENT =
aucune ligne · N/A = n'existe pas pour cet actif.

### Prix et bougies

| METRIC | SOURCE | ENDPOINT | HISTORY | FRESHNESS | TIMEFRAME | USED_BY | STATUS |
| --- | --- | --- | --- | --- | --- | --- | --- |
| prix live | Kraken WebSocket (app) | `wss://ws.kraken.com/v2` | — | < 1 s | tick | en-tête | OK |
| prix consensus | binance/coinbase/kraken | `/ticker` | — | 60 s cache | tick | `market_data` | OK |
| ohlcv 1w | binance_spot | `/api/v3/klines` | 3 304 j | **8,6 j** | 1W | structure 1S | **RETARD** |
| ohlcv 1d | binance_spot | `/api/v3/klines` | 3 309 j | 14,6 h | 1D | régime, edge | OK |
| ohlcv 4h | binance_spot | `/api/v3/klines` | 1 004 j | 2,6 h | 4H | structure, position, timing | OK |
| ohlcv 1h | binance_spot | `/api/v3/klines` | 420 j | 0,6 h | 1H | timing | OK |
| ohlcv 15m | binance_spot | `/api/v3/klines` | 125 j | **41,1 h** | 15m | page Graphique | **RETARD** |

`ohlcv_sync` ne rafraîchit que 1D/4H/1H. **1W et 15m n'ont aucun travail
planifié.**

### Dérivés

| METRIC | SOURCE | ENDPOINT | HISTORY | FRESHNESS | USED_BY | STATUS |
| --- | --- | --- | --- | --- | --- | --- |
| `funding.rate` | binance_futures | `/fapi/v1/fundingRate` | 2 337 j | 6,6 h (cycle 8 h) | pression, crowding | OK |
| `oi.contracts_bybit` | bybit | `/v5/market/open-interest` | 2 225 j | 14,6 h | pression, crowding | OK |
| `oi.value` | binance_futures | `/futures/data/openInterestHist` | 34 j | 14,6 h | repli OI | OK |
| `derivatives.long_account_share` | binance_futures | `/futures/data/globalLongShortAccountRatio` | **31 j** | 2,6 h | pression dérivés | OK |
| `spot.taker_buy_ratio` | binance_spot | `/api/v3/klines` champ 9 | 3 309 j | 14,6 h | pression spot | OK |
| `spot.net_taker_volume` | binance_spot | idem | 3 309 j | 14,6 h | pression spot | OK |
| `dvol.index` | deribit | `/api/v2/public/get_volatility_index_data` | 1 994 j | 14,6 h | volatilité implicite | OK (BTC/ETH) · N/A SOL |
| liquidations | coinglass | — | 0 | — | — | **ABSENT (clé)** |

### Institutionnel, macro, chaîne

| METRIC | SOURCE | HISTORY | FRESHNESS | USED_BY | STATUS |
| --- | --- | --- | --- | --- | --- |
| `etf_flows` | Farside (scrape) | 7 279 lignes / 966 j | **4,6 j** | pression institutions | RETARD (source) · N/A SOL |
| `macro_series` (10 séries) | Yahoo Finance | 3 650 j chacune | **4,0-4,4 j** | recherche, cross-asset | RETARD |
| `observations:macro.` | Yahoo Finance + fixtures | 354 / 45 j | 0,4 h | `MacroAnalyzer` | **VOIR BUG 1** |
| `observations:onchain.` | blockchain_info, blockchair, solana_rpc | 168 / 45 j | 0,3 h | `OnChainAnalyzer` | **VOIR BUG 1** |
| `observations:stablecoin.` | defillama_stables | 648 / 45 j | 0,3 h | liquidité | **VOIR BUG 1** |
| `observations:whale.` | — | **0** | — | pression baleines | **ABSENT (payant)** |
| calendrier macro | `config/macro_calendar.yaml` | 8 événements | tenu à la main | catalyseurs | OK |
| news RSS | SEC/Fed/CFTC (t1), Reuters/CNBC (t2), CoinDesk/TheBlock/Cointelegraph (t3) | 48 h glissantes | 0,4 h | **rien** | **VOIR BUG 3** |

**Cache** : binance 120-3 600 s selon l'unité, coingecko 600 s (8 req/min),
farside 21 600 s, deribit 3 600 s, defillama 1 800 s.

**Repli** : chaîne par capacité dans `config/providers.yaml`. Une capacité sans
provider disponible produit `UNAVAILABLE`, jamais une valeur estimée.

---

## 3. Bugs, par gravité

### BUG 1 — le filtre anti-mock aveugle trois familles entières

`_is_synthetic()` renvoie `True` dès qu'**une seule** observation de la liste
porte une source de fixtures, et l'appelant vide alors **toute** la liste.

```
famille        total  réelles  mock   effet
onchain.         168      144    24   978 observations réelles
stablecoin.      648      576    72   jetées à cause de
macro.           354      258    96   192 lignes de fixtures
```

Ces 192 lignes viennent d'un ancien passage en `MOCK_MODE`. Conséquence
mesurée : `macro_context.available = false` avec pour motif
« set FRED_API_KEY », alors que 258 observations Yahoo Finance réelles sont
présentes et que `MacroAnalyzer` les traite correctement quand on les lui passe
seules (`available: True`, `rates_trend` et `dollar_trend` renseignés).

**Le correctif est de filtrer les lignes synthétiques, pas la famille.**
La règle « aucune donnée fictive hors MOCK_MODE » est respectée dans les deux
cas ; la version actuelle y ajoute une perte de données réelles.

*Je m'étais trompé dans mon premier diagnostic : j'avais annoncé que
`MacroAnalyzer` lisait la mauvaise table. Il lit la bonne ; c'est l'appelant
qui lui retire ses entrées.*

### BUG 2 — mélange de devises à l'écran (§15)

| Affiché | Valeur | Échelle réelle |
| --- | --- | --- |
| en-tête | 67 559 € | EUR |
| bas / haut de range 4H | 62 626 / 81 376 | USD |
| support / résistance | 76 944 / 79 383 | USD |
| prix d'analyse | 78 636 | USD |

Un support s'affiche **au-dessus** du prix de l'en-tête. Tout le calcul
technique est en BTCUSDT ; seul le prix passe en EUR, à l'affichage.

### BUG 3 — le moteur de news n'atteint jamais la page

`NewsEngine` existe, tourne, agrège quatre flux officiels et cinq flux médias,
regroupe les doublons et marque les opinions. La clé `news` est **absente du
payload `/today`**. Câblage manquant, pas capacité manquante.

### BUG 4 — 1W et 15m ne sont jamais rafraîchies

`job_ohlcv_sync` couvre 1D, 4H et 1H. La bougie hebdomadaire (8,6 j) alimente
la ligne « 1S » de la structure ; la 15 minutes (41,1 h) alimente la page
Graphique.

### BUG 5 — textes anglais résiduels (§33)

Tous issus des champs `name` des facteurs et des `interpretation` des moteurs :

| Actuel | Où |
| --- | --- |
| `Higher timeframe structure` | titre de facteur positif |
| `Structural location` | titre de facteur négatif |
| `volatility compressed` | `entry_opportunity.factors[].name` |
| `crowding LOW (28/100) from funding_stretch, oi_percentile` | `crowding.interpretation` |
| `REINTEGRATION to the up through 81375.745, 28 bar(s) ago` | `breakout.interpretation` |
| `funding … sits at the 45th percentile of 2338 days` | `funding.note` |

### BUG 6 — objet JSON rendu brut (§34) — **corrigé**

`{detail: ..., title: ...}` s'affichait littéralement. Régression du commit
`6e98cef` : j'avais structuré les conditions côté backend et laissé le lecteur
Dart interpoler chaque élément avec `'$item'`, ce qui appelle `toString()` sur
une Map. Corrigé dans `c5e71c5`, avec un test qui lit les fichiers livrés.

---

## 4. Données manquantes

| Besoin | État | Ce qu'il faudrait |
| --- | --- | --- |
| flux baleines / exchanges (§22) | **ABSENT** | Glassnode, CryptoQuant ou Nansen — abonnement |
| liquidations (§19) | **ABSENT** | clé Coinglass |
| probabilités implicites de taux (§4) | **ABSENT** | CME FedWatch — le récupérer supposerait de contourner une protection anti-bot, ce que tu as interdit |
| skew, put/call, term structure (§21) | **ABSENT** | Deribit expose les options par instrument ; à construire |
| CVD intrabar (§18) | **ABSENT** | trades tick par tick ; volumineux |
| rendement 2Y en série longue | partiel | présent en observations, pas dans `macro_series` |

---

## 5. Récupérable sans nouveau fournisseur

Vérifié en base, disponible aujourd'hui :

| Pour | Données présentes |
| --- | --- |
| Biais Fed (§4, §36) | `macro.us10y` 4,784 % **+12,4 bp sur 20 j**, `macro.us5y`, `macro.us13w`, `macro.dxy` 99,16 (−0,44 % / 20 j), `macro.vix` 14,53, et en observations `macro.cpi`, `macro.fed_funds_rate`, `macro.us2y`, `macro.unemployment`, `macro.yield_curve_10y2y` |
| Déduplication news (§30) | `NewsEngine.cluster()` par similarité de titres, déjà écrit |
| Pertinence par actif (§29) | `detect_assets()` par article — à transformer en score 0-100 |
| Rumeur vs fait (§5) | `is_official`, `is_opinion`, `tier` déjà portés par chaque item |
| Spot en percentile (§18) | 3 309 j de `spot.taker_buy_ratio` |
| Dérivés enrichis (§19) | OI, variation OI, funding, `long_account_share`, crowding |
| Volatilité implicite (§21) | 1 994 j de DVOL, BTC et ETH |
| Position et niveaux (§11, §12) | range 4H validé, clusters de swings avec distances |

**La lecture Fed que tu décris au §36 est calculable aujourd'hui.** Ce qui ne
l'est pas, c'est « X % de probabilité de baisse » : je peux mesurer la
*direction* des anticipations via les rendements, pas une probabilité
implicite. Ton §37 couvre déjà ce cas.

---

## 6. Ordre proposé pour le LOT 2

1. **BUG 1** — filtrer les lignes synthétiques au lieu de la famille. Débloque
   978 observations réelles et rend le macro disponible, ce dont dépendent les
   LOT 4 et 5.
2. **BUG 2** — une seule couche de conversion, tous les niveaux affichés dans
   la devise choisie ; calcul interne en USDT.
3. **BUG 4** — 1W et 15m dans `job_ohlcv_sync`.
4. **BUG 5** — traduction à la source des `name` et `interpretation`.
5. **§19** — supprimer la règle « prix ↑ + OI ↑ = nouveaux longs » au profit
   d'une classification prix + OI + funding + comptes + crowding.

Rien de tout cela ne demande un nouveau fournisseur.

---

## 7. Ce que je n'ai pas vérifié

- Le rendu visuel : je ne peux pas voir l'application tourner.
- Les fuseaux horaires des événements du calendrier au-delà de la lecture du
  YAML (déclarés en UTC, non confrontés à une source officielle).
- La justesse des données Farside au-delà de leur fraîcheur.
