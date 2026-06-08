from __future__ import annotations

import argparse
import json
from pathlib import Path

from packages.data_lake import DataLakeReader
from packages.replay import ReplayEngine
from packages.strategies import (
    CrossExchangeSpreadStrategy,
    FundingCarryStrategy,
    FuturesBasisStrategy,
    StrategyRegistry,
)


def build_registry() -> StrategyRegistry:
    registry = StrategyRegistry()
    registry.register(CrossExchangeSpreadStrategy())
    registry.register(FundingCarryStrategy())
    registry.register(FuturesBasisStrategy())
    return registry


def replay_strategy(data_lake_root: Path, strategy_name: str) -> dict:
    registry = build_registry()
    strategy = registry.get(strategy_name)
    result = ReplayEngine(DataLakeReader(data_lake_root)).replay(strategy)
    return result.to_dict()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Strategy Miner worker 工具")
    parser.add_argument("command", choices=["replay"])
    parser.add_argument("--data-lake-root", default="var/market-data")
    parser.add_argument("--strategy", default="cross_exchange_spread")
    args = parser.parse_args(argv)

    if args.command == "replay":
        result = replay_strategy(Path(args.data_lake_root), args.strategy)
        print(json.dumps(result, indent=2, sort_keys=True))
        return 0
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
