// Extension-side logger writing to a VS Code output channel.
//
// Slice 4 deliverable (blueprint §3.2; spec NFR-SC-003). Every line is passed
// through `redactSecrets` before it reaches the output channel so an API key or
// token can never surface in the extension log. The runtime keeps the
// authoritative audit trail; this is the client's local diagnostic log.

import * as vscode from "vscode";

import { redactSecrets } from "../secrets/redactionClient";

export type LogLevel = "info" | "warning" | "error";

export class ExtensionLogger {
  constructor(private readonly channel: vscode.OutputChannel) {}

  info(message: string): void {
    this.write("info", message);
  }

  warning(message: string): void {
    this.write("warning", message);
  }

  error(message: string): void {
    this.write("error", message);
  }

  private write(level: LogLevel, message: string): void {
    // Redaction is applied to the full line, defending against secrets embedded
    // anywhere in the message (NFR-SC-003).
    this.channel.appendLine(`[${level}] ${redactSecrets(message)}`);
  }
}
