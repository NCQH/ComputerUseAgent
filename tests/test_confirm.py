from cua.ui.confirm import make_cli_confirm_handler, auto_approve, auto_reject
from cua.models import ConfirmRequest, Click


async def test_auto_helpers():
    req = ConfirmRequest(action=Click(1, 1), reason="x")
    assert await auto_approve(req) is True
    assert await auto_reject(req) is False


async def test_cli_handler_approves_on_yes():
    prompts = []
    async def ask():
        return "y"
    handler = make_cli_confirm_handler(prompts.append, ask)
    req = ConfirmRequest(action=Click(9, 9), reason="denylist: submit")
    assert await handler(req) is True
    assert len(prompts) == 1
    assert "denylist: submit" in prompts[0]


async def test_cli_handler_rejects_on_anything_else():
    async def ask_no():
        return "n"
    async def ask_blank():
        return ""
    h1 = make_cli_confirm_handler(lambda _s: None, ask_no)
    h2 = make_cli_confirm_handler(lambda _s: None, ask_blank)
    req = ConfirmRequest(action=Click(1, 1), reason="r")
    assert await h1(req) is False
    assert await h2(req) is False


async def test_cli_handler_accepts_yes_word_case_insensitively():
    async def ask():
        return "  YES  "
    handler = make_cli_confirm_handler(lambda _s: None, ask)
    req = ConfirmRequest(action=Click(1, 1), reason="r")
    assert await handler(req) is True
