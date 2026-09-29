# WORKLOG — 工作日志

> 每轮迭代在文末追加一节：时间戳、完成内容、测试结果、问题、下一步。

## iter0 — 2026-09-28 凌晨（主会话完成）

**完成：**
- 环境确认：Windows + Git Bash + Python 3.13 + pytest 9.1.1 + ruff 0.16.8；项目路径 `E:\n_projects\gewita`，src 布局，风格对齐 mianju/qiegao（只读参考）。
- 选题取证：GAP_PROOF.md 基于夜间四路调研（白宫假引文 HN 198 分、2026-04 11 万篇污染论文、Deloitte 澳洲 44 万澳元追款、律师假判例制裁潮；arXiv 2026-07《HALLMARK》《What Current Tools Can and Cannot Do》；LongCite 522★ 停更两年、anystyle/verbatim-rag/RefChecker 均不覆盖中文国标）。数据实抓日 2026-09-28。
- 包实现（src/gewita/，11 模块 + py.typed，零必装依赖）：
  - `text.py`：normalize（全角→半角、casefold、统一引号、去空白变体）+ build_index（归一化位置→原始位置映射，偏移不变量的地基）+ split_sentences（。！？；…与 .!?；ASCII 句点的小数/版本/域名/缩写抑制；换行硬边界；拼接不变量）
  - `refs.py`：GB/T 7714（类型标识 [J]/[M]/[C]/[D]/[P]/[S]/[EB/OL]/[DB/OL] 定位标题边界）、无类型码编号体、APA-lite；DOI/arXiv/URL/年份抽取独立于形态；覆盖率如实报告；纯条目文件 assume_section
  - `extract.py`：[1]/[1,2]/[1-3] 展开（区间上限 50 防爆炸）/连续标记/作者-年份式（尽力对应条目，对应不上如实备注）；标记按偏移从句文本中切除，得到干净"引文主张"；参考文献表区自动排除
  - `align.py`：四级裁决。VERBATIM 走归一化子串+索引映射还原原始偏移（构造期自证不变量）；NEAR 句粒度 SequenceMatcher ratio≥0.85（matching blocks 收紧证据 span，引文较长时相邻句合并）；PARAPHRASE bigram 包含度≥0.5（倒排索引筛候选）；全部 NOT_FOUND 语义="未找到"而非"有误"
  - `existence.py`：doi_valid/arxiv_valid 结构校验；title_fingerprint（sha1 前 16）；verify_online（Crossref 优先 arXiv 兜底，标题包含度≥0.85 判 EXISTS，年份差>1 或刊名不符判 SUSPECT 附差异说明；限速 + max_queries 预算；transport=None 永不判存在性；网络失败如实记 UNVERIFIED）
  - `verdict.py`：判定矩阵写进 docstring；ref_status（PARSED/NO_REF_LIST/NOT_IN_LIST）× existence × alignment 合成；refstore 命中升级 LOCAL_ONLY；suspicious 只认"明确冲突"
  - `refstore.py`：追加式 JSONL 指纹库（同指纹去重、坏行跳过、UTF-8 可读）
  - `report.py`：Markdown/JSON 报告；integrity score = credit_align × credit_exist 均值（权重表写明：UNVERIFIED 0.9——证据不足不清零也不打满）；报告文案区分"证据不足"与"发现问题"
  - `bench.py` + benchmarks/corpus/：8 篇微文档（5 中文：学术摘要体/公众号体/综述体/法律意见书体/技术报告体；3 英文）+ 8 篇来源 + 35 条金标；mock transport（Crossref JSON + arXiv Atom 注册库）离线可复现；指标：对齐四级 P/R/F1、fabricated P/R/F1、解析覆盖率
  - `cli.py`：check/refs/bench/refstore stats 四命令；退出码 0 干净 / 1 可疑 / 2 输入错误；--online/--verify 才真联网
- 测试：**172 项全绿**（含：偏移不变量 fuzz 10 seed × 20 例——随机来源 × 逐字注入引文必须精确找回；切句拼接不变量 fuzz 5 seed；离线永不判造假参数化断言；限速/预算/transport 异常全路径；refstore 去重与持久化；CLI 退出码）；ruff 0 error。

