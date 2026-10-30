# Registre des sources de données

Date de contrôle : 2026-10-30

## Lecture du registre

« Adaptateur enregistré » signifie que le code et la capacité existent. « Actif » dépend des clés, droits, quotas, réponses réseau et réglages de l'hôte. Aucun fournisseur externe n'a été déclaré opérationnel uniquement parce que son adaptateur compile.

## Marché et crypto

| Capacité | Chaîne de production | Clé | Cadence applicative | Usage et limites |
|---|---|---:|---:|---|
| Ticker crypto | Binance → Coinbase → Kraken | Non | 5 min | Prix rapide backend ; Flutter possède en plus un flux Kraken de présentation. |
| OHLCV crypto | Binance → Kraken | Non | 60 min, 15m/1h/4h/1d/1w | Le stockage peut mettre à jour une barre en formation; lectures, métadonnées et indicateurs n'exposent que les bougies closes à `as_of`. Aucune bougie manquante n'est synthétisée. |
| Capitalisation/global | CoinGecko Pro | Clé + droit commercial + attribution | Cache 10 min | Désactivé tant que les trois conditions ne sont pas remplies; clé envoyée par en-tête, jamais dans l'URL. |
| Breadth | CoinGecko Pro breadth | Clé + droit commercial + attribution | Avec collecte marché | Même garde de droits que CoinGecko; calcul interne à partir des actifs disponibles. |
| Funding/OI/ratios | Binance Futures | Non pour endpoints publics | 60 min | Unités Binance et Bybit restent séparées lorsqu'elles diffèrent. |
| Liquidations | Coinglass | Oui | Selon pipeline | Indisponible sans clé. |
| Volatilité crypto | Deribit | Non | 60 min | DVOL BTC/ETH seulement ; rien n'est inventé pour SOL. |
| DeFi/TVL/DEX/frais/RWA | DeFiLlama | Non | Selon TTL | Source spécialiste, quotas et attribution à surveiller. |
| Stablecoins | DeFiLlama | Non | 60 min TTL | Encours, pas automatiquement un flux net. |
| On-chain BTC | blockchain.info → Blockchair | Selon provider | 15 min TTL | Donnée native/spécialiste. |
| On-chain ETH | Blockchair → Etherscan | Etherscan oui | 15 min TTL | Fallback conditionnel. |
| On-chain SOL | Solana RPC | Endpoint recommandé | 15 min TTL | RPC public fortement limité. |

## Macro et inter-marchés

| Capacité | Source | Clé/droit | Fréquence naturelle | État de production |
|---|---|---|---|---|
| Séries macro US | FRED API | Clé + autorisation de contenu documentée | Quotidienne à mensuelle | Désactivée sans `FRED_CONTENT_USE_AUTHORIZED`; tiers ICE/Cboe filtrés sans autorisation additionnelle. |
| Rendements US | U.S. Treasury | Non | Jours ouvrés | Source officielle directe. |
| TGA | U.S. Treasury | Non | Quotidienne | Source officielle directe. |
| RRP | New York Fed | Non | Quotidienne | Source officielle directe. |
| Bilan Fed | Federal Reserve H.4.1 | Non | Hebdomadaire | Source officielle directe. |
| Inflation/emploi | BLS | Non | Hebdo/mensuelle | Source officielle ; calendrier séparé. |
| PCE/claims/WALCL | FRED CSV | Autorisation FRED documentée | Hebdo/mensuelle | Lags de disponibilité conservateurs; aucun appel sans `FRED_CONTENT_USE_AUTHORIZED`. |
| Crédit ICE BofA | FRED API/CSV | Autorisations FRED + tiers explicites | Quotidienne | Désactivé sans les deux drapeaux de droits. |
| Indices US/JP/EU, VIX, EUR/USD, USD/JPY | Twelve Data | Clé + droit explicite | Quotidienne | Seule chaîne `macro.indices`; désactivée par défaut. |
| Taux BCE/BoJ/Fed | Sources banques centrales | Non | Calendrier | Adaptateurs officiels. |
| Yahoo Finance / Stooq | Adaptateurs legacy | Droits non établis | — | Hors chaîne de production et hors preuves décisionnelles. |

