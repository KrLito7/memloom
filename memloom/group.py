"""Clustering: sessions -> projects -> topics, with no hand-written alias tables.

The old pipeline needed a `CANON` dict, a `SUPERSEDED` list and a `TOPIC_ALIAS` map that
somebody had to maintain by hand. memloom replaces all of it with two boring rules:

* **a project is a working directory** (plus directories that provably share files)
* **a topic is a repeatable signal** — a normalised error fingerprint or a hot file/command

That means a fresh clone on a stranger's machine produces sensible pages on the first run,
which hand-curated aliases can never do.
"""

from __future__ import annotations

import os
import re
from collections import Counter
from dataclasses import dataclass, field
from typing import Dict, List

from .extract import (
    command_head,
    extract_commands,
    extract_paths,
    error_lines,
    fingerprint,
    path_component,
    session_texts,
)
from .util import is_informative_error, settle, short_tool_name

__all__ = ["SessionFacts", "Project", "Topic", "analyze", "group_projects", "group_topics"]


@dataclass
class SessionFacts:
    paths: Counter = field(default_factory=Counter)
    components: Counter = field(default_factory=Counter)
    commands: Counter = field(default_factory=Counter)
    errors: List[tuple] = field(default_factory=list)  # [(fingerprint, sample)]
    tools: Dict[str, int] = field(default_factory=dict)

    @property
    def top_paths(self) -> List[str]:
        return [p for p, _ in self.paths.most_common(80)]

    @property
    def error_keys(self) -> List[str]:
        seen, out = set(), []
        for fp, _s in self.errors:
            if fp and fp not in seen:
                seen.add(fp)
                out.append(fp)
        return out


@dataclass
class Project:
    name: str
    cwds: List[str] = field(default_factory=list)
    sessions: List[str] = field(default_factory=list)  # session ids, chronological
    paths: Counter = field(default_factory=Counter)
    components: Counter = field(default_factory=Counter)
    errors: Counter = field(default_factory=Counter)

    @property
    def n_sessions(self) -> int:
        return len(self.sessions)

    @property
    def top_files(self) -> List[str]:
        return [p for p, _ in self.paths.most_common(40)]


@dataclass
class Topic:
    title: str
    category: str
    sessions: List[str] = field(default_factory=list)
    evidence: List[str] = field(default_factory=list)
    count: int = 0
    #: untightened fingerprint, kept so a shortened title that collides with
    #: another topic can fall back to the full one instead of being dropped
    raw: str = ""

    @property
    def key(self) -> str:
        return self.title


# ------------------------------------------------------------------ per session

def analyze(session) -> SessionFacts:
    texts = list(session_texts(session))
    facts = SessionFacts()
    facts.paths = extract_paths(texts)
    facts.commands = extract_commands(
        [t for t in texts if t], [tu.name for tu in _all_tools(session)]
    )
    facts.components = Counter()
    for p, n in facts.paths.items():
        comp = path_component(p, depth=2)
        if comp:
            facts.components[comp] += n
    facts.errors = _errors_of(texts)
    facts.tools = session.tool_histogram
    return facts


def _all_tools(session):
    for t in session.turns:
        for tu in t.tools:
            yield tu


def _low_information(fp: str) -> bool:
    """A fingerprint that names no symptom: ``Traceback``, ``Exit code N``, ``pg.on``.

    Such a title tells the reader nothing, and the page would just list every session
    that ever failed at all. A lone ``SyntaxError`` / ``ECONNREFUSED`` is still a symptom.
    """
    f = re.sub(r"<n>", "n", fp or "")
    f = re.sub(r"\([^)]*\)?", " ", f).strip(" :.-").lower()
    f = re.sub(r"\s+", " ", f)
    if f in {"traceback", "traceback most recent call last", "exit code n", "exit code",
             "error", "failed", "fatal", ""}:
        return True
    if re.match(r"^exit code:? n\b", f) and len(f.split()) <= 4:
        return True
    # source code that merely *mentions* an error word (``pg.on("console", lambda m: ...``)
    if re.search(r"\b\w+\.\w+\(\s*[\"']|\blambda\b|=>", (fp or "").lower()):
        return True
    if len(f.split()) < 2 and not re.search(r"error|exception|econn|eacces|enoent|eperm|timeout", f):
        return True
    return False


