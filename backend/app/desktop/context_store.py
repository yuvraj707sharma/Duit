"""Desktop Context Store: Encrypted at rest, sanitized history (never stores passwords, typed text, or screens)."""
import os
import json
import time
import logging
from typing import Dict, Any, List, Optional
from backend.app.security.crypto import encrypt_token, decrypt_token

logger = logging.getLogger(__name__)

# Sensitive keys that must NEVER be stored in context store
FORBIDDEN_KEYS = {"text", "typed_text", "password", "passcode", "secret", "screen", "screenshot", "content", "body"}


class ContextStore:
    def __init__(self, store_path: Optional[str] = None, user_id: str = "default_user"):
        self.user_id = user_id
        self.store_path = store_path or os.path.join(os.path.expanduser("~"), ".fastagent", "desktop_context.enc")
        os.makedirs(os.path.dirname(os.path.abspath(self.store_path)), exist_ok=True)
        self.max_operations = 20

    def _sanitize_operation(self, intent: str, args: Dict[str, Any], status: str) -> Dict[str, Any]:
        """Strips typed text, passwords, content bodies, and screen artifacts."""
        sanitized_args = {}
        for k, v in args.items():
            k_clean = k.lower()
            if any(forbidden in k_clean for forbidden in FORBIDDEN_KEYS):
                sanitized_args[k] = "[REDACTED_BY_SECURITY_POLICY]"
            elif isinstance(v, (str, int, float, bool)):
                sanitized_args[k] = v
            else:
                sanitized_args[k] = str(type(v).__name__)

        return {
            "intent": intent,
            "status": status,
            "timestamp": time.time(),
            "target": sanitized_args.get("app_name") or sanitized_args.get("url") or sanitized_args.get("title") or sanitized_args.get("query") or "local_desktop",
            "metadata": sanitized_args
        }

    def _load_raw(self) -> Dict[str, Any]:
        if not os.path.exists(self.store_path):
            return {"operations": [], "summary": "No recent operations."}
        try:
            with open(self.store_path, "r", encoding="utf-8") as f:
                encrypted_blob = f.read().strip()
            if not encrypted_blob:
                return {"operations": [], "summary": "No recent operations."}
            decrypted_json = decrypt_token(encrypted_blob, user_id=self.user_id)
            return json.loads(decrypted_json)
        except Exception as e:
            logger.warning("Could not decrypt context store (initializing fresh store): %s", e)
            return {"operations": [], "summary": "No recent operations."}

    def _save_raw(self, data: Dict[str, Any]) -> None:
        raw_json = json.dumps(data)
        encrypted_blob = encrypt_token(raw_json, user_id=self.user_id)
        with open(self.store_path, "w", encoding="utf-8") as f:
            f.write(encrypted_blob)

    def record_operation(self, intent: str, args: Dict[str, Any], status: str) -> None:
        """Appends sanitized operation, keeping only the last 20 operations and an updated summary."""
        sanitized = self._sanitize_operation(intent, args, status)
        data = self._load_raw()
        ops: List[Dict[str, Any]] = data.get("operations", [])
        ops.append(sanitized)
        if len(ops) > self.max_operations:
            ops = ops[-self.max_operations:]

        # Update rolling summary
        recent_intents = [op.get("intent") for op in ops[-5:]]
        summary = f"Last {len(ops)} operations. Recent actions: {', '.join(recent_intents)}."

        data["operations"] = ops
        data["summary"] = summary
        self._save_raw(data)

    def get_context(self) -> Dict[str, Any]:
        """Retrieves decrypted history of sanitized operations and summary."""
        return self._load_raw()

    def clear_history(self) -> Dict[str, Any]:
        """Securely clears all context history and writes empty encrypted store."""
        empty_data = {"operations": [], "summary": "Context history cleared by user."}
        self._save_raw(empty_data)
        return {"success": True, "message": "Context history cleared successfully."}


context_store = ContextStore()
