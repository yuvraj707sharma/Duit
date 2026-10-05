"""Mock Messaging Channel for offline execution and testing."""
from typing import Dict, Any, Optional, List
from backend.app.channels.base import MessagingChannel, InboundMessage, get_user_uuid_from_channel_id


class MockChannel(MessagingChannel):
    def __init__(self):
        self.sent_messages: List[Dict[str, Any]] = []
        self.confirmation_prompts: List[Dict[str, Any]] = []

    async def send_text(self, recipient: str, text: str) -> bool:
        self.sent_messages.append({"recipient": recipient, "text": text})
        return True

    async def send_confirmation_prompt(self, recipient: str, text: str, action_id: str) -> bool:
        self.confirmation_prompts.append({
            "recipient": recipient,
            "text": text,
            "action_id": action_id
        })
        return True

    def parse_webhook_payload(self, raw_body: Dict[str, Any], headers: Dict[str, str]) -> Optional[InboundMessage]:
        phone_or_id = raw_body.get("user_phone_or_id", "mock_user_123")
        return InboundMessage(
            message_id=raw_body.get("message_id", "mock_msg_123"),
            user_phone_or_id=phone_or_id,
            user_uuid=get_user_uuid_from_channel_id(phone_or_id),
            text=raw_body.get("text", ""),
            channel_type="mock",
            trust_taint=raw_body.get("trust_taint", False),
            raw_payload=raw_body
        )

    def clear(self):
        self.sent_messages.clear()
        self.confirmation_prompts.clear()
