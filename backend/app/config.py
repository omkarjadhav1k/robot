"""Application configuration module using pydantic-settings."""

from functools import lru_cache
from typing import List
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Configuration settings for Business AI Robot Backend."""

    # Project metadata
    PROJECT_NAME: str = "Business AI Robot"
    VERSION: str = "0.1.0"
    API_V1_STR: str = "/api/v1"
    ENVIRONMENT: str = "development"
    DEBUG: bool = True

    # Server binding
    HOST: str = "0.0.0.0"
    PORT: int = 8000

    # Security
    SECRET_KEY: str = "insecure-dev-secret-key-change-in-production"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24  # 24 hours

    # Database & Supabase
    DATABASE_URL: str = (
        "postgresql://robot_user:robot_password@localhost:5432/business_ai_robot"
    )
    SUPABASE_URL: str = ""
    SUPABASE_KEY: str = ""

    # Google Gemini AI
    GEMINI_API_KEY: str = ""
    GEMINI_MODEL: str = "gemini-3.7-flash"

    # Groq Whisper (Speech-to-Text)
    GROQ_API_KEY: str = ""
    GROQ_WHISPER_MODEL: str = "whisper-large-v3"

    # Edge TTS (Text-to-Speech)
    DEFAULT_TTS_VOICE: str = "en-IN-NeerjaNeural"
    HINDI_TTS_VOICE: str = "hi-IN-SwaraNeural"
    MARATHI_TTS_VOICE: str = "mr-IN-AarohiNeural"

    # Robot defaults & security
    DEFAULT_ROBOT_ID: str = "ROBOT-001"
    ROBOT_SHARED_SECRET: str = "insecure-dev-robot-secret"
    HEARTBEAT_TIMEOUT_SECONDS: int = 60

    # Localization
    DEFAULT_LANGUAGE: str = "en"
    AVAILABLE_LANGUAGES: List[str] = ["en", "hi", "mr"]

    # CORS
    CORS_ORIGINS: List[str] = ["*"]

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore",
    )


@lru_cache
def get_settings() -> Settings:
    """Cached settings singleton."""
    return Settings()
