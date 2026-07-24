# Anvil Architecture — v0.1.4 (delta)

How the v0.1.4 spec's requirements land in the existing runtime. Delta
against the v0.1.3 architecture; only touched components described.
Derived from [spec.md](spec.md).

## Component map

```
runtime/anvil_runtime/
  verify/
    runner.py            #23  local executor, compile smoke, basename mapping (shipped)
    docker_executor.py   #25  DockerExecutor, docker_probe, DockerError (shipped)
    localize.py          #26  NEW — junit report parsing + root-cause clustering
    interface_map.py     #27  NEW — AST interface extraction + connection ranking
  sdk/openhands_adapter.py    LLMBackend: loop orchestration, prompts, gates
  config/schema.py            knobs: #23 (shipped), #25 (shipped), #27 repairContext
  app.py                      env wiring (env > config > default, throughout)
```

All four verify modules stay **mechanical — no LLM involvement**; the only
LLM calls remain `LLMBackend`'s repair completions. That boundary is the
architecture: localization and context assembly are deterministic and
unit-testable with no provider.

## #26 — localization flow

1. `LLMBackend._verify_and_repair` computes the effective command once per
   pass: `{junit_xml}` token present → substitute
   `.anvil/junit-report.xml` (`localize.substitute_report_token`); record
   `report_rel` for retrieval.
2. Executors: `local` — the command writes the report into the workspace
   directly. `docker` — `DockerExecutor.run(..., copy_out_rel=report_rel)`
   copies the report back after the exec (best-effort: a dead command may
   not have written it).
3. `localize.parse_report(path, targets)` → `FailureRecord`s (test id,
   error type, message, implicated frame). `localize.cluster(records)` →
   `FailureCluster`s keyed **(error type, implicated file)**, size-desc.
4. Implicated files := cluster files in cluster order (replacing the
   basename grep); per-file prompt excerpt := that file's cluster summary
   (`localize.cluster_excerpt`, ≤3 representative failures). Missing/
   unparseable report → `implicated_files` fallback + a
   `JunitReportMissing` warning event.

The parse/cluster layer never sees the executor — it reads a file path.
That keeps #26 orthogonal to #25 (and to any future executor).

## #27 — context flow

`interface_map.build(root, artifacts, failing_rel, cap)` runs one `ast`
pass per sibling artifact: signatures (functions, methods, class
attributes) + one-line docstrings; import/name-reference edges to and from
the failing file drive the connection ranking; cap enforcement drops whole
files from the tail with an omission note. `LLMBackend._repair_prompt`
injects the block between the contract and the failure excerpt when
`repairContext == "interfaces"`; `minimal` skips the call entirely
(byte-for-byte first-iteration prompts — the ablation contract is at the
prompt level, so it is testable by string equality).

## Sequencing inside a repair round (revised)

```
run tests ──red──▶ localize (clusters) ──▶ for each implicated file:
  interface map + cluster excerpt → ONE repair completion → write
──▶ #21 manifest re-check (contract outranks tests) ──▶ re-run tests
```

Order matters: the interface map is rebuilt **per round** (a round-1
repair changes the interfaces round 2 must see), but is shared across the
files of one round (single AST pass; the failing file's entry is excluded
per prompt).

## Failure taxonomy (unchanged, extended)

- red tests → repair rounds (bounded) → step failure with tail
- docker infrastructure → `DockerError` → step failure, own reason
- missing report → degrade to basename mapping, warn, continue
- interface-map extraction error on a sibling → that file listed as
  `(currently broken)`; never blocks the round (a broken sibling is
  exactly when repair is running)

## Checkpoint/resume

No new checkpoint state: #26/#27 are stateless within a round, and #24's
`phase_progress` already carries the verify/repair unit boundary. A resume
mid-loop re-runs the current round from the test run (idempotent).
