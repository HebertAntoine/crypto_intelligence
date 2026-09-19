"""Export a small static API snapshot for the Flutter web app.

The Vercel deployment is intentionally static. When no public backend is
configured, the Flutter client can still render the latest local analysis by
reading these JSON assets.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import urlopen

PROJECT_ROOT = Path(__file__).resolve().parents[1]
OUT_DIR = PROJECT_ROOT / "app" / "assets" / "api_snapshots"
#: Bumped when the shape of an exported snapshot changes.
PIPELINE_VERSION = "2026.09.18"
ASSETS = ("BTC", "ETH", "SOL")
TIMEFRAMES = ("15m", "1h", "4h", "1d", "1w")
DECISION_HORIZONS = ("24h", "7d", "30d")


def _chart_period(timeframe: str) -> str:
    """How much candle history each offline snapshot carries.

    Weekly ships everything: the whole series is 474 bars, and the figure scan
    finds shapes back to 2018 - a one-year snapshot showed none of them, and
    the offline chart looked like a market without figures.

    The finer timeframes stay bounded on purpose. Shipping nine years of 15m
    bars would add megabytes to the bundle to serve a mode that exists for
    when the backend is unreachable.
    """
    if timeframe == "1w":
        return "max"
    if timeframe == "1d":
        return "3m"
    return "7d"


def _snapshot_name(path: str, query: dict[str, str] | None = None) -> str:
    name = path.strip("/").replace("/", "__")
    if query:
        suffix = "__".join(f"{key}-{value}" for key, value in sorted(query.items()))
        name = f"{name}__{suffix}"
    return f"{name}.json"


def _endpoints() -> list[tuple[str, dict[str, str] | None]]:
    endpoints: list[tuple[str, dict[str, str] | None]] = [
        ("/health", None),
        ("/edge", None),
        ("/research/marginal-value", None),
        ("/research/structural", None),
        ("/research/replication", None),
        ("/knowledge/educational-claims", None),
        ("/research/claim-validation", None),
        ("/knowledge/dataset-quality", None),
        ("/sources/hierarchy", None),
        # LOT 6A: the studies the app now renders.
        ("/research/revalidation", None),
        ("/research/dvol", None),
        # LOT 6B. The evidence and power endpoints must be in the static
        # bundle: without them the deployed app renders a verdict with no
        # funnel and no detection floor, which is the one presentation of a
        # negative result that misleads.
        ("/evidence", None),
        ("/evidence/ladder", None),
        ("/power", None),
        ("/pooling", None),
        ("/hypotheses", None),
        ("/live-experiments", None),
        ("/redundancy", None),
        ("/market/ratios", None),
        ("/market/breadth", None),
        ("/market/liquidity", None),
        ("/evidence", None),
        ("/power", None),
        ("/pooling", None),
    ]
    for asset in ASSETS:
        endpoints.append((f"/market/price/{asset}", None))
        endpoints.append((f"/today/{asset}", None))
        for horizon in DECISION_HORIZONS:
            endpoints.append((f"/future/{asset}", {"horizon": horizon}))
        endpoints.append((f"/future/{asset}/timeline", {"days": "30"}))
        endpoints.append((f"/cycle/{asset}", None))
        endpoints.append((f"/derivatives/aggregate/{asset}", None))
        endpoints.append((f"/cross-asset/{asset}", None))
        endpoints.append((f"/multi-timeframe/{asset}", None))
        endpoints.append((f"/volatility/implied/{asset}", None))
        endpoints.append((f"/volatility/{asset}", None))
        endpoints.append((f"/leverage/{asset}", None))
        endpoints.append((f"/liquidations/{asset}", None))
        endpoints.append(("/daily-report-v2", {"asset": asset}))
        for timeframe in TIMEFRAMES:
            query = {"timeframe": timeframe}
            endpoints.append((f"/structure/{asset}", query))
            endpoints.append((f"/entry-opportunity/{asset}", query))
            endpoints.append((
                f"/chart/{asset}",
                {"period": _chart_period(timeframe), "timeframe": timeframe},
            ))
    return endpoints


def _fetch_json(base_url: str, path: str, query: dict[str, str] | None) -> object:
    url = f"{base_url.rstrip('/')}/api{path}"
    if query:
        url = f"{url}?{urlencode(query)}"
    try:
        with urlopen(url, timeout=60) as response:
            body = response.read().decode("utf-8")
    except HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"{url} returned HTTP {exc.code}: {detail[:500]}") from exc
    except URLError as exc:
        raise RuntimeError(f"{url} is unreachable: {exc}") from exc
    return json.loads(body)


def _in_process_fetcher():
    """Appeler l'API dans ce processus, sans passer par le réseau.

    Le planificateur et l'API partagent une boucle d'événements: pendant le
    travail d'analyse, qui interroge des flux distants, une requête HTTP peut
    attendre plusieurs minutes et l'export échouait par expiration. Ici
    l'export n'entre en concurrence avec rien, et il n'exige plus qu'un serveur
    tourne.
    """
    import sys

    sys.path.insert(0, str(PROJECT_ROOT / "backend"))
    from crypto_intel.api.routes_cycle import cycle_page
    from crypto_intel.api.routes_future import future_decision, future_timeline

    client = None

    def fetch(_base_url: str, path: str, query: dict[str, str] | None) -> dict:
        # These routes are pure synchronous composers over the same local
        # analysis context. Calling them directly avoids starting a server and
        # also avoids the TestClient/AnyIO incompatibility seen with recent
        # dependency combinations during static builds.
        if path.startswith("/cycle/"):
            return cycle_page(path.strip("/").split("/")[1])
        if path.startswith("/future/"):
            parts = path.strip("/").split("/")
            symbol = parts[1]
            if len(parts) == 3 and parts[2] == "timeline":
                return future_timeline(symbol, int((query or {}).get("days", "30")))
            return future_decision(symbol, (query or {}).get("horizon", "7d"))

        nonlocal client
        if client is None:
            from fastapi.testclient import TestClient

            from crypto_intel.main import app

            client = TestClient(app)
        response = client.get(f"/api{path}", params=query or {})
        if response.status_code != 200:
            raise RuntimeError(
                f"/api{path} returned HTTP {response.status_code}: "
                f"{response.text[:500]}"
            )
        return response.json()

    return fetch


def _new_run_id() -> str:
    """One identifier per cycle, readable in a log and sortable by time."""

    return datetime.now(UTC).strftime("run_%Y%m%dT%H%M%SZ")


def _validate_snapshot(path: Path, data: dict, run_id: str) -> list[str]:
    """Read back what was written and check it before it can be published.

    An exit code of zero from the export says the process finished, not that
    the files are usable. These checks are the difference between the two.
    """

    problems: list[str] = []
    if not isinstance(data, dict) or not data:
        return [f"{path.name}: payload vide ou non structuré"]

    if data.get("run_id") != run_id:
        problems.append(f"{path.name}: run_id {data.get('run_id')} ≠ {run_id}")

    if path.name.startswith("future__") and "horizon-" in path.name:
        symbol = path.name.split("__")[1]
        horizon = path.name.split("horizon-")[1].removesuffix(".json")
        if data.get("asset") != symbol:
            problems.append(f"{path.name}: asset {data.get('asset')} ≠ {symbol}")
        if data.get("horizon") != horizon:
            problems.append(
                f"{path.name}: horizon {data.get('horizon')} ≠ {horizon}"
            )
        if not data.get("decision"):
            problems.append(f"{path.name}: décision absente")

        families = (data.get("families") or {}).get("items") or {}
        if len(families) != 5:
            problems.append(f"{path.name}: {len(families)} familles au lieu de 5")

        for factor in (data.get("families") or {}).get("factors") or []:
            # A stale reading may be shown; it may not claim to be solid.
            if factor.get("availability") == "STALE" and (
                factor.get("confidence_band") == "HIGH"
            ):
                problems.append(
                    f"{path.name}: {factor.get('key')} périmé avec confiance élevée"
                )
            if factor.get("availability") in {"UNAVAILABLE", "NOT_APPLICABLE"} and (
                factor.get("direction") != "UNKNOWN"
            ):
                problems.append(
                    f"{path.name}: {factor.get('key')} indisponible mais directionnel"
                )

        now = datetime.now(UTC)
        for event in (data.get("synthesis") or {}).get("upcoming_events") or []:
            scheduled = event.get("scheduled_at")
            if not scheduled:
                continue
            when = datetime.fromisoformat(scheduled)
            if when < now:
                problems.append(
                    f"{path.name}: événement passé encore listé à surveiller "
                    f"({event.get('title', '')[:40]})"
                )
    return problems


#: A staging directory older than this was left by a run that died; a full
#: export takes minutes, so two hours cannot be a run still in progress.
STAGING_ABANDONED_AFTER = timedelta(hours=2)


def _export_atomically(
    fetch, base_url: str, endpoints, run_id: str
) -> list[str]:
    """Build every snapshot aside, validate the set, then swap it in.

    Writing straight into the served directory let the app read a half-updated
    set: BTC from this cycle beside ETH from the previous one. Everything is
    produced under a staging directory first, and the active set is only
    replaced once the whole cycle validates.
    """

    staging = OUT_DIR / ".staging" / run_id
    if staging.exists():
        shutil.rmtree(staging)
    staging.mkdir(parents=True, exist_ok=True)

    # A staging directory left by a run that was killed must never be promoted.
    # Only an old one is removed: a fresh one belongs to a run still writing -
    # deleting it made that run fail on a file whose directory had vanished.
    abandoned_after = time.time() - STAGING_ABANDONED_AFTER.total_seconds()
    for leftover in (OUT_DIR / ".staging").iterdir():
        if (
            leftover.is_dir()
            and leftover.name != run_id
            and leftover.stat().st_mtime < abandoned_after
        ):
            shutil.rmtree(leftover, ignore_errors=True)

    # Several endpoints can share a snapshot name. Keyed by target rather than
    # appended, so the promotion step moves each file exactly once - appending
    # made the second move fail on a file the first had already taken.
    produced: dict[Path, dict] = {}
    for path, query in endpoints:
        data = fetch(base_url, path, query)
        if isinstance(data, dict):
            data = {**data, "run_id": run_id}
        target = staging / _snapshot_name(path, query)
        target.write_text(
            json.dumps(data, ensure_ascii=True, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        produced[target] = data

    problems: list[str] = []
    for target in produced:
        try:
            reread = json.loads(target.read_text(encoding="utf-8"))
        except json.JSONDecodeError as error:
            problems.append(f"{target.name}: JSON invalide ({error})")
            continue
        problems.extend(_validate_snapshot(target, reread, run_id))

    if problems:
        shutil.rmtree(staging, ignore_errors=True)
        raise SystemExit(
            "export refusé, le jeu précédent reste actif:\n  "
            + "\n  ".join(problems[:20])
        )

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    written: list[str] = []
    for target in produced:
        final = OUT_DIR / target.name
        # Same filesystem, so the rename is atomic: a reader sees either the
        # previous file or the new one, never a partial write.
        os.replace(target, final)
        written.append(str(final.relative_to(PROJECT_ROOT)))

    _write_manifest(run_id, written)
    shutil.rmtree(staging, ignore_errors=True)
    return written


def _write_manifest(run_id: str, written: list[str]) -> None:
    """One file the app and a health check can read to judge the whole set."""

    per_asset: dict[str, dict] = {}
    oldest: str | None = None
    for name in written:
        path = PROJECT_ROOT / name
        if "horizon-7d" not in path.name or not path.name.startswith("future__"):
            continue
        data = json.loads(path.read_text(encoding="utf-8"))
        families = (data.get("families") or {}).get("items") or {}
        available = sum(1 for item in families.values() if item.get("available"))
        per_asset[data.get("asset", path.name)] = {
            "generated_at": data.get("as_of"),
            "verdict": data.get("decision"),
            "families_available": f"{available}/5",
            "data_status": (data.get("synthesis") or {}).get("data_status"),
            "missing_families": (data.get("synthesis") or {}).get(
                "missing_families", []
            ),
        }
        if data.get("as_of") and (oldest is None or data["as_of"] < oldest):
            oldest = data["as_of"]

    degraded = [
        asset
        for asset, item in per_asset.items()
        if item.get("data_status") == "PARTIAL_DATA"
    ]
    manifest = {
        "run_id": run_id,
        "generated_at": datetime.now(UTC).isoformat(),
        "pipeline_version": PIPELINE_VERSION,
        "snapshot_count": len(written),
        "oldest_snapshot_at": oldest,
        "assets": per_asset,
        "status": "DEGRADED" if degraded else "HEALTHY",
        "degraded_assets": degraded,
    }
    (OUT_DIR / "snapshot_manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=True, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://127.0.0.1:8100")
    parser.add_argument(
        "--only-today",
        action="store_true",
        help="Refresh only the three first-page payloads.",
    )
    parser.add_argument(
        "--only-future",
        action="store_true",
        help="Refresh only decision and timeline payloads for the asset tabs.",
    )
    parser.add_argument(
        "--in-process",
        action="store_true",
        help="Build the payloads in this process instead of over HTTP.",
    )
    parser.add_argument(
        "--run-id",
        default="",
        help="Identifier stamped on every snapshot of this cycle.",
    )
    args = parser.parse_args()

    fetch = _in_process_fetcher() if args.in_process else _fetch_json

    endpoints = _endpoints()
    if args.only_today:
        endpoints = [item for item in endpoints if item[0].startswith("/today/")]
    elif args.only_future:
        endpoints = [item for item in endpoints if item[0].startswith("/future/")]

    run_id = args.run_id or _new_run_id()
    written = _export_atomically(fetch, args.base_url, endpoints, run_id)

    print(f"Wrote {len(written)} static API snapshots (run {run_id}):")
    for filename in written:
        print(f"  {filename}")


if __name__ == "__main__":
    main()
