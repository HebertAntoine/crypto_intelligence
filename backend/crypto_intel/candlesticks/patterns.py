"""Les détecteurs de figures de chandeliers.

Chaque définition se calcule sur l'OHLC seul, sans jugement. Là où la
littérature dit « petit corps » ou « longue ombre », un seuil est déclaré en
haut de ce module plutôt qu'enfoui dans une fonction — pour qu'il puisse être
discuté, versionné, et un jour mesuré.

Deux écarts assumés par rapport aux définitions classiques, tous deux dus au
marché sur lequel nous travaillons :

**Les gaps n'existent pas en crypto.** L'étoile du matin classique exige un
trou de cotation entre la première et la deuxième bougie, puis un autre entre
la deuxième et la troisième. Sur un marché ouvert 24 h sur 24, la clôture d'une
barre est l'ouverture de la suivante : ces trous ne se produisent qu'à la
faveur d'un mouvement violent. Exiger le gap ne trouverait presque rien. Il est
donc **facultatif, mais enregistré** : `components["gapped"]` dit si le trou
était là, et on pourra un jour mesurer si sa présence change quoi que ce soit.

**Le contexte fait partie de la définition.** Un marteau et un pendu ont
exactement la même forme. Sans tendance préalable mesurée, on ne peut nommer ni
l'un ni l'autre — la bougie est alors décrite mais pas nommée, et aucune figure
n'est émise. C'est volontaire : inventer un nom sur la moitié d'une définition
serait pire que de ne rien dire.

Rien ici ne prédit. `recognition_confidence` dit à quel point la bougie
correspond à sa définition, jamais ce que le prix fera ensuite.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

import pandas as pd

from ..logging_setup import get_logger
from .anatomy import Candle, candle_at, prior_trend
from .taxonomy import (
    DETECTOR_VERSION,
    NEEDS_PRIOR_TREND,
    PATTERN_BARS,
    PATTERN_FAMILY,
    CandlestickPattern,
)

log = get_logger("candlesticks.patterns")

# --- seuils, tous déclarés ici --------------------------------------------

#: Au-dessous de cette part de l'amplitude, le corps est « inexistant ».
DOJI_BODY_RATIO = 0.10
#: Au-dessous de cette part, le corps est « petit » sans être un doji.
SMALL_BODY_RATIO = 0.34
#: Une ombre est « longue » à partir de cette part de l'amplitude.
LONG_SHADOW_RATIO = 0.60
#: Une ombre est « négligeable » en dessous de cette part.
SHORT_SHADOW_RATIO = 0.15
#: Part de l'amplitude à partir de laquelle une ombre est pleinement
#: convaincante. Sert à noter la toupie, dont les deux ombres comptent.
CONVINCING_SHADOW_RATIO = 0.30
#: Un marubozu n'a presque pas d'ombre, des deux côtés.
MARUBOZU_SHADOW_RATIO = 0.05
#: Taille minimale d'un corps « long », en ATR. Une figure de continuation
#: faite de trois bougies minuscules ne dit rien.
LONG_BODY_ATR = 0.5
#: Un corps « petit » au sens de la taille, pour l'étoile centrale.
STAR_BODY_ATR = 0.35
#: De combien la clôture doit dépasser le milieu du corps précédent.
PENETRATION_RATIO = 0.5
#: Part maximale du corps précédent qu'un harami peut occuper.
#:
#: « Harami » veut dire « enceinte »: la seconde bougie est nettement plus
#: petite, pas seulement contenue. Sans ce seuil, un couvert sombre dont la
#: seconde bougie tient dans la première était capté comme un harami — les
#: deux définitions se recouvraient et la première écrite gagnait.
HARAMI_MAX_BODY_RATIO = 0.5

DEFAULT_MIN_CONFIDENCE = 55.0


@dataclass(slots=True)
class CandlestickDetection:
    """Une figure de chandeliers, à un instant précis.

    Délibérément distinct de `StructuralPattern`: les deux familles ne se
    mélangent pas, et un type commun inviterait à les agréger.
    """

    pattern: CandlestickPattern
    #: Instant de la DERNIÈRE bougie de la figure — le moment où elle devient
    #: reconnaissable. Une figure de trois barres n'existe pas à la première.
    detected_at: datetime
    #: Les bougies qui composent la figure, de la plus ancienne à la dernière.
    bar_times: list[datetime]
    recognition_confidence: float
    prior_trend: str
    components: dict[str, Any] = field(default_factory=dict)
    detector_version: str = DETECTOR_VERSION

    @property
    def family(self) -> str:
        return PATTERN_FAMILY[self.pattern].value

    @property
    def bars(self) -> int:
        return PATTERN_BARS[self.pattern]

    def to_dict(self) -> dict[str, Any]:
        return {
            "pattern": self.pattern.value,
            "taxonomy": "CANDLESTICK_PATTERN",
            "family": self.family,
            "bars": self.bars,
            "detected_at": self.detected_at.isoformat(),
            "bar_times": [when.isoformat() for when in self.bar_times],
            "recognition_confidence": round(self.recognition_confidence, 1),
            "prior_trend": self.prior_trend,
            "components": self.components,
            "detector_version": self.detector_version,
            "edge_state": "NOT_YET_TESTED",
            "separation_note": (
                "A candlestick pattern is not a chart structure and the two "
                "must never be aggregated: one spans a bar, the other spans "
                "hundreds. recognition_confidence describes how cleanly the "
                "candles match the definition, never a price outcome."
            ),
        }


def _score(*parts: float) -> float:
    """La confiance est la moyenne de ses parties nommées, comme ailleurs."""
    values = [max(0.0, min(1.0, part)) for part in parts]
    return round(sum(values) / len(values) * 100, 1) if values else 0.0


def _trend_ok(pattern: CandlestickPattern, trend: str) -> bool:
    """La tendance préalable est-elle celle que la définition exige ?"""
    required = NEEDS_PRIOR_TREND.get(pattern)
    return required is None or trend == required


# --- figures d'une barre ---------------------------------------------------


def _single_bar(candle: Candle, trend: str) -> tuple[CandlestickPattern, float, dict] | None:
    # Quatre prix identiques n'est pas un doji parfait ni un marubozu: c'est
    # une barre sans information. `body_ratio()` renvoie 1 dans ce cas, ce qui
    # satisfaisait par accident la condition du marubozu.
    if candle.range <= 0:
        return None
    body_ratio = candle.body_ratio()
    upper, lower = candle.upper_ratio(), candle.lower_ratio()
    parts = {"body_ratio": round(body_ratio, 3),
             "upper_ratio": round(upper, 3), "lower_ratio": round(lower, 3)}

    if body_ratio <= DOJI_BODY_RATIO:
        # Un doji dont toute l'amplitude est sous le corps: libellule.
        if lower >= LONG_SHADOW_RATIO and upper <= SHORT_SHADOW_RATIO:
            return CandlestickPattern.DRAGONFLY_DOJI, _score(
                1 - body_ratio / DOJI_BODY_RATIO, lower), parts
        if upper >= LONG_SHADOW_RATIO and lower <= SHORT_SHADOW_RATIO:
            return CandlestickPattern.GRAVESTONE_DOJI, _score(
                1 - body_ratio / DOJI_BODY_RATIO, upper), parts
        return CandlestickPattern.DOJI, _score(1 - body_ratio / DOJI_BODY_RATIO), parts

    if body_ratio >= 1 - 2 * MARUBOZU_SHADOW_RATIO and \
            upper <= MARUBOZU_SHADOW_RATIO and lower <= MARUBOZU_SHADOW_RATIO:
        pattern = (CandlestickPattern.MARUBOZU_BULLISH if candle.bullish
                   else CandlestickPattern.MARUBOZU_BEARISH)
        return pattern, _score(body_ratio), parts

    if body_ratio <= SMALL_BODY_RATIO:
        # Corps en haut, longue ombre basse: marteau ou pendu selon la tendance.
        if lower >= LONG_SHADOW_RATIO and upper <= SHORT_SHADOW_RATIO:
            # Même forme, deux noms. Sans tendance mesurée, on ne peut nommer
            # ni l'un ni l'autre: on se tait plutôt que de tirer au sort.
            if trend == "DOWN":
                return (CandlestickPattern.HAMMER,
                        _score(lower, 1 - body_ratio / SMALL_BODY_RATIO), parts)
            if trend == "UP":
                return (CandlestickPattern.HANGING_MAN,
                        _score(lower, 1 - body_ratio / SMALL_BODY_RATIO), parts)
            return None
        # Corps en bas, longue ombre haute.
        if upper >= LONG_SHADOW_RATIO and lower <= SHORT_SHADOW_RATIO:
            if trend == "DOWN":
                return (CandlestickPattern.INVERTED_HAMMER,
                        _score(upper, 1 - body_ratio / SMALL_BODY_RATIO), parts)
            if trend == "UP":
                return (CandlestickPattern.SHOOTING_STAR,
                        _score(upper, 1 - body_ratio / SMALL_BODY_RATIO), parts)
            return None
        # Petit corps, deux ombres notables: toupie.
        if upper >= SHORT_SHADOW_RATIO and lower >= SHORT_SHADOW_RATIO:
            # La qualité d'une toupie tient à deux choses: un corps petit, et
            # DEUX ombres franches. On note la plus courte des deux, rapportée
            # au seuil où elle est pleinement convaincante — un corps interdit
            # structurellement aux deux ombres de valoir la moitié chacune.
            return CandlestickPattern.SPINNING_TOP, _score(
                1 - body_ratio / SMALL_BODY_RATIO,
                min(upper, lower) / CONVINCING_SHADOW_RATIO), parts
    return None


# --- figures de deux barres ------------------------------------------------


def _two_bars(
    first: Candle, second: Candle, trend: str, atr: float
) -> tuple[CandlestickPattern, float, dict] | None:
    if atr <= 0:
        return None
    parts = {
        "first_body_atr": round(first.body / atr, 3),
        "second_body_atr": round(second.body / atr, 3),
    }

    engulfs = (second.body_top >= first.body_top
               and second.body_bottom <= first.body_bottom
               and second.body > first.body)
    inside = (second.body_top <= first.body_top
              and second.body_bottom >= first.body_bottom
              and first.body > 0
              and second.body / first.body <= HARAMI_MAX_BODY_RATIO)

    # L'englobante exige deux corps de sens opposés, et un second qui couvre
    # réellement le premier. Sans le second point, toute grande bougie après
    # une petite deviendrait une englobante.
    if engulfs and first.bearish and second.bullish and trend == "DOWN":
        return CandlestickPattern.BULLISH_ENGULFING, _score(
            min(1.0, second.body / max(first.body, 1e-9) - 1),
            min(1.0, second.body / atr)), parts
    if engulfs and first.bullish and second.bearish and trend == "UP":
        return CandlestickPattern.BEARISH_ENGULFING, _score(
            min(1.0, second.body / max(first.body, 1e-9) - 1),
            min(1.0, second.body / atr)), parts

    if inside and first.bearish and second.bullish and trend == "DOWN":
        return CandlestickPattern.BULLISH_HARAMI, _score(
            1 - second.body / max(first.body, 1e-9), min(1.0, first.body / atr)), parts
    if inside and first.bullish and second.bearish and trend == "UP":
        return CandlestickPattern.BEARISH_HARAMI, _score(
            1 - second.body / max(first.body, 1e-9), min(1.0, first.body / atr)), parts

    # Perçant et couvert: la clôture doit dépasser le MILIEU du corps
    # précédent, sans le couvrir entièrement — sinon c'est une englobante.
    if first.bearish and second.bullish and trend == "DOWN" \
            and first.body / atr >= LONG_BODY_ATR:
        penetration = ((second.close - first.close)
                       / max(first.body, 1e-9))
        if PENETRATION_RATIO <= penetration < 1.0:
            parts["penetration"] = round(penetration, 3)
            return CandlestickPattern.PIERCING_LINE, _score(penetration), parts
    if first.bullish and second.bearish and trend == "UP" \
            and first.body / atr >= LONG_BODY_ATR:
        penetration = ((first.close - second.close)
                       / max(first.body, 1e-9))
        if PENETRATION_RATIO <= penetration < 1.0:
            parts["penetration"] = round(penetration, 3)
            return CandlestickPattern.DARK_CLOUD_COVER, _score(penetration), parts
    return None


# --- figures de trois barres -----------------------------------------------


def _three_bars(
    first: Candle, second: Candle, third: Candle, trend: str, atr: float
) -> tuple[CandlestickPattern, float, dict] | None:
    if atr <= 0:
        return None
    parts = {
        "first_body_atr": round(first.body / atr, 3),
        "star_body_atr": round(second.body / atr, 3),
        "third_body_atr": round(third.body / atr, 3),
    }

    long_first = first.body / atr >= LONG_BODY_ATR
    long_third = third.body / atr >= LONG_BODY_ATR
    small_star = second.body / atr <= STAR_BODY_ATR

    if long_first and small_star and long_third:
        # Le gap est facultatif — voir la docstring du module — mais consigné.
        if first.bearish and third.bullish and trend == "DOWN":
            recovered = ((third.close - first.close) / max(first.body, 1e-9))
            if recovered >= PENETRATION_RATIO:
                parts["recovered"] = round(recovered, 3)
                parts["gapped"] = bool(second.body_top < first.body_bottom)
                return CandlestickPattern.MORNING_STAR, _score(
                    recovered, 1 - second.body / atr / max(STAR_BODY_ATR, 1e-9)), parts
        if first.bullish and third.bearish and trend == "UP":
            recovered = ((first.close - third.close) / max(first.body, 1e-9))
            if recovered >= PENETRATION_RATIO:
                parts["recovered"] = round(recovered, 3)
                parts["gapped"] = bool(second.body_bottom > first.body_top)
                return CandlestickPattern.EVENING_STAR, _score(
                    recovered, 1 - second.body / atr / max(STAR_BODY_ATR, 1e-9)), parts

    # Soldats et corbeaux: trois longs corps de même sens, chacun progressant.
    bodies = [first, second, third]
    if all(c.body / atr >= LONG_BODY_ATR for c in bodies):
        if all(c.bullish for c in bodies) and \
                first.close < second.close < third.close and \
                second.open <= first.body_top and third.open <= second.body_top:
            return CandlestickPattern.THREE_WHITE_SOLDIERS, _score(
                *[min(1.0, c.body / c.range if c.range > 0 else 0) for c in bodies]), parts
        if all(c.bearish for c in bodies) and \
                first.close > second.close > third.close and \
                second.open >= first.body_bottom and third.open >= second.body_bottom:
            return CandlestickPattern.THREE_BLACK_CROWS, _score(
                *[min(1.0, c.body / c.range if c.range > 0 else 0) for c in bodies]), parts
    return None


def detect_at(
    frame: pd.DataFrame,
    index: int,
    atr: float,
    min_confidence: float = DEFAULT_MIN_CONFIDENCE,
) -> list[CandlestickDetection]:
    """Toutes les figures qui se terminent à la barre `index`.

    Ne lit jamais au-delà de `index`. Une figure de trois barres se reconnaît
    à sa troisième bougie et pas avant — c'est ce qui rend le résultat
    utilisable comme observation datée.
    """
    if index < 0 or index >= len(frame):
        return []
    trend = prior_trend(frame, index, atr)
    when = frame.index[index].to_pydatetime()
    found: list[CandlestickDetection] = []

    def add(result, bars: int) -> None:
        if result is None:
            return
        pattern, confidence, parts = result
        if confidence < min_confidence or not _trend_ok(pattern, trend):
            return
        found.append(CandlestickDetection(
            pattern=pattern, detected_at=when,
            bar_times=[frame.index[index - offset].to_pydatetime()
                       for offset in reversed(range(bars))],
            recognition_confidence=confidence, prior_trend=trend,
            components=parts,
        ))

    add(_single_bar(candle_at(frame, index), trend), 1)
    if index >= 1:
        add(_two_bars(candle_at(frame, index - 1), candle_at(frame, index),
                      trend, atr), 2)
    if index >= 2:
        add(_three_bars(candle_at(frame, index - 2), candle_at(frame, index - 1),
                        candle_at(frame, index), trend, atr), 3)
    return found
