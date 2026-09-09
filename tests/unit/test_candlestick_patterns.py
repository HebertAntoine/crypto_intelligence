"""Les figures de chandeliers, et la frontiere avec les structures chartistes.

Le test le plus important de ce fichier est celui du marteau et du pendu: la
MEME bougie, a la MEME echelle, doit changer de nom selon ce qui la precede.
C'est le point le plus souvent rate dans les implementations de chandeliers, et
le rater revient a attribuer les deux noms au hasard.

Le second test qui compte est celui de la separation des taxonomies. Rien dans
le code ne doit permettre de compter un HAMMER et un DOUBLE_TOP ensemble: l'un
tient en une barre, l'autre en centaines.
"""

from __future__ import annotations

from datetime import UTC, datetime

import numpy as np
import pandas as pd
import pytest

from crypto_intel.candlesticks import (
    CandlestickPattern,
    detect_at,
    scan_candlesticks,
)
from crypto_intel.candlesticks.anatomy import prior_trend
from crypto_intel.candlesticks.taxonomy import (
    NEEDS_PRIOR_TREND,
    PATTERN_BARS,
    PATTERN_FAMILY,
)

ATR = 2.0
START = datetime(2024, 1, 1, tzinfo=UTC)


def _frame(rows: list[tuple[float, float, float, float]]) -> pd.DataFrame:
    """`rows` = (open, high, low, close)."""
    index = pd.date_range(START, periods=len(rows), freq="D")
    return pd.DataFrame(
        {
            "open": [r[0] for r in rows],
            "high": [r[1] for r in rows],
            "low": [r[2] for r in rows],
            "close": [r[3] for r in rows],
            "volume": np.full(len(rows), 1000.0),
        },
        index=index,
    )


def _run(rows, index=None):
    frame = _frame(rows)
    return detect_at(frame, index if index is not None else len(rows) - 1, ATR)


def _names(rows, index=None):
    return {d.pattern for d in _run(rows, index)}


#: Cinq barres qui descendent d'environ 5 ATR: une tendance baissiere nette.
DOWNTREND = [(110 - 2 * i, 111 - 2 * i, 109 - 2 * i, 109 - 2 * i) for i in range(6)]
#: Le miroir.
UPTREND = [(90 + 2 * i, 91 + 2 * i, 89 + 2 * i, 91 + 2 * i) for i in range(6)]
#: Cinq barres plates: aucune tendance.
FLAT = [(100, 100.5, 99.5, 100) for _ in range(6)]


class TestTheSameCandleChangesNameWithItsContext:
    """Le point central de l'analyse en chandeliers."""

    #: Petit corps en haut, longue ombre basse, pas d'ombre haute.
    #: Corps petit mais REEL: un corps quasi nul en ferait un doji libellule,
    #: ce qui est une autre figure.
    HAMMER_SHAPE = (100.0, 101.0, 96.0, 100.8)

    def test_after_a_fall_it_is_a_hammer(self):
        assert CandlestickPattern.HAMMER in _names([*DOWNTREND, self.HAMMER_SHAPE])

    def test_after_a_rise_the_identical_candle_is_a_hanging_man(self):
        assert CandlestickPattern.HANGING_MAN in _names([*UPTREND, self.HAMMER_SHAPE])

    def test_without_a_trend_it_is_neither(self):
        """Nommer sur la moitie d'une definition serait pire que se taire."""
        found = _names([*FLAT, self.HAMMER_SHAPE])
        assert CandlestickPattern.HAMMER not in found
        assert CandlestickPattern.HANGING_MAN not in found

    #: Miroir vertical: corps en bas, longue ombre haute.
    STAR_SHAPE = (100.0, 105.0, 99.8, 100.8)

    def test_the_inverted_shape_is_symmetric(self):
        assert CandlestickPattern.INVERTED_HAMMER in _names([*DOWNTREND, self.STAR_SHAPE])
        assert CandlestickPattern.SHOOTING_STAR in _names([*UPTREND, self.STAR_SHAPE])


