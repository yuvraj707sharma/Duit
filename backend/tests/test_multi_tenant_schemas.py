"""Comprehensive tests for Phase 1 Multi-Tenant Identity and Account Model.
Verifies:
1. Tenant isolation and scoping
2. User binding to Tenant
3. WhatsAppAccount linking & tenant boundaries
4. DesktopDevice binding and execution security
5. Execution lifecycle and verification tracking
6. WhatsApp Message archive isolation (User A cannot read User B's chats)
7. SecurityContext server-verified identity enforcement
8. Database table creation and schema integrity
"""
import pytest
import uuid
import time
from datetime import datetime, timezone
from sqlalchemy.ext.asyncio import create_async_engine
from backend.app.db.database import Base
from backend.app.db.repository import DatabaseRepository
from backend.app.security.context import SecurityContext, SecurityContextError


@pytest.fixture
def repo():
    return DatabaseRepository()


@pytest.mark.asyncio
async def test_schema_table_creation():
    """Verify all SQLAlchemy multi-tenant tables compile and create cleanly in an async relational database."""
    test_engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    await test_engine.dispose()
    assert True


@pytest.mark.asyncio
async def test_tenant_creation_and_scoping(repo):
    """Test tenant registration, slug generation, and retrieval."""
    tenant = await repo.create_tenant(name="Acme Corp", slug="acme")
    assert tenant["id"] is not None
    assert tenant["name"] == "Acme Corp"
    assert tenant["slug"] == "acme"

    fetched = await repo.get_tenant(tenant["id"])
    assert fetched is not None
    assert fetched["id"] == tenant["id"]

    non_existent = await repo.get_tenant("non_existent_tenant_xyz")
    assert non_existent is None


@pytest.mark.asyncio
async def test_user_tenant_binding_and_isolation(repo):
    """Test user registration is strictly bound to their tenant."""
    tenant_a = await repo.create_tenant(name="Tenant Alpha")
    tenant_b = await repo.create_tenant(name="Tenant Beta")

    user_a = await repo.register_user(
        tenant_id=tenant_a["id"],
        email="alice@alpha.com",
        phone_number="919111111111",
        full_name="Alice Alpha"
    )
    user_b = await repo.register_user(
        tenant_id=tenant_b["id"],
        email="bob@beta.com",
        phone_number="919222222222",
        full_name="Bob Beta"
    )

    # Scoped retrieval: Alice found under Tenant A, but None under Tenant B
    assert await repo.get_user(user_a["id"], tenant_id=tenant_a["id"]) is not None
    assert await repo.get_user(user_a["id"], tenant_id=tenant_b["id"]) is None

    # Bob found under Tenant B, but None under Tenant A
    assert await repo.get_user(user_b["id"], tenant_id=tenant_b["id"]) is not None
    assert await repo.get_user(user_b["id"], tenant_id=tenant_a["id"]) is None


@pytest.mark.asyncio
async def test_whatsapp_account_linking_boundaries(repo):
    """Test WhatsApp account linking prevents cross-tenant association."""
    tenant_a = await repo.create_tenant(name="Org A")
    tenant_b = await repo.create_tenant(name="Org B")

    user_a = await repo.register_user(tenant_id=tenant_a["id"], email="userA@org.com")

    # Success: User A in Tenant A
    account_a = await repo.link_whatsapp_account(
        tenant_id=tenant_a["id"],
        user_id=user_a["id"],
        phone_number="919876543210",
        display_name="Org A Bot"
    )
    assert account_a["id"] is not None
    assert account_a["phone_number"] == "919876543210"

    # Cross-tenant attack: Trying to link account for User A under Tenant B must fail
    with pytest.raises(SecurityContextError):
        await repo.link_whatsapp_account(
            tenant_id=tenant_b["id"],
            user_id=user_a["id"],
            phone_number="919876543210"
        )


@pytest.mark.asyncio
async def test_desktop_device_registration_and_execution(repo):
    """Test desktop device registration and authorized capability execution."""
    tenant = await repo.create_tenant(name="TechCorp")
    user = await repo.register_user(tenant_id=tenant["id"], email="dev@techcorp.com")

    # Register device
    device = await repo.register_desktop_device(
        tenant_id=tenant["id"],
        user_id=user["id"],
        device_name="Workstation-1",
        platform="windows",
        permissions=["desktop.app.launch", "desktop.ui.snapshot"]
    )
    assert device["id"] is not None
    assert device["is_online"] is True

    # Record execution on user's authorized device
    exec_rec = await repo.record_execution(
        tenant_id=tenant["id"],
        user_id=user["id"],
        device_id=device["id"],
        capability="desktop.app.launch",
        arguments={"app": "notepad.exe"},
        risk_level="low"
    )
    assert exec_rec["status"] == "pending"
    assert exec_rec["verified"] is False

    # Complete execution with verified output
    completed = await repo.complete_execution(
        execution_id=exec_rec["id"],
        status="completed",
        verified=True,
        output={"pid": 1234, "window_title": "Untitled - Notepad"},
        tenant_id=tenant["id"]
    )
    assert completed["status"] == "completed"
    assert completed["verified"] is True
    assert completed["output"]["pid"] == 1234