**真实调试记录（评测框架当场抓住的问题）：**
- **ASCII 句点漏出终结符集合**：`_TERMINATORS` 写漏 `.`，英文文档整篇成一句，导致参考文献区排除失效、NEAR/VERBATIM 大面积误判——一颗雷炸出三层问题，单测+bench 双向夹出。
- **无终结符标题行与正文首句粘连**：增加"换行是硬边界"规则后恢复。
- **NEAR 对 ≤600 字大窗直接算 ratio 被窗长稀释**：近乎逐字的引文 ratio 掉到 0.3——改为句粒度候选（含相邻句合并），与规格设想的粗窗不同，如实记录这一偏离及原因。
- **PARAPHRASE 在窗粒度被英文常见字对（the/tion）抬出误报**：包含度改在句粒度计算，编造句全部回落 NOT_FOUND。
- **EB/OL 条目的刊名字段吃进日期与裸链接**：导致 6 个 SUSPECT 误报——剥掉 (发布日期)[引用日期] 前缀，剩余为 URL 时刊名诚实置空。
- refstore StoreRecord 属性访问、refs span 前导空白紧化等 5 处小修。

**最终快照（真实跑出，见 benchmarks/results.md）：**
- 对齐四级：VERBATIM/NEAR/PARAPHRASE/NOT_FOUND P=R=F1=1.000（micro 准确率 100.0%）
- fabricated 检测（mock transport 离线可复现）：P=R=F1=1.000；unparsable 检出 2/2
- 解析覆盖率 94.3%（33/35，2 条故意无法解析的残卷条目如实标注）
- 注：合成语料，格式级能力上限，不外推真实脏数据。

**诚实未完成项：**
- 在线核验未对真实 Crossref/arXiv 实测（本轮零真实联网），礼仪 UA/缓存/重试留给 iter2。
- GB/T 7714 语料仅 35 条，字段级 F1 报告留给 iter3。
- PARAPHRASE≠语义等价，LLM 语义裁决器留给 iter4。
- 英文 README 仅 quickstart 段，完整版留 iter8。

---

## iter1（2026-09-28 夜间自动迭代 第 2 轮）：竞品源码走读

### 完成清单

- `docs/competitors.md`：四家三维对照（标题边界策略/对齐算法/诚实度设计）+ 逐家走读 + 结论与风险更新 + 证据清单（星数与活跃度全部当日 GitHub API 实抓）。
- README「与现有方案的关系」表重写为源码级结论（anystyle 行加官方兼容性声明原文、新增 reverify 行、RefChecker 行补休眠证据）。
- ROADMAP 追加 iter9（integrity score 信息量加权）、iter10（多命中歧义披露）。

### 走读关键发现

1. **reverify 定位修正（本轮最重要）**：1,249★ 的 reverify 不是文献核查工具——它是二进制逆向工程声明验证器（PE/ELF 解析/反汇编/模拟，MCP server）。上一轮调研的"reverify 关闭幻觉核查窗口"结论对本项目不成立。方法论可抄两件：claim 信息量加权（FActScore CORE：复述/重复/自指权重 0）→ iter9；REFUTED 即非零退出的 CI 门禁（我们已有）。
2. **anystyle 官方弃权中文**：README 原文声明中文/日文/阿语等非空格分词语言"aren't compatible with AnyStyle's approach"（CRF 依赖空格分词特征，默认语料中文 0 条）。GB/T 7714 解析层在其方法框架内不可被反超——这是解析层合法性的最好证明。
3. **verbatim-rag（204★，ACL 2025）互补确认**：生成侧（缩小生成面）vs 我们验证侧；其官方"provenance guarantee, not truth guarantee"诚实表格与我们同源；其官方承认"重复文本使偏移映射歧义"→ 我们的 VERBATIM 返回首命中且无披露机制，是真实缺口 → iter10。
4. **RefChecker（434★）休眠**：News 停在 2024-07、push 停在 2025-05-16；LLM 中心路线维护成本的前车之鉴；验证侧需求真实性的先例。
5. **方法论背书**：三个不同域的项目（reverify 三态+证据回贴 / verbatim-rag 溯源≠真实 / anystyle gold 错误率）在诚实度设计上与我们收敛到同一做法。

### 三视角对抗评审记录

- **资深开发者**：本轮四家全是 README 级精读、未下钻函数级源码（github.com 页面 WebFetch 持续 ECONNRESET，走 raw.githubusercontent 降级）——结论强度必须标注，文档开头已加方法声明；reverify 的 claim weight 只读到 README 描述，实现 iter9 前应先读其源码中 weight 计算段（已写入 iter9 条目备注）。
- **资深项目经理**：anystyle 弃权中文是 README 营销的合法性弹药（"官方声明"比"我们实测它不行"硬得多），launch 时应把这句原文做成对比图；它 1,292★ 且长期慢维护，说明"解析器"单点形态天花板有限，必须绑定"解析+对齐+核验"整链价值。
- **公司老板**：四家排除后赛道确认空置，但 reverify 三周冲到 1,249★ 后 push 停滞（2026-09-07 起）——爆红工具的维护断档是常态，我们的夜间自动化迭代模式恰好是对冲；传播物优先级：iter6 HTML 高亮报告 > 规范文档。

