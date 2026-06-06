"""Artifact lookup route.

Slice 4 deliverable (blueprint §5.1 endpoint 6). ``GET /v1/artifacts/{phase}``
reports the on-disk primary artifact a phase owns: its path (from the phase
contract's ``allowed_outputs``), the SHA-256 checksum of the file bytes, and the
file's last-modified time as ``generatedAt``.

A phase whose contract only owns directories (e.g. ``implementation`` -> ``src/``)
has no single document artifact; such phases, unknown phases, and not-yet-generated
artifacts return ``404``.
"""

from __future__ import annotations

import pathlib
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status

from anvil_runtime.api.deps import get_workspace_root
from anvil_runtime.api.models import ArtifactResponse
from anvil_runtime.core.phase_contracts import PHASE_CONTRACTS, PhaseContract
from anvil_runtime.state.checkpoint_store import compute_checksum

router = APIRouter(prefix="/v1/artifacts", tags=["artifacts"])


def primary_artifact_path(contract: PhaseContract) -> str | None:
    """First file-shaped (non-directory) output a phase owns, else ``None``."""
    for out in contract.allowed_outputs:
        if out.endswith("/"):
            continue
        if "." in pathlib.PurePosixPath(out).name:
            return out
    return None


@router.get("/{phase}", response_model=ArtifactResponse)
def get_artifact(
    phase: str,
    workspace_root: str = Depends(get_workspace_root),
) -> ArtifactResponse:
    """``GET /v1/artifacts/{phase}`` — path, checksum, and generated-at time."""
    contract = PHASE_CONTRACTS.get(phase)
    if contract is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=f"Unknown phase '{phase}'"
        )
    rel = primary_artifact_path(contract)
    if rel is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Phase '{phase}' has no document artifact",
        )
    target = pathlib.Path(workspace_root) / rel
    if not target.is_file():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Artifact for phase '{phase}' has not been generated",
        )
    generated_at = datetime.fromtimestamp(target.stat().st_mtime, tz=timezone.utc)
    return ArtifactResponse(
        phase=phase,
        path=rel,
        checksum=compute_checksum(target),
        generatedAt=generated_at,
    )


__all__ = ["router", "primary_artifact_path"]
