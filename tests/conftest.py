"""Pytest bootstrap for the Anvil test suite.

Adds ``runtime/`` to ``sys.path`` so ``import anvil_runtime`` resolves without an
editable install. This keeps the test suite runnable directly from the repo root
(``python -m pytest tests``) on a clean checkout.
"""

from __future__ import annotations

import pathlib
import sys

_REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
_RUNTIME_DIR = _REPO_ROOT / "runtime"

if str(_RUNTIME_DIR) not in sys.path:
    sys.path.insert(0, str(_RUNTIME_DIR))
