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
