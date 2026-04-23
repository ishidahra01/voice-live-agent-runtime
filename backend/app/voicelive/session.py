"""Voice Live API session management."""

import asyncio
import json
import logging
import websockets
from typing import Any, Optional
from app.config import settings

logger = logging.getLogger(__name__)


class VoiceLiveSession:
    """Manages WebSocket connection to Azure Voice Live API."""

    def __init__(self, frontend_ws):
        self.frontend_ws = frontend_ws
        self.voice_live_ws: Optional[websockets.WebSocketClientProtocol] = None
        self.running = False
        self._tasks = []

    async def connect(self):
        """Connect to Voice Live API."""
        url = settings.voice_live_endpoint
        headers = {
            "api-key": settings.azure_openai_api_key,
        }

        logger.info(f"Connecting to Voice Live API...")
        self.voice_live_ws = await websockets.connect(url, extra_headers=headers)
        logger.info("Connected to Voice Live API")

        # Send initial session configuration
        await self._send_initial_session()

    async def _send_initial_session(self):
        """Send initial session configuration."""
        from app.phases import PHASES
        from app.tools import build_tool_schemas

        initial_phase = "triage"
        phase_config = PHASES[initial_phase]

        session_config = {
            "type": "session.update",
            "session": {
                "model": "gpt-realtime",
                "voice": {"name": "ja-JP-NanamiNeural", "type": "azure-standard"},
                "modalities": ["text", "audio"],
                "input_audio_format": "pcm16",
                "output_audio_format": "pcm16",
                "input_audio_sampling_rate": 24000,
                "output_audio_sampling_rate": 24000,
                "turn_detection": {
                    "type": "azure_semantic_vad",
                    "threshold": 0.5,
                    "prefix_padding_ms": 200,
                    "silence_duration_ms": 500,
                    "end_of_utterance_detection": {
                        "model": "semantic_detection_v1",
                        "threshold": 0.1,
                        "timeout": 4,
                    },
                },
                "input_audio_noise_reduction": {"type": "azure_deep_noise_suppression"},
                "input_audio_echo_cancellation": {"type": "server_echo_cancellation"},
                "input_audio_transcription": {"model": "azure-speech", "language": "ja"},
                "instructions": phase_config["instructions"],
                "tools": build_tool_schemas(phase_config["tools"]),
                "tool_choice": "auto",
                "temperature": 0.7,
            },
        }

        await self.send(session_config)
        logger.info("Sent initial session configuration")

    async def send(self, event: dict):
        """Send event to Voice Live API."""
        if self.voice_live_ws:
            await self.voice_live_ws.send(json.dumps(event))

    async def send_to_frontend(self, event: dict):
        """Send event to frontend."""
        if self.frontend_ws:
            await self.frontend_ws.send_json(event)

    async def send_audio_to_voice_live(self, audio_base64: str):
        """Send audio chunk to Voice Live API."""
        event = {
            "type": "input_audio_buffer.append",
            "audio": audio_base64,
        }
        await self.send(event)

    async def handle_voice_live_events(self, phase_router, context_manager, oob_subagent):
        """Handle events from Voice Live API."""
        try:
            async for message in self.voice_live_ws:
                if isinstance(message, str):
                    event = json.loads(message)
                    await self._dispatch_event(event, phase_router, context_manager, oob_subagent)
                elif isinstance(message, bytes):
                    # Binary audio data
                    logger.debug("Received binary audio data")
        except websockets.exceptions.ConnectionClosed:
            logger.info("Voice Live connection closed")
        except Exception as e:
            logger.error(f"Error handling Voice Live events: {e}", exc_info=True)

    async def _dispatch_event(self, event: dict, phase_router, context_manager, oob_subagent):
        """Dispatch Voice Live event to appropriate handler."""
        event_type = event.get("type", "")

        try:
            if event_type == "session.created":
                logger.info("Session created")
                await self.send_to_frontend({"type": "session_ready"})

            elif event_type == "session.updated":
                logger.info("Session updated")

            elif event_type == "input_audio_buffer.speech_started":
                logger.debug("Speech started")
                await self.send_to_frontend({"type": "speech_started"})

            elif event_type == "input_audio_buffer.speech_stopped":
                logger.debug("Speech stopped")
                await self.send_to_frontend({"type": "speech_stopped"})

            elif event_type == "conversation.item.input_audio_transcription.completed":
                transcript = event.get("transcript", "")
                item_id = event.get("item_id", "")
                logger.info(f"User transcript: {transcript}")

                context_manager.record_utterance(
                    role="user",
                    text=transcript,
                    item_id=item_id,
                    phase=phase_router.current_phase,
                )

                await self.send_to_frontend({
                    "type": "transcript",
                    "role": "user",
                    "text": transcript,
                    "phase": phase_router.current_phase,
                    "item_id": item_id,
                })

            elif event_type == "response.audio_transcript.delta":
                delta = event.get("delta", "")
                item_id = event.get("item_id", "")
                await self.send_to_frontend({
                    "type": "transcript_delta",
                    "role": "assistant",
                    "delta": delta,
                    "item_id": item_id,
                })

            elif event_type == "response.audio_transcript.done":
                transcript = event.get("transcript", "")
                item_id = event.get("item_id", "")
                logger.info(f"Assistant transcript: {transcript}")

                context_manager.record_utterance(
                    role="assistant",
                    text=transcript,
                    item_id=item_id,
                    phase=phase_router.current_phase,
                )

                await self.send_to_frontend({
                    "type": "transcript",
                    "role": "assistant",
                    "text": transcript,
                    "phase": phase_router.current_phase,
                    "item_id": item_id,
                })

            elif event_type == "response.audio.delta":
                audio_delta = event.get("delta", "")
                await self.send_to_frontend({
                    "type": "audio",
                    "data": audio_delta,
                })

            elif event_type == "conversation.item.created":
                item = event.get("item", {})
                if item.get("type") == "function_call":
                    await phase_router.handle_function_call(item)

            elif event_type == "response.function_call_arguments.done":
                await phase_router.handle_function_call_arguments_done(event)

            elif event_type == "response.done":
                response = event.get("response", {})
                usage = response.get("usage", {})

                # Update token usage
                if usage:
                    context_manager.update_usage(
                        prompt_tokens=usage.get("input_tokens", 0),
                        completion_tokens=usage.get("output_tokens", 0),
                    )

                # Check for OOB response
                oob_subagent.handle_response_done(event)

                # Maybe summarize
                summarized = await context_manager.maybe_summarize(self, oob_subagent)
                if summarized:
                    await self.send_to_frontend({
                        "type": "summary_executed",
                        "tokens": context_manager.ctx.cumulative_tokens,
                    })

            elif event_type == "error":
                error_msg = event.get("error", {}).get("message", "Unknown error")
                logger.error(f"Voice Live error: {error_msg}")
                await self.send_to_frontend({"type": "error", "message": error_msg})

        except Exception as e:
            logger.error(f"Error dispatching event {event_type}: {e}", exc_info=True)

    async def close(self):
        """Close Voice Live connection."""
        if self.voice_live_ws:
            await self.voice_live_ws.close()
        self.running = False
