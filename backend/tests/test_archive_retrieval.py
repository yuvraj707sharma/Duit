"""Tests for Phase 3: WhatsApp archive retrieval, structured summary with citations, and zero-hallucination absence reporting."""
import pytest
import uuid
from datetime import datetime, timezone, timedelta
from httpx import AsyncClient, ASGITransport

from backend.app.main import app
from backend.app.cascade.decision import MockDecisionModel
from backend.app.db.repository import repository, DatabaseRepository


@pytest.fixture
def test_repo():
    return DatabaseRepository()


@pytest.fixture
def decision_model():
    return MockDecisionModel()


@pytest.mark.asyncio
async def test_decision_model_classifies_whatsapp_search(decision_model):
    """Verifies WhatsApp chat search & summary queries are classified as whatsapp_search, avoiding email summarization."""
    test_queries = [
        ("can you read my whatsapp texts", "whatsapp_search"),
        ("summarize my recent chats", "whatsapp_search"),
        ("summarize my chats please", "whatsapp_search"),
        ("what did John say in recent messages", "whatsapp_search"),
        ("search whatsapp for invoice", "whatsapp_search"),
        ("Rahul ne kya bola recent chats me", "whatsapp_search"),
    ]
    for text, expected_intent in test_queries:
        out = await decision_model.decide(text)
        assert out.intent == expected_intent, f"Failed for '{text}': got {out.intent}"
        assert out.risk == "low"
        assert out.needs_confirmation is False


@pytest.mark.asyncio
async def test_truthful_empty_archive_response(orchestrator):
    """DUIT must truthfully report 0 messages found when archive is empty, and NEVER prompt for Google OAuth."""
    tenant = await orchestrator.repo.create_tenant(name="Acme Corp")
    user = await orchestrator.repo.register_user(
        tenant_id=tenant["id"],
        phone_number="+15550001111",
        full_name="Alice Smith"
    )
    # Ensure WhatsApp account is linked
    account = await orchestrator.repo.link_whatsapp_account(
        tenant_id=tenant["id"],
        user_id=user["id"],
        phone_number="+15550001111"
    )

    resp = await orchestrator.handle_message(
        user_id="+15550001111",
        message_text="summarize my recent chats"
    )

    assert resp.status == "executed"
    assert "No recorded messages were found matching your criteria" in resp.response_text
    assert "Google Account not connected" not in resp.response_text
    assert "connect google" not in resp.response_text.lower()


@pytest.mark.asyncio
async def test_archive_search_and_citations(test_repo):
    """Verifies archiving messages, keyword filtering, contact filtering, and structured citations."""
    tenant = await test_repo.create_tenant(name="Citation Tenant")
    user = await test_repo.register_user(
        tenant_id=tenant["id"],
        phone_number="+15552223333",
        full_name="Bob Jones"
    )
    account = await test_repo.link_whatsapp_account(
        tenant_id=tenant["id"],
        user_id=user["id"],
        phone_number="+15552223333"
    )
    acc_id = account["id"]
    t_id = tenant["id"]

    # Archive 3 messages
    now = datetime.now(timezone.utc)
    m1 = await test_repo.archive_message(
        tenant_id=t_id,
        whatsapp_account_id=acc_id,
        provider_message_id="msg_101",
        sender_jid="15554445555@s.whatsapp.net",
        sender_phone="+15554445555",
        sender_display_name="Sarah Project Lead",
        text="The client meeting is rescheduled to Thursday 3pm",
        message_timestamp=now - timedelta(minutes=10)
    )
    m2 = await test_repo.archive_message(
        tenant_id=t_id,
        whatsapp_account_id=acc_id,
        provider_message_id="msg_102",
        sender_jid="15556667777@s.whatsapp.net",
        sender_phone="+15556667777",
        sender_display_name="David Tech",
        text="Server deployment completed smoothly on production",
        message_timestamp=now - timedelta(minutes=5)
    )
    m3 = await test_repo.archive_message(
        tenant_id=t_id,
        whatsapp_account_id=acc_id,
        provider_message_id="msg_103",
        sender_jid="15554445555@s.whatsapp.net",
        sender_phone="+15554445555",
        sender_display_name="Sarah Project Lead",
        text="Please send over the updated budget spreadsheet",
        message_timestamp=now - timedelta(minutes=2)
    )

    # 1. Search all
    all_msgs = await test_repo.search_messages(tenant_id=t_id, whatsapp_account_id=acc_id)
    assert len(all_msgs) == 3

    # 2. Search by query keyword "meeting"
    meeting_msgs = await test_repo.search_messages(
        tenant_id=t_id,
        whatsapp_account_id=acc_id,
        query_text="meeting"
    )
    assert len(meeting_msgs) == 1
    assert meeting_msgs[0]["provider_message_id"] == "msg_101"

    # 3. Search by contact "Sarah"
    sarah_msgs = await test_repo.search_messages(
        tenant_id=t_id,
        whatsapp_account_id=acc_id,
        contact="Sarah"
    )
    assert len(sarah_msgs) == 2

    # 4. Generate structured summary with citations
    summary = await test_repo.generate_archive_summary(
        tenant_id=t_id,
        whatsapp_account_id=acc_id
    )
    assert summary["total_found"] == 3
    assert len(summary["citations"]) == 3
    assert "[Msg msg_101" in summary["summary_text"]
    assert "Sarah Project Lead" in summary["summary_text"]
    assert "David Tech" in summary["summary_text"]


