"""Tests for OOBSubagent."""

import asyncio
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


def _make_response_done_event(oob_id: str, text: str = "result text") -> dict:
    return {
        "response": {
            "metadata": {"oob_id": oob_id, "purpose": "test"},
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
    async def test_sends_correct_event_to_session(self):
        session = _make_session()
        oob = OOBSubagent(session)

        async def _capture_and_resolve(*args, **kwargs):
            """Capture the sent event then resolve the pending future."""
            event = args[0]
            oob_id = event["response"]["metadata"]["oob_id"]
            oob.handle_response_done(_make_response_done_event(oob_id, "ok"))

        session.send.side_effect = _capture_and_resolve

        result = await oob.run(purpose="test", instructions="do something")

        session.send.assert_called_once()
        sent = session.send.call_args.args[0]
        assert sent["type"] == "response.create"
        assert sent["response"]["conversation"] == "none"
        assert sent["response"]["instructions"] == "do something"
        assert result == "ok"

    async def test_run_timeout(self):
        session = _make_session()
        oob = OOBSubagent(session)

        with pytest.raises(asyncio.TimeoutError):
            await oob.run(purpose="timeout_test", instructions="will timeout", timeout_s=0.1)

        # After timeout, pending future should be cleaned up
        assert len(oob._pending) == 0


class TestHandleResponseDone:
    async def test_resolves_correct_future(self):
        session = _make_session()
        oob = OOBSubagent(session)

        future = asyncio.get_event_loop().create_future()
        oob._pending["test-id"] = future

        oob.handle_response_done(_make_response_done_event("test-id", "hello"))

        assert future.done()
        assert future.result() == "hello"
        assert "test-id" not in oob._pending

    async def test_ignores_events_without_oob_id(self):
        session = _make_session()
        oob = OOBSubagent(session)

        future = asyncio.get_event_loop().create_future()
        oob._pending["some-id"] = future

        oob.handle_response_done({"response": {"metadata": {}, "output": []}})

        assert not future.done()
        assert "some-id" in oob._pending

    async def test_ignores_unknown_oob_id(self):
        session = _make_session()
        oob = OOBSubagent(session)

        future = asyncio.get_event_loop().create_future()
        oob._pending["my-id"] = future

        oob.handle_response_done(_make_response_done_event("other-id"))

        assert not future.done()
        assert "my-id" in oob._pending


class TestExtractText:
    def test_extracts_text_correctly(self):
        session = _make_session()
        oob = OOBSubagent(session)

        response = {
            "output": [
                {
                    "type": "message",
                    "content": [{"type": "text", "text": "extracted"}],
                }
            ]
        }
        assert oob._extract_text_from_response(response) == "extracted"

    def test_returns_empty_for_no_output(self):
        session = _make_session()
        oob = OOBSubagent(session)
        assert oob._extract_text_from_response({"output": []}) == ""
        assert oob._extract_text_from_response({}) == ""


class TestConcurrentRequests:
    async def test_multiple_concurrent_oob_tracked(self):
        session = _make_session()
        oob = OOBSubagent(session)

        # Create two pending futures manually
        f1 = asyncio.get_event_loop().create_future()
        f2 = asyncio.get_event_loop().create_future()
        oob._pending["id-1"] = f1
        oob._pending["id-2"] = f2

        # Resolve them in reverse order
        oob.handle_response_done(_make_response_done_event("id-2", "second"))
        oob.handle_response_done(_make_response_done_event("id-1", "first"))

        assert f1.result() == "first"
        assert f2.result() == "second"
        assert len(oob._pending) == 0
