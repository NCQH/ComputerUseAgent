"""Windows UI Automation backend: enumerate interactive elements of the focused app.

The desktop analog of `dom_marks.INTERACTIVE_JS`. Instead of reading the DOM, it
walks the Windows UIA tree of the *foreground window* (OQ-2c: scoped to the focused
window — the full desktop tree is huge and slow) and emits one raw record per
interactive control, in the SAME dict shape DOM elements use
(`x,y,width,height,tag,role,type,text`) so `dom_marks.parse_elements/boxes_of/
describe` are reused verbatim (DRY).

`uiautomation` is lazy-imported and the whole walk is wrapped: an absent library
(non-Windows, or `[local]` extra not installed) or any COM error degrades to an
empty list → the provider falls back to grid/point, exactly like the browser
provider's `_elements()`. Never raises.
"""
from __future__ import annotations

from typing import Protocol

# UIA ControlType names (control.ControlTypeName) that are worth targeting.
_INTERACTIVE_CONTROL_TYPES = {
    "ButtonControl", "EditControl", "CheckBoxControl", "RadioButtonControl",
    "ComboBoxControl", "ListItemControl", "MenuItemControl", "TabItemControl",
    "HyperlinkControl", "SliderControl", "TreeItemControl", "SplitButtonControl",
    "HeaderItemControl", "DataItemControl",
}

# Short, model-friendly label derived from the control type (strip the "Control"
# suffix): ButtonControl -> "button".
def _short_type(control_type_name: str) -> str:
    name = control_type_name or ""
    if name.endswith("Control"):
        name = name[: -len("Control")]
    return name.lower()


class A11yBackend(Protocol):
    def elements(self, display_size: tuple[int, int]) -> list[dict]:
        ...


class NullBackend:
    """No-op backend (non-Windows / tests): always abstains -> grid/point fallback."""

    def elements(self, display_size: tuple[int, int]) -> list[dict]:
        return []


class UiaBackend:
    def __init__(self, max_depth: int = 12, max_elements: int = 60) -> None:
        self.max_depth = max_depth
        self.max_elements = max_elements

    def elements(self, display_size: tuple[int, int]) -> list[dict]:
        try:
            import uiautomation as auto  # lazy; Windows-only, part of [local]
        except Exception:  # noqa: BLE001 — absent lib -> degrade to grid/point
            return []
        try:
            return self._walk(auto, display_size)
        except Exception:  # noqa: BLE001 — any COM/UIA error -> degrade, never crash
            return []

    def _walk(self, auto, display_size: tuple[int, int]) -> list[dict]:
        root = auto.GetForegroundControl()
        if root is None:
            return []
        out: list[dict] = []
        stack = [(root, 0)]
        while stack and len(out) < self.max_elements:
            control, depth = stack.pop()
            if depth > self.max_depth:
                continue
            rec = self._record(control, display_size)
            if rec is not None:
                out.append(rec)
            try:
                children = control.GetChildren()
            except Exception:  # noqa: BLE001 — skip an unreadable subtree
                children = []
            # Reverse so the natural top-to-bottom order is preserved with a stack.
            for child in reversed(children):
                stack.append((child, depth + 1))
        return out

    def _record(self, control, display_size: tuple[int, int]) -> dict | None:
        try:
            type_name = control.ControlTypeName
        except Exception:  # noqa: BLE001
            return None
        if type_name not in _INTERACTIVE_CONTROL_TYPES:
            return None
        try:
            r = control.BoundingRectangle
            x, y = int(r.left), int(r.top)
            width, height = int(r.width()), int(r.height())
        except Exception:  # noqa: BLE001 — no geometry -> unusable as a mark
            return None
        if width < 1 or height < 1:
            return None
        try:
            name = (control.Name or "").strip().replace("\n", " ")[:80]
        except Exception:  # noqa: BLE001
            name = ""
        return {
            "x": x, "y": y, "width": width, "height": height,
            "tag": _short_type(type_name), "role": "", "type": "", "text": name,
        }
