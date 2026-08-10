# Background Information — Anvil v0.1.2

Source material for the v0.1.2 release: four issues filed from team usage of
v0.1.1, plus the design decisions made in review discussion. The v0.1.1 release
(per-run isolation, complexity gating, phase-aware routing, failure records) is
the baseline.

## Filed issues

### Issue 1 — Anvil equivalent of `copilot-instructions.md`

Copilot instructions capture the default actions when inputs are underspecified
and fallbacks for various actions. Anvil needs an equivalent standing-instructions
document that it has access to on every run.

### Issue 2 — Domain-knowledge extraction must question the user on missing information

Anvil's domain-knowledge extraction does not check the completeness of the
information before proceeding. It needs to do that so it never builds from
incomplete information without either asking or explicitly assuming.

### Issue 3 — Markdown artifacts should support Google's Open Knowledge Format (OKF)

OKF (Google Cloud, released 2026-06-13, spec v0.1) is an emerging vendor-neutral
format for structuring markdown so coding agents can use it efficiently:
markdown files with YAML frontmatter; the only required field is `type`;
standard optional fields `title`, `description`, `resource`, `tags`,
`timestamp`; cross-links are ordinary markdown links; optional per-directory
`index.md` for progressive disclosure. Producers may add custom fields.
Spec: <https://github.com/GoogleCloudPlatform/knowledge-catalog/tree/main/okf>.
Anvil's markdown artifacts should match/resemble this standard.

### Issue 4 — Read markdown inputs from `domain-knowledge/background-information.md`

Right now `@anvil build` only runs from a chat input. Users need to put their
intent into a background-information markdown file and have a build run consume
it — without losing the v0.1.1 per-run workspace isolation.

## Decisions from review discussion (2026-07-03)

1. **Two documents, two altitudes.** `anvil-instructions.md` is workspace-level
   and governs *how* Anvil behaves on **all** runs (defaults, fallbacks,
   conventions). `background-information.md` is per-run and states *what* to
   build. Every phase reads both.
2. **Gap-filling is a dedicated process**, not piggybacked on the proposal call:
   a small intake step runs before proposal, assesses completeness, and emits
   questions. Chosen over piggybacking (despite the extra small LLM call) because
   the team considers gap-filling important enough to own its own phase.
3. **Keep it easy for v0.1.2**: a single bounded clarification round, a capped
   question list, answers appended to `background-information.md` (the file is
   the single source of truth — the conversation materializes into it; chat
   history is never load-bearing).
4. **Autonomous runs must not block**: in yolo mode the intake step fills gaps
   from `anvil-instructions.md` defaults and records the assumptions instead of
   pausing. The instructions file is the answer sheet when no human is present.
5. **Known enabler bug**: `LLMBackend._read_inputs` truncates every input file to
   2,500 characters — silently cutting off rich background information,
   instructions, and appended answers. Must be fixed in this release or the
   features above underdeliver invisibly.
6. OKF conformance is cheap: Anvil artifacts already carry YAML frontmatter
   (artifactId, phase, generatedAt, lineage), and OKF permits custom fields, so
   Anvil can conform fully while keeping its lineage fields.
