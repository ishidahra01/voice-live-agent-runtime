"""Phase router for managing phase transitions."""

import logging
from typing import TYPE_CHECKING
from app.phases import PHASES, TRANSITIONS, TERMINAL_TOOLS
from app.tools import execute_tool
from app.voicelive.runtime import build_phase_session_event, build_phase_session_request
from datetime import datetime, timezone

if TYPE_CHECKING:
    from app.voicelive.session import VoiceLiveSession
    from app.context.manager import ContextManager
    from app.subagent.oob import OOBSubagent

logger = logging.getLogger(__name__)


class PhaseRouter:
    """Manages phase state and transitions."""

    def __init__(
        self,
        session: "VoiceLiveSession",
        context_manager: "ContextManager",
        oob_subagent: "OOBSubagent",
    ):
        self.session = session
        self.context_manager = context_manager
        self.oob = oob_subagent
        self.current_phase = "triage"
        self._pending_tool_calls: dict[str, dict] = {}
        self._session_ended = False

    async def handle_function_call(self, item: dict) -> None:
        """Handle a function_call item from Voice Live."""
        if self._session_ended:
            logger.info("Ignoring function call after session end")
            return

        call_id = item.get("call_id", "")
        name = item.get("name", "")
        item_id = item.get("id", "")

        logger.info(f"Function call received: {name} (call_id={call_id})")

        # Store pending call for when arguments are complete
        self._pending_tool_calls[call_id] = {
            "name": name,
            "item_id": item_id,
            "call_id": call_id,
            "args": {},
            "start_time": datetime.now(timezone.utc),
        }

    async def handle_function_call_arguments_done(self, event: dict) -> None:
        """Handle completion of function call arguments."""
        if self._session_ended:
            logger.info("Ignoring function call arguments after session end")
            return

        call_id = event.get("call_id", "")
        arguments = event.get("arguments", "{}")

        if call_id not in self._pending_tool_calls:
            logger.warning(f"Unknown call_id: {call_id}")
            return

        pending = self._pending_tool_calls.pop(call_id)
        name = pending["name"]
        item_id = pending["item_id"]

        # Parse arguments
        import json
        try:
            args = json.loads(arguments)
        except json.JSONDecodeError:
            args = {}

        logger.info(f"Executing tool: {name} with args: {args}")

        # Execute tool
        start_ms = (datetime.now(timezone.utc) - pending["start_time"]).total_seconds() * 1000
        result = await execute_tool(name, args)
        duration_ms = int((datetime.now(timezone.utc) - pending["start_time"]).total_seconds() * 1000)

        # Record tool call
        self.context_manager.record_tool_call(
            name=name,
            args=args,
            result=result,
            call_id=call_id,
            item_id=item_id,
            phase=self.current_phase,
            duration_ms=duration_ms,
        )

        # Check for phase transition
        await self._check_transition(name, result, call_id, item_id)

        is_terminal_tool = name in TERMINAL_TOOLS

        # Send tool result back to Voice Live
        await self._send_tool_result(
            call_id,
            item_id,
            result,
            trigger_response=not is_terminal_tool,
        )

        # Notify frontend
        await self.session.send_to_frontend({
            "type": "tool_call",
            "name": name,
            "args": args,
            "result": result,
            "duration_ms": duration_ms,
        })

        # Check for terminal tools
        if is_terminal_tool:
            self._session_ended = True
            logger.info(f"Terminal tool {name} called, ending session")
            await self.session.send_to_frontend({"type": "session_end", "reason": name})

    async def _check_transition(
        self, tool_name: str, tool_result: dict, call_id: str, item_id: str
    ) -> None:
        """Check if tool call triggers a phase transition."""
        transition_key = (self.current_phase, tool_name)

        # Special case for verify_customer - only transition if verified=True
        if tool_name == "verify_customer" and not tool_result.get("verified", False):
            logger.info("verify_customer failed, not transitioning")
            return

        if transition_key not in TRANSITIONS:
            logger.debug(f"No transition for {transition_key}")
            return

        next_phase = TRANSITIONS[transition_key]
        logger.info(f"Transitioning from {self.current_phase} to {next_phase}")

        # Prepare handoff
        vars_dict = await self.context_manager.prepare_handoff(
            session=self.session,
            oob=self.oob,
            from_phase=self.current_phase,
            to_phase=next_phase,
            tool_result=tool_result,
        )

        # Record transition
        self.context_manager.record_phase_transition(
            from_phase=self.current_phase,
            to_phase=next_phase,
            trigger_tool=tool_name,
            vars=vars_dict,
        )

        # Update session with new phase configuration
        await self._apply_phase_config(next_phase, vars_dict)

        # Update current phase
        old_phase = self.current_phase
        self.current_phase = next_phase

        # Notify frontend
        await self.session.send_to_frontend({
            "type": "phase_changed",
            "from": old_phase,
            "to": next_phase,
            "vars": vars_dict,
        })

    async def _apply_phase_config(self, phase: str, vars_dict: dict) -> None:
        """Apply phase configuration to Voice Live session."""
        phase_config = PHASES[phase]
        instructions = phase_config["instructions"]

        # Substitute variables in instructions
        try:
            instructions = instructions.format(**vars_dict)
        except KeyError as e:
            logger.warning(f"Missing variable in instructions: {e}")

        # Send session.update
        await self.session.send({
            "type": "session.update",
            "session": build_phase_session_request(phase, instructions),
        })

        await self.session.send_to_frontend(build_phase_session_event(phase))
        await self.session.send_to_frontend(
            self.context_manager.build_frontend_context_snapshot(phase)
        )

        logger.info(f"Applied phase configuration for {phase}")

    async def _send_tool_result(
        self,
        call_id: str,
        item_id: str,
        result: dict,
        trigger_response: bool = True,
    ) -> None:
        """Send tool execution result to Voice Live."""
        import json

        await self.session.send({
            "type": "conversation.item.create",
            "previous_item_id": item_id,
            "item": {
                "type": "function_call_output",
                "call_id": call_id,
                "output": json.dumps(result, ensure_ascii=False),
            },
        })

        # Trigger response generation
        if trigger_response:
            await self.session.send({"type": "response.create"})
