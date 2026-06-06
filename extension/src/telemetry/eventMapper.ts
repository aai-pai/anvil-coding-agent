// Maps runtime events and run state to user-facing presentation.
//
// Slice 4 deliverable (blueprint §3.2, §6.3). Pure translation of an
// `EventEnvelope` (and a run status string) into a concise label/icon for the
// status bar, chat transcript, and logs. Kept free of the VS Code API so it is
// unit-testable; the icon names use VS Code ThemeIcon ids but are plain strings
// here.

import type { EventEnvelope } from "../runtime/eventStreamClient";

export interface EventPresentation {
  label: string;
  icon: string;
  severity: EventEnvelope["severity"];
}

const EVENT_LABELS: Record<string, string> = {
  SupervisorStarted: "Run started",
  PhaseStarted: "Phase started",
  PhaseCompleted: "Phase completed",
  PhaseFailed: "Phase failed",
  ApprovalRequired: "Approval required",
  ApprovalGranted: "Approval granted",
  ApprovalDenied: "Approval denied",
  OverrideForceAdvance: "Force-advanced",
  Rollback: "Rolled back",
  RunStopped: "Run stopped",
  RunCompleted: "Run completed",
  Escalation: "Escalation",
  ResumeFromCheckpoint: "Resumed",
};

const SEVERITY_ICONS: Record<EventEnvelope["severity"], string> = {
  info: "info",
  warning: "warning",
  error: "error",
  critical: "flame",
};

/** Human-friendly label, icon, and severity for an event envelope. */
export function presentEvent(event: EventEnvelope): EventPresentation {
  const label = EVENT_LABELS[event.eventType] ?? event.eventType;
  return {
    label: event.phase ? `${label} — ${event.phase}` : label,
    icon: SEVERITY_ICONS[event.severity] ?? "info",
    severity: event.severity,
  };
}

/** Short status-bar text for a run status string from `RunStateResponse`. */
export function statusBarText(status: string, currentPhase?: string | null): string {
  const phaseSuffix = currentPhase ? `: ${currentPhase}` : "";
  switch (status) {
    case "running":
      return `$(sync~spin) Anvil${phaseSuffix}`;
    case "awaiting_approval":
      return `$(question) Anvil: approval needed`;
    case "completed":
      return `$(check) Anvil: done`;
    case "escalated":
      return `$(warning) Anvil: escalated`;
    case "stopped":
      return `$(circle-slash) Anvil: stopped`;
    default:
      return `$(rocket) Anvil`;
  }
}
