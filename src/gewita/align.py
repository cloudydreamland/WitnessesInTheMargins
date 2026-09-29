"""align.py — 引文↔来源三级对齐裁决。

四级裁决（从强到弱）：

- **VERBATIM**（逐字命中）：归一化后 quote 是 source 归一化文本的子串。
  通过 归一化位置→原始位置 索引映射还原**原始偏移**，并保证偏移不变量：
  注入式 fuzz 永久守护 ``source[start:end] == 引文原文``。
- **NEAR**（近逐字）：difflib.SequenceMatcher 对句窗的相似度 ratio ≥ 0.85，
  用 bigram 倒排索引先筛候选窗（避免对每个窗跑 O(n·m)），
  证据 span 由 matching blocks 收紧到匹配区间的原始偏移。
- **PARAPHRASE**：字符 bigram 包含度（quote 的 bigram 有多少出现在窗内）≥ 0.5。
  注意：这只是**词面重叠**，不等于语义等价——报告语气如此，如实。
- **NOT_FOUND**：以上皆败。

用法::

    from gewita.align import align_quote, Aligner

    align_quote("自注意力机制", source)          # 单次
    a = Aligner(source); a.align(q1); a.align(q2)  # 同一来源多次对齐（推荐，索引只建一次）
"""

from __future__ import annotations

from bisect import bisect_left
from dataclasses import dataclass
from difflib import SequenceMatcher

from .text import NormIndex, build_index, split_sentences

#: 对齐等级从强到弱
LEVELS = ("VERBATIM", "NEAR", "PARAPHRASE", "NOT_FOUND")
LEVEL_RANK = {"VERBATIM": 3, "NEAR": 2, "PARAPHRASE": 1, "NOT_FOUND": 0}

NEAR_RATIO = 0.85
PARAPHRASE_CONTAINMENT = 0.5
#: VERBATIM 的归一化最小长度（过短子串无信息量，按规格约定）
VERBATIM_MIN_NORM = 6
#: NEAR 候选窗的 bigram 包含度预筛阈值与最多跑 SequenceMatcher 的窗数
_NEAR_PREFILTER = 0.45
_NEAR_TOP_K = 20


@dataclass(frozen=True)
class Alignment:
    """对齐结果。

    ``start``/``end`` 是 source 内的**原始偏移**：VERBATIM 时满足偏移不变量
    （注入场景下 ``source[start:end] == quote``）；NEAR/PARAPHRASE 时证据
    span 为匹配窗（NEAR 由 matching blocks 收紧）；NOT_FOUND 时为 ``-1``。
    """

    level: str
    score: float
    start: int
    end: int
    method: str


_NOT_FOUND = Alignment("NOT_FOUND", 0.0, -1, -1, "none")


@dataclass(frozen=True)
class _Window:
    ns: int  # 归一化起点
    ne: int  # 归一化终点
    os_: int  # 原始起点
    oe: int  # 原始终点
    text: str  # 窗内归一化文本


def _bigrams(s: str) -> set[str]:
    return {s[i : i + 2] for i in range(len(s) - 1)}


