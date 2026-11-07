"""Tests for Phase 5: Desktop Agent Pairing, Local Policy Engine, Encrypted Journal, and Kill Switch."""
import pytest
import time
from httpx import AsyncClient, ASGITransport

from backend.app.main import app
from backend.app.db.repository import DatabaseRepository
from backend.app.desktop.policy import DesktopPolicyEngine
from backend.app.security.context import SecurityContextError


@pytest.fixture
def test_repo():
    return DatabaseRepository()


@pytest.fixture
def policy_engine():
    return DesktopPolicyEngine()


@pytest.mark.asyncio
async def test_desktop_pairing_handshake_and_replay_protection(test_repo):
    """Verifies pairing session creation, mutual code/nonce claim, and replay rejection."""
    tenant = await test_repo.create_tenant(name="Desktop Tenant")
    user = await test_repo.register_user(
        tenant_id=tenant["id"],
        phone_number="+15553334444",
        full_name="Desktop User"
    )

    # 1. Initiate pairing
    session = await test_repo.create_desktop_pairing_session(
        tenant_id=tenant["id"],
        user_id=user["id"],
        ttl_seconds=300
    )
    assert session["status"] == "pending"
    assert session["pairing_code"].startswith("DK-")
    assert len(session["nonce"]) == 32

    # 2. Claim pairing
    claim_res = await test_repo.claim_desktop_pairing(
        pairing_code=session["pairing_code"],
        nonce=session["nonce"],
        device_name="Yuvraj-Workstation",
        platform="windows"
    )
    assert claim_res["status"] == "claimed"
    assert claim_res["device_token"].startswith("dtoken_")
    device_id = claim_res["device"]["id"]
    assert device_id is not None

    # 3. Replay attack rejection
    with pytest.raises(SecurityContextError, match="already claimed"):
        await test_repo.claim_desktop_pairing(
            pairing_code=session["pairing_code"],
            nonce=session["nonce"],
            device_name="Attacker-Machine",
            platform="windows"
        )


@pytest.mark.asyncio
async def test_desktop_pairing_expiration(test_repo):
    """Expired pairing session cannot be claimed."""
    tenant = await test_repo.create_tenant(name="Exp Tenant")
    user = await test_repo.register_user(tenant_id=tenant["id"], phone_number="+15558889999")

    # Session with 0 TTL (already expired)
    session = await test_repo.create_desktop_pairing_session(
        tenant_id=tenant["id"],
        user_id=user["id"],
        ttl_seconds=-1
    )

    with pytest.raises(SecurityContextError, match="expired"):
        await test_repo.claim_desktop_pairing(
            pairing_code=session["pairing_code"],
            nonce=session["nonce"],
            device_name="Expired-Box"
        )


@pytest.mark.asyncio
async def test_local_policy_engine_restrictions(policy_engine):
    """Desktop policy engine must strictly block prohibited actions, sensitive paths, and destructive commands."""
    # 1. Permitted safe actions
    allowed, reason = policy_engine.evaluate_local_action("open_app", {"app_name": "notepad"})
    assert allowed is True
    assert reason is None

    allowed, reason = policy_engine.evaluate_local_action("search_files", {"query": "project report"})
    assert allowed is True

    # 2. Block prohibited actions
    prohibited_actions = ["format_disk", "arbitrary_shell_exec", "extract_passwords", "dump_lsass"]
    for act in prohibited_actions:
        allowed, reason = policy_engine.evaluate_local_action(act, {})
        assert allowed is False
        assert "prohibited" in reason.lower()

    # 3. Block sensitive paths in arguments
    sensitive_path_tests = [
        {"path": "C:\\Users\\Hp\\.ssh\\id_rsa"},
        {"file": "/home/user/.aws/credentials"},
        {"config": "C:\\Users\\Hp\\AppData\\Local\\Google\\Chrome\\User Data\\Default"},
        {"env_file": ".env"},
        {"key": "id_ed25519"},
    ]
    for args in sensitive_path_tests:
        allowed, reason = policy_engine.evaluate_local_action("search_files", args)
        assert allowed is False
        assert "blocked by desktop policy" in reason

    # 4. Block destructive command strings
    destructive_tests = [
        {"cmd": "rm -rf /"},
        {"cmd": "del /f /s /q C:\\"},
        {"cmd": "format c:"},
    ]
    for args in destructive_tests:
        allowed, reason = policy_engine.evaluate_local_action("type_text", args)
        assert allowed is False
        assert "blocked by desktop policy" in reason


