import os
import shutil
import tempfile
from pathlib import Path

from cua.env import load_dotenv


def _make_env(content: str) -> Path:
    # Use a repo-local temp dir; the system temp dir is not writable in CI here.
    d = Path(tempfile.mkdtemp(dir=os.getcwd(), prefix=".envtest_"))
    p = d / ".env"
    p.write_text(content, encoding="utf-8")
    return p


def test_loads_keys_and_skips_comments_and_blanks():
    env = _make_env(
        "# a comment\n"
        "\n"
        "OPENAI_API_KEY=sk-test-123\n"
        "ANTHROPIC_API_KEY = sk-ant-456 \n"
        'QUOTED="value with spaces"\n'
        "EMPTY=\n"
    )
    try:
        loaded = load_dotenv(env, environ={})
        assert loaded["OPENAI_API_KEY"] == "sk-test-123"
        assert loaded["ANTHROPIC_API_KEY"] == "sk-ant-456"
        assert loaded["QUOTED"] == "value with spaces"
        assert loaded["EMPTY"] == ""
    finally:
        shutil.rmtree(env.parent, ignore_errors=True)


def test_does_not_override_existing_environment():
    env = _make_env("OPENAI_API_KEY=from-file\n")
    try:
        existing = {"OPENAI_API_KEY": "from-real-env"}
        loaded = load_dotenv(env, environ=existing)
        assert existing["OPENAI_API_KEY"] == "from-real-env"  # real env wins
        assert "OPENAI_API_KEY" not in loaded
    finally:
        shutil.rmtree(env.parent, ignore_errors=True)


def test_missing_file_is_a_noop():
    assert load_dotenv(Path(os.getcwd()) / "definitely_missing.env", environ={}) == {}


def test_default_targets_process_environ():
    env = _make_env("CUA_SMOKE_VAR=hello\n")
    try:
        os.environ.pop("CUA_SMOKE_VAR", None)
        load_dotenv(env)  # default environ = os.environ
        assert os.environ.get("CUA_SMOKE_VAR") == "hello"
    finally:
        os.environ.pop("CUA_SMOKE_VAR", None)
        shutil.rmtree(env.parent, ignore_errors=True)
