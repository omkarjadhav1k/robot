"""Authoritative Inventory Service querying and modifying PostgreSQL product stock with fuzzy matching and aliases."""

from decimal import Decimal
import difflib
import logging
import re
from typing import Any, Dict, List, Optional
import uuid

from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.models.business import Business
from app.models.product import InventoryTransaction, Product, TransactionType

logger = logging.getLogger(__name__)

# Common Hindi / Hinglish grocery terms mapped to English catalog equivalents
GROCERY_ALIASES = {
    "chawal": "rice",
    "rice": "rice",
    "doodh": "milk",
    "milk": "milk",
    "cheeni": "sugar",
    "shakkar": "sugar",
    "sugar": "sugar",
    "suger": "sugar",
    "namak": "salt",
    "salt": "salt",
    "tel": "oil",
    "oil": "oil",
    "aata": "flour",
    "atta": "flour",
    "wheat": "flour",
    "flour": "flour",
    "chai": "tea",
    "chay": "tea",
    "tea": "tea",
    "sandwich": "sandwich",
    "coffee": "coffee",
    "biscuit": "biscuit",
    "biscuits": "biscuit",
}

STOPWORDS = {
    "abhi", "karo", "do", "ek", "yeh", "woh", "samaan", "item", "so", "bhi",
    "aur", "and", "please", "to", "ka", "ki", "ke", "me", "mein", "add", "bill",
}


class InventoryService:
    """PostgreSQL-backed authoritative inventory operations with smart fuzzy matching."""

    @staticmethod
    def search_product(db: Session, query: str, business_id: Optional[Any] = None) -> Optional[Product]:
        """
        Find best matching active product using:
        1. Stopword filtering
        2. Alias normalization (Hindi/English synonyms)
        3. Exact and substring database search
        4. Token-level matching
        5. Levenshtein fuzzy string distance (e.g. 'suger' -> 'Sugar', 'tat salte' -> 'Tata Salt')
        """
        clean = query.strip().lower()
        if not clean or clean in STOPWORDS or len(clean) < 2:
            return None

        # Clean filler words
        tokens = [w for w in re.split(r"[\s,\-_]+", clean) if w not in STOPWORDS]
        if not tokens:
            return None

        # Check aliases
        normalized_tokens = [GROCERY_ALIASES.get(t, t) for t in tokens]
        normalized_query = " ".join(normalized_tokens)

        q = db.query(Product).filter(Product.is_active == True)
        if business_id:
            q = q.filter(Product.business_id == business_id)

        all_products = q.all()
        if not all_products:
            return None

        # 1. Exact match (case-insensitive)
        for p in all_products:
            p_low = p.name.lower()
            if p_low == clean or p_low == normalized_query:
                return p

        # 2. Substring match
        for p in all_products:
            p_low = p.name.lower()
            if clean in p_low or normalized_query in p_low:
                return p

        # 3. Word token overlap
        for p in all_products:
            p_tokens = set(re.split(r"[\s,\-_]+", p.name.lower()))
            if any(t in p_tokens for t in normalized_tokens if len(t) > 2):
                return p

        # 4. Fuzzy distance matching (difflib)
        prod_map = {p.name.lower(): p for p in all_products}
        name_list = list(prod_map.keys())

        # Match against full normalized query
        close_full = difflib.get_close_matches(normalized_query, name_list, n=1, cutoff=0.55)
        if close_full:
            return prod_map[close_full[0]]

        # Match against individual tokens
        for t in normalized_tokens:
            if len(t) >= 3:
                close_token = difflib.get_close_matches(t, name_list, n=1, cutoff=0.60)
                if close_token:
                    return prod_map[close_token[0]]

        return None

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
        """Deduct stock atomically and write an immutable inventory transaction audit record."""
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

    @staticmethod
    def add_or_update_product(
        db: Session,
        name: str,
        unit: str = "packet",
        selling_price: float = 0.0,
        stock: float = 0.0,
        current_stock: Optional[float] = None,
        purchase_price: Optional[float] = None,
        minimum_stock: float = 5.0,
        business_id: Optional[Any] = None,
    ) -> Dict[str, Any]:
        """Create a new product or restock an existing product in store inventory."""
        if current_stock is not None and (stock == 0.0 or stock is None):
            stock = current_stock
        clean_name = name.strip()
        if not clean_name:
            raise ValueError("Product name cannot be empty.")

        if not business_id:
            default_biz = db.query(Business).first()
            if not default_biz:
                default_biz = Business(name="Business AI Robot Store", owner_name="Store Owner", business_type="Retail")
                db.add(default_biz)
                db.flush()
            business_id = default_biz.id

        existing = InventoryService.search_product(db, clean_name, business_id)
        if existing:
            # Restock existing product
            stock_before = existing.current_stock
            existing.current_stock += Decimal(str(stock))
            if selling_price and Decimal(str(selling_price)) > Decimal("0"):
                existing.selling_price = Decimal(str(selling_price)).quantize(Decimal("0.01"))

            txn = InventoryTransaction(
                business_id=business_id,
                product_id=existing.id,
                transaction_type=TransactionType.STOCK_IN,
                quantity=Decimal(str(stock)),
                stock_before=stock_before,
                stock_after=existing.current_stock,
                reference_id="VOICE_RESTOCK",
                notes=f"Restocked {stock} {existing.unit} via voice command",
            )
            db.add(txn)
            db.commit()
            db.refresh(existing)
            return {
                "created": False,
                "id": str(existing.id),
                "name": existing.name,
                "current_stock": float(existing.current_stock),
                "selling_price": float(existing.selling_price),
                "unit": existing.unit,
                "message": f"Updated {existing.name}: new stock is {float(existing.current_stock)} {existing.unit} at ₹{float(existing.selling_price):.2f}.",
            }

        # Create new product
        dec_sell_price = Decimal(str(selling_price)).quantize(Decimal("0.01"))
        dec_purch_price = (
            Decimal(str(purchase_price)).quantize(Decimal("0.01"))
            if purchase_price
            else (dec_sell_price * Decimal("0.80")).quantize(Decimal("0.01"))
        )
        dec_stock = Decimal(str(stock))
        dec_min_stock = Decimal(str(minimum_stock))

        new_prod = Product(
            business_id=business_id,
            name=clean_name,
            unit=unit.strip().lower(),
            selling_price=dec_sell_price,
            purchase_price=dec_purch_price,
            current_stock=dec_stock,
            minimum_stock=dec_min_stock,
            is_active=True,
        )
        db.add(new_prod)
        db.flush()

        txn = InventoryTransaction(
            business_id=business_id,
            product_id=new_prod.id,
            transaction_type=TransactionType.STOCK_IN,
            quantity=Decimal(str(stock)),
            stock_before=Decimal("0.00"),
            stock_after=Decimal(str(stock)),
            reference_id="INITIAL_STOCK",
            notes=f"Initial stock added via voice command",
        )
        db.add(txn)
        db.commit()
        db.refresh(new_prod)

        return {
            "created": True,
            "id": str(new_prod.id),
            "name": new_prod.name,
            "current_stock": float(new_prod.current_stock),
            "selling_price": float(new_prod.selling_price),
            "unit": new_prod.unit,
            "message": f"Added new product '{new_prod.name}' with stock {float(new_prod.current_stock)} {new_prod.unit} at ₹{float(new_prod.selling_price):.2f}.",
        }
