"""Deterministic Entity Extractor with alias resolution, fuzzy product disambiguation, and pronoun context."""

from decimal import Decimal
import logging
import re
from typing import Any, Dict, List, Optional, Set, Tuple
from sqlalchemy.orm import Session

from app.models.billing import Customer
from app.models.product import Product

logger = logging.getLogger("robot.engine.entities")

# Canonical Product Aliases Dictionary
PRODUCT_ALIASES: Dict[str, List[str]] = {
    "maggi": ["maggi", "maggie", "maggi noodles", "noodles", "meggi"],
    "parle g": ["parle g", "parleg", "parle-g", "parle biscuit", "parle"],
    "tata salt": ["tata salt", "namak", "tata namak", "salt", "solt", "mith"],
    "surf excel": ["surf excel", "surf", "surf detergent", "surf packet"],
    "basmati rice": ["basmati rice", "basmati", "chawal", "rice", "raice"],
    "sugar": ["sugar", "suger", "shugar", "sugr", "shakkar", "cheeni", "sakhar"],
    "milk": ["milk", "doodh", "dudh"],
    "tea": ["tea", "chai", "chaha", "tea powder"],
    "veg sandwich": ["veg sandwich", "sandwich"],
    "sunflower oil": ["sunflower oil", "oil", "tel", "oyil"],
    "wheat flour": ["wheat flour", "aata", "atta", "gehu aata"],
}

# Number words mapping (Hindi / English)
NUMBER_WORDS: Dict[str, float] = {
    "ek": 1.0, "one": 1.0, "a": 1.0,
    "do": 2.0, "two": 2.0,
    "teen": 3.0, "three": 3.0,
    "char": 4.0, "four": 4.0,
    "paanch": 5.0, "panch": 5.0, "five": 5.0,
    "che": 6.0, "chhah": 6.0, "six": 6.0,
    "saat": 7.0, "seven": 7.0,
    "aath": 8.0, "eight": 8.0,
    "nau": 9.0, "nine": 9.0,
    "das": 10.0, "ten": 10.0,
    "aadha": 0.5, "half": 0.5,
    "dedh": 1.5, "dhai": 2.5,
}

# Hardware Devices Mapping
DEVICE_CHANNEL_MAP: Dict[str, int] = {
    "light": 1, "batti": 1, "tubelight": 1, "bulb": 1, "lamp": 1,
    "fan": 2, "pankha": 2, "cooler": 2,
    "socket": 3, "plug": 3, "charger": 3,
    "aux": 4, "motor": 4, "pump": 4, "ac": 4,
}


class ExtractedEntities:
    def __init__(
        self,
        product: Optional[str] = None,
        product_obj: Optional[Product] = None,
        is_ambiguous: bool = False,
        ambiguous_candidates: Optional[List[str]] = None,
        customer: Optional[str] = None,
        customer_obj: Optional[Customer] = None,
        quantity: Optional[float] = None,
        amount: Optional[float] = None,
        payment_method: str = "CASH",
        bill_number: Optional[str] = None,
        device: Optional[str] = None,
        relay_channel: Optional[int] = None,
        relay_state: Optional[str] = None,
        items: Optional[List[Dict[str, Any]]] = None,
    ):
        self.product = product
        self.product_obj = product_obj
        self.is_ambiguous = is_ambiguous
        self.ambiguous_candidates = ambiguous_candidates or []
        self.customer = customer
        self.customer_obj = customer_obj
        self.quantity = quantity
        self.amount = amount
        self.payment_method = payment_method
        self.bill_number = bill_number
        self.device = device
        self.relay_channel = relay_channel
        self.relay_state = relay_state
        self.items = items or []
        self.raw_entities: Dict[str, Any] = {}

    def to_dict(self) -> Dict[str, Any]:
        return {
            "product": self.product,
            "is_ambiguous": self.is_ambiguous,
            "ambiguous_candidates": self.ambiguous_candidates,
            "customer": self.customer,
            "quantity": self.quantity,
            "amount": self.amount,
            "payment_method": self.payment_method,
            "bill_number": self.bill_number,
            "device": self.device,
            "relay_channel": self.relay_channel,
            "relay_state": self.relay_state,
            "items": self.items,
        }


