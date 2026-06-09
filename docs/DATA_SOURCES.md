# 数据源

第一版优先使用官方或公开免费数据源：

- Binance 公开数据仓库和归档路径：
  - `https://github.com/binance/binance-public-data`
  - `https://data.binance.vision`
- OKX 历史数据下载页面：
  - `https://www.okx.com/en-us/historical-data`
- Bybit 公开成交文件：
  - `https://public.bybit.com/trading/`
- Bitget 数据下载页面：
  - `https://www.bitget.com/data-download`

## Open Interest

Open interest 用统一 `EventType.OPEN_INTEREST` 和 `OpenInterestPayload` 表达。当前先接入 REST 数据源边界，后续 collector 再统一调度和落盘：

- Binance USD-M Futures：
  - `https://fapi.binance.com/fapi/v1/openInterest`
  - 历史序列已接 `https://fapi.binance.com/futures/data/openInterestHist`
  - 官方 REST 仅保留最近约 1 个月数据；更早窗口需要外部归档源，或改用从 collector 上线后开始积累的自采数据。
- OKX：
  - `https://www.okx.com/api/v5/public/open-interest`
- Bybit V5：
  - `https://api.bybit.com/v5/market/open-interest`
  - 历史序列已接 `https://api.bybit.com/v5/market/open-interest`
- Bitget：
  - `https://api.bitget.com/api/v2/mix/market/open-interest`

不同交易所和产品的历史 L2 覆盖范围不一致。免费历史覆盖不足时，Strategy Miner 保持 schema 稳定，并从 collector 上线当天开始用自采实时数据补齐样本。

## Funding

Funding rate 用统一 `EventType.FUNDING` 和 `FundingPayload` 表达。当前 collector 优先接入 Binance 和 Bybit：

- Binance USD-M Futures：
  - 历史序列已接 `https://fapi.binance.com/fapi/v1/fundingRate`
  - 默认按日窗口采集；每个 symbol 通常每天 3 条 8 小时 funding 记录。
  - 响应中的 `markPrice` 只作为交易所原始上下文，当前不会当作分钟级 `mark` 分区写入，避免误导 candle / mark 覆盖率。
- Bybit V5：
  - 历史序列已接 `https://api.bybit.com/v5/market/funding/history`
  - 当前用于 Binance REST 返回 451 时的低风险替代源。

## Mark Price

Mark price 用统一 `EventType.MARK` 和 `MarkPricePayload` 表达。当前 collector 先接入 Binance USD-M Futures 公开归档：

- Binance USD-M Futures：
  - 归档路径：`https://data.binance.vision/data/futures/um/daily/markPriceKlines/{symbol}/1m/{symbol}-1m-{day}.zip`
  - 当前将 1m mark price kline 的 close price 写入 `MarkPricePayload.mark_price`。
  - 该分区可满足 `perp_mark_price` 覆盖率；是否由 mark kline 直接派生 candle，需要后续 candle 聚合策略单独确认。
- Bybit V5：
  - REST 序列已接 `https://api.bybit.com/v5/market/mark-price-kline`
  - 默认使用 5m interval 覆盖单日窗口，作为中风险替代源。

## Order Book

Order book 用统一 `EventType.ORDERBOOK` 和 `OrderBookPayload` 表达。当前先接入 Binance 当前盘口快照，不做历史回补：

- Binance Spot：
  - 当前快照已接 `https://api.binance.com/api/v3/depth`
  - MVP limit 固定为 20，写入 top20 bid/ask。
- Binance USD-M Futures：
  - 当前快照已接 `https://fapi.binance.com/fapi/v1/depth`
  - MVP limit 固定为 20，写入 top20 bid/ask。

注意：`orderbook-snapshot` 只能采当前盘口，用于从 collector 上线后开始积累热数据；它不能补齐历史 `orderbook` 分区。需要历史盘口验证时，应使用后续实时采集积累的数据，或接入交易所/第三方历史 orderbook 归档。

## Instrument Metadata

Instrument metadata 用统一 `EventType.INSTRUMENT` 和 `Instrument` payload 表达。当前先接入 Binance 当前交易规则快照，不做历史回补：

- Binance Spot：
  - 当前快照已接 `https://api.binance.com/api/v3/exchangeInfo`
- Binance USD-M Futures：
  - 当前快照已接 `https://fapi.binance.com/fapi/v1/exchangeInfo`

注意：`instrument-snapshot` 只能采当前交易规则，用于从 collector 上线后开始积累 metadata 分区；它不能证明过去某一天的 tick size、lot size、合约状态或精度规则。
