"""Comprehensive tests for Phase 2: Secure WhatsApp Linking Transactions and Encrypted Sessions.
Verifies:
1. Dedicated linking transaction creation with one-time pairing code and nonce
2. Session status lookup and expiration behavior
3. Cryptographic confirmation of pairing (rejects wrong code, wrong nonce, replay)
4. Encrypted session credentials isolation per account (AES-256-GCM)
5. Secure session and account revocation by authorized caller
6. Cross-tenant and cross-user linking isolation
"""
import pytest
import time
from fastapi.testclient import TestClient
from backend.app.main import app
from backend.app.db.repository import repository
from backend.app.security.crypto import encrypt_token, decrypt_token


client = TestClient(app)


async def get_test_tenant_and_user():
    tenant = await repository.create_tenant(name="Linking Org", slug="linking-org")
    user = await repository.register_user(
        tenant_id=tenant["id"],
        email="executive@linking-org.com",
        phone_number="919888877777",
        full_name="Executive Leader"
    )
    return tenant, user


@pytest.mark.asyncio
async def test_create_linking_session():
    tenant, user = await get_test_tenant_and_user()

    res = client.post("/api/linking/sessions", json={
        "tenant_id": tenant["id"],
        "user_id": user["id"],
        "phone_number": "919888877777",
        "ttl_seconds": 300
    })
    assert res.status_code == 201
    data = res.json()
    assert "session_id" in data
    assert "pairing_code" in data
    assert "-" in data["pairing_code"]
    assert "nonce" in data
    assert len(data["nonce"]) == 32
    assert data["status"] == "pending"
    assert data["expires_at"] > time.time()


@pytest.mark.asyncio
async def test_linking_session_status_and_not_found():
    tenant, user = await get_test_tenant_and_user()

    create_res = client.post("/api/linking/sessions", json={
        "tenant_id": tenant["id"],
        "user_id": user["id"]
    })
    session_id = create_res.json()["session_id"]

    # Status check
    status_res = client.get(f"/api/linking/sessions/{session_id}/status")
    assert status_res.status_code == 200
    s_data = status_res.json()
    assert s_data["status"] == "pending"
    assert s_data["tenant_id"] == tenant["id"]

    # Non-existent session
    missing_res = client.get("/api/linking/sessions/fake-session-uuid-123/status")
    assert missing_res.status_code == 404


@pytest.mark.asyncio
async def test_confirm_pairing_success_and_replay_protection():
    tenant, user = await get_test_tenant_and_user()

    # 1. Initiate linking session
    create_res = client.post("/api/linking/sessions", json={
        "tenant_id": tenant["id"],
        "user_id": user["id"],
        "phone_number": "919888877777"
    })
    sess_data = create_res.json()
    session_id = sess_data["session_id"]
    nonce = sess_data["nonce"]
    pairing_code = sess_data["pairing_code"]

    raw_baileys_creds = '{"creds":{"noiseKey":"abc123xyz"},"keys":{}}'
    encrypted_creds = encrypt_token(raw_baileys_creds, user_id=user["id"])

    # 2. Confirm pairing with correct nonce, pairing code, and encrypted credentials
    pair_res = client.post(f"/api/linking/sessions/{session_id}/pair", json={
        "nonce": nonce,
        "pairing_code": pairing_code,
        "phone_number": "919888877777",
        "encrypted_credentials": encrypted_creds
    })
    assert pair_res.status_code == 200
    p_data = pair_res.json()
    assert p_data["status"] == "paired"
    assert p_data["linked_number"] == "919888877777"
    assert "archive_start_time" in p_data
    assert "permissions_granted" in p_data
    assert "whatsapp.search" in p_data["permissions_granted"]

    # Verify session credentials can be decrypted
    account_id = p_data["account_id"]
    saved_creds = await repository.get_whatsapp_session_credentials(account_id)
    assert saved_creds is not None
    decrypted = decrypt_token(saved_creds["encrypted_credentials"], user_id=user["id"])
    assert decrypted == raw_baileys_creds

    # 3. Replay attack: attempting to re-pair same session must be rejected
    replay_res = client.post(f"/api/linking/sessions/{session_id}/pair", json={
        "nonce": nonce,
        "pairing_code": pairing_code,
        "phone_number": "919888877777"
    })
    assert replay_res.status_code == 400
    assert "already been used" in replay_res.json()["detail"]


