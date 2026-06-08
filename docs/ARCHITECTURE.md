# 架构说明

## 原则

- v1 不做自动交易。系统只发现、评分、回放和报告机会。
- Tick 级大行情不进 Postgres。Postgres 只负责元数据、任务、心跳、配置和摘要。
- 每个交易所事件在入库或进入策略评估前，都先标准化为 `MarketEvent`。
- 策略以插件形式实现，必须声明明确的数据契约，并提供确定性的 evaluator。
- 研究智能体可以生成报告和候选代码，但生产策略配置和下单路径必须被阻断。

## 数据流

1. Connector 下载历史文件，或消费 WebSocket 实时消息。
2. Connector parser 输出标准化的 `MarketEvent` 对象。
3. Collector 将事件写入分区数据湖，并更新数据源心跳。
4. Worker 执行清洗、回放、评分和机会摘要。
5. API 暴露健康状态、任务、机会、策略报告和研究报告。
6. 控制台读取 API，为操作人员提供轻量状态面板。

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
