"""Meta WhatsApp Business Cloud API router."""

import logging
from typing import Any, Dict, Optional
import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.config import get_settings
from app.database.session import get_db
from app.models.billing import Bill, Customer
from app.models.business import Business
from app.services.whatsapp_service import WhatsAppService

logger = logging.getLogger("business_ai_robot.whatsapp_api")
router = APIRouter()


class SendInvoiceWhatsAppRequest(BaseModel):
    invoice_id: str = Field(..., description="UUID or Invoice Number (e.g. INV-20260905-1025)")
    customer_id: Optional[str] = Field(None, description="Optional Customer UUID")
    recipient_phone: Optional[str] = Field(None, description="Optional override for recipient WhatsApp phone number")


class SendInvoiceWhatsAppResponse(BaseModel):
    status: str
    message: str
    invoice_number: str
    recipient: Optional[str] = None
    message_id: Optional[str] = None
    media_id: Optional[str] = None


@router.get("/status", summary="Check WhatsApp Business Cloud API configuration")
def get_whatsapp_status() -> Dict[str, Any]:
    """Check whether Meta WhatsApp credentials and template are configured."""
    settings = get_settings()
    has_token = bool(settings.WHATSAPP_ACCESS_TOKEN and settings.WHATSAPP_ACCESS_TOKEN.strip())
    has_phone_id = bool(settings.WHATSAPP_PHONE_NUMBER_ID and settings.WHATSAPP_PHONE_NUMBER_ID.strip())

    return {
        "configured": bool(has_token and has_phone_id),
        "access_token_configured": has_token,
        "phone_number_id_configured": has_phone_id,
        "template_name": settings.WHATSAPP_TEMPLATE_NAME,
        "template_language": settings.WHATSAPP_TEMPLATE_LANGUAGE,
        "api_version": settings.WHATSAPP_API_VERSION,
        "default_country_code": settings.WHATSAPP_DEFAULT_COUNTRY_CODE,
    }


@router.post(
    "/send-invoice",
    response_model=SendInvoiceWhatsAppResponse,
    summary="Send generated invoice PDF to customer via Meta WhatsApp Business API",
)
async def send_invoice_whatsapp(
    req: SendInvoiceWhatsAppRequest,
    db: Session = Depends(get_db),
) -> SendInvoiceWhatsAppResponse:
    """
    Validate customer and invoice, generate/locate invoice PDF, and send
    via official Meta WhatsApp Business Cloud API utility template with document attachment.
    """
    raw_inv = req.invoice_id.strip()

    # 1. Lookup Bill by UUID or bill_number
    bill: Optional[Bill] = None
    try:
        inv_uuid = uuid.UUID(raw_inv)
        bill = db.query(Bill).filter(Bill.id == inv_uuid).first()
    except (ValueError, AttributeError):
        pass

    if not bill:
        bill = db.query(Bill).filter(Bill.bill_number.ilike(raw_inv)).first()

    if not bill:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Invoice '{raw_inv}' was not found in records.",
        )

    # 2. Check Customer
    customer: Optional[Customer] = bill.customer
    if req.customer_id:
        try:
            cust_uuid = uuid.UUID(req.customer_id.strip())
            specified_cust = db.query(Customer).filter(Customer.id == cust_uuid).first()
            if specified_cust:
                customer = specified_cust
        except Exception:
            pass

    # 3. Retrieve Business context
    business = db.query(Business).filter(Business.id == bill.business_id).first() if bill.business_id else db.query(Business).first()

    # 4. Dispatch WhatsApp Send
    res = await WhatsAppService.send_invoice_via_whatsapp(
        bill=bill,
        business=business,
        recipient_phone=req.recipient_phone or (customer.phone if customer else None),
    )

    if not res.success:
        logger.warning("WhatsApp sending failed for invoice %s: %s", bill.bill_number, res.error_message)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Failed to send invoice on WhatsApp: {res.error_message}",
        )

    return SendInvoiceWhatsAppResponse(
        status="success",
        message=f"Bill {bill.bill_number} sent successfully on WhatsApp.",
        invoice_number=bill.bill_number,
        recipient=res.recipient,
        message_id=res.message_id,
        media_id=res.media_id,
    )
