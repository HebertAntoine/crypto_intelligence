"""Engine and session management."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from functools import lru_cache

from sqlalchemy import Engine, create_engine, event
from sqlalchemy.orm import Session, sessionmaker

from ..settings import get_settings
from .base import Base


@lru_cache
def get_engine() -> Engine:
    settings = get_settings()
    url = settings.resolved_database_url
    kwargs: dict = {"echo": False, "future": True}
    if url.startswith("sqlite"):
        # check_same_thread=False: FastAPI runs sync endpoints in a threadpool.
        kwargs["connect_args"] = {"check_same_thread": False, "timeout": 30}
    engine = create_engine(url, **kwargs)

    if url.startswith("sqlite"):
        @event.listens_for(engine, "connect")
        def _sqlite_pragmas(dbapi_conn, _record):  # type: ignore[no-untyped-def]
            cur = dbapi_conn.cursor()
            # WAL lets the scheduler write while the API reads.
            cur.execute("PRAGMA journal_mode=WAL")
            cur.execute("PRAGMA synchronous=NORMAL")
            cur.execute("PRAGMA foreign_keys=ON")
            cur.close()

    return engine


@lru_cache
def get_session_factory() -> sessionmaker[Session]:
    return sessionmaker(bind=get_engine(), expire_on_commit=False, future=True)


def init_db() -> None:
    """Create tables if absent, then apply additive migrations.

    Safe to call repeatedly. Migrations are imported lazily to avoid a circular
    import (migrations needs the engine this module owns).
    """
    Base.metadata.create_all(get_engine())
    from .migrations import run_migrations

    run_migrations()


@contextmanager
def session_scope(*, immediate: bool = False) -> Iterator[Session]:
    """Transactional scope. Rolls back on any exception.

    ``immediate`` reserves SQLite's write lock before a read/check/insert
    sequence. It is opt-in so ordinary readers remain concurrent; alert
    receipt deduplication needs it to make its cooldown check atomic.
    """
    session = get_session_factory()()
    try:
        if immediate and session.bind is not None and session.bind.dialect.name == "sqlite":
            session.connection().exec_driver_sql("BEGIN IMMEDIATE")
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def reset_engine() -> None:
    """Used by tests switching to a temporary database."""
    get_engine.cache_clear()
    get_session_factory.cache_clear()
