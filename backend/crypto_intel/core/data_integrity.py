"""Hard boundaries between production evidence and development examples."""

from __future__ import annotations

import re
from pathlib import Path

NON_PRODUCTION_MARKERS = frozenset({"example", "fixture", "mock", "sample", "test"})


def label_tokens(value: str | Path) -> set[str]:
    """Return semantic filename/source tokens without false matches such as ``latest``."""
    return {
        token
        for token in re.split(r"[^a-z0-9]+", str(value).lower())
        if token
    }


def is_production_label(value: str | Path | None) -> bool:
    """False for anything explicitly named as example, fixture, mock, sample or test."""
    if value is None or not str(value).strip():
        return False
    return not bool(label_tokens(value) & NON_PRODUCTION_MARKERS)


def is_production_etf_source(value: str | None) -> bool:
    """Whether an ETF row may contribute to a production aggregate."""
    return is_production_label(value)
