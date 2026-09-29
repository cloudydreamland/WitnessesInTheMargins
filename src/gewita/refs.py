"""refs.py — 参考文献表解析（GB/T 7714 中文国标 + 无类型码编号体 + APA-lite）。

解析器是**启发式**的：能解析多少就报告多少（:func:`parse_coverage`），
解析不出的条目保留原文并如实标注 ``parsed=False``，绝不编造字段。

支持的形态（按优先级）：

1. GB/T 7714 编号体，靠类型标识定位标题边界::

       [1] 张三，李四. 深度学习综述[J]. 中文信息学报, 2020, 15(3): 12-18.
       [2] 王五. 某本专著[M]. 北京: 某出版社, 2021.
       [3] 某机构. 网页标题[EB/OL]. (2020-01-01)[2026-01-01]. https://example.com.

2. 无类型码的编号体：``[1] 作者. 标题. 刊名, 2020.``（按 ". " 分段猜字段）
3. APA-lite：``Smith, J. (2020). Title of the paper. Venue Name.``

DOI/arXiv/URL 的抽取独立于条目形态，三种形态通用。
所有 span 均为文档内的绝对偏移。
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from .text import normalize

#: 参考文献表标题行（行首匹配）
SECTION_HEADING_RE = re.compile(
    r"^[ \t]*(参考文献|参\s*考\s*文\s*献|引用文献|"
    r"References|REFERENCES|Reference|Bibliography|Works Cited|BIBLIOGRAPHY)[ \t]*:?[ \t]*$",
    re.MULTILINE,
)
#: GB/T 7714 文献类型标识（标题边界锚点）
TYPE_CODE_RE = re.compile(r"\[(J|M|C|D|P|S|A|N|R|EB/OL|DB/OL|J/OL|M/OL|N/OL)\]")
ENTRY_MARK_RE = re.compile(r"^\s*\[(\d+)\]", re.MULTILINE)
DOI_RE = re.compile(r"10\.\d{4,9}/\S+")
ARXIV_RE = re.compile(r"arXiv[:\s]*(\d{4}\.\d{4,5}(?:v\d+)?)", re.IGNORECASE)
URL_RE = re.compile(r"https?://\S+")
YEAR_RE = re.compile(r"\b(19|20)\d{2}\b")
APA_YEAR_RE = re.compile(r"\(((?:19|20)\d{2})[a-z]?\)\.\s*")
#: DOI/URL 尾部需要剥离的标点（\S+ 会贪婪吃到句末标点）
_TRAILING_PUNCT = ".,;:、。，；）)]】》〉"


@dataclass
class Reference:
    """一条参考文献。

    ``span`` 是条目（含编号标记）在文档中的绝对偏移区间；
    ``parsed`` 表示是否成功解析出标题——失败的条目其余字段保持空值。
    """

    index: int
    raw: str
    span: tuple[int, int]
    title: str = ""
    authors: list[str] = field(default_factory=list)
    year: int | None = None
    venue: str = ""
    doi: str = ""
    arxiv_id: str = ""
    url: str = ""
    entry_type: str = "UNKNOWN"  # J/M/C/D/P/S/EB/OL/DB/OL/NUMBERED/APA/UNKNOWN
    parsed: bool = False


@dataclass
class SectionProbe:
    """参考文献表定位结果：表内文本与其在文档中的起始偏移。"""

    text: str
    offset: int
    found: bool


def find_section(doc_text: str) -> SectionProbe:
    """定位参考文献表：优先认表标题行；无标题时回退认密集的 ``[n]`` 编号行。"""
    matches = list(SECTION_HEADING_RE.finditer(doc_text))
    if matches:
        m = matches[-1]
        return SectionProbe(doc_text[m.end() :], m.end(), True)
    hits = list(ENTRY_MARK_RE.finditer(doc_text))
    if len(hits) >= 2:  # 回退启发式：两条以上编号行即视为参考文献区
        return SectionProbe(doc_text[hits[0].start() :], hits[0].start(), True)
    return SectionProbe(doc_text, 0, False)


def _clean_doi(candidate: str) -> str:
    return candidate.rstrip(_TRAILING_PUNCT)


def _extract_ids(raw: str, ref: Reference) -> None:
    if m := DOI_RE.search(raw):
        ref.doi = _clean_doi(m.group(0))
    if m := ARXIV_RE.search(raw):
        ref.arxiv_id = m.group(1)
    if m := URL_RE.search(raw):
        ref.url = m.group(0).rstrip(_TRAILING_PUNCT)


def _split_authors(authors: str) -> list[str]:
    parts = re.split(r"[，；;]| and ", authors)
    return [p.strip(" .。") for p in parts if p.strip(" .。")]


def _parse_gbt(ref: Reference, body: str, type_code: str) -> None:
    """GB/T 7714：标题 = 作者块结束符 与 类型标识 之间的文本。"""
    m = TYPE_CODE_RE.search(body)
    if m is None:  # pragma: no cover - 调用方保证有类型码
        return
    pre = body[: m.start()]
    sep_at = max(pre.rfind(". "), pre.rfind("．"), pre.rfind("。"))
    if sep_at <= 0:
        return
    title = pre[sep_at + 1 :].strip(" .。　\t")
    if not title:
        return
    ref.authors = _split_authors(pre[:sep_at])
    ref.title = title
    ref.entry_type = type_code
    rest = body[m.end() :].lstrip(" .。/　\t")
    # EB/OL 等电子文献的 rest 常以 (发布日期)[引用日期]. 开头——这不是刊名，剥掉
    rest = re.sub(r"^\([^)]*\)\[[^\]]*\]\.?\s*", "", rest)
    if rest.startswith("(") or rest.lower().startswith(("http://", "https://")):
        ref.venue = ""  # 剩下的是日期或裸链接，不是刊名——诚实置空
    else:
        ref.venue = re.split(r"[，,]", rest)[0].strip(" .。　\t")
    ref.parsed = True


def _parse_apa(ref: Reference, body: str) -> bool:
    m = APA_YEAR_RE.search(body)
    if m is None:
        return False
    rest = body[m.end() :]
    segs = [s.strip() for s in re.split(r"(?<=\.)\s+", rest) if s.strip()]
    if not segs or not segs[0].strip(" .。"):
        return False
    ref.authors = _split_authors(body[: m.start()])
    ref.title = segs[0].strip(" .。")
    ref.venue = segs[1].strip(" .。") if len(segs) > 1 else ""
    ref.entry_type = "APA"
    ref.parsed = True
    return True


def _parse_numbered(ref: Reference, body: str) -> None:
    """无类型码编号体：按 '. ' 粗分段，依次当作 作者/标题/出处。"""
    segs = [s.strip() for s in re.split(r"(?<=\.)\s+|．", body) if s.strip()]
    if len(segs) < 2 or not segs[1].strip(" .。"):
        return
    ref.authors = _split_authors(segs[0])
    ref.title = segs[1].strip(" .。")
    ref.venue = segs[2].strip(" .。") if len(segs) > 2 else ""
    ref.entry_type = "NUMBERED"
    ref.parsed = True


def parse_entry_body(ref: Reference, body: str) -> None:
    """对去掉编号标记后的条目文本做形态识别与字段抽取。"""
    _extract_ids(body, ref)
    if m := YEAR_RE.search(body):
        ref.year = int(m.group(0))
    if (m := TYPE_CODE_RE.search(body)) is not None:
        _parse_gbt(ref, body, m.group(1))
    elif not _parse_apa(ref, body):
        _parse_numbered(ref, body)


def _parse_marked_section(section: str, base: int) -> list[Reference]:
    marks = list(ENTRY_MARK_RE.finditer(section))
    refs: list[Reference] = []
    for k, m in enumerate(marks):
        body_start = m.end()
        body_end = marks[k + 1].start() if k + 1 < len(marks) else len(section)
        body = section[body_start:body_end].strip()
        if not body:
            continue
        # span 紧化：去掉编号前的空白与条目尾部的换行
        lead_ws = len(m.group(0)) - len(m.group(0).lstrip())
        trail_ws = body_end - body_start - len(section[body_start:body_end].rstrip())
        span = (base + m.start() + lead_ws, base + body_end - trail_ws)
        ref = Reference(index=int(m.group(1)), raw=f"[{m.group(1)}] {body}", span=span)
        parse_entry_body(ref, body)
        refs.append(ref)
    return refs


def _parse_paragraph_entries(section: str, base: int) -> list[Reference]:
    refs: list[Reference] = []
    for para in re.split(r"\n\s*\n", section):
        text = para.strip()
        at = section.find(text)
        if not text or at < 0:
            continue
        ref = Reference(index=len(refs) + 1, raw=text, span=(base + at, base + at + len(text)))
        parse_entry_body(ref, text)
        refs.append(ref)
    return refs


def parse_references(doc_text: str, *, assume_section: bool = False) -> list[Reference]:
    """解析文档中的参考文献表。

    找不到参考文献表时返回空列表（这是 ``NO_REF_LIST`` 裁决的依据，
    而不是解析失败）。``assume_section=True`` 把整个文本当作参考文献区
    （用于"纯条目列表"文件的 ``gewita refs`` 场景）。
    解析器为启发式：解析不出的条目 ``parsed=False`` 且保留 ``raw``，
    覆盖率请用 :func:`parse_coverage` 如实统计。
    """
    probe = find_section(doc_text)
    if not probe.found:
        if not assume_section:
            return []
        probe = SectionProbe(doc_text, 0, True)
    if ENTRY_MARK_RE.search(probe.text):
        return _parse_marked_section(probe.text, probe.offset)
    return _parse_paragraph_entries(probe.text, probe.offset)


def parse_coverage(refs: list[Reference]) -> float:
    """解析覆盖率：解析出标题的条目占比。空表返回 0.0。"""
    if not refs:
        return 0.0
    return sum(1 for r in refs if r.parsed) / len(refs)


def ref_key_title(ref: Reference) -> str:
    """条目的可比对标题：未解析出标题时回退到原文（是否可用由调用方判断）。"""
    return ref.title if ref.parsed else ref.raw


def norm_title(ref: Reference) -> str:
    """归一化标题，用于指纹与包含度比对。"""
    return normalize(ref_key_title(ref))
