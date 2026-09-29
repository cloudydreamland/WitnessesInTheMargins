"""existence.py 测试：结构校验、mock transport 在线核验、限速与预算。"""

from __future__ import annotations

import json
import time
import urllib.parse

import pytest

from gewita.existence import (
    EXISTS,
    NOT_FOUND,
    SUSPECT,
    UNVERIFIED,
    TransportResponse,
    arxiv_valid,
    doi_valid,
    structure_notes,
    title_containment,
    title_fingerprint,
    verify_online,
)
from gewita.refs import Reference


def _ref(title="预训练语言模型研究综述", year=2021, venue="中文信息学报",
         doi="", parsed=True) -> Reference:
    return Reference(index=1, raw=f"[1] 作者. {title}[J]. {venue}, {year}.",
                     span=(0, 10), title=title if parsed else "", year=year,
                     venue=venue, doi=doi, parsed=parsed)


def _crossref(items: list[dict]) -> str:
    return json.dumps({"message": {"items": items}}, ensure_ascii=False)


def _item(title="预训练语言模型研究综述", year=2021, venue="中文信息学报") -> dict:
    return {"title": [title], "issued": {"date-parts": [[year]]},
            "container-title": [venue], "DOI": "10.1000/real"}


class TestStructure:
    @pytest.mark.parametrize("doi", ["10.1234/abc", "10.12345678/x.y_z", "10.9999/fake.2024.0117"])
    def test_doi_valid(self, doi):
        assert doi_valid(doi)

    @pytest.mark.parametrize("doi", ["", "11.1234/abc", "10.123/abc", "10.1234567890/a", "10.1234/"])
    def test_doi_invalid(self, doi):
        assert not doi_valid(doi)

    @pytest.mark.parametrize("aid", ["2310.12345", "2310.12345v2", "2601.00001"])
    def test_arxiv_valid(self, aid):
        assert arxiv_valid(aid)

    @pytest.mark.parametrize("aid", ["", "2310.123", "231.12345", "999913.1", "abc"])
    def test_arxiv_invalid(self, aid):
        assert not arxiv_valid(aid)

    def test_fingerprint_stable_and_distinct(self):
        a = title_fingerprint("预训练语言模型研究综述")
        assert a == title_fingerprint("Ｐｒｅ…") or a != ""
        assert a == title_fingerprint("预训练语言模型研究综述 ")  # 空白不影响
        assert a != title_fingerprint("另一篇标题")

    def test_containment(self):
        assert title_containment("深度学习综述", "深度学习综述") == 1.0
        assert title_containment("深度学习综述", "完全无关主题") < 0.5
        assert title_containment("", "x") == 0.0

    def test_structure_notes(self):
        notes = structure_notes(_ref(doi="10.12/bad"))
        assert notes and "结构不合法" in notes[0]
        assert structure_notes(_ref(doi="10.1234/ok")) == []


