"""Tests for configuration loading and CLI basics."""

from __future__ import annotations

import json
from collections.abc import Iterator
from pathlib import Path

import pytest

import knowledge_base.config as _config
from knowledge_base.config import Settings, get_settings


@pytest.fixture(autouse=True)
def _reset_settings_singleton() -> Iterator[None]:
    _config._SINGLETON = None
    yield
    _config._SINGLETON = None


def test_defaults_without_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("KB_DATA_DIR", raising=False)
    monkeypatch.delenv("KB_LOG_LEVEL", raising=False)
    monkeypatch.delenv("KB_DATABASE_URL", raising=False)
    monkeypatch.delenv("KB_TEST_DATABASE_URL", raising=False)
    settings = Settings(_env_file=None)
    assert settings.data_dir == Path("data")
    assert settings.log_level == "INFO"
    assert settings.database_url is None
    assert settings.test_database_url is None


def test_env_prefix_mapping(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("KB_DATA_DIR", "some/dir")
    monkeypatch.setenv("KB_LOG_LEVEL", "DEBUG")
    settings = Settings(_env_file=None)
    assert settings.data_dir == Path("some/dir")
    assert settings.log_level == "DEBUG"


def test_env_file_loading(tmp_path: Path) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text("KB_DATA_DIR=./from-env\nKB_LOG_LEVEL=WARNING\n", encoding="utf-8")
    settings = Settings.from_env_file(env_file)
    assert settings.data_dir == Path("./from-env")
    assert settings.log_level == "WARNING"


def test_env_overrides_env_file(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("KB_LOG_LEVEL", "DEBUG")
    env_file = tmp_path / ".env"
    env_file.write_text("KB_LOG_LEVEL=ERROR\n", encoding="utf-8")
    settings = Settings.from_env_file(env_file)
    # Environment variables take precedence over the dotenv file.
    assert settings.log_level == "DEBUG"


def test_get_settings_is_singleton() -> None:
    a = get_settings()
    b = get_settings()
    assert a is b


def test_cli_version(capsys: pytest.CaptureFixture[str]) -> None:
    from knowledge_base.cli import main

    code = main(["version"])
    assert code == 0
    out = capsys.readouterr().out
    assert out.startswith("knowledge-base")


def test_cli_env_json(capsys: pytest.CaptureFixture[str]) -> None:
    from knowledge_base.cli import main

    code = main(["env", "--as-json"])
    assert code == 0
    out = capsys.readouterr().out
    payload = json.loads(out)
    assert "data_dir" in payload
    assert "log_level" in payload


def test_cli_normalize(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    from knowledge_base.cli import main

    src = tmp_path / "sample.txt"
    src.write_text("أحمد إبراهيم آدم 1234\n", encoding="utf-8")
    monkeypatch.setenv("KB_DATA_DIR", str(tmp_path / "kb"))
    code = main(["normalize", str(src)])
    assert code == 0
    out = capsys.readouterr().out
    assert "source_id:" in out
    assert (tmp_path / "kb" / "processed" / "normalized").is_dir()
