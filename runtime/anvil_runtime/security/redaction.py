"""Secret redaction for logs, events, and escalation packets.

Slice 6 deliverable (spec NFR-SC-003, NFR-OB-004, §6.4). The authoritative
runtime-side redactor: applied to events before they are written to the audit
trail or streamed to subscribers, and to any text/mapping that may carry a
secret. Rule families mirror §6.4 — ``api[_-]?key`` / ``password`` / ``token`` /
``secret`` (case-insensitive), plus URLs with embedded credentials — and the key
list is configurable (driven by the ``SecretRedactionRules`` policy values).
"""

from __future__ import annotations

import re
from typing import Iterable

from anvil_runtime.core.phase_contracts import EventEnvelope

REDACTION_PLACEHOLDER = "***REDACTED***"

# Default sensitive key names (§6.4). Matched case-insensitively as substrings of
# a mapping key, and as ``name = value`` / ``name: value`` patterns in free text.
DEFAULT_SENSITIVE_NAMES: tuple[str, ...] = (
    "api[_-]?key",
    "apikey",
    "password",
    "passwd",
    "token",
    "secret",
)

# URL with embedded credentials, e.g. https://user:pass@host -> redact the secret.
_URL_CREDENTIALS = re.compile(r"(?P<scheme>[a-z][a-z0-9+.-]*://)(?P<user>[^:/?#@\s]+):(?P<pw>[^@/?#\s]+)@")
# Bearer / sk- style bare tokens.
_BEARER = re.compile(r"\bBearer\s+[A-Za-z0-9._\-]{8,}\b", re.IGNORECASE)
_SK_KEY = re.compile(r"\bsk-[A-Za-z0-9-]{8,}\b")


class Redactor:
    """Redacts secret-shaped substrings from text, mappings, and events."""

    def __init__(self, sensitive_names: Iterable[str] | None = None) -> None:
        names = tuple(sensitive_names) if sensitive_names is not None else DEFAULT_SENSITIVE_NAMES
        self._names = names
        # `name = value` / `name: value` (value runs to whitespace).
        joined = "|".join(names)
        self._assignment = re.compile(
            rf"(?i)((?:{joined})\s*[=:]\s*)(\S+)"
        )
        self._key_match = re.compile(rf"(?i)(?:{joined})")

    # -- text -------------------------------------------------------------

    def redact_text(self, text: str) -> str:
        """Redact secret values while preserving the surrounding key/label."""
        out = self._assignment.sub(lambda m: f"{m.group(1)}{REDACTION_PLACEHOLDER}", text)
        out = _URL_CREDENTIALS.sub(
            lambda m: f"{m.group('scheme')}{m.group('user')}:{REDACTION_PLACEHOLDER}@", out
        )
        out = _BEARER.sub(f"Bearer {REDACTION_PLACEHOLDER}", out)
        out = _SK_KEY.sub(REDACTION_PLACEHOLDER, out)
        return out

    # -- mappings ---------------------------------------------------------

    def redact_mapping(self, data: dict) -> dict:
        """Redact values whose key name is sensitive; recurse into nested data."""
        result: dict = {}
        for key, value in data.items():
            if isinstance(key, str) and self._key_match.search(key):
                result[key] = REDACTION_PLACEHOLDER
            else:
                result[key] = self._redact_value(value)
        return result

    def _redact_value(self, value: object) -> object:
        if isinstance(value, str):
            return self.redact_text(value)
        if isinstance(value, dict):
            return self.redact_mapping(value)
        if isinstance(value, list):
            return [self._redact_value(item) for item in value]
        return value

    # -- events -----------------------------------------------------------

    def redact_event(self, event: EventEnvelope) -> EventEnvelope:
        """Return a copy of the event with its ``data`` payload redacted."""
        return event.model_copy(update={"data": self.redact_mapping(event.data)})


__all__ = ["Redactor", "REDACTION_PLACEHOLDER", "DEFAULT_SENSITIVE_NAMES"]
