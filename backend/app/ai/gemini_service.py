"""Gemini AI client with Function Calling / Tools, multi-turn history, and low-latency optimization."""

import logging
from typing import Any, Dict, List, Optional, Tuple
import httpx
from pydantic import BaseModel

from app.config import get_settings

logger = logging.getLogger("business_ai_robot.gemini")

SYSTEM_INSTRUCTION = (
    "You are Business AI Robot, an intelligent, helpful, and friendly physical retail AI robot running in an Indian store.\n"
    "You communicate naturally in a warm, polite, and conversational Hinglish/Hindi or English tone matching the user's language.\n"
    "Keep spoken responses concise (1-2 natural sentences) so they sound crisp, warm, and natural when spoken aloud via the speaker.\n\n"
    "CONVERSATIONAL PERSONALITY & TONE EXAMPLES:\n"
    "- User: 'Hello Robo, tum kaise ho?'\n"
    "  Robot: 'Hello! Main bilkul accha hoon 😄 Aap batao, main aapki kya help kar sakta hoon?'\n"
    "- User: 'Robo, Tata Salt ka stock kitna hai?'\n"
    "  Robot queries check_stock -> 'Tata Salt ke 37 packets available hain.'\n"
    "- User: 'Usme se 5 bech diye.'\n"
    "  Robot resolves context to Tata Salt, calls reduce_stock -> 'Okay, Tata Salt ka stock 5 packets kam kar diya. Ab 32 packets available hain.'\n"
    "- User: 'Robo, aaj kitni sale hui?'\n"
    "  Robot queries get_sales_today -> 'Aaj ki total sale ₹18,450 hai.'\n"
    "- User: 'Robo, light on kar.'\n"
    "  Robot calls control_relay(device='light', state='on') -> 'Done, light on kar di.'\n"
    "- User: 'Fan band kar.'\n"
    "  Robot calls control_relay(device='fan', state='off') -> 'Sure, fan band kar diya.'\n"
    "- User: 'Robo, Amit ka bill bana do.' (without items)\n"
    "  Robot asks naturally: 'Bilkul. Amit ke bill mein kaunse items add karne hain?'\n"
    "- User: 'Do Tata Salt aur ek Surf Excel.' (following bill prompt)\n"
    "  Robot creates bill for Amit and asks: 'Bill ₹196 ka bana diya hai. Kya main ise Amit ke WhatsApp par bhej doon?'\n\n"
    "FALLBACKS & SAFETY RULES:\n"
    "- If a query is not understood: 'Sorry, mujhe ye samajh nahi aaya. Aap stock, billing ya shop devices ke baare mein pooch sakte ho.'\n"
    "- If product is not found: 'Mujhe [product] naam ka product inventory mein nahi mila. Product ka naam dobara bataoge?'\n"
    "- If connection fails: 'Abhi inventory system se connection nahi ho raha. Thodi der baad try karo.'\n"
    "- NEVER invent or hallucinate stock quantities, prices, or bill totals. ALWAYS call database tools.\n\n"
    "SHORT-TERM CONTEXT & PRONOUN RESOLUTION:\n"
    "When the user refers to 'usme se', 'isme se', 'uska', 'it', 'them', or says '5 bech diye', '10 aur add kar do' without repeating the product name, ALWAYS look at the previous turn in history to identify the referenced product and call reduce_stock or add_stock!\n\n"
    "MULTI-TURN BILLING WORKFLOW:\n"
    "When user says '[Customer] ka bill bana do', if items are missing, ask what items to add. When items are specified in the next turn, use the customer name from the previous turn to call create_bill. Then ask if they want it sent on WhatsApp. If they reply 'haan' or 'yes', use send_whatsapp_bill!"
)

FALLBACK_MODELS = ["gemini-flash-lite-latest", "gemini-3.5-flash-lite", "gemini-flash-latest", "gemini-3.7-flash"]

