"""SPEC-4 audit sink: append-only JSONL, redaction, null no-op."""
import json

from cua.core.audit import REDACTED, AuditSink, NullAuditSink
from cua.core.safety import PolicyResult, SafetyContext, Verdict
from cua.models import Click, Type


def _result(verdict=Verdict.CONFIRM):
    return PolicyResult(verdict, "because", "denylist")


def test_audit_sink_appends_jsonl(tmp_path):
    sink = AuditSink(tmp_path / "s.jsonl", clock=lambda: 123.0)
    ctx = SafetyContext("web", url="https://x.com")
    sink.record(Click(3, 4), _result(), ctx, approved=True)
    sink.record(Click(5, 6), _result(Verdict.ALLOW), ctx, approved=None)

    lines = (tmp_path / "s.jsonl").read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 2
    first = json.loads(lines[0])
    assert first["ts"] == 123.0
    assert first["executor"] == "web"
    assert first["action"] == {"type": "Click", "x": 3, "y": 4, "button": "left"}
    assert first["verdict"] == "CONFIRM"
    assert first["policy"] == "denylist"
    assert first["approved"] is True
    assert first["ctx"]["url"] == "https://x.com"


def test_audit_redacts_typed_text_when_flagged(tmp_path):
    sink = AuditSink(tmp_path / "s.jsonl")
    ctx = SafetyContext("web", url="https://bank.com")
    sink.record(Type(text="hunter2"), _result(), ctx, approved=True, redact_text=True)
    entry = json.loads((tmp_path / "s.jsonl").read_text(encoding="utf-8").strip())
    assert entry["action"]["text"] == REDACTED
    assert "hunter2" not in (tmp_path / "s.jsonl").read_text(encoding="utf-8")


def test_audit_keeps_text_when_not_flagged(tmp_path):
    sink = AuditSink(tmp_path / "s.jsonl")
    sink.record(Type(text="hello"), _result(), None, approved=True, redact_text=False)
    entry = json.loads((tmp_path / "s.jsonl").read_text(encoding="utf-8").strip())
    assert entry["action"]["text"] == "hello"


def test_audit_creates_parent_dir(tmp_path):
    AuditSink(tmp_path / "nested" / "deep" / "s.jsonl").record(
        Click(1, 1), _result(Verdict.ALLOW), None, None
    )
    assert (tmp_path / "nested" / "deep" / "s.jsonl").exists()


def test_null_audit_sink_writes_nothing(tmp_path):
    NullAuditSink().record(Click(1, 1), _result(), None, True, redact_text=True)
    assert list(tmp_path.iterdir()) == []
