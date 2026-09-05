"""Unit tests for Invoice PDF generation service."""

from decimal import Decimal
import os
import pytest
from sqlalchemy.orm import Session

from app.models.billing import Bill, BillItem, Customer, PaymentMethod, PaymentStatus
from app.models.business import Business
from app.models.product import Product
from app.services.pdf_service import InvoicePDFService


def test_generate_invoice_pdf_creates_valid_file(db_session: Session, tmp_path):
    """Verify that generate_invoice_pdf writes a non-empty, valid PDF file to disk."""
    # 1. Setup Business
    biz = db_session.query(Business).first()
    if not biz:
        biz = Business(
            name="Apex Retail Mart",
            owner_name="Omkar Jadhav",
            business_type="Retail",
            contact_number="9876543210",
            address="123 Main Street, Pune, Maharashtra",
        )
        db_session.add(biz)
        db_session.commit()

    # 2. Setup Customer
    cust = Customer(
        name="Rahul Sharma",
        phone="9876543210",
        business_id=biz.id,
    )
    db_session.add(cust)
    db_session.commit()

    # 3. Setup Products
    p1 = Product(
        name="Special Tea",
        unit="cup",
        selling_price=Decimal("20.00"),
        current_stock=Decimal("100.00"),
        business_id=biz.id,
    )
    p2 = Product(
        name="Grilled Cheese Sandwich",
        unit="pcs",
        selling_price=Decimal("80.00"),
        current_stock=Decimal("50.00"),
        business_id=biz.id,
    )
    db_session.add_all([p1, p2])
    db_session.commit()

    # 4. Setup Bill & Items
    bill = Bill(
        bill_number="INV-2026-TEST001",
        customer_id=cust.id,
        business_id=biz.id,
        subtotal=Decimal("120.00"),
        tax_amount=Decimal("6.00"),
        discount_amount=Decimal("0.00"),
        total_amount=Decimal("126.00"),
        payment_status=PaymentStatus.PAID,
    )
    db_session.add(bill)
    db_session.commit()

    i1 = BillItem(
        bill_id=bill.id,
        product_id=p1.id,
        quantity=Decimal("2.0"),
        unit_price=Decimal("20.00"),
        total_price=Decimal("40.00"),
    )
    i2 = BillItem(
        bill_id=bill.id,
        product_id=p2.id,
        quantity=Decimal("1.0"),
        unit_price=Decimal("80.00"),
        total_price=Decimal("80.00"),
    )
    db_session.add_all([i1, i2])
    db_session.commit()
    db_session.refresh(bill)

    # 5. Generate PDF
    custom_dir = str(tmp_path / "invoices")
    pdf_path = InvoicePDFService.generate_invoice_pdf(bill=bill, business=biz, output_dir=custom_dir)

    # 6. Assertions
    assert os.path.exists(pdf_path), "PDF file must exist on disk"
    assert os.path.getsize(pdf_path) > 1000, "PDF file must not be empty"

    with open(pdf_path, "rb") as f:
        header = f.read(5)
        assert header == b"%PDF-", "Generated file must start with PDF header (%PDF-)"


def test_generate_invoice_pdf_walk_in_customer(db_session: Session, tmp_path):
    """Verify PDF generation works for walk-in customer without an associated customer record."""
    biz = db_session.query(Business).first()
    bill = Bill(
        bill_number="INV-2026-WALKIN",
        customer_id=None,
        business_id=biz.id if biz else None,
        subtotal=Decimal("50.00"),
        tax_amount=Decimal("0.00"),
        discount_amount=Decimal("0.00"),
        total_amount=Decimal("50.00"),
        payment_status=PaymentStatus.PENDING,
    )
    db_session.add(bill)
    db_session.commit()
    db_session.refresh(bill)

    pdf_path = InvoicePDFService.generate_invoice_pdf(bill=bill, business=biz, output_dir=str(tmp_path))
    assert os.path.exists(pdf_path)
    assert os.path.getsize(pdf_path) > 1000
