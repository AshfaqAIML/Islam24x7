"""Structured logging setup built on ``loguru``.

The pipeline speaks a single logging facility configured once at entry points
via :func:`configure_logging`. Logs are emitted to stderr with structured,
colorized key=value records so they can be machine-parsed when needed.
"""

from __future__ import annotations

import sys
from typing import Any

from loguru import logger as logger

from knowledge_base.config import LogLevel

_FORMAT = (
    "<green>{time:YYYY-MM-DD HH:mm:ss.SSS}</green> | "
    "<level>{level: <8}</level> | "
    "<cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - "
    "<level>{message}</level>"
)


def _resolve_level(level: str) -> str:
    upper = level.upper()
    if upper not in {"TRACE", "DEBUG", "INFO", "SUCCESS", "WARNING", "ERROR", "CRITICAL"}:
        raise ValueError(f"Unknown log level: {level!r}")
    return upper


def configure_logging(level: LogLevel | str = "INFO", *, sink: Any = sys.stderr) -> None:
    """Configure the process-wide loguru sink.

    Idempotent: safe to call more than once. Existing sinks are removed first.

    ``sink`` is passed straight to loguru's ``add``, accepting a file, path,
    or callable; defaults to ``sys.stderr``.
    """
    logger.remove()
    logger.add(sink, level=_resolve_level(level), format=_FORMAT)


def apply_settings(level: str) -> None:
    """Configure logging from a raw settings value (e.g. ``KB_LOG_LEVEL``)."""
    configure_logging(_resolve_level(level))


__all__ = ["apply_settings", "configure_logging", "logger"]
