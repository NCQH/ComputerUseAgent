"""DOM interactive-element extraction — the browser_use "Set-of-Marks" technique.

Instead of asking a vision model to guess pixel coordinates, we read the page's
interactive elements (links, buttons, inputs, ARIA widgets) straight from the DOM,
number them, and let the model pick one by index. Far more reliable than OCR/grid
on real pages. `INTERACTIVE_JS` runs in the page; `parse_elements` turns its raw
output into ordered `Element`s whose index == Set-of-Marks mark id, and `describe`
renders the numbered list the model reads. Pure (no Playwright import) → unit-tested
offline with canned dicts.
"""
from __future__ import annotations

from dataclasses import dataclass

# Returns one flat record per visible, non-trivial interactive element, in DOM
# order, with viewport-pixel geometry.
INTERACTIVE_JS = r"""
() => {
  const SEL = 'a,button,input,textarea,select,summary,details,' +
    '[role=button],[role=link],[role=checkbox],[role=radio],[role=tab],' +
    '[role=menuitem],[role=switch],[onclick],[tabindex]';
  const out = [];
  for (const el of document.querySelectorAll(SEL)) {
    const r = el.getBoundingClientRect();
    if (r.width < 1 || r.height < 1) continue;
    if (r.bottom < 0 || r.right < 0 || r.top > innerHeight || r.left > innerWidth) continue;
    const s = getComputedStyle(el);
    if (s.visibility === 'hidden' || s.display === 'none' || s.opacity === '0') continue;
    const text = (el.innerText || el.value || el.getAttribute('aria-label') ||
                  el.getAttribute('placeholder') || el.getAttribute('name') || '')
                 .trim().replace(/\s+/g, ' ').slice(0, 80);
    out.push({
      x: Math.round(r.left), y: Math.round(r.top),
      width: Math.round(r.width), height: Math.round(r.height),
      tag: el.tagName.toLowerCase(),
      role: el.getAttribute('role') || '',
      type: el.getAttribute('type') || '',
      text: text,
    });
  }
  return out;
}
"""

_MAX_ELEMENTS = 60


@dataclass(frozen=True)
class Element:
    index: int
    x0: int
    y0: int
    x1: int
    y1: int
    tag: str
    role: str
    type: str
    text: str


def parse_elements(raw, display_size, max_elements: int = _MAX_ELEMENTS) -> list[Element]:
    """Turn the raw JS records into ordered Elements, dropping zero-size entries,
    clamping boxes to the viewport, and capping the count to bound prompt size."""
    w, h = display_size
    elements: list[Element] = []
    for rec in raw:
        width = int(rec.get("width", 0))
        height = int(rec.get("height", 0))
        if width < 1 or height < 1:
            continue
        x0 = max(0, int(rec.get("x", 0)))
        y0 = max(0, int(rec.get("y", 0)))
        x1 = min(w, x0 + width)
        y1 = min(h, y0 + height)
        if x1 <= x0 or y1 <= y0:
            continue
        elements.append(Element(
            index=len(elements), x0=x0, y0=y0, x1=x1, y1=y1,
            tag=str(rec.get("tag", "")), role=str(rec.get("role", "")),
            type=str(rec.get("type", "")), text=str(rec.get("text", "")),
        ))
        if len(elements) >= max_elements:
            break
    return elements


def boxes_of(elements) -> list[tuple[int, int, int, int]]:
    """Bounding boxes in Element order — feeds imaging.annotate_marks so the drawn
    mark id matches Element.index."""
    return [(e.x0, e.y0, e.x1, e.y1) for e in elements]


def _label(e: Element) -> str:
    head = e.tag
    if e.type:
        head += f"({e.type})"
    if e.role:
        head += f"[{e.role}]"
    text = f' "{e.text}"' if e.text else ""
    return f"[{e.index}] {head}{text}"


def describe(elements) -> str:
    """The numbered element list the model reads to pick a mark by meaning."""
    if not elements:
        return "(no interactive elements detected — use a 'point' or 'grid' target)"
    return "Interactive elements:\n" + "\n".join(_label(e) for e in elements)
