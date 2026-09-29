# REPORT — gewita（Gewita）夜间自动化迭代总结（2026-09-28 01:10 → 07:45）

> 执行方式：主会话完成 iter0（完整项目初版，构建 agent 产出 + 主会话验收），此后 2 轮自动化迭代（每两小时轮换一次）+ 本收尾轮。
> 全程未 push 远程；所有提交在本地 `main`（v0.1.0-rc1 → 68dbe7d）。

## 一句话总结

**gewita（Gewita）v0.1.0-rc1 + 两个迭代完成**：中文优先的引用验证标准件——GB/T 7714 国标参考文献解析、正文引用抽取、引文↔来源四级对齐（逐字命中带精确偏移，fuzz 守护不变量）、DOI/arXiv 存在性核验（离线永不判造假）、引用透明库；**181 项测试全绿，ruff 0 error**。赛道经竞品走读再确认：anystyle（1,292★）官方声明中文不兼容其方法，RefChecker（434★）2025-05 后休眠，"给定文档的引用核验 + 中文解析"组合仍无人占据。

## 每轮完成清单

| 轮次 | 时间 | 完成内容 | 测试 |
|---|---|---|---|
| iter0 | 01:10–01:45 | 完整项目：GB/T 7714/APA-lite 解析、引用抽取（[1-3] 展开）、四级对齐（偏移不变量 fuzz 10 seed）、存在性核验（可注入 transport）、refstore 指纹库、CLI 四命令、8 篇语料 35 条金标评测 | 172 |
| iter1 | 03:40–03:55 | **竞品源码走读**：reverify 定位修正（二进制逆向域，非文献赛道）；anystyle 官方弃权中文（README 原文取证）；RefChecker 休眠证据；verbatim-rag 暴露我们的多命中披露缺口；docs/competitors.md；追加 iter9（integrity score 信息量加权）/iter10（多命中歧义披露） | 172 |
| iter2 | 05:40–05:59 | **在线核验加固**：礼仪 UA + Crossref 礼貌池 mailto 参数（官方文档取证）、文档级共享查询缓存（同指纹不出网）、429/5xx 指数退避重试（尊重 Retry-After，cap 防呆）、带 DOI 条目的注册机构级诚实说明（非 Crossref 机构查不到≠造假）；judge_document 支持 budget 注入 | 181 |
| wrap-up | 07:40–07:45 | 双项目终验（pytest 退出码 0 / ruff 退出码 0）+ 本报告 | 181 |

## 关键数字（全部真实运行，出处见对应文档）

- 内置评测（8 篇合成语料 / 35 条金标，`benchmarks/results.md`）：对齐四级 VERBATIM/NEAR/PARAPHRASE/NOT_FOUND **P=R=F1=1.000**；fabricated 检测（mock transport 离线复现）**F1=1.000**；解析覆盖率 94.3%（2 条故意残卷如实标注）
- 合成语料边界在 README 明示：格式级能力上限，不外推真实脏数据
- 竞品证据（`docs/competitors.md`）：anystyle 官方原文"中文日文等非空格分词语言与 AnyStyle 方法不兼容"（默认语料中文 0 条）；RefChecker News 停在 2024-07；verbatim-rag 官方承认"重复文本使偏移映射歧义"
- 学术背书：arXiv 2026-07《HALLMARK》《Detecting Hallucinated Citations: What Current Tools Can and Cannot Do》结论=现有工具不行（GAP_PROOF 选题依据）

## 夜间抓到的真 bug / 有价值的发现

1. **reverify 定位修正**（iter1）：上轮调研误把它当"关闭幻觉核查窗口"的最大竞品，读原文后确认是二进制逆向域声明验证器——方法论可抄（claim 信息量加权 → iter9），赛道无冲突
2. **160s 测试套件回归**（iter2）：文档级共享预算让限速首次真正生效（旧 per-call 预算 `_last=0` 初始化使首查从不满速），bench 的 35 条 mock 查询每条睡 1s——用 `--durations` 定位后，`run_bench` 显式传零间隔预算，恢复 10s；`judge_document` 增加 budget 注入参数
3. 断言措辞与实现文案不一致、QueryBudget 构造参数顺序错误等 3 处小错，均测试当场抓住当场修

## 诚实未完成项

1. **iter3~iter8 及评审追加条目（iter9~iter12）未执行**：GB/T 7714 语料扩充与字段级 F1、LLM 语义裁决器、透明库共享格式、HTML 报告、红队轮（对抗性引用测试集）、发布工程、integrity score 加权、多命中披露。原因：夜间窗口按协议收尾。
2. **在线核验未对真实 Crossref/arXiv 出网验证**（家规：测试绝不真实联网）；iter12 的 `gewita smoke`（唯一允许出网的用户手动命令）待实现后补上这块观测。
3. 内置评测为合成语料——真实脏数据（真实论文的参考文献表）上的解析覆盖率未知，iter3 语料扩充是解药。
4. GB/T 7714 解析器是启发式规则，字段级 P/R/F1 尚未报告（现只报布尔覆盖率）。
5. README_EN 仅 quickstart 段（iter8 完整版）。

## 给你的下一步建议（按优先级）

1. **注册 GitHub 仓库并 push**：`cd gewita && git remote add origin <url> && git push -u origin main`。
2. **杀手级 demo 先行**：找 3-5 篇真实论文（含 2026-04"11 万篇假引文"事件的样本），跑 `gewita check` 出报告——真实文献上的解析覆盖率与对齐质量是比合成语料 F1=1.000 有说服力一百倍的发布素材，也是 iter3 语料扩充的原料。
3. **配置 `YINZHENG_CONTACT`**（你的邮箱）再跑 `--online`：Crossref 礼貌池能拿到更好的限流待遇；然后实现 iter12 的 smoke 命令验证真实成功率。
4. **发布叙事现成**：白宫假引文 / Deloitte 44 万澳元退款 / 11 万篇污染论文 + "anystyle 官方弃权中文" 对比图（docs/competitors.md 有原文引用）——知乎/掘金一篇《中文论文的引用验证，没有人做》。
5. PyPI 发布需要你的 token（包名 `gewita` 已验证未注册，01:12 查询 404）。
