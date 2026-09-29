"""extract.py — 正文引用标记抽取。

支持形态：

- 数字编号：``[1]``、``[1,2]``、``[1-3]``（区间展开为 ``[1,2,3]``）、``[1][2]`` 连续
- 作者-年份式（可选）：``(Smith, 2020)``——尽力对应到参考文献表条目；
  对应不上时保留标记并如实标注（``ref_indices`` 为空）

每个标记挂到其所在句子（句 span 为原文精确偏移）。参考文献表区域内的
标记不算正文引用，自动排除。
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from . import refs as refs_mod
from .text import Sentence, split_sentences

NUM_MARKER_RE = re.compile(r"\[(\d+(?:\s*[,，\-–]\s*\d+)*)\]")
AUTHOR_YEAR_RE = re.compile(r"\(([A-Z][A-Za-z'’\-]+(?:\s+et al\.?)?),\s*((?:19|20)\d{2})\)")

MAX_RANGE_EXPAND = 50  # [1-10000] 这类异常区间不展开，防止误匹配爆炸


@dataclass
class Citation:
    """一条正文引用标记及其所在句。"""

    ref_indices: list[int]
    raw: str
    style: str  # "numeric" | "author_year"
    sentence_span: tuple[int, int]
    marker_span: tuple[int, int]
    sentence_text: str
    note: str = ""  # 作者-年份无法对应等情形的诚实备注
    authors: list[str] = field(default_factory=list)
    year: int | None = None


def expand_marker(inner: str) -> list[int]:
    """展开标记内层文本：``1`` → [1]，``1,2`` → [1,2]，``1-3`` → [1,2,3]。"""
    out: list[int] = []
    for token in re.split(r"[,，]", inner):
        token = token.strip()
        if m := re.fullmatch(r"(\d+)\s*[-–]\s*(\d+)", token):
            a, b = int(m.group(1)), int(m.group(2))
            if a <= b and b - a + 1 <= MAX_RANGE_EXPAND:
                out.extend(range(a, b + 1))
            continue
        if token.isdigit():
            out.append(int(token))
    return out


def strip_markers(text: str) -> str:
    """去掉数字编号标记（作者-年份标记不动，由调用方按偏移切除）。"""
    return NUM_MARKER_RE.sub("", text)


def resolve_author_year(authors: list[str], year: int | None,
                        entries: list[refs_mod.Reference]) -> list[int]:
    """把 (作者, 年份) 对应到参考文献表：首作者姓氏出现 + 年份一致。"""
    out: list[int] = []
    for ref in entries:
        if ref.year != year:
            continue
        for author in authors:
            surname = author.split()[0].rstrip(",") if author.split() else ""
            if surname and surname.lower() in " ".join(ref.authors).lower():
                out.append(ref.index)
                break
    return out


def _cut_marker(sentence: Sentence, marker_span: tuple[int, int]) -> str:
    """把标记区间从句文本中切除，得到用于对齐的“引文主张”。"""
    rel_s = max(0, marker_span[0] - sentence.start)
    rel_e = min(len(sentence.text), marker_span[1] - sentence.start)
    if rel_e <= rel_s:
        return sentence.text
    return sentence.text[:rel_s] + sentence.text[rel_e:]


def extract_citations(doc: str, entries: list[refs_mod.Reference] | None = None) -> list[Citation]:
    """抽取正文引用标记（自动跳过参考文献表区域）。

    ``entries`` 传入参考文献表时，作者-年份标记会尽力对应到条目编号。
    """
    probe = refs_mod.find_section(doc)
    body_end = probe.offset if probe.found else len(doc)
    citations: list[Citation] = []
    for sent in split_sentences(doc):
        if sent.start >= body_end:
            continue
        for m in NUM_MARKER_RE.finditer(sent.text):
            indices = expand_marker(m.group(1))
            citations.append(
                Citation(
                    ref_indices=indices,
                    raw=m.group(0),
                    style="numeric",
                    sentence_span=(sent.start, sent.end),
                    marker_span=(sent.start + m.start(), sent.start + m.end()),
                    sentence_text=_cut_marker(sent, (sent.start + m.start(), sent.start + m.end())),
                )
            )
        for m in AUTHOR_YEAR_RE.finditer(sent.text):
            authors = [m.group(1)]
            year = int(m.group(2))
            resolved = resolve_author_year(authors, year, entries) if entries else []
            note = ""
            if entries and not resolved:
                note = "作者-年份标记无法对应到参考文献表条目"
            citations.append(
                Citation(
                    ref_indices=resolved,
                    raw=m.group(0),
                    style="author_year",
                    sentence_span=(sent.start, sent.end),
                    marker_span=(sent.start + m.start(), sent.start + m.end()),
                    sentence_text=_cut_marker(sent, (sent.start + m.start(), sent.start + m.end())),
                    note=note,
                    authors=authors,
                    year=year,
                )
            )
    return citations
