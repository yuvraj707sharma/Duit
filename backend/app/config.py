"""FastAgent Backend Configuration using Pydantic Settings."""
import sys
import json
from typing import List, Set, Union
from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(".env", "backend/.env"),
        env_file_encoding="utf-8",
        extra="ignore"
    )

    # Core App
    APP_ENV: str = "development"
    DEBUG: bool = True
    PORT: int = 8000
    SECRET_KEY: str = "fastagent_super_secret_development_key_32bytes_len!!"
    TOKEN_ENCRYPTION_KEY: str = "MDEyMzQ1Njc4OTAxMjM0NTY3ODkwMTIzNDU2Nzg5MDE="  # 32 bytes base64 encoded AES key
    CORS_ORIGINS: Union[List[str], str] = [
        "http://localhost:5173",
        "http://localhost:3000",
        "http://localhost",
        "capacitor://localhost"
    ]

    @field_validator("CORS_ORIGINS")
    @classmethod
    def parse_cors_origins(cls, v: Union[str, List[str]]) -> List[str]:
        if isinstance(v, str):
            v = v.strip()
            if not v:
                return []
            if v.startswith("[") and v.endswith("]"):
                try:
                    return json.loads(v)
                except Exception:
                    pass
            return [origin.strip() for origin in v.split(",") if origin.strip()]
        return v

    # Database & Redis
    DATABASE_URL: str = "postgresql+asyncpg://fastagent:fastagent_dev_password@localhost:5432/fastagent"
    REDIS_URL: str = "redis://localhost:6379/0"

    # Laya Decision Layer
    LAYA_BASE_URL: str = "http://localhost:8001"
    LAYA_ROUTER_DEFAULT: str = "multilingual"
    LAYA_MIN_CONFIDENCE_THRESHOLD: float = 0.75
    USE_MOCK_DECISION: bool = False

    # LLM Providers
    DEFAULT_LLM_PROVIDER: str = "meta"  # meta, gemini, ollama, mock
    GEMINI_API_KEY: str = ""
    OLLAMA_BASE_URL: str = "http://localhost:11434"
    OLLAMA_MODEL: str = "qwen2.5:7b-instruct"
    USE_MOCK_LLM: bool = False

    # Meta Model API (Muse family: Wonder, Spark, Image, Voice Transcribe, SAM 3.1)
    MODEL_API_KEY: str = ""
    META_MODEL_API_KEY: str = ""
    META_MODEL_BASE_URL: str = "https://api.meta.ai/v1"
    META_DEFAULT_MODEL: str = "muse-spark-1.3"
    META_WONDER_MODEL: str = "muse-wonder-1.0"
    META_VOICE_MODEL: str = "muse-voice-transcribe-1.0"
    META_VISION_MODEL: str = "sam-3.1"
    META_MAX_TOKENS_PER_CALL: int = 400
    META_ENABLE_CACHE: bool = True

    @property
    def meta_api_key(self) -> str:
        return self.META_MODEL_API_KEY or self.MODEL_API_KEY

    # Messaging Channels
    MESSAGING_CHANNEL: str = "mock"  # evolution, mock
    EVOLUTION_BASE_URL: str = "http://localhost:8080"
    EVOLUTION_GLOBAL_API_KEY: str = "evolution_dev_api_key_12345"
    EVOLUTION_INSTANCE_NAME: str = "fastagent-primary"
    EVOLUTION_WEBHOOK_SECRET: str = "webhook_secret_key_fastagent_2026"
    WHATSAPP_REQUIRE_REGISTRATION: bool = False
    WHATSAPP_AUTHORIZED_NUMBERS: Union[List[str], str] = ["*"]  # In dev allows all, blocked in production
    APP_WEB_URL: str = "http://localhost:5173"

    @field_validator("WHATSAPP_AUTHORIZED_NUMBERS")
    @classmethod
    def parse_whatsapp_numbers(cls, v: Union[str, List[str]]) -> List[str]:
        if isinstance(v, str):
            v = v.strip()
            if not v:
                return []
            if v.startswith("[") and v.endswith("]"):
                try:
                    return json.loads(v)
                except Exception:
                    pass
            return [num.strip() for num in v.split(",") if num.strip()]
        return v

    # Google OAuth
    GOOGLE_CLIENT_ID: str = ""
    GOOGLE_CLIENT_SECRET: str = ""
    GOOGLE_REDIRECT_URI: str = "http://localhost:8000/api/auth/google/callback"
    USE_MOCK_TOOLS: bool = False

    # Desktop Executor
    DESKTOP_SHARED_SECRET: str = "fastagent_desktop_secret_2026_dev"
    DESKTOP_HEARTBEAT_TIMEOUT_SECONDS: float = 30.0

    # Internal gateway shared secret (server-to-server auth for /save-token, /whatsapp webhook, etc.)
    GATEWAY_SHARED_SECRET: str = "duit_gateway_secret_2026_dev"

    @property
    def is_production(self) -> bool:
        return self.APP_ENV.lower() in ("production", "prod", "staging")

    def validate_production_secrets(self) -> None:
        """Fail application startup immediately if insecure defaults or missing secrets are detected in production."""
        if not self.is_production:
            return

        insecure_defaults = {
            "SECRET_KEY": "fastagent_super_secret_development_key_32bytes_len!!",
            "TOKEN_ENCRYPTION_KEY": "MDEyMzQ1Njc4OTAxMjM0NTY3ODkwMTIzNDU2Nzg5MDE=",
            "EVOLUTION_GLOBAL_API_KEY": "evolution_dev_api_key_12345",
            "EVOLUTION_WEBHOOK_SECRET": "webhook_secret_key_fastagent_2026",
            "DESKTOP_SHARED_SECRET": "fastagent_desktop_secret_2026_dev",
            "GATEWAY_SHARED_SECRET": "duit_gateway_secret_2026_dev",
        }

        errors = []
        for name, bad_val in insecure_defaults.items():
            current_val = getattr(self, name, "")
            if not current_val:
                errors.append(f"{name} is missing")
            elif current_val == bad_val:
                errors.append(f"{name} is using insecure development default")

        if "*" in self.WHATSAPP_AUTHORIZED_NUMBERS:
            errors.append("WHATSAPP_AUTHORIZED_NUMBERS cannot contain wildcard '*' in production")

        if errors:
            msg = "\n".join(f" - {err}" for err in errors)
            print(f"FATAL PRODUCTION SECURITY VIOLATION:\n{msg}", file=sys.stderr)
            sys.exit(1)


settings = Settings()
settings.validate_production_secrets()
