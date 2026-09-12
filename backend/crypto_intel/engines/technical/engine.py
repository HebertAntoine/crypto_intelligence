"""TechnicalAnalysisEngine - fully deterministic, no LLM anywhere.

Produces a TechnicalSnapshot per timeframe: trend, momentum, volatility,
volume, structure, levels, divergences and patterns. Every number here is
computed from candles; nothing is interpreted by a model at this stage.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pandas as pd
from pydantic import BaseModel, Field

from ...config_loader import threshold
from ...core.enums import (
    Direction,
    Freshness,
    MarketStructure,
    Timeframe,
    TrendDirection,
)
from ...core.models import Divergence, Level, OHLCVSeries, PatternMatch, TrendState
from . import indicators as ind
from .divergence import detect_divergences
from .levels import build_levels
from .patterns import PatternContext, all_detectors
from .structure import classify_structure, determine_trend, find_swings


class TechnicalSnapshot(BaseModel):
    """Everything the technical engine knows about one asset on one timeframe."""

    timeframe: Timeframe
    bars: int
    price: float | None = None
    freshness: Freshness = Freshness.UNAVAILABLE
    # The most recent bar is usually still forming. Its volume is a partial
    # accumulation and comparing it to completed bars understates it badly -
    # at 05:00 UTC a daily bar shows a fraction of a full day's volume.
    last_bar_partial: bool = False
    last_bar_completion_pct: float | None = None

    # trend
    trend: TrendState
    ema20: float | None = None
    ema50: float | None = None
    ema100: float | None = None
    ema200: float | None = None
    sma50: float | None = None
    sma200: float | None = None
    price_vs_ema200_pct: float | None = None

    # momentum
    rsi: float | None = None
    rsi_state: str = "UNAVAILABLE"
    macd: float | None = None
    macd_signal: float | None = None
    macd_hist: float | None = None
    macd_state: str = "UNAVAILABLE"
    stoch_k: float | None = None
    adx: float | None = None

    # volatility
    bb_upper: float | None = None
    bb_middle: float | None = None
    bb_lower: float | None = None
    bb_bandwidth: float | None = None
    bb_bandwidth_percentile: float | None = None
    bollinger_squeeze: bool | None = None
    bollinger_direction_contribution: float = 0.0
    bollinger_expected_movement: str = "UNKNOWN"
    bb_position: float | None = None
    atr: float | None = None
    atr_pct: float | None = None
    realized_vol: float | None = None
    volatility_state: str = "UNAVAILABLE"

    # volume
    volume: float | None = None
    volume_avg: float | None = None
    relative_volume: float | None = None
    volume_acceleration: float | None = None
    volume_state: str = "UNAVAILABLE"
    obv_slope: float | None = None

    # changes
    change_1_bar_pct: float | None = None
    change_24h_pct: float | None = None
    change_7d_pct: float | None = None

    # structure
    structure: MarketStructure = MarketStructure.UNDETERMINED
    structure_labels: list[str] = Field(default_factory=list)
    swing_high_count: int = 0
    swing_low_count: int = 0

    levels_support: list[Level] = Field(default_factory=list)
    levels_resistance: list[Level] = Field(default_factory=list)
    divergences: list[Divergence] = Field(default_factory=list)
    patterns: list[PatternMatch] = Field(default_factory=list)

    notes: list[str] = Field(default_factory=list)

    @property
    def has_data(self) -> bool:
        return self.bars > 0 and self.price is not None


class TechnicalAnalysisEngine:
    """Computes a TechnicalSnapshot from an OHLCV series."""

    name = "technical_engine"

    def __init__(self) -> None:
        self.t_rsi = threshold("technical", "rsi", default={}) or {}
        self.t_vol = threshold("technical", "volume", default={}) or {}
        self.t_atr = threshold("technical", "atr_pct", default={}) or {}
        self.t_trend = threshold("technical", "trend", default={}) or {}
        self.t_swings = threshold("technical", "swings", default={}) or {}
        self.t_levels = threshold("technical", "levels", default={}) or {}
        self.t_div = threshold("technical", "divergence", default={}) or {}
        self.t_patterns = threshold("patterns", default={}) or {}

    def to_dataframe(self, series: OHLCVSeries) -> pd.DataFrame:
        return pd.DataFrame(
            {
                "open": [c.open for c in series.candles],
                "high": [c.high for c in series.candles],
                "low": [c.low for c in series.candles],
                "close": [c.close for c in series.candles],
                "volume": [c.volume for c in series.candles],
            },
            index=pd.DatetimeIndex([c.timestamp for c in series.candles]),
        )

    def analyze(self, series: OHLCVSeries) -> TechnicalSnapshot:
        tf = series.timeframe
        if len(series) < 2:
            return TechnicalSnapshot(
                timeframe=tf, bars=len(series), freshness=series.freshness,
                trend=TrendState(direction=TrendDirection.UNDETERMINED,
                                 reason="not enough candles"),
                notes=["UNAVAILABLE - not enough candles to compute indicators"],
            )

        df = self.to_dataframe(series)
        close, high, low, volume = df["close"], df["high"], df["low"], df["volume"]
        notes: list[str] = []

        # Fraction of the most recent bar that has elapsed. The last bar is
        # normally still forming, so its volume is a partial accumulation:
        # comparing it against completed bars understates it badly (a daily bar
        # read at 05:00 UTC holds a fifth of a day's volume).
        last_open = df.index[-1].to_pydatetime()
        if last_open.tzinfo is None:
            last_open = last_open.replace(tzinfo=UTC)
        elapsed_minutes = (datetime.now(UTC) - last_open).total_seconds() / 60.0
        completion = max(0.0, min(1.0, elapsed_minutes / tf.minutes)) if tf.minutes else 1.0
        bar_partial = completion < 0.95

        # --- trend ---------------------------------------------------------
        ema20 = ind.ema(close, 20)
        ema50 = ind.ema(close, 50)
        ema100 = ind.ema(close, 100)
        ema200 = ind.ema(close, 200)
        adx_series = ind.adx(high, low, close, 14)

        if len(close) < 200:
            notes.append(
                f"EMA200 needs 200 bars, {len(close)} available - long-term trend not computed"
            )

        trend = determine_trend(
            close, ema20, ema50, ema200, adx_series,
            ema_separation_min_pct=float(self.t_trend.get("ema_separation_min_pct", 0.35)),
            adx_trending=float(self.t_trend.get("adx_trending", 25)),
        )

        # --- momentum ------------------------------------------------------
        rsi_s = ind.rsi(close, 14)
        macd_line, macd_sig, macd_hist = ind.macd(close)
        stoch_k, _ = ind.stochastic(high, low, close)

        rsi_val = ind.last_valid(rsi_s)
        macd_val = ind.last_valid(macd_line)
        macd_sig_val = ind.last_valid(macd_sig)
        macd_hist_val = ind.last_valid(macd_hist)

        # --- volatility ----------------------------------------------------
        bb_up, bb_mid, bb_low = ind.bollinger_bands(close, 20, 2.0)
        bandwidth = ind.bollinger_bandwidth(close, 20, 2.0)
        atr_val = ind.last_valid(ind.atr(high, low, close, 14))
        atr_pct_val = ind.last_valid(ind.atr_percent(high, low, close, 14))
        periods_per_year = int(365 * 24 * 60 / tf.minutes)
        rvol = ind.last_valid(ind.realized_volatility(close, 20, periods_per_year))

        bb_u, bb_m, bb_l = ind.last_valid(bb_up), ind.last_valid(bb_mid), ind.last_valid(bb_low)
        clean_bandwidth = bandwidth.dropna()
        bandwidth_percentile = None
        bollinger_squeeze = None
        if len(clean_bandwidth) >= 60:
            current_bandwidth = float(clean_bandwidth.iloc[-1])
            bandwidth_percentile = float(
                (clean_bandwidth.iloc[:-1].to_numpy() < current_bandwidth).mean() * 100.0
            )
            bollinger_squeeze = bandwidth_percentile <= 10.0
        price = float(close.iloc[-1])
        bb_pos = None
        if bb_u is not None and bb_l is not None and bb_u > bb_l:
            bb_pos = (price - bb_l) / (bb_u - bb_l) * 100.0

        # --- volume --------------------------------------------------------
        vol_avg = ind.last_valid(ind.volume_sma(volume, 20))
        rel_vol = ind.last_valid(ind.relative_volume(volume, 20))
        vol_accel = ind.last_valid(ind.volume_acceleration(volume, 5, 20))
        obv_s = ind.obv(close, volume)
        obv_slope = None
        if len(obv_s) > 10:
            recent = obv_s.iloc[-10:]
            denom = abs(float(recent.mean())) or 1.0
            obv_slope = float((recent.iloc[-1] - recent.iloc[0]) / denom * 100.0)

        # --- structure and levels -----------------------------------------
        lookback = int(self.t_swings.get("lookback", 5))
        swing_highs, swing_lows = find_swings(high, low, lookback=lookback)
        structure, labels = classify_structure(
            swing_highs, swing_lows,
            min_swings=int(self.t_swings.get("min_swings_for_structure", 4)),
        )
        supports, resistances = build_levels(
            swing_highs, swing_lows, price,
            tolerance_pct=float(self.t_levels.get("cluster_tolerance_pct", 0.6)),
            min_touches=int(self.t_levels.get("min_touches", 2)),
            max_levels=int(self.t_levels.get("max_levels", 6)),
        )

        # --- divergences ---------------------------------------------------
        divergences: list[Divergence] = []
        divergences.extend(
            detect_divergences(
                high, low, close, rsi_s, tf, "RSI",
                lookback_bars=int(self.t_div.get("lookback_bars", 60)),
                swing_lookback=lookback,
                min_pivot_distance=int(self.t_div.get("min_pivot_distance", 5)),
                min_price_move_pct=float(self.t_div.get("min_price_move_pct", 1.0)),
            )
        )
        divergences.extend(
            detect_divergences(
                high, low, close, macd_hist, tf, "MACD",
                lookback_bars=int(self.t_div.get("lookback_bars", 60)),
                swing_lookback=lookback,
                min_pivot_distance=int(self.t_div.get("min_pivot_distance", 5)),
                min_price_move_pct=float(self.t_div.get("min_price_move_pct", 1.0)),
            )
        )

        # --- patterns ------------------------------------------------------
        ctx = PatternContext(
            high=high, low=low, close=close, volume=volume,
            swing_highs=swing_highs, swing_lows=swing_lows,
            timeframe=tf,
            # Pattern detectors need to know the bar is still forming so volume
            # comparisons stay meaningful.
            config={**self.t_patterns, "_bar_completion": completion},
        )
        min_conf = float(self.t_patterns.get("min_confidence", 55))
        patterns: list[PatternMatch] = []
        for detector in all_detectors():
            try:
                match = detector.detect(ctx)
            except Exception as exc:
                notes.append(f"pattern detector '{detector.name}' failed: {exc}")
                continue
            # Below the floor we say nothing rather than hedge.
            if match and match.confidence >= min_conf:
                patterns.append(match)
        patterns.sort(key=lambda p: p.confidence, reverse=True)

        # --- period changes -------------------------------------------------
        bars_24h = max(1, int(1440 / tf.minutes))
        bars_7d = max(1, int(10080 / tf.minutes))

        snap = TechnicalSnapshot(
            timeframe=tf,
            bars=len(df),
            last_bar_partial=bar_partial,
            last_bar_completion_pct=round(completion * 100.0, 1),
            price=price,
            freshness=series.freshness,
            trend=trend,
            ema20=ind.last_valid(ema20), ema50=ind.last_valid(ema50),
            ema100=ind.last_valid(ema100), ema200=ind.last_valid(ema200),
            sma50=ind.last_valid(ind.sma(close, 50)), sma200=ind.last_valid(ind.sma(close, 200)),
            rsi=rsi_val, macd=macd_val, macd_signal=macd_sig_val, macd_hist=macd_hist_val,
            stoch_k=ind.last_valid(stoch_k), adx=ind.last_valid(adx_series),
            bb_upper=bb_u, bb_middle=bb_m, bb_lower=bb_l,
            bb_bandwidth=ind.last_valid(bandwidth), bb_position=bb_pos,
            bb_bandwidth_percentile=bandwidth_percentile,
            bollinger_squeeze=bollinger_squeeze,
            bollinger_direction_contribution=0.0,
            bollinger_expected_movement=(
                "HIGH" if bollinger_squeeze is True
                else "NORMAL" if bollinger_squeeze is False
                else "UNKNOWN"
            ),
            atr=atr_val, atr_pct=atr_pct_val, realized_vol=rvol,
            volume=float(volume.iloc[-1]), volume_avg=vol_avg,
            relative_volume=rel_vol, volume_acceleration=vol_accel, obv_slope=obv_slope,
            change_1_bar_pct=ind.percent_change(close, 1),
            change_24h_pct=ind.percent_change(close, bars_24h),
            change_7d_pct=ind.percent_change(close, bars_7d),
            structure=structure, structure_labels=labels,
            swing_high_count=len(swing_highs), swing_low_count=len(swing_lows),
            levels_support=supports, levels_resistance=resistances,
            divergences=divergences, patterns=patterns,
            notes=notes,
        )

        e200 = snap.ema200
        if e200 and price:
            snap.price_vs_ema200_pct = (price - e200) / e200 * 100.0

        snap.rsi_state = self._rsi_state(rsi_val)
        snap.macd_state = self._macd_state(macd_val, macd_sig_val, macd_hist_val)
        snap.volatility_state = self._volatility_state(atr_pct_val)
        snap.volume_state = (
            "PARTIAL_BAR" if bar_partial else self._volume_state(rel_vol)
        )
        if bar_partial:
            snap.notes.append(
                f"Current {tf.value} bar is only {completion * 100:.0f}% elapsed - "
                "its volume is a partial accumulation and is not compared to completed bars"
            )
        return snap

    # --- labelling helpers ---------------------------------------------------

    def _rsi_state(self, rsi_val: float | None) -> str:
        if rsi_val is None:
            return "UNAVAILABLE"
        if rsi_val <= float(self.t_rsi.get("extreme_low", 20)):
            return "EXTREME_OVERSOLD"
        if rsi_val <= float(self.t_rsi.get("oversold", 30)):
            return "OVERSOLD"
        if rsi_val >= float(self.t_rsi.get("extreme_high", 80)):
            return "EXTREME_OVERBOUGHT"
        if rsi_val >= float(self.t_rsi.get("overbought", 70)):
            return "OVERBOUGHT"
        if rsi_val > 55:
            return "BULLISH"
        if rsi_val < 45:
            return "BEARISH"
        return "NEUTRAL"

    def _macd_state(self, m: float | None, s: float | None, h: float | None) -> str:
        if m is None or s is None or h is None:
            return "UNAVAILABLE"
        if m > s and h > 0:
            return "BULLISH_CROSS" if m > 0 else "BULLISH_RECOVERY"
        if m < s and h < 0:
            return "BEARISH_CROSS" if m < 0 else "BEARISH_WEAKENING"
        return "NEUTRAL"

    def _volatility_state(self, atr_pct: float | None) -> str:
        if atr_pct is None:
            return "UNAVAILABLE"
        if atr_pct < float(self.t_atr.get("low", 1.0)):
            return "LOW"
        if atr_pct > float(self.t_atr.get("high", 5.0)):
            return "HIGH"
        if atr_pct > float(self.t_atr.get("normal", 3.0)):
            return "ELEVATED"
        return "NORMAL"

    def _volume_state(self, rel: float | None) -> str:
        if rel is None:
            return "UNAVAILABLE"
        if rel >= float(self.t_vol.get("spike_ratio", 2.5)):
            return "SPIKE"
        if rel >= float(self.t_vol.get("high_ratio", 1.5)):
            return "HIGH"
        if rel <= float(self.t_vol.get("low_ratio", 0.6)):
            return "LOW"
        return "NORMAL"

    def technical_direction(self, snap: TechnicalSnapshot) -> Direction:
        """Coarse direction used by the multi-timeframe engine."""
        if not snap.has_data:
            return Direction.INCONCLUSIVE
        score = 0
        if snap.trend.direction is TrendDirection.UPTREND:
            score += 2
        elif snap.trend.direction is TrendDirection.DOWNTREND:
            score -= 2
        if snap.structure is MarketStructure.HH_HL:
            score += 2
        elif snap.structure is MarketStructure.LH_LL:
            score -= 2
        if snap.rsi is not None:
            if snap.rsi > 55:
                score += 1
            elif snap.rsi < 45:
                score -= 1
        if snap.macd_state.startswith("BULLISH"):
            score += 1
        elif snap.macd_state.startswith("BEARISH"):
            score -= 1

        if score >= 3:
            return Direction.BULLISH
        if score <= -3:
            return Direction.BEARISH
        return Direction.NEUTRAL
