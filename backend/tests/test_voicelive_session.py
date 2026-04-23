"""Tests for VoiceLiveSession."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

from azure.ai.voicelive.models import Modality, OutputAudioFormat, RequestSession, ServerEventType
from azure.core.credentials import AzureKeyCredential

from app.config import settings
from app.config import settings
from app.voicelive.session import VoiceLiveSession


class FakeDefaultAzureCredential:
    async def close(self):
        return None


class TestVoiceLiveSessionCredentials:
    def test_uses_api_key_when_configured(self):
        session = VoiceLiveSession(frontend_ws=None)

        original_api_key = settings.azure_voicelive_api_key
        settings.azure_voicelive_api_key = "test-key"
        try:
            credential = session._build_credential()
        finally:
            settings.azure_voicelive_api_key = original_api_key

        assert isinstance(credential, AzureKeyCredential)

    def test_falls_back_to_default_credential_when_api_key_missing(self, monkeypatch):
        session = VoiceLiveSession(frontend_ws=None)

        original_api_key = settings.azure_voicelive_api_key
        settings.azure_voicelive_api_key = None
        monkeypatch.setattr(
            "app.voicelive.session.DefaultAzureCredential",
            FakeDefaultAzureCredential,
        )

        try:
            credential = session._build_credential()
        finally:
            settings.azure_voicelive_api_key = original_api_key

        assert isinstance(credential, FakeDefaultAzureCredential)


class TestVoiceLiveSessionSetup:
    async def test_initial_session_uses_request_session_model(self):
        session = VoiceLiveSession(frontend_ws=None)
        session.voice_live_ws = SimpleNamespace(
            session=SimpleNamespace(update=AsyncMock()),
            response=SimpleNamespace(create=AsyncMock(), cancel=AsyncMock()),
            input_audio_buffer=SimpleNamespace(append=AsyncMock()),
            send=AsyncMock(),
        )

        await session._send_initial_session()

        session.voice_live_ws.session.update.assert_awaited_once()
        request_session = session.voice_live_ws.session.update.await_args.kwargs["session"]
        assert isinstance(request_session, RequestSession)
        assert request_session.model == settings.azure_voicelive_model
        assert request_session.voice.as_dict()["name"] == settings.azure_voicelive_voice
        assert request_session.temperature is None
        assert "temperature" not in request_session.as_dict()
        assert request_session.turn_detection.as_dict() == {
            "type": "azure_semantic_vad_multilingual",
            "threshold": 0.5,
            "prefix_padding_ms": 300,
            "speech_duration_ms": 80,
            "silence_duration_ms": 500,
            "remove_filler_words": True,
            "languages": [settings.azure_voicelive_transcription_language],
            "interrupt_response": True,
        }
        assert request_session.input_audio_transcription.as_dict() == {
            "model": settings.azure_voicelive_transcription_model,
            "language": settings.azure_voicelive_transcription_language,
        }

    async def test_audio_delta_bytes_are_base64_encoded_for_frontend(self):
        session = VoiceLiveSession(frontend_ws=None)
        session.send_to_frontend = AsyncMock()

        await session._dispatch_event(
            SimpleNamespace(
                type=SimpleNamespace(value=ServerEventType.RESPONSE_AUDIO_DELTA.value),
                delta=b"\x01\x02\x03\x04",
            ),
            phase_router=SimpleNamespace(current_phase="triage"),
            context_manager=SimpleNamespace(),
            oob_subagent=SimpleNamespace(),
        )

        session.send_to_frontend.assert_awaited_once_with({
            "type": "audio",
            "data": "AQIDBA==",
        })

    async def test_non_realtime_model_triggers_explicit_response_create_after_transcript(self):
        session = VoiceLiveSession(frontend_ws=None)
        session._active_session_model = "gpt-5-nano"
        session._active_session_voice = "ja-JP-NanamiNeural"
        session.send_to_frontend = AsyncMock()
        session.send = AsyncMock()
        context_manager = SimpleNamespace(record_utterance=Mock())

        await session._dispatch_event(
            SimpleNamespace(
                type=SimpleNamespace(
                    value=ServerEventType.CONVERSATION_ITEM_INPUT_AUDIO_TRANSCRIPTION_COMPLETED.value
                ),
                transcript="こんにちは",
                item_id="item-1",
            ),
            phase_router=SimpleNamespace(current_phase="triage"),
            context_manager=context_manager,
            oob_subagent=SimpleNamespace(),
        )

        context_manager.record_utterance.assert_called_once_with(
            role="user",
            text="こんにちは",
            item_id="item-1",
            phase="triage",
        )
        session.send.assert_awaited_once()
        event = session.send.await_args.args[0]
        assert event["type"] == "response.create"
        response = event["response"]
        assert response.commit is True
        assert response.cancel_previous is True
        assert response.modalities == [Modality.TEXT, Modality.AUDIO]
        assert response.output_audio_format == OutputAudioFormat.PCM16
        assert response.voice.as_dict()["name"] == "ja-JP-NanamiNeural"

    async def test_realtime_model_does_not_trigger_explicit_response_create_after_transcript(self):
        session = VoiceLiveSession(frontend_ws=None)
        session._active_session_model = "gpt-realtime"
        session.send_to_frontend = AsyncMock()
        session.send = AsyncMock()
        context_manager = SimpleNamespace(record_utterance=Mock())

        await session._dispatch_event(
            SimpleNamespace(
                type=SimpleNamespace(
                    value=ServerEventType.CONVERSATION_ITEM_INPUT_AUDIO_TRANSCRIPTION_COMPLETED.value
                ),
                transcript="こんにちは",
                item_id="item-1",
            ),
            phase_router=SimpleNamespace(current_phase="triage"),
            context_manager=context_manager,
            oob_subagent=SimpleNamespace(),
        )

        session.send.assert_not_awaited()

    async def test_error_event_is_forwarded_to_frontend(self):
        session = VoiceLiveSession(frontend_ws=None)
        session.send_to_frontend = AsyncMock()

        await session._dispatch_event(
            SimpleNamespace(
                type=SimpleNamespace(value="error"),
                error=SimpleNamespace(message="response.create failed"),
            ),
            phase_router=SimpleNamespace(current_phase="triage"),
            context_manager=SimpleNamespace(),
            oob_subagent=SimpleNamespace(handle_response_done=Mock(return_value=False)),
        )

        session.send_to_frontend.assert_awaited_once_with(
            {"type": "error", "message": "response.create failed"}
        )