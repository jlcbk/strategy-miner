# Claude Code 协作使用说明书

这份说明面向使用者，解释如何把 Strategy Miner 和 Claude Code 搭配起来做策略挖掘。

Strategy Miner 不是一个自己思考、自己搜索、自己上线策略的独立程序。它是给 Claude Code 使用的量化研究执行层：Claude Code 负责阅读资料、提出策略假设、写候选代码、解释结果；Strategy Miner 负责提供数据结构、回放、评分、测试、报告格式和安全边界。

## 你能用它做什么

- 让 Claude Code 从文章、论文、交易所公告、论坛或 GitHub 项目中提炼策略想法。
- 把策略想法整理成机器可读的 `research_report` 和 `strategy_proposal`。
- 让 Claude Code 写候选 evaluator，但只能放在候选代码路径里。
- 用 Strategy Miner 的测试和回放工具验证策略，不靠 AI 口头判断。
- 输出机会报告，供你人工决定是否继续开发。

它默认不能做：

- 自动下单。
- 开启真实交易。
- 自动部署策略。
- 修改生产策略配置。

## 基本工作流

```text
你给 Claude Code 一个研究目标
-> Claude Code 阅读资料并生成研究报告
-> Claude Code 生成策略提案
-> Strategy Miner 检查 schema 和安全边界
-> Claude Code 写候选策略 evaluator 和测试
-> Strategy Miner 跑单元测试和历史回放
-> Claude Code 汇总机会报告和失败模式
-> 你人工决定是否继续推进
```

## 第一次使用

克隆项目后进入目录：

```bash
git clone https://github.com/jlcbk/strategy-miner.git
cd strategy-miner
```

