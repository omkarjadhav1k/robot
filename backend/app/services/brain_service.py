"""Brain Service managing learned business rules, operational context, and dynamic AI injection."""

from datetime import datetime, timezone
import logging
import re
from typing import Any, Dict, List, Optional
import uuid

from sqlalchemy.orm import Session

from app.models.business import Business
from app.models.instruction import BrainInstruction

logger = logging.getLogger("business_ai_robot.brain")

TEACH_PREFIXES = (
    "remember that",
    "remember:",
    "learn this rule",
    "learn this:",
    "rule:",
    "store rule:",
    "always remember",
    "dhyan me rakho",
    "yaad rakhna",
    "yaad rakho",
    "lakshat thev",
    "lakshat theva",
    "our shop timing",
    "store timing",
    "opening timing",
    "closing timing",
)


class BrainService:
    """Service layer for teaching, storing, toggling, and fetching dynamic brain instructions."""

    @staticmethod
    def _resolve_business_id(db: Session, business_id: Optional[Any] = None) -> Optional[uuid.UUID]:
        """Helper to ensure a valid tenant business_id."""
        if business_id:
            return business_id if isinstance(business_id, uuid.UUID) else uuid.UUID(str(business_id))
        first_biz = db.query(Business).first()
        return first_biz.id if first_biz else None

    @classmethod
    def get_active_instructions(
        cls,
        db: Session,
        business_id: Optional[Any] = None,
    ) -> List[BrainInstruction]:
        """Fetch all currently active brain instructions for prompt injection."""
        biz_id = cls._resolve_business_id(db, business_id)
        if not biz_id:
            return []
        return (
            db.query(BrainInstruction)
            .filter(BrainInstruction.business_id == biz_id, BrainInstruction.is_active.is_(True))
            .order_by(BrainInstruction.created_at.asc())
            .all()
        )

    @classmethod
    def get_instruction_strings(
        cls,
        db: Session,
        business_id: Optional[Any] = None,
    ) -> List[str]:
        """Return list of instruction text strings for injection into Gemini AI prompts."""
        instructions = cls.get_active_instructions(db, business_id)
        return [f"[{item.category}] {item.instruction}" for item in instructions]

    @classmethod
    def list_all_instructions(
        cls,
        db: Session,
        business_id: Optional[Any] = None,
    ) -> List[Dict[str, Any]]:
        """List all brain instructions (both active and inactive) with metadata."""
        biz_id = cls._resolve_business_id(db, business_id)
        if not biz_id:
            return []
        records = (
            db.query(BrainInstruction)
            .filter(BrainInstruction.business_id == biz_id)
            .order_by(BrainInstruction.created_at.desc())
            .all()
        )
        return [
            {
                "id": str(r.id),
                "instruction": r.instruction,
                "category": r.category,
                "is_active": r.is_active,
                "source": r.source,
                "created_at": r.created_at.isoformat() if r.created_at else None,
            }
            for r in records
        ]

    @classmethod
    def add_instruction(
        cls,
        db: Session,
        instruction: str,
        category: str = "RULE",
        source: str = "WEB_PANEL",
        business_id: Optional[Any] = None,
    ) -> BrainInstruction:
        """Add and persist a new custom brain instruction."""
        clean_text = instruction.strip()
        if not clean_text:
            raise ValueError("Instruction text cannot be empty")

        biz_id = cls._resolve_business_id(db, business_id)
        if not biz_id:
            raise ValueError("No business tenant found to associate instruction with")

        # Auto-detect category if general RULE is provided
        cat = category.upper()
        if cat == "RULE":
            lower_text = clean_text.lower()
            if any(w in lower_text for w in ("discount", "off", "percentage", "%", "chhut")):
                cat = "DISCOUNT"
            elif any(w in lower_text for w in ("timing", "hours", "open", "close", "baje", "samay", "vel")):
                cat = "TIMING"
            elif any(w in lower_text for w in ("credit", "udhar", "udhari", "balance", "limit")):
                cat = "CREDIT"
            elif any(w in lower_text for w in ("greet", "namaste", "hello", "welcome", "polite")):
                cat = "BEHAVIOR"

        item = BrainInstruction(
            business_id=biz_id,
            instruction=clean_text,
            category=cat,
            is_active=True,
            source=source,
        )
        db.add(item)
        db.commit()
        db.refresh(item)
        logger.info("Saved new BrainInstruction [%s]: '%s' (id=%s)", cat, clean_text, item.id)
        return item

    @classmethod
    def toggle_instruction(
        cls,
        db: Session,
        instruction_id: Any,
        is_active: Optional[bool] = None,
        business_id: Optional[Any] = None,
    ) -> Optional[BrainInstruction]:
        """Toggle an instruction's active status."""
        uid = instruction_id if isinstance(instruction_id, uuid.UUID) else uuid.UUID(str(instruction_id))
        item = db.query(BrainInstruction).filter(BrainInstruction.id == uid).first()
        if not item:
            return None

        if is_active is None:
            item.is_active = not item.is_active
        else:
            item.is_active = is_active

        db.commit()
        db.refresh(item)
        logger.info("Toggled BrainInstruction %s to is_active=%s", item.id, item.is_active)
        return item

    @classmethod
    def delete_instruction(
        cls,
        db: Session,
        instruction_id: Any,
        business_id: Optional[Any] = None,
    ) -> bool:
        """Delete a brain instruction from the database."""
        uid = instruction_id if isinstance(instruction_id, uuid.UUID) else uuid.UUID(str(instruction_id))
        item = db.query(BrainInstruction).filter(BrainInstruction.id == uid).first()
        if not item:
            return False
        db.delete(item)
        db.commit()
        logger.info("Deleted BrainInstruction %s", uid)
        return True

    @classmethod
    def detect_and_learn_rule(
        cls,
        db: Session,
        message: str,
        source: str = "CHAT_TEACH",
        business_id: Optional[Any] = None,
    ) -> Optional[BrainInstruction]:
        """
        Inspect message for direct teaching patterns (e.g. 'Remember that Ramesh gets 5% discount').
        If matched, cleanly extracts and saves the rule permanently.
        """
        msg_clean = message.strip()
        msg_lower = msg_clean.lower()

        # Check for explicit teaching triggers
        for prefix in TEACH_PREFIXES:
            if msg_lower.startswith(prefix):
                # Strip prefix
                rule_body = msg_clean[len(prefix):].strip(" :,.-\t\r\n")
                if len(rule_body) >= 5:
                    return cls.add_instruction(
                        db=db,
                        instruction=rule_body,
                        source=source,
                        business_id=business_id,
                    )

        # Regex for 'Teach: <rule>' or 'Rule: <rule>'
        match = re.match(r'^(?:teach|rule|instruction|note)\s*[:\-]\s*(.+)$', msg_clean, re.IGNORECASE)
        if match:
            rule_body = match.group(1).strip()
            if len(rule_body) >= 5:
                return cls.add_instruction(
                    db=db,
                    instruction=rule_body,
                    source=source,
                    business_id=business_id,
                )

        return None
