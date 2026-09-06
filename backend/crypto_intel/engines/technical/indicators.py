"""Technical indicators, implemented and tested directly on pandas/numpy.

Deliberately not TA-Lib: it needs a C build step that turns a clean install
into a support problem. Each function here is covered by a unit test against
hand-checked reference values, which is worth more than a binary dependency.

Every function returns a pandas Series aligned to the input index, with NaN in
the warm-up region. NaN means "not computable yet" and must never be filled
with a neutral value - a fabricated indicator reading is a fabricated fact.
"""

from __future__ import annotations

import numpy as np
import pandas as pd


def ema(series: pd.Series, period: int) -> pd.Series:
    """Exponential moving average (standard: adjust=False, recursive form)."""
    if period <= 0:
        raise ValueError("period must be positive")
    return series.ewm(span=period, adjust=False, min_periods=period).mean()


def sma(series: pd.Series, period: int) -> pd.Series:
    if period <= 0:
        raise ValueError("period must be positive")
    return series.rolling(window=period, min_periods=period).mean()


def wilder_smooth(values: pd.Series, period: int) -> pd.Series:
    """Wilder's smoothing, seeded with a simple mean of the first `period` values.

    This seeding matters: starting the recursion from the first observation
    (what `ewm(adjust=False)` does) biases the early output and never fully
    converges to the values every charting platform shows. Wilder's original
    formulation is:

        avg[period] = mean(values[1..period])
        avg[i]      = (avg[i-1] * (period - 1) + values[i]) / period
    """
    if period <= 0:
        raise ValueError("period must be positive")

    out = pd.Series(np.nan, index=values.index, dtype=float)
    valid = values.dropna()
    if len(valid) < period:
        return out

    arr = valid.to_numpy(dtype=float)
    positions = [values.index.get_loc(idx) for idx in valid.index]

    avg = float(arr[:period].mean())
    out.iloc[positions[period - 1]] = avg
    for i in range(period, len(arr)):
        avg = (avg * (period - 1) + arr[i]) / period
        out.iloc[positions[i]] = avg
    return out


def rsi(series: pd.Series, period: int = 14) -> pd.Series:
    """Relative Strength Index, Wilder's method.

    Verified against Wilder's own reference dataset (first value 70.46).
    """
    if period <= 0:
        raise ValueError("period must be positive")
    delta = series.diff()
    gain = delta.clip(lower=0.0)
    loss = -delta.clip(upper=0.0)

    avg_gain = wilder_smooth(gain, period)
    avg_loss = wilder_smooth(loss, period)

    rs = avg_gain / avg_loss.replace(0.0, np.nan)
    out = 100.0 - (100.0 / (1.0 + rs))
    # Zero average loss with gains present is RSI 100 by definition, not NaN.
    out = out.where(~((avg_loss == 0) & (avg_gain > 0)), 100.0)
    out = out.where(~((avg_gain == 0) & (avg_loss > 0)), 0.0)
    return out


def macd(
    series: pd.Series, fast: int = 12, slow: int = 26, signal: int = 9
) -> tuple[pd.Series, pd.Series, pd.Series]:
    """MACD line, signal line, histogram."""
    if fast >= slow:
        raise ValueError("fast period must be shorter than slow period")
    ema_fast = series.ewm(span=fast, adjust=False, min_periods=fast).mean()
    ema_slow = series.ewm(span=slow, adjust=False, min_periods=slow).mean()
    macd_line = ema_fast - ema_slow
    signal_line = macd_line.ewm(span=signal, adjust=False, min_periods=signal).mean()
    return macd_line, signal_line, macd_line - signal_line


def bollinger_bands(
    series: pd.Series, period: int = 20, std_dev: float = 2.0
) -> tuple[pd.Series, pd.Series, pd.Series]:
    """Upper, middle, lower bands. Population std (ddof=0), as charts use."""
    middle = sma(series, period)
    std = series.rolling(window=period, min_periods=period).std(ddof=0)
    return middle + std_dev * std, middle, middle - std_dev * std


def bollinger_bandwidth(series: pd.Series, period: int = 20, std_dev: float = 2.0) -> pd.Series:
    """Band width as % of the middle band - a squeeze/expansion measure."""
    upper, middle, lower = bollinger_bands(series, period, std_dev)
    return (upper - lower) / middle.replace(0.0, np.nan) * 100.0


def true_range(high: pd.Series, low: pd.Series, close: pd.Series) -> pd.Series:
    prev_close = close.shift(1)
    return pd.concat(
        [high - low, (high - prev_close).abs(), (low - prev_close).abs()], axis=1
    ).max(axis=1)


