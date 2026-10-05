"""Test idempotent retry on side-effecting tools."""
import pytest


@pytest.mark.asyncio
async def test_tool_idempotency_retry(mock_gmail, mock_calendar):
    idempotency_key = "idemp_uuid_test_12345"
    user_id = "user_test_idemp"

    payload = {
        "idempotency_key": idempotency_key,
        "action": "send",
        "recipient": "rahul@example.com",
        "subject": "Sync",
        "body": "Let's meet tomorrow."
    }

    # First call: executes tool
    res1 = await mock_gmail.execute(user_id, payload)
    assert res1.success is True
    assert res1.cached is False
    assert mock_gmail.execution_count == 1

    # Second call with same idempotency key: returns cached result without re-executing
    res2 = await mock_gmail.execute(user_id, payload)
    assert res2.success is True
    assert res2.cached is True
    # Execution count MUST remain 1
    assert mock_gmail.execution_count == 1


@pytest.mark.asyncio
async def test_calendar_idempotency(mock_calendar):
    key = "cal_idemp_999"
    user_id = "user_cal_test"
    payload = {
        "idempotency_key": key,
        "action": "create",
        "title": "Quarterly Planning"
    }

    res1 = await mock_calendar.execute(user_id, payload)
    assert res1.cached is False
    assert mock_calendar.execution_count == 1

    res2 = await mock_calendar.execute(user_id, payload)
    assert res2.cached is True
    assert mock_calendar.execution_count == 1
