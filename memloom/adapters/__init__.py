"""Adapter registry + auto detection."""

from __future__ import annotations

import os
from typing import List, Optional

from .antigravity import AntigravityAdapter
from .base import Adapter, guess_kind
from .claude_code import ClaudeCodeAdapter
from .codex import CodexAdapter
from .dsh import DshAdapter

__all__ = ["Adapter", "ADAPTERS", "get_adapter", "detect_adapter", "all_default_roots", "adapter_names"]

ADAPTERS: List[Adapter] = [DshAdapter(), ClaudeCodeAdapter(), CodexAdapter(), AntigravityAdapter()]


def adapter_names() -> List[str]:
    return [a.name for a in ADAPTERS]


def get_adapter(name: str) -> Adapter:
    for a in ADAPTERS:
        if a.name == name:
            return a
    raise KeyError(f"unknown adapter {name!r}; known: {', '.join(adapter_names())}")


def _head(path: str, limit: int = 16384) -> str:
    """First few KB of the file as text (decompressing if needed)."""
    try:
        if path.endswith(".zstd"):
            from .. import zstd_frames

            payload, _ = zstd_frames.decompress(path)
            return payload[:limit].decode("utf-8", "replace")
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            return f.read(limit)
    except Exception:
        return ""


def detect_adapter(path: str) -> Optional[Adapter]:
    """Which adapter claims this file: path shape first, then a cheap content sniff."""
    for a in ADAPTERS:
        try:
            if a.match(path):
                return a
        except Exception:
            continue
    head = _head(path)
    if head:
        for a in ADAPTERS:
            try:
                if a.sniff(head):
                    return a
            except Exception:
                continue
    return None


def all_default_roots() -> List[tuple]:
    """``[(adapter_name, root)]`` for every adapter that has a default location."""
    out = []
    for a in ADAPTERS:
        for r in a.default_roots():
            out.append((a.name, r))
    return out


def roots_with_data() -> List[tuple]:
    out = []
    for name, root in all_default_roots():
        if os.path.isdir(root):
            out.append((name, root))
    return out
