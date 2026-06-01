// Anvil extension configuration constants and operating-mode helpers.
//
// Slice 1 deliverable (blueprint §6.2, §6.3). These constants mirror the
// runtime-side values in `runtime/anvil_runtime/config/schema.py` so the thin
// client and the runtime agree on modes, gates, and the localhost endpoint.

export const API_BASE_URL = "http://127.0.0.1:8765";

export type OperatingMode = "yolo" | "gated" | "secure";
export type SecurityProfile = "open" | "restricted" | "strict";

export const DEFAULT_MODE: OperatingMode = "gated";
export const DEFAULT_SECURITY_PROFILE: SecurityProfile = "restricted";

export const OPERATING_MODES: readonly OperatingMode[] = [
  "yolo",
  "gated",
  "secure",
] as const;

export const SECURITY_PROFILES: readonly SecurityProfile[] = [
  "open",
  "restricted",
  "strict",
] as const;

// The four mandatory secure-mode checkpoints (proposal §7). Users may add more
// but cannot remove these.
export const SECURE_MANDATORY_GATES = [
  "post-proposal",
  "post-architecture",
  "post-blueprint",
  "pre-deployment",
] as const;

export type SecureMandatoryGate = (typeof SECURE_MANDATORY_GATES)[number];

/** Type guard: is the value one of the three operating modes? */
export function isOperatingMode(value: string): value is OperatingMode {
  return (OPERATING_MODES as readonly string[]).includes(value);
}

/** Normalize arbitrary input to a valid operating mode, falling back to default. */
export function normalizeMode(value: string | undefined): OperatingMode {
  return value !== undefined && isOperatingMode(value) ? value : DEFAULT_MODE;
}

/** Secure mode enforces all four mandatory gates; other modes enforce none by default. */
export function mandatoryGatesForMode(mode: OperatingMode): readonly string[] {
  return mode === "secure" ? SECURE_MANDATORY_GATES : [];
}

/** True when the given gate is one of the immutable secure-mode checkpoints. */
export function isSecureMandatoryGate(gate: string): gate is SecureMandatoryGate {
  return (SECURE_MANDATORY_GATES as readonly string[]).includes(gate);
}