class Aligner:
    """对一个固定 source 预建句粒度索引，之后可高频对齐。

    NEAR 与 PARAPHRASE 都在**句粒度**（必要时相邻句合并）上裁决：
    内置评测实测表明，对 ≤600 字大窗直接算 ratio 会被窗长稀释
    （近乎逐字的引文 ratio 掉到 0.3），bigram 包含度也会被常见字对
    抬出误报——故 v0.1 以句为证据单元（与规格设想的粗窗不同，如实记录）。
    倒排索引保证候选筛选不做全量两两比对。
    """

    def __init__(self, source: str):
        self.source = source
        self.index: NormIndex = build_index(source)
        self.norm = self.index.norm
        self.units = self._build_units()
        self.inv_unit = self._build_inv(self.units)

    def _norm_span(self, start: int, end: int) -> _Window | None:
        n2o = self.index.norm2orig
        ns, ne = bisect_left(n2o, start), bisect_left(n2o, end)
        if ne <= ns:
            return None
        return _Window(ns, ne, start, end, self.norm[ns:ne])

    def _build_units(self) -> list[_Window]:
        units: list[_Window] = []
        for sent in split_sentences(self.source):
            if w := self._norm_span(sent.start, sent.end):
                units.append(w)
        return units

    @staticmethod
    def _build_inv(items: list[_Window]) -> dict[str, list[int]]:
        inv: dict[str, list[int]] = {}
        for i, w in enumerate(items):
            for bg in _bigrams(w.text):
                inv.setdefault(bg, []).append(i)
        return inv

    def _containments(self, inv: dict[str, list[int]], qbigrams: set[str]) -> dict[int, float]:
        if not qbigrams:
            return {}
        counts: dict[int, int] = {}
        for bg in qbigrams:
            for wi in inv.get(bg, ()):
                counts[wi] = counts.get(wi, 0) + 1
        return {wi: c / len(qbigrams) for wi, c in counts.items()}

    def _verbatim(self, nq: str) -> Alignment | None:
        at = self.norm.find(nq)
        if at < 0:
            return None
        start, end = self.index.to_orig_span(at, at + len(nq))
        # 偏移不变量自证：还原出的原始片段归一化后必须仍等于归一化引文，
        # 否则说明索引映射出了内部 bug——宁可放弃命中也不给错偏移。
        if build_index(self.source[start:end]).norm != nq:
            return None  # pragma: no cover - fuzz 与单测共同守护
        method = "norm-substring"
        if len(nq) < VERBATIM_MIN_NORM:
            method = "norm-substring-short-quote"
        return Alignment("VERBATIM", 1.0, start, end, method)

    def _near(self, nq: str, qbigrams: set[str]) -> Alignment | None:
        """句粒度 NEAR：候选 = 包含度达标的句（引文较长时加相邻句合并），取最优 ratio。"""
        conts = self._containments(self.inv_unit, qbigrams)
        singles = [wi for wi, c in conts.items() if c >= _NEAR_PREFILTER]
        singles.sort(key=lambda wi: (-conts[wi], wi))
        candidates: list[_Window] = [self.units[wi] for wi in singles[:_NEAR_TOP_K]]
        if candidates and len(nq) > max(u.ne - u.ns for u in candidates):
            pair_ids = {wi for wi in singles[:_NEAR_TOP_K] if wi + 1 < len(self.units)}
            pair_ids |= {wi - 1 for wi in singles[:_NEAR_TOP_K] if wi > 0}
            for wi in sorted(pair_ids)[:_NEAR_TOP_K]:
                a, b = self.units[wi], self.units[wi + 1]
                candidates.append(_Window(a.ns, b.ne, a.os_, b.oe, self.norm[a.ns : b.ne]))
        best: tuple[float, _Window] | None = None
        for w in candidates:
            ratio = SequenceMatcher(None, nq, w.text).ratio()
            if ratio < NEAR_RATIO:
                continue
            if best is None or ratio > best[0]:
                best = (ratio, w)
        if best is None:
            return None
        ratio, w = best
        start, end = self._tight_span(nq, w)
        return Alignment("NEAR", ratio, start, end, "seqmatcher-window")

    def _tight_span(self, nq: str, w: _Window) -> tuple[int, int]:
        blocks = SequenceMatcher(None, nq, w.text).get_matching_blocks()
        positions = [j for b in blocks if b.size for j in (b.b, b.b + b.size - 1)]
        if not positions:
            return w.os_, w.oe
        lo, hi = min(positions), max(positions) + 1
        return self.index.to_orig_span(w.ns + lo, w.ns + hi)

    def _paraphrase(self, qbigrams: set[str]) -> Alignment | None:
        """句粒度 bigram 包含度（窗粒度会被常见字对稀释出误报，句粒度更严）。"""
        conts = self._containments(self.inv_unit, qbigrams)
        if not conts:
            return None
        wi = min(conts, key=lambda w: (-conts[w], w))
        if conts[wi] < PARAPHRASE_CONTAINMENT:
            return None
        w = self.units[wi]
        return Alignment("PARAPHRASE", conts[wi], w.os_, w.oe, "bigram-inverted")

    def align(self, quote: str) -> Alignment:
        """对 quote 做四级裁决。空引文/空来源 → NOT_FOUND。"""
        if not quote or not quote.strip() or not self.norm:
            return _NOT_FOUND
        nq = build_index(quote).norm
        if not nq:
            return _NOT_FOUND
        hit = self._verbatim(nq)
        if hit is not None:
            return hit
        qbigrams = _bigrams(nq)
        if qbigrams:
            if hit := self._near(nq, qbigrams):
                return hit
            if hit := self._paraphrase(qbigrams):
                return hit
        return _NOT_FOUND


def align_quote(quote: str, source: str) -> Alignment:
    """便捷入口：``align_quote(quote, source)``。同一 source 多次对齐请用 :class:`Aligner`。"""
    return Aligner(source).align(quote)
