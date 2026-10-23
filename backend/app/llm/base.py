"""LLM Provider Interface for Structured Argument Extraction."""
from abc import ABC, abstractmethod
from typing import Dict, Any, Optional
from pydantic import BaseModel


class ExtractionResult(BaseModel):
    success: bool
    arguments: Dict[str, Any]
    raw_response: Optional[str] = None
    tokens_used: int = 0
    error: Optional[str] = None


class LLMProvider(ABC):
    @abstractmethod
    async def extract_arguments(
        self,
        user_message: str,
        intent: str,
        schema: Dict[str, Any],
        context: Optional[Dict[str, Any]] = None
    ) -> ExtractionResult:
        """Extracts structured tool arguments conforming to the JSON schema."""
        pass

    async def generate_response(
        self,
        system_prompt: str,
        user_message: str,
        context: Optional[Dict[str, Any]] = None
    ) -> str:
        """Generates conversational or task-specific response based on prompt."""
        return f"Processed request according to skill instructions:\n{user_message}"