Twelve Data conserve le fuseau d'échange, l'observation du bar quotidien et une disponibilité conservatrice au lendemain local. Comme la réponse ne fournit pas une heure de publication distincte, `publication_time` reste nulle.

## Événements et documents

| Domaine | Sources configurées | Condition |
|---|---|---|
| Banques centrales | Fed, BCE, BoJ | Calendriers/publications officiels. |
| Statistiques US | BLS, BEA | Calendriers officiels. |
| Dette US | TreasuryDirect | Calendrier/adjudications officielles. |
| Réglementation | SEC, CFTC, House, Senate, Congress.gov | Congress requiert une clé ; toute URL SEC est ignorée sans `SEC_USER_AGENT` contenant un vrai contact. |
| Entreprises | SEC EDGAR | Dépôts officiels; désactivé sans contact SEC valide; pas encore de panel S13 normalisé. |
| FedWatch | API CME licenciée | URL et clé requises ; aucun scraping de la page. |
| Protocoles | dépôts Ethereum/Solana, blogs/statut officiels | Propositions et incidents conservent leur statut. |
| Géopolitique | flux configurés | Fait, déclaration, négociation et rumeur restent distincts. |
| News | RSS Reuters/CNBC/CoinDesk/The Block/Cointelegraph/Decrypt | Métadonnées et liens ; pas de scraping de paywall. |

## Flux institutionnels, ETF et baleines

| Capacité | Source | État par défaut |
|---|---|---|
| ETF spot | Farside → Coinglass → SoSoValue → CSV local | Farside peut bloquer l'automatisation ; providers payants exigent clé ; CSV refuse fixtures/exemples en production. |
| Flux hebdomadaires | CoinShares | Adaptateur présent ; droit de republication à confirmer. |
| Whale analytics | Glassnode, CryptoQuant, Nansen, Arkham | Indisponibles sans abonnement/clé. |
| Grosses transactions | Whale Alert | Indisponible sans clé. |

## Clés et variables

- accès conditionnel : `FRED_API_KEY`, `CONGRESS_API_KEY`, `ETHERSCAN_API_KEY` ; une clé FRED ne lève pas le garde-fou de contenu ;
- commerciales/licenciées : `TWELVE_DATA_API_KEY`, `COINGECKO_API_KEY`, `CME_FEDWATCH_API_KEY`, `COINGLASS_API_KEY`, `SOSOVALUE_API_KEY`, `GLASSNODE_API_KEY`, `CRYPTOQUANT_API_KEY`, `NANSEN_API_KEY`, `ARKHAM_API_KEY`, `WHALE_ALERT_API_KEY` ;
- garde-fous de droits : `TWELVE_DATA_REDISTRIBUTION_AUTHORIZED`, `COINGECKO_COMMERCIAL_USE_AUTHORIZED`, `COINGECKO_ATTRIBUTION_CONFIGURED`, `FRED_CONTENT_USE_AUTHORIZED`, `FRED_THIRD_PARTY_REDISTRIBUTION_AUTHORIZED` ;
- identité obligatoire : `SEC_USER_AGENT` avec adresse de contact non factice ;
- endpoints : `CME_FEDWATCH_API_URL`, `SOLANA_RPC_URL`, `ETH_RPC_URL`.

Une variable vide produit `UNAVAILABLE` ou `NOT_CONFIGURED`. Elle ne déclenche aucune fixture en production.

## Provenance minimale

Chaque mesure utilisée doit permettre de retrouver provider, source, URL, instant observé, instant récupéré, unité et qualité. Les nouvelles séries Twelve Data ajoutent aussi symbole, valeur originale/normalisée, devise, fréquence, calendrier, fuseau, état de licence et flags de validation. Chaque `MacroVintageRow` conserve désormais sa propre source, son provider, son unité, son URL, sa licence, ses métadonnées, son instant de publication et son état de disponibilité; une ligne legacy n'utilise les champs de la série courante que pour les colonnes historiquement nulles. Cette richesse n'est pas encore uniforme sur tous les anciens providers ; c'est une limite documentée, pas une raison pour fabriquer les champs.
