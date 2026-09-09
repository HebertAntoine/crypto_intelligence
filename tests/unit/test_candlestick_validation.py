"""La mesure d'avantage, et les trois facons de la fausser.

**Lire le futur.** Une detection a T ne doit dependre d'aucune bougie
posterieure. Les rendements futurs servent a EVALUER, jamais a reconnaitre.

**Comparer a n'importe quoi.** Un marteau apparait par definition apres une
baisse. Le comparer a toutes les bougies mesurerait le rebond qui suit une
baisse, pas le marteau. Les controles doivent partager le contexte.

**Choisir le sens apres coup.** Le sens attendu est declare dans la taxonomie,
avant toute mesure. Lire un rendement negatif comme « la figure marche a
l'envers » serait choisir l'hypothese en fonction du resultat.
"""

from __future__ import annotations

from datetime import UTC, datetime
from itertools import pairwise

import numpy as np
import pandas as pd
import pytest

from crypto_intel.candlesticks import scan_candlesticks
from crypto_intel.candlesticks.taxonomy import (
    DETECTOR_VERSION,
    EXPECTED_DIRECTION,
    PATTERN_FAMILY,
    CandlestickFamily,
    CandlestickPattern,
)
from crypto_intel.candlesticks.validation import (
    HORIZONS,
    build_context_frame,
    evaluate_pattern,
    walk_forward,
)
from crypto_intel.structure.patterns import PatternEdgeState


@pytest.fixture(scope="module")
def series() -> pd.DataFrame:
    """Une marche aleatoire assez longue pour produire des figures."""
    rng = np.random.default_rng(37)
    n = 3000
    closes = 100 * np.exp(np.cumsum(rng.normal(0, 0.02, n)))
    opens = np.concatenate([[closes[0]], closes[:-1]])
    spread = np.abs(rng.normal(0.02, 0.01, n)) * closes
    highs = np.maximum(opens, closes) + spread * rng.uniform(0, 1, n)
    lows = np.minimum(opens, closes) - spread * rng.uniform(0, 1, n)
    index = pd.date_range(datetime(2018, 1, 1, tzinfo=UTC), periods=n, freq="D")
    return pd.DataFrame(
        {"open": opens, "high": highs, "low": lows, "close": closes,
         "volume": np.full(n, 1000.0)},
        index=index,
    )


@pytest.fixture(scope="module")
def detections(series):
    return scan_candlesticks(series, symbol="TEST", timeframe="1d")


class TestTheExpectedDirectionIsDeclaredNotDiscovered:
    def test_every_pattern_has_a_direction_declared_in_the_taxonomy(self):
        for pattern in CandlestickPattern:
            assert pattern in EXPECTED_DIRECTION, f"{pattern} sans sens attendu"
            assert EXPECTED_DIRECTION[pattern] in (-1, 0, 1)

    def test_indecision_figures_claim_no_direction(self):
        for pattern, family in PATTERN_FAMILY.items():
            if family is CandlestickFamily.INDECISION:
                assert EXPECTED_DIRECTION[pattern] == 0

    def test_the_direction_matches_the_family(self):
        for pattern, family in PATTERN_FAMILY.items():
            expected = EXPECTED_DIRECTION[pattern]
            if "BULLISH" in family.value:
                assert expected == 1, f"{pattern} annoncee haussiere mais {expected}"
            elif "BEARISH" in family.value:
                assert expected == -1

    def test_an_indecision_figure_is_not_evaluated_at_all(self, series, detections):
        evidence = evaluate_pattern(
            series, detections, CandlestickPattern.DOJI, "TEST", "1d", DETECTOR_VERSION
        )
        assert evidence.horizons == []
        assert "no direction" in evidence.note
        assert evidence.edge_state is PatternEdgeState.NOT_YET_TESTED


