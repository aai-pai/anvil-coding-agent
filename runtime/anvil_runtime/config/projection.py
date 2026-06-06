"""Runtime projection writer.

Slice 3 deliverable (proposal §8.5; spec §8.5; blueprint §6.1). Materializes the
effective configuration into workspace-local runtime files so OpenHands-native
paths stay authoritative and the run is reproducible/auditable:

* ``.openhands/runtime/mcp.generated.json``    — resolved MCP server set
* ``.openhands/runtime/policy-snapshot.json``  — policy-relevant effective config
* ``.openhands/hooks.json``                    — compiled hook rules
* ensures ``logs/`` exists for the audit trail
"""

from __future__ import annotations

import hashlib
import json
import pathlib

from pydantic import BaseModel, Field

from anvil_runtime.config.schema import EffectiveConfig
from anvil_runtime.hooks.compiler import HookCompiler
from anvil_runtime.hooks.lifecycle_hooks import HookRule

MCP_PROJECTION_RELPATH = ".openhands/runtime/mcp.generated.json"
POLICY_SNAPSHOT_RELPATH = ".openhands/runtime/policy-snapshot.json"


class ProjectionManifest(BaseModel):
    """Record of what the projection wrote, with content checksums."""

    written_files: list[str] = Field(default_factory=list)
    checksums: dict[str, str] = Field(default_factory=dict)


class RuntimeProjectionWriter:
    """Writes effective runtime files under ``.openhands/`` and ``logs/``."""

    def __init__(
        self,
        workspace_root: str | pathlib.Path = ".",
        hook_compiler: HookCompiler | None = None,
    ) -> None:
        self._root = pathlib.Path(workspace_root)
        self._hook_compiler = hook_compiler or HookCompiler()

    def write_projection(
        self, cfg: EffectiveConfig, hook_rules: list[HookRule] | None = None
    ) -> ProjectionManifest:
        manifest = ProjectionManifest()

        mcp_doc = {"mcpServers": cfg.mcpServers}
        self._write_json(MCP_PROJECTION_RELPATH, mcp_doc, manifest)

        policy_snapshot = {
            "configVersion": cfg.configVersion,
            "mode": cfg.mode,
            "securityProfile": cfg.securityProfile,
            "allowedModels": cfg.allowedModels,
            "tokenBudgetPerPhase": cfg.tokenBudgetPerPhase,
            "requiredApprovalGates": cfg.requiredApprovalGates,
            "maxRetriesPerPhase": cfg.maxRetriesPerPhase,
        }
        self._write_json(POLICY_SNAPSHOT_RELPATH, policy_snapshot, manifest)

        hooks_path = self._hook_compiler.compile_to_file(hook_rules or [], self._root)
        self._record(hooks_path, manifest)

        # Ensure the audit-trail directory exists (FR-SV-026).
        (self._root / "logs").mkdir(parents=True, exist_ok=True)

        return manifest

    def _write_json(self, relpath: str, doc: dict, manifest: ProjectionManifest) -> None:
        path = self._root / relpath
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", encoding="utf-8") as handle:
            json.dump(doc, handle, indent=2, sort_keys=True)
        self._record(path, manifest)

    def _record(self, path: pathlib.Path, manifest: ProjectionManifest) -> None:
        rel = str(path.relative_to(self._root)).replace("\\", "/")
        manifest.written_files.append(rel)
        manifest.checksums[rel] = hashlib.sha256(path.read_bytes()).hexdigest()


__all__ = [
    "RuntimeProjectionWriter",
    "ProjectionManifest",
    "MCP_PROJECTION_RELPATH",
    "POLICY_SNAPSHOT_RELPATH",
]
