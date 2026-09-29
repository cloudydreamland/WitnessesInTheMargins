"""report.py 测试：Markdown/JSON 渲染、integrity score、异常清单。"""

from __future__ import annotations

import json

import pytest

from gewita.bench import make_mock_transport
from gewita.report import (
    CREDIT_ALIGN,
    CREDIT_EXIST,
    integrity_score,
    render_json,
    render_markdown,
    verdict_weight,
)
from gewita.verdict import judge_document

DOC = (
    "正文如下。向量数据库通过 ANN 索引将召回延迟控制在 10 毫秒以内[1]。"
    "敦煌壁画的颜料分析表明青金石曾经丝绸之路传入[2]。\n"
    "参考文献\n"
    "[1] 李强. 向量数据库索引技术[J]. 计算机工程, 2023, 49(5): 88-96.\n"
    "[2] 陈静. 向量检索系统实践[M]. 北京: 电子工业出版社, 2023.\n"
)
SOURCES = {"cn_rag": "向量数据库通过 ANN 索引将召回延迟控制在 10 毫秒以内。其余为背景。"}


def _report():
    return judge_document(DOC, SOURCES, transport=make_mock_transport(), doc_name="demo")


class TestScore:
    def test_weight_formula(self):
        assert verdict_weight("VERBATIM", "EXISTS") == 1.0
        assert verdict_weight("NEAR", "EXISTS") == pytest.approx(0.8)
        assert verdict_weight("PARAPHRASE", "SUSPECT") == pytest.approx(0.25)
        assert verdict_weight("NOT_FOUND", "NOT_FOUND") == 0.0
        assert verdict_weight("VERBATIM", "UNVERIFIED") == pytest.approx(0.9)

    def test_score_bounds_and_empty(self):
        assert integrity_score([]) == 1.0
        report = _report()
        score = integrity_score(report.verdicts)
        assert 0.0 <= score <= 1.0

    def test_score_manual_check(self):
        report = _report()
        ws = [verdict_weight(v.alignment_level, v.existence) for v in report.verdicts]
        assert integrity_score(report.verdicts) == pytest.approx(sum(ws) / len(ws))

    def test_credit_tables_documented(self):
        assert CREDIT_ALIGN["VERBATIM"] > CREDIT_ALIGN["NEAR"] > CREDIT_ALIGN["PARAPHRASE"]
        assert CREDIT_EXIST["UNVERIFIED"] == 0.9  # 证据不足不清零也不打满


class TestMarkdown:
    def test_contains_rows_and_honesty(self):
        md = render_markdown(_report())
        assert "| # | 句子摘录 |" in md
        assert "integrity score" in md
        assert "离线" in md or "在线核验结论" in md
        assert "PARAPHRASE 表示词面 bigram 重叠" in md
        assert "解析覆盖率" in md

    def test_anomaly_listed(self):
        report = _report()
        anomalies = [v for v in report.verdicts if v.suspicious]
        md = render_markdown(report)
        if anomalies:
            assert "异常清单" in md and "需要人工复核" in md

    def test_excerpt_truncated(self):
        report = judge_document("很长" * 40 + "[1]。\n参考文献\n[1] 甲. 标题[J]. 学报, 2020.\n",
                                {}, doc_name="t")
        md = render_markdown(report)
        assert "…" in md


class TestJson:
    def test_valid_json_with_fields(self):
        data = json.loads(render_json(_report()))
        assert data["tool"] == "gewita"
        assert data["doc_name"] == "demo"
        assert 0.0 <= data["integrity_score"] <= 1.0
        assert isinstance(data["verdicts"], list) and data["verdicts"]
        v = data["verdicts"][0]
        for key in ("ref_status", "existence", "alignment_level", "evidence", "message"):
            assert key in v

    def test_evidence_offsets_serialized(self):
        data = json.loads(render_json(_report()))
        evidences = [v["evidence"] for v in data["verdicts"] if v["evidence"]]
        assert evidences and len(evidences[0]) == 2
