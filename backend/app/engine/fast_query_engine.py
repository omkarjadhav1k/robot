"""Fast Query Engine executing read-only and fast business operations with sub-300ms targets."""

import asyncio
from decimal import Decimal
import logging
import time
from typing import Any, Dict, Optional, Tuple
from sqlalchemy.orm import Session

from app.engine.entity_extractor import ExtractedEntities
from app.engine.response_templates import ResponseTemplates
from app.services.billing_service import BillingService
from app.services.customer_service import CustomerService
from app.services.inventory_service import InventoryService
from app.services.robot_service import RobotService

logger = logging.getLogger("robot.engine.fast_query")

# Threshold in milliseconds to distinguish immediate vs. slow query acknowledgement
SLOW_QUERY_THRESHOLD_MS = 600.0


class FastQueryResult:
    def __init__(
        self,
        success: bool,
        response_text: str,
        immediate_ack: Optional[str] = None,
        action_type: str = "business_query",
        data: Optional[Dict[str, Any]] = None,
        command_dispatched: Optional[Any] = None,
        latency_ms: float = 0.0,
    ):
        self.success = success
        self.response_text = response_text
        self.immediate_ack = immediate_ack
        self.action_type = action_type
        self.data = data or {}
        self.command_dispatched = command_dispatched
        self.latency_ms = latency_ms


