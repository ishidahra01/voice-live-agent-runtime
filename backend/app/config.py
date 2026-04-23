"""Configuration management for Voice Live Agent."""

import os
from typing import Optional
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
    azure_openai_endpoint: str
    azure_openai_api_key: str
    azure_openai_deployment: str = "gpt-realtime"

    # Backend
    backend_host: str = "0.0.0.0"
    backend_port: int = 8000
    log_level: str = "INFO"

    # Context Management
    summary_token_threshold: int = 8000
    max_conversation_items: int = 50

    @property
    def voice_live_endpoint(self) -> str:
        """Construct Voice Live WebSocket endpoint."""
        base = self.azure_openai_endpoint.rstrip("/")
        return f"{base}/openai/realtime?api-version=2024-10-01-preview&deployment={self.azure_openai_deployment}"


settings = Settings()
