"""Auth / lead-capture behavior.

This app intentionally has NO real authentication — the name + company form is a
lead-capture gate, by design. These tests pin that behavior AND verify the
removed token backdoor stays removed.
"""


def test_lead_capture_login_redirects_to_portal(client):
    resp = client.post("/login", data={"username": "Jane", "password": "Acme Corp"})
    assert resp.status_code == 302
    assert "/portal" in resp.headers["Location"]


def test_login_missing_fields_unauthorized(client):
    resp = client.post("/login", data={"username": "", "password": ""})
    assert resp.status_code == 401


def test_query_param_auto_auth(client):
    # Portal launch / QR-code path: auto_user + auto_company pre-authenticates.
    resp = client.get("/portal?auto_user=Bob&auto_company=Globex")
    assert resp.status_code == 200


def test_auto_token_backdoor_removed(client, monkeypatch):
    # Even with a real DATABRICKS_TOKEN present, ?auto_token must NOT authenticate
    # (the PAT-in-URL backdoor was removed).
    monkeypatch.setenv("DATABRICKS_TOKEN", "super-secret-pat")
    resp = client.get("/portal?auto_token=super-secret-pat")
    assert resp.status_code == 302
    assert "/login" in resp.headers["Location"]


def test_mobile_auto_auth_demo(client):
    # Mobile SPA auto-authenticates for QR-code demos (intentional).
    resp = client.get("/mobile")
    assert resp.status_code == 200


def test_logout_clears_session(auth_client):
    resp = auth_client.get("/logout")
    assert resp.status_code == 302
    # subsequent protected call is unauthenticated again
    follow = auth_client.get("/api/config")
    assert follow.status_code == 401
