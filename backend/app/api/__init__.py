from fastapi import APIRouter
from app.api.admin import router as admin_router
from app.api.business import router as business_router
from app.api.health import router as health_router
from app.api.robots import router as robots_router
from app.api.security import router as security_router
from app.api.voice import router as voice_router
from app.api.whatsapp import router as whatsapp_router

api_router = APIRouter()

# Register routes
api_router.include_router(health_router, tags=["health"])
api_router.include_router(robots_router, prefix="/robots", tags=["robots"])
api_router.include_router(security_router, prefix="/security", tags=["security"])
api_router.include_router(voice_router, prefix="/voice", tags=["voice"])
api_router.include_router(business_router, tags=["business"])
api_router.include_router(whatsapp_router, prefix="/whatsapp", tags=["whatsapp"])
api_router.include_router(admin_router, tags=["admin"])

