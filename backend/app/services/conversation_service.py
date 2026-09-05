"""Conversation service managing persistent sessions, context windows, and confirmation state."""

from datetime import datetime, timedelta, timezone
import json
import logging
import re
from typing import Any, Dict, List, Optional
import uuid

from sqlalchemy.orm import Session

from app.models.conversation import (
    ConversationMessage,
    ConversationSession,
    ConversationState,
)

logger = logging.getLogger(__name__)

# Regular expressions for affirmative and negative intent in English and Hinglish/Hindi
AFFIRMATION_PATTERNS = [
    r"\b(haan|haa|ha|yes|yep|yeah|yup|sure|ok|okay|okey|theek|thik|theek hai|thik hai|theek h|thik h|haan karo|ha karo|bilkul|kar do|kar dalo|sahi|sahi hai|proceed|confirm|conform|its confirm|its conform|it's confirm|it's conform|done|pakka|ha pakka|haan confirm|ha confirm|conformation|confirmation)\b",
    r"^(karo|do it|add kar do|add karo|banado|bana do)$",
]

# Phrases that express questions or complaints about past actions, which should NOT cancel a pending bill
QUESTION_COMPLAINT_PATTERNS = [
    r"\b(nahi kiya|hua nahi|nahi hua|kyu nahi|kyun nahi|nahi add|add nahi|bana nahi|nahi bana)\b",
]

NEGATION_PATTERNS = [
    r"\b(cancel|mat karo|cancel karo|cancel it|stop|rehne do|rahne do|dont|don't|not now|chhod do|chod do|nhi chahiye|nahi chahiye)\b",
    r"^(nahi|nahin|na|no|nope|n)$",
    r"\b(nahi|nahin|no)\b(?!\s+(kiya|hua|bana|aaya|chal))",
]

AFFIRMATION_REGEX = re.compile("|".join(AFFIRMATION_PATTERNS), re.IGNORECASE)
NEGATION_REGEX = re.compile("|".join(NEGATION_PATTERNS), re.IGNORECASE)
QUESTION_COMPLAINT_REGEX = re.compile("|".join(QUESTION_COMPLAINT_PATTERNS), re.IGNORECASE)



