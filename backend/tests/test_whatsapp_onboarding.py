"""Tests for WhatsApp Multi-Tenant Onboarding, Whitelist Firewall, and QR Status."""
import pytest
from fastapi.testclient import TestClient
from backend.app.main import app
from backend.app.config import settings
from backend.app.db.repository import repository

client = TestClient(app)


def test_whatsapp_status_endpoint():
    res = client.get("/api/whatsapp/status")
    assert res.status_code == 200
    data = res.json()
    assert "status" in data
    assert "instance" in data


def test_whatsapp_qr_endpoint():
    res = client.get("/api/whatsapp/qr")
    assert res.status_code == 200
    data = res.json()
    assert "status" in data


def test_user_onboard_endpoint():
    payload = {
        "phone_number": "919999888877",
        "email": "pilot_user@example.com",
        "display_name": "Pilot User"
    }
    res = client.post("/api/users/onboard", json=payload)
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "registered"
    assert data["user"]["phone_number"] == "919999888877"
    assert "id" in data["user"]


def test_unregistered_number_receives_onboarding_prompt(monkeypatch):
    monkeypatch.setattr(settings, "WHATSAPP_REQUIRE_REGISTRATION", True)
    monkeypatch.setattr(settings, "WHATSAPP_AUTHORIZED_NUMBERS", ["*"])

    payload = {
        "event": "messages.upsert",
        "data": {
            "key": {
                "remoteJid": "915555444433@s.whatsapp.net",
                "fromMe": False,
                "id": "UNREG_MSG_1"
            },
            "message": {"conversation": "Schedule meeting with John"}
        }
    }
    headers = {"apikey": settings.EVOLUTION_GLOBAL_API_KEY}

    res = client.post("/api/webhooks/evolution", json=payload, headers=headers)
    assert res.status_code == 200
    body = res.json()
    assert body["status"] == "onboarding_prompt_sent"
    assert body["reason"] == "new_unregistered_user"


def test_unauthorized_number_dropped_by_whitelist(monkeypatch):
    monkeypatch.setattr(settings, "WHATSAPP_REQUIRE_REGISTRATION", False)
    # Whitelist only allows this single specific number
    monkeypatch.setattr(settings, "WHATSAPP_AUTHORIZED_NUMBERS", ["919876543210"])

    payload = {
        "event": "messages.upsert",
        "data": {
            "key": {
                "remoteJid": "918888777766@s.whatsapp.net",  # Foreign number not in whitelist
                "fromMe": False,
                "id": "FOREIGN_MSG_1"
            },
            "message": {"conversation": "Delete all calendar events"}
        }
    }
    headers = {"apikey": settings.EVOLUTION_GLOBAL_API_KEY}

    res = client.post("/api/webhooks/evolution", json=payload, headers=headers)
    assert res.status_code == 200
    body = res.json()
    assert body["status"] == "dropped"
    assert body["reason"] == "unauthorized_phone_whitelist"


def test_registered_user_processes_through_cascade(monkeypatch):
    monkeypatch.setattr(settings, "WHATSAPP_REQUIRE_REGISTRATION", True)
    monkeypatch.setattr(settings, "WHATSAPP_AUTHORIZED_NUMBERS", ["*"])

    # 919876543210 is pre-registered in repository
    payload = {
        "event": "messages.upsert",
        "data": {
            "key": {
                "remoteJid": "919876543210@s.whatsapp.net",
                "fromMe": False,
                "id": "REG_MSG_1"
            },
            "message": {"conversation": "Check my calendar"}
        }
    }
    headers = {"apikey": settings.EVOLUTION_GLOBAL_API_KEY}

    res = client.post("/api/webhooks/evolution", json=payload, headers=headers)
    assert res.status_code == 200
    body = res.json()
    assert body["status"] == "processed"
    assert "response_text" in body
