"""Conversation session and message history models for persistent multi-turn context."""

from datetime import datetime, timedelta, timezone
import enum
import json
from typing import Any, Dict, List, Optional
import uuid

from sqlalchemy import Column, DateTime, Enum, ForeignKey, Index, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from app.database.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class ConversationState(str, enum.Enum):
    """Conversation state machine lifecycle states."""
    IDLE = "IDLE"
    AWAITING_INPUT = "AWAITING_INPUT"
    AWAITING_CONFIRMATION = "AWAITING_CONFIRMATION"
    EXECUTING = "EXECUTING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


class ConversationSession(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """
    Persistent conversation session representing an ongoing dialog between an owner,
    the robot, and the central brain. Retains active state and pending intents.
    """
    __tablename__ = "conversation_sessions"

    conversation_id = Column(String(64), nullable=False, unique=True, index=True)
    business_id = Column(UUID(as_uuid=True), ForeignKey("businesses.id", ondelete="CASCADE"), nullable=True, index=True)
    robot_id = Column(String(50), nullable=False, default="ROBOT-001", index=True)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)

    state = Column(Enum(ConversationState), nullable=False, default=ConversationState.IDLE)
    last_intent = Column(String(100), nullable=True)
    pending_intent = Column(String(100), nullable=True)
    pending_action = Column(String(100), nullable=True)
    
    # Text-serialized JSON for cross-dialect compatibility (PostgreSQL and SQLite)
    entities_json = Column(Text, nullable=False, default="{}")
    context_data_json = Column(Text, nullable=False, default="{}")

    expires_at = Column(DateTime(timezone=True), nullable=True, index=True)

    # Relationships
    messages = relationship(
        "ConversationMessage",
        back_populates="session",
        cascade="all, delete-orphan",
        order_by="ConversationMessage.created_at",
    )

    @property
    def entities(self) -> Dict[str, Any]:
        try:
            return json.loads(self.entities_json or "{}")
        except Exception:
            return {}

    @entities.setter
    def entities(self, val: Dict[str, Any]):
        self.entities_json = json.dumps(val or {})

    @property
    def context_data(self) -> Dict[str, Any]:
        try:
            return json.loads(self.context_data_json or "{}")
        except Exception:
            return {}

    @context_data.setter
    def context_data(self, val: Dict[str, Any]):
        self.context_data_json = json.dumps(val or {})

    def is_expired(self) -> bool:
        """Check whether the pending context has expired."""
        if not self.expires_at:
            return False
        exp = self.expires_at
        if exp.tzinfo is None:
            exp = exp.replace(tzinfo=timezone.utc)
        return datetime.now(timezone.utc) > exp


class ConversationMessage(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """
    Individual turn in a conversation session, recording user utterances and assistant replies.
    """
    __tablename__ = "conversation_messages"

    session_id = Column(
        UUID(as_uuid=True),
        ForeignKey("conversation_sessions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    role = Column(String(20), nullable=False)  # "user", "assistant", "system"
    content = Column(Text, nullable=False)
    structured_intent = Column(String(100), nullable=True)
    entities_json = Column(Text, nullable=True)

    # Relationships
    session = relationship("ConversationSession", back_populates="messages")
