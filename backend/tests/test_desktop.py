"""Tests for FastAgent Desktop Executor: WAL Journal crash recovery, TTL expiry, Kill-switch, Allowlist skills, and Presence."""
import os
import time
import tempfile
import pytest
from unittest.mock import AsyncMock, patch

from backend.app.desktop.journal import WriteAheadJournal
from backend.app.desktop.skills import DesktopSkillExecutor, SkillValidationError
from backend.app.desktop.context_store import ContextStore
from backend.app.desktop.presence import DesktopPresenceManager
from backend.app.desktop.sidecar import DesktopSidecarAgent
from backend.app.policy.engine import PolicyEngine
from backend.app.cascade.orchestrator import CascadeOrchestrator, OrchestratorResponse
from backend.app.cascade.decision import MockDecisionModel, DecisionOutput
from backend.app.channels.mock import MockChannel


# ---------------------------------------------------------------------------
# Test 1: Crash between 'started' and 'completed' (Simulate kill -9)
# ---------------------------------------------------------------------------
def test_journal_crash_reconciliation_between_started_and_completed():
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = os.path.join(tmpdir, "test_journal.db")
        journal = WriteAheadJournal(db_path=db_path)

        # 1. Side-effecting action started (e.g. open_app)
        act1 = "act_side_effect_01"
        journal.record_received(
            action_id=act1,
            user_id="user_123",
            intent="open_app",
            arguments={"app_name": "notepad", "idempotency_key": "idemp_01"},
            is_read_only=False
        )
        journal.transition_state(act1, "started")

        # 2. Read-only action started (e.g. search_files)
        act2 = "act_read_only_02"
        journal.record_received(
            action_id=act2,
            user_id="user_123",
            intent="search_files",
            arguments={"query": "invoice.pdf"},
            is_read_only=True
        )
        journal.transition_state(act2, "started")

        # 3. Simulate kill -9 crash: instantiate a new journal on startup
        restarted_journal = WriteAheadJournal(db_path=db_path)
        reconciled = restarted_journal.reconcile_on_startup()

        assert len(reconciled) == 2

        # Side-effecting action becomes 'interrupted' and surfaced to user
        entry1 = restarted_journal.get_entry(act1)
        assert entry1["state"] == "interrupted"
        assert "Interrupted" in entry1["error_message"]

        # Read-only action allows re-run
        reconciled_map = {r["action_id"]: r for r in reconciled}
        assert reconciled_map[act1]["reconciliation_status"] == "interrupted_surfaced"
        assert reconciled_map[act2]["reconciliation_status"] == "re_run_allowed"


# ---------------------------------------------------------------------------
# Test 2: TTL Expiry After Sleep (Voice 30s, Confirmation 5m)
# ---------------------------------------------------------------------------
def test_ttl_expiry_voice_and_confirmation():
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = os.path.join(tmpdir, "test_journal_ttl.db")
        journal = WriteAheadJournal(db_path=db_path)

        now = time.time()

        # Voice command created 35s ago (>30s TTL)
        voice_id = "voice_cmd_expired"
        journal.record_received(
            action_id=voice_id,
            user_id="user_voice",
            intent="set_volume",
            arguments={"level": 50, "idempotency_key": "idemp_v1"},
            is_read_only=False,
            is_voice_command=True,
            created_at=now - 35.0
        )

        assert journal.check_ttl_expired(voice_id) is True
        entry = journal.get_entry(voice_id)
        assert entry["state"] == "expired"
        assert "Voice command expired" in entry["error_message"]

        # Fresh voice command created 5s ago (<=30s TTL)
        fresh_voice_id = "voice_cmd_fresh"
        journal.record_received(
            action_id=fresh_voice_id,
            user_id="user_voice",
            intent="set_volume",
            arguments={"level": 50, "idempotency_key": "idemp_v2"},
            is_read_only=False,
            is_voice_command=True,
            created_at=now - 5.0
        )
        assert journal.check_ttl_expired(fresh_voice_id) is False

        # Confirmation created 305s ago (>5m TTL)
        conf_id = "conf_expired"
        journal.record_received(
            action_id=conf_id,
            user_id="user_conf",
            intent="open_app",
            arguments={"app_name": "notepad", "idempotency_key": "idemp_c1"},
            is_read_only=False,
            is_voice_command=False,
            created_at=now - 305.0
        )
        assert journal.check_ttl_expired(conf_id) is True
        entry_conf = journal.get_entry(conf_id)
        assert entry_conf["state"] == "expired"


