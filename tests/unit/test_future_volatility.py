from __future__ import annotations

import numpy as np
import pandas as pd

from crypto_intel.engines.volatility import ExpectedVolatilityEngine


def test_bollinger_squeeze_raises_amplitude_and_contributes_zero_direction():
    # Broad oscillation followed by an almost flat 30-bar compression.
    broad = 100 + np.sin(np.arange(100) / 2) * 8
    compressed = np.full(20, 100.0)
    closes = pd.Series(np.concatenate([broad, compressed]))

    result = ExpectedVolatilityEngine().assess_bollinger(closes)

    assert result.available is True
    assert result.squeeze is True
    assert result.expected_movement.value == "HIGH"
    assert result.directional_bias.value == "NEUTRAL"
    assert result.direction_contribution == 0.0
    assert "no information about the direction" in result.explanation


def test_insufficient_bandwidth_history_is_not_normal_by_default():
    result = ExpectedVolatilityEngine().assess_bollinger(pd.Series([100.0] * 30))

    assert result.available is False
    assert result.squeeze is None
    assert result.directional_bias.value == "NEUTRAL"
    assert result.direction_contribution == 0.0


def test_non_squeeze_still_never_contributes_direction():
    rng = np.random.default_rng(42)
    calm_then_volatile = np.concatenate(
        [100 + rng.normal(0, 0.1, 100), 100 + rng.normal(0, 5.0, 40)]
    )
    result = ExpectedVolatilityEngine().assess_bollinger(pd.Series(calm_then_volatile))

    assert result.available is True
    assert result.squeeze is False
    assert result.direction_contribution == 0.0
    assert result.directional_bias.value == "NEUTRAL"
