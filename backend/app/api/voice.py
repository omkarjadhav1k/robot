"""Voice and text interaction router with Gemini AI and hardware command dispatch."""

import logging
import re
from typing import Optional
from fastapi import APIRouter, File, HTTPException, UploadFile

from app.ai.gemini_service import generate_gemini_response
from app.api.robots import create_robot_command
from app.config import get_settings
from app.schemas.robot import (
    RobotCommandCreate,
    VoiceInteractRequest,
    VoiceInteractResponse,
)

logger = logging.getLogger("business_ai_robot.voice")
router = APIRouter()
settings = get_settings()


def _parse_hardware_intent(prompt: str) -> Optional[dict]:
    """Extract hardware command parameters from natural speech/text."""
    prompt_clean = prompt.lower().strip()

    # Pattern: Turn on/off relay N / light / fan / device N
    relay_match = re.search(r"(?:turn|switch)\s+(on|off)\s+(?:relay|switch|device)?\s*([1-4])", prompt_clean)
    if relay_match:
        state = relay_match.group(1)
        relay_num = int(relay_match.group(2))
        return {
            "action": "set_relay",
            "params": {"relay": relay_num, "state": state},
            "response_text": f"Relay {relay_num} has been switched {state}.",
        }

    # Pattern: Turn on/off all relays
    all_relays_match = re.search(r"(?:turn|switch)\s+(on|off)\s+all\s+(?:relays|switches|devices)?", prompt_clean)
    if all_relays_match:
        state = all_relays_match.group(1)
        return {
            "action": "set_all_relays",
            "params": {"state": state},
            "response_text": f"All relays have been switched {state}.",
        }

    # Pattern: Blink LED / status check
    if re.search(r"(?:blink|flash)\s+(?:the\s+)?(?:led|light)", prompt_clean):
        return {
            "action": "blink_led",
            "params": {"count": 3, "interval_ms": 200},
            "response_text": "Blinking the status LED on the ESP32.",
        }

    # Pattern: Robot status
    if "status" in prompt_clean or "are you online" in prompt_clean:
        return {
            "action": "ping",
            "params": {},
            "response_text": "Business AI Robot is online and connected to the central brain.",
        }

    return None


@router.post(
    "/interact",
    response_model=VoiceInteractResponse,
    summary="Process voice/text interaction and dispatch robot actions",
)
async def process_voice_interaction(req: VoiceInteractRequest) -> VoiceInteractResponse:
    """Process incoming utterance, reason with Gemini AI, and trigger hardware/business action."""
    robot_id = req.robot_id or settings.DEFAULT_ROBOT_ID
    prompt = req.text.strip()

    # 1. Check for direct physical hardware actions (Relays, LED, Status)
    hw_intent = _parse_hardware_intent(prompt)
    if hw_intent:
        cmd_create = RobotCommandCreate(
            action=hw_intent["action"],
            params=hw_intent["params"],
            priority=1,
        )
        cmd_dispatched = await create_robot_command(robot_id, cmd_create)
        return VoiceInteractResponse(
            response_text=hw_intent["response_text"],
            action_type="hardware_action",
            command_dispatched=cmd_dispatched,
        )

    # 2. Real Gemini AI Reasoning
    ai_text, success = await generate_gemini_response(prompt)

    return VoiceInteractResponse(
        response_text=ai_text,
        action_type="conversation",
    )


@router.post("/audio/transcribe", summary="Transcribe speech audio with Groq Whisper")
async def transcribe_audio_endpoint(file: UploadFile = File(...)):
    """Transcribe uploaded voice audio bytes using Groq Whisper-large-v3."""
    from app.ai.speech_service import transcribe_with_groq
    audio_bytes = await file.read()
    transcribed_text = await transcribe_with_groq(audio_bytes, file.filename or "audio.wav")
    return {"text": transcribed_text}


@router.get("/audio/tts", summary="Synthesize speech with Edge TTS")
async def tts_endpoint(text: str, lang: str = "en"):
    """Synthesize high-quality speech MP3 using Microsoft Edge Neural TTS."""
    from fastapi.responses import Response
    from app.ai.speech_service import synthesize_with_edge_tts
    audio_data = await synthesize_with_edge_tts(text, language=lang)
    if not audio_data:
        raise HTTPException(status_code=500, detail="TTS synthesis failed or package unavailable")
    return Response(content=audio_data, media_type="audio/mpeg")
