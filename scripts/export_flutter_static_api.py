"""Export a small static API snapshot for the Flutter web app.

The Vercel deployment is intentionally static. When no public backend is
configured, the Flutter client can still render the latest local analysis by
reading these JSON assets.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import urlopen

PROJECT_ROOT = Path(__file__).resolve().parents[1]
OUT_DIR = PROJECT_ROOT / "app" / "assets" / "api_snapshots"
ASSETS = ("BTC", "ETH", "SOL")
TIMEFRAMES = ("15m", "1h", "4h", "1d", "1w")


def _chart_period(timeframe: str) -> str:
    if timeframe == "1d":
        return "3m"
    if timeframe == "1w":
        return "1y"
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


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://127.0.0.1:8100")
    args = parser.parse_args()

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    written: list[str] = []

    for path, query in _endpoints():
        data = _fetch_json(args.base_url, path, query)
        target = OUT_DIR / _snapshot_name(path, query)
        target.write_text(
            json.dumps(data, ensure_ascii=True, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        written.append(str(target.relative_to(PROJECT_ROOT)))

    print(f"Wrote {len(written)} static API snapshots:")
    for filename in written:
        print(f"  {filename}")


if __name__ == "__main__":
    main()
