"""Command line entry point.

    memloom build  --out ./vault          # the only command most people need
    memloom scan                          # what would be read, and from where
    memloom doctor                        # why is my vault empty?
"""

from __future__ import annotations

import argparse
import os
import sys
from typing import List, Optional, Tuple

from . import __version__


# ------------------------------------------------------------------ plumbing

def _utf8_stdout() -> None:
    """Windows consoles default to cp936/cp1252 and explode on CJK output."""
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[attr-defined]
        except (AttributeError, ValueError):
            pass


def _roots_from_args(values: Optional[List[str]]) -> Optional[List[Tuple[str, str]]]:
    """``--root PATH`` or ``--root name=PATH``, repeated."""
    if not values:
        return None
    from .adapters import ADAPTERS

    out: List[Tuple[str, str]] = []
    for raw in values:
        name, path = None, raw
        if "=" in raw and not os.path.exists(raw):
            name, path = raw.split("=", 1)
        if name is None:
            # guess from the path: a directory owned by an adapter, else "auto"
            name = "auto"
            low = os.path.abspath(path).replace("\\", "/").lower()
            for a in ADAPTERS:
                for r in a.default_roots():
                    if r and os.path.abspath(r).replace("\\", "/").lower() in low:
                        name = a.name
                        break
                if name != "auto":
                    break
        if name == "auto":
            out.append(("__auto__", os.path.abspath(path)))
        else:
            out.append((name, os.path.abspath(path)))
    return out


# ------------------------------------------------------------------ build

def cmd_build(args) -> int:
    from .vault import build

    roots = _roots_from_args(args.root)
    if roots:
        # explicit roots: detect per file, labelled "__auto__" for the report
        roots = [("dsh", p) if n == "__auto__" else (n, p) for n, p in roots] if args.adapter == "dsh" else roots

    result = build(
        out_dir=os.path.abspath(args.out),
        roots=roots,
        only=args.adapter if args.adapter != "auto" else None,
        min_turns=args.min_turns,
        since_days=args.since,
        title=args.title,
        source_label=args.source_label,
        tag_prefix=args.tag_prefix,
        split_threshold=args.split,
        dry_run=args.dry_run,
        quiet=args.quiet,
        verbose=args.verbose,
        full=args.full,
    )

    if args.json:
        import json

        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0

    print()
    print(f"会话   {result['sessions']}" + (f"（过滤掉 {result['skipped']}）" if result["skipped"] else ""))
    print(f"主题   {result['topics']}")
    print(f"页面   {result['pages']}" + (f"（本次改动 {result['written']}）" if not args.dry_run else "（dry-run，未写盘）"))
    names = result["project_names"]
    if names:
        print("项目   {}{}".format(result["projects"], "：" if len(names) <= 3 else ""))
        for n in names[:10]:
            print(f"         · {n}")
        if len(names) > 10:
            print(f"         · 另有 {len(names) - 10} 个")
    if result["pruned"]:
        print(f"清理   {result['pruned']} 个过期页面")
    print("缓存   复用 {} / 新解析 {}".format(result["reused"], result["parsed"]))
    print(f"耗时   {result['seconds']}s")
    if result["problems"]:
        print()
        print(f"跳过 {len(result['problems'])} 个文件：")
        for p in result["problems"][:10]:
            print(f"  - {p}")
    if not args.dry_run:
        print()
        print(f"库在   {result['out']}")
        print("用 Obsidian 打开这个文件夹即可。")
    return 0 if (result["ok"] or args.dry_run) else 1


# ------------------------------------------------------------------ scan

def cmd_scan(args) -> int:
    from .vault import scan

    roots = _roots_from_args(args.root)
    pairs = scan(roots, only=args.adapter if args.adapter != "auto" else None)
    if not pairs:
        print("没有找到任何会话存档。")
        print("跑 `memloom doctor` 看每条采集路径在不在。")
        return 1
    rows = []
    for name, path in pairs:
        try:
            size = os.path.getsize(path)
        except OSError:
            size = 0
        rows.append((name, size, path))
    total = sum(r[1] for r in rows)
    by_adapter: dict = {}
    for name, size, _p in rows:
        n, s = by_adapter.get(name, (0, 0))
        by_adapter[name] = (n + 1, s + size)

    from .util import human_size

    print(f"共 {len(rows)} 个存档，{human_size(total)}")
    for name, (n, size) in sorted(by_adapter.items()):
        print(f"  {name:<14} {n:>4} 个  {human_size(size)}")
    if not args.quiet:
        print()
        for name, size, path in rows:
            print(f"  [{name}] {human_size(size):>9}  {path}")
    return 0


# ------------------------------------------------------------------ doctor

