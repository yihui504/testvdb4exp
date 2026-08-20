# testvdb4exp — RQ1 检测能力实验版

> 2026-08-20 换底座：旧底座 `b80b95d`（judge quartet + dev-reviewer 旧管线）→
> **新底座 = 主插件 `yihui504/TestVDB@4ee83c1`**（ADR-0008：evidence-builder +
> chain-auditor + novelty 提交前终判，含 v7/v8 实验回合的全部机械化改进）。
> 实验改造在其上按项重放（commit `1501e55` 换底座 + `2c2aae8` 重放改造）。

本仓库只用于论文 RQ1 端到端检测能力实验（Phase 3 档3）；正常使用请用主插件。

## 实验改造清单（相对主插件 4ee83c1）

| # | 改造 | 落点 | 状态 |
|---|---|---|---|
| 1 | 轮次上限默认 5→30 | `scripts/pipeline_state.py` `--max-rounds` default | ✅ |
| 2 | 删"覆盖率≥95 停止" | `scripts/reconstruct_context.py` 终止分支 + `commands/mine.md` 两处终止清单 | ✅ |
| 3 | 删"连续 5 轮无新缺陷停止" | 同上 | ✅ |
| 4 | ~~novelty bypass~~ **不迁移** | — | ✅（见下） |
| 5 | GT-informed 续挖注入 | `scripts/gt_reach_injector.py` + `commands/mine.md` 8a `{GT_HINT}` | ✅ |
| 6 | gt.json 按版本分组约定位置自动发现 | injector 自动发现（env `TESTVDB_GT_PATH` override） | ✅ |
| 7 | attack agents maxTurns→500 | `agents/attack-{boundary,state,semantic,vein}.md` | ✅ |
| 8 | 跨版本禁缓存 | 主插件 `check_cache.py` 本就 target+version 双键 | ✅（无改） |

### #4 为何不再 bypass novelty gate（与旧实验版的关键差异）

旧架构里 novelty 查重在确认链内，GT bug 全是已报告 issue 会被判 KNOWN 删掉 →
reach 归零，必须 bypass。**ADR-0008 新架构下该前提不存在**：

- novelty 是**提交前终判**（9a），reach 统计取 `debate_logs/chain_verdicts.json`
  的 DEFECT 全集，novelty 只决定"该 DEFECT 报告 novel 还是已报告"，碰不到 reach 分母；
- NON_NOVEL 改为 `archived/` 归档不删，`manifest.json` 的 related_issue_numbers
  **正是 RQ1 新列"发现已被报告 bug"的数据源**——bypass 会砍掉这一列。

**统计口径（写死）**：reach = `chain_verdicts.json` DEFECT 全集（含被归档的），
不是 Gate-Endorsed 集。详见论文仓库 `docs/mentor-feedback-checklist.md` 2.1。

### #5 的 confirmed 源已切到 ADR-0008 语义

injector 的 `_confirmed_params()` 从读 `stage2_aggregation*.json`（旧 judge 链路
产物，新底座永远不存在 → confirmed 恒空 → 每轮错误催促"0/N"）改为读
`debate_logs/chain_verdicts.json` 的 DEFECT 条目。auditor 每轮对累积的
`evidence_chain/` 全量重判（builders 跨轮追加链），单文件读取即天然跨轮累计，
无需历史文件。

**盲注契约不变**：hint 只含"已确认 X/Y + 提升脚本质量/扩大覆盖/深化挖掘"，
4 个 attack agent 收相同文本，不含任何端点/参数/预期（防方向泄露）。

## 跑法

```bash
# 1. 拷入该版本的 GT（论文仓库 .paperpilot/phase3/gt/{vendor}/{version}/gt.json）
cp <paper>/.paperpilot/phase3/gt/qdrant/v1.18.2/gt.json results/qdrant/v1.18.2/gt.json

# 2. 跑挖掘（不要设 TESTVDB_NOVELTY_BYPASS —— 本版无此开关，novelty 正常开）
/testvdb:mine qdrant v1.18.2

# 3. RQ1 采集项（每版本跑完收集）
#    - reach：debate_logs/chain_verdicts.json DEFECT 全集 vs gt.json（LLM 盲评对齐）
#    - 首达轮次：从各轮 debate_logs 时间戳回溯
#    - FP 过滤后数据 / Submitted：novelty_gate.json + issues/ + archived/manifest.json
#    - "发现已被报告 bug"列：archived/manifest.json related_issue_numbers
#    - novelty 归档数据：archived/ 全目录
#    - retry 子循环 regen 成功率：execution_summary（验证打回机制真在工作）
```

实验运行纪律与 15 版本清单见论文仓库 `docs/phase3-plan.md` + `docs/phase3-progress.md`。

## 测试

```bash
python -X utf8 -m pytest tests/ -q
# 预期：165 passed + 1 known-fail（test_cli_m4_halt_exits_2 —— Windows
# Python3.8 subprocess GBK 编码问题，主插件 HEAD 同样失败，与本实验无关）
```
