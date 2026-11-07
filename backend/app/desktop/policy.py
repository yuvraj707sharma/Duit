"""Desktop Agent Local Policy Engine: enforces local boundary security, protected path restrictions, and tamper-evident HMAC signing."""
import json
import hmac
import hashlib
from typing import Dict, Any, Tuple, Optional, List

PROHIBITED_PATH_PATTERNS = [
    ".ssh",
    ".aws",
    ".env",
    "appdata/local/google/chrome/user data",
    "appdata/roaming/mozilla/firefox",
    "keychains",
    "credentials",
    "id_rsa",
    "id_ed25519",
    "wallet.dat",
    "/etc/shadow",
    "/etc/passwd",
    "sam",
    "system32/config"
]

PROHIBITED_ACTIONS = {
    "format_disk",
    "delete_system_file",
    "extract_passwords",
    "arbitrary_shell_exec",
    "dump_lsass",
    "kill_antivirus",
    "modify_registry_security"
}

DESTRUCTIVE_COMMAND_PATTERNS = [
    "rm -rf",
    "format c:",
    "del /f /s /q",
    "drop database",
    "shred",
    ":(){ :|:& };:"
]


class DesktopPolicyEngine:
    """Evaluates local OS actions before execution on the workstation."""

    def evaluate_local_action(self, action: str, arguments: Dict[str, Any]) -> Tuple[bool, Optional[str]]:
        """Evaluates whether an OS action is permitted to execute on the workstation."""
        action_clean = action.strip().lower()

        # 1. Prohibited capability check
        if action_clean in PROHIBITED_ACTIONS:
            return False, f"Action '{action}' is strictly prohibited by workstation safety policy"

        # 2. Inspect argument values recursively for restricted paths & destructive commands
        found_violation = self._inspect_arguments(arguments)
        if found_violation:
            return False, found_violation

        return True, None

    def _inspect_arguments(self, obj: Any) -> Optional[str]:
        if isinstance(obj, str):
            low = obj.lower().replace("\\", "/")
            for p in PROHIBITED_PATH_PATTERNS:
                if p in low:
                    return f"Access to sensitive path pattern '{p}' is blocked by desktop policy"
            for d in DESTRUCTIVE_COMMAND_PATTERNS:
                if d in low:
                    return f"Destructive command pattern '{d}' is blocked by desktop policy"
        elif isinstance(obj, dict):
            for v in obj.values():
                violation = self._inspect_arguments(v)
                if violation:
                    return violation
        elif isinstance(obj, (list, tuple, set)):
            for item in obj:
                violation = self._inspect_arguments(item)
                if violation:
                    return violation
        return None

    def validate_file_path(self, path: str) -> bool:
        """Validates that a file path does not access prohibited or sensitive locations."""
        return self._inspect_arguments(path) is None

    def validate_command(self, cmd: str) -> bool:
        """Validates that a command does not contain prohibited or destructive patterns."""
        return self._inspect_arguments(cmd) is None

    def hash_arguments(self, arguments: Dict[str, Any]) -> str:
        """Computes deterministic SHA256 digest of normalized arguments."""
        raw = json.dumps(arguments, sort_keys=True, separators=(",", ":")).encode("utf-8")
        return hashlib.sha256(raw).hexdigest()

    def sign_journal_entry(
        self,
        device_id: str,
        action: str,
        arguments_hash: str,
        secret_key: str
    ) -> str:
        """Signs journal entry using HMAC-SHA256 for tamper evidence."""
        message = f"{device_id}:{action}:{arguments_hash}".encode("utf-8")
        return hmac.new(secret_key.encode("utf-8"), message, hashlib.sha256).hexdigest()

    def verify_journal_entry(
        self,
        device_id: str,
        action: str,
        arguments_hash: str,
        signature: str,
        secret_key: str
    ) -> bool:
        """Verifies HMAC signature with constant-time comparison."""
        expected = self.sign_journal_entry(device_id, action, arguments_hash, secret_key)
        return hmac.compare_digest(expected, signature)


desktop_policy = DesktopPolicyEngine()
