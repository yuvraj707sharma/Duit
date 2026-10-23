"""Tests for Production Multi-Tenant Google OAuth, Web Portals, and Tenant Token Isolation."""
import pytest
from fastapi.testclient import TestClient
from backend.app.main import app
from backend.app.db.repository import repository
from backend.app.tools.calendar import GoogleCalendarTool
from backend.app.tools.gmail import GmailTool

client = TestClient(app)


def test_mobile_connect_portal_page():
    """Verify /connect returns responsive HTML onboarding page with Google sign-in button."""
    res = client.get("/connect?phone=919876543210")
    assert res.status_code == 200
    assert "text/html" in res.headers["content-type"]
    assert "Connect FastAgent" in res.text
    assert "Sign in with Google" in res.text
    assert "919876543210" in res.text


def test_mobile_connect_success_page():
    """Verify /connect/success returns the confirmation page with return to WhatsApp button."""
    res = client.get("/connect/success?phone=919876543210")
    assert res.status_code == 200
    assert "text/html" in res.headers["content-type"]
    assert "You&#39;re All Set!" in res.text or "You're All Set!" in res.text
    assert "Return to WhatsApp" in res.text


@pytest.mark.asyncio
async def test_multi_tenant_oauth_callback_isolation():
    """Verify that 2 distinct phone numbers receive completely isolated encrypted credentials."""
    user_a_phone = "919876543210"
    user_b_phone = "919999888877"

    # 1. User A completes Google OAuth
    res_a = client.get(f"/api/auth/google/callback?code=mock_auth_code_a&state={user_a_phone}")
    assert res_a.status_code == 200
    assert res_a.json()["status"] == "success"

    # 2. User B completes Google OAuth
    res_b = client.get(f"/api/auth/google/callback?code=mock_auth_code_b&state={user_b_phone}")
    assert res_b.status_code == 200
    assert res_b.json()["status"] == "success"

    # 3. Check repository stores tokens independently
    token_a = await repository.get_user_oauth_tokens(user_a_phone, "google")
    token_b = await repository.get_user_oauth_tokens(user_b_phone, "google")

    assert token_a is not None
    assert token_b is not None
    assert token_a["encrypted_access_token"] != token_b["encrypted_access_token"]
    assert token_a["encrypted_refresh_token"] != token_b["encrypted_refresh_token"]

    # 4. Check that User A's calendar execution carries User A's identity
    cal_tool = GoogleCalendarTool()
    cal_res_a = await cal_tool.execute(
        user_id=user_a_phone,
        payload={"action": "create", "title": "User A Meeting", "start_time": "2026-10-25T10:00:00Z", "idempotency_key": "idemp_a_1"}
    )
    assert cal_res_a.success is True
    assert cal_res_a.data["user_id"] == user_a_phone
    assert cal_res_a.data["title"] == "User A Meeting"

    # 5. Check that User B's email execution carries User B's identity
    gmail_tool = GmailTool()
    gmail_res_b = await gmail_tool.execute(
        user_id=user_b_phone,
        payload={"action": "send", "recipient": "boss@corp.com", "subject": "Quarterly Report", "idempotency_key": "idemp_b_1"}
    )
    assert gmail_res_b.success is True
    assert gmail_res_b.data["user_id"] == user_b_phone
    assert gmail_res_b.data["recipient"] == "boss@corp.com"
