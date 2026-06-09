# 架构说明

## 原则

- v1 不做自动交易。系统只发现、评分、回放和报告机会。
- AI 能力不内置为常驻自主智能体。Claude Code、Codex、opencode 等外部 agent 负责读互联网、提出假设、写候选代码和解释结果。
- 项目本身提供确定性的执行层：数据、标准化、回放、评分、schema 校验、证据留痕和安全边界。
- Tick 级大行情不进 Postgres。Postgres 只负责元数据、任务、心跳、配置和摘要。
- 每个交易所事件在入库或进入策略评估前，都先标准化为 `MarketEvent`。
- 策略以插件形式实现，必须声明明确的数据契约，并提供确定性的 evaluator。
- 外部 agent 可以生成报告和候选代码，但生产策略配置和下单路径必须被阻断。

## 数据流

1. Connector 下载历史文件，或消费 WebSocket 实时消息。
2. Connector parser 输出标准化的 `MarketEvent` 对象。
3. Collector 将事件写入分区数据湖，并更新数据源心跳。
4. Agent 通过 CLI、schema 或 API 提交研究报告、策略提案和回放请求。
5. Worker 执行清洗、回放、评分和机会摘要。
6. API 暴露健康状态、任务、机会、策略报告和研究报告。
7. 控制台读取 API，为操作人员提供轻量观察面板。

## Agent 协作边界

- `packages/agent_interface` 定义 agent artifact、workflow、guardrail 和工具入口。
- `schemas/` 定义研究报告、策略提案、回测请求、机会报告和人工门禁 checklist 的 JSON schema。
- `apps/cli` 提供 JSON 输入输出，方便 agent 直接调用。
- `packages/research_agent` 保留为兼容层，新能力应优先放到 `agent_interface`。

## 分区

大行情事件写入以下路径：

```text
exchange=<exchange>/date=<yyyy-mm-dd>/market_type=<spot|perp|future|option>/symbol=<symbol>/event_type=<type>/
```

当 `pyarrow` 可用时，writer 使用 Parquet；在最小本地环境中降级为 JSONL。分区形态保持 DuckDB 可读。

## 内置策略族

- 跨所现货/永续价差。
- 永续 funding carry。
- 交割合约 basis。
- 三角或多腿换币价差接口。
- 期限结构异常接口。
- 期权静态套利接口，预留给 put-call parity、box spread、calendar spread 和 butterfly 检查。
