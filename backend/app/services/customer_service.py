"""Authoritative Customer Service querying and updating PostgreSQL customer balances and accounts."""

from decimal import Decimal
import logging
from typing import Any, Dict, List, Optional
import uuid

from sqlalchemy.orm import Session

from app.models.billing import Customer

logger = logging.getLogger(__name__)


class CustomerService:
    """PostgreSQL-backed authoritative customer and credit balance operations."""

    @staticmethod
    def search_customer(
        db: Session,
        query: str,
        business_id: Optional[Any] = None,
    ) -> Optional[Customer]:
        """Look up customer by phone number or name."""
        q = db.query(Customer)
        if business_id:
            q = q.filter(Customer.business_id == business_id)

        clean_query = query.strip()
        # 1. Exact phone match
        customer = q.filter(Customer.phone == clean_query).first()
        if customer:
            return customer

        # 2. Exact name match
        customer = q.filter(Customer.name.ilike(clean_query)).first()
        if customer:
            return customer

        # 3. Partial name match
        return q.filter(Customer.name.ilike(f"%{clean_query}%")).first()

    @staticmethod
    def get_or_create_customer(
        db: Session,
        name: str,
        phone: Optional[str] = None,
        business_id: Optional[Any] = None,
    ) -> Customer:
        """Fetch existing customer by name/phone or create a new customer record."""
        customer = CustomerService.search_customer(db, name, business_id)
        if customer:
            return customer

        if not business_id:
            from app.models.business import Business
            default_biz = db.query(Business).first()
            if not default_biz:
                default_biz = Business(name="Main Store", owner_name="Store Owner", business_type="Retail")
                db.add(default_biz)
                db.flush()
            business_id = default_biz.id

        new_phone = phone or "0000000000"
        customer = Customer(
            name=name.strip(),
            phone=new_phone,
            business_id=business_id,
            outstanding_balance=Decimal("0.00"),
        )
        db.add(customer)
        db.commit()
        db.refresh(customer)
        logger.info("Created new customer: %s (%s)", customer.name, customer.id)
        return customer

    @staticmethod
    def get_customer_balance(
        db: Session,
        customer_name: str,
        business_id: Optional[Any] = None,
    ) -> Dict[str, Any]:
        """Fetch verified customer outstanding balance."""
        customer = CustomerService.search_customer(db, customer_name, business_id)
        if not customer:
            return {
                "found": False,
                "query": customer_name,
                "message": f"Customer '{customer_name}' was not found in records.",
            }

        return {
            "found": True,
            "customer_id": str(customer.id),
            "name": customer.name,
            "phone": customer.phone,
            "outstanding_balance": float(customer.outstanding_balance),
            "credit_limit": float(customer.credit_limit) if customer.credit_limit else None,
        }

    @staticmethod
    def update_balance(
        db: Session,
        customer: Customer,
        delta: Decimal,
    ) -> Decimal:
        """Adjust customer running balance (positive increases balance/due, negative decreases)."""
        new_balance = customer.outstanding_balance + delta
        customer.outstanding_balance = new_balance
        db.add(customer)
        return new_balance

    @staticmethod
    def list_all_customers(
        db: Session,
        business_id: Optional[Any] = None,
        limit: int = 20,
    ) -> List[Dict[str, Any]]:
        """List registered customers with their contact info and outstanding balances."""
        q = db.query(Customer)
        if business_id:
            q = q.filter(Customer.business_id == business_id)
        customers = q.order_by(Customer.name.asc()).limit(limit).all()
        return [
            {
                "customer_id": str(c.id),
                "name": c.name,
                "phone": c.phone,
                "outstanding_balance": float(c.outstanding_balance),
            }
            for c in customers
        ]
