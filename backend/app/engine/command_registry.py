"""Centralized Command Registry for deterministic Robot V1 conversation engine."""

import enum
from typing import Any, Callable, Dict, List, Optional, Set
from pydantic import BaseModel


class CommandMode(str, enum.Enum):
    FAST = "FAST"
    BACKGROUND = "BACKGROUND"
    CONFIRMATION_REQUIRED = "CONFIRMATION_REQUIRED"


class CommandPriority(int, enum.Enum):
    CRITICAL = 1  # Stop, emergency, barge-in
    HIGH = 2      # Stock queries, current user question
    NORMAL = 3    # General reports, status
    LOW = 4       # Background strategy generation


class CommandDefinition(BaseModel):
    """Declarative specification for a recognized business or operational command."""
    intent: str
    description: str
    mode: CommandMode = CommandMode.FAST
    priority: CommandPriority = CommandPriority.HIGH
    keywords: List[str] = []
    regex_patterns: List[str] = []
    required_entities: List[str] = []
    optional_entities: List[str] = []
    destructive: bool = False
    requires_confirmation: bool = False
    permission_level: str = "ALL"  # "ALL", "STAFF", "OWNER"


# Master Registry of Commands
COMMAND_REGISTRY: Dict[str, CommandDefinition] = {
    # 1. Immediate Critical Commands
    "BARGE_IN": CommandDefinition(
        intent="BARGE_IN",
        description="Stop current speech playback immediately upon user interrupt",
        mode=CommandMode.FAST,
        priority=CommandPriority.CRITICAL,
        keywords=["ruko", "chup", "stop", "shant", "tham", "wait", "hold on", "pause"],
        regex_patterns=[r"^(ruko|stop|chup|shant|tham|bas|arre ruko|wait)[\s!.]*$"],
    ),
    "STOP_TASK": CommandDefinition(
        intent="STOP_TASK",
        description="Cancel or terminate an ongoing background operation",
        mode=CommandMode.FAST,
        priority=CommandPriority.CRITICAL,
        keywords=["task cancel karo", "task roko", "cancel task", "stop task", "band karo task"],
        regex_patterns=[r"\b(cancel|stop|roko|abort|terminate)\b.*\b(task|job|strategy|report)\b"],
    ),

    # 2. Inventory & Stock (Fast Mode)
    "GET_STOCK": CommandDefinition(
        intent="GET_STOCK",
        description="Query available stock quantity of a product",
        mode=CommandMode.FAST,
        priority=CommandPriority.HIGH,
        keywords=["stock", "kitna hai", "kitne hai", "baki hai", "available", "pada hai", "how many", "quantity"],
        regex_patterns=[
            r"([a-zA-Z0-9\s]+?)\s+(?:ka\s+)?stock\s+(?:kitna|check)",
            r"([a-zA-Z0-9\s]+?)\s+kitna\s+(?:hai|pada|available|bacha)",
            r"how\s+much\s+(?:stock\s+of\s+)?([a-zA-Z0-9\s]+)",
        ],
        required_entities=["product"],
    ),
    "REDUCE_STOCK": CommandDefinition(
        intent="REDUCE_STOCK",
        description="Deduct or record sale of product stock",
        mode=CommandMode.FAST,
        priority=CommandPriority.HIGH,
        keywords=["bech diye", "bech diya", "sold", "nikal", "kam kar", "reduce stock", "becha"],
        regex_patterns=[
            r"\b(bech diye|bech diya|sold|nikal liye|kam kar do|kam karo|becha)\b",
            r"(?:usme se\s+)?(\d+(?:\.\d+)?)\s+(?:bech|sold)",
        ],
        required_entities=["quantity"],
    ),
    "GET_PRICE": CommandDefinition(
        intent="GET_PRICE",
        description="Query selling price or rate of a product",
        mode=CommandMode.FAST,
        priority=CommandPriority.HIGH,
        keywords=["rate", "price", "bhaav", "kimat", "kitne ka hai", "how much is", "cost"],
        regex_patterns=[
            r"([a-zA-Z0-9\s]+?)\s+(?:ka\s+)?(?:rate|price|kimat|bhaav)",
            r"([a-zA-Z0-9\s]+?)\s+kitne\s+ka\s+hai",
            r"price\s+of\s+([a-zA-Z0-9\s]+)",
        ],
        required_entities=["product"],
    ),
    "GET_LOW_STOCK": CommandDefinition(
        intent="GET_LOW_STOCK",
        description="List products below minimum reorder threshold",
        mode=CommandMode.FAST,
        priority=CommandPriority.HIGH,
        keywords=["low stock", "kam stock", "khatam", "reorder", "shortage", "khatam hone wala"],
        regex_patterns=[r"\b(low stock|kam stock|khatam|reorder|shortage)\b"],
    ),
    "GET_INVENTORY": CommandDefinition(
        intent="GET_INVENTORY",
        description="Overview of all inventory products and quantities",
        mode=CommandMode.FAST,
        priority=CommandPriority.NORMAL,
        keywords=["all stock", "sagle stock", "pura inventory", "all products", "list products", "list stock", "dukan ka saman"],
        regex_patterns=[r"\b(all stock|sagle product|pura inventory|list inventory|all items)\b"],
    ),
    "GET_PRODUCT_DETAILS": CommandDefinition(
        intent="GET_PRODUCT_DETAILS",
        description="Get full product specifications and pricing",
        mode=CommandMode.FAST,
        priority=CommandPriority.NORMAL,
        keywords=["details", "detail", "mahit", "specification"],
        required_entities=["product"],
    ),

    # 3. Customer & Ledger (Fast Mode)
    "GET_CUSTOMER_BALANCE": CommandDefinition(
        intent="GET_CUSTOMER_BALANCE",
        description="Check outstanding credit balance owed by a customer",
        mode=CommandMode.FAST,
        priority=CommandPriority.HIGH,
        keywords=["baki", "balance", "udhari", "hisab", "kitna paisa", "credit", "due", "owe"],
        regex_patterns=[
            r"([a-zA-Z\s]+?)\s+(?:ka\s+)?(?:kitna\s+baki|balance|udhari|hisaab)",
            r"how\s+much\s+(?:does\s+)?([a-zA-Z\s]+)\s+owe",
        ],
        required_entities=["customer"],
    ),
    "GET_PENDING_PAYMENTS": CommandDefinition(
        intent="GET_PENDING_PAYMENTS",
        description="List all customers with outstanding due balances",
        mode=CommandMode.FAST,
        priority=CommandPriority.HIGH,
        keywords=["pending payment", "pending balance", "udhari list", "kiska baki hai", "sabka baki"],
        regex_patterns=[r"\b(pending payment|udhari list|sabka baki|kiska baki|pending dues)\b"],
    ),
    "GET_CUSTOMER_HISTORY": CommandDefinition(
        intent="GET_CUSTOMER_HISTORY",
        description="Retrieve recent bills and payments history of a customer",
        mode=CommandMode.FAST,
        priority=CommandPriority.NORMAL,
        keywords=["history", "purana hisab", "ledger", "khata", "statement"],
        required_entities=["customer"],
    ),

    # 4. Sales & Bills (Fast Mode)
    "GET_TODAY_SALES": CommandDefinition(
        intent="GET_TODAY_SALES",
        description="Get today's total store sales revenue and count",
        mode=CommandMode.FAST,
        priority=CommandPriority.HIGH,
        keywords=["today sales", "aaj ki sale", "aaj kitna hua", "todays revenue", "total sales today", "aaj ka dhanda"],
        regex_patterns=[r"\b(aaj ki sale|today sales|aaj kitna hua|total sales today|aaj ka collection)\b"],
    ),
    "GET_TODAY_BILLS": CommandDefinition(
        intent="GET_TODAY_BILLS",
        description="List bills generated today",
        mode=CommandMode.FAST,
        priority=CommandPriority.NORMAL,
        keywords=["today bills", "aaj ke bill", "recent bills", "todays bills"],
        regex_patterns=[r"\b(aaj ke bill|today bills|todays bills)\b"],
    ),
    "GET_BILL": CommandDefinition(
        intent="GET_BILL",
        description="Lookup details of a specific invoice",
        mode=CommandMode.FAST,
        priority=CommandPriority.HIGH,
        keywords=["bill check", "invoice", "bill number", "rasid"],
        required_entities=["bill_number"],
    ),

    # 5. Financial & Destructive Business Actions (Confirmation Required)
    "CREATE_BILL": CommandDefinition(
        intent="CREATE_BILL",
        description="Generate a sales bill and deduct stock",
        mode=CommandMode.FAST,
        priority=CommandPriority.HIGH,
        keywords=["bill bana", "create bill", "invoice bana", "bill create", "bill banao"],
        required_entities=["items"],
        destructive=False,
    ),
    "UPDATE_PAYMENT": CommandDefinition(
        intent="UPDATE_PAYMENT",
        description="Record a customer payment received",
        mode=CommandMode.CONFIRMATION_REQUIRED,
        priority=CommandPriority.HIGH,
        keywords=["jama kar", "payment kar", "paise diye", "payment mila", "record payment", "jama hue"],
        required_entities=["customer", "amount"],
        destructive=False,
        requires_confirmation=False,  # Under 5,000 runs fast, large payments confirm
    ),

    # 6. Background Jobs & Analytics (Background Mode)
    "CREATE_WEEKLY_STRATEGY": CommandDefinition(
        intent="CREATE_WEEKLY_STRATEGY",
        description="Analyze inventory, sales, and debt to generate a deterministic weekly action strategy",
        mode=CommandMode.BACKGROUND,
        priority=CommandPriority.LOW,
        keywords=["strategy bana", "business plan", "growth strategy", "week ki strategy", "strategy", "hisaab strategy"],
        regex_patterns=[r"\b(strategy|business plan|weekly plan|grow karne ki strategy)\b"],
    ),
    "GENERATE_SALES_REPORT": CommandDefinition(
        intent="GENERATE_SALES_REPORT",
        description="Compile comprehensive sales trends and customer volume report",
        mode=CommandMode.BACKGROUND,
        priority=CommandPriority.LOW,
        keywords=["sales report", "bikri report", "monthly sales", "sales analysis"],
        regex_patterns=[r"\b(sales report|bikri report|sales analysis)\b"],
    ),
    "GENERATE_INVENTORY_REPORT": CommandDefinition(
        intent="GENERATE_INVENTORY_REPORT",
        description="Compile comprehensive stock turnover, valuation, and reorder report",
        mode=CommandMode.BACKGROUND,
        priority=CommandPriority.LOW,
        keywords=["inventory report", "stock report", "stock analysis"],
        regex_patterns=[r"\b(inventory report|stock report|stock analysis)\b"],
    ),
    "TASK_STATUS": CommandDefinition(
        intent="TASK_STATUS",
        description="Check status or progress of an active background task",
        mode=CommandMode.FAST,
        priority=CommandPriority.HIGH,
        keywords=["task status", "kya kar rahe ho", "kaam kitna hua", "progress", "task kahan tak pahuncha"],
        regex_patterns=[r"\b(kya kar rahe ho|task status|progress|kaam kitna hua)\b"],
    ),
    "GET_COMPLETED_TASK": CommandDefinition(
        intent="GET_COMPLETED_TASK",
        description="Retrieve results of a previously completed background job",
        mode=CommandMode.FAST,
        priority=CommandPriority.HIGH,
        keywords=["kal wali strategy", "last strategy", "purani strategy", "last report", "kal ka report", "jo kaam kal hua"],
        regex_patterns=[r"\b(kal wali strategy|last strategy|purani strategy|last report|kal ka report|pehle wali)\b"],
    ),

    # 7. Hardware Controls (Fast Mode)
    "CONTROL_RELAY": CommandDefinition(
        intent="CONTROL_RELAY",
        description="Switch physical shop appliance relays on or off",
        mode=CommandMode.FAST,
        priority=CommandPriority.HIGH,
        keywords=["light", "fan", "socket", "relay", "pankha", "chalu kar", "band kar", "turn on", "turn off"],
        regex_patterns=[
            r"\b(light|fan|pankha|socket|relay\s*[1-4])\b.*\b(on|off|chalu|band)\b",
            r"\b(on|off|chalu|band)\b.*\b(light|fan|pankha|socket|relay\s*[1-4])\b",
        ],
        required_entities=["device", "state"],
    ),

    # 8. Conversational & Status (Fast Mode)
    "GREETING": CommandDefinition(
        intent="GREETING",
        description="Polite social greeting",
        mode=CommandMode.FAST,
        priority=CommandPriority.HIGH,
        keywords=["hello", "hi", "hey", "namaste", "namaskar", "pranam", "ram ram"],
        regex_patterns=[r"^(hello|hi|hey|namaste|namaskar|pranam|ram ram)[\s!.]*$"],
    ),
    "HOW_ARE_YOU": CommandDefinition(
        intent="HOW_ARE_YOU",
        description="Social wellbeing query",
        mode=CommandMode.FAST,
        priority=CommandPriority.HIGH,
        keywords=["kaise ho", "how are you", "kasa ahes", "kya haal hai", "kya haal"],
        regex_patterns=[r"^(kaise ho|how are you|kasa ahes|kya haal|kya haal hai)[\s!?.]*$"],
    ),
    "BOT_STATUS": CommandDefinition(
        intent="BOT_STATUS",
        description="Identity and operational readiness",
        mode=CommandMode.FAST,
        priority=CommandPriority.HIGH,
        keywords=["tum kaun ho", "who are you", "ready ho", "are you online"],
        regex_patterns=[r"^(tum kaun ho|who are you|tu kon ahes|ready ho|are you online)[\s!?.]*$"],
    ),
    "AFFIRMATION": CommandDefinition(
        intent="AFFIRMATION",
        description="User confirmation",
        mode=CommandMode.FAST,
        priority=CommandPriority.HIGH,
        keywords=["haan", "ha", "yes", "theek hai", "batao", "dikhao", "sure", "karo", "do it"],
        regex_patterns=[r"^(haan|ha|yes|theek hai|batao|dikhao|sure|karo|do it|ok)[\s!.]*$"],
    ),
    "NEGATION": CommandDefinition(
        intent="NEGATION",
        description="User rejection or cancellation",
        mode=CommandMode.FAST,
        priority=CommandPriority.HIGH,
        keywords=["nahi", "no", "mat karo", "cancel", "rahne do", "nako"],
        regex_patterns=[r"^(nahi|no|mat karo|cancel|rahne do|nako|stop)[\s!.]*$"],
    ),
    "HELP": CommandDefinition(
        intent="HELP",
        description="Provide usage instructions and available features",
        mode=CommandMode.FAST,
        priority=CommandPriority.NORMAL,
        keywords=["help", "madad", "kya kar sakte ho", "features", "options"],
        regex_patterns=[r"\b(help|madad|kya kar sakte ho|commands)\b"],
    ),
}
