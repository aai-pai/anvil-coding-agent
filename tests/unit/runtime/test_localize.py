"""Unit tests: structured failure localization from JUnit XML (v0.1.4 #26)."""

from __future__ import annotations

import pathlib
import textwrap

from anvil_runtime.verify import (
    JUNIT_TOKEN,
    REPORT_REL,
    cluster,
    cluster_excerpt,
    substitute_report_token,
    try_parse_report,
)

TARGETS = ["src/database.py", "src/queries.py", "src/utils.py"]

REPORT = textwrap.dedent("""\
    <?xml version="1.0" encoding="utf-8"?>
    <testsuites>
      <testsuite name="pytest" tests="5" failures="4" errors="1">
        <testcase classname="tests.test_db" name="test_insert">
          <failure message="TypeError: keys must be str">
    tinydb/database.py line 40, in insert
    TypeError: keys must be str, not TinyDB</failure>
        </testcase>
        <testcase classname="tests.test_db" name="test_upsert">
          <failure message="TypeError: keys must be str">
    tinydb/database.py line 44, in upsert
    TypeError: keys must be str, not TinyDB</failure>
        </testcase>
        <testcase classname="tests.test_db" name="test_update">
          <failure message="TypeError: keys must be str">
    tinydb/database.py line 48, in update
    TypeError: keys must be str, not TinyDB</failure>
        </testcase>
        <testcase classname="tests.test_q" name="test_delegation">
          <failure message="RecursionError: maximum recursion depth">
    tinydb/queries.py line 12, in __getattr__
    RecursionError: maximum recursion depth exceeded</failure>
        </testcase>
        <testcase classname="tests.test_q" name="test_setup">
          <error message="fixture broke">no traceback frames here</error>
        </testcase>
      </testsuite>
    </testsuites>
    """)


def test_token_substitution() -> None:
    command = f"pytest tests -q --junitxml {JUNIT_TOKEN}"
    effective, report_rel = substitute_report_token(command)
    assert report_rel == REPORT_REL
    assert JUNIT_TOKEN not in effective and REPORT_REL in effective


def test_no_token_means_no_report_handling() -> None:
    effective, report_rel = substitute_report_token("pytest tests -q")
    assert effective == "pytest tests -q" and report_rel is None


def _write_report(tmp_path: pathlib.Path, content: str = REPORT) -> pathlib.Path:
    target = tmp_path / REPORT_REL
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding="utf-8")
    return target


def test_parse_maps_frames_to_targets_by_basename(tmp_path: pathlib.Path) -> None:
    records = try_parse_report(_write_report(tmp_path), TARGETS)
    assert records is not None and len(records) == 5
    assert {r.file for r in records[:3]} == {"src/database.py"}
    assert records[3].file == "src/queries.py"
    assert records[4].file is None  # no frame named a target
    assert records[0].test_id == "tests.test_db.test_insert"
    assert records[0].error_type == "failure"  # no type attr -> node kind


def test_clusters_key_on_error_type_and_file_largest_first(
    tmp_path: pathlib.Path,
) -> None:
    records = try_parse_report(_write_report(tmp_path), TARGETS)
    clusters = cluster(records)
    assert [(c.file, c.size) for c in clusters[:2]] == [
        ("src/database.py", 3), ("src/queries.py", 1)]
    assert len(clusters) == 3  # the unmapped error is its own cluster


def test_cluster_excerpt_is_cause_focused(tmp_path: pathlib.Path) -> None:
    records = try_parse_report(_write_report(tmp_path), TARGETS)
    top = cluster(records)[0]
    excerpt = cluster_excerpt(top, limit=2)
    assert "3 test failure(s) share one root cause" in excerpt
    assert "`src/database.py`" in excerpt
    assert "tests.test_db.test_insert" in excerpt
    assert "(and 1 more with the same cause)" in excerpt


def test_missing_and_malformed_reports_return_none(
    tmp_path: pathlib.Path,
) -> None:
    assert try_parse_report(tmp_path / REPORT_REL, TARGETS) is None
    assert try_parse_report(
        _write_report(tmp_path, "<testsuites><unclosed"), TARGETS) is None


def test_single_testsuite_root_parses(tmp_path: pathlib.Path) -> None:
    single = REPORT.replace("<testsuites>\n  ", "").replace(
        "\n</testsuites>", "").replace('<?xml version="1.0" encoding="utf-8"?>',
                                      '<?xml version="1.0"?>')
    records = try_parse_report(_write_report(tmp_path, single), TARGETS)
    assert records is not None and len(records) == 5
