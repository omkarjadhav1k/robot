"""Speech-to-Text (Groq Whisper & Gemini Multimodal) and Text-to-Speech (Edge Neural & Google TTS) services."""

import base64
from collections import OrderedDict
import hashlib
import io
import logging
import re
from typing import Optional
import urllib.parse
import httpx

from app.config import get_settings
from app.core.http_client import get_gemini_http_client, get_general_http_client

logger = logging.getLogger("max.speech")
settings = get_settings()

# In-memory deterministic LRU audio cache for instant sub-10ms TTS playback
_AUDIO_CACHE: OrderedDict[str, bytes] = OrderedDict()
_CACHE_MAX_SIZE = 200

def _get_cache_key(text: str, language: str, voice: Optional[str] = None) -> str:
    norm_text = re.sub(r"[^\w\s\.,\?!₹\-']", "", text).strip().lower()
    raw = f"{norm_text}:{language}:{voice or 'default'}"
    return hashlib.md5(raw.encode("utf-8")).hexdigest()

def get_cached_audio(text: str, language: str, voice: Optional[str] = None) -> Optional[bytes]:
    key = _get_cache_key(text, language, voice)
    if key in _AUDIO_CACHE:
        _AUDIO_CACHE.move_to_end(key)
        return _AUDIO_CACHE[key]
    return None

def put_cached_audio(text: str, language: str, audio: bytes, voice: Optional[str] = None):
    if not audio:
        return
    key = _get_cache_key(text, language, voice)
    _AUDIO_CACHE[key] = audio
    _AUDIO_CACHE.move_to_end(key)
    if len(_AUDIO_CACHE) > _CACHE_MAX_SIZE:
        _AUDIO_CACHE.popitem(last=False)

HINDI_WORDS_PATTERN = re.compile(
    r"\b(hai|hain|mein|ka|ke|ki|kar|diya|diye|bana|aaj|kitna|kitne|available|nahi|kya|bhej|doon|karoon|aur|ek|do|teen)\b",
    re.IGNORECASE,
)
MARATHI_WORDS_PATTERN = re.compile(
    r"\b(aahe|aahet|kiti|dile|aale|sagle|brr|karayche)\b",
    re.IGNORECASE,
)


def detect_language(text: str) -> str:
    """Detect whether spoken text is Hindi/Hinglish, Marathi, or English."""
    # Check for Devanagari script
    if re.search(r"[\u0900-\u097F]", text):
        if MARATHI_WORDS_PATTERN.search(text):
            return "mr"
        return "hi"

    # Check for Latin-script Hindi / Hinglish keywords
    if HINDI_WORDS_PATTERN.search(text):
        return "hi"

    if MARATHI_WORDS_PATTERN.search(text):
        return "mr"

    return "en"


async def transcribe_with_groq(audio_bytes: bytes, filename: str = "audio.wav") -> str:
    """Transcribe spoken audio into text using Groq's high-speed Whisper-large-v3 API."""
    if not settings.GROQ_API_KEY:
        return ""

    url = "https://api.groq.com/openai/v1/audio/transcriptions"
    headers = {"Authorization": f"Bearer {settings.GROQ_API_KEY}"}
    files = {"file": (filename, audio_bytes, "audio/wav")}
    data = {
        "model": settings.GROQ_WHISPER_MODEL or "whisper-large-v3",
        "temperature": "0.0",
        "response_format": "json",
    }

    try:
        client = get_general_http_client()
        resp = await client.post(url, headers=headers, data=data, files=files)
        if resp.status_code == 200:
            result = resp.json()
            return result.get("text", "").strip()
        else:
            logger.warning(f"Groq Whisper returned HTTP {resp.status_code}: {resp.text[:100]}")
            return ""
    except Exception as e:
        logger.warning(f"Groq Whisper API error: {e}")
        return ""


