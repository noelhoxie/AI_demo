"""Shared pytest fixtures.

The environment is configured BEFORE importing ``api`` so the module loads in a
deterministic, fully offline state (no warehouse, no tokens, no network calls
at import time).
"""
import os
import sys
from pathlib import Path

import pytest

APP_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(APP_DIR))

# Must be set before `import api` — module-level config reads these.
os.environ.update({
    "SECRET_KEY":             "test-secret-key",
    "DATABRICKS_HOST":        "",
    "DATABRICKS_TOKEN":       "",
    "ANTHROPIC_API_KEY":      "",
    "GOOGLE_CREDENTIALS_B64": "",
    "GOOGLE_CREDENTIALS_JSON": "",
    "FIN_GOOGLE_API_KEY":     "",
    "SESSION_COOKIE_SECURE":  "false",  # allow the test client to keep cookies over http
})

import api as api_module  # noqa: E402


@pytest.fixture(scope="session", autouse=True)
def _no_side_effects():
    """Neutralize fire-and-forget side effects (warehouse warmup, Sheets logging)."""
    api_module._warm_warehouse     = lambda: None
    api_module._sheets_log_write   = lambda *a, **k: None
    api_module._sheets_log_question = lambda *a, **k: None
    yield


@pytest.fixture
def api():
    return api_module


@pytest.fixture
def app():
    api_module.app.config.update(TESTING=True)
    return api_module.app


@pytest.fixture
def client(app):
    return app.test_client()


@pytest.fixture
def auth_client(client):
    """A client through the lead-capture login (any name + company authenticates)."""
    client.post("/login", data={"username": "Jane Lead", "password": "Acme Corp"})
    return client
