"""Tiny in-process registry for providers and executors (SPEC-5).

Replaces the growing if/elif factories in `config.py` with a name→factory map that
built-ins populate via a decorator. Deliberately *internal* only (OQ-5a, KISS): no
`importlib.metadata` entry-points, no third-party plugin discovery — this is a
personal tool, and entry-points would be speculative generality. Adding a provider
is now one `@PROVIDERS.register("name")` factory next to its peers, and an unknown
name raises a clear error listing what *is* registered.

Each factory is a callable taking the same keyword args the old branch used
(`client`, `display_size`, `environment`, `page`) and ignoring those it doesn't need.
"""
from __future__ import annotations

from typing import Callable


class Registry:
    def __init__(self, kind: str) -> None:
        self._kind = kind
        self._factories: dict[str, Callable] = {}

    def register(self, *names: str) -> Callable[[Callable], Callable]:
        def decorate(factory: Callable) -> Callable:
            for name in names:
                self._factories[name.strip().lower()] = factory
            return factory
        return decorate

    def create(self, name: str, **kwargs):
        key = name.strip().lower()
        factory = self._factories.get(key)
        if factory is None:
            known = ", ".join(sorted(self._factories)) or "(none)"
            raise ValueError(f"Unknown {self._kind}: {name!r} (registered: {known})")
        return factory(**kwargs)

    def names(self) -> set[str]:
        return set(self._factories)


PROVIDERS = Registry("provider")
EXECUTORS = Registry("executor")
