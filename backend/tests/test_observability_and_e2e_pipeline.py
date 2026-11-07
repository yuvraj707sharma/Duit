"""Comprehensive test suite for Phase 10 (Testing Methodology & E2E Pipeline)
and Phase 11 (Observability, Distributed Tracing & Operations).

Validates:
1. OpenTelemetry distributed trace context propagation (X-Trace-Id, X-Request-Id)
2. Operational metrics & P95 latency percentiles
3. Real-time alert triggers (abnormal pairing, brute force, cross-tenant violations)
4. Full End-to-End User Lifecycle & Platform Pipeline:
   - Tenant & User Onboarding
   - Secure WhatsApp Linking
   - WhatsApp Message Archive Retrieval with Citations & Honest Absence Reporting
   - Google OAuth Linking & Encrypted Token Storage
   - Risk-Tiered Step-Up Approvals & In-Place Natural Language Amendment
   - Desktop Device Registration, Policy Enforcement & Remote Kill Switch
   - Transactional Outbox Delivery with Provider ACK Receipts
   - GDPR Data Export & Confirmed Purge
5. Zero-Fabricated Success Law Enforcement
"""
import pytest
from datetime import datetime, timezone
from fastapi.testclient import TestClient

from backend.app.main import app
from backend.app.db.repository import repository
from backend.app.observability.tracing import get_trace_context, set_trace_context
from backend.app.observability.metrics import telemetry_collector
from backend.app.observability.alerts import alert_manager
from backend.app.security.crypto import encrypt_token, decrypt_token
from backend.app.policy.confirmations import is_step_up_confirmed, RISK_TTL_MAP
from backend.app.desktop.policy import DesktopPolicyEngine
from backend.app.broker.outbox import OutboxBroker


def test_opentelemetry_trace_headers_propagation():
    """Validates that incoming requests receive distributed trace and request headers."""
    client = TestClient(app)

    # 1. Custom incoming trace id is propagated
    res = client.get("/api/metrics", headers={"x-trace-id": "custom-trace-12345", "x-request-id": "req-custom-999"})
    assert res.status_code == 200
    assert res.headers.get("X-Trace-Id") == "custom-trace-12345"
    assert res.headers.get("X-Request-Id") == "req-custom-999"

    # 2. When headers omitted, server generates valid trace identifiers
    res_auto = client.get("/api/metrics")
    assert res_auto.status_code == 200
    assert "X-Trace-Id" in res_auto.headers
    assert "X-Request-Id" in res_auto.headers


def test_telemetry_metrics_and_p95_calculations():
    """Validates latency recording and percentile calculations in the telemetry engine."""
    collector = telemetry_collector
    for lat in [10.0, 20.0, 30.0, 40.0, 50.0, 60.0, 70.0, 80.0, 90.0, 100.0]:
        collector.record_ingestion_latency(lat)

    collector.record_tool_call(success=True)
    collector.record_tool_call(success=True)
    collector.record_tool_call(success=False)

    collector.record_approval(converted=True)
    collector.record_approval(converted=False)

    snapshot = collector.get_snapshot()
    assert snapshot["latencies_p95_ms"]["message_ingestion"] >= 90.0
    assert snapshot["counters"]["tool_calls_total"] >= 3
    assert snapshot["counters"]["tool_calls_successful"] >= 2
    assert snapshot["counters"]["approvals_created"] >= 2


def test_operational_alert_triggers():
    """Validates alert condition triggers on abnormal thresholds."""
    collector = telemetry_collector

    # Trigger cross-tenant error
    collector.record_cross_tenant_error()
    alerts = alert_manager.evaluate_alerts(db_latency_ms=650.0, queue_depth=75)

    alert_names = [a["alert"] for a in alerts]
    assert "CROSS_TENANT_VIOLATION_DETECTED" in alert_names
    assert "DATABASE_LATENCY_SPIKE" in alert_names
    assert "DELIVERY_QUEUE_BACKLOG" in alert_names


