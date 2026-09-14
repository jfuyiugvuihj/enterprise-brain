"""Expense approval pre-check.

Amounts are decimal values end to end; a missing policy standard stays missing
instead of being replaced by an invented threshold.
"""
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
import os
import re

_DEFAULT_CURRENCY_ENV = "APP_DEFAULT_CURRENCY"
_TWO_PLACES = Decimal("0.01")


def to_decimal(value, *, field: str = "amount") -> Decimal:
    """Convert an input to Decimal without going through binary floating point."""
    if isinstance(value, Decimal):
        return value
    if value is None:
        raise ValueError(f"{field} is required")
    if isinstance(value, float):
        value = repr(value)
    try:
        return Decimal(str(value).strip())
    except InvalidOperation as exc:
        raise ValueError(f"{field} must be a decimal value") from exc


def default_currency() -> str:
    return (os.getenv(_DEFAULT_CURRENCY_ENV) or "CNY").strip() or "CNY"


def build_precheck(
    amount,
    standard,
    department: str,
    expense_type: str,
    evidence: list[str],
    *,
    currency: str | None = None,
) -> dict:
    """Compare one expense against an explicit policy standard.

    ``standard`` may be ``None``: the result is then explicitly unverifiable rather
    than silently treating the standard as zero.
    """
    amount = to_decimal(amount, field="amount")
    currency_code = (currency or default_currency()).strip() or "CNY"
    has_standard = standard is not None and str(standard).strip() != ""
    standard_value = to_decimal(standard, field="standard") if has_standard else None
    evidence_items = [str(item) for item in (evidence or []) if str(item).strip()]

    if standard_value is None:
        excess = None
        ratio = None
        status = "无法确认"
        risk = "unknown"
        recommendation = "补充制度标准来源后重新预审"
    else:
        if standard_value == 0:
            raise ValueError("standard must be greater than zero")
        excess = max(Decimal("0"), (amount - standard_value).quantize(_TWO_PLACES))
        ratio = ((amount - standard_value) / standard_value).quantize(Decimal("0.0001"))
        if not evidence_items:
            status = "无法确认"
            risk = "unknown"
            recommendation = "补充制度证据后提交人工审批"
        elif excess > 0:
            status = "需人工审批"
            risk = "high" if ratio >= Decimal("0.2") else "warning"
            recommendation = "提交部门负责人及财务复核"
        else:
            status = "符合标准"
            risk = "low"
            recommendation = "按制度自行留存凭证"

    return {
        "department": str(department or ""),
        "expense_type": str(expense_type or ""),
        "amount": amount,
        "standard": standard_value,
        "currency": currency_code,
        "excess_amount": excess,
        "excess_ratio": ratio,
        "risk_level": risk,
        "status": status,
        "approved": False,
        "recommendation": recommendation,
        "evidence": evidence_items,
    }


def precheck_payload(result: dict, *, requested_by: str = "") -> dict:
    """Serialize a pre-check as JSON-safe values, keeping money as decimal strings."""
    payload = dict(result)
    for key in ("amount", "standard", "excess_amount", "excess_ratio"):
        value = payload.get(key)
        payload[key] = None if value is None else str(value)
    if requested_by:
        payload["requested_by"] = requested_by
    return payload

_AMOUNT_PATTERN = re.compile(
    r"(?P<value>\d+(?:[.,]\d+)*)\s*(?P<unit>万元|万|元|块)?"
)
_STANDARD_PATTERNS = (
    re.compile(r"(?:上限|标准|不得超过|不超过|限额|最高)[^0-9]{0,12}(\d+(?:\.\d+)?)"),
    re.compile(r"(\d+(?:\.\d+)?)[^0-9]{0,6}(?:元/晚|元每晚|元\/晚)"),
)
_EXPENSE_TYPES = {
    "住宿费": ("住宿", "酒店", "房租"),
    "差旅费": ("差旅", "出差"),
    "交通费": ("交通", "打车", "机票", "高铁"),
    "餐饮费": ("餐饮", "餐费", "招待"),
}


def parse_expense_request(question: str) -> dict:
    """Extract the expense amount and type the caller actually stated.

    Only explicit decimal amounts are accepted; ambiguous wording returns ``None``
    instead of guessing a business figure.
    """
    text = str(question or "")
    amount = None
    for match in _AMOUNT_PATTERN.finditer(text):
        raw = match.group("value").replace(",", "")
        unit = match.group("unit") or ""
        try:
            value = Decimal(raw) * (Decimal("10000") if "万" in unit else Decimal("1"))
        except InvalidOperation:
            continue
        if unit:
            amount = value
            break
        if amount is None:
            amount = value
    expense_type = next(
        (name for name, keywords in _EXPENSE_TYPES.items() if any(keyword in text for keyword in keywords)),
        "",
    )
    return {"amount": amount, "expense_type": expense_type}


def extract_standard(excerpts: list[str]) -> Decimal | None:
    """Read a monetary standard out of retrieved policy text, if one is stated."""
    candidates: list[Decimal] = []
    for excerpt in excerpts or []:
        text = str(excerpt or "")
        for pattern in _STANDARD_PATTERNS:
            for match in pattern.finditer(text):
                try:
                    value = Decimal(match.group(1))
                except InvalidOperation:
                    continue
                if value > 0:
                    candidates.append(value)
    if not candidates:
        return None
    # The strictest stated limit is the binding standard; the values stay visible in
    # the evidence excerpt so a reviewer can confirm the reading.
    return min(candidates)
