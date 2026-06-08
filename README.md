# Strategy Miner 自动交易策略挖掘平台

Strategy Miner 是一个面向 Claude Code、Codex、opencode 等 agent 的量化研究执行层。它用 Python 提供确定性的行情数据、标准化、回放、评分、报告和安全边界；外部 agent 负责互联网资料阅读、策略假设生成、候选代码编写和结果解释。

当前版本 `0.1.0` 聚焦 agent 可调用工具、机会发现、历史回放、报告生成和研究流程安全。系统不会下单，也不会自动部署由智能体生成的策略。

## 范围

- 交易所：Binance、OKX、Bybit、Bitget。
- MVP 市场：现货、永续合约、交割合约。
- 预留市场：期权元数据和静态套利 evaluator 接口。
- 存储：安装 `pyarrow` 时使用 Parquet 存大行情；本地测试使用 JSONL 作为降级格式；分区结构兼容 DuckDB 查询。
- 元数据：Postgres 保存交易品种、任务、心跳、机会摘要和研究报告。
- 队列：为 worker 预留 Redis/RQ 边界。
- Agent 协作：通过 CLI、JSON schema 和可选 API 暴露确定性工具；AI 分析能力由外部 agent 提供。

## 目录结构

```text
apps/
  api/        兼容 FastAPI 的控制 API
  cli/        agent 可调用 JSON CLI
  worker/     回放、清洗、策略和研究任务执行器
  collector/  实时行情采集服务骨架
  console/    轻量观察面板
packages/
  agent_interface/ 给 agent 使用的 artifact、workflow、guardrail 和工具入口
  connectors/      各交易所公开数据适配器
  data_lake/       分区行情事件存储
  normalization/   标准交易品种和 MarketEvent 模型
  strategies/      策略插件接口和内置 evaluator
  replay/          确定性历史事件回放
  scoring/         edge、容量、置信度和风险评分
  research_agent/  兼容层，逐步迁移到 agent_interface
  risk/            共享安全策略
migrations/         Postgres 元数据 schema
configs/            服务默认配置
schemas/            agent artifact 的 JSON schema
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

Agent CLI：

```bash
python -m apps.cli.main tools
python -m apps.cli.main run-tool check_guardrail --payload-json '{"action":"place_order"}'
```

第一版的 API 和控制台刻意保持轻量。核心行为都在可导入的 Python 包和 JSON CLI 中，方便外部 agent 在人工审核前，为新连接器、新策略插件和 worker 任务补代码、跑测试、跑回放并生成报告。

## Claude Code 使用说明

面向用户的完整协作手册见：[docs/CLAUDE_CODE_USER_GUIDE_ZH.md](docs/CLAUDE_CODE_USER_GUIDE_ZH.md)。