class ConversationService:
    """Manages multi-turn conversation sessions, context expiry, and state transitions."""

    @staticmethod
    def get_or_create_session(
        db: Session,
        conversation_id: Optional[str] = None,
        business_id: Optional[Any] = None,
        robot_id: str = "ROBOT-001",
        ttl_minutes: int = 15,
    ) -> ConversationSession:
        """
        Fetch existing active session or create a new session if not provided or expired.
        """
        now = datetime.now(timezone.utc)
        session: Optional[ConversationSession] = None

        if conversation_id:
            session = (
                db.query(ConversationSession)
                .filter(ConversationSession.conversation_id == str(conversation_id).strip())
                .first()
            )

        if session:
            # Check context expiration
            if session.is_expired():
                logger.info("Conversation %s expired at %s, resetting state to IDLE", session.conversation_id, session.expires_at)
                session.state = ConversationState.IDLE
                session.pending_action = None
                session.pending_intent = None
                session.context_data = {}
                session.entities = {}
                session.expires_at = now + timedelta(minutes=ttl_minutes)
                db.commit()
                db.refresh(session)
            else:
                # Refresh TTL on interaction
                session.expires_at = now + timedelta(minutes=ttl_minutes)
                db.commit()
                db.refresh(session)
            return session

        if not business_id:
            from app.models.business import Business
            default_biz = db.query(Business).first()
            if not default_biz:
                default_biz = Business(name="Main Store", owner_name="Store Owner", business_type="Retail")
                db.add(default_biz)
                db.flush()
            business_id = default_biz.id

        # Create new session
        new_conv_id = conversation_id if (conversation_id and len(conversation_id.strip()) > 0) else f"conv_{uuid.uuid4().hex[:12]}"
        session = ConversationSession(
            conversation_id=new_conv_id,
            business_id=business_id,
            robot_id=robot_id,
            state=ConversationState.IDLE,
            expires_at=now + timedelta(minutes=ttl_minutes),
        )
        db.add(session)
        db.commit()
        db.refresh(session)
        logger.info("Created new ConversationSession: %s", session.conversation_id)
        return session

    @staticmethod
    def append_message(
        db: Session,
        session: ConversationSession,
        role: str,
        content: str,
        structured_intent: Optional[str] = None,
        entities: Optional[Dict[str, Any]] = None,
    ) -> ConversationMessage:
        """Record an utterance/reply in the session history."""
        msg = ConversationMessage(
            session_id=session.id,
            role=role,
            content=content,
            structured_intent=structured_intent,
            entities_json=json.dumps(entities or {}),
        )
        db.add(msg)
        session.updated_at = datetime.now(timezone.utc)
        if structured_intent:
            session.last_intent = structured_intent
        db.commit()
        db.refresh(msg)
        return msg

    @staticmethod
    def get_history(
        db: Session,
        session_id: Any,
        limit: int = 10,
    ) -> List[ConversationMessage]:
        """Fetch the most recent turns (sliding window) ordered by created_at ascending."""
        subquery = (
            db.query(ConversationMessage)
            .filter(ConversationMessage.session_id == session_id)
            .order_by(ConversationMessage.created_at.desc())
            .limit(limit)
            .all()
        )
        # Re-sort chronologically for the LLM
        return sorted(subquery, key=lambda m: m.created_at)

    @staticmethod
    def update_state(
        db: Session,
        session: ConversationSession,
        state: ConversationState,
        pending_intent: Optional[str] = None,
        pending_action: Optional[str] = None,
        context_data: Optional[Dict[str, Any]] = None,
        entities: Optional[Dict[str, Any]] = None,
        ttl_minutes: int = 15,
    ) -> ConversationSession:
        """Update lifecycle state and store pending execution details."""
        session.state = state
        if pending_intent is not None:
            session.pending_intent = pending_intent
        if pending_action is not None:
            session.pending_action = pending_action
        if context_data is not None:
            session.context_data = context_data
        if entities is not None:
            session.entities = entities

        session.expires_at = datetime.now(timezone.utc) + timedelta(minutes=ttl_minutes)
        db.commit()
        db.refresh(session)
        return session

    @staticmethod
    def reset_state(db: Session, session: ConversationSession) -> ConversationSession:
        """Clear pending action and transition back to IDLE."""
        session.state = ConversationState.IDLE
        session.pending_action = None
        session.pending_intent = None
        session.context_data = {}
        session.entities = {}
        db.commit()
        db.refresh(session)
        return session

    @classmethod
    def is_affirmation(cls, text: str) -> bool:
        """Check if user text conveys affirmative confirmation."""
        cleaned = text.strip().lower()
        if cls.is_negation(cleaned):
            return False
        return bool(AFFIRMATION_REGEX.search(cleaned))

    @staticmethod
    def is_negation(text: str) -> bool:
        """Check if user text conveys cancellation or refusal."""
        cleaned = text.strip().lower()
        if QUESTION_COMPLAINT_REGEX.search(cleaned):
            return False
        return bool(NEGATION_REGEX.search(cleaned))

    @classmethod
    def resolve_contextual_affirmation(
        cls,
        session: ConversationSession,
        user_text: str,
    ) -> Optional[Dict[str, Any]]:
        """
        If the session is waiting for confirmation (e.g. "AWAITING_CONFIRMATION"),
        evaluate if user text confirms or cancels the pending action.
        Returns None if not in confirmation state or neither affirmation nor negation.
        """
        if session.state != ConversationState.AWAITING_CONFIRMATION:
            return None

        # Check negation first
        if cls.is_negation(user_text):
            return {
                "confirmed": False,
                "action": session.pending_action,
                "intent": session.pending_intent,
                "context": session.context_data,
                "entities": session.entities,
            }

        if cls.is_affirmation(user_text):
            return {
                "confirmed": True,
                "action": session.pending_action,
                "intent": session.pending_intent,
                "context": session.context_data,
                "entities": session.entities,
            }

        return None
