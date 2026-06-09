"""Smoke tests: the app imports, basic routes behave, the login gate works."""


def test_app_imports(api):
    assert api.app is not None


def test_health_ok(client, api, monkeypatch):
    # Force the outbound-IP lookup to fail fast so the test stays offline.
    def _boom(*a, **k):
        raise RuntimeError("offline")
    monkeypatch.setattr(api.requests, "get", _boom)
    resp = client.get("/health")
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["status"] == "ok"
    assert body["outbound_ip"] == "unknown"


def test_login_get_serves_page(client):
    resp = client.get("/login")
    assert resp.status_code == 200
    assert b"<" in resp.data  # served HTML, not a redirect


def test_portal_requires_auth_redirects(client):
    resp = client.get("/portal")
    assert resp.status_code == 302
    assert "/login" in resp.headers["Location"]


def test_api_requires_auth_returns_401(client):
    resp = client.get("/api/config")
    assert resp.status_code == 401
    assert resp.get_json()["error"] == "not authenticated"


def test_config_after_login(auth_client):
    resp = auth_client.get("/api/config")
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["company_name"] == "Acme Corp"
    assert body["username"] == "Jane Lead"
