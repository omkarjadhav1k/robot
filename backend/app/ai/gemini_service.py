"""Gemini AI client with Function Calling / Tools, multi-turn history, and low-latency optimization."""

import logging
from typing import Any, Dict, List, Optional, Tuple
import httpx
from pydantic import BaseModel

from app.config import get_settings

logger = logging.getLogger("business_ai_robot.gemini")

SYSTEM_INSTRUCTION = (
    "You are Business AI Robot, an intelligent physical AI assistant and business manager running on "
    "an ESP32 robot in a retail store.\n"
    "CRITICAL RULES:\n"
    "1. You NEVER guess, hallucinate, or invent inventory stock, product prices, customer balances, or bill totals.\n"
    "2. You MUST use the provided function tools to query the database whenever the user asks about stock, bills, sales, customers, or to create a bill.\n"
    "3. You MUST use hardware tools (control_relay, blink_led) when asked to switch or toggle appliances, lights, or relays.\n"
    "4. When asked to add, register, or create a new product/sample product in the store/inventory, use the add_product tool.\n"
    "5. For general pleasantries or questions not involving store data, answer directly, concisely, and naturally in 1-2 sentences for speech/display."
)

FALLBACK_MODELS = ["gemini-flash-lite-latest", "gemini-3.5-flash-lite", "gemini-flash-latest", "gemini-3.7-flash"]

# Tool Declarations for Gemini Function Calling
BUSINESS_TOOLS = [
    {
        "functionDeclarations": [
            {
                "name": "get_stock",
                "description": "Check current stock level, unit, and authoritative selling price of a product in inventory.",
                "parameters": {
                    "type": "OBJECT",
                    "properties": {
                        "product_name": {
                            "type": "STRING",
                            "description": "The name or search term of the product (e.g., 'sugar', 'rice', 'milk').",
                        }
                    },
                    "required": ["product_name"],
                },
            },
            {
                "name": "get_low_stock_items",
                "description": "Get a list of products whose inventory is below the minimum reorder threshold.",
                "parameters": {
                    "type": "OBJECT",
                    "properties": {},
                },
            },
            {
                "name": "get_todays_bills",
                "description": "Retrieve today's verified bills count, total revenue, and list of sales.",
                "parameters": {
                    "type": "OBJECT",
                    "properties": {},
                },
            },
            {
                "name": "get_customer_balance",
                "description": "Check a customer's outstanding credit balance and account details by name or phone.",
                "parameters": {
                    "type": "OBJECT",
                    "properties": {
                        "customer_name": {
                            "type": "STRING",
                            "description": "The name or phone number of the customer (e.g. 'Ramesh', 'Suresh').",
                        }
                    },
                    "required": ["customer_name"],
                },
            },
            {
                "name": "create_bill",
                "description": "Initiate creation of a sales bill with line items and customer information.",
                "parameters": {
                    "type": "OBJECT",
                    "properties": {
                        "customer_name": {
                            "type": "STRING",
                            "description": "Customer name if known (optional).",
                        },
                        "items": {
                            "type": "ARRAY",
                            "description": "List of products and quantities to bill.",
                            "items": {
                                "type": "OBJECT",
                                "properties": {
                                    "name": {"type": "STRING", "description": "Product name (e.g. 'rice')"},
                                    "quantity": {"type": "NUMBER", "description": "Quantity purchased (e.g. 2)"},
                                },
                                "required": ["name", "quantity"],
                            },
                        },
                        "payment_method": {
                            "type": "STRING",
                            "description": "Payment method: CASH, UPI, CREDIT, or CARD. Defaults to CASH.",
                        },
                    },
                    "required": ["items"],
                },
            },
            {
                "name": "control_relay",
                "description": "Switch an electrical relay or connected appliance (light, fan, socket) on or off.",
                "parameters": {
                    "type": "OBJECT",
                    "properties": {
                        "relay_number": {
                            "type": "INTEGER",
                            "description": "Relay channel number (1 to 4).",
                        },
                        "state": {
                            "type": "STRING",
                            "description": "Desired state: 'on' or 'off'.",
                        },
                    },
                    "required": ["relay_number", "state"],
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
            {
                "name": "get_business_summary",
                "description": "Get high level store performance metrics (today's revenue, low stock count, credit due).",
                "parameters": {
                    "type": "OBJECT",
                    "properties": {},
                },
            },
            {
                "name": "add_product",
                "description": "Add a new product to inventory or update its stock and price.",
                "parameters": {
                    "type": "OBJECT",
                    "properties": {
                        "name": {
                            "type": "STRING",
                            "description": "Name of the product (e.g. 'Eggs', 'Brown Bread', 'Soap', 'Sample Product').",
                        },
                        "unit": {
                            "type": "STRING",
                            "description": "Unit of measurement, e.g. 'kg', 'pcs', 'ltr', 'packet'. Defaults to 'pcs'.",
                        },
                        "selling_price": {
                            "type": "NUMBER",
                            "description": "Authoritative selling price per unit in rupees.",
                        },
                        "stock": {
                            "type": "NUMBER",
                            "description": "Initial stock quantity. Defaults to 10 if not specified.",
                        },
                    },
                    "required": ["name", "selling_price"],
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
) -> GeminiResult:
    """
    Query Google Gemini with multi-turn history and function calling tools enabled.
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
            "parts": [{"text": SYSTEM_INSTRUCTION}]
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
