"""Tests for Voice Live configuration."""

from app.config import Settings


class TestVoiceLiveSettings:
    def test_normalizes_https_endpoint(self):
        settings = Settings(
            azure_voicelive_endpoint="https://example.services.ai.azure.com/",
            azure_voicelive_api_key="test-key",
        )

        assert settings.voice_live_endpoint == "https://example.services.ai.azure.com"

    def test_normalizes_websocket_endpoint_scheme(self):
        settings = Settings(
            azure_voicelive_endpoint="wss://example.services.ai.azure.com",
            azure_voicelive_api_key="test-key",
        )

        assert settings.voice_live_endpoint == "https://example.services.ai.azure.com"

    def test_prefers_summary_max_completion_tokens_when_set(self):
        settings = Settings(
            azure_voicelive_endpoint="https://example.services.ai.azure.com/",
            azure_voicelive_api_key="test-key",
            azure_summary_max_tokens=300,
            azure_summary_max_completion_tokens=120,
        )

        assert settings.summary_output_tokens == 120