class EntityExtractor:
    """Deterministic extractor for business entities, disambiguation, and multi-turn context."""

    @classmethod
    def normalize_text(cls, text: str) -> str:
        """Clean noise, punctuation, and extra whitespace."""
        clean = text.lower().strip()
        # Keep word chars, spaces, numbers, and basic symbols
        clean = re.sub(r"[^\w\s\.\-₹]", " ", clean)
        clean = re.sub(r"\s+", " ", clean).strip()
        return clean

    @classmethod
    def extract_device_and_relay(cls, text: str) -> Tuple[Optional[str], Optional[int], Optional[str]]:
        """Extract appliance name, relay channel number, and desired state (on/off)."""
        lower = text.lower()
        state = None
        if any(w in lower for w in ["on", "chalu", "jalado", "start", "lagao", "1"]):
            state = "on"
        elif any(w in lower for w in ["off", "band", "bujhao", "stop", "0"]):
            state = "off"

        # Explicit relay channel
        relay_m = re.search(r"relay\s*([1-4])", lower)
        if relay_m:
            ch = int(relay_m.group(1))
            return f"relay {ch}", ch, state

        for dev_name, ch in DEVICE_CHANNEL_MAP.items():
            if re.search(r"\b" + re.escape(dev_name) + r"\b", lower):
                return dev_name, ch, state

        return None, None, state

    @classmethod
    def extract_quantity(cls, text: str) -> Optional[float]:
        """Extract numerical quantity from digits or common words."""
        lower = text.lower()
        # Direct numeric match (e.g. 5, 2.5)
        num_match = re.search(r"\b(\d+(?:\.\d+)?)\s*(?:packet|packets|kg|kilo|gram|gm|cup|pcs|bottle|bag)?\b", lower)
        if num_match:
            try:
                return float(num_match.group(1))
            except ValueError:
                pass

        # Word numbers
        for word, val in NUMBER_WORDS.items():
            if re.search(r"\b" + re.escape(word) + r"\b", lower):
                return val

        return None

    @classmethod
    def extract_amount(cls, text: str) -> Optional[float]:
        """Extract currency amount from text (e.g. ₹500, 250 rs, 100 rupaye)."""
        lower = text.lower()
        # Pattern 1: ₹500 or Rs 500
        m1 = re.search(r"(?:₹|rs\.?|rupees?|rupaye?)\s*(\d+(?:\.\d+)?)", lower)
        if m1:
            try:
                return float(m1.group(1))
            except ValueError:
                pass

        # Pattern 2: 500 rupaye / 500 rs / 500 diye
        m2 = re.search(r"(\d+(?:\.\d+)?)\s*(?:₹|rs\.?|rupees?|rupaye?|diye|jama|baki|ka|wala)", lower)
        if m2:
            try:
                return float(m2.group(1))
            except ValueError:
                pass

        # Fallback to standalone large number
        m3 = re.search(r"\b(\d{2,6})\b", lower)
        if m3:
            try:
                return float(m3.group(1))
            except ValueError:
                pass

        return None

    @classmethod
    def resolve_product(
        cls,
        text: str,
        db: Session,
        business_id: Optional[Any] = None,
        last_product: Optional[str] = None,
    ) -> Tuple[Optional[Product], Optional[str], bool, List[str]]:
        """
        Extract and disambiguate product:
        - Checks pronoun resolution ('uska', 'usme se', 'iska')
        - Matches canonical aliases dictionary
        - Queries database products
        - If multiple variants exist (e.g. Maggi 70g, Maggi 140g), flags ambiguous=True with candidate list.
        """
        lower = text.lower()

        # 1. Pronoun Resolution (Section 19)
        pronoun_match = any(p in lower for p in ["uska", "usme se", "iska", "isme se", "woh", "woh wala", "wahi"])
        if pronoun_match and last_product:
            p_obj = cls._query_db_product(db, last_product, business_id)
            if p_obj:
                return p_obj, p_obj.name, False, []

        # 2. Check Alias Dictionaries first
        candidate_term = None
        for canonical, aliases in PRODUCT_ALIASES.items():
            for alias in aliases:
                if re.search(r"\b" + re.escape(alias) + r"\b", lower):
                    candidate_term = canonical
                    break
            if candidate_term:
                break

        # If alias matched, check database for all products containing this alias
        search_query = candidate_term or lower
        matched_products = cls._find_matching_products(db, search_query, business_id)

        # 3. Check Section 21: Ambiguous product disambiguation
        distinct_names = list(dict.fromkeys([p.name for p in matched_products]))
        if len(distinct_names) > 1:
            # Check if user already specified an exact variant (e.g. '70g' or 'family pack')
            exact_match = None
            for p in matched_products:
                p_name_lower = p.name.lower()
                # If specific keywords appear in text
                specific_tokens = [tok for tok in p_name_lower.split() if tok not in (candidate_term or "").split()]
                if specific_tokens and all(tok in lower for tok in specific_tokens):
                    exact_match = p
                    break
            if exact_match:
                return exact_match, exact_match.name, False, []

            # Otherwise return ambiguous flag with variant names
            candidate_names = distinct_names[:4]
            return None, (candidate_term or matched_products[0].name), True, candidate_names

        elif len(matched_products) >= 1:
            p = matched_products[0]
            return p, p.name, False, []

        # Fallback to direct DB query with extracted nouns
        extracted_tokens = [t for t in lower.split() if t not in [
            "robo", "max", "ka", "ki", "ke", "ko", "stock", "rate", "price", "kitna", "hai",
            "batao", "check", "karo", "bhai", "aaj", "ek", "do", "teen", "ruko"
        ]]
        if extracted_tokens:
            guess_term = " ".join(extracted_tokens[:3])
            single = cls._query_db_product(db, guess_term, business_id)
            if single:
                return single, single.name, False, []

        return None, (last_product if pronoun_match else None), False, []

    @classmethod
    def resolve_customer(
        cls,
        text: str,
        db: Session,
        business_id: Optional[Any] = None,
        last_customer: Optional[str] = None,
    ) -> Tuple[Optional[Customer], Optional[str]]:
        """Extract customer with pronoun support and DB verification."""
        lower = text.lower()

        # Pronoun check
        if any(p in lower for p in ["uska", "usne", "unka", "unhone", "iska"]) and last_customer:
            c_obj = cls._query_db_customer(db, last_customer, business_id)
            return c_obj, (c_obj.name if c_obj else last_customer)

        # Query all customers for matching names
        q = db.query(Customer)
        if business_id:
            q = q.filter(Customer.business_id == business_id)
        customers = q.all()

        for c in customers:
            c_name_lower = c.name.lower()
            if re.search(r"\b" + re.escape(c_name_lower) + r"\b", lower):
                return c, c.name

        # Match potential name tokens (capitalized in original or before 'ka'/'ne')
        m = re.search(r"\b([a-zA-Z]{3,15})\s+(?:ka|ne|ko|se)\b", text, re.IGNORECASE)
        if m:
            token = m.group(1).strip()
            if token.lower() not in ["stock", "rate", "price", "bill", "aaj", "kal", "payment"]:
                c_obj = cls._query_db_customer(db, token, business_id)
                return c_obj, (c_obj.name if c_obj else token)

        return None, None

    @classmethod
    def extract_all(
        cls,
        text: str,
        db: Session,
        business_id: Optional[Any] = None,
        last_product: Optional[str] = None,
        last_customer: Optional[str] = None,
    ) -> ExtractedEntities:
        """Master extraction pipeline filling all entity slots."""
        norm_text = cls.normalize_text(text)
        res = ExtractedEntities()

        # 1. Product resolution with disambiguation
        p_obj, p_name, is_ambig, candidates = cls.resolve_product(
            norm_text, db, business_id, last_product=last_product
        )
        res.product_obj = p_obj
        res.product = p_name
        res.is_ambiguous = is_ambig
        res.ambiguous_candidates = candidates

        # 2. Customer resolution
        c_obj, c_name = cls.resolve_customer(
            text, db, business_id, last_customer=last_customer
        )
        res.customer_obj = c_obj
        res.customer = c_name

        # 3. Numbers, Quantities & Amounts
        res.quantity = cls.extract_quantity(norm_text)
        res.amount = cls.extract_amount(norm_text)

        # 4. Hardware Relay / Device
        dev, ch, st = cls.extract_device_and_relay(norm_text)
        res.device = dev
        res.relay_channel = ch
        res.relay_state = st

        # 5. Bill Number pattern (e.g. INV-20260908-1234 or INV-1025)
        bill_m = re.search(r"\b(inv[-_]\d+[-_]?\d*)\b", norm_text, re.IGNORECASE)
        if bill_m:
            res.bill_number = bill_m.group(1).upper()

        # 6. Payment method
        if any(w in norm_text for w in ["upi", "gpay", "phonepe", "paytm", "online"]):
            res.payment_method = "UPI"
        elif any(w in norm_text for w in ["credit", "udhar", "udhari"]):
            res.payment_method = "CREDIT"
        elif any(w in norm_text for w in ["card", "debit", "swipe"]):
            res.payment_method = "CARD"
        else:
            res.payment_method = "CASH"

        # 7. Line items for billing
        if res.product and res.quantity:
            res.items.append({"name": res.product, "quantity": res.quantity})

        return res

    @classmethod
    def _find_matching_products(cls, db: Session, term: str, business_id: Optional[Any]) -> List[Product]:
        """Find products containing the term."""
        q = db.query(Product).filter(Product.is_active == True)
        if business_id:
            q = q.filter(Product.business_id == business_id)

        clean_term = term.strip()
        matches = q.filter(Product.name.ilike(f"%{clean_term}%")).all()
        if not matches:
            # Try matching individual words
            for word in clean_term.split():
                if len(word) > 2 and word not in ["packet", "packets", "cup", "bottle", "box", "kg", "rate", "price", "kitna", "hai", "kya"]:
                    matches = q.filter(Product.name.ilike(f"%{word}%")).all()
                    if matches:
                        break
        if not matches:
            from app.services.inventory_service import InventoryService
            fuzzy_p = InventoryService.search_product(db, clean_term, business_id)
            if fuzzy_p:
                matches = [fuzzy_p]
        return matches

    @classmethod
    def _query_db_product(cls, db: Session, name: str, business_id: Optional[Any]) -> Optional[Product]:
        q = db.query(Product).filter(Product.is_active == True)
        if business_id:
            q = q.filter(Product.business_id == business_id)
        return q.filter(Product.name.ilike(name.strip())).first()

    @classmethod
    def _query_db_customer(cls, db: Session, name: str, business_id: Optional[Any]) -> Optional[Customer]:
        q = db.query(Customer)
        if business_id:
            q = q.filter(Customer.business_id == business_id)
        return q.filter(Customer.name.ilike(f"%{name.strip()}%")).first()
