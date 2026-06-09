# 策略研究日志

## 2026-06-09：第一批策略 issue

本轮从公开资料和项目已有策略方向中筛选了 5 个 Crypto 策略候选，并创建为 GitHub Issue。当前目标不是形成投资建议，而是建立可持续的研究入口和验证队列。

### 创建的 issue

| Issue | 策略 | 状态 | 主题 | 漏斗分数 |
| --- | --- | --- | --- | --- |
| [#1](https://github.com/jlcbk/strategy-miner/issues/1) | Funding carry with volatility filter | `strategy:validation-ready` | `theme:funding` | 91.00 |
| [#2](https://github.com/jlcbk/strategy-miner/issues/2) | Quarterly futures basis convergence | `strategy:validation-ready` | `theme:basis` | 85.00 |
| [#3](https://github.com/jlcbk/strategy-miner/issues/3) | Open-interest confirmed momentum | `strategy:proposed` | `theme:momentum` | 74.00 |
| [#4](https://github.com/jlcbk/strategy-miner/issues/4) | Cross-exchange funding dispersion hedge | `strategy:proposed` | `theme:funding` | 72.00 |
| [#5](https://github.com/jlcbk/strategy-miner/issues/5) | Order-book imbalance short-horizon filter | `strategy:blocked-data` | `theme:liquidity` | 45.00 |

### 研究判断

- `funding_carry_vol_filter` 和 `quarterly_basis_convergence` 最符合当前 operator profile：不依赖极低延迟，数据可得，验证路径清晰。
- `oi_confirmed_momentum` 适合作为动量过滤器继续研究，但需要先确认 OI 口径、funding 拥挤过滤和不同市场的稳定性。
- `cross_exchange_funding_dispersion` 有研究价值，但跨所保证金、库存和再平衡复杂度较高，不应直接进入验证队列。
- `orderbook_imbalance_filter` 暂时受数据频率和执行成本约束，保留为数据采集能力成熟后的过滤器候选。

### 下一步

- 优先为 #1 和 #2 设计 data coverage check、fixture sample 和 evaluator contract。
- 为 #3 补充不同 OI 口径的交易所数据源对比。
- 为 #4 明确“不依赖跨所转账”的库存和保证金假设。
- 为 #5 等待 orderbook/trades 数据采集方案明确后再重新评分。

## 2026-06-09：验证准备工具和 #3/#4/#5 数据覆盖检查

本轮新增 `plan_strategy_validation` agent 工具，用于把 `strategy_proposal.data_requirements` 映射到当前项目已有的 `EventType`、可派生数据和缺失数据模型。

### 检查结果

| Issue | 策略 | readiness | 关键阻塞 |
| --- | --- | --- | --- |
| [#3](https://github.com/jlcbk/strategy-miner/issues/3) | Open-interest confirmed momentum | `ready_for_fixture` | 已补 `open_interest` 数据模型和四家交易所 REST 边界；下一步做 OI fixture 和口径稳定性检查。 |
| [#4](https://github.com/jlcbk/strategy-miner/issues/4) | Cross-exchange funding dispersion hedge | `needs_data_collection_plan` | `depth / volume` 可映射到 `orderbook` + `trade`，但需要固定采样窗口和盘口深度。 |
| [#5](https://github.com/jlcbk/strategy-miner/issues/5) | Order-book imbalance short-horizon filter | `needs_data_collection_plan` | `orderbook` 已建模，但验证前必须定义 depth、采样频率、staleness 和保留期。 |

### 下一步

- #3 已解除缺模型阻塞；下一步创建 OI + candle + funding 的最小 fixture。
- #4 可以继续作为 proposed，但需要先写清楚预分配库存、保证金和 depth/volume 采样窗口。
- #5 保持 `strategy:blocked-data`，直到 orderbook/trades 采集策略明确。

## 2026-06-09：#3 OI momentum 最小 evaluator

本轮为 [#3](https://github.com/jlcbk/strategy-miner/issues/3) 新增 `oi_confirmed_momentum` 策略 evaluator 和确定性 fixture。

### 验证结果

- `list_strategies` 已暴露 `oi_confirmed_momentum`，required data 为 `open_interest`、`mark`、`funding`。
- fixture 覆盖 OI 和价格同向上升时输出候选机会。
- fixture 覆盖 funding 过热时过滤候选机会。
- 重新运行研究漏斗后，#3 分数从 74.00 提升到 82.00，推荐状态为 `queued_for_validation`。

### 下一步

- 将 #3 标记为 `strategy:validation-ready`。
- 后续验证前仍需比较 Binance / OKX / Bybit / Bitget 的 OI 口径、采样间隔和数据延迟。
- 该 evaluator 仍是研究候选，不能用于真实交易或自动部署。

## 2026-06-09：Data coverage 检查工具

本轮新增 `check_data_coverage` agent 工具，用于在 replay/backtest 前检查 data lake 是否已经存在目标分区。

### 工具行为

- 输入：data lake root、`strategy_proposal`、交易所、市场类型、品种和日期窗口。
- 输出：覆盖数量、缺失数量、缺失分区、unsupported requirement。
- 当前只做本地文件系统检查，不联网补数，不触发交易。

### 首次检查结果

当前本地 `/Users/cui/test3/.data/lake` 没有生产数据分区，因此 #1、#2、#3 都不能直接进入 replay。下一步应为这些 `strategy:validation-ready` issue 生成 data collection jobs 或 fixture 数据。

### Issue 状态调整

- #1、#2、#3 都保留为高优先级候选，但因为本地 data lake 覆盖率为 0%，先改为 `strategy:blocked-data`。
- 解除阻塞的条件不是重新研究策略，而是补齐目标窗口的 funding、mark、trade、fee、instrument 或 open interest 分区。
- 数据分区补齐后，应重新运行 `check_data_coverage`，覆盖率为 100% 时再恢复 `strategy:validation-ready`。

## 2026-06-09：Data collection job 生成工具

本轮新增 `generate_data_collection_jobs` agent 工具，用于把 `check_data_coverage` 的缺失分区转换成 ingestion job JSON。

### 工具行为

- 每个缺失分区生成一个 `queued` job。
- Job id 使用缺失分区字段确定性生成，重复运行不会改变 id。
- 时间窗口按缺失日期展开为 UTC 当日 00:00 到次日 00:00。
- 工具只生成 JSON，不写数据库，不联网抓数据，不触发交易。

### 首次 job 计划

- #1 Funding carry：Binance，BTC/ETH/SOL，spot + perp，2024-01-01，生成 21 个缺失分区 job。
- #2 Quarterly basis：Binance，BTC/ETH，spot + perp + future，2024-01-01，生成 22 个缺失分区 job。
- #3 OI momentum：Binance，BTC/ETH/SOL perp，2024-01-01，生成 18 个缺失分区 job。

## 2026-06-09：#4 Cross-exchange funding dispersion artifact 化

本轮将 [#4](https://github.com/jlcbk/strategy-miner/issues/4) 从 GitHub Issue 文本整理为机器可读 artifact：

- `artifacts/strategies/cross_exchange_funding_dispersion/research_report.json`
- `artifacts/strategies/cross_exchange_funding_dispersion/strategy_proposal.json`

### 操作适配判断

- 资金规模：适合小到中等资金先做模拟和告警。
- 持仓周期：小时级到日级，跨 funding interval。
- 自动化要求：允许离线扫描和人工确认，不进入无人值守执行。
- 执行假设：必须预分配交易所库存和保证金，不依赖临时跨所转账。
- 主要风险：funding spread 反转、mark/index 脱锚、API 或账户限制、保证金分散导致单边风险。

### 工具验证结果

- `plan_strategy_validation` readiness：`needs_data_collection_plan`。
- 关键阻塞：`depth_volume` 需要固定 orderbook depth、trade volume、采样窗口和 staleness 策略。
- `rank_strategy_candidates` total_score：`71.00`。
- 推荐状态：`needs_human_review`。
- `check_data_coverage` 范围：Binance / OKX / Bybit / Bitget，BTCUSDT / ETHUSDT / SOLUSDT，perp，2026-06-08。
- 覆盖率：`0.00`，`covered_count=0`，`required_count=84`，且 `depth_volume` 仍是 unsupported requirement。

### 状态结论

#4 仍是有研究价值的候选，但当前不能进入 `strategy:validation-ready`。下一步应先确定 `depth_volume` 采集政策，并补齐 funding、mark/index、trade/mark、fee、instrument 分区后再重新检查 data coverage。

## 2026-06-09：depth_volume MVP 采集政策

本轮将 `depth_volume` 从“采样政策待定”推进为项目默认 MVP 政策，供 [#4](https://github.com/jlcbk/strategy-miner/issues/4) 和 [#5](https://github.com/jlcbk/strategy-miner/issues/5) 复用。

### 默认政策

- `orderbook`：top20 bid/ask，1s snapshot。
- staleness：超过 3s 的 orderbook snapshot 不参与容量估计。
- `trade`：同时聚合 1m 和 5m volume。
- capacity window：默认 5m，短周期过滤器可额外看 1m。
- retention：orderbook 热数据 7-14 天，trades 14-30 天。
- scope：优先 BTC / ETH perp，Binance / Bybit；SOL、OKX、Bitget 作为第二阶段。

### 工具状态变化

- `plan_strategy_validation` 对 #4 的 readiness 从 `needs_data_collection_plan` 变为 `ready_for_fixture`。
- `plan_strategy_validation` 对 #5 的 readiness 从 `needs_data_collection_plan` 变为 `ready_for_fixture`。
- `check_data_coverage` 对 #4 最小范围 Binance BTCUSDT perp / 2026-06-08 仍为 `ready=false`，`covered_count=0`，`required_count=9`。
- `generate_data_collection_jobs` 已能把 `depth_volume` 展开为 `orderbook` 和 `trade` 分区，并与 `perp_candles` 复用同一个 `trade` job。
- `plan_data_collection_commands` 对 `orderbook` 返回高风险阻塞：`orderbook snapshot collector 尚未接入；MVP 目标为 top20 1s snapshot`。

### 状态结论

采样政策不再是 #4/#5 的主要阻塞。当前主要阻塞变为实际数据分区缺失，以及 `orderbook`、`index`、`fee`、`instrument` collector 尚未接入。两个策略仍保持 `strategy:blocked-data`，直到目标 data coverage 满足验证窗口。

## 2026-06-09：Binance orderbook snapshot collector

本轮新增 Binance 当前盘口快照 collector，用于让数据层从现在开始积累 `orderbook` 热数据。

### 能力边界

- 新命令：`python3 -m apps.collector.main orderbook-snapshot --exchange binance --market-type perp --symbol BTCUSDT --limit 20 --data-lake-root .data/lake`
- Spot 使用 `https://api.binance.com/api/v3/depth`。
- USD-M futures 使用 `https://fapi.binance.com/fapi/v1/depth`。
- 当前只保存 top20 bid/ask，匹配 `depth_volume` MVP。
- 该命令只采当前盘口，不能回补历史 `orderbook` 分区。

### 工具状态变化

- `plan_data_collection_commands` 对 Binance 当日 `orderbook` job 输出 `orderbook-snapshot` 命令。
- 历史日期的 `orderbook` job 仍保持 blocked，原因是 snapshot collector 不能回补历史分区。
- 风险等级为 `high`，因为它属于高频热数据入口，虽然单次 REST 数据较小。

### 对策略状态的影响

#4 和 #5 的一个 collector 阻塞被部分解除：可以从当前时间开始采集 Binance top20 orderbook snapshot。它们仍保持 `strategy:blocked-data`，因为目标验证窗口还缺历史 `orderbook`、`trade`、`fee`、`index`、`instrument` 等分区。

## 2026-06-09：Binance instrument snapshot collector

本轮新增 Binance 当前交易规则快照 collector，用于让数据层从现在开始积累 `instrument` 分区。

### 能力边界

- 新命令：`python3 -m apps.collector.main instrument-snapshot --exchange binance --market-type perp --symbol BTCUSDT --data-lake-root .data/lake`
- Spot 使用 `https://api.binance.com/api/v3/exchangeInfo`。
- USD-M futures 使用 `https://fapi.binance.com/fapi/v1/exchangeInfo`。
- 当前写入 symbol、base/quote、价格精度、数量精度、合约面值和原始交易规则。
- 该命令只采当前交易规则，不能回补历史 `instrument` 分区。

### 工具状态变化

- `plan_data_collection_commands` 对 Binance 当日 `instrument` job 输出 `instrument-snapshot` 命令。
- 历史日期的 `instrument` job 仍保持 blocked，原因是 snapshot collector 不能证明过去的交易规则。
- 风险等级为 `low`，因为它是小 REST metadata 请求。

### 对策略状态的影响

#1、#2、#4 的 `instrument_metadata` collector 阻塞被部分解除：可以从当前时间开始采集 Binance 交易规则快照。相关策略仍保持 `strategy:blocked-data`，因为历史验证窗口还缺 fee、index、trade、mark、orderbook 等分区。

## 2026-06-09：Binance index price collector

本轮新增 Binance USD-M Futures index price kline collector，用于补齐 `mark_index_price` 中的 `index` 分区。

### 能力边界

- 新命令：`python3 -m apps.collector.main historical-index --exchange binance --market-type perp --symbol BTCUSDT --day 2026-06-08 --data-lake-root .data/lake`
- REST 使用 `https://fapi.binance.com/fapi/v1/indexPriceKlines`。
- 默认 interval 为 `1m`，按单日窗口采集。
- 写入统一 `EventType.INDEX` 分区，payload 包含 `index_price` 和 `interval`。

### 工具状态变化

- `plan_data_collection_commands` 对 Binance `index` job 输出 `historical-index` 命令。
- 风险等级为 `medium`，和 1m `mark` 类似。

### 对策略状态的影响

#4 的 `mark_index_price` collector 阻塞被部分解除：Binance `mark` 和 `index` 都已有采集入口。#4 仍保持 `strategy:blocked-data`，因为目标窗口还缺 fee、trade、orderbook 等分区，并且本机访问 Binance REST 仍受限。

## 2026-06-09：fee assumption collector

本轮新增 `fee-assumption` collector，用于把手续费从隐含参数变成显式 data lake 分区。

### 能力边界

- 新命令：`python3 -m apps.collector.main fee-assumption --exchange binance --market-type perp --symbol BTCUSDT --day 2026-06-08 --data-lake-root .data/lake --maker-bps 10 --taker-bps 10 --fee-tier conservative_manual`
- 写入统一 `EventType.FEE` 分区，payload 为 `FeeSchedule`。
- source 固定为 `manual_fee_assumption`。
- 命令不访问网络，风险等级为 `low`。

### 设计约束

真实手续费依赖账户等级、交易所、产品、maker/taker 和活动规则。当前 collector 不声称抓取官方真实账户费率，只用于回放阶段显式记录扣费假设。进入人工审核前，应替换为真实费率表或账户级费率来源。

### 对策略状态的影响

#1、#2、#4 的 fee 分区可以先用保守假设补齐，减少“成本项不明确”的问题。相关策略仍保持 `strategy:blocked-data`，因为还缺其他行情分区或真实数据运行环境。

## 2026-06-09：#1 Funding carry artifact 化

本轮将 [#1](https://github.com/jlcbk/strategy-miner/issues/1) 从 Issue 文本整理为机器可读 artifact：

- `artifacts/strategies/funding_carry_vol_filter/research_report.json`
- `artifacts/strategies/funding_carry_vol_filter/strategy_proposal.json`

### 操作适配判断

- 资金规模：适合小到中等资金先做模拟和告警。
- 持仓周期：小时级到日级，分钟级扫描。
- 自动化要求：允许离线扫描和人工确认，不进入无人值守执行。
- 执行假设：spot 多头 + perp 空头，低杠杆或不使用杠杆，限制单交易所和单标的名义敞口。
- 主要风险：funding 反转、极端波动下两腿不同步、mark/index 脱锚、费用等级假设错误、滑点吞噬净 edge。

### 工具验证结果

- `rank_strategy_candidates` total_score：`85.00`。
- 推荐状态：`queued_for_validation`。
- `plan_strategy_validation` readiness：`ready_for_fixture`。
- `check_data_coverage` 范围：Binance，BTCUSDT / ETHUSDT / SOLUSDT，spot + perp，2026-06-08。
- 覆盖率：`0.03`，`covered_count=1`，`required_count=33`。
- 缺失事件类型：`funding`、`mark`、`index`、`trade`、`fee`、`instrument`。
- `generate_data_collection_jobs` 生成 26 个物理补数 job。
- `plan_data_collection_commands`：20 个 supported，6 个 blocked；blocked 原因为历史 `instrument` 分区不能由当前 snapshot collector 回补。

### candle 和 mark/index 口径修正

本轮同步修正了 data coverage 的数据需求映射：

- `spot_candles`、`perp_candles` 和通用 `candles` 默认展开为 `trade` 分区，由验证层聚合 candle。
- `mark_index_price` 和 `index_price` 只作用于 perp / future，不作用于 spot。
- 如果策略需要成交量 candle 和 mark/index 过滤，应同时声明 `candles` 与 `mark_index_price`。

### 状态结论

#1 是当前最贴近 operator profile 的高优先级候选之一，已经具备机器可读研究产物和 fixture 准备条件。但它仍保持 `strategy:blocked-data`，因为真实 data lake 尚未补齐目标窗口的行情、费用和 instrument 分区。下一步可以优先补 `trade` 分区或创建最小 fixture，验证波动过滤和 funding 反转退出逻辑。

## 2026-06-09：#1 Funding carry 最小双腿 evaluator

本轮将内置 `FundingCarryStrategy` 对齐为 `funding_carry_vol_filter`，并补齐 #1 的最小 fixture 行为。

### evaluator 行为

- 有 spot reference price 时，输出 `spot buy + perp sell` 双腿候选。
- 只处理正 funding carry，默认跳过负 funding，避免引入 spot short、借币或更复杂库存假设。
- 使用 perp mark 和 index price 做 mark/index 脱锚过滤。
- 使用 spot/perp basis 过滤极端 basis 窗口。
- 使用最近 spot mark 变动作为最小波动代理，过滤短期价格大幅跳变窗口。
- 缺少 spot reference 时仍可输出单腿研究候选，但会标记 `requires_spot_or_correlated_hedge_before_execution`。
- 缺少 index price 时会标记 `missing_index_price_for_depeg_filter`。

### 测试覆盖

- 正 funding + spot/perp/index 正常时生成双腿候选。
- 缺 spot 时保留阻塞 failure mode。
- spot/perp basis 过大时过滤。
- mark/index 脱锚时过滤。
- 近期价格变动代理超过阈值时过滤。

### 状态结论

#1 已从纯文本研究产物推进到最小可测 evaluator。它仍不是验证通过策略，也不能进入实盘；下一步需要用真实或 fixture candle/trade 数据替换当前的最小波动代理，并补齐 data lake 分区后跑 replay/backtest。