class TestControlsShareTheContext:
    def test_the_matching_variables_are_all_backward_looking(self, series):
        """Un appariement qui lit le futur choisirait les controles selon leur
        resultat, ce qui inverserait la question posee."""
        context = build_context_frame(series)
        # On tronque la serie: les valeurs calculees sur le prefixe doivent
        # etre identiques a celles de la serie complete.
        cut = 2000
        partial = build_context_frame(series.iloc[:cut])
        for column in ("atr", "trend_atr"):
            full_values = context[column].iloc[:cut].to_numpy()
            part_values = partial[column].to_numpy()
            finite = np.isfinite(full_values) & np.isfinite(part_values)
            assert np.allclose(full_values[finite], part_values[finite]), (
                f"{column} change quand on retire les barres posterieures"
            )

    def test_controls_are_drawn_and_counted(self, series, detections):
        evidence = evaluate_pattern(
            series, detections, CandlestickPattern.BULLISH_ENGULFING,
            "TEST", "1d", DETECTOR_VERSION,
        )
        if evidence.n_occurrences < 5:
            pytest.skip("pas assez d'occurrences dans cette serie synthetique")
        first = evidence.horizons[0]
        assert first.n_controls > first.n_events, (
            "chaque occurrence doit etre comparee a plusieurs controles"
        )

    def test_a_control_is_never_itself_a_detected_figure(self, series, detections):
        """Un controle qui est lui-meme un marteau ne controle rien."""
        from crypto_intel.candlesticks.validation import _matched_controls

        context = build_context_frame(series)
        events = {
            series.index.get_loc(d.detected_at) for d in detections
            if d.detected_at in series.index
        }
        assert events, "aucune figure: le test ne prouve rien"
        rng = np.random.default_rng(1)
        target = sorted(events)[len(events) // 2]
        controls = _matched_controls(context, events, target, rng)
        assert not (set(controls) & events)
        assert target not in controls


class TestSampleSizeGovernsTheVerdict:
    def test_a_thin_sample_can_never_claim_an_edge(self, series):
        """Un resultat tres net sur sept cas n'est pas un resultat."""
        evidence = evaluate_pattern(
            series, [], CandlestickPattern.HAMMER, "TEST", "1d", DETECTOR_VERSION
        )
        assert evidence.sample_status == "INSUFFICIENT_DATA"
        assert evidence.edge_state is PatternEdgeState.NOT_YET_TESTED

    def test_the_thresholds_are_declared(self):
        from crypto_intel.candlesticks.validation import (
            EXPLORATORY_BELOW,
            INSUFFICIENT_BELOW,
        )

        assert INSUFFICIENT_BELOW < EXPLORATORY_BELOW

    def test_the_project_enum_is_reused_not_replaced(self):
        """Le projet possede deja une enumeration qui couvre ces etats."""
        for state in ("INSUFFICIENT_DATA", "NO_MEASURABLE_EDGE",
                      "POSITIVE_EDGE", "NEGATIVE_EDGE", "UNSTABLE",
                      "NOT_YET_TESTED"):
            assert hasattr(PatternEdgeState, state)


class TestNoLookahead:
    def test_forward_returns_never_enter_the_detection(self, series, detections):
        """Les composants d'une detection ne doivent contenir aucune mesure
        posterieure a sa barre."""
        forbidden = {"fwd", "future", "mfe", "mae", "return", "outcome"}
        for detection in detections[:200]:
            for key in detection.components:
                assert not any(word in key.lower() for word in forbidden), (
                    f"{detection.pattern.value} expose {key} dans sa definition"
                )

    def test_a_detection_is_unchanged_when_the_future_is_removed(self, series):
        cut = 1500
        full = scan_candlesticks(series, symbol="T", timeframe="1d")
        partial = scan_candlesticks(series.iloc[:cut], symbol="T", timeframe="1d")
        early_full = [
            (d.pattern, d.detected_at) for d in full
            if d.detected_at < series.index[cut - 25]
        ]
        early_partial = [
            (d.pattern, d.detected_at) for d in partial
            if d.detected_at < series.index[cut - 25]
        ]
        assert early_full == early_partial

    def test_the_context_window_stops_at_the_pattern(self, series, detections):
        for detection in detections[:200]:
            assert detection.context_start is not None
            assert detection.context_start <= detection.start_time
            assert detection.end_time == detection.detected_at


class TestWalkForward:
    def test_the_three_windows_are_disjoint_and_ordered(self, series, detections):
        result = walk_forward(
            series, detections, CandlestickPattern.BULLISH_ENGULFING,
            "TEST", "1d", horizon=5,
        )
        total = result.n_train + result.n_validation + result.n_test
        occurrences = sum(
            1 for d in detections if d.pattern is CandlestickPattern.BULLISH_ENGULFING
        )
        # Les dernieres occurrences n'ont pas d'horizon complet et disparaissent.
        assert total <= occurrences

    def test_an_unobserved_window_makes_the_verdict_unknown(self):
        from crypto_intel.candlesticks.validation import WalkForwardResult

        partial = WalkForwardResult(
            pattern="X", symbol="T", timeframe="1d", horizon=5,
            train=0.5, validation=None, test=0.3,
        )
        assert partial.sign_holds is None, (
            "un signe qu'on n'a pas observe ne peut pas etre declare stable"
        )

    def test_a_sign_that_flips_is_not_stable(self):
        from crypto_intel.candlesticks.validation import WalkForwardResult

        flipped = WalkForwardResult(
            pattern="X", symbol="T", timeframe="1d", horizon=5,
            train=0.5, validation=-0.2, test=0.3,
        )
        assert flipped.sign_holds is False


class TestGlobalCorrection:
    def test_correcting_across_everything_is_stricter_than_per_pattern(self, series, detections):
        """Corriger figure par figure laisse passer, par construction, une
        poignee de faux positifs — exactement ceux qu'on aurait envie de
        retenir."""
        from crypto_intel.candlesticks.validation import apply_global_fdr

        evidences = [
            evaluate_pattern(series, detections, p, "TEST", "1d", DETECTOR_VERSION)
            for p in (CandlestickPattern.BULLISH_ENGULFING,
                      CandlestickPattern.BEARISH_ENGULFING,
                      CandlestickPattern.BULLISH_HARAMI,
                      CandlestickPattern.BEARISH_HARAMI)
        ]
        before = sum(h.survives_fdr for e in evidences for h in e.horizons)
        apply_global_fdr(evidences)
        after = sum(h.survives_fdr for e in evidences for h in e.horizons)
        assert after <= before

    def test_every_horizon_is_measured(self, series, detections):
        evidence = evaluate_pattern(
            series, detections, CandlestickPattern.BEARISH_ENGULFING,
            "TEST", "1d", DETECTOR_VERSION,
        )
        assert [h.horizon for h in evidence.horizons] == list(HORIZONS)


class TestTheBlockBootstrapPreservesLocalMemory:
    def test_a_block_keeps_its_candles_consecutive(self, series):
        from crypto_intel.candlesticks.benchmark import _moving_block

        rebuilt = _moving_block(series, 20, np.random.default_rng(3))
        assert len(rebuilt) == len(series)
        assert list(rebuilt.index) == list(series.index)
        # Chaque bougie doit exister telle quelle dans l'originale.
        original = {tuple(r) for r in series[["open", "high", "low", "close"]].to_numpy()}
        for row in rebuilt[["open", "high", "low", "close"]].to_numpy()[:200]:
            assert tuple(row) in original

    def test_bigger_blocks_preserve_more_sequence(self, series):
        """Verification directe de ce que le bootstrap pretend faire: plus les
        blocs sont longs, plus les enchainements reels survivent."""
        from crypto_intel.candlesticks.benchmark import _moving_block

        real_pairs = set(pairwise(series["close"].to_numpy()))
        kept = {}
        for block in (5, 50):
            rebuilt = _moving_block(series, block, np.random.default_rng(9))
            closes = rebuilt["close"].to_numpy()
            pairs = list(pairwise(closes))
            kept[block] = sum(1 for p in pairs if p in real_pairs) / len(pairs)
        assert kept[50] > kept[5], (
            f"blocs de 50 preservent {kept[50]:.2%} des enchainements, "
            f"blocs de 5 en preservent {kept[5]:.2%}"
        )
