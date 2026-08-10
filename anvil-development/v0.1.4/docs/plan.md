# Anvil Plan — v0.1.4 (remaining work)

Ordered slices for the unshipped scope. Each slice ends with the full
suite green. Derived from [blueprint.md](blueprint.md).

1. **#26 mechanics** — `verify/localize.py` + unit tests (no adapter
   changes yet). Pure functions, provider-free.
2. **#27 mechanics** — `verify/interface_map.py` + unit tests. Same.
3. **Loop integration** — adapter ctor gate + `_verify_and_repair` token/
   report/cluster threading + `_repair_prompt` interface block + docker
   `copy_out_rel`; config/env wiring; `test_repair_loop.py` additions
   incl. the byte-for-byte `minimal` ablation check.
4. **Commit0 adapter §3** — staging snapshot, `graft_and_test.py` entry
   point with `{junit_xml}`, timeout-workaround removal; optional per-repo
   docker image.
5. **Real-docker smoke** (manual, once): one offline-llm run with
   `ANVIL_TEST_EXECUTOR=docker` against Docker Desktop to validate the
   CLI assumptions the fakes encode.
6. **The measurement** (binding, proposal §Measurement): tinydb
   median-of-3 with the full loop vs baseline median 24/201
   {0, 19, 24, 60, 78} — must beat the median AND delete the import-fail
   arm; cachetools ≥ 177/215; smoke suite 6/6 with no command. Record
   executor + ablation flags per run. If the delta demands decomposition,
   ablate: no `{junit_xml}` token (#26 off) and/or
   `ANVIL_REPAIR_CONTEXT=minimal` (#27 off).
7. **Close-out** — implementation log, RUNNING.md, STATUS.md run-log
   entries.
