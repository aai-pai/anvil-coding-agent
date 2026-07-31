"""Commit0 adapter — v0.1.4 spec §3 integration (snapshot + graft_and_test).

Uses a miniature skeleton repo instead of a cloned Commit0 repo; each
graft_and_test invocation spawns a real pytest subprocess against the
scratch package, exactly as the repair loop would.
"""

from __future__ import annotations

import json
import pathlib
import sys
import textwrap

_ROOT = pathlib.Path(__file__).resolve().parents[3]
sys.path.insert(0, str(_ROOT / "benchmarks" / "commit0"))
sys.path.insert(0, str(_ROOT / "evals"))  # anvil_eval, used by score.py

from commit0_adapter import graft_and_test  # noqa: E402
from commit0_adapter.prepare import (  # noqa: E402
    META_NAME,
    PRISTINE_DIR,
    stage_workspace,
)
from commit0_adapter.score import run_repo_tests  # noqa: E402

STUB_CORE = textwrap.dedent('''\
    """Core module."""


    def add(a, b):
        """Return a + b."""
        pass
    ''')

GOOD_CORE = STUB_CORE.replace("    pass", "    return a + b")
BAD_CORE = STUB_CORE.replace("    pass", "    return a - b")

TEST_CORE = textwrap.dedent("""\
    from mylib.core import add


    def test_add():
        assert add(1, 2) == 3
    """)


def _make_skeleton(tmp_path: pathlib.Path) -> pathlib.Path:
    skeleton = tmp_path / "mylib"
    (skeleton / "mylib").mkdir(parents=True)
    (skeleton / "mylib" / "__init__.py").write_text(
        "from mylib.core import add\n", encoding="utf-8")
    (skeleton / "mylib" / "core.py").write_text(STUB_CORE, encoding="utf-8")
    (skeleton / "tests").mkdir()
    (skeleton / "tests" / "test_core.py").write_text(TEST_CORE,
                                                    encoding="utf-8")
    (skeleton / "README.md").write_text("# mylib\n", encoding="utf-8")
    return skeleton


def _stage(tmp_path: pathlib.Path) -> pathlib.Path:
    stage = tmp_path / "stage"
    info = stage_workspace("mylib", _make_skeleton(tmp_path), stage)
    assert info["test_snapshot"] == 1
    return stage


def test_staging_writes_snapshot_meta_and_pristine(
    tmp_path: pathlib.Path,
) -> None:
    stage = _stage(tmp_path)
    meta = json.loads((stage / META_NAME).read_text(encoding="utf-8"))
    assert meta["tests"] == ["tests/test_core.py"]
    assert meta["package_name"] == "mylib"
    pristine = stage / PRISTINE_DIR / "mylib" / "core.py"
    assert pristine.is_file()
    assert "pass" in pristine.read_text(encoding="utf-8")


def test_scoring_counts_only_snapshot_tests(tmp_path: pathlib.Path) -> None:
    stage = _stage(tmp_path)
    # Simulate Anvil's qa phase adding its own (trivially green) test.
    (stage / "tests" / "test_qa_generated.py").write_text(
        "def test_always_green():\n    assert True\n", encoding="utf-8")
    meta = json.loads((stage / META_NAME).read_text(encoding="utf-8"))
    scored = run_repo_tests(stage, timeout_s=120,
                            package_dir=stage / "mylib",
                            test_files=meta["tests"])
    assert scored["total"] == 1  # the qa test never entered the score


def test_graft_and_test_green_grafts_in_place(
    tmp_path: pathlib.Path, monkeypatch,
) -> None:
    stage = _stage(tmp_path)
    (stage / "src").mkdir(exist_ok=True)
    (stage / "src" / "core.py").write_text(GOOD_CORE, encoding="utf-8")
    monkeypatch.chdir(stage)
    assert graft_and_test.main([".anvil/junit-report.xml"]) == 0
    assert (stage / ".anvil" / "junit-report.xml").is_file()
    # In-place graft: the staged package carries the implementation, while
    # the pristine copy stays stubbed as the per-round restoration source.
    assert "return a + b" in (stage / "mylib" / "core.py").read_text(
        encoding="utf-8")
    assert "pass" in (stage / PRISTINE_DIR / "mylib" / "core.py").read_text(
        encoding="utf-8")


def test_repairs_propagate_via_pristine_regraft(
    tmp_path: pathlib.Path, monkeypatch,
) -> None:
    stage = _stage(tmp_path)
    (stage / "src").mkdir(exist_ok=True)
    generated = stage / "src" / "core.py"
    monkeypatch.chdir(stage)
    generated.write_text(BAD_CORE, encoding="utf-8")
    assert graft_and_test.main([".anvil/junit-report.xml"]) != 0
    report = (stage / ".anvil" / "junit-report.xml").read_text(encoding="utf-8")
    assert "test_add" in report  # the failure Anvil's #26 will localize
    # A repair rewrites the generated file; the pristine re-graft must pick
    # it up (an in-place graft would skip the no-longer-stub body).
    generated.write_text(GOOD_CORE, encoding="utf-8")
    assert graft_and_test.main([".anvil/junit-report.xml"]) == 0
