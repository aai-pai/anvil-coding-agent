"""Assert the runtime and extension versions agree (and match a release tag).

Version drift is a real defect in this repo's history: at v0.1.4 the runtime
pyproject still said 0.1.0 and the extension package.json said 0.1.2. This
script is the mechanical gate that stops that recurring -- it runs in CI on
every push and again in the release workflow, where the tag is also compared.

Usage:
    python scripts/check_versions.py            # runtime == extension
    python scripts/check_versions.py v0.1.5     # ...and both == the tag
"""

from __future__ import annotations

import ast
import json
import pathlib
import sys
import tomllib

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
PYPROJECT = REPO_ROOT / "runtime" / "pyproject.toml"
PACKAGE_JSON = REPO_ROOT / "extension" / "package.json"
INIT_PY = REPO_ROOT / "runtime" / "anvil_runtime" / "__init__.py"


def runtime_version() -> str:
    return tomllib.loads(PYPROJECT.read_text(encoding="utf-8"))["project"]["version"]


def extension_version() -> str:
    return json.loads(PACKAGE_JSON.read_text(encoding="utf-8"))["version"]


def dunder_version() -> str:
    """Read ``__version__`` by parsing, so no dependencies need to be installed."""
    tree = ast.parse(INIT_PY.read_text(encoding="utf-8"))
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(
            isinstance(t, ast.Name) and t.id == "__version__" for t in node.targets
        ):
            if isinstance(node.value, ast.Constant):
                return str(node.value.value)
    raise SystemExit(f"__version__ not found in {INIT_PY}")


def main(argv: list[str]) -> int:
    runtime = runtime_version()
    extension = extension_version()
    dunder = dunder_version()
    problems: list[str] = []

    if runtime != extension:
        problems.append(
            f"runtime/pyproject.toml is {runtime} but "
            f"extension/package.json is {extension}"
        )
    if runtime != dunder:
        problems.append(
            f"runtime/pyproject.toml is {runtime} but "
            f"anvil_runtime.__version__ is {dunder}"
        )

    if len(argv) > 1:
        # Release tags are "v<version>"; compare against the bare version.
        tag = argv[1]
        expected = tag[1:] if tag.startswith("v") else tag
        for label, found in (
            ("runtime", runtime),
            ("extension", extension),
            ("__version__", dunder),
        ):
            if found != expected:
                problems.append(f"tag {tag} does not match {label} version {found}")

    if problems:
        print("Version check FAILED:", file=sys.stderr)
        for problem in problems:
            print(f"  - {problem}", file=sys.stderr)
        return 1

    suffix = f" (matches tag {argv[1]})" if len(argv) > 1 else ""
    print(f"Version check OK: runtime, extension and __version__ all {runtime}{suffix}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
