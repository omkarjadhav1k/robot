"""Structured conversation state tracking entities, active tasks, follow-up pronouns, and confirmation flows."""

from datetime import datetime, timezone
import json
import logging
from typing import Any, Dict, List, Optional
import uuid
from sqlalchemy.orm import Session

from app.models.conversation import ConversationSession, ConversationState

logger = logging.getLogger("robot.engine.state")


class StateContext:
    def __init__(
        self,
        session_id: str,
        last_intent: Optional[str] = None,
        last_product: Optional[str] = None,
        last_customer: Optional[str] = None,
        active_task_ids: Optional[List[str]] = None,
        pending_confirmation: bool = False,
        pending_action: Optional[str] = None,
        pending_data: Optional[Dict[str, Any]] = None,
    ):
        self.session_id = session_id
        self.last_intent = last_intent
        self.last_product = last_product
        self.last_customer = last_customer
        self.active_task_ids = active_task_ids or []
        self.pending_confirmation = pending_confirmation
        self.pending_action = pending_action
        self.pending_data = pending_data or {}


class ConversationStateManager:
    """Manages active conversation session state across turns without LLM."""

    @classmethod
    def load_state(cls, db: Session, session: ConversationSession) -> StateContext:
        """Hydrate StateContext from database session context_data."""
        data = session.context_data or {}
        return StateContext(
            session_id=session.conversation_id,
            last_intent=session.last_intent,
            last_product=data.get("last_product"),
            last_customer=data.get("last_customer"),
            active_task_ids=data.get("active_task_ids", []),
            pending_confirmation=(session.state == ConversationState.AWAITING_CONFIRMATION),
            pending_action=session.pending_action,
            pending_data=data.get("pending_data", {}),
        )

    @classmethod
    def save_state(cls, db: Session, session: ConversationSession, ctx: StateContext):
        """Persist updated StateContext into database session."""
        session.last_intent = ctx.last_intent
        if ctx.pending_confirmation:
            session.state = ConversationState.AWAITING_CONFIRMATION
            session.pending_action = ctx.pending_action
        else:
            session.state = ConversationState.IDLE
            session.pending_action = None

        ctx_dict = {
            "last_product": ctx.last_product,
            "last_customer": ctx.last_customer,
            "active_task_ids": ctx.active_task_ids,
            "pending_data": ctx.pending_data,
        }
        session.context_data = ctx_dict
        db.commit()

    @classmethod
    def set_pending_confirmation(
        cls,
        db: Session,
        session: ConversationSession,
        action: str,
        data: Dict[str, Any],
        prompt: str,
    ):
        """Set state to AWAITING_CONFIRMATION for destructive actions."""
        session.state = ConversationState.AWAITING_CONFIRMATION
        session.pending_action = action
        ctx_dict = session.context_data or {}
        ctx_dict["pending_data"] = data
        ctx_dict["confirmation_prompt"] = prompt
        session.context_data = ctx_dict
        db.commit()

    @classmethod
    def clear_confirmation(cls, db: Session, session: ConversationSession):
        """Reset confirmation state back to IDLE."""
        session.state = ConversationState.IDLE
        session.pending_action = None
        ctx_dict = session.context_data or {}
        ctx_dict.pop("pending_data", None)
        ctx_dict.pop("confirmation_prompt", None)
        session.context_data = ctx_dict
        db.commit()
