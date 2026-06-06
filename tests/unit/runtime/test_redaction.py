"""Unit tests: secret redaction.

Slice 6 (spec NFR-SC-003, NFR-OB-004, §6.4; plan §2.6). Verifies text/mapping/
event redaction and the event-bus integration (events redacted before logging).
"""

from __future__ import annotations

import pathlib

from anvil_runtime.core.phase_contracts import EventEnvelope
from anvil_runtime.security.redaction import REDACTION_PLACEHOLDER, Redactor
from anvil_runtime.state.event_bus import EventBus


def test_redacts_assignment_patterns() -> None:
    r = Redactor()
    assert "SECRET123" not in r.redact_text("api_key=SECRET123")
    assert "hunter2" not in r.redact_text("password: hunter2")
    assert "tokABCDEFGH" not in r.redact_text("token = tokABCDEFGH")


def test_redacts_url_credentials_and_bearer() -> None:
    r = Redactor()
    out = r.redact_text("connect https://user:p4ssw0rd@host/db")
    assert "p4ssw0rd" not in out
    assert "user" in out  # username preserved, only the secret removed
    assert REDACTION_PLACEHOLDER in r.redact_text("Authorization: Bearer abcdef123456")
    assert REDACTION_PLACEHOLDER in r.redact_text("key sk-abcdef123456")


def test_redacts_mapping_by_key_name() -> None:
    r = Redactor()
    out = r.redact_mapping({"apiKey": "x", "nested": {"secret": "y"}, "ok": "fine"})
    assert out["apiKey"] == REDACTION_PLACEHOLDER
    assert out["nested"]["secret"] == REDACTION_PLACEHOLDER
    assert out["ok"] == "fine"


def test_redact_event_copies_and_scrubs() -> None:
    r = Redactor()
    ev = EventEnvelope(
        timestamp="2026-05-31T00:00:00Z", eventType="PromptSubmitted",
        runId="r1", phase="implementation", data={"api_key": "leak", "model": "gemma-4"},
    )
    redacted = r.redact_event(ev)
    assert redacted.data["api_key"] == REDACTION_PLACEHOLDER
    assert redacted.data["model"] == "gemma-4"
    assert ev.data["api_key"] == "leak"  # original untouched


def test_event_bus_redacts_before_logging(tmp_path: pathlib.Path) -> None:
    bus = EventBus(str(tmp_path), redactor=Redactor())
    bus.emit(EventEnvelope(
        timestamp="2026-05-31T00:00:00Z", eventType="ToolInvoked",
        runId="r1", phase="implementation", data={"token": "supersecret"},
    ))
    raw = bus.events_path.read_text(encoding="utf-8")
    assert "supersecret" not in raw
    assert REDACTION_PLACEHOLDER in raw
    # Round-trips back as a valid envelope.
    assert bus.read_all()[0].data["token"] == REDACTION_PLACEHOLDER


def test_event_bus_without_redactor_is_unchanged(tmp_path: pathlib.Path) -> None:
    bus = EventBus(str(tmp_path))
    bus.emit(EventEnvelope(
        timestamp="2026-05-31T00:00:00Z", eventType="X", runId="r1",
        phase="", data={"token": "kept"},
    ))
    assert bus.read_all()[0].data["token"] == "kept"