# Tool Declarations for Gemini Function Calling
BUSINESS_TOOLS = [
    {
        "functionDeclarations": [
            {
                "name": "check_stock",
                "description": "Check current available stock level, unit, and authoritative price of a product in store inventory (e.g. 'Tata Salt kitna hai', 'stock of sugar', 'available stock', 'kitne packets bache hain').",
                "parameters": {
                    "type": "OBJECT",
                    "properties": {
                        "product_name": {
                            "type": "STRING",
                            "description": "The name of the product to check (e.g. 'Tata Salt', 'Sugar', 'Milk', 'Tea').",
                        }
                    },
                    "required": ["product_name"],
                },
            },
            {
                "name": "reduce_stock",
                "description": "Deduct, reduce, or record sale of product stock (e.g. 'Usme se 5 bech diye', '5 packets bech diye', 'reduce 2 kg sugar', 'sold 5'). Use conversation history if product name is referenced as 'usme se'.",
                "parameters": {
                    "type": "OBJECT",
                    "properties": {
                        "product_name": {
                            "type": "STRING",
                            "description": "Name of the product being sold or deducted (e.g. 'Tata Salt'). Inferred from context if not explicitly spoken.",
                        },
                        "quantity": {
                            "type": "NUMBER",
                            "description": "Quantity sold or deducted (e.g. 5).",
                        },
                    },
                    "required": ["product_name", "quantity"],
                },
            },
            {
                "name": "add_stock",
                "description": "Add, restock, or replenish quantity for a product in inventory (e.g. 'Tata Salt ke 10 packet aur aaye hain', 'add 10 stock to sugar').",
                "parameters": {
                    "type": "OBJECT",
                    "properties": {
                        "product_name": {
                            "type": "STRING",
                            "description": "Name of the product to restock (e.g. 'Tata Salt').",
                        },
                        "quantity": {
                            "type": "NUMBER",
                            "description": "Quantity to add to inventory (e.g. 10).",
                        },
                        "unit": {
                            "type": "STRING",
                            "description": "Optional unit of measurement, e.g. 'packet', 'kg', 'pcs'.",
                        },
                    },
                    "required": ["product_name", "quantity"],
                },
            },
            {
                "name": "get_sales_today",
                "description": "Retrieve today's total store revenue, bill count, or sales given to a specific customer (e.g. 'aaj kitni sale hui', 'today's sales', 'today revenue', 'omkar ke bill').",
                "parameters": {
                    "type": "OBJECT",
                    "properties": {
                        "customer_name": {
                            "type": "STRING",
                            "description": "Optional customer name to filter sales for that specific customer only (e.g. 'Omkar', 'Amit').",
                        }
                    },
                },
            },
            {
                "name": "list_all_products",
                "description": "List all products in inventory, count total items, or provide stock overview (e.g. 'check all stock', 'list products', 'sagle kiti product aahe').",
                "parameters": {
                    "type": "OBJECT",
                    "properties": {},
                },
            },
            {
                "name": "get_low_stock_items",
                "description": "Get products low on stock or below reorder threshold (e.g. 'what is low on stock', 'kam stock wale saman').",
                "parameters": {
                    "type": "OBJECT",
                    "properties": {},
                },
            },
            {
                "name": "get_customer",
                "description": "Check customer outstanding credit balance, contact details, or customer directory (e.g. 'Ramesh balance', 'list customers').",
                "parameters": {
                    "type": "OBJECT",
                    "properties": {
                        "customer_name": {
                            "type": "STRING",
                            "description": "Customer name (e.g. 'Ramesh', 'Amit') or 'all'.",
                        }
                    },
                    "required": ["customer_name"],
                },
            },
            {
                "name": "create_bill",
                "description": "Create a customer sales bill with products, quantities, and prices, optionally sending it on WhatsApp.",
                "parameters": {
                    "type": "OBJECT",
                    "properties": {
                        "customer_name": {
                            "type": "STRING",
                            "description": "Customer name if known (e.g. 'Amit', 'Rahul', 'Omkar').",
                        },
                        "items": {
                            "type": "ARRAY",
                            "description": "List of products and quantities to bill.",
                            "items": {
                                "type": "OBJECT",
                                "properties": {
                                    "name": {"type": "STRING", "description": "Product name (e.g. 'Tata Salt', 'Surf Excel', 'Tea')"},
                                    "quantity": {"type": "NUMBER", "description": "Quantity purchased (e.g. 2)"},
                                },
                                "required": ["name", "quantity"],
                            },
                        },
                        "payment_method": {
                            "type": "STRING",
                            "description": "Payment method: CASH, UPI, CREDIT, or CARD. Defaults to CASH.",
                        },
                        "send_whatsapp": {
                            "type": "BOOLEAN",
                            "description": "True if user explicitly wants the bill sent to customer WhatsApp.",
                        },
                    },
                    "required": ["items"],
                },
            },
            {
                "name": "control_relay",
                "description": "Switch physical shop appliances (light, fan, socket, etc.) or electrical relay channels on or off (e.g. 'light on kar', 'fan band kar', 'turn off relay 1').",
                "parameters": {
                    "type": "OBJECT",
                    "properties": {
                        "device": {
                            "type": "STRING",
                            "description": "Device name: 'light', 'fan', 'socket', 'aux', or 'all'.",
                        },
                        "relay_number": {
                            "type": "INTEGER",
                            "description": "Relay channel number (1 to 4) if device is not specified.",
                        },
                        "state": {
                            "type": "STRING",
                            "description": "Desired state: 'on' or 'off'.",
                        },
                    },
                    "required": ["state"],
                },
            },
            {
                "name": "send_whatsapp_bill",
                "description": "Send a bill or invoice to customer on WhatsApp (e.g. 'Amit ka bill WhatsApp par bhej do', 'send bill on WhatsApp').",
                "parameters": {
                    "type": "OBJECT",
                    "properties": {
                        "invoice_id": {
                            "type": "STRING",
                            "description": "Invoice number or 'latest' for last generated bill.",
                        },
                        "customer_name": {
                            "type": "STRING",
                            "description": "Customer name (e.g. 'Amit', 'Rahul').",
                        },
                        "phone_number": {
                            "type": "STRING",
                            "description": "WhatsApp phone number if provided by user.",
                        },
                    },
                },
            },
            {
                "name": "blink_led",
                "description": "Blink the robot's hardware status LED.",
                "parameters": {
                    "type": "OBJECT",
                    "properties": {
                        "times": {
                            "type": "INTEGER",
                            "description": "Number of blinks (1 to 10). Default 3.",
                        }
                    },
                },
            },
        ]
    }
]


