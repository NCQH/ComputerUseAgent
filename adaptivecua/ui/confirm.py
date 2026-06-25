"""Confirmation handlers for the irreversibility gate."""
from __future__ import annotations


async def auto_approve(request) -> bool:
    return True


async def auto_reject(request) -> bool:
    return False


def make_cli_confirm_handler(prompt_fn, ask_fn):
    async def handler(request) -> bool:
        prompt_fn(
            f"Cần xác nhận: {request.reason}\n"
            f"  Hành động: {request.action}\n"
            f"  Cho phép? [y/N] "
        )
        answer = await ask_fn()
        return str(answer).strip().lower() in {"y", "yes"}
    return handler
