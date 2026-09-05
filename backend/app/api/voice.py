"""Voice and text interaction router connecting persistent conversation sessions,
Gemini function calling, authoritative PostgreSQL business services, and hardware command dispatch."""

from datetime import datetime, timezone
from decimal import Decimal
import logging
import re
import time
from typing import Any, Dict, List, Optional
from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from sqlalchemy.orm import Session

from app.ai.gemini_service import reason_with_gemini
from app.config import get_settings
from app.database.session import get_db
from app.models.billing import BillSource
from app.models.conversation import ConversationState
from app.models.robot_command import AIActivity, CommandStatus
from app.schemas.robot import (
    RobotCommand,
    RobotCommandCreate,
    VoiceInteractRequest,
    VoiceInteractResponse,
)
from app.services.billing_service import BillingService
from app.services.conversation_service import ConversationService
from app.services.customer_service import CustomerService
from app.services.inventory_service import InventoryService
from app.services.report_service import ReportService
from app.services.robot_service import RobotService

logger = logging.getLogger("business_ai_robot.voice")
router = APIRouter()
settings = get_settings()


def _get_immediate_ack(prompt: str) -> str:
    """Generate sub-200ms acoustic/text acknowledgment based on user utterance keywords."""
    p = prompt.lower()
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
    db: Session = Depends(get_db),
) -> VoiceInteractResponse:
    """
    Main conversational brain orchestrator:
    1. Retrieve or initialize persistent conversation session.
    2. Deliver immediate acknowledgement (< 200ms).
    3. Evaluate affirmative confirmation ("haan karo") for pending multi-turn intents.
    4. Reason with Gemini AI with tools and conversational history.
    5. Execute authoritative PostgreSQL business services (Stock, Billing, Ledgers).
    6. Persist message history, AI activity log, and return response.
    """
    t_start = time.perf_counter()
    robot_id = req.robot_id or settings.DEFAULT_ROBOT_ID
    prompt = req.text.strip()
    immediate_ack = _get_immediate_ack(prompt)

    # 1. Retrieve or create session
    session = ConversationService.get_or_create_session(
        db=db,
        conversation_id=req.conversation_id,
        business_id=req.business_id,
        robot_id=robot_id,
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

    # 4. Multi-Turn Gemini AI Reasoning with Function Calling
    # Fetch recent history turns
    history_records = ConversationService.get_history(db, session.id, limit=8)
    history_payload = [
        {"role": "user" if m.role == "user" else "assistant", "content": m.content}
        for m in history_records
    ]

    t_ai_start = time.perf_counter()
    gemini_res = await reason_with_gemini(user_text=prompt, history=history_payload)
    ai_duration = (time.perf_counter() - t_ai_start) * 1000

    response_text = ""
    action_type = "conversation"
    business_data: Optional[Dict[str, Any]] = None
    command_dispatched: Optional[RobotCommand] = None

    # 5. Handle Tool / Function Call
    if gemini_res.function_call:
        fn_name = gemini_res.function_call.get("name")
        args = gemini_res.function_call.get("args", {})
        logger.info("Handling tool call: %s with args: %s", fn_name, args)

        if fn_name == "get_stock":
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
                    response_text = f"We have {len(products)} products in stock: {summary}{more}."
                else:
                    response_text = "There are currently no products in store inventory."
            else:
                stock_info = InventoryService.get_stock(db, product_name, session.business_id)
                business_data = stock_info
                action_type = "business_query"
                if stock_info.get("found"):
                    response_text = (
                        f"{stock_info['name']} has {stock_info['current_stock']:.1f} {stock_info['unit']} in stock "
                        f"at ₹{stock_info['selling_price']:.2f} per {stock_info['unit']}."
                    )
                    if stock_info.get("is_low_stock"):
                        response_text += " Note: stock is running low!"
                else:
                    response_text = f"Sorry, '{product_name}' was not found in inventory."

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

        elif fn_name == "get_todays_bills":
            bills_info = BillingService.get_todays_bills(db, session.business_id)
            business_data = bills_info
            action_type = "business_query"
            total_b = bills_info.get("total_bills", 0)
            total_rev = bills_info.get("total_revenue", 0.0)
            recent_b = bills_info.get("recent_bills", [])

            if total_b == 0:
                response_text = "No bills have been generated today."
            else:
                cust_details = []
                for b in recent_b[:5]:
                    c_name = b.get("customer_name") or "Walk-in Customer"
                    amt = b.get("total_amount", 0.0)
                    cust_details.append(f"{c_name} (₹{amt:.2f})")
                cust_str = ", ".join(cust_details)
                more_suffix = f" and {len(recent_b) - 5} more" if len(recent_b) > 5 else ""
                response_text = f"Today {total_b} bills were given totaling ₹{total_rev:.2f} to: {cust_str}{more_suffix}."

        elif fn_name == "get_customer_balance":
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

            if missing_items:
                response_text = f"Cannot create bill. Products not found in stock: {', '.join(missing_items)}."
            elif not preview_items:
                response_text = "Please specify products and quantities to create a bill."
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
                    },
                )
                action_type = "billing_action"

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
            relay_num = args.get("relay_number", 1)
            state = args.get("state", "off").lower()
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
            response_text = f"Turning relay {relay_num} {state}."
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

        else:
            response_text = f"Tool '{fn_name}' executed."

    else:
        # Natural conversational text from Gemini
        response_text = gemini_res.text or "I am here. How can I help you with your store?"

    # 6. Save Turn and AI Activity Log
    ConversationService.append_message(db, session, role="user", content=prompt)
    ConversationService.append_message(
        db,
        session,
        role="assistant",
        content=response_text,
        structured_intent=gemini_res.function_call.get("name") if gemini_res.function_call else None,
        entities=gemini_res.function_call.get("args") if gemini_res.function_call else None,
    )

    total_time = (time.perf_counter() - t_start) * 1000

    # Log AI Activity
    activity = AIActivity(
        business_id=session.business_id,
        robot_id=robot_id,
        user_query=prompt,
        ai_response_text=response_text,
        structured_tool_name=gemini_res.function_call.get("name") if gemini_res.function_call else None,
        structured_tool_payload=gemini_res.function_call.get("args") if gemini_res.function_call else None,
        execution_status="SUCCESS" if gemini_res.is_success else "FAILED",
        latency_ms=int(total_time),
    )
    db.add(activity)
    db.commit()

    return VoiceInteractResponse(
        response_text=response_text,
        action_type=action_type,
        conversation_id=session.conversation_id,
        immediate_ack=immediate_ack,
        state=session.state.value,
        business_data=business_data,
        command_dispatched=command_dispatched,
        latencies={
            "ai_ms": round(ai_duration, 2),
            "total_ms": round(total_time, 2),
        },
    )


@router.post("/audio/transcribe", summary="Transcribe speech audio with Groq Whisper")
async def transcribe_audio_endpoint(file: UploadFile = File(...)):
    """Transcribe uploaded voice audio bytes using Groq Whisper-large-v3."""
    from app.ai.speech_service import transcribe_with_groq
    audio_bytes = await file.read()
    transcribed_text = await transcribe_with_groq(audio_bytes, file.filename or "audio.wav")
    return {"text": transcribed_text}


@router.get("/audio/tts", summary="Synthesize speech with Edge TTS")
async def tts_endpoint(text: str, lang: str = "en"):
    """Synthesize high-quality speech MP3 using Microsoft Edge Neural TTS."""
    from fastapi.responses import Response
    from app.ai.speech_service import synthesize_with_edge_tts
    audio_data = await synthesize_with_edge_tts(text, language=lang)
    if not audio_data:
        raise HTTPException(status_code=500, detail="TTS synthesis failed or package unavailable")
    return Response(content=audio_data, media_type="audio/mpeg")
