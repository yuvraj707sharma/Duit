"""Evolution Go WhatsApp Webhook Ingestion Endpoint with Constant-Time Shared Secret Auth."""
import hmac
from typing import Dict, Any, Optional
from fastapi import APIRouter, Request, HTTPException, Header
from backend.app.channels.evolution import EvolutionChannel
from backend.app.channels.mock import MockChannel
from backend.app.cascade.orchestrator import cascade_orchestrator
from backend.app.config import settings

router = APIRouter(prefix="/api/webhooks", tags=["Webhooks"])

channel = EvolutionChannel() if settings.MESSAGING_CHANNEL == "evolution" else MockChannel()


@router.post("/evolution")
async def receive_evolution_webhook(
    request: Request,
    apikey: Optional[str] = Header(default=None, alias="apikey"),
    x_evolution_secret: Optional[str] = Header(default=None, alias="x-evolution-secret")
):
    provided_secret = apikey or x_evolution_secret
    expected_secret = settings.EVOLUTION_GLOBAL_API_KEY or settings.EVOLUTION_WEBHOOK_SECRET

    # Enforce constant-time comparison of shared secret header
    if not provided_secret or not expected_secret or not hmac.compare_digest(provided_secret.strip(), expected_secret.strip()):
        raise HTTPException(
            status_code=401,
            detail="Unauthorized webhook signature: missing or invalid shared-secret header."
        )

    raw_body = await request.json()
    headers = dict(request.headers)

    inbound = channel.parse_webhook_payload(raw_body, headers)
    if not inbound:
        return {"status": "ignored", "reason": "non_message_or_non_individual_event"}

    # Process message through FastAgent 4-stage cascade with message_id for deduplication
    res = await cascade_orchestrator.handle_message(
        user_id=inbound.user_phone_or_id,
        message_text=inbound.text,
        source_is_third_party=False,
        inbound_message_id=inbound.message_id
    )

    return {
        "status": "processed",
        "request_id": res.request_id,
        "intent": res.intent,
        "result_status": res.status,
        "response_text": res.response_text
    }
