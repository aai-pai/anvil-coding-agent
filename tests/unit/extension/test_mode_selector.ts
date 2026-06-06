// Unit tests for the extension mode-selector constants and helpers.
//
// Slice 1 (blueprint §6.2, §6.3). Runner: vitest (see extension/vitest.config.ts).
// NOTE: this suite requires Node.js/npm, which is unavailable in the current
// authoring environment; it is written to spec and runs wherever Node is present.

import { describe, expect, it } from "vitest";

import {
  API_BASE_URL,
  DEFAULT_MODE,
  DEFAULT_SECURITY_PROFILE,
  SECURE_MANDATORY_GATES,
  isOperatingMode,
  isSecureMandatoryGate,
  mandatoryGatesForMode,
  normalizeMode,
} from "../../../extension/src/config/modeSelector";
import {
  DEFAULT_WORKSPACE_CONFIG,
  resolveWorkspaceConfig,
} from "../../../extension/src/config/workspaceConfig";

describe("modeSelector constants", () => {
  it("uses the loopback runtime endpoint", () => {
    expect(API_BASE_URL).toBe("http://127.0.0.1:8765");
  });

  it("defaults to gated mode and restricted profile", () => {
    expect(DEFAULT_MODE).toBe("gated");
    expect(DEFAULT_SECURITY_PROFILE).toBe("restricted");
  });

  it("declares the four immutable secure gates in order", () => {
    expect([...SECURE_MANDATORY_GATES]).toEqual([
      "post-proposal",
      "post-architecture",
      "post-blueprint",
      "pre-deployment",
    ]);
  });
});

describe("operating-mode helpers", () => {
  it("recognizes valid modes", () => {
    expect(isOperatingMode("secure")).toBe(true);
    expect(isOperatingMode("turbo")).toBe(false);
  });

  it("normalizes unknown/empty input to the default mode", () => {
    expect(normalizeMode("yolo")).toBe("yolo");
    expect(normalizeMode("nope")).toBe("gated");
    expect(normalizeMode(undefined)).toBe("gated");
  });

  it("enforces mandatory gates only in secure mode", () => {
    expect(mandatoryGatesForMode("secure")).toHaveLength(4);
    expect(mandatoryGatesForMode("gated")).toHaveLength(0);
    expect(mandatoryGatesForMode("yolo")).toHaveLength(0);
  });

  it("identifies secure mandatory gates", () => {
    expect(isSecureMandatoryGate("post-blueprint")).toBe(true);
    expect(isSecureMandatoryGate("post-spec")).toBe(false);
  });
});

describe("workspace config resolution", () => {
  it("returns defaults when no overrides are supplied", () => {
    expect(resolveWorkspaceConfig()).toEqual(DEFAULT_WORKSPACE_CONFIG);
  });

  it("applies overrides and normalizes an invalid mode", () => {
    const cfg = resolveWorkspaceConfig({
      mode: "bogus",
      securityProfile: "strict",
      extraApprovalGates: ["post-spec"],
    });
    expect(cfg.mode).toBe("gated");
    expect(cfg.securityProfile).toBe("strict");
    expect(cfg.extraApprovalGates).toEqual(["post-spec"]);
  });
});
