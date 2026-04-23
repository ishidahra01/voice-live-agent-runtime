"""Tests for ContextManager."""

import json
import os
from unittest.mock import AsyncMock

import pytest

from app.context.manager import ContextManager


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_cm(call_id: str = "test-call", threshold: int = 8000) -> ContextManager:
    return ContextManager(call_id=call_id, summary_threshold=threshold)


# ---------------------------------------------------------------------------
# record_utterance
# ---------------------------------------------------------------------------


class TestRecordUtterance:
    def test_adds_to_utterances(self):
        cm = _make_cm()
        cm.record_utterance("user", "hello", "item_1", "triage")

        assert len(cm.ctx.utterances) == 1
        u = cm.ctx.utterances[0]
        assert u.role == "user"
        assert u.text == "hello"
        assert u.item_id == "item_1"
        assert u.phase == "triage"

    def test_tracks_item_ids_by_phase(self):
        cm = _make_cm()
        cm.record_utterance("user", "a", "id1", "triage")
        cm.record_utterance("assistant", "b", "id2", "triage")
        cm.record_utterance("user", "c", "id3", "identity")

        assert cm.ctx.vl_item_ids_by_phase["triage"] == ["id1", "id2"]
        assert cm.ctx.vl_item_ids_by_phase["identity"] == ["id3"]


# ---------------------------------------------------------------------------
# record_tool_call
# ---------------------------------------------------------------------------


class TestRecordToolCall:
    def test_adds_to_tool_calls(self):
        cm = _make_cm()
        cm.record_tool_call(
            name="verify_customer",
            args={"customer_id": "12345678"},
            result={"verified": True},
            call_id="c1",
            item_id="i1",
            phase="identity",
            duration_ms=42,
        )

        assert len(cm.ctx.tool_calls) == 1
        tc = cm.ctx.tool_calls[0]
        assert tc.name == "verify_customer"
        assert tc.duration_ms == 42


# ---------------------------------------------------------------------------
# record_phase_transition
# ---------------------------------------------------------------------------


class TestRecordPhaseTransition:
    def test_adds_to_phase_history_and_updates_current_phase(self):
        cm = _make_cm()
        assert cm.current_phase == "triage"

        cm.record_phase_transition("triage", "identity", "start_identity_verification", {"a": 1})

        assert len(cm.ctx.phase_history) == 1
        assert cm.ctx.phase_history[0].from_phase == "triage"
        assert cm.ctx.phase_history[0].to_phase == "identity"
        assert cm.current_phase == "identity"


# ---------------------------------------------------------------------------
# update_usage
# ---------------------------------------------------------------------------


class TestUpdateUsage:
    def test_accumulates_tokens(self):
        cm = _make_cm()
        assert cm.ctx.cumulative_tokens == 0

        cm.update_usage(100, 50)
        assert cm.ctx.cumulative_tokens == 150

        cm.update_usage(200, 100)
        assert cm.ctx.cumulative_tokens == 450


# ---------------------------------------------------------------------------
# maybe_summarize
# ---------------------------------------------------------------------------


class TestMaybeSummarize:
    async def test_returns_false_below_threshold(self):
        cm = _make_cm(threshold=8000)
        cm.ctx.cumulative_tokens = 100
        oob = AsyncMock()
        session = AsyncMock()

        result = await cm.maybe_summarize(session, oob)
        assert result is False
        oob.run.assert_not_called()

    async def test_calls_oob_when_above_threshold(self):
        cm = _make_cm(threshold=100)
        cm.ctx.cumulative_tokens = 200
        # Need enough utterances so the slice has >= 3 items
        for i in range(10):
            cm.record_utterance("user", f"msg {i}", f"id_{i}", "triage")

        oob = AsyncMock()
        oob.run = AsyncMock(return_value="summary text")
        session = AsyncMock()

        result = await cm.maybe_summarize(session, oob)
        assert result is True
        oob.run.assert_called_once()
        assert cm.ctx.vars["conversation_summary"] == "summary text"

    async def test_deletes_old_items_via_session(self):
        """Verify conversation.item.delete is sent for old utterances."""
        cm = _make_cm(threshold=100)
        cm.ctx.cumulative_tokens = 200
        for i in range(10):
            cm.record_utterance("user", f"msg {i}", f"id_{i}", "triage")

        oob = AsyncMock()
        oob.run = AsyncMock(return_value="summary text")
        session = AsyncMock()

        await cm.maybe_summarize(session, oob)

        # Old items (first 4 of 10, since we keep last 6) should be deleted
        delete_calls = [
            c for c in session.send.call_args_list
            if c[0][0].get("type") == "conversation.item.delete"
        ]
        assert len(delete_calls) == 4
        deleted_ids = {c[0][0]["item_id"] for c in delete_calls}
        assert deleted_ids == {"id_0", "id_1", "id_2", "id_3"}

    async def test_reinjects_summary_as_system_message(self):
        """Verify summary is re-injected via conversation.item.create."""
        cm = _make_cm(threshold=100)
        cm.ctx.cumulative_tokens = 200
        for i in range(10):
            cm.record_utterance("user", f"msg {i}", f"id_{i}", "triage")

        oob = AsyncMock()
        oob.run = AsyncMock(return_value="summary text")
        session = AsyncMock()

        await cm.maybe_summarize(session, oob)

        # A system message should be created at root
        create_calls = [
            c for c in session.send.call_args_list
            if c[0][0].get("type") == "conversation.item.create"
        ]
        assert len(create_calls) == 1
        item = create_calls[0][0][0]["item"]
        assert item["type"] == "message"
        assert item["role"] == "system"
        assert "summary text" in item["content"][0]["text"]


