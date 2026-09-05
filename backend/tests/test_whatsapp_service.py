"""Unit tests for Meta WhatsApp Business Cloud API Service."""

from decimal import Decimal
import os
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from app.config import get_settings
from app.models.billing import Bill, BillItem, Customer, PaymentStatus
from app.models.business import Business
from app.models.product import Product
from app.services.whatsapp_service import WhatsAppResult, WhatsAppService


def test_normalize_phone_number_valid_formats():
    """Verify standard phone number normalization to E.164 without leading plus."""
    # 10 digits without country code -> prepends default 91
    assert WhatsAppService.normalize_phone_number("9876543210") == "919876543210"
    # Formatted with spaces and dashes
    assert WhatsAppService.normalize_phone_number("+91 98765-43210") == "919876543210"
    # Starting with 0 (11 digits)
    assert WhatsAppService.normalize_phone_number("09876543210") == "919876543210"
    # Already has 91 (12 digits)
    assert WhatsAppService.normalize_phone_number("919876543210") == "919876543210"
    # International number (e.g. US +1 415 555 2671)
    assert WhatsAppService.normalize_phone_number("+14155552671") == "14155552671"


def test_normalize_phone_number_invalid_inputs():
    """Verify invalid phone numbers raise ValueError with helpful messages."""
    with pytest.raises(ValueError, match="missing"):
        WhatsAppService.normalize_phone_number(None)

    with pytest.raises(ValueError, match="missing"):
        WhatsAppService.normalize_phone_number("")

    with pytest.raises(ValueError, match="no numeric digits"):
        WhatsAppService.normalize_phone_number("abcdef")

    with pytest.raises(ValueError, match="Invalid phone number length"):
        WhatsAppService.normalize_phone_number("12345")


def test_format_item_list_for_template(db_session):
    """Verify bill line items are cleanly formatted for template variable {{4}}."""
    biz = db_session.query(Business).first()
    p1 = Product(name="Chai", unit="cup", selling_price=Decimal("20.00"), current_stock=Decimal("100"), business_id=biz.id)
    p2 = Product(name="Sandwich", unit="pcs", selling_price=Decimal("80.00"), current_stock=Decimal("50"), business_id=biz.id)
    db_session.add_all([p1, p2])
    db_session.commit()

    bill = Bill(
        bill_number="INV-FMT-01",
        subtotal=Decimal("120"),
        total_amount=Decimal("120"),
        payment_status=PaymentStatus.PAID,
        business_id=biz.id,
    )
    db_session.add(bill)
    db_session.commit()

    i1 = BillItem(bill_id=bill.id, product_id=p1.id, quantity=Decimal("2.0"), unit_price=Decimal("20.00"), total_price=Decimal("40.00"))
    i2 = BillItem(bill_id=bill.id, product_id=p2.id, quantity=Decimal("1.0"), unit_price=Decimal("80.00"), total_price=Decimal("80.00"))
    db_session.add_all([i1, i2])
    db_session.commit()
    db_session.refresh(bill)

    formatted = WhatsAppService.format_item_list_for_template(bill)
    assert "2 × Chai — ₹40.00" in formatted
    assert "1 × Sandwich — ₹80.00" in formatted


@pytest.mark.asyncio
async def test_upload_pdf_media_success(tmp_path):
    """Verify successful media upload returns Meta media ID."""
    test_pdf = tmp_path / "dummy.pdf"
    test_pdf.write_bytes(b"%PDF-1.4 dummy content")

    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {"id": "meta_media_999888"}

    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
        mock_post.return_value = mock_resp
        media_id = await WhatsAppService.upload_pdf_media(
            pdf_path=str(test_pdf),
            phone_number_id="1234567890",
            access_token="test_token",
        )
        assert media_id == "meta_media_999888"
        mock_post.assert_called_once()


@pytest.mark.asyncio
async def test_send_invoice_via_whatsapp_missing_credentials(db_session):
    """Verify failure result when WHATSAPP_ACCESS_TOKEN is missing."""
    biz = db_session.query(Business).first()
    settings = get_settings()
    orig_token = settings.WHATSAPP_ACCESS_TOKEN
    try:
        settings.WHATSAPP_ACCESS_TOKEN = ""
        bill = Bill(
            bill_number="INV-NO-CREDS",
            total_amount=Decimal("100"),
            payment_status=PaymentStatus.PAID,
            business_id=biz.id,
        )
        db_session.add(bill)
        db_session.commit()

        res = await WhatsAppService.send_invoice_via_whatsapp(bill=bill)
        assert res.success is False
        assert "access token is not configured" in res.error_message
    finally:
        settings.WHATSAPP_ACCESS_TOKEN = orig_token


