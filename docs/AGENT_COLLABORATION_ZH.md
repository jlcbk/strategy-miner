# Agent 协作说明

Strategy Miner 不再定位为独立运行的 AI 后台，而是给 Claude Code、Codex、opencode 等外部 agent 使用的量化研究执行层。

## 职责分工

外部 agent 负责：

- 阅读互联网文章、论文、公告、论坛和代码仓库。
- 提炼策略假设、公式、成本项和失败模式。
- 生成符合 schema 的研究报告和策略提案。
- 编写候选 evaluator 和测试。
- 调用本项目的 CLI、测试和回放工具。
- 解释结果，并生成 PR 或人工审核材料。

Strategy Miner 负责：

- 交易所数据接入和统一 `MarketEvent`。
- 数据湖写入、查询和历史回放。
- 策略插件接口和确定性 evaluator。
- 机会评分、容量估计、风险提示和失败码。
- JSON schema、workflow、artifact 留痕和安全边界。
- 阻止生产配置修改、自动部署和真实下单。

## 标准工作流

```text
GitHub issue 或互联网策略灵感
-> agent 生成 research_report
-> agent 生成 strategy_proposal
-> agent 调用 rank_strategy_candidates
-> 项目校验 schema 和 guardrail
-> agent 生成候选 evaluator
-> 项目跑 fixture tests
-> 项目跑 replay/backtest
-> 项目输出 opportunity_report
-> 人工审核是否合入
```

## Artifact 契约

当前定义的核心机器可读 artifact：

- `research_report`：来源、摘要、关键 claim、公式、成本项、失败模式和数据需求。
- `strategy_proposal`：策略假设、evaluator 契约、数据需求、测试计划、风险控制和候选文件。
- `backtest_request`：策略名、版本、数据窗口、symbols、exchanges 和参数。
- `opportunity_report`：策略结果、机会数量、机会列表、数据窗口和结果哈希。
- `manual_gate_checklist`：非行情数据或人工风控门禁，例如发行方状态、赎回状态、监管状态和人工确认要求；默认不产生 data lake 分区。

对应 schema 放在 `schemas/` 目录。

## Issue 入口

策略灵感优先记录在 GitHub Issue 中。新建 issue 时使用 `Strategy idea` 模板；agent 处理 issue 后，应把自然语言内容整理为 artifact，而不是只在 issue 评论里给结论。

Issue 生命周期和处理规则见：[STRATEGY_INTAKE_ZH.md](STRATEGY_INTAKE_ZH.md)。

每个候选策略都必须对照 [OPERATOR_PROFILE_ZH.md](OPERATOR_PROFILE_ZH.md) 判断是否适合我们的操作条件。收益假设高但需要高杠杆、极低延迟、复杂跨所转账或持续人工盯盘的策略，应降低优先级或标记为人工审核。

## CLI

列出可用工具：

```bash
python -m apps.cli.main tools
```

检查安全边界：

```bash
python -m apps.cli.main run-tool check_guardrail --payload-json '{"action":"place_order"}'
```

对一批 `strategy_proposal` 做研究漏斗排序：

```bash
python -m apps.cli.main run-tool rank_strategy_candidates --payload-json '{"candidates":[{"proposal":{"kind":"strategy_proposal","title":"Funding carry","created_by":"codex","strategy_name":"funding_carry","hypothesis":"正 funding 扣除成本后存在 carry 机会","data_requirements":["funding","mark_price"],"test_plan":["按周回放主流 perp"],"risk_controls":["限制单交易所敞口"]},"research_report":{"failure_modes":["拥挤交易压缩收益"]},"scores":{"verifiability":5,"data_availability":5,"capacity_potential":4,"cost_robustness":4,"overfit_resilience":4,"implementation_simplicity":5}}]}'
```

检查一个 `strategy_proposal` 是否具备验证准备条件：

```bash
python -m apps.cli.main run-tool plan_strategy_validation --payload-json '{"proposal":{"strategy_name":"funding_carry","data_requirements":["funding","mark_price","spot_candles","fees"]}}'
```

检查本地 data lake 是否已有目标窗口的验证数据：

```bash
python -m apps.cli.main run-tool check_data_coverage --payload-json '{"root":"/data/hdd/strategy-miner/lake","proposal":{"strategy_name":"funding_carry","data_requirements":["funding","mark_price"]},"exchanges":["binance"],"market_types":["perp"],"symbols":["BTCUSDT"],"start_date":"2024-01-01","end_date":"2024-01-01"}'
```

把缺失分区转换成待执行采集任务：

```bash
python -m apps.cli.main run-tool generate_data_collection_jobs --payload-json '{"root":"/data/hdd/strategy-miner/lake","proposal":{"strategy_name":"funding_carry","data_requirements":["funding","mark_price"]},"exchanges":["binance"],"market_types":["perp"],"symbols":["BTCUSDT"],"start_date":"2024-01-01","end_date":"2024-01-01"}'
```

CLI 输出 JSON，方便 agent 直接解析。

`rank_strategy_candidates` 使用 0 到 5 分的研究维度：

- `verifiability`：验证路径是否清晰。
- `data_availability`：需要的数据是否容易取得。
- `capacity_potential`：策略容量潜力。
- `cost_robustness`：对手续费、滑点、资金费和冲击成本是否稳健。
- `overfit_resilience`：是否便于做跨时间、跨交易所或跨品种稳定性检查。
- `implementation_simplicity`：候选 evaluator 和测试是否容易落地。

高分且核心字段完整的候选会进入 `queued_for_validation`；高分但缺少失败模式、数据需求、测试计划或风险控制的候选会进入 `needs_human_review`。

## 安全边界

默认禁止：

- `place_order`
- `enable_live_trading`
- `auto_deploy_strategy`
- `write_production_config`
- 触及 `configs/production`、`order_router`、`broker`、`live_trading` 等路径的候选文件。

允许：

- 创建研究报告。
- 创建策略提案。
- 创建候选 evaluator。
- 运行测试。
- 运行回放。
- 生成 PR 或人工审核材料。

## 设计原则

- AI 负责提出假设，本项目负责验证假设。
- Agent 输出必须机器可读，不能只给自然语言。
- 任何策略结论都必须绑定数据窗口和可复现回放结果。
- 未经人工审核的策略不能标记为 production-ready。
