"""Tiny zero-dependency .env loader.

Loads KEY=VALUE lines into the given environment mapping without overriding
values that are already set (so real environment variables always win). Returns
a dict of the keys it actually set.
"""
from __future__ import annotations

import os
from pathlib import Path


def load_dotenv(path=".env", environ=None) -> dict[str, str]:
    environ = os.environ if environ is None else environ
    p = Path(path)
    if not p.is_file():
        return {}

    loaded: dict[str, str] = {}
    for raw in p.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip()
        if (len(value) >= 2) and value[0] == value[-1] and value[0] in ("'", '"'):
            value = value[1:-1]
        if not key or key in environ:
            continue
        environ[key] = value
        loaded[key] = value
    return loaded
