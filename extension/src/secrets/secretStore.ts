// OpenRouter API key storage via VS Code Secret Storage.
//
// Slice 4 deliverable (blueprint §3.2; spec NFR-SC-001). Persists/retrieves the
// OpenRouter API key using `vscode.SecretStorage` so it is never written to
// settings or disk in plaintext. When Secret Storage is unavailable (CI /
// headless), the runtime falls back to the `OPENROUTER_API_KEY` environment
// variable (NFR-SC-002, `runtime/anvil_runtime/security/secret_adapter.py`).

import type * as vscode from "vscode";

export const OPENROUTER_SECRET_KEY = "anvil.openRouterApiKey";

export class SecretStore {
  constructor(private readonly secrets: vscode.SecretStorage) {}

  /** Retrieve the stored OpenRouter key, or undefined if none is set. */
  async getOpenRouterKey(): Promise<string | undefined> {
    return this.secrets.get(OPENROUTER_SECRET_KEY);
  }

  /** Store the OpenRouter key in Secret Storage. */
  async setOpenRouterKey(value: string): Promise<void> {
    await this.secrets.store(OPENROUTER_SECRET_KEY, value);
  }

  /** Remove the stored OpenRouter key. */
  async clearOpenRouterKey(): Promise<void> {
    await this.secrets.delete(OPENROUTER_SECRET_KEY);
  }
}
