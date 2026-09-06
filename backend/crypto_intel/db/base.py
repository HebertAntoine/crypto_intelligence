"""SQLAlchemy 2.0 ORM models.

Pure ORM, no SQLite-specific SQL in business logic: switching to PostgreSQL is
a DATABASE_URL change. The one SQLite-specific piece (the FTS5 knowledge index)
lives behind the KnowledgeStore interface, isolated from everything else.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    Float,
    Index,
    Integer,
    String,
    Text,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


def _utcnow() -> datetime:
    return datetime.now(UTC)


class Base(DeclarativeBase):
    pass


class ObservationRow(Base):
    """Persisted FACT. `id` is the deterministic hash, so re-collecting the same
    datapoint updates rather than duplicates."""

    __tablename__ = "observations"

    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    asset: Mapped[str | None] = mapped_column(String(16), index=True)
    metric: Mapped[str] = mapped_column(String(96), index=True)
    value_num: Mapped[float | None] = mapped_column(Float)
    value_text: Mapped[str | None] = mapped_column(Text)
    value_json: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    unit: Mapped[str] = mapped_column(String(24), default="")
    timeframe: Mapped[str | None] = mapped_column(String(8))
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    source: Mapped[str] = mapped_column(String(64))
    provider: Mapped[str] = mapped_column(String(64), index=True)
    source_url: Mapped[str | None] = mapped_column(String(512))
    freshness: Mapped[str] = mapped_column(String(16), default="UNAVAILABLE")
    confidence: Mapped[float] = mapped_column(Float, default=80.0)
    quality: Mapped[str] = mapped_column(String(16), default="MEASURED")
    meta: Mapped[dict[str, Any] | None] = mapped_column(JSON)

    __table_args__ = (
        Index("ix_obs_asset_metric_ts", "asset", "metric", "timestamp"),
        Index("ix_obs_metric_ts", "metric", "timestamp"),
    )


class ComputationRow(Base):
    __tablename__ = "computations"

    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    asset: Mapped[str | None] = mapped_column(String(16), index=True)
    name: Mapped[str] = mapped_column(String(96), index=True)
    value_num: Mapped[float | None] = mapped_column(Float)
    value_json: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    unit: Mapped[str] = mapped_column(String(24), default="")
    formula: Mapped[str] = mapped_column(Text, default="")
    engine: Mapped[str] = mapped_column(String(64), default="")
    timeframe: Mapped[str | None] = mapped_column(String(8))
    evidence_ids: Mapped[list[str] | None] = mapped_column(JSON)
    freshness: Mapped[str] = mapped_column(String(16), default="UNAVAILABLE")
    computed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)


class ReportRow(Base):
    """A frozen snapshot of everything known at time T.

    `payload` stores the full report so evaluation later compares what we
    actually said, not a reconstruction. That is what makes the accuracy
    statistics meaningful.
    """

    __tablename__ = "reports"

    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    asset: Mapped[str] = mapped_column(String(16), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, index=True)
    price_at_report: Mapped[float | None] = mapped_column(Float)
    conviction_short: Mapped[float | None] = mapped_column(Float)
    conviction_medium: Mapped[float | None] = mapped_column(Float)
    conviction_long: Mapped[float | None] = mapped_column(Float)
    confidence: Mapped[float | None] = mapped_column(Float)
    market_regime: Mapped[str | None] = mapped_column(String(32))
    scores: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    payload: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    text_report: Mapped[str | None] = mapped_column(Text)
    llm_used: Mapped[bool] = mapped_column(Boolean, default=False)


class ReportOutcomeRow(Base):
    """What actually happened after a report. Filled in later, never at
    creation time - that would be look-ahead."""

    __tablename__ = "report_outcomes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    report_id: Mapped[str] = mapped_column(String(40), index=True)
    asset: Mapped[str] = mapped_column(String(16), index=True)
    horizon: Mapped[str] = mapped_column(String(8))          # 1h, 4h, 24h, 3d, 7d, 30d
    price_then: Mapped[float | None] = mapped_column(Float)
    price_now: Mapped[float | None] = mapped_column(Float)
    return_pct: Mapped[float | None] = mapped_column(Float)
    predicted_direction: Mapped[str | None] = mapped_column(String(16))
    actual_direction: Mapped[str | None] = mapped_column(String(16))
    correct: Mapped[bool | None] = mapped_column(Boolean)
    evaluated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)

    __table_args__ = (Index("ix_outcome_report_horizon", "report_id", "horizon", unique=True),)


class KnowledgeDocumentRow(Base):
    __tablename__ = "knowledge_documents"

    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    path: Mapped[str] = mapped_column(String(512), unique=True)
    title: Mapped[str] = mapped_column(String(256))
    category: Mapped[str] = mapped_column(String(64), index=True)
    file_type: Mapped[str] = mapped_column(String(16))
    content_hash: Mapped[str] = mapped_column(String(64))
    pages: Mapped[int | None] = mapped_column(Integer)
    chunk_count: Mapped[int] = mapped_column(Integer, default=0)
    ingested_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)


class KnowledgeChunkRow(Base):
    """A passage from a personal document.

    Deliberately a different table from `observations`: a course is a source of
    KNOWLEDGE, never a source of real-time DATA. The schema enforces that.
    """

    __tablename__ = "knowledge_chunks"

    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    document_id: Mapped[str] = mapped_column(String(40), index=True)
    document_title: Mapped[str] = mapped_column(String(256))
    category: Mapped[str] = mapped_column(String(64), index=True)
    page: Mapped[int | None] = mapped_column(Integer)
    chunk_index: Mapped[int] = mapped_column(Integer)
    text: Mapped[str] = mapped_column(Text)
    char_count: Mapped[int] = mapped_column(Integer, default=0)


class AlertRow(Base):
    __tablename__ = "alerts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    kind: Mapped[str] = mapped_column(String(48), index=True)
    importance: Mapped[str] = mapped_column(String(16), index=True)
    asset: Mapped[str | None] = mapped_column(String(16), index=True)
    title: Mapped[str] = mapped_column(String(256))
    detail: Mapped[str] = mapped_column(Text, default="")
    triggered_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, index=True)
    evidence_ids: Mapped[list[str] | None] = mapped_column(JSON)
    acknowledged: Mapped[bool] = mapped_column(Boolean, default=False)
    # Stable identity of "the same alert", used for cooldown so a persistent
    # condition fires once rather than on every collection cycle.
    dedup_key: Mapped[str | None] = mapped_column(String(128), index=True)
    reason: Mapped[str] = mapped_column(Text, default="")

    __table_args__ = (Index("ix_alert_dedup_time", "dedup_key", "triggered_at"),)


class EventRow(Base):
    """Macro and regulatory calendar entries."""

    __tablename__ = "events"

    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    kind: Mapped[str] = mapped_column(String(32), index=True)     # FOMC, CPI, REGULATION...
    name: Mapped[str] = mapped_column(String(256))
    institution: Mapped[str | None] = mapped_column(String(64))
    legal_status: Mapped[str | None] = mapped_column(String(32))
    scheduled_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    importance: Mapped[str] = mapped_column(String(16), default="INFO")
    summary: Mapped[str] = mapped_column(Text, default="")
    source_url: Mapped[str | None] = mapped_column(String(512))
    source_name: Mapped[str | None] = mapped_column(String(96))
    assets: Mapped[list[str] | None] = mapped_column(JSON)
    meta: Mapped[dict[str, Any] | None] = mapped_column(JSON)


class ETFFlowRow(Base):
    """Daily ETF flow per fund, in millions of USD.

    `import_source` records how the row entered the system (csv / api name),
    because ETF data provenance is the most contested part of this project.
    """

    __tablename__ = "etf_flows"

    id: Mapped[str] = mapped_column(String(48), primary_key=True)
    asset: Mapped[str] = mapped_column(String(16), index=True)
    ticker: Mapped[str] = mapped_column(String(16), index=True)
    date: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    flow_musd: Mapped[float] = mapped_column(Float)
    import_source: Mapped[str] = mapped_column(String(64))
    source_url: Mapped[str | None] = mapped_column(String(512))
    imported_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)

    __table_args__ = (Index("ix_etf_asset_date", "asset", "date"),)


class MarketSnapshotRow(Base):
    """Periodic point-in-time snapshot - the system's own market memory.

    One row per (asset, kind, timestamp bucket). `kind` separates cadences:
    market data is captured often, ETF flows once a day, macro when it moves.
    Bucketing the timestamp is what makes re-running the scheduler idempotent:
    two runs inside the same bucket update one row rather than creating two.
    """

    __tablename__ = "market_snapshots"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    asset: Mapped[str | None] = mapped_column(String(16), index=True)
    kind: Mapped[str] = mapped_column(String(24), index=True)   # market|derivatives|etf|onchain|defi|macro|news|analysis
    captured_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    bucket: Mapped[str] = mapped_column(String(32), index=True)
    price: Mapped[float | None] = mapped_column(Float)
    payload: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)

    __table_args__ = (
        Index("ix_snapshot_asset_kind_time", "asset", "kind", "captured_at"),
        Index("ix_snapshot_bucket", "kind", "bucket", "asset", unique=True),
    )


class OHLCVRow(Base):
    """Persisted candles - the backbone of every historical study.

    Stored separately from `observations` because a candle is a compound record
    (5 values) and research queries need to scan years of them efficiently.
    """

    __tablename__ = "ohlcv"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    asset: Mapped[str] = mapped_column(String(16), index=True)
    timeframe: Mapped[str] = mapped_column(String(8), index=True)
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    open: Mapped[float] = mapped_column(Float)
    high: Mapped[float] = mapped_column(Float)
    low: Mapped[float] = mapped_column(Float)
    close: Mapped[float] = mapped_column(Float)
    volume: Mapped[float] = mapped_column(Float)
    source: Mapped[str] = mapped_column(String(48), default="")

    __table_args__ = (
        Index("ix_ohlcv_asset_tf_ts", "asset", "timeframe", "timestamp", unique=True),
    )


class MacroSeriesRow(Base):
    """Historical macro series with full temporal provenance.

    `timestamp` is the OBSERVATION time (the period the value describes).
    `release_time` is when it became public. Studies must filter on
    release_time, not timestamp - otherwise July's CPI appears usable on
    31 July, weeks before anyone had it.
    """

    __tablename__ = "macro_series"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    metric: Mapped[str] = mapped_column(String(64), index=True)
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    value: Mapped[float] = mapped_column(Float)
    source: Mapped[str] = mapped_column(String(48), default="")
    release_time: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    revision_time: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    availability: Mapped[str] = mapped_column(String(24), default="UNKNOWN")
    is_first_print: Mapped[bool] = mapped_column(Boolean, default=True)
    vintage_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    ingested_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)

    __table_args__ = (Index("ix_macro_metric_ts", "metric", "timestamp", unique=True),)


class MacroVintageRow(Base):
    """First-print and revised values from ALFRED.

    One row per (metric, observation, vintage): the value as it stood on a
    given date. This is what makes an exact as-of reconstruction possible,
    rather than an estimated publication lag.
    """

    __tablename__ = "macro_vintages"

    id: Mapped[str] = mapped_column(String(80), primary_key=True)
    metric: Mapped[str] = mapped_column(String(64), index=True)
    series_id: Mapped[str] = mapped_column(String(32), index=True)
    observation_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    vintage_date: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    value: Mapped[float] = mapped_column(Float)
    is_first_print: Mapped[bool] = mapped_column(Boolean, default=False)
    revision_number: Mapped[int] = mapped_column(Integer, default=0)
    ingested_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)

    __table_args__ = (
        Index("ix_vintage_lookup", "metric", "observation_time", "vintage_date", unique=True),
    )


class MacroReleaseRow(Base):
    """A scheduled macro release: actual, consensus, previous.

    Consensus is never invented. When no reliable free source exists it stays
    NULL and the surprise cannot be computed - which the engine reports rather
    than filling in.
    """

    __tablename__ = "macro_releases"

    id: Mapped[str] = mapped_column(String(80), primary_key=True)
    metric: Mapped[str] = mapped_column(String(64), index=True)
    event_name: Mapped[str] = mapped_column(String(96))
    observation_period: Mapped[str] = mapped_column(String(32))
    release_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    actual: Mapped[float | None] = mapped_column(Float)
    consensus: Mapped[float | None] = mapped_column(Float)
    previous: Mapped[float | None] = mapped_column(Float)
    revised_previous: Mapped[float | None] = mapped_column(Float)
    surprise: Mapped[float | None] = mapped_column(Float)
    surprise_zscore: Mapped[float | None] = mapped_column(Float)
    unit: Mapped[str] = mapped_column(String(16), default="")
    source: Mapped[str] = mapped_column(String(48), default="")
    ingested_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)

    __table_args__ = (Index("ix_release_metric_time", "metric", "release_time"),)


class DerivativesHistoryRow(Base):
    """Funding and open-interest history, needed for event studies."""

    __tablename__ = "derivatives_history"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    asset: Mapped[str] = mapped_column(String(16), index=True)
    metric: Mapped[str] = mapped_column(String(48), index=True)
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    value: Mapped[float] = mapped_column(Float)
    source: Mapped[str] = mapped_column(String(48), default="")

    __table_args__ = (
        Index("ix_deriv_asset_metric_ts", "asset", "metric", "timestamp", unique=True),
    )


class ResearchResultRow(Base):
    """Output of a quantitative study, stored so the UI and the report can read
    it without recomputing, and so results can be compared over time.

    `sample_size` and `split` are first-class: a result computed on 40 points
    in-sample must never be presented like one validated out-of-sample.
    """

    __tablename__ = "research_results"

    id: Mapped[str] = mapped_column(String(80), primary_key=True)
    study: Mapped[str] = mapped_column(String(48), index=True)   # etf_lag|event_study|calibration
    asset: Mapped[str | None] = mapped_column(String(16), index=True)
    signal: Mapped[str] = mapped_column(String(96), index=True)
    horizon: Mapped[str] = mapped_column(String(16), index=True)
    split: Mapped[str] = mapped_column(String(16), default="full")  # train|validation|oos|full
    sample_size: Mapped[int] = mapped_column(Integer, default=0)
    metrics: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    computed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    data_start: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    data_end: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    __table_args__ = (
        Index("ix_research_lookup", "study", "asset", "signal", "horizon", "split"),
    )


class BackfillStateRow(Base):
    """What has already been backfilled, so `make backfill` is idempotent and
    resumable after an interruption."""

    __tablename__ = "backfill_state"

    id: Mapped[str] = mapped_column(String(80), primary_key=True)
    dataset: Mapped[str] = mapped_column(String(48), index=True)
    asset: Mapped[str | None] = mapped_column(String(16))
    timeframe: Mapped[str | None] = mapped_column(String(8))
    earliest: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    latest: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    rows: Mapped[int] = mapped_column(Integer, default=0)
    source: Mapped[str] = mapped_column(String(48), default="")
    complete: Mapped[bool] = mapped_column(Boolean, default=False)
    note: Mapped[str] = mapped_column(Text, default="")
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)


class PredictionSnapshotRow(Base):
    """An immutable record of what the system predicted, and when.

    Written once and never updated. `content_hash` lets a later read prove the
    payload has not been edited - without that, revised inputs or a code change
    could silently rewrite history and make the accuracy statistics meaningless.
    """

    __tablename__ = "prediction_snapshots"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    asset: Mapped[str] = mapped_column(String(16), index=True)
    recorded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    bucket: Mapped[str] = mapped_column(String(16), index=True)
    price: Mapped[float | None] = mapped_column(Float)
    regime: Mapped[str | None] = mapped_column(String(32))
    entry_timing: Mapped[str | None] = mapped_column(String(32))
    conviction_medium: Mapped[float | None] = mapped_column(Float)
    payload: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    content_hash: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)

    __table_args__ = (Index("ix_prediction_asset_time", "asset", "recorded_at"),)


class PredictionOutcomeRow(Base):
    """What actually happened after a prediction snapshot.

    Stored separately from the snapshot: the prediction is a fact recorded at
    time T, the outcome is a fact recorded later. Keeping them in one row would
    invite updating the prediction alongside its result.
    """

    __tablename__ = "prediction_outcomes"

    id: Mapped[str] = mapped_column(String(80), primary_key=True)
    snapshot_id: Mapped[str] = mapped_column(String(64), index=True)
    asset: Mapped[str] = mapped_column(String(16), index=True)
    horizon: Mapped[str] = mapped_column(String(8), index=True)
    price_then: Mapped[float | None] = mapped_column(Float)
    price_now: Mapped[float | None] = mapped_column(Float)
    return_pct: Mapped[float | None] = mapped_column(Float)
    predicted_direction: Mapped[str | None] = mapped_column(String(16))
    actual_direction: Mapped[str | None] = mapped_column(String(16))
    correct: Mapped[bool | None] = mapped_column(Boolean)
    regime_at_prediction: Mapped[str | None] = mapped_column(String(32))
    timing_at_prediction: Mapped[str | None] = mapped_column(String(32))
    evaluated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)

    __table_args__ = (Index("ix_outcome_snapshot_horizon", "snapshot_id", "horizon"),)
