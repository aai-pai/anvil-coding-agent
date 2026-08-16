"""Verification by execution — all mechanical, no LLM involvement:
the repair loop's primitives (v0.1.4 #23, ``runner.py``), the
docker-isolated executor (#25, ``docker_executor.py``), junit failure
localization (#26, ``localize.py``), and the interface map for repair
context (#27, ``interface_map.py``)."""

from anvil_runtime.verify.candidates import (
    MAX_CANDIDATES,
    build as build_candidates,
)
from anvil_runtime.verify.docker_executor import (
    DockerError,
    DockerExecutor,
    docker_probe,
)
from anvil_runtime.verify.interface_map import (
    INTERFACE_MAP_MAX_CHARS,
    AstIndex,
    build as build_interface_map,
    index as build_ast_index,
)
from anvil_runtime.verify.localize import (
    FailureCluster,
    FailureCounts,
    FailureRecord,
    JUNIT_TOKEN,
    REPORT_REL,
    cluster,
    cluster_excerpt,
    substitute_report_token,
    try_parse_counts,
    try_parse_report,
)
from anvil_runtime.verify.slices import (
    SLICE_MAX_CHARS,
    build as build_slices,
)
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
    "DockerError",
    "DockerExecutor",
    "docker_probe",
    "JUNIT_TOKEN",
    "REPORT_REL",
    "FailureRecord",
    "FailureCluster",
    "FailureCounts",
    "substitute_report_token",
    "try_parse_report",
    "try_parse_counts",
    "cluster",
    "cluster_excerpt",
    "build_interface_map",
    "INTERFACE_MAP_MAX_CHARS",
    "AstIndex",
    "build_ast_index",
    "build_candidates",
    "MAX_CANDIDATES",
    "build_slices",
    "SLICE_MAX_CHARS",
]
