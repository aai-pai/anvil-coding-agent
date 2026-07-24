"""Adapter-owned repair-signal entry point (v0.1.4 spec §3).

Run BY ANVIL as the ``externalTestCommand``, with cwd = the staged run
workspace::

    python .../graft_and_test.py {junit_xml}

Per invocation (i.e. per repair-loop test round):

1. Re-create a scratch package from the staging-time PRISTINE copy — the
   graft fills only stub bodies, so grafting in place would never let a
   repair replace an earlier wrong body.
2. Graft Anvil's current ``src/`` output onto the scratch package
   (``apply_generated``), leaving the staged skeleton untouched for the
   final apply+score step.
3. Run the STAGING SNAPSHOT of the repo's own test files (never Anvil's
   qa-generated tests) against the scratch package, writing the JUnit
   report Anvil's #26 localization reads, and exit with pytest's code —
   so the repair signal tests exactly what scoring tests.
"""

from __future__ import annotations

import json
import os
import pathlib
import shutil
import subprocess
import sys

# The command is invoked by absolute script path from an arbitrary cwd, so
# the adapter package root must be put on sys.path by hand.
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from commit0_adapter.apply import apply_generated  # noqa: E402
from commit0_adapter.prepare import (  # noqa: E402
    META_NAME,
    PRISTINE_DIR,
    SCRATCH_DIR,
)


def main(argv: list[str] | None = None) -> int:
    args = sys.argv[1:] if argv is None else argv
    junit_rel = args[0] if args else ".anvil/junit-report.xml"
    stage = pathlib.Path.cwd().resolve()

    meta_path = stage / META_NAME
    if not meta_path.is_file():
        print(f"{META_NAME} not found in {stage} — stage_workspace must run "
              "first", file=sys.stderr)
        return 2
    meta = json.loads(meta_path.read_text(encoding="utf-8"))

    pristine = stage / PRISTINE_DIR / meta["package_name"]
    if not pristine.is_dir():
        print(f"pristine package missing: {pristine}", file=sys.stderr)
        return 2
    scratch_root = stage / SCRATCH_DIR
    scratch_pkg = scratch_root / meta["package_name"]
    if scratch_root.exists():
        shutil.rmtree(scratch_root)
    shutil.copytree(pristine, scratch_pkg)

    merged = apply_generated(stage, scratch_pkg,
                             exclude_dir=stage / meta["package_rel"])
    print(f"grafted {merged['grafted_bodies']} stub bodies from "
          f"{merged['applied']}/{merged['generated_py_files']} generated "
          "modules onto scratch")

    test_files = [stage / rel for rel in meta["tests"]
                  if (stage / rel).is_file()]
    if not test_files:
        print("no snapshot test files present", file=sys.stderr)
        return 2

    junit_path = stage / junit_rel
    junit_path.parent.mkdir(parents=True, exist_ok=True)
    env = dict(os.environ)
    # Scratch package must shadow the staged skeleton: cwd (= sys.path[0]
    # under `python -m`) and the PYTHONPATH head are both the scratch root;
    # the stage root follows for any test-helper imports.
    env["PYTHONPATH"] = os.pathsep.join(
        [str(scratch_root), str(stage)]) + os.pathsep + env.get("PYTHONPATH", "")
    command = [sys.executable, "-m", "pytest", *[str(p) for p in test_files],
               "-q", "--tb=short", "-p", "no:cacheprovider",
               f"--junitxml={junit_path}", f"--rootdir={stage}"]
    proc = subprocess.run(command, cwd=str(scratch_root))
    return proc.returncode


if __name__ == "__main__":
    raise SystemExit(main())
