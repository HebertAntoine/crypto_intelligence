"""Deux propriétés dont l'absence se voit trop tard.

**Identité.** Une figure re-scannée après une nouvelle bougie doit garder le
même id. Sinon chaque scan crée des occurrences neuves, le suivi d'une figure
dans le temps devient impossible, et un comptage d'observations mesure la
fréquence des scans plutôt que celle des figures.

**Invalidation par version.** Le bug trouvé en PHASE A: les détecteurs avaient
changé, `SCAN_VERSION` non, et le cache servait les anciennes règles sous les
nouvelles. Rien ne le signalait. Ces tests figent la correction.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import numpy as np
import pandas as pd
import pytest

from crypto_intel.core.enums import Timeframe
from crypto_intel.structure import history_scan
from crypto_intel.structure.detection import make_pattern_id


def _frame(closes: np.ndarray, start: datetime | None = None) -> pd.DataFrame:
    n = len(closes)
    index = pd.date_range(start or datetime(2020, 1, 1, tzinfo=UTC), periods=n, freq="D")
    wick = np.abs(closes) * 0.004
    return pd.DataFrame(
        {
            "open": closes - wick * 0.2,
            "high": closes + wick,
            "low": closes - wick,
            "close": closes,
            "volume": np.full(n, 1000.0),
        },
        index=index,
    )


def _leg(a: float, b: float, n: int) -> np.ndarray:
    return np.linspace(a, b, n, endpoint=False)


@pytest.fixture(scope="module")
def series() -> pd.DataFrame:
    """Un double sommet net, suivi de barres supplémentaires."""
    return _frame(np.concatenate([
        _leg(100, 130, 40), _leg(130, 108, 25),
        _leg(108, 129.5, 25), _leg(129.5, 112, 25),
        _leg(112, 118, 20),
    ]))


def _enriched(df: pd.DataFrame, asset: str = "BTC") -> list[dict]:
    figures = [f.to_dict() for f in history_scan.scan_history(df, Timeframe.D1)]
    return history_scan.enrich_with_detection(figures, asset, Timeframe.D1)


class TestIdentityIsStable:
    def test_a_new_candle_does_not_create_a_new_occurrence(self, series):
        """Le cas normal: une barre de plus, les mêmes figures."""
        before = {f["id"]: f["name"] for f in _enriched(series.iloc[:-1])}
        after = {f["id"]: f["name"] for f in _enriched(series)}
        assert before, "rien à comparer"
        shared = set(before) & set(after)
        assert shared, (
            "aucune figure n'a survécu à une bougie supplémentaire: "
            "les identités sont recréées à chaque scan"
        )
        for pattern_id in shared:
            assert before[pattern_id] == after[pattern_id]

    def test_the_id_is_derived_from_the_occurrence_not_from_the_clock(self):
        """Rejouer le même calcul deux fois doit donner le même id."""
        start = datetime(2021, 5, 1, tzinfo=UTC)
        end = datetime(2021, 6, 1, tzinfo=UTC)
        first = make_pattern_id("BTC", "1d", "double_top", start, end)
        # La chaîne ISO doit donner la même identité que l'objet: sinon
        # l'occurrence change d'id selon l'endroit d'où on la demande.
        second = make_pattern_id(
            "BTC", "1d", "double_top", start.isoformat(), end.isoformat()
        )
        assert first == second

    def test_a_structurally_different_figure_gets_a_different_id(self):
        """Comportement documenté: changer la fenêtre change l'occurrence."""
        start = datetime(2021, 5, 1, tzinfo=UTC)
        end = datetime(2021, 6, 1, tzinfo=UTC)
        same = make_pattern_id("BTC", "1d", "double_top", start, end)
        moved = make_pattern_id(
            "BTC", "1d", "double_top", start, end + timedelta(days=1)
        )
        assert same != moved

    def test_the_same_shape_on_two_assets_is_two_occurrences(self):
        start, end = datetime(2021, 5, 1, tzinfo=UTC), datetime(2021, 6, 1, tzinfo=UTC)
        btc = make_pattern_id("BTC", "1d", "double_top", start, end)
        eth = make_pattern_id("ETH", "1d", "double_top", start, end)
        assert btc != eth


