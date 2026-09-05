"""Gemini AI client using httpx REST calls to Generative Language API."""

import logging
from typing import Optional, Tuple
import httpx

from app.config import get_settings

logger = logging.getLogger("business_ai_robot.gemini")

SYSTEM_INSTRUCTION = (
    "You are Business AI Robot, a physical AI business assistant and operational manager. "
    "You run on physical ESP32 robot hardware and help store owners with inventory, appliances, "
    "customer management, and billing.\n"
    "Keep responses conversational, concise (1-2 sentences), clear, and natural for speech/serial display."
)

FALLBACK_MODELS = ["gemini-3.7-flash", "gemini-3.1-flash-lite"]


async def generate_gemini_response(prompt: str, api_key: Optional[str] = None) -> Tuple[str, bool]:
    """
    Call official Google Gemini API using REST endpoint via httpx.
    Includes automatic model fallback to ensure high availability.
    Returns (response_text, is_success).
    """
    settings = get_settings()
    key = api_key or settings.GEMINI_API_KEY
    if not key or key == "your-gemini-api-key-here":
        return (
            "Gemini API key is not configured yet. Please add your GEMINI_API_KEY in backend/.env to enable real AI reasoning.",
            False,
        )

    # Clean key (strip quotes, whitespace)
    clean_key = key.strip("\"' \t\r\n")

    models_to_try = [settings.GEMINI_MODEL] if settings.GEMINI_MODEL in FALLBACK_MODELS else []
    for m in FALLBACK_MODELS:
        if m not in models_to_try:
            models_to_try.append(m)

    payload = {
        "contents": [
            {
                "parts": [
                    {"text": prompt}
                ]
            }
        ],
        "systemInstruction": {
            "parts": [
                {"text": SYSTEM_INSTRUCTION}
            ]
        },
        "generationConfig": {
            "temperature": 0.7,
            "maxOutputTokens": 100,
            "thinkingConfig": {
                "thinkingBudget": 0
            }
        },
    }

    last_err = "No response"
    async with httpx.AsyncClient(timeout=20.0) as client:
        for model in models_to_try:
            url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={clean_key}"
            try:
                resp = await client.post(url, json=payload)
                if resp.status_code == 200:
                    data = resp.json()
                    candidates = data.get("candidates", [])
                    if candidates:
                        parts = candidates[0].get("content", {}).get("parts", [])
                        if parts:
                            return (parts[0].get("text", "").strip(), True)
                else:
                    logger.warning(f"Model {model} returned status {resp.status_code}: {resp.text[:120]}")
                    last_err = f"API Status {resp.status_code}"
            except (httpx.TimeoutException, httpx.ReadTimeout):
                logger.warning(f"Model {model} timed out, trying next fallback model...")
                last_err = "Request timed out"
            except Exception as e:
                logger.warning(f"Model {model} error: {e}")
                last_err = str(e)

    return (f"Gemini API temporarily unavailable: {last_err}", False)
