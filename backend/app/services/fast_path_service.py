"""Fast-Path execution engine for sub-50ms greetings, relays, and direct database queries."""

import logging
import re
import uuid
from typing import Any, Dict, Optional
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.schemas.robot import RobotCommand
from app.services.customer_service import CustomerService
from app.services.inventory_service import InventoryService
from app.services.robot_service import RobotService

logger = logging.getLogger("max.fast_path")


class FastPathResult(BaseModel):
    matched: bool = False
    response_text: str = ""
    action_type: str = "conversation"
    command_dispatched: Optional[RobotCommand] = None
    business_data: Optional[Dict[str, Any]] = None


class FastPathService:
    """Evaluates user text against lightweight pattern matchers to bypass cloud LLMs."""

    # 1. Common Greetings Patterns
    GREETING_PATTERNS = [
        r"^(hello|hi|hey|namaste|namaskar|pranam)[\s!.]*$",
        r"^(hello|hi|hey)\s+max[\s!.]*$",
        r"^(kaise ho|how are you|kasa ahes|kasi ahes|kya haal|kya haal hai)[\s!?.]*$",
        r"^(tum kaun ho|who are you|tu kon ahes|what is your name)[\s!?.]*$",
    ]

    # 2. Appliance Relay Patterns
    RELAY_PATTERNS = [
        # Light
        (r"\b(light|batti|tubelight)\b.*\b(on|chalu|jalado|start|lagao)\b", 1, "on"),
        (r"\b(light|batti|tubelight)\b.*\b(off|band|bujhao|stop)\b", 1, "off"),
        (r"\b(on|chalu)\b.*\b(light|batti)\b", 1, "on"),
        (r"\b(off|band)\b.*\b(light|batti)\b", 1, "off"),
        # Fan
        (r"\b(fan|pankha)\b.*\b(on|chalu|start|lagao)\b", 2, "on"),
        (r"\b(fan|pankha)\b.*\b(off|band|stop)\b", 2, "off"),
        (r"\b(on|chalu)\b.*\b(fan|pankha)\b", 2, "on"),
        (r"\b(off|band)\b.*\b(fan|pankha)\b", 2, "off"),
        # Socket
        (r"\b(socket|plug|charger)\b.*\b(on|chalu|start)\b", 3, "on"),
        (r"\b(socket|plug|charger)\b.*\b(off|band|stop)\b", 3, "off"),
        # Aux / Relay 4
        (r"\b(aux|motor|pump|ac)\b.*\b(on|chalu)\b", 4, "on"),
        (r"\b(aux|motor|pump|ac)\b.*\b(off|band)\b", 4, "off"),
        # Direct Relay number
        (r"\b(turn on|switch on|start)\b.*\brelay\s*([1-4])\b", None, "on"),
        (r"\b(turn off|switch off|stop|band)\b.*\brelay\s*([1-4])\b", None, "off"),
        (r"\brelay\s*([1-4])\b.*\b(on|chalu)\b", None, "on"),
        (r"\brelay\s*([1-4])\b.*\b(off|band)\b", None, "off"),
    ]

    # 3. Simple Direct Stock Query Patterns
    STOCK_PATTERNS = [
        r"^(?:max\s+)?(?:check\s+)?([a-zA-Z0-9\s]+?)\s+(?:ka\s+)?stock\s+(?:kitna|check).*$",
        r"^(?:max\s+)?([a-zA-Z0-9\s]+?)\s+kitna\s+(?:hai|pada\s+hai|available\s+hai|bacha\s+hai).*$",
        r"^(?:how\s+much\s+stock\s+do\s+we\s+have\s+of\s+)([a-zA-Z0-9\s]+).*$",
    ]

    # 4. Simple Customer Balance Patterns
    BALANCE_PATTERNS = [
        r"^(?:max\s+)?([a-zA-Z\s]+?)\s+(?:ka\s+)?(?:kitna\s+baki\s+hai|balance\s+kitna\s+hai|udhari\s+kitni\s+hai|ka\s+hisab|hisab\s+kitna\s+hai)[\s!?.]*$",
        r"^(?:max\s+)?(?:check\s+)?([a-zA-Z\s]+?)\s+balance[\s!?.]*$",
        r"^(?:how\s+much\s+does\s+)([a-zA-Z\s]+)\s+owe[\s!?.]*$",
    ]

    @classmethod
    def evaluate(
        cls,
        db: Session,
        text: str,
        robot_id: str,
        business_id: uuid.UUID,
    ) -> FastPathResult:
        """Execute fast-path rules before hitting Gemini. Sub-50ms target."""
        clean = text.strip()
        lower = clean.lower()

        # A. Greetings Fast-Path
        for pat in cls.GREETING_PATTERNS:
            if re.search(pat, lower):
                if any(k in lower for k in ["kaise ho", "how are you", "kasa ahes", "kya haal"]):
                    reply = "Main bilkul badhiya hoon! Aap bataiye, MAX aapki kya madad kar sakta hai?"
                elif any(k in lower for k in ["kaun ho", "who are you", "tu kon", "name"]):
                    reply = "Main MAX hoon — Manager AI eXecutive. Aapke store ka inventory, billing aur appliances handle karta hoon."
                else:
                    reply = "Namaste! Main MAX hoon. Bataiye aaj kya kaam hai?"
                return FastPathResult(matched=True, response_text=reply, action_type="conversation")

        # B. Relay Commands Fast-Path
        for pat, default_channel, state in cls.RELAY_PATTERNS:
            m = re.search(pat, lower)
            if m:
                channel = default_channel
                if channel is None:
                    # Extracted from regex group
                    for g in m.groups():
                        if g and g.isdigit():
                            channel = int(g)
                            break
                if channel and 1 <= channel <= 4:
                    db_cmd = RobotService.queue_command(
                        db=db,
                        robot_id=robot_id,
                        action="set_relay",
                        params={"relay": channel, "state": state},
                        business_id=business_id,
                    )
                    cmd_schema = RobotCommand(
                        command_id=db_cmd.command_id,
                        robot_id=robot_id,
                        action=db_cmd.action,
                        params=db_cmd.payload or {},
                        status="pending",
                    )
                    # Natural Manager replies
                    if "relay" in lower:
                        reply = f"Relay {channel} has been switched {state}."
                    else:
                        device_names = {1: "Light", 2: "Fan", 3: "Socket", 4: "Aux device"}
                        dev_name = device_names.get(channel, f"Relay {channel}")
                        action_word = "on kar di" if state == "on" else "band kar diya"
                        reply = f"Done. {dev_name} {action_word}."

                    return FastPathResult(
                        matched=True,
                        response_text=reply,
                        action_type="hardware_action",
                        command_dispatched=cmd_schema,
                    )

        # C. Simple Direct Stock Lookup Fast-Path
        for pat in cls.STOCK_PATTERNS:
            m = re.match(pat, lower)
            if m:
                raw_prod = m.group(1).strip()
                # Exclude broad conversational phrases
                if raw_prod and len(raw_prod) > 2 and raw_prod not in ["aaj", "kya", "bhai", "hello", "sale", "bill"]:
                    stock_res = InventoryService.get_stock(db, raw_prod, business_id)
                    if stock_res.get("found"):
                        stk = stock_res["current_stock"]
                        stk_str = str(int(stk)) if stk % 1 == 0 else f"{stk:.1f}"
                        reply = f"{stock_res['name']} ke {stk_str} {stock_res['unit']} available hain."
                        return FastPathResult(
                            matched=True,
                            response_text=reply,
                            action_type="business_query",
                            business_data=stock_res,
                        )

        # D. Simple Customer Balance Lookup Fast-Path
        for pat in cls.BALANCE_PATTERNS:
            m = re.match(pat, lower)
            if m:
                raw_cust = m.group(1).strip()
                if raw_cust and len(raw_cust) > 2 and raw_cust not in ["aaj", "kya", "bhai", "hello", "sale", "bill"]:
                    bal_res = CustomerService.get_customer_balance(db, raw_cust, business_id)
                    if bal_res.get("found"):
                        bal = bal_res["outstanding_balance"]
                        if bal > 0:
                            reply = f"{bal_res['name']} ka ₹{bal:.2f} baki hai."
                        else:
                            reply = f"{bal_res['name']} ka koi baki nahi hai, balance clear hai."
                        return FastPathResult(
                            matched=True,
                            response_text=reply,
                            action_type="business_query",
                            business_data=bal_res,
                        )

        return FastPathResult(matched=False)
