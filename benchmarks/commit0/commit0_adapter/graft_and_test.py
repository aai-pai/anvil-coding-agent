"""Adapter-owned repair-signal entry point (v0.1.4 spec §3).

Run BY ANVIL as the ``externalTestCommand``, with cwd = the staged run
workspace::

    python .../graft_and_test.py {junit_xml}

Per invocation (i.e. per repair-loop test round):

1. **Restore the staged package from the staging-time PRISTINE copy** —
   the graft fills only stub bodies, so grafting an already-grafted
   package would pin the first wrong body forever; restoring first is
   what lets a repair round replace it.
2. Graft Anvil's current ``src/`` output onto the restored package, in
   place (``apply_generated``).
3. Run the STAGING SNAPSHOT of the repo's own test files (never Anvil's
   qa-generated tests) with the same invocation shape as ``score.py``,
   writing the JUnit report Anvil's #26 localization reads, and exit
   with pytest's code — the repair signal tests exactly what scoring
   tests.

Design note (measured 2026-07-24): the first version grafted onto a
scratch package and relied on sys.path ordering to shadow the staged
skeleton. pytest's conftest loading resolved the package against the
STAGE root anyway (observed: the skeleton's dangling ``_immutable``
NameError killed collection with pytest exit 4 and no junit report, so
the loop repaired blind all round). In-place restore+graft removes the
shadowing problem instead of fighting it.
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
from commit0_adapter.prepare import META_NAME, PRISTINE_DIR  # noqa: E402


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
    package_dir = stage / meta["package_rel"]
    if package_dir.exists():
        shutil.rmtree(package_dir)
    shutil.copytree(pristine, package_dir)

    merged = apply_generated(stage, package_dir)
    print(f"grafted {merged['grafted_bodies']} stub bodies from "
          f"{merged['applied']}/{merged['generated_py_files']} generated "
          "modules (package restored from pristine first)")

    test_files = [stage / rel for rel in meta["tests"]
                  if (stage / rel).is_file()]
    if not test_files:
        print("no snapshot test files present", file=sys.stderr)
        return 2

    junit_path = stage / junit_rel
    junit_path.parent.mkdir(parents=True, exist_ok=True)
    env = dict(os.environ)
    # Same invocation shape as score.py (the proven one): cwd = stage,
    # importable root = the package's parent (handles src layouts), stage
    # root second.
    roots = [str(package_dir.parent.resolve()), str(stage)]
    env["PYTHONPATH"] = os.pathsep.join(
        dict.fromkeys(roots)) + os.pathsep + env.get("PYTHONPATH", "")
    command = [sys.executable, "-m", "pytest", *[str(p) for p in test_files],
               "-q", "--tb=short", "-p", "no:cacheprovider",
               f"--junitxml={junit_path}"]
    proc = subprocess.run(command, cwd=str(stage))
    return proc.returncode


if __name__ == "__main__":
    raise SystemExit(main())
