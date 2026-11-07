"""FastAPI router for transactional outbox dispatch, status queries, and delivery receipts."""
from typing import Optional, Dict, Any
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field
from backend.app.db.repository import repository
from backend.app.broker.outbox import outbox_broker

router = APIRouter(prefix="/api/outbox", tags=["Transactional Outbox"])


class OutboxPublishRequest(BaseModel):
    batch_size: int = Field(20, ge=1, le=100, description="Maximum number of outbox events to dispatch")


class DeliveryAcknowledgeRequest(BaseModel):
    idempotency_key: str = Field(..., description="Idempotency key of the outbound event")
    provider_message_id: Optional[str] = Field(None, description="Gateway or WhatsApp assigned message ID")
    delivered_at: Optional[str] = Field(None, description="Timestamp of delivery")


@router.post("/publish")
async def publish_outbox_batch(req: Optional[OutboxPublishRequest] = None):
    """Processes and dispatches pending outbox events with exponential backoff and DLQ routing."""
    batch_size = req.batch_size if req else 20
    res = await outbox_broker.dispatch_pending_batch(batch_size=batch_size)
    return {
        "status": "success",
        "results": res
    }


@router.post("/acknowledge")
async def acknowledge_delivery(req: DeliveryAcknowledgeRequest):
    """Acknowledge outbound message receipt from gateway (e.g. WhatsApp / Baileys)."""
    updated = await repository.mark_outbox_event_delivered(
        idempotency_key_or_id=req.idempotency_key,
        provider_message_id=req.provider_message_id
    )
    if not updated:
        raise HTTPException(
            status_code=404,
            detail=f"Outbox event with key/id '{req.idempotency_key}' not found"
        )
    return {
        "status": "acknowledged",
        "idempotency_key": req.idempotency_key,
        "event_status": updated["status"],
        "delivered_at": updated.get("delivered_at")
    }


@router.get("/status/{idempotency_key}")
async def get_outbox_status(idempotency_key: str, tenant_id: Optional[str] = Query(None)):
    """Retrieves current delivery status and lifecycle stage of an outbound event."""
    t_id = tenant_id or "tenant_default_duit"
    evt = await repository.get_outbox_event_by_idempotency_key(
        tenant_id=t_id,
        idempotency_key=idempotency_key
    )
    if not evt:
        # Fallback check across store if default tenant not matched
        for e in repository.outbox_store:
            if e.get("idempotency_key") == idempotency_key or e.get("id") == idempotency_key:
                evt = e
                break

    if not evt:
        raise HTTPException(
            status_code=404,
            detail=f"Outbox event '{idempotency_key}' not found"
        )

    return {
        "status": "success",
        "event_id": evt["id"],
        "tenant_id": evt["tenant_id"],
        "aggregate_type": evt["aggregate_type"],
        "aggregate_id": evt["aggregate_id"],
        "event_type": evt["event_type"],
        "lifecycle_status": evt["status"],
        "retry_count": evt["retry_count"],
        "error_message": evt.get("error_message"),
        "created_at": evt.get("created_at"),
        "published_at": evt.get("published_at"),
        "delivered_at": evt.get("delivered_at")
    }

