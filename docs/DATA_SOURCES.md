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

不同交易所和产品的历史 L2 覆盖范围不一致。免费历史覆盖不足时，Strategy Miner 保持 schema 稳定，并从 collector 上线当天开始用自采实时数据补齐样本。
