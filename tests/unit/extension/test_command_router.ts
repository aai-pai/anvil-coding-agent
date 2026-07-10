// Unit tests for the chat command parser.
//
// Slice 4 (blueprint §3.2; plan §2.4). Runner: vitest. `parseCommand` is pure,
// so these run without the VS Code API or a live runtime.
// NOTE: requires Node.js/npm; written to spec and runs wherever Node is present.

import { describe, expect, it } from "vitest";

import { parseCommand } from "../../../extension/src/chat/commandRouter";

describe("parseCommand: start", () => {
  it("parses mode and security profile", () => {
    const cmd = parseCommand("start secure strict");
    expect(cmd).toEqual({
      kind: "start",
      mode: "secure",
      securityProfile: "strict",
      extraGates: [],
    });
  });

  it("accepts a leading slash and extra gates", () => {
    const cmd = parseCommand("/start gated restricted post-spec post-qa");
    expect(cmd).toMatchObject({
      kind: "start",
      mode: "gated",
      securityProfile: "restricted",
      extraGates: ["post-spec", "post-qa"],
    });
  });

  it("normalizes an invalid mode and profile to defaults", () => {
    const cmd = parseCommand("start turbo paranoid");
    expect(cmd).toMatchObject({
      kind: "start",
      mode: "gated", // normalizeMode fallback
      securityProfile: "restricted", // DEFAULT_SECURITY_PROFILE fallback
    });
  });
});

describe("parseCommand: build", () => {
  it("captures the full free-form description", () => {
    expect(parseCommand("build a CLI that converts Celsius to Fahrenheit")).toEqual({
      kind: "build",
      description: "a CLI that converts Celsius to Fahrenheit",
    });
  });

  it("accepts make/create aliases and a leading slash", () => {
    expect(parseCommand("/make a todo list app")).toEqual({
      kind: "build",
      description: "a todo list app",
    });
    expect(parseCommand("create a password generator")).toMatchObject({
      kind: "build",
    });
  });

  it("returns an empty description for a bare build (file-based flow, FR-SRC-005)", () => {
    expect(parseCommand("build")).toEqual({ kind: "build", description: "" });
  });
});

describe("parseCommand: answer", () => {
  it("captures the raw answer text (FR-INT-012)", () => {
    expect(parseCommand("answer yes, localStorage; plain HTML")).toEqual({
      kind: "answer",
      text: "yes, localStorage; plain HTML",
    });
  });

  it("accepts the clarify alias and falls back to help when empty", () => {
    expect(parseCommand("clarify use sqlite")).toEqual({
      kind: "answer",
      text: "use sqlite",
    });
    expect(parseCommand("answer")).toEqual({ kind: "help" });
  });
});

describe("parseCommand: approvals", () => {
  it("parses approve with a comment", () => {
    expect(parseCommand("approve looks good to me")).toEqual({
      kind: "approve",
      comments: "looks good to me",
    });
  });

  it("treats yes/no as approve/deny", () => {
    expect(parseCommand("yes")).toEqual({ kind: "approve", comments: undefined });
    expect(parseCommand("no")).toEqual({ kind: "deny", comments: undefined });
  });
});

describe("parseCommand: overrides", () => {
  it("parses stop with a default reason", () => {
    expect(parseCommand("stop")).toEqual({
      kind: "override",
      action: "stop",
      reason: "user stop",
    });
  });

  it("parses rollback with a target phase and reason", () => {
    expect(parseCommand("rollback architecture spec drifted")).toEqual({
      kind: "override",
      action: "rollback",
      targetPhase: "architecture",
      reason: "spec drifted",
    });
  });

  it("parses force-advance", () => {
    expect(parseCommand("force-advance trust me")).toEqual({
      kind: "override",
      action: "force-advance",
      reason: "trust me",
    });
  });

  it("does not treat bare `advance` as a gate-bypassing override", () => {
    expect(parseCommand("advance")).toEqual({
      kind: "unknown",
      input: "advance",
    });
  });
});

describe("parseCommand: misc", () => {
  it("maps status and health", () => {
    expect(parseCommand("status")).toEqual({ kind: "status" });
    expect(parseCommand("health")).toEqual({ kind: "health" });
  });

  it("returns help on empty input", () => {
    expect(parseCommand("   ")).toEqual({ kind: "help" });
  });

  it("returns unknown for unrecognized verbs", () => {
    expect(parseCommand("frobnicate now")).toEqual({
      kind: "unknown",
      input: "frobnicate now",
    });
  });
});
