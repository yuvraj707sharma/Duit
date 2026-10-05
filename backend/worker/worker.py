"""Arq Background Worker for Async Jobs and Notifications."""
from typing import Dict, Any
from arq.connections import RedisSettings
from backend.app.config import settings
from backend.app.cascade.orchestrator import cascade_orchestrator


async def process_async_message(ctx: Dict[Any, Any], user_id: str, message_text: str, source_is_third_party: bool = False):
    """Processes incoming background messages."""
    return await cascade_orchestrator.handle_message(
        user_id=user_id,
        message_text=message_text,
        source_is_third_party=source_is_third_party
    )


class WorkerSettings:
    functions = [process_async_message]
    redis_settings = RedisSettings.from_dsn(settings.REDIS_URL)
