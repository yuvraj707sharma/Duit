"""Base Tool with mandatory Idempotency Tracking."""
from abc import ABC, abstractmethod
from typing import Dict, Any, Optional
from pydantic import BaseModel, Field


class ToolResult(BaseModel):
    success: bool
    data: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
    cached: bool = False


class BaseTool(ABC):
    def __init__(self):
        # In-memory idempotency cache (keyed by user_id:idempotency_key)
        self._idempotency_cache: Dict[str, ToolResult] = {}

    def get_cached_result(self, user_id: str, idempotency_key: str) -> Optional[ToolResult]:
        cache_key = f"{user_id}:{idempotency_key}"
        if cache_key in self._idempotency_cache:
            res = self._idempotency_cache[cache_key]
            return ToolResult(
                success=res.success,
                data=res.data,
                error=res.error,
                cached=True
            )
        return None

    def store_cached_result(self, user_id: str, idempotency_key: str, result: ToolResult):
        cache_key = f"{user_id}:{idempotency_key}"
        self._idempotency_cache[cache_key] = result

    @abstractmethod
    async def execute(self, user_id: str, payload: Dict[str, Any]) -> ToolResult:
        """Executes the tool with arguments."""
        pass
