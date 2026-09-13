"""Tests for hashing, logging, and small config helpers.

This covers the modules that the pipeline touches indirectly but that had no
direct unit tests: ``core.hashing``, ``logging``, ``Settings.resolve`` and
``EmbedConfig.from_settings``.
"""

from __future__ import annotations

import hashlib
from collections.abc import Iterator
from pathlib import Path

import pytest

import knowledge_base.config as _config
from knowledge_base.core.hashing import sha256_bytes, sha256_file, sha256_text
from knowledge_base.logging import apply_settings, configure_logging
from knowledge_base.pipeline.embed.config import EmbedConfig


@pytest.fixture(autouse=True)
def _reset_settings_singleton() -> Iterator[None]:
    _config._SINGLETON = None
    yield
    _config._SINGLETON = None


class TestSha256:
    def test_sha256_text_known_answer(self) -> None:
        assert sha256_text("hello") == hashlib.sha256(b"hello").hexdigest()

    def test_sha256_bytes_matches_text_encoding(self) -> None:
        assert sha256_bytes(b"sabr") == sha256_text("sabr")

    def test_sha256_file_streams_large_content(self, tmp_path: Path) -> None:
        target = tmp_path / "large.bin"
        target.write_bytes(b"x" * (2 * 1024 * 1024) + b"tail")
        assert sha256_file(target) == hashlib.sha256(b"x" * (2 * 1024 * 1024) + b"tail").hexdigest()

    def test_sha256_file_empty(self, tmp_path: Path) -> None:
        target = tmp_path / "empty.bin"
        target.write_bytes(b"")
        assert sha256_file(target) == hashlib.sha256(b"").hexdigest()

    def test_functions_are_deterministic(self) -> None:
        text = "الحمد لله رب العالمين"
        assert sha256_text(text) == sha256_text(text)
        assert sha256_bytes(text.encode("utf-8")) == sha256_text(text)


class TestLogging:
    def test_configure_logging_default_level(self) -> None:
        configure_logging()  # must not raise

    def test_configure_logging_lowercase_level(self) -> None:
        configure_logging("info")
        configure_logging("warning")

    def test_configure_logging_invalid_level_raises(self) -> None:
        with pytest.raises(ValueError):
            configure_logging("no-such-level")

    def test_configure_logging_is_idempotent(self) -> None:
        configure_logging("DEBUG")
        configure_logging("INFO")  # must not raise (remove + re-add)

    def test_apply_settings_valid(self) -> None:
        apply_settings("WARNING")

    def test_apply_settings_invalid_raises(self) -> None:
        with pytest.raises(ValueError):
            apply_settings("LOUD")

    def test_custom_sink_receives_messages(self) -> None:
        from loguru import logger

        captured: list[str] = []
        configure_logging("TRACE", sink=lambda message: captured.append(str(message)))
        logger.debug("hello kb")
        assert any("hello kb" in line for line in captured)


class TestConfigHelpers:
    def test_settings_resolve_makes_path_absolute(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("KB_DATA_DIR", "relative/data")
        settings = _config.Settings(_env_file=None)
        resolved = settings.resolve()
        assert resolved.data_dir.is_absolute()
        assert settings.data_dir == Path("relative/data")

    def test_embed_config_from_settings(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("KB_EMBEDDING_PROVIDER", "dummy")
        monkeypatch.setenv("KB_EMBEDDING_MODEL", "my-model")
        monkeypatch.setenv("KB_EMBEDDING_MODEL_VERSION", "2.0.0")
        monkeypatch.setenv("KB_EMBEDDING_DIMENSIONS", "384")
        monkeypatch.setenv("KB_EMBEDDING_BATCH_SIZE", "16")
        settings = _config.Settings(_env_file=None)
        cfg = EmbedConfig.from_settings(settings)
        assert cfg.provider_name == "dummy"
        assert cfg.model_name == "my-model"
        assert cfg.model_version == "2.0.0"
        assert cfg.dimensions == 384
        assert cfg.batch_size == 16

    def test_embed_config_defaults(self) -> None:
        cfg = EmbedConfig()
        assert cfg.provider_name == "dummy"
        assert cfg.dimensions == 768
        assert cfg.batch_size == 64
