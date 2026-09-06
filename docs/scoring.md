# Scoring et conviction

## Convention

Chaque domaine produit un score de **−100 à +100** :

```
-100  très négatif        0  neutre / indéterminé       +100  très positif
```

Mais un score seul ne veut rien dire. Chaque `ScoreCard` porte aussi :

| Champ | Rôle |
|---|---|
| `confidence` | 0–100, à quel point cette lecture est fiable |
| `freshness` | fraîcheur de la pire preuve utilisée |
| `evidence_count` | nombre de faits sur lesquels elle repose |
| `available` | si `false`, poids **exactement nul** |

## La confiance est dérivée, jamais déclarée

```python
confidence = base × facteur_preuves × facteur_fraîcheur − pénalités
```

- 0 preuve → confiance 0
- fraîcheur `UNAVAILABLE` → confiance 0
- volume de preuves à rendements décroissants (10 points suffisent)
- données `STALE` → forte décote
- timeframes en désaccord → pénalité de 15 points sur la technique

Un domaine avec une seule donnée périmée **ne peut pas** afficher 90 % de confiance.

## La conviction n'est pas une moyenne

```
poids_effectif = poids_actif × f(confiance) × g(fraîcheur) × h(horizon)
```

Effet mesuré sur un cas réel :

| Domaine | Score | Confiance | Poids effectif |
|---|---|---|---|
| ETF | +72 | 91 % | **0.2406** |
| Whales | +90 | 20 % | **0.0014** |

Le signal whale, pourtant plus élevé, pèse **170 fois moins**. C'est exactement
l'exigence : *un signal +90 avec 20 % de confiance ne doit pas dominer l'analyse.*

## Trois horizons séparés

Un RSI 15 minutes et une décision du FOMC n'agissent pas sur la même échelle de
temps ; les mélanger produirait une bouillie inutile aux deux horizons.

| Domaine | Court (1h–24h) | Moyen (jours–semaines) | Long (semaines–mois) |
|---|---|---|---|
| Technique | 1.40 | 1.00 | 0.65 |
| Dérivés | 1.35 | 0.95 | 0.40 |
| News | 1.30 | 0.75 | 0.30 |
| ETF | 0.85 | 1.30 | 1.35 |
| Macro | 0.60 | 1.15 | 1.40 |
| Régulation | 0.50 | 1.00 | 1.45 |

## Pondérations par actif

Elles diffèrent volontairement — les trois actifs n'ont pas les mêmes moteurs :

```yaml
BTC:  etf 0.24 · macro 0.14 · technical 0.18   # demande institutionnelle dominante
ETH:  etf 0.15 · onchain 0.16 · defi 0.10      # burn, staking, L2, TVL
SOL:  etf 0.00 · technical 0.26 · onchain 0.20 # pas d'ETF spot US
```

`SOL.etf = 0` signifie que le domaine est **exclu du calcul**, pas qu'il vaut zéro.

## Effet des contradictions

Les conflits ne sont jamais absorbés par une moyenne :

| Force du conflit | Effet |
|---|---|
| ≥ 40 | score ×0.8, confiance ×0.85 |
| ≥ 65 | score ×0.5, confiance ×0.7, signalé `capped_by_contradiction` |

Exemple constaté : conviction moyenne **+35.2 → +17.6** en présence de signaux
fortement contradictoires. La direction reste la même ; c'est l'engagement qui
diminue.

## Étiquettes

```
-100 … -60  STRONGLY BEARISH        +8 … +25   SLIGHTLY BULLISH
 -60 … -25  BEARISH                +25 … +60   BULLISH
 -25 …  -8  SLIGHTLY BEARISH       +60 … +100  STRONGLY BULLISH
  -8 …  +8  NEUTRAL
```

`INCONCLUSIVE` est distinct de `NEUTRAL` : « nous ne pouvons pas conclure »
n'est pas la même affirmation que « le marché est équilibré ».

## Probabilités des scénarios

Les probabilités des scénarios sont dérivées de la conviction et de la confiance
par une heuristique. Elles sont donc systématiquement présentées comme
**« probabilité analytique indicative »**, jamais comme une statistique calibrée.
Seul un modèle réellement backtesté pourrait poser `calibrated=True`.
