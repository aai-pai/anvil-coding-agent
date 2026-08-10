"""Aggregation and reporting: results.json (machine) + report.md (human)."""

from __future__ import annotations

import json
import pathlib
from datetime import datetime, timezone


def aggregate(results: list[dict]) -> dict:
    """Suite-level headline metrics from per-task results."""
    total = len(results)
    resolved = sum(1 for r in results if r.get("resolved"))
    completed = sum(1 for r in results if r.get("run_status") == "completed")
    tokens = [r["events"]["total_tokens"] for r in results
              if r.get("events", {}).get("total_tokens")]
    durations = [r["wall_clock_s"] for r in results if r.get("wall_clock_s")]
    costs = [r["estimated_cost_usd"] for r in results
             if r.get("estimated_cost_usd") is not None]
    docs = sum(r.get("artifacts", {}).get("docs_total", 0) for r in results)
    okf = sum(r.get("artifacts", {}).get("okf_valid", 0) for r in results)
    complexity_checked = [r for r in results
                          if r.get("complexity", {}).get("match") is not None]
    complexity_matched = sum(1 for r in complexity_checked
                             if r["complexity"]["match"])
    return {
        "tasks": total,
        "resolved": resolved,
        "resolve_rate": round(resolved / total, 4) if total else 0.0,
        "completed_runs": completed,
        "completion_rate": round(completed / total, 4) if total else 0.0,
        "avg_tokens": round(sum(tokens) / len(tokens)) if tokens else 0,
        "avg_wall_clock_s": round(sum(durations) / len(durations), 1)
        if durations else 0.0,
        "total_estimated_cost_usd": round(sum(costs), 4) if costs else None,
        "okf_valid_docs_rate": round(okf / docs, 4) if docs else None,
        "complexity_match_rate": (
            round(complexity_matched / len(complexity_checked), 4)
            if complexity_checked else None
        ),
        "escalations": sum(r.get("events", {}).get("escalations", 0)
                           for r in results),
        "artifact_validation_failures": sum(
            r.get("events", {}).get("artifact_validation_failures", 0)
            for r in results),
        "input_truncations": sum(r.get("events", {}).get("input_truncations", 0)
                                 for r in results),
        "failure_records": sum(r.get("artifacts", {}).get("failure_records", 0)
                               for r in results),
    }


def _pct(value: float | None) -> str:
    return "-" if value is None else f"{value * 100:.0f}%"


def render_markdown(payload: dict) -> str:
    """A human-readable report.md for a suite run."""
    summary = payload["summary"]
    meta = payload["meta"]
    lines = [
        f"# Anvil eval report — {meta['suite']}",
        "",
        f"- **When:** {meta['started_at']}",
        f"- **Execution mode:** {meta['execution_mode']}  |  "
        f"**run mode:** {meta['run_mode']}  |  **label:** {meta.get('label') or '-'}",
        f"- **Resolve rate (pass@1):** {_pct(summary['resolve_rate'])} "
        f"({summary['resolved']}/{summary['tasks']})",
        f"- **Pipeline completion rate:** {_pct(summary['completion_rate'])}",
        f"- **Avg tokens/task:** {summary['avg_tokens']:,}  |  "
        f"**avg wall-clock:** {summary['avg_wall_clock_s']}s"
        + (f"  |  **est. cost:** ${summary['total_estimated_cost_usd']}"
           if summary["total_estimated_cost_usd"] is not None else ""),
        f"- **OKF-valid docs:** {_pct(summary['okf_valid_docs_rate'])}  |  "
        f"**complexity match:** {_pct(summary['complexity_match_rate'])}",
        f"- **Reliability:** {summary['escalations']} escalations, "
        f"{summary['artifact_validation_failures']} artifact validation failures, "
        f"{summary['input_truncations']} truncations, "
        f"{summary['failure_records']} failure records",
        "",
        "| Task | Resolved | Run status | Tests | Tier | Tokens | Wall (s) |",
        "|---|---|---|---|---|---|---|",
    ]
    for r in payload["results"]:
        tests = r.get("tests", {})
        tier = r.get("events", {}).get("complexity_tier") or "-"
        if r.get("complexity", {}).get("match") is False:
            tier = f"{tier} (expected {'/'.join(r['complexity']['expected'])})"
        lines.append(
            f"| {r['task_id']} "
            f"| {'YES' if r.get('resolved') else 'no'} "
            f"| {r.get('run_status', '-')} "
            f"| {tests.get('passed_count', 0)}/{tests.get('total', 0)} "
            f"| {tier} "
            f"| {r.get('events', {}).get('total_tokens', 0):,} "
            f"| {r.get('wall_clock_s', '-')} |"
        )
    unresolved = [r for r in payload["results"] if not r.get("resolved")]
    if unresolved:
        lines += ["", "## Unresolved tasks", ""]
        for r in unresolved:
            tail = r.get("tests", {}).get("output_tail", "") or r.get("error", "")
            lines += [f"### {r['task_id']} — run status `{r.get('run_status')}`",
                      "", "```", tail.strip()[-1500:], "```", ""]
    return "\n".join(lines) + "\n"


