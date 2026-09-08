"""Le validateur géométrique doit pouvoir dire non.

Ces tests existent parce qu'un validateur qui accepte tout est aussi inutile
qu'un validateur qui rejette tout, et que la différence ne se voit pas en
lisant le code. Chaque cas corrompt délibérément une géométrie réelle et exige
le rejet.

Le validateur est indépendant du détecteur par construction: il ne reçoit que
la géométrie publiée et les bougies. Il ne peut donc pas confirmer un détecteur
en répétant son raisonnement — c'est tout l'intérêt.
"""

from __future__ import annotations

import dataclasses
from datetime import UTC, datetime, timedelta

import numpy as np
import pandas as pd
import pytest

from crypto_intel.pattern_validation import validate_geometry
from crypto_intel.structure.geometry import (
    GeometryPoint,
    GeometryZone,
    PatternGeometry,
    TrendLine,
)

ATR = 2.0


@pytest.fixture(scope="module")
def candles() -> pd.DataFrame:
    """Deux sommets égaux séparés par un creux net, en clair."""
    closes = np.concatenate([
        np.linspace(100, 130, 20, endpoint=False),
        np.linspace(130, 110, 15, endpoint=False),
        np.linspace(110, 130, 15, endpoint=False),
        np.linspace(130, 112, 10, endpoint=False),
    ])
    index = pd.date_range(datetime(2024, 1, 1, tzinfo=UTC), periods=len(closes), freq="D")
    return pd.DataFrame(
        {
            "open": closes,
            "high": closes + 1.0,
            "low": closes - 1.0,
            "close": closes,
            "volume": np.full(len(closes), 1000.0),
        },
        index=index,
    )


@pytest.fixture
def double_top(candles: pd.DataFrame) -> PatternGeometry:
    """Une géométrie que le validateur doit accepter."""
    first_index, second_index = 19, 49
    first_time = candles.index[first_index]
    second_time = candles.index[second_index]
    valley = float(candles["low"].iloc[20:49].min())
    neckline = TrendLine(
        start=GeometryPoint(time=first_time, price=valley, role="neckline"),
        end=GeometryPoint(time=candles.index[-1], price=valley, role="neckline"),
        role="neckline",
        extend=True,
    )
    return PatternGeometry(
        points=[
            GeometryPoint(
                time=first_time,
                price=float(candles["high"].iloc[first_index]),
                role="first_top",
            ),
            GeometryPoint(
                time=second_time,
                price=float(candles["high"].iloc[second_index]),
                role="second_top",
            ),
        ],
        trend_lines=[neckline],
        neckline=neckline,
        zones=[
            GeometryZone(
                start_time=first_time, end_time=second_time,
                low=valley, high=float(candles["high"].iloc[first_index]),
                role="breakout",
            )
        ],
    )


def _validate(name, geometry, candles):
    return validate_geometry(name, geometry, candles, ATR)


class TestItAcceptsAValidDrawing:
    def test_an_intact_double_top_passes(self, double_top, candles):
        result = _validate("double_top", double_top, candles)
        assert result.valid, result.rejection_reasons
        assert result.score == 100.0
        assert result.checks_run > 5, "un score de 100 sur deux contrôles ne vaut rien"


