"""Application configuration backed by ``pydantic-settings``.

Settings are resolved in increasing priority:

1. Field defaults
2. Values from a local ``.env`` file (gitignored — see ``.env.example``)
3. Environment variables prefixed with ``KB_`` (e.g. ``KB_LOG_LEVEL``)
4. Keyword arguments passed to :class:`Settings`

Every real credential lives only in the local ``.env``; nothing secret is
committed.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

LogLevel = Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]

_DEFAULT_ENV_FILE = Path(".env")


class Settings(BaseSettings):
    """Typed, env-driven application settings."""

    model_config = SettingsConfigDict(
        env_prefix="KB_",
        env_file=str(_DEFAULT_ENV_FILE),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    data_dir: Path = Field(default=Path("data"))
    log_level: LogLevel = Field(default="INFO")
    database_url: str | None = Field(default=None)
    test_database_url: str | None = Field(default=None)

    @classmethod
    def from_env_file(cls, env_file: str | os.PathLike[str], **kwargs: Any) -> Settings:
        """Build settings from a specific dotenv file instead of the default one.

        ``env_file`` may point at any dotenv file; existing environment
        variables still take precedence, matching pydantic-settings behaviour.
        """
        options: dict[str, Any] = {
            "_env_file": os.fspath(env_file),
            "_env_file_encoding": "utf-8",
        }
        options.update(kwargs)
        return cls(**options)

    def resolve(self) -> Settings:
        """Return a copy of this settings instance with absolute paths."""
        return self.model_copy(update={"data_dir": self.data_dir.resolve()})


def get_settings() -> Settings:
    """Return a cached process-wide settings instance."""
    global _SINGLETON
    if _SINGLETON is None:
        _SINGLETON = Settings()
    return _SINGLETON


_SINGLETON: Settings | None = None
