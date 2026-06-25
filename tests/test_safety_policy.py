"""SPEC-4 Safety/Policy v2: policies, chain severity, context-awareness."""
from adaptivecua.core.safety import (
    DenylistPolicy,
    DestructiveKeyPolicy,
    IrreversibilityGate,
    ModelRiskPolicy,
    PolicyChain,
    PolicyResult,
    SafetyConfig,
    SafetyContext,
    SensitiveContextPolicy,
    Verdict,
)
from adaptivecua.models import Click, Key, Move, Type


# --- individual policies -------------------------------------------------

def test_model_risk_policy_confirms_when_flagged():
    r = ModelRiskPolicy().evaluate(Move(1, 1), "harmless", model_flagged=True, ctx=None)
    assert r is not None and r.verdict is Verdict.CONFIRM


def test_model_risk_policy_abstains_when_not_flagged():
    assert ModelRiskPolicy().evaluate(Move(1, 1), "harmless", False, None) is None


def test_destructive_key_policy_confirms_known_combo():
    r = DestructiveKeyPolicy().evaluate(Key("ctrl+shift+delete"), "", False, None)
    assert r is not None and r.verdict is Verdict.CONFIRM


def test_destructive_key_policy_blocks_catastrophic_combo():
    pol = DestructiveKeyPolicy(catastrophic_keys=["ctrl+alt+del"])
    r = pol.evaluate(Key("ctrl+alt+del"), "", False, None)
    assert r is not None and r.verdict is Verdict.BLOCK


def test_destructive_key_policy_abstains_on_benign_key():
    assert DestructiveKeyPolicy().evaluate(Key("enter"), "", False, None) is None


def test_denylist_policy_confirms_on_keyword():
    r = DenylistPolicy().evaluate(Click(1, 1), "click Submit", False, None)
    assert r is not None and r.verdict is Verdict.CONFIRM and "submit" in r.reason.lower()


def test_denylist_policy_abstains_on_benign():
    assert DenylistPolicy().evaluate(Click(1, 1), "click search box", False, None) is None


# --- sensitive context ---------------------------------------------------

def test_sensitive_context_confirms_on_banking_url():
    ctx = SafetyContext("web", url="https://mybank.example.com/login")
    r = SensitiveContextPolicy().evaluate(Click(1, 1), "", False, ctx)
    assert r is not None and r.verdict is Verdict.CONFIRM


def test_sensitive_context_confirms_on_password_manager_title():
    ctx = SafetyContext("local", active_title="KeePass - vault.kdbx")
    r = SensitiveContextPolicy().evaluate(Click(1, 1), "", False, ctx)
    assert r is not None and r.verdict is Verdict.CONFIRM


def test_sensitive_context_abstains_on_benign_surface():
    ctx = SafetyContext("local", active_title="Notepad - untitled.txt")
    assert SensitiveContextPolicy().evaluate(Click(1, 1), "", False, ctx) is None


def test_sensitive_context_abstains_without_context():
    assert SensitiveContextPolicy().evaluate(Click(1, 1), "", False, None) is None


def test_sensitive_context_matches_vietnamese_banking_title():
    ctx = SafetyContext("local", active_title="Ứng dụng Ngân hàng MB")
    assert SensitiveContextPolicy().matches(ctx) is True


# --- chain severity ------------------------------------------------------

def test_chain_takes_most_severe_verdict_block_over_confirm():
    chain = PolicyChain([
        DenylistPolicy(),                                   # CONFIRM on 'delete'
        DestructiveKeyPolicy(catastrophic_keys=["ctrl+alt+del"]),
    ])
    best, fired = chain.evaluate(Key("ctrl+alt+del"), "delete now", False, None)
    assert best.verdict is Verdict.BLOCK
    assert len(fired) == 2  # both fired, full audit trail


def test_chain_all_abstain_is_allow():
    best, fired = PolicyChain([DenylistPolicy()]).evaluate(
        Click(1, 1), "click search", False, None
    )
    assert best.verdict is Verdict.ALLOW and fired == []


def test_chain_ties_keep_first_policy_reason():
    # both CONFIRM; model_risk listed first -> its reason wins (back-compat)
    chain = PolicyChain([ModelRiskPolicy(), DenylistPolicy()])
    best, _ = chain.evaluate(Click(1, 1), "submit", model_flagged=True, ctx=None)
    assert best.verdict is Verdict.CONFIRM and "model" in best.reason.lower()


# --- gate API: decide() + sensitivity + back-compat ----------------------

def test_gate_decide_allows_benign_with_context():
    gate = IrreversibilityGate()
    ctx = SafetyContext("local", active_title="Notepad")
    assert gate.decide(Click(1, 1), "click box", False, ctx).verdict is Verdict.ALLOW


def test_gate_decide_confirms_benign_click_on_banking():
    gate = IrreversibilityGate()
    ctx = SafetyContext("web", url="https://paypal.com/transfer")
    r = gate.decide(Click(1, 1), "click button", False, ctx)
    assert r.verdict is Verdict.CONFIRM and r.policy == "sensitive_context"


def test_gate_decide_blocks_catastrophic_key():
    gate = IrreversibilityGate(catastrophic_keys=["ctrl+alt+del"])
    r = gate.decide(Key("ctrl+alt+del"), "", False, None)
    assert r.verdict is Verdict.BLOCK


def test_gate_is_sensitive_context():
    gate = IrreversibilityGate()
    assert gate.is_sensitive_context(SafetyContext("web", url="https://x.bank/")) is True
    assert gate.is_sensitive_context(SafetyContext("local", active_title="Calc")) is False
    assert gate.is_sensitive_context(None) is False


def test_from_config_builds_gate():
    gate = IrreversibilityGate.from_config(
        SafetyConfig(denylist=["frobnicate"], catastrophic_keys=["ctrl+alt+del"])
    )
    assert gate.decide(Key("ctrl+alt+del"), "", False, None).verdict is Verdict.BLOCK
    assert gate.needs_confirmation(Click(1, 1), "frobnicate", False)[0] is True
    assert gate.needs_confirmation(Click(1, 1), "submit", False)[0] is False  # custom overrides default
