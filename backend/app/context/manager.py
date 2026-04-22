"""Context manager for conversation history and summarization."""

from dataclasses import dataclass, field
from datetime import datetime
from typing import TYPE_CHECKING
import json
import logging

if TYPE_CHECKING:
    from app.voicelive.session import VoiceLiveSession
    from app.subagent.oob import OOBSubagent

logger = logging.getLogger(__name__)


@dataclass
class Utterance:
    """Single utterance in the conversation."""

    role: str  # "user" | "assistant"
    text: str
    item_id: str
    phase: str
    timestamp: datetime


@dataclass
class ToolCallLog:
    """Tool call execution record."""

    name: str
    args: dict
    result: dict
    call_id: str
    item_id: str
    phase: str
    timestamp: datetime
    duration_ms: int


@dataclass
class PhaseTransition:
    """Phase transition record."""

    from_phase: str
    to_phase: str
    trigger_tool: str
    context_vars: dict
    timestamp: datetime


@dataclass
class FullContext:
    """Complete conversation context."""

    call_id: str
    started_at: datetime
    phase_history: list[PhaseTransition] = field(default_factory=list)
    utterances: list[Utterance] = field(default_factory=list)
    tool_calls: list[ToolCallLog] = field(default_factory=list)
    vars: dict = field(default_factory=dict)
    vl_item_ids_by_phase: dict[str, list[str]] = field(default_factory=dict)
    cumulative_tokens: int = 0
    last_summary_token_count: int = 0