@pytest.mark.asyncio
async def test_tenant_isolation_in_archive(test_repo):
    """Archived messages from Tenant A must never be accessible or returned to Tenant B."""
    tenant_a = await test_repo.create_tenant(name="Tenant Alpha")
    user_a = await test_repo.register_user(tenant_id=tenant_a["id"], phone_number="+1111111111")
    acc_a = await test_repo.link_whatsapp_account(tenant_id=tenant_a["id"], user_id=user_a["id"], phone_number="+1111111111")

    tenant_b = await test_repo.create_tenant(name="Tenant Beta")
    user_b = await test_repo.register_user(tenant_id=tenant_b["id"], phone_number="+2222222222")
    acc_b = await test_repo.link_whatsapp_account(tenant_id=tenant_b["id"], user_id=user_b["id"], phone_number="+2222222222")

    # Tenant A archives a confidential message
    await test_repo.archive_message(
        tenant_id=tenant_a["id"],
        whatsapp_account_id=acc_a["id"],
        provider_message_id="secret_001",
        sender_jid="111@s.whatsapp.net",
        text="Confidential merger discussion notes"
    )

    # Tenant B searches for "Confidential"
    b_results = await test_repo.search_messages(
        tenant_id=tenant_b["id"],
        whatsapp_account_id=acc_b["id"],
        query_text="Confidential"
    )
    assert len(b_results) == 0

    # Cross-tenant query attempt (Tenant B ID with Account A ID)
    cross_results = await test_repo.search_messages(
        tenant_id=tenant_b["id"],
        whatsapp_account_id=acc_a["id"],
        query_text="Confidential"
    )
    assert len(cross_results) == 0


@pytest.mark.asyncio
async def test_archive_fastapi_endpoints():
    """Verifies POST /api/archive/search and POST /api/archive/summary HTTP endpoints."""
    from backend.app.db.repository import repository
    tenant = await repository.create_tenant(name="HTTP Archive Tenant")
    user = await repository.register_user(tenant_id=tenant["id"], phone_number="+1999888777")
    account = await repository.link_whatsapp_account(
        tenant_id=tenant["id"],
        user_id=user["id"],
        phone_number="+1999888777"
    )
    acc_id = account["id"]
    t_id = tenant["id"]

    await repository.archive_message(
        tenant_id=t_id,
        whatsapp_account_id=acc_id,
        provider_message_id="http_msg_1",
        sender_jid="1999@s.whatsapp.net",
        sender_phone="+1999888777",
        sender_display_name="CEO Office",
        text="Quarterly board presentation finalized"
    )

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # Search endpoint
        search_res = await client.post("/api/archive/search", json={
            "tenant_id": t_id,
            "whatsapp_account_id": acc_id,
            "query": "Quarterly"
        })
        assert search_res.status_code == 200
        search_json = search_res.json()
        assert search_json["status"] == "success"
        assert search_json["count"] == 1
        assert search_json["messages"][0]["provider_message_id"] == "http_msg_1"

        # Summary endpoint
        summary_res = await client.post("/api/archive/summary", json={
            "tenant_id": t_id,
            "whatsapp_account_id": acc_id
        })
        assert summary_res.status_code == 200
        sum_json = summary_res.json()
        assert sum_json["status"] == "success"
        assert sum_json["total_found"] == 1
        assert len(sum_json["citations"]) == 1
        assert "Quarterly board presentation finalized" in sum_json["summary_text"]

        # Cross-tenant boundary violation returns 400
        bad_res = await client.post("/api/archive/search", json={
            "tenant_id": "different_tenant_uuid",
            "whatsapp_account_id": acc_id
        })
        assert bad_res.status_code == 400
