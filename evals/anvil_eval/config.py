"""Harness configuration shared by the CLI, runner, and scoring."""

from __future__ import annotations

import dataclasses
import json
import pathlib

EVALS_ROOT = pathlib.Path(__file__).resolve().parent.parent
SUITES_ROOT = EVALS_ROOT / "suites"
DEFAULT_RESULTS_ROOT = EVALS_ROOT / "results"

DEFAULT_BASE_URL = "http://127.0.0.1:8765"
DEFAULT_TASK_TIMEOUT_S = 900.0
DEFAULT_ADVANCE_TIMEOUT_S = 600.0
DEFAULT_PYTEST_TIMEOUT_S = 120.0


@dataclasses.dataclass
class EvalConfig:
    """Everything one suite invocation needs.

    ``pricing`` maps an OpenRouter model slug to a blended USD price per
    million tokens; when supplied the report includes an estimated cost per
    task (Anvil's audit trail records tokens per phase and the model each
    phase routed to, but not dollars).
    """

    base_url: str = DEFAULT_BASE_URL
    run_mode: str = "yolo"  # unattended pass@1 is the benchmark condition
    security_profile: str = "open"
    task_timeout_s: float = DEFAULT_TASK_TIMEOUT_S
    advance_timeout_s: float = DEFAULT_ADVANCE_TIMEOUT_S
    pytest_timeout_s: float = DEFAULT_PYTEST_TIMEOUT_S
    pricing: dict[str, float] = dataclasses.field(default_factory=dict)
    # v0.1.3 acceptance condition: submit each task WITHOUT its per-task
    # anvil-instructions.md (the runtime copies a sibling file automatically,
    # so the prompt is staged alone). Proves #20's contract markers replace
    # the per-task fidelity-instructions workaround.
    task_instructions: bool = True


def load_pricing(path: str | pathlib.Path) -> dict[str, float]:
    """Load a ``{model-slug: usd_per_million_tokens}`` pricing table."""
    data = json.loads(pathlib.Path(path).read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"pricing file must be a JSON object: {path}")
    # Keys starting with "_" are comments (see pricing.example.json).
    return {str(model): float(price) for model, price in data.items()
            if not str(model).startswith("_")}


__all__ = [
    "EvalConfig",
    "load_pricing",
    "EVALS_ROOT",
    "SUITES_ROOT",
    "DEFAULT_RESULTS_ROOT",
    "DEFAULT_BASE_URL",
]
