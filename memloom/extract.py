"""Rule-based extraction. No LLM, no API key, deterministic and reproducible.

Everything memloom knows about a session comes from four extractors:

* **paths** — which files were touched (drives project clustering)
* **commands** — which tools ran (drives topic clustering)
* **errors** — normalised fingerprints of failures (drives the 踩坑 / pitfalls pages)
* **stats** — tool histogram, turn counts, cost

The trade-off is deliberate: rule-based output is boring but honest, fast, offline, and
identical on every machine. A human-readable narrative layer (``--enrich``) is optional
and lives in ``memloom/llm.py`` (roadmap).
"""

from __future__ import annotations

import os
import re
from collections import Counter
from typing import Iterable, List

__all__ = [
    "session_texts",
    "extract_paths",
    "extract_commands",
    "error_lines",
    "fingerprint",
    "is_error_line",
    "path_component",
    "command_head",
]


# ---------------------------------------------------------------- regex rules

_WIN_PATH = re.compile(r"(?<![\w:\\/])([A-Za-z]:[\\/][^\s\"'`<>|*?]+)")
_POSIX_PATH = re.compile(r"(?<![\w:/.])(/(?:[\w.\-]+/)+[\w.\-]+)")
_REL_PATH = re.compile(r"(?<![\w/\\])((?:[\w.\-]+/)+[\w.\-]+\.[A-Za-z0-9]{1,6})\b")
_EXT = re.compile(r"\.[A-Za-z0-9]{1,8}$")
_URL = re.compile(r"^[a-zA-Z]+://")
_URL_IN_TEXT = re.compile(r"\b[a-zA-Z][a-zA-Z0-9+.\-]*://[^\s\"'`<>)\]]+")

_CMD_HEAD = re.compile(
    r"^\s*(?:sudo\s+)?([A-Za-z][\w.\-]*)\s",
)
_DOLLAR_CMD = re.compile(r"^\s*\$\s+(.+)$")
_KNOWN_HEADS = {
    "npm", "pnpm", "yarn", "npx", "pip", "pip3", "python", "python3", "py", "node", "deno",
    "git", "gh", "docker", "kubectl", "cargo", "go", "rustc", "make", "cmake", "gradle",
    "mvn", "pytest", "jest", "vitest", "tsc", "eslint", "ruff", "black", "mypy",
    "curl", "wget", "ssh", "scp", "robocopy", "xcopy", "copy", "move", "del", "rm", "cp",
    "ls", "dir", "cat", "type", "grep", "rg", "find", "sed", "awk", "tar", "zip", "unzip",
    "powershell", "pwsh", "bash", "sh", "cmd", "docker-compose", "ffmpeg", "playwright",
    "zstd", "robocopy", "code", "winget", "choco", "scoop", "composer", "php", "ruby", "bundle",
}

_ERROR_PAT = re.compile(
    r"(?:"
    r"\b[A-Za-z]*(?:Error|Exception)\b"
    r"|\bTraceback \(most recent call last\)"
    r"|\bfatal:"
    r"|\bERR_[A-Z0-9_]+\b"
    r"|\bE(?:CONN[A-Z]*|ACCES|NOENT|PERM|EXIST|ADDRINUSE|PIPE|TIMEDOUT|NOTFOUND|HOSTUNREACH)\b"
    r"|\bexit code:?\s*[1-9]\d*\b"
    r"|\b(?:failed to|unable to|cannot find|cannot open|cannot read|cannot load"
    r"|not found|not defined|is not a function|permission denied|command not found"
    r"|no such file|timed out|connection refused)\b"
    r"|(?:失败|报错|错误|异常)[:：]"
    r"|无法(?:打开|读取|写入|连接|访问|加载|启动)"
    r")",
    re.I,
)
#: a pasted report has one clause per line; prose has commas. Errors rarely do.
_PROSE_HINT = re.compile(r"[，；]|[（(].+[）)]")
#: test runners shout in capitals — matched case-sensitively so "tests fail" is not news
_UPPER_ERROR = re.compile(r"\bFAIL\b")

_UUID = re.compile(r"\b[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\b", re.I)
_HEX = re.compile(r"\b0x[0-9a-fA-F]+\b")
_TS = re.compile(r"\b\d{4}-\d{2}-\d{2}([T ]\d{2}:\d{2}(:\d{2})?(\.\d+)?)?\b")
_NUM = re.compile(r"\b\d+(?:\.\d+)?\b")
# request ids / trace ids: long alphanumeric blobs that always contain a digit
_LONG_ID = re.compile(r"\b(?=[A-Za-z]*\d)[A-Za-z0-9]{18,}\b")
_INPATH = re.compile(r"(?:[A-Za-z]:)?[\\/][^\s\"'`<>|]+")


# ---------------------------------------------------------------- text access

def session_texts(session) -> Iterable[str]:
    """Every meaningful string in a session, in order (prompts, replies, tool info)."""
    for t in session.turns:
        if t.prompt:
            yield t.prompt
        if t.reply:
            yield t.reply
        for tu in t.tools:
            if tu.summary:
                yield tu.summary
            if tu.error:
                yield tu.error


# ---------------------------------------------------------------- paths

def extract_paths(texts: Iterable[str]) -> Counter:
    """File paths mentioned in the session, normalised to forward slashes.

    URLs are stripped first (``http://h/v1/search`` is not a file), and a path is only
    counted when something more specific is not already present — otherwise
    ``D:/work/app`` shadows and inflates ``D:/work/app/src/main.ts``.
    """
    c = Counter()
    for txt in texts:
        if not txt:
            continue
        txt = _URL_IN_TEXT.sub(" ", txt)
        for m in _WIN_PATH.finditer(txt):
            c[_norm_path(m.group(1))] += 1
        for m in _POSIX_PATH.finditer(txt):
            c[_norm_path(m.group(1))] += 1
        for m in _REL_PATH.finditer(txt):
            raw = m.group(1)
            if _EXT.search(raw):
                c[_norm_path(raw)] += 1
    return _drop_shadowed(c)


