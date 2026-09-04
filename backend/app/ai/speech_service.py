"""Speech-to-Text (Groq Whisper) and Text-to-Speech (Edge TTS) services."""

import io
import logging
from typing import Optional
import httpx

from app.config import get_settings

logger = logging.getLogger("business_ai_robot.speech")
settings = get_settings()


async def transcribe_with_groq(audio_bytes: bytes, filename: str = "audio.wav") -> str:
    """
    Transcribe spoken audio into text using Groq's high-speed Whisper-large-v3 API.
    Returns transcribed text string.
    """
    if not settings.GROQ_API_KEY:
        logger.warning("GROQ_API_KEY not set. Cannot transcribe audio.")
        return ""

    url = "https://api.groq.com/openai/v1/audio/transcriptions"
    headers = {"Authorization": f"Bearer {settings.GROQ_API_KEY}"}

    files = {
        "file": (filename, audio_bytes, "audio/wav"),
    }
    data = {
        "model": settings.GROQ_WHISPER_MODEL or "whisper-large-v3",
        "temperature": "0.0",
        "response_format": "json",
    }

    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.post(url, headers=headers, data=data, files=files)
            if resp.status_code == 200:
                result = resp.json()
                return result.get("text", "").strip()
            else:
                logger.error(f"Groq Whisper API returned {resp.status_code}: {resp.text}")
                return ""
    except Exception as e:
        logger.error(f"Error calling Groq Whisper API: {e}")
        return ""


async def synthesize_with_edge_tts(
    text: str,
    language: str = "en",
    voice: Optional[str] = None,
) -> bytes:
    """
    Synthesize speech from text using Microsoft Edge Neural TTS.
    Returns MP3 audio bytes.
    """
    try:
        import edge_tts
    except ImportError:
        logger.warning("edge-tts package is not installed. Audio synthesis unavailable.")
        return b""

    # Choose voice based on language
    selected_voice = voice
    if not selected_voice:
        if language == "hi":
            selected_voice = settings.HINDI_TTS_VOICE
        elif language == "mr":
            selected_voice = settings.MARATHI_TTS_VOICE
        else:
            selected_voice = settings.DEFAULT_TTS_VOICE

    try:
        communicate = edge_tts.Communicate(text, selected_voice)
        audio_stream = io.BytesIO()
        async for chunk in communicate.stream():
            if chunk["type"] == "audio":
                audio_stream.write(chunk["data"])
        return audio_stream.getvalue()
    except Exception as e:
        logger.error(f"Edge TTS synthesis error: {e}")
        return b""
