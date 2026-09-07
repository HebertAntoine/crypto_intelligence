"""Periodic snapshots - the system's own market memory.

Each snapshot kind has its own cadence, because the underlying data does:
prices move continuously, ETF flows publish once a day, macro moves on release
schedules. Capturing everything at the fastest cadence would bloat the database
and teach us nothing.

Idempotence comes from bucketing: a snapshot's identity is
(kind, asset, time bucket). Two runs inside the same bucket update one row
rather than creating a duplicate, which also makes restart-after-crash safe.
"""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select

from ..core.enums import Asset
from ..db.base import MarketSnapshotRow
from ..db.session import session_scope
from ..logging_setup import get_logger

log = get_logger("history.snapshots")

# kind -> bucket size in minutes. Snapshots inside the same bucket collapse.
CADENCES: dict[str, int] = {
    "market": 15,        # price, OHLCV summary, technical indicators
    "derivatives": 60,   # funding, open interest
    "onchain": 240,      # chain metrics move slowly
    "defi": 240,
    "etf": 1440,         # published once a day
    "macro": 720,
    "news": 60,
    "analysis": 60,      # scores, conviction, regime, timing, contradictions
    "decision": 30,      # the buy-opportunity verdict, for "last change"
}


def bucket_for(kind: str, when: datetime | None = None) -> str:
    """Deterministic bucket label for a timestamp and cadence."""
    when = when or datetime.now(UTC)
    minutes = CADENCES.get(kind, 60)
    epoch_minutes = int(when.timestamp() // 60)
    bucket_index = epoch_minutes // minutes
    return f"{kind}:{bucket_index}"


def _snapshot_id(kind: str, asset: Asset | None, bucket: str) -> str:
    raw = f"{kind}|{asset.value if asset else 'GLOBAL'}|{bucket}"
    return hashlib.sha1(raw.encode()).hexdigest()[:32]


def save_snapshot(
    kind: str,
    asset: Asset | None,
    payload: dict[str, Any],
    price: float | None = None,
    when: datetime | None = None,
) -> bool:
    """Store a snapshot. Returns True when a new row was created.

    Re-running inside the same bucket refreshes the row instead of inserting a
    duplicate - which is what makes the scheduler safe to restart.
    """
    when = when or datetime.now(UTC)
    bucket = bucket_for(kind, when)
    sid = _snapshot_id(kind, asset, bucket)

    with session_scope() as s:
        row = s.get(MarketSnapshotRow, sid)
        if row is not None:
            row.payload = payload
            row.price = price
            row.captured_at = when
            return False
        s.add(
            MarketSnapshotRow(
                id=sid, asset=asset.value if asset else None, kind=kind,
                captured_at=when, bucket=bucket, price=price, payload=payload,
            )
        )
        return True


def load_snapshots(
    kind: str,
    asset: Asset | None = None,
    since: datetime | None = None,
    limit: int = 500,
) -> list[dict[str, Any]]:
    with session_scope() as s:
        stmt = select(MarketSnapshotRow).where(MarketSnapshotRow.kind == kind)
        if asset is not None:
            stmt = stmt.where(MarketSnapshotRow.asset == asset.value)
        if since is not None:
            stmt = stmt.where(MarketSnapshotRow.captured_at >= since)
        stmt = stmt.order_by(MarketSnapshotRow.captured_at.desc()).limit(limit)
        rows = s.execute(stmt).scalars().all()

    return [
        {
            "id": r.id, "kind": r.kind, "asset": r.asset,
            "captured_at": r.captured_at if r.captured_at.tzinfo
            else r.captured_at.replace(tzinfo=UTC),
            "price": r.price, "payload": r.payload or {},
        }
        for r in rows
    ]


def snapshot_stats() -> dict[str, Any]:
    """What the memory currently holds - shown on the Sources page."""
    with session_scope() as s:
        rows = s.execute(
            select(MarketSnapshotRow.kind, MarketSnapshotRow.asset, MarketSnapshotRow.captured_at)
        ).all()

    stats: dict[str, dict[str, Any]] = {}
    for kind, asset, captured in rows:
        captured = captured if captured.tzinfo else captured.replace(tzinfo=UTC)
        entry = stats.setdefault(kind, {"count": 0, "assets": set(), "first": captured, "last": captured})
        entry["count"] += 1
        if asset:
            entry["assets"].add(asset)
        entry["first"] = min(entry["first"], captured)
        entry["last"] = max(entry["last"], captured)

    return {
        kind: {
            "count": e["count"],
            "assets": sorted(e["assets"]),
            "first": e["first"].isoformat(),
            "last": e["last"].isoformat(),
            "span_hours": round((e["last"] - e["first"]).total_seconds() / 3600.0, 1),
            "cadence_minutes": CADENCES.get(kind),
        }
        for kind, e in sorted(stats.items())
    }


def capture_analysis(analysis: Any) -> dict[str, bool]:
    """Persist one full analysis, split across its natural cadences.

    Splitting matters: the price part is worth keeping every 15 minutes, the
    ETF part only once a day. Storing the whole analysis at the fastest cadence
    would multiply near-identical ETF rows for no analytical gain.
    """
    asset = analysis.asset
    now = analysis.generated_at
    created: dict[str, bool] = {}

    daily_tech = (analysis.technical or {}).get("1d") or {}
    created["market"] = save_snapshot(
        "market", asset,
        {
            "price": analysis.price,
            "change_24h_pct": analysis.change_24h_pct,
            "change_7d_pct": analysis.change_7d_pct,
            "market_cap": analysis.market_cap,
            "volume_24h": analysis.volume_24h,
            "rsi_1d": daily_tech.get("rsi"),
            "ema20": daily_tech.get("ema20"),
            "ema50": daily_tech.get("ema50"),
            "ema200": daily_tech.get("ema200"),
            "atr_pct": daily_tech.get("atr_pct"),
            "trend": (daily_tech.get("trend") or {}).get("direction"),
            "structure": daily_tech.get("structure"),
            "volume_state": daily_tech.get("volume_state"),
        },
        price=analysis.price, when=now,
    )

    deriv = (analysis.domains or {}).get("derivatives") or {}
    if deriv.get("available"):
        created["derivatives"] = save_snapshot(
            "derivatives", asset,
            {
                "funding_rate": deriv.get("funding_rate"),
                "funding_state": deriv.get("funding_state"),
                "open_interest": deriv.get("open_interest"),
                "oi_change_24h_pct": deriv.get("oi_change_24h_pct"),
                "long_short_ratio": deriv.get("long_short_ratio"),
                "price_oi_regime": deriv.get("price_oi_regime"),
            },
            price=analysis.price, when=now,
        )

    etf = (analysis.domains or {}).get("etf") or {}
    if etf.get("available"):
        created["etf"] = save_snapshot(
            "etf", asset,
            {
                "latest_total": etf.get("latest_total"),
                "latest_date": etf.get("latest_date"),
                "ma_3d": etf.get("ma_3d"), "ma_5d": etf.get("ma_5d"), "ma_7d": etf.get("ma_7d"),
                "cumulative_30d": etf.get("cumulative_30d"),
                "streak_days": etf.get("streak_days"),
                "streak_direction": etf.get("streak_direction"),
                "flow_price_divergence": etf.get("flow_price_divergence"),
            },
            price=analysis.price, when=now,
        )

    onchain = (analysis.domains or {}).get("onchain") or {}
    if onchain.get("available"):
        created["onchain"] = save_snapshot(
            "onchain", asset,
            {"metrics": onchain.get("metrics"), "trends": onchain.get("trends")},
            price=analysis.price, when=now,
        )

    defi = (analysis.domains or {}).get("defi") or {}
    if defi.get("available"):
        created["defi"] = save_snapshot(
            "defi", asset,
            {
                "tvl": defi.get("tvl"),
                "tvl_change_7d_pct": defi.get("tvl_change_7d_pct"),
                "dex_volume_24h": defi.get("dex_volume_24h"),
                "fees_24h": defi.get("fees_24h"),
            },
            price=analysis.price, when=now,
        )

    # The analysis layer itself: scores, conviction, regime, timing.
    created["analysis"] = save_snapshot(
        "analysis", asset,
        {
            "scores": {
                d: {
                    "score": c.get("score"), "confidence": c.get("confidence"),
                    "available": c.get("available"), "freshness": c.get("freshness"),
                }
                for d, c in (analysis.scores or {}).items()
            },
            "conviction": {
                h: {
                    "score": (analysis.conviction.get(h) or {}).get("score"),
                    "label": (analysis.conviction.get(h) or {}).get("label"),
                    "confidence": (analysis.conviction.get(h) or {}).get("confidence"),
                }
                for h in ("short", "medium", "long")
            },
            "regime": {
                "regime": (analysis.regime or {}).get("regime"),
                "regime_score": (analysis.regime or {}).get("regime_score"),
                "conditions": (analysis.regime or {}).get("conditions"),
            },
            "entry_timing": {
                "timing": (analysis.entry_timing or {}).get("timing"),
                "timing_score": (analysis.entry_timing or {}).get("timing_score"),
            },
            "contradictions": {
                "max_strength": (analysis.contradictions or {}).get("max_strength"),
                "count": len((analysis.contradictions or {}).get("contradictions") or []),
            },
            "market_regime_text": analysis.market_regime,
            "scenarios": [
                {"name": s.get("name"), "probability": s.get("probability")}
                for s in (analysis.scenarios or [])
            ],
        },
        price=analysis.price, when=now,
    )

    return created


def capture_global(payload: dict[str, Any]) -> bool:
    """Snapshot the market-wide view (macro, liquidity, news)."""
    return save_snapshot("macro", None, payload)


def purge_old(kind: str, keep_days: int = 400) -> int:
    from datetime import timedelta

    from sqlalchemy import delete

    cutoff = datetime.now(UTC) - timedelta(days=keep_days)
    with session_scope() as s:
        result = s.execute(
            delete(MarketSnapshotRow).where(
                MarketSnapshotRow.kind == kind, MarketSnapshotRow.captured_at < cutoff
            )
        )
        return result.rowcount or 0
