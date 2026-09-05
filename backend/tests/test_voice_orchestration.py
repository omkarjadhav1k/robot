"""Integration tests for the voice interaction orchestrator endpoint."""

from decimal import Decimal
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.models.billing import Bill
from app.models.conversation import ConversationSession, ConversationState
from app.models.product import Product


def test_voice_interact_immediate_ack_and_session(client: TestClient):
    """Verify that every voice request returns a conversation_id and immediate_ack."""
    resp = client.post(
        "/voice/interact",
        json={"text": "How much stock do we have of rice?", "robot_id": "ROBOT-001"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "conversation_id" in data
    assert data["conversation_id"].startswith("conv_")
    assert data["immediate_ack"] is not None
    assert "stock" in data["immediate_ack"].lower() or "inventory" in data["immediate_ack"].lower()


def test_voice_hardware_command_execution(client: TestClient):
    """Verify hardware prompt triggers direct command queueing."""
    resp = client.post(
        "/voice/interact",
        json={"text": "turn on relay 3", "robot_id": "ROBOT-001"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["action_type"] == "hardware_action"
    assert "Relay 3 has been switched on" in data["response_text"]
    assert data["command_dispatched"] is not None
    assert data["command_dispatched"]["action"] == "set_relay"
    assert data["command_dispatched"]["params"] == {"relay": 3, "state": "on"}


def test_voice_multi_turn_confirmation_flow(client: TestClient, engine):
    """Verify two-turn flow: staged bill creation followed by 'haan karo' confirmation."""
    from sqlalchemy.orm import sessionmaker
    from app.models.business import Business
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    db = SessionLocal()

    biz = db.query(Business).first()
    if not biz:
        biz = Business(name="Test Retail Store", owner_name="Store Owner", business_type="Retail")
        db.add(biz)
        db.commit()

    # Seed product
    prod = Product(
        name="Wheat Flour 5kg",
        unit="bag",
        selling_price=Decimal("210.00"),
        current_stock=Decimal("15.00"),
        minimum_stock=Decimal("2.00"),
        is_active=True,
        business_id=biz.id,
    )
    db.add(prod)
    db.commit()

    # Pre-stage a conversation session awaiting confirmation
    session = ConversationSession(
        conversation_id="conv_stage_test",
        robot_id="ROBOT-001",
        state=ConversationState.AWAITING_CONFIRMATION,
        pending_action="create_bill",
        pending_intent="create_bill",
    )
    session.context_data = {
        "items": [{"name": "Wheat Flour 5kg", "quantity": 2}],
        "customer_name": "Deepak",
        "payment_method": "CASH",
        "estimated_total": 420.0,
    }
    db.add(session)
    db.commit()
    db.close()

    # Turn 2: User says "haan karo" with conversation_id attached
    resp = client.post(
        "/voice/interact",
        json={
            "text": "haan karo",
            "conversation_id": "conv_stage_test",
            "robot_id": "ROBOT-001",
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["action_type"] == "billing_action"
    assert "created successfully for Deepak" in data["response_text"]
    assert "420.00" in data["response_text"]
    assert data["business_data"]["total_amount"] == 420.00
    assert data["state"] == "IDLE"  # Reset back to IDLE after execution
