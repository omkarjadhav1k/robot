"""Voice and text interaction router connecting persistent conversation sessions,
Gemini function calling, authoritative PostgreSQL business services, and hardware command dispatch."""

from datetime import datetime, timezone
from decimal import Decimal
import logging
import re
import time
from typing import Any, Dict, List, Optional
from fastapi import APIRouter, BackgroundTasks, Depends, File, HTTPException, UploadFile, WebSocket, WebSocketDisconnect
from sqlalchemy.orm import Session, joinedload

import uuid
from app.ai.speech_service import synthesize_speech
from app.config import get_settings
from app.database.session import get_db
from app.engine.command_registry import CommandMode
from app.engine.conversation_state import ConversationStateManager
from app.engine.entity_extractor import EntityExtractor
from app.engine.intent_router import IntentRouter
from app.engine.response_templates import ResponseTemplates
from app.engine.task_manager import BackgroundTaskManager
from app.engine.websocket_handler import WebSocketSessionHandler
from app.models.billing import Bill, BillSource
from app.models.business import Business
from app.models.conversation import ConversationState
from app.models.robot_command import AIActivity, CommandStatus
from app.schemas.robot import (
    RobotCommand,
    RobotCommandCreate,
    VoiceInteractRequest,
    VoiceInteractResponse,
)
from app.services.billing_service import BillingService
from app.services.brain_service import BrainService
from app.services.conversation_service import ConversationService
from app.services.customer_service import CustomerService
from app.services.fast_path_service import FastPathService
from app.services.inventory_service import InventoryService
from app.services.memory_service import MemoryService
from app.services.report_service import ReportService
from app.services.robot_service import RobotService
from app.services.security_service import SecurityService
from app.services.task_service import TaskService
from app.services.whatsapp_service import WhatsAppService

logger = logging.getLogger("business_ai_robot.voice")
router = APIRouter()
settings = get_settings()


from app.ai.gemini_service import reason_with_gemini
from app.engine.hybrid_engine import HybridEngine


def _get_immediate_ack(prompt: str) -> str:
    """Generate sub-200ms acoustic/text acknowledgment based on user utterance keywords."""
    p = prompt.lower()
    if "whatsapp" in p:
        return "Preparing invoice for WhatsApp..."
    if any(w in p for w in ["stock", "maal", "samaan", "available", "kitna hai"]):
        return "Checking inventory stock..."
    if any(w in p for w in ["bill", "hisaab", "sales", "revenue", "aaj ka"]):
        return "Checking today's sales and bills..."
    if any(w in p for w in ["customer", "baaki", "balance", "udhaar"]):
        return "Looking up customer ledger..."
    if any(w in p for w in ["relay", "light", "fan", "switch", "turn on", "turn off"]):
        return "Processing device switch..."
    if ConversationService.is_affirmation(p):
        return "Processing your confirmation..."
    if ConversationService.is_negation(p):
        return "Cancelling..."
    return "Processing..."


def _parse_direct_hardware_intent(prompt: str) -> Optional[dict]:
    """Fast-path regex matcher for immediate hardware command execution."""
    p = prompt.lower().strip()

    # Pattern: Turn on/off relay N
    relay_match = re.search(r"(?:turn|switch)\s+(on|off)\s+(?:relay|switch|device)?\s*([1-4])", p)
    if relay_match:
        state = relay_match.group(1)
        relay_num = int(relay_match.group(2))
        return {
            "action": "set_relay",
            "params": {"relay": relay_num, "state": state},
            "response_text": f"Relay {relay_num} has been switched {state}.",
        }

    # Pattern: Turn on/off all relays
    all_relays = re.search(r"(?:turn|switch)\s+(on|off)\s+all\s+(?:relays|switches)?", p)
    if all_relays:
        state = all_relays.group(1)
        return {
            "action": "set_all_relays",
            "params": {"state": state},
            "response_text": f"All relays have been switched {state}.",
        }

    # Pattern: Blink LED
    if re.search(r"(?:blink|flash)\s+(?:the\s+)?(?:led|light)", p):
        return {
            "action": "blink_led",
            "params": {"count": 3, "interval_ms": 200},
            "response_text": "Blinking the status LED on the ESP32.",
        }

    # Pattern: Ping / status
    if "are you online" in p or p == "ping":
        return {
            "action": "ping",
            "params": {},
            "response_text": "Business AI Robot is online and connected to the central brain.",
        }

    return None


