"""FastAgent Backend Configuration using Pydantic Settings."""
from typing import List
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore"
    )

    # Core App
    APP_ENV: str = "development"
    DEBUG: bool = True
    PORT: int = 8000
    SECRET_KEY: str = "fastagent_super_secret_development_key_32bytes_len!!"
    TOKEN_ENCRYPTION_KEY: str = "MDEyMzQ1Njc4OTAxMjM0NTY3ODkwMTIzNDU2Nzg5MDE="  # 32 bytes base64 encoded AES key
    CORS_ORIGINS: List[str] = [
        "http://localhost:5173",
        "http://localhost:3000",
        "http://localhost",
        "capacitor://localhost"
    ]

    # Database & Redis
    DATABASE_URL: str = "postgresql+asyncpg://fastagent:fastagent_dev_password@localhost:5432/fastagent"
    REDIS_URL: str = "redis://localhost:6379/0"

    # Laya Decision Layer
    LAYA_BASE_URL: str = "http://localhost:8001"
    LAYA_ROUTER_DEFAULT: str = "multilingual"
    LAYA_MIN_CONFIDENCE_THRESHOLD: float = 0.75
    USE_MOCK_DECISION: bool = False

    # LLM Providers
    DEFAULT_LLM_PROVIDER: str = "mock"  # gemini, ollama, mock
    GEMINI_API_KEY: str = ""
    OLLAMA_BASE_URL: str = "http://localhost:11434"
    OLLAMA_MODEL: str = "qwen2.5:7b-instruct"
    USE_MOCK_LLM: bool = False

    # Messaging Channels
    MESSAGING_CHANNEL: str = "mock"  # evolution, mock
    EVOLUTION_BASE_URL: str = "http://localhost:8080"
    EVOLUTION_GLOBAL_API_KEY: str = "evolution_dev_api_key_12345"
    EVOLUTION_INSTANCE_NAME: str = "fastagent-primary"
    EVOLUTION_WEBHOOK_SECRET: str = "webhook_secret_key_fastagent_2026"
    WHATSAPP_REQUIRE_REGISTRATION: bool = False  # Set True for strict pilot/production registration gate
    WHATSAPP_AUTHORIZED_NUMBERS: List[str] = ["*"]  # List of allowed phone numbers or ["*"] for public self-registration
    APP_WEB_URL: str = "http://localhost:5173"


    # Google OAuth
    GOOGLE_CLIENT_ID: str = ""
    GOOGLE_CLIENT_SECRET: str = ""
    GOOGLE_REDIRECT_URI: str = "http://localhost:8000/api/auth/google/callback"
    USE_MOCK_TOOLS: bool = False

    # Desktop Executor
    DESKTOP_SHARED_SECRET: str = "fastagent_desktop_secret_2026_dev"
    DESKTOP_HEARTBEAT_TIMEOUT_SECONDS: float = 30.0


settings = Settings()
