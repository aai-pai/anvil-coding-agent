// Typed client for the localhost Anvil runtime REST API.
//
// Slice 4 deliverable (blueprint §3.2, §5.1). A thin, dependency-injected HTTP
// client over the `/v1` surface. The transport (`fetch`) is injectable so the
// client is unit-testable without a live runtime or the VS Code API. Request and
// response interfaces mirror the runtime Pydantic models
// (`runtime/anvil_runtime/api/models.py`) field-for-field to keep the contract
// in sync across the language boundary.

import { API_BASE_URL } from "../config/modeSelector";

// -- request/response contracts (mirror api/models.py) ----------------------

export interface RunStartRequest {
  mode: string;
  security_profile: string;
  phase_gates?: string[];
  run_overrides?: Record<string, unknown>;
}

export interface RunStarted {
  run_id: string;
  started_at: string;
  mode: string;
}

export interface RunStateResponse {
  run_id: string;
  status: string;
  current_phase: string | null;
  completed_phases: string[];
  pending_approval_gate: string | null;
}

export interface ApprovalRequest {
  gateId: string;
  gateName: string;
  approved: boolean;
  comments?: string;
  requesterId: string;
}

export interface OverrideRequest {
  action: "force-advance" | "rollback" | "stop";
  targetPhase?: string;
  reason: string;
  comments?: string;
  requesterId: string;
}

export interface OverrideResult {
  status: string;
  action: string;
  targetPhase: string | null;
}

export interface HealthResponse {
  status: string;
  runtime: string;
  checks: Record<string, string>;
}

// -- minimal transport shape (subset of the DOM fetch API) ------------------

export interface RequestInitLike {
  method?: string;
  headers?: Record<string, string>;
  body?: string;
}

export interface ResponseLike {
  ok: boolean;
  status: number;
  json(): Promise<unknown>;
  text(): Promise<string>;
}

export type FetchLike = (
  input: string,
  init?: RequestInitLike
) => Promise<ResponseLike>;

/** Raised when the runtime returns a non-2xx response. */
export class RuntimeApiError extends Error {
  constructor(
    public readonly status: number,
    message: string
  ) {
    super(message);
    this.name = "RuntimeApiError";
  }
}

export class RuntimeClient {
  private readonly baseUrl: string;
  private readonly fetchImpl: FetchLike;

  constructor(
    baseUrl: string = API_BASE_URL,
    fetchImpl?: FetchLike
  ) {
    this.baseUrl = baseUrl.replace(/\/$/, "");
    // Default to the platform fetch (VS Code / Node 18+) when not injected.
    this.fetchImpl =
      fetchImpl ?? ((globalThis as { fetch?: FetchLike }).fetch as FetchLike);
  }

  /** POST /v1/runs — start a run; the runtime advances to the first pause. */
  async startRun(request: RunStartRequest): Promise<RunStarted> {
    return this.requestJson<RunStarted>("POST", "/v1/runs", request);
  }

  /** GET /v1/runs/{run_id} — current status, phase, and pending gate. */
  async getRun(runId: string): Promise<RunStateResponse> {
    return this.requestJson<RunStateResponse>(
      "GET",
      `/v1/runs/${encodeURIComponent(runId)}`
    );
  }

  /** POST /v1/runs/{run_id}/approve — record a gate decision (204, no body). */
  async approve(runId: string, req: ApprovalRequest): Promise<void> {
    await this.send(
      "POST",
      `/v1/runs/${encodeURIComponent(runId)}/approve`,
      req
    );
  }

  /** POST /v1/runs/{run_id}/override — force-advance, rollback, or stop. */
  async override(runId: string, req: OverrideRequest): Promise<OverrideResult> {
    return this.requestJson<OverrideResult>(
      "POST",
      `/v1/runs/${encodeURIComponent(runId)}/override`,
      req
    );
  }

  /** GET /v1/health — runtime liveness and subsystem checks. */
  async health(): Promise<HealthResponse> {
    return this.requestJson<HealthResponse>("GET", "/v1/health");
  }

  // -- internals ------------------------------------------------------------

  private async send(
    method: string,
    path: string,
    body?: unknown
  ): Promise<ResponseLike> {
    const init: RequestInitLike = { method };
    if (body !== undefined) {
      init.headers = { "Content-Type": "application/json" };
      init.body = JSON.stringify(body);
    }
    const res = await this.fetchImpl(`${this.baseUrl}${path}`, init);
    if (!res.ok) {
      let detail = `HTTP ${res.status}`;
      try {
        detail = (await res.text()) || detail;
      } catch {
        // Keep the status-only message if the body cannot be read.
      }
      throw new RuntimeApiError(res.status, detail);
    }
    return res;
  }

  private async requestJson<T>(
    method: string,
    path: string,
    body?: unknown
  ): Promise<T> {
    const res = await this.send(method, path, body);
    return (await res.json()) as T;
  }
}