class FastQueryEngine:
    """Executes fast, deterministic queries against PostgreSQL without an LLM."""

    @classmethod
    def execute(
        cls,
        intent: str,
        entities: ExtractedEntities,
        db: Session,
        business_id: Optional[Any] = None,
        robot_id: str = "ROBOT-001",
        simulate_slow: bool = False,
    ) -> FastQueryResult:
        """Execute query synchronously with latency tracking and slow-query fallback."""
        t0 = time.perf_counter()
        immediate_ack = None

        # Handle slow query behavior (Section 8)
        if simulate_slow:
            immediate_ack = ResponseTemplates.get("ACK_CHECK")

        # 1. GET_STOCK
        if intent == "GET_STOCK":
            if not entities.product:
                return FastQueryResult(
                    success=False,
                    response_text="Kripya product ka naam batayein jiska stock check karna hai.",
                    latency_ms=(time.perf_counter() - t0) * 1000,
                )

            stock_info = InventoryService.get_stock(db, entities.product, business_id=business_id)
            elapsed = (time.perf_counter() - t0) * 1000
            if stock_info.get("found"):
                reply = ResponseTemplates.format_stock_response(
                    product_name=stock_info["name"],
                    stock=stock_info["current_stock"],
                    unit=stock_info.get("unit", "packet"),
                    is_low=stock_info.get("is_low_stock", False),
                )
                if simulate_slow:
                    reply = f"Check kar liya. {reply}"
                return FastQueryResult(
                    success=True,
                    response_text=reply,
                    immediate_ack=immediate_ack,
                    data=stock_info,
                    latency_ms=elapsed,
                )
            else:
                return FastQueryResult(
                    success=False,
                    response_text=f"'{entities.product}' inventory mein nahi mila.",
                    immediate_ack=immediate_ack,
                    latency_ms=elapsed,
                )

        # 1b. REDUCE_STOCK
        elif intent == "REDUCE_STOCK":
            if not entities.product:
                return FastQueryResult(
                    success=False,
                    response_text="Kripya product ka naam batayein jiska stock kam karna hai.",
                    latency_ms=(time.perf_counter() - t0) * 1000,
                )
            qty = entities.quantity or 1.0
            res = InventoryService.reduce_or_sell_stock(
                db=db,
                product_name=entities.product,
                quantity=qty,
                business_id=business_id,
            )
            elapsed = (time.perf_counter() - t0) * 1000
            return FastQueryResult(
                success=True,
                response_text=res["message"],
                data=res,
                latency_ms=elapsed,
            )

        # 2. GET_PRICE
        elif intent == "GET_PRICE":
            if not entities.product:
                return FastQueryResult(
                    success=False,
                    response_text="Kripya product ka naam batayein jiska rate poochna hai.",
                    latency_ms=(time.perf_counter() - t0) * 1000,
                )
            stock_info = InventoryService.get_stock(db, entities.product, business_id=business_id)
            elapsed = (time.perf_counter() - t0) * 1000
            if stock_info.get("found"):
                price = stock_info.get("selling_price", 0.0)
                unit = stock_info.get("unit", "packet")
                reply = ResponseTemplates.format_price_response(stock_info["name"], price, unit)
                return FastQueryResult(success=True, response_text=reply, data=stock_info, latency_ms=elapsed)
            else:
                return FastQueryResult(
                    success=False,
                    response_text=f"'{entities.product}' ka price database mein nahi mila.",
                    latency_ms=elapsed,
                )

        # 3. GET_CUSTOMER_BALANCE
        elif intent == "GET_CUSTOMER_BALANCE":
            if not entities.customer:
                return FastQueryResult(
                    success=False,
                    response_text="Kripya customer ka naam batayein jinka hisaab dekhna hai.",
                    latency_ms=(time.perf_counter() - t0) * 1000,
                )
            bal_info = CustomerService.get_customer_balance(db, entities.customer, business_id=business_id)
            elapsed = (time.perf_counter() - t0) * 1000
            if bal_info.get("found"):
                reply = ResponseTemplates.format_balance_response(bal_info["name"], bal_info["outstanding_balance"])
                return FastQueryResult(success=True, response_text=reply, data=bal_info, latency_ms=elapsed)
            else:
                return FastQueryResult(
                    success=False,
                    response_text=f"Customer '{entities.customer}' records mein nahi mile.",
                    latency_ms=elapsed,
                )

        # 4. GET_TODAY_SALES
        elif intent == "GET_TODAY_SALES":
            bills_data = BillingService.get_todays_bills(db, business_id=business_id)
            elapsed = (time.perf_counter() - t0) * 1000
            total_b = bills_data.get("total_bills", 0)
            total_rev = bills_data.get("total_revenue", 0.0)
            reply = ResponseTemplates.format_today_sales(total_b, total_rev)
            return FastQueryResult(success=True, response_text=reply, data=bills_data, latency_ms=elapsed)

        # 5. GET_TODAY_BILLS
        elif intent == "GET_TODAY_BILLS":
            bills_data = BillingService.get_todays_bills(db, business_id=business_id)
            elapsed = (time.perf_counter() - t0) * 1000
            recent = bills_data.get("recent_bills", [])
            if not recent:
                reply = "Aaj abhi tak koi bill generate nahi hua hai."
            else:
                b_list = [f"{b['bill_number']} (₹{b['total_amount']:.2f})" for b in recent[:4]]
                reply = f"Aaj ke bills: {', '.join(b_list)}."
            return FastQueryResult(success=True, response_text=reply, data=bills_data, latency_ms=elapsed)

        # 6. GET_LOW_STOCK
        elif intent == "GET_LOW_STOCK":
            low_items = InventoryService.get_low_stock_items(db, business_id=business_id)
            elapsed = (time.perf_counter() - t0) * 1000
            if low_items:
                summary = ", ".join([f"{i['name']} ({i['current_stock']} {i['unit']})" for i in low_items[:4]])
                reply = f"Ye {len(low_items)} products low stock par hain: {summary}."
            else:
                reply = "Sabhi products minimum stock level se upar hain."
            return FastQueryResult(success=True, response_text=reply, data={"items": low_items}, latency_ms=elapsed)

        # 7. GET_INVENTORY
        elif intent == "GET_INVENTORY":
            products = InventoryService.list_all_products(db, business_id=business_id, limit=20)
            elapsed = (time.perf_counter() - t0) * 1000
            if products:
                summary = ", ".join([f"{p['name']} ({p['current_stock']:.1f} {p['unit']})" for p in products[:5]])
                more = f" aur {len(products)-5} products" if len(products) > 5 else ""
                reply = f"Dukan mein {len(products)} products hain: {summary}{more}."
            else:
                reply = "Dukan mein abhi koi products registered nahi hain."
            return FastQueryResult(success=True, response_text=reply, data={"products": products}, latency_ms=elapsed)

        # 8. GET_PENDING_PAYMENTS
        elif intent == "GET_PENDING_PAYMENTS":
            customers = CustomerService.list_all_customers(db, business_id=business_id)
            due_custs = [c for c in customers if c.get("outstanding_balance", 0) > 0]
            elapsed = (time.perf_counter() - t0) * 1000
            if due_custs:
                names = ", ".join([f"{c['name']} (₹{c['outstanding_balance']:.2f})" for c in due_custs[:4]])
                reply = f"{len(due_custs)} customers ka balance baki hai: {names}."
            else:
                reply = "Kisi bhi customer ka udhari balance pending nahi hai."
            return FastQueryResult(success=True, response_text=reply, data={"customers": due_custs}, latency_ms=elapsed)

        # 9. CONTROL_RELAY
        elif intent == "CONTROL_RELAY":
            ch = entities.relay_channel or 1
            st = entities.relay_state or "on"
            dev = entities.device or f"Relay {ch}"
            db_cmd = RobotService.queue_command(
                db=db,
                robot_id=robot_id,
                action="set_relay",
                params={"relay": ch, "state": st},
                business_id=business_id,
            )
            elapsed = (time.perf_counter() - t0) * 1000
            reply = ResponseTemplates.format_relay_response(dev, st)
            return FastQueryResult(
                success=True,
                response_text=reply,
                action_type="hardware_action",
                command_dispatched={
                    "command_id": db_cmd.command_id,
                    "action": "set_relay",
                    "params": {"relay": ch, "state": st},
                },
                latency_ms=elapsed,
            )

        # 10. Conversational Social Queries
        elif intent == "GREETING":
            return FastQueryResult(
                success=True,
                response_text=ResponseTemplates.get("GREETING"),
                action_type="conversation",
                latency_ms=(time.perf_counter() - t0) * 1000,
            )
        elif intent == "HOW_ARE_YOU":
            return FastQueryResult(
                success=True,
                response_text=ResponseTemplates.get("HOW_ARE_YOU"),
                action_type="conversation",
                latency_ms=(time.perf_counter() - t0) * 1000,
            )
        elif intent == "BOT_STATUS":
            return FastQueryResult(
                success=True,
                response_text=ResponseTemplates.get("BOT_STATUS"),
                action_type="conversation",
                latency_ms=(time.perf_counter() - t0) * 1000,
            )
        elif intent == "HELP":
            return FastQueryResult(
                success=True,
                response_text=ResponseTemplates.get("HELP"),
                action_type="conversation",
                latency_ms=(time.perf_counter() - t0) * 1000,
            )

        return FastQueryResult(
            success=False,
            response_text=ResponseTemplates.get("UNKNOWN"),
            latency_ms=(time.perf_counter() - t0) * 1000,
        )
