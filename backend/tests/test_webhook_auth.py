"""Tests for Webhook Authentication, JID Validation, and Security Headers."""
import pytest
from fastapi.testclient import TestClient
from backend.app.main import app
from backend.app.config import settings
from backend.app.channels.evolution import EvolutionChannel


def test_webhook_auth_missing_header_fails_401():
    client = TestClient(app)
    payload = {
        "event": "messages.upsert",
        "data": {
            "key": {
                "remoteJid": "919876543210@s.whatsapp.net",
                "fromMe": False,
                "id": "MSG_AUTH_1"
            },
            "message": {"conversation": "Check my schedule"}
        }
    }
    # No apikey / secret header provided
    res = client.post("/api/webhooks/evolution", json=payload)
    assert res.status_code == 401
    assert "unauthorized" in res.json().get("detail", "").lower()


def test_webhook_auth_invalid_header_fails_401():
    client = TestClient(app)
    payload = {
        "event": "messages.upsert",
        "data": {
            "key": {
                "remoteJid": "919876543210@s.whatsapp.net",
                "fromMe": False,
                "id": "MSG_AUTH_2"
            },
            "message": {"conversation": "Check my schedule"}
        }
    }
    res = client.post(
        "/api/webhooks/evolution",
        json=payload,
        headers={"apikey": "wrong_secret_key_123"}
    )
    assert res.status_code == 401


def test_webhook_rejects_non_individual_jids():
    channel = EvolutionChannel()
    
    # Group JID (@g.us)
    group_payload = {
        "event": "messages.upsert",
        "data": {
            "key": {"remoteJid": "123456789-987654@g.us", "fromMe": False, "id": "GRP_1"},
            "message": {"conversation": "move meeting"}
        }
    }
    assert channel.parse_webhook_payload(group_payload, {}) is None

    # Broadcast JID (@broadcast)
    broadcast_payload = {
        "event": "messages.upsert",
        "data": {
            "key": {"remoteJid": "status@broadcast", "fromMe": False, "id": "BCAST_1"},
            "message": {"conversation": "status update"}
        }
    }
    assert channel.parse_webhook_payload(broadcast_payload, {}) is None

    # Newsletter JID (@newsletter)
    newsletter_payload = {
        "event": "messages.upsert",
        "data": {
            "key": {"remoteJid": "12036302@newsletter", "fromMe": False, "id": "NEWS_1"},
            "message": {"conversation": "channel news"}
        }
    }
    assert channel.parse_webhook_payload(newsletter_payload, {}) is None


def test_webhook_accepts_valid_individual_jid():
    channel = EvolutionChannel()
    payload = {
        "event": "messages.upsert",
        "data": {
            "key": {"remoteJid": "919876543210@s.whatsapp.net", "fromMe": False, "id": "VALID_1"},
            "message": {"conversation": "Check calendar"}
        }
    }
    inbound = channel.parse_webhook_payload(payload, {})
    assert inbound is not None
    assert inbound.user_phone_or_id == "919876543210"
