"""Tests for PhaseRouter."""

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

import app.tools  # noqa: F401 – importing registers tool functions
from app.phases.router import PhaseRouter
from app.phases.transitions import TERMINAL_TOOLS, TRANSITIONS


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_mocks():
    """Return (session, context_manager, oob_subagent) mocks."""
    session = AsyncMock()
    session.send = AsyncMock()
    session.send_to_frontend = AsyncMock()

    ctx = MagicMock()
    ctx.record_tool_call = MagicMock()
    ctx.record_phase_transition = MagicMock()
    ctx.prepare_handoff = AsyncMock(return_value={})

    oob = AsyncMock()
    return session, ctx, oob


def _make_function_call_item(name: str, call_id: str, item_id: str = "item_1") -> dict:
    return {"name": name, "call_id": call_id, "id": item_id}


def _make_args_done_event(call_id: str, arguments: dict | None = None) -> dict:
    return {"call_id": call_id, "arguments": json.dumps(arguments or {})}


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestPhaseRouterInit:
    def test_initial_phase_is_triage(self):
        session, ctx, oob = _make_mocks()
        router = PhaseRouter(session, ctx, oob)
        assert router.current_phase == "triage"


class TestHandleFunctionCall:
    async def test_stores_pending_call(self):
        session, ctx, oob = _make_mocks()
        router = PhaseRouter(session, ctx, oob)

        item = _make_function_call_item("verify_customer", "call_1")
        await router.handle_function_call(item)

        assert "call_1" in router._pending_tool_calls
        assert router._pending_tool_calls["call_1"]["name"] == "verify_customer"


class TestHandleFunctionCallArgumentsDone:
    async def test_executes_tool_and_sends_result(self):
        session, ctx, oob = _make_mocks()
        router = PhaseRouter(session, ctx, oob)

        item = _make_function_call_item("start_identity_verification", "call_1")
        await router.handle_function_call(item)
        event = _make_args_done_event("call_1")
        await router.handle_function_call_arguments_done(event)

        # Tool result should have been sent via session.send (conversation.item.create + response.create)
        assert session.send.call_count >= 2
        # Tool call should be recorded in context
        ctx.record_tool_call.assert_called_once()

    async def test_transition_triage_to_identity(self):
        session, ctx, oob = _make_mocks()
        ctx.prepare_handoff = AsyncMock(return_value={"some": "vars"})
        router = PhaseRouter(session, ctx, oob)
        assert router.current_phase == "triage"

        item = _make_function_call_item("start_identity_verification", "call_1")
        await router.handle_function_call(item)
        await router.handle_function_call_arguments_done(_make_args_done_event("call_1"))

        assert router.current_phase == "identity"
        ctx.record_phase_transition.assert_called_once()
        args = ctx.record_phase_transition.call_args
        assert args.kwargs["from_phase"] == "triage"
        assert args.kwargs["to_phase"] == "identity"

    async def test_transition_identity_to_business_verified(self):
        session, ctx, oob = _make_mocks()
        ctx.prepare_handoff = AsyncMock(return_value={"customer_name": "テスト"})
        router = PhaseRouter(session, ctx, oob)
        router.current_phase = "identity"

        item = _make_function_call_item("verify_customer", "call_2")
        await router.handle_function_call(item)
        # Valid 8-digit customer ID that exists in mock DB
        await router.handle_function_call_arguments_done(
            _make_args_done_event("call_2", {"customer_id": "12345678"})
        )

        assert router.current_phase == "business"

    async def test_no_transition_identity_verify_customer_failed(self):
        session, ctx, oob = _make_mocks()
        router = PhaseRouter(session, ctx, oob)
        router.current_phase = "identity"

        item = _make_function_call_item("verify_customer", "call_3")
        await router.handle_function_call(item)
        # Non-existent customer
        await router.handle_function_call_arguments_done(
            _make_args_done_event("call_3", {"customer_id": "00000000"})
        )

        assert router.current_phase == "identity"
        ctx.record_phase_transition.assert_not_called()

    async def test_transition_to_escalation(self):
        session, ctx, oob = _make_mocks()
        ctx.prepare_handoff = AsyncMock(return_value={})
        router = PhaseRouter(session, ctx, oob)
        assert router.current_phase == "triage"

        item = _make_function_call_item("escalate_to_human", "call_4")
        await router.handle_function_call(item)
        await router.handle_function_call_arguments_done(
            _make_args_done_event("call_4", {"reason": "angry customer"})
        )

        assert router.current_phase == "escalation"

    async def test_terminal_tool_end_call_triggers_session_end(self):
        session, ctx, oob = _make_mocks()
        router = PhaseRouter(session, ctx, oob)

        item = _make_function_call_item("end_call", "call_5")
        await router.handle_function_call(item)
        await router.handle_function_call_arguments_done(
            _make_args_done_event("call_5", {"summary": "resolved"})
        )

        # session_end should be sent to frontend
        frontend_calls = [
            c.args[0] for c in session.send_to_frontend.call_args_list
        ]
        session_end_msgs = [m for m in frontend_calls if m.get("type") == "session_end"]
        assert len(session_end_msgs) == 1
        assert session_end_msgs[0]["reason"] == "end_call"

    async def test_unknown_call_id_is_ignored(self):
        session, ctx, oob = _make_mocks()
        router = PhaseRouter(session, ctx, oob)

        event = _make_args_done_event("unknown_call_id")
        await router.handle_function_call_arguments_done(event)

        session.send.assert_not_called()
        ctx.record_tool_call.assert_not_called()
