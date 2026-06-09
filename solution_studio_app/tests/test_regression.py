"""Static regression guards — lock in the release-hardening fixes so they can't
silently regress in future edits."""
from pathlib import Path

APP_DIR = Path(__file__).resolve().parent.parent


def _api_source():
    return (APP_DIR / "api.py").read_text()


def test_no_committed_private_key_in_app_yaml():
    text = (APP_DIR / "app.yaml").read_text()
    assert "PRIVATE KEY" not in text
    assert "BEGIN PRIVATE KEY" not in text


def test_secrets_injected_via_valuefrom():
    text = (APP_DIR / "app.yaml").read_text()
    assert "valueFrom:" in text
    # the four sensitive env vars must be sourced from secrets, not inline values
    for name in ("ANTHROPIC_API_KEY", "GOOGLE_CREDENTIALS_B64", "SECRET_KEY", "FIN_GOOGLE_API_KEY"):
        assert name in text


def test_no_raw_exception_leak_in_source():
    src = _api_source()
    assert 'jsonify({"error": str(e)})' not in src


def test_no_launch_token_leak():
    assert "launch_token" not in _api_source()
    assert "launch_token" not in (APP_DIR / "static" / "portal.html").read_text()


def test_no_predictable_secret_key_fallback():
    assert b"solution-studio-master-2024" not in (APP_DIR / "api.py").read_bytes()


def test_gunicorn_preload_enabled():
    assert "--preload" in (APP_DIR / "app.yaml").read_text()
    assert "--preload" in (APP_DIR / "start.sh").read_text()
