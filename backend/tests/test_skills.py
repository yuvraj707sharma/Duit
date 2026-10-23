"""Test suite for FastAgent dynamic skills system."""
import pytest
from httpx import AsyncClient, ASGITransport
from backend.app.main import app
from backend.app.cascade.orchestrator import CascadeOrchestrator
from backend.app.channels.mock import MockChannel
from backend.app.db.repository import DatabaseRepository


@pytest.mark.asyncio
async def test_skills_api_crud():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        # 1. List skills
        res = await client.get("/api/skills")
        assert res.status_code == 200
        skills = res.json()
        assert len(skills) >= 4
        slugs = [s["slug"] for s in skills]
        assert "expense_tracker" in slugs
        assert "action_items" in slugs

        # 2. Create custom skill
        new_skill_payload = {
            "name": "Fitness Nutritionist",
            "slug": "fitness_nutrition",
            "description": "Calculates macros and gives workout tips",
            "system_prompt": "You are an elite sports nutritionist.",
            "trigger_keywords": "workout, macros, protein, fitness"
        }
        res_create = await client.post("/api/skills", json=new_skill_payload)
        assert res_create.status_code == 201
        created = res_create.json()
        skill_id = created["id"]
        assert created["name"] == "Fitness Nutritionist"

        # 3. Verify it is listed
        res_after = await client.get("/api/skills")
        assert any(s["id"] == skill_id for s in res_after.json())

        # 4. Delete skill
        res_del = await client.delete(f"/api/skills/{skill_id}")
        assert res_del.status_code == 200

        # 5. Verify deletion
        res_final = await client.get("/api/skills")
        assert not any(s["id"] == skill_id for s in res_final.json())


@pytest.mark.asyncio
async def test_dynamic_skill_execution_in_cascade():
    repo = DatabaseRepository()
    mock_channel = MockChannel()
    orch = CascadeOrchestrator(
        db_repo=repo,
        messaging_channel=mock_channel
    )
    user_id = "user_skill_tester_999"

    # Message triggering Receipt & Expense Tracker skill
    expense_msg = "Here is my lunch bill receipt: $25 for pasta and soda"
    res = await orch.handle_message(user_id=user_id, message_text=expense_msg)

    assert res.status == "executed"
    assert "expense" in res.intent
    assert "Expense Analysis" in res.response_text or "Logged" in res.response_text
    assert len(mock_channel.sent_messages) >= 1
    assert mock_channel.sent_messages[-1]["recipient"] == user_id


@pytest.mark.asyncio
async def test_custom_user_added_skill_execution():
    repo = DatabaseRepository()
    mock_channel = MockChannel()
    orch = CascadeOrchestrator(
        db_repo=repo,
        messaging_channel=mock_channel
    )
    user_id = "user_custom_author_777"

    # Add custom skill to repo
    await repo.add_skill(
        name="Crypto Analyst",
        slug="crypto_analyst",
        system_prompt="You are a veteran crypto trader. Analyze token momentum.",
        trigger_keywords="bitcoin, btc, crypto, eth, token"
    )

    # Trigger custom skill
    crypto_msg = "What is the trend for bitcoin this week?"
    res = await orch.handle_message(user_id=user_id, message_text=crypto_msg)

    assert res.status == "executed"
    assert "crypto_analyst" in res.intent
    assert res.confidence == 1.0
