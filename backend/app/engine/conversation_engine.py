"""Main Non-LLM Conversation Engine orchestrator connecting intent routing, entity extraction, fast queries, and tasks."""

from datetime import datetime, timezone
from decimal import Decimal
import logging
import re
import time
from typing import Any, Dict, List, Optional
import urllib.parse
from sqlalchemy.orm import Session

from app.engine.command_registry import CommandMode
from app.engine.conversation_state import ConversationStateManager, StateContext
from app.engine.entity_extractor import EntityExtractor, ExtractedEntities
from app.engine.fast_query_engine import FastQueryEngine, FastQueryResult
from app.engine.intent_router import IntentRouter
from app.engine.response_templates import ResponseTemplates
from app.engine.task_manager import BackgroundTaskManager
from app.models.billing import BillSource, Customer
from app.models.conversation import ConversationSession, ConversationState
from app.schemas.robot import RobotCommand, VoiceInteractResponse
from app.services.billing_service import BillingService
from app.services.conversation_service import ConversationService
from app.services.customer_service import CustomerService

logger = logging.getLogger("robot.engine.main")


class ConversationEngine:
    """Master non-LLM, event-driven deterministic conversation processor."""

    @classmethod
    def process_utterance(
        cls,
        db: Session,
        text: str,
        robot_id: str = "ROBOT-001",
        conversation_id: Optional[str] = None,
        business_id: Optional[Any] = None,
        simulate_slow: bool = False,
    ) -> VoiceInteractResponse:
        """
        Deterministic, zero-LLM pipeline:
        1. Retrieve or create conversation session.
        2. Check for confirmation response (Haan / Nahi) if awaiting confirmation.
        3. Extract entities (products, customers, numbers, relays) with pronoun resolution.
        4. Classify intent with confidence scoring.
        5. Handle product ambiguity clarification ("Kaunsi Maggi?").
        6. Dispatch Fast Action OR Background Task.
        7. Maintain state and return immediate non-blocking response.
        """
        t_start = time.perf_counter()
        clean_text = text.strip()

        # 1. Session & State Retrieval
        session = ConversationService.get_or_create_session(
            db=db,
            conversation_id=conversation_id,
            business_id=business_id,
            robot_id=robot_id,
        )
        state_ctx = ConversationStateManager.load_state(db, session)
        biz_id = session.business_id or business_id

        # 2. Check Confirmation Flow (Section 22)
        if state_ctx.pending_confirmation:
            if ConversationService.is_affirmation(clean_text):
                # Execute verified destructive action
                pending_act = state_ctx.pending_action
                p_data = state_ctx.pending_data or {}
                ConversationStateManager.clear_confirmation(db, session)

                if pending_act == "UPDATE_PAYMENT":
                    try:
                        pay_res = BillingService.record_payment(
                            db=db,
                            customer_name=p_data["customer"],
                            amount=p_data["amount"],
                            payment_method=p_data.get("payment_method", "CASH"),
                            business_id=biz_id,
                        )
                        msg = f"{pay_res['customer_name']} ka ₹{pay_res['amount_paid']:.2f} payment successfully confirm ho gaya."
                        return cls._build_response(
                            session=session,
                            text=msg,
                            action_type="billing_action",
                            business_data=pay_res,
                            total_ms=(time.perf_counter() - t_start) * 1000,
                        )
                    except Exception as e:
                        return cls._build_response(
                            session=session,
                            text=f"Payment update nahi ho paya: {str(e)}",
                            action_type="billing_action",
                            total_ms=(time.perf_counter() - t_start) * 1000,
                        )

                elif pending_act == "CREATE_BILL":
                    try:
                        bill_res = BillingService.create_bill(
                            db=db,
                            items_requested=p_data.get("items", []),
                            customer_name=p_data.get("customer_name"),
                            payment_method=p_data.get("payment_method", "CASH"),
                            source=BillSource.ROBOT_VOICE,
                            business_id=biz_id,
                        )
                        msg = f"Bill {bill_res['bill_number']} of ₹{bill_res['total_amount']:.2f} has been created successfully for {bill_res['customer_name']}."
                        return cls._build_response(
                            session=session,
                            text=msg,
                            action_type="billing_action",
                            business_data=bill_res,
                            total_ms=(time.perf_counter() - t_start) * 1000,
                        )
                    except Exception as e:
                        return cls._build_response(
                            session=session,
                            text=f"Failed to create bill: {str(e)}",
                            action_type="billing_action",
                            total_ms=(time.perf_counter() - t_start) * 1000,
                        )

            elif ConversationService.is_negation(clean_text):
                ConversationStateManager.clear_confirmation(db, session)
                cancel_msg = ResponseTemplates.get("CANCELLED")
                return cls._build_response(
                    session=session,
                    text=cancel_msg,
                    action_type="conversation",
                    total_ms=(time.perf_counter() - t_start) * 1000,
                )

        # 3. Entity Extraction (with pronoun resolution from previous turns)
        t_entity_0 = time.perf_counter()
        entities = EntityExtractor.extract_all(
            text=clean_text,
            db=db,
            business_id=biz_id,
            last_product=state_ctx.last_product,
            last_customer=state_ctx.last_customer,
        )
        entity_ms = (time.perf_counter() - t_entity_0) * 1000

        # 4. Intent Classification
        t_intent_0 = time.perf_counter()
        match = IntentRouter.classify(clean_text, entities)
        intent_ms = (time.perf_counter() - t_intent_0) * 1000

        # 5. Handle Ambiguity & Clarification (Section 21 & Section 34)
        if match.requires_clarification:
            clarify_text = match.clarification_message or ResponseTemplates.get("UNKNOWN")
            return cls._build_response(
                session=session,
                text=clarify_text,
                action_type="clarification",
                total_ms=(time.perf_counter() - t_start) * 1000,
            )

        if match.is_unknown:
            unknown_text = ResponseTemplates.get("UNKNOWN")
            return cls._build_response(
                session=session,
                text=unknown_text,
                action_type="unknown",
                total_ms=(time.perf_counter() - t_start) * 1000,
            )

        intent = match.intent

        # 6. Background Jobs: Strategy & Reports (Section 9)
        if intent in ("CREATE_WEEKLY_STRATEGY", "GENERATE_SALES_REPORT", "GENERATE_INVENTORY_REPORT"):
            immediate_ack = ResponseTemplates.get("ACK_STRATEGY") if "STRATEGY" in intent else ResponseTemplates.get("ACK_TASK")
            
            # Enqueue background task
            task_id = BackgroundTaskManager.enqueue_task(
                task_type=intent,
                business_id=biz_id,
            )
            state_ctx.active_task_ids.append(task_id)
            state_ctx.last_intent = intent
            ConversationStateManager.save_state(db, session, state_ctx)

            return cls._build_response(
                session=session,
                text=immediate_ack,
                action_type="background_task",
                immediate_ack=immediate_ack,
                business_data={"task_id": task_id, "status": "QUEUED", "type": intent},
                total_ms=(time.perf_counter() - t_start) * 1000,
            )

        # 7. Check Task Status
        if intent == "TASK_STATUS":
            active_ids = state_ctx.active_task_ids
            if not active_ids:
                status_text = "Abhi koi background task running nahi hai. Main ready hoon."
            else:
                latest_id = active_ids[-1]
                t_stat = BackgroundTaskManager.get_task_status(latest_id)
                if t_stat and t_stat.get("status") == "RUNNING":
                    status_text = f"Abhi {t_stat['type'].replace('_', ' ').lower()} chal raha hai. Progress {t_stat['progress']}% hai."
                elif t_stat and t_stat.get("status") == "COMPLETED":
                    status_text = f"Task {latest_id} complete ho gaya hai."
                else:
                    status_text = "Abhi ready hoon. Batao kya karna hai."

            return cls._build_response(
                session=session,
                text=status_text,
                action_type="task_status",
                total_ms=(time.perf_counter() - t_start) * 1000,
            )

        # 8. Retrieve Old Completed Task Result ("Kal wali strategy batao") (Section 18)
        if intent == "GET_COMPLETED_TASK":
            completed_job = BackgroundTaskManager.get_latest_completed_task(
                task_type="STRATEGY" if "strategy" in clean_text.lower() else None,
                business_id=biz_id,
            )
            if completed_job and completed_job.get("result"):
                res_obj = completed_job["result"]
                retrieval_text = res_obj.get("natural_summary") or res_obj.get("summary") or "Last task successfully complete hua tha."
                return cls._build_response(
                    session=session,
                    text=retrieval_text,
                    action_type="task_retrieval",
                    business_data=res_obj,
                    total_ms=(time.perf_counter() - t_start) * 1000,
                )
            else:
                return cls._build_response(
                    session=session,
                    text="Purana koi saved task result nahi mila.",
                    action_type="task_retrieval",
                    total_ms=(time.perf_counter() - t_start) * 1000,
                )

        # 9. Stop/Cancel Task
        if intent == "STOP_TASK":
            if state_ctx.active_task_ids:
                cancelled_id = state_ctx.active_task_ids[-1]
                BackgroundTaskManager.cancel_task(cancelled_id)
                return cls._build_response(
                    session=session,
                    text=f"Task {cancelled_id} cancel kar diya hai.",
                    action_type="task_cancellation",
                    total_ms=(time.perf_counter() - t_start) * 1000,
                )
            else:
                return cls._build_response(
                    session=session,
                    text="Koi active task nahi hai jise cancel kiya ja sake.",
                    action_type="task_cancellation",
                    total_ms=(time.perf_counter() - t_start) * 1000,
                )

        # 10. Large Payment Entry Confirmation (Section 22)
        if intent == "UPDATE_PAYMENT":
            if not entities.customer:
                return cls._build_response(
                    session=session,
                    text="Kripya customer ka naam batayein jinka payment record karna hai.",
                    action_type="billing_action",
                    total_ms=(time.perf_counter() - t_start) * 1000,
                )
            amt = entities.amount or 0.0
            if amt >= 5000.0:
                # Requires confirmation
                prompt = f"₹{amt:,.2f} ka payment update karna hai for {entities.customer}. Confirm karo."
                ConversationStateManager.set_pending_confirmation(
                    db=db,
                    session=session,
                    action="UPDATE_PAYMENT",
                    data={"customer": entities.customer, "amount": amt, "payment_method": entities.payment_method},
                    prompt=prompt,
                )
                return cls._build_response(
                    session=session,
                    text=prompt,
                    action_type="confirmation_required",
                    state=ConversationState.AWAITING_CONFIRMATION.value,
                    total_ms=(time.perf_counter() - t_start) * 1000,
                )
            else:
                # Direct execute for standard amounts
                try:
                    pay_res = BillingService.record_payment(
                        db=db,
                        customer_name=entities.customer,
                        amount=amt,
                        payment_method=entities.payment_method,
                        business_id=biz_id,
                    )
                    reply = f"{pay_res['customer_name']} se ₹{pay_res['amount_paid']:.2f} payment receive ho gaya. Ab baki balance ₹{pay_res['remaining_balance']:.2f} hai."
                    return cls._build_response(
                        session=session,
                        text=reply,
                        action_type="billing_action",
                        business_data=pay_res,
                        total_ms=(time.perf_counter() - t_start) * 1000,
                    )
                except Exception as pe:
                    return cls._build_response(
                        session=session,
                        text=f"Payment record nahi ho paya: {str(pe)}",
                        action_type="billing_action",
                        total_ms=(time.perf_counter() - t_start) * 1000,
                    )

        # 11. Fast Query Engine Execution (<300ms)
        fast_res = FastQueryEngine.execute(
            intent=intent,
            entities=entities,
            db=db,
            business_id=biz_id,
            robot_id=robot_id,
            simulate_slow=simulate_slow,
        )

        # Update Conversation State
        if entities.product:
            state_ctx.last_product = entities.product
        if entities.customer:
            state_ctx.last_customer = entities.customer
        state_ctx.last_intent = intent
        ConversationStateManager.save_state(db, session, state_ctx)

        # Convert dispatched command if any
        cmd_schema = None
        if fast_res.command_dispatched:
            cmd_schema = RobotCommand(
                command_id=fast_res.command_dispatched["command_id"],
                robot_id=robot_id,
                action=fast_res.command_dispatched["action"],
                params=fast_res.command_dispatched["params"],
                status="pending",
            )

        total_ms = (time.perf_counter() - t_start) * 1000

        return cls._build_response(
            session=session,
            text=fast_res.response_text,
            action_type=fast_res.action_type,
            immediate_ack=fast_res.immediate_ack,
            business_data=fast_res.data,
            command_dispatched=cmd_schema,
            latencies={
                "entity_ms": round(entity_ms, 2),
                "intent_ms": round(intent_ms, 2),
                "query_ms": round(fast_res.latency_ms, 2),
                "total_ms": round(total_ms, 2),
            },
            total_ms=total_ms,
        )

    @classmethod
    def _build_response(
        cls,
        session: ConversationSession,
        text: str,
        action_type: str,
        immediate_ack: Optional[str] = None,
        state: str = "IDLE",
        business_data: Optional[Dict[str, Any]] = None,
        command_dispatched: Optional[RobotCommand] = None,
        latencies: Optional[Dict[str, float]] = None,
        total_ms: float = 0.0,
    ) -> VoiceInteractResponse:
        """Helper to create standard schema response."""
        clean_display_text = re.sub(r'[\U00010000-\U0010ffff]', '', text).strip()
        clean_audio_text = re.sub(r"[^\w\s\.,\?!₹\-']", "", clean_display_text or text).strip()
        audio_url = f"/api/v1/voice/audio/tts?text={urllib.parse.quote(clean_audio_text or clean_display_text or text)}&lang=hi"

        return VoiceInteractResponse(
            response_text=clean_display_text or text,
            action_type=action_type,
            conversation_id=session.conversation_id,
            immediate_ack=immediate_ack,
            state=state or session.state.value,
            business_data=business_data,
            command_dispatched=command_dispatched,
            audio_url=audio_url,
            latencies=latencies or {"total_ms": round(total_ms, 2)},
        )
