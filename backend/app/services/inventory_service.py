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

        # 2. Substring match (e.g., query "salt" in "Tata Salt", or query "tata salt packet" contains "tata salt")
        for p in all_products:
            p_low = p.name.lower()
            if clean in p_low or normalized_query in p_low:
                return p
            # If product name is entirely contained in query and product name has >= 4 chars
            if len(p_low) >= 4 and p_low in clean:
                return p

        # 3. High-confidence fuzzy match on full query (e.g., "suger" vs "sugar")
        prod_map = {p.name.lower(): p for p in all_products}
        name_list = list(prod_map.keys())
        close_full = difflib.get_close_matches(normalized_query, name_list, n=1, cutoff=0.72)
        if close_full:
            return prod_map[close_full[0]]

        # 4. Word token overlap: only if ALL normalized tokens of query are in product tokens
        for p in all_products:
            p_tokens = set(re.split(r"[\s,\-_]+", p.name.lower()))
            if set(normalized_tokens).issubset(p_tokens):
                return p

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
            return {"success": False, "found": False, "message": "Product ka naam empty nahi ho sakta."}

        if not business_id:
            default_biz = db.query(Business).first()
            if not default_biz:
                default_biz = Business(name="Business AI Robot Store", owner_name="Store Owner", business_type="Retail")
                db.add(default_biz)
                db.flush()
            business_id = default_biz.id

        # Check for exact case-insensitive match when creating/restocking
        q_exist = db.query(Product).filter(Product.is_active == True)
        if business_id:
            q_exist = q_exist.filter(Product.business_id == business_id)
        existing = None
        for p in q_exist.all():
            if p.name.lower().strip() == clean_name.lower().strip():
                existing = p
                break
        if not existing:
            # Fallback to high-confidence match for minor typo (e.g. "suger" -> "Sugar")
            existing = InventoryService.search_product(db, clean_name, business_id)
            if existing and existing.name.lower().strip() != clean_name.lower().strip():
                # Don't merge if both are multi-word or have distinct keywords
                clean_words = set(clean_name.lower().split())
                exist_words = set(existing.name.lower().split())
                if len(clean_words.symmetric_difference(exist_words)) > 1:
                    existing = None

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

    @staticmethod
    def reduce_or_sell_stock(
        db: Session,
        product_name: str,
        quantity: float,
        notes: Optional[str] = None,
        business_id: Optional[Any] = None,
    ) -> Dict[str, Any]:
        """Atomically deduct stock for a product, recording a SALE transaction audit."""
        clean_name = product_name.strip()
        if not clean_name:
            return {
                "success": False,
                "found": False,
                "product_name": "",
                "message": "Kis product ka stock kam karna hai? Kripya product ka naam bataiye.",
            }

        product = InventoryService.search_product(db, clean_name, business_id)
        if not product:
            return {
                "success": False,
                "found": False,
                "product_name": clean_name,
                "message": f"Mujhe '{clean_name}' naam ka product inventory mein nahi mila. Product ka naam dobara bataoge?",
            }

        dec_qty = Decimal(str(quantity))
        if dec_qty <= Decimal("0"):
            return {
                "success": False,
                "found": True,
                "product_name": product.name,
                "message": "Quantity to reduce must be greater than zero.",
            }

        stock_before = product.current_stock
        stock_after = max(Decimal("0.00"), stock_before - dec_qty)
        product.current_stock = stock_after

        txn = InventoryTransaction(
            business_id=product.business_id,
            product_id=product.id,
            transaction_type=TransactionType.SALE,
            quantity=dec_qty,
            stock_before=stock_before,
            stock_after=stock_after,
            reference_id="VOICE_SALE",
            notes=notes or f"Stock sold / reduced by {float(dec_qty)} {product.unit} via voice/chat",
        )
        db.add(txn)
        db.commit()
        db.refresh(product)
        logger.info("Stock reduced for %s: %s -> %s (sold %s)", product.name, stock_before, stock_after, dec_qty)

        return {
            "success": True,
            "found": True,
            "product_id": str(product.id),
            "product_name": product.name,
            "quantity_reduced": float(dec_qty),
            "stock_before": float(stock_before),
            "new_stock": float(stock_after),
            "unit": product.unit,
            "message": f"Okay, {product.name} ka stock {int(dec_qty) if dec_qty % 1 == 0 else float(dec_qty)} {product.unit} kam kar diya. Ab {int(stock_after) if stock_after % 1 == 0 else float(stock_after)} {product.unit} available hain.",
        }

    @staticmethod
    def add_or_restock_product(
        db: Session,
        product_name: str,
        quantity: float = 1.0,
        unit: Optional[str] = None,
        selling_price: float = 0.0,
        business_id: Optional[Any] = None,
    ) -> Dict[str, Any]:
        """Atomically add stock for an existing product or register new with added stock."""
        clean_name = product_name.strip()
        if not clean_name:
            return {
                "success": False,
                "found": False,
                "product_name": "",
                "message": "Kis product ka stock add karna hai? Kripya product ka naam bataiye.",
            }

        product = InventoryService.search_product(db, clean_name, business_id)
        dec_qty = Decimal(str(quantity))

        if product:
            stock_before = product.current_stock
            product.current_stock += dec_qty
            if selling_price and Decimal(str(selling_price)) > Decimal("0"):
                product.selling_price = Decimal(str(selling_price)).quantize(Decimal("0.01"))
            txn = InventoryTransaction(
                business_id=product.business_id,
                product_id=product.id,
                transaction_type=TransactionType.STOCK_IN,
                quantity=dec_qty,
                stock_before=stock_before,
                stock_after=product.current_stock,
                reference_id="VOICE_RESTOCK",
                notes=f"Restocked {float(dec_qty)} {product.unit} via voice/chat",
            )
            db.add(txn)
            db.commit()
            db.refresh(product)
            return {
                "success": True,
                "found": True,
                "product_id": str(product.id),
                "product_name": product.name,
                "quantity_added": float(dec_qty),
                "new_stock": float(product.current_stock),
                "unit": product.unit,
                "message": f"{product.name} mein {int(dec_qty) if dec_qty % 1 == 0 else float(dec_qty)} {product.unit} add kar diye. Ab total {int(product.current_stock) if product.current_stock % 1 == 0 else float(product.current_stock)} {product.unit} available hain.",
            }
        else:
            # Add new product with selling_price if available
            res = InventoryService.add_or_update_product(
                db=db,
                name=clean_name,
                unit=unit or "packet",
                selling_price=selling_price,
                stock=float(dec_qty),
                business_id=business_id,
            )
            price_str = f" @ ₹{res['selling_price']:.0f}" if res.get("selling_price") else ""
            return {
                "success": True,
                "found": False,
                "product_id": res["id"],
                "product_name": res["name"],
                "quantity_added": float(dec_qty),
                "new_stock": float(dec_qty),
                "unit": res.get("unit", "packet"),
                "selling_price": res.get("selling_price", 0.0),
                "message": f"Naya product '{res['name']}' register kiya aur {float(dec_qty):.0f} {res.get('unit', 'packet')}{price_str} stock add kar diya.",
            }

    @staticmethod
    def add_multiple_products(
        db: Session,
        products: List[Dict[str, Any]],
        business_id: Optional[Any] = None,
    ) -> Dict[str, Any]:
        """Create or restock multiple products/varieties in batch in store inventory."""
        if not products:
            return {"success": False, "added_count": 0, "products": [], "message": "Koi product details nahi mili."}

        results = []
        for p in products:
            name = str(p.get("name", "")).strip()
            if not name:
                continue
            price = float(p.get("selling_price") or p.get("price") or 0.0)
            stock = float(p.get("quantity") or p.get("stock") or 10.0)
            unit = str(p.get("unit") or "pieces").strip()
            purch_price = float(p.get("purchase_price") or (price * 0.75 if price else 0.0))
            res = InventoryService.add_or_update_product(
                db=db,
                name=name,
                unit=unit,
                selling_price=price,
                stock=stock,
                purchase_price=purch_price,
                business_id=business_id,
            )
            results.append(res)

        items_summary = [f"{r['name']} ({r['current_stock']:.0f} {r['unit']} @ ₹{r['selling_price']:.0f})" for r in results]
        return {
            "success": True,
            "added_count": len(results),
            "products": results,
            "summary": ", ".join(items_summary),
            "message": f"{len(results)} varieties add ho gayi hain: {', '.join(items_summary)}.",
        }

    @staticmethod
    def clear_all_inventory(db: Session, business_id: Optional[Any] = None) -> Dict[str, Any]:
        """Reset or clear all products/stock in inventory."""
        q = db.query(Product).filter(Product.is_active == True)
        if business_id:
            q = q.filter(Product.business_id == business_id)
        products = q.all()
        count = len(products)
        for p in products:
            p.current_stock = Decimal("0.00")
            p.is_active = False
        db.commit()
        return {
            "success": True,
            "cleared_count": count,
            "message": f"Dukan ke sabhi {count} products ka stock clear aur remove kar diya gaya hai. Ab aap naye items ek-ek karke add kar sakte hain.",
        }
