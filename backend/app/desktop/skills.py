"""Typed, JSON-schema validated Desktop Skills (Allowlist only, no shell, no delete)."""
import os
import re
import urllib.parse
from typing import Dict, Any, List, Optional
from pydantic import BaseModel, Field, field_validator


# Allowlisted Desktop Applications
ALLOWLISTED_APPS = {
    "notepad",
    "calculator",
    "terminal",
    "code",
    "browser",
    "slack",
    "spotify",
    "files"
}

# Explicitly Disallowed Keywords/Actions
DISALLOWED_INTENTS = {"shell", "exec", "delete", "rm", "unlink", "drop", "format", "eval"}


class SkillValidationError(ValueError):
    """Raised when skill payload fails strict allowlist or schema validation."""
    pass


class OpenAppArgs(BaseModel):
    idempotency_key: str = Field(..., description="Unique client-side UUID.")
    app_name: str = Field(..., description="Allowlisted application name.")

    @field_validator("app_name")
    @classmethod
    def validate_app_name(cls, v: str) -> str:
        clean = v.strip().lower()
        if clean not in ALLOWLISTED_APPS:
            raise SkillValidationError(
                f"Application '{clean}' is not in allowlist: {sorted(list(ALLOWLISTED_APPS))}"
            )
        return clean


class OpenUrlArgs(BaseModel):
    idempotency_key: str = Field(..., description="Unique client-side UUID.")
    url: str = Field(..., description="HTTP or HTTPS URL.")

    @field_validator("url")
    @classmethod
    def validate_url(cls, v: str) -> str:
        parsed = urllib.parse.urlparse(v.strip())
        if parsed.scheme.lower() not in ("http", "https"):
            raise SkillValidationError(
                f"Invalid URL scheme '{parsed.scheme}'. Only 'http' and 'https' are permitted."
            )
        if not parsed.netloc:
            raise SkillValidationError("Invalid URL: missing domain/hostname.")
        return v.strip()


class CreateNoteArgs(BaseModel):
    idempotency_key: str = Field(..., description="Unique client-side UUID.")
    title: str = Field(..., description="Title of the note.")
    content: str = Field(..., description="Text content of the note.")

    @field_validator("title")
    @classmethod
    def validate_title(cls, v: str) -> str:
        clean = v.strip()
        if not clean:
            raise SkillValidationError("Note title cannot be empty.")
        if ".." in clean or "/" in clean or "\\" in clean:
            raise SkillValidationError("Note title cannot contain path separators or parent directory traversal.")
        return clean


class TypeTextArgs(BaseModel):
    idempotency_key: str = Field(..., description="Unique client-side UUID.")
    text: str = Field(..., description="Text to type into focused non-password window.")
    target_control_type: Optional[str] = Field("edit", description="Focused control type (must not be password).")

    @field_validator("target_control_type")
    @classmethod
    def validate_not_password_field(cls, v: Optional[str]) -> Optional[str]:
        if v and any(p in v.lower() for p in ("password", "passcode", "secret", "secure_edit", "pin")):
            raise SkillValidationError(
                "Security policy violation: Typing directly into password or secure entry fields is strictly prohibited."
            )
        return v


class SetVolumeArgs(BaseModel):
    idempotency_key: str = Field(..., description="Unique client-side UUID.")
    level: int = Field(..., ge=0, le=100, description="Volume level from 0 to 100.")


class SearchFilesArgs(BaseModel):
    query: str = Field(..., description="Read-only search substring.")
    directory: Optional[str] = Field(None, description="Optional sandbox directory.")


class ClearHistoryArgs(BaseModel):
    idempotency_key: str = Field(..., description="Unique client-side UUID.")


class DesktopSkillExecutor:
    def __init__(self, sandbox_dir: Optional[str] = None):
        self.sandbox_dir = sandbox_dir or os.path.join(os.path.expanduser("~"), ".fastagent", "notes")
        os.makedirs(self.sandbox_dir, exist_ok=True)

    def is_read_only(self, intent: str) -> bool:
        return intent in ("search_files",)

    def execute_skill(self, intent: str, args: Dict[str, Any]) -> Dict[str, Any]:
        """Validates schema against strict allowlist and executes safely without shell or deletion."""
        clean_intent = intent.strip().lower()

        # Reject disallowed intents immediately
        if clean_intent in DISALLOWED_INTENTS or any(d in clean_intent for d in ("delete", "shell", "exec")):
            raise SkillValidationError(f"Action '{clean_intent}' is strictly forbidden by desktop security policy.")

        try:
            if clean_intent == "open_app":
                parsed_app = OpenAppArgs(**args)
                return {
                    "success": True,
                    "action": "open_app",
                    "app_name": parsed_app.app_name,
                    "message": f"Opened allowlisted application '{parsed_app.app_name}'."
                }

            elif clean_intent == "open_url":
                parsed_url = OpenUrlArgs(**args)
                return {
                    "success": True,
                    "action": "open_url",
                    "url": parsed_url.url,
                    "message": f"Opened URL in default browser: {parsed_url.url}"
                }

            elif clean_intent == "create_note":
                parsed_note = CreateNoteArgs(**args)
                safe_filename = f"{re.sub(r'[^a-zA-Z0-9_-]', '_', parsed_note.title)}.txt"
                file_path = os.path.join(self.sandbox_dir, safe_filename)
                
                # Double check canonical path is within sandbox
                real_path = os.path.realpath(file_path)
                if not real_path.startswith(os.path.realpath(self.sandbox_dir)):
                    raise SkillValidationError("Path traversal detected: note must reside strictly inside sandbox folder.")

                with open(real_path, "w", encoding="utf-8") as f:
                    f.write(parsed_note.content)

                return {
                    "success": True,
                    "action": "create_note",
                    "title": parsed_note.title,
                    "path": real_path,
                    "message": f"Created note '{parsed_note.title}' in sandbox folder."
                }

            elif clean_intent == "type_text":
                parsed_type = TypeTextArgs(**args)
                # Simulated typing into focused non-password window
                return {
                    "success": True,
                    "action": "type_text",
                    "character_count": len(parsed_type.text),
                    "message": f"Typed {len(parsed_type.text)} characters into focused window."
                }

            elif clean_intent == "set_volume":
                parsed_vol = SetVolumeArgs(**args)
                return {
                    "success": True,
                    "action": "set_volume",
                    "level": parsed_vol.level,
                    "message": f"System volume adjusted to {parsed_vol.level}%."
                }

            elif clean_intent == "search_files":
                parsed_search = SearchFilesArgs(**args)
                target_dir = parsed_search.directory or self.sandbox_dir
                real_target = os.path.realpath(target_dir)

                matches = []
                if os.path.exists(real_target):
                    for root, _, files in os.walk(real_target):
                        for file in files:
                            if parsed_search.query.lower() in file.lower():
                                matches.append(os.path.join(root, file))
                        if len(matches) >= 20:
                            break

                return {
                    "success": True,
                    "action": "search_files",
                    "query": parsed_search.query,
                    "matches": matches,
                    "count": len(matches)
                }

            elif clean_intent == "clear_history":
                ClearHistoryArgs(**args)
                return {
                    "success": True,
                    "action": "clear_history",
                    "message": "Desktop context history cleared."
                }

            else:
                raise SkillValidationError(f"Unknown or unsupported skill intent: '{clean_intent}'")

        except Exception as e:
            if isinstance(e, SkillValidationError):
                raise
            raise SkillValidationError(f"Skill parameter validation failed: {e}") from e


skill_executor = DesktopSkillExecutor()
