"""extract.py 测试：标记形态、区间展开、句挂接、表区排除。"""

from __future__ import annotations

from gewita.extract import expand_marker, extract_citations, strip_markers
from gewita.refs import parse_references


class TestExpand:
    def test_single(self):
        assert expand_marker("1") == [1]

    def test_list(self):
        assert expand_marker("1,2") == [1, 2]
        assert expand_marker("1，3") == [1, 3]

    def test_range(self):
        assert expand_marker("1-3") == [1, 2, 3]
        assert expand_marker("2 – 4") == [2, 3, 4]

    def test_range_capped(self):
        assert expand_marker("1-10000") == []

    def test_reversed_range_skipped(self):
        assert expand_marker("3-1") == []

    def test_garbage_token_skipped(self):
        assert expand_marker("2026-03-01") == []


class TestExtract:
    def test_simple_marker(self):
        doc = "这是一个句子[1]。"
        cites = extract_citations(doc)
        assert len(cites) == 1
        c = cites[0]
        assert c.ref_indices == [1] and c.style == "numeric" and c.raw == "[1]"
        assert doc[c.marker_span[0] : c.marker_span[1]] == "[1]"
        assert c.marker_span[0] == doc.find("[1]")
        assert c.sentence_text == "这是一个句子。"  # 标记被切除，主张保持干净
        assert doc[c.sentence_span[0] : c.sentence_span[1]] == "这是一个句子[1]。"

    def test_multi_and_range(self):
        doc = "句子甲[1,2]。句子乙[1-3]。"
        cites = extract_citations(doc)
        assert cites[0].ref_indices == [1, 2]
        assert cites[1].ref_indices == [1, 2, 3]

    def test_consecutive_markers(self):
        doc = "连续标记[1][2]。"
        cites = extract_citations(doc)
        assert [c.ref_indices for c in cites] == [[1], [2]]

    def test_sentence_attachment(self):
        doc = "第一句。第二句有引用[1]。"
        c = extract_citations(doc)[0]
        assert c.sentence_text == "第二句有引用。"
        assert doc[c.sentence_span[0] : c.sentence_span[1]] == "第二句有引用[1]。"

    def test_refs_section_excluded(self):
        doc = "正文引用[1]。\n\n参考文献\n[1] 甲. 标题[J]. 学报, 2020.\n"
        cites = extract_citations(doc)
        assert len(cites) == 1
        assert cites[0].marker_span[0] < doc.find("参考文献")

    def test_author_year_resolved(self):
        doc = "正文 (Smith, 2020) 完毕。\n\n参考文献\n[3] SMITH J. A study[J]. J. of AI, 2020."
        entries = parse_references(doc)
        cites = extract_citations(doc, entries)
        ay = [c for c in cites if c.style == "author_year"]
        assert len(ay) == 1
        assert ay[0].ref_indices == [3] and ay[0].year == 2020

    def test_author_year_unresolved_noted(self):
        doc = "正文 (Nobody, 1999) 完毕。\n\n参考文献\n[1] 甲. 标题[J]. 学报, 2020."
        entries = parse_references(doc)
        cites = extract_citations(doc, entries)
        ay = [c for c in cites if c.style == "author_year"]
        assert ay[0].ref_indices == []
        assert ay[0].note != ""

    def test_markdown_link_not_matched(self):
        doc = "参见 [文档](https://example.com)。"
        assert extract_citations(doc) == []

    def test_strip_markers(self):
        assert strip_markers("世界[1]。多[2,3]个[4-6]。") == "世界。多个。"

    def test_no_citations(self):
        assert extract_citations("干净文档，没有引用。") == []
