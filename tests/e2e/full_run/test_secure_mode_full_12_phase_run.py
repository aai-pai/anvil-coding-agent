"""E2E: full secure-mode 12-phase run with redacted audit trail.

Slice 6 (spec §2.4.3, §2.5, NFR-OB-004; blueprint §7.3; plan §2.6). Drives a
complete secure-mode run through the supervisor, approving each mandatory gate,
and asserts the full ordered 12-phase completion, a written run summary, and a
secret-free (redacted) audit trail.
"""

from __future__ import annotations

import pathlib

from anvil_runtime.api.models import ApprovalRequest, RunStartRequest
from anvil_runtime.core.development_manager import DevelopmentManager
from anvil_runtime.core.phase_contracts import PHASE_IDS
from anvil_runtime.security.redaction import REDACTION_PLACEHOLDER, Redactor
from anvil_runtime.state.event_bus import EventBus

MANDATORY_GATES = ["post-proposal", "post-architecture", "post-blueprint", "pre-deployment"]


def test_full_secure_run_completes_all_phases(tmp_path: pathlib.Path) -> None:
    # Redaction hardening is active on the audit trail for the whole run.
    bus = EventBus(str(tmp_path), redactor=Redactor())
    manager = DevelopmentManager(workspace_root=str(tmp_path), event_bus=bus)
    started = manager.start_run(
        RunStartRequest(mode="secure", security_profile="restricted")
    )

    encountered: list[str] = []
    for _ in range(len(PHASE_IDS) + 4):
        progress = manager.run_until_pause(started.run_id)
        if progress.status == "completed":
            break
        assert progress.status == "awaiting_approval"
        gate = progress.pending_approval_gate
        encountered.append(gate)
        manager.submit_approval(
            started.run_id,
            ApprovalRequest(
                gateId=gate, gateName=gate, approved=True, requesterId="e2e"
            ),
        )
    else:  # pragma: no cover
        raise AssertionError("secure run did not complete within the gate budget")

    final = manager.get_progress(started.run_id)
    assert final.status == "completed"
    # Full, ordered 12-phase completion.
    assert final.completed_phases == list(PHASE_IDS)
    # Each mandatory secure gate was presented, in order.
    assert encountered == MANDATORY_GATES

    # Run summary was written (FR-SV-025).
    assert (tmp_path / "logs" / "run-summary.log").is_file()


def test_audit_trail_is_redacted(tmp_path: pathlib.Path) -> None:
    bus = EventBus(str(tmp_path), redactor=Redactor())
    manager = DevelopmentManager(workspace_root=str(tmp_path), event_bus=bus)
    started = manager.start_run(RunStartRequest(mode="yolo", security_profile="open"))
    manager.run_until_pause(started.run_id)

    # Inject an event carrying a secret-shaped payload through the same bus.
    from anvil_runtime.core.phase_contracts import EventEnvelope

    bus.emit(EventEnvelope(
        timestamp="2026-05-31T00:00:00Z", eventType="PromptSubmitted",
        runId=started.run_id, phase="implementation",
        data={"api_key": "sk-deadbeefcafebabe"},
    ))
    raw = (tmp_path / "logs" / "events.jsonl").read_text(encoding="utf-8")
    assert "sk-deadbeefcafebabe" not in raw
    assert REDACTION_PLACEHOLDER in raw
