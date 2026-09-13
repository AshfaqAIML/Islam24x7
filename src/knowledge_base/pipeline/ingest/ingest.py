"""Ingestion: register raw source files into the knowledge base.

Responsibilities:
- Walk a source directory and compute SHA-256 content ids.
- Register a :class:`SourceFile` row (deduplicated by hash).
- Copy accepted files into ``data/raw/<category>/...`` (content-addressed).
- Move unusable files (unsupported type, empty) into ``data/quarantine/``.
- Record a ``ProcessingJob`` of type ``ingest`` with a manifest.

Nothing here reads the PDF body; that is the job of the ``inspect`` stage.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from knowledge_base.config import Settings, get_settings
from knowledge_base.core.hashing import sha256_file
from knowledge_base.database.enums import JobStatus, JobType, SourceFormat, SourceStatus
from knowledge_base.database.models.sources import ProcessingJob, SourceFile
from knowledge_base.logging import logger

_SUPPORTED_EXTENSIONS: dict[str, SourceFormat] = {
    ".pdf": SourceFormat.PDF,
    ".epub": SourceFormat.EPUB,
    ".docx": SourceFormat.DOCX,
    ".txt": SourceFormat.TXT,
    ".md": SourceFormat.TXT,
    ".html": SourceFormat.HTML,
    ".htm": SourceFormat.HTML,
    ".json": SourceFormat.JSON,
}


class IngestionError(Exception):
    """Raised when a file cannot be reliably ingested."""


@dataclass(frozen=True)
class IngestionResult:
    """Outcome of ingesting one file."""

    path: Path
    sha256: str | None = None
    status: str = "registered"  # registered | duplicate | quarantined | failed
    reason: str | None = None
    target: Path | None = None


def raw_target(data_dir: Path, category: str, sha256: str, filename: str) -> Path:
    """Return the content-addressed storage path for an ingested file."""
    return data_dir / "raw" / category / sha256[:2] / sha256[2:4] / sha256 / filename


def _quarantine_target(data_dir: Path, path: Path) -> Path:
    quarantine_dir = data_dir / "quarantine"
    target = quarantine_dir / path.name
    counter = 1
    while target.exists():
        target = quarantine_dir / f"{path.stem}-{counter}{path.suffix}"
        counter += 1
    return target


def _format_for(path: Path) -> SourceFormat | None:
    return _SUPPORTED_EXTENSIONS.get(path.suffix.lower())


def ingest_file(
    path: Path,
    *,
    session: Session,
    data_dir: Path,
    category: str,
    dry_run: bool = False,
) -> IngestionResult:
    """Register, hash, and store one source file.

    ``dry_run`` hashes and reports what *would* happen without touching the
    database or the filesystem.
    """
    fmt = _format_for(path)
    if fmt is None:
        reason = f"unsupported extension {path.suffix!r}"
        return IngestionResult(path=path, status="quarantined", reason=reason)

    if path.stat().st_size == 0:
        return IngestionResult(path=path, status="quarantined", reason="empty file")

    sha = sha256_file(path)
    existing = session.scalar(
        select(SourceFile).where(SourceFile.sha256 == sha).options(selectinload(SourceFile.jobs))
    )
    if existing is not None:
        return IngestionResult(path=path, sha256=sha, status="duplicate", reason=existing.file_path)

    target = raw_target(data_dir, category, sha, path.name)

    if dry_run:
        return IngestionResult(path=path, sha256=sha, status="registered", target=target)

    data_dir.mkdir(parents=True, exist_ok=True)
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists() and sha256_file(target) != sha:
        raise IngestionError(f"target already exists with different content: {target}")

    try:
        source_file = SourceFile(
            sha256=sha,
            file_path=str(target.relative_to(data_dir.resolve())).replace("\\", "/"),
            format=fmt,
            status=SourceStatus.REGISTERED,
            title_hint=path.stem,
            size_bytes=path.stat().st_size,
        )
        manifest = {
            "source_path": str(path),
            "size_bytes": path.stat().st_size,
            "category": category,
        }
        if not target.exists():
            with target.open("xb") as handle, path.open("rb") as source:
                for chunk in iter(lambda: source.read(1024 * 1024), b""):
                    handle.write(chunk)
        session.add(source_file)
        session.flush()
        session.add(
            ProcessingJob(
                source_file_id=source_file.id,
                job_type=JobType.INGEST,
                status=JobStatus.SUCCEEDED,
                manifest=manifest,
            )
        )
        return IngestionResult(path=path, sha256=sha, status="registered", target=target)
    except Exception as exc:
        target.unlink(missing_ok=True)
        if isinstance(exc, IngestionError):
            raise
        return IngestionResult(path=path, sha256=sha, status="failed", reason=str(exc))


def ingest_directory(
    source_dir: Path,
    *,
    session: Session,
    data_dir: Path | None = None,
    category: str = "books",
    dry_run: bool = False,
    settings: Settings | None = None,
) -> list[IngestionResult]:
    """Ingest every supported file under ``source_dir``.

    Returns one :class:`IngestionResult` per file in stable (sorted) order.
    Quarantined files are moved to ``data/quarantine/`` on disk immediately;
    all other mutations are committed by the caller's ``session_scope``.
    """
    if settings is None:
        settings = get_settings()
    if data_dir is None:
        data_dir = settings.data_dir
    data_dir = data_dir.resolve()
    source_dir = source_dir.resolve()
    if not source_dir.is_dir():
        raise ValueError(f"not a directory: {source_dir}")

    results: list[IngestionResult] = []
    files = sorted(p for p in source_dir.rglob("*") if p.is_file())

    for path in files:
        result = ingest_file(
            path,
            session=session,
            data_dir=data_dir,
            category=category,
            dry_run=dry_run,
        )
        if result.status == "quarantined" and not dry_run:
            target = _quarantine_target(data_dir, path)
            target.parent.mkdir(parents=True, exist_ok=True)
            path.rename(target)
            logger.warning("quarantined {} ({})", path, result.reason)
        else:
            logger.info("{} {} -> {}", result.status, path.name, result.sha256 or "-")
        results.append(result)

    return results


__all__ = [
    "IngestionError",
    "IngestionResult",
    "ingest_directory",
    "ingest_file",
    "raw_target",
]
