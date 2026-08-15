"""Unit tests: interface map for repair context (v0.1.4 #27)."""

from __future__ import annotations

import pathlib
import textwrap

from anvil_runtime.verify import build_ast_index, build_interface_map

DATABASE = textwrap.dedent('''\
    """The database module."""
    from storage import Storage

    DEFAULT_TABLE = "_default"

    class TinyDB:
        """Main database class."""
        table_class = ...

        def __init__(self, path: str, storage=Storage):
            self._secret = 1

        def insert(self, document: dict) -> int:
            return 1
    ''')

STORAGE = textwrap.dedent('''\
    """Storage backends."""

    class Storage:
        def read(self):
            return None

        def write(self, data) -> None:
            pass
    ''')

UNRELATED = 'def helper(x, y=2):\n    return x + y\n'


def _stage(tmp_path: pathlib.Path) -> list[str]:
    src = tmp_path / "src"
    src.mkdir()
    (src / "database.py").write_text(DATABASE, encoding="utf-8")
    (src / "storage.py").write_text(STORAGE, encoding="utf-8")
    (src / "helpers.py").write_text(UNRELATED, encoding="utf-8")
    return ["src/database.py", "src/storage.py", "src/helpers.py"]


def test_signatures_and_attributes_but_never_bodies(
    tmp_path: pathlib.Path,
) -> None:
    artifacts = _stage(tmp_path)
    block = build_interface_map(tmp_path, artifacts, "src/storage.py")
    assert "class TinyDB" in block
    assert "def insert(self, document: dict) -> int" in block
    assert "def __init__(self, path: str, storage=Storage)" in block
    assert "table_class = ..." in block
    assert "DEFAULT_TABLE = ..." in block
    assert "The database module." in block  # one-line docstring
    assert "self._secret" not in block      # bodies never leak
    assert "return" not in block


def test_failing_file_excluded_and_connection_ranked(
    tmp_path: pathlib.Path,
) -> None:
    artifacts = _stage(tmp_path)
    # database.py imports storage -> storage ranks before unrelated helpers.
    block = build_interface_map(tmp_path, artifacts, "src/database.py")
    assert "`src/database.py`" not in block
    assert block.index("storage.py") < block.index("helpers.py")
    # storage.py is imported BY database -> database ranks first for it too.
    block2 = build_interface_map(tmp_path, artifacts, "src/storage.py")
    assert block2.index("database.py") < block2.index("helpers.py")


def test_cap_drops_least_connected_with_note(tmp_path: pathlib.Path) -> None:
    artifacts = _stage(tmp_path)
    block = build_interface_map(tmp_path, artifacts, "src/database.py", cap=130)
    assert "storage.py" in block            # most-connected survives
    assert "helpers.py" not in block        # least-connected dropped
    assert "file(s) omitted)" in block


def test_broken_sibling_listed_without_content(tmp_path: pathlib.Path) -> None:
    artifacts = _stage(tmp_path)
    (tmp_path / "src" / "helpers.py").write_text("def broken(:\n",
                                                 encoding="utf-8")
    block = build_interface_map(tmp_path, artifacts, "src/database.py")
    assert "## `src/helpers.py` (currently broken)" in block


def test_no_siblings_returns_empty(tmp_path: pathlib.Path) -> None:
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "only.py").write_text("x = 1\n", encoding="utf-8")
    assert build_interface_map(tmp_path, ["src/only.py"], "src/only.py") == ""


# --- v0.1.5 #28/#29: the shared AST index -----------------------------------


def test_index_symbols_include_class_level_definitions(
    tmp_path: pathlib.Path,
) -> None:
    """FR-FL-001: methods are indexed, not just top-level names.

    An assertion failure names ``TinyDB.insert`` far more often than it
    names the module that defines it — that is the whole reason symbol
    matching localizes what basename matching cannot.
    """
    artifacts = _stage(tmp_path)
    idx = build_ast_index(tmp_path, artifacts)

    assert idx.symbols["TinyDB"] == "src/database.py"
    assert idx.symbols["insert"] == "src/database.py"  # class-level
    assert idx.symbols["Storage"] == "src/storage.py"
    assert idx.symbols["write"] == "src/storage.py"  # class-level
    assert idx.symbols["helper"] == "src/helpers.py"


def test_index_edges_point_at_upstream_dependencies(
    tmp_path: pathlib.Path,
) -> None:
    """FR-FL-003 ranks by this direction: database depends on storage."""
    artifacts = _stage(tmp_path)
    idx = build_ast_index(tmp_path, artifacts)

    assert idx.edges["src/database.py"] == ["src/storage.py"]
    assert idx.edges["src/storage.py"] == []
    assert idx.edges["src/helpers.py"] == []


def test_index_records_broken_files_rather_than_dropping_them(
    tmp_path: pathlib.Path,
) -> None:
    artifacts = _stage(tmp_path)
    (tmp_path / "src" / "helpers.py").write_text("def oops(:\n", encoding="utf-8")
    idx = build_ast_index(tmp_path, artifacts)

    assert idx.broken == ["src/helpers.py"]
    assert "helper" not in idx.symbols
    assert "src/helpers.py" not in idx.edges


def test_index_first_definer_wins_and_is_stable(tmp_path: pathlib.Path) -> None:
    """Artifacts are walked sorted, so a duplicated name resolves the same
    way on every round."""
    src = tmp_path / "src"
    src.mkdir()
    (src / "b_second.py").write_text("def shared():\n    ...\n", encoding="utf-8")
    (src / "a_first.py").write_text("def shared():\n    ...\n", encoding="utf-8")
    artifacts = ["src/b_second.py", "src/a_first.py"]

    first = build_ast_index(tmp_path, artifacts)
    second = build_ast_index(tmp_path, list(reversed(artifacts)))

    assert first.symbols["shared"] == "src/a_first.py"
    assert first.symbols == second.symbols


def test_build_with_prebuilt_index_is_byte_identical(
    tmp_path: pathlib.Path,
) -> None:
    """The index is a performance seam, never a behavioral one."""
    artifacts = _stage(tmp_path)
    idx = build_ast_index(tmp_path, artifacts)

    for failing in artifacts:
        assert build_interface_map(
            tmp_path, artifacts, failing, ast_index=idx
        ) == build_interface_map(tmp_path, artifacts, failing)


def test_build_with_prebuilt_index_still_marks_broken_siblings(
    tmp_path: pathlib.Path,
) -> None:
    artifacts = _stage(tmp_path)
    (tmp_path / "src" / "helpers.py").write_text("def oops(:\n", encoding="utf-8")
    idx = build_ast_index(tmp_path, artifacts)

    block = build_interface_map(
        tmp_path, artifacts, "src/database.py", ast_index=idx
    )
    assert "## `src/helpers.py` (currently broken)" in block
