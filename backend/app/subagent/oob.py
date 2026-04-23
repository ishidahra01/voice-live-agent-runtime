"""Out-of-Band Subagent for auxiliary inference tasks."""

import asyncio
import logging
from uuid import uuid4
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.voicelive.session import VoiceLiveSession

logger = logging.getLogger(__name__)


class OOBSubagent:
    """Handles out-of-band responses for auxiliary tasks."""

    def __init__(self, session: "VoiceLiveSession"):
        self.session = session
        self._pending: dict[str, asyncio.Future] = {}

    async def run(
        self,
        purpose: str,
        instructions: str,
        input_items: list[dict] | None = None,
        output_modalities: list[str] = ["text"],
        timeout_s: float = 15.0,
    ) -> str:
        """Execute an out-of-band response and return the result text.

        Args:
            purpose: Description of the task (for logging)
            instructions: Instructions for the model
            input_items: Optional input items to include
            output_modalities: Output modalities (default: ["text"])
            timeout_s: Timeout in seconds

        Returns:
            The text response from the model
        """
        oob_id = str(uuid4())
        future = asyncio.get_event_loop().create_future()
        self._pending[oob_id] = future

        event = {
            "type": "response.create",
            "response": {
                "conversation": "none",
                "output_modalities": output_modalities,
                "instructions": instructions,
                "metadata": {"purpose": purpose, "oob_id": oob_id},
            },
        }

        if input_items:
            event["response"]["input"] = input_items

        logger.debug(f"Sending OOB request: {purpose} (id={oob_id})")
        await self.session.send(event)

        try:
            result = await asyncio.wait_for(future, timeout=timeout_s)
            logger.debug(f"OOB request completed: {purpose} (id={oob_id})")
            return result
        except asyncio.TimeoutError:
            self._pending.pop(oob_id, None)
            logger.error(f"OOB request timeout: {purpose} (id={oob_id})")
            raise

    def handle_response_done(self, event: dict) -> None:
        """Handle response.done event for OOB responses."""
        metadata = event.get("response", {}).get("metadata", {})
        oob_id = metadata.get("oob_id")

        if oob_id and oob_id in self._pending:
            future = self._pending.pop(oob_id)
            text = self._extract_text_from_response(event["response"])
            future.set_result(text)

    def _extract_text_from_response(self, response: dict) -> str:
        """Extract text from response output."""
        outputs = response.get("output", [])
        for output in outputs:
            if output.get("type") == "message":
                content = output.get("content", [])
                for item in content:
                    if item.get("type") == "text":
                        return item.get("text", "")
        return ""
