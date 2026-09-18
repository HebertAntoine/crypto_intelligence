"""Where a source's history lives between two processes.

The light pass and the full pass are separate programs launched by separate
timers, so nothing survives in memory between them. Due-ness, failure counts
and breaker state are therefore written to a small JSON file: without it every
run would believe each source had never been called, and the breaker would
never fire.
"""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path

from .source_policy import SourceState

PROJECT_ROOT = Path(__file__).resolve().parents[3]
STATE_PATH = PROJECT_ROOT / "data" / "source_state.json"


def load(path: Path | None = None) -> dict[str, SourceState]:
    target = path or STATE_PATH
    if not target.exists():
        return {}
    try:
        raw = json.loads(target.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        # A corrupt state file must not stop a refresh. Losing the history
        # costs one extra collection; refusing to run costs a whole cycle.
        return {}
    return {
        key: SourceState.from_dict({**value, "source_id": key})
        for key, value in raw.items()
        if isinstance(value, dict)
    }


def save(states: dict[str, SourceState], path: Path | None = None) -> Path:
    target = path or STATE_PATH
    target.parent.mkdir(parents=True, exist_ok=True)
    payload = {key: value.to_dict() for key, value in states.items()}
    # Written aside and renamed: a run killed mid-write must not leave a
    # half-file that the next run would discard as corrupt.
    with tempfile.NamedTemporaryFile(
        "w", dir=target.parent, delete=False, encoding="utf-8"
    ) as handle:
        json.dump(payload, handle, ensure_ascii=True, indent=2, sort_keys=True)
        handle.write("\n")
        temporary = Path(handle.name)
    os.replace(temporary, target)
    return target
