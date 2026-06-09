# 流水线和存储策略

这份文档记录当前对 Strategy Miner 运行方式的设计结论。

## 三条独立流水线

Strategy Miner 应该拆成三条独立但互相衔接的流水线：

```text
策略研究流水线：token 密集
数据采集流水线：长期持续运行
策略验证流水线：异步消费研究结果和数据
```

## 策略研究流水线

策略研究是 producer。它适合在 token 资源充足时，让 Claude Code、Codex、opencode 等 agent 尽可能多地学习已有策略。

研究阶段目标不是证明策略赚钱，而是积累结构化策略素材：

- 阅读文章、论文、GitHub、交易所公告和论坛。
- 提炼策略逻辑。
- 记录来源 URL。
- 总结公式、成本项和失败模式。
- 判断需要哪些行情数据。
- 生成 `research_report`。
- 生成 `strategy_proposal`。
- 给策略打研究优先级。

研究阶段可以不跑历史回放，也不要求完整真实数据可用。

## 数据采集流水线

数据采集是长期运行的基础设施。它不依赖某个具体策略，也不等待验证任务。

数据层目标是持续积累可回放的数据资产：

- 历史数据下载。
- 实时 trades 采集。
- 实时 top-N order book 采集。
- funding rate。
- mark/index price。
- open interest。
- instrument metadata。
- fee schedule。
- 数据缺口检测。
- 数据源健康监控。
- Parquet/JSONL 数据湖写入。
- Postgres 元数据和心跳更新。

数据层可以部署在远程 VPS、存储机或对象存储上，不必须和验证层同机。

## 策略验证流水线

策略验证是 consumer。它异步消费 `strategy_proposal` 和数据湖里的历史/实时样本。

验证阶段负责：

- 校验 schema。
- 检查需要的数据是否存在。
- 生成或完善候选 evaluator。
- 构造 fixture 测试。
- 跑单元测试。
- 跑 replay/backtest。
- 输出 `opportunity_report`。
- 标记验证状态。

验证阶段不应该重新让 agent 漫无边际地读资料。它应该消费研究阶段已经结构化的 proposal。

## 推荐状态流

```text
researched
-> proposed
-> queued_for_validation
-> validating
-> validated_pass
-> validated_fail
-> blocked_missing_data
-> needs_human_review
```

推荐新增概念：

- `research_backlog`：agent 研究出来的策略想法。
- `data_collection_jobs`：历史补数和实时采集任务。
- `validation_queue`：等待验证的策略提案。
- `validation_job`：一次具体验证任务。
- `validation_result`：验证结果和报告。

## 数据层运行模式

一次性历史补数：

```bash
python -m apps.collector.main historical-trades \
  --exchange binance \
  --market-type spot \
  --symbol BTCUSDT \
  --day 2025-01-01
```

长期实时采集的目标形态：

```bash
collector stream \
  --exchange binance \
  --symbols BTCUSDT,ETHUSDT \
  --events trade,orderbook,funding,mark
```

当前项目仍是 scaffold，实时 stream 命令会在后续 collector 扩展中补齐。

## 验证层如何使用数据

验证任务不应该直接去交易所临时抓数据，而应该先问数据层：

```text
这个 strategy_proposal 需要哪些数据？
-> data_coverage 是否满足？
-> 满足则进入 replay/backtest
-> 不满足则标记 blocked_missing_data
-> 同时创建 data_collection_job
-> 将 data_collection_job 转换成 collector CLI 命令或明确阻塞原因
```

这样可以保证验证结果可复现，也能避免不同 agent 会话各自抓一份不一致的数据。

当前可用工具链：

```bash
python3 -m apps.cli.main run-tool generate_data_collection_jobs --payload-json '{...}'
python3 -m apps.cli.main run-tool plan_data_collection_commands --payload-json '{"jobs":[...]}'
```

`plan_data_collection_commands` 不会执行下载，只输出可执行命令和阻塞原因。当前映射边界：

- Binance `trade` -> `historical-trades`
- Binance `mark` -> `historical-mark`
- Binance `funding` -> `funding`
- Binance `open_interest` -> `open-interest`，但官方历史 REST 只支持最近约 1 个月
- Binance `orderbook` -> `orderbook-snapshot`，只支持当前盘口快照，不能回补历史分区
- Bybit `trade` -> `historical-trades`
- Bybit `mark` -> `historical-mark`
- Bybit `funding` -> `funding`
- Bybit `open_interest` -> `open-interest`
- 其他交易所或事件类型会标记为 blocked，并返回尚未接入的原因

命令规划会给每个 job 标注执行风险：

- `low`：小 REST 数据，例如 `funding`、`open_interest`
- `medium`：中等归档数据，例如 1m `mark`
- `high`：大归档数据或高频热数据入口，例如逐笔 `trade`、`orderbook-snapshot`，默认需要人工确认后再执行

因此验证前补数应优先跑 `low` / `medium` 命令，等磁盘和下载窗口确认后再跑 `high` 命令。

## 三个月数据规模估算

如果采集范围是：

