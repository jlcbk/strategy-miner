# Windows 本地数据层和验证层运行说明

这份文档描述如何在一台 Windows 电脑上运行 Strategy Miner 的本地 MVP。目标是先打通：

```text
strategy_proposal
-> data coverage
-> data collection plan
-> collector commands
-> data lake JSONL/Parquet
-> replay validation
-> opportunity_report
```

本地 MVP 不需要 Postgres、Redis、DuckDB 或交易账户。没有安装 `pyarrow` 时，data lake 自动写入 JSONL；安装 `pyarrow` 后会优先写 Parquet。

## 环境准备

在 PowerShell 中执行：

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e ".[dev]"
pytest
```

如果需要 Parquet：

```powershell
python -m pip install -e ".[dev,data]"
```

## 本地目录

推荐使用仓库内的默认目录：

```text
.data/lake      本地 data lake
var/downloads   历史归档下载缓存
var/plans       采集计划输出
var/reports     验证报告输出
```

这些目录不需要提交到 Git。

## 离线冒烟验证

第一次在 Windows 上运行时，建议先不联网采集数据，而是写入确定性 fixture，验证 data lake 和 replay 是否可用。

写入 funding carry fixture：

```powershell
python -m apps.local_pipeline.main seed-fixture `
  --fixture funding-carry `
  --data-lake-root .data/lake `
  --output var/reports/seed_funding_carry.json
```

运行验证：

```powershell
python -m apps.local_pipeline.main validate `
  --data-lake-root .data/lake `
  --strategy funding_carry_vol_filter `
  --output var/reports/funding_carry_fixture_validation.json
```

也可以写入其它 fixture：

```powershell
python -m apps.local_pipeline.main seed-fixture --fixture oi-momentum --data-lake-root .data/lake
python -m apps.local_pipeline.main seed-fixture --fixture quarterly-basis --data-lake-root .data/lake
```

对应验证策略：

```text
oi-momentum -> oi_confirmed_momentum
quarterly-basis -> quarterly_basis_convergence
```

## 生成采集计划

示例：为 `funding_carry_vol_filter` 生成 Binance BTCUSDT 在 2026-06-08 的最小数据计划。

```powershell
python -m apps.local_pipeline.main plan `
  --proposal artifacts/strategies/funding_carry_vol_filter/strategy_proposal.json `
  --data-lake-root .data/lake `
  --download-dir var/downloads `
  --exchanges binance `
  --market-types spot,perp `
  --symbols BTCUSDT `
  --start-date 2026-06-08 `
  --end-date 2026-06-08 `
  --output var/plans/funding_carry_btc_2026-06-08.json
```

计划里会包含：

- `coverage`：当前 data lake 覆盖率。
- `job_plan`：缺失分区转换出的采集 job。
- `command_plan`：可执行 collector 命令和阻塞原因。

命令计划使用当前 Python 解释器路径生成，避免 Windows 上没有 `python3` 的问题。

## 执行采集计划

默认只执行支持且不需要人工确认的命令。高风险命令，例如历史逐笔 trade 或 orderbook snapshot，会默认跳过。

```powershell
python -m apps.local_pipeline.main collect `
  --plan-json var/plans/funding_carry_btc_2026-06-08.json `
  --output var/reports/funding_carry_btc_collect_result.json
```

只预览不执行：

```powershell
python -m apps.local_pipeline.main collect `
  --plan-json var/plans/funding_carry_btc_2026-06-08.json `
  --dry-run
```

如果确认磁盘、网络和风险边界后，要执行高风险命令：

```powershell
python -m apps.local_pipeline.main collect `
  --plan-json var/plans/funding_carry_btc_2026-06-08.json `
  --include-high-risk
```

建议正式运行时始终带 job 状态文件：

```powershell
python -m apps.local_pipeline.main collect `
  --plan-json var/plans/funding_carry_btc_2026-06-08.json `
  --state-json .data/jobs/jobs.json `
  --output var/reports/funding_carry_btc_collect_result.json
```

行为：

- 已经 `succeeded` 的 job 会自动跳过。
- `failed` 的 job 会在下次运行时重试。
- `blocked` 的 job 会记录阻塞原因。
- 如需强制重跑成功任务，显式加 `--force`。

## 检查覆盖率

采集后重新检查覆盖率：

```powershell
python -m apps.local_pipeline.main coverage `
  --proposal artifacts/strategies/funding_carry_vol_filter/strategy_proposal.json `
  --data-lake-root .data/lake `
  --exchanges binance `
  --market-types spot,perp `
  --symbols BTCUSDT `
  --start-date 2026-06-08 `
  --end-date 2026-06-08
```

只有当 `ready` 为 `true`，才说明目标窗口的 required partitions 都已存在。

## 每日采集计划

复制示例配置：

```powershell
Copy-Item configs/local_windows_data.example.toml configs/local_windows_data.toml
```

生成每日采集计划：

```powershell
python -m apps.local_pipeline.main daily-ingest `
  --config configs/local_windows_data.toml `
  --output var/plans/daily_ingest.json
```

执行每日采集计划：

```powershell
python -m apps.local_pipeline.main collect `
  --plan-json var/plans/daily_ingest.json `
  --state-json .data/jobs/jobs.json `
  --output var/reports/daily_collect_result.json
```

`daily-ingest` 默认按配置里的 `lookback_days` 生成昨天或最近几天的缺口计划，适合挂到 Windows Task Scheduler。

## 保留最近 180 天数据

先 dry-run：

```powershell
python -m apps.local_pipeline.main retention `
  --data-lake-root .data/lake `
  --keep-days 180 `
  --output var/reports/retention_dry_run.json
```

确认 `would_delete_files` 后再执行：

```powershell
python -m apps.local_pipeline.main retention `
  --data-lake-root .data/lake `
  --keep-days 180 `
  --apply `
  --output var/reports/retention_apply.json
```

## 运行验证

读取 data lake 并跑 replay：

```powershell
python -m apps.local_pipeline.main validate `
  --data-lake-root .data/lake `
  --strategy funding_carry_vol_filter `
  --exchange binance `
  --symbol BTC-USDT `
  --output var/reports/funding_carry_btc_validation.json
```

可用策略来自本地 registry：

```text
cross_exchange_spread
funding_carry_vol_filter
quarterly_basis_convergence
oi_confirmed_momentum
```

## 安全边界

- 本地 pipeline 不接入真实账户。
- `collect` 只调用公开数据 collector 或手工假设写入命令。
- 默认跳过 `requires_confirmation=true` 的高风险命令。
- `validate` 只读 data lake 并输出本地 `opportunity_report`。
- 任何结果都不是投资建议，也不能标记为 production-ready。

## 常见问题

### PowerShell 不允许激活 venv

可以先执行：

```powershell
Set-ExecutionPolicy -Scope CurrentUser RemoteSigned
```

### Binance 或 Bybit 网络访问失败

先保留 plan 和 collect result，记录失败原因。不要为了通过验证临时抓取不可复现的数据。网络恢复后重新运行同一个 plan。

### 缺 `trade` 或 `orderbook` 分区

这类数据通常是高风险或大数据量入口。先用小范围、单日、单 symbol 验证，再扩大范围。
