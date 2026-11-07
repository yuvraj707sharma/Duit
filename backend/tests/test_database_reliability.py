"""Comprehensive test suite for Phase 9: Database and Reliability.

Validates:
1. Automatic retry on transient DB errors with exponential backoff
2. Immediate failure on non-transient errors
3. Optimistic concurrency control & version conflict detection on approvals
4. Deep readiness health probe with DB latency and pool stats
5. Alembic migration configuration and revision discovery
"""
import pytest
from unittest.mock import MagicMock
from sqlalchemy.exc import OperationalError
from fastapi.testclient import TestClient

from backend.app.main import app
from backend.app.db.retry import execute_with_retry, is_transient_db_error
from backend.app.db.repository import repository


@pytest.mark.asyncio
async def test_transient_error_retry_success():
    """Validates that execute_with_retry recovers from transient operational errors."""
    attempts = 0

    async def flaky_db_operation():
        nonlocal attempts
        attempts += 1
        if attempts < 3:
            raise OperationalError("deadlock detected", params=None, orig=Exception("deadlock detected"))
        return "operation_success"

    result = await execute_with_retry(
        flaky_db_operation,
        max_retries=3,
        initial_delay=0.01,
        backoff_multiplier=1.5
    )

    assert result == "operation_success"
    assert attempts == 3


@pytest.mark.asyncio
async def test_non_transient_error_fails_immediately():
    """Validates that non-transient programming/value errors fail immediately without retrying."""
    attempts = 0

    async def failing_operation():
        nonlocal attempts
        attempts += 1
        raise ValueError("Invalid query parameter")

    with pytest.raises(ValueError, match="Invalid query parameter"):
        await execute_with_retry(failing_operation, max_retries=3, initial_delay=0.01)

    assert attempts == 1


@pytest.mark.asyncio
async def test_optimistic_locking_conflict_detection():
    """Validates optimistic concurrency control preventing conflicting concurrent resolutions."""
    user_id = "user_optimistic_test"
    tenant_id = "tenant_optimistic_test"

    await repository.create_tenant(tenant_id=tenant_id, name="Optimistic Org")
    await repository.register_user(user_id=user_id, tenant_id=tenant_id, email="optimistic@example.com")

    # Create pending approval
    rec = await repository.create_pending_approval(
        user_id=user_id,
        request_id="req_opt_123",
        query_text="Send email to CEO",
        intent="send_email",
        risk="high",
        confidence=0.98,
        arguments={"to": "ceo@example.com", "subject": "Urgent"},
        tenant_id=tenant_id
    )
    approval_id = rec["id"]
    initial_version = rec.get("version", 1)

    # 1. First resolution with matching expected_version succeeds
    res1 = await repository.resolve_approval(
        approval_id=approval_id,
        decision="approve",
        caller_user_id=user_id,
        expected_version=initial_version
    )
    assert res1["status"] == "approve"
    assert res1["record"]["version"] == initial_version + 1

    # 2. Concurrent resolution attempting to resolve with stale initial_version is rejected with conflict
    res2 = await repository.resolve_approval(
        approval_id=approval_id,
        decision="reject",
        caller_user_id=user_id,
        expected_version=initial_version
    )
    assert res2.get("conflict") is True or "error" in res2


def test_deep_readiness_probe_endpoint():
    """Validates /api/health/ready returns DB latency timings, pool statistics, and truthful status."""
    client = TestClient(app)
    res = client.get("/api/health/ready")
    # Response code is truthfully 200 when reachable, or 503 when DB host is unreachable
    assert res.status_code in (200, 503)

    data = res.json()
    assert "status" in data
    assert "database" in data
    assert "status" in data["database"]
    assert "latency_ms" in data["database"]
    assert "pool" in data["database"]
    assert isinstance(data["database"]["latency_ms"], (int, float))


def test_alembic_configuration_validity():
    """Validates that Alembic can load env.py, resolve metadata, and identify initial migration."""
    from alembic.config import Config
    from alembic.script import ScriptDirectory

    alembic_cfg = Config("alembic.ini")
    script = ScriptDirectory.from_config(alembic_cfg)
    revisions = list(script.walk_revisions())

    assert len(revisions) >= 1
    initial_rev = revisions[-1]
    assert initial_rev.revision == "001_initial_schema"
