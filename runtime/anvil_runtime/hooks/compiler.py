"""Hook compiler: canonical hook definitions -> ``.openhands/hooks.json``.

Slice 3 deliverable (spec §4.2.2). Canonical hook rules authored in
policy/config are compiled into the OpenHands-native ``.openhands/hooks.json``
projection so native callbacks stay authoritative. Hook kinds that do not map
1:1 to native callbacks are still emitted here and executed by the
supervisor-managed :class:`~anvil_runtime.hooks.adapter.HookAdapter`.
"""

from __future__ import annotations

import json
import pathlib

from anvil_runtime.hooks.lifecycle_hooks import HookRule

HOOKS_PROJECTION_RELPATH = ".openhands/hooks.json"


class HookCompiler:
    """Compiles hook rules into the runtime hooks projection."""

    def compile(self, rules: list[HookRule]) -> dict[str, object]:
        """Return the ``hooks.json`` document for the given rules."""
        return {
            "version": "0.1.0",
            "hooks": [rule.model_dump(exclude_none=True) for rule in rules],
        }

    def compile_to_file(
        self, rules: list[HookRule], workspace_root: str | pathlib.Path = "."
    ) -> pathlib.Path:
        path = pathlib.Path(workspace_root) / HOOKS_PROJECTION_RELPATH
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", encoding="utf-8") as handle:
            json.dump(self.compile(rules), handle, indent=2, sort_keys=True)
        return path

    @staticmethod
    def load_rules(raw: list[dict[str, object]] | None) -> list[HookRule]:
        """Parse raw hook definitions (from config) into typed rules."""
        return [HookRule.model_validate(item) for item in (raw or [])]


__all__ = ["HookCompiler", "HOOKS_PROJECTION_RELPATH"]