class TestVersionInvalidatesTheCache:
    """Le bug de PHASE A, figé.

    Les détecteurs avaient changé sans que la version du cache bouge: les
    anciennes réponses étaient servies sous les nouvelles règles, en silence.
    """

    @pytest.fixture
    def isolated(self, tmp_path, monkeypatch):
        monkeypatch.setattr(history_scan, "SCAN_DIR", tmp_path)
        monkeypatch.setattr(history_scan, "_memo", {})
        return history_scan

    def test_the_cache_file_carries_the_version_in_its_name(self, isolated, series):
        isolated.scan_cached("BTC", Timeframe.D1, series)
        written = list(isolated.SCAN_DIR.iterdir())
        assert written, "aucun cache écrit"
        assert all(isolated.SCAN_VERSION in path.name for path in written), (
            "le nom du fichier ne porte pas la version: une nouvelle version "
            "écraserait l'ancienne au lieu de l'ignorer"
        )

    def test_bumping_the_version_ignores_the_previous_scan(
        self, isolated, series, monkeypatch
    ):
        first = isolated.scan_cached("BTC", Timeframe.D1, series)
        assert first

        monkeypatch.setattr(isolated, "SCAN_VERSION", "test-bumped-version")
        monkeypatch.setattr(isolated, "_memo", {})
        # Nouveau nom de fichier, donc aucune reprise: le balayage repart de
        # zéro plutôt que de servir les résultats d'anciennes règles.
        second = isolated.scan_cached("BTC", Timeframe.D1, series)
        names = {path.name for path in isolated.SCAN_DIR.iterdir()}
        assert len(names) == 2, f"une seule entrée pour deux versions: {names}"
        assert [f["name"] for f in first] == [f["name"] for f in second]

    def test_a_different_series_is_not_served_from_cache(self, isolated, series):
        """Même longueur, même dernière barre, prix différents."""
        isolated.scan_cached("BTC", Timeframe.D1, series)
        other = series.copy()
        other["close"] = other["close"] * 1.5
        other["high"] = other["high"] * 1.5
        other["low"] = other["low"] * 1.5
        isolated._memo.clear()
        assert isolated._stamp(other) != isolated._stamp(series), (
            "deux séries différentes partagent une empreinte: le cache de "
            "l'une pourrait être servi pour l'autre"
        )


class TestTheArtefactPathDoesNotDependOnTheWorkingDirectory:
    """Le second bug de PHASE A.

    Le repère au hasard était lu depuis un chemin relatif; l'API tourne depuis
    `backend/`, donc le fichier n'était jamais trouvé et le rapport arrivait
    vide sans qu'aucune erreur ne soit levée.
    """

    def test_the_benchmark_artefact_is_an_absolute_path(self):
        from crypto_intel.structure import noise_benchmark

        assert noise_benchmark.ARTEFACT.is_absolute(), (
            "chemin relatif: le contenu dépendrait du répertoire de lancement"
        )

    def test_it_resolves_the_same_from_any_directory(self, tmp_path, monkeypatch):
        import importlib

        from crypto_intel.structure import noise_benchmark

        expected = noise_benchmark.ARTEFACT
        monkeypatch.chdir(tmp_path)
        importlib.reload(noise_benchmark)
        assert expected == noise_benchmark.ARTEFACT

    def test_a_missing_artefact_says_so_instead_of_looking_empty(
        self, monkeypatch, tmp_path
    ):
        from crypto_intel.structure import noise_benchmark

        monkeypatch.setattr(noise_benchmark, "ARTEFACT", tmp_path / "absent.json")
        loaded = noise_benchmark.load()
        assert loaded["available"] is False
        assert loaded["reason"], "une absence sans raison est indistinguable d'un vide"
