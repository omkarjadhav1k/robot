"""Integration and unit tests for natural conversational voice understanding, inventory tools, and TTS audio."""

from decimal import Decimal
import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.models.business import Business
from app.models.product import Product, InventoryTransaction, TransactionType
from app.services.inventory_service import InventoryService


def test_inventory_service_check_and_reduce_stock(db_session: Session, default_business: Business):
    """Test check_stock and reduce_or_sell_stock methods for Tata Salt."""
    # Ensure Tata Salt exists with 37 packets
    p = db_session.query(Product).filter(
        Product.business_id == default_business.id,
        Product.name == "Tata Salt"
    ).first()
    if not p:
        p = Product(
            business_id=default_business.id,
            name="Tata Salt",
            unit="packet",
            selling_price=Decimal("28.00"),
            purchase_price=Decimal("22.40"),
            current_stock=Decimal("37.00"),
            minimum_stock=Decimal("5.00"),
            is_active=True,
        )
        db_session.add(p)
        db_session.commit()
    else:
        p.current_stock = Decimal("37.00")
        db_session.commit()

    # 1. Check stock
    stock_info = InventoryService.get_stock(db_session, "Tata Salt", default_business.id)
    assert stock_info["found"] is True
    assert stock_info["current_stock"] == 37.0
    assert stock_info["unit"] == "packet"

    # 2. Reduce stock by 5
    res = InventoryService.reduce_or_sell_stock(
        db=db_session,
        product_name="Tata Salt",
        quantity=5.0,
        notes="Sold via voice",
        business_id=default_business.id,
    )
    assert res["success"] is True
    assert res["new_stock"] == 32.0
    assert "32" in res["message"]

    # Verify inventory audit transaction was logged
    txn = db_session.query(InventoryTransaction).filter(
        InventoryTransaction.product_id == p.id,
        InventoryTransaction.transaction_type == TransactionType.SALE
    ).first()
    assert txn is not None
    assert txn.quantity == Decimal("5.00")
    assert txn.transaction_type == TransactionType.SALE


def test_inventory_service_add_stock(db_session: Session, default_business: Business):
    """Test add_or_restock_product adds stock and logs STOCK_IN."""
    p = db_session.query(Product).filter(
        Product.business_id == default_business.id,
        Product.name == "Surf Excel"
    ).first()
    if not p:
        p = Product(
            business_id=default_business.id,
            name="Surf Excel",
            unit="packet",
            selling_price=Decimal("140.00"),
            purchase_price=Decimal("112.00"),
            current_stock=Decimal("50.00"),
            minimum_stock=Decimal("5.00"),
            is_active=True,
        )
        db_session.add(p)
        db_session.commit()
    else:
        p.current_stock = Decimal("50.00")
        db_session.commit()

    res = InventoryService.add_or_restock_product(
        db=db_session,
        product_name="Surf Excel",
        quantity=10.0,
        unit="packet",
        business_id=default_business.id,
    )
    assert res["success"] is True
    assert res["new_stock"] == 60.0


def test_voice_interact_audio_url_included(client: TestClient):
    """Verify that voice interact responses contain an audio_url for the speaker."""
    resp = client.post(
        "/voice/interact",
        json={"text": "Hello Robo, tum kaise ho?", "robot_id": "ROBOT-VOICE-DEV"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "response_text" in data
    assert "audio_url" in data
    assert data["audio_url"].startswith("/api/v1/voice/audio/tts")


def test_voice_device_relay_mapping(client: TestClient):
    """Verify natural device names (light, fan) map to respective relay channels."""
    # 1. Light -> Relay 1
    resp1 = client.post(
        "/voice/interact",
        json={"text": "turn on the light", "robot_id": "ROBOT-VOICE-DEV"},
    )
    assert resp1.status_code == 200
    data1 = resp1.json()
    assert data1["action_type"] == "hardware_action"
    assert data1["command_dispatched"]["params"]["relay"] == 1
    assert data1["command_dispatched"]["params"]["state"] == "on"

    # 2. Fan -> Relay 2
    resp2 = client.post(
        "/voice/interact",
        json={"text": "turn off the fan", "robot_id": "ROBOT-VOICE-DEV"},
    )
    assert resp2.status_code == 200
    data2 = resp2.json()
    assert data2["action_type"] == "hardware_action"
    assert data2["command_dispatched"]["params"]["relay"] == 2
    assert data2["command_dispatched"]["params"]["state"] == "off"


def test_tts_endpoint_returns_audio(client: TestClient):
    """Verify GET /api/v1/voice/audio/tts returns audio bytes."""
    resp = client.get("/api/v1/voice/audio/tts", params={"text": "Tata Salt ke 37 packets available hain", "lang": "hi"})
    assert resp.status_code == 200
    assert resp.headers["content-type"] == "audio/mpeg"
    assert len(resp.content) > 1000  # Valid MP3 audio bytes
