"""Meta tools for phase transitions."""

from .registry import register_tool


@register_tool("start_identity_verification")
async def start_identity_verification() -> dict:
    """本人確認フェーズを開始する。"""
    return {"action": "start_identity", "next_phase": "identity"}


@register_tool("back_to_triage")
async def back_to_triage() -> dict:
    """トリアージフェーズに戻る。"""
    return {"action": "back_to_triage", "next_phase": "triage"}


@register_tool("escalate_to_human")
async def escalate_to_human(reason: str) -> dict:
    """オペレータにエスカレーションする。"""
    return {"action": "escalate", "reason": reason, "next_phase": "escalation"}


@register_tool("end_call")
async def end_call(summary: str) -> dict:
    """通話を終了する。"""
    return {"action": "end_call", "summary": summary}
