"""Anvil runtime package.

The Anvil runtime is the localhost service half of Anvil v0.1.0 (see
``docs/architecture.md`` and ``docs/blueprint.md``). It owns supervisor
orchestration, phase contracts, configuration resolution, policy enforcement,
and the versioned REST/SSE API consumed by the VS Code extension.

This module exposes only the package version. Concrete contracts are imported
from their domain subpackages (``api``, ``core``, ``config``, ``policy``,
``agents``) to keep import-time side effects minimal.
"""

from __future__ import annotations

__version__ = "0.1.4"

__all__ = ["__version__"]
