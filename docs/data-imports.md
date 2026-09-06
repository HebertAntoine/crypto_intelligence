# Imports manuels de données

Certaines séries ne sont pas accessibles gratuitement avec assez de profondeur.
Ces chemins d'import permettent d'apporter des données auxquelles tu as
légitimement accès, sans contourner aucune limitation de fournisseur.

---

## Open interest

**Pourquoi.** Binance publie ~30 jours d'historique d'open interest. C'est
insuffisant pour les études d'événements et l'analyse des interactions
prix × OI × funding, qui retournent `INSUFFICIENT_DATA` en conséquence.

**Où.** `data/imports/open_interest/*.csv`

**Format.**

```csv
date,asset,open_interest_usd
2024-01-15,BTC,18420000000
2024-01-16,BTC,18755000000
2024-01-15,ETH,7210000000
```

- `date` — `YYYY-MM-DD`, timestamp ISO, ou epoch (secondes ou millisecondes)
- `asset` — `BTC`, `ETH` ou `SOL`
- `open_interest_usd` — open interest notionnel en dollars

**Commande.** `make import-oi`

**Comportement.** Une cellule vide est traitée comme une donnée manquante,
jamais comme zéro. Les lignes sont upsertées par `(asset, metric, timestamp)` :
réimporter le même fichier corrige au lieu de dupliquer.

**Provenance.** Les lignes importées portent `source = "csv:<fichier>"`, les
lignes live portent `source = "binance_futures"`. Une étude peut donc
distinguer les deux origines.

---

## Flux ETF

**Où.** `data/imports/etf/*.csv`

```csv
date,asset,ticker,flow_musd
2026-09-03,BTC,IBIT,454.0
2026-09-03,BTC,GBTC,8.2
```

**Commande.** `make import-etf`

Voie de secours et de correction manuelle : le connecteur Farside fonctionne,
mais un import permet de corriger une valeur ou de couvrir une interruption.

---

## Ce que ces imports ne font pas

Ils ne contournent aucune protection, aucun paywall et aucune limite d'API. La
fenêtre de 30 jours de Binance est respectée telle que publiée ; ces chemins
existent pour que tu puisses verser des données que tu as déjà le droit
d'utiliser.
