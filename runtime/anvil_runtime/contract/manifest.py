"""Mechanical contract validation (v0.1.3 #21).

With the contract in one structured place (#20), generated code can be checked
against it deterministically — no LLM. The contract block may include a fenced
```` ```contract-manifest ```` JSON subsection::

    {"files": ["storages.py"],
     "symbols": [{"qualname": "JSONStorage.read",
                  "signature": "def read(self) -> Optional[dict]",
                  "file": "storages.py"}]}

``files`` and each symbol's ``file`` are paths relative to the run's ``src/``
directory. Post-implementation the validator AST-parses ``src/`` and verifies
every manifest file exists and every symbol exists with an unchanged
signature; violations name the offender and fail the phase into the normal
retry path. The manifest is optional — a prose-only contract skips mechanical
checks (encouraged, not required; the same posture as OKF cross-links, #16).
"""

from __future__ import annotations

import ast
import json
import pathlib
import re

from pydantic import BaseModel, Field

MANIFEST_FENCE = "contract-manifest"
_MANIFEST_RE = re.compile(
    r"^```" + MANIFEST_FENCE + r"[ \t]*\n(.*?)^```[ \t]*$",
    re.MULTILINE | re.DOTALL,
)


class ManifestSymbol(BaseModel):
    """One pinned symbol: a function/class the generated code must define."""

    qualname: str
    file: str
    signature: str | None = None  # None -> existence-only check (e.g. a class)


class ContractManifest(BaseModel):
    """The machine-checkable subset of a task contract."""

    files: list[str] = Field(default_factory=list)
    symbols: list[ManifestSymbol] = Field(default_factory=list)


def parse_contract_manifest(
    contract_text: str,
) -> tuple[ContractManifest | None, str | None]:
    """Extract the fenced manifest from a contract block.

    Returns ``(manifest, None)`` on success, ``(None, None)`` when no fence is
    present (prose-only contract), and ``(None, reason)`` when a fence exists
    but cannot be parsed — a malformed manifest must fail loudly, not silently
    skip the mechanical check.
    """
    match = _MANIFEST_RE.search(contract_text)
    if match is None:
        return None, None
    try:
        data = json.loads(match.group(1))
    except json.JSONDecodeError as exc:
        return None, f"contract-manifest is not valid JSON: {exc}"
    try:
        manifest = ContractManifest.model_validate(data)
    except Exception as exc:  # noqa: BLE001 - pydantic validation detail
        return None, f"contract-manifest does not match the schema: {exc}"
    return manifest, None


def _render_signature(node: ast.FunctionDef | ast.AsyncFunctionDef) -> str:
    prefix = "async def" if isinstance(node, ast.AsyncFunctionDef) else "def"
    returns = f" -> {ast.unparse(node.returns)}" if node.returns else ""
    return f"{prefix} {node.name}({ast.unparse(node.args)}){returns}"


def _normalize_signature(signature: str) -> str:
    """Whitespace-insensitive comparable form of a pinned signature."""
    text = signature.strip().rstrip(":").strip()
    text = re.sub(r"^async\s+def\s+", "async def ", text)
    return re.sub(r"\s+", "", text)


def _index_module(path: pathlib.Path) -> dict[str, ast.AST]:
    """Map qualname -> def node for every function/class in a module."""
    tree = ast.parse(path.read_text(encoding="utf-8", errors="replace"))
    index: dict[str, ast.AST] = {}

    def visit(node: ast.AST, prefix: str) -> None:
        for child in ast.iter_child_nodes(node):
            if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                index[f"{prefix}{child.name}"] = child
                visit(child, f"{prefix}{child.name}.")

    visit(tree, "")
    return index


def validate_manifest(
    manifest: ContractManifest, src_root: str | pathlib.Path
) -> list[str]:
    """Check generated sources against the manifest; return named violations."""
    root = pathlib.Path(src_root)
    violations: list[str] = []
    missing_files: set[str] = set()

    for rel in manifest.files:
        if not (root / rel).is_file():
            violations.append(f"missing file: {rel}")
            missing_files.add(rel)

    indexes: dict[str, dict[str, ast.AST] | None] = {}
    for symbol in manifest.symbols:
        if symbol.file in missing_files:
            continue  # the missing file is already reported once
        if symbol.file not in indexes:
            target = root / symbol.file
            if not target.is_file():
                violations.append(
                    f"missing file: {symbol.file} (expected to define {symbol.qualname})"
                )
                missing_files.add(symbol.file)
                indexes[symbol.file] = None
                continue
            try:
                indexes[symbol.file] = _index_module(target)
            except SyntaxError as exc:
                violations.append(f"unparseable python: {symbol.file} ({exc.msg})")
                indexes[symbol.file] = None
        index = indexes[symbol.file]
        if index is None:
            continue
        node = index.get(symbol.qualname)
        if node is None:
            violations.append(
                f"missing symbol: {symbol.qualname} (expected in {symbol.file})"
            )
            continue
        if symbol.signature is None:
            continue
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            violations.append(
                f"changed symbol kind: {symbol.qualname} in {symbol.file} is not a "
                f"function (pinned signature `{symbol.signature}`)"
            )
            continue
        found = _render_signature(node)
        if _normalize_signature(found) != _normalize_signature(symbol.signature):
            violations.append(
                f"changed signature: {symbol.qualname} in {symbol.file} — "
                f"pinned `{symbol.signature}`, found `{found}`"
            )
    return violations


__all__ = [
    "MANIFEST_FENCE",
    "ManifestSymbol",
    "ContractManifest",
    "parse_contract_manifest",
    "validate_manifest",
]