def _errors_of(texts) -> List[tuple]:
    out, seen = [], set()
    for line in error_lines(texts):
        fp = fingerprint(line)
        if not fp or fp in seen or _low_information(fp):
            continue
        seen.add(fp)
        out.append((fp, line[:400]))
        if len(out) >= 40:
            break
    return out


# ------------------------------------------------------------------ projects

_GENERIC_COMPONENTS = {"README", "readme", "package.json", "tsconfig.json", "pyproject.toml"}


def _cwd_key(cwd: str) -> str:
    if not cwd:
        return ""
    p = cwd.replace("\\", "/").rstrip("/")
    return p


def _cwd_name(cwd: str) -> str:
    p = _cwd_key(cwd)
    if not p:
        return "未标注工作目录"
    parts = [x for x in p.split("/") if x]
    if not parts:
        return p
    tail = parts[-1]
    if len(tail) > 3 and tail[1:3] == "--":
        # Claude Code flattens a project path into ``C--Users-you`` (every
        # separator becomes '-'). Restore it so the name and the home check stay sane.
        p = (tail[0] + ":/" + tail[3:].replace("-", "/")).rstrip("/")
        parts = [x for x in p.split("/") if x]
        tail = parts[-1] if parts else tail
    home = os.path.expanduser("~").replace("\\", "/").rstrip("/").lower()
    if p.lower() == home:
        # the session ran from home, so it says nothing about which project it was
        return "家目录"
    return tail or p


def group_projects(
    sessions: Dict[str, object],
    factsmap: Dict[str, SessionFacts],
    split_threshold: int = 12,
) -> List[Project]:
    """Group by cwd, merge directories that share files, then split crowded buckets.

    The split step matters in practice: most people run every session from the *same*
    workspace directory, so "one cwd = one project" would collapse a hundred sessions
    into one useless page. When a bucket is crowded we re-cluster its sessions by the
    files they actually touched, and name each sub-project after its dominant folder.
    """
    buckets: Dict[str, Project] = {}
    order: List[str] = []
    for sid, s in sessions.items():
        cwd = _cwd_key(getattr(s, "cwd", "") or "")
        key = cwd or "\x00none"
        if key not in buckets:
            buckets[key] = Project(name=_cwd_name(cwd or ""))
            order.append(key)
        proj = buckets[key]
        proj.sessions.append(sid)
        f = factsmap.get(sid)
        if f:
            proj.paths.update(f.paths)
            proj.components.update(f.components)
            for fp in f.error_keys:
                proj.errors[fp] += 1
        if cwd and cwd not in proj.cwds:
            proj.cwds.append(cwd)

    projects = [buckets[k] for k in order]
    _merge_by_shared_files(projects, factsmap)
    projects = [p for p in projects if p.sessions]
    projects = _split_oversized(projects, factsmap, split_threshold)

    projects.sort(key=lambda p: (-p.n_sessions, p.name))
    seen = Counter()
    for p in projects:
        seen[p.name] += 1
        if seen[p.name] > 1:
            p.name = f"{p.name} ({seen[p.name]})"
    for p in projects:
        p.sessions.sort()
    return projects


#: folder names that say nothing about what a session was about
_GENERIC_DIRS = {
    "src", "lib", "app", "apps", "packages", "scripts", "script", "tools", "tool",
    "test", "tests", "__tests__", "spec", "specs", "docs", "doc", "dist", "build",
    "out", "output", "tmp", "temp", "cache", ".cache", "node_modules", ".venv", "venv",
    "env", ".git", ".github", "__pycache__", "static", "public", "assets", "images",
    "img", "config", "configs", "bin", "obj", "target", "vendor", "logs", "log",
    "raw", "per", "lite", "micro", "data", "input", "outputs", "users", "administrator",
    "documents", "desktop", "workspace", "projects", "sessions", "home",
    "core", "hooks", "references", "common", "shared", "utils", "util", "types",
    "router", "routes", "models", "services", "components", "pages", "layouts",
    "themes", "styles", "media", "node_modules", "asar-dump",
    # scratch spaces and throwaway output: the session ran *somewhere*, that is all it says
    "preview", "review", "renders", "render", "scratch", "sandbox", "experiments",
    "sheet", "seen", "dialogue", "conversation", "对话记录", "临时", "草稿",
    # OS / browser / installer plumbing that sessions touch but never *work on*
    "appdata", "chrome-profile", "state", "globalstorage", "program", "program files",
    "program files (x86)", "windowsapps", "local", "roaming", "programdata",
}