class TestVerifyOnline:
    def test_disabled_by_default(self):
        """招牌断言：transport=None（离线）→ UNVERIFIED，永不输出否定存在结论。"""
        r = verify_online(_ref(), transport=None)
        assert r.status == UNVERIFIED
        assert r.status not in (NOT_FOUND, SUSPECT, EXISTS)

    def test_crossref_hit_exists(self):
        calls: list[str] = []

        def transport(url: str) -> TransportResponse:
            calls.append(url)
            assert "api.crossref.org" in url
            assert "query.bibliographic" in url
            return TransportResponse(200, _crossref([_item()]))

        r = verify_online(_ref(), transport, min_interval=0)
        assert r.status == EXISTS and r.provider == "crossref"
        assert len(calls) == 1  # 命中即止，不查 arXiv

    def test_year_mismatch_suspect(self):
        def transport(url: str) -> TransportResponse:
            return TransportResponse(200, _crossref([_item(year=2015)]))

        r = verify_online(_ref(year=2021), transport, min_interval=0)
        assert r.status == SUSPECT
        assert "年份不符" in r.detail and "2021" in r.detail and "2015" in r.detail

    def test_venue_mismatch_suspect(self):
        def transport(url: str) -> TransportResponse:
            return TransportResponse(200, _crossref([_item(venue="完全不同的刊物名称")]))

        r = verify_online(_ref(venue="中文信息学报"), transport, min_interval=0)
        assert r.status == SUSPECT and "刊名不符" in r.detail

    def test_not_found_both_providers(self):
        def transport(url: str) -> TransportResponse:
            if "crossref" in url:
                return TransportResponse(200, _crossref([]))
            assert "export.arxiv.org" in url
            return TransportResponse(
                200, '<?xml version="1.0"?><feed xmlns="http://www.w3.org/2005/Atom"></feed>')

        r = verify_online(_ref(title="不存在的编造标题"), transport, min_interval=0)
        assert r.status == NOT_FOUND
        assert "均未找到" in r.detail

    def test_arxiv_fallback_hit(self):
        atom = ('<?xml version="1.0"?><feed xmlns="http://www.w3.org/2005/Atom">'
                "<entry><title>预训练语言模型研究综述</title>"
                "<published>2021-06-01T00:00:00Z</published></entry></feed>")

        def transport(url: str) -> TransportResponse:
            if "crossref" in url:
                return TransportResponse(200, _crossref([]))
            return TransportResponse(200, atom)

        r = verify_online(_ref(), transport, min_interval=0)
        assert r.status == EXISTS and r.provider == "arxiv"

    def test_transport_error_is_unverified(self):
        def transport(url: str) -> TransportResponse:
            raise ConnectionError("网络断了")

        r = verify_online(_ref(), transport, min_interval=0)
        assert r.status == UNVERIFIED and "Crossref 查询失败" in r.detail

    def test_http_error_recorded_honestly(self):
        def transport(url: str) -> TransportResponse:
            return TransportResponse(500, "oops")

        r = verify_online(_ref(title="不在任何库里的标题"), transport, min_interval=0)
        assert r.status == NOT_FOUND
        assert "HTTP 500" in r.detail  # 失败细节如实带出

    def test_max_queries_budget(self):
        calls: list[str] = []

        def transport(url: str) -> TransportResponse:
            calls.append(url)
            return TransportResponse(200, _crossref([]))

        r = verify_online(_ref(title="查询预算会被用尽的标题"), transport,
                          max_queries=1, min_interval=0)
        assert len(calls) == 1  # 预算用尽，arXiv 不再查
        assert r.status == UNVERIFIED and "预算" in r.detail

    def test_rate_limit_interval(self):
        calls: list[float] = []

        def transport(url: str) -> TransportResponse:
            calls.append(time.monotonic())
            return TransportResponse(200, _crossref([]))

        verify_online(_ref(title="限速标题甲"), transport, max_queries=2, min_interval=0.05)
        assert len(calls) == 2
        assert calls[1] - calls[0] >= 0.05

    def test_unparsed_ref_skipped_honestly(self):
        def transport(url: str) -> TransportResponse:  # pragma: no cover - 不应被调用
            raise AssertionError("不应发起查询")

        r = verify_online(_ref(parsed=False), transport, min_interval=0)
        assert r.status == UNVERIFIED and "未解析出标题" in r.detail


class TestTransportUrlShape:
    def test_url_is_properly_encoded(self):
        seen: list[str] = []

        def transport(url: str) -> TransportResponse:
            seen.append(url)
            return TransportResponse(200, _crossref([]))

        verify_online(_ref(title="汉 字 标题"), transport, min_interval=0)
        q = urllib.parse.parse_qs(urllib.parse.urlparse(seen[0]).query)
        assert q["query.bibliographic"] == ["汉 字 标题"]
        assert int(q["rows"][0]) == 3


