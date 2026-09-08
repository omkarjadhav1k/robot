"""Real-Time WebSocket Audio & Control Gateway supporting 16kHz PCM streaming, barge-in, and async jobs."""

import asyncio
from datetime import datetime, timezone
import io
import json
import logging
import time
from typing import Any, Dict, Optional, Set
import wave

from fastapi import WebSocket, WebSocketDisconnect
from sqlalchemy.orm import Session

from app.ai.speech_service import synthesize_speech, transcribe_speech
from app.database.session import SessionLocal
from app.engine.command_registry import CommandMode
from app.engine.conversation_state import ConversationStateManager
from app.engine.entity_extractor import EntityExtractor
from app.engine.fast_query_engine import FastQueryEngine
from app.engine.intent_router import IntentRouter
from app.engine.response_templates import ResponseTemplates
from app.engine.task_manager import BackgroundTaskManager
from app.models.conversation import ConversationSession, ConversationState
from app.services.conversation_service import ConversationService

logger = logging.getLogger("robot.engine.websocket")

# Frame specifications (Section 26)
FRAME_SAMPLE_RATE = 16000
FRAME_CHANNELS = 1
FRAME_BYTES_PER_SAMPLE = 2  # 16-bit
FRAME_DURATION_MS = 20
FRAME_BYTES = 640           # 320 samples * 2 bytes


