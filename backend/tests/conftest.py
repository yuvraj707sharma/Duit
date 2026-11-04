"""Pytest fixtures and configuration for FastAgent tests."""
import pytest
import os
import sys

# Ensure root workspace is on python path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))
os.environ["APP_ENV"] = "test"
os.environ["USE_MOCK_LLM"] = "True"

from backend.app.cascade.orchestrator import CascadeOrchestrator
from backend.app.channels.mock import MockChannel
from backend.app.tools.mock import MockCalendarTool, MockGmailTool
from backend.app.cascade.decision import MockDecisionModel
from backend.app.llm.mock import MockLLMProvider


@pytest.fixture
def mock_channel():
    return MockChannel()


@pytest.fixture
def mock_calendar():
    return MockCalendarTool()


@pytest.fixture
def mock_gmail():
    return MockGmailTool()


@pytest.fixture
def orchestrator(mock_channel, mock_calendar, mock_gmail):
    return CascadeOrchestrator(
        decision_model=MockDecisionModel(),
        llm_provider=MockLLMProvider(),
        messaging_channel=mock_channel,
        calendar_tool=mock_calendar,
        gmail_tool=mock_gmail
    )
