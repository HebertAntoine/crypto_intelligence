"""Une métrique ne peut pas avoir deux valeurs dans le même instantané.

Deux contradictions étaient visibles à l'écran, et c'était la même erreur
commise deux fois: un `else` traitant « état valide que je n'ai pas énuméré »
comme « donnée manquante ».

  - le funding affichait « NÉGATIF · p24 » et, trois lignes plus bas,
    « funding percentile unavailable ». La branche ne nommait que NEUTRAL et
    les deux extrêmes; NEGATIVE tombait dans le cas d'absence.
  - la structure 1D valait RANGE_STRUCTURE, une lecture parfaitement établie,
    et se retrouvait comptée comme « Lecture structurelle incomplète » parce
    qu'elle ne penchait d'aucun côté.
"""

from __future__ import annotations

import pytest

from crypto_intel.core.enums import Asset, Timeframe
from crypto_intel.engines.entry_opportunity import EntryOpportunityEngine
from crypto_intel.engines.leverage import LeverageCrowdingEngine
from crypto_intel.structure.market_structure import MarketStructureEngine

ASSETS = [Asset.BTC, Asset.ETH, Asset.SOL]


@pytest.fixture(scope="module")
def assessments() -> dict[Asset, object]:
    engine = EntryOpportunityEngine()
    return {asset: engine.assess(asset, Timeframe.H4) for asset in ASSETS}


class TestFundingHasOneValue:
    @pytest.mark.parametrize("asset", ASSETS)
    def test_a_measured_percentile_is_never_reported_unavailable(
        self, asset, assessments
    ):
        funding = LeverageCrowdingEngine().funding_context(asset)
        if funding.percentile is None:
            pytest.skip("aucun percentile mesuré pour cet actif")

        missing = " ".join(assessments[asset].missing)
        assert "funding percentile unavailable" not in missing, (
            f"{asset.value}: le funding vaut p{funding.percentile:.0f} et "
            "l'explication le déclare indisponible"
        )

    @pytest.mark.parametrize("asset", ASSETS)
    def test_a_measured_band_produces_a_factor(self, asset, assessments):
        funding = LeverageCrowdingEngine().funding_context(asset)
        if funding.percentile is None:
            pytest.skip("aucun percentile mesuré")
        names = {f.name for f in assessments[asset].factors}
        assert any("funding" in name for name in names), (
            f"{asset.value}: percentile mesuré mais aucun facteur funding"
        )


class TestRangeIsAReadingNotAGap:
    @pytest.mark.parametrize("asset", ASSETS)
    def test_a_range_structure_is_not_counted_as_missing(
        self, asset, assessments
    ):
        higher = Timeframe.D1
        structure = MarketStructureEngine().assess(asset, higher)
        if structure.state.value != "RANGE_STRUCTURE":
            pytest.skip("la structure n'est pas en range ici")

        missing = " ".join(assessments[asset].missing)
        assert "RANGE_STRUCTURE" not in missing, (
            f"{asset.value}: un range est une lecture établie, pas une lacune"
        )

    @pytest.mark.parametrize("asset", ASSETS)
    def test_the_higher_timeframe_always_produces_a_factor_when_read(
        self, asset, assessments
    ):
        structure = MarketStructureEngine().assess(asset, Timeframe.D1)
        if structure.state.value not in (
            "BULLISH_STRUCTURE", "BEARISH_STRUCTURE", "RANGE_STRUCTURE"
        ):
            pytest.skip("structure réellement indéterminée")
        names = {f.name for f in assessments[asset].factors}
        assert "higher timeframe structure" in names


class TestNoElseBranchSwallowsAValidState:
    """Le motif à éviter, isolé: seule une absence réelle vaut `missing`."""

    @pytest.mark.parametrize("asset", ASSETS)
    def test_missing_entries_correspond_to_real_absences(
        self, asset, assessments
    ):
        for note in assessments[asset].missing:
            lowered = note.lower()
            assert not any(
                valid in lowered
                for valid in ("range_structure", "neutral", "negative", "positive")
            ), f"{asset.value}: {note!r} nomme un état mesuré, pas une absence"


class TestBranchesDirectly:
    """Sans dépendre des données du moment: le code source des deux branches.

    Les tests ci-dessus sautent quand la base de test n'a ni funding ni
    structure. L'invariant, lui, doit être vérifié en toutes circonstances.
    """

    @staticmethod
    def _source() -> str:
        import inspect

        return inspect.getsource(EntryOpportunityEngine.assess)

    def test_a_range_structure_has_its_own_branch(self):
        source = self._source()
        assert 'RANGE_STRUCTURE' in source, (
            "aucune branche ne traite le range: il retombe dans le cas "
            "d'absence, ce qui le compte comme donnée manquante"
        )
        # La branche du range doit précéder le `else` qui remplit `missing`.
        range_at = source.index('RANGE_STRUCTURE')
        missing_at = source.index('out.missing.append(')
        assert range_at < missing_at, (
            "le range est traité après la branche d'absence: il y retombe"
        )

    def test_a_measured_percentile_has_its_own_branch(self):
        source = self._source()
        assert "elif funding.percentile is not None:" in source, (
            "une bande mesurée hors extrêmes retombe dans « indisponible »"
        )
        branch_at = source.index("elif funding.percentile is not None:")
        unavailable_at = source.index('"funding percentile unavailable"')
        assert branch_at < unavailable_at


class TestLivePriceAndAnalysisAreSeparate:
    """Deux couches, deux horodatages.

    L'écran affichait « Analyse hors ligne · instantané du 7 sept. » au-dessus
    de « LIVE · Kraken · 0,5 s ». Les deux étaient vrais et le tout
    incompréhensible: le prix arrive en direct, l'analyse vient d'un
    instantané, et rien ne le disait.
    """

    def test_the_payload_dates_the_analysis_separately_from_the_price(self):
        import asyncio

        from crypto_intel.api.routes_lot4 import today

        payload = asyncio.run(today("BTC"))
        analysis = payload["analysis"]
        for key in (
            "computed_at", "price_at_analysis", "live_price",
            "price_drift_pct", "stale_for_current_price",
        ):
            assert key in analysis, f"{key} manquant"

    def test_drift_is_measured_against_the_price_the_analysis_used(self):
        import asyncio

        from crypto_intel.api.routes_lot4 import today

        analysis = asyncio.run(today("BTC"))["analysis"]
        if analysis["price_at_analysis"] is None or analysis["live_price"] is None:
            pytest.skip("un des deux prix est absent")

        expected = (
            analysis["live_price"] / analysis["price_at_analysis"] - 1
        ) * 100
        assert analysis["price_drift_pct"] == pytest.approx(expected, abs=0.01)

    def test_a_large_drift_marks_the_reading_as_no_longer_current(self):
        import asyncio

        from crypto_intel.api.routes_lot4 import today

        analysis = asyncio.run(today("BTC"))["analysis"]
        drift = analysis["price_drift_pct"]
        if drift is None:
            pytest.skip("aucune dérive calculable")
        threshold = analysis["drift_threshold_pct"]
        assert analysis["stale_for_current_price"] is (abs(drift) >= threshold)

    def test_the_ui_never_calls_it_offline_when_the_price_is_live(self):
        from pathlib import Path

        screen = (
            Path(__file__).resolve().parents[2]
            / "app" / "lib" / "screens" / "today_screen.dart"
        ).read_text(encoding="utf-8")
        # Le sous-titre doit choisir selon les deux couches, pas selon un
        # unique statut de page.
        assert "_subtitleForLayers" in screen
        assert "Prix en direct · analyse calculée à" in screen
