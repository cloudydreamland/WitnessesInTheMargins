"""text.py — 归一化与切句，全程携带精确偏移。

两个公开能力：

- ``normalize(text)`` / ``build_index(text)``：全角→半角、casefold、统一引号、
  去除一切空白变体；``build_index`` 额外给出 归一化位置→原始位置 的索引映射，
  这是 :mod:`gewita.align` 偏移不变量（``source[start:end] == 引文原文``）的地基。
- ``split_sentences(text)``：中英文感知的切句，每个句子返回 ``(text, start, end)``，
  满足拼接不变量 ``"".join(s.text for s in sentences) == text``。

切句规则（启发式，如实记录）：
终結符 ``。！？；…`` 与 ``!?;`` 无条件断句；ASCII ``.`` 在前后均为字母数字
（小数 1.5、版本 1.2.3、域名 a.com）或后一字符也是 ``.``（缩写 U.S.、省略号）
时不断句；终结符后的重复终结符与闭引号/闭括号并入本句。
"""

from __future__ import annotations

from dataclasses import dataclass

# 归一化时映射为普通双引号 " 的引号变体（中文直角/弯引号、西文弯引号等）
_QUOTE_VARIANTS = "「」『』“”‘’‚„‟‛〝〞«»‹›"
# 归一化时直接丢弃的不可见字符（零宽系 + BOM + 软连字符）
_INVISIBLE = "\u200b‌‍﻿­"
_TERMINATORS = set("。！？；…!?;.")
_CLOSERS = set("”’」』）)]】》〉\"'、，")

_SKIP = frozenset(_QUOTE_VARIANTS)  # 引号变体在归一化串里统一成 '"'，不是丢弃


@dataclass(frozen=True)
class NormIndex:
    """原文与归一化文本的对应关系。

    ``norm[i]`` 来自原文的 ``norm2orig[i]`` 位置（casefold 展开时多个归一化字符
    指向同一原始位置）。据此可把归一化串上的匹配还原为原文精确偏移。
    """

    text: str
    norm: str
    norm2orig: tuple[int, ...]

    def to_orig_span(self, start: int, end: int) -> tuple[int, int]:
        """把归一化区间 [start, end) 映射回原文区间 [orig_start, orig_end)。

        要求 start < end（空区间无意义）。
        """
        if start >= end:
            raise ValueError("归一化区间为空，无法映射回原文偏移")
        return self.norm2orig[start], self.norm2orig[end - 1] + 1


def _fold_char(ch: str) -> str:
    code = ord(ch)
    if 0xFF01 <= code <= 0xFF5E:  # 全角 ASCII 区
        ch = chr(code - 0xFEE0)
    elif ch in _SKIP:
        ch = '"'
    return ch.casefold()


def build_index(text: str) -> NormIndex:
    """归一化并建立 归一化位置→原始位置 索引。"""
    out: list[str] = []
    origins: list[int] = []
    for i, ch in enumerate(text):
        if ch.isspace() or ch in _INVISIBLE:
            continue
        for folded in _fold_char(ch):
            out.append(folded)
            origins.append(i)
    return NormIndex(text, "".join(out), tuple(origins))


def normalize(text: str) -> str:
    """全角→半角、casefold、统一引号、去所有空白变体。空串安全。"""
    return build_index(text).norm


@dataclass(frozen=True)
class Sentence:
    """一个句子及其在原文中的精确区间，``text == text_[start:end]``。"""

    text: str
    start: int
    end: int


def split_sentences(text: str) -> list[Sentence]:
    """中英文感知切句，返回的句子首尾相接恰好覆盖整个 ``text``。

    换行是硬边界（无终结符的标题行自成一句，不与正文首句粘连）。
    """
    sentences: list[Sentence] = []
    n = len(text)
    start = 0
    i = 0
    while i < n:
        ch = text[i]
        is_newline = ch == "\n"
        if (ch in _TERMINATORS and not _is_suppressed_dot(text, i)) or is_newline:
            j = i + 1
            if not is_newline:
                # 连续终结符（！！、？。）与紧随的闭引号/闭括号并入本句
                while j < n and (text[j] in _TERMINATORS or text[j] in _CLOSERS):
                    j += 1
            # 尾随空白归入本句，保证拼接不变量
            while j < n and text[j].isspace():
                j += 1
            sentences.append(Sentence(text[start:j], start, j))
            start = j
            i = j
            continue
        i += 1
    if start < n:
        tail = text[start:]
        if not tail.strip() and sentences:
            last = sentences[-1]
            sentences[-1] = Sentence(text[last.start : n], last.start, n)
        else:
            sentences.append(Sentence(tail, start, n))
    return sentences


def _is_suppressed_dot(text: str, i: int) -> bool:
    """ASCII '.' 在小数/版本号/域名/缩写场景下不算终结符。"""
    if text[i] != ".":
        return False
    prev = text[i - 1] if i > 0 else ""
    nxt = text[i + 1] if i + 1 < len(text) else ""
    if prev.isalnum() and nxt.isalnum():  # 1.5 / 1.2.3 / 192.168.0.1 / a.com
        return True
    if nxt == ".":  # U.S. / ...
        return True
    # 单字母缩写尾点：U.S. / J. K.
    return prev.isalpha() and i >= 2 and text[i - 2] == "."