def atr(high: pd.Series, low: pd.Series, close: pd.Series, period: int = 14) -> pd.Series:
    """Average True Range, Wilder-smoothed (same seeding as RSI)."""
    tr = true_range(high, low, close)
    return wilder_smooth(tr, period)


def atr_percent(
    high: pd.Series, low: pd.Series, close: pd.Series, period: int = 14
) -> pd.Series:
    """ATR as % of price - comparable across assets, unlike raw ATR."""
    return atr(high, low, close, period) / close.replace(0.0, np.nan) * 100.0


def realized_volatility(close: pd.Series, period: int = 20, periods_per_year: int = 365) -> pd.Series:
    """Annualized volatility of log returns, in percent."""
    log_ret = np.log(close / close.shift(1))
    return log_ret.rolling(window=period, min_periods=period).std(ddof=0) * np.sqrt(
        periods_per_year
    ) * 100.0


def volume_sma(volume: pd.Series, period: int = 20) -> pd.Series:
    return sma(volume, period)


def relative_volume(volume: pd.Series, period: int = 20) -> pd.Series:
    """Current volume vs its average. 1.0 = normal, 2.0 = twice normal."""
    avg = volume_sma(volume, period)
    return volume / avg.replace(0.0, np.nan)


def volume_acceleration(volume: pd.Series, short: int = 5, long: int = 20) -> pd.Series:
    """Short-term vs long-term average volume. >1 means volume is building."""
    return sma(volume, short) / sma(volume, long).replace(0.0, np.nan)


def adx(high: pd.Series, low: pd.Series, close: pd.Series, period: int = 14) -> pd.Series:
    """Average Directional Index - trend strength regardless of direction.

    Used to separate a genuine trend from a drifting range, which matters when
    deciding whether EMA alignment means anything.
    """
    up_move = high.diff()
    down_move = -low.diff()

    plus_dm = pd.Series(
        np.where((up_move > down_move) & (up_move > 0), up_move, 0.0), index=high.index
    )
    minus_dm = pd.Series(
        np.where((down_move > up_move) & (down_move > 0), down_move, 0.0), index=high.index
    )

    tr = true_range(high, low, close)
    atr_s = wilder_smooth(tr, period)

    plus_di = 100.0 * wilder_smooth(plus_dm, period) / atr_s.replace(0.0, np.nan)
    minus_di = 100.0 * wilder_smooth(minus_dm, period) / atr_s.replace(0.0, np.nan)

    dx = ((plus_di - minus_di).abs() / (plus_di + minus_di).replace(0.0, np.nan)) * 100.0
    return wilder_smooth(dx, period)


def stochastic(
    high: pd.Series, low: pd.Series, close: pd.Series, k_period: int = 14, d_period: int = 3
) -> tuple[pd.Series, pd.Series]:
    lowest = low.rolling(window=k_period, min_periods=k_period).min()
    highest = high.rolling(window=k_period, min_periods=k_period).max()
    k = 100.0 * (close - lowest) / (highest - lowest).replace(0.0, np.nan)
    return k, k.rolling(window=d_period, min_periods=d_period).mean()


def obv(close: pd.Series, volume: pd.Series) -> pd.Series:
    """On-Balance Volume - cumulative volume signed by price direction."""
    direction = np.sign(close.diff()).fillna(0.0)
    return (direction * volume).cumsum()


def vwap(high: pd.Series, low: pd.Series, close: pd.Series, volume: pd.Series) -> pd.Series:
    """Rolling VWAP over the whole series (session-agnostic)."""
    typical = (high + low + close) / 3.0
    cum_vol = volume.cumsum().replace(0.0, np.nan)
    return (typical * volume).cumsum() / cum_vol


def percent_change(series: pd.Series, periods: int) -> float | None:
    """Percent change over N periods, or None if there is not enough history.

    Returns None rather than 0.0 on insufficient data: "no change" and "we
    cannot know" are different answers.
    """
    if len(series) <= periods:
        return None
    current = series.iloc[-1]
    past = series.iloc[-1 - periods]
    if pd.isna(current) or pd.isna(past) or past == 0:
        return None
    return float((current - past) / past * 100.0)


def last_valid(series: pd.Series) -> float | None:
    """Most recent non-NaN value, or None."""
    if series is None or series.empty:
        return None
    s = series.dropna()
    if s.empty:
        return None
    return float(s.iloc[-1])
