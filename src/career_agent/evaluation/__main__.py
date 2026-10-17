"""Explicit local eval CLI. All execution defaults to fixture/offline mode."""

import argparse
import asyncio
import json
from pathlib import Path
from typing import Any

from httpx import ASGITransport, AsyncClient

from career_agent.api.app import create_app
from career_agent.config import Settings
from career_agent.evaluation.contracts import EvalCase, EvalSuite


async def execute(args: argparse.Namespace) -> Any:
    app = create_app(Settings())
    async with app.router.lifespan_context(app):
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://local-eval"
        ) as client:

            async def request(method: str, path: str, payload: dict[str, Any] | None = None) -> Any:
                response = await client.request(method, "/api/v1/evaluation/" + path, json=payload)
                if response.status_code >= 400:
                    raise ValueError(
                        response.json().get("error", {}).get("code", "eval_request_failed")
                    )
                return response.json()

            if args.command == "run":
                content = json.loads(await asyncio.to_thread(Path(args.suite).read_text))
                suite = EvalSuite.model_validate(content["suite"])
                for value in content["cases"]:
                    case = EvalCase.model_validate(value)
                    await request("POST", "cases", case.model_dump(mode="json"))
                await request("POST", "suites", suite.model_dump(mode="json"))
                run = await request(
                    "POST",
                    "runs",
                    {
                        "suite_id": suite.suite_id,
                        "suite_version": suite.version,
                        "trials": args.trials,
                        "mode": args.mode,
                        "explicit_diagnostic": args.explicit_diagnostic,
                    },
                )
                return await request("POST", f"runs/{run['id']}/execute")
            if args.command == "inspect":
                return await request("GET", f"{args.resource}/{args.id}")
            if args.command == "reconstruct":
                return await request("GET", f"cases/{args.id}/origin")
            if args.command == "compare":
                return await request(
                    "POST",
                    "comparisons",
                    {"baseline_run_id": args.baseline, "candidate_run_id": args.candidate},
                )
            if args.command == "drain-judge":
                return await request(
                    "POST", "judges/drain", {"limit": args.limit, "concurrency": args.concurrency}
                )
            if args.command == "calibration":
                return await request("GET", "calibration")
            if args.command == "annotation-queue":
                return await request("GET", "annotations/queue")
            if args.command == "sanitize-capture":
                return await request("GET", f"captures/{args.id}/sanitized")
            raise ValueError("unknown_command")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--format", choices=["json", "text"], default="json")
    commands = parser.add_subparsers(dest="command", required=True)
    run = commands.add_parser("run")
    run.add_argument("suite")
    run.add_argument("--trials", type=int, default=1, choices=range(1, 6))
    run.add_argument(
        "--mode", choices=["candidate_replay", "origin_reexecution"], default="candidate_replay"
    )
    run.add_argument("--explicit-diagnostic", action="store_true")
    inspect = commands.add_parser("inspect")
    inspect.add_argument(
        "resource", choices=["runs", "trials", "operations", "comparisons", "judges", "captures"]
    )
    inspect.add_argument("id")
    reconstruct = commands.add_parser("reconstruct")
    reconstruct.add_argument("id")
    compare = commands.add_parser("compare")
    compare.add_argument("baseline")
    compare.add_argument("candidate")
    drain = commands.add_parser("drain-judge")
    drain.add_argument("--limit", type=int, default=20)
    drain.add_argument("--concurrency", type=int, default=2)
    commands.add_parser("calibration")
    commands.add_parser("annotation-queue")
    sanitize = commands.add_parser("sanitize-capture")
    sanitize.add_argument("id")
    args = parser.parse_args()
    try:
        value = asyncio.run(execute(args))
    except Exception:
        # Raw transport/DB exceptions may contain private bodies/paths. Stable CLI failure only.
        raise SystemExit("evaluation_command_failed") from None
    if args.format == "json":
        print(json.dumps(value, ensure_ascii=False, indent=2, default=str))
    else:
        if isinstance(value, dict):
            for key in ["id", "status", "reason_code", "gate", "summary", "aggregate"]:
                if key in value:
                    print(f"{key}: {value[key]}")
        else:
            print(f"{len(value)} records")


if __name__ == "__main__":
    main()
