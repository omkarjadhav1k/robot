"""Security API endpoints for Owner PIN verification, PIN management, and audit log."""

import logging
from typing import Any, Dict, List, Optional
import uuid
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.database.session import get_db
from app.models.business import Business
from app.services.security_service import SecurityService

logger = logging.getLogger("max.api.security")

router = APIRouter()


class VerifyOwnerRequest(BaseModel):
    pin: str = Field(..., min_length=6, max_length=6, description="6-digit owner PIN")
    robot_id: Optional[str] = None
    action: Optional[str] = "OWNER_VERIFY"


class VerifyOwnerResponse(BaseModel):
    success: bool
    message: str
    auth_token: Optional[str] = None


class ChangePinRequest(BaseModel):
    old_pin: str = Field(..., min_length=6, max_length=6)
    new_pin: str = Field(..., min_length=6, max_length=6)
    robot_id: Optional[str] = None


class ChangePinResponse(BaseModel):
    success: bool
    message: str


def _get_default_business_id(db: Session) -> uuid.UUID:
    biz = db.query(Business).first()
    if not biz:
        biz = Business(name="Main Store", owner_name="Store Owner", business_type="Retail")
        db.add(biz)
        db.commit()
        db.refresh(biz)
    return biz.id


@router.post("/verify-owner", response_model=VerifyOwnerResponse, tags=["security"])
def verify_owner(req: VerifyOwnerRequest, db: Session = Depends(get_db)) -> VerifyOwnerResponse:
    """Verify owner 6-digit PIN and obtain a short-lived authorization token (5 min)."""
    biz_id = _get_default_business_id(db)
    success, message, token = SecurityService.verify_owner(
        db=db,
        business_id=biz_id,
        pin=req.pin,
        robot_id=req.robot_id,
        source_action=req.action or "OWNER_VERIFY",
    )
    if not success:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=message,
        )
    return VerifyOwnerResponse(success=True, message=message, auth_token=token)


@router.post("/change-pin", response_model=ChangePinResponse, tags=["security"])
def change_pin(req: ChangePinRequest, db: Session = Depends(get_db)) -> ChangePinResponse:
    """Change owner PIN after verifying existing PIN."""
    biz_id = _get_default_business_id(db)
    success, message = SecurityService.change_pin(
        db=db,
        business_id=biz_id,
        old_pin=req.old_pin,
        new_pin=req.new_pin,
        robot_id=req.robot_id,
    )
    if not success:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=message,
        )
    return ChangePinResponse(success=True, message=message)


@router.get("/events", tags=["security"])
def list_security_events(limit: int = 50, db: Session = Depends(get_db)) -> List[Dict[str, Any]]:
    """List recent security events and audit records."""
    biz_id = _get_default_business_id(db)
    return SecurityService.list_events(db=db, business_id=biz_id, limit=limit)
