"""Shared helpers for recording pipeline ``ProcessingJob`` records."""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from knowledge_base.database.enums import JobStatus, JobType
from knowledge_base.database.models.sources import ProcessingJob


def upsert_processing_job(
    session: Session,
    *,
    source_file_id: uuid.UUID,
    job_type: JobType,
    status: JobStatus,
    manifest: dict[str, Any],
    error: str | None = None,
) -> ProcessingJob:
    """Create or replace the single job record for a (file, stage) pair.

    The ``UNIQUE (source_file_id, job_type)`` constraint keeps each stage
    idempotent: re-running a stage updates its latest record instead of
    accumulating duplicates.
    """
    job = session.scalar(
        select(ProcessingJob).where(
            ProcessingJob.source_file_id == source_file_id,
            ProcessingJob.job_type == job_type,
        )
    )
    if job is None:
        job = ProcessingJob(
            source_file_id=source_file_id,
            job_type=job_type,
            status=status,
            manifest=manifest,
            error=error,
        )
        session.add(job)
    else:
        job.status = status
        job.manifest = manifest
        job.error = error
    return job


__all__ = ["upsert_processing_job"]