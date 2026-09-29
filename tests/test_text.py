"""text.py 测试：归一化、切句、偏移不变量 fuzz。"""

from __future__ import annotations

import random

import pytest

from gewita.text import build_index, normalize, split_sentences


class TestNormalize:
    def test_fullwidth_to_halfwidth(self):
        assert normalize("Ｈｅｌｌｏ　Ｗｏｒｌｄ") == "helloworld"

    def test_fullwidth_punct(self):
        assert normalize("ｘ＝１．５：ｙ") == "x=1.5:y"

    def test_quotes_unified(self):
        assert normalize("「引用」‘单’“双”『嵌』") == '"引用""单""双""嵌"'
        assert normalize(normalize("「x」")) == normalize("「x」")  # 幂等

    def test_whitespace_variants_removed(self):
        assert normalize("a\u3000b\tc\nd\r\ne\u200bf﻿g­h") == "abcdefgh"

    def test_casefold(self):
        assert normalize("Straße ABC") == "strasseabc"

    def test_empty(self):
        assert normalize("") == ""

    def test_idempotent(self):
        for s in ["Hello 世界！ ｘ", "「引」「证」\t\n　", "a.b.c(v1.2)"]:
            assert normalize(normalize(s)) == normalize(s)


class TestBuildIndex:
    def test_to_orig_span_roundtrip(self):
        text = "模型 量化（Quant）将权重压缩。"
        idx = build_index(text)
        nq = normalize("量化（Quant）将权重")
        at = idx.norm.find(nq)
        assert at >= 0
        start, end = idx.to_orig_span(at, at + len(nq))
        assert normalize(text[start:end]) == nq

    def test_empty_span_rejected(self):
        with pytest.raises(ValueError):
            build_index("abc").to_orig_span(2, 2)

    def test_norm2orig_monotonic(self):
        idx = build_index("a b　c\nd")
        assert list(idx.norm2orig) == sorted(idx.norm2orig)


class TestSplitSentences:
    def test_cjk_basic(self):
        sents = split_sentences("你好。世界！再见？")
        assert [s.text for s in sents] == ["你好。", "世界！", "再见？"]

    def test_closing_quote_attached(self):
        sents = split_sentences("他说：“来啦。”然后走了。")
        assert sents[0].text == "他说：“来啦。”"
        assert sents[1].text == "然后走了。"

    def test_decimal_not_split(self):
        assert len(split_sentences("精度达到 95.5% 以上。")) == 1

    def test_version_not_split(self):
        assert len(split_sentences("版本 1.2.3 已发布。")) == 1

    def test_url_not_split(self):
        sents = split_sentences("详见 https://example.com/a.b。")
        assert len(sents) == 1
        assert sents[0].text.endswith("。")

    def test_abbreviation_not_split(self):
        sents = split_sentences("She met U.S. officials yesterday. Then left.")
        assert len(sents) == 2

    def test_ascii_period_splits(self):
        sents = split_sentences("First one. Second one.")
        # 尾随空白按设计归入前句（保证拼接不变量）
        assert [s.text for s in sents] == ["First one. ", "Second one."]

    def test_newline_is_hard_boundary(self):
        sents = split_sentences("标题行没有句号\n\n正文第一句。")
        assert sents[0].text == "标题行没有句号\n\n"
        assert sents[1].text == "正文第一句。"

    def test_semicolon_and_ellipsis(self):
        sents = split_sentences("一者也；二者也……完。")
        assert len(sents) == 3

    def test_join_invariant(self):
        text = "句子一[1]。句子二！句子三；尾行没有终结符"
        assert "".join(s.text for s in split_sentences(text)) == text

    def test_span_equality(self):
        text = "甲。乙[1]。\n丙"
        for s in split_sentences(text):
            assert s.text == text[s.start : s.end]

    def test_trailing_whitespace_joined_to_last(self):
        sents = split_sentences("完。\n\n")
        assert len(sents) == 1 and sents[0].text == "完。\n\n"

    def test_empty(self):
        assert split_sentences("") == []


@pytest.mark.parametrize("seed", [1, 42, 2026, 777, 31337])
def test_fuzz_split_invariant(seed):
    """随机文本 fuzz：切句结果拼接必须精确还原原文，span 必须自洽。"""
    rng = random.Random(seed)
    alphabet = "。！？；…!?;.，、abcＡＢ１２“”「」 \n\n字词句"
    for _ in range(30):
        text = "".join(rng.choice(alphabet) for _ in range(rng.randint(0, 80)))
        sents = split_sentences(text)
        assert "".join(s.text for s in sents) == text
        pos = 0
        for s in sents:
            assert s.text == text[s.start : s.end]
            assert s.start == pos
            pos = s.end


@pytest.mark.parametrize("seed", [5, 6, 7])
def test_fuzz_norm_index_consistency(seed):
    """随机文本 fuzz：归一化区间还原回原文后，归一化结果必须等于归一化引文。"""
    rng = random.Random(seed)
    alphabet = "。！？abcＡＢ“” \n字词"
    for _ in range(30):
        text = "".join(rng.choice(alphabet) for _ in range(rng.randint(1, 60)))
        idx = build_index(text)
        if not idx.norm:
            continue
        a = rng.randrange(len(idx.norm))
        b = rng.randint(a + 1, len(idx.norm))
        start, end = idx.to_orig_span(a, b)
        assert build_index(text[start:end]).norm == idx.norm[a:b]
