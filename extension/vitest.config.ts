import { defineConfig } from "vitest/config";

// Slice 1 chose vitest as the TypeScript test runner (lightest modern default;
// see logs/implementation.log). Pure modules under src/config/* are unit-tested
// without the VS Code API; modules that import `vscode` are covered later with
// the extension host harness in Slice 4.
export default defineConfig({
  test: {
    environment: "node",
    include: ["../tests/unit/extension/**/*.ts"],
    coverage: {
      provider: "v8",
      include: ["src/**/*.ts"],
    },
  },
});