### 上网调研发现

- 星数/活跃度全部当日实抓：reverify 1,249★（push 停在 09-07）、verbatim-rag 204★（活跃）、anystyle 1,292★（慢维护）、RefChecker 434★（休眠）。
- 未发现 2026-09 有任何"中文引用核验"新入场者。

### 诚实未完成项

- 四家均未逐行走读函数级源码（网络降级 + 时间盒）；iter9 实施前需补读 reverify 的 weight 计算实现。
- anystyle"中文 0 条语料"来自其 README 自述的 corpus 语言表，未下载其训练集独立复核。
- 本轮纯文档轮，无代码变更；pytest/ruff 作为门禁照跑。

---

## iter2（2026-09-28 夜间自动迭代 第 4 轮）：在线核验加固

### 完成清单

- **礼仪 UA / 礼貌池参数**：`user_agent()` 读环境变量 `YINZHENG_CONTACT` 附加 mailto；Crossref 查询 URL 同步带 `&mailto=`（官方礼貌池两种机制都实现，官方 README 原文取证 2026-09-28）。
- **文档级共享查询缓存**：`QueryBudget.cache` 以（标题指纹+年份+刊名）为键，同指纹不重复出网，命中详情标注"同文档缓存命中"；年份/刊名参与键，SUSPECT 判定不被缓存吞掉。
- **429/5xx 指数退避重试**：`_query` 对 429/500/502/503/504 重试（默认 2 次，backoff 0.5s 起步翻倍，测试可调），优先尊重 `Retry-After` 头（cap 10s 防呆）；重试不重复消耗查询预算；`TransportResponse` 加可选 headers（向后兼容，既有 mock 全部不受影响）。
- **注册机构级诚实说明**：带 DOI 条目 Crossref/arXiv 均未命中时，NOT_FOUND 详情明确"中文 DOI 多注册于 ISTIC/CNKI 等非 Crossref 机构，查不到≠造假"——防对中文文献误伤。
- **接线**：`judge_document` 自动创建文档级预算（新增 `budget` 参数可注入）；CLI `refs --verify` 共享预算；README 诚实边界补"在线查不到≠造假"。
- 新测试 9 项（181 passed 全绿，ruff 0 error）。

### 门禁事件（诚实记录）

- 首次跑全套 160s（原 26s）——**本轮改动让限速首次真正生效**：文档级预算的 min_interval=1.0 作用于 bench 的 mock transport（35 条查询各睡 1s；旧 per-call 预算因 `_last=0` 初始化缺陷首查从不满速）。修复：`run_bench` 显式传 `min_interval=0` 预算（mock 不需要礼貌），`judge_document` 支持注入。10s 恢复。教训：性能回归要用 `--durations` 定位而不是猜。

### 三视角对抗评审记录

- **资深开发者**：缓存键必须含年份与刊名（只按标题指纹会把年份不符的 SUSPECT 缓存成 EXISTS）——已实现；TransportResponse 加字段保持 frozen+默认值，旧 mock 零改动；`verify_online` 独立调用仍每次新建预算（无跨调用缓存）——使用模式需文档化 → iter11。
- **资深项目经理**：Crossref 礼貌池=免费限流配额，`YINZHENG_CONTACT` 未设置时静默退化（不报错）但 launch 文案必须提醒配置；"中文 DOI 查不到≠造假"是与所有英文中心竞品的差异化卖点，已写进 README 诚实边界。
- **公司老板**：iter2 之后在线链路对真实 Crossref 的成功率仍是未知数（家规：测试绝不真实联网）——需要一个用户手动的冒烟命令把"真实世界到底行不行"变成可观测事实 → iter12（唯一允许出网的命令，--yes 确认）。

### 诚实未完成项

- 未对真实 Crossref/arXiv 出网验证（家规约束），etiquette 取证来自官方 README 原文，实现是否符合礼貌池生效条件（mailto 可达邮箱）待 iter12 冒烟确认。
- arXiv 兜底查询未实现重试分API差异（其 5xx 语义与 Crossref 不同），当前同等对待，如实标注。
- `judge_document` 未暴露 min_interval/max_queries 参数（预算对象可直接注入替代），API 面保持最小。
