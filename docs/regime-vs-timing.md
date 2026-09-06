# Régime de marché et timing d'entrée

Deux questions différentes, deux réponses indépendantes.

| | Question | Échelle | Horizon |
|---|---|---|---|
| **Market regime** | « Dans quel sens penche ce marché ? » | STRONGLY_BEARISH → STRONGLY_BULLISH | jours à semaines |
| **Entry timing** | « Est-ce un bon moment maintenant ? » | VERY_UNFAVORABLE → VERY_FAVORABLE | heures à jours |

Le cas qui justifie la séparation :

```
ETH
Market regime : STRONGLY_BULLISH
Entry timing  : WAIT

→ tendance daily haussière, flux ETF positifs,
  mais RSI 1H élevé, funding tendu, prix à +5 % de son EMA20,
  résistance à 2 % au-dessus.
```

Fusionner ces deux axes en un seul score détruirait exactement l'information
utile.

---

## MarketRegimeEngine

Multi-facteurs par construction. « Prix au-dessus de l'EMA200 » ne dit rien de
la volatilité, du levier ni de la participation, et étiquette un range comme un
marché haussier.

**Axe directionnel** (pondéré) : tendance daily (×2.0), tendance weekly (×2.5),
structure de marché (×1.5), position vs EMA200 (×1.5), RSI daily (×1.0), flux
ETF (×1.8), liquidité stablecoin (×1.0), appétit macro (×1.2).

**Axe caractère** (non directionnel) : `VOLATILITY_EXPANSION`,
`VOLATILITY_COMPRESSION`, `RANGE`, `RISK_ON`, `RISK_OFF`, `DELEVERAGING`,
`LEVERAGE_BUILDUP`, `OVERHEATED`, `CAPITULATION`, `LIQUIDITY_EXPANSION`,
`LIQUIDITY_CONTRACTION`.

Un marché peut être `BULLISH` **et** `OVERHEATED`. Chaque facteur expose sa
contribution et son poids — le panneau WHY ? les affiche tous.

Un domaine sans données ne vote pas : il figure dans `missing` plutôt que de
compter comme neutre, ce qui tirerait tous les régimes vers NEUTRAL à mesure
que des sources tombent.

---

## EntryTimingEngine

Onze familles de facteurs, entièrement déterministes, calculées avant toute
intervention du LLM :

1. RSI court terme (1h/4h, poids 2.0) — le contrôle « suis-je en train de courir après le mouvement ? »
2. RSI daily (1.2)
3. Distance à l'EMA20 (1.8) — acheter à +12 % de sa moyenne est structurellement moins bon
4. Position dans les bandes de Bollinger (1.2)
5. Proximité résistance / support (1.6 / 1.4)
6. Confirmation par le volume (1.0)
7. Volatilité (1.0) — un ATR élevé élargit tout stop
8. Divergences (1.3)
9. Funding et open interest (1.7 / 1.0)
10. Flux ETF (1.2)
11. Position dans le range (1.2)

### Les événements macro imminents sont un plafond, pas un terme

Un CPI dans 2h est appliqué **après** la moyenne pondérée, comme une borne
supérieure :

```python
if imminent_penalty is not None:
    score = min(score, imminent_penalty) - 5.0
```

Raison : à l'intérieur d'une moyenne, un facteur à −45 peut **remonter** un
score déjà à −47. Un CPI imminent améliorerait alors le timing — l'inverse de ce
qu'il doit faire. Ce défaut a été trouvé par un test et corrigé.

### Bougie en cours

La dernière bougie est presque toujours incomplète. Son volume est une
accumulation partielle : à 05:00 UTC, une bougie daily contient un cinquième
d'une journée. Le facteur volume est donc **exclu** tant que la bougie n'est pas
à 95 %, et l'exclusion est signalée dans `missing`.

Sans cette correction, le timing était pénalisé à tort chaque matin.

### Sorties

- `timing_score` −100 → +100 et son étiquette
- `confidence`, dérivée de la couverture des facteurs
- facteurs positifs et négatifs, avec leur contribution
- risques explicites
- **zones à surveiller**, toujours dérivées de niveaux calculés (clustering de
  swings, moyennes mobiles) — jamais un objectif de prix arbitraire
- niveau d'invalidation, avec sa justification
- `explanation` : le détail de l'arithmétique, affiché dans le panneau WHY ?

---

## Seuils

```
Regime :  ≥ +55 STRONGLY_BULLISH · ≥ +20 BULLISH · −20..+20 NEUTRAL
          ≤ −20 BEARISH · ≤ −55 STRONGLY_BEARISH

Timing :  ≥ +45 VERY_FAVORABLE · ≥ +15 FAVORABLE · −15..+15 WAIT
          ≤ −15 UNFAVORABLE · ≤ −45 VERY_UNFAVORABLE
```