# ---------------------------------------------------------------------------
# prepare_handoff
# ---------------------------------------------------------------------------


class TestPrepareHandoff:
    async def test_extracts_customer_info_from_tool_result(self):
        cm = _make_cm()
        cm.record_utterance("user", "hi", "id1", "triage")

        oob = AsyncMock()
        oob.run = AsyncMock(return_value="handoff summary")
        session = AsyncMock()

        tool_result = {
            "customer_name": "山田太郎",
            "plan": "プレミアム",
            "customer_id": "12345678",
        }

        vars_dict = await cm.prepare_handoff(session, oob, "triage", "identity", tool_result)

        assert vars_dict["customer_name"] == "山田太郎"
        assert vars_dict["customer_plan"] == "プレミアム"
        assert vars_dict["customer_id"] == "12345678"
        assert "triage_summary" in vars_dict

    async def test_deletes_old_phase_items(self):
        """Verify old phase items are deleted via conversation.item.delete."""
        cm = _make_cm()
        cm.record_utterance("user", "hi", "id1", "triage")
        cm.record_utterance("assistant", "hello", "id2", "triage")
        cm.record_utterance("user", "help me", "id3", "triage")

        oob = AsyncMock()
        oob.run = AsyncMock(return_value="handoff summary")
        session = AsyncMock()

        await cm.prepare_handoff(session, oob, "triage", "identity", {})

        delete_calls = [
            c for c in session.send.call_args_list
            if c[0][0].get("type") == "conversation.item.delete"
        ]
        assert len(delete_calls) == 3
        deleted_ids = {c[0][0]["item_id"] for c in delete_calls}
        assert deleted_ids == {"id1", "id2", "id3"}

    async def test_injects_handoff_summary_as_system_message(self):
        """Verify handoff summary is injected via conversation.item.create."""
        cm = _make_cm()
        cm.record_utterance("user", "hi", "id1", "triage")

        oob = AsyncMock()
        oob.run = AsyncMock(return_value="handoff summary")
        session = AsyncMock()

        await cm.prepare_handoff(session, oob, "triage", "identity", {})

        create_calls = [
            c for c in session.send.call_args_list
            if c[0][0].get("type") == "conversation.item.create"
        ]
        assert len(create_calls) == 1
        item = create_calls[0][0][0]["item"]
        assert item["type"] == "message"
        assert item["role"] == "system"
        assert "handoff summary" in item["content"][0]["text"]


# ---------------------------------------------------------------------------
# dump
# ---------------------------------------------------------------------------


class TestDump:
    def test_creates_valid_json_file(self, tmp_path):
        cm = _make_cm()
        cm.record_utterance("user", "hello", "id1", "triage")
        cm.record_tool_call("end_call", {"summary": "done"}, {"action": "end"}, "c1", "i1", "triage", 10)
        cm.record_phase_transition("triage", "identity", "start_identity_verification", {})

        path = str(tmp_path / "dump.json")
        cm.dump(path)

        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)

        assert data["call_id"] == "test-call"
        assert len(data["utterances"]) == 1
        assert len(data["tool_calls"]) == 1
        assert len(data["phase_history"]) == 1
