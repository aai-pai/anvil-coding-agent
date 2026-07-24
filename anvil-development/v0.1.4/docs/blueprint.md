# Anvil Blueprint — v0.1.4 (delta)

File-level construction plan for the unshipped spec sections (#26, #27,
adapter §3). #23/#24/#25 are shipped; their blueprint is the
[implementation log](implementation-log.md). Derived from
[architecture.md](architecture.md).

## New files

### `runtime/anvil_runtime/verify/localize.py` (#26)

- `JUNIT_TOKEN = "{junit_xml}"`, `REPORT_REL = ".anvil/junit-report.xml"`
- `substitute_report_token(command) -> tuple[str, str | None]` — effective
  command + `report_rel` (None when no token).
- `FailureRecord` (pydantic): `test_id`, `error_type`, `message`,
  `file` (implicated generated artifact, may be None), `excerpt`.
- `parse_report(path, targets) -> list[FailureRecord]` — stdlib
  `xml.etree`; `<failure>`/`<error>` children of `<testcase>`; implicated
  frame = deepest traceback line whose basename matches a target (reuses
  the FR-RL-007 join key); tolerant of both `<testsuites>` and
  `<testsuite>` roots. Raises nothing: unreadable/malformed → `None`
  sentinel via `try_parse_report` wrapper.
- `FailureCluster`: `error_type`, `file`, `records` (size = len).
- `cluster(records) -> list[FailureCluster]` — key (error_type, file),
  size-desc, stable.
- `cluster_excerpt(cluster, limit=3) -> str` — count + error type + up to
  3 representative failures (test id, message, excerpt).

### `runtime/anvil_runtime/verify/interface_map.py` (#27)

- `INTERFACE_MAP_MAX_CHARS = 6_000`
- `build(root, artifacts, failing_rel, cap) -> str` — per sibling `.py`
  artifact: `ast.parse`; emit `def`/`async def` signatures (with defaults),
  class headers + method signatures + assigned attributes, one-line
  docstrings. Connection rank: (0) siblings the failing file
  imports/references, (1) siblings importing/referencing the failing
  file's module, (2) rest; drop whole files from the tail on cap overflow,
  append `({n} files omitted)`. Sibling with syntax error → header line
  `# <rel> (currently broken)`. Returns `""` when there are no siblings.

## Modified files

### `runtime/anvil_runtime/verify/docker_executor.py`

- `DockerExecutor.run(command, timeout_s, copy_out_rel=None)` — after a
  non-timeout exec, best-effort `docker cp cid:WORKDIR/<rel> <host>/<rel>`
  (failure ignored: the command may have died before writing the report;
  FR-JL-002 degrades downstream).

### `runtime/anvil_runtime/sdk/openhands_adapter.py`

- ctor: `repair_context: str | None = None` → `self._repair_context`
  (default `"interfaces"`).
- `_verify_and_repair`: substitute token once; thread `report_rel` into
  both executors' `run_tests`; after each red run, `try_parse_report` +
  `cluster` → implicated files + per-file excerpts dict; missing report →
  `JunitReportMissing` warning event + basename fallback;
  `RepairRoundStarted.data` gains `clusters` summary (FR-JL-005).
- `_repair_files`: accept optional per-file excerpt dict (falls back to
  the raw tail).
- `_repair_prompt`: when `repair_context == "interfaces"`, insert the
  interface-map block (built once per round, passed in) + the FR-IC-003
  harmony instruction between contract and failure excerpt.

### `runtime/anvil_runtime/config/schema.py` / `app.py`

- `repairContext: Literal["interfaces", "minimal"] = "interfaces"`;
  `DEFAULT_REPAIR_CONTEXT`; env `ANVIL_REPAIR_CONTEXT`, wired in
  `_build_real_manager`.

### `benchmarks/commit0/commit0_adapter/` (§3, adapter-side)

- `prepare.py`: snapshot the staged repo's original `tests/` file list
  (JSON alongside the stage); `score.py` runs only snapshot files.
- New `graft_and_test.py` entry point: graft generated `src/` onto a
  scratch skeleton copy, run the snapshot suite with
  `--junitxml {junit_xml}`; wired as `ANVIL_TEST_COMMAND` by `cli.py`.
- Drop the long-advance timeout workaround (FR-AG-002 landed).

## Tests

- `tests/unit/runtime/test_localize.py` — token substitution; parse of a
  representative junit file (testsuites/testsuite roots, failure+error);
  frame implication by basename; clustering key + order; excerpt format;
  malformed XML → None.
- `tests/unit/runtime/test_interface_map.py` — signatures not bodies;
  connection ranking; cap + omission note; broken sibling; no siblings.
- `test_repair_loop.py` additions — cluster-driven implication end-to-end
  (scripted junit written by the fake command); prompt carries cluster
  excerpt + interface block; `minimal` restores prior prompts
  byte-for-byte; missing report degrades with warning; docker copy-out
  called with the report path.
- Adapter tests live with the adapter (existing pattern).
