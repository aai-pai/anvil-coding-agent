"""Unit tests: contract/context split + manifest parsing (v0.1.3 #20/#21).

The contract block is the task-scoped channel for binding facts: split out of
``domain-knowledge/background-information.md`` by HTML-comment markers,
injected verbatim, appended-into by intake, and optionally carrying a
machine-checkable ``contract-manifest``. An unmarkered file must behave
exactly as v0.1.2 (all context, nothing pinned).
"""

from __future__ import annotations

import pathlib
import textwrap

from anvil_runtime.contract import (
    CONTRACT_MARKER,
    CONTEXT_MARKER,
    append_block,
    parse_contract_manifest,
    resolve_contract,
    split_contract,
    validate_manifest,
    ContractManifest,
    ManifestSymbol,
)

MARKERED = textwrap.dedent(f"""\
    # My Task

    intro prose

    {CONTRACT_MARKER}

    ## Output contract

    - PINNED_FACT: `issues` is a dict
    {CONTEXT_MARKER}

    ## Background

    CTX_ONLY_FACT about the library.
    """)


# -- split_contract -----------------------------------------------------------


def test_unmarkered_file_is_all_context_byte_for_byte() -> None:
    text = "# Task\n\njust prose, no markers\n"
    split = split_contract(text)
    assert split.has_markers is False
    assert split.contract == ""
    assert split.context == text  # byte-for-byte v0.1.2 behavior


def test_markered_file_splits_contract_and_context() -> None:
    split = split_contract(MARKERED)
    assert split.has_markers is True
    assert "PINNED_FACT: `issues` is a dict" in split.contract
    assert "CTX_ONLY_FACT" not in split.contract
    assert "CTX_ONLY_FACT" in split.context
    assert "PINNED_FACT" not in split.context
    # Marker lines belong to neither part.
    assert CONTRACT_MARKER not in split.contract + split.context
    assert CONTEXT_MARKER not in split.contract + split.context


def test_contract_section_may_run_to_end_of_file() -> None:
    text = f"prose\n\n{CONTRACT_MARKER}\npinned tail fact\n"
    split = split_contract(text)
    assert split.contract == "pinned tail fact"
    assert "pinned tail fact" not in split.context


def test_resolve_contract_reads_run_file(tmp_path: pathlib.Path) -> None:
    target = tmp_path / "domain-knowledge" / "background-information.md"
    target.parent.mkdir(parents=True)
    target.write_text(MARKERED, encoding="utf-8")
    resolved = resolve_contract(tmp_path)
    assert resolved.present is True
    assert "PINNED_FACT" in resolved.text
    assert resolved.length == len(resolved.text)


def test_resolve_contract_absent_file_or_markers(tmp_path: pathlib.Path) -> None:
    assert resolve_contract(tmp_path).present is False
    target = tmp_path / "domain-knowledge" / "background-information.md"
    target.parent.mkdir(parents=True)
    target.write_text("# Task\n\nno markers\n", encoding="utf-8")
    assert resolve_contract(tmp_path).present is False


# -- append_block -------------------------------------------------------------


def test_append_block_unmarkered_matches_v012_format() -> None:
    text = "# Task\n\nbody\n"
    addition = "\n## Assumptions\n\n- no persistence"
    # Exactly the v0.1.2 expression: rstrip + "\n" + addition + "\n".
    assert append_block(text, addition) == text.rstrip("\n") + "\n" + addition + "\n"


def test_append_block_lands_inside_contract_section() -> None:
    result = append_block(MARKERED, "\n## Assumptions\n\n- ASSUMED_FACT")
    split = split_contract(result)
    assert "ASSUMED_FACT" in split.contract
    assert "ASSUMED_FACT" not in split.context
    # The original pinned fact and the context both survive.
    assert "PINNED_FACT" in split.contract
    assert "CTX_ONLY_FACT" in split.context


def test_append_block_contract_at_eof() -> None:
    text = f"prose\n{CONTRACT_MARKER}\npinned\n"
    result = append_block(text, "\n- appended binding fact")
    assert "appended binding fact" in split_contract(result).contract


# -- contract-manifest (#21) --------------------------------------------------

MANIFEST_CONTRACT = textwrap.dedent("""\
    pinned prose

    ```contract-manifest
    {"files": ["storages.py"],
     "symbols": [{"qualname": "JSONStorage.read",
                  "signature": "def read(self) -> dict | None",
                  "file": "storages.py"}]}
    ```
    """)


def test_parse_manifest_absent_and_valid() -> None:
    manifest, error = parse_contract_manifest("prose only, no fence")
    assert manifest is None and error is None
    manifest, error = parse_contract_manifest(MANIFEST_CONTRACT)
    assert error is None
    assert manifest.files == ["storages.py"]
    assert manifest.symbols[0].qualname == "JSONStorage.read"


def test_parse_manifest_malformed_fails_loudly() -> None:
    manifest, error = parse_contract_manifest("```contract-manifest\n{oops\n```\n")
    assert manifest is None
    assert "JSON" in error


def _manifest() -> ContractManifest:
    return ContractManifest(
        files=["storages.py"],
        symbols=[ManifestSymbol(
            qualname="JSONStorage.read",
            signature="def read(self) -> dict | None",
            file="storages.py",
        )],
    )


CONFORMING = textwrap.dedent("""\
    class JSONStorage:
        def read(self) -> dict | None:
            return {}
    """)


def test_validate_manifest_conforming_src_passes(tmp_path: pathlib.Path) -> None:
    (tmp_path / "storages.py").write_text(CONFORMING, encoding="utf-8")
    assert validate_manifest(_manifest(), tmp_path) == []


def test_validate_manifest_missing_file_named(tmp_path: pathlib.Path) -> None:
    violations = validate_manifest(_manifest(), tmp_path)
    assert any("missing file: storages.py" in v for v in violations)


def test_validate_manifest_missing_symbol_named(tmp_path: pathlib.Path) -> None:
    (tmp_path / "storages.py").write_text("class JSONStorage:\n    pass\n",
                                          encoding="utf-8")
    violations = validate_manifest(_manifest(), tmp_path)
    assert any("missing symbol: JSONStorage.read" in v for v in violations)


def test_validate_manifest_changed_signature_named(tmp_path: pathlib.Path) -> None:
    (tmp_path / "storages.py").write_text(
        "class JSONStorage:\n    def read(self, extra) -> bool:\n        return True\n",
        encoding="utf-8",
    )
    violations = validate_manifest(_manifest(), tmp_path)
    assert any("changed signature: JSONStorage.read" in v for v in violations)
    assert any("def read(self, extra) -> bool" in v for v in violations)


def test_validate_manifest_signature_is_whitespace_insensitive(
    tmp_path: pathlib.Path,
) -> None:
    (tmp_path / "storages.py").write_text(
        "class JSONStorage:\n    def read(self)->dict|None:\n        return {}\n",
        encoding="utf-8",
    )
    assert validate_manifest(_manifest(), tmp_path) == []