# ---------------------------------------------------------------------------
# Test 3: Kill-Switch Cancels a Pending Action
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_kill_switch_cancels_pending_action():
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = os.path.join(tmpdir, "test_sidecar.db")
        journal = WriteAheadJournal(db_path=db_path)
        context = ContextStore(store_path=os.path.join(tmpdir, "context.enc"), user_id="user_ks")
        sidecar = DesktopSidecarAgent(
            user_id="user_ks",
            journal_instance=journal,
            context_store_instance=context
        )

        # Trigger Kill Switch
        sidecar.trigger_kill_switch()
        assert sidecar.kill_switch_active is True

        # Attempt executing an action while kill switch is active
        action_payload = {
            "action_id": "act_kill_switched",
            "intent": "open_app",
            "arguments": {"app_name": "calculator", "idempotency_key": "ks_01"}
        }

        res = await sidecar.execute_action_safely(action_payload)
        assert res["success"] is False
        assert res["status"] == "interrupted"
        assert "kill-switch" in res["error"].lower()

        # Check WAL journal recorded interrupted
        entry = journal.get_entry("act_kill_switched")
        assert entry["state"] == "interrupted"


# ---------------------------------------------------------------------------
# Test 4: Disallowed Skills are Strictly Rejected
# ---------------------------------------------------------------------------
def test_disallowed_skills_and_allowlist_rejection():
    with tempfile.TemporaryDirectory() as tmpdir:
        executor = DesktopSkillExecutor(sandbox_dir=tmpdir)
        policy = PolicyEngine()

        # 1. Shell command strictly rejected
        with pytest.raises(SkillValidationError, match="forbidden"):
            executor.execute_skill("shell", {"command": "dir"})

        eval_shell = policy.evaluate_action(
            user_id="u1",
            intent="shell",
            arguments={"command": "whoami"},
            confidence=0.99
        )
        assert eval_shell.allowed is False
        assert "strictly prohibited" in eval_shell.reasoning

        # 2. File deletion strictly rejected
        with pytest.raises(SkillValidationError, match="forbidden"):
            executor.execute_skill("delete", {"path": "file.txt"})

        eval_delete = policy.evaluate_action(
            user_id="u1",
            intent="delete",
            arguments={"path": "file.txt"},
            confidence=0.99
        )
        assert eval_delete.allowed is False

        # 3. Non-allowlisted app rejected
        with pytest.raises(SkillValidationError, match="allowlist"):
            executor.execute_skill("open_app", {"app_name": "malicious_app.exe", "idempotency_key": "k1"})

        eval_app = policy.evaluate_action(
            user_id="u1",
            intent="open_app",
            arguments={"app_name": "malicious_app.exe"},
            confidence=0.95
        )
        assert eval_app.allowed is False

        # 4. Non-http URL rejected (e.g. file:// or javascript:)
        with pytest.raises(SkillValidationError, match="http"):
            executor.execute_skill("open_url", {"url": "file:///C:/secrets.txt", "idempotency_key": "k2"})

        eval_url = policy.evaluate_action(
            user_id="u1",
            intent="open_url",
            arguments={"url": "file:///etc/passwd"},
            confidence=0.95
        )
        assert eval_url.allowed is False

        # 5. Type text into password field rejected
        with pytest.raises(SkillValidationError, match="password"):
            executor.execute_skill("type_text", {
                "text": "secret123",
                "target_control_type": "password_input",
                "idempotency_key": "k3"
            })

        # 6. Valid allowlisted skills succeed
        res_app = executor.execute_skill("open_app", {"app_name": "notepad", "idempotency_key": "k4"})
        assert res_app["success"] is True

        res_note = executor.execute_skill("create_note", {
            "title": "meeting_notes",
            "content": "Discuss quarterly targets.",
            "idempotency_key": "k5"
        })
        assert res_note["success"] is True
        assert os.path.exists(res_note["path"])


