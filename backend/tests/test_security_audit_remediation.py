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


def test_unauthenticated_approvals_return_401(monkeypatch):
    """Verify unauthenticated access to /api/approvals returns 401."""
    monkeypatch.setattr(settings, "APP_ENV", "production")
    res = client.get("/api/approvals")
    assert res.status_code == 401


def test_user_cannot_access_or_resolve_another_users_approval():
    """Verify users cannot view or resolve approvals belonging to other users."""
    from backend.app.cascade.orchestrator import cascade_orchestrator
    import uuid

    appr_id = f"appr_test_{uuid.uuid4().hex[:8]}"
    cascade_orchestrator.repo.approvals_store[appr_id] = {
        "approval_id": appr_id,
        "user_id": "alice_user",
        "action_type": "send_email",
        "status": "pending",
        "created_at": 1000.0,
        "expires_at": 9999999999.0
    }

    # 1. Bob attempts to list Alice's approvals -> 403 Forbidden
    res_list = client.get(
        "/api/approvals?user_id=alice_user",
        headers={"x-user-id": "bob_attacker"}
    )
    assert res_list.status_code == 403

    # 2. Bob attempts to resolve Alice's approval -> 403 Forbidden
    res_resolve = client.post(
        f"/api/approvals/{appr_id}/resolve",
        json={"decision": "approve"},
        headers={"x-user-id": "bob_attacker"}
    )
    assert res_resolve.status_code == 403

    # 3. Alice accesses her own approvals -> 200 OK
    res_alice = client.get(
        "/api/approvals",
        headers={"x-user-id": "alice_user"}
    )
    assert res_alice.status_code == 200
    approval_ids = [a["approval_id"] for a in res_alice.json()]
    assert appr_id in approval_ids


def test_unauthenticated_audit_logs_return_401(monkeypatch):
    """Verify unauthenticated access to /api/audit-logs returns 401 in production."""
    monkeypatch.setattr(settings, "APP_ENV", "production")
    res = client.get("/api/audit-logs")
    assert res.status_code == 401


def test_user_cannot_access_another_users_audit_logs():
    """Verify users cannot request another user's audit logs."""
    # Bob attempts to request Alice's audit logs -> 403 Forbidden
    res = client.get(
        "/api/audit-logs?user_id=alice_user",
        headers={"x-user-id": "bob_attacker"}
    )
    assert res.status_code == 403

    # Alice requests her own audit logs -> 200 OK
    res_alice = client.get(
        "/api/audit-logs?user_id=alice_user",
        headers={"x-user-id": "alice_user"}
    )
    assert res_alice.status_code == 200


def test_oauth_csrf_protection_and_state_lifecycle(monkeypatch):
    """Verify OAuth state generation, one-time consumption, and rejection of invalid/reused tokens."""
    from backend.app.security.oauth import oauth_state_store

    user_id = "test_oauth_user_123"

    # 1. State token is random and non-trivial (not equal to raw user_id)
    token = oauth_state_store.create_state(user_id=user_id)
    assert token != user_id
    assert len(token) >= 32

    # 2. First consumption succeeds and returns the bound user
    consumed_user = oauth_state_store.validate_and_consume(token)
    assert consumed_user == user_id

    # 3. Second consumption of same token fails (one-time-use / replay protection)
    reused_user = oauth_state_store.validate_and_consume(token)
    assert reused_user is None

    # 4. Unknown/tampered state returns None
    assert oauth_state_store.validate_and_consume("tampered_state_token") is None

    # 5. In production, callback rejects unseeded state with 400 Bad Request
    monkeypatch.setattr(settings, "APP_ENV", "production")
    res_bad = client.get("/api/auth/google/callback?code=fake_code&state=forged_state")
    assert res_bad.status_code == 400
    assert "Invalid, expired, or reused" in res_bad.json()["detail"]
