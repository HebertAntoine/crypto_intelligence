"""Lightweight additive migrations.

`Base.metadata.create_all` creates missing tables but never adds a column or an
index to an existing one, so a schema change would silently fail on an existing
database.

Scope is deliberately narrow: additive columns and indexes only.  Both are safe
to run repeatedly and avoid pulling in Alembic for a single-user local tool.
Anything destructive is out of scope on purpose.
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
        # Nullable keeps legacy rows readable. New writes populate the full
        # receipt only once the in-app row is accepted by the transaction.
        ("notification_id", "VARCHAR(40)", ""),
        ("trigger_id", "VARCHAR(128)", ""),
        ("asset_id", "VARCHAR(16)", ""),
        ("analysis_id", "VARCHAR(64)", ""),
        ("created_at", "DATETIME", ""),
        ("delivered_at", "DATETIME", ""),
        ("delivery_status", "VARCHAR(24)", ""),
        ("source_snapshot", "JSON", ""),
    ],
    # LOT 4: temporal provenance on macro series. Without release_time a study
    # cannot tell when a value actually became knowable.
    "macro_series": [
        ("provider", "VARCHAR(64)", "DEFAULT ''"),
        ("unit", "VARCHAR(24)", "DEFAULT ''"),
        ("source_url", "VARCHAR(512)", ""),
        ("series_id", "VARCHAR(64)", ""),
        ("license_status", "VARCHAR(32)", "DEFAULT 'UNKNOWN'"),
        ("meta", "JSON", ""),
        ("release_time", "DATETIME", ""),
        ("revision_time", "DATETIME", ""),
        ("availability", "VARCHAR(24)", "DEFAULT 'UNKNOWN'"),
        ("is_first_print", "BOOLEAN", "DEFAULT 1"),
        ("revision_number", "INTEGER", "DEFAULT 0"),
        ("vintage_date", "DATETIME", ""),
        ("ingested_at", "DATETIME", ""),
    ],
    # Vintage provenance is nullable so existing ALFRED/history rows remain
    # readable. New writes always populate it; legacy NULLs use a field-level
    # fallback to the current series row.
    "macro_vintages": [
        ("source", "VARCHAR(48)", ""),
        ("provider", "VARCHAR(64)", ""),
        ("unit", "VARCHAR(24)", ""),
        ("source_url", "VARCHAR(512)", ""),
        ("license_status", "VARCHAR(32)", ""),
        ("meta", "JSON", ""),
        ("release_time", "DATETIME", ""),
        ("availability", "VARCHAR(24)", ""),
    ],
}

# table -> [(index name, comma-separated columns, unique)]
_ADDITIVE_INDEXES: dict[str, list[tuple[str, str, bool]]] = {
    # NULL legacy identifiers do not conflict. Deterministic identifiers make
    # retrying the exact same event idempotent at the database boundary.
    "alerts": [("ux_alert_notification_id", "notification_id", True)],
}


def existing_columns(table: str) -> set[str]:
    inspector = inspect(get_engine())
    if table not in inspector.get_table_names():
        return set()
    return {c["name"] for c in inspector.get_columns(table)}


def existing_indexes(table: str) -> set[str]:
    inspector = inspect(get_engine())
    if table not in inspector.get_table_names():
        return set()
    indexes = {index["name"] for index in inspector.get_indexes(table) if index.get("name")}
    # Some databases expose a unique constraint separately from indexes.
    indexes.update(
        constraint["name"]
        for constraint in inspector.get_unique_constraints(table)
        if constraint.get("name")
    )
    return indexes


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

    for table, indexes in _ADDITIVE_INDEXES.items():
        if not existing_columns(table):
            continue
        present = existing_indexes(table)
        for name, index_columns, unique in indexes:
            if name in present:
                continue
            qualifier = "UNIQUE " if unique else ""
            statement = f"CREATE {qualifier}INDEX {name} ON {table} ({index_columns})"
            try:
                with engine.begin() as conn:
                    conn.execute(text(statement))
                applied.append(f"{table}.{name}")
                log.info("migration_index_applied", table=table, index=name)
            except Exception as exc:
                log.warning("migration_index_failed", table=table, index=name, error=str(exc))

    return applied
