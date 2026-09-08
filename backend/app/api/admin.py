"""Admin Web Dashboard & Brain Training API router.

Serves the interactive Admin Panel at /admin and provides REST APIs for:
- Live interactive chat with the Robot Brain
- Brain Knowledge / Instruction management (CRUD, active toggle, category tagging)
- Store inventory, sales metrics, and WhatsApp operations
"""

from decimal import Decimal
import logging
from pathlib import Path
import time
from typing import Any, Dict, List, Optional
import uuid

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

import re
from app.ai.gemini_service import reason_with_gemini
from app.database.session import get_db
from app.models.billing import Bill, Customer
from app.models.business import Business
from app.models.product import Product
from app.services.billing_service import BillingService
from app.services.brain_service import BrainService
from app.services.customer_service import CustomerService
from app.services.inventory_service import InventoryService
from app.services.memory_service import MemoryService
from app.services.report_service import ReportService
from app.services.security_service import SecurityService
from app.services.task_service import TaskService
from app.services.whatsapp_service import WhatsAppService

logger = logging.getLogger("business_ai_robot.admin")
router = APIRouter()

TEMPLATES_DIR = Path(__file__).resolve().parent.parent / "templates"
ADMIN_HTML_PATH = TEMPLATES_DIR / "admin.html"


# --- Request / Response Schemas ---

class CreateInstructionRequest(BaseModel):
    instruction: str
    category: Optional[str] = "RULE"
    source: Optional[str] = "WEB_PANEL"


class ToggleInstructionRequest(BaseModel):
    is_active: Optional[bool] = None


class AdminChatRequest(BaseModel):
    message: str
    teach_mode: bool = False
    auth_token: Optional[str] = None


class CreateTaskRequest(BaseModel):
    description: str
    customer_name: Optional[str] = None
    due_date: Optional[str] = None


class CreateMemoryRequest(BaseModel):
    content: str
    memory_type: Optional[str] = "BUSINESS_PREFERENCE"


class RecordPaymentRequest(BaseModel):
    customer_name: str
    amount: float
    payment_method: Optional[str] = "CASH"
    notes: Optional[str] = None


class UpdateProductRequest(BaseModel):
    name: str
    selling_price: float
    current_stock: Optional[float] = None
    unit: Optional[str] = "kg"


# --- UI Endpoints ---

@router.get("/admin", response_class=HTMLResponse, tags=["admin"])
@router.get("/dashboard", response_class=HTMLResponse, tags=["admin"])
async def get_admin_dashboard():
    """Serve the modern dark-themed interactive Robot Brain Training & Ops Dashboard."""
    if not ADMIN_HTML_PATH.exists():
        raise HTTPException(status_code=404, detail="Admin dashboard template not found.")
    content = ADMIN_HTML_PATH.read_text(encoding="utf-8")
    return HTMLResponse(content=content)


# --- REST API Endpoints ---

@router.get("/api/v1/admin/stats", tags=["admin"])
async def get_admin_stats(db: Session = Depends(get_db)):
    """Fetch aggregated store metrics, products, and today's bills for the dashboard."""
    biz = db.query(Business).first()
    biz_id = biz.id if biz else None

    # Summary
    summary = ReportService.get_business_summary(db, biz_id)

    # Products
    prods = InventoryService.list_all_products(db, biz_id, limit=50)

    # Today's Bills
    bills_data = BillingService.get_todays_bills(db, biz_id)

    # Customer count
    cust_q = db.query(Customer)
    if biz_id:
        cust_q = cust_q.filter(Customer.business_id == biz_id)
    cust_count = cust_q.count()

    # Active rules count
    active_rules_count = len(BrainService.get_active_instructions(db, biz_id))

    return {
        "today_revenue": summary.get("today_revenue", 0.0),
        "today_bills_count": summary.get("today_sales_count", 0),
        "total_credit_due": summary.get("total_credit_due", 0.0),
        "total_products": len(prods),
        "low_stock_count": summary.get("low_stock_count", 0),
        "total_customers": cust_count,
        "active_rules_count": active_rules_count,
        "products": prods,
        "recent_bills": bills_data.get("recent_bills", []),
    }


@router.get("/api/v1/admin/instructions", tags=["admin"])
async def list_instructions(db: Session = Depends(get_db)):
    """List all brain instructions and custom rules in the database."""
    biz = db.query(Business).first()
    return BrainService.list_all_instructions(db, biz.id if biz else None)


