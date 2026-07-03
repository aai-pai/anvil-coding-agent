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
  renderProgress,
  renderRunStarted,
  renderRunState,
} from "./responseRenderer";
import type {
  RunStartRequest,
  RunStarted,
  RunStateResponse,
  RuntimeClient,
} from "../runtime/runtimeClient";

export interface ChatContext {
  /** The id recorded as the requester on approvals/overrides. */
  requesterId: string;
  /** The open VS Code folder; runs build into it when present. */
  workspace?: string;
}

export interface ChatResponse {
  markdown: string;
}

/** Optional live-progress sink (the chat stream); called between phases. */
export type ProgressSink = (message: string) => void;

const TERMINAL_STATUSES = new Set([
  "completed",
  "escalated",
  "stopped",
  "awaiting_approval",
  "awaiting_clarification",
]);

export class AnvilChatParticipant {
  private activeRunId: string | undefined;

  constructor(private readonly client: RuntimeClient) {}

  /** Most recently started/observed run id (used to target approvals). */
  get currentRunId(): string | undefined {
    return this.activeRunId;
  }

  async handleRequest(
    message: string,
    context: ChatContext,
    progress?: ProgressSink
  ): Promise<ChatResponse> {
    const command = parseCommand(message);
    try {
      return { markdown: await this.execute(command, context, progress) };
    } catch (error) {
      const detail = error instanceof Error ? error.message : String(error);
      return { markdown: `⚠️ Runtime error: ${detail}` };
    }
  }

  /** Start a run and, when a progress sink is present, drive it phase-by-phase. */
  private async runWithProgress(
    request: RunStartRequest,
    progress?: ProgressSink
  ): Promise<{ started: RunStarted; state: RunStateResponse }> {
    const started = await this.client.startRun(
      request,
      progress ? { defer: true } : undefined
    );
    this.activeRunId = started.run_id;
    let state = await this.client.getRun(started.run_id);
    if (!progress) {
      return { started, state };
    }
    // Deferred run: advance one phase at a time, reporting progress between each.
    let guard = 0;
    while (!TERMINAL_STATUSES.has(state.status) && guard < 60) {
      progress(renderProgress(state));
      state = await this.client.advance(started.run_id);
      guard += 1;
    }
    progress(renderProgress(state));
    return { started, state };
  }

  private async execute(
    command: ChatCommand,
    context: ChatContext,
    progress?: ProgressSink
  ): Promise<string> {
    switch (command.kind) {
      case "start": {
        const { started, state } = await this.runWithProgress(
          {
            mode: command.mode,
            security_profile: command.securityProfile,
            phase_gates: command.extraGates,
            workspace: context.workspace,
          },
          progress
        );
        return `${renderRunStarted(started)}\n\n${renderRunState(state)}`;
      }
      case "build": {
        // Conversational flow: the task comes straight from chat. The runtime
        // writes it to domain-knowledge, then runs autonomously (yolo/open),
        // building into the open VS Code folder when there is one. With no
        // description (#17, FR-SRC-005), the open folder's
        // domain-knowledge/background-information.md is the intent file.
        let intent: { task?: string; source_path?: string };
        let label: string;
        if (command.description) {
          intent = { task: command.description };
          label = `🛠️ Building: _${command.description}_`;
        } else {
          if (!context.workspace) {
            return (
              "⚠️ `build` without a description needs an open folder containing " +
              "`domain-knowledge/background-information.md`."
            );
          }
          const sourcePath = `${context.workspace}/domain-knowledge/background-information.md`;
          intent = { source_path: sourcePath };
          label = `🛠️ Building from \`${sourcePath}\``;
        }
        const { started, state } = await this.runWithProgress(
          {
            mode: "yolo",
            security_profile: "open",
            ...intent,
            workspace: context.workspace,
          },
          progress
        );
        const where = context.workspace
          ? `\n📁 into \`${context.workspace}\``
          : "";
        return (
          `${label}${where}\n\n` +
          `${renderRunStarted(started)}\n\n${renderRunState(state)}`
        );
      }
      case "status": {
        const runId = this.requireRun();
        return renderRunState(await this.client.getRun(runId));
      }
      case "answer": {
        // #15 (FR-INT-012): forward answers to /clarify; `;` separates answers.
        const runId = this.requireRun();
        const answers = command.text
          .split(";")
          .map((part) => part.trim())
          .filter((part) => part.length > 0);
        const state = await this.client.clarify(runId, { answers });
        return renderRunState(state);
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
