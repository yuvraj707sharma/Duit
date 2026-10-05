"""Local Ollama Provider (Qwen 2.5) with Structured JSON Output."""
import json
from typing import Dict, Any, Optional
import httpx
from backend.app.llm.base import LLMProvider, ExtractionResult
from backend.app.config import settings


class OllamaProvider(LLMProvider):
    def __init__(self, base_url: Optional[str] = None, model: Optional[str] = None):
        self.base_url = (base_url or settings.OLLAMA_BASE_URL).rstrip("/")
        self.model = model or settings.OLLAMA_MODEL

    async def extract_arguments(
        self,
        user_message: str,
        intent: str,
        schema: Dict[str, Any],
        context: Optional[Dict[str, Any]] = None
    ) -> ExtractionResult:
        prompt = f"""
Extract parameters for intent '{intent}' as valid JSON matching schema:
{json.dumps(schema, indent=2)}

User request: {user_message}
Output JSON only:
"""
        payload = {
            "model": self.model,
            "prompt": prompt,
            "format": "json",
            "stream": False
        }
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                res = await client.post(f"{self.base_url}/api/generate", json=payload)
                if res.status_code == 200:
                    resp_json = res.json()
                    response_text = resp_json.get("response", "{}")
                    parsed = json.loads(response_text)
                    return ExtractionResult(success=True, arguments=parsed, raw_response=response_text)
                return ExtractionResult(success=False, arguments={}, error=f"Ollama returned HTTP {res.status_code}")
        except Exception as e:
            return ExtractionResult(success=False, arguments={}, error=str(e))
