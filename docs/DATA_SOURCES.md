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
- Bitget：
  - `https://api.bitget.com/api/v2/mix/market/open-interest`

不同交易所和产品的历史 L2 覆盖范围不一致。免费历史覆盖不足时，Strategy Miner 保持 schema 稳定，并从 collector 上线当天开始用自采实时数据补齐样本。

## Funding

Funding rate 用统一 `EventType.FUNDING` 和 `FundingPayload` 表达。当前 collector 先接入 Binance USD-M Futures：

- Binance USD-M Futures：
  - 历史序列已接 `https://fapi.binance.com/fapi/v1/fundingRate`
  - 默认按日窗口采集；每个 symbol 通常每天 3 条 8 小时 funding 记录。
  - 响应中的 `markPrice` 只作为交易所原始上下文，当前不会当作分钟级 `mark` 分区写入，避免误导 candle / mark 覆盖率。
