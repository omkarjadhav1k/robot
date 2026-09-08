"""
Hybrid AI Engine: Tier 1 Deterministic Fast-Path (<20ms) + Tier 2 Gemini Thinking Brain.

Tier 1: Handles instant exact stock queries ("Tata Salt kitna hai?"), hardware relays ("Light on"),
barge-in ("Ruko"), and background tasks ("Is week ki strategy bana.") with zero latency.

Tier 2: For casual phrasing, voice typos ("stocl", "genrate"), mixed Marathi/Hindi/Hinglish,
incomplete requests ("bill"), or high-impact actions ("shop clean kar raha hu stock delete kardo"),
engages Gemini Thinking Engine to reason, understand true human intent, ask friendly questions to proceed,
require confirmation for destructive changes, and execute authoritative PostgreSQL tools.
"""

from decimal import Decimal
import logging
import time
from typing import Any, Dict, List, Optional
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.ai.gemini_service import reason_with_gemini, GeminiResult
from app.engine.response_templates import ResponseTemplates
from app.services.billing_service import BillingService
from app.services.brain_service import BrainService
from app.services.customer_service import CustomerService
from app.services.inventory_service import InventoryService
from app.services.memory_service import MemoryService
from app.services.robot_service import RobotService
from app.services.task_service import TaskService

logger = logging.getLogger("robot.engine.hybrid")


class HybridResult(BaseModel):
    success: bool = True
    response_text: str
    action_type: str = "conversation"
    data: Optional[Dict[str, Any]] = None
    command_dispatched: Optional[Dict[str, Any]] = None
    tool_invoked: Optional[str] = None
    tier: str = "TIER_2_GEMINI"
    latency_ms: float = 0.0


