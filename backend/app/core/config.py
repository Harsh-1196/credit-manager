import os
from typing import Any

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    PROJECT_NAME: str = "SHG Credit Manager"
    API_V1_STR: str = "/api/v1"
    ENVIRONMENT: str = Field(default="development", description="development | testing | production")
    LOG_LEVEL: str = Field(default="INFO", description="DEBUG | INFO | WARNING | ERROR | CRITICAL")

    # Database
    DATABASE_URL: str = Field(
        default="postgresql+asyncpg://postgres:postgres@localhost:5432/shg_credit",
        description="Async database connection string",
    )
    DATABASE_POOL_SIZE: int = Field(default=10, ge=1)
    DATABASE_MAX_OVERFLOW: int = Field(default=20, ge=0)

    @field_validator("DATABASE_URL", mode="after")
    @classmethod
    def resolve_database_url(cls, v: str) -> str:
        if v.startswith("sqlite+aiosqlite:///"):
            prefix = "sqlite+aiosqlite:///"
            db_path = v[len(prefix):]
            if not os.path.isabs(db_path) and ":memory:" not in db_path:
                # Resolve relative to the backend directory
                backend_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
                target_path = os.path.join(backend_dir, os.path.basename(db_path))
                return f"{prefix}{target_path.replace(os.sep, '/')}"
        return v

    # Redis / Worker
    REDIS_URL: str = Field(
        default="redis://localhost:6379/0",
        description="Redis connection URL for ARQ worker and caching",
    )

    # Security
    SECRET_KEY: str = Field(
        default="phase0-development-insecure-secret-key-at-least-32-chars-long",
        description="JWT signature secret key",
    )
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = Field(default=15, ge=1)
    REFRESH_TOKEN_EXPIRE_DAYS: int = Field(default=7, ge=1)
    COOKIE_SECURE: bool = Field(default=False, description="Set True in production with HTTPS")
    COOKIE_SAMESITE: str = Field(default="strict", description="lax | strict | none")

    # CORS
    CORS_ORIGINS: list[str] = Field(
        default=[
            "http://localhost:5173",
            "http://127.0.0.1:5173",
            "http://localhost:3000",
            "http://127.0.0.1:3000",
        ],
        description="Allowed CORS origin URLs",
    )

    @field_validator("CORS_ORIGINS", mode="before")
    @classmethod
    def assemble_cors_origins(cls, v: Any) -> list[str]:
        if isinstance(v, str) and not v.startswith("["):
            return [i.strip() for i in v.split(",") if i.strip()]
        if isinstance(v, list):
            return [str(i) for i in v]
        return []

    # AI Assistant (Phase 6b)
    AI_PROVIDER: str = Field(default="gemini", description="gemini | openai | mock")
    GEMINI_API_KEY: str | None = Field(default=None, description="Google Gemini API key")
    OPENAI_API_KEY: str | None = Field(default=None, description="OpenAI API key")
    AI_MODEL: str = Field(default="gemini-1.5-flash", description="Target LLM model")
    AI_TIMEOUT_SECONDS: float = Field(default=30.0, description="HTTP timeout for AI calls")
    AI_MAX_RETRIES: int = Field(default=2, description="Max retry attempts for AI provider calls")

    model_config = SettingsConfigDict(
        env_file=(".env", "backend/.env", "../backend/.env"),
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=True,
    )


# Validated immediately at import time to ensure fail-fast configuration on startup
settings: Settings = Settings()
