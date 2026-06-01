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
  return lines.join("\n");
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
    "- `start [mode] [profile] [gates…]` — begin a run (e.g. `start secure restricted`)",
    "- `status` — show the current run state",
    "- `approve [comment]` / `deny [comment]` — resolve the pending gate",
    "- `rollback <phase> [reason]` — roll back to a phase",
    "- `force-advance [reason]` / `stop [reason]` — override the supervisor",
    "- `health` — check runtime liveness",
  ].join("\n");
}
