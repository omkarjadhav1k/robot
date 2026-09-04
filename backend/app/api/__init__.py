"""API router aggregator."""

from fastapi import APIRouter
from app.api.health import router as health_router
from app.api.robots import router as robots_router
from app.api.voice import router as voice_router

api_router = APIRouter()

# Register routes
api_router.include_router(health_router, tags=["health"])
api_router.include_router(robots_router, prefix="/robots", tags=["robots"])
api_router.include_router(voice_router, prefix="/voice", tags=["voice"])