def _drop_shadowed(counter: Counter) -> Counter:
    """Remove bare directory prefixes that a longer, more specific path covers."""
    keys = sorted(counter, key=len, reverse=True)
    keep = []
    for k in keys:
        ext = bool(_EXT.search(k))
        if not ext:
            prefix = k + "/"
            if any(x.startswith(prefix) for x in keep):
                continue
        keep.append(k)
    return Counter({k: counter[k] for k in keep})


def _norm_path(p: str) -> str:
    p = p.replace("\\", "/").rstrip(".,;:)]}'\"")
    p = re.sub(r"/{2,}", "/", p)
    return p


def path_component(path: str, depth: int = 1) -> str:
    """Coarse bucket for a path: last ``depth`` components without extension.

    ``D:/work/app/src/render.ts`` -> ``src/render`` (depth=2). Drive letters and other
    single-letter roots are dropped so Windows and POSIX checkouts agree, and leading dots
    are stripped so ``.claude/settings`` and ``claude/settings`` land in the same bucket
    instead of becoming two near-duplicate topics.
    """
    parts = [x for x in _norm_path(path).split("/") if x]
    parts = [x for x in parts if not re.match(r"^[A-Za-z]:$", x)]
    parts = [x.lstrip(".") or x for x in parts]
    if not parts:
        return ""
    parts = parts[-depth:]
    parts[-1] = _EXT.sub("", parts[-1])
    return "/".join(x for x in parts if x)


# ---------------------------------------------------------------- commands

def command_head(cmd: str) -> str:
    """The program name of a shell command line, or '' if it does not look like one."""
    cmd = (cmd or "").strip()
    m = _DOLLAR_CMD.match(cmd)
    if m:
        cmd = m.group(1)
    if not cmd:
        return ""
    m = _CMD_HEAD.match(cmd)
    head = (m.group(1) if m else cmd.split()[0]).strip().lower()
    head = os.path.basename(head.replace("\\", "/"))
    if head.endswith(".exe"):
        head = head[:-4]
    return head if head in _KNOWN_HEADS else ""


def extract_commands(texts: Iterable[str], tool_names: Iterable[str] = ()) -> Counter:
    """Program histogram from shell-ish text plus raw tool names."""
    c = Counter()
    for name in tool_names:
        if name:
            c[f"tool:{name}"] += 1
    for txt in texts:
        if not txt:
            continue
        head = command_head(txt)
        if head:
            c[head] += 1
    return c


# ---------------------------------------------------------------- errors

#: lines that look like errors but carry no symptom worth a page: the user's own decisions,
#: bare exit codes / traceback headers, and PowerShell's error-record wrapper
_NOT_A_BUG = re.compile(
    r"^(?:"
    r"\+?\s*categoryinfo\b.*"
    r"|\+?\s*fullyqualifiederrorid\b.*"
    r")$",
    re.I,
)
#: the user declining a tool call is a decision, not a failure — wherever it sits in the line
_USER_DECISION = re.compile(r"\bthe user (?:cancelled|canceled|rejected|denied|doesn't want)\b", re.I)


def is_error_line(line: str) -> bool:
    """True for a *failure message*, not for prose that merely mentions failure.

    Instructions like「不管发生什么，报告至少留一行（哪怕只写『失败：原因是 X』）」are
    full sentences; grouping them as a repeated bug would poison the whole 踩坑 folder.
    """
    if not line:
        return False
    s = line.strip().strip("`*_>#- \t")
    if not (6 <= len(s) <= 200):
        return False
    if len(_PROSE_HINT.findall(s)) >= 2:
        return False
    if _NOT_A_BUG.match(s) or _USER_DECISION.search(s):
        return False
    if s.count(" ") > 40:
        return False
    return bool(_ERROR_PAT.search(s)) or bool(_UPPER_ERROR.search(s))


def error_lines(texts: Iterable[str], limit: int = 400) -> List[str]:
    out = []
    for txt in texts:
        if not txt:
            continue
        for line in txt.splitlines():
            line = line.strip()
            if is_error_line(line):
                out.append(line)
                if len(out) >= limit:
                    return out
    return out


def fingerprint(line: str, width: int = 150) -> str:
    """Collapse volatile parts so the same failure groups across sessions."""
    s = (line or "").strip()
    s = _UUID.sub("<uuid>", s)
    s = _LONG_ID.sub("<id>", s)
    s = _TS.sub("<ts>", s)
    s = _HEX.sub("0xX", s)
    s = _INPATH.sub("<path>", s)
    s = _NUM.sub("<n>", s)
    s = re.sub(r"\s+", " ", s).strip(" -|{}[](),:;。，")
    # A fingerprint that *opens* with a placeholder has lost its subject
    # ("<path>: No such file or directory"); strip the run so the title starts at a word.
    s = re.sub(r"^(?:<(?:path|uuid|ts|id|n)>[\s:'`,;.：，]*)+", "", s)
    # The tool wrapper's own caption ("Error: ...") is on every single failure, so keeping
    # it spends the title budget on nothing. Drop it and let the real symptom lead.
    s = re.sub(r"^(?:error|exception)\s*[:：]\s*", "", s, flags=re.I)
    return s.strip(" -|{}[](),:;。，")[:width]


def signature_key(fp: str) -> str:
    """Short stable id for a fingerprint (used as a file name / anchor)."""
    import hashlib

    return hashlib.sha1(fp.encode("utf-8")).hexdigest()[:10]
