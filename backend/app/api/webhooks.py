"""Evolution Go WhatsApp Webhook Ingestion Endpoint with Constant-Time Shared Secret Auth."""
import hmac
from typing import Dict, Any, Optional
from pydantic import BaseModel, Field
from fastapi import APIRouter, Request, HTTPException, Header
from backend.app.channels.evolution import EvolutionChannel
from backend.app.channels.mock import MockChannel
from backend.app.cascade.orchestrator import cascade_orchestrator
from backend.app.config import settings

router = APIRouter(prefix="/api/webhooks", tags=["Webhooks"])

evolution_channel = EvolutionChannel()
outbound_channel = EvolutionChannel() if settings.MESSAGING_CHANNEL == "evolution" else MockChannel()


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

    inbound = evolution_channel.parse_webhook_payload(raw_body, headers)
    if not inbound:
        return {"status": "ignored", "reason": "non_message_or_non_individual_event"}


    # Whitelist Security Gate (protects against unauthorized external numbers)
    from backend.app.db.repository import repository
    phone = inbound.user_phone_or_id
    clean_phone = phone.strip().lstrip("+")
    is_whitelisted = (
        ("*" in settings.WHATSAPP_AUTHORIZED_NUMBERS and not settings.is_production) or
        clean_phone in settings.WHATSAPP_AUTHORIZED_NUMBERS or
        phone in settings.WHATSAPP_AUTHORIZED_NUMBERS
    )
    if not is_whitelisted:
        return {"status": "dropped", "reason": "unauthorized_phone_whitelist"}

    # Registration / Onboarding Gate
    if settings.WHATSAPP_REQUIRE_REGISTRATION:
        is_registered = await repository.is_user_registered(clean_phone)
        if not is_registered:
            onboarding_url = f"{settings.APP_WEB_URL}/connect?phone={clean_phone}"
            onboarding_msg = (
                f"Welcome to *DUIT*.\n\n"
                f"Your phone number (+{clean_phone}) is not yet connected.\n\n"
                f"Link here to connect your Google Calendar, Email, and Desktop apps:\n"
                f"{onboarding_url}\n\n"
                f"Once connected, you can manage your daily schedule, emails, and workstation instantly from here."
            )
            await outbound_channel.send_text(phone, onboarding_msg)
            return {
                "status": "onboarding_prompt_sent",
                "phone": clean_phone,
                "reason": "new_unregistered_user"
            }

    # Process message through 4-stage cascade with message_id for deduplication
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


class WhatsAppGatewayMessage(BaseModel):
    from_phone: str = Field(..., alias="from")
    text: str
    channel: Optional[str] = "whatsapp"
    idempotency_key: Optional[str] = None


@router.post("/whatsapp")
async def receive_whatsapp_gateway_message(
    payload: WhatsAppGatewayMessage,
    x_gateway_secret: Optional[str] = Header(default=None, alias="x-gateway-secret")
):
    """Direct webhook endpoint for DUIT WhatsApp bot gateway (Baileys). Requires gateway secret."""
    # Authenticate gateway-to-backend communication (strictly fail closed in production, no hardcoded secrets)
    if settings.is_production:
        if not settings.GATEWAY_SHARED_SECRET:
            raise HTTPException(status_code=503, detail="Gateway secret is not configured on backend")
        if not x_gateway_secret or not hmac.compare_digest(
            x_gateway_secret.strip(),
            settings.GATEWAY_SHARED_SECRET.strip()
        ):
            raise HTTPException(status_code=401, detail="Unauthorized: invalid or missing gateway secret")
    elif x_gateway_secret and settings.GATEWAY_SHARED_SECRET:
        if not hmac.compare_digest(x_gateway_secret.strip(), settings.GATEWAY_SHARED_SECRET.strip()):
            raise HTTPException(status_code=401, detail="Unauthorized: invalid gateway secret")

    clean_phone = payload.from_phone.strip().lstrip("+")
    if not clean_phone:
        raise HTTPException(status_code=400, detail="Invalid phone number.")

    from backend.app.db.repository import repository
    if not await repository.is_user_registered(clean_phone):
        await repository.register_user(phone=clean_phone)

    res = await cascade_orchestrator.handle_message(
        user_id=clean_phone,
        message_text=payload.text,
        source_is_third_party=False,
        inbound_message_id=payload.idempotency_key
    )

    return {
        "status": "processed",
        "reply": res.response_text,
        "text": res.response_text,
        "message": res.response_text,
        "intent": res.intent,
        "result_status": res.status,
        "request_id": res.request_id,
        "stage_latencies_ms": res.stage_latencies_ms
    }


class SessionStatePayload(BaseModel):
    session_id: str
    files: Dict[str, str]


@router.post("/session-state")
async def save_session_state(
    payload: SessionStatePayload,
    x_gateway_secret: Optional[str] = Header(default=None, alias="x-gateway-secret")
):
    if settings.is_production:
        if not settings.GATEWAY_SHARED_SECRET:
            raise HTTPException(status_code=503, detail="Gateway secret is not configured on backend")
        if not x_gateway_secret or not hmac.compare_digest(
            x_gateway_secret.strip(),
            settings.GATEWAY_SHARED_SECRET.strip()
        ):
            raise HTTPException(status_code=401, detail="Unauthorized")
    elif x_gateway_secret and settings.GATEWAY_SHARED_SECRET:
        if not hmac.compare_digest(x_gateway_secret.strip(), settings.GATEWAY_SHARED_SECRET.strip()):
            raise HTTPException(status_code=401, detail="Unauthorized")

    from backend.app.db.database import get_db, engine, Base
    from backend.app.db.models import WhatsAppSessionFile
    from sqlalchemy import select

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async for session in get_db():
        for filename, content in payload.files.items():
            stmt = select(WhatsAppSessionFile).where(
                WhatsAppSessionFile.session_id == payload.session_id,
                WhatsAppSessionFile.file_name == filename
            )
            res = await session.execute(stmt)
            existing = res.scalar_one_or_none()
            if existing:
                existing.file_content = content
            else:
                session.add(WhatsAppSessionFile(
                    session_id=payload.session_id,
                    file_name=filename,
                    file_content=content
                ))
        await session.commit()
        break

    return {"status": "ok", "saved_files": len(payload.files)}


@router.get("/session-state/{session_id}")
async def get_session_state(
    session_id: str,
    x_gateway_secret: Optional[str] = Header(default=None, alias="x-gateway-secret")
):
    if settings.is_production:
        if not settings.GATEWAY_SHARED_SECRET:
            raise HTTPException(status_code=503, detail="Gateway secret is not configured on backend")
        if not x_gateway_secret or not hmac.compare_digest(
            x_gateway_secret.strip(),
            settings.GATEWAY_SHARED_SECRET.strip()
        ):
            raise HTTPException(status_code=401, detail="Unauthorized")
    elif x_gateway_secret and settings.GATEWAY_SHARED_SECRET:
        if not hmac.compare_digest(x_gateway_secret.strip(), settings.GATEWAY_SHARED_SECRET.strip()):
            raise HTTPException(status_code=401, detail="Unauthorized")

    from backend.app.db.database import get_db, engine, Base
    from backend.app.db.models import WhatsAppSessionFile
    from sqlalchemy import select

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    files_dict = {}
    async for session in get_db():
        stmt = select(WhatsAppSessionFile).where(WhatsAppSessionFile.session_id == session_id)
        res = await session.execute(stmt)
        records = res.scalars().all()
        for rec in records:
            files_dict[rec.file_name] = rec.file_content
        break

    return {"status": "ok", "session_id": session_id, "files": files_dict}
