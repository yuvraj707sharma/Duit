"""Tests for Phase 6: Google OAuth 2.0 & Capability Token Model with Multi-Tenant State Binding and Cryptographic Revocation."""
import pytest
from httpx import AsyncClient, ASGITransport

from backend.app.main import app
from backend.app.db.repository import DatabaseRepository
from backend.app.security.oauth import oauth_state_store
from backend.app.security.crypto import encrypt_token, decrypt_token


@pytest.fixture
def test_repo():
    return DatabaseRepository()


@pytest.mark.asyncio
async def test_oauth_state_store_multi_tenant_binding():
    """OAuth state store must bind user_id, tenant_id, and scopes, and enforce one-time consumption."""
    state = oauth_state_store.create_state(
        user_id="user_alpha_123",
        tenant_id="tenant_alpha_456",
        scopes=["calendar.readonly", "gmail.readonly"]
    )
    assert len(state) > 16

    # 1. First consumption succeeds
    payload = oauth_state_store.validate_and_consume_payload(state)
    assert payload is not None
    assert payload["user_id"] == "user_alpha_123"
    assert payload["tenant_id"] == "tenant_alpha_456"
    assert "calendar.readonly" in payload["scopes"]

    # 2. Second consumption fails (CSRF / replay protection)
    reused = oauth_state_store.validate_and_consume_payload(state)
    assert reused is None


@pytest.mark.asyncio
async def test_token_encryption_and_decryption_integrity():
    """OAuth access and refresh tokens must never be stored plaintext and must be AES-256-GCM encrypted."""
    raw_token = "ya29.a0AfH6SMD_secret_google_oauth_token_123456789"
    user_id = "user_secure_999"

    encrypted = encrypt_token(raw_token, user_id=user_id)
    assert encrypted != raw_token
    assert raw_token not in encrypted
    assert ":" in encrypted  # iv:ciphertext:tag format

    decrypted = decrypt_token(encrypted, user_id=user_id)
    assert decrypted == raw_token

    # Cross-user AAD tampering check
    with pytest.raises(Exception):
        decrypt_token(encrypted, user_id="different_user_attacker")


@pytest.mark.asyncio
async def test_oauth_linking_revocation_and_capability_lifecycle(test_repo):
    """Verifies token save, capability status check, and cryptographic revocation."""
    tenant = await test_repo.create_tenant(name="OAuth Lifecycle Tenant")
    t_id = tenant["id"]
    user = await test_repo.register_user(
        tenant_id=t_id,
        phone_number="+15557776666",
        full_name="OAuth User"
    )
    u_id = user["id"]

    # 1. Save tokens
    enc_access = encrypt_token("access_tok_111", user_id=u_id)
    enc_refresh = encrypt_token("refresh_tok_222", user_id=u_id)
    scopes = ["calendar.read", "calendar.write", "gmail.read", "gmail.send"]

    await test_repo.save_user_oauth_tokens(
        user_id=u_id,
        provider="google",
        encrypted_access_token=enc_access,
        encrypted_refresh_token=enc_refresh,
        tenant_id=t_id,
        scopes=scopes
    )

    # Verify active connection and scopes
    conn = await test_repo.get_user_oauth_connection(user_id=u_id, provider="google", tenant_id=t_id)
    assert conn is not None
    assert conn["status"] == "active"
    assert "calendar.write" in conn["scopes"]

    # Verify tokens stored
    toks = await test_repo.get_user_oauth_tokens(user_id=u_id, provider="google")
    assert toks is not None
    assert toks["encrypted_access_token"] == enc_access

    # 2. Revoke OAuth tokens
    revoked = await test_repo.revoke_user_oauth_tokens(user_id=u_id, provider="google", tenant_id=t_id)
    assert revoked is True

    # Tokens must be deleted
    after_toks = await test_repo.get_user_oauth_tokens(user_id=u_id, provider="google")
    assert after_toks is None

    # Connection status must reflect revoked
    after_conn = await test_repo.get_user_oauth_connection(user_id=u_id, provider="google", tenant_id=t_id)
    assert after_conn is None or after_conn.get("status") == "revoked"


@pytest.mark.asyncio
async def test_oauth_fastapi_endpoints():
    """Verifies /api/auth/google/initiate, /tokens/status, and /google/revoke HTTP endpoints."""
    from backend.app.db.repository import repository
    tenant = await repository.create_tenant(name="API OAuth Tenant")
    user = await repository.register_user(
        tenant_id=tenant["id"],
        phone_number="+15551112233",
        full_name="Endpoint Test User"
    )
    t_id = tenant["id"]
    u_id = user["id"]

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # 1. Initiate OAuth
        init_res = await client.post("/api/auth/google/initiate", json={
            "tenant_id": t_id,
            "user_id": u_id,
            "scopes": ["calendar.read", "gmail.read"]
        })
        assert init_res.status_code == 200
        init_data = init_res.json()
        assert init_data["status"] == "initiated"
        assert "accounts.google.com" in init_data["auth_url"]
        state = init_data["state"]

        # 2. Mock callback with valid state
        cb_res = await client.get(f"/api/auth/google/callback?code=mock_auth_code_123&state={state}")
        assert cb_res.status_code == 200
        assert cb_res.json()["status"] == "success"

        # 3. Check capability status
        status_res = await client.get(f"/api/auth/tokens/status?user_id={u_id}&tenant_id={t_id}")
        assert status_res.status_code == 200
        status_data = status_res.json()
        assert status_data["connected"] is True
        assert status_data["provider"] == "google"

        # 4. Revoke OAuth connection
        revoke_res = await client.post("/api/auth/google/revoke", json={
            "tenant_id": t_id,
            "user_id": u_id
        })
        assert revoke_res.status_code == 200
        assert revoke_res.json()["status"] == "revoked"

        # 5. Check status after revocation
        post_revoke_status = await client.get(f"/api/auth/tokens/status?user_id={u_id}&tenant_id={t_id}")
        assert post_revoke_status.status_code == 200
        assert post_revoke_status.json()["connected"] is False
        assert post_revoke_status.json()["scopes"] == []

        # 6. Replay attack with consumed state rejected
        replay_res = await client.get(f"/api/auth/google/callback?code=replay_code&state={state}")
        assert replay_res.status_code == 400

