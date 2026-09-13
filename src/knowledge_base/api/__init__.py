"""HTTP API for the Islamic Knowledge Base.

Exposes the user-facing operations of the CLI over JSON: health, status
dashboard, full-text search, and the source-grounded RAG ``ask`` endpoint.

Run with ``kb serve --host 127.0.0.1 --port 8000``.
"""

from __future__ import annotations

from knowledge_base.api.app import create_app

__all__ = ["create_app"]
