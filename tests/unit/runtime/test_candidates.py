"""Unit tests: fault candidate generation (v0.1.5 #28)."""

from __future__ import annotations

import pathlib
import textwrap

from anvil_runtime.verify import build_ast_index, build_candidates
from anvil_runtime.verify.candidates import MAX_CANDIDATES, symbol_hits
from anvil_runtime.verify.localize import FailureCluster, FailureRecord

# table is the producer; database consumes it. This is the shape the v0.1.4
# measurement found pathological: the consumer is named far more often in the
# failure text, so hit count alone always picks the wrong file.
TABLE = textwrap.dedent('''\
    class Table:
        def insert_row(self, doc):
            return doc
    ''')

DATABASE = textwrap.dedent('''\
    from table import Table

    class TinyDB:
        def insert_doc(self, doc):
            return Table().insert_row(doc)

        def search_docs(self, cond):
            return []
    ''')

UNRELATED = 'def unrelated_helper(x):\n    return x\n'


def _stage(tmp_path: pathlib.Path) -> list[str]:
    src = tmp_path / "src"
    src.mkdir()
    (src / "table.py").write_text(TABLE, encoding="utf-8")
    (src / "database.py").write_text(DATABASE, encoding="utf-8")
    (src / "helpers.py").write_text(UNRELATED, encoding="utf-8")
    return ["src/table.py", "src/database.py", "src/helpers.py"]


def _cluster(text: str, file: str | None = None) -> FailureCluster:
    return FailureCluster(
        error_type="failure",
        file=file,
        records=[FailureRecord(test_id="t", error_type="failure",
                               message="", excerpt=text)],
    )


def test_producer_ranks_above_consumer_despite_hit_count(
    tmp_path: pathlib.Path,
) -> None:
    """FR-FL-003, the finding that shaped #28.

    The text names two ``database.py`` symbols and one ``table.py`` symbol,
    so hit count would pick the consumer. Ranking must invert that: on the
    real v0.1.4 data ``table.py`` was a candidate 20 times and the
    hit-count winner zero times.
    """
    artifacts = _stage(tmp_path)
    index = build_ast_index(tmp_path, artifacts)
    cluster = _cluster("TinyDB.insert_doc returned wrong rows for Table")

    hits = symbol_hits(cluster, index)
    assert hits["src/database.py"] > hits["src/table.py"]

    assert build_candidates(cluster, index)[0] == "src/table.py"


def test_basename_result_is_always_a_member(tmp_path: pathlib.Path) -> None:
    """FR-FL-002/FR-FL-008: generation is strictly additive."""
    artifacts = _stage(tmp_path)
    index = build_ast_index(tmp_path, artifacts)
    # Text names nothing in helpers.py, yet basename implicated it.
    cluster = _cluster("Table and TinyDB", file="src/helpers.py")

    assert "src/helpers.py" in build_candidates(cluster, index)


def test_short_symbols_are_ignored_as_noise(tmp_path: pathlib.Path) -> None:
    """FR-FL-001: names of 3 characters or fewer never localize."""
    src = tmp_path / "src"
    src.mkdir()
    (src / "tiny.py").write_text("def ab(): ...\ndef abc(): ...\n",
                                 encoding="utf-8")
    index = build_ast_index(tmp_path, ["src/tiny.py"])

    assert build_candidates(_cluster("ab abc"), index) == []
    assert build_candidates(_cluster("abcd"), index) == []


def test_empty_candidate_set_when_nothing_matches(
    tmp_path: pathlib.Path,
) -> None:
    """FR-FL-006's signal: no candidate, so the caller must not drop it."""
    artifacts = _stage(tmp_path)
    index = build_ast_index(tmp_path, artifacts)

    assert build_candidates(_cluster("nothing familiar here"), index) == []


def test_cap_applied_and_seed_survives_it(tmp_path: pathlib.Path) -> None:
    """FR-FL-005: at most MAX_CANDIDATES, and the basename seed is kept."""
    src = tmp_path / "src"
    src.mkdir()
    names = [f"mod{i}" for i in range(6)]
    for i, name in enumerate(names):
        (src / f"{name}.py").write_text(f"def symbol_{i}(): ...\n",
                                        encoding="utf-8")
    (src / "seed.py").write_text("def seed_symbol(): ...\n", encoding="utf-8")
    artifacts = [f"src/{n}.py" for n in names] + ["src/seed.py"]
    index = build_ast_index(tmp_path, artifacts)

    # Names every module except the seed, which basename implicated.
    cluster = _cluster(" ".join(f"symbol_{i}" for i in range(6)),
                       file="src/seed.py")
    result = build_candidates(cluster, index)

    assert len(result) == MAX_CANDIDATES
    assert "src/seed.py" in result


