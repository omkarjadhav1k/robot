import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session
from decimal import Decimal

from app.models.business import Business
from app.models.product import Product
from app.engine.intent_router import IntentRouter
from app.engine.entity_extractor import ExtractedEntities

def test_intent_router_distinguishes_stock_inquiry_vs_clear():
    """Verify clean shop/delete stock is classified as CLEAR_INVENTORY, not GET_STOCK."""
    match = IntentRouter.classify(
        "aaj mai shop clean kar raha hau stock pura remove delete kardo ham firsse ek ek karke add karenge",
        ExtractedEntities()
    )
    assert match.intent == "CLEAR_INVENTORY"
    assert match.confidence >= 0.85

def test_fast_stock_query_still_works_deterministically(client: TestClient, db_session: Session):
    """Verify exact stock query still executes fast-path directly."""
    biz = db_session.query(Business).first()
    p = Product(
        name="Tata Salt",
        unit="packet",
        selling_price=Decimal("28.00"),
        purchase_price=Decimal("20.00"),
        current_stock=Decimal("35.00"),
        minimum_stock=Decimal("5.00"),
        business_id=biz.id,
        is_active=True,
    )
    db_session.add(p)
    db_session.commit()

    resp = client.post(
        "/voice/interact",
        json={"text": "Tata Salt kitna hai?", "robot_id": "ROBOT-001"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "Tata Salt" in data["response_text"]
    assert "35" in data["response_text"]

@pytest.mark.asyncio
async def test_hybrid_engine_casual_language_prompts(db_session: Session):
    """Verify Tier 2 Gemini Thinking Engine handles typos and prompts for confirmation/details."""
    from app.engine.hybrid_engine import HybridEngine
    biz = db_session.query(Business).first()

    # 1. Shop clean / delete stock
    r1 = await HybridEngine.reason_and_execute(
        user_text="aaj mai shop clean kar raha hau stock pura remove delete kardo ham firsse ek ek karke add karenge",
        db=db_session,
        business_id=biz.id,
        robot_id="ROBOT-001",
        history=[]
    )
    assert r1.action_type == "confirmation_required" or "confirm" in r1.response_text.lower() or "delete" in r1.response_text.lower()

    # 2. Voice typo 'remove karo stocl'
    r2 = await HybridEngine.reason_and_execute(
        user_text="remove karo stocl",
        db=db_session,
        business_id=biz.id,
        robot_id="ROBOT-001",
        history=[]
    )
    assert "product" in r2.response_text.lower() or "item" in r2.response_text.lower() or "quantity" in r2.response_text.lower() or "naam" in r2.response_text.lower()

    # 3. Typo 'genrate bill'
    r3 = await HybridEngine.reason_and_execute(
        user_text="genrate bill",
        db=db_session,
        business_id=biz.id,
        robot_id="ROBOT-001",
        history=[]
    )
    assert "bill" in r3.response_text.lower() or "item" in r3.response_text.lower() or "customer" in r3.response_text.lower()

    # 4. Incomplete request 'bill'
    r4 = await HybridEngine.reason_and_execute(
        user_text="bill",
        db=db_session,
        business_id=biz.id,
        robot_id="ROBOT-001",
        history=[]
    )
    assert "bill" in r4.response_text.lower() or "item" in r4.response_text.lower() or "customer" in r4.response_text.lower()


def test_sugar_price_typo_and_idiom(client: TestClient, db_session: Session):
    """Verify 'suger' typo resolves to Sugar with price, and 'ek kam karo' does not crash."""
    biz = db_session.query(Business).first()
    sugar = Product(
        name="Sugar",
        unit="kg",
        selling_price=Decimal("42.00"),
        purchase_price=Decimal("38.00"),
        current_stock=Decimal("9.00"),
        minimum_stock=Decimal("5.00"),
        business_id=biz.id,
        is_active=True,
    )
    db_session.add(sugar)
    db_session.commit()

    # 1. Phonetic voice typo 'suger' + price query
    resp1 = client.post(
        "/voice/interact",
        json={"text": "1 kg suger ki price kya hai", "robot_id": "ROBOT-001"},
    )
    assert resp1.status_code == 200
    data1 = resp1.json()
    # Response must mention Sugar and price 42
    assert "Sugar" in data1["response_text"]
    assert "42" in data1["response_text"]

    # 2. Idiom 'ek kam karo to online suger ka rate kya chal raha hai check karna'
    resp2 = client.post(
        "/voice/interact",
        json={"text": "ek kam karo to online suger ka rate kya chal raha hai check karna", "robot_id": "ROBOT-001"},
    )
    assert resp2.status_code == 200
    data2 = resp2.json()
    assert data2["response_text"]  # must return valid response without 500


def test_add_multiple_product_varieties(db_session: Session):
    """Verify InventoryService.add_multiple_products adds varieties with prices to DB."""
    from app.services.inventory_service import InventoryService
    biz = db_session.query(Business).first()
    varieties = [
        {"name": "Casual Cotton Shirt", "selling_price": 699.0, "quantity": 20.0, "unit": "pieces"},
        {"name": "Formal Slim Fit Shirt", "selling_price": 999.0, "quantity": 15.0, "unit": "pieces"},
        {"name": "Denim Shirt", "selling_price": 1199.0, "quantity": 10.0, "unit": "pieces"},
    ]
    res = InventoryService.add_multiple_products(db=db_session, products=varieties, business_id=biz.id)
    assert res["success"] is True
    assert res["added_count"] == 3

    # Check products exist in DB
    all_prods = InventoryService.list_all_products(db=db_session, business_id=biz.id)
    prod_names = [p["name"] for p in all_prods]
    assert "Casual Cotton Shirt" in prod_names
    assert "Formal Slim Fit Shirt" in prod_names
    assert "Denim Shirt" in prod_names

    # Check prices
    for p in all_prods:
        if p["name"] == "Casual Cotton Shirt":
            assert p["selling_price"] == 699.0
            assert p["current_stock"] == 20.0