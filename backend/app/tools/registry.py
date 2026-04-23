"""Tool registry and schemas."""

from typing import Any, Callable, Dict
import asyncio

# Tool function registry
_TOOL_FUNCTIONS: Dict[str, Callable] = {}


def register_tool(name: str):
    """Decorator to register a tool function."""
    def decorator(func: Callable):
        _TOOL_FUNCTIONS[name] = func
        return func
    return decorator


async def execute_tool(name: str, args: Dict[str, Any]) -> Dict[str, Any]:
    """Execute a registered tool by name."""
    if name not in _TOOL_FUNCTIONS:
        return {"error": f"Tool {name} not found"}

    func = _TOOL_FUNCTIONS[name]
    try:
        if asyncio.iscoroutinefunction(func):
            result = await func(**args)
        else:
            result = func(**args)
        return result
    except Exception as e:
        return {"error": str(e)}


# Tool schemas for Voice Live API
TOOL_SCHEMAS: Dict[str, Dict] = {
    "verify_customer": {
        "type": "function",
        "name": "verify_customer",
        "description": "お客様番号で本人確認を行う",
        "parameters": {
            "type": "object",
            "properties": {
                "customer_id": {"type": "string", "description": "8桁のお客様番号"}
            },
            "required": ["customer_id"],
        },
    },
    "lookup_order": {
        "type": "function",
        "name": "lookup_order",
        "description": "注文情報を照会する",
        "parameters": {
            "type": "object",
            "properties": {
                "customer_id": {"type": "string", "description": "お客様番号"},
                "order_id": {"type": "string", "description": "注文ID（省略可）"},
            },
            "required": ["customer_id"],
        },
    },
    "update_plan": {
        "type": "function",
        "name": "update_plan",
        "description": "プランを変更する",
        "parameters": {
            "type": "object",
            "properties": {
                "customer_id": {"type": "string", "description": "お客様番号"},
                "new_plan": {"type": "string", "description": "新しいプラン名"},
            },
            "required": ["customer_id", "new_plan"],
        },
    },
    "create_escalation": {
        "type": "function",
        "name": "create_escalation",
        "description": "エスカレーションチケットを作成する",
        "parameters": {
            "type": "object",
            "properties": {
                "summary": {"type": "string", "description": "問題のサマリ"},
                "urgency": {"type": "string", "description": "緊急度（low/medium/high）"},
                "customer_id": {"type": "string", "description": "お客様番号（省略可）"},
            },
            "required": ["summary", "urgency"],
        },
    },
    "start_identity_verification": {
        "type": "function",
        "name": "start_identity_verification",
        "description": "本人確認フェーズを開始する",
        "parameters": {"type": "object", "properties": {}, "required": []},
    },
    "back_to_triage": {
        "type": "function",
        "name": "back_to_triage",
        "description": "トリアージフェーズに戻る",
        "parameters": {"type": "object", "properties": {}, "required": []},
    },
    "escalate_to_human": {
        "type": "function",
        "name": "escalate_to_human",
        "description": "オペレータにエスカレーションする",
        "parameters": {
            "type": "object",
            "properties": {
                "reason": {"type": "string", "description": "エスカレーション理由"}
            },
            "required": ["reason"],
        },
    },
    "end_call": {
        "type": "function",
        "name": "end_call",
        "description": "通話を終了する",
        "parameters": {
            "type": "object",
            "properties": {
                "summary": {"type": "string", "description": "対応サマリ"}
            },
            "required": ["summary"],
        },
    },
}


def build_tool_schemas(tool_names: list[str]) -> list[dict]:
    """Build tool schemas for a list of tool names."""
    return [TOOL_SCHEMAS[name] for name in tool_names if name in TOOL_SCHEMAS]
