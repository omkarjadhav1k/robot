"""Tests for persistent conversation session, sliding window history, and TTL expiration."""

from datetime import datetime, timedelta, timezone
from sqlalchemy.orm import Session

from app.models.conversation import ConversationSession, ConversationState
from app.services.conversation_service import ConversationService


def test_session_lifecycle(db_session: Session):
    """Test session creation, turn addition, and state transitions."""
    # 1. Create new session
    session = ConversationService.get_or_create_session(
        db=db_session,
        conversation_id="conv_test_123",
        robot_id="ROBOT-001",
    )
    assert session is not None
    assert session.conversation_id == "conv_test_123"
    assert session.state == ConversationState.IDLE
    assert session.is_expired() is False

    # 2. Append turns
    msg1 = ConversationService.append_message(
        db=db_session,
        session=session,
        role="user",
        content="Kitna chawal bacha hai?",
    )
    assert msg1.id is not None
    assert msg1.content == "Kitna chawal bacha hai?"

    msg2 = ConversationService.append_message(
        db=db_session,
        session=session,
        role="assistant",
        content="Chawal ka stock 25 kg hai.",
    )
    assert msg2.id is not None

    # 3. Retrieve sliding window history
    history = ConversationService.get_history(db=db_session, session_id=session.id, limit=5)
    assert len(history) == 2
    assert history[0].role == "user"
    assert history[1].role == "assistant"

    # 4. State transition
    ConversationService.update_state(
        db=db_session,
        session=session,
        state=ConversationState.AWAITING_CONFIRMATION,
        pending_action="create_bill",
        context_data={"item": "rice", "qty": 2},
    )
    assert session.state == ConversationState.AWAITING_CONFIRMATION
    assert session.pending_action == "create_bill"
    assert session.context_data == {"item": "rice", "qty": 2}

    # 5. Reset state
    ConversationService.reset_state(db=db_session, session=session)
    assert session.state == ConversationState.IDLE
    assert session.pending_action is None
    assert session.context_data == {}


def test_session_ttl_expiration(db_session: Session):
    """Test that expired sessions are automatically reset to IDLE on next interaction."""
    session = ConversationService.get_or_create_session(
        db=db_session,
        conversation_id="conv_expired_test",
        ttl_minutes=15,
    )
    ConversationService.update_state(
        db=db_session,
        session=session,
        state=ConversationState.AWAITING_CONFIRMATION,
        pending_action="create_bill",
    )

    # Force expiration into past
    session.expires_at = datetime.now(timezone.utc) - timedelta(minutes=5)
    db_session.commit()
    assert session.is_expired() is True

    # Re-retrieving the session should reset expired state
    refreshed = ConversationService.get_or_create_session(
        db=db_session,
        conversation_id="conv_expired_test",
        ttl_minutes=15,
    )
    assert refreshed.state == ConversationState.IDLE
    assert refreshed.pending_action is None
    assert refreshed.is_expired() is False
