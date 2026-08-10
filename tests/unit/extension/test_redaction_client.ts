// Unit tests: client-side secret redaction (spec NFR-SC-003, §6.4).
//
// Mirrors the runtime-side redaction tests: assignment shapes, JSON-quoted
// keys (the shape that leaks inside error bodies), and well-known bare tokens.

import { describe, expect, it } from "vitest";

import {
  REDACTION_PLACEHOLDER,
  redactSecrets,
} from "../../../extension/src/secrets/redactionClient";

describe("redactSecrets", () => {
  it("redacts assignment patterns while keeping the label", () => {
    const out = redactSecrets("api_key=SECRET123 and password: hunter2");
    expect(out).not.toContain("SECRET123");
    expect(out).not.toContain("hunter2");
    expect(out).toContain("api_key=");
  });

  it("redacts JSON-quoted keys, preserving the document shape", () => {
    const out = redactSecrets('{"api_key": "AKIAIOSFODNN7EXAMPLE"}');
    expect(out).toBe(`{"api_key": "${REDACTION_PLACEHOLDER}"}`);
  });

  it("redacts quoted multi-word values whole", () => {
    const out = redactSecrets('password = "my secret phrase"');
    expect(out).not.toContain("secret phrase");
  });

  it("redacts bare token shapes", () => {
    expect(redactSecrets("sk-or-abcdef123456")).not.toContain("abcdef");
    expect(
      redactSecrets("pushed with ghp_abcdefghijklmnopqrstu012345"),
    ).not.toContain("ghp_");
    expect(redactSecrets("aws AKIAIOSFODNN7EXAMPLE")).not.toContain("AKIA");
    expect(redactSecrets("Authorization: Basic dXNlcjpwYXNz")).toContain(
      REDACTION_PLACEHOLDER,
    );
  });

  it("leaves ordinary text untouched", () => {
    const text = "Phase implementation completed; 1234 total tokens.";
    expect(redactSecrets(text)).toBe(text);
  });
});