class WebSocketSessionHandler:
    """Manages an active WebSocket client with binary audio streaming and barge-in support."""

    def __init__(self, websocket: WebSocket, robot_id: str = "ROBOT-001"):
        self.ws = websocket
        self.robot_id = robot_id
        self.conversation_id = f"conv_{int(time.time()*1000)}"
        self.pcm_audio_buffer = bytearray()
        self.is_recording = False
        self.current_request_id: Optional[str] = None
        self.is_speaking = False
        self.cancel_tts_event = asyncio.Event()
        self._tts_task: Optional[asyncio.Task] = None

    async def handle_connection(self):
        """Main lifecycle loop for a WebSocket client."""
        await self.ws.accept()
        logger.info("WebSocket client connected: %s (conv: %s)", self.robot_id, self.conversation_id)

        # Register listener for background job completions
        async def on_job_completed(payload: Dict[str, Any]):
            await self._send_json(payload)
            # Synthesize completion notification speech
            await self.stream_tts_response(payload.get("text", "Job completed."), "NOTIFICATION")

        BackgroundTaskManager.register_completion_listener(on_job_completed)

        try:
            while True:
                message = await self.ws.receive()
                
                # 1. Binary Audio Frame (PCM)
                if "bytes" in message and message["bytes"]:
                    if self.is_recording:
                        self.pcm_audio_buffer.extend(message["bytes"])

                # 2. Text / JSON Control Event
                elif "text" in message and message["text"]:
                    try:
                        data = json.loads(message["text"])
                        await self._process_control_event(data)
                    except json.JSONDecodeError:
                        logger.warning("Invalid JSON received on WS: %s", message["text"])

        except WebSocketDisconnect:
            logger.info("WebSocket client disconnected: %s", self.robot_id)
        except Exception as e:
            logger.error("WebSocket session error: %s", e, exc_info=True)
        finally:
            self.stop_current_playback()

    async def _process_control_event(self, data: Dict[str, Any]):
        """Dispatch structured JSON events."""
        event_type = data.get("type")
        request_id = data.get("request_id") or f"REQ-{int(time.time()*1000)}"

        # A. BARGE-IN / INTERRUPT (Sections 14 & 15)
        if event_type in ("barge_in", "interrupt"):
            logger.info("Barge-in received. Stopping current speech output immediately.")
            self.stop_current_playback()
            await self._send_json({
                "type": "barge_in_ack",
                "action": "stop_playback",
                "request_id": request_id,
                "status": "playback_cancelled",
            })
            return

        # B. SPEECH START
        if event_type == "speech_start":
            self.is_recording = True
            self.current_request_id = request_id
            self.pcm_audio_buffer.clear()
            # If robot was speaking when user started talking, trigger automatic barge-in!
            if self.is_speaking:
                logger.info("User speech started during robot playback. Triggering auto barge-in.")
                self.stop_current_playback()
            await self._send_json({
                "type": "listening",
                "request_id": request_id,
                "status": "ready",
            })
            return

        # C. SPEECH END
        if event_type == "speech_end":
            self.is_recording = False
            raw_pcm = bytes(self.pcm_audio_buffer)
            self.pcm_audio_buffer.clear()

            # Transcribe audio buffer or use provided text
            text = data.get("text", "")
            if not text and len(raw_pcm) > 640:
                wav_bytes = self._pcm_to_wav(raw_pcm)
                text = await transcribe_speech(wav_bytes, filename="user_speech.wav")

            if text:
                await self.process_user_utterance(text, request_id)
            else:
                await self._send_json({
                    "type": "error",
                    "request_id": request_id,
                    "message": "No audible speech detected.",
                })
            return

        # D. DIRECT TEXT QUERY (Simulation & Console)
        if event_type == "text_query":
            text = data.get("text", "")
            if text:
                await self.process_user_utterance(text, request_id)
            return

    async def process_user_utterance(self, text: str, request_id: str):
        """Core non-LLM processing pipeline for an incoming user utterance."""
        with SessionLocal() as db:
            session = ConversationService.get_or_create_session(
                db=db,
                conversation_id=self.conversation_id,
                robot_id=self.robot_id,
            )
            state_ctx = ConversationStateManager.load_state(db, session)

            # 1. Check Barge-In command ("ruko", "stop")
            if text.strip().lower() in ("ruko", "stop", "chup", "shant", "bas", "arre ruko"):
                self.stop_current_playback()
                await self._send_json({"type": "ack", "request_id": request_id, "text": "Ruk gaya."})
                return

            # 2. Extract Entities
            entities = EntityExtractor.extract_all(
                text=text,
                db=db,
                business_id=session.business_id,
                last_product=state_ctx.last_product,
                last_customer=state_ctx.last_customer,
            )

            # 3. Classify Intent
            match = IntentRouter.classify(text, entities)

            # 4. Handle Disambiguation
            if match.requires_clarification:
                reply = match.clarification_message or ResponseTemplates.get("UNKNOWN")
                await self._send_json({"type": "clarification", "request_id": request_id, "text": reply})
                await self.stream_tts_response(reply, request_id)
                return

            intent = match.intent
            cmd_def = match.command_def or {}
            mode = cmd_def.get("mode", CommandMode.FAST.value)

            # 5. Handle Background Jobs (Strategy, Reports)
            if mode == CommandMode.BACKGROUND.value or intent in ("CREATE_WEEKLY_STRATEGY", "GENERATE_SALES_REPORT", "GENERATE_INVENTORY_REPORT"):
                immediate_ack = ResponseTemplates.get("ACK_STRATEGY") if "STRATEGY" in intent else ResponseTemplates.get("ACK_TASK")
                # Immediately acknowledge! (Section 1)
                await self._send_json({"type": "ack", "request_id": request_id, "text": immediate_ack})
                await self.stream_tts_response(immediate_ack, request_id)

                # Queue background task
                task_id = BackgroundTaskManager.enqueue_task(
                    task_type=intent,
                    business_id=session.business_id,
                )
                state_ctx.active_task_ids.append(task_id)
                ConversationStateManager.save_state(db, session, state_ctx)

                await self._send_json({
                    "type": "job_started",
                    "request_id": request_id,
                    "job_id": task_id,
                    "text": f"Task {task_id} start ho gaya hai.",
                })
                return

            # 6. Handle Task Status Query
            if intent == "TASK_STATUS":
                active_ids = state_ctx.active_task_ids
                if not active_ids:
                    reply = "Abhi koi background task running nahi hai. Main ready hoon."
                else:
                    latest_id = active_ids[-1]
                    status_info = BackgroundTaskManager.get_task_status(latest_id)
                    if status_info and status_info["status"] == "RUNNING":
                        reply = f"Abhi {status_info['type'].replace('_', ' ').lower()} chal raha hai. Progress {status_info['progress']}% hai."
                    else:
                        reply = "Abhi ready hoon. Batao kya karna hai."

                await self._send_json({"type": "response", "request_id": request_id, "text": reply})
                await self.stream_tts_response(reply, request_id)
                return

            # 7. Handle Past Task Retrieval ("Kal wali strategy batao")
            if intent == "GET_COMPLETED_TASK":
                completed_task = BackgroundTaskManager.get_latest_completed_task(
                    task_type="STRATEGY" if "strategy" in text.lower() else None,
                    business_id=session.business_id,
                )
                if completed_task and completed_task.get("result"):
                    res_data = completed_task["result"]
                    reply = res_data.get("natural_summary") or res_data.get("summary") or "Last task successfully complete hua tha."
                else:
                    reply = "Purana koi saved task result nahi mila."

                await self._send_json({"type": "response", "request_id": request_id, "text": reply})
                await self.stream_tts_response(reply, request_id)
                return

            # 8. Fast Query Engine Execution
            fast_res = FastQueryEngine.execute(
                intent=intent,
                entities=entities,
                db=db,
                business_id=session.business_id,
                robot_id=self.robot_id,
            )

            # Update conversation state context with entities
            if entities.product:
                state_ctx.last_product = entities.product
            if entities.customer:
                state_ctx.last_customer = entities.customer
            state_ctx.last_intent = intent
            ConversationStateManager.save_state(db, session, state_ctx)

            # Send response & stream audio
            await self._send_json({
                "type": "response",
                "request_id": request_id,
                "text": fast_res.response_text,
                "action_type": fast_res.action_type,
                "data": fast_res.data,
                "latency_ms": fast_res.latency_ms,
            })
            await self.stream_tts_response(fast_res.response_text, request_id)

    async def stream_tts_response(self, text: str, request_id: str):
        """Synthesize and stream audio frames over WebSocket with interruption support."""
        self.stop_current_playback()
        self.cancel_tts_event.clear()
        self._tts_task = asyncio.create_task(self._tts_streamer(text, request_id))

    async def _tts_streamer(self, text: str, request_id: str):
        self.is_speaking = True
        try:
            await self._send_json({"type": "tts_start", "request_id": request_id, "text": text})

            # Synthesize MP3 audio
            audio_bytes = await synthesize_speech(text, language="hi")
            if not audio_bytes or self.cancel_tts_event.is_set():
                return

            # Stream audio in 640-byte chunks to match ESP32 buffer
            chunk_size = 640
            for i in range(0, len(audio_bytes), chunk_size):
                if self.cancel_tts_event.is_set():
                    logger.info("TTS streaming cancelled by user barge-in.")
                    break
                chunk = audio_bytes[i : i + chunk_size]
                await self.ws.send_bytes(chunk)
                await asyncio.sleep(0.015)  # Pace frames

            if not self.cancel_tts_event.is_set():
                await self._send_json({"type": "tts_end", "request_id": request_id})

        except Exception as e:
            logger.warning("TTS streaming note: %s", e)
        finally:
            self.is_speaking = False

    def stop_current_playback(self):
        """Instantly abort current audio playback without touching background jobs."""
        if self.is_speaking or (self._tts_task and not self._tts_task.done()):
            self.cancel_tts_event.set()
            if self._tts_task:
                self._tts_task.cancel()
            self.is_speaking = False
            logger.info("Speech playback stopped immediately.")

    async def _send_json(self, payload: Dict[str, Any]):
        try:
            await self.ws.send_text(json.dumps(payload))
        except Exception:
            pass

    def _pcm_to_wav(self, pcm_bytes: bytes) -> bytes:
        """Wrap raw PCM bytes into WAV container format."""
        wav_io = io.BytesIO()
        with wave.open(wav_io, "wb") as wav_file:
            wav_file.setnchannels(FRAME_CHANNELS)
            wav_file.setsampwidth(FRAME_BYTES_PER_SAMPLE)
            wav_file.setframerate(FRAME_SAMPLE_RATE)
            wav_file.writeframes(pcm_bytes)
        return wav_io.getvalue()
