"""Interface-aware repair context (v0.1.4 #27, "functional harmony").

Mechanical, no LLM involvement. A repair prompt must see the structural
connections to the passing code — signatures, parameters, class
attributes, dependency edges — so a targeted fix cannot drift the
interfaces the passing files rely on. SIGNATURES ONLY: bodies of passing
files never enter the prompt (full dependency-slice source is v0.1.5),
and passing files are never in the write-set (FR-RL-008, unchanged).

:func:`build` extracts one map per repair round (interfaces move as
repairs land), connection-ranked from the failing file's point of view
(FR-IC-002) and size-capped by dropping whole least-connected files.
"""

from __future__ import annotations

import ast
import pathlib

INTERFACE_MAP_MAX_CHARS = 6_000


def _module_name(rel: str) -> str:
    stem = rel.replace("\\", "/").rsplit("/", 1)[-1]
    return stem[:-3] if stem.endswith(".py") else stem


def _signature(node: ast.FunctionDef | ast.AsyncFunctionDef) -> str:
    prefix = "async def" if isinstance(node, ast.AsyncFunctionDef) else "def"
    args = ast.unparse(node.args)
    returns = f" -> {ast.unparse(node.returns)}" if node.returns else ""
    return f"{prefix} {node.name}({args}){returns}"


def _doc_line(node: ast.AST) -> str | None:
    doc = ast.get_docstring(node)
    return doc.strip().splitlines()[0] if doc else None


def _file_interface(rel: str, tree: ast.Module) -> list[str]:
    """Signatures, class attributes, one-line docstrings — never bodies."""
    lines = [f"## `{rel}`"]
    doc = _doc_line(tree)
    if doc:
        lines.append(f"# {doc}")
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            lines.append(_signature(node))
        elif isinstance(node, ast.ClassDef):
            bases = ", ".join(ast.unparse(b) for b in node.bases)
            lines.append(f"class {node.name}({bases}):" if bases
                         else f"class {node.name}:")
            for item in node.body:
                if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    lines.append(f"    {_signature(item)}")
                elif isinstance(item, ast.Assign):
                    for t in item.targets:
                        if isinstance(t, ast.Name):
                            lines.append(f"    {t.id} = ...")
                elif isinstance(item, ast.AnnAssign) and isinstance(
                        item.target, ast.Name):
                    lines.append(
                        f"    {item.target.id}: {ast.unparse(item.annotation)}")
        elif isinstance(node, ast.Assign):
            for t in node.targets:
                if isinstance(t, ast.Name) and not t.id.startswith("_"):
                    lines.append(f"{t.id} = ...")
    return lines


def _names_used(tree: ast.Module) -> set[str]:
    """Imported module names + attribute/name references (edge detection)."""
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            names.add(node.module.split(".")[0])
            names.update(alias.name for alias in node.names)
        elif isinstance(node, ast.Name):
            names.add(node.id)
    return names


def _top_level_defs(tree: ast.Module) -> set[str]:
    defs: set[str] = set()
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef,
                             ast.ClassDef)):
            defs.add(node.name)
        elif isinstance(node, ast.Assign):
            defs.update(t.id for t in node.targets if isinstance(t, ast.Name))
    return defs


def build(
    root: str | pathlib.Path,
    artifacts: list[str],
    failing_rel: str,
    cap: int = INTERFACE_MAP_MAX_CHARS,
) -> str:
    """Connection-ranked, capped interface map of the OTHER artifacts.

    Rank 0: siblings the failing file imports/references; rank 1: siblings
    importing/referencing the failing file's module or defs; rank 2: rest.
    Cap overflow drops whole files from the tail with an omission note
    (FR-IC-002). Empty string when there is nothing to show.
    """
    base = pathlib.Path(root)
    siblings = [rel for rel in artifacts
                if rel != failing_rel and rel.endswith(".py")]
    if not siblings:
        return ""

    def _parse(rel: str) -> ast.Module | None:
        target = base / rel
        if not target.is_file():
            return None
        try:
            return ast.parse(target.read_text(encoding="utf-8",
                                              errors="replace"))
        except SyntaxError:
            return None

    failing_tree = _parse(failing_rel)
    failing_uses = _names_used(failing_tree) if failing_tree else set()
    failing_exports = ({_module_name(failing_rel)}
                       | (_top_level_defs(failing_tree)
                          if failing_tree else set()))

    ranked: list[tuple[int, str, ast.Module | None]] = []
    for rel in siblings:
        tree = _parse(rel)
        if tree is None:
            ranked.append((2, rel, None))
            continue
        exports = {_module_name(rel)} | _top_level_defs(tree)
        if failing_uses & exports:
            rank = 0  # the failing file depends on this sibling
        elif _names_used(tree) & failing_exports:
            rank = 1  # this sibling depends on the failing file
        else:
            rank = 2
        ranked.append((rank, rel, tree))
    ranked.sort(key=lambda item: item[0])

    blocks: list[str] = []
    used = 0
    omitted = 0
    for _rank, rel, tree in ranked:
        block = ("\n".join(_file_interface(rel, tree)) if tree is not None
                 else f"## `{rel}` (currently broken)")
        if used + len(block) > cap and blocks:
            omitted += 1
            continue
        blocks.append(block)
        used += len(block)
    if omitted:
        blocks.append(f"({omitted} file(s) omitted)")
    return "\n\n".join(blocks)


__all__ = ["build", "INTERFACE_MAP_MAX_CHARS"]
