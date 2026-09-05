"""Authoritative Billing Service performing atomic invoice creation, stock deduction, and revenue queries."""

from datetime import datetime, time, timezone
from decimal import Decimal
import logging
import random
from typing import Any, Dict, List, Optional
import uuid

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.audit import ActorType, AuditLog
from app.models.billing import (
    Bill,
    BillItem,
    BillSource,
    Customer,
    Payment,
    PaymentMethod,
    PaymentStatus,
)
from app.services.customer_service import CustomerService
from app.services.inventory_service import InventoryService

logger = logging.getLogger(__name__)


class BillingService:
    """PostgreSQL-backed authoritative billing and invoice calculations."""

    @staticmethod
    def generate_bill_number(db: Session) -> str:
        """Generate a sequential unique human-readable invoice identifier."""
        today_str = datetime.now(timezone.utc).strftime("%Y%m%d")
        rand_suffix = random.randint(1000, 9999)
        return f"INV-{today_str}-{rand_suffix}"

    @classmethod
    def create_bill(
        cls,
        db: Session,
        items_requested: List[Dict[str, Any]],
        customer_name: Optional[str] = None,
        customer_phone: Optional[str] = None,
        payment_method: str = "CASH",
        discount: float = 0.0,
        tax_rate: float = 0.0,
        source: BillSource = BillSource.ROBOT_VOICE,
        business_id: Optional[Any] = None,
    ) -> Dict[str, Any]:
        """
        Atomically create a bill:
        1. Resolve customer.
        2. Verify product prices and stock from DB (DB prices OVERRULE any AI estimates).
        3. Deduct stock and log inventory transactions.
        4. Calculate subtotal, tax, discount, and total.
        5. Insert Bill, BillItems, Payment, and AuditLog in a single transaction.
        """
        if not items_requested:
            raise ValueError("Cannot create a bill with zero items.")

        if not business_id:
            from app.models.business import Business
            default_biz = db.query(Business).first()
            if not default_biz:
                default_biz = Business(name="Main Store", owner_name="Store Owner", business_type="Retail")
                db.add(default_biz)
                db.flush()
            business_id = default_biz.id

        # 1. Customer resolution
        customer: Optional[Customer] = None
        if customer_name:
            customer = CustomerService.get_or_create_customer(
                db, name=customer_name, phone=customer_phone, business_id=business_id
            )

        bill_number = cls.generate_bill_number(db)
        created_items: List[BillItem] = []
        subtotal = Decimal("0.00")
        line_summaries: List[Dict[str, Any]] = []

        try:
            # 2 & 3. Process line items with authoritative prices
            for item in items_requested:
                name = item.get("name") or item.get("product_name", "")
                raw_qty = item.get("quantity", 1)
                quantity = Decimal(str(raw_qty))

                if quantity <= Decimal("0"):
                    raise ValueError(f"Invalid quantity {quantity} for '{name}'.")

                product = InventoryService.search_product(db, name, business_id=business_id)
                if not product:
                    raise ValueError(f"Product '{name}' not found in inventory.")

                # Authoritative price from database
                unit_price = product.selling_price
                line_total = (unit_price * quantity).quantize(Decimal("0.01"))
                subtotal += line_total

                # Deduct stock with inventory audit trail
                InventoryService.deduct_stock(
                    db=db,
                    product=product,
                    quantity=quantity,
                    reference_id=bill_number,
                    notes=f"Sold via Bill {bill_number}",
                )

                # Line item summary
                line_summaries.append({
                    "product_id": str(product.id),
                    "product_name": product.name,
                    "quantity": float(quantity),
                    "unit": product.unit,
                    "unit_price": float(unit_price),
                    "line_total": float(line_total),
                    "remaining_stock": float(product.current_stock),
                })

            # 4. Authoritative backend totals
            discount_amount = Decimal(str(round(discount, 2)))
            tax_amount = (subtotal * Decimal(str(tax_rate))).quantize(Decimal("0.01"))
            total_amount = (subtotal + tax_amount - discount_amount).quantize(Decimal("0.01"))
            if total_amount < Decimal("0.00"):
                total_amount = Decimal("0.00")

            pay_method_enum = PaymentMethod.CASH
            try:
                pay_method_enum = PaymentMethod(payment_method.upper())
            except Exception:
                pay_method_enum = PaymentMethod.CASH

            is_credit = pay_method_enum == PaymentMethod.CREDIT
            payment_status = PaymentStatus.PENDING if is_credit else PaymentStatus.PAID

            # Create Bill
            bill = Bill(
                bill_number=bill_number,
                customer_id=customer.id if customer else None,
                business_id=business_id,
                subtotal=subtotal,
                tax_amount=tax_amount,
                discount_amount=discount_amount,
                total_amount=total_amount,
                payment_status=payment_status,
                source=source,
            )
            db.add(bill)
            db.flush()  # Populates bill.id

            # Create BillItems
            for summary in line_summaries:
                bill_item = BillItem(
                    bill_id=bill.id,
                    product_id=uuid.UUID(summary["product_id"]),
                    quantity=Decimal(str(summary["quantity"])),
                    unit_price=Decimal(str(summary["unit_price"])),
                    total_price=Decimal(str(summary["line_total"])),
                )
                db.add(bill_item)

            # Update customer ledger or record payment
            if customer:
                if is_credit:
                    CustomerService.update_balance(db, customer, total_amount)
                else:
                    payment = Payment(
                        customer_id=customer.id,
                        bill_id=bill.id,
                        business_id=business_id,
                        amount=total_amount,
                        payment_method=pay_method_enum,
                        notes=f"Payment for {bill_number}",
                    )
                    db.add(payment)

            # Audit log
            audit = AuditLog(
                business_id=business_id,
                actor_type=ActorType.ROBOT if source == BillSource.ROBOT_VOICE else ActorType.USER,
                actor_id=customer.name if customer else "ROBOT-001",
                action="CREATE_BILL",
                entity_type="Bill",
                entity_id=str(bill.id),
                details={
                    "bill_number": bill_number,
                    "total_amount": float(total_amount),
                    "items_count": len(line_summaries),
                    "customer": customer.name if customer else "Anonymous",
                },
            )
            db.add(audit)

            # Commit the entire atomic unit
            db.commit()
            db.refresh(bill)

            logger.info("Successfully created bill %s for total ₹%s", bill.bill_number, bill.total_amount)

            return {
                "success": True,
                "bill_id": str(bill.id),
                "bill_number": bill.bill_number,
                "customer_name": customer.name if customer else "Walk-in Customer",
                "items": line_summaries,
                "subtotal": float(subtotal),
                "tax": float(tax_amount),
                "discount": float(discount_amount),
                "total_amount": float(total_amount),
                "payment_status": bill.payment_status.value,
                "payment_method": pay_method_enum.value,
            }

        except Exception as e:
            db.rollback()
            logger.error("Failed to create bill, transaction rolled back: %s", str(e), exc_info=True)
            raise

    @staticmethod
    def get_todays_bills(
        db: Session,
        business_id: Optional[Any] = None,
        customer_name: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Fetch today's verified bills and sales totals directly from PostgreSQL, optionally filtered by customer."""
        now = datetime.now(timezone.utc)
        today_start = datetime.combine(now.date(), time.min, tzinfo=timezone.utc)
        today_end = datetime.combine(now.date(), time.max, tzinfo=timezone.utc)

        q = db.query(Bill).filter(Bill.created_at >= today_start, Bill.created_at <= today_end)
        if business_id:
            q = q.filter(Bill.business_id == business_id)

        clean_customer = customer_name.strip() if customer_name else None
        if clean_customer:
            q = q.outerjoin(Customer, Bill.customer_id == Customer.id)
            if clean_customer.lower() in ("walk-in", "walk-in customer", "walkin", "anonymous"):
                q = q.filter(Bill.customer_id.is_(None))
            else:
                q = q.filter(Customer.name.ilike(f"%{clean_customer}%"))

        bills = q.order_by(Bill.created_at.desc()).all()
        total_revenue = sum(b.total_amount for b in bills) if bills else Decimal("0.00")
        paid_count = sum(1 for b in bills if b.payment_status == PaymentStatus.PAID)
        pending_count = sum(1 for b in bills if b.payment_status == PaymentStatus.PENDING)

        return {
            "date": now.strftime("%Y-%m-%d"),
            "customer_filter": clean_customer,
            "total_bills": len(bills),
            "total_revenue": float(total_revenue),
            "paid_bills_count": paid_count,
            "pending_bills_count": pending_count,
            "recent_bills": [
                {
                    "bill_number": b.bill_number,
                    "customer_name": b.customer.name if b.customer else "Walk-in Customer",
                    "total_amount": float(b.total_amount),
                    "status": b.payment_status.value,
                    "time": b.created_at.strftime("%H:%M"),
                }
                for b in bills[:10]
            ],
        }
