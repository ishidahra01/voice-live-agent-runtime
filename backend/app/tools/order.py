"""Order management tools."""

from .registry import register_tool


@register_tool("lookup_order")
async def lookup_order(customer_id: str, order_id: str | None = None) -> dict:
    """注文照会。order_id省略時は直近注文を返す。"""
    # Mock implementation
    return {
        "order_id": order_id or "ORD-2026-0042",
        "status": "出荷済",
        "items": ["商品A x1"],
        "total_jpy": 4980,
    }


@register_tool("update_plan")
async def update_plan(customer_id: str, new_plan: str) -> dict:
    """プラン変更。モックでは成功を返すだけ。"""
    return {"success": True, "old_plan": "不明", "new_plan": new_plan}
