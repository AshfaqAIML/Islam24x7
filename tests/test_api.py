"""Tests for the HTTP API surface (health, status, ask, search)."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

import knowledge_base.config as _config

_TEST_URL = "postgresql+psycopg://knowledge_base:islam24x7_dev@localhost:5434/knowledge_base_test"


@pytest.fixture(autouse=True)
def _reset_settings(monkeypatch: pytest.MonkeyPatch) -> None:
    _config._SINGLETON = None
    monkeypatch.setenv("KB_DATABASE_URL", _TEST_URL)
    monkeypatch.setenv("KB_TEST_DATABASE_URL", _TEST_URL)
    monkeypatch.setenv("KB_LOG_LEVEL", "ERROR")
    yield
    _config._SINGLETON = None


@pytest.fixture()
def client(db_engine: object) -> TestClient:
    from knowledge_base.api import create_app

    return TestClient(create_app())


def test_health(client: TestClient) -> None:
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}


def test_status_empty_db(client: TestClient) -> None:
    r = client.get("/status")
    assert r.status_code == 200
    body = r.json()
    for key in ("sources", "books", "chunks", "embeddings", "search_documents"):
        assert body[key] == 0


def test_ask_empty_db(client: TestClient) -> None:
    r = client.post("/ask", json={"question": "What is the virtue of patience?"})
    assert r.status_code == 200
    body = r.json()
    assert body["question"] == "What is the virtue of patience?"
    assert isinstance(body["answer"], str)
    assert isinstance(body["grounded"], bool)
    assert body["sources"] == []
    assert body["generator"] == "extractive"


def test_ask_missing_question_is_422(client: TestClient) -> None:
    r = client.post("/ask", json={})
    assert r.status_code == 422


def test_ask_invalid_language_is_422(client: TestClient) -> None:
    r = client.post("/ask", json={"question": "q", "language": "xx"})
    assert r.status_code == 422


def test_search_empty_db(client: TestClient) -> None:
    r = client.post("/search", json={"query": "patience", "limit": 5})
    assert r.status_code == 200
    body = r.json()
    assert body["query"] == "patience"
    assert isinstance(body["hits"], list)


def test_search_missing_query_is_422(client: TestClient) -> None:
    r = client.post("/search", json={"limit": 3})
    assert r.status_code == 422


def test_ask_get_not_allowed(client: TestClient) -> None:
    r = client.get("/ask")
    assert r.status_code == 405


def test_openapi_schema(client: TestClient) -> None:
    schema = client.get("/openapi.json").json()
    paths = schema["paths"]
    for route in ("/health", "/status", "/ask", "/search"):
        assert route in paths
