# 自动交易策略挖掘平台项目规划

## 项目目标

构建一个 Python 优先的服务化后台，用于从 Binance、OKX、Bybit、Bitget 的免费历史数据和实时行情中挖掘交易机会。第一版重点做广泛 Alpha 和套利机会发现，不自动交易。后续智能体可以从互联网寻找策略灵感、生成候选策略和 PR 或方案，但不能自动上线，也不能自动下单。

## 默认技术路线

- 数据源：官方免费历史数据和自建实时采集；必要时未来补充 Tardis 或 CryptoHFTData。
- 产品范围：现货、永续、交割合约、期权都纳入模型；MVP 优先现货、永续和交割合约，期权先做接口和数据模型预留。
- 架构：Python 服务化后台，Postgres 管元数据和任务，Parquet/DuckDB 管大行情和回放，Redis Queue 管异步任务。
- 界面：简单 Web 控制台，展示数据健康、机会列表、回测任务和策略报告。

## 核心子系统

- `data_ingestion`：下载四家交易所免费历史数据；通过 WebSocket 实时采集 trades、top 20 order book、funding、mark/index、open interest；所有原始数据先标准化为统一 `MarketEvent`。
- `market_data_lake`：大行情写入 Parquet，按 `exchange/date/market_type/symbol/event_type` 分区；DuckDB 用于本地和服务端查询回放；Postgres 只保存元数据、任务状态、策略配置和机会摘要。
- `normalization`：统一交易所 symbol、时间戳、产品类型、价格精度、合约面值和币种；产出统一对象 `Instrument`、`OrderBookSnapshot`、`TradeEvent`、`FundingEvent`、`MarkPriceEvent`、`FeeSchedule`。
- `strategy_lab`：策略以插件形式注册，每个策略实现 `required_data()`、`evaluate(market_state)`、`explain(opportunity)` 和 `risk_checks(opportunity)`。
- `replay_engine`：按时间重放历史 Parquet 数据，支持新策略上线后回头复盘，输出机会次数、持续时间、容量、净 edge、滑点敏感性和交易所分布。
- `opportunity_scoring`：统一计算 gross edge、fee-adjusted edge、slippage-adjusted edge、capacity、latency sensitivity、funding exposure、execution complexity 和 risk score。
- `research_agent`：周期性从 GitHub、论文、交易所公告、博客、论坛中寻找策略灵感，只生成策略研究报告、候选 evaluator、测试建议或 PR。
- `control_console`：轻量 Web 控制台，展示数据源健康、最近机会、回测任务、策略表现、智能体研究报告和数据缺口告警。

## 第一批内置策略

- 跨所现货/永续价差。
- 永续 funding carry。
- 交割合约 basis。
- 三角和多腿换币价差。
- 期限结构异常。
- 期权 put-call parity 和静态套利，第一版先预留接口。

## 机会分级

- A：全 taker 后仍为正。
- B：maker/taker 后为正。
- C：理论为正但可执行性弱。

## MVP 里程碑

1. 数据底座：支持四家交易所现货/永续历史数据下载；支持实时 WebSocket 采集 top 20 order book、trades、funding、mark/index；数据写入 Parquet 和 Postgres 元数据；控制台展示数据源健康和数据缺口。
2. 策略和回放：实现跨所价差、funding carry、basis 三类策略；实现历史回放引擎；每日生成机会报告；新增策略后可对已有历史数据重新跑 evaluator。
3. 智能体研究：智能体定期搜索策略来源；输出策略摘要、公式、成本项、失败模式和候选实现；生成 PR 或方案，人工审核后合入。
4. 期权扩展：接入期权 instrument metadata；建立期权链数据模型；实现 put-call parity、box spread、calendar/butterfly 静态套利 evaluator；如果免费历史 L2 不足，优先使用实时自采数据做样本。

## 安全边界

- 第一版不做自动交易。
- 智能体不能修改生产策略配置。
- 智能体不能触发下单相关接口。
- 任何策略上线、生产配置变更和真实交易动作都必须由人审核。

## 测试策略

- 数据接入测试：每家交易所至少选 BTC、ETH、SOL 的 spot/perp，验证下载、解析和标准化；检查时间戳单调性、缺口、重复事件和异常价格。
- 数据湖测试：写入后用 DuckDB 查询，验证分区、schema、压缩和读取性能；模拟一天数据回放，确认不丢 event。
- 策略测试：用固定样本构造确定性机会，验证 fee、slippage、funding 后净 edge；对无机会样本验证不会误报；对 stale data、缺 funding、缺 orderbook 的场景输出明确失败原因。
- 回放测试：同一历史窗口重复回放结果必须一致；新增策略插件后，可以对旧数据重新生成报告。
- 智能体测试：只能生成报告或候选 PR；不允许修改生产策略配置；不允许触发下单相关接口。
