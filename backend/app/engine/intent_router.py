"""Deterministic Intent Router with multi-signal confidence scoring and clarification rules."""

import logging
import re
from typing import Dict, List, Optional, Tuple
from pydantic import BaseModel

from app.engine.command_registry import COMMAND_REGISTRY, CommandDefinition, CommandPriority
from app.engine.entity_extractor import ExtractedEntities

logger = logging.getLogger("robot.engine.intent")


class IntentMatch(BaseModel):
    intent: str
    confidence: float
    command_def: Optional[Dict] = None
    requires_clarification: bool = False
    clarification_message: Optional[str] = None
    is_unknown: bool = False


class IntentRouter:
    """Classifies user utterance into deterministic business commands without an LLM."""

    # High-confidence pattern triggers
    INTENT_TRIGGERS = [
        # 1. Emergency / Barge-In
        ("BARGE_IN", [r"^(ruko|stop|chup|shant|tham|bas|wait|arre ruko)[\s!.]*$"]),
        ("STOP_TASK", [r"\b(cancel|stop|roko|abort)\b.*\b(task|job|strategy|report)\b"]),

        # 2. Strategy & Background Jobs
        ("GET_COMPLETED_TASK", [
            r"\b(kal wali|last strategy|purani strategy|last report|kal ka report|pehle wali|purana task|old strategy)\b",
            r"(?:kal|last)\s+(?:jo\s+)?(?:strategy|report|kaam|task)",
        ]),
        ("TASK_STATUS", [r"\b(task status|progress|kya kar rahe ho|kaam kitna hua|status kya|kya status)\b"]),
        ("CREATE_WEEKLY_STRATEGY", [
            r"\b(strategy bana|nayi strategy|make strategy|create strategy|generate strategy|weekly plan|grow karne ki strategy|weekly strategy)\b",
            r"is\s+week\s+(?:ki\s+)?strategy",
            r"\bstrategy\b",
        ]),
        ("GENERATE_SALES_REPORT", [r"\b(sales report|bikri report|sales analysis)\b"]),
        ("GENERATE_INVENTORY_REPORT", [r"\b(inventory report|stock report|stock analysis)\b"]),

        # 3. Fast Inquiries
        ("GET_STOCK", [
            r"\b(stock|kitna hai|kitne hai|baki hai|available|pada hai|quantity)\b",
            r"how\s+much\s+(?:stock\s+of\s+)?",
        ]),
        ("REDUCE_STOCK", [
            r"\b(bech diye|bech diya|sold|nikal liye|kam kar do|kam karo|becha)\b",
            r"(?:usme se\s+)?(?:\d+(?:\.\d+)?)\s+(?:bech|sold)",
        ]),
        ("GET_PRICE", [
            r"\b(rate|price|kimat|bhaav|cost)\b",
            r"kitne\s+ka\s+hai",
        ]),
        ("GET_LOW_STOCK", [r"\b(low stock|kam stock|khatam|reorder|shortage)\b"]),
        ("GET_INVENTORY", [r"\b(all stock|sagle stock|pura inventory|list products|all products|dukan ka saman)\b"]),

        # 4. Customers & Ledgers
        ("GET_CUSTOMER_BALANCE", [
            r"\b(baki|balance|udhari|hisaab|hisab|kitna paisa|due|owe)\b",
            r"how\s+much\s+does\s+.*owe",
        ]),
        ("GET_PENDING_PAYMENTS", [r"\b(pending payment|udhari list|sabka baki|kiska baki|pending dues)\b"]),
        ("GET_CUSTOMER_HISTORY", [r"\b(history|purana hisab|ledger|khata|statement)\b"]),

        # 5. Sales & Bills
        ("GET_TODAY_SALES", [r"\b(aaj ki sale|today sales|aaj kitna hua|total sales today|aaj ka collection|aaj ka dhanda)\b"]),
        ("GET_TODAY_BILLS", [r"\b(aaj ke bill|today bills|todays bills)\b"]),
        ("CREATE_BILL", [r"\b(bill bana|create bill|invoice bana|bill create|bill banao)\b"]),
        ("UPDATE_PAYMENT", [r"\b(jama kar|payment kar|paise diye|payment mila|jama hue)\b"]),

        # 6. Hardware Relays
        ("CONTROL_RELAY", [
            r"\b(light|fan|pankha|socket|relay\s*[1-4])\b.*\b(on|off|chalu|band)\b",
            r"\b(on|off|chalu|band)\b.*\b(light|fan|pankha|socket|relay\s*[1-4])\b",
        ]),

        # 7. Conversational Status
        ("GREETING", [r"^(hello|hi|hey|namaste|namaskar|pranam|ram ram)[\s!.]*$"]),
        ("HOW_ARE_YOU", [r"^(kaise ho|how are you|kasa ahes|kya haal|kya haal hai)[\s!?.]*$"]),
        ("BOT_STATUS", [r"^(tum kaun ho|who are you|tu kon ahes|ready ho|are you online)[\s!?.]*$"]),
        ("AFFIRMATION", [r"^(haan|ha|yes|theek hai|batao|dikhao|sure|karo|do it|ok)[\s!.]*$"]),
        ("NEGATION", [r"^(nahi|no|mat karo|cancel|rahne do|nako|stop)[\s!.]*$"]),
        ("HELP", [r"\b(help|madad|kya kar sakte ho|features|commands)\b"]),
    ]

    @classmethod
    def classify(cls, text: str, entities: ExtractedEntities) -> IntentMatch:
        """
        Classify utterance and return structured match with confidence score.
        Confidence thresholds:
          >= 0.80 -> Direct execution
          0.50 - 0.79 -> Ask clarification
          < 0.50 -> Unknown command response
        """
        clean = text.lower().strip()

        # Step 0: Check product ambiguity (Section 21)
        if entities.is_ambiguous and len(entities.ambiguous_candidates) > 1:
            opts = ", ".join(entities.ambiguous_candidates)
            clarification = f"Kaunsi {entities.product}? {opts}?"
            return IntentMatch(
                intent="AMBIGUOUS_PRODUCT",
                confidence=0.75,
                requires_clarification=True,
                clarification_message=clarification,
            )

        # Step 1: Check Exact Trigger Regexes
        best_intent: Optional[str] = None
        best_score = 0.0

        for intent_name, patterns in cls.INTENT_TRIGGERS:
            for pat in patterns:
                if re.search(pat, clean):
                    # Base score for regex match
                    score = 0.85

                    # Boost score if required entities are present
                    cmd_def = COMMAND_REGISTRY.get(intent_name)
                    if cmd_def and cmd_def.required_entities:
                        if "product" in cmd_def.required_entities and (entities.product or entities.product_obj):
                            score += 0.10
                        if "customer" in cmd_def.required_entities and (entities.customer or entities.customer_obj):
                            score += 0.10
                        if "device" in cmd_def.required_entities and (entities.device or entities.relay_channel):
                            score += 0.10

                    if score > best_score:
                        best_score = min(1.0, score)
                        best_intent = intent_name

        # Step 2: Fallback to Keyword Intersection
        if not best_intent or best_score < 0.80:
            tokens = set(clean.split())
            for intent_name, cmd_def in COMMAND_REGISTRY.items():
                keyword_hits = 0
                for kw in cmd_def.keywords:
                    kw_tokens = set(kw.lower().split())
                    if kw_tokens.issubset(tokens):
                        keyword_hits += 1

                if keyword_hits > 0:
                    score = 0.50 + (keyword_hits * 0.15)
                    # Check required entities
                    if cmd_def.required_entities:
                        if "product" in cmd_def.required_entities and (entities.product or entities.product_obj):
                            score += 0.15
                        if "customer" in cmd_def.required_entities and (entities.customer or entities.customer_obj):
                            score += 0.15

                    if score > best_score:
                        best_score = min(0.95, score)
                        best_intent = intent_name

        # Step 3: Contextual fallback for follow-up questions (e.g. "uska rate?", "5 bech diye")
        if not best_intent and entities.product:
            if any(w in clean for w in ["rate", "price", "kimat", "bhaav"]):
                best_intent = "GET_PRICE"
                best_score = 0.90
            else:
                best_intent = "GET_STOCK"
                best_score = 0.85

        if not best_intent and entities.customer:
            best_intent = "GET_CUSTOMER_BALANCE"
            best_score = 0.85

        cmd_obj = COMMAND_REGISTRY.get(best_intent) if (best_intent and best_intent in COMMAND_REGISTRY) else None
        cmd_info = (cmd_obj.model_dump() if hasattr(cmd_obj, "model_dump") else cmd_obj.dict()) if cmd_obj else None

        if best_score >= 0.80 and best_intent:
            return IntentMatch(
                intent=best_intent,
                confidence=round(best_score, 2),
                command_def=cmd_info,
                requires_clarification=False,
            )
        elif 0.50 <= best_score < 0.80 and best_intent:
            clarify_msg = f"Kya aap {best_intent.replace('_', ' ').lower()} ke baare mein pooch rahe hain?"
            return IntentMatch(
                intent=best_intent,
                confidence=round(best_score, 2),
                command_def=cmd_info,
                requires_clarification=True,
                clarification_message=clarify_msg,
            )
        else:
            # Unknown command response (Section 34)
            return IntentMatch(
                intent="UNKNOWN",
                confidence=round(best_score, 2),
                is_unknown=True,
                requires_clarification=False,
            )