def write_reports(results_dir: pathlib.Path, meta: dict,
                  results: list[dict]) -> dict:
    payload = {"meta": meta, "summary": aggregate(results), "results": results}
    results_dir.mkdir(parents=True, exist_ok=True)
    (results_dir / "results.json").write_text(
        json.dumps(payload, indent=2), encoding="utf-8")
    (results_dir / "report.md").write_text(
        render_markdown(payload), encoding="utf-8")
    return payload


def print_summary(payload: dict) -> None:
    summary = payload["summary"]
    print()
    print("=" * 62)
    print(f"  Resolve rate (pass@1): {_pct(summary['resolve_rate'])} "
          f"({summary['resolved']}/{summary['tasks']})")
    print(f"  Completion rate:       {_pct(summary['completion_rate'])}")
    print(f"  Avg tokens/task:       {summary['avg_tokens']:,}")
    print(f"  Avg wall-clock/task:   {summary['avg_wall_clock_s']}s")
    if summary["total_estimated_cost_usd"] is not None:
        print(f"  Est. total cost:       ${summary['total_estimated_cost_usd']}")
    print("=" * 62)
    for r in payload["results"]:
        tests = r.get("tests", {})
        flag = "PASS" if r.get("resolved") else "FAIL"
        print(f"  [{flag}] {r['task_id']:<28} {tests.get('passed_count', 0)}"
              f"/{tests.get('total', 0)} tests, {r.get('run_status')}")
    print()


def compare(baseline_path: pathlib.Path, candidate_path: pathlib.Path) -> None:
    """Print a per-task and headline delta between two results.json files."""
    baseline = json.loads(baseline_path.read_text(encoding="utf-8"))
    candidate = json.loads(candidate_path.read_text(encoding="utf-8"))
    base_by_id = {r["task_id"]: r for r in baseline["results"]}
    cand_by_id = {r["task_id"]: r for r in candidate["results"]}
    print(f"baseline:  {baseline['meta'].get('label') or baseline_path}")
    print(f"candidate: {candidate['meta'].get('label') or candidate_path}")
    print()
    for task_id in sorted(set(base_by_id) | set(cand_by_id)):
        old = base_by_id.get(task_id, {}).get("resolved")
        new = cand_by_id.get(task_id, {}).get("resolved")
        if old == new:
            marker = "  ="
        elif new and not old:
            marker = "  IMPROVED"
        elif old and not new:
            marker = "  REGRESSED"
        else:
            marker = "  (only in one run)"
        print(f"  {task_id:<28} {old!s:>5} -> {new!s:<5}{marker}")
    old_rate = baseline["summary"]["resolve_rate"]
    new_rate = candidate["summary"]["resolve_rate"]
    print(f"\nresolve rate: {_pct(old_rate)} -> {_pct(new_rate)} "
          f"({(new_rate - old_rate) * 100:+.0f} pts)")


__all__ = ["aggregate", "write_reports", "print_summary", "compare",
           "render_markdown"]
