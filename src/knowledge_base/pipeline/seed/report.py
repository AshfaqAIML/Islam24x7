"""Seeding report and conflict error type."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class SeedReport:
    """Idempotent-seed outcome counters."""

    kind: str
    created: int = 0
    skipped: int = 0
    conflicts: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, object]:
        return {
            "kind": self.kind,
            "created": self.created,
            "skipped": self.skipped,
            "conflicts": self.conflicts,
        }


class SeedConflictError(ValueError):
    """Raised when an existing row's text disagrees with the dataset.

    Sacred text is never overwritten; callers roll the transaction back.
    """
