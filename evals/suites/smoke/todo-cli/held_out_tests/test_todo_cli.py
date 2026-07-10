"""Held-out acceptance tests for todo-cli. The agent never sees these.

Drives the CLI as a subprocess and asserts on the pinned JSON storage format
rather than stdout formatting, which the contract leaves flexible.
"""

import json
import os
import subprocess
import sys


def _run(tmp_db, *args):
    script = os.path.join(os.environ["ANVIL_GENERATED_SRC"], "todo.py")
    env = dict(os.environ, TODO_DB_PATH=str(tmp_db))
    return subprocess.run(
        [sys.executable, script, *args],
        capture_output=True, text=True, timeout=30, env=env,
    )


def _read_db(tmp_db):
    with open(tmp_db, encoding="utf-8") as handle:
        return json.load(handle)


def test_add_creates_task_with_pinned_schema(tmp_path):
    db = tmp_path / "todo.json"
    proc = _run(db, "add", "buy milk")
    assert proc.returncode == 0, proc.stderr
    tasks = _read_db(db)
    assert tasks == [{"id": 1, "title": "buy milk", "done": False}]


def test_ids_increment(tmp_path):
    db = tmp_path / "todo.json"
    assert _run(db, "add", "first").returncode == 0
    assert _run(db, "add", "second").returncode == 0
    tasks = _read_db(db)
    assert [t["id"] for t in tasks] == [1, 2]
    assert [t["title"] for t in tasks] == ["first", "second"]


def test_list_contains_titles(tmp_path):
    db = tmp_path / "todo.json"
    _run(db, "add", "walk the dog")
    _run(db, "add", "water plants")
    proc = _run(db, "list")
    assert proc.returncode == 0, proc.stderr
    assert "walk the dog" in proc.stdout
    assert "water plants" in proc.stdout


def test_done_marks_task(tmp_path):
    db = tmp_path / "todo.json"
    _run(db, "add", "pay rent")
    proc = _run(db, "done", "1")
    assert proc.returncode == 0, proc.stderr
    assert _read_db(db)[0]["done"] is True


def test_done_unknown_id_fails(tmp_path):
    db = tmp_path / "todo.json"
    _run(db, "add", "only task")
    proc = _run(db, "done", "99")
    assert proc.returncode != 0
    assert proc.stderr.strip() != ""
