// Escalation prompt.
//
// Slice 4 deliverable (blueprint §3.2; spec FR-SV-019/020). When the runtime
// escalates after exhausting retries, this surface presents the escalation
// packet to the user and collects their chosen recovery action, which the chat
// participant translates into an override (`force-advance`, `rollback`, `stop`).

import * as vscode from "vscode";

export interface EscalationInfo {
  runId: string;
  phase: string;
  reason: string;
  attempts: number;
}

export type EscalationChoice = "force-advance" | "rollback" | "stop" | "dismiss";

/** Show the escalation and ask how to proceed. */
export async function promptEscalation(
  info: EscalationInfo
): Promise<EscalationChoice> {
  const choice = await vscode.window.showWarningMessage(
    `Anvil escalation in '${info.phase}' after ${info.attempts} attempts: ${info.reason}`,
    { modal: true },
    "Force advance",
    "Roll back",
    "Stop run"
  );
  switch (choice) {
    case "Force advance":
      return "force-advance";
    case "Roll back":
      return "rollback";
    case "Stop run":
      return "stop";
    default:
      return "dismiss";
  }
}
