"""AST-based function-body grafting: skeleton stays, generated bodies land.

Anvil's implementation phase regenerates whole modules from its plan docs and
(without reading the skeleton source) drops everything the skeleton already
provided — type aliases, implemented classes, ``__all__`` (observed: the
tinydb run lost ``QueryLike``, ``FrozenDict``, ``LRUCache``, ``MemoryStorage``).
Whole-file replacement therefore breaks imports even when every generated
implementation is fine.

Grafting is the faithful translation of "fill in the skeleton": for each stub
function in the skeleton module, transplant the same-qualname function from
the generated module; keep every other skeleton line exactly as shipped. The
graded content (the stub bodies) remains 100% model-generated.
"""

from __future__ import annotations

import ast
import dataclasses

from commit0_adapter.stubs import _is_stub_body, referenced_undefined


@dataclasses.dataclass
class _FuncSpan:
    qualname: str
    node: ast.FunctionDef | ast.AsyncFunctionDef
    start_line: int  # 1-based, includes decorators
    end_line: int    # 1-based, inclusive


def _index_functions(tree: ast.Module) -> dict[str, _FuncSpan]:
    spans: dict[str, _FuncSpan] = {}

    def visit(node: ast.AST, prefix: str) -> None:
        for child in ast.iter_child_nodes(node):
            if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                start = min([child.lineno]
                            + [d.lineno for d in child.decorator_list])
                spans[f"{prefix}{child.name}"] = _FuncSpan(
                    qualname=f"{prefix}{child.name}", node=child,
                    start_line=start, end_line=child.end_lineno or child.lineno)
                visit(child, f"{prefix}{child.name}.")
            elif isinstance(child, ast.ClassDef):
                visit(child, f"{prefix}{child.name}.")

    visit(tree, "")
    return spans


def _reindent(lines: list[str], from_col: int, to_col: int) -> list[str]:
    if from_col == to_col:
        return lines
    out = []
    for line in lines:
        if not line.strip():
            out.append(line)
        elif from_col < to_col:
            out.append(" " * (to_col - from_col) + line)
        else:
            cut = min(from_col - to_col, len(line) - len(line.lstrip()))
            out.append(line[cut:])
    return out


def _missing_imports(skeleton_tree: ast.Module, generated_tree: ast.Module) -> list[str]:
    """Top-level import statements the generated code has and the skeleton lacks."""
    def render(tree: ast.Module) -> dict[str, ast.stmt]:
        return {ast.unparse(node): node for node in tree.body
                if isinstance(node, (ast.Import, ast.ImportFrom))}

    skeleton_imports = render(skeleton_tree)
    return [text for text in render(generated_tree) if text not in skeleton_imports]


def graft_module(skeleton_src: str, generated_src: str) -> tuple[str, dict]:
    """Return (merged source, stats). Never raises on model output: a generated
    module that fails to parse grafts nothing (stats say so)."""
    stats = {"stubs": 0, "grafted": 0, "missing_in_generated": [],
             "imports_added": 0}
    skeleton_tree = ast.parse(skeleton_src)
    try:
        generated_tree = ast.parse(generated_src)
    except SyntaxError:
        stats["error"] = "generated module is not valid python"
        return skeleton_src, stats

    skeleton_funcs = _index_functions(skeleton_tree)
    generated_funcs = _index_functions(generated_tree)
    skeleton_lines = skeleton_src.splitlines()
    generated_lines = generated_src.splitlines()

    stubs = [s for s in skeleton_funcs.values() if _is_stub_body(s.node)]
    stats["stubs"] = len(stubs)
    # Bottom-up so earlier line numbers stay valid while splicing.
    for span in sorted(stubs, key=lambda s: s.start_line, reverse=True):
        source = generated_funcs.get(span.qualname)
        if source is None:
            stats["missing_in_generated"].append(span.qualname)
            continue
        replacement = _reindent(
            generated_lines[source.start_line - 1:source.end_line],
            source.node.col_offset, span.node.col_offset)
        skeleton_lines[span.start_line - 1:span.end_line] = replacement
        stats["grafted"] += 1

    # Insertion pass: generated functions the skeleton LACKS entirely.
    # Commit0's stripper sometimes deletes a whole definition and leaves a
    # dangling reference (tinydb: `__setitem__ = _immutable` with the def
    # gone), so filling stubs alone cannot make the module import. Insert a
    # generated method when its parent class exists in the skeleton; insert a
    # module-level def only when the skeleton actually references that name.
    stats["inserted"] = 0
    dangling = set(referenced_undefined(skeleton_src))
    merged_src = "\n".join(skeleton_lines)
    merged_tree = ast.parse(merged_src)
    merged_funcs = _index_functions(merged_tree)
    class_spans: dict[str, ast.ClassDef] = {}

    def index_classes(node: ast.AST, prefix: str) -> None:
        for child in ast.iter_child_nodes(node):
            if isinstance(child, ast.ClassDef):
                class_spans[f"{prefix}{child.name}"] = child
                index_classes(child, f"{prefix}{child.name}.")

    index_classes(merged_tree, "")
    insertions: list[tuple[int, list[str]]] = []  # (after_line, lines)
    for qualname, span in generated_funcs.items():
        if qualname in merged_funcs:
            continue
        parent, _, name = qualname.rpartition(".")
        body = generated_lines[span.start_line - 1:span.end_line]
        if parent and parent in class_spans:
            target = class_spans[parent]
            indent = target.body[0].col_offset if target.body else target.col_offset + 4
            insertions.append((target.end_lineno or target.lineno,
                               [""] + _reindent(body, span.node.col_offset, indent)))
        elif not parent and name in dangling:
            # Insert BEFORE the first top-level statement that references the
            # name, not at end-of-file: a reference inside a class body (the
            # observed tinydb case, `__setitem__ = _immutable` in FrozenDict)
            # executes at import time, so a def appended after the class
            # raises NameError before the module ever loads.
            insert_after = len(skeleton_lines)
            for stmt in merged_tree.body:
                if any(isinstance(n, ast.Name) and n.id == name
                       and isinstance(n.ctx, ast.Load) for n in ast.walk(stmt)):
                    first_line = min([stmt.lineno]
                                     + [d.lineno for d in
                                        getattr(stmt, "decorator_list", [])])
                    insert_after = first_line - 1
                    break
            insertions.append((insert_after,
                               [""] + _reindent(body, span.node.col_offset, 0)
                               + [""]))
    for after_line, lines in sorted(insertions, reverse=True):
        skeleton_lines[after_line:after_line] = lines
        stats["inserted"] += 1

    # Generated bodies may rely on imports the skeleton never needed.
    extra_imports = _missing_imports(skeleton_tree, generated_tree)
    if extra_imports and (stats["grafted"] or stats["inserted"]):
        insert_at = 0
        for index, node in enumerate(ast.parse("\n".join(skeleton_lines)).body):
            if isinstance(node, (ast.Import, ast.ImportFrom)):
                insert_at = node.end_lineno or node.lineno
            elif index == 0 and isinstance(node, ast.Expr):  # module docstring
                insert_at = node.end_lineno or node.lineno
        skeleton_lines[insert_at:insert_at] = extra_imports
        stats["imports_added"] = len(extra_imports)

    merged = "\n".join(skeleton_lines)
    if skeleton_src.endswith("\n"):
        merged += "\n"
    try:
        ast.parse(merged)
    except SyntaxError:
        stats["error"] = "merged module failed to parse; skeleton kept"
        return skeleton_src, {**stats, "grafted": 0, "inserted": 0,
                              "imports_added": 0}
    return merged, stats


__all__ = ["graft_module"]
