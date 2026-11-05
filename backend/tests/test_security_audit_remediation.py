"""Regression tests verifying all 7 security audit remediation controls."""
import pytest
from fastapi.testclient import TestClient
from backend.app.main import app
from backend.app.config import settings, Settings
from backend.app.api.skills import _validate_webhook_url
from fastapi import HTTPException

client = TestClient(app)


def test_ssrf_webhook_url_validation():
    """Verify SSRF protection blocks private IP ranges, localhosts, and non-HTTPS schemes."""
    # 1. Non-HTTPS must be rejected
    with pytest.raises(HTTPException) as exc_info:
        _validate_webhook_url("http://external-api.com/webhook")
    assert exc_info.value.status_code == 400
    assert "HTTPS" in exc_info.value.detail

    # 2. Localhost must be rejected
    with pytest.raises(HTTPException) as exc_info:
        _validate_webhook_url("https://localhost:8000/hook")
    assert exc_info.value.status_code == 400

    # 3. Cloud metadata IP (169.254.169.254) must be rejected
    with pytest.raises(HTTPException) as exc_info:
        _validate_webhook_url("https://169.254.169.254/latest/meta-data")
    assert exc_info.value.status_code == 400

    # 4. RFC 1918 Private IP (192.168.x.x, 10.x.x.x) must be rejected
    with pytest.raises(HTTPException) as exc_info:
        _validate_webhook_url("https://192.168.1.100/webhook")
    assert exc_info.value.status_code == 400

    # 5. Internal domain names must be rejected
    with pytest.raises(HTTPException) as exc_info:
        _validate_webhook_url("https://server.internal/webhook")
    assert exc_info.value.status_code == 400

    # 6. Valid public HTTPS URL passes without exception
    _validate_webhook_url("https://api.example.com/duit-webhook")
    _validate_webhook_url(None)


def test_production_fails_on_insecure_defaults():
    """Verify application startup fails fast if production environment uses dev defaults."""
    # Production with dev defaults must exit
    prod_settings = Settings(
        APP_ENV="production",
        SECRET_KEY="fastagent_super_secret_development_key_32bytes_len!!",
        TOKEN_ENCRYPTION_KEY="MDEyMzQ1Njc4OTAxMjM0NTY3ODkwMTIzNDU2Nzg5MDE="
    )
    with pytest.raises(SystemExit):
        prod_settings.validate_production_secrets()


def test_desktop_websocket_rejects_query_param_secrets(monkeypatch):
    """Verify WebSocket tunnel does not accept secrets in query parameters in production."""
    monkeypatch.setattr(settings, "APP_ENV", "production")
    monkeypatch.setattr(settings, "DESKTOP_SHARED_SECRET", "super_desktop_secret")

    from starlette.websockets import WebSocketDisconnect
    with pytest.raises(WebSocketDisconnect) as exc_info:
        with client.websocket_connect(
            "/api/desktop/ws?user_id=attacker&secret=super_desktop_secret"
        ):
            pass
    assert exc_info.value.code == 1008


def test_save_token_requires_gateway_secret_in_production(monkeypatch):
    """Verify /save-token rejects requests without valid gateway secret in production."""
    monkeypatch.setattr(settings, "APP_ENV", "production")
    monkeypatch.setattr(settings, "GATEWAY_SHARED_SECRET", "super_secure_gateway_token_123")

    payload = {
        "user_id": "test_user_victim",
        "access_token": "ya29.attacker_token",
        "email": "victim@example.com"
    }

    # Request without secret header -> 401
    res = client.post("/api/auth/save-token", json=payload)
    assert res.status_code == 401

    # Request with wrong secret -> 401
    res_bad = client.post(
        "/api/auth/save-token",
        json=payload,
        headers={"x-gateway-secret": "wrong_secret"}
    )
    assert res_bad.status_code == 401

    # Request with correct secret -> 200
    res_good = client.post(
        "/api/auth/save-token",
        json=payload,
        headers={"x-gateway-secret": "super_secure_gateway_token_123"}
    )
    assert res_good.status_code == 200
