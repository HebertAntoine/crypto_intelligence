"""Lightweight additive migrations.

`Base.metadata.create_all` creates missing TABLES but never adds a column to an
existing one, so a schema change would silently fail on an existing database.

Scope is deliberately narrow: additive column changes only. That covers every
migration this project has needed, is safe to run repeatedly, and avoids
pulling in Alembic for a single-user local tool. Anything destructive is out of
scope on purpose - it would be the wrong thing to automate here.
"""

from __future__ import annotations

from sqlalchemy import inspect, text

from ..logging_setup import get_logger
from .session import get_engine

log = get_logger("db.migrations")

# table -> [(column, SQL type, default clause)]
_ADDITIVE_COLUMNS: dict[str, list[tuple[str, str, str]]] = {
    "alerts": [
        ("dedup_key", "VARCHAR(128)", ""),
        ("reason", "TEXT", "DEFAULT ''"),
    ],
    # LOT 4: temporal provenance on macro series. Without release_time a study
    # cannot tell when a value actually became knowable.
    "macro_series": [
        ("release_time", "DATETIME", ""),
        ("revision_time", "DATETIME", ""),
        ("availability", "VARCHAR(24)", "DEFAULT 'UNKNOWN'"),
        ("is_first_print", "BOOLEAN", "DEFAULT 1"),
        ("vintage_date", "DATETIME", ""),
        ("ingested_at", "DATETIME", ""),
    ],
}


def existing_columns(table: str) -> set[str]:
    inspector = inspect(get_engine())
    if table not in inspector.get_table_names():
        return set()
    return {c["name"] for c in inspector.get_columns(table)}


def run_migrations() -> list[str]:
    """Apply additive migrations. Safe to call on every startup."""
    applied: list[str] = []
    engine = get_engine()

    for table, columns in _ADDITIVE_COLUMNS.items():
        present = existing_columns(table)
        if not present:
            continue  # table does not exist yet; create_all will build it correctly
        for name, sql_type, default in columns:
            if name in present:
                continue
            statement = f"ALTER TABLE {table} ADD COLUMN {name} {sql_type} {default}".strip()
            try:
                with engine.begin() as conn:
                    conn.execute(text(statement))
                applied.append(f"{table}.{name}")
                log.info("migration_applied", table=table, column=name)
            except Exception as exc:
                # A failed additive migration must not stop the application.
                log.warning("migration_failed", table=table, column=name, error=str(exc))

    return applied