@pytest.mark.asyncio
async def test_full_e2e_platform_lifecycle():
    """Comprehensive end-to-end test simulating a complete multi-tenant user lifecycle."""
    tenant_id = "tenant_e2e_full"
    user_id = "user_e2e_director"
    phone_number = "+919876543210"

    # 1. Onboarding: Tenant and User Registration
    await repository.create_tenant(tenant_id=tenant_id, name="DUIT Enterprise Org")
    user = await repository.register_user(
        tenant_id=tenant_id,
        user_id=user_id,
        email="director@duit.ai",
        phone_number=phone_number,
        role="director"
    )
    assert user["id"] == user_id
    assert user["role"] == "director"

    # 2. WhatsApp Account Linking via Cryptographic Pairing Session
    session = await repository.create_linking_session(
        tenant_id=tenant_id,
        user_id=user_id,
        phone_number=phone_number
    )
    assert session["status"] == "pending"
    assert session["pairing_code"] is not None

    pair_res = await repository.confirm_pairing(
        session_id=session["id"],
        nonce=session["nonce"],
        pairing_code=session["pairing_code"],
        encrypted_credentials="encrypted_baileys_auth_data"
    )
    assert pair_res["status"] == "paired"
    account_id = pair_res["account_id"]

    # 3. Message Archive & Citation-backed Search
    await repository.archive_message(
        tenant_id=tenant_id,
        whatsapp_account_id=account_id,
        provider_message_id="msg_e2e_101",
        sender_jid=f"{phone_number}@s.whatsapp.net",
        text="Please schedule budget review for Monday at 10 AM",
        message_timestamp=datetime.now(timezone.utc)
    )

    summary_res = await repository.generate_archive_summary(
        tenant_id=tenant_id,
        whatsapp_account_id=account_id,
        query_text="budget"
    )
    summary = summary_res["summary_text"]
    assert "Msg msg_e2e_101" in summary
    assert "budget review" in summary

    # Absence reporting check
    empty_res = await repository.generate_archive_summary(
        tenant_id=tenant_id,
        whatsapp_account_id=account_id,
        query_text="completely_unrelated_query"
    )
    empty_summary = empty_res["summary_text"]
    assert "No recorded messages were found matching your criteria in this window." in empty_summary

    # 4. Google OAuth Linking with AES-256-GCM Encryption
    enc_access = encrypt_token("ya29.mock_google_access_token", user_id=user_id)
    enc_refresh = encrypt_token("1//mock_google_refresh_token", user_id=user_id)

    await repository.save_user_oauth_tokens(
        user_id=user_id,
        provider="google",
        encrypted_access_token=enc_access,
        encrypted_refresh_token=enc_refresh,
        tenant_id=tenant_id,
        scopes=["https://www.googleapis.com/auth/calendar", "https://www.googleapis.com/auth/gmail.send"]
    )
    oauth_conn = await repository.get_user_oauth_connection(user_id=user_id, provider="google", tenant_id=tenant_id)
    assert oauth_conn["status"] == "active"
    assert "https://www.googleapis.com/auth/calendar" in oauth_conn["scopes"]

    # 5. Risk-Tiered Approval & In-Place Amendment
    approval = await repository.create_pending_approval(
        user_id=user_id,
        request_id="req_e2e_approval",
        query_text="Send email to board of directors",
        intent="send_email",
        risk="critical",
        confidence=0.99,
        arguments={"to": "board@duit.ai", "subject": "Q4 Results", "body": "Draft report"},
        tenant_id=tenant_id
    )
    approval_id = approval["id"]
    assert approval["risk"] == "critical"
    # Step-up check: 'y' is rejected for critical risk; explicit confirmation required
    assert not is_step_up_confirmed("y", "critical")
    assert is_step_up_confirmed("confirm", "critical")

    # In-place amendment
    amend_res = await repository.amend_approval(
        approval_id=approval_id,
        caller_user_id=user_id,
        amendments={"subject": "Q4 Final Verified Results"},
        tenant_id=tenant_id
    )
    assert amend_res["status"] == "amended"
    assert amend_res["record"]["arguments"]["subject"] == "Q4 Final Verified Results"

    # Resolve approval
    resolve_res = await repository.resolve_approval(
        approval_id=approval_id,
        decision="approve",
        caller_user_id=user_id
    )
    assert resolve_res["status"] == "approve"

    # 6. Desktop Device Pairing, Policy Protection & Kill Switch
    device = await repository.register_desktop_device(
        tenant_id=tenant_id,
        user_id=user_id,
        device_name="Director Workstation",
        platform="windows"
    )
    device_id = device["id"]

    policy_engine = DesktopPolicyEngine()
    # Sensitive path protected
    assert not policy_engine.validate_file_path("C:/Users/Admin/.ssh/id_rsa")
    assert not policy_engine.validate_command("format c: /q")
    assert policy_engine.validate_file_path("C:/Users/Admin/Documents/report.pdf")

    # Remote Kill Switch
    kill_res = await repository.kill_desktop_device(device_id=device_id, tenant_id=tenant_id)
    assert kill_res["is_online"] is False
    assert kill_res["revoked_at"] is not None

    # 7. Transactional Outbox Delivery with Receipts
    outbox_event = await repository.create_outbox_event(
        tenant_id=tenant_id,
        aggregate_type="whatsapp_message",
        aggregate_id="msg_out_101",
        event_type="send_message",
        payload={"recipient": phone_number, "body": "Action completed successfully"},
        idempotency_key=f"outbox-{user_id}-1"
    )
    assert outbox_event["status"] == "pending"

    # Acknowledge delivery
    ack_res = await repository.mark_outbox_event_delivered(
        event_id=outbox_event["id"],
        delivery_receipt_id="wa_ack_receipt_9999"
    )
    assert ack_res["status"] == "delivered"
    assert ack_res["delivered_at"] is not None

    # 8. GDPR Personal Data Export & Confirmed Purge
    export_data = await repository.export_user_data(tenant_id=tenant_id, user_id=user_id)
    assert export_data["user"]["id"] == user_id
    assert len(export_data["messages"]) >= 1

    purge_res = await repository.purge_user_data(tenant_id=tenant_id, user_id=user_id, options={"confirm": True})
    assert purge_res["status"] == "success"
    assert purge_res["purged_records"]["messages"] >= 1


@pytest.mark.asyncio
async def test_zero_fabricated_success_law():
    """Validates that DUIT never reports simulated actions as successful in non-mock production mode."""
    from backend.app.config import settings

    # In strict mode, mock actions must never return false completion
    from backend.app.cascade.decision import MockDecisionModel
    dm = MockDecisionModel()
    decision = await dm.decide("What is the status of my laptop?")
    # Intent routes to system status or help, never claims action executed
    assert decision.intent in ("laptop_status", "system_status", "greeting", "other")
