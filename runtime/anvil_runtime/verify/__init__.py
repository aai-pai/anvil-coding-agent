"""Verification by execution: the external-test repair loop's mechanical
pieces (v0.1.4 #23). See ``runner.py``."""

from anvil_runtime.verify.runner import (
    EVENT_TAIL_CHARS,
    PROMPT_TAIL_CHARS,
    TestRunResult,
    compile_smoke,
    implicated_files,
    run_external_tests,
)

__all__ = [
    "TestRunResult",
    "run_external_tests",
    "compile_smoke",
    "implicated_files",
    "PROMPT_TAIL_CHARS",
    "EVENT_TAIL_CHARS",
]
