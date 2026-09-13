"""Tests for database session helpers and job upserting.

``database.session`` helpers (session_scope commit/rollback contract, URL
guards) and ``pipeline.jobs.upsert_processing_job`` (create-vs-replace) were
only exercised indirectly before.
"""

from __future__ import annotations

import pytest
from sqlalchemy import func, select

import knowledge_base.config as _config
from knowledge_base.database import create_app_engine, make_session_factory, session_scope
from knowledge_base.database.enums import JobStatus, JobType, SourceFormat, SourceStatus
from knowledge_base.database.models.sources import ProcessingJob, SourceFile
from knowledge_base.database.session import build_url, is_postgres_url
from knowledge_base.pipeline.jobs import upsert_processing_job


@pytest.fixture(autouse=True)
def _reset_settings_singleton() -> None:
    _config._SINGLETON = None
    yield
    _config._SINGLETON = None


def _make_source(sha: str = "a" * 64) -> SourceFile:
    return SourceFile(
        sha256=sha,
        file_path="/raw/test.pdf",
        format=SourceFormat.PDF,
        status=SourceStatus.REGISTERED,
    )


class TestBuildUrl:
    def test_explicit_url_wins(self) -> None:
        assert build_url("postgresql+psycopg://x") == "postgresql+psycopg://x"

    def test_falls_back_to_settings(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("KB_DATABASE_URL", "postgresql+psycopg://env")
        assert build_url(None) == "postgresql+psycopg://env"

    def test_unconfigured_raises(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("KB_DATABASE_URL", raising=False)
        with pytest.raises(ValueError):
            build_url(None)


class TestIsPostgresUrl:
    def test_postgresql_true(self) -> None:
        assert is_postgres_url("postgresql+psycopg://u:p@localhost:5434/db")

    def test_sqlite_false(self) -> None:
        assert not is_postgres_url("sqlite:///tmp/x.db")

    def test_sqlite_absolute_false(self) -> None:
        assert not is_postgres_url("sqlite:////absolute/path.db")


class TestSessionScope:
    def _cleanup_source(self, factory: object, sha: str) -> None:
        from sqlalchemy import delete
        from sqlalchemy import select as _select

        with session_scope(factory) as session:  # type: ignore[arg-type]
            sf = session.scalar(_select(SourceFile).where(SourceFile.sha256 == sha))
            if sf is None:
                return
            session.execute(delete(ProcessingJob).where(ProcessingJob.source_file_id == sf.id))  # type: ignore[arg-type]
            session.execute(delete(SourceFile).where(SourceFile.id == sf.id))

    def test_commit_on_success(self, db_engine: object) -> None:

        engine = db_engine  # type: ignore[assignment]
        factory = make_session_factory(engine)  # type: ignore[arg-type]
        with session_scope(factory) as session:
            session.add(_make_source())
        with factory() as check:
            count = check.scalar(
                select(func.count()).select_from(SourceFile).where(SourceFile.sha256 == "a" * 64)
            )
        assert count == 1
        self._cleanup_source(factory, "a" * 64)

    def test_rollback_on_exception(self, db_engine: object) -> None:

        engine = db_engine  # type: ignore[assignment]
        factory = make_session_factory(engine)  # type: ignore[arg-type]
        with pytest.raises(RuntimeError):
            with session_scope(factory) as session:
                session.add(_make_source(sha="b" * 64))
                raise RuntimeError("boom")
        with factory() as check:
            count = check.scalar(
                select(func.count()).select_from(SourceFile).where(SourceFile.sha256 == "b" * 64)
            )
        assert count == 0
        self._cleanup_source(factory, "b" * 64)

    def test_public_create_app_engine_smoke(self) -> None:
        # create_app_engine must construct without connecting.
        engine = create_app_engine("postgresql+psycopg://localhost/none")
        assert engine.dialect.name == "postgresql"
        engine.dispose()


class TestUpsertProcessingJob:
    def _engine(self, db_engine: object):
        return db_engine  # type: ignore[return-value]

    def _factory(self, db_engine: object):
        engine = self._engine(db_engine)
        return make_session_factory(engine)

    def _cleanup_source(self, factory: object, sha: str) -> None:
        from sqlalchemy import delete
        from sqlalchemy import select as _select

        with session_scope(factory) as session:  # type: ignore[arg-type]
            sf = session.scalar(_select(SourceFile).where(SourceFile.sha256 == sha))
            if sf is None:
                return
            session.execute(delete(ProcessingJob).where(ProcessingJob.source_file_id == sf.id))  # type: ignore[arg-type]
            session.execute(delete(SourceFile).where(SourceFile.id == sf.id))

    def _register_source(self, factory: object, sha: str) -> str:
        with session_scope(factory) as session:  # type: ignore[arg-type]
            src = _make_source(sha)
            session.add(src)
            session.flush()
            sid = src.id
        return str(sid)

    def test_creates_then_updates_single_row(self, db_engine: object) -> None:
        factory = self._factory(db_engine)
        source_id = self._register_source(factory, "c" * 64)

        with session_scope(factory) as session:
            job1 = upsert_processing_job(
                session,
                source_file_id=source_id,
                job_type=JobType.EXTRACT,
                status=JobStatus.RUNNING,
                manifest={"pages": 5},
            )
            session.flush()
            first_id = job1.id
            # Re-running the same stage replaces the record in place.
            job2 = upsert_processing_job(
                session,
                source_file_id=source_id,
                job_type=JobType.EXTRACT,
                status=JobStatus.SUCCEEDED,
                manifest={"pages": 6, "chars": 100},
            )
            assert job2.id == first_id
            session.flush()

        with factory() as check:
            jobs = check.scalars(
                select(ProcessingJob).where(
                    ProcessingJob.source_file_id == source_id  # type: ignore[arg-type]
                )
            ).all()
        assert len(jobs) == 1
        assert jobs[0].status == JobStatus.SUCCEEDED
        assert jobs[0].manifest == {"pages": 6, "chars": 100}
        self._cleanup_source(factory, "c" * 64)

    def test_distinct_job_types_coexist(self, db_engine: object) -> None:
        factory = self._factory(db_engine)
        source_id = self._register_source(factory, "d" * 64)

        with session_scope(factory) as session:
            upsert_processing_job(
                session,
                source_file_id=source_id,
                job_type=JobType.EXTRACT,
                status=JobStatus.SUCCEEDED,
                manifest={},
            )
            upsert_processing_job(
                session,
                source_file_id=source_id,
                job_type=JobType.OCR,
                status=JobStatus.FAILED,
                manifest={},
                error="engine missing",
            )
            session.flush()

        with factory() as check:
            jobs = check.scalars(
                select(ProcessingJob).where(
                    ProcessingJob.source_file_id == source_id  # type: ignore[arg-type]
                )
            ).all()
        assert len(jobs) == 2
        failed = next(j for j in jobs if j.job_type == JobType.OCR)
        assert failed.status == JobStatus.FAILED
        assert failed.error == "engine missing"
        self._cleanup_source(factory, "d" * 64)
