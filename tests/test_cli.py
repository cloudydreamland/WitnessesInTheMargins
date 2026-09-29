"""cli.py 冒烟测试（全部离线，不触发 --online/--verify 的真实网络）。"""

from __future__ import annotations

import json

import pytest

from gewita.bench import default_corpus_dir
from gewita.cli import main

SUSPICIOUS_EXIT = 1
INPUT_ERROR_EXIT = 2


@pytest.fixture()
def workspace(tmp_path):
    sources = tmp_path / "sources"
    sources.mkdir()
    (sources / "src1.txt").write_text(
        "向量数据库通过 ANN 索引将召回延迟控制在 10 毫秒以内。", encoding="utf-8")
    doc = tmp_path / "doc.txt"
    doc.write_text(
        "正文。向量数据库通过 ANN 索引将召回延迟控制在 10 毫秒以内[1]。\n"
        "参考文献\n[1] 李强. 向量数据库索引技术[J]. 计算机工程, 2023, 49(5): 88-96.\n",
        encoding="utf-8")
    return doc, sources, tmp_path


class TestCheck:
    def test_clean_exit_0(self, workspace, capsys):
        doc, sources, _ = workspace
        assert main(["check", str(doc), "--sources", str(sources)]) == 0
        out = capsys.readouterr().out
        assert "引用核验报告" in out and "离线模式" in out

    def test_suspicious_exit_1(self, workspace, capsys):
        _, sources, tmp_path = workspace
        bad = tmp_path / "bad.txt"
        bad.write_text("编号超界[9]。\n参考文献\n[1] 甲. 标题[J]. 学报, 2020.\n", encoding="utf-8")
        assert main(["check", str(bad), "--sources", str(sources)]) == SUSPICIOUS_EXIT

    def test_json_output(self, workspace, capsys):
        doc, sources, _ = workspace
        assert main(["check", str(doc), "--sources", str(sources), "--json"]) == 0
        data = json.loads(capsys.readouterr().out)
        assert data["doc_name"] == "doc"

    def test_missing_doc_exit_2(self, tmp_path):
        assert main(["check", str(tmp_path / "nope.txt"),
                     "--sources", str(tmp_path)]) == INPUT_ERROR_EXIT

    def test_missing_sources_exit_2(self, workspace):
        doc, _, tmp_path = workspace
        assert main(["check", str(doc), "--sources", str(tmp_path / "none")]) == INPUT_ERROR_EXIT


class TestRefs:
    def test_refs_list(self, tmp_path, capsys):
        f = tmp_path / "refs.txt"
        f.write_text("[1] 张三. 深度学习综述[J]. 学报, 2020.\n[2] 残卷无题名.\n", encoding="utf-8")
        assert main(["refs", str(f)]) == 0
        out = capsys.readouterr().out
        assert "共 2 条" in out and "解析覆盖率 50%" in out
        assert "<未解析出标题>" in out

    def test_refs_json(self, tmp_path, capsys):
        f = tmp_path / "refs.txt"
        f.write_text("[1] 张三. 标题[J]. 学报, 2020.\n", encoding="utf-8")
        assert main(["refs", str(f), "--json"]) == 0
        data = json.loads(capsys.readouterr().out)
        assert data["refs"][0]["title"] == "标题"

    def test_refs_missing_file_exit_2(self, tmp_path):
        assert main(["refs", str(tmp_path / "none.txt")]) == INPUT_ERROR_EXIT


class TestBenchAndStore:
    def test_bench_runs_offline(self, capsys):
        assert main(["bench"]) == 0
        out = capsys.readouterr().out
        assert "内置评测结果" in out
        assert "金标" in out

    def test_refstore_stats(self, tmp_path, capsys):
        from gewita.refs import Reference
        from gewita.refstore import RefStore
        path = tmp_path / "s.jsonl"
        RefStore(path).append(Reference(1, "[1] 甲. 题[J]. 学, 2020.", (0, 5),
                                        title="题", parsed=True), "EXISTS")
        assert main(["refstore", "stats", str(path)]) == 0
        assert "指纹总数：1" in capsys.readouterr().out

    def test_refstore_missing_exit_2(self, tmp_path):
        assert main(["refstore", "stats", str(tmp_path / "no.jsonl")]) == INPUT_ERROR_EXIT


def test_corpus_reachable_from_tests():
    """测试环境必须能找到内置语料（bench 与 docs 的地基）。"""
    corpus = default_corpus_dir()
    assert (corpus / "gold.json").is_file()
    assert len(list((corpus / "docs").glob("*.txt"))) == 8
