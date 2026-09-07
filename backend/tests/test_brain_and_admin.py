"""Tests for BrainService, customer bill filtering, dynamic instruction injection, and Admin endpoints."""

from decimal import Decimal
import uuid
import pytest
from sqlalchemy.orm import Session
from fastapi.testclient import TestClient

from app.models.billing import Bill, Customer
from app.models.business import Business
from app.models.instruction import BrainInstruction
from app.models.product import Product
from app.services.billing_service import BillingService
from app.services.brain_service import BrainService


def test_brain_service_crud_and_learning(db_session: Session, default_business: Business):
    """Verify adding, listing, toggling, deleting, and auto-learning rules."""
    # 1. Add instruction
    item = BrainService.add_instruction(
        db=db_session,
        instruction="Ramesh gets 5% discount on all purchases",
        category="DISCOUNT",
        source="WEB_PANEL",
        business_id=default_business.id,
    )
    assert item.id is not None
    assert item.instruction == "Ramesh gets 5% discount on all purchases"
    assert item.category == "DISCOUNT"
    assert item.is_active is True

    # 2. Get active instructions
    active = BrainService.get_active_instructions(db_session, default_business.id)
    assert any(i.id == item.id for i in active)

    # 3. Dynamic prompt injection strings
    strings = BrainService.get_instruction_strings(db_session, default_business.id)
    assert any("[DISCOUNT] Ramesh gets 5% discount on all purchases" in s for s in strings)

    # 4. Toggle instruction
    toggled = BrainService.toggle_instruction(db_session, item.id, is_active=False)
    assert toggled.is_active is False
    active_after = BrainService.get_active_instructions(db_session, default_business.id)
    assert not any(i.id == item.id for i in active_after)

    # 5. Re-enable
    BrainService.toggle_instruction(db_session, item.id, is_active=True)

    # 6. Delete instruction
    deleted = BrainService.delete_instruction(db_session, item.id)
    assert deleted is True
    assert db_session.query(BrainInstruction).filter(BrainInstruction.id == item.id).first() is None


def test_brain_service_detect_and_learn_rule(db_session: Session, default_business: Business):
    """Verify chat-based rule detection from natural language prefixes."""
    # Test "Remember that..."
    rule1 = BrainService.detect_and_learn_rule(
        db_session,
        "Remember that our store timing is 9am to 10pm",
        business_id=default_business.id,
    )
    assert rule1 is not None
    assert "our store timing is 9am to 10pm" in rule1.instruction
    assert rule1.category == "TIMING"

    # Test "Rule: ..."
    rule2 = BrainService.detect_and_learn_rule(
        db_session,
        "Rule: Never give credit above 1000 rupees",
        business_id=default_business.id,
    )
    assert rule2 is not None
    assert "Never give credit above 1000 rupees" in rule2.instruction
    assert rule2.category == "CREDIT"

    # Non-rule should return None
    non_rule = BrainService.detect_and_learn_rule(
        db_session,
        "What is 2 + 2?",
        business_id=default_business.id,
    )
    assert non_rule is None


def test_customer_filtered_todays_bills(db_session: Session, default_business: Business):
    """Verify that get_todays_bills correctly filters bills by customer name."""
    # Create test product
    prod = Product(
        business_id=default_business.id,
        name="Test Tea",
        unit="cup",
        selling_price=Decimal("15.00"),
        purchase_price=Decimal("10.00"),
        current_stock=Decimal("100.00"),
        minimum_stock=Decimal("5.00"),
        is_active=True,
    )
    db_session.add(prod)
    db_session.commit()

    # Create bills for Omkar and Rahul
    b1 = BillingService.create_bill(
        db=db_session,
        items_requested=[{"name": "Test Tea", "quantity": 2}],
        customer_name="Omkar",
        business_id=default_business.id,
    )
    b2 = BillingService.create_bill(
        db=db_session,
        items_requested=[{"name": "Test Tea", "quantity": 1}],
        customer_name="Rahul",
        business_id=default_business.id,
    )

    # 1. Unfiltered query
    all_bills = BillingService.get_todays_bills(db_session, default_business.id)
    assert all_bills["total_bills"] >= 2

    # 2. Filtered for "Omkar"
    omkar_bills = BillingService.get_todays_bills(db_session, default_business.id, customer_name="Omkar")
    assert omkar_bills["total_bills"] >= 1
    assert all("omkar" in b["customer_name"].lower() for b in omkar_bills["recent_bills"])
    assert not any("rahul" in b["customer_name"].lower() for b in omkar_bills["recent_bills"])

    # 3. Filtered for "Rahul"
    rahul_bills = BillingService.get_todays_bills(db_session, default_business.id, customer_name="Rahul")
    assert rahul_bills["total_bills"] >= 1
    assert all("rahul" in b["customer_name"].lower() for b in rahul_bills["recent_bills"])


def test_admin_dashboard_endpoints(client: TestClient):
    """Verify admin web dashboard and REST API endpoints."""
    # 1. GET /admin
    r = client.get("/admin")
    assert r.status_code == 200
    assert "MAX" in r.text or "Business AI Robot" in r.text
    assert "Brain Trainer" in r.text

    # 2. GET /dashboard
    r2 = client.get("/dashboard")
    assert r2.status_code == 200

    # 3. GET /api/v1/admin/stats
    r_stats = client.get("/api/v1/admin/stats")
    assert r_stats.status_code == 200
    data = r_stats.json()
    assert "today_revenue" in data
    assert "total_products" in data

    # 4. POST /api/v1/admin/instructions
    r_add = client.post("/api/v1/admin/instructions", json={
        "instruction": "Special loyalty discount for regular customers",
        "category": "DISCOUNT",
    })
    assert r_add.status_code == 200
    rule_id = r_add.json()["id"]

    # 5. GET /api/v1/admin/instructions
    r_list = client.get("/api/v1/admin/instructions")
    assert r_list.status_code == 200
    items = r_list.json()
    assert any(i["id"] == rule_id for i in items)

    # 6. PATCH toggle
    r_toggle = client.patch(f"/api/v1/admin/instructions/{rule_id}/toggle", json={"is_active": False})
    assert r_toggle.status_code == 200
    assert r_toggle.json()["is_active"] is False

    # 7. DELETE instruction
    r_del = client.delete(f"/api/v1/admin/instructions/{rule_id}")
    assert r_del.status_code == 200
    assert r_del.json()["success"] is True


def test_admin_chat_teach_mode(client: TestClient):
    """Verify admin chat with teach_mode saves rule directly."""
    res = client.post("/api/v1/admin/chat", json={
        "message": "Always smile and greet customers with Namaste",
        "teach_mode": True,
    })
    assert res.status_code == 200
    data = res.json()
    assert data["rule_saved"] is True
    assert "Memorized to Brain Database" in data["response_text"]


def test_admin_chat_natural_rule_learning(client: TestClient):
    """Verify admin chat auto-detects teaching intent."""
    res = client.post("/api/v1/admin/chat", json={
        "message": "Remember that Ramesh gets 5% discount",
        "teach_mode": False,
    })
    assert res.status_code == 200
    data = res.json()
    assert data["rule_saved"] is True
    assert data["rule_category"] == "DISCOUNT"
    assert "memorized this discount rule" in data["response_text"].lower()
