"""Structured JSON logging with a ``run_id`` on every record.

Usage::

    from src.log import get_logger
    logger = get_logger(__name__)
    logger.info("scoring complete", n_customers=2000, scoring_date="2024-11-01")

All log lines are JSON objects for machine parsing.  A ``run_id`` is
generated once per process and attached to every record so pipeline
runs can be traced end-to-end.
"""
from __future__ import annotations

import logging
import sys
import uuid
from functools import lru_cache

import structlog

# ── Process-level run id ──────────────────────────────────────────────
RUN_ID: str = uuid.uuid4().hex[:12]


def _add_run_id(logger: logging.Logger, method_name: str, event_dict: dict) -> dict:
    event_dict["run_id"] = RUN_ID
    return event_dict


def configure_logging(level: str = "INFO", json: bool = True) -> None:
    """Call once at process start to configure structured logging."""
    processors: list = [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_log_level,
        structlog.stdlib.add_logger_name,
        structlog.processors.TimeStamper(fmt="iso"),
        _add_run_id,
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
    ]
    if json:
        processors.append(structlog.processors.JSONRenderer())
    else:
        processors.append(structlog.dev.ConsoleRenderer())

    structlog.configure(
        processors=processors,
        wrapper_class=structlog.stdlib.BoundLogger,
        context_class=dict,
        logger_factory=structlog.PrintLoggerFactory(file=sys.stderr),
        cache_logger_on_first_use=True,
    )
    logging.basicConfig(format="%(message)s", stream=sys.stderr, level=getattr(logging, level.upper(), logging.INFO))


@lru_cache(maxsize=1)
def _ensure_configured() -> None:
    configure_logging()


def get_logger(name: str | None = None) -> structlog.stdlib.BoundLogger:
    """Return a bound structured logger, configuring on first call."""
    _ensure_configured()
    return structlog.get_logger(name or "predelinq")