class TestSingleBarShapes:
    def test_a_doji_has_almost_no_body(self):
        assert CandlestickPattern.DOJI in _names([*FLAT, (100.0, 103.0, 97.0, 100.05)])

    def test_a_dragonfly_puts_all_its_range_below(self):
        found = _names([*FLAT, (100.0, 100.1, 96.0, 100.05)])
        assert CandlestickPattern.DRAGONFLY_DOJI in found

    def test_a_gravestone_puts_all_its_range_above(self):
        found = _names([*FLAT, (100.0, 104.0, 99.9, 100.05)])
        assert CandlestickPattern.GRAVESTONE_DOJI in found

    def test_a_marubozu_has_no_shadows(self):
        assert CandlestickPattern.MARUBOZU_BULLISH in _names([*FLAT, (100.0, 104.0, 100.0, 104.0)])
        assert CandlestickPattern.MARUBOZU_BEARISH in _names([*FLAT, (104.0, 104.0, 100.0, 100.0)])

    def test_a_spinning_top_has_a_small_body_and_two_shadows(self):
        assert CandlestickPattern.SPINNING_TOP in _names([*FLAT, (100.0, 103.0, 97.0, 101.2)])

    def test_a_flat_candle_with_no_range_produces_nothing(self):
        """Quatre prix identiques n'est pas un doji parfait: c'est une absence."""
        assert _names([*FLAT, (100.0, 100.0, 100.0, 100.0)]) == set()


class TestTwoBarPatterns:
    def test_bullish_engulfing(self):
        rows = [*DOWNTREND, (100.0, 100.5, 98.0, 98.5), (98.0, 103.0, 97.5, 102.0)]
        assert CandlestickPattern.BULLISH_ENGULFING in _names(rows)

    def test_bearish_engulfing(self):
        rows = [*UPTREND, (100.0, 102.0, 99.5, 101.5), (102.0, 102.5, 97.0, 98.0)]
        assert CandlestickPattern.BEARISH_ENGULFING in _names(rows)

    def test_a_bigger_candle_that_does_not_cover_is_not_engulfing(self):
        """Sans le recouvrement, toute grande bougie deviendrait une englobante."""
        rows = [*DOWNTREND, (104.0, 104.5, 100.0, 100.5), (99.0, 103.0, 98.5, 102.5)]
        assert CandlestickPattern.BULLISH_ENGULFING not in _names(rows)

    def test_bullish_harami_sits_inside_its_predecessor(self):
        rows = [*DOWNTREND, (106.0, 106.5, 99.0, 99.5), (101.0, 103.0, 100.5, 102.5)]
        assert CandlestickPattern.BULLISH_HARAMI in _names(rows)

    def test_piercing_line_closes_past_the_midpoint(self):
        rows = [*DOWNTREND, (106.0, 106.5, 99.0, 99.5), (99.0, 104.0, 98.5, 103.5)]
        assert CandlestickPattern.PIERCING_LINE in _names(rows)

    def test_dark_cloud_cover_is_the_mirror(self):
        rows = [*UPTREND, (99.0, 106.5, 98.5, 106.0), (106.0, 106.5, 100.5, 101.0)]
        assert CandlestickPattern.DARK_CLOUD_COVER in _names(rows)


