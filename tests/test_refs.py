"""refs.py 测试：GB/T 7714 各类型码、编号体、APA-lite、ID 抽取、坏输入。"""

from __future__ import annotations

from gewita.refs import (
    find_section,
    parse_coverage,
    parse_references,
    ref_key_title,
)


def _doc_with(refs: str, body: str = "正文引用[1]。\n") -> str:
    return f"{body}\n参考文献\n{refs}"


class TestGBT:
    def test_journal(self):
        doc = _doc_with("[1] 张三，李四. 深度学习综述[J]. 中文信息学报, 2020, 15(3): 12-18.")
        refs = parse_references(doc)
        assert len(refs) == 1
        r = refs[0]
        assert r.index == 1 and r.parsed
        assert r.title == "深度学习综述"
        assert r.authors == ["张三", "李四"]
        assert r.year == 2020
        assert r.venue == "中文信息学报"
        assert r.entry_type == "J"

    def test_book(self):
        doc = _doc_with("[1] 王五. 某本专著[M]. 北京: 某出版社, 2021.")
        r = parse_references(doc)[0]
        assert r.title == "某本专著" and r.entry_type == "M" and r.year == 2021

    def test_conference(self):
        doc = _doc_with("[3] LI M, CHEN J. Some QA method[C]//Proceedings of ACL. 2023: 112-124.")
        r = parse_references(doc)[0]
        assert r.index == 3
        assert r.title == "Some QA method" and r.entry_type == "C"
        assert r.venue.startswith("Proceedings of ACL")

    def test_thesis_and_patent(self):
        doc = _doc_with(
            "[1] 赵六. 某研究[D]. 某大学, 2019.\n[2] 孙七. 某装置[P]. 2022."
        )
        refs = parse_references(doc)
        assert [r.entry_type for r in refs] == ["D", "P"]
        assert refs[0].title == "某研究"

    def test_ebol_with_dates_and_url(self):
        doc = _doc_with(
            "[1] 某机构. 网页标题[EB/OL]. (2020-01-01)[2026-01-01]. https://example.com/a."
        )
        r = parse_references(doc)[0]
        assert r.title == "网页标题" and r.entry_type == "EB/OL"
        assert r.year == 2020
        assert r.url == "https://example.com/a"
        assert r.venue == ""  # 剩下的是日期与链接，不是刊名——诚实置空

    def test_dbol(self):
        doc = _doc_with("[1] 某库. 数据集[DB/OL]. https://data.example.com.")
        r = parse_references(doc)[0]
        assert r.entry_type == "DB/OL" and r.url.startswith("https://data.example.com")

    def test_multi_author_semicolon(self):
        doc = _doc_with("[1] 张三；李四；王五. 多作者标题[J]. 学报, 2018.")
        r = parse_references(doc)[0]
        assert r.authors == ["张三", "李四", "王五"]


class TestNumberedAndAPA:
    def test_numbered_without_type_code(self):
        doc = _doc_with("[1] 张三. 无类型码标题. 刊名, 2020.")
        r = parse_references(doc)[0]
        assert r.parsed and r.title == "无类型码标题"
        assert r.entry_type == "NUMBERED" and r.venue == "刊名, 2020"

    def test_apa_lite(self):
        doc = _doc_with("[1] Smith, J. (2020). Title of the paper. Venue Name.")
        r = parse_references(doc)[0]
        assert r.parsed and r.title == "Title of the paper"
        assert r.year == 2020 and r.entry_type == "APA"
        assert r.venue == "Venue Name"

    def test_apa_in_plain_section(self):
        doc = "正文\n\nReferences\n\nDoe, J. (2019). Another study. Journal of Tests.\n"
        refs = parse_references(doc)
        assert len(refs) == 1 and refs[0].title == "Another study"


class TestIds:
    def test_doi_extracted_trailing_punct_stripped(self):
        doc = _doc_with("[1] 作者. 标题[J]. 刊名, 2024. DOI:10.1234/abc.def.")
        r = parse_references(doc)[0]
        assert r.doi == "10.1234/abc.def"

    def test_arxiv_extracted(self):
        doc = _doc_with("[1] 作者. 标题[J]. 刊名, 2023. arXiv:2310.12345v2.")
        r = parse_references(doc)[0]
        assert r.arxiv_id == "2310.12345v2"

    def test_year_first_occurrence(self):
        doc = _doc_with("[1] 机构. 标题[EB/OL]. (2020-11-25)[2026-01-10]. https://x.io.")
        assert parse_references(doc)[0].year == 2020


class TestStructure:
    def test_multiple_entries_indices_and_spans(self):
        refs_text = "[1] 甲. 标题一[J]. 学报, 2020.\n[2] 乙. 标题二[J]. 学报, 2021."
        doc = _doc_with(refs_text)
        refs = parse_references(doc)
        assert [r.index for r in refs] == [1, 2]
        for r in refs:
            assert doc[r.span[0] : r.span[1]].startswith(f"[{r.index}]")

    def test_no_section_returns_empty(self):
        assert parse_references("没有任何参考文献的文档[1]。") == []

    def test_find_section_heading(self):
        doc = "正文\n参考文献\n[1] 甲. 标题[J]. 学报, 2020."
        probe = find_section(doc)
        assert probe.found and doc[probe.offset:].startswith("\n[1]")

    def test_garbage_line_not_crash_and_unparsed(self):
        doc = _doc_with("[1] ［清］佚名稿本残卷（题名信息缺失），藏于某图书馆特藏部.")
        refs = parse_references(doc)
        assert len(refs) == 1
        assert not refs[0].parsed
        assert refs[0].title == "" and refs[0].entry_type == "UNKNOWN"

    def test_empty_entry_skipped(self):
        refs = parse_references(_doc_with("[1] 甲. 标题[J]. 学报, 2020.\n[2]"))
        assert [r.index for r in refs] == [1]

    def test_coverage(self):
        doc = _doc_with(
            "[1] 甲. 标题一[J]. 学报, 2020.\n[2] 无题名残卷，信息缺失."
        )
        refs = parse_references(doc)
        assert parse_coverage(refs) == 0.5
        assert parse_coverage([]) == 0.0

    def test_assume_section(self):
        refs = parse_references("[1] 甲. 标题[J]. 学报, 2020.", assume_section=True)
        assert len(refs) == 1 and refs[0].parsed

    def test_ref_key_title_fallback(self):
        doc = _doc_with("[1] 无题名残卷.")
        r = parse_references(doc)[0]
        assert ref_key_title(r) == r.raw