@router.post("/api/v1/admin/instructions", tags=["admin"])
async def add_instruction(req: CreateInstructionRequest, db: Session = Depends(get_db)):
    """Add and persist a new custom brain instruction."""
    try:
        biz = db.query(Business).first()
        item = BrainService.add_instruction(
            db=db,
            instruction=req.instruction,
            category=req.category or "RULE",
            source=req.source or "WEB_PANEL",
            business_id=biz.id if biz else None,
        )
        return {
            "success": True,
            "id": str(item.id),
            "instruction": item.instruction,
            "category": item.category,
            "is_active": item.is_active,
        }
    except Exception as e:
        logger.error("Failed to add instruction: %s", e)
        raise HTTPException(status_code=400, detail=str(e))


@router.patch("/api/v1/admin/instructions/{instruction_id}/toggle", tags=["admin"])
async def toggle_instruction(
    instruction_id: uuid.UUID,
    req: ToggleInstructionRequest,
    db: Session = Depends(get_db),
):
    """Toggle a brain instruction active or disabled."""
    item = BrainService.toggle_instruction(
        db=db,
        instruction_id=instruction_id,
        is_active=req.is_active,
    )
    if not item:
        raise HTTPException(status_code=404, detail="Instruction not found")
    return {"success": True, "id": str(item.id), "is_active": item.is_active}


@router.delete("/api/v1/admin/instructions/{instruction_id}", tags=["admin"])
async def delete_instruction(instruction_id: uuid.UUID, db: Session = Depends(get_db)):
    """Permanently remove a brain instruction from the database."""
    success = BrainService.delete_instruction(db=db, instruction_id=instruction_id)
    if not success:
        raise HTTPException(status_code=404, detail="Instruction not found")
    return {"success": True, "id": str(instruction_id)}


@router.get("/api/v1/admin/tasks", tags=["admin"])
async def list_admin_tasks(db: Session = Depends(get_db)):
    """List operational tasks and reminders."""
    biz = db.query(Business).first()
    return TaskService.list_tasks(db, biz.id if biz else None, status=None, limit=50)


@router.post("/api/v1/admin/tasks", tags=["admin"])
async def create_admin_task(req: CreateTaskRequest, db: Session = Depends(get_db)):
    """Create an operational task or reminder."""
    biz = db.query(Business).first()
    task = TaskService.create_task(
        db,
        description=req.description,
        customer_name=req.customer_name,
        business_id=biz.id if biz else None,
    )
    return {"success": True, "task_id": str(task.id), "description": task.description}


@router.post("/api/v1/admin/tasks/{task_id}/complete", tags=["admin"])
async def complete_admin_task(task_id: str, db: Session = Depends(get_db)):
    """Mark an operational task as completed."""
    biz = db.query(Business).first()
    return TaskService.complete_task(db, task_id_or_keyword=task_id, business_id=biz.id if biz else None)


@router.get("/api/v1/admin/memories", tags=["admin"])
async def list_admin_memories(db: Session = Depends(get_db)):
    """List contextual preferences and habits stored in AI memory."""
    biz = db.query(Business).first()
    return MemoryService.list_memories(db, biz.id if biz else None, limit=50)


@router.post("/api/v1/admin/memories", tags=["admin"])
async def create_admin_memory(req: CreateMemoryRequest, db: Session = Depends(get_db)):
    """Store a new preference into AI memory."""
    biz = db.query(Business).first()
    mem = MemoryService.store_memory(
        db,
        biz.id if biz else None,
        content=req.content,
        memory_type=req.memory_type or "BUSINESS_PREFERENCE",
    )
    return {"success": True, "memory_id": str(mem.id), "content": mem.content}


@router.get("/api/v1/admin/customers/{customer_name}/ledger", tags=["admin"])
async def get_admin_customer_ledger(customer_name: str, db: Session = Depends(get_db)):
    """Fetch chronological customer ledger, running balances, and manager summary."""
    biz = db.query(Business).first()
    return CustomerService.get_customer_ledger(db, customer_name=customer_name, business_id=biz.id if biz else None)


