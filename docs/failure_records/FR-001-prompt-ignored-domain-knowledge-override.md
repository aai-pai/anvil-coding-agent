# FR-001: User Prompt Ignored — Domain Knowledge Overrides Build Target

**Date:** 2026-06-15  
**Run ID:** `7afb7eade1054914bb16d2c46c0da2b0`  
**Execution Mode:** `real` (OpenRouter)  
**Status:** Closed

---

## Summary

A run was submitted with the user prompt `"build a cli tool that converts dollars to cents"`. The runtime completed all 12 phases successfully (no errors, no retries), but produced artifacts describing and implementing a **software development factory / phase automation system** — not a dollars-to-cents CLI tool. The user's prompt was effectively ignored.

---

## Updated Assessment

Current working theory: the run was executed inside the existing Anvil repository, which already contained canonical artifacts from the earlier GHCP-driven build of Anvil itself. Because Anvil is designed to derive later phases from those same documents, the runtime likely treated the pre-existing project artifacts as the authoritative project definition.

Under that interpretation, the failure is more precise than "the prompt was ignored." The prompt was likely present, but it lost against a much stronger and already-consistent set of workspace inputs: existing `docs/` artifacts, `domain-knowledge/` content, and the surrounding Anvil repository structure.

This means the run may have behaved as designed for a continuation workflow, but produced the wrong outcome for a fresh-project workflow because it was pointed at a workspace that already described a different project.

---

## Observed Behaviour

- **Run completed:** All 12 phases finished (`proposal` → `cleanup`).
- **Generated proposal (`docs/proposal.md`):** Describes "Traditional software development processes" and a "Software Development Factory" — clearly derived from `domain-knowledge/background-information.md`, not the user prompt.
- **Generated spec (`docs/spec.md`):** Specifies a Development Manager, Phase Specialist Agents, and Model Integration — again Anvil-internal concepts.
- **Generated code (`src/main.py`, `src/core/`):** Implements a `DevelopmentManager`, `PhaseAgent`, and `ArtifactGenerator` — all Anvil-codebase constructs.
- **No dollars-to-cents logic anywhere** in any generated artifact.

---

## Artifacts Generated

| File | Expected | Actual |
|---|---|---|
| `docs/proposal.md` | Proposal for a currency CLI | Proposal for a software dev factory |
| `docs/spec.md` | Spec for dollar→cent conversion | Spec for phase agents & dev manager |
| `src/main.py` | `dollars_to_cents()` CLI entrypoint | `DevelopmentManager` workflow scaffold |
| `src/core/artifact_generator.py` | (should not exist) | Anvil-style artifact template engine |
| `src/core/development_manager.py` | (should not exist) | Phase state machine |
| `src/core/phase_agent.py` | (should not exist) | Phase agent base class |

---

## Hypotheses

1. **Pre-existing GHCP-generated Anvil artifacts were treated as the authoritative project definition.** The runtime likely consumed the existing `docs/` and `domain-knowledge/` inputs as source-of-truth and continued the Anvil project rather than starting a new one from the prompt.
2. **Domain knowledge injected as system context outweighs the user prompt.** The proposal phase reads `domain-knowledge/background-information.md` (which describes Anvil) and may treat it as the primary project to build.
3. **The `prompt` field is passed through, but with lower priority than workspace artifacts.** The POST body prompt may reach the LLM but be underweighted relative to existing phase documents and repository structure.
4. **The workspace working directory context bleeds in.** Since the runtime runs inside the Anvil repo itself, the LLM may be seeing the repo structure and treating it as the build target.

---

## Investigation Checklist

- [ ] Trace how the `prompt` field flows from `POST /v1/runs` → `DevelopmentManager` → phase agent → LLM call
- [ ] Check whether `prompt` is included in the LLM message sent for the `proposal` phase
- [ ] Check what context (`domain-knowledge/`, workspace files) is injected at the proposal phase
- [ ] Verify whether existing `docs/proposal.md`, `docs/spec.md`, `docs/architecture.md`, and `docs/blueprint.md` are treated as canonical inputs when present
- [ ] Re-run the same prompt in a clean workspace with no prior artifacts to compare behavior
- [ ] Determine if `derivedFrom: domain-knowledge/background-information.md` in `proposal.md` frontmatter means the domain knowledge is read and used as the build spec
- [ ] Check `routes_runs.py` and `development_manager.py` for how `prompt` is stored and forwarded

---

## Notes

- The `docs/proposal.md` frontmatter shows `derivedFrom: domain-knowledge/background-information.md` — strong signal that the proposal agent is hardcoded to derive from domain knowledge files rather than the user prompt.
- The existing `docs/` files in the workspace (spec, architecture, blueprint, plan from the Anvil project itself) may have been overwritten by the run, or the generated files may conflict with pre-existing ones. This should be verified.
- Revised interpretation: the strongest confounder may not be domain knowledge alone, but the combination of existing GHCP-generated Anvil artifacts plus a workflow that intentionally uses those artifacts as inputs for subsequent phases.