class HybridEngine:
    """Dispatches reasoning to Gemini and executes authoritative PostgreSQL tools."""

    @classmethod
    async def reason_and_execute(
        cls,
        user_text: str,
        db: Session,
        business_id: Optional[Any] = None,
        robot_id: str = "ROBOT-001",
        history: Optional[List[Dict[str, str]]] = None,
        custom_rules: Optional[List[str]] = None,
    ) -> HybridResult:
        t0 = time.perf_counter()

        # Pull dynamic store rules and AI memories if not explicitly passed
        active_rules = custom_rules
        if active_rules is None:
            active_rules = BrainService.get_instruction_strings(db, business_id)
            relevant_mems = MemoryService.get_relevant_memories(db, business_id, query_text=user_text)
            if relevant_mems:
                active_rules = list(active_rules) + [f"AI Memory Context: {m}" for m in relevant_mems]

        gemini_res = await reason_with_gemini(
            user_text=user_text,
            history=history,
            custom_instructions=active_rules,
        )

        elapsed = round((time.perf_counter() - t0) * 1000, 2)
        response_text = ""
        action_type = "conversation"
        business_data = None
        cmd_dispatched = None
        tool_name = None

        if gemini_res.function_call:
            tool_name = gemini_res.function_call.get("name")
            args = gemini_res.function_call.get("args", {})
            logger.info("Hybrid Engine executing tool: %s (%s)", tool_name, args)

            # 1. Clear / Reset Inventory
            if tool_name == "clear_or_reset_inventory":
                is_confirmed = bool(args.get("confirm", False))
                if is_confirmed:
                    res = InventoryService.clear_all_inventory(db, business_id=business_id)
                    response_text = res["message"]
                    business_data = res
                    action_type = "inventory_action"
                else:
                    response_text = "Dukan ka sara stock delete karna bada action hai. Kya aap sach mein confirm karte hain? Haan bolenge toh main proceed karunga."
                    action_type = "confirmation_required"

            # 2. Check Stock
            elif tool_name in ("check_stock", "get_stock"):
                p_name = str(args.get("product_name", "")).strip()
                if not p_name or p_name.lower() in ("all", "all items", "sagle", "sab", "stock", "saman", "everything"):
                    prods = InventoryService.list_all_products(db, business_id, limit=20)
                    summary = ", ".join([f"{p['name']} ({p['current_stock']:.1f} {p['unit']})" for p in prods[:5]])
                    more = f" aur {len(prods)-5} products" if len(prods) > 5 else ""
                    response_text = f"Dukan mein {len(prods)} products available hain: {summary}{more}."
                    business_data = {"products": prods}
                else:
                    stock_info = InventoryService.get_stock(db, p_name, business_id)
                    business_data = stock_info
                    if stock_info.get("found"):
                        stk = stock_info["current_stock"]
                        stk_str = str(int(stk)) if stk % 1 == 0 else f"{stk:.1f}"
                        price = stock_info.get("selling_price", 0.0)
                        if any(w in user_text.lower() for w in ["rate", "price", "bhaav", "kimat", "kitne ka"]):
                            response_text = f"{stock_info['name']} ka rate ₹{price:.2f} per {stock_info['unit']} hai, aur abhi {stk_str} {stock_info['unit']} available hain."
                        else:
                            response_text = f"{stock_info['name']} ke {stk_str} {stock_info['unit']} available hain."
                    else:
                        response_text = f"Mujhe '{p_name}' naam ka product inventory mein nahi mila."
                action_type = "business_query"

            # 3. Reduce Stock
            elif tool_name == "reduce_stock":
                p_name = str(args.get("product_name", "")).strip()
                try:
                    qty = float(args.get("quantity", 1.0))
                except Exception:
                    qty = 1.0
                res = InventoryService.reduce_or_sell_stock(db=db, product_name=p_name, quantity=qty, business_id=business_id)
                response_text = res["message"]
                business_data = res
                action_type = "business_query"

            # 4. Add Stock
            elif tool_name == "add_stock":
                p_name = str(args.get("product_name", "")).strip()
                try:
                    qty = float(args.get("quantity", 1.0))
                except Exception:
                    qty = 1.0
                res = InventoryService.add_or_restock_product(db=db, product_name=p_name, quantity=qty, unit=args.get("unit"), business_id=business_id)
                response_text = res["message"]
                business_data = res
                action_type = "business_query"

            # 5. Create Bill
            elif tool_name == "create_bill":
                raw_items = args.get("items", [])
                cust_name = args.get("customer_name")
                pay_method = args.get("payment_method", "CASH")
                if not raw_items:
                    response_text = "Bilkul! Kiska bill banana hai aur kaunse items add karne hain? Customer ka naam aur items bataiye."
                    action_type = "conversation"
                else:
                    try:
                        bill_res = BillingService.create_bill(
                            db=db,
                            items_requested=raw_items,
                            customer_name=cust_name,
                            payment_method=pay_method,
                            business_id=business_id,
                        )
                        response_text = f"Bill {bill_res['bill_number']} create ho gaya. Total: ₹{bill_res['total_amount']:.2f}."
                        business_data = bill_res
                        action_type = "billing_action"
                    except Exception as e:
                        response_text = f"Bill create nahi ho paya: {str(e)}"
                        action_type = "error"

            # 6. Record Payment
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
                        business_id=business_id,
                    )
                    business_data = pay_res
                    rem = pay_res["remaining_balance"]
                    response_text = f"{pay_res['customer_name']} se ₹{pay_res['amount_paid']:.2f} receive ho gaye. Baki balance ₹{rem:.2f} hai."
                    action_type = "billing_action"
                except Exception as pe:
                    response_text = f"Payment record nahi ho paya: {str(pe)}"
                    action_type = "error"

            # 7. Customer Ledger
            elif tool_name == "get_customer_ledger":
                cust_name = str(args.get("customer_name", "")).strip()
                ledger_res = CustomerService.get_customer_ledger(db=db, customer_name=cust_name, business_id=business_id)
                business_data = ledger_res
                response_text = ledger_res.get("summary") or f"{cust_name} ka hisaab check kiya."
                action_type = "business_query"

            # 8. Sales Today
            elif tool_name in ("get_sales_today", "get_todays_bills"):
                cust_filter = args.get("customer_name")
                bills_info = BillingService.get_todays_bills(db, business_id, customer_name=cust_filter)
                total_b = bills_info.get("total_bills", 0)
                total_rev = bills_info.get("total_revenue", 0.0)
                response_text = f"Aaj ki total sale ₹{total_rev:,.2f} hai ({total_b} bills se)."
                business_data = bills_info
                action_type = "business_query"

            # 9. List All Products
            elif tool_name == "list_all_products":
                prods = InventoryService.list_all_products(db, business_id, limit=20)
                summary = ", ".join([f"{p['name']} ({p['current_stock']:.1f} {p['unit']})" for p in prods[:5]])
                response_text = f"Dukan mein {len(prods)} products hain: {summary}."
                business_data = {"products": prods}
                action_type = "business_query"

            # 10. Low Stock Items
            elif tool_name == "get_low_stock_items":
                low_items = InventoryService.get_low_stock_items(db, business_id)
                business_data = {"items": low_items}
                if low_items:
                    summary = ", ".join([f"{i['name']} ({i['current_stock']:.1f} {i['unit']})" for i in low_items[:5]])
                    response_text = f"{len(low_items)} items low stock par hain: {summary}."
                else:
                    response_text = "Koi bhi product low stock par nahi hai. Sabhi items sufficiently stocked hain."
                action_type = "business_query"

            # 11. Hardware Relay Control
            elif tool_name == "control_relay":
                ch = int(args.get("relay_number") or 1)
                st = str(args.get("state", "on")).lower()
                dev = args.get("device") or f"Relay {ch}"
                db_cmd = RobotService.queue_command(
                    db=db,
                    robot_id=robot_id,
                    action="set_relay",
                    params={"relay": ch, "state": st},
                    business_id=business_id,
                )
                cmd_dispatched = {
                    "command_id": db_cmd.command_id,
                    "action": "set_relay",
                    "params": {"relay": ch, "state": st},
                }
                response_text = ResponseTemplates.format_relay_response(dev, st)
                action_type = "hardware_action"

            # 12. Create Task
            elif tool_name == "create_task":
                desc = str(args.get("description", "")).strip()
                t = TaskService.create_task(db=db, description=desc, customer_name=args.get("customer_name"), business_id=business_id)
                response_text = f"Done. Task note kar liya: '{t.description}'."
                business_data = {"task_id": str(t.id), "description": t.description}
                action_type = "task_action"

            # 13. List Tasks
            elif tool_name == "list_tasks":
                tasks = TaskService.list_tasks(db=db, business_id=business_id, customer_name=args.get("customer_name"))
                if tasks:
                    t_list = [t["description"] for t in tasks[:3]]
                    response_text = f"{len(tasks)} pending tasks hain: {'; '.join(t_list)}."
                else:
                    response_text = "Koi pending task nahi hai."
                business_data = {"tasks": tasks}
                action_type = "task_action"

            else:
                response_text = gemini_res.text or "Samajh gaya."

        else:
            # Gemini returned natural language text response (e.g. asking clarifying questions or conversational chat)
            response_text = gemini_res.text or "Samajh gaya. Aage kya karna hai?"
            action_type = "conversation"

        return HybridResult(
            success=gemini_res.is_success,
            response_text=response_text,
            action_type=action_type,
            data=business_data,
            command_dispatched=cmd_dispatched,
            tool_invoked=tool_name,
            tier="TIER_2_GEMINI",
            latency_ms=elapsed,
        )