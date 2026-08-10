// Anvil VS Code extension entry point.
//
// Slice 4 (blueprint §2.1, §2.2). Activation now wires the full thin client:
// the typed runtime client, the chat participant, the status bar, the secret
// store, and a redacting logger. All long-lived resources are registered on
// `context.subscriptions` so VS Code disposes them on deactivation.

import * as vscode from "vscode";

import { AnvilChatParticipant } from "./chat/participant";
import { API_BASE_URL } from "./config/modeSelector";
import { redactSecrets } from "./secrets/redactionClient";
import { SecretStore } from "./secrets/secretStore";
import { ExtensionLogger } from "./telemetry/extensionLogger";
import { StatusBar } from "./ui/statusBar";
import { RuntimeClient } from "./runtime/runtimeClient";

const CHAT_PARTICIPANT_ID = "anvil.chat";

/** Called by VS Code when the extension activates (onStartupFinished). */
export function activate(context: vscode.ExtensionContext): void {
  const channel = vscode.window.createOutputChannel("Anvil");
  const logger = new ExtensionLogger(channel);
  const secretStore = new SecretStore(context.secrets);
  const statusBar = new StatusBar();
  const client = new RuntimeClient(API_BASE_URL);
  const participant = new AnvilChatParticipant(client);

  const handler: vscode.ChatRequestHandler = async (request, _ctx, stream) => {
    // Build into the folder the user has open in VS Code, when there is one.
    const workspace = vscode.workspace.workspaceFolders?.[0]?.uri.fsPath;
    // Everything rendered in chat passes the redaction rules first — runtime
    // error bodies can quote request payloads that carry secret-shaped text.
    const response = await participant.handleRequest(
      request.prompt,
      { requesterId: "vscode-user", workspace },
      (message) => stream.progress(redactSecrets(message)),
    );
    stream.markdown(redactSecrets(response.markdown));
    if (participant.currentRunId) {
      try {
        statusBar.update(await client.getRun(participant.currentRunId));
      } catch {
        // Status-bar refresh is best-effort; never fail the chat turn on it.
      }
    }
    return {};
  };

  const chatParticipant = vscode.chat.createChatParticipant(
    CHAT_PARTICIPANT_ID,
    handler
  );

  logger.info(`Anvil activated; runtime endpoint ${API_BASE_URL}`);
  void secretStore; // consumed by the LLM-routing path wired in Slice 5

  context.subscriptions.push(channel, statusBar, chatParticipant);
}

/** Called by VS Code when the extension deactivates. */
export function deactivate(): void {
  // All resources are owned by context.subscriptions and disposed by VS Code.
}
