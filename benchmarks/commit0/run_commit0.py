#!/usr/bin/env python
"""Launcher: python benchmarks/commit0/run_commit0.py run --repo tinydb ..."""

import pathlib
import sys

_here = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(_here))                              # commit0_adapter
sys.path.insert(0, str(_here.parent.parent / "evals"))      # anvil_eval

from commit0_adapter.cli import main  # noqa: E402

raise SystemExit(main())