class TestThreeBarPatterns:
    def test_morning_star(self):
        rows = [*DOWNTREND, (106.0, 106.5, 99.0, 99.5), (99.2, 99.8, 98.6, 99.0), (99.5, 105.0, 99.3, 104.5)]
        assert CandlestickPattern.MORNING_STAR in _names(rows)

    def test_evening_star(self):
        rows = [*UPTREND, (99.0, 106.5, 98.5, 106.0), (106.2, 106.8, 105.8, 106.4), (106.0, 106.2, 100.0, 100.5)]
        assert CandlestickPattern.EVENING_STAR in _names(rows)

    def test_the_gap_is_optional_but_recorded(self):
        """Les gaps n'existent quasiment pas en crypto: on ne les exige pas,
        on note s'ils etaient la."""
        rows = [*DOWNTREND, (106.0, 106.5, 99.0, 99.5), (99.2, 99.8, 98.6, 99.0), (99.5, 105.0, 99.3, 104.5)]
        star = next(d for d in _run(rows) if d.pattern is CandlestickPattern.MORNING_STAR)
        assert "gapped" in star.components
        assert isinstance(star.components["gapped"], bool)

    def test_three_white_soldiers(self):
        rows = [*FLAT, (100.0, 102.2, 99.8, 102.0), (101.5, 104.2, 101.3, 104.0), (103.5, 106.2, 103.3, 106.0)]
        assert CandlestickPattern.THREE_WHITE_SOLDIERS in _names(rows)

    def test_three_black_crows(self):
        rows = [*FLAT, (106.0, 106.2, 103.8, 104.0), (104.5, 104.7, 101.8, 102.0), (102.5, 102.7, 99.8, 100.0)]
        assert CandlestickPattern.THREE_BLACK_CROWS in _names(rows)

    def test_three_tiny_candles_are_not_three_soldiers(self):
        """La forme ne suffit pas: la taille fait partie de la definition."""
        rows = [*FLAT, (100.0, 100.15, 99.98, 100.1), (100.05, 100.25, 100.03, 100.2), (100.15, 100.35, 100.13, 100.3)]
        assert CandlestickPattern.THREE_WHITE_SOLDIERS not in _names(rows)


class TestTheTwoTaxonomiesNeverMix:
    """La separation est structurelle, pas seulement documentaire."""

    def test_no_name_is_shared_with_the_chart_structures(self):
        from crypto_intel.structure.patterns import PATTERN_CLASSES

        candlestick = {p.value.lower() for p in CandlestickPattern}
        structural = {name.lower() for name in PATTERN_CLASSES}
        shared = candlestick & structural
        assert not shared, f"noms partages entre les deux taxonomies: {shared}"

    def test_a_candlestick_detection_declares_its_taxonomy(self):
        payload = _run([*DOWNTREND, (100.0, 101.0, 96.0, 100.8)])[0].to_dict()
        assert payload["taxonomy"] == "CANDLESTICK_PATTERN"
        assert "never be aggregated" in payload["separation_note"]

    def test_every_pattern_declares_its_size_and_family(self):
        for pattern in CandlestickPattern:
            assert pattern in PATTERN_BARS, f"{pattern} sans nombre de barres"
            assert pattern in PATTERN_FAMILY, f"{pattern} sans famille"
            assert 1 <= PATTERN_BARS[pattern] <= 3

    def test_recognition_never_travels_without_its_edge_state(self):
        payload = _run([*DOWNTREND, (100.0, 101.0, 96.0, 100.8)])[0].to_dict()
        assert payload["edge_state"] == "NOT_YET_TESTED"
        assert "never a price outcome" in payload["separation_note"]


class TestNoLookahead:
    def test_a_detection_does_not_change_when_later_bars_are_removed(self):
        rows = [*DOWNTREND, (106.0, 106.5, 99.0, 99.5), (99.2, 99.8, 98.6, 99.0), (99.5, 105.0, 99.3, 104.5), (104.0, 108.0, 103.0, 107.0), (107.0, 110.0, 106.0, 109.0)]
        target = len(DOWNTREND) + 2
        with_future = {d.pattern for d in detect_at(_frame(rows), target, ATR)}
        without = {d.pattern for d in detect_at(_frame(rows[: target + 1]), target, ATR)}
        assert with_future == without

    def test_the_prior_trend_never_reads_the_pattern_bar_itself(self):
        """Une longue bougie ne doit pas creer la tendance qu'elle est censee
        retourner: ce serait circulaire."""
        rows = [*FLAT, (100.0, 130.0, 99.0, 129.0)]
        frame = _frame(rows)
        assert prior_trend(frame, len(rows) - 1, ATR) == "NONE"

    def test_every_named_pattern_has_the_trend_its_definition_requires(self):
        rows = [*DOWNTREND, (100.0, 101.0, 96.0, 100.8)]
        for detection in _run(rows):
            required = NEEDS_PRIOR_TREND.get(detection.pattern)
            if required is not None:
                assert detection.prior_trend == required


