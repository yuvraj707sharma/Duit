"""Meta Model API Provider (Muse Spark & Muse Wonder) with Token Conservation."""
import json
import hashlib
import logging
from typing import Dict, Any, Optional
from backend.app.llm.base import LLMProvider, ExtractionResult
from backend.app.config import settings

logger = logging.getLogger(__name__)


class MetaModelProvider(LLMProvider):
    """
    Official Meta Model API Adapter for the Muse family.
    - Uses 'muse-spark-1.3' for ultra-fast, cost-effective argument extraction & routing.
    - Uses 'muse-wonder-1.0' for complex long-horizon task planning when requested.
    - Built-in token conservation cache to avoid burning credits on repeated prompts.
    """

    def __init__(self, api_key: Optional[str] = None, base_url: Optional[str] = None):
        self.api_key = api_key or settings.meta_api_key
        self.base_url = (base_url or settings.META_MODEL_BASE_URL).rstrip("/")
        self.default_model = settings.META_DEFAULT_MODEL or "muse-spark-1.3"
        self.wonder_model = settings.META_WONDER_MODEL or "muse-wonder-1.0"
        self.max_tokens = settings.META_MAX_TOKENS_PER_CALL
        self.enable_cache = settings.META_ENABLE_CACHE
        self._cache: Dict[str, Any] = {}
        self.client = None

        if self.api_key:
            try:
                import openai
                self.client = openai.AsyncOpenAI(
                    base_url=self.base_url,
                    api_key=self.api_key,
                    timeout=25.0
                )
            except Exception as e:
                logger.warning("Optional AsyncOpenAI initialization: %s", e)
                self.client = None

    async def _call_api_direct(self, messages: list, temperature: float = 0.0, max_tokens: int = 800, json_mode: bool = False) -> str:
        """Direct HTTP caller for Meta Model API using httpx."""
        if not self.api_key:
            raise ValueError("No Meta Model API key configured")
        import httpx
        url = f"{self.base_url}/chat/completions"
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }
        payload = {
            "model": self.default_model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "reasoning_effort": "low"
        }
        if json_mode:
            payload["response_format"] = {"type": "json_object"}
        async with httpx.AsyncClient(timeout=25.0) as client:
            res = await client.post(url, headers=headers, json=payload)
            res.raise_for_status()
            data = res.json()
            return data["choices"][0]["message"]["content"] or ""

    def _cache_key(self, prefix: str, text: str, schema: Optional[Dict[str, Any]] = None) -> str:
        content = f"{prefix}:{text}:{json.dumps(schema or {}, sort_keys=True)}"
        return hashlib.sha256(content.encode("utf-8")).hexdigest()

    async def extract_arguments(
        self,
        user_message: str,
        intent: str,
        schema: Dict[str, Any],
        context: Optional[Dict[str, Any]] = None
    ) -> ExtractionResult:
        """Extracts structured tool parameters via Muse Spark with strict JSON output."""
        cache_k = self._cache_key(intent, user_message, schema)
        if self.enable_cache and cache_k in self._cache:
            cached_data, tokens = self._cache[cache_k]
            return ExtractionResult(success=True, arguments=cached_data, tokens_used=0, raw_response="[cached]")

        if not schema:
            from backend.app.cascade.schemas import get_schema_for_intent
            schema = get_schema_for_intent(intent)

        system_instruction = (
            f"You are DUIT's structured parameter extractor for the '{intent}' action.\n"
            f"Extract valid JSON arguments conforming to this schema:\n"
            f"{json.dumps(schema, separators=(',', ':'))}\n"
            "- For email (send_email / reply_email): ALWAYS generate professional subject and full body directly from the user's message context. NEVER use generic templates or placeholders like 'Quick Update'.\n"
            "- For desktop (open_app): Map 'microsoft edge', 'edge browser', 'ms edge' to app_name='msedge'. Map 'chrome', 'google chrome' to app_name='chrome'.\n"
            "- For browser actions (open_app / open_url): If the user specifies or mentions a profile (e.g. 'in my yuvraj profile', 'in college profile', 'in profile 4', 'kishan profile', 'work profile'), extract it into the 'profile' field.\n"
            "Return ONLY raw JSON with no markdown tags or conversational filler."
        )

        try:
            raw_text = ""
            tokens_used = 0
            try:
                raw_text = await self._call_api_direct(
                    messages=[
                        {"role": "system", "content": system_instruction},
                        {"role": "user", "content": user_message}
                    ],
                    temperature=0.0,
                    max_tokens=max(800, self.max_tokens),
                    json_mode=True
                )
            except Exception as directErr:
                if self.client:
                    response = await self.client.chat.completions.create(
                        model=self.default_model,
                        messages=[
                            {"role": "system", "content": system_instruction},
                            {"role": "user", "content": user_message}
                        ],
                        temperature=0.0,
                        max_tokens=max(800, self.max_tokens),
                        extra_body={"reasoning_effort": "low"},
                        response_format={"type": "json_object"} if hasattr(self.client.chat.completions, "create") else None
                    )
                    raw_text = response.choices[0].message.content or "{}"
                    tokens_used = getattr(response.usage, "total_tokens", 0) if response.usage else 0
                if not raw_text:
                    raise directErr

            # Strip any residual code fences
            clean_text = raw_text.strip()
            if clean_text.startswith("```"):
                lines = clean_text.splitlines()
                clean_text = "\n".join(lines[1:-1] if lines[-1].startswith("```") else lines[1:])

            parsed_args = json.loads(clean_text)

            # Defensive fallback / merge: If parsed_args is empty or missing critical keys, merge with deterministic parser
            from backend.app.llm.mock import MockLLMProvider
            fallback_mock = MockLLMProvider()
            if not parsed_args or (intent == "open_app" and not any(k in parsed_args for k in ("app_name", "app", "application", "name"))) or (intent == "open_url" and not any(k in parsed_args for k in ("url", "link", "website"))):
                fallback_res = await fallback_mock.extract_arguments(user_message, intent, schema, context)
                for k, v in fallback_res.arguments.items():
                    if k not in parsed_args or not parsed_args[k]:
                        parsed_args[k] = v

            # Normalize common fields
            if intent == "open_url" and "url" in parsed_args:
                url_val = str(parsed_args["url"]).strip()
                if url_val and "://" not in url_val:
                    parsed_args["url"] = f"https://{url_val}"
            elif intent == "open_app":
                app_val = str(parsed_args.get("app_name") or parsed_args.get("app") or parsed_args.get("name") or "").strip().rstrip(".!?,")
                if app_val:
                    parsed_args["app_name"] = app_val

            if self.enable_cache:
                self._cache[cache_k] = (parsed_args, tokens_used)

            return ExtractionResult(
                success=True,
                arguments=parsed_args,
                raw_response=raw_text,
                tokens_used=tokens_used
            )

        except Exception as e:
            logger.error("Meta Model API extraction error: %s. Using local fallback.", e)
            from backend.app.llm.mock import MockLLMProvider
            fallback = MockLLMProvider()
            res = await fallback.extract_arguments(user_message, intent, schema, context)
            res.error = f"Meta API fallback: {e}"
            return res

    async def generate_response(
        self,
        system_prompt: str,
        user_message: str,
        context: Optional[Dict[str, Any]] = None
    ) -> str:
        """Generates concise agent replies with strict token bounding."""
        cache_k = self._cache_key("gen", f"{system_prompt}:{user_message}")
        if self.enable_cache and cache_k in self._cache:
            return self._cache[cache_k][0]

        history_msgs = []
        if context and "history" in context:
            for item in context["history"]:
                if isinstance(item, dict) and "role" in item and "content" in item:
                    history_msgs.append({"role": item["role"], "content": item["content"]})

        call_messages = [
            {"role": "system", "content": f"{system_prompt}\nKeep responses warm, concise, and helpful like a trusted personal assistant. Strictly zero emojis."},
            *history_msgs,
            {"role": "user", "content": user_message}
        ]

        try:
            reply = ""
            try:
                reply = await self._call_api_direct(
                    messages=call_messages,
                    temperature=0.3,
                    max_tokens=max(800, self.max_tokens)
                )
            except Exception as directErr:
                if self.client:
                    response = await self.client.chat.completions.create(
                        model=self.default_model,
                        messages=call_messages,
                        temperature=0.3,
                        max_tokens=max(800, self.max_tokens),
                        extra_body={"reasoning_effort": "low"}
                    )
                    reply = response.choices[0].message.content or ""
                if not reply:
                    raise directErr

            if not reply:
                reply = "I am here and ready to help. What would you like to do?"
            
            # Strictly remove emojis to comply with formatting policy
            import re
            emoji_pattern = re.compile(
                "["
                "\U0001F600-\U0001F64F"
                "\U0001F300-\U0001F5FF"
                "\U0001F680-\U0001F6FF"
                "\U0001F1E0-\U0001F1FF"
                "\U00002702-\U000027B0"
                "\U000024C2-\U0001F251"
                "\U0001F900-\U0001F9FF"
                "\U0001FA70-\U0001FAFF"
                "]+", flags=re.UNICODE
            )
            reply = emoji_pattern.sub("", reply).strip()
            reply = re.sub(r'[\ufffd\u200b-\u200f\ufeff\xad]', '', reply).strip()

            if self.enable_cache:
                self._cache[cache_k] = (reply, 0)
            return reply

        except Exception as e:
            logger.error("Meta Model API generation error: %s", e)
            if settings.GEMINI_API_KEY:
                try:
                    from backend.app.llm.gemini import GeminiProvider
                    gemini_fallback = GeminiProvider()
                    return await gemini_fallback.generate_response(system_prompt, user_message, context)
                except Exception as gErr:
                    logger.error("Gemini fallback generation error: %s", gErr)
            from backend.app.llm.mock import MockLLMProvider
            mock_fallback = MockLLMProvider()
            return await mock_fallback.generate_response(system_prompt, user_message, context)

