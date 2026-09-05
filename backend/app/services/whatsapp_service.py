"""Official Meta WhatsApp Business Cloud API integration service."""

import logging
import os
import re
from typing import Any, Dict, List, Optional
import httpx
from pydantic import BaseModel

from app.config import get_settings
from app.models.billing import Bill
from app.models.business import Business
from app.services.pdf_service import InvoicePDFService

logger = logging.getLogger("business_ai_robot.whatsapp")


class WhatsAppResult(BaseModel):
    """Result of WhatsApp API operation."""
    success: bool
    message_id: Optional[str] = None
    media_id: Optional[str] = None
    recipient: Optional[str] = None
    error_message: Optional[str] = None
    status_code: Optional[int] = None
    raw_response: Optional[Dict[str, Any]] = None


class WhatsAppService:
    """Official Meta WhatsApp Business Cloud API Client."""

    BASE_GRAPH_URL = "https://graph.facebook.com"

    @classmethod
    def normalize_phone_number(cls, phone: Optional[str], default_country_code: Optional[str] = None) -> str:
        """
        Normalize phone number to international E.164 without leading plus.
        Example: "+91 98765-43210" -> "919876543210".
        If 10 digits, prepend default country code (defaults to 91 for India).
        """
        if not phone:
            raise ValueError("Customer phone number is missing.")

        # Strip non-digits
        digits = re.sub(r"\D", "", phone.strip())
        if not digits:
            raise ValueError("Phone number contains no numeric digits.")

        settings = get_settings()
        country_code = default_country_code or getattr(settings, "WHATSAPP_DEFAULT_COUNTRY_CODE", "91")

        # 10-digit Indian/local mobile numbers
        if len(digits) == 10:
            return f"{country_code}{digits}"

        # 11-digit numbers starting with 0 (e.g. 09876543210)
        if len(digits) == 11 and digits.startswith("0"):
            return f"{country_code}{digits[1:]}"

        # 12-digit number already starting with country code 91
        if len(digits) == 12 and digits.startswith(country_code):
            return digits

        # International E.164 length is between 10 and 15 digits
        if 10 <= len(digits) <= 15:
            return digits

        raise ValueError(f"Invalid phone number length ({len(digits)} digits): '{phone}'")

    @classmethod
    def format_item_list_for_template(cls, bill: Bill) -> str:
        """
        Format bill line items for template variable {{4}}.
        Example:
        2 × Tea — ₹40.00
        1 × Sandwich — ₹80.00
        """
        lines = []
        for item in bill.items:
            name = item.product.name if item.product else "Item"
            qty = f"{float(item.quantity):.0f}" if float(item.quantity).is_integer() else f"{float(item.quantity):.1f}"
            lines.append(f"{qty} × {name} (₹{float(item.total_price):.2f})")
        return ", ".join(lines) if lines else "Products purchased"

    @classmethod
    async def upload_pdf_media(
        cls,
        pdf_path: str,
        phone_number_id: str,
        access_token: str,
        api_version: str = "v21.0",
    ) -> Optional[str]:
        """
        Upload invoice PDF to Meta Graph API media endpoint.
        Returns the Meta media ID if successful.
        """
        if not os.path.isfile(pdf_path):
            raise FileNotFoundError(f"Invoice PDF file not found at {pdf_path}")

        url = f"{cls.BASE_GRAPH_URL}/{api_version}/{phone_number_id}/media"
        headers = {"Authorization": f"Bearer {access_token}"}
        filename = os.path.basename(pdf_path)

        with open(pdf_path, "rb") as f:
            file_bytes = f.read()

        files = {
            "file": (filename, file_bytes, "application/pdf"),
        }
        data = {
            "messaging_product": "whatsapp",
            "type": "application/pdf",
        }

        async with httpx.AsyncClient(timeout=20.0) as client:
            resp = await client.post(url, headers=headers, data=data, files=files)
            if resp.status_code in (200, 201):
                res_data = resp.json()
                media_id = res_data.get("id")
                logger.info("Successfully uploaded invoice PDF to Meta media: %s", media_id)
                return media_id
            else:
                logger.error("Meta media upload failed with HTTP %s: %s", resp.status_code, resp.text)
                raise RuntimeError(f"Meta media upload failed (HTTP {resp.status_code}): {resp.text}")

    @classmethod
    async def send_invoice_via_whatsapp(
        cls,
        bill: Bill,
        business: Optional[Business] = None,
        recipient_phone: Optional[str] = None,
        custom_pdf_path: Optional[str] = None,
    ) -> WhatsAppResult:
        """
        Complete official Meta WhatsApp Cloud API invoice sending pipeline:
        1. Validates recipient phone number.
        2. Generates / verifies the PDF invoice.
        3. Uploads PDF to Meta Media endpoint.
        4. Sends the approved Utility WhatsApp Template with document header and variables.
        """
        settings = get_settings()
        token = settings.WHATSAPP_ACCESS_TOKEN.strip()
        phone_id = settings.WHATSAPP_PHONE_NUMBER_ID.strip()
        template_name = settings.WHATSAPP_TEMPLATE_NAME or "invoice_bill"
        language_code = settings.WHATSAPP_TEMPLATE_LANGUAGE or "en"
        api_version = settings.WHATSAPP_API_VERSION or "v21.0"

        # Check credentials
        if not token:
            logger.warning("WhatsApp sending skipped: WHATSAPP_ACCESS_TOKEN is not configured.")
            return WhatsAppResult(
                success=False,
                error_message="Meta WhatsApp access token is not configured. Please set WHATSAPP_ACCESS_TOKEN.",
            )

        if not phone_id:
            logger.warning("WhatsApp sending skipped: WHATSAPP_PHONE_NUMBER_ID is not configured.")
            return WhatsAppResult(
                success=False,
                error_message="Meta WhatsApp Phone Number ID is not configured. Please set WHATSAPP_PHONE_NUMBER_ID.",
            )

        # 1. Resolve & normalize phone number
        raw_phone = recipient_phone or (bill.customer.phone if bill.customer else None)
        try:
            recipient = cls.normalize_phone_number(raw_phone)
        except ValueError as ve:
            logger.warning("Invalid phone number for bill %s: %s", bill.bill_number, ve)
            return WhatsAppResult(
                success=False,
                recipient=raw_phone,
                error_message=str(ve),
            )

        # 2. Generate or locate PDF invoice
        pdf_path = custom_pdf_path
        if not pdf_path or not os.path.isfile(pdf_path):
            try:
                pdf_path = InvoicePDFService.generate_invoice_pdf(bill=bill, business=business)
            except Exception as pe:
                logger.error("Failed to generate PDF for bill %s: %s", bill.bill_number, pe, exc_info=True)
                return WhatsAppResult(
                    success=False,
                    recipient=recipient,
                    error_message=f"Failed to generate invoice PDF: {pe}",
                )

        # 3. Upload PDF Media to Meta
        media_id = None
        try:
            media_id = await cls.upload_pdf_media(
                pdf_path=pdf_path,
                phone_number_id=phone_id,
                access_token=token,
                api_version=api_version,
            )
        except Exception as me:
            logger.error("Error uploading media to Meta: %s", me)
            return WhatsAppResult(
                success=False,
                recipient=recipient,
                error_message=f"Meta media upload failed: {me}",
            )

        # 4. Prepare Template Payload
        customer_name = bill.customer.name if bill.customer else "Valued Customer"
        biz_name = business.name if business else "Business AI Robot Store"
        formatted_items = cls.format_item_list_for_template(bill)
        final_total = f"{float(bill.total_amount):.2f}"

        def _clean_param(val: Any) -> str:
            cleaned = re.sub(r"[\r\n\t]+", " ", str(val or "")).strip()
            return re.sub(r" {2,}", " ", cleaned)

        components = [
            {
                "type": "header",
                "parameters": [
                    {
                        "type": "document",
                        "document": {
                            "id": media_id,
                            "filename": f"Invoice_{bill.bill_number}.pdf",
                        },
                    }
                ],
            },
            {
                "type": "body",
                "parameters": [
                    {"type": "text", "text": _clean_param(customer_name)},
                    {"type": "text", "text": _clean_param(biz_name)},
                    {"type": "text", "text": _clean_param(bill.bill_number)},
                    {"type": "text", "text": _clean_param(formatted_items)},
                    {"type": "text", "text": _clean_param(final_total)},
                ],
            },
        ]

        payload = {
            "messaging_product": "whatsapp",
            "recipient_type": "individual",
            "to": recipient,
            "type": "template",
            "template": {
                "name": template_name,
                "language": {"code": language_code},
                "components": components,
            },
        }

        # 5. Send Template Message to Meta API
        url = f"{cls.BASE_GRAPH_URL}/{api_version}/{phone_id}/messages"
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        }

        try:
            async with httpx.AsyncClient(timeout=20.0) as client:
                resp = await client.post(url, headers=headers, json=payload)
                resp_json = resp.json() if resp.content else {}

                # Fallback: if template in Meta does not have a header, retry with body only
                if resp.status_code != 200:
                    err_info = resp_json.get("error", {})
                    err_details = str(err_info.get("error_data", {}).get("details", ""))
                    if "header:" in err_details or "does not contain title component" in err_details:
                        logger.info("Template has no header component in Meta; retrying with body only...")
                        body_only_payload = dict(payload)
                        body_only_payload["template"] = dict(payload["template"])
                        body_only_payload["template"]["components"] = [
                            c for c in components if c.get("type") != "header"
                        ]
                        resp = await client.post(url, headers=headers, json=body_only_payload)
                        resp_json = resp.json() if resp.content else {}

                        # If template succeeded and we have a generated PDF media_id, dispatch document
                        if resp.status_code in (200, 201) and media_id:
                            try:
                                doc_payload = {
                                    "messaging_product": "whatsapp",
                                    "recipient_type": "individual",
                                    "to": recipient,
                                    "type": "document",
                                    "document": {
                                        "id": media_id,
                                        "filename": f"Invoice_{bill.bill_number}.pdf",
                                        "caption": f"Invoice #{bill.bill_number}",
                                    },
                                }
                                await client.post(url, headers=headers, json=doc_payload)
                                logger.info("Successfully dispatched follow-up PDF document to %s", recipient)
                            except Exception as de:
                                logger.warning("Follow-up PDF document send warning: %s", de)

                if resp.status_code in (200, 201):
                    messages = resp_json.get("messages", [])
                    msg_id = messages[0].get("id") if messages else None
                    logger.info("WhatsApp invoice sent successfully to %s: wamid=%s", recipient, msg_id)
                    return WhatsAppResult(
                        success=True,
                        message_id=msg_id,
                        media_id=media_id,
                        recipient=recipient,
                        status_code=resp.status_code,
                        raw_response=resp_json,
                    )
                else:
                    err_info = resp_json.get("error", {})
                    err_msg = err_info.get("message") or resp.text
                    err_code = err_info.get("code")
                    logger.error("Meta WhatsApp API error (HTTP %s, code %s): %s", resp.status_code, err_code, err_msg)
                    return WhatsAppResult(
                        success=False,
                        recipient=recipient,
                        status_code=resp.status_code,
                        error_message=f"Meta WhatsApp API error (code {err_code}): {err_msg}",
                        raw_response=resp_json,
                    )

        except Exception as ex:
            logger.error("Exception connecting to Meta WhatsApp API: %s", ex, exc_info=True)
            return WhatsAppResult(
                success=False,
                recipient=recipient,
                error_message=f"Network error communicating with Meta WhatsApp API: {ex}",
            )
