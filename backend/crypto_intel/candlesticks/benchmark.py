"""Ces figures sont-elles une propriété du marché, ou de l'arithmétique ?

Même question que pour les structures chartistes, mais elle demande ici un
autre test nul, et le choix de ce test est la partie difficile.

**Pourquoi pas une marche aléatoire.** Pour les structures, on simule une série
de même volatilité. Pour les chandeliers, ce serait mesurer surtout la qualité
du générateur : il faudrait inventer une distribution de corps et d'ombres, et
les ratios diraient autant sur ce choix que sur le marché.

**La permutation.** On garde les vraies bougies — chacune intacte, avec son
corps et ses deux ombres — et on mélange leur ORDRE. La distribution des formes
est préservée exactement ; seule la séquence disparaît.

Ce test se valide lui-même : une figure d'une seule barre sans condition de
tendance doit ressortir à **1,00×**, puisque sa fréquence ne dépend que de la
distribution des formes. Un écart y signalerait un défaut du test, pas une
découverte.

**Ce qu'il ne peut pas dire.** Toute figure de deux ou trois barres exige que
des bougies consécutives se ressemblent. Or le regroupement de volatilité est
le fait stylisé le plus robuste de la finance : mélanger le détruit, et les
figures multi-barres deviennent quasi impossibles. Un rapport de 900× ne dit
donc pas que la figure est remarquable — il dit qu'elle a besoin d'une
dépendance sérielle, ce qui est vrai de n'importe quelle suite de bougies.
Mesurer correctement celles-là demanderait un nul qui préserve ce
regroupement : bootstrap par blocs, ou simulation calibrée. Ce n'est pas fait
ici, et le rapport le dit.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any

import numpy as np
import pandas as pd

from ..core.enums import Asset, Timeframe
from ..logging_setup import get_logger
from ..settings import PROJECT_ROOT
from .scan import scan_candlesticks
from .taxonomy import (
    DETECTOR_VERSION,
    NEEDS_PRIOR_TREND,
    PATTERN_BARS,
    CandlestickPattern,
)

log = get_logger("candlesticks.benchmark")

#: Chemin ancré sur la racine du projet, jamais sur le répertoire courant.
ARTEFACT = PROJECT_ROOT / "config" / "candlestick_benchmark.json"

SEED = 20260909
PERMUTATIONS = 8

#: Au-delà de cet écart à 1, une figure d'une barre sans tendance signale un
#: défaut du test nul plutôt qu'un fait de marché.
SANITY_TOLERANCE = 0.15


def _shuffled(frame: pd.DataFrame, rng: np.random.Generator) -> pd.DataFrame:
    """Les mêmes bougies, dans un autre ordre.

    Chaque ligne reste entière — ouverture, haut, bas, clôture voyagent
    ensemble — et l'index d'origine est réappliqué pour que les intervalles
    restent réguliers.
    """
    mixed = frame.iloc[rng.permutation(len(frame))].copy()
    mixed.index = frame.index
    return mixed


def run_benchmark(
    assets: tuple[Asset, ...] = (Asset.BTC, Asset.ETH, Asset.SOL),
    timeframe: Timeframe = Timeframe.D1,
    permutations: int = PERMUTATIONS,
) -> dict[str, Any]:
    """Fréquences réelles contre fréquences sur séries permutées."""
    from collections import Counter

    from ..history import store

    real: Counter[str] = Counter()
    real_bars = 0
    frames: dict[str, pd.DataFrame] = {}
    for asset in assets:
        frame = store.load_candles(asset, timeframe)
        if frame is None or frame.empty:
            continue
        frames[asset.value] = frame
        real_bars += len(frame)
        for detection in scan_candlesticks(frame):
            real[detection.pattern.value] += 1

    if not real_bars:
        return {"available": False, "reason": "no stored history to compare against"}

    rng = np.random.default_rng(SEED)
    shuffled: Counter[str] = Counter()
    shuffled_bars = 0
    for _ in range(permutations):
        for frame in frames.values():
            mixed = _shuffled(frame, rng)
            shuffled_bars += len(mixed)
            for detection in scan_candlesticks(mixed):
                shuffled[detection.pattern.value] += 1

    rows: dict[str, Any] = {}
    for pattern in CandlestickPattern:
        name = pattern.value
        per_real = round(real[name] / real_bars * 1000, 3)
        per_shuffled = round(shuffled[name] / shuffled_bars * 1000, 3)
        ratio = round(per_real / per_shuffled, 2) if per_shuffled > 0 else None
        bars = PATTERN_BARS[pattern]
        needs_trend = pattern in NEEDS_PRIOR_TREND
        rows[name] = {
            "bars": bars,
            "needs_prior_trend": needs_trend,
            "per_1000_real": per_real,
            "per_1000_shuffled": per_shuffled,
            "ratio": ratio,
            # Ce que ce chiffre autorise à dire, figure par figure.
            "interpretable": bars == 1 and not needs_trend,
            "verdict": _verdict(bars, needs_trend, ratio),
        }

    log.info("candlestick_benchmark", real_bars=real_bars,
             shuffled_bars=shuffled_bars, patterns=len(rows))
    return {
        "available": True,
        "measured_at": datetime.now(UTC).isoformat(),
        "seed": SEED,
        "permutations": permutations,
        "timeframe": timeframe.value,
        "assets": [asset.value for asset in assets],
        "real_bars": real_bars,
        "shuffled_bars": shuffled_bars,
        "detector_version": DETECTOR_VERSION,
        "detectors": rows,
        "sanity_check": _sanity(rows),
        "note": (
            "Null model: the same candles in a shuffled order. Single-bar "
            "figures with no trend condition must come out at 1.00x - that is "
            "the test validating itself, not a finding. Multi-bar figures need "
            "serial dependence, which shuffling destroys, so their ratios "
            "measure that need and nothing more."
        ),
    }


def _verdict(bars: int, needs_trend: bool, ratio: float | None) -> str:
    if ratio is None:
        return "ABSENT_FROM_SHUFFLED"
    if bars > 1:
        # Toute figure multi-barres exige une dépendance sérielle; le rapport
        # ne mesure que ce besoin.
        return "REQUIRES_SEQUENCE"
    if needs_trend:
        return "TREND_CONDITIONED"
    if abs(ratio - 1.0) <= SANITY_TOLERANCE:
        return "AS_FREQUENT_AS_ITS_SHAPE_IMPLIES"
    return "SHAPE_DISTRIBUTION_ANOMALY"


def _sanity(rows: dict[str, Any]) -> dict[str, Any]:
    """Le test nul se comporte-t-il comme il le devrait ?

    Les figures d'une barre sans condition de tendance sont le témoin: leur
    rapport doit valoir 1. S'il s'en écarte, c'est la mesure qui est fausse.
    """
    witnesses = {
        name: row["ratio"] for name, row in rows.items()
        if row["interpretable"] and row["ratio"] is not None
    }
    worst = max(
        (abs(ratio - 1.0) for ratio in witnesses.values()), default=None
    )
    return {
        "witnesses": witnesses,
        "worst_deviation": round(worst, 3) if worst is not None else None,
        "passed": worst is not None and worst <= SANITY_TOLERANCE,
        "note": (
            "Single-bar, trend-free figures must land at 1.00x by "
            "construction. A deviation means the permutation is not "
            "preserving what it claims to preserve."
        ),
    }


def load() -> dict[str, Any]:
    if not ARTEFACT.exists():
        return {"available": False, "reason": "candlestick benchmark never run"}
    try:
        return json.loads(ARTEFACT.read_text())
    except (json.JSONDecodeError, OSError) as exc:
        return {"available": False, "reason": f"unreadable artefact: {exc}"[:120]}


# --- bootstrap par blocs ---------------------------------------------------
#
# La permutation simple détruit le regroupement de volatilité, donc toute
# figure de deux ou trois barres devient quasi impossible. Un rapport de 900x
# ne dit alors rien de la figure — il dit que le test nul est trop destructeur.
#
# Le bootstrap par blocs mobiles conserve des morceaux de série intacts: à
# l'intérieur d'un bloc, les dépendances locales survivent. En faisant varier
# la taille des blocs, on voit à partir de quelle longueur de mémoire une
# figure cesse d'être exceptionnelle.
#
# Les tailles sont fixées d'avance et TOUTES rapportées. Choisir après coup
# celle qui donne le résultat souhaité serait le contraire d'une mesure.

BLOCK_SIZES = (5, 10, 20, 50)
BLOCK_REPLICATES = 4


def _moving_block(frame: pd.DataFrame, block: int, rng: np.random.Generator) -> pd.DataFrame:
    """Une série de même longueur, faite de blocs consécutifs tirés au hasard.

    Chaque bloc est une tranche réelle de l'historique: à l'intérieur, tout est
    préservé — l'enchaînement des corps, le regroupement de volatilité, les
    séquences de bougies. Seule la façon dont les blocs se succèdent est
    aléatoire.
    """
    n = len(frame)
    if block >= n:
        return frame.copy()
    starts = rng.integers(0, n - block, size=n // block + 1)
    pieces = [frame.iloc[s: s + block] for s in starts]
    rebuilt = pd.concat(pieces).iloc[:n].copy()
    rebuilt.index = frame.index
    return rebuilt


def block_bootstrap_benchmark(
    assets: tuple[Asset, ...] = (Asset.BTC, Asset.ETH, Asset.SOL),
    timeframe: Timeframe = Timeframe.D1,
    block_sizes: tuple[int, ...] = BLOCK_SIZES,
    replicates: int = BLOCK_REPLICATES,
) -> dict[str, Any]:
    """Fréquences réelles contre un nul qui préserve la mémoire locale."""
    from collections import Counter

    from ..history import store

    real: Counter[str] = Counter()
    real_bars = 0
    frames: dict[str, pd.DataFrame] = {}
    for asset in assets:
        frame = store.load_candles(asset, timeframe)
        if frame is None or frame.empty:
            continue
        frames[asset.value] = frame
        real_bars += len(frame)
        for detection in scan_candlesticks(frame):
            real[detection.pattern.value] += 1

    if not real_bars:
        return {"available": False, "reason": "no stored history"}

    by_block: dict[str, dict[str, float]] = {}
    for block in block_sizes:
        rng = np.random.default_rng(SEED + block)
        counts: Counter[str] = Counter()
        bars = 0
        for _ in range(replicates):
            for frame in frames.values():
                rebuilt = _moving_block(frame, block, rng)
                bars += len(rebuilt)
                for detection in scan_candlesticks(rebuilt):
                    counts[detection.pattern.value] += 1
        by_block[str(block)] = {
            name: round(counts[name] / bars * 1000, 3)
            for name in (p.value for p in CandlestickPattern)
        }

    rows: dict[str, Any] = {}
    for pattern in CandlestickPattern:
        name = pattern.value
        per_real = round(real[name] / real_bars * 1000, 3)
        ratios: dict[str, float | None] = {}
        for block_name, freqs in by_block.items():
            null = freqs[name]
            ratios[block_name] = round(per_real / null, 2) if null > 0 else None
        finite = [r for r in ratios.values() if r is not None]
        rows[name] = {
            "bars": PATTERN_BARS[pattern],
            "per_1000_real": per_real,
            "per_1000_by_block": {b: by_block[b][name] for b in by_block},
            "ratio_by_block": ratios,
            # L'écart entre tailles de blocs EST le résultat: il dit à quel
            # point la conclusion dépend de l'hypothèse de mémoire.
            "ratio_min": min(finite) if finite else None,
            "ratio_max": max(finite) if finite else None,
            "sensitive_to_block_size": (
                bool(finite and max(finite) / max(min(finite), 1e-9) >= 2.0)
            ),
        }

    log.info("block_bootstrap", real_bars=real_bars, blocks=list(by_block))
    return {
        "available": True,
        "measured_at": datetime.now(UTC).isoformat(),
        "seed": SEED,
        "timeframe": timeframe.value,
        "assets": [asset.value for asset in assets],
        "real_bars": real_bars,
        "block_sizes": list(block_sizes),
        "replicates": replicates,
        "detectors": rows,
        "note": (
            "Null model: moving-block bootstrap. Inside a block the real "
            "sequence survives, so local dependence - volatility clustering "
            "above all - is preserved. Every block size is reported: picking "
            "the one that gives the preferred answer would not be a "
            "measurement."
        ),
    }
