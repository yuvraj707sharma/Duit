"""Evolution Go WhatsApp Messaging Channel Adapter."""
from typing import Dict, Any, Optional
import httpx
from backend.app.channels.base import MessagingChannel, InboundMessage, get_user_uuid_from_channel_id
from backend.app.config import settings


class EvolutionChannel(MessagingChannel):
    def __init__(self, base_url: str = None, api_key: str = None, instance_name: str = None):
        self.base_url = (base_url or settings.EVOLUTION_BASE_URL).rstrip("/")
        self.api_key = api_key or settings.EVOLUTION_GLOBAL_API_KEY
        self.instance_name = instance_name or settings.EVOLUTION_INSTANCE_NAME

    async def send_text(self, recipient: str, text: str) -> bool:
        url = f"{self.base_url}/send/text"
        headers = {
            "apikey": self.api_key,
            "Content-Type": "application/json"
        }
        payload = {
            "number": recipient,
            "text": text
        }
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                res = await client.post(url, json=payload, headers=headers)
                return res.status_code in (200, 201)
        except Exception:
            return False

    async def send_confirmation_prompt(self, recipient: str, text: str, action_id: str) -> bool:
        prompt_text = f"{text}\n\n👉 Reply *YES* to confirm, *NO* to cancel, or text your corrections."
        return await self.send_text(recipient, prompt_text)

    def parse_webhook_payload(self, raw_body: Dict[str, Any], headers: Dict[str, str]) -> Optional[InboundMessage]:
        event_type = raw_body.get("event")
        data = raw_body.get("data", {})
        
        # Check standard Evolution messages.upsert event
        if event_type == "messages.upsert" or "message" in data:
            key = data.get("key", {})
            remote_jid = key.get("remoteJid", "")
            from_me = key.get("fromMe", False)
            if from_me:
                return None  # Ignore outbound echoes
            
            # Security: Reject non-individual JIDs (groups @g.us, broadcasts @broadcast, newsletters @newsletter, etc.)
            if not remote_jid:
                return None
            if "@" in remote_jid:
                domain = remote_jid.split("@")[1]
                if domain not in ("s.whatsapp.net", "lid"):
                    return None  # Rejected non-individual JID

            phone = remote_jid.split("@")[0] if "@" in remote_jid else remote_jid
            cleaned_phone = phone.lstrip("+")
            if not cleaned_phone.isdigit() and "@lid" not in remote_jid:
                return None

            message_obj = data.get("message", {})
            text = (
                message_obj.get("conversation") or
                message_obj.get("extendedTextMessage", {}).get("text") or
                ""
            )
            msg_id = key.get("id", "")
            if text and phone:
                user_uuid = get_user_uuid_from_channel_id(phone)
                return InboundMessage(
                    message_id=msg_id,
                    user_phone_or_id=phone,
                    user_uuid=user_uuid,
                    text=text.strip(),
                    channel_type="evolution_whatsapp",
                    trust_taint=False,
                    raw_payload=raw_body
                )
        return None
