# benchmarks/results — 内置评测真实结果

> 本文件由 `gewita bench`（`python -m gewita bench`）真实跑出并回填，**禁止手编数字**。
> 最近运行：2026-09-28（iter0，Python 3.13 / Windows，离线 mock transport）

# gewita 内置评测结果

- 文档 8 篇 / 来源 8 篇 / 金标 35 条 / 参考文献条目 35 条
- 解析覆盖率：**94.3%**（启发式解析器，如实统计）
- 对齐四级 micro 准确率：**100.0%**

| 对齐级别 | P | R | F1 |
|---|---|---|---|
| VERBATIM | 1.000 | 1.000 | 1.000 |
| NEAR | 1.000 | 1.000 | 1.000 |
| PARAPHRASE | 1.000 | 1.000 | 1.000 |
| NOT_FOUND | 1.000 | 1.000 | 1.000 |

- fabricated 检测（mock transport，离线可复现）：P 1.000 / R 1.000 / F1 1.000
- unparsable 条目检出 2 / 漏检 0

| 文档 | 条目 | 解析出 | 引用标记 | 覆盖率 |
|---|---|---|---|---|
| cn_academic | 6 | 6 | 6 | 100% |
| cn_legal | 4 | 4 | 4 | 100% |
| cn_review | 6 | 5 | 6 | 83% |
| cn_tech | 4 | 4 | 4 | 100% |
| cn_wechat | 4 | 4 | 4 | 100% |
| en_notes | 3 | 2 | 3 | 67% |
| en_paper | 4 | 4 | 4 | 100% |
| en_report | 4 | 4 | 4 | 100% |
