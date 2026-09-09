"""La frontière d'une figure, et ce que le prix en fait.

Deux confusions que ces tests existent pour empêcher.

**Une mèche n'est pas une cassure.** Le prix traverse une frontière en séance
bien plus souvent qu'il ne clôture au-delà. Les confondre gonflerait le taux de
confirmation de chaque figure sans qu'aucune règle n'ait changé.

**Une frontière inclinée n'est pas un prix.** La borne haute d'un triangle
descend. La figer au dernier chandelier donnerait un niveau juste ce jour-là et
faux le lendemain — et un backtest jugerait la cassure contre un prix que
personne n'a jamais vu à l'écran.

Les fixtures sont construites à la main pour que chaque cas soit sans
ambiguïté: un humain lisant le graphique donnerait la même réponse.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import numpy as np
import pandas as pd
import pytest

from crypto_intel.structure.breakout import (
    BREAKOUT_BUFFER_ATR,
    BoundaryType,
    BreakoutBoundary,
    BreakoutState,
    BreakSide,
    boundaries_for,
    evaluate_breakout,
    horizon_for,
)
from crypto_intel.structure.geometry import (
    GeometryPoint,
    GeometryZone,
    PatternGeometry,
    TrendLine,
)

ATR = 2.0
START = datetime(2024, 1, 1, tzinfo=UTC)


def _bars(rows: list[tuple[float, float, float]], start: datetime = START) -> pd.DataFrame:
    """`rows` = (haut, bas, cloture), une ligne par barre."""
    index = pd.date_range(start, periods=len(rows), freq="D")
    return pd.DataFrame(
        {
            "open": [c for _, _, c in rows],
            "high": [h for h, _, _ in rows],
            "low": [low for _, low, _ in rows],
            "close": [c for _, _, c in rows],
            "volume": np.full(len(rows), 1000.0),
        },
        index=index,
    )


def _horizontal(level: float, side: BreakSide) -> BreakoutBoundary:
    return BreakoutBoundary(
        role="test", kind=BoundaryType.HORIZONTAL, side=side,
        start_time=START, start_price=level,
        end_time=START + timedelta(days=30), end_price=level,
    )


class TestAnInclinedBoundaryStaysInclined:
    """Le point central de cette phase."""

    def test_a_falling_upper_line_is_read_at_the_right_moment(self):
        boundary = BreakoutBoundary(
            role="upper", kind=BoundaryType.LINE, side=BreakSide.ABOVE,
            start_time=START, start_price=100.0,
            end_time=START + timedelta(days=10), end_price=90.0,
        )
        assert boundary.price_at(START) == pytest.approx(100.0)
        assert boundary.price_at(START + timedelta(days=5)) == pytest.approx(95.0)
        assert boundary.price_at(START + timedelta(days=10)) == pytest.approx(90.0)

    def test_it_is_extended_beyond_its_last_point(self):
        """Une cassure apres le dernier pivot doit etre jugee contre la droite
        prolongee, pas contre un niveau perime."""
        boundary = BreakoutBoundary(
            role="upper", kind=BoundaryType.LINE, side=BreakSide.ABOVE,
            start_time=START, start_price=100.0,
            end_time=START + timedelta(days=10), end_price=90.0,
        )
        assert boundary.price_at(START + timedelta(days=20)) == pytest.approx(80.0)

    def test_a_horizontal_boundary_ignores_time(self):
        boundary = _horizontal(100.0, BreakSide.ABOVE)
        assert boundary.price_at(START + timedelta(days=999)) == 100.0

    def test_the_same_price_breaks_one_day_and_not_another(self):
        """La consequence concrete: figer la droite changerait la reponse."""
        boundary = BreakoutBoundary(
            role="upper", kind=BoundaryType.LINE, side=BreakSide.ABOVE,
            start_time=START, start_price=100.0,
            end_time=START + timedelta(days=10), end_price=90.0,
        )
        early = _bars([(96.5, 95.0, 96.0)], start=START)
        late = _bars([(96.5, 95.0, 96.0)], start=START + timedelta(days=8))
        assert evaluate_breakout([boundary], early, ATR, bars_span=10).state \
            is not BreakoutState.CLOSE_CONFIRMED
        assert evaluate_breakout([boundary], late, ATR, bars_span=10).state \
            is BreakoutState.CLOSE_CONFIRMED


class TestWickIsNotAClose:
    def test_a_wick_through_the_boundary_is_not_a_breakout(self):
        boundary = _horizontal(100.0, BreakSide.ABOVE)
        bars = _bars([(103.0, 97.0, 98.0), (102.0, 96.0, 97.5)])
        outcome = evaluate_breakout([boundary], bars, ATR, bars_span=10)
        assert outcome.state is BreakoutState.WICK_ONLY
        assert outcome.first_wick_time is not None

    def test_a_close_beyond_the_buffer_is_a_breakout(self):
        boundary = _horizontal(100.0, BreakSide.ABOVE)
        bars = _bars([(103.0, 99.0, 102.0)])
        outcome = evaluate_breakout([boundary], bars, ATR, bars_span=10)
        assert outcome.state is BreakoutState.CLOSE_CONFIRMED
        assert outcome.bars_to_event == 1

    def test_a_close_inside_the_buffer_is_not_yet_a_breakout(self):
        """Le tampon en ATR existe pour que le bruit de cotation ne compte pas."""
        boundary = _horizontal(100.0, BreakSide.ABOVE)
        just_over = 100.0 + ATR * BREAKOUT_BUFFER_ATR * 0.5
        bars = _bars([(just_over + 0.1, 99.0, just_over)])
        outcome = evaluate_breakout([boundary], bars, ATR, bars_span=10)
        assert outcome.state is not BreakoutState.CLOSE_CONFIRMED

    def test_downward_breaks_are_symmetric(self):
        boundary = _horizontal(100.0, BreakSide.BELOW)
        wick = _bars([(103.0, 97.0, 101.0)])
        close = _bars([(103.0, 97.0, 98.0)])
        assert evaluate_breakout([boundary], wick, ATR, bars_span=10).state \
            is BreakoutState.WICK_ONLY
        assert evaluate_breakout([boundary], close, ATR, bars_span=10).state \
            is BreakoutState.CLOSE_CONFIRMED


class TestTheFourTriangleCases:
    """Les fixtures demandees, sur une borne inclinee."""

    @pytest.fixture
    def triangle(self) -> PatternGeometry:
        upper = TrendLine(
            start=GeometryPoint(time=START, price=110.0, role="upper", kind="projected"),
            end=GeometryPoint(time=START + timedelta(days=10), price=104.0,
                              role="upper", kind="projected"),
            role="upper", extend=True,
        )
        lower = TrendLine(
            start=GeometryPoint(time=START, price=90.0, role="lower", kind="projected"),
            end=GeometryPoint(time=START + timedelta(days=10), price=96.0,
                              role="lower", kind="projected"),
            role="lower", extend=True,
        )
        return PatternGeometry(trend_lines=[upper, lower])

    def _forward(self, triangle, rows):
        bounds = boundaries_for("symmetrical_triangle", triangle, "NEUTRAL")
        return bounds, _bars(rows, start=START + timedelta(days=11))

    def test_a_symmetrical_triangle_offers_both_sides(self, triangle):
        bounds = boundaries_for("symmetrical_triangle", triangle, "NEUTRAL")
        assert {b.side for b in bounds} == {BreakSide.ABOVE, BreakSide.BELOW}
        assert all(b.kind is BoundaryType.LINE for b in bounds), \
            "les bornes d'un triangle sont inclinees, pas des prix"

    def test_no_breakout(self, triangle):
        # Trois barres au milieu du triangle, avant convergence: les deux
        # bornes sont encore a plus d'une ATR du prix.
        bounds, bars = self._forward(triangle, [(101.0, 99.0, 100.0)] * 3)
        assert evaluate_breakout(bounds, bars, ATR, bars_span=10).state \
            is BreakoutState.NO_BREAKOUT

    def test_price_pinned_to_a_converging_boundary_is_pending_not_quiet(self):
        """Un triangle qui converge finit par coller au prix.

        Ce n'est pas « rien ne se passe »: c'est l'attente. Les confondre
        ferait passer pour calme le moment ou la figure se decide.
        """
        upper = TrendLine(
            start=GeometryPoint(time=START, price=110.0, role="upper", kind="projected"),
            end=GeometryPoint(time=START + timedelta(days=10), price=104.0,
                              role="upper", kind="projected"),
            role="upper", extend=True,
        )
        lower = TrendLine(
            start=GeometryPoint(time=START, price=90.0, role="lower", kind="projected"),
            end=GeometryPoint(time=START + timedelta(days=10), price=96.0,
                              role="lower", kind="projected"),
            role="lower", extend=True,
        )
        bounds = boundaries_for(
            "symmetrical_triangle",
            PatternGeometry(trend_lines=[upper, lower]),
            "NEUTRAL",
        )
        # A J+15 les deux bornes valent 101 et 99: le prix a 100 est a
        # exactement 0,5 ATR de chacune, sans qu'aucune meche ne les traverse.
        bars = _bars([(101.0, 99.0, 100.0)] * 5, start=START + timedelta(days=11))
        assert evaluate_breakout(bounds, bars, ATR, bars_span=10).state \
            is BreakoutState.POTENTIAL

    def test_wick_only(self, triangle):
        bounds, bars = self._forward(triangle, [(105.0, 99.0, 101.0)] * 3)
        assert evaluate_breakout(bounds, bars, ATR, bars_span=10).state \
            is BreakoutState.WICK_ONLY

    def test_close_confirmed(self, triangle):
        bounds, bars = self._forward(triangle, [(107.0, 102.0, 106.0)])
        outcome = evaluate_breakout(bounds, bars, ATR, bars_span=10)
        assert outcome.state is BreakoutState.CLOSE_CONFIRMED
        assert outcome.boundary.role == "upper"

    def test_a_false_breakout_is_recorded_as_failed(self, triangle):
        """Cassure haussiere, puis retour sous la frontiere."""
        bounds, bars = self._forward(triangle, [
            (107.0, 102.0, 106.0),
            (106.0, 100.0, 101.0),
            (102.0, 98.0, 99.0),
        ])
        outcome = evaluate_breakout(bounds, bars, ATR, bars_span=10)
        assert outcome.state is BreakoutState.FAILED_BREAKOUT
        assert outcome.retest_held is False


class TestFlagsAndWedges:
    def test_a_bull_flag_breaks_above_its_consolidation(self):
        geometry = PatternGeometry(
            points=[
                GeometryPoint(time=START, price=80.0, role="pole_start"),
                GeometryPoint(time=START + timedelta(days=5), price=100.0,
                              role="pole_end"),
            ],
            zones=[GeometryZone(
                start_time=START + timedelta(days=5),
                end_time=START + timedelta(days=10),
                low=95.0, high=100.0, role="consolidation",
            )],
        )
        bounds = boundaries_for("bull_flag", geometry, "BULLISH")
        assert len(bounds) == 1
        assert bounds[0].side is BreakSide.ABOVE
        assert bounds[0].start_price == 100.0
        bars = _bars([(104.0, 100.0, 103.0)], start=START + timedelta(days=11))
        assert evaluate_breakout(bounds, bars, ATR, bars_span=10).state \
            is BreakoutState.CLOSE_CONFIRMED

    def test_a_bear_flag_breaks_below(self):
        geometry = PatternGeometry(
            zones=[GeometryZone(
                start_time=START, end_time=START + timedelta(days=5),
                low=95.0, high=100.0, role="consolidation",
            )],
        )
        bounds = boundaries_for("bear_flag", geometry, "BEARISH")
        assert bounds[0].side is BreakSide.BELOW
        assert bounds[0].start_price == 95.0

    def test_a_directional_wedge_offers_only_its_own_side(self):
        upper = TrendLine(
            start=GeometryPoint(time=START, price=110.0, role="upper"),
            end=GeometryPoint(time=START + timedelta(days=10), price=120.0, role="upper"),
            role="upper",
        )
        lower = TrendLine(
            start=GeometryPoint(time=START, price=100.0, role="lower"),
            end=GeometryPoint(time=START + timedelta(days=10), price=115.0, role="lower"),
            role="lower",
        )
        geometry = PatternGeometry(trend_lines=[upper, lower])
        bounds = boundaries_for("rising_wedge", geometry, "BEARISH")
        assert len(bounds) == 1, "un biseau baissier casse par le bas"
        assert bounds[0].side is BreakSide.BELOW


class TestNothingIsInvented:
    def test_a_figure_without_usable_geometry_gets_no_boundary(self):
        assert boundaries_for("double_top", PatternGeometry(), "BEARISH") == []

    def test_and_therefore_reports_no_trigger_rather_than_a_guess(self):
        outcome = evaluate_breakout([], _bars([(1.0, 1.0, 1.0)]), ATR)
        assert outcome.state is BreakoutState.NO_TRIGGER_DEFINED


class TestTheHorizonIsBounded:
    """Sans borne, tout finit par etre invalide."""

    def test_the_horizon_scales_with_the_figure(self):
        assert horizon_for(0) >= 20
        assert horizon_for(40) == 120
        assert horizon_for(10_000) <= 250

    def test_a_move_beyond_the_horizon_does_not_count(self):
        boundary = _horizontal(100.0, BreakSide.ABOVE)
        bars = _bars([(99.0, 97.0, 98.0)] * 30 + [(120.0, 110.0, 118.0)])
        outcome = evaluate_breakout([boundary], bars, ATR, bars_span=0)
        assert outcome.state is not BreakoutState.CLOSE_CONFIRMED


class TestNoLookahead:
    """Le controle le plus important de cette phase."""

    def test_the_boundary_comes_only_from_geometry(self):
        """Aucune bougie n'entre dans le calcul de la frontiere.

        `boundaries_for` ne recoit pas de prix: il ne PEUT pas regarder le
        futur. Propriete de signature, verifiee ici pour qu'elle ne se perde
        pas a la prochaine refonte.
        """
        import inspect

        params = set(inspect.signature(boundaries_for).parameters)
        assert params == {"pattern_name", "geometry", "direction"}, (
            "boundaries_for a gagne un acces aux prix: la frontiere pourrait "
            "desormais dependre de ce qui s'est passe apres la detection"
        )

    def test_truncating_the_future_never_changes_a_past_verdict(self):
        boundary = _horizontal(100.0, BreakSide.ABOVE)
        rows = [(99.0, 97.0, 98.0), (103.0, 99.0, 102.0), (95.0, 90.0, 92.0)]
        full = evaluate_breakout([boundary], _bars(rows), ATR, bars_span=10)
        truncated = evaluate_breakout([boundary], _bars(rows[:2]), ATR, bars_span=10)
        assert truncated.state is BreakoutState.CLOSE_CONFIRMED
        assert truncated.bars_to_event == full.bars_to_event == 2

    def test_a_verdict_before_the_event_says_nothing_happened_yet(self):
        boundary = _horizontal(100.0, BreakSide.ABOVE)
        rows = [(99.0, 97.0, 98.0), (103.0, 99.0, 102.0)]
        before = evaluate_breakout([boundary], _bars(rows[:1]), ATR, bars_span=10)
        assert before.state is not BreakoutState.CLOSE_CONFIRMED

    def test_invalidation_is_checked_before_any_later_breakout(self):
        """Une figure invalidee ne peut pas etre sauvee par la suite."""
        boundary = _horizontal(100.0, BreakSide.BELOW)
        rows = [(130.0, 125.0, 128.0), (99.0, 90.0, 92.0)]
        outcome = evaluate_breakout(
            [boundary], _bars(rows), ATR,
            invalidation_level=120.0, direction="BEARISH", bars_span=10,
        )
        assert outcome.state is BreakoutState.INVALIDATED_FIRST
        assert outcome.bars_to_event == 1
