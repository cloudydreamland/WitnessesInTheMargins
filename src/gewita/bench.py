"""bench.py — 内置评测：8 篇微文档 + 迷你来源集 + 35 条金标。

- **离线可复现**：fabricated 检测用注入的 mock transport（模拟 Crossref/arXiv
  注册库），测试与评测**绝不真联网**。
- 指标：对齐四级 P/R/F1（含 micro）、fabricated 检测 P/R/F1、解析覆盖率。
- 结果真实跑出，写入 benchmarks/results.md（禁止编造数字）。

语料位置：仓库根 benchmarks/corpus/（可用环境变量 YINZHENG_CORPUS 覆盖）。
以 wheel 安装后语料不随包分发——跑 ``gewita bench`` 请用仓库检出。
"""

from __future__ import annotations

import json
import os
import urllib.parse
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

from .existence import NOT_FOUND, SUSPECT, QueryBudget, Transport, TransportResponse
from .text import normalize
from .verdict import judge_document

LEVEL_MAP = {"verbatim": "VERBATIM", "near": "NEAR", "paraphrase": "PARAPHRASE",
             "not_in_source": "NOT_FOUND"}


@dataclass(frozen=True)
class GoldEntry:
    doc: str
    cite: int
    ref_pos: int
    level: str  # verbatim/near/paraphrase/not_in_source
    fabricated: bool
    unparsable: bool


def default_corpus_dir() -> Path:
    env = os.environ.get("YINZHENG_CORPUS")
    if env:
        return Path(env)
    return Path(__file__).resolve().parents[2] / "benchmarks" / "corpus"


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def load_corpus(corpus_dir: Path | None = None) -> tuple[dict[str, str], dict[str, str],
                                                          list[GoldEntry]]:
    """返回 (docs, sources, gold)。文档与来源均以去扩展名为键。"""
    base = Path(corpus_dir) if corpus_dir else default_corpus_dir()
    docs_dir, sources_dir = base / "docs", base / "sources"
    if not docs_dir.is_dir():
        raise FileNotFoundError(
            f"未找到内置语料目录 {docs_dir}；wheel 安装不含语料，请在仓库检出内运行，"
            "或设置 YINZHENG_CORPUS 指向语料目录"
        )
    docs = {p.stem: _read(p) for p in sorted(docs_dir.glob("*.txt"))}
    sources = {p.stem: _read(p) for p in sorted(sources_dir.glob("*.txt"))}
    gold_raw = json.loads(_read(base / "gold.json"))["gold"]
    gold = [GoldEntry(doc=g["doc"], cite=g["cite"], ref_pos=g.get("ref_pos", 0),
                      level=g["level"], fabricated=g["fabricated"],
                      unparsable=g["unparsable"]) for g in gold_raw]
    return docs, sources, gold


# ---------- mock transport（离线可复现的"注册库"） ----------

#: 语料内"真实存在"的文献注册库：归一化标题 → (year, venue)
REGISTRY: dict[str, tuple[int, str]] = {
    normalize("预训练语言模型研究综述"): (2021, "中文信息学报"),
    normalize("混合检索技术及其应用"): (2022, "计算机学报"),
    normalize("Cross-encoder reranking for open-domain QA"): (2023, "Proceedings of ACL"),
    normalize("向量检索系统实践"): (2023, "电子工业出版社"),
    normalize("知识蒸馏理论与实践"): (2022, "清华大学出版社"),
    normalize("中国居民膳食指南（2022）"): (2022, "人民卫生出版社"),
    normalize("睡眠与健康研究进展"): (2021, "中华健康管理学杂志"),
    normalize("身体活动指南"): (2020, "世界卫生组织"),
    normalize("有氧运动与心血管健康"): (2020, "中国体育科学"),
    normalize("中文分词四十年"): (2019, "中文信息学报"),
    normalize("Retrieval-augmented generation survey"): (2024, "ACM Computing Surveys"),
    normalize("中华人民共和国个人信息保护法"): (2021, "全国人民代表大会常务委员会公报"),
    normalize("中华人民共和国数据安全法"): (2021, "全国人民代表大会常务委员会公报"),
    normalize("互联网信息服务算法推荐管理规定"): (2022, "国家互联网信息办公室"),
    normalize("促进和规范数据跨境流动规定"): (2024, "国务院办公厅"),
    normalize("向量数据库索引技术"): (2023, "计算机工程"),
    normalize("中文文本切块策略研究"): (2022, "中文信息学报"),
    normalize("Product documentation: citations"): (2024, "OpenAI"),
    normalize("Emergent abilities of large language models"): (2022, "Transactions on Machine Learning Research, 2022"),
    normalize("Retrieval-augmented generation for knowledge-intensive NLP tasks"): (2020, "NeurIPS"),
    normalize("Self-consistency improves chain of thought reasoning in language models"): (2023, "ICLR"),
    normalize("Climate change 2023: synthesis report"): (2023, "Cambridge University Press"),
    normalize("Sea ice index, version 4"): (2025, "NSIDC"),
    normalize("State and trends of carbon pricing"): (2025, "World Bank"),
    normalize("Expectations, outcomes, and challenges of modern code review"): (2013, "ICSE"),
}
# 编造文献（标题故意不在注册库）：中文分词与机器翻译质量关联研究 / RLHF completely
# solves alignment / Surface warming projections / Technical debt myths debunked /
# Contrastive learning history, 1988-2023


