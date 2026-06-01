// Runtime health probe.
//
// Slice 4 deliverable (blueprint §3.2, §5.1). A small wrapper over
// `RuntimeClient.health()` that reduces the check map to a single liveness
// verdict the status bar and chat participant can consume. Pure with respect to
// the VS Code API; depends only on the injected runtime client.

import type { HealthResponse, RuntimeClient } from "./runtimeClient";

export interface HealthVerdict {
  reachable: boolean;
  status: string;
  detail: HealthResponse | null;
}

export class HealthProbe {
  constructor(private readonly client: RuntimeClient) {}

  /** Probe the runtime; never throws — an unreachable runtime is a verdict. */
  async probe(): Promise<HealthVerdict> {
    try {
      const detail = await this.client.health();
      return { reachable: true, status: detail.status, detail };
    } catch {
      return { reachable: false, status: "unreachable", detail: null };
    }
  }
}
