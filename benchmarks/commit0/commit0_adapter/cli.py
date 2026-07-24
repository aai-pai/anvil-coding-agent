"""Commit0 adapter CLI.

Usage (from the repo root)::

    python benchmarks/commit0/run_commit0.py list
    python benchmarks/commit0/run_commit0.py run --repo tinydb --start-server --mode real
    python benchmarks/commit0/run_commit0.py run --repo tinydb --repo simpy --base-url http://127.0.0.1:8765
"""

from __future__ import annotations

import argparse
import json
import os
import pathlib
import sys
import time
from datetime import datetime, timezone

from anvil_eval.client import AnvilClient, AnvilClientError
from anvil_eval.config import EvalConfig
from anvil_eval.runner import _drive_run
from anvil_eval.scoring import analyze_events
from anvil_eval.server import AnvilServer

from commit0_adapter.apply import apply_generated
from commit0_adapter.prepare import stage_workspace
from commit0_adapter.repos import STARTER_REPOS, fetch_skeleton
from commit0_adapter.score import run_repo_tests

BENCH_ROOT = pathlib.Path(__file__).resolve().parent.parent
RESULTS_ROOT = BENCH_ROOT / "results"
SKELETONS_ROOT = BENCH_ROOT / "skeletons"
# v0.1.4 spec §3: the repair-signal entry point Anvil runs after the
# implementation phase ({junit_xml} activates #26 localization).
GRAFT_AND_TEST = pathlib.Path(__file__).resolve().parent / "graft_and_test.py"


def run_one(client: AnvilClient, repo: str, results_dir: pathlib.Path,
            cfg: EvalConfig, test_timeout_s: float, baseline: bool,
            log=print) -> dict:
    result: dict = {"repo": repo, "run_status": "not_started"}
    wall_start = time.monotonic()
    try:
        skeleton = fetch_skeleton(repo, SKELETONS_ROOT)
        stage_dir = results_dir / "repos" / repo
        info = stage_workspace(repo, skeleton, stage_dir)
        result.update(info)
        result["stage_dir"] = str(stage_dir)
        log(f"    staged: {info['stubs']} stubs across {info['modules']} modules"
            f" | task {info['task_chars']:,} chars"
            f" ({info['doc_chars']:,} from docs)")

        # Score only the staging-time test snapshot (qa-leak fix, spec §3).
        meta = json.loads((stage_dir / "commit0-meta.json").read_text(
            encoding="utf-8"))
        snapshot_tests = meta["tests"]
        result["test_snapshot"] = len(snapshot_tests)

        if baseline:
            base = run_repo_tests(stage_dir, timeout_s=test_timeout_s,
                                  junit_name="baseline-junit.xml",
                                  package_dir=pathlib.Path(info["package_dir"]),
                                  test_files=snapshot_tests)
            result["baseline"] = {k: base[k] for k in
                                  ("total", "passed_count", "pass_rate")}
            log(f"    skeleton baseline: {base['passed_count']}/{base['total']}")

        started = client.start_run_in_place(
            workspace=str(stage_dir), mode=cfg.run_mode,
            security_profile=cfg.security_profile, defer=True)
        run_id = started["run_id"]
        result["run_id"] = run_id
        log(f"    run {run_id[:12]} started")
        status, state = _drive_run(client, run_id, cfg.task_timeout_s, log)
        result["run_status"] = status
        result["completed_phases"] = state.get("completed_phases", [])

        events = analyze_events(stage_dir)
        result["tokens"] = events.get("total_tokens", 0)
        result["events"] = {k: events[k] for k in
                            ("complexity_tier", "escalations",
                             "artifact_validation_failures", "input_truncations")}

        merged = apply_generated(stage_dir, pathlib.Path(info["package_dir"]))
        result["apply"] = {k: merged[k] for k in
                           ("generated_py_files", "applied", "grafted_bodies",
                            "unmatched", "skipped_invalid")}
        (results_dir / "repos" / f"{repo}-apply.json").write_text(
            json.dumps(merged, indent=2), encoding="utf-8")
        log(f"    grafted {merged['grafted_bodies']} stub bodies from "
            f"{merged['applied']}/{merged['generated_py_files']} generated modules")

        tests = run_repo_tests(stage_dir, timeout_s=test_timeout_s,
                               package_dir=pathlib.Path(info["package_dir"]),
                               test_files=snapshot_tests)
        result["tests"] = {k: tests.get(k) for k in
                           ("total", "passed_count", "failures", "errors",
                            "skipped", "pass_rate", "exit_code",
                            "collection_error")}
        if tests.get("collection_error"):
            log("    NOTE: package failed to import - tests never collected")
        result["output_tail"] = tests.get("output_tail", "")
        log(f"    tests: {tests.get('passed_count', 0)}/{tests.get('total', 0)} "
            f"passed (pass rate {tests.get('pass_rate', 0):.1%})")
    except (AnvilClientError, Exception) as exc:  # noqa: BLE001 - always record
        result["error"] = f"{type(exc).__name__}: {exc}"
        log(f"    ERROR: {result['error']}")
    result["wall_clock_s"] = round(time.monotonic() - wall_start, 2)
    return result


