"""Copy-only provider views; retain domain records and business references unchanged."""

import re
from typing import Any

MODEL_VIEW_VERSION = "model-view-v2"

CONTACT_KEYS = frozenset(
    {
        "email",
        "phone",
        "mobile",
        "telephone",
        "address",
        "home_address",
        "postal_address",
        "contact",
        "contact_info",
        "wechat",
        "weixin",
        "qq",
        "邮箱",
        "电话",
        "手机号",
        "地址",
        "住址",
        "联系地址",
        "联系方式",
        "微信",
    }
)


def minimize(text: str, name: str = "", contacts: tuple[str, ...] = ()) -> str:
    # Exact structural UUIDs are references, even if a hex segment resembles a phone.
    if re.fullmatch(r"[0-9a-fA-F]{8}(?:-[0-9a-fA-F]{4}){3}-[0-9a-fA-F]{12}", text):
        return text
    if name:
        # Avoid removing a short Latin name from a longer skill/company identifier.
        pattern = re.escape(name)
        if name.isascii():
            pattern = r"(?<!\w)" + pattern + r"(?!\w)"
        text = re.sub(pattern, "[PERSON]", text)
    for value in sorted(set(contacts), key=len, reverse=True):
        if value:
            text = text.replace(value, "[CONTACT]")
    text = re.sub(r"[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}", "[EMAIL]", text)
    text = re.sub(r"(?<!\d)(?:\+?86[- ]?)?1[3-9]\d{9}(?!\d)", "[PHONE]", text)
    text = re.sub(r"(?<!\d)\+\d[\d ()-]{8,}\d", "[PHONE]", text)
    text = re.sub(r"(?<!\d)0\d{2,3}[- ]\d{7,8}(?!\d)", "[PHONE]", text)
    # Explicit personal-contact spans, not general cities, company/project locations or dates.
    text = re.sub(
        r"(?i)(家庭住址|通讯地址|联系地址|住址|home address|postal address|contact address|"
        r"联系方式|微信(?:号)?|wechat|weixin|QQ)\s*[:：]\s*[^\n;；。，,|]+",
        r"\1：[CONTACT]",
        text,
    )
    text = re.sub(
        r"(?m)^(\s*(?:个人)?地址\s*[:：])[^\n;；。，,|]+",
        r"\1[CONTACT]",
        text,
    )
    return text


def model_view(value: Any, *, name: str = "", contacts: tuple[str, ...] = ()) -> Any:
    """Never mutate input; UUIDs, evidence ownership and other structural fields survive."""
    if isinstance(value, str):
        return minimize(value, name, contacts)
    if isinstance(value, list):
        return [model_view(item, name=name, contacts=contacts) for item in value]
    if isinstance(value, dict):
        resume = "sections" in value and "profile_id" in value and "template" in value
        return {
            key: model_view(item, name=name, contacts=contacts)
            for key, item in value.items()
            if (not isinstance(key, str) or key.lower() not in CONTACT_KEYS)
            and not (resume and key == "metadata")
        }
    return value


def contact_values(preferences: dict[str, str]) -> tuple[str, ...]:
    # A broad location preference (e.g. 上海) is useful job context, not a street address.
    return tuple(
        value
        for key, value in preferences.items()
        if key.lower() in CONTACT_KEYS and len(value.strip()) >= 6
    )