class GeminiResult(BaseModel):
    """Structured response from Gemini API."""
    text: Optional[str] = None
    function_call: Optional[Dict[str, Any]] = None
    is_success: bool = True
    model_used: Optional[str] = None
    raw_error: Optional[str] = None


async def reason_with_gemini(
    user_text: str,
    history: Optional[List[Dict[str, str]]] = None,
    api_key: Optional[str] = None,
    custom_instructions: Optional[List[str]] = None,
    system_instruction: Optional[str] = None,
) -> GeminiResult:
    """
    Query Google Gemini with multi-turn history, dynamic custom instructions, and function calling tools enabled.
    Returns GeminiResult containing either natural language text or a structured function call.
    """
    settings = get_settings()
    key = api_key or settings.GEMINI_API_KEY
    if not key or key == "your-gemini-api-key-here":
        return GeminiResult(
            text="Gemini API key is not configured yet. Please add your GEMINI_API_KEY to enable real AI reasoning.",
            is_success=False,
            raw_error="Missing API Key",
        )

    clean_key = key.strip("\"' \t\r\n")

    # Ensure fastest models are always tried first to guarantee sub-second robot responsiveness.
    # Never prioritize heavy models like gemini-3.7-flash ahead of flash-lite.
    fast_models = ["gemini-flash-lite-latest", "gemini-3.5-flash-lite", "gemini-flash-latest"]
    if settings.GEMINI_MODEL and settings.GEMINI_MODEL not in fast_models and "3.7" not in settings.GEMINI_MODEL:
        models_to_try = [settings.GEMINI_MODEL] + [m for m in fast_models if m != settings.GEMINI_MODEL]
    else:
        models_to_try = list(fast_models)
    if "gemini-3.7-flash" not in models_to_try:
        models_to_try.append("gemini-3.7-flash")

    # Build active system prompt including any learned brain instructions
    active_system_prompt = system_instruction or SYSTEM_INSTRUCTION
    if custom_instructions:
        active_system_prompt += "\n\nACTIVE CUSTOM STORE RULES & LEARNED BRAIN INSTRUCTIONS:\n"
        for idx, rule in enumerate(custom_instructions, 1):
            rule_clean = rule.strip()
            if rule_clean:
                active_system_prompt += f"{idx}. {rule_clean}\n"

    # Format multi-turn contents
    contents: List[Dict[str, Any]] = []
    if history:
        for turn in history:
            role = turn.get("role", "user")
            # Map role: "assistant" -> "model" for Gemini
            g_role = "model" if role in ("assistant", "model") else "user"
            content_text = turn.get("content") or turn.get("text") or ""
            if content_text.strip():
                contents.append({
                    "role": g_role,
                    "parts": [{"text": content_text.strip()}],
                })

    # Append current user prompt
    contents.append({
        "role": "user",
        "parts": [{"text": user_text.strip()}],
    })

    payload = {
        "contents": contents,
        "tools": BUSINESS_TOOLS,
        "systemInstruction": {
            "parts": [{"text": active_system_prompt}]
        },
        "generationConfig": {
            "temperature": 0.2,  # Low temperature for strict, reliable tool selection
            "maxOutputTokens": 200,
        },
    }

    last_err = "No response"
    async with httpx.AsyncClient(timeout=8.0) as client:
        for model in models_to_try:
            url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={clean_key}"
            try:
                resp = await client.post(url, json=payload)
                if resp.status_code == 200:
                    data = resp.json()
                    candidates = data.get("candidates", [])
                    if candidates:
                        parts = candidates[0].get("content", {}).get("parts", [])
                        for part in parts:
                            # 1. Check for function call
                            if "functionCall" in part:
                                fn = part["functionCall"]
                                logger.info("Gemini invoked tool '%s' with args: %s", fn.get("name"), fn.get("args"))
                                return GeminiResult(
                                    function_call={
                                        "name": fn.get("name"),
                                        "args": fn.get("args", {}),
                                    },
                                    is_success=True,
                                    model_used=model,
                                )
                            # 2. Check for text
                            if "text" in part:
                                return GeminiResult(
                                    text=part["text"].strip(),
                                    is_success=True,
                                    model_used=model,
                                )
                else:
                    logger.warning("Model %s returned HTTP %s: %s", model, resp.status_code, resp.text[:120])
                    last_err = f"HTTP {resp.status_code}: {resp.text[:100]}"
            except (httpx.TimeoutException, httpx.ReadTimeout):
                logger.warning("Model %s timed out, trying next fallback model...", model)
                last_err = "Request timed out"
            except Exception as e:
                logger.warning("Model %s error: %s", model, e)
                last_err = str(e)

    return GeminiResult(
        text=f"AI service temporarily unavailable: {last_err}",
        is_success=False,
        raw_error=last_err,
    )


async def generate_gemini_response(prompt: str, api_key: Optional[str] = None) -> Tuple[str, bool]:
    """Backward-compatible helper for simple text generation."""
    res = await reason_with_gemini(user_text=prompt, api_key=api_key)
    return (res.text or "Understood.", res.is_success)
