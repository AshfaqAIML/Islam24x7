"""Hashing helpers for sources and content.

Source identity is the SHA-256 of the raw file: stable, content-addressed,
and independent of file name or location.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

_CHUNK_SIZE = 1024 * 1024


def sha256_file(path: Path) -> str:
    """Return the lowercase hex SHA-256 digest of a file."""
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(_CHUNK_SIZE):
            digest.update(chunk)
    return digest.hexdigest()


def sha256_bytes(data: bytes) -> str:
    """Return the lowercase hex SHA-256 digest of raw bytes."""
    return hashlib.sha256(data).hexdigest()


def sha256_text(text: str) -> str:
    """Return the lowercase hex SHA-256 digest of a UTF-8 encoded string."""
    return sha256_bytes(text.encode("utf-8"))


__all__ = ["sha256_bytes", "sha256_file", "sha256_text"]
