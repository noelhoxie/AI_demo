"""Unit tests for the refactored helpers."""


def test_delta_log_write_uses_bound_parameters(api, monkeypatch):
    captured = {}

    monkeypatch.setattr(api, "_DELTA_LOG_OK", True)

    def fake_exec(statement, parameters=None):
        captured["statement"] = statement
        captured["parameters"] = parameters
        return True

    monkeypatch.setattr(api, "_delta_sql_exec", fake_exec)

    ok = api._delta_log_write(
        "INSERT INTO t (a, b, c) VALUES (%s, %s, %s)",
        ("o'brien; DROP TABLE x", 5, 1.5),
    )

    assert ok is True
    stmt = captured["statement"]
    # placeholders rewritten to named markers; nothing interpolated into SQL text
    assert ":p0" in stmt and ":p1" in stmt and ":p2" in stmt
    assert "%s" not in stmt
    assert "o'brien" not in stmt and "DROP TABLE" not in stmt

    params = {p["name"]: p for p in captured["parameters"]}
    assert params["p0"]["value"] == "o'brien; DROP TABLE x"
    assert params["p0"]["type"] == "STRING"
    assert params["p1"]["type"] == "INT"
    assert params["p2"]["type"] == "DOUBLE"


def test_delta_log_write_noop_when_disabled(api, monkeypatch):
    monkeypatch.setattr(api, "_DELTA_LOG_OK", False)
    assert api._delta_log_write("INSERT ...", ("x",)) is False


def test_workspace_creds_prefers_env_token(api, monkeypatch):
    monkeypatch.setenv("DATABRICKS_HOST", "myhost.cloud.databricks.com")
    monkeypatch.setenv("DATABRICKS_TOKEN", "tok123")
    host, hdrs = api._workspace_creds()
    assert host == "https://myhost.cloud.databricks.com"
    assert hdrs["Authorization"] == "Bearer tok123"
    assert hdrs["Content-Type"] == "application/json"


def test_workspace_creds_normalizes_https(api, monkeypatch):
    monkeypatch.setenv("DATABRICKS_HOST", "https://h.example.com/")
    monkeypatch.setenv("DATABRICKS_TOKEN", "t")
    host, _ = api._workspace_creds()
    assert host == "https://h.example.com"


def test_classify_vertical_energy_keyword(api):
    assert api._classify_vertical("Exxon Mobil Corporation") == "energy"


def test_classify_vertical_default_without_api_key(api, monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "")
    assert api._classify_vertical("Generic Widgets Inc") == "manufacturing"


def test_secret_key_is_not_the_legacy_constant(api):
    import hashlib
    legacy = hashlib.sha256(b"solution-studio-master-2024").hexdigest()
    assert api.app.secret_key
    assert api.app.secret_key != legacy


def test_cookie_hardening(api):
    assert api.app.config["SESSION_COOKIE_HTTPONLY"] is True
    assert api.app.config["SESSION_COOKIE_SAMESITE"] == "Lax"
