"""Phase-aware Voice Live session runtime helpers."""

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
)

from app.config import settings
from app.phases import PHASES
from app.tools import build_tool_schemas


def get_phase_runtime(phase: str) -> dict:
    """Return the runtime policy for a phase."""
    phase_config = PHASES[phase]
    runtime_mode = phase_config.get("runtime_mode", "realtime")

    if runtime_mode == "structured":
        return {
            "mode": runtime_mode,
            "model": settings.azure_voicelive_structured_model,
            "voice": settings.azure_voicelive_structured_voice,
        }

    return {
        "mode": "realtime",
        "model": settings.azure_voicelive_model,
        "voice": settings.azure_voicelive_voice,
    }


def build_phase_session_request(phase: str, instructions: str) -> RequestSession:
    """Build a complete RequestSession for the target phase."""
    phase_config = PHASES[phase]
    runtime = get_phase_runtime(phase)

    return RequestSession(
        model=runtime["model"],
        voice=AzureStandardVoice(name=runtime["voice"]),
        modalities=[Modality.TEXT, Modality.AUDIO],
        input_audio_format=InputAudioFormat.PCM16,
        output_audio_format=OutputAudioFormat.PCM16,
        input_audio_sampling_rate=24000,
        turn_detection=AzureSemanticVadMultilingual(
            threshold=0.5,
            prefix_padding_ms=300,
            speech_duration_ms=80,
            silence_duration_ms=500,
            remove_filler_words=True,
            languages=[settings.azure_voicelive_transcription_language],
            interrupt_response=True,
        ),
        input_audio_noise_reduction=AudioNoiseReduction(
            type="azure_deep_noise_suppression"
        ),
        input_audio_echo_cancellation=AudioEchoCancellation(
            type="server_echo_cancellation"
        ),
        input_audio_transcription=AudioInputTranscriptionOptions(
            model=settings.azure_voicelive_transcription_model,
            language=settings.azure_voicelive_transcription_language,
        ),
        instructions=instructions,
        tools=build_tool_schemas(phase_config["tools"]),
        tool_choice="auto",
        temperature=None,
        max_response_output_tokens="inf",
    )


def build_phase_session_event(phase: str) -> dict:
    """Build a frontend-facing summary of the current phase runtime."""
    phase_config = PHASES[phase]
    runtime = get_phase_runtime(phase)
    return {
        "type": "session_config",
        "phase": phase,
        "mode": runtime["mode"],
        "model": runtime["model"],
        "voice": runtime["voice"],
        "tools": phase_config["tools"],
    }