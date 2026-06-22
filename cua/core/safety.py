"""Two-layer irreversibility gate: hard denylist + model risk flag."""
from __future__ import annotations

from cua.models import Action, Key, Type

DEFAULT_DENYLIST: list[str] = [
    "submit", "delete", "remove", "buy", "purchase", "pay", "send",
    "confirm", "xóa", "mua", "thanh toán", "gửi", "xác nhận",
]

DESTRUCTIVE_KEY_COMBOS: list[str] = [
    "ctrl+shift+delete",
    "ctrl+shift+del",
    "shift+delete",
]


class IrreversibilityGate:
    def __init__(self, denylist: list[str] | None = None) -> None:
        self._denylist = [k.lower() for k in (denylist if denylist is not None else DEFAULT_DENYLIST)]

    def needs_confirmation(
        self, action: Action, description: str, model_flagged: bool
    ) -> tuple[bool, str]:
        if model_flagged:
            return True, "Model đánh dấu hành động rủi ro (cần xác nhận)"

        if isinstance(action, Key):
            combo = action.combo.lower().replace(" ", "")
            if combo in DESTRUCTIVE_KEY_COMBOS:
                return True, f"Tổ hợp phím phá huỷ: '{action.combo}'"

        haystack = (description or "").lower()
        if isinstance(action, Type):
            haystack += " " + action.text.lower()
        if isinstance(action, Key):
            haystack += " " + action.combo.lower()

        for keyword in self._denylist:
            if keyword in haystack:
                return True, f"Khớp denylist: '{keyword}'"

        return False, ""
