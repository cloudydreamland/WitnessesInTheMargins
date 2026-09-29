# Witnesses in the Margins — Gewita

[English](README.md) · 简体中文

> 名字取自古英语 **gewita**——「证士、证人」。每一条引文，都该有自己的证人。
[![CI](https://github.com/cloudydreamland/WitnessesInTheMargins/actions/workflows/ci.yml/badge.svg)](.github/workflows/ci.yml)

**中文优先的引用验证标准件。GB/T 7714 参考文献解析、正文引用抽取、引文↔来源三级对齐裁决、文献存在性核验——把"引用可验证"做成 pip 标准件。**

[![Python](https://img.shields.io/badge/python-3.10%2B-blue)](pyproject.toml)
[![License: MIT](https://img.shields.io/badge/license-MIT-green)](LICENSE)
[![Tests](https://img.shields.io/badge/tests-181%20passed-brightgreen)](#开发与测试)

## 为什么需要它 / Why

LLM、RAG 与 AI 辅助写作的引用大规模不可信——这不是道德问题，是工程问题：

- **2025-05 白宫健康报告假引文事件**：报告引用的研究"不存在或结论相反"，Hacker News 相关讨论获 198 分热度——公文级引用无人核验
- **2026-04 "11 万篇论文含假引文"**：批量生成的污染文献正在进入科学引用网络（学术圈自查已追不上生成速度）
- **Deloitte 澳洲公开报告编造引文**：向政府提交的报告含虚构学术引文与失效链接，被追讨 44 万澳元并公开道歉
- **2024–2025 律师假判例制裁潮**：多国法院对提交 ChatGPT 编造判例的律师罚款、立案、取消资格
- **工具侧空白**（arXiv 2026-07《HALLMARK》《What Current Tools Can and Cannot Do》结论）：现有引用验证工具**能力远低于需求**，且几乎全部面向英文与 APA——GB/T 7714（中国国标参考文献格式）没有像样的开源解析标准件；LongCite（522★）停更两年，只是训练数据集不是可安装的验证工具

国内团队现状：手抽检，或者干脆不查。`gewita`（Gewita）把这件事做成零依赖标准件：

- **三级对齐裁决**：VERBATIM（逐字命中，带原文精确偏移）/ NEAR（近逐字，归一化相似度 ≥0.85）/ PARAPHRASE（字符 bigram 包含度 ≥0.5）/ NOT_FOUND——每条引用给证据和偏移，不给玄学分数
- **偏移不变量**（招牌）：VERBATIM 结果保证 `source[start:end] == 引文原文`，fuzz 测试永久守护，证据可回贴原文
- **GB/T 7714 中文参考文献解析**：`[J]/[M]/[C]/[D]/[P]/[S]/[EB/OL]/[DB/OL]` 类型标识定位标题边界、中文作者顿号分隔、电子文献日期/链接字段
- **诚实原则**：离线模式**永不输出"造假"结论**，只说"未在给定来源中找到"；只有在线核验（Crossref/arXiv）或 refstore 历史裁决才能给 EXISTS/SUSPECT/NOT_FOUND
- **引用透明库 refstore**：本地追加式"已核验参考文献指纹库"（归一化标题 sha1 指纹 + 历史裁决），越用越强
- **零必装依赖**：核心纯标准库（difflib/json/hashlib/urllib 够用）；在线核验可注入 transport，测试绝不真联网
- **自带评测**：内置 8 篇微文档 + 35 条金标，指标真实跑出（见 [benchmarks/results.md](benchmarks/results.md)）

## 三级裁决模型

```
正文句子（含 [n] 标记）──┐
                        ├─► ① 对齐裁决（对来源语料）
sources/ 目录 ──────────┘         │
                        VERBATIM  原文精确偏移 source[start:end]==引文（归一化抹平全角/引号/空白）
                        NEAR      句粒度 SequenceMatcher ratio≥0.85（证据=句窗）
                        PARAPHRASE 字符 bigram 包含度≥0.5（词面重叠，≠语义等价）
                        NOT_FOUND 未在给定来源中找到（≠内容有误）
参考文献表 ──► ② 解析（GB/T 7714 / 编号体 / APA-lite，覆盖率如实报告）
                │
                ├─► ③ 存在性核验
                LOCAL_ONLY refstore 历史（离线可判）
                EXISTS     在线命中（标题包含度≥0.85 且年份/刊名不冲突）
                SUSPECT    命中但年份差>1 或刊名不符（附差异说明）
                NOT_FOUND  Crossref+arXiv 均未找到（仅在线模式）
                UNVERIFIED 未启用在线且无历史——诚实弃权，绝不推定造假
                │
                └─► ④ 合成裁决 + integrity score（credit_align × credit_exist 均值，权重写明）
```

## 安装 / Install

```bash
# 克隆仓库后，在项目根目录安装
python -m pip install .
# 发布到 PyPI 后可直接安装
python -m pip install gewita
```

## 快速开始 / Quickstart

```python
from gewita import judge_document, align_quote, parse_references, extract_citations

doc = open("报告.md", encoding="utf-8").read()

# 一次完整核验（离线；传入 transport=... 启用在线）

report = judge_document(doc, {"来源A": src_a_text, "来源B": src_b_text}, doc_name="报告")
print(render_markdown(report))   # Markdown 报告：逐条裁决 + integrity score + 异常清单

# 单独用各件

refs = parse_references(doc)          # 参考文献表 → list[Reference]
cites = extract_citations(doc, refs)  # 正文引用标记（[1] [1,2] [1-3] (Smith, 2020)）
a = align_quote("自注意力机制建模长距离依赖", src_a_text)
a.level, a.start, a.end               # 'VERBATIM', 23, 35 —— src_a_text[23:35] 就是引文
```

命令行：

```bash
gewita check 报告.md --sources sources/          # 离线核验，退出码 0/1/2
gewita check 报告.md --sources sources/ --online # 启用 Crossref/arXiv 在线核验（真实联网）
gewita check 报告.md --sources sources/ --json   # JSON 报告
gewita refs 参考文献.txt                          # 解析参考文献表（覆盖率如实报告）
gewita refs 参考文献.txt --verify                 # 逐条在线核验（真实联网，内置限速）
gewita bench                                     # 内置评测（离线，mock transport）
gewita refstore stats refstore.jsonl             # 引用透明库统计
```

退出码：`0` 干净 / `1` 有可疑引用 / `2` 输入错误。

## 偏移不变量（招牌）

`align_quote` 的 VERBATIM 结果保证证据可回贴原文：

```python
a = align_quote(quote, source)
assert a.level == "VERBATIM"
assert source[a.start:a.end] == quote          # 引文与来源逐字一致时
assert normalize(source[a.start:a.end]) == normalize(quote)  # 全角/引号/空白变体抹平时
```

实现是**归一化位置→原始位置 的索引映射**（`text.build_index`）：归一化串上 `str.find` 命中后，把区间两端映射回原文码点偏移。fuzz 测试（随机来源 × 随机逐字注入引文 × 多 seed）永久守护这条不变量。切句同理：`"".join(s.text for s in split_sentences(text)) == text`。

## 诚实边界（读这个再用）

1. **离线不判造假**。`transport=None` 时 existence 只会是 `UNVERIFIED` / `LOCAL_ONLY`。对齐 `NOT_FOUND` 只表示"未在给定来源中找到"——来源给少了责任在使用者，报告会如实写"证据不足，不等于内容有误"。
2. **GB/T 7714 是启发式解析**。内置语料实测覆盖率 94.3%（33/35，2 条故意无法解析的残卷条目如实标注 `parsed=False`）。解析不出的条目保留原文，绝不编造字段；更全的语料与 F1 报告在 ROADMAP iter3。
3. **PARAPHRASE ≠ 语义等价**，只是字符 bigram 词面重叠 ≥0.5。语义相反但词面重叠的改写也会判 PARAPHRASE（测试里有这条断言）；支持性判断留给 ROADMAP iter4 的可插拔 LLM judge。
4. **NEAR/PARAPHRASE 的证据 span 是句级窗**，不是字符级精确区间（VERBATIM 才有精确区间）。
5. **在线核验礼仪**：默认关闭；开启后内置限速（相邻查询 ≥1s）与单次预算（`max_queries`），网络失败如实记为 `UNVERIFIED` 而不是 NOT_FOUND。
6. **内置评测是合成语料**，数字（对齐四级 F1=1.000）是格式级能力上限，不外推到真实脏数据。

## 与现有方案的关系（如实）

| 项目 | 定位 | 与 gewita 的关系 |
|---|---|---|
| verbatim-rag（204★，ACL 2025，活跃） | 生成侧摘录式 RAG：检索→逐字摘录→带引用回答 | 关注"缩小生成面"产出处方式引用，不核验已有文档；官方自认"重复文本使偏移映射歧义"（我们同样面临，见 iter10）；互补关系源码级确认。源码级走读见 [docs/competitors.md](docs/competitors.md) |
| reverify（1,249★） | 二进制逆向声明验证器（模型提议、确定性工具裁决） | **不在本赛道**（域是 PE/ELF 逆向，非文献）；但其 claim 信息量加权（FActScore CORE）与三态裁决是方法论同源，前者已吸收为 iter9 |
| LongCite (522★) | 长引用训练数据集 | 停更两年（2024-09 起）；是数据不是可安装验证件；可作训练资源 |
| anystyle（1,292★，2011 老牌） | 参考文献解析（Ruby，Wapiti CRF） | **官方声明中文不兼容其方法**（"…aren't compatible with AnyStyle's approach: this includes Chinese, Japanese…"，默认语料中文 0 条）——GB/T 7714 解析层在其方法框架内不可被反超；其 gold 两级错误率报告法已被 iter3 吸收 |
| RefChecker（434★，2025-05 后休眠） | LLM 输出三元组幻觉核查（阿里，ACL 2024） | LLM+spacy+搜索引擎重依赖、片段级 localization；News 停在 2024-07。验证侧需求真实的先例，路线不同（模型驱动 vs 规则驱动、片段级 vs 字符偏移） |
| HALLMARK 等 2026 评测论文 | 指出现有工具不行 | 选题依据（见 GAP_PROOF.md），非竞品 |

- **在线查不到 ≠ 造假**。带 DOI 的条目在 Crossref 无命中时，报告会明确说明：大量中文 DOI 注册于 ISTIC/CNKI 等非 Crossref 注册机构，注册机构级核验不在本工具能力内（详见 docs/competitors.md 对 anystyle 的同类分析）。

## 开发与测试

```bash
python -m pytest          # 172 项测试，全离线（在线核验注入 mock transport）
python -m ruff check .    # 0 error
python -m gewita bench  # 内置评测，结果回填 benchmarks/results.md
```

English quickstart: `pip install gewita`; then
`judge_document(doc_text, {"source": text})` returns a report whose verdicts carry
`ref_status` (PARSED/NO_REF_LIST/NOT_IN_LIST), `existence`
(LOCAL_ONLY/EXISTS/SUSPECT/NOT_FOUND/UNVERIFIED — offline never claims fabrication)
and `alignment_level` (VERBATIM/NEAR/PARAPHRASE/NOT_FOUND) with exact source offsets
for VERBATIM hits. GB/T 7714 (Chinese national standard) parsing included; APA-lite
supported. CLI: `gewita check doc.md --sources dir/`, `gewita refs refs.txt`,
`gewita bench`. Exit codes: 0 clean, 1 suspicious, 2 input error. See this README
for the honesty boundary — the offline mode never claims a reference is fabricated.

## 许可

MIT。见 [LICENSE](LICENSE)。
