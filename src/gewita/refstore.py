"""refstore.py — 引用透明库：本地追加式"已核验参考文献指纹库"。

JSONL 每行一条::

    {"fingerprint": "...", "title_norm": "...", "year": 2020,
     "doi": "10.xxxx/yyy", "verdict": "EXISTS", "ts": 1769...

- ``check(ref)``：按指纹查历史裁决（命中即可离线给出 LOCAL_ONLY）；
- ``append(ref, verdict)``：追加记录，同指纹不重复（去重）；
- ``stats()``：库内统计。

越用越强：每次在线核验落库，下次同一文献离线即可复用结论，
为未来的跨项目共享格式（见 ROADMAP iter5）铺路。所有写入显式 UTF-8。
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass
from pathlib import Path

from .existence import ref_fingerprint
from .refs import Reference
from .text import normalize


@dataclass
class StoreRecord:
    """库内一条记录。"""

    fingerprint: str
    title_norm: str
    year: int | None
    doi: str
    verdict: str
    ts: float

    def as_dict(self) -> dict:
        return {
            "fingerprint": self.fingerprint,
            "title_norm": self.title_norm,
            "year": self.year,
            "doi": self.doi,
            "verdict": self.verdict,
            "ts": self.ts,
        }


class RefStore:
    """追加式 JSONL 指纹库。线程不安全（单机单进程用途，如实说明）。"""

    def __init__(self, path: str | Path):
        self.path = Path(path)
        self._records: dict[str, StoreRecord] = {}
        self._load()

    def _load(self) -> None:
        if not self.path.exists():
            return
        with open(self.path, encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    data = json.loads(line)
                    rec = StoreRecord(
                        fingerprint=data["fingerprint"],
                        title_norm=data.get("title_norm", ""),
                        year=data.get("year"),
                        doi=data.get("doi", ""),
                        verdict=data.get("verdict", "UNVERIFIED"),
                        ts=data.get("ts", 0.0),
                    )
                except (json.JSONDecodeError, KeyError):
                    continue  # 坏行跳过，不炸整个库
                self._records.setdefault(rec.fingerprint, rec)

    def check(self, ref: Reference) -> StoreRecord | None:
        """按指纹查历史裁决；无记录返回 None。"""
        return self._records.get(ref_fingerprint(ref))

    def append(self, ref: Reference, verdict: str, ts: float | None = None) -> bool:
        """追加一条记录。同指纹已存在时不重复写入，返回 False；新写入返回 True。"""
        fingerprint = ref_fingerprint(ref)
        if fingerprint in self._records:
            return False
        record = StoreRecord(
            fingerprint=fingerprint,
            title_norm=normalize(ref.title if ref.parsed else ref.raw),
            year=ref.year,
            doi=ref.doi,
            verdict=verdict,
            ts=time.time() if ts is None else ts,
        )
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.path, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(record.as_dict(), ensure_ascii=False) + "\n")
        self._records[fingerprint] = record
        return True

    def stats(self) -> dict:
        """库内统计：总数、按裁决分布。"""
        by_verdict: dict[str, int] = {}
        for rec in self._records.values():
            by_verdict[rec.verdict] = by_verdict.get(rec.verdict, 0) + 1
        return {"total": len(self._records), "by_verdict": by_verdict, "path": str(self.path)}