class TestTheScan:
    def test_a_series_too_short_produces_nothing(self):
        assert scan_candlesticks(_frame(FLAT)) == []

    def test_detections_come_out_oldest_first(self):
        rng = np.random.default_rng(7)
        closes = 100 * np.exp(np.cumsum(rng.normal(0, 0.02, 400)))
        rows = [(c, c * 1.01, c * 0.99, c * 1.002) for c in closes]
        found = scan_candlesticks(_frame(rows))
        times = [d.detected_at for d in found]
        assert times == sorted(times)


class TestThePermutationBenchmarkValidatesItself:
    """Un test nul qu'on n'a pas verifie ne vaut pas mieux qu'une opinion.

    Les figures d'une barre sans condition de tendance sont le temoin: leur
    frequence ne depend que de la distribution des formes, que la permutation
    preserve exactement. Elles DOIVENT ressortir a 1,00x. Un ecart signale que
    le melange ne preserve pas ce qu'il pretend preserver.
    """

    def test_shuffling_keeps_every_candle_intact(self):
        from crypto_intel.candlesticks.benchmark import _shuffled

        rows = [(100 + i, 102 + i, 98 + i, 101 + i) for i in range(50)]
        frame = _frame(rows)
        mixed = _shuffled(frame, np.random.default_rng(1))

        assert len(mixed) == len(frame)
        assert list(mixed.index) == list(frame.index), "l'index doit rester regulier"
        # Chaque bougie doit exister telle quelle dans l'originale: si les
        # colonnes etaient melangees separement, on fabriquerait des bougies
        # qui n'ont jamais existe.
        original = {tuple(row) for row in frame[["open", "high", "low", "close"]].to_numpy()}
        for row in mixed[["open", "high", "low", "close"]].to_numpy():
            assert tuple(row) in original

    def test_the_witness_patterns_are_declared_interpretable(self):
        from crypto_intel.candlesticks.benchmark import _verdict

        assert _verdict(1, False, 1.0) == "AS_FREQUENT_AS_ITS_SHAPE_IMPLIES"
        assert _verdict(1, True, 1.0) == "TREND_CONDITIONED"
        # Une figure multi-barres ne peut pas etre lue comme les autres.
        assert _verdict(3, False, 900.0) == "REQUIRES_SEQUENCE"
        assert _verdict(2, True, None) == "ABSENT_FROM_SHUFFLED"

    def test_a_stored_benchmark_carries_its_own_sanity_verdict(self):
        from crypto_intel.candlesticks import benchmark

        stored = benchmark.load()
        if not stored.get("available"):
            pytest.skip("repere jamais calcule dans cet environnement")
        check = stored["sanity_check"]
        assert check["witnesses"], "aucun temoin: le controle ne controle rien"
        assert check["passed"], (
            f"le test nul dévie de {check['worst_deviation']} sur ses temoins: "
            "c'est la mesure qui est fausse, pas le marche"
        )

    def test_multi_bar_ratios_are_never_presented_as_findings(self):
        """Un rapport de 900x dit que la figure exige une dependance
        serielle, pas qu'elle est remarquable."""
        from crypto_intel.candlesticks import benchmark

        stored = benchmark.load()
        if not stored.get("available"):
            pytest.skip("repere jamais calcule dans cet environnement")
        for name, row in stored["detectors"].items():
            if row["bars"] > 1:
                assert row["interpretable"] is False, f"{name} presente comme lisible"
                assert row["verdict"] in ("REQUIRES_SEQUENCE", "ABSENT_FROM_SHUFFLED")
