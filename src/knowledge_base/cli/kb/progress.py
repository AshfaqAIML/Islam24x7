"""Progress, table, and console helpers for the ``kb`` CLI.

Everything uses only ``sys.stderr`` for progress/metadata (so piped stdout
stays clean for ``--json``), and degrades gracefully on non-TTY prompts.
No third-party dependencies are required.
"""

from __future__ import annotations

import sys
import time
from collections.abc import Iterable
from dataclasses import dataclass

try:
    _COLORS = sys.stderr.isatty()
except Exception:  # pragma: no cover - defensive
    _COLORS = False

_CLEAR = "\r\x1b[2K"


def colorize(text: str, code: str) -> str:
    if not _COLORS:
        return text
    return f"\x1b[{code}m{text}\x1b[0m"


def green(text: str) -> str:
    return colorize(text, "32")


def yellow(text: str) -> str:
    return colorize(text, "33")


def red(text: str) -> str:
    return colorize(text, "31")


def cyan(text: str) -> str:
    return colorize(text, "36")


def dim(text: str) -> str:
    return colorize(text, "2")


def status_symbol(status: str) -> str:
    """Colour a short status word for tables / reports."""
    upper = status.upper()
    if upper in {"SUCCEEDED", "OK", "REGISTERED", "DONE"}:
        return green(status)
    if upper in {"FAILED", "ERROR", "INVALID", "QUARANTINED"}:
        return red(status)
    if upper in {"WAITING", "SKIPPED", "PENDING", "REVIEW"}:
        return yellow(status)
    return status


@dataclass
class Progress:
    """A minimal stderr progress bar (``[n/m] 52% label``)."""

    total: int
    label: str = ""
    _current: int = 0
    _enabled: bool = True

    def __post_init__(self) -> None:
        if not sys.stderr.isatty() or getattr(sys, "_kb_quiet", False):
            self._enabled = False

    def update(self, n: int | None = None, *, label: str | None = None) -> None:
        if n is not None:
            self._current = max(0, min(n, self.total))
        else:
            self._current += 1
        if label is not None:
            self.label = label
        if not self._enabled:
            return
        pct = int(100 * self._current / self.total) if self.total else 100
        bar = "=" * (self._current)
        tail = f" {self.label}" if self.label else ""
        sys.stderr.write(f"\r[{self._current}/{self.total}] {bar}{' ' * max(0, 4)}{pct}%{tail}")
        sys.stderr.flush()

    def finish(self, message: str = "") -> None:
        if not self._enabled:
            return
        sys.stderr.write(_CLEAR)
        sys.stderr.write(message + "\n")
        sys.stderr.flush()


def spinner(label: str) -> _Spinner:
    return _Spinner(label)


class _Spinner:
    """A lightweight blocking spinner used while a command runs."""

    FRAMES = "|/-\\"

    def __init__(self, label: str) -> None:
        self.label = label
        self._enabled = sys.stderr.isatty() and not getattr(sys, "_kb_quiet", False)
        self._pos = 0
        self._started: float | None = None

    def __enter__(self) -> _Spinner:
        if self._enabled:
            self._started = time.monotonic()
            sys.stderr.write(self.FRAMES[0])
            sys.stderr.flush()
        return self

    def tick(self) -> None:
        if not self._enabled:
            return
        self._pos = (self._pos + 1) % len(self.FRAMES)
        sys.stderr.write(f"\r{self.FRAMES[self._pos]} {self.label}")
        sys.stderr.flush()

    def __exit__(self, *exc: object) -> None:
        if not self._enabled:
            return
        sys.stderr.write(_CLEAR)
        sys.stderr.write(self.label + "\n")
        sys.stderr.flush()


def render_table(rows: Iterable[list[str]]) -> str:
    """Render a simple aligned table from a list of string rows."""
    grid = [list(row) for row in rows]
    if not grid:
        return "    (no rows)"
    widths = [max(len(cell) for cell in col) for col in zip(*grid, strict=False)]
    lines: list[str] = []
    for row in grid:
        cells = [cell + " " * (width - len(cell)) for cell, width in zip(row, widths, strict=False)]
        lines.append("   " + "  ".join(cells).rstrip())
    return "\n".join(lines)


__all__ = [
    "Progress",
    "colorize",
    "cyan",
    "dim",
    "green",
    "red",
    "render_table",
    "spinner",
    "status_symbol",
    "yellow",
]
