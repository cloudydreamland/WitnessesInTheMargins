# 竞品源码走读（ROADMAP iter1 交付物）

> 走读日期：2026-09-28 凌晨。方法：四家 README 原文全文精读（raw.githubusercontent 实抓，含 anystyle 语言兼容性声明、RefChecker 流水线说明）+ GitHub API 星数/活跃度实抓。**本轮未逐行走读四家的函数级源码**（夜间网络对 github.com 页面渲染不稳定，降级为 README 原文级）——结论强度据此如实标注，后续轮次可下钻。星数为当日实抓。

## 一、三维对照（标题边界策略 / 对齐算法 / 诚实度设计）

| 项目 | 定位 | 标题边界策略（解析层） | 对齐算法 | 诚实度设计 |
|---|---|---|---|---|
| reverify（1,249★） | **二进制逆向声明验证器**（不是文献工具！PE/ELF/Mach-O 解析、反汇编、模拟执行；MCP server） | 无参考文献解析；claim 是 JSON 结构（offset/mnemonics 等） | 对字节：`bytes_at`/`pattern_present`/`emulate_result` 等 15 种 claim kind，证据回贴真实字节 | `VERIFIED/REFUTED/INCONCLUSIVE` 三态 + claim `weight` 信息量加权（FActScore CORE 精化：复述事实清单、重复、自指的 claim 权重为 0）+ "verifier 由独立 judge 检查" |
| verbatim-rag（204★，活跃，ACL 2025） | **生成侧**摘录式 RAG：检索→逐字摘录→带引用回答 | 不解析参考文献表；处理文档块（docling+chonkie） | span 抽取器（150M 微调模型，Word-F1 53.6）+ rapidfuzz 模糊定位；"重复文本使偏移映射歧义"被官方承认 | 官方"what verbatim means"表：**provenance guarantee, not truth guarantee**（溯源保证≠真实性保证），上下文模板生成框外文字明确标出保证范围外 |
| anystyle（1,292★，2011 年老牌） | 参考文献解析器（Ruby，Wapiti CRF 机器学习） | **序列标注切字段**（author/title/date…），corpus 965 英/54 法/26 德/**中文 0 条** | 无对齐（它只管解析不管验证） | `anystyle check` 对 gold 集输出 sequence/token 两级错误率（评测纪律好）；**官方声明：中文日文阿语等非空格分词语言"aren't compatible with AnyStyle's approach"** |
| RefChecker（434★，2025-05 后休眠） | LLM 输出细粒度幻觉核查（阿里，ACL 2024） | 无参考文献解析 | knowledge triplet 抽取→LLM 核查→**localization model 把三元组映射回参考文本片段**（模型驱动、片段级，非字符偏移） | ✅/❌/❓ 三态 + 整体 factuality score；2.1k 人工标注基准 |
| **gewita（本项目）** | **验证侧**：对给定文档的引用做三级对齐+存在性核验 | 规则解析 GB/T 7714 类型标识（[J]/[M]/[C]…）+ APA-lite，启发式且如实报告覆盖率 | VERBATIM 字符偏移（不变量 fuzz 守护）/ NEAR 句粒度 0.85 / PARAPHRASE bigram 包含度，纯 CPU 零依赖 | 离线**永不判造假**（只有"未在给定来源中找到"）；INSUFFICIENT 级诚实降级；合成语料不外推声明 |

## 二、逐家走读

### reverify —— 定位修正 + 两件值得抄的事

**上一轮调研把它当成"关闭幻觉核查窗口"的竞品，本轮读原文后必须修正：它根本不在文献/引用赛道。** 它是给二进制逆向工程（malware 分析、CTF、互操作研究）做的"模型提议、确定性工具裁决"系统：claim 是对 PE 文件的结构假设（`bytes_at`/`instructions`/`emulate_result`），裁判是纯 Python 的 PE 解析器/反汇编器/模拟器。它 71 个 Windows 系统文件上"教科书答案 97% 是错的，reverify 全部抓住且从未接受一个错误 claim"的数字来自逆向域，与引用验证无关。

**但方法论上有两件真东西**：

1. **claim `weight` 信息量加权**（自称遵循 FActScore 的 CORE 精化）：逐字复述已知事实清单、重复、自指的 claim 权重记 0，"grounded" 要求零反驳**且**加权信息量达标。对我们的直译威胁是：integrity score 会被"引用了来源标题/引用了文献自身摘要"这类琐碎命中注水——每条引用都 VERBATIM 但信息量为零的报告不该得高分（已转为 iter9）。
2. **CI 门禁姿态**：CLI 在任一 claim 被 REFUTED 时非零退出，agent/CI 可直接 gate。我们已有退出码 0/1/2，方向一致，验证了设计。

### verbatim-rag —— 生成侧的诚实样板，互补关系源码级确认

它做"检索→逐字摘录→带引用回答"，目的是**缩小生成面**，产出天然带溯源的答案；gewita 做"给定文档的引用核验"，是**验证侧**。两者不可互相替代：它不检查你手里已有的报告。三点值得记录：

- **诚实度表格是同类最佳实践**："provenance guarantee, not a truth guarantee"（溯源≠真实），上下文模板生成的框外文字明确宣布在保证范围外。我们 README 的诚实边界小节同源，可再吸收它的表格形式。
- **重复文本偏移歧义被官方承认**："Repeated identical text can still make source-offset mapping ambiguous"。我们的 VERBATIM 目前返回首个命中——同样的歧义我们**还没有披露机制**（命中 N 处时报告只指向 1 处，已转为 iter10）。
- 依赖：verbatim-core 仅 openai/pydantic/rapidfuzz/jinja2；完整管线要 SPLADE/Milvus。轻核重管线，与我们"零必装"路线无冲突。

### anystyle —— 官方弃权中文，我们的解析层有了"合法性证明"

README 原文：*"Languages written in syllabaries or complex symbols which don't use white space to separate tokens aren't compatible with AnyStyle's approach: this includes Chinese, Japanese, Arabic, and Indian languages."* ——不是它没顾上，是**方法不兼容**（Wapiti CRF 依赖空格分词特征，默认语料 965 英/54 法/26 德/中文 0）。GB/T 7714 的类型标识（[J]/[M]/[C]）与中文顿号作者列表在它的特征体系里天然无解。这把 gewita 解析层从"又一个 parser"升级为"中文文献解析的唯一切实选项"（在其方法框架内不可被 anystyle 反超）。

**它做得对的**：`anystyle check` 对 gold 集输出 sequence/token 两级错误率、训练自定义模型的一整套流程、2011 年活到现在的长维护。我们 iter3 的"字段级 P/R/F1"应向它的两级口径看齐（条目级 + 字符/字段级并列报告）。

### RefChecker —— 最接近的"验证侧"前辈，但已休眠且路线不同

三段式：claim 抽取（LLM）→ 三元组核查（LLM，✅/❌/❓）→ 聚合；localization model 把三元组映射回参考片段。与我们最近的相似点是"把结论映射回原文"，但它是**模型驱动、片段级、重依赖**（litellm/vllm/spacy/搜索引擎），我们是**规则驱动、字符偏移、零依赖**。News 停在 2024-07-22，最后 push 2025-05-16——ACL 论文热度之后实际停更。它证明了两件事：验证侧需求真实（434★）+ LLM 中心路线的维护成本压垮了持续迭代。

## 三、结论

1. **赛道再确认（本轮最强结论）**：四家按域排除后，"给定文档的引用核验 + 中文参考文献解析"这个组合**在 2026-09 仍然无人占据**：anystyle 官方弃权中文、RefChecker 休眠、verbatim-rag 在生成侧、reverify 在逆向域。
2. **吸收两点**（已转 iter9/iter10）：claim 信息量加权防 integrity score 注水；多命中歧义披露。
3. **方法论背书**：reverify 的三态+证据回贴、verbatim-rag 的溯源≠真实、anystyle 的 gold 错误率——三个不同域的项目在"诚实度设计"上收敛到与我们相同的做法，方向互相验证。
4. **风险更新**：anystyle 若做中文（需换方法，概率低）；RefChecker 复活（阿里内部项目，论文热度已过，概率低）；最大变数仍是"某个 LLM 厂商把引用核验做成平台功能"——开源标准件的生存空间在"可嵌入、可离线、可审计"。

## 四、证据清单

- reverify README（全文精读）：https://github.com/2akouwu/reverify ，1,249★，created 2026-08-31，last push 2026-09-07（2026-09-28 实抓）
- verbatim-rag README（全文精读）：https://github.com/KRLabsOrg/verbatim-rag ，204★，last push 2026-09-07（2026-09-28 实抓）
- anystyle README（全文精读，含语言兼容性声明原文）：https://github.com/inukshuk/anystyle ，1,292★，last push 2025-05-11（2026-09-28 实抓）
- RefChecker README（全文精读）：https://github.com/amazon-science/RefChecker ，434★，last push 2025-05-16（2026-09-28 实抓）
- 本轮网络备注：github.com 页面经 WebFetch 持续 ECONNRESET，全部改走 raw.githubusercontent + GitHub API 实抓，证据不受影响。