#: auto-generated task / job ids (``b08k6i984``): letters mixed with digits, no separators
_RANDOM_ID = re.compile(r"^(?=[a-z0-9]*\d)(?=[a-z0-9]*[a-z])[a-z0-9]{8,14}$", re.I)


def _split_oversized(projects: List[Project], factsmap: Dict[str, SessionFacts], threshold: int) -> List[Project]:
    """Split a crowded cwd into sub-projects — but only when the split is defensible.

    Guards against the failure mode where a dozen unrelated sessions each get their own
    one-session page named after whatever folder they happened to touch:

    * a sub-project must hold **at least two** sessions (a lone session is noise)
    * leftover singletons fold back into the parent bucket
    * if that leaves a single group, no split happens at all
    """
    out: List[Project] = []
    for proj in projects:
        if proj.n_sessions < threshold:
            out.append(proj)
            continue
        groups = _partition_by_files(proj.sessions, factsmap)
        big = [g for g in groups if len(g) >= 2]
        singletons = [sid for g in groups if len(g) == 1 for sid in g]
        if len(big) < 2 and not (len(big) == 1 and len(singletons) >= 2):
            out.append(proj)
            continue

        def build(name: str, sids: List[str]) -> Project:
            sub = Project(name=name, cwds=list(proj.cwds), sessions=sorted(sids))
            for sid in sids:
                f = factsmap.get(sid)
                if not f:
                    continue
                sub.paths.update(f.paths)
                sub.components.update(f.components)
                for fp in f.error_keys:
                    sub.errors[fp] += 1
            return sub

        taken = {p.name for p in out} | {proj.name}
        leftovers: List[str] = []
        for g in big:
            cands = _name_candidates(g, factsmap, proj.name)
            if not cands:
                leftovers.extend(g)  # cannot name it -> do not split it out
                continue
            name = next((c for c in cands if c not in taken), cands[0])
            taken.add(name)
            out.append(build(name, g))
        rest_ids = singletons + leftovers
        if rest_ids:
            rest = build(proj.name, rest_ids)
            if proj.cwds:
                rest.name = proj.name
            out.append(rest)
    return out


def _partition_by_files(sids: List[str], factsmap: Dict[str, SessionFacts]) -> List[List[str]]:
    """Connected components over "these two sessions touched the same files"."""
    sets = []
    for sid in sids:
        f = factsmap.get(sid)
        sets.append({p.lower() for p in f.paths} if f else set())

    n = len(sids)
    parent = list(range(n))

    def find(i: int) -> int:
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    for i in range(n):
        if not sets[i]:
            continue
        for j in range(i + 1, n):
            if not sets[j]:
                continue
            inter = len(sets[i] & sets[j])
            if inter < 2:
                continue
            jac = inter / float(len(sets[i] | sets[j]) or 1)
            if inter >= 6 or jac >= 0.2:
                ri, rj = find(i), find(j)
                if ri != rj:
                    parent[rj] = ri

    comp: Dict[int, List[str]] = {}
    for i, sid in enumerate(sids):
        comp.setdefault(find(i), []).append(sid)
    return sorted(comp.values(), key=len, reverse=True)