def test_ranking_is_deterministic(tmp_path: pathlib.Path) -> None:
    artifacts = _stage(tmp_path)
    index = build_ast_index(tmp_path, artifacts)
    cluster = _cluster("Table TinyDB unrelated_helper")

    assert build_candidates(cluster, index) == build_candidates(cluster, index)


def test_cycle_between_candidates_does_not_break_ordering(
    tmp_path: pathlib.Path,
) -> None:
    """v0.1.3 saw a real query/middleware recursion cycle; ranking must stay
    total rather than assuming a DAG."""
    src = tmp_path / "src"
    src.mkdir()
    (src / "left.py").write_text(
        "from right import Right\n\nclass Left:\n    def go(self): ...\n",
        encoding="utf-8")
    (src / "right.py").write_text(
        "from left import Left\n\nclass Right:\n    def go(self): ...\n",
        encoding="utf-8")
    artifacts = ["src/left.py", "src/right.py"]
    index = build_ast_index(tmp_path, artifacts)

    result = build_candidates(_cluster("Left Right"), index)
    assert sorted(result) == artifacts


# --- FR-FL-008 against the committed v0.1.4 fixture -------------------------

FIXTURE = (pathlib.Path(__file__).parent / "fixtures"
           / "junit-v0.1.4-fix-r3.xml")

# A compact tinydb-shaped package carrying the real symbol names the stored
# report references, so the index has the same shape the measurement saw.
TINYDB_STUBS = {
    "tinydb/database.py": (
        "from tinydb.table import Table\n\n"
        "class TinyDB:\n"
        "    def table(self, name): ...\n"
        "    def tables(self): ...\n"
        "    def storage(self): ...\n"
    ),
    "tinydb/table.py": (
        "class Document:\n    def doc_id(self): ...\n\n"
        "class Table:\n"
        "    def insert(self, doc): ...\n"
        "    def name(self): ...\n"
        "    def storage(self): ...\n"
    ),
    "tinydb/queries.py": (
        "class QueryInstance:\n    def is_cacheable(self): ...\n\n"
        "class Query:\n    def where(self, key): ...\n"
    ),
    "tinydb/middlewares.py": (
        "from tinydb.storages import Storage\n\n"
        "class CachingMiddleware:\n    def flush(self): ...\n"
    ),
    "tinydb/storages.py": "class Storage:\n    def read(self): ...\n",
    "tinydb/operations.py": "def delete(key): ...\ndef increment(key): ...\n",
    "tinydb/utils.py": "def with_typehint(base): ...\n",
}


def _stage_tinydb(tmp_path: pathlib.Path) -> list[str]:
    (tmp_path / "tinydb").mkdir()
    for rel, body in TINYDB_STUBS.items():
        (tmp_path / rel).write_text(body, encoding="utf-8")
    return sorted(TINYDB_STUBS)


def test_fixture_reproduces_the_unlocalized_pathology() -> None:
    """The stored report's largest cluster is the one basename matching
    cannot see — that is the defect #28 exists to close."""
    from anvil_runtime.verify import cluster, try_parse_report

    records = try_parse_report(FIXTURE, sorted(TINYDB_STUBS))
    clusters = cluster(records)

    assert clusters[0].file is None
    assert clusters[0].size > sum(c.size for c in clusters[1:])


def test_symbols_localize_what_basename_dropped(
    tmp_path: pathlib.Path,
) -> None:
    """The previously-discarded cluster gets candidates, producer first.

    On the full v0.1.4 report ``tinydb/table.py`` was implicated in 20 of
    28 recovered failures and chosen by hit count in none.
    """
    from anvil_runtime.verify import cluster, try_parse_report

    artifacts = _stage_tinydb(tmp_path)
    index = build_ast_index(tmp_path, artifacts)
    unlocalized = [c for c in cluster(try_parse_report(FIXTURE, artifacts))
                   if c.file is None]
    assert unlocalized, "fixture must contain an unlocalized cluster"

    candidates = build_candidates(unlocalized[0], index)

    assert candidates, "the dropped cluster must now be repairable"
    assert candidates[0] == "tinydb/table.py"


def test_fr_fl_008_no_regression_on_the_fixture(
    tmp_path: pathlib.Path,
) -> None:
    """Coverage may only grow: every file basename implicated stays
    implicated. This is the guard against trading a correct narrow answer
    for a confident wrong one."""
    from anvil_runtime.verify import cluster, try_parse_report

    artifacts = _stage_tinydb(tmp_path)
    index = build_ast_index(tmp_path, artifacts)
    clusters = cluster(try_parse_report(FIXTURE, artifacts))

    basename_files = {c.file for c in clusters if c.file}
    candidate_files: set[str] = set()
    for entry in clusters:
        candidate_files.update(build_candidates(entry, index))

    assert basename_files <= candidate_files
    assert candidate_files - basename_files, "symbols must reach further"
