"""Test Messaging Channels and Webhook Payload Parsing."""
import pytest
from backend.app.channels.evolution import EvolutionChannel
from backend.app.channels.mock import MockChannel


def test_evolution_webhook_parsing():
    channel = EvolutionChannel()

    # Valid incoming message payload from Evolution Go
    payload = {
        "event": "messages.upsert",
        "data": {
            "key": {
                "remoteJid": "919876543210@s.whatsapp.net",
                "fromMe": False,
                "id": "EVO_MSG_ID_999"
            },
            "message": {
                "conversation": "Move my 4pm meeting to tomorrow"
            }
        }
    }

    inbound = channel.parse_webhook_payload(payload, {})
    assert inbound is not None
    assert inbound.user_phone_or_id == "919876543210"
    assert inbound.text == "Move my 4pm meeting to tomorrow"
    assert inbound.channel_type == "evolution_whatsapp"


def test_evolution_outbound_echo_ignored():
    channel = EvolutionChannel()
    payload = {
        "event": "messages.upsert",
        "data": {
            "key": {
                "remoteJid": "919876543210@s.whatsapp.net",
                "fromMe": True
            },
            "message": {
                "conversation": "Bot's own message"
            }
        }
    }
    assert channel.parse_webhook_payload(payload, {}) is None