准备 Python 环境：

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
pytest
```

如果你使用 `uv`：

```bash
uv run --with pytest pytest -q
```

确认 agent 工具可用：

```bash
python -m apps.cli.main tools
```

检查安全边界：

```bash
python -m apps.cli.main run-tool check_guardrail --payload-json '{"action":"place_order"}'
```

你应该看到 JSON 输出，其中 `allowed` 是 `false`，原因是 agent 不能触发下单或开启真实交易。

## 如何打开 Claude Code

在项目根目录启动 Claude Code：

```bash
claude
```

然后告诉 Claude Code：你正在操作的是 Strategy Miner，目标不是开发独立 AI 应用，而是使用本项目作为策略研究执行层。

推荐第一条提示词：

```text
请先阅读 README.md、docs/AGENT_COLLABORATION_ZH.md、docs/CLAUDE_CODE_USER_GUIDE_ZH.md 和 schemas/ 目录。
这个项目是给 Claude Code/Codex/opencode 使用的量化研究执行层。
你负责提出策略假设、生成研究报告、写候选 evaluator 和测试。
项目负责 schema、guardrail、回放、评分和安全边界。
默认不允许自动下单、自动部署或修改生产策略配置。
```

## 让 Claude Code 挖掘一个策略

你可以这样提需求：

```text
请研究“永续 funding carry”是否适合加入 Strategy Miner。
要求：
1. 先阅读公开资料并总结策略逻辑、成本项和失败模式。
2. 生成符合 schemas/research_report.schema.json 的 research_report。
3. 生成符合 schemas/strategy_proposal.schema.json 的 strategy_proposal。
4. 不要修改生产配置，不要触碰下单相关接口。
5. 如果要写代码，只能写候选 evaluator 和测试。
```

Claude Code 应该先产出研究材料，而不是直接改核心策略。你可以要求它把报告放在 `docs/research/` 或未来约定的 artifact 目录。

## 让 Claude Code 写候选 evaluator

当你认可策略提案后，可以继续：

```text
基于刚才的 strategy_proposal，请实现一个候选 evaluator。
要求：
1. 遵守 packages/strategies/interface.py 的 StrategyPlugin 接口。
2. 增加确定性 fixture 测试。
3. 输出失败码和中文解释。
4. 跑 pytest。
5. 不要改生产配置，不要加入下单逻辑。
```

Claude Code 应该修改或新增策略模块，并补测试。你要重点看：

- 是否依赖不可复现的 AI 判断。
- 是否把自然语言结论写死成策略结果。
- 是否有费用、滑点、容量和风险检查。
- 是否有无机会样本测试。
- 是否误触生产配置或下单路径。

## 让 Claude Code 跑回放

如果你已有历史数据，可以让 Claude Code 调用 worker：

```text
请使用现有 data lake，对 cross_exchange_spread 策略跑一次回放。
输出 opportunity_report，包含数据窗口、机会数量、net edge、capacity、failure_modes 和风险解释。
```

CLI 形式通常是：

```bash
python -m apps.worker.main replay --data-lake-root var/market-data --strategy cross_exchange_spread
```

当前项目还是 scaffold，真实数据接入和完整回放任务会逐步补齐。没有数据时，Claude Code 应该先构造 fixture 或说明缺少数据，而不是编造结果。

## 推荐的 Claude Code 提示词模板

### 研究新策略

```text
请作为量化研究 agent，研究这个策略想法：<策略想法>。
请按以下步骤执行：
1. 阅读相关公开资料，并列出来源 URL。
2. 总结策略假设、公式、成本项、容量约束和失败模式。
3. 生成 research_report，字段必须符合 schemas/research_report.schema.json。
4. 生成 strategy_proposal，字段必须符合 schemas/strategy_proposal.schema.json。
5. 只提出候选实现方案，不要修改生产配置，不要加入下单逻辑。
```

### 实现候选策略

```text
请根据已有 strategy_proposal 实现候选策略。
要求：
1. 使用 packages/strategies/interface.py 的插件接口。
2. 费用、滑点、容量、stale data 和缺失数据必须显式处理。
3. 增加确定性 pytest。
4. 跑完整测试。
5. 输出变更摘要和剩余风险。
```

### 做代码审查

```text
请审查这个候选策略是否可以进入人工评审。
重点检查：
1. 是否有数据泄漏或回放不确定性。
2. 是否低估费用、滑点、容量限制或 funding 风险。
3. 是否缺少无机会样本和异常数据测试。
4. 是否触碰生产配置、自动部署或下单接口。
5. 是否符合 agent_interface 的 workflow 和 guardrail。
```

## 你应该如何判断结果可信不可信

可信结果通常具备：

- 有来源 URL。
- 有清楚的策略公式。
- 有成本项。
- 有失败模式。
- 有数据窗口。
- 有测试结果。
- 有回放结果。
- 有机会报告。
- 能说明为什么无机会样本不会误报。

不可信结果通常表现为：

- 只有“这个策略看起来可行”的自然语言判断。
- 没有数据窗口。
- 没有费用或滑点。
- 没有容量估计。
- 没有失败模式。
- 没有测试。
- 用 AI 解释替代 evaluator 逻辑。
- 编造不存在的历史数据或回放结果。

## 项目里的关键文件

- `README.md`：项目定位和快速开始。
- `docs/AGENT_COLLABORATION_ZH.md`：agent 和项目的职责边界。
- `schemas/`：agent 输出 artifact 的 JSON schema。
- `apps/cli/main.py`：agent 可调用 CLI。
- `packages/agent_interface/`：artifact、workflow、guardrail 和工具定义。
- `packages/strategies/interface.py`：策略插件接口。
- `packages/replay/engine.py`：历史回放入口。
- `packages/scoring/engine.py`：机会评分逻辑。
- `packages/risk/policy.py`：安全策略。

## 最重要的使用原则

Claude Code 可以帮你想策略、读资料、写代码和跑测试，但不能替你决定策略上线。Strategy Miner 的作用是让每个 AI 生成的策略想法都变成可检查、可回放、可评分、可审计的工程产物。
