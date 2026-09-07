# Dynamic UI Integration Report

Hotfix applique le 2026-09-07.

## 1. Origine exacte du BTC 52 840 EUR

La valeur venait de `app/lib/screens/today_screen.dart`, classe `_AssetMeta`,
methode `forAsset`. Elle etait codee directement dans le frontend avec les prix
ETH/SOL et les variations 24h visuelles. Elle ne provenait ni d'un provider, ni
de `/api/today/BTC`, ni d'un endpoint prix.

## 2. Pourquoi elle etait affichee

La route `/api/today/{asset}` ne renvoyait que l'analyse: direction, edge,
crowding, leverage, funding, volatilite et incertitude. La carte Flutter avait
donc complete visuellement l'en-tete avec des metadonnees statiques.

## 3. Hardcodes trouves et corriges

- Prix visuels BTC/ETH/SOL dans `_AssetMeta`
- Variations 24h visuelles BTC/ETH/SOL dans `_AssetMeta`
- Objectifs/invalidation de la page Graphique
- Fallback OHLCV synthetique du chart painter
- Label "Action recommandee", remplace par "Opportunite d'entree"

## 4. Snapshots trouves

`app/assets/static_api/*.json` sert de fallback Vercel lorsque aucun backend
public n'est configure. Le client marque alors `DataOrigin.snapshot`; l'UI
affiche une banniere et ne presente pas les donnees comme live. Un snapshot sans
date est maintenant considere `age inconnu` et perime.

## 5. Fallbacks trouves

- Fallback snapshot dans `ApiClient._tryStaticSnapshot`
- Fallback UI analytique: `INDISPONIBLE`, `DONNEES INSUFFISANTES`, ou message
  d'erreur; aucun chiffre de marche n'est fabrique.
- Fallback chart: etat vide quand les bougies OHLCV reelles sont absentes.

## 6. Architecture live actuelle

Provider `market.ticker` -> `ProviderRegistry` -> `MarketPriceSnapshot` ->
`/api/market/price/{asset}` et `/api/today/{asset}.market_data` -> Flutter
`MarketPriceRead` -> ecrans Aujourd'hui et Marches.

La methode USD est une mediane robuste des providers configures
Binance/Coinbase/Kraken quand ils repondent. Le 24h vient du ticker provider
qui expose explicitement `price.change_24h_pct`; il n'est pas confondu avec la
variation d'une bougie journaliere.

## 7. Architecture Vercel

Le build Vercel statique ne peut pas joindre un backend local Debian/Tailscale
si aucune URL publique securisee n'est fournie via `API_BASE_URL`. Dans ce cas,
l'app lit les snapshots embarques et l'indique comme hors ligne/snapshot. Elle
ne pretend pas etre live.

## 8. Providers utilises

- USD spot: chaine `market.ticker` configuree dans `config/providers.yaml`
  (`binance_spot`, `coinbase_spot`, `kraken_spot`)
- EUR spot: paire directe Coinbase EUR quand disponible
- FX affiche: taux implique par le prix EUR Coinbase direct contre le consensus
  USD; si indisponible, l'UI affiche USD

## 9. Freshness Policy

Le backend utilise `core.freshness.compute_freshness`, qui applique des seuils
par classe de metrique: prix, derivatives, ETF, macro, on-chain, etc. Le
frontend lit `status`, `freshness`, `as_of` et `age_seconds`.

## 10. Pages auditees

Aujourd'hui, Marches, Graphique, Rapport, Recherche, Connaissances et les bottom
sheets/actions visibles.

## 11. Champs connectes

Prix, variation 24h, direction, edge, crowding, leverage, funding, volatilite,
incertitude, structure multi-timeframe, OHLCV, ranges, patterns, entry
opportunity, sections rapport, recherche et connaissances sont relies aux
payloads backend existants.

## 12. Champs indisponibles

EUR reste indisponible si Coinbase EUR ne repond pas. SOL DVOL reste
indisponible lorsqu'aucune source reelle n'existe. Les objectifs graphiques sont
indisponibles tant qu'un engine ne fournit pas de target explicite.

## 13. Feature -> API -> UI

Voir `docs/feature-ui-coverage.md`.

## 14. Tests ajoutes

- Tests backend du snapshot prix robuste
- Test API `/today` avec contrat `market_data`
- Tests Flutter de parsing `MarketPriceRead`
- Test de garde-fou contre prix/variations frontend hardcodes
- Test de garde-fou contre graphiques OHLCV synthetiques

## 15. Bugs trouves

- Prix/24h hardcodes dans Aujourd'hui
- Titre "temps reel" visible en mode snapshot
- Extraction de prix qui prenait `4` depuis `4h`
- Graphique pouvant dessiner une serie artificielle

## 16. Bugs corriges

Tous les points ci-dessus sont corriges dans ce hotfix.

## 17. Validation visuelle

Validation demandee: relancer l'app web Flutter, tester la navigation mobile,
scroll, taps, refresh, badges de freshness, chart OHLCV et etats indisponibles.
Les commandes exactes de verification sont conservees dans le retour final.

## 18. Limitations restantes

- Le vrai live Vercel depend d'un `API_BASE_URL` public et securise.
- Les pages Recherche/Connaissances rendent les payloads backend disponibles,
  mais certains blocs restent vides si LOT 6B n'a pas encore produit de donnees.
- Pattern geometry avancee reste limitee par ce que `/api/chart` et
  `/api/structure` exposent deja; aucun dessin de figure n'est invente.

