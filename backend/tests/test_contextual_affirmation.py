"""Tests for contextual affirmation matching and multi-turn confirmation resolution."""

from sqlalchemy.orm import Session

from app.models.conversation import ConversationState
from app.services.conversation_service import ConversationService


def test_is_affirmation():
    """Verify various English and Hindi/Hinglish affirmative phrases."""
    affirmative_phrases = [
        "haan",
        "haan karo",
        "haa",
        "ha",
        "yes",
        "yep",
        "sure",
        "ok",
        "okay",
        "theek hai",
        "thik hai",
        "karo",
        "bilkul",
        "kar do",
        "sahi hai",
        "confirm",
        "proceed",
    ]
    for phrase in affirmative_phrases:
        assert ConversationService.is_affirmation(phrase) is True, f"Failed on: {phrase}"

    # Non-affirmative phrases
    assert ConversationService.is_affirmation("nahi") is False
    assert ConversationService.is_affirmation("cancel karo") is False
    assert ConversationService.is_affirmation("what is the stock?") is False


def test_is_negation():
    """Verify various cancellation and refusal phrases."""
    negation_phrases = [
        "nahi",
        "nahin",
        "no",
        "cancel",
        "cancel it",
        "mat karo",
        "rehne do",
        "rahne do",
        "stop",
        "don't",
    ]
    for phrase in negation_phrases:
        assert ConversationService.is_negation(phrase) is True, f"Failed on: {phrase}"

    assert ConversationService.is_negation("haan") is False
    assert ConversationService.is_negation("yes") is False


def test_resolve_contextual_affirmation(db_session: Session):
    """Test resolving pending action confirmation on 'haan karo' vs 'nahi'."""
    session = ConversationService.get_or_create_session(
        db=db_session,
        conversation_id="conv_confirm_test",
    )

    # 1. When in IDLE, affirmation does not resolve to an action
    res_idle = ConversationService.resolve_contextual_affirmation(session, "haan karo")
    assert res_idle is None

    # 2. Transition to AWAITING_CONFIRMATION with pending action
    ConversationService.update_state(
        db=db_session,
        session=session,
        state=ConversationState.AWAITING_CONFIRMATION,
        pending_action="create_bill",
        pending_intent="create_bill",
        context_data={"items": [{"name": "Basmati Rice", "quantity": 2}], "customer_name": "Ramesh"},
    )

    # 3. User says "haan karo"
    res_yes = ConversationService.resolve_contextual_affirmation(session, "haan karo")
    assert res_yes is not None
    assert res_yes["confirmed"] is True
    assert res_yes["action"] == "create_bill"
    assert res_yes["context"]["customer_name"] == "Ramesh"

    # 4. User says "nahi cancel karo"
    res_no = ConversationService.resolve_contextual_affirmation(session, "nahi cancel karo")
    assert res_no is not None
    assert res_no["confirmed"] is False
    assert res_no["action"] == "create_bill"
