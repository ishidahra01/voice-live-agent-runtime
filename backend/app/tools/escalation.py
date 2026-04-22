"""Escalation tools."""

from uuid import uuid4
from .registry import register_tool


@register_tool("create_escalation")
async def create_escalation(
    summary: str, urgency: str, customer_id: str | None = None
) -> dict:
    """エスカレーション起票。コンソール出力のみ。"""
    ticket_id = f"ESC-{uuid4().hex[:8]}"
    print(f"[ESCALATION] {ticket_id} urgency={urgency} customer={customer_id}: {summary}")
    return {"ticket_id": ticket_id, "created": True}