class ContextManager:
    """Manages conversation context and history."""

    def __init__(self, call_id: str, summary_threshold: int = 8000):
        self.ctx = FullContext(call_id=call_id, started_at=datetime.utcnow())
        self.summary_threshold = summary_threshold
        self.current_phase = "triage"

    def record_utterance(self, role: str, text: str, item_id: str, phase: str) -> None:
        """Record a user or assistant utterance."""
        utterance = Utterance(
            role=role,
            text=text,
            item_id=item_id,
            phase=phase,
            timestamp=datetime.utcnow(),
        )
        self.ctx.utterances.append(utterance)

        # Track item IDs by phase
        if phase not in self.ctx.vl_item_ids_by_phase:
            self.ctx.vl_item_ids_by_phase[phase] = []
        self.ctx.vl_item_ids_by_phase[phase].append(item_id)

    def record_tool_call(
        self,
        name: str,
        args: dict,
        result: dict,
        call_id: str,
        item_id: str,
        phase: str,
        duration_ms: int,
    ) -> None:
        """Record a tool call execution."""
        tool_call = ToolCallLog(
            name=name,
            args=args,
            result=result,
            call_id=call_id,
            item_id=item_id,
            phase=phase,
            timestamp=datetime.utcnow(),
            duration_ms=duration_ms,
        )
        self.ctx.tool_calls.append(tool_call)

    def record_phase_transition(
        self, from_phase: str, to_phase: str, trigger_tool: str, vars: dict
    ) -> None:
        """Record a phase transition."""
        transition = PhaseTransition(
            from_phase=from_phase,
            to_phase=to_phase,
            trigger_tool=trigger_tool,
            context_vars=vars.copy(),
            timestamp=datetime.utcnow(),
        )
        self.ctx.phase_history.append(transition)
        self.current_phase = to_phase

    def update_usage(self, prompt_tokens: int, completion_tokens: int) -> None:
        """Update cumulative token usage."""
        self.ctx.cumulative_tokens += prompt_tokens + completion_tokens

    async def prepare_handoff(
        self,
        session: "VoiceLiveSession",
        oob: "OOBSubagent",
        from_phase: str,
        to_phase: str,
        tool_result: dict,
    ) -> dict:
        """Prepare context for phase handoff.

        Returns: Dictionary of variables to inject into new phase instructions.
        """
        logger.info(f"Preparing handoff from {from_phase} to {to_phase}")

        # Extract relevant info from tool result
        if "customer_name" in tool_result:
            self.ctx.vars["customer_name"] = tool_result["customer_name"]
        if "plan" in tool_result:
            self.ctx.vars["customer_plan"] = tool_result["plan"]
        if "customer_id" in tool_result:
            self.ctx.vars["customer_id"] = tool_result["customer_id"]
        if "reason" in tool_result:
            self.ctx.vars["escalation_reason"] = tool_result["reason"]

        # Generate handoff summary using OOB
        recent_utterances = [u for u in self.ctx.utterances if u.phase == from_phase][-5:]
        summary_prompt = f"""以下の会話を1-2文で要約してください:

"""
        for u in recent_utterances:
            summary_prompt += f"{u.role}: {u.text}\n"

        try:
            summary = await oob.run(
                purpose="handoff_summary",
                instructions=summary_prompt,
                output_modalities=["text"],
                timeout_s=10.0,
            )
            self.ctx.vars[f"{from_phase}_summary"] = summary
        except Exception as e:
            logger.warning(f"Failed to generate handoff summary: {e}")
            self.ctx.vars[f"{from_phase}_summary"] = "（サマリ生成失敗）"

        # Delete old phase items (optional - can be kept for full history)
        # For now, we keep everything and rely on periodic summarization

        return self.ctx.vars.copy()

    async def maybe_summarize(
        self, session: "VoiceLiveSession", oob: "OOBSubagent"
    ) -> bool:
        """Conditionally summarize conversation if token threshold exceeded.

        Returns: True if summarization was performed.
        """
        if self.ctx.cumulative_tokens < self.summary_threshold:
            return False

        logger.info(f"Token threshold reached ({self.ctx.cumulative_tokens}), summarizing")

        # Get utterances excluding the most recent 3 turns
        all_utterances = self.ctx.utterances[:-6]  # Keep last 3 user + 3 assistant turns
        if len(all_utterances) < 3:
            return False

        # Generate summary
        summary_prompt = """以下の会話履歴を300トークン以内で要約してください:

"""
        for u in all_utterances:
            summary_prompt += f"{u.role}: {u.text}\n"

        try:
            summary = await oob.run(
                purpose="conversation_summary",
                instructions=summary_prompt,
                output_modalities=["text"],
                timeout_s=15.0,
            )

            # Store summary
            self.ctx.vars["conversation_summary"] = summary
            self.ctx.last_summary_token_count = self.ctx.cumulative_tokens

            logger.info("Conversation summarized successfully")
            return True

        except Exception as e:
            logger.error(f"Failed to summarize conversation: {e}")
            return False

    def dump(self, path: str) -> None:
        """Dump full context to JSON file."""
        data = {
            "call_id": self.ctx.call_id,
            "started_at": self.ctx.started_at.isoformat(),
            "phase_history": [
                {
                    "from_phase": t.from_phase,
                    "to_phase": t.to_phase,
                    "trigger_tool": t.trigger_tool,
                    "context_vars": t.context_vars,
                    "timestamp": t.timestamp.isoformat(),
                }
                for t in self.ctx.phase_history
            ],
            "utterances": [
                {
                    "role": u.role,
                    "text": u.text,
                    "item_id": u.item_id,
                    "phase": u.phase,
                    "timestamp": u.timestamp.isoformat(),
                }
                for u in self.ctx.utterances
            ],
            "tool_calls": [
                {
                    "name": tc.name,
                    "args": tc.args,
                    "result": tc.result,
                    "call_id": tc.call_id,
                    "item_id": tc.item_id,
                    "phase": tc.phase,
                    "timestamp": tc.timestamp.isoformat(),
                    "duration_ms": tc.duration_ms,
                }
                for tc in self.ctx.tool_calls
            ],
            "vars": self.ctx.vars,
            "cumulative_tokens": self.ctx.cumulative_tokens,
        }

        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

        logger.info(f"Context dumped to {path}")
