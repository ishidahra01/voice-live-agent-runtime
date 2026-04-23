"""Voice Live API session management."""

import asyncio
import base64
import logging
from typing import Any, Optional

from azure.ai.voicelive.aio import VoiceLiveConnection, connect
from azure.ai.voicelive.models import (
    AudioEchoCancellation,
    AudioInputTranscriptionOptions,
    AudioNoiseReduction,
    AzureSemanticVadMultilingual,
    AzureStandardVoice,
    InputAudioFormat,
    Modality,
    OutputAudioFormat,
    RequestSession,
    ResponseCreateParams,
    ServerEventType,
)
from azure.core.credentials import AzureKeyCredential
from azure.core.credentials_async import AsyncTokenCredential
from azure.identity.aio import DefaultAzureCredential

from app.config import settings
from app.voicelive.runtime import build_phase_session_request

logger = logging.getLogger(__name__)


def _model_requires_explicit_response_create(model_name: str | None) -> bool:
    """Return whether a model needs an explicit response.create after user turns."""
    if not model_name:
        return False

    return "realtime" not in model_name.lower()


def _encode_audio_delta(audio_delta: Any) -> str:
    """Normalize Voice Live audio deltas to the frontend's base64 PCM16 payload."""
    if isinstance(audio_delta, str):
        return audio_delta

    if isinstance(audio_delta, memoryview):
        audio_delta = audio_delta.tobytes()

    if isinstance(audio_delta, (bytes, bytearray)):
        return base64.b64encode(audio_delta).decode("ascii")

    raise TypeError(f"Unsupported audio delta payload: {type(audio_delta).__name__}")


def _voice_name_from_session(session: Any) -> str | None:
    """Extract a displayable voice name from a session payload."""
    voice = getattr(session, "voice", None)
    if voice is None:
        return None

    if isinstance(voice, dict):
        return voice.get("name")

    return getattr(voice, "name", None)