def _arxiv_atom(title: str, year: int) -> str:
    return (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<feed xmlns="http://www.w3.org/2005/Atom"><title>ArXiv Query</title>'
        f"<entry><title>{title}</title><published>{year}-01-01T00:00:00Z</published></entry>"
        "</feed>"
    )


def make_mock_transport() -> Transport:
    """构造离线可复现的 mock transport：Crossref JSON + arXiv Atom，全 200。"""

    def transport(url: str) -> TransportResponse:
        parsed = urllib.parse.urlparse(url)
        qs = urllib.parse.parse_qs(parsed.query)
        if "api.crossref.org" in parsed.netloc:
            title = qs.get("query.bibliographic", [""])[0]
            hit = REGISTRY.get(normalize(title))
            if hit is None:
                return TransportResponse(200, '{"message":{"items":[]}}')
            year, venue = hit
            payload = {"message": {"items": [{
                "title": [title],
                "issued": {"date-parts": [[year]]},
                "container-title": [venue],
                "DOI": "10.1000/mock.registration",
            }]}}
            return TransportResponse(200, json.dumps(payload, ensure_ascii=False))
        if "export.arxiv.org" in parsed.netloc:
            raw = qs.get("search_query", [""])[0]
            title = urllib.parse.unquote(raw.removeprefix('ti:"').removesuffix('"'))
            hit = REGISTRY.get(normalize(title))
            if hit is None:
                return TransportResponse(
                    200, '<?xml version="1.0"?><feed xmlns="http://www.w3.org/2005/Atom"></feed>'
                )
            return TransportResponse(200, _arxiv_atom(title, hit[0]))
        return TransportResponse(404, "unknown host in mock transport")

    return transport


# ---------- 评测 ----------


def _prf(tp: int, fp: int, fn: int) -> tuple[float, float, float]:
    p = tp / (tp + fp) if tp + fp else 0.0
    r = tp / (tp + fn) if tp + fn else 0.0
    f = 2 * p * r / (p + r) if p + r else 0.0
    return p, r, f


