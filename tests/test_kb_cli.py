"""Tests for the ``kb`` CLI: parsing, dispatch, dry-runs, and exit codes.

Database-backed commands run against the shared test database schema
(``db_engine`` fixture) so the full command surface is exercised without a
stub engine.
"""

from __future__ import annotations

from pathlib import Path

import pytest

import knowledge_base.config as _config
from knowledge_base.cli.kb import main

_TEST_URL = "postgresql+psycopg://knowledge_base:islam24x7_dev@localhost:5434/knowledge_base_test"


@pytest.fixture(autouse=True)
def _reset_settings(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Isolate settings + env for every kb CLI test."""
    _config._SINGLETON = None
    monkeypatch.setenv("KB_DATABASE_URL", _TEST_URL)
    monkeypatch.setenv("KB_TEST_DATABASE_URL", _TEST_URL)
    monkeypatch.setenv("KB_DATA_DIR", str(tmp_path / "kb"))
    monkeypatch.setenv("KB_LOG_LEVEL", "ERROR")
    monkeypatch.delenv("KB_AUTOFLUSH", raising=False)
    yield
    _config._SINGLETON = None


def test_kb_version(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as err:
        main(["--version"])
    assert err.value.code == 0
    assert "kb" in capsys.readouterr().out


def test_kb_help_lists_commands(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as err:
        main(["--help"])
    assert err.value.code == 0
    out = capsys.readouterr().out
    for cmd in (
        "inspect",
        "import",
        "process",
        "validate",
        "search",
        "embed",
        "reindex",
        "status",
        "retry",
        "stats",
        "export",
    ):
        assert cmd in out


def test_kb_unknown_command_exits_2() -> None:
    with pytest.raises(SystemExit) as err:
        main(["frobnicate"])
    assert err.value.code == 2


def test_kb_inspect_missing_file_exits_1(capsys: pytest.CaptureFixture[str]) -> None:
    missing = Path("data") / "does-not-exist.pdf"
    code = main(["inspect", str(missing)])
    assert code == 1
    assert "file not found" in capsys.readouterr().err


def test_kb_process_dry_run_no_db_needed(capsys: pytest.CaptureFixture[str]) -> None:
    code = main(["process", "--dry-run"])
    assert code == 0
    assert "dry run" in capsys.readouterr().err


def test_kb_process_dry_run_json(capsys: pytest.CaptureFixture[str]) -> None:
    code = main(["--json", "process", "--dry-run"])
    assert code == 0
    out = capsys.readouterr().out  # json path not used for dry-run; still exit 0
    assert "dry run" in out or out == ""


def test_kb_status_db_backed(db_engine: object) -> None:
    code = main(["status"])
    assert code == 0


def test_kb_status_json(db_engine: object, capsys: pytest.CaptureFixture[str]) -> None:
    import json

    code = main(["--json", "status"])
    assert code == 0
    payload = json.loads(capsys.readouterr().out)
    assert "sources" in payload
    assert "books" in payload
    assert "chunks" in payload


def test_kb_stats_db_backed(db_engine: object) -> None:
    code = main(["stats"])
    assert code == 0


def test_kb_validate_empty_db_ok(db_engine: object, capsys: pytest.CaptureFixture[str]) -> None:
    code = main(["validate"])
    assert code == 0
    assert "no issues" in capsys.readouterr().out


def test_kb_search_none_found(db_engine: object, capsys: pytest.CaptureFixture[str]) -> None:
    code = main(["search", "nonexistenttermzz", "--limit", "5"])
    assert code == 0
    assert "no results" in capsys.readouterr().err or "no results" in capsys.readouterr().out


def test_kb_embed_no_books(db_engine: object, capsys: pytest.CaptureFixture[str]) -> None:
    code = main(["embed", "--all"])
    assert code == 0
    assert "no books to embed" in capsys.readouterr().err


def test_kb_reindex_no_books(db_engine: object, capsys: pytest.CaptureFixture[str]) -> None:
    code = main(["reindex", "--all"])
    assert code == 0
    assert "no books to index" in capsys.readouterr().err


def test_kb_retry_empty(db_engine: object, capsys: pytest.CaptureFixture[str]) -> None:
    code = main(["retry", "--all"])
    assert code == 0
    assert "nothing to retry" in capsys.readouterr().err


def test_kb_export_no_books(
    db_engine: object, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    code = main(["export", "--all", "--out", str(tmp_path / "exports")])
    assert code == 0
    assert "no books to export" in capsys.readouterr().err
