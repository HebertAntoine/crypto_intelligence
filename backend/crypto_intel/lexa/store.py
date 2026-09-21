"""Lexa's own database, kept apart from everything the app publishes.

The main database feeds JSON snapshots that are committed to a public
repository. Lexa analyses come from a paid, personal subscription whose terms
forbid redistribution, so they live in a separate SQLite file under
``data/lexa/`` - ignored by Git, never read by the export script.

Each analysis is immutable once written: a new video creates a new scenario,
it never overwrites an old one. The only thing that changes afterwards is a
correction, which keeps the original value beside the corrected one.
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
    return engine


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
