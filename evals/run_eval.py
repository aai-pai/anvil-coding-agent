#!/usr/bin/env python
"""Launcher so the harness works from anywhere without installation:

    python evals/run_eval.py run --suite smoke --start-server --mode offline-llm
"""

import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

from anvil_eval.cli import main  # noqa: E402

raise SystemExit(main())
