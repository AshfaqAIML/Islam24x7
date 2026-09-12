"""Shared pytest fixtures."""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from loguru import logger


@pytest.fixture(autouse=True)
def _teardown_loguru() -> Iterator[None]:
    logger.remove()
    yield
    logger.remove()