def write_report(results_dir: pathlib.Path, meta: dict, results: list[dict]) -> None:
    payload = {"meta": meta, "results": results}
    (results_dir / "results.json").write_text(json.dumps(payload, indent=2),
                                              encoding="utf-8")
    lines = [f"# Commit0 adapter report — {meta['label'] or meta['started_at']}",
             "",
             "| Repo | Run | Stubs | Applied | Tests passed | Pass rate |",
             "|---|---|---|---|---|---|"]
    for r in results:
        tests = r.get("tests", {})
        rate = ("import-fail" if tests.get("collection_error")
                else f"{tests.get('pass_rate', 0.0):.1%}")
        lines.append(
            f"| {r['repo']} | {r.get('run_status', '-')} | {r.get('stubs', '-')} "
            f"| {r.get('apply', {}).get('applied', '-')}"
            f"/{r.get('apply', {}).get('generated_py_files', '-')} "
            f"| {tests.get('passed_count', 0)}/{tests.get('total', 0)} "
            f"| {rate} |")
    lines += ["", "Local dev-loop scores; use the official `commit0` evaluator "
                  "for leaderboard numbers."]
    (results_dir / "report.md").write_text("\n".join(lines) + "\n",
                                           encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="commit0-adapter")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("list", help="show the starter repo subset")
    run = sub.add_parser("run", help="run Anvil on Commit0 repos and score")
    run.add_argument("--repo", action="append", dest="repos", default=None,
                     help="repo name under github.com/commit-0 (repeatable; "
                          "default: tinydb)")
    run.add_argument("--base-url", default=None)
    run.add_argument("--start-server", action="store_true")
    run.add_argument("--mode", default="offline-llm",
                     choices=["real", "offline-llm", "stub"])
    run.add_argument("--label", default=None)
    run.add_argument("--timeout", type=float, default=1800.0,
                     help="per-repo Anvil wall-clock timeout (default 1800s)")
    run.add_argument("--test-timeout", type=float, default=600.0)
    run.add_argument("--baseline", action="store_true",
                     help="also score the untouched skeleton for a delta")
    run.add_argument("--no-repair", action="store_true",
                     help="do not configure the repair loop on the spawned "
                          "server (one-shot / #23-ablation runs)")
    args = parser.parse_args(argv)

    if args.command == "list":
        print("starter repos (not the official split):")
        for repo in STARTER_REPOS:
            print(f"  {repo}")
        return 0

    repos = args.repos or ["tinydb"]
    if args.mode == "real" and args.start_server \
            and not os.environ.get("OPENROUTER_API_KEY"):
        print("error: --mode real needs OPENROUTER_API_KEY", file=sys.stderr)
        return 2

    cfg = EvalConfig(run_mode="yolo", task_timeout_s=args.timeout)
    # #24 landed: one /advance now performs one artifact (or the final
    # verify/repair unit), so the old whole-run-budget workaround is gone.
    # The verify/repair unit is still the longest single advance — a test
    # run per round plus repair completions — so bound it by what the loop
    # can actually spend: (rounds + 1) test runs + slack for completions.
    repair_rounds = int(os.environ.get("ANVIL_REPAIR_MAX_ROUNDS", "2"))
    cfg.advance_timeout_s = max(cfg.advance_timeout_s,
                                (repair_rounds + 1) * args.test_timeout + 300)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    results_dir = RESULTS_ROOT / (f"{stamp}-{args.label}" if args.label else stamp)
    results_dir.mkdir(parents=True, exist_ok=True)

    server = None
    try:
        if args.start_server:
            # Library-scale defaults for the spawned server, unless the user
            # pinned their own values; --base-url users must set these on
            # their server themselves (see README). Input: the staged task
            # file (stub inventory + doc excerpts) runs well past the 20k-char
            # default. Output (#19): doc phases must fit the quoted inventory,
            # and implementation must fit whole modules.
            os.environ.setdefault("ANVIL_INPUT_CHAR_LIMIT", "80000")
            os.environ.setdefault("ANVIL_DOC_MAX_TOKENS", "6000")
            os.environ.setdefault("ANVIL_CODE_MAX_TOKENS", "16000")
            # #20: a library-scale contract (stub inventory + manifest JSON)
            # runs past the 16k default; the cap fails intake loudly, so give
            # it headroom rather than shrinking the pinned inventory.
            os.environ.setdefault("ANVIL_CONTRACT_MAX_CHARS", "48000")
            # v0.1.4 #23/#26: the repair signal is the adapter's
            # graft-and-test entry point over the staging snapshot; the
            # {junit_xml} token turns on structured localization. The run's
            # `open` profile permits the local executor.
            if not args.no_repair:
                os.environ.setdefault(
                    "ANVIL_TEST_COMMAND",
                    f"{sys.executable} {GRAFT_AND_TEST} {{junit_xml}}")
                os.environ.setdefault("ANVIL_TEST_TIMEOUT_S",
                                      str(int(args.test_timeout)))
            server = AnvilServer(args.mode, results_dir / "server-workspace")
            print(f"starting Anvil server ({args.mode}) on {server.base_url} "
                  f"(input limit {os.environ['ANVIL_INPUT_CHAR_LIMIT']}, "
                  f"doc budget {os.environ['ANVIL_DOC_MAX_TOKENS']}, "
                  f"code budget {os.environ['ANVIL_CODE_MAX_TOKENS']}, "
                  f"contract cap {os.environ['ANVIL_CONTRACT_MAX_CHARS']}) ...")
            server.start()
            cfg.base_url = server.base_url
        else:
            cfg.base_url = args.base_url or cfg.base_url
        client = AnvilClient(cfg.base_url, timeout_s=cfg.advance_timeout_s)
        client.health()

        meta = {"benchmark": "commit0", "label": args.label,
                "started_at": datetime.now(timezone.utc).isoformat(),
                "execution_mode": args.mode if args.start_server else "external",
                "repos": repos}
        results = []
        for index, repo in enumerate(repos, start=1):
            print(f"[{index}/{len(repos)}] {repo}")
            results.append(run_one(client, repo, results_dir, cfg,
                                   args.test_timeout, args.baseline))
        write_report(results_dir, meta, results)
        print(f"\nresults: {results_dir / 'results.json'}")
        print(f"report:  {results_dir / 'report.md'}")
        return 0
    finally:
        if server is not None:
            server.stop()


if __name__ == "__main__":
    raise SystemExit(main())
