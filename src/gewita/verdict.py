"""verdict.py — 每条引用的裁决合成。

判定矩阵（诚实边界写死在代码里）::

    ┌────────────┬──────────────────────────────────────────────────────┐
    │ ref_status │ PARSED（条目在表中且解析出标题）                       │
    │            │ NO_REF_LIST（文档没有参考文献表）                      │
    │            │ NOT_IN_LIST（标记编号超出条目范围/无法对应）            │
    ├────────────┼──────────────────────────────────────────────────────┤
    │ existence  │ LOCAL_ONLY  refstore 里有该条目的历史裁决（离线可判）   │
    │            │ EXISTS     在线命中（标题包含度≥0.85 且年份/刊名不冲突）│
    │            │ SUSPECT    命中但年份差>1 或刊名不符（附差异说明）      │
    │            │ NOT_FOUND  在线核验（Crossref+arXiv）均未找到           │
    │            │ UNVERIFIED 未启用在线且无历史——诚实弃权                 │
    ├────────────┼──────────────────────────────────────────────────────┤
    │ alignment  │ VERBATIM / NEAR / PARAPHRASE / NOT_FOUND（句子 vs 来源）│
    └────────────┴──────────────────────────────────────────────────────┘

**离线模式永不输出"造假"结论**：transport=None 且 refstore 无记录时，
existence 只能是 UNVERIFIED——"查不到"与"不存在"是两回事，
只有在线核验（或 refstore 里的历史在线结论）才允许说 NOT_FOUND / SUSPECT。
"""

from __future__ import annotations

from dataclasses import dataclass, field

from . import refs as refs_mod
from .align import LEVEL_RANK, Aligner, Alignment, align_quote
from .existence import (
    LOCAL_ONLY,
    NOT_FOUND,
    SUSPECT,
    UNVERIFIED,
    ExistenceResult,
    QueryBudget,
    Transport,
    structure_notes,
    verify_online,
)
from .extract import Citation, extract_citations
from .refs import Reference, parse_coverage, parse_references

PARSED = "PARSED"
NO_REF_LIST = "NO_REF_LIST"
NOT_IN_LIST = "NOT_IN_LIST"

#: 离线允许的 existence 全集（永不包含 NOT_FOUND/SUSPECT 之外的"造假"级结论）
_OFFLINE_ALLOWED = frozenset({LOCAL_ONLY, UNVERIFIED})


@dataclass
class CitationVerdict:
    """一条 (引用标记 × 指向条目) 的完整裁决。"""

    citation_index: int
    ref_pos: int  # 标记内第几个 ref（[1-3] 展开后各自一条裁决）
    marker: str
    ref_index: int | None
    ref_status: str
    existence: str
    alignment_level: str
    alignment_score: float = 0.0
    evidence: tuple[int, int] | None = None  # 来源内的偏移对
    source_name: str = ""
    message: str = ""
    ref_title: str = ""
    sentence_excerpt: str = ""

    @property
    def suspicious(self) -> bool:
        """是否进入异常清单：证据不足不算可疑，明确冲突才算。"""
        return (
            self.existence in (SUSPECT, NOT_FOUND)
            or self.alignment_level == "NOT_FOUND"
            or self.ref_status in (NO_REF_LIST, NOT_IN_LIST)
        )


@dataclass
class DocReport:
    """一篇文档的完整核验报告数据。"""

    doc_name: str
    refs: list[Reference]
    citations: list[Citation]
    verdicts: list[CitationVerdict]
    ref_list_found: bool
    parse_coverage: float
    online: bool
    sources: dict[str, str] = field(default_factory=dict)


def _best_alignment(quote: str, sources: dict[str, str],
                    aligners: dict[str, Aligner]) -> tuple[Alignment, str]:
    """在全部来源中取最强对齐（等级优先，同级比分数）。"""
    best: tuple[Alignment, str] = (Alignment("NOT_FOUND", 0.0, -1, -1, "none"), "")
    for name, aligner in aligners.items():
        result = aligner.align(quote) if aligner else align_quote(quote, sources[name])
        if (LEVEL_RANK[result.level], result.score) > (LEVEL_RANK[best[0].level], best[0].score):
            best = (result, name)
    return best


def _existence_for(ref: Reference, transport: Transport | None, store, budget) -> ExistenceResult:
    """存在性裁决：refstore 历史 → 在线核验 → 诚实弃权（UNVERIFIED）。"""
    if store is not None:
        hit = store.check(ref)
        if hit is not None:
            detail = f"refstore 历史记录（上次裁决 {hit.verdict}，ts={hit.ts}）"
            return ExistenceResult(LOCAL_ONLY, detail, provider="refstore")
    if transport is not None:
        return verify_online(ref, transport, _budget=budget)
    notes = structure_notes(ref)
    detail = "未启用在线核验且 refstore 无历史记录；离线模式不判存在性"
    if notes:
        detail += "；" + "；".join(notes)
    return ExistenceResult(UNVERIFIED, detail, provider="offline")