class VoiceLiveSession:
    """Manages WebSocket connection to Azure Voice Live API."""

    def __init__(self, frontend_ws):
        self.frontend_ws = frontend_ws
        self.voice_live_ws: Optional[VoiceLiveConnection] = None
        self._connection_context = None
        self._credential: Optional[AsyncTokenCredential | AzureKeyCredential] = None
        self._last_requested_session_model: str | None = None
        self._active_session_model: str | None = settings.azure_voicelive_model
        self._active_session_voice: str = settings.azure_voicelive_voice
        self.running = False
        self._tasks = []

    def _build_default_response_create_params(self) -> ResponseCreateParams:
        """Build an explicit response request for models that do not auto-start audio output."""
        return ResponseCreateParams(
            commit=True,
            cancel_previous=True,
            modalities=[Modality.TEXT, Modality.AUDIO],
            voice=AzureStandardVoice(name=self._active_session_voice),
            output_audio_format=OutputAudioFormat.PCM16,
        )

    def _create_background_task(self, coroutine: Any, label: str) -> None:
        """Run a coroutine without blocking the Voice Live event loop."""
        task = asyncio.create_task(coroutine)
        self._tasks.append(task)

        def _cleanup(done_task: asyncio.Task) -> None:
            try:
                self._tasks.remove(done_task)
            except ValueError:
                pass

            if done_task.cancelled():
                return

            exc = done_task.exception()
            if exc is not None:
                logger.error("Background task failed: %s", label, exc_info=exc)

        task.add_done_callback(_cleanup)

    async def connect(self):
        """Connect to Voice Live API using the official async SDK."""
        self._credential = self._build_credential()
        self._connection_context = connect(
            endpoint=settings.voice_live_endpoint,
            credential=self._credential,
            model=settings.azure_voicelive_model,
            api_version=settings.azure_voicelive_api_version,
        )

        logger.info("Connecting to Voice Live API...")
        self.voice_live_ws = await self._connection_context.__aenter__()
        logger.info("Connected to Voice Live API")

        # Send initial session configuration
        await self._send_initial_session()

    def _build_credential(self) -> AsyncTokenCredential | AzureKeyCredential:
        """Create the Voice Live credential from settings."""
        if settings.azure_voicelive_api_key:
            return AzureKeyCredential(settings.azure_voicelive_api_key)

        logger.info("AZURE_VOICELIVE_API_KEY not set, using DefaultAzureCredential")
        return DefaultAzureCredential()

    async def _send_initial_session(self):
        """Send initial session configuration."""
        from app.phases import PHASES

        initial_phase = "triage"
        phase_config = PHASES[initial_phase]

        session_config = {
            "type": "session.update",
            "session": build_phase_session_request(initial_phase, phase_config["instructions"]),
        }

        await self.send(session_config)
        logger.info("Sent initial session configuration")

    async def send(self, event: dict):
        """Send event to Voice Live API."""
        if self.voice_live_ws:
            event_type = event.get("type")
            if event_type == "session.update":
                session = event.get("session", {})
                self._last_requested_session_model = getattr(session, "model", None)
                await self.voice_live_ws.session.update(session=session)
                return

            if event_type == "response.create":
                await self.voice_live_ws.response.create(
                    response=event.get("response"),
                    event_id=event.get("event_id"),
                )
                return

            if event_type == "response.cancel":
                await self.voice_live_ws.response.cancel(
                    response_id=event.get("response_id"),
                    event_id=event.get("event_id"),
                )
                return

            if event_type == "input_audio_buffer.append":
                await self.voice_live_ws.input_audio_buffer.append(audio=event["audio"])
                return

            await self.voice_live_ws.send(event)

    async def send_to_frontend(self, event: dict):
        """Send event to frontend."""
        if self.frontend_ws:
            await self.frontend_ws.send_json(event)

    async def send_audio_to_voice_live(self, audio_base64: str):
        """Send audio chunk to Voice Live API."""
        if self.voice_live_ws:
            await self.voice_live_ws.input_audio_buffer.append(audio=audio_base64)

    async def handle_voice_live_events(self, phase_router, context_manager, oob_subagent):
        """Handle events from Voice Live API."""
        try:
            async for event in self.voice_live_ws:
                await self._dispatch_event(event, phase_router, context_manager, oob_subagent)
        except Exception as e:
            if "closed" in str(e).lower():
                logger.info("Voice Live connection closed")
            else:
                logger.error(f"Error handling Voice Live events: {e}", exc_info=True)

    async def _dispatch_event(self, event: Any, phase_router, context_manager, oob_subagent):
        """Dispatch Voice Live event to appropriate handler."""
        event_type = getattr(event, "type", "")
        event_type_value = getattr(event_type, "value", event_type)

        try:
            if event_type_value == ServerEventType.SESSION_CREATED.value:
                logger.info("Session created")

            elif event_type_value == ServerEventType.SESSION_UPDATED.value:
                session = getattr(event, "session", None)
                session_model = getattr(session, "model", None)
                session_voice = _voice_name_from_session(session)
                if session_model:
                    self._active_session_model = session_model
                if session_voice:
                    self._active_session_voice = session_voice
                logger.info(
                    "Session updated: model=%s voice=%s",
                    session_model or "<unchanged>",
                    session_voice or "<unchanged>",
                )
                if (
                    self._last_requested_session_model
                    and session_model
                    and session_model != self._last_requested_session_model
                ):
                    logger.warning(
                        "Requested session model %s but service kept %s. "
                        "Voice/tools/instructions may have updated while model stayed fixed.",
                        self._last_requested_session_model,
                        session_model,
                    )
                await self.send_to_frontend({"type": "session_ready"})
                await self.send_to_frontend({
                    "type": "session_updated",
                    "model": session_model,
                    "voice": session_voice,
                })

            elif event_type_value == ServerEventType.INPUT_AUDIO_BUFFER_SPEECH_STARTED.value:
                logger.debug("Speech started")
                await self.send_to_frontend({"type": "speech_started"})

            elif event_type_value == ServerEventType.INPUT_AUDIO_BUFFER_SPEECH_STOPPED.value:
                logger.debug("Speech stopped")
                await self.send_to_frontend({"type": "speech_stopped"})

            elif (
                event_type_value
                == ServerEventType.CONVERSATION_ITEM_INPUT_AUDIO_TRANSCRIPTION_COMPLETED.value
            ):
                transcript = getattr(event, "transcript", "")
                item_id = getattr(event, "item_id", "")
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

                if _model_requires_explicit_response_create(self._active_session_model):
                    logger.info(
                        "Triggering explicit response.create for non-realtime model=%s",
                        self._active_session_model,
                    )
                    await self.send({
                        "type": "response.create",
                        "response": self._build_default_response_create_params(),
                    })

            elif event_type_value == ServerEventType.RESPONSE_AUDIO_TRANSCRIPT_DELTA.value:
                delta = getattr(event, "delta", "")
                item_id = getattr(event, "item_id", "")
                await self.send_to_frontend({
                    "type": "transcript_delta",
                    "role": "assistant",
                    "delta": delta,
                    "item_id": item_id,
                })

            elif event_type_value == ServerEventType.RESPONSE_AUDIO_TRANSCRIPT_DONE.value:
                transcript = getattr(event, "transcript", "")
                item_id = getattr(event, "item_id", "")
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

            elif event_type_value == ServerEventType.RESPONSE_AUDIO_DELTA.value:
                audio_delta = getattr(event, "delta", "")
                await self.send_to_frontend({
                    "type": "audio",
                    "data": _encode_audio_delta(audio_delta),
                })

            elif event_type_value == ServerEventType.CONVERSATION_ITEM_CREATED.value:
                item = getattr(event, "item", None)
                if item and getattr(item, "type", "") == "function_call":
                    await phase_router.handle_function_call({
                        "name": getattr(item, "name", ""),
                        "call_id": getattr(item, "call_id", ""),
                        "id": getattr(item, "id", ""),
                    })

            elif event_type_value == ServerEventType.RESPONSE_FUNCTION_CALL_ARGUMENTS_DONE.value:
                self._create_background_task(
                    phase_router.handle_function_call_arguments_done({
                        "call_id": getattr(event, "call_id", ""),
                        "arguments": getattr(event, "arguments", "{}"),
                        "item_id": getattr(event, "item_id", ""),
                    }),
                    label="handle_function_call_arguments_done",
                )

            elif event_type_value == ServerEventType.RESPONSE_DONE.value:
                response = getattr(event, "response", None)
                if oob_subagent.handle_response_done(event):
                    return

                response_id = getattr(response, "id", None)
                response_status = getattr(response, "status", None)
                status_details = getattr(response, "status_details", None)
                if response_status and str(response_status).lower() != "completed":
                    logger.warning(
                        "Voice Live response done with status=%s id=%s details=%s",
                        response_status,
                        response_id,
                        status_details,
                    )

                usage = getattr(response, "usage", None)

                # Update token usage
                if usage:
                    context_manager.update_usage(
                        prompt_tokens=getattr(usage, "input_tokens", 0) or 0,
                        completion_tokens=getattr(usage, "output_tokens", 0) or 0,
                    )

                async def _maybe_summarize_in_background() -> None:
                    summarized = await context_manager.maybe_summarize(self, oob_subagent)
                    if summarized:
                        await self.send_to_frontend({
                            "type": "summary_executed",
                            "tokens": context_manager.ctx.cumulative_tokens,
                        })
                        await self.send_to_frontend(
                            context_manager.build_frontend_context_snapshot(
                                phase_router.current_phase
                            )
                        )

                self._create_background_task(
                    _maybe_summarize_in_background(),
                    label="maybe_summarize",
                )

            elif event_type_value == "warning":
                warning = getattr(event, "warning", None)
                logger.warning("Voice Live warning: %s", getattr(warning, "message", warning))

            elif event_type_value == "error":
                error = getattr(event, "error", None)
                error_msg = getattr(error, "message", "Unknown error")
                logger.error(f"Voice Live error: {error_msg}")
                await self.send_to_frontend({"type": "error", "message": error_msg})

            else:
                logger.debug("Unhandled Voice Live event: %s", event_type_value)

        except Exception as e:
            logger.error(f"Error dispatching event {event_type_value}: {e}", exc_info=True)

    async def close(self):
        """Close Voice Live connection."""
        for task in list(self._tasks):
            task.cancel()
        if self._tasks:
            await asyncio.gather(*self._tasks, return_exceptions=True)
        self._tasks.clear()

        if self._connection_context is not None:
            await self._connection_context.__aexit__(None, None, None)
            self._connection_context = None
            self.voice_live_ws = None

        if isinstance(self._credential, DefaultAzureCredential):
            await self._credential.close()
        self._credential = None
        self.running = False
