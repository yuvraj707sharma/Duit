"""Tests for Phase 4: Transactional Outbox Pattern, Event Broker, Deduplication, and Delivery Tracking."""
import pytest
from datetime import datetime, timezone, timedelta
from httpx import AsyncClient, ASGITransport

from backend.app.main import app
from backend.app.db.repository import DatabaseRepository
from backend.app.broker.outbox import OutboxBroker


class MockFailingChannel:
    async def send_text(self, recipient: str, text: str):
        raise RuntimeError("Gateway connection dropped (network timeout)")


class MockSuccessfulChannel:
    def __init__(self):
        self.sent = []

    async def send_text(self, recipient: str, text: str):
        self.sent.append({"recipient": recipient, "text": text})


@pytest.fixture
def test_repo():
    return DatabaseRepository()


@pytest.mark.asyncio
async def test_outbox_event_creation_and_deduplication(test_repo):
    """Verifies outbox event creation with tenant scoping and deduplication via idempotency key."""
    tenant = await test_repo.create_tenant(name="Outbox Tenant")
    t_id = tenant["id"]
    key = "idem_key_001"

    evt1 = await test_repo.create_outbox_event(
        tenant_id=t_id,
        aggregate_type="whatsapp_message",
        aggregate_id="wa_acc_123",
        event_type="outbound_message_requested",
        payload={"recipient": "+15551234567", "text": "Your appointment is confirmed."},
        idempotency_key=key
    )
    assert evt1["id"] is not None
    assert evt1["status"] == "pending"
    assert evt1["retry_count"] == 0
    assert evt1["tenant_id"] == t_id

    # Re-insert with same tenant and idempotency key
    evt2 = await test_repo.create_outbox_event(
        tenant_id=t_id,
        aggregate_type="whatsapp_message",
        aggregate_id="wa_acc_123",
        event_type="outbound_message_requested",
        payload={"recipient": "+15551234567", "text": "Duplicate call."},
        idempotency_key=key
    )
    assert evt2["id"] == evt1["id"], "Duplicate outbox event must be deduplicated by idempotency key"
    assert len(test_repo.outbox_store) == 1


@pytest.mark.asyncio
async def test_outbox_successful_dispatch_and_acknowledgement(test_repo):
    """Verifies end-to-end lifecycle: pending -> published -> delivered."""
    tenant = await test_repo.create_tenant(name="Lifecycle Tenant")
    t_id = tenant["id"]
    key = "idem_key_lifecycle"

    await test_repo.create_outbox_event(
        tenant_id=t_id,
        aggregate_type="whatsapp_message",
        aggregate_id="wa_acc_456",
        event_type="outbound_message_requested",
        payload={"recipient": "+15559876543", "text": "Executive summary report."},
        idempotency_key=key
    )

    channel = MockSuccessfulChannel()
    broker = OutboxBroker(repo=test_repo, messaging_channel=channel)

    # 1. Dispatch pending events
    metrics = await broker.dispatch_pending_batch(batch_size=10)
    assert metrics["processed"] == 1
    assert metrics["published"] == 1
    assert len(channel.sent) == 1

    # Verify event is published
    evt = await test_repo.get_outbox_event_by_idempotency_key(t_id, key)
    assert evt["status"] == "published"
    assert evt["published_at"] is not None

    # 2. Gateway delivers and sends acknowledgement receipt
    delivered = await test_repo.mark_outbox_event_delivered(
        idempotency_key_or_id=key,
        provider_message_id="wa_msg_receipt_999"
    )
    assert delivered["status"] == "delivered"
    assert delivered["delivered_at"] is not None
    assert delivered["payload"].get("provider_delivery_id") == "wa_msg_receipt_999"


@pytest.mark.asyncio
async def test_outbox_retry_backoff_and_dead_letter(test_repo):
    """Verifies retry count increment, exponential backoff scheduling, and dead-letter queue routing after 5 failures."""
    tenant = await test_repo.create_tenant(name="Failure Tenant")
    t_id = tenant["id"]
    key = "idem_key_fail"

    evt = await test_repo.create_outbox_event(
        tenant_id=t_id,
        aggregate_type="whatsapp_message",
        aggregate_id="wa_acc_fail",
        event_type="outbound_message_requested",
        payload={"recipient": "+15550000000", "text": "This dispatch will fail."},
        idempotency_key=key,
        max_retries=3  # Test with max_retries=3 for fast test execution
    )
    eid = evt["id"]

    broker = OutboxBroker(repo=test_repo, messaging_channel=MockFailingChannel())

    # Retries 1, 2: should transition to failed with backoff
    for attempt in range(1, 3):
        # Force scheduled_at to current/past so it's ready for dispatch
        evt["scheduled_at"] = datetime.now(timezone.utc) - timedelta(seconds=1)
        res = await broker.dispatch_pending_batch()
        assert res["failed"] == 1
        assert evt["retry_count"] == attempt
        assert evt["status"] == "failed"
        assert "Gateway connection dropped" in evt["error_message"]

    # Retry 3: exceeds max_retries -> transitions to dead_letter
    evt["scheduled_at"] = datetime.now(timezone.utc) - timedelta(seconds=1)
    res = await broker.dispatch_pending_batch()
    assert res["dead_letter"] == 1
    assert evt["status"] == "dead_letter"
    assert evt["retry_count"] == 3


@pytest.mark.asyncio
async def test_outbox_fastapi_endpoints():
    """Verifies /api/outbox/publish, /api/outbox/acknowledge, and /api/outbox/status endpoints."""
    from backend.app.db.repository import repository
    tenant = await repository.create_tenant(name="API Outbox Tenant")
    t_id = tenant["id"]
    key = "idem_api_key_777"

    await repository.create_outbox_event(
        tenant_id=t_id,
        aggregate_type="whatsapp_message",
        aggregate_id="wa_acc_api",
        event_type="outbound_message_requested",
        payload={"recipient": "+15557778888", "text": "Testing API outbox."},
        idempotency_key=key
    )

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # 1. Status endpoint before dispatch
        status_res = await client.get(f"/api/outbox/status/{key}?tenant_id={t_id}")
        assert status_res.status_code == 200
        assert status_res.json()["lifecycle_status"] == "pending"

        # 2. Trigger batch dispatch
        pub_res = await client.post("/api/outbox/publish", json={"batch_size": 10})
        assert pub_res.status_code == 200
        assert pub_res.json()["status"] == "success"

        # 3. Acknowledge delivery
        ack_res = await client.post("/api/outbox/acknowledge", json={
            "idempotency_key": key,
            "provider_message_id": "receipt_wam_777"
        })
        assert ack_res.status_code == 200
        assert ack_res.json()["status"] == "acknowledged"
        assert ack_res.json()["event_status"] == "delivered"

        # 4. Status endpoint after delivery
        final_status = await client.get(f"/api/outbox/status/{key}?tenant_id={t_id}")
        assert final_status.status_code == 200
        assert final_status.json()["lifecycle_status"] == "delivered"
        assert final_status.json()["delivered_at"] is not None

        # 5. Non-existent key returns 404
        bad_ack = await client.post("/api/outbox/acknowledge", json={
            "idempotency_key": "non_existent_key_99999"
        })
        assert bad_ack.status_code == 404

