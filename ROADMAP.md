# ROADMAP — 夜间自动化迭代驱动表

> 规则：自动迭代每一轮从上到下找第一个未勾选条目，完整做完（代码+测试+文档）再勾选。
> 每条目设计为一轮（≤45 分钟）可完成。做完更新 WORKLOG.md 并提交。
> 每轮固定动作：① 选条目实现；② **对抗评审**（以资深开发者/项目经理/老板三视角挑刺，可上网核查竞品与用户抱怨，结论写入 WORKLOG 的"评审记录"）；③ 有效批评转化为新条目追加到本表末尾；④ 全量 pytest + ruff 必须绿；⑤ 提交。

## 迭代条目

- [x] **iter0（2026-09-28 凌晨，主会话完成）**：三大件落地——GB/T 7714/编号体/APA-lite 参考文献解析（覆盖率如实报告）、正文引用抽取（[1]/[1,2]/[1-3] 展开/连续标记/作者-年份式）、三级对齐裁决（VERBATIM 精确偏移 + 偏移不变量 fuzz 10 seed、NEAR 句粒度 SequenceMatcher≥0.85、PARAPHRASE bigram 包含度≥0.5 倒排索引筛候选、1MB smoke <1s）；存在性核验（DOI/arXiv 结构校验 + Crossref/arXiv 可注入 transport，限速+预算，离线永不判造假）；refstore 指纹库（追加/去重/统计）；Markdown/JSON 报告 + integrity score（权重写明）；CLI check/refs/bench/refstore 四命令 + 退出码 0/1/2；内置 8 篇语料 + 35 条金标评测全绿（对齐四级 F1=1.000、fabricated F1=1.000、解析覆盖率 94.3%）；172 项测试全绿 + ruff 0 error。
- [x] **iter1 — 竞品源码走读（2026-09-28 夜间完成）**：精读 reverify / verbatim-rag / anystyle / RefChecker 的核心解析与对齐代码，写 `docs/competitors.md`：各自的标题边界策略、对齐算法、诚实度设计，与我们的差异表（如实记录它们做对的点）；README"与现有方案的关系"表格据此更新。
- [x] **iter2 — 在线核验加固（2026-09-28 夜间完成）**：Crossref 礼仪 UA（带 mailto 联系方式，环境变量 `YINZHENG_CONTACT`）；文档级共享查询预算与缓存（同指纹不重复查询）；429/5xx 指数退避重试；诚实记录哪些 DOI 前缀查不到（registrant 级缺失 ≠ 文献造假，写入 detail）。
- [ ] **iter3 — GB/T 7714 语料扩充 + 解析器 F1 报告**：扩充真实风格语料（多作者/译者/版次/页码区间/DOI+arXiv 混排/机构作者/无年份），给解析器加字段级 P/R/F1 报告（标题/年份/刊名分列），覆盖率从"布尔 parsed"升级为分字段统计；benchmarks/results.md 增列。
- [ ] **iter4 — LLM 语义裁决器**：PARAPHRASE 的支持性判断（句子是否真被来源支持），可插拔 judge 协议（OpenAI 兼容），干跑模式（只记录不裁决）、限速批量、偏移安全阀（judge 只输出支持/不支持/无法判断，不改偏移）；mock 测试全覆盖，默认关闭。
- [ ] **iter5 — 引用透明库共享格式规范 v0**：refstore 导出/合并/去重策略（多库合并时同指纹不同裁决的冲突消解规则），格式规范文档 + 跨库合并测试，为"已核验文献指纹共享网络"铺路。
- [ ] **iter6 — HTML 报告工件 + 徽章**：单文件 HTML 报告（证据偏移高亮回贴原文、可点击跳转）、integrity score 徽章 SVG、CI workflow 示例（pytest+ruff+bench 回填）。
- [ ] **iter7 — 红队评审轮**：对抗性引用测试集——改写引文（同义替换攻 NEAR）、拼接引文（两句各半攻对齐）、翻译引文（中↔英攻归一化）、跨来源拼接（A 来源开头 + B 来源结尾）；逐项记录当前防线与失守点，能修则修，不能修如实写进 README 诚实边界。
- [ ] **iter8 — 发布工程**：launch_checklist（知乎/掘金/V2EX/学术社区群发文案要点）；PyPI 发布检查单（trusted publisher）；README_EN.md 完整版（当前仅 quickstart 段）；`python -m build` 出 sdist/wheel 验证 + tag v0.1.0。

### iter1 评审追加（2026-09-28 夜间，竞品源码走读产出）

- [ ] **iter9 — integrity score 信息量加权**：借鉴 reverify 的 claim `weight`（FActScore CORE 精化）：自我指涉（引用了来源标题/文献自身摘要）、重复命中、琐碎命中的引用在 integrity score 中降权或记零分——防止"每条引用都 VERBATIM 但信息量为零"的报告得高分；权重规则写进报告文档；bench 加"注水报告"反例 fixture 验证分数被压低。
- [ ] **iter10 — 多命中歧义披露**：verbatim-rag 官方承认"重复文本使偏移映射歧义"，我们同样存在：VERBATIM/NEAR 命中多处时 `align_quote` 返回 `match_count` 与全部命中偏移（封顶如 10 处），报告在证据栏标注"证据指向第 1 处命中，全文共 N 处相同/相似片段"；不变量 fuzz 扩展：注入 k 处相同片段时 match_count==k。

### iter2 评审追加（2026-09-28 夜间，在线核验加固轮）

- [ ] **iter11 — 在线核验使用指南 docs/online.md**：QueryBudget 生命周期（跨文档共享=二级缓存）、YINZHENG_CONTACT 配置说明（附 Crossref 官方礼仪文档原文出处）、重试语义（429/5xx、Retry-After 优先、cap 上限）、限速默认值依据；明确"独立调用 verify_online 不共享缓存，请走 judge_document 或自建预算"。
- [ ] **iter12 — 在线冒烟测试命令 `gewita smoke`**：唯一允许真实出网的命令，需 `--yes` 显式确认；内置 3 条真实文献（Crossref/arXiv 各一）+ 1 条编造文献，输出各家 provider 的裁决与耗时；家规"测试绝不真实联网"不破——smoke 是用户手动命令，pytest 不碰。

## 收尾条目

- [ ] **wrap-up**：全量测试与 lint 最终确认；写 REPORT.md（本轮总结：完成清单、测试状态、诚实未完成项、给用户的下一步建议）；最终提交。
