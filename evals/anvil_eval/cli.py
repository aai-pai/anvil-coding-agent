"""Command-line interface: run a suite, list tasks, compare two runs.

Usage (from the repo root)::

    python evals/run_eval.py run --suite smoke --start-server --mode offline-llm
    python evals/run_eval.py run --suite smoke --base-url http://127.0.0.1:8765
    python evals/run_eval.py list --suite smoke
    python evals/run_eval.py compare <baseline>/results.json <candidate>/results.json
"""

from __future__ import annotations

import argparse
import os
import pathlib
import sys
from datetime import datetime, timezone

from anvil_eval.client import AnvilClient, AnvilClientError
from anvil_eval.config import (
    DEFAULT_BASE_URL,
    DEFAULT_RESULTS_ROOT,
    EvalConfig,
    load_pricing,
)
from anvil_eval.report import compare, print_summary, write_reports
from anvil_eval.runner import run_suite
from anvil_eval.server import AnvilServer
from anvil_eval.tasks import SuiteError, load_suite


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="anvil-eval", description="Anvil Tier-1 evaluation harness")
    sub = parser.add_subparsers(dest="command", required=True)

    run = sub.add_parser("run", help="run a suite against an Anvil server")
    run.add_argument("--suite", required=True,
                     help="suite name under evals/suites/ or a directory path")
    run.add_argument("--task", action="append", dest="tasks", default=None,
                     help="run only this task id (repeatable)")
    run.add_argument("--base-url", default=None,
                     help=f"use an already-running server (default {DEFAULT_BASE_URL})")
    run.add_argument("--start-server", action="store_true",
                     help="spawn a local server for the duration of the suite")
    run.add_argument("--mode", default="offline-llm",
                     choices=["real", "offline-llm", "stub"],
                     help="execution mode for --start-server (default offline-llm)")
    run.add_argument("--port", type=int, default=None,
                     help="port for --start-server (default: a free port)")
    run.add_argument("--run-mode", default="yolo",
                     choices=["yolo", "gated", "secure"],
                     help="Anvil run mode (default yolo; the benchmark condition)")
    run.add_argument("--results", default=None,
                     help=f"results root (default {DEFAULT_RESULTS_ROOT})")
    run.add_argument("--label", default=None,
                     help="short name recorded in the report (e.g. 'v0.1.2')")
    run.add_argument("--pricing", default=None,
                     help="JSON file: {model-slug: usd per 1M tokens} for cost estimates")
    run.add_argument("--timeout", type=float, default=None,
                     help="per-task wall-clock timeout in seconds")
    run.add_argument("--no-task-instructions", action="store_true",
                     help="submit each prompt WITHOUT its per-task "
                          "anvil-instructions.md (v0.1.3 #20 acceptance run: "
                          "contract markers must carry the interface alone)")

    lst = sub.add_parser("list", help="list the tasks in a suite")
    lst.add_argument("--suite", required=True)

    cmp_parser = sub.add_parser("compare",
                                help="diff two results.json files (baseline, candidate)")
    cmp_parser.add_argument("baseline")
    cmp_parser.add_argument("candidate")
    return parser


def _cmd_list(args: argparse.Namespace) -> int:
    tasks = load_suite(args.suite)
    for task in tasks:
        tiers = "/".join(task.expected_complexity) or "-"
        print(f"  {task.id:<28} tier={tiers:<18} {task.title}")
    print(f"\n{len(tasks)} task(s)")
    return 0


def _cmd_run(args: argparse.Namespace) -> int:
    tasks = load_suite(args.suite, only=args.tasks)
    if args.base_url and args.start_server:
        print("error: --base-url and --start-server are mutually exclusive",
              file=sys.stderr)
        return 2
    if args.mode == "real" and args.start_server \
            and not os.environ.get("OPENROUTER_API_KEY"):
        print("error: --mode real needs OPENROUTER_API_KEY set", file=sys.stderr)
        return 2

    cfg = EvalConfig(run_mode=args.run_mode)
    if args.timeout:
        cfg.task_timeout_s = args.timeout
    if args.pricing:
        cfg.pricing = load_pricing(args.pricing)
    if args.no_task_instructions:
        cfg.task_instructions = False

    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    results_root = pathlib.Path(args.results) if args.results else DEFAULT_RESULTS_ROOT
    results_dir = results_root / (f"{stamp}-{args.label}" if args.label else stamp)
    results_dir.mkdir(parents=True, exist_ok=True)

    server: AnvilServer | None = None
    execution_mode = "external"
    try:
        if args.start_server:
            server = AnvilServer(args.mode, results_dir / "server-workspace",
                                 port=args.port)
            print(f"starting Anvil server ({args.mode}) on {server.base_url} ...")
            server.start()
            cfg.base_url = server.base_url
            execution_mode = args.mode
        else:
            cfg.base_url = args.base_url or DEFAULT_BASE_URL

        client = AnvilClient(cfg.base_url, timeout_s=cfg.advance_timeout_s)
        try:
            client.health()
        except AnvilClientError as exc:
            print(f"error: no Anvil server at {cfg.base_url} ({exc}); "
                  f"start one or pass --start-server", file=sys.stderr)
            return 1

        meta = {
            "suite": args.suite,
            "label": args.label,
            "started_at": datetime.now(timezone.utc).isoformat(),
            "base_url": cfg.base_url,
            "execution_mode": execution_mode,
            "run_mode": cfg.run_mode,
            "task_instructions": cfg.task_instructions,
            "task_ids": [t.id for t in tasks],
        }
        results = run_suite(client, tasks, cfg, results_dir)
        payload = write_reports(results_dir, meta, results)
        print_summary(payload)
        print(f"results: {results_dir / 'results.json'}")
        print(f"report:  {results_dir / 'report.md'}")
        return 0
    finally:
        if server is not None:
            server.stop()


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    try:
        if args.command == "list":
            return _cmd_list(args)
        if args.command == "run":
            return _cmd_run(args)
        if args.command == "compare":
            compare(pathlib.Path(args.baseline), pathlib.Path(args.candidate))
            return 0
    except SuiteError as exc:
        print(f"suite error: {exc}", file=sys.stderr)
        return 2
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
