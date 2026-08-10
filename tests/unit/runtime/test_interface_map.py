"""Unit tests: interface map for repair context (v0.1.4 #27)."""

from __future__ import annotations

import pathlib
import textwrap

from anvil_runtime.verify import build_interface_map

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
