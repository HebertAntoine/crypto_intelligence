"""Niveau 1 — la figure dessinée est-elle cohérente avec les bougies ?

Ce module est un contrôle **indépendant**. Il ne rejoue pas la logique du
détecteur et n'a pas accès à son état interne : il reçoit la géométrie publiée
— points nommés, droites, zones — et les bougies, puis vérifie que ce qui est
dessiné correspond à ce que le prix a réellement fait.

C'est ce qui le rend utile. Un détecteur peut se tromper de deux façons :
appliquer une règle fausse, ou appliquer correctement une règle à de mauvaises
données. Se relire lui-même n'attrape ni l'une ni l'autre. Repartir du dessin
attrape la seconde, et une partie de la première — c'est exactement ainsi que
la neckline horizontale de l'épaule-tête-épaule aurait été prise.

Les vérifications se rangent en trois familles :

  * **cohérence avec les bougies** — un sommet annoncé à 2 546,66 doit se
    trouver sur une bougie qui a réellement atteint ce prix ;
  * **cohérence interne** — ordre temporel des points, absence d'inversion,
    zones dont le haut est au-dessus du bas ;
  * **cohérence avec la définition** — deux sommets pour un double sommet,
    trois pour un triple, une tête plus haute que ses épaules.

Un échec n'est pas « la figure est fausse au sens du marché ». C'est « ce
dessin ne tient pas debout ». C'est plus faible, et c'est vérifiable.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import pandas as pd

from ..logging_setup import get_logger
from ..structure.geometry import PatternGeometry

log = get_logger("pattern_validation.geometry")

#: Un prix annoncé peut différer de la bougie d'une fraction d'ATR sans que ce
#: soit une erreur: les détecteurs arrondissent, et une mèche se mesure au
#: centième. Au-delà, le point ne décrit plus la bougie qu'il prétend décrire.
PRICE_TOLERANCE_ATR = 0.25

#: Combien de points nommés chaque figure doit porter, et lesquels.
REQUIRED_ROLES: dict[str, set[str]] = {
    "double_top": {"first_top", "second_top"},
    "double_bottom": {"first_bottom", "second_bottom"},
    "triple_top": {"first_top", "second_top", "third_top"},
    "triple_bottom": {"first_bottom", "second_bottom", "third_bottom"},
    "head_and_shoulders": {
        "left_shoulder", "head", "right_shoulder", "left_armpit", "right_armpit",
    },
    "inverse_head_and_shoulders": {
        "left_shoulder", "head", "right_shoulder", "left_armpit", "right_armpit",
    },
    "bull_flag": {"pole_start", "pole_end"},
    "bear_flag": {"pole_start", "pole_end"},
    # Triangles et biseaux publient les deux bornes ajustées. Leurs points sont
    # « projected »: ils sont posés sur la droite, pas sur un extrême.
    "symmetrical_triangle": {"upper_pivot", "lower_pivot"},
    "ascending_triangle": {"upper_pivot", "lower_pivot"},
    "descending_triangle": {"upper_pivot", "lower_pivot"},
    "rising_wedge": {"upper_pivot", "lower_pivot"},
    "falling_wedge": {"upper_pivot", "lower_pivot"},
}

#: Contre quel prix de la bougie chaque rôle doit être vérifié.
#:
#: La polarité dépend de la FIGURE, pas seulement du nom du rôle: dans une ETE
#: inversée les épaules et la tête sont des plus BAS et les aisselles des plus
#: HAUTS — exactement l'inverse d'une ETE normale. Une première version de ce
#: module a ignoré cette symétrie et a rejeté les 1 005 ETE inversées d'un
#: coup. Le contrôle avait tort, pas le détecteur.
_INVERTED_FIGURES = {
    "inverse_head_and_shoulders",
    "double_bottom",
    "triple_bottom",
}

_EXTREME_ROLES = {
    "first_top", "second_top", "third_top", "peak",
    "left_shoulder", "head", "right_shoulder",
    "first_bottom", "second_bottom", "third_bottom", "valley",
    "left_armpit", "right_armpit",
}

#: Les rôles dont la polarité s'inverse par rapport à la figure: dans une ETE,
#: les aisselles sont des creux quand les épaules sont des sommets.
_COUNTER_ROLES = {"left_armpit", "right_armpit", "valley"}


def _expected_extreme(pattern_name: str, role: str) -> str | None:
    """« high », « low », ou rien quand le rôle ne vise pas un extrême."""
    if role not in _EXTREME_ROLES:
        return None
    upward = pattern_name not in _INVERTED_FIGURES
    if role in _COUNTER_ROLES:
        upward = not upward
    return "high" if upward else "low"


@dataclass(slots=True)
class GeometryValidation:
    """Le verdict, et pourquoi.

    `score` n'est pas une confiance de reconnaissance : c'est la part des
    contrôles passés. Les deux ne se remplacent pas, et une figure peut avoir
    une reconnaissance élevée et une géométrie invalide — c'est précisément ce
    cas qu'on cherche à voir.
    """

    valid: bool
    score: float
    checks_run: int
    rejection_reasons: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "geometry_valid": self.valid,
            "geometry_score": self.score,
            "checks_run": self.checks_run,
            "rejection_reasons": self.rejection_reasons,
            "warnings": self.warnings,
            "note": (
                "Level 1 only: whether the drawing is consistent with the "
                "candles. Says nothing about whether the figure predicts "
                "anything, nor whether the shape is more common than noise."
            ),
        }


class _Checks:
    """Accumulateur: chaque contrôle compte, qu'il passe ou non.

    Compter les contrôles exécutés évite un score flatteur obtenu en n'en
    lançant que deux.
    """

    def __init__(self) -> None:
        self.run = 0
        self.failed: list[str] = []
        self.warned: list[str] = []

    def require(self, condition: bool, reason: str) -> bool:
        self.run += 1
        if not condition:
            self.failed.append(reason)
        return condition

    def warn(self, condition: bool, reason: str) -> None:
        self.run += 1
        if not condition:
            self.warned.append(reason)


def _bar_at(candles: pd.DataFrame, when: Any) -> pd.Series | None:
    """La bougie portant cet horodatage, ou rien.

    Rien plutôt qu'une approximation: un point qui ne tombe sur aucune bougie
    est une erreur en soi, pas quelque chose à rapprocher de la plus proche.
    """
    try:
        return candles.loc[pd.Timestamp(when)]
    except (KeyError, ValueError, TypeError):
        return None


def validate_geometry(
    pattern_name: str,
    geometry: PatternGeometry,
    candles: pd.DataFrame,
    atr: float,
) -> GeometryValidation:
    """Le dessin tient-il debout devant les bougies ?"""
    checks = _Checks()

    if candles is None or candles.empty:
        return GeometryValidation(
            valid=False, score=0.0, checks_run=1,
            rejection_reasons=["no candles to validate against"],
        )
    if atr <= 0 or atr != atr:
        return GeometryValidation(
            valid=False, score=0.0, checks_run=1,
            rejection_reasons=["ATR unusable - normalised checks impossible"],
        )

    _check_not_empty(checks, geometry)
    _check_required_roles(checks, pattern_name, geometry)
    _check_points_lie_on_candles(checks, pattern_name, geometry, candles, atr)
    _check_chronology(checks, pattern_name, geometry)
    _check_zones(checks, geometry)
    _check_lines(checks, geometry)
    _check_shape_rules(checks, pattern_name, geometry, atr)

    passed = checks.run - len(checks.failed)
    score = round(passed / checks.run * 100, 1) if checks.run else 0.0
    return GeometryValidation(
        valid=not checks.failed,
        score=score,
        checks_run=checks.run,
        rejection_reasons=checks.failed,
        warnings=checks.warned,
    )


def _check_not_empty(checks: _Checks, geometry: PatternGeometry) -> None:
    checks.require(
        not geometry.is_empty,
        "geometry is empty - nothing to draw and nothing to check",
    )


def _check_required_roles(
    checks: _Checks, pattern_name: str, geometry: PatternGeometry
) -> None:
    required = REQUIRED_ROLES.get(pattern_name)
    if required is None:
        # Pas de contrat déclaré pour cette figure: on le signale plutôt que de
        # laisser croire qu'elle a été vérifiée.
        checks.warn(False, f"no declared role contract for '{pattern_name}'")
        return
    present = {point.role for point in geometry.points}
    missing = required - present
    checks.require(
        not missing,
        f"missing named points: {', '.join(sorted(missing))}" if missing else "",
    )


def _check_points_lie_on_candles(
    checks: _Checks,
    pattern_name: str,
    geometry: PatternGeometry,
    candles: pd.DataFrame,
    atr: float,
) -> None:
    """Chaque point nommé décrit-il vraiment sa bougie ?

    C'est le contrôle le plus fort du module: il repart des prix bruts et ne
    peut pas être satisfait par un détecteur qui se trompe de barre.
    """
    for point in geometry.points:
        bar = _bar_at(candles, point.time)
        checks.require(
            bar is not None, f"{point.role or 'point'} falls on no candle"
        )
        # `require` renvoie un booléen, pas un TypeGuard: le test explicite
        # sert au typage autant qu'à la lecture.
        if bar is None:
            continue
        low, high = float(bar["low"]), float(bar["high"])
        margin = atr * PRICE_TOLERANCE_ATR

        # `kind` dit ce que le point prétend être, et donc ce qu'il faut
        # vérifier. Un point « projected » est posé sur une droite ajustée: il
        # ne tombe sur aucun extrême, et exiger qu'il en touche un rejetait
        # tous les triangles et tous les biseaux.
        if point.kind == "projected":
            checks.warn(
                low - margin * 4 <= point.price <= high + margin * 4,
                f"projected {point.role or 'point'} at {point.price:.2f} is far "
                f"from its candle [{low:.2f}, {high:.2f}]",
            )
            continue

        if point.kind == "close":
            close = float(bar["close"])
            drift = abs(point.price - close) / atr
            checks.require(
                drift <= PRICE_TOLERANCE_ATR,
                f"{point.role or 'point'} at {point.price:.2f} is {drift:.2f} "
                f"ATR from its candle's close {close:.2f}",
            )
            continue

        extreme = _expected_extreme(pattern_name, point.role)
        if extreme is None:
            checks.require(
                low - margin <= point.price <= high + margin,
                f"{point.role or 'point'} at {point.price:.2f} is outside its "
                f"candle [{low:.2f}, {high:.2f}]",
            )
            continue
        reference = high if extreme == "high" else low
        drift = abs(point.price - reference) / atr
        checks.require(
            drift <= PRICE_TOLERANCE_ATR,
            f"{point.role} at {point.price:.2f} is {drift:.2f} ATR from its "
            f"candle's {extreme} {reference:.2f}",
        )


#: Figures dont les points nommés décrivent une séquence. Un triangle publie
#: un pivot haut et un pivot bas qui peuvent s'entrelacer: leur ordre dans la
#: liste ne dit rien, et l'exiger rejetait des triangles corrects.
_SEQUENTIAL_FIGURES = {
    "double_top", "double_bottom", "triple_top", "triple_bottom",
    "head_and_shoulders", "inverse_head_and_shoulders",
    "bull_flag", "bear_flag",
}


def _check_chronology(
    checks: _Checks, pattern_name: str, geometry: PatternGeometry
) -> None:
    """Les points nommés doivent se suivre dans le temps."""
    if pattern_name not in _SEQUENTIAL_FIGURES:
        return
    times = [point.time for point in geometry.points]
    if len(times) < 2:
        return
    checks.require(
        times == sorted(times),
        "named points are not in chronological order",
    )
    checks.require(
        len(set(times)) == len(times),
        "two named points share the same timestamp",
    )


def _check_zones(checks: _Checks, geometry: PatternGeometry) -> None:
    for zone in geometry.zones:
        checks.require(
            zone.high >= zone.low,
            f"zone '{zone.role}' has its high below its low",
        )
        checks.require(
            zone.end_time >= zone.start_time,
            f"zone '{zone.role}' ends before it starts",
        )


def _check_lines(checks: _Checks, geometry: PatternGeometry) -> None:
    for line in geometry.trend_lines:
        checks.require(
            line.end.time >= line.start.time,
            f"line '{line.role}' ends before it starts",
        )
    neckline = geometry.neckline
    if neckline is not None:
        checks.require(
            neckline.end.time >= neckline.start.time,
            "neckline ends before it starts",
        )


def _check_shape_rules(
    checks: _Checks, pattern_name: str, geometry: PatternGeometry, atr: float
) -> None:
    """Les règles propres à chaque famille, relues depuis le dessin seul."""
    by_role = {point.role: point for point in geometry.points}

    if pattern_name in ("head_and_shoulders", "inverse_head_and_shoulders"):
        head = by_role.get("head")
        left = by_role.get("left_shoulder")
        right = by_role.get("right_shoulder")
        if head and left and right:
            inverse = pattern_name.startswith("inverse")
            dominates = (
                head.price < left.price and head.price < right.price
                if inverse
                else head.price > left.price and head.price > right.price
            )
            checks.require(
                dominates,
                "the head does not stand beyond both shoulders",
            )
        # Les aisselles doivent se trouver entre les épaules.
        for side in ("left", "right"):
            armpit = by_role.get(f"{side}_armpit")
            shoulder = by_role.get(f"{side}_shoulder")
            if armpit and head and shoulder:
                between = (
                    min(shoulder.time, head.time)
                    <= armpit.time
                    <= max(shoulder.time, head.time)
                )
                checks.require(
                    between, f"the {side} armpit is not between its shoulder and the head"
                )

    if pattern_name in ("double_top", "double_bottom"):
        top = pattern_name.endswith("top")
        a = by_role.get("first_top" if top else "first_bottom")
        b = by_role.get("second_top" if top else "second_bottom")
        neckline = geometry.neckline
        if a and b and neckline is not None:
            # La vallée doit réellement séparer les deux extrêmes.
            level = neckline.start.price
            separated = (
                level < min(a.price, b.price) if top else level > max(a.price, b.price)
            )
            checks.require(
                separated,
                "the neckline does not sit between the two extremes",
            )

    if pattern_name in ("bull_flag", "bear_flag"):
        start = by_role.get("pole_start")
        end = by_role.get("pole_end")
        if start and end:
            bullish = pattern_name.startswith("bull")
            rising = end.price > start.price
            checks.require(
                rising == bullish,
                "the pole runs against the direction the flag claims",
            )
            checks.require(
                end.time > start.time, "the pole ends before it starts"
            )
