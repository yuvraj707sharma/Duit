"""MessagingChannel Abstract Interface."""
import uuid
from abc import ABC, abstractmethod
from typing import Dict, Any, Optional, List
from pydantic import BaseModel


FASTAGENT_UUID_NAMESPACE = uuid.UUID("f902526d-66d8-49c3-b2b5-5fe95c870be6")


def get_user_uuid_from_channel_id(channel_id: str) -> str:
    """Deterministically maps a channel identifier (phone number, @lid, email) to an internal UUID."""
    cleaned = channel_id.strip().lower()
    return str(uuid.uuid5(FASTAGENT_UUID_NAMESPACE, f"channel:{cleaned}"))


class InboundMessage(BaseModel):
    message_id: str
    user_phone_or_id: str
    user_uuid: str
    text: str
    channel_type: str = "whatsapp"
    trust_taint: bool = False  # Set to True for text derived from inbound emails or 3rd-party messages
    raw_payload: Optional[Dict[str, Any]] = None


class OutboundMessage(BaseModel):
    recipient: str
    text: str
    buttons: Optional[List[Dict[str, str]]] = None


class MessagingChannel(ABC):
    @abstractmethod
    async def send_text(self, recipient: str, text: str) -> bool:
        """Sends a plain text message to the recipient."""
        pass

    @abstractmethod
    async def send_confirmation_prompt(self, recipient: str, text: str, action_id: str) -> bool:
        """Sends an interactive confirmation prompt (Yes/No buttons or text)."""
        pass

    @abstractmethod
    def parse_webhook_payload(self, raw_body: Dict[str, Any], headers: Dict[str, str]) -> Optional[InboundMessage]:
        """Parses channel-specific webhook payload into a normalized InboundMessage."""
        pass
