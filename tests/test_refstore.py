"""refstore.py 测试：追加、去重、持久化、统计、UTF-8。"""

from __future__ import annotations

from gewita.refs import Reference
from gewita.refstore import RefStore


def _ref(title="预训练语言模型研究综述", year=2021, doi="10.1234/abc") -> Reference:
    return Reference(index=1, raw=f"[1] 作者. {title}[J]. 学报, {year}.", span=(0, 5),
                     title=title, year=year, doi=doi, parsed=True)


class TestRefStore:
    def test_append_and_check_roundtrip(self, tmp_path):
        store = RefStore(tmp_path / "r.jsonl")
        ref = _ref()
        assert store.check(ref) is None
        assert store.append(ref, "EXISTS") is True
        hit = store.check(ref)
        assert hit is not None
        assert hit.verdict == "EXISTS" and hit.year == 2021 and hit.doi == "10.1234/abc"
        assert hit.title_norm  # 中文标题归一化后非空

    def test_dedup_same_fingerprint(self, tmp_path):
        store = RefStore(tmp_path / "r.jsonl")
        assert store.append(_ref(), "EXISTS") is True
        assert store.append(_ref(), "NOT_FOUND") is False  # 同指纹不重复
        assert store.check(_ref()).verdict == "EXISTS"  # 保留首条

    def test_persists_across_reopen(self, tmp_path):
        path = tmp_path / "r.jsonl"
        RefStore(path).append(_ref(), "EXISTS")
        again = RefStore(path)
        assert again.stats()["total"] == 1
        assert again.check(_ref()).verdict == "EXISTS"

    def test_utf8_chinese_title(self, tmp_path):
        path = tmp_path / "r.jsonl"
        RefStore(path).append(_ref(title="中文标题：引用透明库"), "EXISTS")
        raw = path.read_text(encoding="utf-8")
        assert "中文标题" in raw  # ensure_ascii=False，文件本身可读

    def test_stats_by_verdict(self, tmp_path):
        store = RefStore(tmp_path / "r.jsonl")
        store.append(_ref(), "EXISTS")
        store.append(_ref(title="另一篇文献"), "NOT_FOUND")
        stats = store.stats()
        assert stats["total"] == 2
        assert stats["by_verdict"] == {"EXISTS": 1, "NOT_FOUND": 1}

    def test_unparsed_ref_uses_raw_fingerprint(self, tmp_path):
        store = RefStore(tmp_path / "r.jsonl")
        ref = Reference(index=1, raw="[1] 残卷。", span=(0, 5), parsed=False)
        assert store.append(ref, "UNVERIFIED") is True
        assert store.check(ref) is not None

    def test_corrupt_line_skipped(self, tmp_path):
        path = tmp_path / "r.jsonl"
        path.write_text('{"fingerprint": "ab12", "title_norm": "x", "verdict": "EXISTS", "ts": 1}\n'
                        "不是 json 的坏行\n", encoding="utf-8")
        store = RefStore(path)
        assert store.stats()["total"] == 1  # 坏行跳过不炸
