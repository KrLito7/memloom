"""Google Antigravity conversation transcripts.

Format: ``~/.gemini/antigravity/brain/<conversation-uuid>/.system_generated/logs/transcript.jsonl``
-- one JSON object per step, ordered by ``step_index``::

    source=USER_EXPLICIT type=USER_INPUT       content = "<USER_REQUEST>...</USER_REQUEST>" + metadata blocks
    source=MODEL         type=PLANNER_RESPONSE content = what the model said, tool_calls = [{name, args}]
    source=MODEL         type=GENERIC          content = the output of the oldest unanswered tool call
    source=SYSTEM        type=SYSTEM_MESSAGE   harness reminders and background-task notices (skipped)

The directory also holds ``transcript_full.jsonl`` (the same steps with long fields
un-truncated). Only ``transcript.jsonl`` is read: taking both would count every conversation
twice.

.. note::
   Tool results carry no call id, so they are paired with the pending tool calls **in order**.
   That is exact for the sequential calls this format records and a close approximation when
   one response issues several calls at once.
"""

from __future__ import annotations

import os
import re
from typing import Optional

from ..extract import is_error_line
from ..model import Session, ToolUse, Turn
from ..util import parse_iso
from .base import Adapter, clip, fallback_title, read_jsonl

__all__ = ["AntigravityAdapter"]

_USER_REQUEST = re.compile(r"<USER_REQUEST>\s*(.*?)\s*</USER_REQUEST>", re.S)
#: metadata blocks the harness appends to every user message
_META_BLOCK = re.compile(
    r"<(ADDITIONAL_METADATA|USER_SETTINGS_CHANGE|SYSTEM_MESSAGE)>.*?</\1>", re.S
)

#: argument keys worth summarising, in priority order (Antigravity tools use CamelCase names)
_ARG_KEYS = (
    "CommandLine", "Path", "AbsolutePath", "TargetFile", "SearchPath", "Query", "query",
    "Url", "Prompt", "Description", "toolSummary", "Action", "TaskId",
)


def _conversation_id(path: str) -> str:
    """``.../brain/<uuid>/.system_generated/logs/transcript.jsonl`` -> ``<uuid>``."""
    parts = os.path.abspath(path).replace("\\", "/").split("/")
    if "brain" in parts:
        i = len(parts) - 1 - parts[::-1].index("brain")
        if i + 1 < len(parts) - 1:
            return parts[i + 1]
    return os.path.basename(os.path.dirname(path)) or "antigravity"


def _prompt_of(content: str) -> str:
    """The user's own words, without the wrapper tags and harness metadata."""
    content = content or ""
    m = _USER_REQUEST.search(content)
    text = m.group(1) if m else content
    return _META_BLOCK.sub("", text).strip()


def _summary(name: str, args) -> str:
    if isinstance(args, dict):
        for k in _ARG_KEYS:
            v = args.get(k)
            if isinstance(v, str) and v.strip():
                v = v.strip()
                # arguments arrive JSON-quoted twice: '"Get-ChildItem D:\\"'
                if len(v) >= 2 and v[0] == v[-1] == '"':
                    v = v[1:-1]
                return clip(re.sub(r"\s+", " ", v), 140)
    return Adapter.tool_summary(name, args)


def _first_error(output: str) -> str:
    for line in (output or "").splitlines():
        if is_error_line(line):
            return clip(line.strip(), 300)
    return ""


class AntigravityAdapter(Adapter):
    name = "antigravity"
    label = "Google Antigravity"
    suffixes = (".jsonl",)

    def default_roots(self) -> list:
        return [os.path.join(os.path.expanduser("~"), ".gemini", "antigravity", "brain")]

    def match(self, path: str) -> bool:
        p = path.replace("\\", "/")
        return (
            "/.gemini/antigravity/" in p
            and "/brain/" in p
            and os.path.basename(p) == "transcript.jsonl"
        )

    # No content sniff on purpose: ``transcript_full.jsonl`` looks identical, and claiming it
    # would load every conversation twice. Files outside the default tree can still be read
    # by keeping the ``.gemini/antigravity/brain/`` layout.

    def load(self, path: str) -> Optional[Session]:
        times, turns, pending = [], [], []
        model = None
        cur = None

        for d in read_jsonl(path):
            ts = parse_iso(d.get("created_at"))
            typ = d.get("type")
            content = d.get("content") if isinstance(d.get("content"), str) else ""

            if typ == "USER_INPUT":
                text = _prompt_of(content)
                if not text:
                    continue
                if ts:
                    times.append(ts)
                cur = Turn(index=len(turns) + 1, at=ts, prompt=clip(text, 4000))
                turns.append(cur)
                pending = []
            elif typ == "PLANNER_RESPONSE":
                if ts:
                    times.append(ts)
                model = d.get("model") or model
                if cur is None:
                    cur = Turn(index=len(turns) + 1, at=ts)
                    turns.append(cur)
                if content.strip():
                    reply = clip(content, 4000)
                    cur.reply = (cur.reply + "\n\n" + reply).strip() if cur.reply else reply
                for call in d.get("tool_calls") or []:
                    if not isinstance(call, dict):
                        continue
                    name = call.get("name") or "?"
                    tu = ToolUse(name=name, summary=_summary(name, call.get("args")))
                    cur.tools.append(tu)
                    pending.append(tu)
            elif typ == "GENERIC":
                if ts:
                    times.append(ts)
                if not pending:
                    continue
                tu = pending.pop(0)
                tu.ok = True
                err = _first_error(content)
                if err:
                    tu.ok = False
                    tu.error = err
            # SYSTEM_MESSAGE and anything new: ignored on purpose

        if not any(t.prompt or t.reply or t.tools for t in turns):
            return None

        return Session(
            id=_conversation_id(path),
            source=os.path.abspath(path),
            adapter="antigravity",
            title=fallback_title(turns),
            cwd=None,
            model=model,
            started_at=times[0] if times else None,
            ended_at=times[-1] if times else None,
            turns=turns,
        )
