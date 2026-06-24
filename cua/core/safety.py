"""Safety / Policy v2: a composable, context-aware policy chain.

There is NO sandbox in this project (memory `cua-project-scope`): the agent acts on
the real host desktop (`local`) or a live browser (`web`). This module is therefore
the *only* net. It evaluates every proposed action through a chain of independent
policies and aggregates the most-severe verdict.

Three verdicts:
  ALLOW   — run, no prompt
  CONFIRM — pause and ask the user
  BLOCK   — refuse; never run, even if the user says yes (BLOCK set is empty by
            default, so default behaviour matches the old binary gate exactly)

`IrreversibilityGate` keeps a back-compat `needs_confirmation() -> (bool, str)` so
the existing tests and call sites keep working, and adds `decide() -> PolicyResult`
plus context-awareness for the session.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import Enum
from fnmatch import fnmatch
from typing import Protocol

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

# Substring keywords matched against the focused window title (case-folded).
DEFAULT_SENSITIVE_TITLES: list[str] = [
    "bank", "ngân hàng", "credential", "mật khẩu", "password",
    "keepass", "1password", "bitwarden", "lastpass",
]

# fnmatch glob patterns matched against the page URL (case-folded).
DEFAULT_SENSITIVE_URL_PATTERNS: list[str] = [
    "*bank*", "*paypal*", "*/login*", "*signin*", "*wallet*",
]


class Verdict(Enum):
    ALLOW = "ALLOW"      # run, no prompt
    CONFIRM = "CONFIRM"  # pause, ask
    BLOCK = "BLOCK"      # refuse; never run even if user says yes


_SEVERITY: dict[Verdict, int] = {Verdict.ALLOW: 0, Verdict.CONFIRM: 1, Verdict.BLOCK: 2}


@dataclass(frozen=True)
class SafetyContext:
    executor: str                    # "local" | "web"
    active_title: str | None = None  # focused window title (local)
    url: str | None = None           # page URL (web)


@dataclass(frozen=True)
class PolicyResult:
    verdict: Verdict
    reason: str
    policy: str                      # which policy fired


@dataclass(frozen=True)
class SafetyConfig:
    denylist: list[str] | None = None
    sensitive_titles: list[str] | None = None
    sensitive_url_patterns: list[str] | None = None
    catastrophic_keys: list[str] = field(default_factory=list)  # -> BLOCK
    audit_enabled: bool = True


class Policy(Protocol):
    name: str

    def evaluate(
        self,
        action: Action,
        description: str,
        model_flagged: bool,
        ctx: SafetyContext | None,
    ) -> PolicyResult | None:
        """Assert a verdict, or return None to abstain."""
        ...


class ModelRiskPolicy:
    name = "model_risk"

    def evaluate(self, action, description, model_flagged, ctx):
        if model_flagged:
            return PolicyResult(
                Verdict.CONFIRM,
                "Model đánh dấu hành động rủi ro (cần xác nhận)",
                self.name,
            )
        return None


class DestructiveKeyPolicy:
    name = "destructive_key"

    def __init__(self, catastrophic_keys: list[str] | None = None) -> None:
        # Catastrophic combos escalate to BLOCK (never run). Empty by default,
        # so the default verdict for destructive combos stays CONFIRM (old behaviour).
        self._catastrophic = {
            k.lower().replace(" ", "") for k in (catastrophic_keys or [])
        }

    def evaluate(self, action, description, model_flagged, ctx):
        if isinstance(action, Key):
            combo = action.combo.lower().replace(" ", "")
            if combo in self._catastrophic:
                return PolicyResult(
                    Verdict.BLOCK, f"Tổ hợp phím cấm tuyệt đối: '{action.combo}'", self.name
                )
            if combo in DESTRUCTIVE_KEY_COMBOS:
                return PolicyResult(
                    Verdict.CONFIRM, f"Tổ hợp phím phá huỷ: '{action.combo}'", self.name
                )
        return None


class DenylistPolicy:
    name = "denylist"

    def __init__(self, denylist: list[str] | None = None) -> None:
        self._denylist = [
            k.lower() for k in (denylist if denylist is not None else DEFAULT_DENYLIST)
        ]
        # Whole-word boundaries so 'confirm' does not fire on 'confirmations'.
        # \b is Unicode-aware for str, so Vietnamese keywords match too.
        self._patterns = [
            re.compile(r"\b" + re.escape(k) + r"\b", re.UNICODE) for k in self._denylist
        ]

    def evaluate(self, action, description, model_flagged, ctx):
        haystack = (description or "").lower()
        if isinstance(action, Type):
            haystack += " " + action.text.lower()
        if isinstance(action, Key):
            haystack += " " + action.combo.lower()
        for keyword, pattern in zip(self._denylist, self._patterns):
            if pattern.search(haystack):
                return PolicyResult(Verdict.CONFIRM, f"Khớp denylist: '{keyword}'", self.name)
        return None


class SensitiveContextPolicy:
    """Escalate to CONFIRM when acting on a sensitive surface (banking, password
    managers, OS credential dialogs). Best-effort: titles/URLs can be empty or
    spoofed, so this *adds* a signal, it does not *replace* the denylist."""

    name = "sensitive_context"

    def __init__(
        self,
        sensitive_titles: list[str] | None = None,
        sensitive_url_patterns: list[str] | None = None,
    ) -> None:
        titles = (
            sensitive_titles if sensitive_titles is not None else DEFAULT_SENSITIVE_TITLES
        )
        urls = (
            sensitive_url_patterns
            if sensitive_url_patterns is not None
            else DEFAULT_SENSITIVE_URL_PATTERNS
        )
        self._titles = [t.lower() for t in titles]
        self._url_patterns = [p.lower() for p in urls]

    def matches(self, ctx: SafetyContext | None) -> bool:
        if ctx is None:
            return False
        title = (ctx.active_title or "").lower()
        if any(t in title for t in self._titles):
            return True
        url = (ctx.url or "").lower()
        if url and any(fnmatch(url, p) for p in self._url_patterns):
            return True
        return False

    def evaluate(self, action, description, model_flagged, ctx):
        if self.matches(ctx):
            where = ctx.url or ctx.active_title or "?"
            return PolicyResult(
                Verdict.CONFIRM,
                f"Ngữ cảnh nhạy cảm (ngân hàng / mật khẩu): '{where}'",
                self.name,
            )
        return None


class PolicyChain:
    """Evaluate every policy (full audit), then take the most-severe verdict.
    Severity BLOCK > CONFIRM > ALLOW; ties broken by policy order (first wins, so
    back-compat reason strings are preserved). Empty / all-abstain => ALLOW."""

    def __init__(self, policies: list[Policy]) -> None:
        self._policies = list(policies)

    def evaluate(
        self, action, description, model_flagged, ctx
    ) -> tuple[PolicyResult, list[PolicyResult]]:
        fired = [
            r
            for p in self._policies
            if (r := p.evaluate(action, description, model_flagged, ctx)) is not None
        ]
        if not fired:
            return PolicyResult(Verdict.ALLOW, "", "none"), fired
        # max() returns the first element achieving the maximum -> first-wins ties.
        best = max(fired, key=lambda r: _SEVERITY[r.verdict])
        return best, fired


class IrreversibilityGate:
    def __init__(
        self,
        denylist: list[str] | None = None,
        *,
        sensitive_titles: list[str] | None = None,
        sensitive_url_patterns: list[str] | None = None,
        catastrophic_keys: list[str] | None = None,
    ) -> None:
        self._sensitive = SensitiveContextPolicy(sensitive_titles, sensitive_url_patterns)
        self._chain = PolicyChain([
            ModelRiskPolicy(),
            DestructiveKeyPolicy(catastrophic_keys=catastrophic_keys),
            DenylistPolicy(denylist=denylist),
            self._sensitive,
        ])

    @classmethod
    def from_config(cls, cfg: SafetyConfig) -> "IrreversibilityGate":
        return cls(
            denylist=cfg.denylist,
            sensitive_titles=cfg.sensitive_titles,
            sensitive_url_patterns=cfg.sensitive_url_patterns,
            catastrophic_keys=cfg.catastrophic_keys,
        )

    def decide(
        self,
        action: Action,
        description: str,
        model_flagged: bool,
        ctx: SafetyContext | None = None,
    ) -> PolicyResult:
        best, _ = self._chain.evaluate(action, description, model_flagged, ctx)
        return best

    def is_sensitive_context(self, ctx: SafetyContext | None) -> bool:
        """Whether `ctx` is a sensitive surface — used to redact typed text in the
        audit log so passwords never land in plaintext."""
        return self._sensitive.matches(ctx)

    def needs_confirmation(
        self, action: Action, description: str, model_flagged: bool
    ) -> tuple[bool, str]:
        """Back-compat binary API. Evaluates without context (sensitive-context
        policy abstains), so existing behaviour and reason strings are unchanged."""
        result = self.decide(action, description, model_flagged, None)
        if result.verdict is Verdict.ALLOW:
            return False, ""
        return True, result.reason