def cmd_doctor(args) -> int:
    from .adapters import ADAPTERS, detect_adapter
    from .util import human_size

    ok = True
    print(f"memloom {__version__}")
    print(f"python  {sys.version.split()[0]}  ({sys.executable})")
    if sys.version_info < (3, 9):
        print("  ✗ 需要 Python 3.9+")
        ok = False

    print()
    print("采集路径：")
    any_root = False
    for adapter in ADAPTERS:
        roots = adapter.default_roots()
        found_any = False
        for root in roots:
            if not root:
                continue
            if os.path.isdir(root):
                files = []
                for dirpath, dirnames, filenames in os.walk(root):
                    dirnames[:] = [d for d in dirnames if d not in ("node_modules", ".git")]
                    for fn in filenames:
                        files.append(os.path.join(dirpath, fn))
                matched = [f for f in files if detect_adapter(f)]
                size = 0
                for f in matched:
                    try:
                        size += os.path.getsize(f)
                    except OSError:
                        pass
                if matched:
                    found_any = any_root = True
                    print(f"  ✓ {adapter.name:<14} {len(matched):>4} 个  {human_size(size):>9}  {root}")
                else:
                    print(f"  · {adapter.name:<14} 目录在，但里面没有认得出的会话  {root}")
            else:
                print(f"  · {adapter.name:<14} 不存在  {root}")
        if not found_any:
            pass

    print()
    zstd_files = 0
    for adapter in ADAPTERS:
        for root in adapter.default_roots():
            if not root or not os.path.isdir(root):
                continue
            for dirpath, _d, filenames in os.walk(root):
                zstd_files += sum(1 for fn in filenames if fn.endswith(".zstd"))
    if zstd_files:
        from .zstd_frames import backend

        try:
            b = backend()
            print(f"zstd 后端：{b}（{zstd_files} 个压缩存档可读）")
        except Exception as exc:
            print(f"zstd 后端：不可用 — {exc}")
            print("  装了 pyzstd 就能读压缩存档：pip install memloom[zstd]")
            ok = False
    else:
        print("zstd 后端：不需要（没有压缩存档）")

    print()
    if not any_root:
        print("没有找到任何会话存档 —— 这就是库会是空的原因。")
        print("如果你把工具装在别的地方，用 --root name=PATH 指定。")
        return 1
    print("环境看起来没问题。跑 `memloom build --out ./vault`。")
    return 0 if ok else 1


# ------------------------------------------------------------------ parser

def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="memloom",
        description="把本机 AI 编程会话存档织成一个可导航的 Obsidian 记忆库。零依赖、不需要大模型。",
    )
    p.add_argument("--version", action="version", version=f"memloom {__version__}")
    sub = p.add_subparsers(dest="cmd")

    b = sub.add_parser("build", help="生成记忆库")
    b.add_argument("--out", "-o", default="vault", help="输出目录（默认 ./vault）")
    b.add_argument("--root", action="append", help="额外的采集路径，可多次；支持 name=PATH")
    b.add_argument("--adapter", default="auto", help="auto | dsh | claude-code | codex | antigravity")
    b.add_argument("--since", type=int, default=None, help="只要最近 N 天有活动的会话")
    b.add_argument("--min-turns", type=int, default=1, help="少于 N 轮的会话不要（默认 1）")
    b.add_argument("--split", type=int, default=12, help="同一工作目录超过 N 个会话才尝试拆子项目（默认 12）")
    b.add_argument("--title", default="记忆库", help="库标题")
    b.add_argument("--source-label", default="memloom", help="页面 front-matter 里的「来源」字段")
    b.add_argument("--tag-prefix", default="memloom", help="Obsidian 标签前缀")
    b.add_argument("--dry-run", action="store_true", help="只统计，不写文件")
    b.add_argument("--full", action="store_true", help="忽略增量缓存，全部重新解析")
    b.add_argument("--json", action="store_true", help="输出机器可读结果")
    b.add_argument("--quiet", "-q", action="store_true", help="一个文件都不打印，只留汇总")
    b.add_argument("--verbose", "-v", action="store_true",
                   help="连命中缓存的文件也打印（默认只打印本次真正解析的）")
    b.set_defaults(func=cmd_build)

    s = sub.add_parser("scan", help="看看会读哪些文件")
    s.add_argument("--root", action="append", help="额外的采集路径，可多次")
    s.add_argument("--adapter", default="auto")
    s.add_argument("--quiet", "-q", action="store_true", help="只打印汇总")
    s.set_defaults(func=cmd_scan)

    d = sub.add_parser("doctor", help="体检：采集路径、压缩后端、Python 版本")
    d.set_defaults(func=cmd_doctor)
    return p


def main(argv: Optional[List[str]] = None) -> int:
    _utf8_stdout()
    parser = build_parser()
    args = parser.parse_args(argv)
    if not getattr(args, "cmd", None):
        parser.print_help()
        return 0
    try:
        return args.func(args)
    except KeyboardInterrupt:
        print("\n中断了。")
        return 130
    except Exception as exc:
        if os.environ.get("MEMLOOM_DEBUG"):
            raise
        print(f"出错了：{type(exc).__name__}: {exc}")
        print("设置 MEMLOOM_DEBUG=1 可看完整调用栈。")
        return 1


if __name__ == "__main__":
    sys.exit(main())
