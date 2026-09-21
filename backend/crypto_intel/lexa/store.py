"""Lexa's own database, kept apart from everything the app publishes.

The main database feeds JSON snapshots that are committed to a public
repository. Lexa analyses come from a paid, personal subscription whose terms
forbid redistribution, so they live in a separate SQLite file under
``data/lexa/`` - ignored by Git, never read by the export script.

Each analysis is immutable once written: a new video creates a new scenario,
it never overwrites an old one. The only thing that changes afterwards is a
correction, which keeps the original value beside the corrected one.

Four kinds of information, never mixed in one column:

    EXPLICIT / INFERRED   what the video says     levels, conditions, quotes
    USER_PLAN             what WE decided          budget, amounts (lexa_actions)
    fills                 what we actually did     lexa_fills, entered by hand
    MARKET_VALIDATION     computed live            never stored as a Lexa fact
"""

from __future__ import annotations

import os
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from functools import lru_cache
from pathlib import Path

from sqlalchemy import (
    JSON,
    DateTime,
    Engine,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    create_engine,
    event,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column, sessionmaker


def _now() -> datetime:
    return datetime.now(UTC)


class LexaBase(DeclarativeBase):
    pass


class LexaVideoRow(LexaBase):
    """One video of the subscription, as the member saw it."""

    __tablename__ = "lexa_videos"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    title: Mapped[str] = mapped_column(String(300))
    published_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    duration_s: Mapped[int | None] = mapped_column(Integer, nullable=True)
    #: Where the video lives on the platform - a reference, never the file.
    source_ref: Mapped[str] = mapped_column(String(500), default="")
    #: MANUAL_NOTES | TRANSCRIPT (only with the publisher's permission)
    source_kind: Mapped[str] = mapped_column(String(32), default="MANUAL_NOTES")
    #: Link to the video on the platform (never the file itself).
    video_url: Mapped[str] = mapped_column(String(500), default="")
    status: Mapped[str] = mapped_column(String(32), default="ANALYSED")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class LexaAnalysisRow(LexaBase):
    """One asset's scenario in one video. Written once, never rewritten."""

    __tablename__ = "lexa_analyses"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    video_id: Mapped[int] = mapped_column(ForeignKey("lexa_videos.id"), index=True)
    asset: Mapped[str] = mapped_column(String(16), index=True)
    published_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    processed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    #: Price the member noted at the time of the video, in the quote currency.
    price_at_video: Mapped[float | None] = mapped_column(Float, nullable=True)
    quote: Mapped[str] = mapped_column(String(8), default="USD")
    stance: Mapped[str] = mapped_column(String(32), default="UNSPECIFIED")
    summary: Mapped[str] = mapped_column(Text, default="")
    #: Lexa's own words on the market context, when noted.
    market_context: Mapped[str] = mapped_column(Text, default="")
    #: MANUAL_NOTES | TRANSCRIPT_TEST (imported after the member's validation)
    source_type: Mapped[str] = mapped_column(String(32), default="MANUAL_NOTES")
    #: Where this asset is discussed in the video, in seconds.
    timestamp_start_s: Mapped[int | None] = mapped_column(Integer, nullable=True)
    timestamp_end_s: Mapped[int | None] = mapped_column(Integer, nullable=True)
    #: When to look again, and when the scenario stops being current.
    review_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    #: Set by the member only: INVALIDATED | COMPLETED. Everything else is computed.
    status_override: Mapped[str | None] = mapped_column(String(16), nullable=True)
    status_reason: Mapped[str] = mapped_column(Text, default="")
    status_changed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class LexaLevelRow(LexaBase):
    """A level announced in the video, with where it came from."""

    __tablename__ = "lexa_levels"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    analysis_id: Mapped[int] = mapped_column(ForeignKey("lexa_analyses.id"), index=True)
    kind: Mapped[str] = mapped_column(String(24))
    original_value: Mapped[float] = mapped_column(Float)
    corrected_value: Mapped[float | None] = mapped_column(Float, nullable=True)
    corrected_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    unit: Mapped[str] = mapped_column(String(8), default="USD")
    #: Share of the simulated capital, in percent, when the video gives one.
    allocation_pct: Mapped[float | None] = mapped_column(Float, nullable=True)
    #: Position in the video, in seconds ("18:42" -> 1122).
    timestamp_s: Mapped[int | None] = mapped_column(Integer, nullable=True)
    source_text: Mapped[str] = mapped_column(Text, default="")
    #: What confirms the level, as stated in the video - UNKNOWN when it was not.
    condition: Mapped[str] = mapped_column(String(24), default="UNKNOWN")
    confidence: Mapped[str] = mapped_column(String(8), default="HIGH")
    label: Mapped[str] = mapped_column(String(120), default="")
    extra: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    #: EXPLICIT (said) | INFERRED (read from the context)
    basis: Mapped[str] = mapped_column(String(12), default="EXPLICIT")


class LexaConditionRow(LexaBase):
    """How a level counts: a touch, or closes on a given timeframe.

    TOUCH != CLOSE != CONFIRMATION. A CLOSE condition needs `required_closes`
    consecutive closed candles beyond the level; with `confirmation_window`
    the breakout must then hold that many more candles.
    """

    __tablename__ = "lexa_conditions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    level_id: Mapped[int] = mapped_column(ForeignKey("lexa_levels.id"), index=True)
    #: CLOSE | TOUCH | HOLD | RETEST | VOLUME | OTHER
    condition_type: Mapped[str] = mapped_column(String(12), default="CLOSE")
    #: 1H | 4H | 1D | 1W - None when the video did not say
    timeframe: Mapped[str | None] = mapped_column(String(4), nullable=True)
    #: ABOVE | BELOW
    operator: Mapped[str] = mapped_column(String(8), default="ABOVE")
    required_closes: Mapped[int] = mapped_column(Integer, default=1)
    confirmation_window: Mapped[int | None] = mapped_column(Integer, nullable=True)
    description: Mapped[str] = mapped_column(Text, default="")
    basis: Mapped[str] = mapped_column(String(12), default="EXPLICIT")


class LexaActionRow(LexaBase):
    """USER_PLAN: what WE decided to do at a level. Never attributed to Lexa."""

    __tablename__ = "lexa_actions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    analysis_id: Mapped[int] = mapped_column(ForeignKey("lexa_analyses.id"), index=True)
    level_id: Mapped[int | None] = mapped_column(ForeignKey("lexa_levels.id"), nullable=True)
    #: BUY | BUY_PARTIAL | HOLD | TAKE_PROFIT | SELL | WAIT | WAIT_CLOSE | WATCH
    action: Mapped[str] = mapped_column(String(16))
    #: EURO | PERCENT | NONE
    amount_type: Mapped[str] = mapped_column(String(8), default="NONE")
    amount: Mapped[float | None] = mapped_column(Float, nullable=True)
    origin: Mapped[str] = mapped_column(String(12), default="USER_PLAN")
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class LexaFillRow(LexaBase):
    """A purchase or a sale the member says they made. Never automatic."""

    __tablename__ = "lexa_fills"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    analysis_id: Mapped[int] = mapped_column(ForeignKey("lexa_analyses.id"), index=True)
    level_id: Mapped[int | None] = mapped_column(ForeignKey("lexa_levels.id"), nullable=True)
    side: Mapped[str] = mapped_column(String(4))  # BUY | SELL
    price_usd: Mapped[float] = mapped_column(Float)
    quantity: Mapped[float] = mapped_column(Float)
    amount_eur: Mapped[float | None] = mapped_column(Float, nullable=True)
    eurusd: Mapped[float | None] = mapped_column(Float, nullable=True)
    executed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    note: Mapped[str] = mapped_column(Text, default="")


class LexaPlanEventRow(LexaBase):
    """A dated fact of a plan's life: a touch, a close, a supersession, a fill."""

    __tablename__ = "lexa_plan_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    analysis_id: Mapped[int] = mapped_column(ForeignKey("lexa_analyses.id"), index=True)
    asset: Mapped[str] = mapped_column(String(16), index=True)
    event_type: Mapped[str] = mapped_column(String(32))
    scheduled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    triggered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    status: Mapped[str] = mapped_column(String(16), default="TRIGGERED")
    description: Mapped[str] = mapped_column(Text, default="")
    dedup_key: Mapped[str] = mapped_column(String(200), unique=True)


class LexaNotificationRow(LexaBase):
    """An in-app notification. Same key within its cooldown = not sent again."""

    __tablename__ = "lexa_notifications"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    dedup_key: Mapped[str] = mapped_column(String(200), index=True)
    asset: Mapped[str] = mapped_column(String(16), index=True)
    analysis_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    kind: Mapped[str] = mapped_column(String(32))
    message: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    read_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class LexaSettingRow(LexaBase):
    __tablename__ = "lexa_settings"

    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    value: Mapped[str] = mapped_column(String(200))


def database_path() -> Path:
    override = os.environ.get("LEXA_DATABASE_PATH")
    if override:
        return Path(override)
    from ..settings import PROJECT_ROOT

    return PROJECT_ROOT / "data" / "lexa" / "lexa.db"


@lru_cache
def get_engine() -> Engine:
    path = database_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    # Personal data: readable by the owner only.
    os.chmod(path.parent, 0o700)
    engine = create_engine(
        f"sqlite:///{path}", future=True,
        connect_args={"check_same_thread": False, "timeout": 30},
    )

    @event.listens_for(engine, "connect")
    def _pragmas(dbapi_conn, _record):  # type: ignore[no-untyped-def]
        cursor = dbapi_conn.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    LexaBase.metadata.create_all(engine)
    _add_missing_columns(engine)
    if path.exists():
        os.chmod(path, 0o600)
    return engine


def _add_missing_columns(engine: Engine) -> None:
    """SQLite's create_all never adds a column to an existing table: do it here."""

    from sqlalchemy import inspect, text

    inspector = inspect(engine)
    with engine.begin() as conn:
        for table in LexaBase.metadata.sorted_tables:
            present = {c["name"] for c in inspector.get_columns(table.name)}
            for column in table.columns:
                if column.name in present:
                    continue
                kind = column.type.compile(engine.dialect)
                default = column.default.arg if column.default is not None and \
                    not callable(column.default.arg) else None
                clause = f" DEFAULT {default!r}" if default is not None else ""
                conn.execute(text(f"ALTER TABLE {table.name} ADD COLUMN {column.name} {kind}{clause}"))


def reset_engine() -> None:
    get_engine.cache_clear()
    _factory.cache_clear()


@lru_cache
def _factory() -> sessionmaker[Session]:
    return sessionmaker(bind=get_engine(), expire_on_commit=False, future=True)


@contextmanager
def lexa_session() -> Iterator[Session]:
    session = _factory()()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
