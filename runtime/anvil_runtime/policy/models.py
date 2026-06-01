"""Policy data models and the policy-rule JSON schema.

Slice 1 deliverable (blueprint §4.2; spec §4.3, §2.6). These are the typed
contracts the policy engine (Slice 3) loads, merges, and evaluates. Field names
mirror the spec's policy-file schema (§4.3) verbatim so authored YAML/JSON
policies validate without translation.
"""

from __future__ import annotations

from pydantic import BaseModel, Field

POLICY_SCHEMA_VERSION = "0.1.0"


class PolicyRule(BaseModel):
    """A single policy rule (spec §4.3).

    Different rule ``type`` values populate different optional carriers
    (``values`` for whitelists, ``limits`` for numeric limits, ``gates`` for
    mandatory lists). Per FR-PL-003A, ``remediable`` defaults to ``False`` and a
    ``remediationStrategy`` is only meaningful when ``remediable`` is ``True``.
    """

    name: str
    type: str
    target: str
    # Type-specific carriers (optional; populated per rule ``type``).
    values: list[str] | None = None
    limits: dict[str, int] | None = None
    gates: list[str] | None = None
    mode: str | None = None
    # Remediation metadata (FR-PL-003A).
    remediable: bool = False
    remediationStrategy: str | None = None


class PolicyDocument(BaseModel):
    """A versioned collection of policy rules (spec §4.3)."""

    policyVersion: str = POLICY_SCHEMA_VERSION
    policies: list[PolicyRule] = Field(default_factory=list)


# Blueprint §4.2: POLICY_RULE_SCHEMA stored as a constant in policy/models.py,
# derived from the canonical model for a single source of truth.
POLICY_RULE_SCHEMA: dict[str, object] = PolicyRule.model_json_schema()


__all__ = [
    "POLICY_SCHEMA_VERSION",
    "PolicyRule",
    "PolicyDocument",
    "POLICY_RULE_SCHEMA",
]
