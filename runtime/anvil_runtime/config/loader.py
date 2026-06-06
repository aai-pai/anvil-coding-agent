"""Configuration source loading (four-level precedence).

Slice 3 deliverable (spec §2.7.1; FR-CF-007). Loads the four configuration
levels — run-time flags, workspace ``.anvil/config.yaml``, user-root
``~/.anvil/config.yaml``, and built-in defaults — into a :class:`ConfigSources`
bundle for the merger. YAML/JSON syntax errors are surfaced with context
(FR-CF-007); missing files are treated as empty levels.
"""

from __future__ import annotations

import pathlib

import yaml
from pydantic import BaseModel, Field

from anvil_runtime.config.schema import (
    CONFIG_VERSION,
    DEFAULT_MAX_RETRIES_PER_PHASE,
    DEFAULT_MODE,
    DEFAULT_SECURITY_PROFILE,
)

WORKSPACE_CONFIG_RELPATH = ".anvil/config.yaml"
USER_CONFIG_RELPATH = ".anvil/config.yaml"  # under the user home directory


def builtin_defaults() -> dict[str, object]:
    """Level 4: extension built-in defaults (FR-CF-001 fallback)."""
    return {
        "configVersion": CONFIG_VERSION,
        "mode": DEFAULT_MODE,
        "securityProfile": DEFAULT_SECURITY_PROFILE,
        "allowedModels": [],
        "tokenBudgetPerPhase": {},
        "maxRetriesPerPhase": DEFAULT_MAX_RETRIES_PER_PHASE,
        "requiredApprovalGates": [],
        "mcpServers": [],
    }


class ConfigSources(BaseModel):
    """The four precedence levels, lowest to highest. Each is a raw mapping."""

    builtin: dict[str, object] = Field(default_factory=dict)
    user_root: dict[str, object] = Field(default_factory=dict)
    workspace: dict[str, object] = Field(default_factory=dict)
    run_flags: dict[str, object] = Field(default_factory=dict)

    def ordered_low_to_high(self) -> list[dict[str, object]]:
        return [self.builtin, self.user_root, self.workspace, self.run_flags]


class ConfigLoader:
    """Reads configuration files from the four precedence levels."""

    def __init__(
        self,
        workspace_root: str | pathlib.Path = ".",
        user_home: str | pathlib.Path | None = None,
    ) -> None:
        self._workspace_root = pathlib.Path(workspace_root)
        self._user_home = pathlib.Path(user_home) if user_home is not None else pathlib.Path.home()

    def load_sources(self, run_flags: dict[str, object] | None = None) -> ConfigSources:
        return ConfigSources(
            builtin=builtin_defaults(),
            user_root=self._read_yaml(self._user_home / USER_CONFIG_RELPATH),
            workspace=self._read_yaml(self._workspace_root / WORKSPACE_CONFIG_RELPATH),
            run_flags=dict(run_flags or {}),
        )

    @staticmethod
    def _read_yaml(path: pathlib.Path) -> dict[str, object]:
        if not path.exists():
            return {}
        try:
            with path.open("r", encoding="utf-8") as handle:
                data = yaml.safe_load(handle)
        except yaml.YAMLError as exc:  # FR-CF-007: report with context
            raise ValueError(f"Malformed configuration file '{path}': {exc}") from exc
        if data is None:
            return {}
        if not isinstance(data, dict):
            raise ValueError(f"Configuration file '{path}' must be a mapping at top level")
        return data


__all__ = ["ConfigLoader", "ConfigSources", "builtin_defaults"]