async def transcribe_with_gemini(audio_bytes: bytes, mime_type: str = "audio/wav") -> str:
    """
    Transcribe spoken audio into text using Gemini's native multimodal audio understanding.
    Works natively using the configured GEMINI_API_KEY without needing separate STT keys.
    """
    key = settings.GEMINI_API_KEY
    if not key or key == "your-gemini-api-key-here":
        return ""

    clean_key = key.strip("\"' \t\r\n")
    models = ["gemini-flash-lite-latest", "gemini-flash-latest", "gemini-1.5-flash"]
    b64_data = base64.b64encode(audio_bytes).decode("utf-8")

    payload = {
        "contents": [
            {
                "role": "user",
                "parts": [
                    {
                        "text": (
                            "Transcribe the following spoken audio accurately in its original language "
                            "(Hindi, Hinglish, Marathi, or English). Return ONLY the transcription text, "
                            "no conversational filler, explanation, or quotes."
                        )
                    },
                    {
                        "inlineData": {
                            "mimeType": mime_type,
                            "data": b64_data,
                        }
                    },
                ],
            }
        ],
        "generationConfig": {
            "temperature": 0.0,
            "maxOutputTokens": 150,
        },
    }

    client = get_gemini_http_client()
    for m in models:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{m}:generateContent?key={clean_key}"
        try:
            resp = await client.post(url, json=payload)
            if resp.status_code == 200:
                data = resp.json()
                candidates = data.get("candidates", [])
                if candidates:
                    parts = candidates[0].get("content", {}).get("parts", [])
                    for p in parts:
                        if "text" in p:
                            return p["text"].strip().strip("\"'")
        except Exception as e:
            logger.warning(f"Gemini transcription with {m} failed: {e}")

    return ""


async def transcribe_speech(audio_bytes: bytes, filename: str = "audio.wav") -> str:
    """Master STT dispatcher: tries Groq Whisper first, then falls back to Gemini Multimodal Audio."""
    if settings.GROQ_API_KEY:
        text = await transcribe_with_groq(audio_bytes, filename)
        if text:
            return text

    # Fallback to Gemini
    return await transcribe_with_gemini(audio_bytes)


async def synthesize_with_edge_tts(
    text: str,
    language: str = "hi",
    voice: Optional[str] = None,
) -> bytes:
    """Synthesize high quality Indian speech using Microsoft Edge Neural TTS."""
    try:
        import edge_tts
    except ImportError:
        logger.warning("edge-tts package is not installed.")
        return b""

    selected_voice = voice
    if not selected_voice:
        if language == "hi":
            selected_voice = "hi-IN-MadhurNeural"  # Warm, natural conversational Indian voice
        elif language == "mr":
            selected_voice = "mr-IN-AarohiNeural"
        else:
            selected_voice = "en-IN-NeerjaNeural"

    # Clean text of emojis for cleaner TTS synthesis
    clean_text = re.sub(r"[^\w\s\.,\?!₹\-']", "", text).strip()
    if not clean_text:
        clean_text = text

    try:
        communicate = edge_tts.Communicate(clean_text, selected_voice)
        audio_stream = io.BytesIO()
        async for chunk in communicate.stream():
            if chunk["type"] == "audio":
                audio_stream.write(chunk["data"])
        return audio_stream.getvalue()
    except Exception as e:
        logger.warning(f"Edge TTS synthesis error: {e}")
        return b""


async def synthesize_with_google_tts(text: str, language: str = "hi") -> bytes:
    """Reliable fallback TTS using Google Translate TTS endpoint (no credentials required)."""
    lang_code = "hi" if language == "hi" else ("mr" if language == "mr" else "en")
    encoded_query = urllib.parse.quote(text[:200])
    url = f"https://translate.google.com/translate_tts?ie=UTF-8&q={encoded_query}&tl={lang_code}&client=tw-ob"

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    }
    try:
        client = get_general_http_client()
        resp = await client.get(url, headers=headers)
        if resp.status_code == 200 and len(resp.content) > 500:
            return resp.content
    except Exception as e:
        logger.warning(f"Google TTS fallback error: {e}")

    return b""


async def synthesize_speech(text: str, language: Optional[str] = None, voice: Optional[str] = None) -> bytes:
    """
    Master TTS dispatcher with sub-10ms LRU cache:
    1. Checks deterministic in-memory cache first.
    2. Auto-detects Hindi/Hinglish, Marathi, or English if not specified.
    3. Uses Microsoft Edge Neural Indian voice.
    4. Gracefully falls back to Google TTS if Edge TTS is unavailable.
    5. Saves synthesized audio to cache.
    """
    if not text or not text.strip():
        return b""

    lang = language or detect_language(text)

    # Check cache first
    cached = get_cached_audio(text, lang, voice)
    if cached:
        return cached

    # 1. Primary: Edge Neural TTS
    audio = await synthesize_with_edge_tts(text, language=lang, voice=voice)
    if not audio:
        # 2. Fallback: Google TTS
        audio = await synthesize_with_google_tts(text, language=lang)

    if audio:
        put_cached_audio(text, lang, audio, voice)

    return audio