@pytest.mark.asyncio
async def test_emergency_kill_switch(test_repo):
    """Emergency kill switch must immediately revoke credentials and disconnect device."""
    tenant = await test_repo.create_tenant(name="Kill Tenant")
    user = await test_repo.register_user(tenant_id=tenant["id"], phone_number="+15554443333")
    device = await test_repo.register_desktop_device(
        tenant_id=tenant["id"],
        user_id=user["id"],
        device_name="Target-Device"
    )
    did = device["id"]
    assert device["is_online"] is True

    kill_res = await test_repo.kill_desktop_device(
        device_id=did,
        reason="Security alert triggered by director",
        tenant_id=tenant["id"]
    )
    assert kill_res["status"] == "killed"
    assert kill_res["device_id"] == did

    # Device record must reflect revoked state
    dev_after = await test_repo.get_desktop_device(did, tenant_id=tenant["id"])
    assert dev_after["is_online"] is False
    assert dev_after["revoked_at"] is not None


@pytest.mark.asyncio
async def test_tamper_evident_journal_signing(test_repo, policy_engine):
    """Journal entries must be signed with HMAC-SHA256 and verifiable."""
    tenant = await test_repo.create_tenant(name="Journal Tenant")
    t_id = tenant["id"]
    device_id = "device_test_123"
    secret = "hmac_device_secret_key_999"

    action = "open_app"
    args = {"app": "calculator"}
    args_hash = policy_engine.hash_arguments(args)

    sig = policy_engine.sign_journal_entry(
        device_id=device_id,
        action=action,
        arguments_hash=args_hash,
        secret_key=secret
    )
    assert len(sig) == 64

    # Verify signature
    assert policy_engine.verify_journal_entry(device_id, action, args_hash, sig, secret) is True

    # Tampered arguments hash should fail verification
    assert policy_engine.verify_journal_entry(device_id, action, "tampered_hash", sig, secret) is False

    # Append to repository journal
    entry = await test_repo.append_journal_entry(
        tenant_id=t_id,
        device_id=device_id,
        action=action,
        arguments_hash=args_hash,
        status="executed",
        signature=sig
    )
    assert entry["id"] is not None
    assert entry["action"] == action

    # Retrieve entries
    history = await test_repo.get_journal_entries(device_id=device_id, tenant_id=t_id)
    assert len(history) == 1
    assert history[0]["signature"] == sig


@pytest.mark.asyncio
async def test_desktop_fastapi_endpoints():
    """Verifies HTTP endpoints for desktop pairing, kill switch, and journal."""
    from backend.app.db.repository import repository
    tenant = await repository.create_tenant(name="API Desktop Tenant")
    user = await repository.register_user(tenant_id=tenant["id"], phone_number="+15556665555")
    t_id = tenant["id"]
    u_id = user["id"]

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # 1. Initiate pairing
        init_res = await client.post("/api/desktop/pair/initiate", json={
            "tenant_id": t_id,
            "user_id": u_id,
            "ttl_seconds": 600
        })
        assert init_res.status_code == 201
        init_data = init_res.json()
        code = init_data["pairing_code"]
        nonce = init_data["nonce"]

        # 2. Claim pairing
        claim_res = await client.post("/api/desktop/pair/claim", json={
            "pairing_code": code,
            "nonce": nonce,
            "device_name": "API-Laptop",
            "platform": "windows"
        })
        assert claim_res.status_code == 200
        claim_data = claim_res.json()
        did = claim_data["device"]["id"]
        assert claim_data["device_token"].startswith("dtoken_")

        # 3. Post to journal
        j_res = await client.post("/api/desktop/journal", json={
            "device_id": did,
            "tenant_id": t_id,
            "action": "open_app",
            "arguments": {"app": "terminal"},
            "status": "executed",
            "signature": "fake_signed_hmac_hex"
        })
        assert j_res.status_code == 200
        assert j_res.json()["status"] == "success"

        # 4. Read journal
        read_res = await client.get(f"/api/desktop/journal/{did}")
        assert read_res.status_code == 200
        assert read_res.json()["count"] >= 1

        # 5. Emergency kill switch
        kill_res = await client.post("/api/desktop/kill", json={
            "device_id": did,
            "reason": "Test kill trigger"
        })
        assert kill_res.status_code == 200
        assert kill_res.json()["status"] == "killed"