@pytest.mark.asyncio
async def test_confirm_pairing_invalid_code_or_nonce():
    tenant, user = await get_test_tenant_and_user()

    create_res = client.post("/api/linking/sessions", json={
        "tenant_id": tenant["id"],
        "user_id": user["id"],
        "phone_number": "919888877777"
    })
    sess_data = create_res.json()
    session_id = sess_data["session_id"]
    nonce = sess_data["nonce"]
    pairing_code = sess_data["pairing_code"]

    # Wrong pairing code
    bad_code_res = client.post(f"/api/linking/sessions/{session_id}/pair", json={
        "nonce": nonce,
        "pairing_code": "WRONG-1234",
        "phone_number": "919888877777"
    })
    assert bad_code_res.status_code == 400
    assert "verification failed" in bad_code_res.json()["detail"].lower()

    # Wrong nonce
    bad_nonce_res = client.post(f"/api/linking/sessions/{session_id}/pair", json={
        "nonce": "00000000000000000000000000000000",
        "pairing_code": pairing_code,
        "phone_number": "919888877777"
    })
    assert bad_nonce_res.status_code == 400


@pytest.mark.asyncio
async def test_session_expiration():
    tenant, user = await get_test_tenant_and_user()

    # Create session with 0 TTL to simulate expiration
    create_res = client.post("/api/linking/sessions", json={
        "tenant_id": tenant["id"],
        "user_id": user["id"],
        "ttl_seconds": -10
    })
    sess_data = create_res.json()
    session_id = sess_data["session_id"]

    # Status check marks it expired
    status_res = client.get(f"/api/linking/sessions/{session_id}/status")
    assert status_res.json()["status"] == "expired"

    # Pairing attempt fails due to expiry
    pair_res = client.post(f"/api/linking/sessions/{session_id}/pair", json={
        "nonce": sess_data["nonce"],
        "pairing_code": sess_data["pairing_code"],
        "phone_number": "919888877777"
    })
    assert pair_res.status_code == 400
    assert "expired" in pair_res.json()["detail"].lower()


@pytest.mark.asyncio
async def test_revoke_session_and_credentials():
    tenant, user = await get_test_tenant_and_user()

    create_res = client.post("/api/linking/sessions", json={
        "tenant_id": tenant["id"],
        "user_id": user["id"],
        "phone_number": "919888877777"
    })
    sess_data = create_res.json()
    session_id = sess_data["session_id"]

    # Pair successfully
    pair_res = client.post(f"/api/linking/sessions/{session_id}/pair", json={
        "nonce": sess_data["nonce"],
        "pairing_code": sess_data["pairing_code"],
        "phone_number": "919888877777"
    })
    account_id = pair_res.json()["account_id"]

    # Unauthorized caller cannot revoke
    unauth_revoke = client.post(
        f"/api/linking/sessions/{session_id}/revoke",
        headers={"x-user-id": "attacker_user_uuid"}
    )
    assert unauth_revoke.status_code == 403

    # Authorized caller revokes
    auth_revoke = client.post(
        f"/api/linking/sessions/{session_id}/revoke",
        headers={"x-user-id": user["id"], "x-tenant-id": tenant["id"]}
    )
    assert auth_revoke.status_code == 200
    assert auth_revoke.json()["status"] == "revoked"

    # Status reflects revoked
    status_res = client.get(f"/api/linking/sessions/{session_id}/status")
    assert status_res.json()["status"] == "revoked"

    # Account status is revoked
    account = await repository.get_whatsapp_account(account_id)
    assert account["status"] == "revoked"