```text
4 家交易所
BTC / ETH / SOL
spot + perp
trades
top20 orderbook 1s snapshot
funding
mark/index
open interest
```

三个月压缩后粗略估算：

```text
250GB 到 1.2TB
```

如果 order book 采 100ms 或全量 delta 高频：

```text
3 个月也可能达到 2TB 到 10TB+
```

最大变量是订单簿频率。MVP 不建议一开始采全量深度或 100ms 全市场。

## depth_volume MVP 采集政策

`depth_volume` 是策略验证里的容量和滑点代理，不是高频执行信号。它的目标是回答“这个候选在目标 notional 下是否有足够流动性”，而不是重建完整订单流。

默认 MVP 政策：

```text
orderbook depth：top20 bid/ask
orderbook frequency：1s snapshot
orderbook staleness：超过 3s 视为 stale，不参与该窗口容量估计
trade aggregation：按 1m 和 5m 同时聚合
capacity window：默认 5m，短周期过滤器可额外看 1m
retention：orderbook 热数据 7-14 天，trades 14-30 天
symbols：优先 BTC / ETH perp，SOL 和其他标的按磁盘压力降级
exchanges：优先 Binance / Bybit，OKX / Bitget 第二阶段补齐
```

用于验证时，`depth_volume` 展开为两个物理事件分区：

```text
event_type=orderbook
event_type=trade
```

策略使用规则：

- 对 #4 这类跨所 funding 策略，`depth_volume` 只用于过滤容量不足或滑点过高的候选。
- 对 #5 这类 order-book imbalance 策略，MVP 只允许作为 1m 到 5m 过滤器评估，不允许演变成无人值守高频做市。
- 如果策略要求全量深度、100ms 级 snapshot 或 L2 delta，需要单独标记为 `orderbook_full_depth`，重新评估磁盘、延迟、保留期和 operator fit。
- 任何依赖 `depth_volume` 的策略，在 data coverage 未满足 `orderbook` 和 `trade` 分区前，都保持 `strategy:blocked-data`。
- 当前 `orderbook-snapshot` collector 只采当前 Binance spot/perp/future top20 快照。它适合让数据层从现在开始积累热数据，不适合补齐过去日期的 `orderbook` 分区。

## 有 500GB SSD + 3TB HDD 时

推荐分工：

```text
500GB SSD：热数据、写入缓冲、Postgres、Redis、回放临时缓存
3TB HDD：主数据湖，存历史 Parquet/JSONL
```

推荐目录：

```text
/data/ssd/strategy-miner/staging
/data/ssd/strategy-miner/hot
/data/ssd/strategy-miner/validation_cache
/data/hdd/strategy-miner/lake
/data/hdd/strategy-miner/reports
```

推荐流程：

```text
实时采集 -> SSD staging
清洗/分区/压缩 -> HDD data lake
最近 7-14 天热点分区 -> SSD hot cache
验证任务需要某段历史 -> 从 HDD 拉到 SSD validation_cache
验证完成 -> 删除 cache，只保留 report
```

这个配置适合跑 3 个月 MVP，前提是 order book 控制在 top20、1s snapshot 或低频 delta。

## 只有 500GB SSD 时

只有 500GB SSD 时，不应该追求完整 3 个月高频数据湖。目标应改为：

```text
滚动窗口 + 分层降采样
```

推荐容量分配：

```text
Postgres 元数据          20GB - 40GB
Redis / 队列             5GB - 10GB
staging 写入缓冲         40GB - 80GB
hot data lake            300GB - 350GB
validation_cache         50GB - 80GB
reports/artifacts        10GB - 20GB
系统和预留空间            50GB+
```

推荐采集范围：

```text
优先级 1：
BTC / ETH
perp
Binance / Bybit
trades
top20 orderbook 1s snapshot
funding
mark/index
open interest

优先级 2：
SOL perp
OKX / Bitget
只采 funding、mark/index、1m candles

优先级 3：
spot
只保留 1m candles + 少量 trades 样本
```

推荐保留期：

```text
top20 orderbook 1s snapshot：7-14 天
trades：14-30 天
funding / mark / index / open interest：90 天
1m candles：180 天或更久
research reports / validation reports：长期保留
```

磁盘压力降级规则：

```text
超过 70%：
- 停止采集低优先级 exchange/symbol
- orderbook 从 1s 降到 5s
- spot trades 改为 candle-only
- 删除 validation_cache

超过 85%：
- orderbook 只保 7 天
- trades 只保 14 天
- 只保 BTC/ETH perp
- 压缩旧分区

超过 90%：
- 暂停 orderbook 采集
- 只采 funding/mark/index/candles
- 保 collector 不崩
```

## 当前结论

- 策略研究、数据采集、策略验证应该独立运行。
- 数据采集可以且应该长期运行。
- 数据层可以放远程 VPS，不必须和验证层同机。
- 验证层按需读取指定窗口数据，不要同步全量数据。
- 有 3TB HDD 时，HDD 做主数据湖，SSD 做热数据和缓存。
- 只有 500GB SSD 时，采用滚动窗口和降采样，长期只保留低频聚合数据和报告。
