"""verdict.py 测试：判定矩阵、离线诚实性、refstore 联动（自带 mock transport）。"""

from __future__ import annotations

import json

import pytest

from gewita.existence import NOT_FOUND, SUSPECT, UNVERIFIED, TransportResponse
from gewita.refs import parse_references
from gewita.refstore import RefStore
from gewita.verdict import (
    NO_REF_LIST,
    NOT_IN_LIST,
    PARSED,
    judge_document,
)

SOURCES = {
    "src1": "个人信息处理者应当对数据处理活动进行记录，记录至少保存三年。向量数据库通过 ANN 索引将召回延迟控制在 10 毫秒以内。",
}

DOC_OK = (
    "正文如下。个人信息处理者应当对数据处理活动进行记录，记录至少保存三年[1]。\n"
    "参考文献\n[1] 全国人大常委会. 个人信息保护法手册[M]. 北京: 法律出版社, 2021.\n"
)


def _mock(title="个人信息保护法手册", year=2021, venue="法律出版社"):
    def transport(url: str) -> TransportResponse:
        if "crossref" in url:
            payload = {"message": {"items": [{
                "title": [title], "issued": {"date-parts": [[year]]},
                "container-title": [venue], "DOI": "10.1000/x",
            }]}}
            return TransportResponse(200, json.dumps(payload, ensure_ascii=False))
        return TransportResponse(
            200, '<?xml version="1.0"?><feed xmlns="http://www.w3.org/2005/Atom"></feed>')

    return transport


class TestMatrix:
    def test_clean_document(self):
        report = judge_document(DOC_OK, SOURCES, transport=_mock(), doc_name="t")
        assert report.ref_list_found and len(report.refs) == 1
        v = report.verdicts[0]
        assert v.ref_status == PARSED
        assert v.existence == "EXISTS"
        assert v.alignment_level == "VERBATIM"
        assert v.evidence is not None and v.evidence[0] >= 0
        assert not v.suspicious

    def test_not_in_list(self):
        doc = "句子甲[9]。\n参考文献\n[1] 甲. 标题[J]. 学报, 2020.\n"
        report = judge_document(doc, SOURCES, doc_name="t")
        v = report.verdicts[0]
        assert v.ref_status == NOT_IN_LIST and v.ref_index == 9
        assert v.suspicious

    def test_no_ref_list(self):
        doc = "只有正文，没有参考文献表[1]。"
        report = judge_document(doc, SOURCES, doc_name="t")
        v = report.verdicts[0]
        assert v.ref_status == NO_REF_LIST and report.ref_list_found is False

    def test_suspect_year_mismatch(self):
        """命中但年份差 >1 → SUSPECT 且进入异常清单。"""
        report = judge_document(DOC_OK, SOURCES, transport=_mock(year=2015), doc_name="t")
        v = report.verdicts[0]
        assert v.existence == SUSPECT
        assert "年份不符" in v.message
        assert v.suspicious


class TestOfflineHonesty:
    @pytest.mark.parametrize("doc", [
        DOC_OK,
        "主张毫无出处[3]。\n参考文献\n[3] 编者. 天书[M]. 天空: 虚构社, 2099.\n",
        "只有正文[1]，连参考文献表都没有。",
    ])
    def test_offline_never_fabricates(self, doc):
        """离线模式对所有文档形态：existence 只能是 UNVERIFIED/LOCAL_ONLY。"""
        report = judge_document(doc, SOURCES, transport=None, doc_name="t")
        assert report.online is False
        for v in report.verdicts:
            assert v.existence in (UNVERIFIED, "LOCAL_ONLY")
            assert v.existence not in (NOT_FOUND, SUSPECT)

    def test_unparsed_ref_limits_existence(self):
        doc = "引用古籍[1]。\n参考文献\n[1] ［清］佚名稿本（题名缺失），藏于某馆.\n"
        report = judge_document(doc, {}, transport=_mock(), doc_name="t")
        v = report.verdicts[0]
        assert v.existence == UNVERIFIED and "未解析出标题" in v.message


class TestRefStoreIntegration:
    def test_local_only_from_history(self, tmp_path):
        store = RefStore(tmp_path / "store.jsonl")
        entries = parse_references(DOC_OK)
        store.append(entries[0], "EXISTS", ts=1700000000.0)
        report = judge_document(DOC_OK, SOURCES, transport=None, store=store, doc_name="t")
        v = report.verdicts[0]
        assert v.existence == "LOCAL_ONLY"
        assert "1700000000" in v.message

    def test_online_verdicts_saved_then_reused(self, tmp_path):
        store = RefStore(tmp_path / "s.jsonl")
        report = judge_document(DOC_OK, SOURCES, transport=_mock(), doc_name="t")
        for v in report.verdicts:
            ref = next(r for r in report.refs if r.index == v.ref_index)
            store.append(ref, v.existence)
        assert store.stats()["total"] == 1
        again = judge_document(DOC_OK, SOURCES, transport=None, store=store, doc_name="t")
        assert again.verdicts[0].existence == "LOCAL_ONLY"
