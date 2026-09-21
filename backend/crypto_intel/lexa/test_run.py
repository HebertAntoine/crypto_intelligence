"""One test run: one video's transcript through the whole chain, then a stop.

    transcript -> extraction -> verification -> plan on 100 € -> reports

Each run is written to `data/lexa/tests/<run_id>/` (ignored by Git):

    transcript.txt    the cleaned, timestamped transcript
    extraction.json   the typed result (schema lexa-extraction/1)
    report.md         what Lexa says, crypto by crypto
    validation.md     the validation report, with the manual comparison to fill
    status.json       RUNNING / DONE / FAILED

Nothing is written to the Lexa database: the member validates first.
"""

from __future__ import annotations

import json
import os
import threading
import traceback
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from ..logging_setup import get_logger
from .extraction import DEFAULT_MODEL, extract
from .report import human_report, plan, validation_report
from .store import database_path
from .transcript import parse, render

log = get_logger(__name__)
MAX_TRANSCRIPT_CHARS = 400_000


def runs_dir() -> Path:
    path = database_path().parent / "tests"
    path.mkdir(parents=True, exist_ok=True)
    os.chmod(path, 0o700)
    return path


def _write(path: Path, name: str, content: str) -> None:
    target = path / name
    target.write_text(content, encoding="utf-8")
    os.chmod(target, 0o600)


def _status(path: Path, **fields: Any) -> None:
    current = {}
    if (path / "status.json").exists():
        current = json.loads((path / "status.json").read_text())
    current.update(fields)
    _write(path, "status.json", json.dumps(current, ensure_ascii=False, indent=2))


def _parse_date(value: str | None) -> datetime | None:
    if not value:
        return None
    moment = datetime.fromisoformat(value.replace("Z", "+00:00"))
    return moment if moment.tzinfo else moment.replace(tzinfo=UTC)


def execute(run_path: Path, raw: str, *, title: str, published_at: str | None,
            source: str, model: str = DEFAULT_MODEL, capital: float = 100.0,
            llm=None, prices=None) -> dict[str, Any]:
    segments = parse(raw)
    if not segments:
        raise ValueError("Transcription illisible : aucun passage horodaté trouvé.")
    _write(run_path, "transcript.txt", render(segments))
    kwargs = {"llm": llm} if llm is not None else {}
    result = extract(segments, title=title, published_at=published_at, source=source,
                     model=model, **kwargs)

    moment = _parse_date(published_at)
    if prices is None:
        from .prices import hourly_prices as prices
    tables = {}
    for asset in result.assets:
        frame = prices(asset.symbol, moment) if moment else None
        tables[asset.symbol] = plan(asset, capital=capital, frame=frame, published_at=moment)

    payload = {**result.model_dump(), "plans": tables}
    _write(run_path, "extraction.json", json.dumps(payload, ensure_ascii=False, indent=2))
    _write(run_path, "report.md", human_report(result, tables))
    _write(run_path, "validation.md", validation_report(result))
    return payload


def start(raw: str, *, title: str, published_at: str | None, source: str,
          model: str = DEFAULT_MODEL, capital: float = 100.0, background: bool = True) -> str:
    if len(raw) > MAX_TRANSCRIPT_CHARS:
        raise ValueError("Transcription trop longue pour un test (400 000 caractères maximum).")
    if not parse(raw):
        raise ValueError("Transcription illisible : aucun passage horodaté trouvé.")
    run_id = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    path = runs_dir() / run_id
    path.mkdir(mode=0o700)
    _status(path, run_id=run_id, state="RUNNING", title=title, published_at=published_at,
            source=source, model=model, started_at=datetime.now(UTC).isoformat())

    def job() -> None:
        try:
            execute(path, raw, title=title, published_at=published_at, source=source,
                    model=model, capital=capital)
            _status(path, state="DONE", finished_at=datetime.now(UTC).isoformat())
        except Exception as exc:
            log.warning("lexa_test_failed", run_id=run_id, error=str(exc))
            _status(path, state="FAILED", error=str(exc),
                    trace=traceback.format_exc(limit=3),
                    finished_at=datetime.now(UTC).isoformat())

    if background:
        threading.Thread(target=job, name=f"lexa-test-{run_id}", daemon=True).start()
    else:
        job()
    return run_id


def get(run_id: str) -> dict[str, Any] | None:
    if not run_id.replace("T", "").replace("Z", "").isdigit():
        return None
    path = runs_dir() / run_id
    if not (path / "status.json").exists():
        return None
    out: dict[str, Any] = {"status": json.loads((path / "status.json").read_text())}
    for name, key in (("transcript.txt", "transcript"), ("report.md", "report"),
                      ("validation.md", "validation")):
        if (path / name).exists():
            out[key] = (path / name).read_text(encoding="utf-8")
    if (path / "extraction.json").exists():
        out["extraction"] = json.loads((path / "extraction.json").read_text(encoding="utf-8"))
    return out


def list_runs() -> list[dict[str, Any]]:
    runs = []
    for path in sorted(runs_dir().iterdir(), reverse=True):
        if (path / "status.json").exists():
            runs.append(json.loads((path / "status.json").read_text()))
    return runs
