# 策略灵感入口和协作流程

Strategy Miner 的长期目标是找到适合我们实际操作的交易策略。GitHub Issue 是人类输入和讨论入口；项目内 artifact 是机器可读的正式记录。

## 推荐流程

```text
GitHub issue
-> agent 整理 research_report
-> agent 整理 strategy_proposal
-> rank_strategy_candidates 研究漏斗评分
-> validation_queue
-> fixture tests / replay / backtest
-> opportunity_report
-> 人工审核
```

## Issue 职责

Issue 用来记录原始灵感、讨论、补充链接和状态。灵感可以不完整，但应该尽量说明：

- 策略想法。
- 市场范围。
- 为什么可能有效。
- 信号或触发条件。
- 可能需要的数据。
- 成本和风险。
- 是否适合我们的操作约束。
- 参考材料。

## Artifact 职责

进入研究漏斗后，agent 应该把 issue 内容整理为机器可读 artifact：

- `research_report`：来源、摘要、关键 claim、公式、成本项、失败模式和数据需求。
- `strategy_proposal`：策略假设、evaluator 契约、数据需求、测试计划、风险控制和候选文件。
- `data_collection_plan`：当候选卡在数据覆盖率时，记录缺失分区、采集命令模板、阻塞原因和执行安全边界。
- `opportunity_report`：验证结果、机会数量、数据窗口、评分和结果哈希。
- `manual_gate_checklist`：当策略依赖发行方状态、赎回通道、监管状态、人工风控判断等非行情数据时，记录人工门禁问题、证据要求和默认阻塞规则。

Issue 不是最终数据库。正式研究结论必须能转换成 artifact，方便后续验证和复现。

## Label 状态

建议使用这些 label 维护生命周期：

- `strategy:idea`：刚记录的策略灵感。
- `strategy:researched`：已经形成研究报告。
- `strategy:proposed`：已经形成策略提案。
- `strategy:validation-ready`：研究漏斗高分且核心字段完整。
- `strategy:blocked-data`：因为数据缺失无法验证。
- `strategy:rejected`：不适合继续投入。
- `strategy:validated`：已经完成验证并产出报告。

同一 issue 可以保留一个生命周期 label，再叠加主题 label，例如 `theme:funding`、`theme:basis`、`theme:momentum`。

## Agent 处理规则

- 优先处理 `strategy:idea` 和 `strategy:proposed`。
- 不直接把自然语言 issue 当成已验证结论。
- 每个候选必须写出失败模式；缺失失败模式时，不能进入 `validation_queue`。
- 每个高分候选都要对照 `docs/OPERATOR_PROFILE_ZH.md` 判断是否适合我们操作。
- 如果 `plan_strategy_validation` 返回 `needs_manual_gate`，只能生成 blocked alert，不能进入自动验证队列或 validation-ready。
- 不触发真实下单，不写生产交易配置。

## 研究漏斗评分

使用 CLI 对候选排序：

```bash
python -m apps.cli.main run-tool rank_strategy_candidates --payload-json '<strategy-candidates-json>'
```

评分维度为 0 到 5 分：

- `verifiability`：验证路径是否清晰。
- `data_availability`：需要的数据是否容易取得。
- `capacity_potential`：容量潜力。
- `cost_robustness`：对手续费、滑点、资金费和冲击成本是否稳健。
- `overfit_resilience`：是否便于做跨时间、跨交易所或跨品种稳定性检查。
- `implementation_simplicity`：候选 evaluator 和测试是否容易落地。
