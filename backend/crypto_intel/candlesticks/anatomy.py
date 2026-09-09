"""Les parties mesurables d'un chandelier.

Toutes les définitions de ce module reposent sur cinq quantités et rien
d'autre : le corps, les deux ombres, l'amplitude totale, et la position du
corps dans cette amplitude. Les nommer une fois évite que chaque détecteur
recalcule « une ombre longue » à sa façon.

Deux normalisations coexistent, et le choix entre elles est délibéré :

* **en part de l'amplitude** pour tout ce qui décrit la FORME de la bougie —
  un doji est un doji parce que son corps est petit *par rapport à sa propre
  amplitude*, pas par rapport à la volatilité du marché ;
* **en ATR** pour tout ce qui décrit la TAILLE — « une longue bougie » ne veut
  rien dire sans échelle, et 2 % est énorme en quinze minutes, négligeable en
  hebdomadaire.

Confondre les deux est l'erreur classique : un doji reste un doji qu'il soit
grand ou petit, mais trois soldats blancs minuscules ne sont pas trois
soldats blancs.
"""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd


@dataclass(slots=True, frozen=True)
class Candle:
    """Une bougie et ses proportions, calculées une fois."""

    open: float
    high: float
    low: float
    close: float

    @property
    def body(self) -> float:
        return abs(self.close - self.open)

    @property
    def range(self) -> float:
        return self.high - self.low

    @property
    def upper_shadow(self) -> float:
        return self.high - max(self.open, self.close)

    @property
    def lower_shadow(self) -> float:
        return min(self.open, self.close) - self.low

    @property
    def bullish(self) -> bool:
        return self.close > self.open

    @property
    def bearish(self) -> bool:
        return self.close < self.open

    @property
    def body_top(self) -> float:
        return max(self.open, self.close)

    @property
    def body_bottom(self) -> float:
        return min(self.open, self.close)

    @property
    def midpoint(self) -> float:
        """Le milieu du CORPS, pas de l'amplitude.

        C'est celui qu'utilisent les définitions du perçant et du couvert:
        « clôture au-delà du milieu du corps précédent ».
        """
        return (self.open + self.close) / 2

    def body_ratio(self) -> float:
        """Part de l'amplitude occupée par le corps, entre 0 et 1.

        Une amplitude nulle — les quatre prix identiques — n'est pas un doji
        parfait mais une bougie sans information. On renvoie 1 pour qu'elle ne
        déclenche aucune figure de petit corps.
        """
        if self.range <= 0:
            return 1.0
        return self.body / self.range

    def upper_ratio(self) -> float:
        return self.upper_shadow / self.range if self.range > 0 else 0.0

    def lower_ratio(self) -> float:
        return self.lower_shadow / self.range if self.range > 0 else 0.0


def candle_at(frame: pd.DataFrame, index: int) -> Candle:
    """La bougie à cette position, en objet mesurable."""
    row = frame.iloc[index]
    return Candle(
        open=float(row["open"]),
        high=float(row["high"]),
        low=float(row["low"]),
        close=float(row["close"]),
    )


#: Sur combien de barres on regarde la tendance qui précède une figure.
#:
#: Cinq barres: assez pour qu'une direction se dessine, assez peu pour que la
#: figure soit un retournement de ce mouvement-là et non d'un autre.
TREND_LOOKBACK = 5

#: De combien le prix doit avoir bougé, en ATR, pour qu'on parle de tendance.
#:
#: Sans ce seuil, toute dérive de bruit compterait, et « marteau » et « pendu »
#: seraient attribués au hasard — ce qui reviendrait à ne pas les distinguer.
TREND_MIN_ATR = 1.0


def prior_trend(frame: pd.DataFrame, index: int, atr: float) -> str:
    """« UP », « DOWN » ou « NONE » avant la barre `index`.

    Ne regarde que des barres STRICTEMENT antérieures. Inclure la barre de la
    figure ferait dépendre le contexte de la figure elle-même, ce qui est
    circulaire — et sur une longue bougie, décisif.
    """
    if atr <= 0 or index <= 0:
        return "NONE"
    start = index - TREND_LOOKBACK
    if start < 0:
        return "NONE"
    before = float(frame["close"].iloc[start])
    until = float(frame["close"].iloc[index - 1])
    move = (until - before) / atr
    if move >= TREND_MIN_ATR:
        return "UP"
    if move <= -TREND_MIN_ATR:
        return "DOWN"
    return "NONE"