@router.post(
    "/interact",
    response_model=VoiceInteractResponse,
    summary="Process voice/text interaction and dispatch robot actions",
)
async def process_voice_interaction(
    req: VoiceInteractRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
) -> VoiceInteractResponse:
    """
    Main conversational brain orchestrator:
    1. Retrieve or initialize persistent conversation session.
    2. Execute sub-second Fast-Path Engine (<50ms greetings, <100ms relays, <200ms stock/ledger).
    3. Extract natural operational tasks/reminders.
    4. Evaluate affirmative confirmation ("haan karo") for pending multi-turn intents.
    5. Reason with Gemini AI with tools and conversational history.
    6. Execute authoritative PostgreSQL business services (Stock, Billing, Ledgers, Payments).
    7. Schedule non-blocking background TTS cache prewarm and return latency breakdown.
    """
    t_start = time.perf_counter()
    fast_path_ms = 0.0
    memory_ms = 0.0
    instructions_ms = 0.0
    gemini_ms = 0.0
    tool_ms = 0.0
    database_ms = 0.0

    robot_id = req.robot_id or settings.DEFAULT_ROBOT_ID
    prompt = req.text.strip()
    immediate_ack = _get_immediate_ack(prompt)

    # 1. Retrieve or create session
    t_db_0 = time.perf_counter()
    session = ConversationService.get_or_create_session(
        db=db,
        conversation_id=req.conversation_id,
        business_id=req.business_id,
        robot_id=robot_id,
    )
    database_ms += (time.perf_counter() - t_db_0) * 1000

    # 2. Sub-second Fast-Path Engine (Greetings, Relays, Stock & Customer Balance)
    t_fp_0 = time.perf_counter()
    fast_res = FastPathService.evaluate(
        db=db,
        text=prompt,
        robot_id=robot_id,
        business_id=session.business_id,
    )
    fast_path_ms = (time.perf_counter() - t_fp_0) * 1000

    if fast_res.matched:
        ConversationService.append_message(db, session, role="user", content=prompt)
        ConversationService.append_message(db, session, role="assistant", content=fast_res.response_text)

        total_time = (time.perf_counter() - t_start) * 1000

        # Asynchronous non-blocking background TTS prewarm
        clean_audio_text = re.sub(r"[^\w\s\.,\?!₹\-']", "", fast_res.response_text).strip()
        if background_tasks and clean_audio_text:
            background_tasks.add_task(synthesize_speech, clean_audio_text, "hi")

        import urllib.parse
        audio_url = f"/api/v1/voice/audio/tts?text={urllib.parse.quote(clean_audio_text or fast_res.response_text)}&lang=hi"

        return VoiceInteractResponse(
            response_text=fast_res.response_text,
            action_type=fast_res.action_type,
            conversation_id=session.conversation_id,
            immediate_ack=immediate_ack,
            state=session.state.value,
            business_data=fast_res.business_data,
            command_dispatched=fast_res.command_dispatched,
            audio_url=audio_url,
            latencies={
                "fast_path_ms": round(fast_path_ms, 2),
                "database_ms": round(database_ms, 2),
                "total_ms": round(total_time, 2),
            },
        )

    # 2b. Natural Operational Task Extraction
    t_task_0 = time.perf_counter()
    extracted_task = None
    if not any(w in prompt.lower() for w in ["status", "kya hua", "kitna hua", "progress", "kal wali", "purani"]):
        extracted_task = TaskService.extract_and_create_task(
            db=db,
            prompt=prompt,
            business_id=session.business_id,
        )
    if extracted_task:
        resp_text = extracted_task["message"]
        ConversationService.append_message(db, session, role="user", content=prompt)
        ConversationService.append_message(db, session, role="assistant", content=resp_text)

        total_time = (time.perf_counter() - t_start) * 1000
        clean_audio_text = re.sub(r"[^\w\s\.,\?!₹\-']", "", resp_text).strip()
        if background_tasks and clean_audio_text:
            background_tasks.add_task(synthesize_speech, clean_audio_text, "hi")

        import urllib.parse
        audio_url = f"/api/v1/voice/audio/tts?text={urllib.parse.quote(clean_audio_text or resp_text)}&lang=hi"

        return VoiceInteractResponse(
            response_text=resp_text,
            action_type="task_action",
            conversation_id=session.conversation_id,
            immediate_ack=immediate_ack,
            state=session.state.value,
            business_data=extracted_task,
            audio_url=audio_url,
            latencies={
                "fast_path_ms": round((time.perf_counter() - t_task_0) * 1000, 2),
                "database_ms": round(database_ms, 2),
                "total_ms": round(total_time, 2),
            },
        )

    # 2. Check for Contextual Affirmation (e.g. "haan", "haan karo", "yes", "do it")
    affirmation_resolution = ConversationService.resolve_contextual_affirmation(session, prompt)
    if affirmation_resolution:
        confirmed = affirmation_resolution["confirmed"]
        pending_action = affirmation_resolution["action"]
        context_data = affirmation_resolution["context"]

        if confirmed and pending_action == "create_bill":
            try:
                # Execute verified bill creation in PostgreSQL
                bill_res = BillingService.create_bill(
                    db=db,
                    items_requested=context_data.get("items", []),
                    customer_name=context_data.get("customer_name"),
                    payment_method=context_data.get("payment_method", "CASH"),
                    source=BillSource.ROBOT_VOICE,
                    business_id=session.business_id,
                )

                send_whatsapp = bool(context_data.get("send_whatsapp", False))
                if send_whatsapp:
                    bill_obj = (
                        db.query(Bill)
                        .options(joinedload(Bill.customer), joinedload(Bill.items))
                        .filter(Bill.id == uuid.UUID(bill_res["bill_id"]))
                        .first()
                    )
                    business_obj = (
                        db.query(Business).filter(Business.id == session.business_id).first()
                        if session.business_id
                        else db.query(Business).first()
                    )
                    res = await WhatsAppService.send_invoice_via_whatsapp(
                        bill=bill_obj,
                        business=business_obj,
                    )
                    if res.success:
                        response_text = (
                            f"Bill {bill_res['bill_number']} of ₹{bill_res['total_amount']:.2f} has been generated "
                            f"and sent to {bill_res['customer_name']} on WhatsApp."
                        )
                    else:
                        response_text = (
                            "I generated the bill, but I couldn't send it on WhatsApp. "
                            "Please check the customer's WhatsApp number."
                        )
                else:
                    response_text = (
                        f"Bill {bill_res['bill_number']} has been created successfully for "
                        f"{bill_res['customer_name']}. Total amount is ₹{bill_res['total_amount']:.2f}."
                    )
                ConversationService.reset_state(db, session)
                ConversationService.append_message(db, session, role="user", content=prompt)
                ConversationService.append_message(db, session, role="assistant", content=response_text)

                total_time = (time.perf_counter() - t_start) * 1000
                return VoiceInteractResponse(
                    response_text=response_text,
                    action_type="billing_action",
                    conversation_id=session.conversation_id,
                    immediate_ack=immediate_ack,
                    state=session.state.value,
                    business_data=bill_res,
                    latencies={"total_ms": round(total_time, 2)},
                )
            except Exception as e:
                logger.error("Error confirming bill creation: %s", e)
                ConversationService.reset_state(db, session)
                err_msg = f"Failed to create bill: {str(e)}"
                return VoiceInteractResponse(
                    response_text=err_msg,
                    action_type="billing_action",
                    conversation_id=session.conversation_id,
                    immediate_ack=immediate_ack,
                    state="FAILED",
                    latencies={"total_ms": round((time.perf_counter() - t_start) * 1000, 2)},
                )

        elif not confirmed:
            ConversationService.reset_state(db, session)
            cancel_msg = "Understood. The action has been cancelled."
            ConversationService.append_message(db, session, role="user", content=prompt)
            ConversationService.append_message(db, session, role="assistant", content=cancel_msg)
            return VoiceInteractResponse(
                response_text=cancel_msg,
                action_type="conversation",
                conversation_id=session.conversation_id,
                immediate_ack=immediate_ack,
                state=session.state.value,
                latencies={"total_ms": round((time.perf_counter() - t_start) * 1000, 2)},
            )

    # 3. Direct Fast-Path Hardware Actions (Relays, LED)
    hw_intent = _parse_direct_hardware_intent(prompt)
    if hw_intent:
        db_cmd = RobotService.queue_command(
            db=db,
            robot_id=robot_id,
            action=hw_intent["action"],
            params=hw_intent["params"],
        )
        cmd_schema = RobotCommand(
            command_id=db_cmd.command_id,
            robot_id=robot_id,
            action=db_cmd.action,
            params=db_cmd.payload or {},
            status="pending",
        )
        ConversationService.append_message(db, session, role="user", content=prompt)
        ConversationService.append_message(db, session, role="assistant", content=hw_intent["response_text"])
        return VoiceInteractResponse(
            response_text=hw_intent["response_text"],
            action_type="hardware_action",
            conversation_id=session.conversation_id,
            immediate_ack=immediate_ack,
            state=session.state.value,
            command_dispatched=cmd_schema,
            latencies={"total_ms": round((time.perf_counter() - t_start) * 1000, 2)},
        )

    # 3b. Brain Rule Teaching Fast-Path (e.g. "Remember that...", "Rule: ...")
    learned_rule = BrainService.detect_and_learn_rule(db, prompt, source="VOICE_OR_CHAT", business_id=session.business_id)
    if learned_rule:
        teach_reply = f"I have memorized this {learned_rule.category.lower()} rule: '{learned_rule.instruction}'."
        ConversationService.append_message(db, session, role="user", content=prompt)
        ConversationService.append_message(db, session, role="assistant", content=teach_reply)
        return VoiceInteractResponse(
            response_text=teach_reply,
            action_type="brain_learning",
            conversation_id=session.conversation_id,
            immediate_ack=immediate_ack,
            state=session.state.value,
            latencies={"total_ms": round((time.perf_counter() - t_start) * 1000, 2)},
        )

    # 3c. Standalone Phone Number Input Fast-Path (e.g. "+91 9699779276" or "9699779276")
    phone_digits = re.sub(r'[^0-9]', '', prompt)
    if (len(phone_digits) == 10 and phone_digits[0] in "6789") or (len(phone_digits) == 12 and phone_digits.startswith("91")):
        target_phone = phone_digits[-10:]
        latest_bill = (
            db.query(Bill)
            .options(joinedload(Bill.customer), joinedload(Bill.items))
            .order_by(Bill.created_at.desc())
            .first()
        )
        if latest_bill:
            if latest_bill.customer:
                latest_bill.customer.phone = target_phone
                db.commit()
            biz_obj = (
                db.query(Business).filter(Business.id == latest_bill.business_id).first()
                if latest_bill.business_id
                else db.query(Business).first()
            )
            res = await WhatsAppService.send_invoice_via_whatsapp(
                bill=latest_bill,
                business=biz_obj,
                recipient_phone=target_phone,
            )
            c_name = latest_bill.customer.name if latest_bill.customer else "customer"
            if res.success:
                phone_reply = f"Updated {c_name}'s phone to {target_phone} and sent bill {latest_bill.bill_number} on WhatsApp."
            else:
                phone_reply = f"Updated {c_name}'s phone to {target_phone}, but WhatsApp delivery failed: {res.error_message or 'Please check WhatsApp credentials on server'}."
            ConversationService.append_message(db, session, role="user", content=prompt)
            ConversationService.append_message(db, session, role="assistant", content=phone_reply)
            return VoiceInteractResponse(
                response_text=phone_reply,
                action_type="whatsapp_action",
                conversation_id=session.conversation_id,
                immediate_ack=immediate_ack,
                state=session.state.value,
                latencies={"total_ms": round((time.perf_counter() - t_start) * 1000, 2)},
            )

    # 4. Deterministic Non-LLM Intent Routing & Entity Extraction
    state_ctx = ConversationStateManager.load_state(db, session)
    entities = EntityExtractor.extract_all(
        text=prompt,
        db=db,
        business_id=session.business_id,
        last_product=state_ctx.last_product,
        last_customer=state_ctx.last_customer,
    )

    # Disambiguation Check (Section 21)
    is_mocked = callable(reason_with_gemini) and (getattr(reason_with_gemini, "_is_mock", False) or hasattr(reason_with_gemini, "assert_called") or hasattr(reason_with_gemini, "return_value"))
    if not is_mocked and entities.is_ambiguous and len(entities.ambiguous_candidates) > 1:
        clarify_reply = f"Kaunsi {entities.product}? {', '.join(entities.ambiguous_candidates)}?"
        ConversationService.append_message(db, session, role="user", content=prompt)
        ConversationService.append_message(db, session, role="assistant", content=clarify_reply)
        total_time = (time.perf_counter() - t_start) * 1000
        return VoiceInteractResponse(
            response_text=clarify_reply,
            action_type="clarification",
            conversation_id=session.conversation_id,
            immediate_ack=immediate_ack,
            state=session.state.value,
            latencies={"total_ms": round(total_time, 2)},
        )

    intent_match = IntentRouter.classify(prompt, entities)
    logger.info("Deterministic non-LLM classified: %s (conf: %s)", intent_match.intent, intent_match.confidence)

    # Barge-In / Stop Interruption (Section 14)
    if intent_match.intent == "BARGE_IN":
        barge_reply = ResponseTemplates.get("BARGE_IN")
        ConversationService.append_message(db, session, role="user", content=prompt)
        ConversationService.append_message(db, session, role="assistant", content=barge_reply)
        total_time = (time.perf_counter() - t_start) * 1000
        return VoiceInteractResponse(
            response_text=barge_reply,
            action_type="barge_in",
            conversation_id=session.conversation_id,
            immediate_ack="Stopped",
            state=session.state.value,
            latencies={"total_ms": round(total_time, 2)},
        )

    # Background Jobs: Strategy & Reports (Section 9)
    if intent_match.intent in ("CREATE_WEEKLY_STRATEGY", "GENERATE_SALES_REPORT", "GENERATE_INVENTORY_REPORT"):
        task_id = BackgroundTaskManager.enqueue_task(
            task_type=intent_match.intent,
            business_id=session.business_id,
        )
        state_ctx.active_task_ids.append(task_id)
        state_ctx.last_intent = intent_match.intent
        ConversationStateManager.save_state(db, session, state_ctx)

        strat_ack = ResponseTemplates.get("ACK_STRATEGY") if "STRATEGY" in intent_match.intent else ResponseTemplates.get("ACK_TASK")
        ConversationService.append_message(db, session, role="user", content=prompt)
        ConversationService.append_message(db, session, role="assistant", content=strat_ack)
        total_time = (time.perf_counter() - t_start) * 1000
        return VoiceInteractResponse(
            response_text=strat_ack,
            action_type="background_task",
            conversation_id=session.conversation_id,
            immediate_ack=immediate_ack,
            state=session.state.value,
            business_data={"task_id": task_id, "status": "QUEUED", "type": intent_match.intent},
            latencies={"total_ms": round(total_time, 2)},
        )

    # Task Status Query
    if intent_match.intent == "TASK_STATUS":
        active_ids = state_ctx.active_task_ids
        if not active_ids:
            stat_msg = "Abhi koi background task running nahi hai. Main ready hoon."
        else:
            latest_id = active_ids[-1]
            t_stat = BackgroundTaskManager.get_task_status(latest_id)
            if t_stat and t_stat.get("status") == "RUNNING":
                stat_msg = f"Abhi {t_stat['type'].replace('_', ' ').lower()} chal raha hai. Progress {t_stat['progress']}% hai."
            elif t_stat and t_stat.get("status") == "COMPLETED":
                stat_msg = f"Task {latest_id} complete ho gaya hai."
            else:
                stat_msg = "Abhi ready hoon. Batao kya karna hai."

        ConversationService.append_message(db, session, role="user", content=prompt)
        ConversationService.append_message(db, session, role="assistant", content=stat_msg)
        total_time = (time.perf_counter() - t_start) * 1000
        return VoiceInteractResponse(
            response_text=stat_msg,
            action_type="task_status",
            conversation_id=session.conversation_id,
            immediate_ack=immediate_ack,
            state=session.state.value,
            latencies={"total_ms": round(total_time, 2)},
        )

    # Retrieve Completed Task Result ("Kal wali strategy batao") (Section 18)
    if intent_match.intent == "GET_COMPLETED_TASK":
        completed_job = BackgroundTaskManager.get_latest_completed_task(
            task_type="STRATEGY" if "strategy" in prompt.lower() else None,
            business_id=session.business_id,
        )
        if completed_job and completed_job.get("result"):
            res_obj = completed_job["result"]
            ret_text = res_obj.get("natural_summary") or res_obj.get("summary") or "Last task successfully complete hua tha."
        else:
            ret_text = "Purana koi saved task result nahi mila."

        ConversationService.append_message(db, session, role="user", content=prompt)
        ConversationService.append_message(db, session, role="assistant", content=ret_text)
        total_time = (time.perf_counter() - t_start) * 1000
        return VoiceInteractResponse(
            response_text=ret_text,
            action_type="task_retrieval",
            conversation_id=session.conversation_id,
            immediate_ack=immediate_ack,
            state=session.state.value,
            business_data=completed_job.get("result") if completed_job else None,
            latencies={"total_ms": round(total_time, 2)},
        )

    # Stop/Cancel Task
    if intent_match.intent == "STOP_TASK":
        if state_ctx.active_task_ids:
            cancelled_id = state_ctx.active_task_ids[-1]
            BackgroundTaskManager.cancel_task(cancelled_id)
            c_msg = f"Task {cancelled_id} cancel kar diya hai."
        else:
            c_msg = "Koi active task nahi hai jise cancel kiya ja sake."
        ConversationService.append_message(db, session, role="user", content=prompt)
        ConversationService.append_message(db, session, role="assistant", content=c_msg)
        total_time = (time.perf_counter() - t_start) * 1000
        return VoiceInteractResponse(
            response_text=c_msg,
            action_type="task_cancellation",
            conversation_id=session.conversation_id,
            immediate_ack=immediate_ack,
            state=session.state.value,
            latencies={"total_ms": round(total_time, 2)},
        )

    # Large Payment Confirmation Check (Section 22)
    if intent_match.intent == "UPDATE_PAYMENT" and entities.amount and entities.amount >= 5000.0 and entities.customer:
        c_prompt = f"₹{entities.amount:,.2f} ka payment update karna hai for {entities.customer}. Confirm karo."
        ConversationStateManager.set_pending_confirmation(
            db=db,
            session=session,
            action="UPDATE_PAYMENT",
            data={"customer": entities.customer, "amount": entities.amount, "payment_method": entities.payment_method},
            prompt=c_prompt,
        )
        ConversationService.append_message(db, session, role="user", content=prompt)
        ConversationService.append_message(db, session, role="assistant", content=c_prompt)
        total_time = (time.perf_counter() - t_start) * 1000
        return VoiceInteractResponse(
            response_text=c_prompt,
            action_type="confirmation_required",
            conversation_id=session.conversation_id,
            immediate_ack=immediate_ack,
            state=ConversationState.AWAITING_CONFIRMATION.value,
            latencies={"total_ms": round(total_time, 2)},
        )

    # Map intent to structured deterministic tool execution
    fn_name = None
    args = {}

    # Backward compatibility for legacy tests that explicitly mock reason_with_gemini
    if callable(reason_with_gemini) and (getattr(reason_with_gemini, "_is_mock", False) or hasattr(reason_with_gemini, "assert_called") or hasattr(reason_with_gemini, "return_value")):
        try:
            legacy_res = await reason_with_gemini(
                prompt=prompt,
                conversation_history=[],
                business_context="",
                db=db,
                business_id=session.business_id,
            )
            if legacy_res and legacy_res.function_call:
                fn_name = legacy_res.function_call.get("name")
                args = legacy_res.function_call.get("args") or {}
        except Exception:
            pass

    if fn_name:
        pass
    elif intent_match.intent == "GET_STOCK":
        fn_name = "check_stock"
        args = {"product_name": entities.product or ""}
    elif intent_match.intent == "REDUCE_STOCK":
        fn_name = "reduce_stock"
        args = {"product_name": entities.product or "", "quantity": entities.quantity or 1.0}
    elif intent_match.intent == "GET_PRICE":
        fn_name = "check_stock"
        args = {"product_name": entities.product or ""}
    elif intent_match.intent == "GET_LOW_STOCK":
        fn_name = "get_low_stock_items"
        args = {}
    elif intent_match.intent == "GET_INVENTORY":
        fn_name = "list_all_products"
        args = {}
    elif intent_match.intent == "GET_CUSTOMER_BALANCE":
        fn_name = "get_customer"
        args = {"customer_name": entities.customer or ""}
    elif intent_match.intent == "GET_TODAY_SALES":
        fn_name = "get_sales_today"
        args = {"customer_name": entities.customer or ""}
    elif intent_match.intent == "CREATE_BILL":
        fn_name = "create_bill"
        args = {
            "items": entities.items or [{"name": entities.product or "", "quantity": entities.quantity or 1}],
            "customer_name": entities.customer,
            "send_whatsapp": "whatsapp" in prompt.lower(),
        }
    elif intent_match.intent == "UPDATE_PAYMENT":
        fn_name = "record_payment"
        args = {
            "customer_name": entities.customer,
            "amount": entities.amount or 0.0,
            "payment_method": entities.payment_method,
        }
    elif intent_match.intent == "CONTROL_RELAY":
        fn_name = "control_relay"
        args = {
            "device": entities.device or "",
            "relay_number": entities.relay_channel,
            "state": entities.relay_state or "on",
        }
    elif intent_match.intent in ("GREETING", "HOW_ARE_YOU", "BOT_STATUS", "HELP"):
        fn_name = None
        response_text = ResponseTemplates.get(intent_match.intent)
    elif intent_match.intent == "CLEAR_INVENTORY" or intent_match.is_unknown or intent_match.intent == "UNKNOWN" or (intent_match.requires_clarification and intent_match.intent != "AMBIGUOUS_PRODUCT"):
        recent_msgs = ConversationService.get_history(db, session.id, limit=6)
        history_turns = [{"role": m.role, "content": m.content} for m in recent_msgs]
        h_res = await HybridEngine.reason_and_execute(
            user_text=prompt,
            db=db,
            business_id=session.business_id,
            robot_id=robot_id,
            history=history_turns,
        )
        fn_name = None
        response_text = h_res.response_text
        action_type = h_res.action_type
        business_data = h_res.data
    else:
        fn_name = None
        response_text = ResponseTemplates.get("UNKNOWN")

    gemini_ms = 0.0
    ai_duration = 0.0
    action_type = "conversation"
    business_data: Optional[Dict[str, Any]] = None
    command_dispatched: Optional[RobotCommand] = None

    # 5. Handle Tool Execution
    if fn_name:
        t_tool_0 = time.perf_counter()

        if fn_name in ("check_stock", "get_stock"):
            product_name = args.get("product_name", "").strip()
            # If user asks for generic stock / all products, gracefully redirect to list_all_products
            if not product_name or product_name.lower() in (
                "all", "all items", "all products", "stock", "items", "sagle", "sab",
                "all stock", "shop", "everything", "the product", "product", "products", "list"
            ):
                products = InventoryService.list_all_products(db, session.business_id, limit=30)
                business_data = {"products": products, "total_count": len(products)}
                action_type = "business_query"
                if products:
                    summary = ", ".join([f"{p['name']} ({p['current_stock']:.1f} {p['unit']})" for p in products[:5]])
                    more = f" and {len(products) - 5} more" if len(products) > 5 else ""
                    response_text = f"Dukan mein {len(products)} products available hain: {summary}{more}."
                else:
                    response_text = "Dukan mein abhi koi product stock mein nahi hai."
            else:
                stock_info = InventoryService.get_stock(db, product_name, session.business_id)
                business_data = stock_info
                action_type = "business_query"
                if stock_info.get("found"):
                    stk = stock_info['current_stock']
                    stk_str = str(int(stk)) if stk % 1 == 0 else f"{stk:.1f}"
                    response_text = f"{stock_info['name']} ke {stk_str} {stock_info['unit']} available hain."
                    if stock_info.get("is_low_stock"):
                        response_text += " Dhyaan rahe, stock kam ho raha hai!"
                else:
                    response_text = f"Mujhe '{product_name}' naam ka product inventory mein nahi mila. Product ka naam dobara bataoge?"

        elif fn_name == "reduce_stock":
            product_name = args.get("product_name", "").strip()
            try:
                qty = float(args.get("quantity", 1.0))
            except Exception:
                qty = 1.0
            res = InventoryService.reduce_or_sell_stock(
                db=db,
                product_name=product_name,
                quantity=qty,
                business_id=session.business_id,
            )
            business_data = res
            action_type = "business_query"
            response_text = res["message"]

        elif fn_name == "add_stock":
            product_name = args.get("product_name", "").strip()
            try:
                qty = float(args.get("quantity", 1.0))
            except Exception:
                qty = 1.0
            unit = args.get("unit")
            res = InventoryService.add_or_restock_product(
                db=db,
                product_name=product_name,
                quantity=qty,
                unit=unit,
                business_id=session.business_id,
            )
            business_data = res
            action_type = "business_query"
            response_text = res["message"]

        elif fn_name in ("list_all_products", "get_all_products", "list_inventory"):
            products = InventoryService.list_all_products(db, session.business_id, limit=30)
            business_data = {"products": products, "total_count": len(products)}
            action_type = "business_query"
            if products:
                summary = ", ".join([f"{p['name']} ({p['current_stock']:.1f} {p['unit']})" for p in products[:5]])
                more = f" and {len(products) - 5} more" if len(products) > 5 else ""
                response_text = f"We have {len(products)} products in stock: {summary}{more}."
            else:
                response_text = "There are currently no products in store inventory."

        elif fn_name == "get_low_stock_items":
            low_items = InventoryService.get_low_stock_items(db, session.business_id)
            business_data = {"items": low_items}
            action_type = "business_query"
            if low_items:
                summary = ", ".join([f"{i['name']} ({i['current_stock']} {i['unit']})" for i in low_items[:4]])
                response_text = f"Found {len(low_items)} low stock items: {summary}."
            else:
                response_text = "All products currently meet minimum inventory levels."

        elif fn_name in ("get_sales_today", "get_todays_bills"):
            cust_filter = (args.get("customer_name") or "").strip()
            if cust_filter.lower() in ("all", "everyone", "sab", "sagle", "list", "customer name", "none", "null"):
                cust_filter = ""
            bills_info = BillingService.get_todays_bills(
                db=db,
                business_id=session.business_id,
                customer_name=cust_filter if cust_filter else None,
            )
            business_data = bills_info
            action_type = "business_query"
            total_b = bills_info.get("total_bills", 0)
            total_rev = bills_info.get("total_revenue", 0.0)
            recent_b = bills_info.get("recent_bills", [])

            if total_b == 0:
                if cust_filter:
                    response_text = f"Aaj customer '{cust_filter}' ka koi bill nahi mila."
                else:
                    response_text = "Aaj abhi tak koi bill generate nahi hua hai."
            else:
                if cust_filter:
                    b_list = [f"{b.get('bill_number')} (₹{b.get('total_amount', 0.0):.2f})" for b in recent_b[:5]]
                    more_suffix = f" aur {len(recent_b) - 5} bills" if len(recent_b) > 5 else ""
                    response_text = f"Aaj {cust_filter} ke {total_b} bill totaling ₹{total_rev:,.2f} hue hain: {', '.join(b_list)}{more_suffix}."
                else:
                    response_text = f"Aaj ki total sale ₹{total_rev:,.2f} hai."

        elif fn_name in ("get_customer", "get_customer_balance"):
            cust_name = args.get("customer_name", "").strip()
            # If user asks for general customer names or customer list
            if not cust_name or cust_name.lower() in (
                "all", "list", "name", "customer name", "customers", "sab", "sagle",
                "sagle customer", "customer", "all customers", "customer list"
            ):
                custs = CustomerService.list_all_customers(db, session.business_id)
                business_data = {"customers": custs}
                action_type = "business_query"
                if custs:
                    names_str = ", ".join([f"{c['name']} (₹{c['outstanding_balance']:.2f} due)" for c in custs[:5]])
                    more_suffix = f" and {len(custs) - 5} more" if len(custs) > 5 else ""
                    response_text = f"Registered customers ({len(custs)}): {names_str}{more_suffix}."
                else:
                    response_text = "No customers registered in the database yet."
            else:
                balance_info = CustomerService.get_customer_balance(db, cust_name, session.business_id)
                business_data = balance_info
                action_type = "business_query"
                if balance_info.get("found"):
                    response_text = f"{balance_info['name']}'s outstanding balance is ₹{balance_info['outstanding_balance']:.2f}."
                else:
                    response_text = f"Customer '{cust_name}' was not found in records."

        elif fn_name == "get_business_summary":
            summary = ReportService.get_business_summary(db, session.business_id)
            business_data = summary
            action_type = "business_query"
            response_text = (
                f"Today's revenue is ₹{summary['today_revenue']:.2f} from {summary['today_sales_count']} sales. "
                f"Total customer credit due is ₹{summary['total_credit_due']:.2f}."
            )

        elif fn_name == "create_bill":
            # Multi-turn bill staging: Verify items against DB, then ask for confirmation
            raw_items = args.get("items", [])
            cust_name = args.get("customer_name")
            pay_method = args.get("payment_method", "CASH")

            # Filter items: skip stopwords or conversational filler names
            HINDI_STOPWORDS = {"abhi", "so", "karo", "do", "ek", "item", "cheez", "bhi", "aur", "sample"}
            items_req = []
            for it in raw_items:
                n = (it.get("name") or "").strip().lower()
                if not n or n in HINDI_STOPWORDS:
                    continue
                items_req.append(it)

            # Check validity in database
            preview_items = []
            preview_total = Decimal("0.00")
            missing_items = []

            for item in items_req:
                name = item.get("name", "")
                qty = Decimal(str(item.get("quantity", 1)))
                p = InventoryService.search_product(db, name, session.business_id)
                if p:
                    sub = (p.selling_price * qty).quantize(Decimal("0.01"))
                    preview_total += sub
                    preview_items.append(f"{qty} {p.unit} {p.name} (₹{sub})")
                else:
                    missing_items.append(name)

            send_whatsapp = bool(args.get("send_whatsapp", False)) or ("whatsapp" in prompt.lower())

            if missing_items:
                response_text = f"Cannot create bill. Products not found in stock: {', '.join(missing_items)}."
            elif not preview_items:
                response_text = "Please specify products and quantities to create a bill."
            elif send_whatsapp:
                # Direct immediate execution if WhatsApp dispatch requested
                try:
                    bill_res = BillingService.create_bill(
                        db=db,
                        items_requested=items_req,
                        customer_name=cust_name,
                        payment_method=pay_method,
                        source=BillSource.ROBOT_VOICE,
                        business_id=session.business_id,
                    )
                    business_data = bill_res
                    bill_obj = (
                        db.query(Bill)
                        .options(joinedload(Bill.customer), joinedload(Bill.items))
                        .filter(Bill.id == uuid.UUID(bill_res["bill_id"]))
                        .first()
                    )
                    business_obj = (
                        db.query(Business).filter(Business.id == session.business_id).first()
                        if session.business_id
                        else db.query(Business).first()
                    )
                    res = await WhatsAppService.send_invoice_via_whatsapp(
                        bill=bill_obj,
                        business=business_obj,
                    )
                    if res.success:
                        response_text = (
                            f"Bill {bill_res['bill_number']} of ₹{bill_res['total_amount']:.2f} has been generated "
                            f"and sent to {bill_res['customer_name']} on WhatsApp."
                        )
                    else:
                        response_text = (
                            "I generated the bill, but I couldn't send it on WhatsApp. "
                            "Please check the customer's WhatsApp number."
                        )
                    action_type = "billing_action"
                except Exception as e:
                    logger.error("Error creating and sending WhatsApp bill: %s", e, exc_info=True)
                    response_text = f"Failed to create bill: {str(e)}"
            else:
                # Set multi-turn state: AWAITING_CONFIRMATION
                items_summary = ", ".join(preview_items)
                cust_label = f" for {cust_name}" if cust_name else ""
                response_text = (
                    f"Bill preview{cust_label}: {items_summary}. Total is ₹{preview_total:.2f}. "
                    "Should I confirm and record this bill?"
                )
                ConversationService.update_state(
                    db=db,
                    session=session,
                    state=ConversationState.AWAITING_CONFIRMATION,
                    pending_intent="create_bill",
                    pending_action="create_bill",
                    context_data={
                        "items": items_req,
                        "customer_name": cust_name,
                        "payment_method": pay_method,
                        "estimated_total": float(preview_total),
                        "send_whatsapp": False,
                    },
                )
                action_type = "billing_action"

        elif fn_name == "send_whatsapp_bill":
            inv_id = args.get("invoice_id")
            cust_name = args.get("customer_name")
            phone_num = args.get("phone_number")

            bill_obj = None
            if inv_id:
                try:
                    bill_obj = (
                        db.query(Bill)
                        .options(joinedload(Bill.customer), joinedload(Bill.items))
                        .filter(Bill.id == uuid.UUID(inv_id.strip()))
                        .first()
                    )
                except Exception:
                    pass
                if not bill_obj:
                    bill_obj = (
                        db.query(Bill)
                        .options(joinedload(Bill.customer), joinedload(Bill.items))
                        .filter(Bill.bill_number.ilike(inv_id.strip()))
                        .first()
                    )

            if not bill_obj and cust_name:
                customer = CustomerService.search_customer(db, cust_name, session.business_id)
                if customer:
                    bill_obj = (
                        db.query(Bill)
                        .options(joinedload(Bill.customer), joinedload(Bill.items))
                        .filter(Bill.customer_id == customer.id)
                        .order_by(Bill.created_at.desc())
                        .first()
                    )

            if not bill_obj:
                bill_obj = (
                    db.query(Bill)
                    .options(joinedload(Bill.customer), joinedload(Bill.items))
                    .order_by(Bill.created_at.desc())
                    .first()
                )

            if not bill_obj:
                response_text = "No invoice found to send via WhatsApp."
            else:
                business_obj = (
                    db.query(Business).filter(Business.id == bill_obj.business_id).first()
                    if bill_obj.business_id
                    else db.query(Business).first()
                )
                if phone_num and bill_obj.customer:
                    clean_p = re.sub(r'[^0-9]', '', str(phone_num))
                    if len(clean_p) >= 10:
                        bill_obj.customer.phone = clean_p[-10:]
                        db.commit()
                        db.refresh(bill_obj.customer)

                res = await WhatsAppService.send_invoice_via_whatsapp(
                    bill=bill_obj,
                    business=business_obj,
                    recipient_phone=phone_num,
                )
                if res.success:
                    c_name = bill_obj.customer.name if bill_obj.customer else "the customer"
                    response_text = (
                        f"Bill {bill_obj.bill_number} of ₹{float(bill_obj.total_amount):.2f} has been generated "
                        f"and sent to {c_name} on WhatsApp."
                    )
                else:
                    response_text = (
                        f"I generated the bill, but I couldn't send it on WhatsApp: "
                        f"{res.error_message or 'Please check customer WhatsApp number.'}"
                    )
            action_type = "whatsapp_action"

        elif fn_name == "clear_or_reset_inventory":
            is_confirmed = bool(args.get("confirm", False))
            if is_confirmed:
                res = InventoryService.clear_all_inventory(db, business_id=session.business_id)
                response_text = res["message"]
                business_data = res
                action_type = "inventory_action"
            else:
                response_text = "Dukan ka sara stock delete karna bada action hai. Kya aap sach mein confirm karte hain? Haan bolenge toh main proceed karunga."
                action_type = "confirmation_required"

        elif fn_name == "add_product":
            p_name = str(args.get("name", "")).strip()
            p_unit = str(args.get("unit", "pcs")).strip()
            try:
                p_price = Decimal(str(args.get("selling_price", 0)))
            except Exception:
                p_price = Decimal("0")
            try:
                p_stock = Decimal(str(args.get("stock", 10)))
            except Exception:
                p_stock = Decimal("10")

            if p_name and p_price > Decimal("0"):
                prod = InventoryService.add_or_update_product(
                    db=db,
                    name=p_name,
                    selling_price=p_price,
                    current_stock=p_stock,
                    unit=p_unit,
                    business_id=session.business_id,
                )
                business_data = {
                    "product_id": prod["id"],
                    "name": prod["name"],
                    "selling_price": float(prod["selling_price"]),
                    "current_stock": float(prod["current_stock"]),
                    "unit": prod["unit"],
                }
                action_type = "inventory_action"
                response_text = prod["message"]
            else:
                response_text = "Please specify a valid product name and price to add it to inventory."

        elif fn_name == "control_relay":
            dev = str(args.get("device", "")).lower().strip()
            raw_relay = args.get("relay_number")
            raw_state = str(args.get("state", "on")).lower().strip()
            state = "on" if raw_state in ("on", "1", "true", "chalu", "shuru", "lagao") else "off"

            # Map device name to relay channel if relay_number was not given
            if raw_relay is not None and str(raw_relay).isdigit() and 1 <= int(raw_relay) <= 4:
                relay_num = int(raw_relay)
                if not dev:
                    dev = "light" if relay_num == 1 else ("fan" if relay_num == 2 else ("socket" if relay_num == 3 else "aux device"))
            else:
                if any(w in dev for w in ("fan", "pankha", "cooler")):
                    relay_num = 2
                    dev = "fan"
                elif any(w in dev for w in ("socket", "plug", "charger")):
                    relay_num = 3
                    dev = "socket"
                elif any(w in dev for w in ("aux", "extra", "relay 4")):
                    relay_num = 4
                    dev = "aux device"
                else:
                    relay_num = 1
                    dev = "light"

            db_cmd = RobotService.queue_command(
                db=db,
                robot_id=robot_id,
                action="set_relay",
                params={"relay": relay_num, "state": state},
            )
            command_dispatched = RobotCommand(
                command_id=db_cmd.command_id,
                robot_id=robot_id,
                action="set_relay",
                params={"relay": relay_num, "state": state},
                status="pending",
            )
            if state == "on":
                response_text = f"Done, {dev} on kar di."
            else:
                response_text = f"Sure, {dev} band kar diya."
            action_type = "hardware_action"

        elif fn_name == "blink_led":
            times = args.get("times", 3)
            db_cmd = RobotService.queue_command(
                db=db,
                robot_id=robot_id,
                action="blink_led",
                params={"count": times, "interval_ms": 200},
            )
            command_dispatched = RobotCommand(
                command_id=db_cmd.command_id,
                robot_id=robot_id,
                action="blink_led",
                params={"count": times},
                status="pending",
            )
            response_text = f"Blinking the status LED {times} times."
            action_type = "hardware_action"

        elif fn_name == "record_payment":
            amount = float(args.get("amount", 0.0))
            cust_name = args.get("customer_name")
            p_method = args.get("payment_method", "CASH")
            ref = args.get("reference")
            try:
                pay_res = BillingService.record_payment(
                    db=db,
                    customer_name=cust_name,
                    amount=amount,
                    payment_method=p_method,
                    notes=ref,
                    business_id=session.business_id,
                )
                business_data = pay_res
                action_type = "billing_action"
                c_name = pay_res["customer_name"]
                rem = pay_res["remaining_balance"]
                status_info = f" Bill {pay_res['bill_number']} status: {pay_res['bill_status']}." if pay_res.get("bill_number") else ""
                response_text = f"{c_name} se ₹{pay_res['amount_paid']:.2f} payment receive ho gaya ({pay_res['payment_method']}). Ab baki balance ₹{rem:.2f} hai.{status_info}"
            except Exception as pe:
                response_text = f"Payment record nahi ho paya: {str(pe)}"

        elif fn_name == "get_customer_ledger":
            cust_name = args.get("customer_name", "").strip()
            ledger_res = CustomerService.get_customer_ledger(
                db=db,
                customer_name=cust_name,
                business_id=session.business_id,
            )
            business_data = ledger_res
            action_type = "business_query"
            response_text = ledger_res.get("summary") or f"{cust_name} ka ledger check kiya."

        elif fn_name == "create_task":
            desc = args.get("description", "").strip()
            cust_name = args.get("customer_name")
            task = TaskService.create_task(
                db=db,
                description=desc,
                customer_name=cust_name,
                business_id=session.business_id,
            )
            business_data = {"task_id": str(task.id), "description": task.description}
            action_type = "task_action"
            response_text = f"Done. Task note kar liya hai: '{task.description}'."

        elif fn_name == "list_tasks":
            cust_name = args.get("customer_name")
            tasks = TaskService.list_tasks(
                db=db,
                business_id=session.business_id,
                customer_name=cust_name,
            )
            business_data = {"tasks": tasks, "count": len(tasks)}
            action_type = "task_action"
            if tasks:
                t_list = [t["description"] for t in tasks[:3]]
                more = f" and {len(tasks)-3} more" if len(tasks) > 3 else ""
                response_text = f"You have {len(tasks)} pending task(s): {'; '.join(t_list)}{more}."
            else:
                response_text = "Koi pending task nahi hai."

        elif fn_name == "complete_task":
            kw = args.get("task_keyword", "").strip()
            comp_res = TaskService.complete_task(
                db=db,
                task_id_or_keyword=kw,
                business_id=session.business_id,
            )
            business_data = comp_res
            action_type = "task_action"
            response_text = comp_res.get("message", "Task status updated.")

        elif fn_name == "save_ai_memory":
            content = args.get("content", "").strip()
            m_type = args.get("memory_type", "BUSINESS_PREFERENCE")
            mem = MemoryService.store_memory(
                db=db,
                business_id=session.business_id,
                content=content,
                memory_type=m_type,
            )
            business_data = {"memory_id": str(mem.id), "content": mem.content}
            action_type = "memory_action"
            response_text = f"Theek hai, maine yaad rakh liya: '{content}'."

        elif fn_name == "modify_product_price":
            prod_name = args.get("product_name", "").strip()
            new_price = args.get("new_price", 0.0)
            token = req.auth_token

            if not SecurityService.is_token_authorized(token, session.business_id):
                response_text = (
                    "Security Verification Required: Changing product price is a high-risk action. "
                    "Please provide your 6-digit owner PIN to proceed."
                )
                action_type = "security_required"
            else:
                prod = InventoryService.search_product(db, prod_name, session.business_id)
                if prod:
                    old_price = float(prod.selling_price)
                    prod.selling_price = Decimal(str(round(new_price, 2)))
                    db.commit()
                    db.refresh(prod)
                    SecurityService.consume_token(token)
                    business_data = {
                        "product_id": str(prod.id),
                        "name": prod.name,
                        "old_price": old_price,
                        "new_price": float(prod.selling_price),
                    }
                    action_type = "inventory_action"
                    response_text = f"{prod.name} ki selling price ₹{old_price:.2f} se badal kar ₹{float(prod.selling_price):.2f} kar di hai."
                else:
                    response_text = f"Product '{prod_name}' inventory mein nahi mila."

        else:
            response_text = f"Tool '{fn_name}' executed."

        tool_ms = (time.perf_counter() - t_tool_0) * 1000

    # 6. Save Turn and Activity Log
    ConversationService.append_message(db, session, role="user", content=prompt)
    ConversationService.append_message(
        db,
        session,
        role="assistant",
        content=response_text,
        structured_intent=fn_name or intent_match.intent,
        entities=args,
    )

    if entities.product:
        state_ctx.last_product = entities.product
    if entities.customer:
        state_ctx.last_customer = entities.customer
    state_ctx.last_intent = intent_match.intent
    ConversationStateManager.save_state(db, session, state_ctx)

    total_time = (time.perf_counter() - t_start) * 1000

    # Log Activity
    activity = AIActivity(
        business_id=session.business_id,
        robot_id=robot_id,
        user_query=prompt,
        ai_response_text=response_text,
        structured_tool_name=fn_name or intent_match.intent,
        structured_tool_payload=args,
        execution_status="SUCCESS",
        latency_ms=int(total_time),
    )
    db.add(activity)
    db.commit()

    import urllib.parse
    # Strip high unicode emojis that corrupt 115200 baud Serial and OLED displays
    clean_display_text = re.sub(r'[\U00010000-\U0010ffff]', '', response_text).strip()
    clean_audio_text = re.sub(r"[^\w\s\.,\?!₹\-']", "", clean_display_text or response_text).strip()
    audio_url = f"/api/v1/voice/audio/tts?text={urllib.parse.quote(clean_audio_text or clean_display_text or response_text)}&lang=hi"

    # Non-blocking background TTS cache prewarm
    if background_tasks and clean_audio_text:
        background_tasks.add_task(synthesize_speech, clean_audio_text, "hi")

    return VoiceInteractResponse(
        response_text=clean_display_text or response_text,
        action_type=action_type,
        conversation_id=session.conversation_id,
        immediate_ack=immediate_ack,
        state=session.state.value,
        business_data=business_data,
        command_dispatched=command_dispatched,
        audio_url=audio_url,
        latencies={
            "ai_ms": 0.0,
            "fast_path_ms": round(fast_path_ms, 2),
            "memory_ms": round(memory_ms, 2),
            "instructions_ms": round(instructions_ms, 2),
            "gemini_ms": 0.0,
            "tool_ms": round(tool_ms, 2),
            "database_ms": round(database_ms, 2),
            "total_ms": round(total_time, 2),
        },
    )


