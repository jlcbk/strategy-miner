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
