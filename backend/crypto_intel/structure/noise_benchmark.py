"""How often each figure appears in price that contains no figures at all.

A detector that finds four thousand double tops on nine years of BTC has
proved nothing until you know how many it finds on nine years of *noise*. If
the two numbers match, the shape is not a property of the market: it is a
property of any random walk with that volatility, and the count describes the
detector rather than the price.

This is the measurement §14 asks for, made explicit instead of assumed. It is
deliberately not a claim about profit - `edge_state` still answers that, and
still says NOT_YET_TESTED. It answers a narrower and prior question: does this
shape occur more often here than in randomness?

The benchmark is reproducible: same seed, same volatility, same answer. It is
stored as an artefact rather than computed on import, because replaying ten
random histories through every detector takes minutes.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

import numpy as np
import pandas as pd

from ..core.enums import Asset, Timeframe
from ..logging_setup import get_logger
from ..settings import PROJECT_ROOT

log = get_logger("structure.noise_benchmark")

#: Where the measured result lives. Committed, so the app can state the ratio
#: without re-running minutes of simulation.
#:
#: Ancré sur la racine du projet et non sur le répertoire courant: l'API est
#: lancée depuis `backend/`, et un chemin relatif y cherchait un fichier
#: inexistant — le rapport au hasard arrivait vide sans que rien ne le dise.
ARTEFACT = PROJECT_ROOT / "config" / "noise_benchmark.json"

#: Fixed, so the number is the same for everyone who reruns it.
SEED = 20260909
WALKS = 10


@dataclass(slots=True)
class NoiseRatio:
    """One detector, measured against randomness."""

    name: str
    per_1000_real: float
    per_1000_noise: float

    @property
    def ratio(self) -> float | None:
        """How much more often on real prices than on noise.

        None when the shape never appeared in noise: a ratio against zero
        would be infinite, and reporting infinity for a shape seen twice
        would be worse than reporting nothing.
        """
        if self.per_1000_noise <= 0:
            return None
        return round(self.per_1000_real / self.per_1000_noise, 2)

    @property
    def verdict(self) -> str:
        ratio = self.ratio
        if ratio is None:
            return "ABSENT_FROM_NOISE"
        if ratio >= 2.0:
            return "MORE_THAN_NOISE"
        if ratio <= 0.75:
            return "LESS_THAN_NOISE"
        return "INDISTINGUISHABLE_FROM_NOISE"


def daily_volatility(df: pd.DataFrame) -> float:
    """The log-return standard deviation the random walks must reproduce.

    Calibrating the noise to the asset's own volatility is what makes the
    comparison fair: a quiet random walk would produce fewer figures for a
    reason that has nothing to do with the shapes.
    """
    closes = df["close"].to_numpy(dtype=float)
    return float(np.std(np.diff(np.log(closes))))


def _synthetic(closes: np.ndarray) -> pd.DataFrame:
    n = len(closes)
    index = pd.date_range(datetime(2015, 1, 1, tzinfo=UTC), periods=n, freq="D")
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


def run_benchmark(
    assets: tuple[Asset, ...] = (Asset.BTC, Asset.ETH, Asset.SOL),
    timeframe: Timeframe = Timeframe.D1,
    walks: int = WALKS,
) -> dict[str, Any]:
    """Count figures on real history and on volatility-matched noise."""
    from collections import Counter

    from ..history import store
    from .history_scan import scan_history

    real: Counter[str] = Counter()
    real_bars = 0
    volatilities = []
    for asset in assets:
        df = store.load_candles(asset, timeframe)
        if df is None or df.empty:
            continue
        real_bars += len(df)
        volatilities.append(daily_volatility(df))
        for figure in scan_history(df, timeframe):
            real[figure.name] += 1

    if not real_bars:
        return {"available": False, "reason": "no stored history to compare against"}

    sigma = float(np.mean(volatilities))
    bars_each = real_bars // max(1, len(volatilities))
    rng = np.random.default_rng(SEED)
    noise: Counter[str] = Counter()
    noise_bars = 0
    for _ in range(walks):
        closes = 100 * np.exp(np.cumsum(rng.normal(0, sigma, bars_each)))
        frame = _synthetic(closes)
        noise_bars += len(frame)
        for figure in scan_history(frame, timeframe):
            noise[figure.name] += 1

    rows = []
    for name in sorted(set(real) | set(noise)):
        rows.append(NoiseRatio(
            name=name,
            per_1000_real=round(real[name] / real_bars * 1000, 3),
            per_1000_noise=round(noise[name] / noise_bars * 1000, 3),
        ))

    log.info(
        "noise_benchmark", real_bars=real_bars, noise_bars=noise_bars,
        sigma=round(sigma, 5), detectors=len(rows),
    )
    return {
        "available": True,
        "measured_at": datetime.now(UTC).isoformat(),
        "seed": SEED,
        "timeframe": timeframe.value,
        "assets": [asset.value for asset in assets],
        "real_bars": real_bars,
        "noise_bars": noise_bars,
        "noise_sigma": round(sigma, 6),
        "detectors": {
            row.name: {
                "per_1000_real": row.per_1000_real,
                "per_1000_noise": row.per_1000_noise,
                "ratio": row.ratio,
                "verdict": row.verdict,
            }
            for row in rows
        },
        "note": (
            "How often each shape appears on real prices versus on random "
            "walks matched to the same volatility. A ratio near 1 means the "
            "shape is what randomness produces anyway. This is NOT an edge "
            "measurement - it is the prior question of whether the shape is a "
            "property of the market at all."
        ),
    }


def load() -> dict[str, Any]:
    """The stored measurement, or an explicit absence."""
    if not ARTEFACT.exists():
        return {
            "available": False,
            "reason": (
                "noise benchmark never run - `crypto-intel noise-benchmark` "
                "produces it"
            ),
        }
    try:
        return json.loads(ARTEFACT.read_text())
    except (json.JSONDecodeError, OSError) as exc:
        return {"available": False, "reason": f"unreadable artefact: {exc}"[:120]}


def ratio_for(name: str) -> dict[str, Any] | None:
    """What the benchmark says about one detector, if it says anything."""
    stored = load()
    if not stored.get("available"):
        return None
    return (stored.get("detectors") or {}).get(name)
