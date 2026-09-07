"""Health check API endpoint."""

from typing import Dict, Optional
from datetime import datetime, timezone
from fastapi import APIRouter
from pydantic import BaseModel
from sqlalchemy import text

from app.config import get_settings
from app.database.session import engine

router = APIRouter()
settings = get_settings()


class HealthResponse(BaseModel):
    status: str
    service: str
    version: str
    environment: str
    database: str
    components: Optional[Dict[str, str]] = None
    timestamp: datetime


@router.get("/health", response_model=HealthResponse, tags=["health"])
async def get_health() -> HealthResponse:
    """Return backend service health, database connectivity, version, component status, and server timestamp."""
    db_status = "unconfigured"
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
            db_status = "connected"
    except Exception:
        db_status = "disconnected"

    components = {
        "api": "ready",
        "database": db_status,
        "gemini": "configured" if (settings.GEMINI_API_KEY and settings.GEMINI_API_KEY != "your-gemini-api-key-here") else "unconfigured",
        "groq_whisper": "configured" if settings.GROQ_API_KEY else "unconfigured",
        "edge_tts": "ready",
        "whatsapp": "configured" if (settings.WHATSAPP_ACCESS_TOKEN and settings.WHATSAPP_PHONE_NUMBER_ID) else "unconfigured",
    }

    return HealthResponse(
        status="ok",
        service=settings.PROJECT_NAME,
        version=settings.VERSION,
        environment=settings.ENVIRONMENT,
        database=db_status,
        components=components,
        timestamp=datetime.now(timezone.utc),
    )
