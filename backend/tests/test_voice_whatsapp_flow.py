"""Integration test for Voice-triggered WhatsApp Bill Generation and Dispatch."""

from decimal import Decimal
from unittest.mock import AsyncMock, patch
from fastapi.testclient import TestClient

from app.ai.gemini_service import GeminiResult
from app.models.billing import Customer
from app.models.business import Business
from app.models.product import Product
from app.services.whatsapp_service import WhatsAppResult


def test_voice_create_bill_and_whatsapp_flow_success(client: TestClient, db_session):
    """
    Test the full user voice flow:
    'Robot, Rahul ka 2 chai aur 1 sandwich ka bill bana ke WhatsApp kar do.'
    Verifies:
    1. Products and customer exist in database.
    2. Bill is generated with correct total.
    3. WhatsApp service is invoked.
    4. Exact robot speech is returned: 'Bill {bill_number} of ₹{total} has been generated and sent to Rahul on WhatsApp.'
    """
    biz = db_session.query(Business).first()

    # Seed customer Rahul with phone number
    cust = Customer(name="Rahul", phone="9876543210", business_id=biz.id)
    db_session.add(cust)

    # Seed products Tea and Veg Sandwich
    p_chai = Product(
        name="Tea",
        unit="cup",
        selling_price=Decimal("20.00"),
        current_stock=Decimal("50.00"),
        business_id=biz.id,
    )
    p_sandwich = Product(
        name="Veg Sandwich",
        unit="pcs",
        selling_price=Decimal("80.00"),
        current_stock=Decimal("20.00"),
        business_id=biz.id,
    )
    db_session.add_all([p_chai, p_sandwich])
    db_session.commit()

    # Mock Gemini function call for: Rahul ka 2 chai aur 1 sandwich ka bill bana ke WhatsApp kar do
    mock_gemini_res = GeminiResult(
        text="Creating bill for Rahul and sending on WhatsApp.",
        function_call={
            "name": "create_bill",
            "args": {
                "customer_name": "Rahul",
                "items": [
                    {"name": "chai", "quantity": 2},
                    {"name": "sandwich", "quantity": 1},
                ],
                "send_whatsapp": True,
            },
        },
        is_success=True,
    )

    mock_whatsapp_res = WhatsAppResult(
        success=True,
        message_id="wamid.HBgTEST_ROBOT_VOICE_WA",
        media_id="media_test_invoice_pdf",
        recipient="919876543210",
    )

    with patch("app.api.voice.reason_with_gemini", new_callable=AsyncMock) as mock_gemini, \
         patch("app.api.voice.WhatsAppService.send_invoice_via_whatsapp", new_callable=AsyncMock) as mock_wa:

        mock_gemini.return_value = mock_gemini_res
        mock_wa.return_value = mock_whatsapp_res

        resp = client.post(
            "/voice/interact",
            json={
                "text": "Robot, Rahul ka 2 chai aur 1 sandwich ka bill bana ke WhatsApp kar do.",
                "robot_id": "ROBOT-001",
            },
        )

        assert resp.status_code == 200
        data = resp.json()

        # Check immediate ack
        assert "whatsapp" in data["immediate_ack"].lower() or "invoice" in data["immediate_ack"].lower()

        # Check exact robot spoken response
        assert "has been generated and sent to Rahul on WhatsApp." in data["response_text"]
        assert "₹120.00" in data["response_text"]

        # Check WhatsAppService was called and bill data matches
        mock_wa.assert_called_once()
        assert data["business_data"]["customer_name"] == "Rahul"
        assert data["business_data"]["total_amount"] == 120.00


def test_voice_create_bill_and_whatsapp_flow_failure(client: TestClient, db_session):
    """
    Verify spoken fallback response when WhatsApp fails:
    'I generated the bill, but I couldn't send it on WhatsApp. Please check the customer's WhatsApp number.'
    """
    biz = db_session.query(Business).first()

    # Seed products
    p_chai = Product(name="Tea", unit="cup", selling_price=Decimal("20.00"), current_stock=Decimal("50"), business_id=biz.id)
    db_session.add(p_chai)
    db_session.commit()

    mock_gemini_res = GeminiResult(
        text="Creating bill and sending WhatsApp.",
        function_call={
            "name": "create_bill",
            "args": {
                "customer_name": "Unknown Person",
                "items": [{"name": "chai", "quantity": 1}],
                "send_whatsapp": True,
            },
        },
        is_success=True,
    )

    # WhatsApp fails due to missing phone number
    mock_whatsapp_res = WhatsAppResult(
        success=False,
        error_message="Customer phone number is missing.",
    )

    with patch("app.api.voice.reason_with_gemini", new_callable=AsyncMock) as mock_gemini, \
         patch("app.api.voice.WhatsAppService.send_invoice_via_whatsapp", new_callable=AsyncMock) as mock_wa:

        mock_gemini.return_value = mock_gemini_res
        mock_wa.return_value = mock_whatsapp_res

        resp = client.post(
            "/voice/interact",
            json={
                "text": "Unknown Person ka 1 chai ka bill bana ke WhatsApp kar do.",
                "robot_id": "ROBOT-001",
            },
        )

        assert resp.status_code == 200
        data = resp.json()

        # Check required failure response text
        expected_failure_msg = "I generated the bill, but I couldn't send it on WhatsApp. Please check the customer's WhatsApp number."
        assert data["response_text"] == expected_failure_msg
