"""existence.py — 参考文献存在性核验。

两级能力：

- **离线结构校验**（永远可用）：``doi_valid`` / ``arxiv_valid`` 只看形态是否合法；
  ``title_fingerprint`` 给出归一化标题的 sha1 指纹（refstore 的主键）。
- **在线核验**（可选，transport 可注入）：Crossref 优先、arXiv 兜底。
  归一化标题 bigram 包含度 ≥ 0.85 判 EXISTS；命中但年份差 > 1 或刊名对不上
  判 SUSPECT（附差异说明）；两边都没有判 NOT_FOUND。

**诚实原则**：

- ``transport=None``（默认）= 禁用在线，返回 ``UNVERIFIED``——离线模式
  **永不输出"造假"结论**，最多说"未在给定来源中找到/未核验"。
- transport 抛错或返回非 200 → ``UNVERIFIED``（网络失败 ≠ 文献不存在）。
- 内置限速（token bucket 式：相邻查询间隔 ≥ ``min_interval`` 秒）与
  ``max_queries`` 单次预算；``_budget`` 可跨调用共享。
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import time
import urllib.parse
import xml.etree.ElementTree as ET
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from .refs import Reference
from .text import build_index, normalize

#: 存在性裁决值
EXISTS = "EXISTS"
SUSPECT = "SUSPECT"
NOT_FOUND = "NOT_FOUND"
UNVERIFIED = "UNVERIFIED"
LOCAL_ONLY = "LOCAL_ONLY"

#: 归一化标题包含度阈值（判命中）
TITLE_CONTAINMENT = 0.85
#: 命中后刊名比对的最低包含度
VENUE_CONTAINMENT = 0.5

Transport = Callable[[str], "TransportResponse"]
UA_BASE = "gewita/0.1.0 (citation verifier; https://github.com/gewita)"

#: Crossref 礼仪池：请求带 mailto（UA 或查询参数）可获更稳的限流待遇。
#: 联系方式从环境变量 ``YINZHENG_CONTACT`` 读取（邮箱），未设置则不附加。
_RETRYABLE_STATUSES = frozenset({429, 500, 502, 503, 504})
QUERYABLE_STATUSES = _RETRYABLE_STATUSES  # 供 __all__ 导出的可重试状态集合


def user_agent() -> str:
    """带联系方式的礼仪 UA：设置 ``YINZHENG_CONTACT`` 时附加 mailto。"""
    contact = os.environ.get("YINZHENG_CONTACT", "").strip()
    return f"{UA_BASE} mailto:{contact}" if contact else UA_BASE


def crossref_mailto() -> str:
    """Crossref 官方推荐的礼貌池参数值（同一环境变量）。"""
    return os.environ.get("YINZHENG_CONTACT", "").strip()


@dataclass(frozen=True)
class TransportResponse:
    """transport 的返回：HTTP 状态码 + 响应体 +（可选）响应头。"""

    status: int
    body: str
    headers: dict[str, str] | None = None


@dataclass(frozen=True)
class ExistenceResult:
    """存在性核验结果。``status`` 见模块常量；``detail`` 面向人的诚实说明。"""

    status: str
    detail: str
    matched_title: str = ""
    provider: str = ""  # crossref / arxiv / offline / refstore


def http_transport(url: str, timeout: float = 15.0) -> TransportResponse:
    """默认真实 transport（仅在用户显式启用 --online/--verify 时被使用）。

    测试绝不使用它——测试注入 mock transport。
    """
    import urllib.request

    req = urllib.request.Request(url, headers={"User-Agent": user_agent()})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        retry_after = resp.headers.get("Retry-After")
        headers = {"Retry-After": retry_after} if retry_after else None
        return TransportResponse(resp.status, resp.read().decode("utf-8", "replace"),
                                 headers=headers)


# ---------- 离线结构校验 ----------

DOI_FULL_RE = re.compile(r"10\.\d{4,9}/\S+")
ARXIV_FULL_RE = re.compile(r"(\d{4})\.(?:\d{4,5})(?:v\d+)?")


def doi_valid(doi: str) -> bool:
    """DOI 结构校验（离线）：``10.`` + 4-9 位注册方前缀 + 非空后缀。"""
    if not doi:
        return False
    m = DOI_FULL_RE.fullmatch(doi.strip())
    return m is not None and len(doi) > len("10.") + 1


def arxiv_valid(arxiv_id: str) -> bool:
    """arXiv 新式编号结构校验（离线）：``YYMM.NNNNN(vN)``。旧式编号不支持，如实。"""
    if not arxiv_id:
        return False
    m = ARXIV_FULL_RE.fullmatch(arxiv_id.strip())
    if m is None:
        return False
    yy, mm = int(m.group(1)[:2]), int(m.group(1)[2:])
    return 7 <= yy <= 35 and 1 <= mm <= 12


def title_fingerprint(title: str) -> str:
    """归一化标题 sha1 前 16 位（refstore 指纹）。"""
    return hashlib.sha1(normalize(title).encode("utf-8")).hexdigest()[:16]


def ref_fingerprint(ref: Reference) -> str:
    """条目指纹：有标题用标题；无标题回退原文（两者都无法区分时指纹同样诚实）。"""
    text = ref.title if ref.parsed else ref.raw
    return title_fingerprint(text)


def title_containment(a: str, b: str) -> float:
    """归一化标题包含度：共享 bigram / 较短方的 bigram 数（短方无 bigram 时回退字符集）。"""
    na, nb = normalize(a), normalize(b)
    if not na or not nb:
        return 0.0
    if len(na) < 2 or len(nb) < 2:
        sa, sb = set(na), set(nb)
        return len(sa & sb) / max(1, min(len(sa), len(sb)))
    ba = {na[i : i + 2] for i in range(len(na) - 1)}
    bb = {nb[i : i + 2] for i in range(len(nb) - 1)}
    return len(ba & bb) / max(1, min(len(ba), len(bb)))


# ---------- 在线核验 ----------


class QueryBudget:
    """文档级共享的限速、预算、重试与缓存状态。

    - ``acquire``：预算内则等待限速窗口并占坑；预算用尽返回 False。
    - ``cache``：同指纹（标题+年份+刊名）的在线查询结果在文档内复用，
      不重复出网（``verify_online`` 读写）。
    - ``backoff_base``/``max_retries``：429/5xx 指数退避重试参数
      （``backoff_base`` 调小仅供测试）。
    """

    def __init__(
        self,
        min_interval: float,
        max_queries: int,
        *,
        backoff_base: float = 0.5,
        max_retries: int = 2,
        retry_after_cap: float = 10.0,
    ) -> None:
        self.min_interval = min_interval
        self.max_queries = max_queries
        self.used = 0
        self._last = 0.0
        self.backoff_base = backoff_base
        self.max_retries = max_retries
        self.retry_after_cap = retry_after_cap
        self.cache: dict[str, ExistenceResult] = {}

    def acquire(self) -> bool:
        """预算内则等待限速窗口并占坑；预算用尽返回 False。"""
        if self.used >= self.max_queries:
            return False
        wait = self.min_interval - (time.monotonic() - self._last)
        if wait > 0:
            # Add a small margin for timer granularity (notably Windows), so
            # the observed interval does not undershoot the configured limit.
            time.sleep(wait + min(0.01, max(0.005, self.min_interval * 0.01)))
        self._last = time.monotonic()
        self.used += 1
        return True


#: 旧名别名（历史调用方/测试兼容）
_Budget = QueryBudget


def _cache_key(ref: Reference) -> str:
    """缓存键：标题指纹 + 年份 + 刊名（三者共同决定 SUSPECT 判定，缺一不可）。"""
    return "|".join((
        title_fingerprint(ref.title),
        str(ref.year or ""),
        normalize(ref.venue or ""),
    ))


def _crossref_match(ref: Reference, resp: TransportResponse) -> ExistenceResult | None:
    try:
        items = json.loads(resp.body).get("message", {}).get("items", [])
    except (json.JSONDecodeError, AttributeError):
        return ExistenceResult(UNVERIFIED, "Crossref 返回无法解析为 JSON", provider="crossref")
    ref_title = ref.title
    best: tuple[float, dict[str, Any]] | None = None
    for item in items:
        titles = item.get("title") or [""]
        cr_title = titles[0] if titles else ""
        cont = title_containment(ref_title, cr_title)
        if best is None or cont > best[0]:
            best = (cont, item)
    if best is None or best[0] < TITLE_CONTAINMENT:
        return None
    cont, item = best
    cr_title = (item.get("title") or [""])[0]
    issued = item.get("issued", {}).get("date-parts", [[None]])
    cr_year = issued[0][0] if issued and issued[0] else None
    container = item.get("container-title") or [""]
    cr_venue = container[0] if container else ""
    problems: list[str] = []
    if ref.year and cr_year and abs(int(ref.year) - int(cr_year)) > 1:
        problems.append(f"年份不符：条目标注 {ref.year}，Crossref 记录 {cr_year}")
    if ref.venue and cr_venue and title_containment(ref.venue, cr_venue) < VENUE_CONTAINMENT:
        problems.append(f"刊名不符：条目标注「{ref.venue}」，Crossref 记录「{cr_venue}」")
    if problems:
        return ExistenceResult(SUSPECT, "；".join(problems), matched_title=cr_title, provider="crossref")
    return ExistenceResult(EXISTS, f"Crossref 命中（包含度 {cont:.2f}）", matched_title=cr_title,
                           provider="crossref")


def _arxiv_match(ref: Reference, resp: TransportResponse) -> ExistenceResult | None:
    try:
        root = ET.fromstring(resp.body)
    except ET.ParseError:
        return ExistenceResult(UNVERIFIED, "arXiv 返回无法解析为 XML", provider="arxiv")
    ns = "{http://www.w3.org/2005/Atom}"
    for entry in root.findall(f"{ns}entry"):
        title_el = entry.find(f"{ns}title")
        ax_title = (title_el.text or "").strip() if title_el is not None else ""
        if title_containment(ref.title, ax_title) >= TITLE_CONTAINMENT:
            year = None
            pub = entry.find(f"{ns}published")
            if pub is not None and pub.text:
                year = int(pub.text[:4])
            problems = []
            if ref.year and year and abs(ref.year - year) > 1:
                problems.append(f"年份不符：条目标注 {ref.year}，arXiv 记录 {year}")
            if problems:
                return ExistenceResult(SUSPECT, "；".join(problems), matched_title=ax_title,
                                       provider="arxiv")
            return ExistenceResult(EXISTS, "arXiv 命中", matched_title=ax_title, provider="arxiv")
    return None


def _query(transport: Transport, url: str, budget: QueryBudget) -> TransportResponse | None:
    """预算内出网一次；429/5xx 按 Retry-After 或指数退避重试。

    重试不重复消耗预算（一次逻辑查询），但尊重限速与重试上限。
    """
    if not budget.acquire():
        return None
    resp: TransportResponse | None = None
    for attempt in range(budget.max_retries + 1):
        resp = transport(url)
        if resp.status not in _RETRYABLE_STATUSES or attempt >= budget.max_retries:
            return resp
        ra: float | None = None
        if resp.headers and resp.headers.get("Retry-After"):
            try:
                ra = min(float(resp.headers["Retry-After"]), budget.retry_after_cap)
            except ValueError:
                ra = None
        time.sleep(ra if ra is not None else budget.backoff_base * (2**attempt))
    return resp


def verify_online(
    ref: Reference,
    transport: Transport | None = None,
    max_queries: int = 4,
    min_interval: float = 1.0,
    _budget: QueryBudget | None = None,
) -> ExistenceResult:
    """核验一条参考文献是否真实存在（Crossref 优先，arXiv 兜底）。

    ``transport=None``（默认）= 禁用在线：返回 UNVERIFIED，绝不臆断。
    ``_budget`` 供文档级调用共享限速、预算、重试与同指纹缓存。
    """
    if transport is None:
        return ExistenceResult(UNVERIFIED, "在线核验未启用（transport=None）；离线模式不判存在性",
                               provider="offline")
    if not ref.parsed or not ref.title:
        return ExistenceResult(UNVERIFIED, "条目未解析出标题，无法发起在线核验", provider="offline")
    budget = _budget or QueryBudget(min_interval, max_queries)
    key = _cache_key(ref)
    if key in budget.cache:
        hit = budget.cache[key]
        return ExistenceResult(hit.status, hit.detail + "；同文档缓存命中",
                               matched_title=hit.matched_title, provider=hit.provider)
    # 1) Crossref 书目查询（礼仪池：环境变量 YINZHENG_CONTACT 转 mailto 参数）
    q = urllib.parse.quote(ref.title)
    contact = crossref_mailto()
    mailto = f"&mailto={urllib.parse.quote(contact)}" if contact else ""
    crossref_note = ""
    try:
        resp = _query(transport,
                      f"https://api.crossref.org/works?query.bibliographic={q}&rows=3{mailto}",
                      budget)
    except Exception as exc:  # noqa: BLE001 - transport 是外部注入的任意可调用
        return ExistenceResult(UNVERIFIED, f"Crossref 查询失败：{exc!r}", provider="crossref")
    if resp is None:
        return ExistenceResult(UNVERIFIED, "查询预算用尽，未完成核验", provider="crossref")
    if resp.status == 200:
        matched = _crossref_match(ref, resp)
        if matched is not None and matched.status in (EXISTS, SUSPECT):
            budget.cache[key] = matched
            return matched
    else:
        crossref_note = f"（Crossref HTTP {resp.status}）"
    # 2) arXiv 兜底
    try:
        resp = _query(transport,
                      f"http://export.arxiv.org/api/query?search_query=ti:%22{q}%22&max_results=3",
                      budget)
    except Exception as exc:  # noqa: BLE001
        return ExistenceResult(UNVERIFIED, f"arXiv 查询失败：{exc!r}", provider="arxiv")
    if resp is None:
        return ExistenceResult(UNVERIFIED, "查询预算用尽，未完成核验", provider="arxiv")
    if resp.status == 200:
        matched_ax = _arxiv_match(ref, resp)
        if matched_ax is not None and matched_ax.status in (EXISTS, SUSPECT):
            budget.cache[key] = matched_ax
            return matched_ax
    note = "Crossref 与 arXiv 均未找到相近标题" + crossref_note
    if ref.doi and doi_valid(ref.doi):
        note += (f"；注意：条目带 DOI（{ref.doi}）。大量中文 DOI 注册于 ISTIC/CNKI 等"
                 "非 Crossref 注册机构，Crossref 查不到≠造假；注册机构级核验不在本工具能力内，"
                 "本结果仅供参考")
    result = ExistenceResult(NOT_FOUND, note, provider="crossref+arxiv")
    budget.cache[key] = result
    return result


def structure_notes(ref: Reference) -> list[str]:
    """离线即可得出的结构观察（措辞克制：只说结构，不说造假）。"""
    notes: list[str] = []
    if ref.doi and not doi_valid(ref.doi):
        notes.append(f"DOI「{ref.doi}」结构不合法（应为 10.<4-9位注册方>/<后缀>）")
    if ref.arxiv_id and not arxiv_valid(ref.arxiv_id):
        notes.append(f"arXiv 编号「{ref.arxiv_id}」不符合新式 YYMM.NNNNN 格式")
    return notes


__all__ = [
    "EXISTS",
    "LOCAL_ONLY",
    "NOT_FOUND",
    "QUERYABLE_STATUSES",
    "SUSPECT",
    "UA_BASE",
    "UNVERIFIED",
    "ExistenceResult",
    "QueryBudget",
    "Transport",
    "TransportResponse",
    "arxiv_valid",
    "build_index",
    "crossref_mailto",
    "doi_valid",
    "http_transport",
    "ref_fingerprint",
    "structure_notes",
    "title_containment",
    "title_fingerprint",
    "user_agent",
    "verify_online",
]
