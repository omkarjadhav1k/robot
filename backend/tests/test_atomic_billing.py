"""Tests for atomic bill creation, stock deduction, audit logs, and transaction rollback."""

from decimal import Decimal
import pytest
from sqlalchemy.orm import Session

from app.models.audit import AuditLog
from app.models.billing import Bill, BillItem, Customer, Payment, PaymentStatus
from app.models.business import Business
from app.models.product import InventoryTransaction, Product, TransactionType
from app.services.billing_service import BillingService


def test_atomic_bill_creation_and_stock_deduction(db_session: Session, default_business: Business):
    """Verify that creating a bill updates bill items, deducts stock, and records transactions atomically."""
    # Seed product
    product = Product(
        name="Sunflower Oil 1L",
        unit="bottle",
        selling_price=Decimal("150.00"),
        current_stock=Decimal("20.00"),
        minimum_stock=Decimal("5.00"),
        is_active=True,
        business_id=default_business.id,
    )
    db_session.add(product)
    db_session.commit()

    # Create bill for 3 bottles
    result = BillingService.create_bill(
        db=db_session,
        items_requested=[{"name": "Sunflower Oil 1L", "quantity": 3}],
        customer_name="Anita Sharma",
        payment_method="CASH",
        business_id=default_business.id,
    )

    assert result["success"] is True
    assert result["total_amount"] == 450.00  # 3 * 150
    assert result["bill_number"].startswith("INV-")

    # 1. Product stock must be reduced from 20 to 17
    db_session.refresh(product)
    assert product.current_stock == Decimal("17.00")

    # 2. Inventory transaction audit record must exist
    txn = (
        db_session.query(InventoryTransaction)
        .filter(InventoryTransaction.product_id == product.id)
        .first()
    )
    assert txn is not None
    assert txn.transaction_type == TransactionType.SALE
    assert txn.quantity == Decimal("3")
    assert txn.stock_before == Decimal("20.00")
    assert txn.stock_after == Decimal("17.00")

    # 3. Bill & BillItem records exist
    bill = db_session.query(Bill).filter(Bill.bill_number == result["bill_number"]).first()
    assert bill is not None
    assert bill.total_amount == Decimal("450.00")
    assert bill.payment_status == PaymentStatus.PAID

    items = db_session.query(BillItem).filter(BillItem.bill_id == bill.id).all()
    assert len(items) == 1
    assert items[0].quantity == Decimal("3")
    assert items[0].unit_price == Decimal("150.00")
    assert items[0].total_price == Decimal("450.00")

    # 4. AuditLog record exists
    audit = db_session.query(AuditLog).filter(AuditLog.entity_id == str(bill.id)).first()
    assert audit is not None
    assert audit.action == "CREATE_BILL"


def test_atomic_bill_creation_rollback_on_error(db_session: Session, default_business: Business):
    """Verify that if an item is invalid, the entire transaction rolls back cleanly."""
    initial_bills = db_session.query(Bill).count()
    initial_txns = db_session.query(InventoryTransaction).count()

    product = Product(
        name="Sugar",
        unit="kg",
        selling_price=Decimal("45.00"),
        current_stock=Decimal("50.00"),
        minimum_stock=Decimal("10.00"),
        is_active=True,
        business_id=default_business.id,
    )
    db_session.add(product)
    db_session.commit()

    # Attempt to create bill with one valid product and one non-existent product
    with pytest.raises(ValueError, match="not found in inventory"):
        BillingService.create_bill(
            db=db_session,
            items_requested=[
                {"name": "Sugar", "quantity": 5},
                {"name": "NonExistentItem99", "quantity": 1},
            ],
            customer_name="Test Customer",
            business_id=default_business.id,
        )

    # Product stock must NOT have been deducted
    db_session.refresh(product)
    assert product.current_stock == Decimal("50.00")

    # No new bills or transactions should be saved
    assert db_session.query(Bill).count() == initial_bills
    assert db_session.query(InventoryTransaction).count() == initial_txns
