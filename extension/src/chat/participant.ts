// Anvil chat participant: turns chat messages into runtime actions.
//
// Slice 4 deliverable (blueprint §2.2, §3.2). Parses the user's message with the
// pure `commandRouter`, executes it against the typed `RuntimeClient`, and
// renders a Markdown reply via `responseRenderer`. The class is constructed with
// an injected `RuntimeClient`, keeping the request-handling logic decoupled from
// the VS Code chat API; `registerAnvilParticipant` performs the host wiring.

import { parseCommand, type ChatCommand } from "./commandRouter";
import {
  renderHelp,
  renderOverrideResult,
  renderRunStarted,
  renderRunState,
} from "./responseRenderer";
import type { RuntimeClient } from "../runtime/runtimeClient";

export interface ChatContext {
  /** The id recorded as the requester on approvals/overrides. */
  requesterId: string;
}

export interface ChatResponse {
  markdown: string;
}

export class AnvilChatParticipant {
  private activeRunId: string | undefined;

  constructor(private readonly client: RuntimeClient) {}

  /** Most recently started/observed run id (used to target approvals). */
  get currentRunId(): string | undefined {
    return this.activeRunId;
  }

  async handleRequest(
    message: string,
    context: ChatContext
  ): Promise<ChatResponse> {
    const command = parseCommand(message);
    try {
      return { markdown: await this.execute(command, context) };
    } catch (error) {
      const detail = error instanceof Error ? error.message : String(error);
      return { markdown: `⚠️ Runtime error: ${detail}` };
    }
  }

  private async execute(
    command: ChatCommand,
    context: ChatContext
  ): Promise<string> {
    switch (command.kind) {
      case "start": {
        const started = await this.client.startRun({
          mode: command.mode,
          security_profile: command.securityProfile,
          phase_gates: command.extraGates,
        });
        this.activeRunId = started.run_id;
        const state = await this.client.getRun(started.run_id);
        return `${renderRunStarted(started)}\n\n${renderRunState(state)}`;
      }
      case "build": {
        // Conversational flow: the task comes straight from chat. The runtime
        // writes it to domain-knowledge, then runs autonomously (yolo/open).
        const started = await this.client.startRun({
          mode: "yolo",
          security_profile: "open",
          task: command.description,
        });
        this.activeRunId = started.run_id;
        const state = await this.client.getRun(started.run_id);
        return (
          `🛠️ Building: _${command.description}_\n\n` +
          `${renderRunStarted(started)}\n\n${renderRunState(state)}`
        );
      }
      case "status": {
        const runId = this.requireRun();
        return renderRunState(await this.client.getRun(runId));
      }
      case "approve":
      case "deny": {
        const runId = this.requireRun();
        const state = await this.client.getRun(runId);
        const gate = state.pending_approval_gate ?? "";
        await this.client.approve(runId, {
          gateId: gate,
          gateName: gate,
          approved: command.kind === "approve",
          comments: command.comments,
          requesterId: context.requesterId,
        });
        return renderRunState(await this.client.getRun(runId));
      }
      case "override": {
        const runId = this.requireRun();
        const result = await this.client.override(runId, {
          action: command.action,
          targetPhase: command.targetPhase,
          reason: command.reason,
          requesterId: context.requesterId,
        });
        return renderOverrideResult(result);
      }
      case "health": {
        const health = await this.client.health();
        return `**Runtime ${health.runtime}** — ${health.status}`;
      }
      case "unknown":
        return `Unrecognized command: \`${command.input}\`\n\n${renderHelp()}`;
      case "help":
      default:
        return renderHelp();
    }
  }

  private requireRun(): string {
    if (!this.activeRunId) {
      throw new Error("No active run. Start one with `start [mode] [profile]`.");
    }
    return this.activeRunId;
  }
}
