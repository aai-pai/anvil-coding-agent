// Chat command parser for the Anvil participant.
//
// Slice 4 deliverable (blueprint §2.2, §3.2). Pure, deterministic parsing of a
// user's chat message into a typed `ChatCommand`. Kept free of the VS Code API
// and the runtime client so it is fully unit-testable. The participant
// (`participant.ts`) executes the parsed command against `RuntimeClient`.

import {
  DEFAULT_SECURITY_PROFILE,
  SECURITY_PROFILES,
  normalizeMode,
  type OperatingMode,
  type SecurityProfile,
} from "../config/modeSelector";

export type OverrideAction = "force-advance" | "rollback" | "stop";

export type ChatCommand =
  | {
      kind: "start";
      mode: OperatingMode;
      securityProfile: SecurityProfile;
      extraGates: string[];
    }
  | { kind: "build"; description: string }
  | { kind: "approve"; comments?: string }
  | { kind: "deny"; comments?: string }
  | { kind: "status" }
  | { kind: "health" }
  | {
      kind: "override";
      action: OverrideAction;
      targetPhase?: string;
      reason: string;
    }
  | { kind: "help" }
  | { kind: "unknown"; input: string };

function isSecurityProfile(value: string): value is SecurityProfile {
  return (SECURITY_PROFILES as readonly string[]).includes(value);
}

/** Parse a raw chat message into a typed command. */
export function parseCommand(raw: string): ChatCommand {
  const trimmed = raw.trim();
  if (trimmed === "") {
    return { kind: "help" };
  }
  // Tokenize; the leading verb may carry a `/` prefix (e.g. `/start`).
  const tokens = trimmed.split(/\s+/);
  const verb = tokens[0].replace(/^\//, "").toLowerCase();
  const rest = tokens.slice(1);

  switch (verb) {
    case "start":
    case "run":
      return parseStart(rest);
    case "build":
    case "make":
    case "create": {
      const description = rest.join(" ").trim();
      return description
        ? { kind: "build", description }
        : { kind: "help" };
    }
    case "approve":
    case "yes":
      return { kind: "approve", comments: joinOrUndefined(rest) };
    case "deny":
    case "reject":
    case "no":
      return { kind: "deny", comments: joinOrUndefined(rest) };
    case "status":
    case "state":
      return { kind: "status" };
    case "health":
      return { kind: "health" };
    case "stop":
    case "abort":
      return {
        kind: "override",
        action: "stop",
        reason: joinOrUndefined(rest) ?? "user stop",
      };
    case "rollback":
      return {
        kind: "override",
        action: "rollback",
        targetPhase: rest[0],
        reason: joinOrUndefined(rest.slice(1)) ?? "user rollback",
      };
    case "force":
    case "force-advance":
    case "advance":
      return {
        kind: "override",
        action: "force-advance",
        reason: joinOrUndefined(rest) ?? "user force-advance",
      };
    case "help":
    case "?":
      return { kind: "help" };
    default:
      return { kind: "unknown", input: trimmed };
  }
}

function parseStart(args: string[]): ChatCommand {
  // Grammar: start [mode] [securityProfile] [extraGate...]
  const mode = normalizeMode(args[0]);
  const profile =
    args[1] !== undefined && isSecurityProfile(args[1])
      ? args[1]
      : DEFAULT_SECURITY_PROFILE;
  const extraGates = args
    .slice(2)
    .filter((gate) => gate.length > 0);
  return { kind: "start", mode, securityProfile: profile, extraGates };
}

function joinOrUndefined(parts: string[]): string | undefined {
  const text = parts.join(" ").trim();
  return text.length > 0 ? text : undefined;
}