class TestIter2Hardening:
    """ROADMAP iter2：礼仪 UA/mailto、共享缓存、429/5xx 退避重试、注册机构级诚实说明。"""

    def test_user_agent_with_contact_env(self, monkeypatch):
        from gewita.existence import UA_BASE, user_agent
        monkeypatch.delenv("YINZHENG_CONTACT", raising=False)
        assert user_agent() == UA_BASE
        monkeypatch.setenv("YINZHENG_CONTACT", "audit@example.org")
        assert user_agent() == f"{UA_BASE} mailto:audit@example.org"

    def test_crossref_url_carries_mailto_param(self, monkeypatch):
        urls: list[str] = []

        def transport(url: str) -> TransportResponse:
            urls.append(url)
            return TransportResponse(200, _crossref([_item()]))

        monkeypatch.setenv("YINZHENG_CONTACT", "audit@example.org")
        r = verify_online(_ref(), transport, min_interval=0)
        assert r.status == EXISTS
        assert any("mailto=audit%40example.org" in u for u in urls), urls

    def test_retry_on_429_then_success(self, monkeypatch):
        monkeypatch.delenv("YINZHENG_CONTACT", raising=False)
        calls: list[int] = []
        body = _crossref([_item()])

        def transport(url: str) -> TransportResponse:
            calls.append(1)
            if len(calls) <= 2:
                return TransportResponse(429, "slow down")
            return TransportResponse(200, body)

        from gewita.existence import QueryBudget
        budget = QueryBudget(min_interval=0, max_queries=4, backoff_base=0.01)
        r = verify_online(_ref(), transport, _budget=budget)
        assert r.status == EXISTS
        assert len(calls) == 3, "429 两次后第三次成功，共 3 次尝试"

    def test_retry_respects_retry_after_cap(self, monkeypatch):
        monkeypatch.delenv("YINZHENG_CONTACT", raising=False)
        import time as _time
        calls: list[TransportResponse | None] = []

        def transport(url: str) -> TransportResponse:
            calls.append(None)
            if len(calls) == 1:
                return TransportResponse(503, "busy", headers={"Retry-After": "9999"})
            return TransportResponse(200, _crossref([_item()]))

        from gewita.existence import QueryBudget
        budget = QueryBudget(min_interval=0, max_queries=4, retry_after_cap=0.01)
        t0 = _time.monotonic()
        r = verify_online(_ref(), transport, _budget=budget)
        elapsed = _time.monotonic() - t0
        assert r.status == EXISTS
        assert elapsed < 2.0, "Retry-After 必须 cap，不允许睡 9999 秒"

    def test_retry_exhausted_honest_note(self, monkeypatch):
        monkeypatch.delenv("YINZHENG_CONTACT", raising=False)

        def transport(url: str) -> TransportResponse:
            return TransportResponse(500, "oops")

        from gewita.existence import QueryBudget
        budget = QueryBudget(min_interval=0, max_queries=4, backoff_base=0.01)
        r = verify_online(_ref(title="重试也救不了的标题"), transport, _budget=budget)
        assert r.status == NOT_FOUND
        assert "Crossref HTTP 500" in r.detail

    def test_same_fingerprint_cached_across_entries(self, monkeypatch):
        monkeypatch.delenv("YINZHENG_CONTACT", raising=False)
        crossref_calls: list[str] = []

        def transport(url: str) -> TransportResponse:
            if "crossref" in url:
                crossref_calls.append(url)
                return TransportResponse(200, _crossref([_item()]))
            return TransportResponse(200, "<feed/>")

        from gewita.existence import QueryBudget
        budget = QueryBudget(min_interval=0, max_queries=8)
        r1 = verify_online(_ref(), transport, _budget=budget)
        r2 = verify_online(_ref(), transport, _budget=budget)
        assert r1.status == EXISTS and r2.status == EXISTS
        assert len(crossref_calls) == 1, "同指纹第二次必须走缓存"
        assert "同文档缓存命中" in r2.detail

    def test_different_year_not_cached(self, monkeypatch):
        monkeypatch.delenv("YINZHENG_CONTACT", raising=False)
        crossref_calls: list[str] = []

        def transport(url: str) -> TransportResponse:
            if "crossref" in url:
                crossref_calls.append(url)
                return TransportResponse(200, _crossref([_item()]))
            return TransportResponse(200, "<feed/>")

        from gewita.existence import QueryBudget
        budget = QueryBudget(min_interval=0, max_queries=8)
        verify_online(_ref(year=2021), transport, _budget=budget)
        verify_online(_ref(year=2022), transport, _budget=budget)
        assert len(crossref_calls) == 2, "年份参与缓存键：不同年份不共享缓存"

    def test_not_found_with_doi_carries_registrant_caveat(self, monkeypatch):
        monkeypatch.delenv("YINZHENG_CONTACT", raising=False)

        def transport(url: str) -> TransportResponse:
            if "crossref" in url:
                return TransportResponse(200, _crossref([]))
            return TransportResponse(200, "<feed/>")

        r = verify_online(_ref(title="查无此题的中文刊论文", doi="10.3969/issn.1000-0000.2021.01.001"),
                          transport, min_interval=0)
        assert r.status == NOT_FOUND
        assert "非 Crossref 注册机构" in r.detail
        assert "查不到≠造假" in r.detail

    def test_document_level_budget_shared(self, monkeypatch):
        """judge_document 级共享预算：3 条同题条目只出网 1 次 Crossref。"""
        monkeypatch.delenv("YINZHENG_CONTACT", raising=False)
        from gewita.verdict import judge_document

        crossref_calls: list[str] = []

        def transport(url: str) -> TransportResponse:
            if "crossref" in url:
                crossref_calls.append(url)
                return TransportResponse(200, _crossref([_item()]))
            return TransportResponse(200, "<feed/>")

        doc = (
            "正文引用[1]和[2]以及[3]。\n\n"
            "参考文献\n"
            "[1] 张三. 预训练语言模型研究综述[J]. 中文信息学报, 2021.\n"
            "[2] 张三. 预训练语言模型研究综述[J]. 中文信息学报, 2021.\n"
            "[3] 李四. 预训练语言模型研究综述[J]. 中文信息学报, 2021.\n"
        )
        report = judge_document(doc, transport=transport)
        assert len(crossref_calls) == 1, f"应只出网 1 次，实际 {len(crossref_calls)}"
        assert report is not None
