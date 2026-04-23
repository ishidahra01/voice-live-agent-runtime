"""Tests for OOBSubagent."""

from unittest.mock import AsyncMock

import pytest

from app.subagent.oob import OOBSubagent


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_session() -> AsyncMock:
    session = AsyncMock()
    session.send = AsyncMock()
    return session


def _make_response_done_event(
    text: str = "result text",
    event_id: str | None = "oob-test",
) -> dict:
    return {
        "event_id": event_id,
        "response": {
            "output": [
                {
                    "type": "message",
                    "content": [{"type": "text", "text": text}],
                }
            ],
        }
    }


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestOOBRun:
    async def test_uses_summary_request(self):
        session = _make_session()
        oob = OOBSubagent(session)

        oob._request_summary = AsyncMock(return_value="ok")

        result = await oob.run(purpose="test", instructions="do something")

        oob._request_summary.assert_awaited_once()
        assert result == "ok"

    async def test_run_propagates_timeout(self):
        session = _make_session()
        oob = OOBSubagent(session)
        oob._request_summary = AsyncMock(side_effect=TimeoutError())

        with pytest.raises(TimeoutError):
            await oob.run(purpose="timeout_test", instructions="will timeout", timeout_s=0.1)


class TestHandleResponseDone:
    async def test_is_noop_for_http_summaries(self):
        session = _make_session()
        oob = OOBSubagent(session)

        handled = oob.handle_response_done(_make_response_done_event())

        assert handled is False

    async def test_builds_messages_with_serialized_input_items(self):
        session = _make_session()
        oob = OOBSubagent(session)

        messages = oob._build_messages(
            purpose="handoff_summary",
            instructions="summarize this",
            input_items=[{"type": "message", "text": "hello"}],
        )

        assert len(messages) == 3
        assert "summarize this" in messages[1]["content"]
        assert "hello" in messages[2]["content"]


class TestRequestSummary:
    def test_summary_base_url_uses_openai_v1_suffix(self):
        session = _make_session()
        oob = OOBSubagent(session)

        assert oob._get_client is not None
        assert oob._serialize_input_items([{"a": 1}]) == "{'a': 1}"

    def test_build_completion_kwargs_for_gpt5_reasoning(self):
        session = _make_session()
        oob = OOBSubagent(session)

        from app.subagent.oob import settings
        original_model = settings.azure_summary_model
        settings.azure_summary_model = "gpt-5-nano"

        try:
            kwargs = oob._build_completion_kwargs(
                purpose="handoff_summary",
                instructions="summarize",
                input_items=None,
                timeout=5,
            )
        finally:
            settings.azure_summary_model = original_model

        assert kwargs["model"]
        assert "max_completion_tokens" in kwargs
        assert "max_tokens" not in kwargs
        assert "temperature" not in kwargs
        assert kwargs["reasoning_effort"] == "minimal"

    def test_reasoning_effort_is_none_for_gpt5_4(self, monkeypatch):
        session = _make_session()
        oob = OOBSubagent(session)

        monkeypatch.setattr("app.subagent.oob.settings.azure_summary_model", "gpt-5.4-nano-1")
        kwargs = oob._build_completion_kwargs(
            purpose="handoff_summary",
            instructions="summarize",
            input_items=None,
            timeout=5,
        )

        assert kwargs["reasoning_effort"] == "none"
        assert "temperature" not in kwargs

    def test_build_completion_kwargs_for_non_reasoning_model(self, monkeypatch):
        session = _make_session()
        oob = OOBSubagent(session)

        monkeypatch.setattr("app.subagent.oob.settings.azure_summary_model", "gpt-4.1-mini")
        kwargs = oob._build_completion_kwargs(
            purpose="handoff_summary",
            instructions="summarize",
            input_items=None,
            timeout=5,
        )

        assert "max_tokens" in kwargs
        assert "temperature" in kwargs
        assert "max_completion_tokens" not in kwargs
