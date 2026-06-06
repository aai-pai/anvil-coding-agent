// SSE subscription client for the runtime event stream.
//
// Slice 4 deliverable (blueprint §3.2, §5.1). Subscribes to
// `GET /v1/runs/{runId}/events` (`text/event-stream`) and forwards each decoded
// `EventEnvelope` to a callback. The SSE wire-format decoding (`SseDecoder`) is a
// pure, transport-agnostic state machine so it can be unit-tested without a live
// stream; `subscribe` drives it from a `fetch` byte stream and returns a
// `Disposable` that aborts the request.

import { API_BASE_URL } from "../config/modeSelector";

/** Mirror of `anvil_runtime.core.phase_contracts.EventEnvelope`. */
export interface EventEnvelope {
  timestamp: string;
  eventType: string;
  runId: string;
  phase: string;
  severity: "info" | "warning" | "error" | "critical";
  userId?: string | null;
  data: Record<string, unknown>;
}

/** Minimal disposable handle (matches the `vscode.Disposable` shape). */
export interface Disposable {
  dispose(): void;
}

/**
 * Incremental decoder for the SSE `data:` frames the runtime emits. Feed it raw
 * text chunks; it yields one parsed `EventEnvelope` per completed `data:` line.
 */
export class SseDecoder {
  private buffer = "";

  /** Append a chunk and return any envelopes whose frames are now complete. */
  push(chunk: string): EventEnvelope[] {
    this.buffer += chunk;
    const out: EventEnvelope[] = [];
    let newlineIndex = this.buffer.indexOf("\n");
    while (newlineIndex !== -1) {
      const line = this.buffer.slice(0, newlineIndex).replace(/\r$/, "");
      this.buffer = this.buffer.slice(newlineIndex + 1);
      const envelope = this.decodeLine(line);
      if (envelope) {
        out.push(envelope);
      }
      newlineIndex = this.buffer.indexOf("\n");
    }
    return out;
  }

  private decodeLine(line: string): EventEnvelope | undefined {
    if (!line.startsWith("data:")) {
      return undefined; // ignore `event:` / comment / blank separator lines
    }
    const payload = line.slice("data:".length).trim();
    if (payload === "") {
      return undefined;
    }
    try {
      return JSON.parse(payload) as EventEnvelope;
    } catch {
      return undefined; // skip malformed frames rather than throwing mid-stream
    }
  }
}

/** Subset of the fetch streaming API used to read the SSE body. */
export interface StreamFetchLike {
  (
    input: string,
    init?: { method?: string; headers?: Record<string, string>; signal?: unknown }
  ): Promise<{
    ok: boolean;
    status: number;
    body: AsyncIterable<Uint8Array> | null;
  }>;
}

export class EventStreamClient {
  private readonly baseUrl: string;
  private readonly fetchImpl: StreamFetchLike;

  constructor(baseUrl: string = API_BASE_URL, fetchImpl?: StreamFetchLike) {
    this.baseUrl = baseUrl.replace(/\/$/, "");
    this.fetchImpl =
      fetchImpl ??
      ((globalThis as { fetch?: StreamFetchLike }).fetch as StreamFetchLike);
  }

  /** Subscribe to a run's event stream; dispose() aborts and stops delivery. */
  subscribe(runId: string, onEvent: (e: EventEnvelope) => void): Disposable {
    const controller = new AbortController();
    const decoder = new SseDecoder();
    const url = `${this.baseUrl}/v1/runs/${encodeURIComponent(runId)}/events`;
    let active = true;

    void (async () => {
      const res = await this.fetchImpl(url, {
        method: "GET",
        headers: { Accept: "text/event-stream" },
        signal: controller.signal,
      });
      if (!res.ok || res.body === null) {
        return;
      }
      const textDecoder = new TextDecoder();
      for await (const bytes of res.body) {
        if (!active) {
          break;
        }
        for (const envelope of decoder.push(textDecoder.decode(bytes))) {
          onEvent(envelope);
        }
      }
    })().catch(() => {
      // Stream errors (including abort) end the subscription quietly; the UI
      // re-subscribes on the next run if needed.
    });

    return {
      dispose: () => {
        active = false;
        controller.abort();
      },
    };
  }
}
