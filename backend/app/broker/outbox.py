"""Transactional Outbox Broker: durable, at-least-once message dispatch with exponential backoff and DLQ routing."""
import logging
from typing import Optional, Dict, Any, List
from datetime import datetime, timezone
from backend.app.db.repository import repository, DatabaseRepository

logger = logging.getLogger(__name__)


class OutboxBroker:
    """Manages transactional outbox events: polling, dispatching, retries, and delivery tracking."""

    def __init__(self, repo: Optional[DatabaseRepository] = None, messaging_channel: Optional[Any] = None):
        self.repo = repo or repository
        self.messaging_channel = messaging_channel

    async def enqueue_outbound_message(
        self,
        tenant_id: str,
        whatsapp_account_id: str,
        recipient: str,
        text: str,
        idempotency_key: str,
        metadata: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """Enqueues an outbound WhatsApp message in the transactional outbox before dispatch."""
        payload = {
            "whatsapp_account_id": whatsapp_account_id,
            "recipient": recipient,
            "text": text,
            "metadata": metadata or {}
        }
        return await self.repo.create_outbox_event(
            tenant_id=tenant_id,
            aggregate_type="whatsapp_message",
            aggregate_id=whatsapp_account_id,
            event_type="outbound_message_requested",
            payload=payload,
            idempotency_key=idempotency_key
        )

    async def dispatch_pending_batch(self, batch_size: int = 20) -> Dict[str, Any]:
        """Polls ready events from outbox, dispatches to target channel, and handles retries / DLQ."""
        events = await self.repo.fetch_pending_outbox_events(limit=batch_size)
        published_count = 0
        failed_count = 0
        dead_letter_count = 0

        for evt in events:
            eid = evt["id"]
            current_retries = evt.get("retry_count", 0)
            try:
                # Dispatch if messaging channel is wired
                if self.messaging_channel and evt.get("event_type") == "outbound_message_requested":
                    pl = evt.get("payload", {})
                    recipient = pl.get("recipient")
                    text = pl.get("text")
                    if recipient and text:
                        await self.messaging_channel.send_text(recipient, text)

                # Mark successfully published
                updated = await self.repo.mark_outbox_event_published(eid)
                if updated:
                    published_count += 1
            except Exception as e:
                err_msg = str(e)
                backoff_sec = min(300, (2 ** current_retries) * 5)
                updated = await self.repo.mark_outbox_event_failed(
                    event_id=eid,
                    error_message=err_msg,
                    backoff_seconds=backoff_sec
                )
                if updated and updated.get("status") == "dead_letter":
                    dead_letter_count += 1
                else:
                    failed_count += 1
                logger.error("Outbox dispatch failed for event %s: %s (retries: %s)", eid, err_msg, current_retries)

        return {
            "processed": len(events),
            "published": published_count,
            "failed": failed_count,
            "dead_letter": dead_letter_count
        }


outbox_broker = OutboxBroker()

