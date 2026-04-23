"""Configuration management for Voice Live Agent."""

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # Azure Voice Live API
    azure_voicelive_endpoint: str
    azure_voicelive_api_key: str | None = None
    azure_voicelive_model: str = "gpt-realtime"
    azure_voicelive_structured_model: str = "gpt-5-nano"
    azure_voicelive_api_version: str = "2025-10-01"
    azure_voicelive_voice: str = "ja-JP-NanamiNeural"
    azure_voicelive_structured_voice: str = "ja-JP-KeitaNeural"
    azure_voicelive_transcription_model: str = "azure-speech"
    azure_voicelive_transcription_language: str = "ja-JP"
    azure_summary_endpoint: str | None = None
    azure_summary_api_key: str | None = None
    azure_summary_model: str = "gpt-5-nano"
    azure_summary_api_version: str = "2024-10-21"
    azure_summary_temperature: float = 0.2
    azure_summary_max_tokens: int = 300
    azure_summary_max_completion_tokens: int | None = Field(default=None)
    azure_summary_timeout_seconds: float = 8.0

    # Backend
    backend_host: str = "0.0.0.0"
    backend_port: int = 8000
    log_level: str = "INFO"

    # Context Management
    summary_token_threshold: int = 8000
    max_conversation_items: int = 50

    @property
    def voice_live_endpoint(self) -> str:
        """Return the normalized Voice Live resource endpoint for the SDK."""
        endpoint = self.azure_voicelive_endpoint.rstrip("/")
        if endpoint.startswith("wss://"):
            return "https://" + endpoint[len("wss://") :]
        if endpoint.startswith("ws://"):
            return "http://" + endpoint[len("ws://") :]
        return endpoint

    @property
    def summary_endpoint(self) -> str:
        """Return the normalized Foundry/Azure OpenAI endpoint for summarization."""
        endpoint = (self.azure_summary_endpoint or self.azure_voicelive_endpoint).rstrip("/")
        if endpoint.startswith("wss://"):
            return "https://" + endpoint[len("wss://") :]
        if endpoint.startswith("ws://"):
            return "http://" + endpoint[len("ws://") :]
        return endpoint

    @property
    def summary_base_url(self) -> str:
        """Return the OpenAI-compatible base URL for summary generation."""
        endpoint = self.summary_endpoint
        if endpoint.endswith("/openai/v1"):
            return endpoint
        return endpoint + "/openai/v1"

    @property
    def summary_output_tokens(self) -> int:
        """Return the configured max output tokens for the summary model."""
        return self.azure_summary_max_completion_tokens or self.azure_summary_max_tokens


settings = Settings()
