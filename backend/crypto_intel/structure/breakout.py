"""Où passe la frontière d'une figure, et ce que le prix en a fait.

Trois familles n'avaient aucun niveau de déclenchement — triangles, biseaux,
drapeaux — et ne pouvaient donc structurellement jamais être confirmées. Sur
BTC en quotidien, douze figures sur 95 sortaient en `NO_TRIGGER_DEFINED`.

Deux idées gouvernent ce module.

**Une frontière n'est pas toujours un prix.** La borne haute d'un triangle
descend, celle d'un biseau monte, une neckline d'épaule-tête-épaule peut
pencher. Les réduire à une horizontale prise au dernier chandelier donnerait un
niveau juste aujourd'hui et faux demain — et un backtest les évaluerait contre
un prix que le lecteur n'aurait jamais vu. `BreakoutBoundary` porte donc soit
un prix constant, soit une droite, et sait répondre `price_at(instant)` dans
les deux cas.

**Une mèche n'est pas une cassure.** Le prix traverse une frontière en séance
bien plus souvent qu'il ne clôture au-delà. Confondre les deux gonflerait le
taux de confirmation de chaque figure sans qu'aucune règle n'ait changé. Les
deux événements sont distincts, nommés, et une mèche ne devient jamais une
confirmation.

Rien ici n'entre dans `recognition_confidence`. La frontière se déduit de la
géométrie connue à la détection; ce que le prix a fait ensuite est un
**résultat**, calculé séparément et jamais réinjecté dans le score.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import Any

import pandas as pd

from ..logging_setup import get_logger
from .geometry import PatternGeometry

log = get_logger("structure.breakout")

#: De combien une clôture doit dépasser la frontière pour compter.
#:
#: En ATR, pas en pourcentage: le même dépassement doit vouloir dire la même
#: chose sur BTC en hebdomadaire et sur SOL en quinze minutes. Zéro
#: accepterait un dépassement d'un centième, ce qui est du bruit de cotation.
BREAKOUT_BUFFER_ATR = 0.15

#: À quelle distance de la frontière le prix est considéré « dessus » sans
#: l'avoir franchie — l'état d'attente.
PROXIMITY_ATR = 0.5

#: À quelle distance un retour vers la frontière compte comme un retest.
RETEST_PROXIMITY_ATR = 0.35

#: Combien de barres après la cassure on cherche un retest avant d'abandonner.
RETEST_WINDOW_BARS = 12

#: Sur combien de barres une figure reste jugeable, en multiple de sa propre
#: taille.
#:
#: Sans borne, on évalue sur tout l'historique restant: sur neuf ans, le prix
#: finit par franchir n'importe quel niveau, et 37 % des figures sortaient
#: « invalidées » pour un mouvement survenu des années plus tard. Une figure
#: qui n'a rien produit dans un multiple de sa propre durée n'a rien produit.
HORIZON_MULTIPLE = 3
MIN_HORIZON_BARS = 20
MAX_HORIZON_BARS = 250


class BoundaryType(StrEnum):
    """Une frontière est un prix, ou une droite."""

    HORIZONTAL = "HORIZONTAL"
    LINE = "LINE"


class BreakSide(StrEnum):
    """De quel côté une cassure se produit."""

    ABOVE = "ABOVE"
    BELOW = "BELOW"


class BreakoutState(StrEnum):
    """Où en est la cassure — distinct de l'état de la figure.

    Une énumération nouvelle parce qu'aucune n'existait: `PatternStatus`
    décrit le cycle de vie de la figure, pas le détail de ce qui se passe à sa
    frontière. Les deux axes sont volontairement séparés — une figure peut
    être invalidée sans qu'aucune cassure n'ait eu lieu.
    """

    #: Le détecteur n'a fourni aucune frontière exploitable.
    NO_TRIGGER_DEFINED = "NO_TRIGGER_DEFINED"
    #: Frontière connue, prix loin de celle-ci.
    NO_BREAKOUT = "NO_BREAKOUT"
    #: Le prix est collé à la frontière sans l'avoir franchie en clôture.
    POTENTIAL = "POTENTIAL"
    #: Une mèche a traversé; aucune clôture au-delà. Ce n'est pas une cassure.
    WICK_ONLY = "WICK_ONLY"
    #: Une clôture a dépassé la frontière du tampon requis.
    CLOSE_CONFIRMED = "CLOSE_CONFIRMED"
    #: Le prix est repassé de l'autre côté après avoir cassé.
    FAILED_BREAKOUT = "FAILED_BREAKOUT"
    #: L'invalidation a été atteinte avant toute cassure.
    INVALIDATED_FIRST = "INVALIDATED_FIRST"


@dataclass(slots=True, frozen=True)
class BreakoutBoundary:
    """La frontière qu'une cassure doit franchir.

    Elle porte ses deux extrémités même quand elle est horizontale: cela
    permet de la dessiner sans cas particulier, et de prolonger une droite
    au-delà de son dernier point sans avoir à savoir laquelle on tient.
    """

    role: str
    kind: BoundaryType
    side: BreakSide
    start_time: datetime
    start_price: float
    end_time: datetime
    end_price: float

    def price_at(self, when: datetime) -> float:
        """Le niveau à franchir à cet instant.

        Une droite est prolongée au-delà de son dernier point: c'est ce que
        fait un opérateur qui trace une borne de triangle, et sans quoi une
        cassure survenue après le dernier pivot serait jugée contre un niveau
        périmé.
        """
        if self.kind is BoundaryType.HORIZONTAL:
            return self.start_price
        span = (self.end_time - self.start_time).total_seconds()
        if span <= 0:
            return self.end_price
        elapsed = (when - self.start_time).total_seconds()
        slope = (self.end_price - self.start_price) / span
        return self.start_price + slope * elapsed

    def to_dict(self) -> dict[str, Any]:
        return {
            "role": self.role,
            "type": self.kind.value,
            "side": self.side.value,
            "start_time": self.start_time.isoformat(),
            "start_price": round(self.start_price, 8),
            "end_time": self.end_time.isoformat(),
            "end_price": round(self.end_price, 8),
        }


@dataclass(slots=True)
class BreakoutOutcome:
    """Ce que le prix a fait de la frontière. Un fait, pas un avantage."""

    state: BreakoutState
    boundary: BreakoutBoundary | None = None
    level_at_event: float | None = None
    event_time: datetime | None = None
    bars_to_event: int | None = None
    #: Une mèche vue avant toute clôture au-delà. Enregistrée séparément: elle
    #: dit que le niveau a été touché, jamais qu'il a été cassé.
    first_wick_time: datetime | None = None
    #: Le retour sur la frontière après cassure, s'il a eu lieu.
    #:
    #: Un fait annexe et non un état: le prix revient presque toujours frôler
    #: sa frontière dans les barres qui suivent, et laisser cela écraser
    #: `CLOSE_CONFIRMED` effaçait l'information principale — qu'une clôture
    #: avait bien franchi le niveau.
    retest_time: datetime | None = None
    retest_held: bool | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "state": self.state.value,
            "boundary": self.boundary.to_dict() if self.boundary else None,
            "level_at_event": self.level_at_event,
            "event_time": self.event_time.isoformat() if self.event_time else None,
            "bars_to_event": self.bars_to_event,
            "first_wick_time": (
                self.first_wick_time.isoformat() if self.first_wick_time else None
            ),
            "retest_time": self.retest_time.isoformat() if self.retest_time else None,
            "retest_held": self.retest_held,
            "note": (
                "A close beyond the boundary by the ATR buffer, never a wick. "
                "This is what price did, not evidence that the figure predicts."
            ),
        }


def boundaries_for(
    pattern_name: str,
    geometry: PatternGeometry,
    direction: str,
) -> list[BreakoutBoundary]:
    """Les frontières d'une figure, déduites de sa seule géométrie.

    Aucune invention: si le détecteur n'a pas publié de quoi tracer une
    frontière, la liste est vide et la figure reste `NO_TRIGGER_DEFINED`. Une
    frontière fabriquée serait pire qu'aucune — elle donnerait des
    confirmations mesurées contre un niveau que personne n'a décidé.
    """
    neckline = geometry.neckline
    if neckline is not None:
        # Retournements: la neckline est la frontière, inclinée ou non.
        side = BreakSide.BELOW if direction == "BEARISH" else BreakSide.ABOVE
        horizontal = abs(neckline.end.price - neckline.start.price) < 1e-9
        return [BreakoutBoundary(
            role="neckline",
            kind=BoundaryType.HORIZONTAL if horizontal else BoundaryType.LINE,
            side=side,
            start_time=neckline.start.time, start_price=neckline.start.price,
            end_time=neckline.end.time, end_price=neckline.end.price,
        )]

    lines = {line.role: line for line in geometry.trend_lines}
    upper, lower = lines.get("upper"), lines.get("lower")
    if upper is not None and lower is not None:
        # Triangles et biseaux: deux bornes ajustées, toutes deux inclinées.
        #
        # Un triangle symétrique peut casser des deux côtés: on rend les deux
        # frontières et l'évaluation retient celle que le prix franchit en
        # premier. Choisir un côté d'avance serait un pari, pas une mesure.
        boundaries = [
            BreakoutBoundary(
                role="upper", kind=BoundaryType.LINE, side=BreakSide.ABOVE,
                start_time=upper.start.time, start_price=upper.start.price,
                end_time=upper.end.time, end_price=upper.end.price,
            ),
            BreakoutBoundary(
                role="lower", kind=BoundaryType.LINE, side=BreakSide.BELOW,
                start_time=lower.start.time, start_price=lower.start.price,
                end_time=lower.end.time, end_price=lower.end.price,
            ),
        ]
        if direction == "BULLISH":
            return [boundaries[0]]
        if direction == "BEARISH":
            return [boundaries[1]]
        return boundaries

    consolidation = next(
        (zone for zone in geometry.zones if zone.role == "consolidation"), None
    )
    if consolidation is not None:
        # Drapeaux: la cassure sort de la consolidation, dans le sens du mât.
        #
        # Horizontale et non ajustée: nos détecteurs ne tracent pas les deux
        # bornes du canal du drapeau. Une droite inclinée déduite de deux
        # points arbitraires serait une invention.
        above = direction == "BULLISH"
        level = consolidation.high if above else consolidation.low
        return [BreakoutBoundary(
            role="flag_top" if above else "flag_bottom",
            kind=BoundaryType.HORIZONTAL,
            side=BreakSide.ABOVE if above else BreakSide.BELOW,
            start_time=consolidation.start_time, start_price=level,
            end_time=consolidation.end_time, end_price=level,
        )]

    return []


def _crossed_on_close(
    boundary: BreakoutBoundary, level: float, close: float, buffer: float
) -> bool:
    if boundary.side is BreakSide.ABOVE:
        return close > level + buffer
    return close < level - buffer


def _touched_by_wick(
    boundary: BreakoutBoundary, level: float, high: float, low: float
) -> bool:
    if boundary.side is BreakSide.ABOVE:
        return high > level
    return low < level


def horizon_for(bars_span: int) -> int:
    """Combien de barres une figure reste jugeable après sa détection."""
    return int(min(MAX_HORIZON_BARS, max(MIN_HORIZON_BARS, bars_span * HORIZON_MULTIPLE)))


def evaluate_breakout(
    boundaries: list[BreakoutBoundary],
    forward: pd.DataFrame,
    atr: float,
    invalidation_level: float | None = None,
    direction: str = "NEUTRAL",
    bars_span: int = 0,
) -> BreakoutOutcome:
    """Ce qui est arrivé à la frontière, barre par barre après la détection.

    `forward` ne doit contenir que des barres POSTÉRIEURES à la détection.
    L'appelant en est responsable: passer la série complète ferait juger une
    figure sur des bougies qui n'existaient pas quand elle a été reconnue.

    L'évaluation s'arrête après `horizon_for(bars_span)` barres. Au-delà, ce
    que fait le prix ne parle plus de la figure.
    """
    if not boundaries:
        return BreakoutOutcome(state=BreakoutState.NO_TRIGGER_DEFINED)
    if forward is None or forward.empty or atr <= 0:
        return BreakoutOutcome(state=BreakoutState.NO_BREAKOUT, boundary=boundaries[0])

    horizon = horizon_for(bars_span)
    forward = forward.iloc[:horizon]
    if forward.empty:
        return BreakoutOutcome(state=BreakoutState.NO_BREAKOUT, boundary=boundaries[0])

    buffer = atr * BREAKOUT_BUFFER_ATR
    first_wick: tuple[datetime, BreakoutBoundary, int] | None = None
    closest: tuple[float, BreakoutBoundary] | None = None

    for offset, (when, bar) in enumerate(forward.iterrows(), start=1):
        close = float(bar["close"])
        high, low = float(bar["high"]), float(bar["low"])

        # L'invalidation d'abord: si elle est atteinte avant toute cassure, la
        # figure a échoué et ce qui suit ne la concerne plus.
        if invalidation_level is not None:
            broke_invalidation = (
                close > invalidation_level if direction == "BEARISH"
                else close < invalidation_level
            )
            if direction not in ("BULLISH", "BEARISH"):
                broke_invalidation = False
            if broke_invalidation:
                return BreakoutOutcome(
                    state=BreakoutState.INVALIDATED_FIRST,
                    boundary=boundaries[0],
                    level_at_event=invalidation_level,
                    event_time=when, bars_to_event=offset,
                    first_wick_time=first_wick[0] if first_wick else None,
                )

        for boundary in boundaries:
            level = boundary.price_at(when)
            if _crossed_on_close(boundary, level, close, buffer):
                outcome = BreakoutOutcome(
                    state=BreakoutState.CLOSE_CONFIRMED,
                    boundary=boundary, level_at_event=level,
                    event_time=when, bars_to_event=offset,
                    first_wick_time=first_wick[0] if first_wick else None,
                )
                _look_for_retest(outcome, forward.iloc[offset:], boundary, atr)
                return outcome
            if first_wick is None and _touched_by_wick(boundary, level, high, low):
                first_wick = (when, boundary, offset)
            distance = abs(close - level) / atr
            if closest is None or distance < closest[0]:
                closest = (distance, boundary)

    if first_wick is not None:
        when, boundary, offset = first_wick
        return BreakoutOutcome(
            state=BreakoutState.WICK_ONLY,
            boundary=boundary,
            level_at_event=boundary.price_at(when),
            event_time=when,
            bars_to_event=offset,
            first_wick_time=when,
        )
    if closest is not None and closest[0] <= PROXIMITY_ATR:
        return BreakoutOutcome(state=BreakoutState.POTENTIAL, boundary=closest[1])
    return BreakoutOutcome(
        state=BreakoutState.NO_BREAKOUT, boundary=boundaries[0]
    )


def _look_for_retest(
    outcome: BreakoutOutcome,
    after: pd.DataFrame,
    boundary: BreakoutBoundary,
    atr: float,
) -> None:
    """Le prix est-il revenu sur la frontière, et l'a-t-il tenue ?

    Volontairement minimal: on note le retour et, s'il échoue, on requalifie
    la cassure. Le suivi complet — combien de fois, avec quelle qualité —
    appartient à la phase de mesure, pas à la détection.
    """
    if after is None or after.empty:
        return
    window = after.iloc[:RETEST_WINDOW_BARS]
    for when, bar in window.iterrows():
        level = boundary.price_at(when)
        close = float(bar["close"])
        returned = (
            float(bar["low"]) <= level + atr * RETEST_PROXIMITY_ATR
            if boundary.side is BreakSide.ABOVE
            else float(bar["high"]) >= level - atr * RETEST_PROXIMITY_ATR
        )
        if not returned:
            continue
        outcome.retest_time = when
        held = close > level if boundary.side is BreakSide.ABOVE else close < level
        outcome.retest_held = held
        # Seul un échec change l'état: une cassure reprise dans l'autre sens
        # n'était pas une cassure. Un retest tenu ne fait que confirmer ce que
        # `CLOSE_CONFIRMED` disait déjà.
        if not held:
            outcome.state = BreakoutState.FAILED_BREAKOUT
        return
