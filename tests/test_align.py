"""align.py 测试：四级正反例、偏移不变量 fuzz、性能 smoke。"""

from __future__ import annotations

import random
import time

import pytest

from gewita.align import LEVEL_RANK, Aligner, align_quote

SOURCE = (
    "Transformer 架构通过自注意力机制建模长距离依赖，已成为主流范式。"
    "模型量化将权重从浮点压缩到低位宽整数，是边缘部署的关键技术。"
    "Retrieval-augmented generation grounds model outputs in external evidence."
)


def test_verbatim_cjk_exact_offsets():
    quote = "模型量化将权重从浮点压缩到低位宽整数"
    a = align_quote(quote, SOURCE)
    assert a.level == "VERBATIM"
    assert SOURCE[a.start : a.end] == quote  # 偏移不变量


def test_verbatim_with_marker_cut_leftovers():
    """句文本带被切标记后的残留空格（如 'threshold .'）仍应逐字命中。"""
    src = "Large models exhibit emergent capabilities."
    a = align_quote("Large models exhibit emergent capabilities .", src)
    assert a.level == "VERBATIM" and src[a.start : a.end] == "Large models exhibit emergent capabilities."


def test_verbatim_width_and_quote_variants():
    src = "他说：“模型量化是关键技术”。"
    a = align_quote('模型量化是关键技术', src)  # 归一化后引号/宽度差异抹平
    assert a.level == "VERBATIM"
    assert a.start >= 0 and a.end <= len(src)


def test_verbatim_short_quote_still_exact():
    a = align_quote("量化", SOURCE)
    assert a.level == "VERBATIM"
    assert SOURCE[a.start : a.end] == "量化"
    assert a.method == "norm-substring-short-quote"


def test_near_positive():
    src = "混合检索结合稀疏召回与稠密向量召回，在多数基准上优于单一检索通道。"
    quote = "混合检索结合稀疏召回与稠密向量召回，在多数基准上普遍优于单一检索通道。"  # 多两个字
    a = align_quote(quote, src)
    assert a.level == "NEAR"
    assert a.score >= 0.85
    assert 0 <= a.start < a.end <= len(src)


def test_near_beats_paraphrase_ordering():
    """同为命中时强等级优先：近逐字不该降级为 PARAPHRASE。"""
    src = "引用透传要求生成器在输出答案的同时标注所引用片段的编号，这是工程要求。"
    quote = "引用透传要求生成器在输出答案的同时标注所引用片段的编号，"  # 近逐字前缀
    a = align_quote(quote, src)
    assert a.level in ("VERBATIM", "NEAR")


def test_paraphrase_positive():
    src = "重排序模型对候选文档做交叉编码打分，能将答案命中率提升 12 个百分点。"
    quote = "交叉编码重排序对候选文档打分，使答案命中率得到显著提升。"
    a = align_quote(quote, src)
    assert a.level == "PARAPHRASE"
    assert a.score >= 0.5


def test_paraphrase_not_semantic_equivalence():
    """PARAPHRASE 只认词面：语义相反但词面高度重叠的改写也判 PARAPHRASE（诚实边界）。"""
    src = "系统在离线运行时不得输出关于文献真实性的否定结论，所有解析器应报告解析覆盖率。"
    quote = "系统离线时可以输出否定文献真实性的结论，解析器无需报告覆盖率。"
    a = align_quote(quote, src)
    assert a.level == "PARAPHRASE"
    assert a.score >= 0.5 and a.score < 1.0


def test_not_found_when_unrelated():
    a = align_quote("敦煌壁画颜料分析与宋代瓷器贸易", SOURCE)
    assert a.level == "NOT_FOUND" and a.start == -1 and a.end == -1


def test_not_found_below_containment():
    src = "唯一的一句话。"
    a = align_quote("完全无关的内容', '另一句话", src)
    assert a.level == "NOT_FOUND"


@pytest.mark.parametrize("quote,src", [("", SOURCE), ("  ", SOURCE), ("引文", "")])
def test_empty_inputs(quote, src):
    assert align_quote(quote, src).level == "NOT_FOUND"


def test_level_rank_order():
    assert LEVEL_RANK["VERBATIM"] > LEVEL_RANK["NEAR"] > LEVEL_RANK["PARAPHRASE"]


def test_aligner_reuse_consistent():
    al = Aligner(SOURCE)
    a1 = al.align("自注意力机制建模长距离依赖")
    a2 = align_quote("自注意力机制建模长距离依赖", SOURCE)
    assert (a1.level, a1.start, a1.end) == (a2.level, a2.start, a2.end)


@pytest.mark.parametrize("seed", [0, 1, 2, 3, 4, 5, 6, 7, 8, 9])
def test_fuzz_injected_quote_recovered_exactly(seed):
    """偏移不变量 fuzz（招牌）：把随机引文**逐字**注入随机来源，必须 VERBATIM 且精确找回。

    词均带唯一编号且引文取自来源的连续原文切片，保证归一化形态只出现一次——
    找回的必须正是注入处，`injected[start:end] == quote` 逐字符成立。
    """
    rng = random.Random(seed)
    base = ["模型", "量化", "检索", "引用", "transformer", "注意力", "数据", "校勘"]
    seps = ["。", "，", "、"]
    for _ in range(20):
        words = [f"{rng.choice(base)}{k}" for k in range(rng.randint(3, 30))]
        source = "".join(w + rng.choice(seps) for w in words)
        # 引文 = 来源的连续原文切片（词内含分隔符），保证是逐字注入
        a_at = source.find(words[rng.randrange(len(words))])
        quote = source[a_at : a_at + rng.randint(6, 24)]
        if not quote.strip() or len("".join(quote.split())) < 6:
            continue
        cut = a_at // 2  # 注入点在切片之前，find 命中的必是注入处
        injected = source[:cut] + quote + source[cut:]
        a = align_quote(quote, injected)
        assert a.level == "VERBATIM", (seed, quote, injected)
        assert injected[a.start : a.end] == quote  # 招牌不变量：精确找回


def test_perf_smoke_1mb():
    """性能 smoke：~1MB 来源建索引 + 三次对齐应在数秒内完成（bigram 倒排，非 O(n²)）。"""
    big = ("自注意力机制建模长距离依赖，检索增强生成缓解幻觉问题，重排序提升命中率。" * 28000)
    assert len(big) > 900_000
    t0 = time.perf_counter()
    al = Aligner(big)
    al.align("重排序模型对候选文档打分，使答案命中率得到显著提升")  # PARAPHRASE 路径
    al.align("自注意力机制建模长距离依赖，检索增强生成缓解幻觉问题，")  # VERBATIM 路径
    al.align("完全无关的句子，讲的是敦煌壁画颜料分析。")  # NOT_FOUND 路径
    elapsed = time.perf_counter() - t0
    assert elapsed < 10.0, f"1MB 对齐耗时 {elapsed:.1f}s，疑似 O(n²) 回潮"
