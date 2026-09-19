"""The monthly archive of the cycle reading: what the app said, when it said it.

The price moves all the time, the regime moves slowly, and the written record
of the analysis moves once a month. A snapshot is written for a month that has
none, and an extra one when the phase itself changes - never as a rewrite of
an existing row. Reading September's snapshot in December must show what was
actually said in September, so no snapshot is ever recomputed with later data.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select

from ..core.enums import Asset, Timeframe
from ..db.base import CycleSnapshotRow
from ..db.session import session_scope
from ..logging_setup import get_logger
from .cycle_regime import PHASE_EMOJI, PHASE_FR, BitcoinCycleRegimeEngine, CycleRegime, Phase

log = get_logger(__name__)

TREND_FR = {"HIGHER": "ascendante", "LOWER": "descendante", "MIXED": "mixte", "UNCLEAR": "indécise"}
MOMENTUM_FR = {
    "ACCELERATING": "accélère", "SLOWING": "ralentit",
    "REVERSING": "se retourne", "STEADY": "stable",
}


def month_key(when: datetime) -> str:
    return f"{when:%Y-%m}"


def _row_id(asset: str, month: str) -> str:
    return f"{asset}:{month}"


def summary_text(regime: CycleRegime) -> str:
    dims = regime.dimensions
    return (
        f"{PHASE_FR[regime.phase]}. Le marché est à {abs(dims.drawdown_pct):.0f} % de son record, "
        f"sa structure long terme est {TREND_FR.get(dims.structure, 'indécise')} et son momentum "
        f"{MOMENTUM_FR.get(dims.momentum, 'stable')}."
    )


def changes_since(previous: CycleSnapshotRow | None, regime: CycleRegime) -> list[str]:
    """What moved since the last archived reading - measured, not narrated."""

    if previous is None:
        return ["🆕 Première lecture archivée du cycle."]
    dims = regime.dimensions
    out: list[str] = []
    if dims.price > previous.btc_price * 1.02:
        out.append("📈 Prix en progression")
    elif dims.price < previous.btc_price * 0.98:
        out.append("📉 Prix en recul")
    if dims.drawdown_pct > previous.drawdown_from_ath + 1:
        out.append("🏆 Écart au record réduit")
    elif dims.drawdown_pct < previous.drawdown_from_ath - 1:
        out.append("🔻 Écart au record creusé")
    if dims.structure != previous.market_structure:
        out.append(f"🧱 Structure {TREND_FR.get(dims.structure, dims.structure).lower()}")
    if regime.phase.value != previous.phase:
        out.append(
            f"🔄 Phase : {PHASE_FR.get(Phase(previous.phase), previous.phase)} → {regime.label}"
        )
    return out or ["➡️ Aucun changement notable"]


def latest_snapshot(asset: str = "BTC") -> CycleSnapshotRow | None:
    with session_scope() as session:
        row = session.execute(
            select(CycleSnapshotRow)
            .where(CycleSnapshotRow.asset == asset)
            .order_by(CycleSnapshotRow.taken_at.desc())
        ).scalars().first()
        if row is not None:
            session.expunge(row)
        return row


def list_snapshots(asset: str = "BTC", limit: int = 24) -> list[dict[str, Any]]:
    with session_scope() as session:
        rows = session.execute(
            select(CycleSnapshotRow)
            .where(CycleSnapshotRow.asset == asset)
            .order_by(CycleSnapshotRow.taken_at.desc())
            .limit(limit)
        ).scalars().all()
        return [snapshot_dict(row) for row in rows]


def snapshot_dict(row: CycleSnapshotRow) -> dict[str, Any]:
    phase = Phase(row.phase) if row.phase in {p.value for p in Phase} else Phase.UNDETERMINED
    return {
        "month": row.month,
        "month_label": _month_label(row.month),
        "taken_at": row.taken_at.isoformat(),
        "data_cutoff": row.data_cutoff.isoformat(),
        "phase": row.phase,
        "phase_label": PHASE_FR[phase],
        "phase_emoji": PHASE_EMOJI[phase],
        "previous_phase": row.previous_phase or None,
        "candidate_phase": row.candidate_phase or None,
        "confidence": row.phase_confidence,
        "direction": row.direction,
        "btc_price": row.btc_price,
        "ath": row.ath,
        "drawdown_from_ath": row.drawdown_from_ath,
        "days_since_ath": row.days_since_ath,
        "days_since_halving": row.days_since_halving,
        "long_term_trend": row.long_term_trend,
        "market_structure": row.market_structure,
        "momentum_regime": row.momentum_regime,
        "relative_strength": row.relative_strength,
        "notes": row.notes,
        "changes": row.changes or [],
        "evidence": row.evidence or [],
        "engine_version": row.engine_version,
    }


_MONTHS_FR = ["janvier", "février", "mars", "avril", "mai", "juin", "juillet",
              "août", "septembre", "octobre", "novembre", "décembre"]


def _month_label(month: str) -> str:
    try:
        year, number = month.split("-")[:2]
        return f"{_MONTHS_FR[int(number) - 1].capitalize()} {year}"
    except (ValueError, IndexError):
        return month


def write_snapshot(regime: CycleRegime, *, asset: str = "BTC",
                   relative_strength: dict[str, Any] | None = None,
                   now: datetime | None = None, force: bool = False) -> dict[str, Any] | None:
    """Archive this month's reading, or an extra one when the phase changed.

    Returns the stored snapshot, or None when this month already has one and
    nothing changed. Existing rows are never modified.
    """

    now = now or datetime.now(UTC)
    previous = latest_snapshot(asset)
    month = month_key(now)
    phase_changed = previous is not None and previous.phase != regime.phase.value
    key = month if not (phase_changed and previous.month == month) else f"{month}/changement-de-phase"
    with session_scope() as session:
        existing = session.get(CycleSnapshotRow, _row_id(asset, key))
        if existing is not None and not force:
            return None
        if existing is not None:
            # force only ever adds a distinct row; a written month stays as it was.
            key = f"{month}/{now:%d%H%M}"
        dims = regime.dimensions
        row = CycleSnapshotRow(
            id=_row_id(asset, key),
            asset=asset,
            month=key,
            taken_at=now,
            data_cutoff=regime.data_cutoff,
            phase=regime.phase.value,
            previous_phase=regime.previous_phase.value if regime.previous_phase else "",
            candidate_phase=regime.candidate_phase.value if regime.candidate_phase else "",
            phase_confidence=regime.confidence,
            direction=regime.direction,
            btc_price=dims.price,
            ath=dims.ath,
            drawdown_from_ath=dims.drawdown_pct,
            days_since_ath=dims.days_since_ath,
            days_since_halving=dims.days_since_halving,
            long_term_trend=(
                "HAUSSIÈRE" if dims.sma200_slope_pct and dims.sma200_slope_pct > 0
                else "BAISSIÈRE" if dims.sma200_slope_pct is not None else "INDÉTERMINÉE"
            ),
            market_structure=dims.structure,
            momentum_regime=dims.momentum,
            relative_strength=relative_strength,
            notes=summary_text(regime),
            changes=changes_since(previous, regime),
            evidence=regime.evidence,
            engine_version=BitcoinCycleRegimeEngine.version,
        )
        session.add(row)
        session.flush()
        return snapshot_dict(row)


def ensure_snapshot(daily, halvings: list[datetime], *, asset: str = "BTC",
                    now: datetime | None = None) -> dict[str, Any] | None:
    """Read the regime and archive it if this month has nothing yet."""

    regime = BitcoinCycleRegimeEngine().read(daily, halvings)
    if regime is None:
        return None
    return write_snapshot(regime, asset=asset, now=now)


def backfill_snapshots(daily, halvings: list[datetime], *, asset: str = "BTC",
                       months: int = 18) -> list[dict[str, Any]]:
    """Write the months already past, each from the data known at its end.

    Used once, to give the history a starting point. Every month is computed
    on the bars that existed at its close, so nothing is written with later
    knowledge; a month that already has a snapshot is left untouched.
    """

    import pandas as pd

    from .cycle_regime import BitcoinCycleRegimeEngine as Engine

    if daily is None or daily.empty:
        return []
    written: list[dict[str, Any]] = []
    ends = pd.date_range(end=daily.index[-1], periods=months, freq="ME")
    engine = Engine()
    for stamp in ends:
        window = daily.loc[:stamp]
        if len(window) < 300:
            continue
        cutoff = pd.Timestamp(stamp).to_pydatetime()
        if cutoff.tzinfo is None:
            cutoff = cutoff.replace(tzinfo=UTC)
        regime = engine.read(window, [h for h in halvings if h <= cutoff], as_of=cutoff)
        if regime is None:
            continue
        stored = write_snapshot(regime, asset=asset, now=cutoff)
        if stored:
            written.append(stored)
    return written


def load_daily_and_halvings(asset: str = "BTC"):
    """Daily bars and halving timestamps, as the engines read them."""

    from .pit_view import DataCache, PointInTimeView

    view = PointInTimeView(DataCache(), datetime.now(UTC))
    halvings = [
        datetime.fromtimestamp(point.value, UTC)
        for point in view.points("btc.halving.block_epoch")
    ]
    return view.candles(asset, Timeframe.D1), halvings, view


__all__ = [
    "Asset",
    "backfill_snapshots",
    "ensure_snapshot",
    "list_snapshots",
    "load_daily_and_halvings",
    "month_key",
    "write_snapshot",
]
