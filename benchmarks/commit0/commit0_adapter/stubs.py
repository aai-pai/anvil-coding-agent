"""AST stub inventory: what the skeleton promises and what needs implementing.

The inventory drives two things: the generated background-information.md (so
Anvil sees the exact contract it must honor) and the apply/score reporting
(how many stubs its output actually filled).
"""

from __future__ import annotations

import ast
import dataclasses
import pathlib


@dataclasses.dataclass
class StubEntry:
    module: str            # package-relative path, e.g. "storages.py"
    qualname: str          # e.g. "JSONStorage.read"
    signature: str         # "def read(self) -> Optional[dict]"
    doc_first_line: str
    is_stub: bool          # body is pass/.../NotImplementedError only


def _is_stub_body(node: ast.FunctionDef | ast.AsyncFunctionDef) -> bool:
    real = [n for n in node.body
            if not (isinstance(n, ast.Expr) and isinstance(n.value, ast.Constant))]
    if not real:
        return True  # docstring-only body
    if len(real) == 1:
        stmt = real[0]
        if isinstance(stmt, ast.Pass):
            return True
        if isinstance(stmt, ast.Expr) and isinstance(stmt.value, ast.Constant) \
                and stmt.value.value is Ellipsis:
            return True
        if isinstance(stmt, ast.Raise):
            exc = stmt.exc
            name = ""
            if isinstance(exc, ast.Call):
                exc = exc.func
            if isinstance(exc, ast.Name):
                name = exc.id
            elif isinstance(exc, ast.Attribute):
                name = exc.attr
            return name == "NotImplementedError"
    return False


def _signature(node: ast.FunctionDef | ast.AsyncFunctionDef) -> str:
    prefix = "async def" if isinstance(node, ast.AsyncFunctionDef) else "def"
    args = ast.unparse(node.args)
    returns = f" -> {ast.unparse(node.returns)}" if node.returns else ""
    return f"{prefix} {node.name}({args}){returns}"


def scan_module(path: pathlib.Path, module: str) -> list[StubEntry]:
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"))
    except (SyntaxError, UnicodeDecodeError):
        return []
    entries: list[StubEntry] = []

    def visit(node: ast.AST, prefix: str) -> None:
        for child in ast.iter_child_nodes(node):
            if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                doc = ast.get_docstring(child) or ""
                entries.append(StubEntry(
                    module=module,
                    qualname=f"{prefix}{child.name}",
                    signature=_signature(child),
                    doc_first_line=doc.strip().splitlines()[0] if doc.strip() else "",
                    is_stub=_is_stub_body(child),
                ))
                visit(child, f"{prefix}{child.name}.")
            elif isinstance(child, ast.ClassDef):
                visit(child, f"{prefix}{child.name}.")

    visit(tree, "")
    return entries


def scan_package(package_dir: pathlib.Path) -> list[StubEntry]:
    """Inventory every .py module in the package, package-relative."""
    entries: list[StubEntry] = []
    for path in sorted(package_dir.rglob("*.py")):
        module = path.relative_to(package_dir).as_posix()
        entries.extend(scan_module(path, module))
    return entries


def render_inventory(entries: list[StubEntry], char_budget: int = 14000) -> str:
    """Markdown stub inventory grouped by module, trimmed to a char budget.

    Stubs are listed with signatures (+ docstring first line while budget
    allows); already-implemented helpers are only counted, not listed.
    """
    by_module: dict[str, list[StubEntry]] = {}
    for entry in entries:
        by_module.setdefault(entry.module, []).append(entry)
    lines: list[str] = []
    used = 0

    def emit(text: str) -> bool:
        nonlocal used
        if used + len(text) + 1 > char_budget:
            return False
        lines.append(text)
        used += len(text) + 1
        return True

    for module, module_entries in by_module.items():
        stubs = [e for e in module_entries if e.is_stub]
        done = len(module_entries) - len(stubs)
        if not stubs:
            continue
        if not emit(f"### `{module}` — {len(stubs)} to implement"
                    f" ({done} already provided)"):
            lines.append("... (inventory truncated to fit the input budget)")
            break
        for entry in stubs:
            doc = f"  — {entry.doc_first_line}" if entry.doc_first_line else ""
            if not emit(f"- `{entry.qualname}`: `{entry.signature}`{doc}"):
                lines.append("... (inventory truncated to fit the input budget)")
                return "\n".join(lines)
    return "\n".join(lines)


__all__ = ["StubEntry", "scan_module", "scan_package", "render_inventory"]