@pytest.mark.asyncio
async def test_cross_user_device_execution_blocked(repo):
    """Test that User B cannot trigger execution on User A's desktop device."""
    tenant = await repo.create_tenant(name="Shared Tenant")
    user_a = await repo.register_user(tenant_id=tenant["id"], email="usera@corp.com")
    user_b = await repo.register_user(tenant_id=tenant["id"], email="userb@corp.com")

    device_a = await repo.register_desktop_device(
        tenant_id=tenant["id"],
        user_id=user_a["id"],
        device_name="Alice-Laptop"
    )

    # User B attempting to execute on Alice's device must be rejected
    with pytest.raises(SecurityContextError) as exc_info:
        await repo.record_execution(
            tenant_id=tenant["id"],
            user_id=user_b["id"],
            device_id=device_a["id"],
            capability="desktop.app.launch",
            arguments={"app": "cmd.exe"}
        )
    assert "does not belong to user" in str(exc_info.value)


@pytest.mark.asyncio
async def test_message_archive_isolation(repo):
    """Test that archived messages are strictly isolated per WhatsApp account and tenant."""
    tenant_a = await repo.create_tenant(name="Tenant Alpha")
    tenant_b = await repo.create_tenant(name="Tenant Beta")

    user_a = await repo.register_user(tenant_id=tenant_a["id"], email="a@alpha.com")
    user_b = await repo.register_user(tenant_id=tenant_b["id"], email="b@beta.com")

    wa_a = await repo.link_whatsapp_account(tenant_a["id"], user_a["id"], "919000000001")
    wa_b = await repo.link_whatsapp_account(tenant_b["id"], user_b["id"], "919000000002")

    # Archive confidential message for Account A
    await repo.archive_message(
        tenant_id=tenant_a["id"],
        whatsapp_account_id=wa_a["id"],
        provider_message_id="msg_alpha_secret_1",
        sender_jid="919999999999@s.whatsapp.net",
        text="Confidential M&A discussion notes for Alpha",
        sender_phone="919999999999"
    )

    # Archive message for Account B
    await repo.archive_message(
        tenant_id=tenant_b["id"],
        whatsapp_account_id=wa_b["id"],
        provider_message_id="msg_beta_1",
        sender_jid="919888888888@s.whatsapp.net",
        text="Beta daily standup notes",
        sender_phone="919888888888"
    )

    # Search in Account A sees Alpha notes
    results_a = await repo.search_messages(
        tenant_id=tenant_a["id"],
        whatsapp_account_id=wa_a["id"],
        query_text="Confidential"
    )
    assert len(results_a) == 1
    assert "Confidential M&A" in results_a[0]["text"]

    # Search in Account B cannot find Alpha's notes
    results_b = await repo.search_messages(
        tenant_id=tenant_b["id"],
        whatsapp_account_id=wa_b["id"],
        query_text="Confidential"
    )
    assert len(results_b) == 0

    # Cross-tenant archive query is empty
    cross_search = await repo.search_messages(
        tenant_id=tenant_b["id"],
        whatsapp_account_id=wa_a["id"],
        query_text="Confidential"
    )
    assert len(cross_search) == 0


@pytest.mark.asyncio
async def test_server_verified_security_context(repo):
    """Test SecurityContext validation enforces full identity graph verification."""
    tenant = await repo.create_tenant(name="Security Org")
    user = await repo.register_user(tenant_id=tenant["id"], email="officer@sec.org")
    account = await repo.link_whatsapp_account(tenant["id"], user["id"], "919333333333")
    device = await repo.register_desktop_device(tenant["id"], user["id"], "Sec-Station")

    # 1. Valid security context
    valid_ctx = SecurityContext(
        tenant_id=tenant["id"],
        user_id=user["id"],
        account_id=account["id"],
        device_id=device["id"]
    )
    assert await repo.verify_security_context(valid_ctx) is True

    # 2. Invalid tenant ID
    bad_tenant_ctx = SecurityContext(
        tenant_id="fake_tenant_id",
        user_id=user["id"]
    )
    with pytest.raises(SecurityContextError):
        await repo.verify_security_context(bad_tenant_ctx)

    # 3. Mismatched user in tenant
    bad_user_ctx = SecurityContext(
        tenant_id=tenant["id"],
        user_id="fake_user_id"
    )
    with pytest.raises(SecurityContextError):
        await repo.verify_security_context(bad_user_ctx)

    # 4. Another user's account in context
    other_user = await repo.register_user(tenant_id=tenant["id"], email="other@sec.org")
    mismatched_acc_ctx = SecurityContext(
        tenant_id=tenant["id"],
        user_id=other_user["id"],
        account_id=account["id"]
    )
    with pytest.raises(SecurityContextError):
        await repo.verify_security_context(mismatched_acc_ctx)
