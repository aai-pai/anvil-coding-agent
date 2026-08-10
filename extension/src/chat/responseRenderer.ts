// Renders runtime responses into Markdown for the chat transcript.
//
// Slice 4 deliverable (blueprint §3.2). Pure formatting helpers that turn the
// runtime's typed responses into the Markdown strings the chat participant
// streams back to the user. No VS Code API dependency, so each renderer is
// unit-testable in isolation.

import type {
  OverrideResult,
  RunStarted,
  RunStateResponse,
} from "../runtime/runtimeClient";
import { presentEvent } from "../telemetry/eventMapper";
import type { EventEnvelope } from "../runtime/eventStreamClient";

/** Confirmation line for a freshly started run. */
export function renderRunStarted(started: RunStarted): string {
  return `**Run started** \`${started.run_id}\` in **${started.mode}** mode.`;
}

/** A compact status card for `GET /v1/runs/{id}`. */
export function renderRunState(state: RunStateResponse): string {
  const lines = [
    `**Run** \`${state.run_id}\` — _${state.status}_`,
    `- Current phase: ${state.current_phase ?? "—"}`,
    `- Completed: ${
      state.completed_phases.length > 0
        ? state.completed_phases.join(", ")
        : "none"
    }`,
  ];
  if (state.pending_approval_gate) {
    lines.push(`- ⏸ Awaiting approval: **${state.pending_approval_gate}**`);
  }
  if (state.pending_questions && state.pending_questions.length > 0) {
    lines.push("- ❓ Anvil needs clarification — reply with `answer <a1>; <a2>; …`:");
    for (const question of state.pending_questions) {
      lines.push(`  1. ${question}`);
    }
  }
  return lines.join("\n");
}

const TOTAL_PHASES = 13;

/** A short, live one-line progress message for a run in flight (Level 2). */
export function renderProgress(state: RunStateResponse): string {
  const done = state.completed_phases.length;
  if (state.status === "completed") {
    return `Anvil: all ${TOTAL_PHASES} phases complete ✓`;
  }
  if (state.pending_approval_gate) {
    return `Anvil: paused for approval — ${state.pending_approval_gate}`;
  }
  if (state.status === "awaiting_clarification") {
    return "Anvil: paused — needs clarification (see questions below)";
  }
  if (state.status === "escalated") {
    return `Anvil: escalated at ${state.current_phase ?? "?"}`;
  }
  const current = state.current_phase ? ` — ${state.current_phase}` : "";
  return `Anvil: ${done}/${TOTAL_PHASES} phases${current}`;
}

/** Result line for an override action. */
export function renderOverrideResult(result: OverrideResult): string {
  const target = result.targetPhase ? ` → ${result.targetPhase}` : "";
  return `**Override ${result.action}** ${result.status}${target}.`;
}

/** A single transcript line for a streamed event. */
export function renderEvent(event: EventEnvelope): string {
  const { label } = presentEvent(event);
  return `- ${label}`;
}

/** The built-in help text listing supported chat commands. */
export function renderHelp(): string {
  return [
    "**Anvil commands**",
    "- `build <description>` — build something from a plain-English description (e.g. `build a CLI that converts Celsius to Fahrenheit`)",
    "- `build` — build from the open folder's `domain-knowledge/background-information.md`",
    "- `start [mode] [profile] [gates…]` — begin a run from the domain-knowledge file (e.g. `start secure restricted`)",
    "- `status` — show the current run state",
    "- `answer <a1>; <a2>; …` — answer Anvil's clarifying questions",
    "- `approve [comment]` / `deny [comment]` — resolve the pending gate",
    "- `rollback <phase> [reason]` — roll back to a phase",
    "- `force-advance [reason]` / `stop [reason]` — override the supervisor",
    "- `health` — check runtime liveness",
  ].join("\n");
}