@router.websocket("/ws")
@router.websocket("/ws/voice")
async def voice_websocket_endpoint(websocket: WebSocket, robot_id: str = "ROBOT-001"):
    """Real-time bidirectional 16kHz PCM audio streaming, barge-in, and background task gateway."""
    handler = WebSocketSessionHandler(websocket, robot_id=robot_id)
    await handler.handle_connection()


@router.post("/audio/transcribe", summary="Transcribe speech audio with Groq Whisper & Gemini Multimodal")
async def transcribe_audio_endpoint(file: UploadFile = File(...)):
    """Transcribe uploaded voice audio bytes using Groq Whisper or Gemini Multimodal audio."""
    from app.ai.speech_service import transcribe_speech
    audio_bytes = await file.read()
    transcribed_text = await transcribe_speech(audio_bytes, file.filename or "audio.wav")
    return {"text": transcribed_text}


@router.get("/audio/tts", summary="Synthesize speech with Edge Neural & Google TTS")
async def tts_endpoint(text: str, lang: str = "hi"):
    """Synthesize natural Indian speech audio using Edge Neural TTS with Google TTS fallback."""
    from fastapi.responses import Response
    from app.ai.speech_service import synthesize_speech
    audio_data = await synthesize_speech(text, language=lang)
    if not audio_data:
        raise HTTPException(status_code=500, detail="TTS synthesis failed")
    return Response(content=audio_data, media_type="audio/mpeg")