def run_bench(corpus_dir: Path | None = None, verbose: bool = False) -> dict:
    """跑完整评测，返回指标 dict。fabricated 检测使用 mock transport（离线可复现）。"""
    docs, sources, gold = load_corpus(corpus_dir)
    transport = make_mock_transport()
    budget = QueryBudget(min_interval=0, max_queries=10**9)  # mock 不需要限速
    per_doc: dict[str, dict] = {}
    verdict_index: dict[tuple[str, int, int], object] = {}
    refs_index: dict[tuple[str, int], object] = {}
    total_refs = parsed_refs = 0
    for name, text in docs.items():
        report = judge_document(text, sources, transport=transport, doc_name=name,
                                budget=budget)
        total_refs += len(report.refs)
        parsed_refs += sum(1 for r in report.refs if r.parsed)
        per_doc[name] = {
            "refs": len(report.refs),
            "parsed": sum(1 for r in report.refs if r.parsed),
            "citations": len(report.citations),
            "coverage": report.parse_coverage,
        }
        for ref in report.refs:
            refs_index[(name, ref.index)] = ref
        for v in report.verdicts:
            verdict_index[(name, v.citation_index, v.ref_pos)] = v
        if verbose:
            for v in report.verdicts:
                print(f"  {name} cite{v.citation_index}.{v.ref_pos} [{v.ref_index}] "
                      f"{v.alignment_level}/{v.existence} :: {v.message[:60]}")
    # 对齐四级 + fabricated + unparsable
    level_tp: Counter = Counter()
    level_pred: Counter = Counter()
    level_gold: Counter = Counter()
    micro_tp = micro_all = 0
    fab_tp = fab_fp = fab_fn = 0
    unp_tp = unp_fn = 0
    mismatches: list[str] = []
    for g in gold:
        v = verdict_index.get((g.doc, g.cite, g.ref_pos))
        if v is None:
            mismatches.append(f"{g.doc}#{g.cite}.{g.ref_pos}: 无对应裁决（抽取序号与 gold 不符）")
            continue
        gold_level = LEVEL_MAP[g.level]
        micro_all += 1
        level_gold[gold_level] += 1
        level_pred[v.alignment_level] += 1
        if v.alignment_level == gold_level:
            micro_tp += 1
            level_tp[gold_level] += 1
        else:
            mismatches.append(
                f"{g.doc}#{g.cite}.{g.ref_pos}: gold={gold_level} pred={v.alignment_level} "
                f"({v.message[:50]})")
        flagged = v.existence in (NOT_FOUND, SUSPECT)
        if g.fabricated and flagged:
            fab_tp += 1
        elif g.fabricated:
            fab_fn += 1
        elif flagged:
            fab_fp += 1
        pointed = refs_index.get((g.doc, v.ref_index))
        if g.unparsable:
            if pointed is not None and not pointed.parsed:
                unp_tp += 1
            else:
                unp_fn += 1
    metrics = {
        "n_docs": len(docs),
        "n_sources": len(sources),
        "n_gold": micro_all,
        "n_refs": total_refs,
        "parse_coverage": parsed_refs / total_refs if total_refs else 0.0,
        "alignment_micro": {
            "accuracy": micro_tp / micro_all if micro_all else 0.0,
            **{lvl: {"precision": _prf(level_tp[lvl],
                                       level_pred[lvl] - level_tp[lvl],
                                       level_gold[lvl] - level_tp[lvl])[0],
                     "recall": _prf(level_tp[lvl], level_pred[lvl] - level_tp[lvl],
                                    level_gold[lvl] - level_tp[lvl])[1],
                     "f1": _prf(level_tp[lvl], level_pred[lvl] - level_tp[lvl],
                                level_gold[lvl] - level_tp[lvl])[2]}
               for lvl in ("VERBATIM", "NEAR", "PARAPHRASE", "NOT_FOUND")},
        },
        "fabricated": dict(zip(("precision", "recall", "f1"), _prf(fab_tp, fab_fp, fab_fn))),
        "unparsable_detected": unp_tp,
        "unparsable_missed": unp_fn,
        "per_doc": per_doc,
        "mismatches": mismatches,
    }
    return metrics


def format_bench_markdown(metrics: dict) -> str:
    """把 run_bench 的指标渲染成 Markdown 表格。"""
    lines = ["# gewita 内置评测结果", ""]
    lines.append(f"- 文档 {metrics['n_docs']} 篇 / 来源 {metrics['n_sources']} 篇 / "
                 f"金标 {metrics['n_gold']} 条 / 参考文献条目 {metrics['n_refs']} 条")
    lines.append(f"- 解析覆盖率：**{metrics['parse_coverage']:.1%}**（启发式解析器，如实统计）")
    micro = metrics["alignment_micro"]
    lines.append(f"- 对齐四级 micro 准确率：**{micro['accuracy']:.1%}**")
    lines.append("")
    lines.append("| 对齐级别 | P | R | F1 |")
    lines.append("|---|---|---|---|")
    for lvl in ("VERBATIM", "NEAR", "PARAPHRASE", "NOT_FOUND"):
        m = micro[lvl]
        lines.append(f"| {lvl} | {m['precision']:.3f} | {m['recall']:.3f} | {m['f1']:.3f} |")
    lines.append("")
    fab = metrics["fabricated"]
    lines.append(f"- fabricated 检测（mock transport，离线可复现）："
                 f"P {fab['precision']:.3f} / R {fab['recall']:.3f} / F1 {fab['f1']:.3f}")
    lines.append(f"- unparsable 条目检出 {metrics['unparsable_detected']} / "
                 f"漏检 {metrics['unparsable_missed']}")
    lines.append("")
    lines.append("| 文档 | 条目 | 解析出 | 引用标记 | 覆盖率 |")
    lines.append("|---|---|---|---|---|")
    for name, d in metrics["per_doc"].items():
        lines.append(f"| {name} | {d['refs']} | {d['parsed']} | {d['citations']} "
                     f"| {d['coverage']:.0%} |")
    if metrics["mismatches"]:
        lines.append("")
        lines.append("## gold 与预测不一致项")
        lines.extend(f"- {m}" for m in metrics["mismatches"])
    return "\n".join(lines) + "\n"