@pytest.mark.asyncio
async def test_send_invoice_via_whatsapp_end_to_end_mock(db_session, tmp_path):
    """Verify complete dispatch: upload PDF media + send template message with document header."""
    settings = get_settings()
    orig_token = settings.WHATSAPP_ACCESS_TOKEN
    orig_phone_id = settings.WHATSAPP_PHONE_NUMBER_ID
    try:
        settings.WHATSAPP_ACCESS_TOKEN = "EAABtest_token_123"
        settings.WHATSAPP_PHONE_NUMBER_ID = "phone_id_456"

        biz = db_session.query(Business).first()
        cust = Customer(name="Rahul", phone="9876543210", business_id=biz.id)
        db_session.add(cust)
        db_session.commit()

        p1 = Product(name="Chai", unit="cup", selling_price=Decimal("20.00"), current_stock=Decimal("100"), business_id=biz.id)
        p2 = Product(name="Sandwich", unit="pcs", selling_price=Decimal("80.00"), current_stock=Decimal("50"), business_id=biz.id)
        db_session.add_all([p1, p2])
        db_session.commit()

        bill = Bill(
            bill_number="INV-WA-001",
            customer_id=cust.id,
            business_id=biz.id,
            subtotal=Decimal("120.00"),
            tax_amount=Decimal("0.00"),
            discount_amount=Decimal("0.00"),
            total_amount=Decimal("120.00"),
            payment_status=PaymentStatus.PAID,
        )
        db_session.add(bill)
        db_session.commit()

        i1 = BillItem(bill_id=bill.id, product_id=p1.id, quantity=Decimal("2.0"), unit_price=Decimal("20.00"), total_price=Decimal("40.00"))
        i2 = BillItem(bill_id=bill.id, product_id=p2.id, quantity=Decimal("1.0"), unit_price=Decimal("80.00"), total_price=Decimal("80.00"))
        db_session.add_all([i1, i2])
        db_session.commit()
        db_session.refresh(bill)

        # Mock media upload and message send
        with patch.object(WhatsAppService, "upload_pdf_media", new_callable=AsyncMock) as mock_upload:
            mock_upload.return_value = "meta_media_invoice_01"

            mock_send_resp = MagicMock()
            mock_send_resp.status_code = 200
            mock_send_resp.json.return_value = {
                "messaging_product": "whatsapp",
                "contacts": [{"input": "919876543210", "wa_id": "919876543210"}],
                "messages": [{"id": "wamid.HBgMOTE5ODc2NTQzMjEwFQIAERgSMTQ1"}],
            }

            with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
                mock_post.return_value = mock_send_resp
                res = await WhatsAppService.send_invoice_via_whatsapp(bill=bill, business=biz)

                assert res.success is True
                assert res.message_id == "wamid.HBgMOTE5ODc2NTQzMjEwFQIAERgSMTQ1"
                assert res.recipient == "919876543210"
                assert res.media_id == "meta_media_invoice_01"

                # Verify payload sent to Meta
                mock_post.assert_called_once()
                call_kwargs = mock_post.call_args[1]
                payload = call_kwargs["json"]
                assert payload["messaging_product"] == "whatsapp"
                assert payload["to"] == "919876543210"
                assert payload["type"] == "template"
                assert payload["template"]["name"] == settings.WHATSAPP_TEMPLATE_NAME

                # Check header component has document with media id
                components = payload["template"]["components"]
                header_comp = next((c for c in components if c["type"] == "header"), None)
                assert header_comp is not None
                assert header_comp["parameters"][0]["type"] == "document"
                assert header_comp["parameters"][0]["document"]["id"] == "meta_media_invoice_01"

                # Check body component has 5 variables
                body_comp = next((c for c in components if c["type"] == "body"), None)
                assert body_comp is not None
                params = [p["text"] for p in body_comp["parameters"]]
                assert len(params) == 5
                assert params[0] == "Rahul"          # {{1}} Customer name
                assert params[1] == biz.name         # {{2}} Business name
                assert params[2] == "INV-WA-001"     # {{3}} Invoice number
                assert "2 × Chai" in params[3]       # {{4}} Item list
                assert params[4] == "120.00"         # {{5}} Total
    finally:
        settings.WHATSAPP_ACCESS_TOKEN = orig_token
        settings.WHATSAPP_PHONE_NUMBER_ID = orig_phone_id
