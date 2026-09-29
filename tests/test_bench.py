"""bench.py 测试：金标规模下限、指标确定性、mock transport 形态、渲染。"""

from __future__ import annotations

import json
import urllib.parse

from gewita.bench import (
    REGISTRY,
    format_bench_markdown,
    load_corpus,
    make_mock_transport,
    run_bench,
)
from gewita.existence import TransportResponse
from gewita.text import normalize


def _gold_counts(gold):
    from collections import Counter
    return Counter(g.level for g in gold)


class TestGoldScale:
    """规格下限：金标 ≥26 条，verbatim≥8 / paraphrase≥6 / not_in_source≥5 / fabricated≥5 / unparsable≥2。"""

    def test_counts_meet_spec(self):
        _, _, gold = load_corpus()
        counts = _gold_counts(gold)
        assert len(gold) >= 26
        assert counts["verbatim"] >= 8
        assert counts["paraphrase"] >= 6
        assert counts["not_in_source"] >= 5
        assert sum(1 for g in gold if g.fabricated) >= 5
        assert sum(1 for g in gold if g.unparsable) >= 2

    def test_docs_and_sources(self):
        docs, sources, _ = load_corpus()
        assert len(docs) == 8 and len(sources) == 8


class TestMetrics:
    def test_builtin_corpus_fully_solved(self):
        """内置语料的真实上限（合成语料，格式级，不外推）：全指标 1.0。"""
        m = run_bench()
        assert m["alignment_micro"]["accuracy"] == 1.0
        assert m["fabricated"]["f1"] == 1.0
        assert m["unparsable_detected"] == 2 and m["unparsable_missed"] == 0
        assert 0 < m["parse_coverage"] < 1  # 有意保留 unparsable 条目，覆盖率如实 <100%

    def test_deterministic(self):
        assert run_bench() == run_bench()


class TestMockTransport:
    def test_crossref_hit_shape(self):
        transport = make_mock_transport()
        title = "预训练语言模型研究综述"
        url = ("https://api.crossref.org/works?query.bibliographic="
               + urllib.parse.quote(title) + "&rows=3")
        resp = transport(url)
        assert resp.status == 200
        items = json.loads(resp.body)["message"]["items"]
        assert items and items[0]["title"][0] == title

    def test_crossref_miss_then_arxiv_miss(self):
        transport = make_mock_transport()
        fake = "https://api.crossref.org/works?query.bibliographic=" \
               + urllib.parse.quote("不存在的编造标题") + "&rows=3"
        assert json.loads(transport(fake).body)["message"]["items"] == []
        arxiv = "http://export.arxiv.org/api/query?search_query=" \
                + urllib.parse.quote('ti:"不存在的编造标题"') + "&max_results=3"
        assert "<entry>" not in transport(arxiv).body

    def test_registry_keys_normalized(self):
        for key in REGISTRY:
            assert key == normalize(key)

    def test_unknown_host_404(self):
        transport = make_mock_transport()
        assert transport("https://elsewhere.example.org/x") == TransportResponse(404, "unknown host in mock transport")


class TestRender:
    def test_markdown_tables(self):
        md = format_bench_markdown(run_bench())
        assert "| 对齐级别 | P | R | F1 |" in md
        assert "fabricated 检测" in md
        assert "解析覆盖率" in md
