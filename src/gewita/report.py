"""report.py — Markdown 与 JSON 报告渲染 + integrity score。

integrity score 加权公式（写明，不做黑箱）::

    credit_align = {VERBATIM: 1.0, NEAR: 0.8, PARAPHRASE: 0.5, NOT_FOUND: 0.0}
    credit_exist = {EXISTS: 1.0, LOCAL_ONLY: 1.0, UNVERIFIED: 0.9,
                    SUSPECT: 0.5, NOT_FOUND: 0.0}
    每条裁决 w = credit_align × credit_exist
    score = mean(w)   # 无引用时 1.0（"没有可核验的引用"不是扣分项）

语气诚实：报告明确区分"证据不足"（UNVERIFIED / NOT_FOUND 对齐——只是没找到，
不代表内容有误）与"发现问题"（SUSPECT / NOT_FOUND 存在性——在线核验后的
负面结论）。离线报告不含任何"造假"字样。
"""

from __future__ import annotations

import json
from dataclasses import asdict

from .verdict import DocReport

CREDIT_ALIGN = {"VERBATIM": 1.0, "NEAR": 0.8, "PARAPHRASE": 0.5, "NOT_FOUND": 0.0}
CREDIT_EXIST = {"EXISTS": 1.0, "LOCAL_ONLY": 1.0, "UNVERIFIED": 0.9, "SUSPECT": 0.5,
                "NOT_FOUND": 0.0}

_CONFIDENCE_HIGH = 0.8
_CONFIDENCE_MEDIUM = 0.5


def verdict_weight(alignment_level: str, existence: str) -> float:
    return CREDIT_ALIGN.get(alignment_level, 0.0) * CREDIT_EXIST.get(existence, 0.0)


def integrity_score(verdicts) -> float:
    """加权完整性得分 ∈ [0,1]。公式见模块 docstring。"""
    if not verdicts:
        return 1.0
    return sum(verdict_weight(v.alignment_level, v.existence) for v in verdicts) / len(verdicts)


def confidence(weight: float) -> str:
    if weight >= _CONFIDENCE_HIGH:
        return "高"
    if weight >= _CONFIDENCE_MEDIUM:
        return "中"
    return "低"


def _excerpt(text: str, limit: int = 30) -> str:
    text = text.replace("\n", " ")
    return text if len(text) <= limit else text[:limit] + "…"


def render_markdown(report: DocReport) -> str:
    """渲染人类可读的 Markdown 报告。"""
    lines: list[str] = []
    lines.append(f"# gewita 引用核验报告 — {report.doc_name}")
    lines.append("")
    mode = "在线核验" if report.online else "离线模式（未启用在线核验，永不输出造假结论）"
    lines.append(f"- 模式：{mode}")
    lines.append(f"- 参考文献表：{'已定位' if report.ref_list_found else '未找到'}，"
                 f"共 {len(report.refs)} 条，解析覆盖率 {report.parse_coverage:.0%}")
    lines.append(f"- 正文引用标记：{len(report.citations)} 个，逐条裁决 {len(report.verdicts)} 条")
    lines.append(f"- **integrity score：{integrity_score(report.verdicts):.3f}**"
                 f"（credit_align × credit_exist 的均值，权重表见文档）")
    lines.append("")
    lines.append("## 逐条裁决")
    lines.append("")
    lines.append("| # | 句子摘录 | 指向 | ref_status | existence | alignment | 证据(来源:偏移) "
                 "| 置信 | 说明 |")
    lines.append("|---|---|---|---|---|---|---|---|---|")
    for i, v in enumerate(report.verdicts, 1):
        weight = verdict_weight(v.alignment_level, v.existence)
        evidence = f"{v.source_name}:{v.evidence[0]}:{v.evidence[1]}" if v.evidence else "—"
        target = f"[{v.ref_index}]" if v.ref_index is not None else v.marker
        lines.append(
            f"| {i} | {_excerpt(v.sentence_excerpt)} | {target} | {v.ref_status} "
            f"| {v.existence} | {v.alignment_level} | {evidence} | {confidence(weight)} "
            f"| {_excerpt(v.message, 60)} |"
        )
    lines.append("")
    lines.append("## 异常清单（需要人工复核）")
    anomalies = [v for v in report.verdicts if v.suspicious]
    if not anomalies:
        lines.append("无。")
    else:
        for i, v in enumerate(anomalies, 1):
            target = f"[{v.ref_index}]" if v.ref_index is not None else v.marker
            lines.append(f"{i}. 标记 `{v.marker}`（→ {target}）：{v.message}")
    lines.append("")
    lines.append("## 诚实声明")
    lines.append("")
    if report.online:
        lines.append("- 本报告含在线核验结论（Crossref/arXiv）；NOT_FOUND 表示两边都没查到，"
                     "仍建议人工复核后再下结论。")
    else:
        lines.append("- 本报告为离线生成：existence 全部为 UNVERIFIED/LOCAL_ONLY，"
                     "**不含任何\"造假\"结论**；对齐 NOT_FOUND 只表示\"未在给定来源中找到\"。")
    lines.append("- PARAPHRASE 表示词面 bigram 重叠，不等于语义等价。")
    lines.append("- GB/T 7714 解析为启发式，覆盖率如上；未解析条目已如实标注。")
    return "\n".join(lines) + "\n"


def render_json(report: DocReport) -> str:
    """渲染 JSON 报告（ensure_ascii=False，供下游程序消费）。"""
    payload = {
        "tool": "gewita",
        "doc_name": report.doc_name,
        "online": report.online,
        "ref_list_found": report.ref_list_found,
        "parse_coverage": report.parse_coverage,
        "integrity_score": integrity_score(report.verdicts),
        "refs": [
            {
                "index": r.index,
                "title": r.title,
                "parsed": r.parsed,
                "year": r.year,
                "doi": r.doi,
                "arxiv_id": r.arxiv_id,
                "entry_type": r.entry_type,
            }
            for r in report.refs
        ],
        "verdicts": [{**asdict(v), "evidence": list(v.evidence) if v.evidence else None}
                     for v in report.verdicts],
    }
    return json.dumps(payload, ensure_ascii=False, indent=2) + "\n"
