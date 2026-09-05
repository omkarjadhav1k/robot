"""Tests verifying PostgreSQL database truth: stock lookups, customer balances, reports."""

from decimal import Decimal
from sqlalchemy.orm import Session

from app.models.billing import Customer
from app.models.business import Business
from app.models.product import Product
from app.services.customer_service import CustomerService
from app.services.inventory_service import InventoryService
from app.services.report_service import ReportService


def test_inventory_service_stock_truth(db_session: Session, default_business: Business):
    """Ensure stock queries return actual database truth, never hallucinations."""
    # Seed known products
    p1 = Product(
        name="Basmati Rice",
        unit="kg",
        selling_price=Decimal("85.00"),
        current_stock=Decimal("42.50"),
        minimum_stock=Decimal("10.00"),
        is_active=True,
        business_id=default_business.id,
    )
    p2 = Product(
        name="Tata Salt",
        unit="packet",
        selling_price=Decimal("28.00"),
        current_stock=Decimal("3.00"),
        minimum_stock=Decimal("10.00"),  # Low stock
        is_active=True,
        business_id=default_business.id,
    )
    db_session.add_all([p1, p2])
    db_session.commit()

    # 1. Exact match query
    stock1 = InventoryService.get_stock(db_session, "Basmati Rice", default_business.id)
    assert stock1["found"] is True
    assert stock1["current_stock"] == 42.50
    assert stock1["selling_price"] == 85.00
    assert stock1["unit"] == "kg"
    assert stock1["is_low_stock"] is False

    # 2. Case-insensitive substring match
    stock2 = InventoryService.get_stock(db_session, "salt", default_business.id)
    assert stock2["found"] is True
    assert stock2["name"] == "Tata Salt"
    assert stock2["current_stock"] == 3.00
    assert stock2["is_low_stock"] is True

    # 3. Non-existent product
    stock_unknown = InventoryService.get_stock(db_session, "Alien Laser", default_business.id)
    assert stock_unknown["found"] is False
    assert "not found" in stock_unknown["message"].lower()

    # 4. Low stock items
    low_items = InventoryService.get_low_stock_items(db_session, default_business.id)
    assert len(low_items) == 1
    assert low_items[0]["name"] == "Tata Salt"


def test_customer_service_balance_truth(db_session: Session, default_business: Business):
    """Ensure customer balance lookups return verified ledger amounts."""
    cust = Customer(
        name="Ramesh Kumar",
        phone="9876543210",
        outstanding_balance=Decimal("450.00"),
        business_id=default_business.id,
    )
    db_session.add(cust)
    db_session.commit()

    # Lookup by name
    res = CustomerService.get_customer_balance(db_session, "Ramesh", default_business.id)
    assert res["found"] is True
    assert res["name"] == "Ramesh Kumar"
    assert res["outstanding_balance"] == 450.00

    # Lookup non-existent customer
    res_unknown = CustomerService.get_customer_balance(db_session, "NonExistentPerson", default_business.id)
    assert res_unknown["found"] is False
