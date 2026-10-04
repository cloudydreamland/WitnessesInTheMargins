# CHANGELOG

## 0.1.0 (2026-10-05)

首个稳定版。原"未发布"段的在线核验加固内容随本版一并发布；README 安装说明
更新为 PyPI 安装优先。


### 新增（未发布）

- **在线核验加固**：礼仪 UA 与 Crossref 礼貌池 mailto 参数（环境变量 `YINZHENG_CONTACT`）；文档级共享查询缓存（同指纹不重复出网）；429/5xx 指数退避重试（尊重 Retry-After，cap 防呆）；带 DOI 条目查无结果时详情明示"非 Crossref 注册机构查不到≠造假"；`judge_document` 支持注入文档级 `QueryBudget`。

### 文档

- iter1 竞品源码走读：新增 `docs/competitors.md`（reverify 定位修正、anystyle 官方弃权中文声明、RefChecker 休眠证据、verbatim-rag 互补确认）；README「与现有方案的关系」表升级；新增 iter9（integrity score 信息量加权）/iter10（多命中歧义披露）。

## 0.1.0rc1 — 2026-09-28

首个候选版本。三大件：参考文献解析、引用抽取、三级对齐裁决；外加存在性核验与引用透明库。

### 新增
- `text`：归一化（全角→半角/casefold/统一引号/去空白变体）+ 归一化位置→原始位置索引映射；中英文感知切句（拼接不变量、换行硬边界、小数/版本/域名/缩写抑制）
- `refs`：GB/T 7714（[J]/[M]/[C]/[D]/[P]/[S]/[EB/OL]/[DB/OL]）、无类型码编号体、APA-lite 解析；DOI/arXiv/URL/年份抽取；覆盖率如实报告
- `extract`：`[1]` `[1,2]` `[1-3]`（区间展开）连续标记、作者-年份式；标记挂接所在句；参考文献表区排除
- `align`：VERBATIM（精确偏移，`source[start:end]==引文` 由 fuzz 守护）/ NEAR（≥0.85）/ PARAPHRASE（bigram 包含度≥0.5）/ NOT_FOUND
- `existence`：DOI/arXiv 结构校验；title_fingerprint；verify_online（Crossref→arXiv，可注入 transport，限速+预算；离线永不判造假）
- `verdict`：判定矩阵合成（ref_status × existence × alignment）；refstore 联动 LOCAL_ONLY
- `refstore`：追加式 JSONL 指纹库（去重/统计/持久化）
- `report`：Markdown/JSON 报告；integrity score（权重公式写明）；异常清单与诚实声明
- `bench` + benchmarks/corpus：8 篇微文档 + 35 条金标，mock transport 离线可复现评测
- `cli`：check / refs / bench / refstore stats；退出码 0/1/2

### 质量
- 172 项测试全绿（全离线）；ruff 0 error；py.typed 完整类型标注
- 内置评测（真实跑出）：对齐四级 F1=1.000，fabricated F1=1.000，解析覆盖率 94.3%