def _name_candidates(sids: List[str], factsmap: Dict[str, SessionFacts], base: str) -> List[str]:
    """Possible ``base · something`` names for a bucket, most informative first.

    Two passes: business-looking directories (strict) beat generic ones (``src``, ``out``,
    ``lite``). A bucket that yields nothing better than ``base`` itself is *unnamable* —
    the caller then refuses to split it, because ``project (2)`` / ``project (3)`` pages
    are worse than one honest big page.
    """
    strict: Counter = Counter()
    loose: Counter = Counter()
    for sid in sids:
        f = factsmap.get(sid)
        if not f:
            continue
        for p, n in f.paths.items():
            parts = [x for x in p.split("/") if x]
            if len(parts) < 2:
                continue
            raw = parts[-2]
            d = raw.lower()
            if len(d) < 3 or d.startswith("."):
                continue
            weight = 1 + (n // 10)
            if d in _GENERIC_DIRS or raw.startswith("_"):
                loose[raw] += weight
            else:
                strict[raw] += weight

    out: List[str] = []
    seen = set()
    for counter in (strict, loose):
        for name, _count in counter.most_common(3):
            if name.lower() in base.lower():
                continue
            full = f"{base} · {name}"
            if full.lower() in seen:
                continue
            seen.add(full.lower())
            out.append(full)
    return out


def _merge_by_shared_files(projects: List[Project], factsmap: Dict[str, SessionFacts]) -> None:
    """Union cwds whose session file sets overlap strongly (workspace vs subdir)."""
    def fileset(p: Project) -> set:
        s = {x for x in p.paths if os.path.basename(x).lower() not in {g.lower() for g in _GENERIC_COMPONENTS}}
        return {x.lower() for x in s}

    sets = [fileset(p) for p in projects]
    n = len(projects)
    parent = list(range(n))

    def find(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    def union(a, b):
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[rb] = ra

    for i in range(n):
        if not sets[i]:
            continue
        for j in range(i + 1, n):
            if not sets[j]:
                continue
            inter = len(sets[i] & sets[j])
            if inter < 5:
                continue
            jac = inter / float(len(sets[i] | sets[j]) or 1)
            if jac >= 0.3 or inter >= 12:
                union(i, j)

    merged: Dict[int, Project] = {}
    for i, p in enumerate(projects):
        r = find(i)
        if r not in merged:
            merged[r] = Project(name=p.name)
        tgt = merged[r]
        if tgt.name != p.name and p.n_sessions > 0 and not tgt.cwds and not tgt.sessions:
            tgt.name = p.name
        tgt.sessions.extend(p.sessions)
        tgt.paths.update(p.paths)
        tgt.components.update(p.components)
        tgt.errors.update(p.errors)
        for c in p.cwds:
            if c not in tgt.cwds:
                tgt.cwds.append(c)
    projects[:] = list(merged.values())


# ------------------------------------------------------------------ topics

_GENERIC_HEADS = {
    "tool:pwsh", "tool:bash", "tool:shell", "tool:read", "tool:write", "tool:edit",
    "tool:glob", "tool:grep", "tool:ls", "tool:multi_tool_use", "pwsh", "bash", "sh",
    "powershell", "cmd", "ls", "dir", "cat", "type",
}


def group_topics(
    sessions: Dict[str, object],
    factsmap: Dict[str, SessionFacts],
    max_pitfalls: int = 40,
    max_code: int = 24,
    max_tools: int = 12,
) -> List[Topic]:
    err_sessions: Dict[str, List[str]] = {}
    err_sample: Dict[str, str] = {}
    comp_sessions: Dict[str, List[str]] = {}
    cmd_sessions: Dict[str, List[str]] = {}

    for sid in sessions:
        f = factsmap.get(sid)
        if not f:
            continue
        for fp, sample in f.errors:
            err_sessions.setdefault(fp, []).append(sid)
            err_sample.setdefault(fp, sample)
        for comp, n in f.components.items():
            if n >= 2:
                comp_sessions.setdefault(comp, []).append(sid)
        for head, n in f.commands.items():
            if head in _GENERIC_HEADS:
                continue
            cmd_sessions.setdefault(head, []).append(sid)

    topics: List[Topic] = []

    for fp, sids in err_sessions.items():
        if len(sids) < 2:
            continue  # a one-off failure is noise, not a topic
        if not is_informative_error(fp):
            continue  # "Error" / "Failed" on their own name no subject; see util
        topics.append(
            Topic(
                # The fingerprint is capped at 150 chars, which then gets cut again by
                # safe_name(limit=60) at whatever character happens to land there --
                # 「踩坑-API Error： N Not enough point. Need N, reduce…」. Tighten here
                # instead, so the page name ends on a boundary and nothing is cut twice.
                title=settle(fp, 34),
                category="踩坑",
                sessions=_uniq(sids),
                evidence=[err_sample.get(fp, "")],
                count=len(sids),
                raw=fp,
            )
        )
    topics.sort(key=lambda t: -t.count)
    topics = topics[:max_pitfalls]

    code = [
        Topic(title=_collapse_compound(c), category="代码", sessions=_uniq(s), count=len(s))
        for c, s in comp_sessions.items()
        if len(s) >= 3 and _is_code_topic(c)
    ]
    code.sort(key=lambda t: -t.count)
    topics.extend(code[:max_code])

    tools = [
        Topic(title=short_tool_name(h), category="工具", sessions=_uniq(s), count=len(s))
        for h, s in cmd_sessions.items()
        if len(s) >= 3
    ]
    tools.sort(key=lambda t: -t.count)
    topics.extend(tools[:max_tools])

    # unique titles (a component and a command may collide)
    #
    # Tightening a fingerprint for readability can make two different ones land on
    # the same title. They are near-identical by construction -- same first 34
    # characters of the same symptom -- so merge them and union the sessions.
    # Dropping one deletes a topic; falling back to the full name undoes the
    # tightening for exactly the long names people complain about.
    merged: Dict[tuple, Topic] = {}
    out: List[Topic] = []
    for t in topics:
        k = (t.category, t.title)
        prev = merged.get(k)
        if prev is not None:
            prev.sessions = _uniq(list(prev.sessions) + list(t.sessions))
            prev.count = len(prev.sessions)
            if not prev.evidence:
                prev.evidence = t.evidence
            continue
        merged[k] = t
        out.append(t)
    out.sort(key=lambda t: -t.count)
    return out


_TOPIC_SEP = re.compile(r"[／/]")


def _collapse_compound(name: str) -> str:
    """``cc-switch／cc-switch`` -> ``cc-switch``: naming the same folder twice adds nothing."""
    parts = [p.strip() for p in _TOPIC_SEP.split(name or "") if p.strip()]
    if len(parts) == 2 and parts[0].lower() == parts[1].lower():
        return parts[0]
    return name

#: a "folder" that is really the name of an interpreter says nothing about the work
_SHELL_HEADS = {
    "python", "python3", "py", "node", "npm", "pnpm", "yarn", "deno", "bun",
    "bash", "sh", "zsh", "pwsh", "powershell", "cmd", "git", "uv", "pip",
}

#: packaged binaries and lockfiles leak through as bold "folders"
_ARTIFACT_EXT = (".asar", ".egg", ".whl", ".jar", ".zip", ".tar", ".gz", ".dmg", ".exe")


def _is_code_topic(name: str) -> bool:
    """A folder worth a 代码 page: specific enough that a reader learns something.

    ``images``, ``shared``, ``1`` — such pages are empty shells, so they are dropped
    even when they appear in many sessions. Compounds are judged by their **head**:
    ``bin/bash`` and ``app.asar/dsh`` only say *where* a command ran, while
    ``douyin-duty/seen`` still points at something you could open.
    """
    n = (name or "").strip()
    if len(n) < 4 or n.isdigit():
        return False
    if n.lower() in _GENERIC_DIRS:
        return False
    parts = [p for p in _TOPIC_SEP.split(n) if p]
    if not parts:
        return False
    head = parts[0].strip()
    if len(head) < 4 or head.isdigit():
        return False
    bare = re.sub(r"\d+$", "", head.lower())
    if head.lower() in _GENERIC_DIRS or head.lower() in _SHELL_HEADS:
        return False
    if bare in _SHELL_HEADS or bare in _GENERIC_DIRS:
        return False
    if head.lower().endswith(_ARTIFACT_EXT):
        return False
    # a random job id anywhere in the path (``tasks/b08k6i984``) is not a subject
    if any(_RANDOM_ID.match(p.strip()) for p in parts):
        return False
    # a trailing generic part (``.../1``, ``.../config``) is filler, not a subject
    for p in parts[1:]:
        p = p.strip()
        if p.isdigit() or (len(p) >= 4 and p.lower() in _GENERIC_DIRS):
            return False
    return any(ch.isalpha() for ch in n)


def _uniq(items) -> List[str]:
    seen, out = set(), []
    for x in items:
        if x not in seen:
            seen.add(x)
            out.append(x)
    return out
