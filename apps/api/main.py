from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone

from packages.strategies import (
    CrossExchangeSpreadStrategy,
    FundingCarryStrategy,
    FuturesBasisStrategy,
    StrategyRegistry,
)
from packages.strategies.reserved import (
    OptionsStaticArbitrageStrategy,
    TermStructureAnomalyStrategy,
    TriangularSpreadStrategy,
)


registry = StrategyRegistry()
for plugin in (
    CrossExchangeSpreadStrategy(),
    FundingCarryStrategy(),
    FuturesBasisStrategy(),
    TriangularSpreadStrategy(),
    TermStructureAnomalyStrategy(),
    OptionsStaticArbitrageStrategy(),
):
    registry.register(plugin)


@dataclass(frozen=True)
class ApiHealth:
    service: str
    status: str
    no_auto_trading: bool
    checked_at: str


def health_payload() -> dict:
    return asdict(
        ApiHealth(
            service="strategy-miner-api",
            status="ok",
            no_auto_trading=True,
            checked_at=datetime.now(timezone.utc).isoformat(),
        )
    )


def strategy_payload() -> list[dict]:
    return [
        {
            "name": plugin.name,
            "version": plugin.version,
            "required_data": sorted(event.value for event in plugin.required_data()),
        }
        for plugin in registry.all()
    ]


try:
    from fastapi import FastAPI

    app = FastAPI(title="Strategy Miner 控制 API", version="0.1.0")

    @app.get("/health")
    def health() -> dict:
        return health_payload()

    @app.get("/strategies")
    def strategies() -> list[dict]:
        return strategy_payload()

    @app.get("/opportunities/recent")
    def recent_opportunities() -> list[dict]:
        return []

    @app.get("/data-sources/health")
    def data_sources_health() -> list[dict]:
        return []

    @app.get("/research/reports")
    def research_reports() -> list[dict]:
        return []

except ImportError:

    class MissingFastAPIApp:
        def __call__(self, *args, **kwargs):
            raise RuntimeError("请先安装 API 依赖：`pip install -e '.[api]'`。")

    app = MissingFastAPIApp()
