"""cli.py — 命令行入口。

::

    gewita check DOC --sources DIR [--online] [--json] [--refstore PATH]
    gewita refs REFS_FILE [--verify] [--json]
    gewita bench
    gewita refstore stats PATH

退出码：0 干净 / 1 有可疑引用 / 2 输入错误。
``--online`` / ``--verify`` 才会真联网（Crossref/arXiv，内置限速）；
默认离线，且离线永不输出"造假"结论。测试绝不使用真实网络。
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from . import __version__
from .bench import format_bench_markdown, run_bench
from .existence import QueryBudget, http_transport
from .refs import parse_coverage, parse_references
from .refstore import RefStore
from .report import render_json, render_markdown
from .verdict import judge_document

SUSPICIOUS_EXIT = 1
INPUT_ERROR_EXIT = 2


def _load_sources(path: Path) -> dict[str, str]:
    sources: dict[str, str] = {}
    for pattern in ("*.txt", "*.md"):
        for p in sorted(path.glob(pattern)):
            sources[p.stem] = p.read_text(encoding="utf-8")
    return sources


def _read_doc(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def cmd_check(args: argparse.Namespace) -> int:
    doc_path = Path(args.doc)
    sources_path = Path(args.sources)
    if not doc_path.is_file():
        print(f"错误：文档不存在：{doc_path}", file=sys.stderr)
        return INPUT_ERROR_EXIT
    if not sources_path.is_dir():
        print(f"错误：来源目录不存在：{sources_path}", file=sys.stderr)
        return INPUT_ERROR_EXIT
    sources = _load_sources(sources_path)
    if not sources:
        print(f"错误：来源目录中没有 *.txt/*.md 文件：{sources_path}", file=sys.stderr)
        return INPUT_ERROR_EXIT
    transport = http_transport if args.online else None
    store = RefStore(args.refstore) if args.refstore else None
    doc_text = _read_doc(doc_path)
    report = judge_document(doc_text, sources, transport=transport, store=store,
                            doc_name=doc_path.stem)
    if store is not None:
        _save_verdicts(report, store)
    out = render_json(report) if args.json else render_markdown(report)
    print(out)
    return SUSPICIOUS_EXIT if any(v.suspicious for v in report.verdicts) else 0


def _save_verdicts(report, store: RefStore) -> None:
    """把本次在线/离线结论落库（同一指纹不重复）。"""
    for v in report.verdicts:
        ref = next((r for r in report.refs if r.index == v.ref_index), None)
        if ref is not None:
            store.append(ref, v.existence)


def cmd_refs(args: argparse.Namespace) -> int:
    path = Path(args.refs_file)
    if not path.is_file():
        print(f"错误：文件不存在：{path}", file=sys.stderr)
        return INPUT_ERROR_EXIT
    text = _read_doc(path)
    refs = parse_references(text, assume_section=True)
    if not refs:
        print("未解析出任何参考文献条目（文件为空或格式完全无法识别）", file=sys.stderr)
        return INPUT_ERROR_EXIT
    transport = http_transport if args.verify else None
    budget = (
        QueryBudget(min_interval=1.0, max_queries=max(8, len(refs) * 2))
        if transport is not None
        else None
    )
    if args.json:
        import json as _json

        from .existence import verify_online

        payload = []
        for ref in refs:
            ex = verify_online(ref, transport, _budget=budget) if transport else None
            payload.append({
                "index": ref.index, "title": ref.title, "parsed": ref.parsed,
                "year": ref.year, "doi": ref.doi, "arxiv_id": ref.arxiv_id,
                "url": ref.url, "entry_type": ref.entry_type,
                "existence": ex.status if ex else "UNVERIFIED",
                "existence_detail": ex.detail if ex else "未启用 --verify",
            })
        print(_json.dumps({"refs": payload, "parse_coverage": parse_coverage(refs)},
                          ensure_ascii=False, indent=2))
    else:
        print(f"共 {len(refs)} 条，解析覆盖率 {parse_coverage(refs):.0%}")
        for ref in refs:
            mark = "✓" if ref.parsed else "✗"
            extra = " ".join(filter(None, [
                f"year={ref.year}" if ref.year else "",
                ref.doi, f"arXiv:{ref.arxiv_id}" if ref.arxiv_id else "", ref.url,
            ]))
            print(f"  [{ref.index:>2}] {mark} {ref.entry_type:<8} "
                  f"{ref.title or '<未解析出标题>'}  {extra}")
    return 0


def cmd_bench(args: argparse.Namespace) -> int:
    metrics = run_bench()
    print(format_bench_markdown(metrics))
    return 0


def cmd_refstore(args: argparse.Namespace) -> int:
    path = Path(args.path)
    if not path.exists():
        print(f"错误：refstore 文件不存在：{path}", file=sys.stderr)
        return INPUT_ERROR_EXIT
    store = RefStore(path)
    stats = store.stats()
    print(f"refstore：{stats['path']}")
    print(f"  指纹总数：{stats['total']}")
    for verdict, count in sorted(stats["by_verdict"].items()):
        print(f"  {verdict}: {count}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="gewita",
        description="Gewita — 中文优先的引用验证标准件（离线模式永不输出造假结论）",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    sub = parser.add_subparsers(dest="command", required=True)

    p_check = sub.add_parser("check", help="核验文档引用（对照来源目录）")
    p_check.add_argument("doc", help="待核验文档路径")
    p_check.add_argument("--sources", required=True, help="来源目录（*.txt/*.md）")
    p_check.add_argument("--online", action="store_true",
                         help="启用在线核验（Crossref/arXiv，真实联网）")
    p_check.add_argument("--json", action="store_true", help="输出 JSON 报告")
    p_check.add_argument("--refstore", default=None, help="refstore JSONL 路径（历史裁决复用）")
    p_check.set_defaults(func=cmd_check)

    p_refs = sub.add_parser("refs", help="解析参考文献文件（条目列表或整篇文档）")
    p_refs.add_argument("refs_file", help="参考文献文件路径")
    p_refs.add_argument("--verify", action="store_true",
                        help="在线核验每条文献（真实联网，内置限速）")
    p_refs.add_argument("--json", action="store_true", help="输出 JSON")
    p_refs.set_defaults(func=cmd_refs)

    p_bench = sub.add_parser("bench", help="运行内置评测（离线，mock transport）")
    p_bench.set_defaults(func=cmd_bench)

    p_store = sub.add_parser("refstore", help="引用透明库")
    p_sub = p_store.add_subparsers(dest="refstore_command", required=True)
    p_stats = p_sub.add_parser("stats", help="库内统计")
    p_stats.add_argument("path", help="refstore JSONL 路径")
    p_stats.set_defaults(func=cmd_refstore)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
