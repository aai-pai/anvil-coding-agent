// Unit tests for the live-progress renderer (Level 2).
//
// Runner: vitest. `renderProgress` is pure, so no VS Code API / runtime needed.

import { describe, expect, it } from "vitest";

import { renderProgress } from "../../../extension/src/chat/responseRenderer";
import type { RunStateResponse } from "../../../extension/src/runtime/runtimeClient";

function state(overrides: Partial<RunStateResponse>): RunStateResponse {
  return {
    run_id: "r1",
    status: "running",
    current_phase: null,
    completed_phases: [],
    pending_approval_gate: null,
    ...overrides,
  };
}

describe("renderProgress", () => {
  it("shows phase count and current phase while running", () => {
    const msg = renderProgress(
      state({ completed_phases: ["proposal", "factory-init"], current_phase: "specification" })
    );
    expect(msg).toContain("2/13");
    expect(msg).toContain("specification");
  });

  it("reports completion", () => {
    expect(renderProgress(state({ status: "completed" }))).toContain("complete");
  });

  it("reports a pending approval gate", () => {
    const msg = renderProgress(
      state({ status: "awaiting_approval", pending_approval_gate: "post-proposal" })
    );
    expect(msg).toContain("approval");
    expect(msg).toContain("post-proposal");
  });

  it("reports escalation", () => {
    expect(
      renderProgress(state({ status: "escalated", current_phase: "implementation" }))
    ).toContain("escalated");
  });
});
