import pytest
from decimal import Decimal
from app.services.inventory_service import InventoryService
from app.services.conversation_service import ConversationService
from app.models.product import Product
from app.models.business import Business


def test_fuzzy_matching_and_aliases(db_session):
    biz = Business(name="Test Biz", owner_name="Owner", business_type="Retail")
    db_session.add(biz)
    db_session.commit()

    p_sugar = Product(name="Sugar", selling_price=Decimal("42.00"), current_stock=Decimal("50"), unit="kg", business_id=biz.id)
    p_salt = Product(name="Tata Salt", selling_price=Decimal("28.00"), current_stock=Decimal("30"), unit="packet", business_id=biz.id)
    p_milk = Product(name="Amul Milk", selling_price=Decimal("30.00"), current_stock=Decimal("20"), unit="packet", business_id=biz.id)
    db_session.add_all([p_sugar, p_salt, p_milk])
    db_session.commit()

    # Test spelling errors
    assert InventoryService.search_product(db_session, "suger", biz.id).id == p_sugar.id
    assert InventoryService.search_product(db_session, "tat salte", biz.id).id == p_salt.id
    
    # Test Hindi aliases
    assert InventoryService.search_product(db_session, "cheeni", biz.id).id == p_sugar.id
    assert InventoryService.search_product(db_session, "doodh", biz.id).id == p_milk.id


def test_add_or_update_product(db_session):
    biz = Business(name="Test Biz 2", owner_name="Owner", business_type="Retail")
    db_session.add(biz)
    db_session.commit()

    res = InventoryService.add_or_update_product(
        db=db_session,
        name="Sample Biscuit",
        selling_price=20.00,
        current_stock=15.0,
        unit="packet",
        business_id=biz.id,
    )
    assert res["created"] is True
    assert res["id"] is not None
    assert res["name"] == "Sample Biscuit"
    assert res["selling_price"] == 20.00
    assert res["current_stock"] == 15.0


def test_affirmation_and_negation_nuance():
    # User typos and variations
    assert ConversationService.is_affirmation("conform") is True
    assert ConversationService.is_affirmation("its conform") is True
    assert ConversationService.is_affirmation("it's conform") is True
    assert ConversationService.is_affirmation("theek h") is True
    assert ConversationService.is_affirmation("ha confirm") is True

    # Complaints or questions containing 'nahi' must NOT be cancellations
    assert ConversationService.is_negation("abhi ka bill add nahi kiya") is False
    assert ConversationService.is_negation("kyu nahi kiya") is False
    assert ConversationService.is_negation("nahi hua kya") is False

    # Actual cancellations MUST be recognized
    assert ConversationService.is_negation("nahi") is True
    assert ConversationService.is_negation("cancel") is True
    assert ConversationService.is_negation("mat karo") is True
