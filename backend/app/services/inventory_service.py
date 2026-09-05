"""Authoritative Inventory Service querying and modifying PostgreSQL product stock."""

from decimal import Decimal
import logging
from typing import Any, Dict, List, Optional
import uuid

from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.models.product import InventoryTransaction, Product, TransactionType

logger = logging.getLogger(__name__)


class InventoryService:
    """PostgreSQL-backed authoritative inventory operations."""

    @staticmethod
    def search_product(db: Session, query: str, business_id: Optional[Any] = None) -> Optional[Product]:
        """Find the best matching active product by exact or case-insensitive partial name match."""
        q = db.query(Product).filter(Product.is_active == True)
        if business_id:
            q = q.filter(Product.business_id == business_id)

        clean_query = query.strip()
        # 1. Exact match
        product = q.filter(Product.name.ilike(clean_query)).first()
        if product:
            return product

        # 2. Substring match
        product = q.filter(Product.name.ilike(f"%{clean_query}%")).first()
        if product:
            return product

        # 3. Barcode match
        return q.filter(Product.barcode == clean_query).first()

    @staticmethod
    def get_stock(db: Session, product_name: str, business_id: Optional[Any] = None) -> Dict[str, Any]:
        """Fetch verified live stock for a product from the database."""
        product = InventoryService.search_product(db, product_name, business_id)
        if not product:
            return {
                "found": False,
                "query": product_name,
                "message": f"Product '{product_name}' was not found in store inventory.",
            }

        return {
            "found": True,
            "product_id": str(product.id),
            "name": product.name,
            "current_stock": float(product.current_stock),
            "unit": product.unit,
            "selling_price": float(product.selling_price),
            "is_low_stock": bool(product.current_stock <= product.minimum_stock),
            "minimum_stock": float(product.minimum_stock),
        }

    @staticmethod
    def get_low_stock_items(db: Session, business_id: Optional[Any] = None, limit: int = 20) -> List[Dict[str, Any]]:
        """Return products whose current stock is at or below minimum reorder threshold."""
        q = db.query(Product).filter(
            Product.is_active == True,
            Product.current_stock <= Product.minimum_stock,
        )
        if business_id:
            q = q.filter(Product.business_id == business_id)

        items = q.order_by(Product.current_stock.asc()).limit(limit).all()
        return [
            {
                "product_id": str(p.id),
                "name": p.name,
                "current_stock": float(p.current_stock),
                "minimum_stock": float(p.minimum_stock),
                "unit": p.unit,
            }
            for p in items
        ]

    @staticmethod
    def list_all_products(db: Session, business_id: Optional[Any] = None, limit: int = 50) -> List[Dict[str, Any]]:
        """List active products with authoritative selling prices and available stock."""
        q = db.query(Product).filter(Product.is_active == True)
        if business_id:
            q = q.filter(Product.business_id == business_id)

        items = q.order_by(Product.name.asc()).limit(limit).all()
        return [
            {
                "product_id": str(p.id),
                "name": p.name,
                "unit": p.unit,
                "selling_price": float(p.selling_price),
                "current_stock": float(p.current_stock),
            }
            for p in items
        ]

    @staticmethod
    def deduct_stock(
        db: Session,
        product: Product,
        quantity: Decimal,
        reference_id: Optional[str] = None,
        notes: Optional[str] = None,
    ) -> InventoryTransaction:
        """
        Deduct stock atomically and write an immutable inventory transaction audit record.
        Does NOT commit internally to allow outer transactional atomicity.
        """
        stock_before = product.current_stock
        stock_after = stock_before - quantity

        if stock_after < Decimal("0"):
            logger.warning(
                "Stock going negative for product %s (%s). Current: %s, Deducting: %s",
                product.id,
                product.name,
                stock_before,
                quantity,
            )

        product.current_stock = stock_after

        txn = InventoryTransaction(
            business_id=product.business_id,
            product_id=product.id,
            transaction_type=TransactionType.SALE,
            quantity=quantity,
            stock_before=stock_before,
            stock_after=stock_after,
            reference_id=reference_id,
            notes=notes or f"Sale deduction for reference {reference_id}",
        )
        db.add(txn)
        return txn
