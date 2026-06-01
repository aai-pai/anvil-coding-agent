// Anvil VS Code extension entry point.
//
// Slice 1 deliverable (blueprint §2.1). This is the activation scaffold only:
// the chat participant, runtime client, status bar, and approval surfaces are
// implemented in Slice 4. Keeping activation minimal here avoids drift while
// establishing the entry contract VS Code calls.

import type * as vscode from "vscode";

import { API_BASE_URL, DEFAULT_MODE } from "./config/modeSelector";

/** Called by VS Code when the extension activates (onStartupFinished). */
export function activate(context: vscode.ExtensionContext): void {
  // Slice 1: record activation context only. Slice 4 registers the chat
  // participant (vscode.chat.createChatParticipant), wires the runtime client to
  // API_BASE_URL, and attaches status-bar / approval UI to `context.subscriptions`.
  void context;
  void API_BASE_URL;
  void DEFAULT_MODE;
}

/** Called by VS Code when the extension deactivates. */
export function deactivate(): void {
  // No long-lived resources are created in Slice 1.
}
