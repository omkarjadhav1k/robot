"""Owner verification, PBKDF2 PIN hashing, temporary authorization sessions, and security audit."""

import enum
import hashlib
import hmac
import logging
import secrets
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional, Tuple
from sqlalchemy.orm import Session

from app.models.security import OwnerSecurity, SecurityEvent

logger = logging.getLogger("max.security")

# In-memory storage for active owner authorization sessions
# Token -> {"business_id": uuid, "expires_at": datetime, "robot_id": str}
_ACTIVE_AUTH_SESSIONS: Dict[str, Dict[str, Any]] = {}


class RiskLevel(str, enum.Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"


class SecurityService:
    """Security management for owner PIN verification, risk assessment, and audit trails."""

    PBKDF2_ROUNDS = 600000

    @classmethod
    def hash_pin(cls, pin: str) -> str:
        """Securely hash a 6-digit PIN using PBKDF2-HMAC-SHA256 with a unique salt."""
        salt = secrets.token_hex(16)
        key = hashlib.pbkdf2_hmac(
            "sha256",
            pin.encode("utf-8"),
            salt.encode("utf-8"),
            cls.PBKDF2_ROUNDS,
        )
        return f"pbkdf2:sha256:{cls.PBKDF2_ROUNDS}${salt}${key.hex()}"

    @classmethod
    def verify_pin_hash(cls, pin: str, hashed: str) -> bool:
        """Constant-time verification of a PIN against stored PBKDF2 hash."""
        try:
            algorithm, salt, stored_key = hashed.split("$")
            _, _, rounds_str = algorithm.split(":")
            rounds = int(rounds_str)
            calculated_key = hashlib.pbkdf2_hmac(
                "sha256",
                pin.encode("utf-8"),
                salt.encode("utf-8"),
                rounds,
            )
            return hmac.compare_digest(calculated_key.hex(), stored_key)
        except Exception as e:
            logger.error(f"Error during PIN verification: {e}")
            return False

    @classmethod
    def get_or_create_owner_security(cls, db: Session, business_id: uuid.UUID) -> OwnerSecurity:
        """Fetch existing owner security record or initialize with default PIN 123456."""
        sec = db.query(OwnerSecurity).filter(OwnerSecurity.business_id == business_id).first()
        if not sec:
            default_pin = "123456"
            sec = OwnerSecurity(
                business_id=business_id,
                pin_hash=cls.hash_pin(default_pin),
                failed_attempts=0,
                locked_until=None,
            )
            db.add(sec)
            db.commit()
            db.refresh(sec)
            logger.info("Initialized default owner PIN for business %s", business_id)
        return sec

    @classmethod
    def verify_owner(
        cls,
        db: Session,
        business_id: uuid.UUID,
        pin: str,
        robot_id: Optional[str] = None,
        source_action: str = "OWNER_LOGIN",
    ) -> Tuple[bool, str, Optional[str]]:
        """
        Verify owner PIN against stored hash with brute-force lockout protection.
        Returns (success, message, auth_token).
        CRITICAL: PIN is NEVER logged or stored.
        """
        sec = cls.get_or_create_owner_security(db, business_id)
        now = datetime.now(timezone.utc)

        # Check if currently locked
        if sec.locked_until:
            locked_dt = sec.locked_until if sec.locked_until.tzinfo else sec.locked_until.replace(tzinfo=timezone.utc)
            if now < locked_dt:
                remaining_secs = int((locked_dt - now).total_seconds())
                mins = (remaining_secs // 60) + 1
                cls._log_event(db, business_id, robot_id, "PIN_BLOCKED_LOCKED", False, {"source_action": source_action})
                return False, f"Account is locked due to repeated incorrect PIN attempts. Please try again in {mins} minutes.", None

        # Clean digits
        clean_pin = pin.strip()
        if not clean_pin.isdigit() or len(clean_pin) != 6:
            return False, "Invalid format. Owner PIN must be exactly 6 digits.", None

        # Verify hash
        is_valid = cls.verify_pin_hash(clean_pin, sec.pin_hash)

        if is_valid:
            sec.failed_attempts = 0
            sec.locked_until = None
            db.commit()

            # Issue short-lived authorization token (valid 300 seconds / 5 minutes)
            token = f"auth_{secrets.token_urlsafe(24)}"
            expires_at = now + timedelta(seconds=300)
            _ACTIVE_AUTH_SESSIONS[token] = {
                "business_id": business_id,
                "expires_at": expires_at,
                "robot_id": robot_id,
            }

            cls._log_event(db, business_id, robot_id, "PIN_VERIFY_SUCCESS", True, {"source_action": source_action})
            return True, "Owner verification successful. Temporary authorization granted for 5 minutes.", token
        else:
            sec.failed_attempts = (sec.failed_attempts or 0) + 1
            remaining = max(0, 3 - sec.failed_attempts)
            if sec.failed_attempts >= 3:
                sec.locked_until = now + timedelta(minutes=5)
                db.commit()
                cls._log_event(db, business_id, robot_id, "PIN_ACCOUNT_LOCKED", False, {"attempts": sec.failed_attempts})
                return False, "Incorrect PIN. Account locked for 5 minutes due to 3 consecutive failures.", None
            else:
                db.commit()
                cls._log_event(db, business_id, robot_id, "PIN_VERIFY_FAILED", False, {"attempts": sec.failed_attempts})
                return False, f"Incorrect PIN. {remaining} attempt(s) remaining before temporary lockout.", None

    @classmethod
    def is_token_authorized(cls, token: Optional[str], business_id: uuid.UUID) -> bool:
        """Check if an authorization token is valid and not expired."""
        if not token or token not in _ACTIVE_AUTH_SESSIONS:
            return False
        session = _ACTIVE_AUTH_SESSIONS[token]
        if session["business_id"] != business_id:
            return False
        if datetime.now(timezone.utc) > session["expires_at"]:
            del _ACTIVE_AUTH_SESSIONS[token]
            return False
        return True

    @classmethod
    def consume_token(cls, token: Optional[str]) -> None:
        """Consume/revoke an authorization token immediately after sensitive execution."""
        if token and token in _ACTIVE_AUTH_SESSIONS:
            del _ACTIVE_AUTH_SESSIONS[token]

    @classmethod
    def change_pin(
        cls,
        db: Session,
        business_id: uuid.UUID,
        old_pin: str,
        new_pin: str,
        robot_id: Optional[str] = None,
    ) -> Tuple[bool, str]:
        """Change owner PIN after verifying existing PIN."""
        success, msg, _ = cls.verify_owner(db, business_id, old_pin, robot_id, source_action="CHANGE_PIN")
        if not success:
            return False, f"Cannot change PIN: {msg}"

        new_clean = new_pin.strip()
        if not new_clean.isdigit() or len(new_clean) != 6:
            return False, "New PIN must be exactly 6 digits."

        sec = cls.get_or_create_owner_security(db, business_id)
        sec.pin_hash = cls.hash_pin(new_clean)
        sec.failed_attempts = 0
        sec.locked_until = None
        db.commit()

        cls._log_event(db, business_id, robot_id, "PIN_CHANGED", True, {})
        return True, "Owner PIN changed successfully."

    @classmethod
    def classify_risk(cls, action_name: str) -> RiskLevel:
        """Central risk policy determining whether an action requires owner PIN verification."""
        high_risk_actions = {
            "modify_product_price",
            "change_selling_price",
            "change_purchase_price",
            "delete_bill",
            "delete_product",
            "manual_stock_override",
            "change_credit_limit",
            "change_owner_pin",
            "wipe_data",
        }
        medium_risk_actions = {
            "create_bill",
            "send_whatsapp_bill",
            "record_payment",
            "add_stock",
            "reduce_stock",
            "complete_task",
        }
        if action_name in high_risk_actions:
            return RiskLevel.HIGH
        elif action_name in medium_risk_actions:
            return RiskLevel.MEDIUM
        return RiskLevel.LOW

    @classmethod
    def _log_event(
        cls,
        db: Session,
        business_id: uuid.UUID,
        robot_id: Optional[str],
        action: str,
        success: bool,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Create an audit entry in security_events. Strictly sanitizes metadata."""
        try:
            safe_meta = {k: v for k, v in (metadata or {}).items() if "pin" not in k.lower()}
            event = SecurityEvent(
                business_id=business_id,
                robot_id=robot_id,
                action=action,
                success=success,
                event_timestamp=datetime.now(timezone.utc),
                event_metadata=safe_meta,
            )
            db.add(event)
            db.commit()
        except Exception as e:
            logger.error(f"Failed to record security event: {e}")

    @classmethod
    def list_events(
        cls,
        db: Session,
        business_id: Optional[uuid.UUID] = None,
        limit: int = 50,
    ) -> list[Dict[str, Any]]:
        """Return recent security audit events."""
        q = db.query(SecurityEvent)
        if business_id:
            q = q.filter(SecurityEvent.business_id == business_id)
        events = q.order_by(SecurityEvent.event_timestamp.desc()).limit(limit).all()
        return [
            {
                "id": str(e.id),
                "robot_id": e.robot_id,
                "action": e.action,
                "success": e.success,
                "timestamp": e.event_timestamp.isoformat() if e.event_timestamp else "",
                "metadata": e.event_metadata or {},
            }
            for e in events
        ]
