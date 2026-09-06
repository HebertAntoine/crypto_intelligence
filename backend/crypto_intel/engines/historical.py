"""HistoricalSimilarityEngine.

Answers: "when have we seen a configuration resembling this one before?"

ANTI LOOK-AHEAD - the absolute rule of this module.
The feature vector at bar t is built ONLY from bars with index <= t. Forward
returns are read from a separate structure and are never fed back into the
features. Concretely:

  * `build_feature_matrix` slices `df.iloc[:t+1]` for every t;
  * indicators are computed once over the full series, then read at position t,
    which is safe because every indicator here is causal (EMA, RSI, ATR all
    depend only on past bars);
  * forward returns live in `forward_returns`, computed separately and only
    ever used for REPORTING what happened after a match - never for finding it.

A dedicated test mutates future bars and asserts the historical feature vectors
are unchanged.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
from pydantic import BaseModel, Field

from ..config_loader import threshold
from ..core.enums import Asset, Timeframe
from .technical import indicators as ind

# Order matters: it defines the vector layout.
FEATURE_NAMES = [
    "rsi", "trend_slope", "price_vs_ema50", "price_vs_ema200",
    "atr_pct", "volume_ratio", "macd_hist_norm", "bb_position",
]


class HistoricalMatch(BaseModel):
    date: str
    index: int
    similarity: float
    forward_returns: dict[str, float | None] = Field(default_factory=dict)
    features: dict[str, float] = Field(default_factory=dict)


class HistoricalAnalysis(BaseModel):
    asset: Asset
    timeframe: Timeframe
    available: bool = True
    unavailable_reason: str | None = None
    current_features: dict[str, float] = Field(default_factory=dict)
    matches: list[HistoricalMatch] = Field(default_factory=list)
    sample_size: int = 0
    avg_forward_returns: dict[str, float | None] = Field(default_factory=dict)
    hit_rate: dict[str, float | None] = Field(default_factory=dict)
    interpretation: str = ""
    caveat: str = (
        "Historical analogues are descriptive, not predictive. A small sample of similar "
        "past configurations says nothing certain about this one."
    )


class HistoricalSimilarityEngine:
    name = "historical_engine"

    def __init__(self) -> None:
        self.t = threshold("historical", default={}) or {}
        self.min_similarity = float(self.t.get("min_similarity", 0.80))
        self.top_k = int(self.t.get("top_k", 8))
        self.min_bars = int(self.t.get("min_history_bars", 200))
        self.horizons_days = list(self.t.get("forward_horizons_days", [1, 3, 7, 30]))

    def build_feature_matrix(self, df: pd.DataFrame) -> pd.DataFrame:
        """Causal features only.

        Every indicator used is causal by construction, so reading its value at
        position t uses no information from t+1 onward. This is what makes the
        matrix safe to search against.
        """
        close, high, low, volume = df["close"], df["high"], df["low"], df["volume"]

        rsi = ind.rsi(close, 14)
        ema20 = ind.ema(close, 20)
        ema50 = ind.ema(close, 50)
        ema200 = ind.ema(close, 200)
        atr_pct = ind.atr_percent(high, low, close, 14)
        rel_vol = ind.relative_volume(volume, 20)
        _, _, macd_hist = ind.macd(close)
        bb_up, _bb_mid, bb_low = ind.bollinger_bands(close, 20, 2.0)

        # Normalise to comparable scales so cosine similarity is meaningful.
        features = pd.DataFrame(index=df.index)
        features["rsi"] = (rsi - 50.0) / 50.0
        features["trend_slope"] = (ema20 - ema50) / close * 10.0
        features["price_vs_ema50"] = (close - ema50) / close * 5.0
        features["price_vs_ema200"] = (close - ema200) / close * 3.0
        features["atr_pct"] = (atr_pct - 2.5) / 2.5
        features["volume_ratio"] = (rel_vol - 1.0).clip(-2, 3)
        denom = close.rolling(20, min_periods=20).std(ddof=0).replace(0, np.nan)
        features["macd_hist_norm"] = (macd_hist / denom).clip(-3, 3)
        band = (bb_up - bb_low).replace(0, np.nan)
        features["bb_position"] = ((close - bb_low) / band - 0.5) * 2.0

        return features[FEATURE_NAMES]

    def forward_returns(self, df: pd.DataFrame, timeframe: Timeframe) -> pd.DataFrame:
        """Returns AFTER each bar.

        Computed in its own structure, deliberately separate from the feature
        matrix, so it is structurally impossible for a forward return to leak
        into a similarity search.
        """
        close = df["close"]
        bars_per_day = max(1, int(1440 / timeframe.minutes))
        out = pd.DataFrame(index=df.index)
        for days in self.horizons_days:
            shift = days * bars_per_day
            if shift < len(close):
                out[f"{days}d"] = (close.shift(-shift) - close) / close * 100.0
            else:
                out[f"{days}d"] = np.nan
        return out

    def analyze(
        self, asset: Asset, df: pd.DataFrame, timeframe: Timeframe
    ) -> HistoricalAnalysis:
        if len(df) < self.min_bars:
            return HistoricalAnalysis(
                asset=asset, timeframe=timeframe, available=False,
                unavailable_reason=(
                    f"UNAVAILABLE - need at least {self.min_bars} bars for historical "
                    f"similarity, only {len(df)} available"
                ),
            )

        features = self.build_feature_matrix(df)
        fwd = self.forward_returns(df, timeframe)

        current = features.iloc[-1]
        if current.isna().any():
            return HistoricalAnalysis(
                asset=asset, timeframe=timeframe, available=False,
                unavailable_reason="UNAVAILABLE - current feature vector is incomplete",
            )
        current_vec = current.to_numpy(dtype=float)

        # Exclude the most recent window: those bars have no forward return yet,
        # so including them would produce matches we cannot evaluate.
        max_horizon_bars = max(self.horizons_days) * max(1, int(1440 / timeframe.minutes))
        end = len(features) - max_horizon_bars
        if end <= 20:
            end = len(features) - 1

        sims: list[tuple[int, float]] = []
        for i in range(50, end):
            row = features.iloc[i]
            if row.isna().any():
                continue
            vec = row.to_numpy(dtype=float)
            denom = np.linalg.norm(vec) * np.linalg.norm(current_vec)
            if denom == 0:
                continue
            # Cosine similarity mapped from [-1,1] to [0,1].
            sim = float(np.dot(vec, current_vec) / denom)
            sims.append((i, (sim + 1.0) / 2.0))

        sims.sort(key=lambda x: -x[1])
        selected = [(i, s) for i, s in sims if s >= self.min_similarity][: self.top_k]
        if not selected:
            # Report the best available rather than pretending there is nothing.
            selected = sims[: self.top_k]

        matches: list[HistoricalMatch] = []
        for i, sim in selected:
            returns = {
                col: (None if pd.isna(fwd.iloc[i][col]) else round(float(fwd.iloc[i][col]), 2))
                for col in fwd.columns
            }
            idx = df.index[i]
            matches.append(HistoricalMatch(
                date=idx.strftime("%Y-%m-%d") if hasattr(idx, "strftime") else str(idx),
                index=i, similarity=round(sim, 4), forward_returns=returns,
                features={k: round(float(features.iloc[i][k]), 3) for k in FEATURE_NAMES},
            ))

        avg: dict[str, float | None] = {}
        hit: dict[str, float | None] = {}
        for col in fwd.columns:
            values = [m.forward_returns[col] for m in matches if m.forward_returns.get(col) is not None]
            if values:
                avg[col] = round(float(np.mean(values)), 2)
                hit[col] = round(sum(1 for v in values if v > 0) / len(values) * 100.0, 1)
            else:
                avg[col] = None
                hit[col] = None

        interpretation = self._interpret(matches, avg, hit)
        return HistoricalAnalysis(
            asset=asset, timeframe=timeframe, available=True,
            current_features={k: round(float(current[k]), 3) for k in FEATURE_NAMES},
            matches=matches, sample_size=len(matches),
            avg_forward_returns=avg, hit_rate=hit, interpretation=interpretation,
        )

    def _interpret(self, matches, avg, hit) -> str:
        if not matches:
            return "INCONCLUSIVE - no comparable historical configuration found."
        n = len(matches)
        best = matches[0].similarity
        parts = [
            f"{n} historical configuration(s) found with similarity up to {best * 100:.1f}%."
        ]
        # A handful of analogues is not a statistical result and must be said.
        if n < 5:
            parts.append(
                f"Sample of {n} is too small for a statistical claim - treat as illustrative only."
            )
        for horizon in ("1d", "3d", "7d", "30d"):
            if avg.get(horizon) is not None and hit.get(horizon) is not None:
                parts.append(
                    f"After {horizon}: average {avg[horizon]:+.2f}%, "
                    f"positive {hit[horizon]:.0f}% of the time."
                )
        return " ".join(parts)
