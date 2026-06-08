from __future__ import annotations

import argparse
import json

from packages.agent_interface import available_tools, run_tool


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Strategy Miner agent 工具 CLI")
    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("tools", help="输出 agent 可调用工具清单")

    run_parser = subparsers.add_parser("run-tool", help="运行一个 agent 工具")
    run_parser.add_argument("name")
    run_parser.add_argument("--payload-json", default="{}")

    args = parser.parse_args(argv)
    if args.command == "tools":
        print(json.dumps({"tools": available_tools()}, ensure_ascii=False, indent=2))
        return 0

    if args.command == "run-tool":
        payload = json.loads(args.payload_json)
        result = run_tool(args.name, payload)
        print(
            json.dumps(
                {"ok": result.ok, "payload": result.payload, "message": result.message},
                ensure_ascii=False,
                indent=2,
            )
        )
        if args.name == "check_guardrail":
            return 0
        return 0 if result.ok else 1

    return 1


if __name__ == "__main__":
    raise SystemExit(main())
