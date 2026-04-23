"""Out-of-band summarization client backed by a Foundry/Azure OpenAI model."""

import asyncio
import logging
from typing import TYPE_CHECKING, Any

from azure.identity import DefaultAzureCredential, get_bearer_token_provider
from openai import OpenAI

from app.config import settings

if TYPE_CHECKING:
    from app.voicelive.session import VoiceLiveSession

logger = logging.getLogger(__name__)


class OOBSubagent:
    """Handles auxiliary summaries using a separate Foundry/Azure OpenAI request path."""

    def __init__(self, session: "VoiceLiveSession"):
        self.session = session
        self._credential: DefaultAzureCredential | None = None
        self._client: OpenAI | None = None

    async def run(
        self,
        purpose: str,
        instructions: str,
        input_items: list[dict] | None = None,
        output_modalities: list[str] | None = None,
        timeout_s: float = 15.0,
    ) -> str:
        """Execute an out-of-band summary request and return the result text.

        Args:
            purpose: Description of the task (for logging)
            instructions: Instructions for the model
            input_items: Optional input items to include
            output_modalities: Output modalities (default: ["text"])
            timeout_s: Timeout in seconds

        Returns:
            The text response from the model
        """
        del output_modalities

        logger.debug("Sending summary request: %s", purpose)
        result = await self._request_summary(
            purpose=purpose,
            instructions=instructions,
            input_items=input_items,
            timeout_s=timeout_s,
        )
        logger.debug("Summary request completed: %s", purpose)
        return result.strip()

    def handle_response_done(self, event: Any) -> bool:
        """No-op for the decoupled HTTP summarization path."""
        del event
        return False

    async def close(self) -> None:
        """Release any resources used by the summarizer."""
        if self._client is not None:
            self._client.close()
            self._client = None

        if self._credential is not None:
            self._credential.close()
            self._credential = None

    async def _request_summary(
        self,
        purpose: str,
        instructions: str,
        input_items: list[dict] | None,
        timeout_s: float,
    ) -> str:
        client = self._get_client()
        request_timeout = min(timeout_s, settings.azure_summary_timeout_seconds)
        completion_kwargs = self._build_completion_kwargs(
            purpose=purpose,
            instructions=instructions,
            input_items=input_items,
            timeout=request_timeout,
        )

        completion = await asyncio.to_thread(
            client.chat.completions.create,
            **completion_kwargs,
        )

        try:
            content = completion.choices[0].message.content
        except (AttributeError, IndexError) as exc:
            logger.error("Unexpected summary response payload for %s: %s", purpose, completion)
            raise RuntimeError("Unexpected summary response payload") from exc

        if isinstance(content, str):
            return content

        if isinstance(content, list):
            parts = []
            for item in content:
                text = getattr(item, "text", None)
                if text:
                    parts.append(text)
            return "\n".join(parts)

        raise RuntimeError("Summary response did not contain text content")

    def _build_completion_kwargs(
        self,
        purpose: str,
        instructions: str,
        input_items: list[dict] | None,
        timeout: float,
    ) -> dict[str, Any]:
        model = settings.azure_summary_model
        kwargs: dict[str, Any] = {
            "model": model,
            "messages": self._build_messages(purpose, instructions, input_items),
            "timeout": timeout,
        }

        if self._is_reasoning_model(model):
            kwargs["max_completion_tokens"] = settings.summary_output_tokens
            reasoning_effort = self._reasoning_effort_for_model(model)
            if reasoning_effort is not None:
                kwargs["reasoning_effort"] = reasoning_effort
            return kwargs

        kwargs["max_tokens"] = settings.summary_output_tokens
        kwargs["temperature"] = settings.azure_summary_temperature
        return kwargs

    def _is_reasoning_model(self, model: str) -> bool:
        normalized = model.lower()
        return normalized.startswith(("gpt-5", "o1", "o3", "o4"))

    def _reasoning_effort_for_model(self, model: str) -> str | None:
        normalized = model.lower()

        if normalized.startswith(("gpt-5.1", "gpt-5.2", "gpt-5.3", "gpt-5.4")):
            return "none"

        if normalized.startswith("gpt-5"):
            return "minimal"

        if normalized.startswith("o1-mini"):
            return None

        return "low"

    def _build_messages(
        self,
        purpose: str,
        instructions: str,
        input_items: list[dict] | None,
    ) -> list[dict[str, str]]:
        messages = [
            {
                "role": "system",
                "content": (
                    "あなたはコンタクトセンター支援用の要約モデルです。"
                    "事実・顧客情報・ツール結果・未解決事項を落とさず、日本語で簡潔かつ構造的に要約してください。"
                ),
            },
            {
                "role": "user",
                "content": f"purpose: {purpose}\n\n{instructions}",
            },
        ]

        serialized_items = self._serialize_input_items(input_items)
        if serialized_items:
            messages.append({"role": "user", "content": serialized_items})

        return messages

    def _serialize_input_items(self, input_items: list[dict] | None) -> str:
        if not input_items:
            return ""

        chunks: list[str] = []
        for item in input_items:
            chunks.append(str(item))
        return "\n".join(chunks)

    def _get_client(self) -> OpenAI:
        if self._client is not None:
            return self._client

        api_key = settings.azure_summary_api_key or settings.azure_voicelive_api_key
        if api_key:
            credential = api_key
        else:
            credential = self._get_token_provider()

        self._client = OpenAI(
            base_url=settings.summary_base_url,
            api_key=credential,
        )
        return self._client

    def _get_token_provider(self):
        if self._credential is None:
            self._credential = DefaultAzureCredential()
        return get_bearer_token_provider(
            self._credential,
            "https://ai.azure.com/.default",
        )

    def _extract_text_from_response(self, response: Any) -> str:
        """Extract text from response output."""
        outputs = self._get_value(response, "output", [])
        for output in outputs:
            if self._get_value(output, "type", "") == "message":
                content = self._get_value(output, "content", [])
                for item in content:
                    if self._get_value(item, "type", "") == "text":
                        return self._get_value(item, "text", "")
        return ""

    def _get_response(self, event: Any) -> Any:
        if isinstance(event, dict):
            return event.get("response", {})
        return getattr(event, "response", None)

    def _get_value(self, payload: Any, key: str, default: Any) -> Any:
        if isinstance(payload, dict):
            return payload.get(key, default)
        return getattr(payload, key, default)
