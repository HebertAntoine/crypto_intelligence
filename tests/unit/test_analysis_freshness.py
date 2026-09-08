"""L'âge d'une analyse, et ce qu'elle a encore le droit d'affirmer.

Une lecture calculée à 13:24 et affichée à 17:16 se présentait comme
« maintenant ». Quatre heures sur un marché crypto, c'est un autre marché : le
prix sur lequel le verdict a été calculé n'existe plus.

Ces tests tiennent la frontière entre une analyse qu'on peut suivre et une
analyse qu'il faut d'abord actualiser.
"""

from __future__ import annotations

from datetime import datetime, timedelta

import pytest

from crypto_intel.core.enums import Asset
from crypto_intel.engines.analysis_context import (
    AnalysisFreshness,
    analysis_freshness,
    context_for,
    freshness_sentence,
    live_layer,
)


class TestTheAgeDecidesTheStatus:
    """TEST 9 — une analyse de plusieurs heures doit se dire périmée."""

    @pytest.mark.parametrize(
        ("seconds", "expected"),
        [
            (0, AnalysisFreshness.FRESH),
            (60, AnalysisFreshness.FRESH),
            (900, AnalysisFreshness.FRESH),
            (901, AnalysisFreshness.AGING),
            (3600, AnalysisFreshness.AGING),
            (3601, AnalysisFreshness.STALE),
            (10800, AnalysisFreshness.STALE),
            (10801, AnalysisFreshness.EXPIRED),
            (4 * 3600, AnalysisFreshness.EXPIRED),
        ],
    )
    def test_each_band(self, seconds, expected):
        assert analysis_freshness(seconds) is expected

    def test_a_four_hour_old_analysis_is_not_actionable(self):
        """Le cas exact de la capture: 13:24 affiché à 17:16."""
        age = (datetime(2026, 9, 8, 17, 16) - datetime(2026, 9, 8, 13, 24))
        status = analysis_freshness(age.total_seconds())
        assert status is AnalysisFreshness.EXPIRED
        assert status.is_actionable is False

    def test_a_fresh_analysis_is_actionable(self):
        assert analysis_freshness(300).is_actionable is True
        assert analysis_freshness(1800).is_actionable is True

    def test_the_sentence_never_says_now_for_an_old_reading(self):
        for seconds in (3700, 10900, 20000):
            sentence = freshness_sentence(analysis_freshness(seconds), seconds)
            assert "maintenant" not in sentence.lower()
            assert "Actualisée il y a" not in sentence

    def test_the_age_is_written_for_a_human(self):
        assert freshness_sentence(AnalysisFreshness.FRESH, 480) == (
            "Actualisée il y a 8 min"
        )
        assert "3 h 52" in freshness_sentence(AnalysisFreshness.EXPIRED, 13920)


class TestOfflineMode:
    """TEST 10 — un ancien instantané ne se présente jamais comme live."""

    def test_offline_names_itself_and_its_age(self):
        sentence = freshness_sentence(
            AnalysisFreshness.EXPIRED, 13920, offline=True
        )
        assert "hors ligne" in sentence.lower()
        assert "non actualisée" in sentence.lower()
        assert "3 h 52" in sentence

    def test_the_status_travels_with_the_payload(self):
        """L'écran ne doit pas recalculer l'âge: chaque écran le ferait autrement."""
        snapshot = context_for(Asset.BTC)
        layer = live_layer(snapshot, {"price_usd": 1.0, "method": "test"})
        analysis = layer["analysis"]
        assert analysis["freshness_status"] in {s.value for s in AnalysisFreshness}
        assert isinstance(analysis["verdict_is_actionable"], bool)
        assert analysis["freshness_sentence"]
        assert analysis["freshness_limits"]["stale"] == 10800

    def test_an_expired_analysis_marks_the_verdict_inactive(self):
        snapshot = context_for(Asset.BTC)
        old = snapshot.analysis_time + timedelta(hours=5)
        layer = live_layer(snapshot, {"price_usd": 1.0, "method": "test"}, now=old)
        assert layer["analysis"]["freshness_status"] == "EXPIRED"
        assert layer["analysis"]["verdict_is_actionable"] is False


class TestLevelsUseTheAnalysisReference:
    """TEST 11 — les pourcentages partent du prix de référence, pas du live."""

    def test_distances_are_measured_from_the_analysis_price(self):
        from types import SimpleNamespace

        from crypto_intel.engines.today_view import nearest_levels

        snapshot = SimpleNamespace(
            price_at_analysis=100.0,
            supports=[SimpleNamespace(price=95.0, touches=3, strength=70.0,
                                      last_touch=None)],
            resistances=[SimpleNamespace(price=104.0, touches=4, strength=90.0,
                                         last_touch=None)],
        )
        block = nearest_levels(snapshot)
        assert block["reference_price"] == 100.0
        assert block["reference_is_analysis_price"] is True
        # (95 - 100) / 100 * 100 = -5
        assert block["support"]["distance_pct"] == pytest.approx(-5.0)
        # (104 - 100) / 100 * 100 = +4
        assert block["resistance"]["distance_pct"] == pytest.approx(4.0)

    def test_the_sign_convention_holds(self):
        from types import SimpleNamespace

        from crypto_intel.engines.today_view import nearest_levels

        snapshot = SimpleNamespace(
            price_at_analysis=67120.0,
            supports=[SimpleNamespace(price=65845.0, touches=2, strength=60.0,
                                      last_touch=None)],
            resistances=[SimpleNamespace(price=67925.0, touches=2, strength=60.0,
                                         last_touch=None)],
        )
        block = nearest_levels(snapshot)
        assert block["support"]["distance_pct"] < 0
        assert block["resistance"]["distance_pct"] > 0
        assert block["support_label"] == "Support à"
        assert block["resistance_label"] == "Résistance à"

    def test_the_today_payload_does_not_mix_the_live_price_in(self):
        """Le prix live reste en en-tête; il ne déplace pas les niveaux."""
        import inspect

        from crypto_intel.engines import today_view

        source = inspect.getsource(today_view.render)
        assert "nearest_levels(snapshot)" in source, (
            "les niveaux sont mesurés contre un prix qui n'est pas celui de "
            "l'analyse"
        )
