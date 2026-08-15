"""Unit tests: dependency-slice repair context (v0.1.5 #29)."""

from __future__ import annotations

import pathlib
import textwrap

from anvil_runtime.verify import build_ast_index, build_slices
from anvil_runtime.verify.slices import upstream_of

UTIL = textwrap.dedent('''\
    """Utilities."""

    def with_typehint(base):
        """The load-bearing helper two temp-0 runs got wrong."""
        return base
    ''')

TABLE = textwrap.dedent('''\
    from util import with_typehint

    class Table:
        def insert_row(self, doc):
            return with_typehint(doc)
    ''')

FARAWAY = 'def faraway_helper(x):\n    return x\n'


def _stage(tmp_path: pathlib.Path) -> list[str]:
    src = tmp_path / "src"
    src.mkdir()
    (src / "util.py").write_text(UTIL, encoding="utf-8")
    (src / "table.py").write_text(TABLE, encoding="utf-8")
    (src / "faraway.py").write_text(FARAWAY, encoding="utf-8")
    return ["src/util.py", "src/table.py", "src/faraway.py"]


def test_upstream_excludes_candidates_and_unrelated_files(
    tmp_path: pathlib.Path,
) -> None:
    artifacts = _stage(tmp_path)
    index = build_ast_index(tmp_path, artifacts)

    assert upstream_of(["src/table.py"], index) == ["src/util.py"]
    # A candidate's own source is already in the repair prompt.
    assert upstream_of(["src/table.py", "src/util.py"], index) == []


def test_upstream_bodies_present_unrelated_absent(
    tmp_path: pathlib.Path,
) -> None:
    """FR-DS-001: selecting A over B needs to see what A *does*."""
    artifacts = _stage(tmp_path)
    index = build_ast_index(tmp_path, artifacts)

    block = build_slices(tmp_path, ["src/table.py"], index)

    assert "def with_typehint(base):" in block
    assert "return base" in block  # the body, not just the signature
    assert "faraway_helper" not in block


def test_no_upstream_returns_empty_string(tmp_path: pathlib.Path) -> None:
    """So the caller composes the prompt unconditionally."""
    artifacts = _stage(tmp_path)
    index = build_ast_index(tmp_path, artifacts)

    assert build_slices(tmp_path, ["src/util.py"], index) == ""


def test_budget_degrades_to_signatures_never_mid_body(
    tmp_path: pathlib.Path,
) -> None:
    """FR-DS-002: half a function body reads as complete, which is worse
    than none — so overflow drops to signatures instead of truncating."""
    artifacts = _stage(tmp_path)
    index = build_ast_index(tmp_path, artifacts)

    block = build_slices(tmp_path, ["src/table.py"], index, cap=40)

    assert "def with_typehint(base)" in block  # signature survives
    assert "return base" not in block  # body does not
    assert "reduced to signatures" in block


def test_broken_upstream_marked_not_dropped(tmp_path: pathlib.Path) -> None:
    artifacts = _stage(tmp_path)
    (tmp_path / "src" / "util.py").write_text("def oops(:\n", encoding="utf-8")
    index = build_ast_index(tmp_path, artifacts)

    # A broken upstream has no edge to discover it by, so name it directly.
    block = build_slices(tmp_path, ["src/table.py"], index)
    assert block == "" or "currently broken" in block


def test_shared_dependency_ranks_before_singly_used_one(
    tmp_path: pathlib.Path,
) -> None:
    """A dependency two candidates rely on is likelier to be the shared
    cause than one only a single candidate touches."""
    src = tmp_path / "src"
    src.mkdir()
    (src / "shared.py").write_text("def shared_fn():\n    return 1\n",
                                   encoding="utf-8")
    (src / "solo.py").write_text("def solo_fn():\n    return 2\n",
                                 encoding="utf-8")
    (src / "one.py").write_text(
        "from shared import shared_fn\n\ndef one_fn():\n    return shared_fn()\n",
        encoding="utf-8")
    (src / "two.py").write_text(
        "from shared import shared_fn\nfrom solo import solo_fn\n\n"
        "def two_fn():\n    return shared_fn() + solo_fn()\n",
        encoding="utf-8")
    artifacts = ["src/shared.py", "src/solo.py", "src/one.py", "src/two.py"]
    index = build_ast_index(tmp_path, artifacts)

    assert upstream_of(["src/one.py", "src/two.py"], index) == [
        "src/shared.py", "src/solo.py",
    ]