@router.post("/api/v1/admin/payments", tags=["admin"])
async def record_admin_payment(req: RecordPaymentRequest, db: Session = Depends(get_db)):
    """Record customer payment and update bill/ledger status."""
    biz = db.query(Business).first()
    try:
        return BillingService.record_payment(
            db=db,
            customer_name=req.customer_name,
            amount=req.amount,
            payment_method=req.payment_method or "CASH",
            notes=req.notes,
            business_id=biz.id if biz else None,
        )
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/api/v1/admin/products/update", tags=["admin"])
async def update_admin_product(req: UpdateProductRequest, db: Session = Depends(get_db)):
    """Add or update a product's price, stock, and unit in the store inventory."""
    biz = db.query(Business).first()
    biz_id = biz.id if biz else None
    res = InventoryService.add_or_update_product(
        db=db,
        name=req.name,
        selling_price=Decimal(str(req.selling_price)),
        current_stock=Decimal(str(req.current_stock)) if req.current_stock is not None else None,
        unit=req.unit or "kg",
        business_id=biz_id,
    )
    return res


@router.post("/api/v1/admin/chat", tags=["admin"])
async def admin_chat(req: AdminChatRequest, db: Session = Depends(get_db)):
    """
    Live conversational playground endpoint for training or operating the robot brain.
    - If teach_mode is ON or message has a teaching pattern, permanently saves rule to PostgreSQL.
    - Otherwise reasons with Gemini with dynamic custom instructions and executes store tools.
    """
    t_start = time.perf_counter()
    msg = req.message.strip()
    if not msg:
        raise HTTPException(status_code=400, detail="Message cannot be empty")

    biz = db.query(Business).first()
    biz_id = biz.id if biz else None

    # Case 1: Explicit Teach Mode enabled
    if req.teach_mode:
        item = BrainService.add_instruction(
            db=db,
            instruction=msg,
            source="TEACH_MODE_CHAT",
            business_id=biz_id,
        )
        duration = round((time.perf_counter() - t_start) * 1000, 2)
        resp_text = f"✅ Memorized to Brain Database: '{item.instruction}' (Category: {item.category})"
        import urllib.parse
        return {
            "response_text": resp_text,
            "rule_saved": True,
            "rule_category": item.category,
            "tool_invoked": None,
            "action_type": "brain_learning",
            "audio_url": f"/api/v1/voice/audio/tts?text={urllib.parse.quote(resp_text)}&lang=hi",
            "latencies": {"total_ms": duration},
        }

    # Case 2: Natural Language Teaching detection (e.g. "Remember that...", "Rule:...")
    learned = BrainService.detect_and_learn_rule(db, msg, source="CHAT_TEACH", business_id=biz_id)
    if learned:
        duration = round((time.perf_counter() - t_start) * 1000, 2)
        resp_text = f"I have memorized this {learned.category.lower()} rule: '{learned.instruction}'. It will now be actively enforced across all robot interactions."
        import urllib.parse
        return {
            "response_text": resp_text,
            "rule_saved": True,
            "rule_category": learned.category,
            "tool_invoked": None,
            "action_type": "brain_learning",
            "audio_url": f"/api/v1/voice/audio/tts?text={urllib.parse.quote(resp_text)}&lang=hi",
            "latencies": {"total_ms": duration},
        }

    # Case 3: Live Query with Tool Calling & Dynamic Active Rules + AI Memories Injected
    custom_rules = BrainService.get_instruction_strings(db, biz_id)
    relevant_mems = MemoryService.get_relevant_memories(db, biz_id, query_text=msg)
    if relevant_mems:
        custom_rules = list(custom_rules) + [f"AI Memory Context: {m}" for m in relevant_mems]

    gemini_res = await reason_with_gemini(
        user_text=msg,
        custom_instructions=custom_rules,
    )

    response_text = ""
    tool_name = None
    action_type = "conversation"
    business_data = None

    if gemini_res.function_call:
        tool_name = gemini_res.function_call.get("name")
        args = gemini_res.function_call.get("args", {})
        logger.info("Admin Chat Gemini tool invocation: %s (%s)", tool_name, args)

        if tool_name in ("check_stock", "get_stock"):
            p_name = args.get("product_name", "")
            stock_info = InventoryService.get_stock(db, p_name, biz_id)
            if stock_info.get("found"):
                stk = stock_info['current_stock']
                stk_str = str(int(stk)) if stk % 1 == 0 else f"{stk:.1f}"
                response_text = f"{stock_info['name']} ke {stk_str} {stock_info['unit']} available hain."
            else:
                response_text = f"Mujhe '{p_name}' naam ka product inventory mein nahi mila. Product ka naam dobara bataoge?"
            action_type = "business_query"

        elif tool_name == "reduce_stock":
            p_name = args.get("product_name", "").strip()
            try:
                qty = float(args.get("quantity", 1.0))
            except Exception:
                qty = 1.0
            res = InventoryService.reduce_or_sell_stock(db=db, product_name=p_name, quantity=qty, business_id=biz_id)
            response_text = res["message"]
            business_data = res
            action_type = "business_query"

        elif tool_name == "add_stock":
            p_name = args.get("product_name", "").strip()
            try:
                qty = float(args.get("quantity", 1.0))
            except Exception:
                qty = 1.0
            res = InventoryService.add_or_restock_product(db=db, product_name=p_name, quantity=qty, unit=args.get("unit"), business_id=biz_id)
            response_text = res["message"]
            business_data = res
            action_type = "business_query"

        elif tool_name in ("get_sales_today", "get_todays_bills"):
            cust_filter = args.get("customer_name")
            bills_info = BillingService.get_todays_bills(db, biz_id, customer_name=cust_filter)
            total_b = bills_info.get("total_bills", 0)
            total_rev = bills_info.get("total_revenue", 0.0)
            recent_b = bills_info.get("recent_bills", [])
            if total_b == 0:
                response_text = f"No bills found{' for ' + cust_filter if cust_filter else ''} today."
            else:
                if cust_filter:
                    b_list = [f"{b['bill_number']} (₹{b['total_amount']:.2f})" for b in recent_b[:5]]
                    response_text = f"Found {total_b} bill{'s' if total_b > 1 else ''} totaling ₹{total_rev:.2f}: {', '.join(b_list)}."
                else:
                    response_text = f"Aaj ki total sale ₹{total_rev:,.2f} hai ({total_b} bills se)."
            action_type = "business_query"

        elif tool_name == "control_relay":
            dev = str(args.get("device", "light")).lower().strip()
            raw_state = str(args.get("state", "on")).lower().strip()
            state = "on" if raw_state in ("on", "1", "true") else "off"
            if state == "on":
                response_text = f"Done, {dev} on kar di."
            else:
                response_text = f"Sure, {dev} band kar diya."
            action_type = "hardware_action"

        elif tool_name == "list_all_products":
            prods = InventoryService.list_all_products(db, biz_id, limit=20)
            summary = ", ".join([f"{p['name']} ({p['current_stock']:.1f} {p['unit']})" for p in prods[:5]])
            response_text = f"Inventory has {len(prods)} products: {summary}."
            action_type = "business_query"

        elif tool_name == "create_bill":
            raw_items = args.get("items", [])
            cust_name = args.get("customer_name")
            pay_method = args.get("payment_method", "CASH")
            try:
                bill_res = BillingService.create_bill(
                    db=db,
                    items_requested=raw_items,
                    customer_name=cust_name,
                    payment_method=pay_method,
                    business_id=biz_id,
                )
                response_text = f"Bill {bill_res['bill_number']} created for {bill_res['customer_name']}. Total: ₹{bill_res['total_amount']:.2f}."
                if args.get("send_whatsapp"):
                    bill_obj = db.query(Bill).filter(Bill.id == uuid.UUID(bill_res["bill_id"])).first()
                    wa_res = await WhatsAppService.send_invoice_via_whatsapp(bill=bill_obj, business=biz)
                    if wa_res.success:
                        response_text += " Sent to customer on WhatsApp!"
                    else:
                        response_text += f" WhatsApp error: {wa_res.error_message or 'Check phone number'}"
            except Exception as e:
                response_text = f"Failed to create bill: {str(e)}"
            action_type = "billing_action"

        elif tool_name == "send_whatsapp_bill":
            inv_id = args.get("invoice_id")
            phone_num = args.get("phone_number")
            bill_obj = db.query(Bill).order_by(Bill.created_at.desc()).first()
            if bill_obj:
                wa_res = await WhatsAppService.send_invoice_via_whatsapp(
                    bill=bill_obj,
                    business=biz,
                    recipient_phone=phone_num,
                )
                if wa_res.success:
                    response_text = f"Bill {bill_obj.bill_number} sent on WhatsApp!"
                else:
                    response_text = f"WhatsApp delivery failed: {wa_res.error_message}"
            else:
                response_text = "No bill found to send."
            action_type = "whatsapp_action"

        elif tool_name == "record_payment":
            amount = float(args.get("amount", 0.0))
            cust_name = args.get("customer_name")
            p_method = args.get("payment_method", "CASH")
            try:
                pay_res = BillingService.record_payment(
                    db=db,
                    customer_name=cust_name,
                    amount=amount,
                    payment_method=p_method,
                    notes=args.get("reference"),
                    business_id=biz_id,
                )
                business_data = pay_res
                action_type = "billing_action"
                c_name = pay_res["customer_name"]
                rem = pay_res["remaining_balance"]
                status_info = f" Bill {pay_res['bill_number']} status: {pay_res['bill_status']}." if pay_res.get("bill_number") else ""
                response_text = f"{c_name} se ₹{pay_res['amount_paid']:.2f} payment receive ho gaya ({pay_res['payment_method']}). Ab baki balance ₹{rem:.2f} hai.{status_info}"
            except Exception as pe:
                response_text = f"Payment record nahi ho paya: {str(pe)}"

        elif tool_name == "get_customer_ledger":
            cust_name = args.get("customer_name", "").strip()
            ledger_res = CustomerService.get_customer_ledger(
                db=db,
                customer_name=cust_name,
                business_id=biz_id,
            )
            business_data = ledger_res
            action_type = "business_query"
            response_text = ledger_res.get("summary") or f"{cust_name} ka ledger check kiya."

        elif tool_name == "create_task":
            desc = args.get("description", "").strip()
            cust_name = args.get("customer_name")
            task = TaskService.create_task(
                db=db,
                description=desc,
                customer_name=cust_name,
                business_id=biz_id,
            )
            business_data = {"task_id": str(task.id), "description": task.description}
            action_type = "task_action"
            response_text = f"Done. Task note kar liya hai: '{task.description}'."

        elif tool_name == "list_tasks":
            cust_name = args.get("customer_name")
            tasks = TaskService.list_tasks(
                db=db,
                business_id=biz_id,
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

        elif tool_name == "complete_task":
            kw = args.get("task_keyword", "").strip()
            comp_res = TaskService.complete_task(
                db=db,
                task_id_or_keyword=kw,
                business_id=biz_id,
            )
            business_data = comp_res
            action_type = "task_action"
            response_text = comp_res.get("message", "Task status updated.")

        elif tool_name == "save_ai_memory":
            content = args.get("content", "").strip()
            m_type = args.get("memory_type", "BUSINESS_PREFERENCE")
            mem = MemoryService.store_memory(
                db=db,
                business_id=biz_id,
                content=content,
                memory_type=m_type,
            )
            business_data = {"memory_id": str(mem.id), "content": mem.content}
            action_type = "memory_action"
            response_text = f"Theek hai, maine yaad rakh liya: '{content}'."

        elif tool_name == "modify_product_price":
            prod_name = args.get("product_name", "").strip()
            new_price = args.get("new_price", 0.0)
            token = req.auth_token

            if not SecurityService.is_token_authorized(token, biz_id):
                response_text = (
                    "Security Verification Required: Changing product price is a high-risk action. "
                    "Please verify your 6-digit owner PIN in the Security tab or pass a valid auth token."
                )
                action_type = "security_required"
            else:
                prod = InventoryService.search_product(db, prod_name, biz_id)
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
            response_text = f"Executed {tool_name} successfully."
            action_type = "tool_execution"

    else:
        response_text = gemini_res.text or "I am ready. How can I help your store today?"

    duration = round((time.perf_counter() - t_start) * 1000, 2)
    import urllib.parse
    clean_audio_text = re.sub(r"[^\w\s\.,\?!₹\-']", "", response_text).strip()
    audio_url = f"/api/v1/voice/audio/tts?text={urllib.parse.quote(clean_audio_text or response_text)}&lang=hi"
    return {
        "response_text": response_text,
        "rule_saved": False,
        "tool_invoked": tool_name,
        "action_type": action_type,
        "business_data": business_data,
        "audio_url": audio_url,
        "latencies": {"total_ms": duration},
    }


@router.post("/inventory/clear")
def clear_inventory(db: Session = Depends(get_db)):
    """Clear all products from inventory so store can start fresh with clean varieties."""
    res = InventoryService.clear_all_inventory(db=db)
    return res