# ---------------------------------------------------------------------------
# Test 5: Offline Presence Reply (Cross-Channel WhatsApp/Telegram -> Desktop)
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_cross_channel_offline_presence_reply():
    presence = DesktopPresenceManager(heartbeat_timeout=30.0)
    channel = MockChannel()
    decision_model = MockDecisionModel()
    
    orchestrator = CascadeOrchestrator(
        decision_model=decision_model,
        messaging_channel=channel
    )

    user_id = "user_cross_channel_01"

    # Ensure desktop is offline
    assert presence.is_online(user_id) is False

    # Patch decision model to predict a desktop intent: open_app
    with patch.object(
        decision_model,
        "decide",
        return_value=DecisionOutput(
            intent="open_app",
            risk="medium",
            needs_confirmation=True,
            confidence=0.95,
            detected_language="en",
            model_used="laya-multilingual",
            reasoning_tag="desktop_action"
        )
    ):
        with patch("backend.app.desktop.presence.presence_manager", presence):
            # Inbound request targeting desktop while laptop is offline
            resp = await orchestrator.handle_message(
                user_id=user_id,
                message_text="Open notepad on my laptop"
            )

            # Verifies Requirement 6: Replies "laptop offline" instead of queueing risky actions
            assert resp.status == "offline"
            assert resp.response_text == "laptop offline"
            assert len(channel.sent_messages) > 0
            assert channel.sent_messages[-1]["text"] == "laptop offline"


# ---------------------------------------------------------------------------
# Test 6: Context Store Sanitization and Clear-History
# ---------------------------------------------------------------------------
def test_context_store_sanitization_and_encryption():
    with tempfile.TemporaryDirectory() as tmpdir:
        store_path = os.path.join(tmpdir, "test_context.enc")
        store = ContextStore(store_path=store_path, user_id="user_test_ctx")

        # Record operation containing sensitive typed text and password
        store.record_operation(
            intent="type_text",
            args={"text": "SuperSecretPassword123!", "password": "hidden", "target_app": "terminal"},
            status="completed"
        )

        ctx = store.get_context()
        assert len(ctx["operations"]) == 1
        op = ctx["operations"][0]

        # Invariant: NEVER store typed text or passwords in context store
        assert "SuperSecretPassword123!" not in str(op)
        assert op["metadata"]["text"] == "[REDACTED_BY_SECURITY_POLICY]"
        assert op["metadata"]["password"] == "[REDACTED_BY_SECURITY_POLICY]"

        # Clear history command
        res_clear = store.clear_history()
        assert res_clear["success"] is True

        ctx_cleared = store.get_context()
        assert len(ctx_cleared["operations"]) == 0
        assert "cleared" in ctx_cleared["summary"].lower()


# ---------------------------------------------------------------------------
# Test 7: Ultra-Low-Latency Local Voice STT Engine & API Integration
# ---------------------------------------------------------------------------
def test_voice_stt_engine_and_api():
    from backend.app.desktop.voice_stt import voice_stt_engine
    from fastapi.testclient import TestClient
    from backend.app.main import app

    client = TestClient(app)

    # 1. Direct engine unit test
    audio_sample = b"open notepad on my laptop"
    stt_res = voice_stt_engine.transcribe_audio(audio_sample)
    assert stt_res["text"] == "open notepad on my laptop"
    assert "latency_ms" in stt_res
    assert stt_res["latency_ms"] < 250.0  # Must be fast
    assert stt_res["confidence"] > 0.9

    # 2. VAD check
    assert voice_stt_engine.detect_voice_activity(b"") is False
    assert voice_stt_engine.detect_voice_activity(b"0" * 1500) is True

    # 3. HTTP endpoint test
    res = client.post(
        "/api/desktop/voice/transcribe?user_id=desktop_test_user&execute_cascade=true",
        content=audio_sample,
        headers={"Content-Type": "application/octet-stream"}
    )
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "success"
    assert data["transcription"]["text"] == "open notepad on my laptop"
    assert "cascade" in data

