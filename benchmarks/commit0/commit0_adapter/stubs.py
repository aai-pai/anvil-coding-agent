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


def referenced_undefined(source: str) -> list[str]:
    """Names a module loads but never defines, imports, or binds.

    Commit0's stub-stripper sometimes deletes a helper *definition* while a
    reference to it survives (observed: tinydb's ``FrozenDict`` keeps
    ``__setitem__ = _immutable`` with ``def _immutable`` gone). Such names
    can't appear in the stub inventory — this pyflakes-lite pass finds them
    so the task can demand their definition explicitly.
    """
    import builtins

    try:
        tree = ast.parse(source)
    except SyntaxError:
        return []
    defined = set(dir(builtins)) | {"__name__", "__file__", "__doc__"}
    loaded: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Name):
            (loaded if isinstance(node.ctx, ast.Load) else defined).add(node.id)
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            defined.add(node.name)
        elif isinstance(node, ast.arg):
            defined.add(node.arg)
        elif isinstance(node, ast.alias):
            defined.add((node.asname or node.name).split(".")[0])
        elif isinstance(node, ast.ExceptHandler) and node.name:
            defined.add(node.name)
        elif isinstance(node, ast.Global) or isinstance(node, ast.Nonlocal):
            defined.update(node.names)
    return sorted(loaded - defined)


def scan_package_missing(package_dir: pathlib.Path) -> dict[str, list[str]]:
    """Per-module referenced-but-undefined names across the package."""
    missing: dict[str, list[str]] = {}
    for path in sorted(package_dir.rglob("*.py")):
        module = path.relative_to(package_dir).as_posix()
        names = referenced_undefined(
            path.read_text(encoding="utf-8", errors="replace"))
        if names:
            missing[module] = names
    return missing


def scan_package(package_dir: pathlib.Path) -> list[StubEntry]:
    """Inventory every .py module in the package, package-relative."""
    entries: list[StubEntry] = []
    for path in sorted(package_dir.rglob("*.py")):
        module = path.relative_to(package_dir).as_posix()
        entries.extend(scan_module(path, module))
    return entries


def render_inventory(entries: list[StubEntry], char_budget: int = 14000,
                     missing_by_module: dict[str, list[str]] | None = None) -> str:
    """Markdown stub inventory grouped by module, trimmed to a char budget.

    Stubs are listed with signatures (+ docstring first line while budget
    allows); already-implemented helpers are only counted, not listed.
    ``missing_by_module`` adds a per-module "must also define" line for
    definitions the skeleton references but no longer contains.
    """
    missing_by_module = missing_by_module or {}
    by_module: dict[str, list[StubEntry]] = {}
    for entry in entries:
        by_module.setdefault(entry.module, []).append(entry)
    for module in missing_by_module:
        by_module.setdefault(module, [])
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
        missing = missing_by_module.get(module, [])
        if not stubs and not missing:
            continue
        if not emit(f"### `{module}` — {len(stubs)} to implement"
                    f" ({done} already provided)"):
            lines.append("... (inventory truncated to fit the input budget)")
            break
        if missing:
            emit(f"- MUST ALSO DEFINE (referenced by this module but the "
                 f"definition is missing): {', '.join(f'`{m}`' for m in missing)}")
        for entry in stubs:
            doc = f"  — {entry.doc_first_line}" if entry.doc_first_line else ""
            if not emit(f"- `{entry.qualname}`: `{entry.signature}`{doc}"):
                lines.append("... (inventory truncated to fit the input budget)")
                return "\n".join(lines)
    return "\n".join(lines)


def render_manifest(entries: list[StubEntry],
                    missing_by_module: dict[str, list[str]] | None = None) -> str:
    """JSON ``contract-manifest`` (#21) from the stub inventory.

    Files: every module that needs work (has stubs or dangling references) —
    these are also the per-artifact targets Anvil iterates (#22). Symbols:
    every stub, pinned by qualname + exact signature, so Anvil's validator
    can AST-check the generated code mechanically. Paths are src-relative
    (the same package-relative paths ``apply`` maps back onto the package).
    """
    import json

    missing_by_module = missing_by_module or {}
    files: list[str] = []
    for entry in entries:
        if entry.is_stub and entry.module not in files:
            files.append(entry.module)
    for module in missing_by_module:
        if module not in files:
            files.append(module)
    symbols = [
        {"qualname": e.qualname, "signature": e.signature, "file": e.module}
        for e in entries if e.is_stub
    ]
    # Dangling references (MUST ALSO DEFINE) are pinned existence-only: the
    # skeleton lost their definitions outright, so there is no signature to
    # pin, but a module that fails to define them cannot import — Anvil's
    # #21 validator must catch that mechanically, not the test run.
    pinned = {(s["qualname"], s["file"]) for s in symbols}
    for module, names in missing_by_module.items():
        for name in names:
            if (name, module) not in pinned:
                symbols.append({"qualname": name, "file": module})
    return json.dumps({"files": files, "symbols": symbols}, indent=2)


__all__ = ["StubEntry", "scan_module", "scan_package", "render_inventory",
           "render_manifest"]
