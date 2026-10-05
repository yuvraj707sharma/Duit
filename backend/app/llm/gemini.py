"""Google Gemini Provider (Free Tier) with Structured JSON Output."""
import json
from typing import Dict, Any, Optional
from backend.app.llm.base import LLMProvider, ExtractionResult
from backend.app.config import settings


class GeminiProvider(LLMProvider):
    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or settings.GEMINI_API_KEY
        self.model = None
        if self.api_key:
            try:
                import google.generativeai as genai
                genai.configure(api_key=self.api_key)
                self.model = genai.GenerativeModel("gemini-1.5-flash")
            except ImportError:
                self.model = None

    async def extract_arguments(
        self,
        user_message: str,
        intent: str,
        schema: Dict[str, Any],
        context: Optional[Dict[str, Any]] = None
    ) -> ExtractionResult:
        if not self.model:
            return ExtractionResult(success=False, arguments={}, error="Gemini API Key not configured")

        prompt = f"""
You are an argument extractor. Extract the exact JSON tool parameters matching the schema below from the user's request.
Intent: {intent}
JSON Schema:
{json.dumps(schema, indent=2)}

User Request: {user_message}

Return ONLY valid JSON matching the schema. No markdown backticks, no conversation.
"""
        try:
            response = self.model.generate_content(prompt)
            text = response.text.strip()
            if text.startswith("```"):
                lines = text.splitlines()
                text = "\n".join(lines[1:-1] if lines[-1].startswith("```") else lines[1:])
            data = json.loads(text)
            return ExtractionResult(success=True, arguments=data, raw_response=text)
        except Exception as e:
            return ExtractionResult(success=False, arguments={}, error=str(e))
