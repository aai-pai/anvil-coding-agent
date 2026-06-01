// Unit tests for the typed runtime client.
//
// Slice 4 (blueprint §3.2, §5.1; plan §2.4). Runner: vitest. The client is
// exercised against an injected fake `fetch`, so no live runtime is needed.
// NOTE: requires Node.js/npm; written to spec and runs wherever Node is present.

import { describe, expect, it, vi } from "vitest";

import {
  RuntimeApiError,
  RuntimeClient,
  type FetchLike,
  type RequestInitLike,
  type ResponseLike,
} from "../../../extension/src/runtime/runtimeClient";

function jsonResponse(status: number, body: unknown): ResponseLike {
  return {
    ok: status >= 200 && status < 300,
    status,
    json: async () => body,
    text: async () => JSON.stringify(body),
  };
}

function noContentResponse(): ResponseLike {
  return {
    ok: true,
    status: 204,
    json: async () => ({}),
    text: async () => "",
  };
}

const BASE = "http://127.0.0.1:8765";

describe("RuntimeClient.startRun", () => {
  it("POSTs JSON to /v1/runs and parses the response", async () => {
    const calls: Array<{ url: string; init?: RequestInitLike }> = [];
    const fetchImpl: FetchLike = async (url, init) => {
      calls.push({ url, init });
      return jsonResponse(201, {
        run_id: "run-1",
        started_at: "2026-05-31T00:00:00Z",
        mode: "secure",
      });
    };
    const client = new RuntimeClient(BASE, fetchImpl);

    const started = await client.startRun({
      mode: "secure",
      security_profile: "restricted",
    });

    expect(started.run_id).toBe("run-1");
    expect(calls).toHaveLength(1);
    expect(calls[0].url).toBe(`${BASE}/v1/runs`);
    expect(calls[0].init?.method).toBe("POST");
    expect(calls[0].init?.headers?.["Content-Type"]).toBe("application/json");
    expect(JSON.parse(calls[0].init?.body ?? "{}")).toEqual({
      mode: "secure",
      security_profile: "restricted",
    });
  });
});

describe("RuntimeClient.getRun", () => {
  it("GETs the run and encodes the id", async () => {
    const fetchImpl = vi.fn<Parameters<FetchLike>, ReturnType<FetchLike>>(
      async () =>
        jsonResponse(200, {
          run_id: "a b",
          status: "running",
          current_phase: "architecture",
          completed_phases: ["proposal"],
          pending_approval_gate: null,
        })
    );
    const client = new RuntimeClient(BASE, fetchImpl);

    const state = await client.getRun("a b");

    expect(state.status).toBe("running");
    expect(fetchImpl).toHaveBeenCalledWith(`${BASE}/v1/runs/a%20b`, {
      method: "GET",
    });
  });
});

describe("RuntimeClient.approve", () => {
  it("POSTs the approval and tolerates a 204 with no body", async () => {
    const fetchImpl: FetchLike = async () => noContentResponse();
    const client = new RuntimeClient(BASE, fetchImpl);
    await expect(
      client.approve("run-1", {
        gateId: "post-proposal",
        gateName: "Post-Proposal",
        approved: true,
        requesterId: "user-1",
      })
    ).resolves.toBeUndefined();
  });
});

describe("RuntimeClient error handling", () => {
  it("throws RuntimeApiError on a non-2xx response", async () => {
    const fetchImpl: FetchLike = async () =>
      jsonResponse(404, { detail: "Unknown run 'ghost'" });
    const client = new RuntimeClient(BASE, fetchImpl);

    await expect(client.getRun("ghost")).rejects.toBeInstanceOf(RuntimeApiError);
    await expect(client.getRun("ghost")).rejects.toMatchObject({ status: 404 });
  });

  it("normalizes a trailing slash in the base URL", async () => {
    const calls: string[] = [];
    const fetchImpl: FetchLike = async (url) => {
      calls.push(url);
      return jsonResponse(200, { status: "ok", runtime: "anvil-runtime", checks: {} });
    };
    const client = new RuntimeClient(`${BASE}/`, fetchImpl);
    await client.health();
    expect(calls[0]).toBe(`${BASE}/v1/health`);
  });
});
