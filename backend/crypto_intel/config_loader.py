"""YAML configuration loading, with ${ENV_VAR} interpolation.

Weights and thresholds live in config/*.yaml precisely so they can be tuned
without touching code.
"""

from __future__ import annotations

import os
import re
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

from .core.errors import ConfigurationError
from .settings import get_settings

_ENV_PATTERN = re.compile(r"\$\{([A-Z_][A-Z0-9_]*)\}")


def _interpolate(value: Any) -> Any:
    """Replace ${VAR} with the environment value, recursively."""
    if isinstance(value, str):
        def repl(m: re.Match[str]) -> str:
            return os.environ.get(m.group(1), m.group(0))
        return _ENV_PATTERN.sub(repl, value)
    if isinstance(value, dict):
        return {k: _interpolate(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_interpolate(v) for v in value]
    return value


def load_yaml(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise ConfigurationError(f"Configuration file missing: {path}")
    try:
        with path.open(encoding="utf-8") as fh:
            data = yaml.safe_load(fh) or {}
    except yaml.YAMLError as exc:
        raise ConfigurationError(f"Invalid YAML in {path}: {exc}") from exc
    if not isinstance(data, dict):
        raise ConfigurationError(f"Expected a mapping at the top level of {path}")
    return _interpolate(data)


@lru_cache
def _load(name: str) -> dict[str, Any]:
    return load_yaml(get_settings().config_dir / name)


def assets_config() -> dict[str, Any]:
    return _load("assets.yaml")


def scoring_config() -> dict[str, Any]:
    return _load("scoring.yaml")


def thresholds_config() -> dict[str, Any]:
    return _load("thresholds.yaml")


def providers_config() -> dict[str, Any]:
    return _load("providers.yaml")


def macro_calendar_config() -> dict[str, Any]:
    """Deprecated compatibility loader; production events use FutureEvent."""
    return _load("macro_calendar.yaml")


def asset_meta(symbol: str) -> dict[str, Any]:
    cfg = assets_config().get("assets", {})
    if symbol not in cfg:
        raise ConfigurationError(f"Asset {symbol} not defined in config/assets.yaml")
    return cfg[symbol]


def asset_weights(symbol: str) -> dict[str, float]:
    """Per-asset domain weights. They deliberately differ between assets."""
    weights = scoring_config().get("assets", {}).get(symbol)
    if not weights:
        raise ConfigurationError(f"No scoring weights for {symbol} in config/scoring.yaml")
    return {k: float(v) for k, v in weights.items()}


def horizon_weights(horizon: str) -> dict[str, float]:
    hz = scoring_config().get("horizons", {}).get(horizon, {})
    return {k: float(v) for k, v in hz.items()}


def threshold(*path: str, default: Any = None) -> Any:
    """Read a nested threshold: threshold('technical', 'rsi', 'oversold')."""
    node: Any = thresholds_config()
    for key in path:
        if not isinstance(node, dict) or key not in node:
            return default
        node = node[key]
    return node


def clear_config_cache() -> None:
    _load.cache_clear()
