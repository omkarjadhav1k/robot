"""Unit tests for WhatsApp REST API endpoints."""

from decimal import Decimal
from unittest.mock import AsyncMock, patch
from fastapi.testclient import TestClient

from app.models.billing import Bill, Customer, PaymentStatus
from app.models.business import Business
from app.services.whatsapp_service import WhatsAppResult


def test_whatsapp_status_endpoint(client: TestClient):
    """Verify /whatsapp/status returns configuration dictionary."""
    resp = client.get("/whatsapp/status")
    assert resp.status_code == 200
    data = resp.json()
    assert "configured" in data
    assert "template_name" in data
    assert "template_language" in data
    assert "api_version" in data


def test_send_invoice_whatsapp_api_not_found(client: TestClient):
    """Verify 404 response when invoice does not exist."""
    resp = client.post(
        "/whatsapp/send-invoice",
        json={"invoice_id": "INV-NONEXISTENT"},
    )
    assert resp.status_code == 404
    assert "not found" in resp.json()["detail"].lower()


def test_send_invoice_whatsapp_api_success(client: TestClient, db_session):
    """Verify 200 response when invoice exists and WhatsApp send succeeds."""
    biz = db_session.query(Business).first()
    cust = Customer(name="Rahul", phone="9876543210", business_id=biz.id)
    db_session.add(cust)
    db_session.commit()

    bill = Bill(
        bill_number="INV-API-001",
        customer_id=cust.id,
        business_id=biz.id,
        total_amount=Decimal("150.00"),
        payment_status=PaymentStatus.PAID,
    )
    db_session.add(bill)
    db_session.commit()

    mock_result = WhatsAppResult(
        success=True,
        message_id="wamid.HBgTEST123",
        media_id="media_test_456",
        recipient="919876543210",
    )

    with patch("app.services.whatsapp_service.WhatsAppService.send_invoice_via_whatsapp", new_callable=AsyncMock) as mock_send:
        mock_send.return_value = mock_result
        resp = client.post(
            "/whatsapp/send-invoice",
            json={"invoice_id": bill.bill_number},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "success"
        assert data["invoice_number"] == "INV-API-001"
        assert data["recipient"] == "919876543210"
        assert data["message_id"] == "wamid.HBgTEST123"
        assert data["media_id"] == "media_test_456"


def test_send_invoice_whatsapp_api_failed_delivery(client: TestClient, db_session):
    """Verify 400 response when WhatsApp delivery fails with error message."""
    biz = db_session.query(Business).first()
    bill = Bill(
        bill_number="INV-API-FAIL",
        customer_id=None,
        business_id=biz.id,
        total_amount=Decimal("100.00"),
        payment_status=PaymentStatus.PAID,
    )
    db_session.add(bill)
    db_session.commit()

    mock_result = WhatsAppResult(
        success=False,
        error_message="Customer phone number is missing.",
    )

    with patch("app.services.whatsapp_service.WhatsAppService.send_invoice_via_whatsapp", new_callable=AsyncMock) as mock_send:
        mock_send.return_value = mock_result
        resp = client.post(
            "/whatsapp/send-invoice",
            json={"invoice_id": bill.bill_number},
        )
        assert resp.status_code == 400
        assert "Customer phone number is missing" in resp.json()["detail"]