class TestItRejectsWhatIsWrong:
    """Chaque cas est une erreur qu'un détecteur peut réellement commettre."""

    def test_a_peak_that_is_not_on_its_candle(self, double_top, candles):
        moved = dataclasses.replace(double_top.points[0], price=200.0)
        broken = dataclasses.replace(double_top, points=[moved, double_top.points[1]])
        result = _validate("double_top", broken, candles)
        assert not result.valid
        assert any("ATR from its candle" in r for r in result.rejection_reasons)

    def test_points_out_of_chronological_order(self, double_top, candles):
        broken = dataclasses.replace(
            double_top, points=list(reversed(double_top.points))
        )
        assert not _validate("double_top", broken, candles).valid

    def test_a_missing_named_point(self, double_top, candles):
        broken = dataclasses.replace(double_top, points=double_top.points[:1])
        result = _validate("double_top", broken, candles)
        assert not result.valid
        assert any("second_top" in r for r in result.rejection_reasons)

    def test_a_point_on_no_candle_at_all(self, double_top, candles):
        ghost = dataclasses.replace(
            double_top.points[0],
            time=double_top.points[0].time + timedelta(hours=7),
        )
        broken = dataclasses.replace(double_top, points=[ghost, double_top.points[1]])
        result = _validate("double_top", broken, candles)
        assert not result.valid
        assert any("falls on no candle" in r for r in result.rejection_reasons)

    def test_a_zone_with_its_high_below_its_low(self, double_top, candles):
        zone = double_top.zones[0]
        flipped = GeometryZone(
            start_time=zone.start_time, end_time=zone.end_time,
            low=zone.high, high=zone.low, role="breakout",
        )
        broken = dataclasses.replace(double_top, zones=[flipped])
        assert not _validate("double_top", broken, candles).valid

    def test_a_neckline_that_does_not_separate_the_peaks(self, double_top, candles):
        above = max(point.price for point in double_top.points) + 10
        neckline = TrendLine(
            start=dataclasses.replace(double_top.neckline.start, price=above),
            end=dataclasses.replace(double_top.neckline.end, price=above),
            role="neckline",
        )
        broken = dataclasses.replace(double_top, neckline=neckline)
        result = _validate("double_top", broken, candles)
        assert not result.valid
        assert any("neckline" in r for r in result.rejection_reasons)

    def test_an_empty_geometry(self, candles):
        result = _validate("double_top", PatternGeometry(), candles)
        assert not result.valid
        assert any("empty" in r for r in result.rejection_reasons)


class TestItKnowsWhichWayEachFigurePoints:
    """La polarité dépend de la figure, pas du nom du rôle.

    Une première version traitait « head » comme un sommet dans tous les cas et
    rejetait d'un coup les 1 005 ETE inversées de l'historique. Le contrôle
    avait tort, pas le détecteur : ce test fige la correction.
    """

    def test_an_inverse_head_and_shoulders_is_read_upside_down(self, candles):
        # Tête sur un plus BAS, aisselles sur des plus HAUTS.
        lows = candles["low"]
        highs = candles["high"]
        geometry = PatternGeometry(
            points=[
                GeometryPoint(time=candles.index[10], price=float(lows.iloc[10]),
                              role="left_shoulder"),
                GeometryPoint(time=candles.index[15], price=float(highs.iloc[15]),
                              role="left_armpit"),
                GeometryPoint(time=candles.index[25], price=float(lows.iloc[25]),
                              role="head"),
                GeometryPoint(time=candles.index[35], price=float(highs.iloc[35]),
                              role="right_armpit"),
                GeometryPoint(time=candles.index[40], price=float(lows.iloc[40]),
                              role="right_shoulder"),
            ],
        )
        result = _validate("inverse_head_and_shoulders", geometry, candles)
        # La tête doit être sous les deux épaules; si la série ne le permet pas
        # le rejet doit porter sur CE motif, jamais sur la polarité des points.
        assert not any(
            "ATR from its candle" in reason for reason in result.rejection_reasons
        ), result.rejection_reasons


class TestItRefusesToJudgeWithoutData:
    def test_no_candles_is_not_a_pass(self, double_top):
        result = validate_geometry("double_top", double_top, pd.DataFrame(), ATR)
        assert not result.valid
        assert result.score == 0.0

    def test_an_unusable_atr_is_not_a_pass(self, double_top, candles):
        result = validate_geometry("double_top", double_top, candles, 0.0)
        assert not result.valid
        assert any("ATR" in r for r in result.rejection_reasons)

    def test_an_undeclared_figure_is_warned_about_not_silently_passed(
        self, double_top, candles
    ):
        result = _validate("cup_and_handle", double_top, candles)
        assert any("no declared role contract" in w for w in result.warnings)
