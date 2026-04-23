"""Customer verification tools."""

from .registry import register_tool

# Mock customer database
MOCK_CUSTOMER_DB = {
    "12345678": {"name": "山田 太郎", "plan": "プレミアム", "since": "2019-04-01"},
    "87654321": {"name": "佐藤 花子", "plan": "ベーシック", "since": "2023-10-15"},
}


@register_tool("verify_customer")
async def verify_customer(customer_id: str) -> dict:
    """お客様番号で本人確認を行う。8桁の数字のみ有効。"""
    if not (customer_id.isdigit() and len(customer_id) == 8):
        return {"verified": False, "reason": "お客様番号は8桁の数字です"}

    if customer_id in MOCK_CUSTOMER_DB:
        data = MOCK_CUSTOMER_DB[customer_id]
        return {"verified": True, "customer_id": customer_id, **data}

    return {"verified": False, "reason": "該当する顧客が見つかりません"}
