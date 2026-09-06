"""Structured logging via structlog.

Console-friendly in local development, JSON when ENV != local so that logs
stay grep-able if this ever runs unattended.
"""

from __future__ import annotations

import logging
import sys

import structlog

_configured = False


def setup_logging(level: str = "INFO", json_logs: bool = False) -> None:
    global _configured
    if _configured:
        return

    logging.basicConfig(
        format="%(message)s",
        stream=sys.stdout,
        level=getattr(logging, level.upper(), logging.INFO),
    )
    # These libraries are chatty at INFO and drown out our own events.
    for noisy in ("httpx", "httpcore", "apscheduler", "urllib3"):
        logging.getLogger(noisy).setLevel(logging.WARNING)

    processors: list = [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_log_level,
        structlog.processors.TimeStamper(fmt="iso", utc=True),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
    ]
    processors.append(
        structlog.processors.JSONRenderer()
        if json_logs
        else structlog.dev.ConsoleRenderer(colors=sys.stdout.isatty())
    )

    structlog.configure(
        processors=processors,
        wrapper_class=structlog.make_filtering_bound_logger(
            getattr(logging, level.upper(), logging.INFO)
        ),
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )
    _configured = True


def get_logger(name: str = "crypto_intel") -> structlog.stdlib.BoundLogger:
    if not _configured:
        setup_logging()
    return structlog.get_logger(name)
