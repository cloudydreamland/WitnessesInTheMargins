"""Gewita — 中文优先的引用验证标准件。

四件事：① GB/T 7714/APA-lite 参考文献解析 ② 正文引用标记抽取
③ 引文↔来源三级对齐裁决（VERBATIM/NEAR/PARAPHRASE/NOT_FOUND，带精确偏移）
④ 参考文献存在性核验（DOI/arXiv 结构校验 + 可选在线核验）。

诚实原则：离线模式**永不输出"造假"结论**，最多说"未在给定来源中找到"。

快速上手::

    from gewita import judge_document, align_quote, parse_references

    report = judge_document(doc_text, {"source1": text})   # 离线核验
    a = align_quote("自注意力机制", text)                    # a.start/a.end 指向原文
"""

from .align import LEVELS, Aligner, Alignment, align_quote
from .existence import (
    EXISTS,
    LOCAL_ONLY,
    NOT_FOUND,
    SUSPECT,
    UNVERIFIED,
    arxiv_valid,
    doi_valid,
    title_containment,
    title_fingerprint,
    verify_online,
)
from .extract import Citation, extract_citations
from .refs import Reference, parse_coverage, parse_references
from .refstore import RefStore
from .report import integrity_score, render_json, render_markdown
from .text import Sentence, normalize, split_sentences
from .verdict import CitationVerdict, DocReport, judge_document

__version__ = "0.1.0"

__all__ = [
    "EXISTS",
    "LEVELS",
    "LOCAL_ONLY",
    "NOT_FOUND",
    "SUSPECT",
    "UNVERIFIED",
    "Aligner",
    "Alignment",
    "Citation",
    "CitationVerdict",
    "DocReport",
    "RefStore",
    "Reference",
    "Sentence",
    "align_quote",
    "arxiv_valid",
    "doi_valid",
    "extract_citations",
    "integrity_score",
    "judge_document",
    "normalize",
    "parse_coverage",
    "parse_references",
    "render_json",
    "render_markdown",
    "split_sentences",
    "title_containment",
    "title_fingerprint",
    "verify_online",
]
