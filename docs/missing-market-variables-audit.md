# MISSING_MARKET_VARIABLES_AUDIT

**Date** : 14/09/2026 · **Méthode** : inventaire des séries réellement présentes
en base (`observations`), croisé avec les providers déclarés et les variables
demandées au §58.

**Constat qui conditionne tout le reste** : `FRED_API_KEY` **n'est pas
configurée**. Le provider FRED déclare donc `UNAVAILABLE` pour ses 18 séries — y
compris celles que ce lot ajoute. Les variables accessibles sans clé (Yahoo,
Stooq) fonctionnent, elles.

## Ce qui est réellement en base aujourd'hui

| métrique | observations | provider sans clé ? |
|---|---|---|
| `macro.oil_wti` | 96 | **oui** (Yahoo `CL=F`, Stooq `cl.f`) |
| `macro.dxy` | 95 | oui (Yahoo) |
| `macro.gold` | 96 | oui |
| `macro.vix` | 81 | oui |
| `macro.sp500` / `macro.nasdaq` | 78 | oui |
| `macro.us10y_yahoo` | 69 | oui (`^TNX`) |
| `macro.dow` | 68 | oui |
| `macro.cpi`, `macro.us2y`, `macro.us10y`, `macro.fed_funds_rate`, `macro.unemployment`, `macro.yield_curve_10y2y` | 10 chacune | non — FRED, backfill historique seulement |

## Variables auditées (§58)

| variable | disponible ? | source actuelle | source idéale | impact | coût | fréquence | priorité | famille |
|---|---|---|---|---|---|---|---|---|
| Fed / taux directeur | partiel | FRED `DFF`, 10 obs | FRED | élevé | clé gratuite | quotidien | **1** | Macro |
| Probabilités de taux | **non** | — | CME FedWatch | très élevé | **licence payante** | quotidien | 2 | Macro |
| US 2Y | partiel | FRED `DGS2` | FRED | élevé | clé gratuite | quotidien | **1** | Macro |
| US 10Y | oui | Yahoo `^TNX` (69 obs) | FRED + Yahoo | élevé | nul | quotidien | ok | Macro |
| US 30Y | **non** | — | FRED `DGS30` *(ajouté)* | moyen | clé gratuite | quotidien | 2 | Macro |
| DXY | oui | Yahoo | Yahoo | moyen | nul | quotidien | ok | Macro |
| WTI | oui | Yahoo, Stooq (96 obs) | idem | élevé | nul | quotidien | ok | Macro |
| Brent | **non** | — | FRED `DCOILBRENTEU` *(ajouté)* | moyen | clé gratuite | quotidien | 3 | Macro |
| Variation pétrole 7j/30j | calculable | dérivable de `macro.oil_wti` | idem | élevé | nul | quotidien | **1** | Macro |
| **Spreads crédit haut rendement** | **non** | — | FRED `BAMLH0A0HYM2` *(ajouté)* | **très élevé** | clé gratuite | quotidien | **1** | Macro |
| Spreads qualité investissement | **non** | — | FRED `BAMLC0A0CM` *(ajouté)* | élevé | clé gratuite | quotidien | 2 | Macro |
| CPI | partiel | FRED, 10 obs | FRED + BLS | élevé | clé gratuite | mensuel | 2 | Macro |
| PCE | **non** en base | FRED déclaré | FRED | élevé | clé gratuite | mensuel | 2 | Macro |
| PPI | **non** | — | FRED `PPIACO` *(ajouté)* | moyen | clé gratuite | mensuel | 3 | Macro |
| Emploi | partiel | FRED `UNRATE` | FRED + BLS | moyen | clé gratuite | mensuel | 3 | Macro |
| Résultats / guidance / CapEx | **non** | — | calendriers officiels | moyen | à instruire | trimestriel | 4 | Macro |
| ETF BTC / ETH | oui | Farside | Farside | élevé | nul | quotidien | ok | Flux |
| ETF SOL | **non** | — | Farside si publié | moyen | nul | quotidien | 3 | Flux |
| Stablecoins | oui | DefiLlama | idem | moyen | nul | quotidien | ok | Flux |
| Réglementation US | oui | Congress, Senate, SEC, CFTC | idem | élevé | nul | continu | ok | Catalyseurs |
| Géopolitique | partiel | flux de presse | primaires | moyen | nul | continu | 3 | Catalyseurs |
| Incidents exchange | partiel | status pages | idem | moyen | nul | continu | 3 | Catalyseurs |
| Mises à jour protocole | oui | blogs officiels | idem | moyen | nul | continu | ok | Catalyseurs |

## Priorité 1 — ce qui débloquerait le plus

**Configurer `FRED_API_KEY`** (gratuite, inscription en ligne). Un seul geste
rend disponibles : les spreads de crédit, le 30 ans, le Brent, le PPI, et
rafraîchit CPI/PCE/2Y/10Y qui n'ont que 10 observations chacune.

Les spreads de crédit sont la variable la plus rentable du lot : sans eux, le
système ne peut pas distinguer une correction d'un stress systémique. C'est
exactement le test du §52, et il n'a aujourd'hui aucune donnée pour tourner en
production.

**Calculer les variations du pétrole.** `macro.oil_wti` a 96 observations : les
variations 7 j et 30 j sont dérivables immédiatement, sans nouvelle source. Elles
sont ce qui distingue « pétrole élevé » de « pétrole +20 % », et le moteur
d'interprétation les attend déjà.

## Ce qui n'a pas été ajouté, et pourquoi

Rien n'a été ajouté « parce qu'un analyste en parle » (§59). Les six séries
retenues le sont parce qu'elles alimentent une chaîne d'interprétation
identifiée : énergie → inflation → politique monétaire → rendements →
conditions financières, et crédit comme étape de confirmation du risque.

Les probabilités de taux CME restent hors d'atteinte : licence commerciale.
Pistes sous licence propre à instruire, non implémentées : Kalshi (marché
réglementé CFTC, API publique) et le *Survey of Primary Dealers* de la NY Fed.
