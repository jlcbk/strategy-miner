# Strategy Miner 自动交易策略挖掘平台

Strategy Miner 是一个 Python 优先的服务化后台，用于从免费公开历史数据和自建实时行情中挖掘加密货币 Alpha、价差和套利机会。

当前版本 `0.1.0` 聚焦机会发现、历史回放、报告生成和研究流程安全。系统不会下单，也不会自动部署由智能体生成的策略。

## 范围

- 交易所：Binance、OKX、Bybit、Bitget。
- MVP 市场：现货、永续合约、交割合约。
- 预留市场：期权元数据和静态套利 evaluator 接口。
- 存储：安装 `pyarrow` 时使用 Parquet 存大行情；本地测试使用 JSONL 作为降级格式；分区结构兼容 DuckDB 查询。
- 元数据：Postgres 保存交易品种、任务、心跳、机会摘要和研究报告。
- 队列：为 worker 预留 Redis/RQ 边界。

## 目录结构

```text
apps/
  api/        兼容 FastAPI 的控制 API
  worker/     回放、清洗、策略和研究任务执行器
  collector/  实时行情采集服务骨架
  console/    轻量控制台页面
packages/
  connectors/      各交易所公开数据适配器
  data_lake/       分区行情事件存储
  normalization/   标准交易品种和 MarketEvent 模型
  strategies/      策略插件接口和内置 evaluator
  replay/          确定性历史事件回放
  scoring/         edge、容量、置信度和风险评分
  research_agent/  只生成报告的研究智能体护栏
  risk/            共享安全策略
migrations/         Postgres 元数据 schema
configs/            服务默认配置
tests/              确定性单元测试
docs/               架构说明
```

## 快速开始

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
pytest
```

API 开发：

```bash
pip install -e ".[api,dev]"
uvicorn apps.api.main:app --reload
```

第一版的 API 和控制台刻意保持轻量。核心行为都在可导入的 Python 包中，方便后续智能体在人工审核前，为新连接器、新策略插件和 worker 任务补代码与测试。
