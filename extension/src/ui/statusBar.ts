// Status-bar surface reflecting the active run.
//
// Slice 4 deliverable (blueprint §2.1, §3.2). Owns a single status-bar item and
// updates its text/tooltip from run state and streamed events. Presentation
// strings come from the pure `eventMapper` so the formatting stays testable.

import * as vscode from "vscode";

import { statusBarText } from "../telemetry/eventMapper";
import type { RunStateResponse } from "../runtime/runtimeClient";

export class StatusBar {
  private readonly item: vscode.StatusBarItem;

  constructor() {
    this.item = vscode.window.createStatusBarItem(
      vscode.StatusBarAlignment.Left,
      100
    );
    this.item.text = "$(rocket) Anvil";
    this.item.tooltip = "Anvil coding factory";
  }

  /** Reflect the latest run state in the status bar. */
  update(state: RunStateResponse): void {
    this.item.text = statusBarText(state.status, state.current_phase);
    this.item.tooltip = state.pending_approval_gate
      ? `Awaiting approval: ${state.pending_approval_gate}`
      : `Run ${state.run_id} — ${state.status}`;
    this.item.show();
  }

  /** Reset the status bar to its idle label. */
  reset(): void {
    this.item.text = "$(rocket) Anvil";
    this.item.tooltip = "Anvil coding factory";
  }

  dispose(): void {
    this.item.dispose();
  }
}
