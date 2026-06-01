// Secure-mode approval prompt.
//
// Slice 4 deliverable (blueprint §3.2 `promptApproval`). Collects an explicit
// approve/deny decision (with an optional comment) for a pending gate and builds
// the `ApprovalRequest` the runtime expects. Uses VS Code modal dialogs so a
// secure-mode gate cannot be dismissed implicitly (spec: explicit approvals).

import * as vscode from "vscode";

import type { ApprovalRequest } from "../runtime/runtimeClient";

export interface ApprovalGate {
  gateId: string;
  gateName: string;
  requesterId: string;
}

/** Prompt the user to approve or deny a gate; returns the decision payload. */
export async function promptApproval(
  gate: ApprovalGate
): Promise<ApprovalRequest> {
  const choice = await vscode.window.showInformationMessage(
    `Anvil approval required: ${gate.gateName}`,
    { modal: true },
    "Approve",
    "Deny"
  );
  const approved = choice === "Approve";
  const comments = await vscode.window.showInputBox({
    prompt: approved
      ? "Optional approval comment"
      : "Reason for denial (optional)",
    placeHolder: approved ? "Looks good" : "Needs changes",
  });
  return {
    gateId: gate.gateId,
    gateName: gate.gateName,
    approved,
    comments: comments && comments.length > 0 ? comments : undefined,
    requesterId: gate.requesterId,
  };
}