def judge_document(
    doc_text: str,
    sources: dict[str, str] | None = None,
    *,
    transport: Transport | None = None,
    store=None,
    doc_name: str = "doc",
    budget: QueryBudget | None = None,
) -> DocReport:
    """对一篇文档做完整引用核验，返回 :class:`DocReport`。

    ``sources``: {来源名: 来源文本}；``transport``: 在线核验 transport（None=离线）；
    ``store``: :class:`gewita.refstore.RefStore`（有历史时给出 LOCAL_ONLY）；
    ``budget``: 文档级共享预算（限速/重试/同指纹缓存）——默认自动创建
    ``min_interval=1.0`` 的礼貌预算；离线评测（mock transport）应自行传入
    ``min_interval=0`` 的预算以免限速空转。
    """
    sources = sources or {}
    entries = parse_references(doc_text)
    citations = extract_citations(doc_text, entries)
    aligners = {name: Aligner(text) for name, text in sources.items()}
    # 文档级共享预算：限速/重试/同指纹缓存跨条目复用（ROADMAP iter2）
    if budget is None and transport is not None:
        budget = QueryBudget(min_interval=1.0, max_queries=max(8, len(entries) * 2))
    verdicts: list[CitationVerdict] = []
    existence_cache: dict[int, ExistenceResult] = {}
    aligned: list[tuple[Citation, Alignment, str]] = []
    for ci, citation in enumerate(citations):
        alignment, src_name = _best_alignment(citation.sentence_text, sources, aligners)
        aligned.append((citation, alignment, src_name))
        if not citation.ref_indices:
            verdicts.append(
                CitationVerdict(
                    citation_index=ci, ref_pos=0, marker=citation.raw, ref_index=None,
                    ref_status=NO_REF_LIST if not entries else NOT_IN_LIST,
                    existence=UNVERIFIED, alignment_level=alignment.level,
                    alignment_score=alignment.score,
                    evidence=(alignment.start, alignment.end) if alignment.start >= 0 else None,
                    source_name=src_name,
                    message=citation.note or "标记无法对应到参考文献表条目",
                    sentence_excerpt=citation.sentence_text[:30],
                )
            )
            continue
        for pos, ref_index in enumerate(citation.ref_indices):
            ref = _ref_by_index(entries, ref_index)
            if ref is None:
                verdicts.append(
                    CitationVerdict(
                        citation_index=ci, ref_pos=pos, marker=citation.raw, ref_index=ref_index,
                        ref_status=NO_REF_LIST if not entries else NOT_IN_LIST,
                        existence=UNVERIFIED,
                        alignment_level=alignment.level, alignment_score=alignment.score,
                        evidence=(alignment.start, alignment.end) if alignment.start >= 0 else None,
                        source_name=src_name,
                        message=("文档没有参考文献表" if not entries
                                 else f"编号 [{ref_index}] 不在参考文献表中（表内共 {len(entries)} 条）"),
                        sentence_excerpt=citation.sentence_text[:30],
                    )
                )
                continue
            if ref_index not in existence_cache:
                existence_cache[ref_index] = _existence_for(ref, transport, store, budget)
            ex = existence_cache[ref_index]
            verdicts.append(_assemble(ci, pos, citation, ref, ex, alignment, src_name, bool(entries)))
    return DocReport(
        doc_name=doc_name,
        refs=entries,
        citations=citations,
        verdicts=verdicts,
        ref_list_found=bool(entries) or _has_ref_section(doc_text),
        parse_coverage=parse_coverage(entries),
        online=transport is not None,
        sources=dict(sources),
    )


def _ref_by_index(entries: list[Reference], index: int) -> Reference | None:
    for ref in entries:
        if ref.index == index:
            return ref
    return None


def _has_ref_section(doc_text: str) -> bool:
    return refs_mod.find_section(doc_text).found


def _assemble(ci: int, pos: int, citation: Citation, ref: Reference, ex: ExistenceResult,
              alignment: Alignment, src_name: str, has_entries: bool) -> CitationVerdict:
    """ref_status：条目在表中=PARSED（未解析出标题用 message 如实注明）。"""
    ref_status = PARSED if has_entries else NO_REF_LIST
    messages: list[str] = []
    if ex.status == UNVERIFIED:
        messages.append(ex.detail)
    if ex.status == LOCAL_ONLY:
        messages.append(ex.detail)
    if ex.status == NOT_FOUND:
        messages.append("在线核验未找到该文献")
    if ex.status == SUSPECT:
        messages.append(ex.detail)
    if alignment.level == "NOT_FOUND":
        messages.append("引文主张未在任何给定来源中找到（证据不足，不等于内容有误）")
    elif alignment.start >= 0:
        messages.append(f"证据见来源「{src_name}」偏移 {alignment.start}:{alignment.end}")
    if not ref.parsed and has_entries:
        messages.append("条目未解析出标题，存在性核验受限（解析覆盖率口径内）")
    return CitationVerdict(
        citation_index=ci,
        ref_pos=pos,
        marker=citation.raw,
        ref_index=ref.index,
        ref_status=ref_status,
        existence=ex.status,
        alignment_level=alignment.level,
        alignment_score=alignment.score,
        evidence=(alignment.start, alignment.end) if alignment.start >= 0 else None,
        source_name=src_name,
        message="；".join(messages) or "无异常",
        ref_title=ref.title,
        sentence_excerpt=citation.sentence_text[:30],
    )
