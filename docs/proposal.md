# Anvil Proposal (Draft v0.1)

## 1. Executive Summary

Anvil is a local-first, supervisor-orchestrated coding factory built on OpenHands and OpenRouter. It is designed to convert user intent in `domain-knowledge/background-information.md` into progressively refined software artifacts and production-ready code through a governed, phase-based workflow.

The core objective for v0.1.0 is to deliver a reliable autonomous coding system with strong instruction fidelity, token efficiency, policy enforcement, and bounded self-healing. Anvil should operate end-to-end with minimal human intervention, while still supporting approval checkpoints when required.

## 2. Problem Statement

Current AI coding workflows often fail in one or more of these areas:

- Weak control over agent behavior and tool usage.
- Poor traceability from high-level intent to generated code.
- Inconsistent model routing and high token waste.
- Limited recovery from runtime and orchestration failures.
- Inadequate policy governance for safety, security, and compliance.

Anvil addresses these gaps by combining a supervisor pattern, explicit artifact contracts, policy gates, and phased execution with auditable outputs.

## 3. Vision and Product Intent

Anvil should be a dependable coding agent platform that:

- Runs locally as a VS Code extension whose primary user-facing surface is a chat participant (via `vscode.chat.createChatParticipant`). Run state, phase progress, and approval prompts are surfaced through native VS Code affordances (status bar, notifications) rather than command palette entries, reflecting the long-running autonomous nature of coding-agent workflows.
- Runs a localhost REST API service (Anvil runtime) with versioned endpoints for run control, phase state, artifacts, events, and health.
- Uses the VS Code extension as a thin client that calls those localhost endpoints.
- Uses OpenHands as the orchestration engine.
- Uses OpenRouter for configurable multi-model routing.
- Produces high-quality artifacts in `docs/` before and during implementation.
- Maintains strict alignment between proposal, spec, architecture, blueprint, plan, and code.

Strategic direction after v0.1.0: use Anvil to build additional Anvil capabilities (bootstrapping).

## 4. Goals and Success Criteria

### 4.1 Primary Goals

- High instruction precision with low drift.
- High token efficiency via scoped context and progressive disclosure.
- Reliable autonomous execution with bounded self-healing.
- Deterministic runtime control and observability through explicit OpenHands hook enforcement and event lifecycle handling.
- Clear, actionable escalations only when automation cannot converge.
- Strong governance through policy files and validation gates.

### 4.2 v0.1.0 Success Criteria

- End-to-end run from background input to implementation and quality checks.
- Resume-from-checkpoint behavior after interruption.
- Manual phase override to restart from user-selected phase.
- Policy enforcement with remediation before escalation.
- Ability to support large project generation workflows with low intervention frequency.

## 5. Target Users

- Primary: repository owner operating the factory.
- Secondary: team developers collaborating in the same workspace.
- Programmatic: higher-level orchestration/swarm systems that need a predictable coding sub-agent.

## 6. Scope and Non-Goals (v0.1.0)

### In Scope

- Local execution in VS Code.
- Linux/WSL-first runtime.
- Python 3.12 baseline for orchestration.
- Docker-required-by-default execution isolation.
- Model routing defaults plus user overrides.
- Generated-code target languages: Python, Rust, C.

### Out of Scope

- Model fine-tuning or model training.
- Mandatory dependency on GHCP runtime.
- Distributed message-bus architecture (planned future evolution).
- Agent-to-Agent (A2A) peer transport protocol — v0.1.0 uses in-process agent invocation and the localhost REST API for all coordination; A2A is explicitly deferred to a future release once agent contracts are proven stable.
- Build and deployment execution — v0.1.0 packaging and deployment phases are documentation-first. Agents emit plans, scripts, and templates under `docs/packaging/` and `docs/deployment/`, but do not execute builds or deployments.

## 7. Operating Modes

- YOLO: full autonomous progression with no user stops.
- Gated: user selects phases requiring approval.
- Secure: four mandatory approval checkpoints — Post-Proposal, Post-Architecture, Post-Blueprint, and Pre-Deployment. Users may add further checkpoints but cannot remove these four.

Mode behavior is enforced by the development-manager phase controller.

## 8. Proposed System Approach

### 8.1 Supervisor-Centric Architecture

The development-manager orchestrates phase progression, delegates tasks to specialized phase agents, enforces operational mode constraints, and verifies expected artifacts.

### 8.2 Phase Agents with Contracts

Each phase agent has:

- Defined input files.
- Defined output files/artifacts.
- Allowed tools and behaviors.
- Clear completion criteria reported to supervisor.

### 8.3 Artifact-First Workflow

Long-form artifacts are produced in `docs/` and serve as control points:

1. Proposal
2. Specification
3. Architecture
4. Blueprint
5. Implementation Plan
6. Implementation and QA outputs

This sequencing reduces drift by requiring explicit design intent before code generation.

### 8.4 Policy and Governance Layer

Anvil enforces behavior through:

- Central policy files.
- Validation gates that fail non-compliant outputs.
- Auto-rewrite/remediation attempts before escalation.

Policies declare intent; their runtime enforcement and audit trail are provided by the hooks and events layer (see §8.8).

### 8.5 Runtime Projection Model

User-level intent and policy live in `~/.anvil/`. At run start, effective runtime files are materialized into workspace-local runtime folders (for hooks, MCP resolution, and policy snapshot) to ensure reproducible, auditable execution.

### 8.6 Phase Execution Model

Phases form a dependency-aware DAG: each declares its prerequisites and the supervisor executes them in topological order. v0.1.0 runs serially to keep resume and self-heal semantics simple; parallel execution is a deferred non-goal. The DAG declaration is forward-compatible, so a future scheduler can parallelize without changing phase contracts.

### 8.7 Skills Layer

Skills are modular knowledge-and-behavior bundles — distinct from hooks (enforcement), MCP (tools), and policies (intent) — loaded on demand via progressive disclosure to preserve token efficiency. User-global skills live in `~/.anvil/skills/`; workspace overlays in `.agents/skills/`. Skills activate only when triggered by phase context or explicit reference, never preloaded wholesale, and respect the configuration-precedence model and the three security profiles (`open`, `restricted`, `strict`).

### 8.8 Hooks and Events Layer

Hooks are lifecycle-boundary interceptors around tool use, prompt submission, and session/run transitions — the deterministic mechanism that enforces policy at runtime via a stable block/allow contract. Events are the structured stream emitted across that lifecycle (conversation state, actions/observations, hook executions, token/cost telemetry) and form the audit trail behind every escalation, resume, and postmortem. Hook source-of-truth lives under `~/.anvil/`, merges with workspace overrides, and compiles into the runtime projection (§8.5) so OpenHands-native paths stay authoritative. Anvil-specific telemetry may ride alongside native events when first-class queryability is required.

### 8.9 MCP Tool Integration Layer

MCP is Anvil's external tool surface — distinct from skills (knowledge), hooks (enforcement), and policies (intent). Servers are declared in Anvil configuration and resolved per run into the workspace runtime config (§8.5), making the run's tool set deterministic and auditable. Tool registration is policy-gated by server, by tool name or pattern, and by the active security profile (`open`, `restricted`, `strict`); unspecified tools are denied by default in `restricted` and `strict`. Discovery uses bounded timeouts, self-heals on transient failures, and escalates with actionable diagnostics when handshake or listing cannot converge.

### 8.10 Configuration Precedence

Effective configuration is resolved at run start using a fixed four-level precedence (highest wins):

1. Run-time flags and overrides supplied at invocation.
2. Workspace-local configuration in the active project.
3. User-root defaults under `~/.anvil/`.
4. Extension built-in defaults.

This applies uniformly to policies, hooks, skills, MCP server selection, and model-routing overrides.

## 9. Proposed Phases and Deliverables

Anvil executes a twelve-phase pipeline. Each phase is owned by a dedicated agent with a defined input/output contract and emits artifacts under `docs/`, `src/`, `tests/`, `build/`, `deployment/`, or `logs/` as applicable:

| # | Phase | Agent | Primary Output |
|---|---|---|---|
| 1 | Proposal Development | `proposal_agent` | `docs/proposal/code-proposal.md` |
| 2 | Factory Initialization | `factory_init_agent` | Initial repository structure (`docs/`, `src/`, `tests/`, `logs/`, …) |
| 3 | Specification Development | `specification_agent` | `docs/specifications/software-specification.md` |
| 4 | Architecture Design | `architecture_agent` | `docs/architecture/system-architecture.md` |
| 5 | Development Plan Creation | `dev_plan_agent` | `docs/development-plan/development-plan.md` |
| 6 | Code Blueprint Creation | `blueprint_agent` | `docs/blueprints/code-blueprint.md` |
| 7 | Code Implementation | `implementation_agent` | Source code under `src/` |
| 8 | Quality Assurance Testing | `qa_agent` | `docs/qa/qa-test-plan.md` plus tests under `tests/unit/`, `tests/integration/`, `tests/e2e/` |
| 9 | Packaging | `packaging_agent` | `docs/packaging/packaging-plan.md` plus `build/` artifacts |
| 10 | Documentation Writing | `documentation_agent` | `docs/documentation/documentation-plan.md` |
| 11 | Deployment | `deployment_agent` | `docs/deployment/deployment-plan.md` plus `deployment/` scripts |
| 12 | Factory Cleanup | `cleanup_agent` | `docs/summary/phase-summary-log.md` |

Phase dependencies are encoded in the DAG (see §8.6); the supervisor selects ready phases according to current state, operational mode, and approval gates.

## 10. Model and Tooling Strategy

- OpenRouter is the LLM provider abstraction.
- Routing is **phase + task hybrid**: each phase declares a default model, and subtasks within a phase (for example: planning, code generation, debugging, review) may route to different models.
- Initial model defaults:
	- Claude 3 Haiku for planning, analysis, and architecture.
	- DeepSeek Coder for coding-heavy generation and refactoring.
- User-configurable overrides at both phase and subtask granularity, resolved through the configuration precedence hierarchy (§8.10).
- Extensible routing configuration for additional low-cost models.

## 11. Reliability, Recovery, and Escalation

- Self-heal first: retries and correction loops are default.
- Bounded retries: default of **two self-heal attempts per phase** before escalation.
- Retry counts, wall-clock budgets, and token budgets are all configurable via the configuration precedence hierarchy (§8.10).
- Escalations must include phase context and relevant event references.
- Checkpoint-based resume from last completed phase on restart.

## 12. Security and Secrets

- Use VS Code Secret Storage for OpenRouter key by default.
- Support `OPENROUTER_API_KEY` environment fallback for CI/headless.
- Redact sensitive values from logs and escalation payloads.
- Apply configurable network/tool access profiles (`open`, `restricted`, `strict`).

## 13. Risks and Mitigations

- Runtime dependency risk (Docker/WSL setup friction):
	- Mitigation: setup validation checks and startup diagnostics.
- Model behavior variability:
	- Mitigation: policy gates, deterministic phase contracts, and retry heuristics.
- Drift between docs and generated code:
	- Mitigation: mandatory drift checks at phase boundaries.
- Tool or MCP instability:
	- Mitigation: bounded timeouts, fallback paths, and actionable escalation packets.

## 14. Acceptance Criteria for Proposal Completion

This proposal is considered approved when it is accepted as the canonical high-level intent and supports downstream derivation of:

- `docs/spec.md` with testable requirements.
- `docs/architecture.md` with component and interaction definitions.
- `docs/blueprint.md` with implementation-ready module plans.
- `docs/plan.md` with phased slices and test strategy.

## 15. Open Questions for Alignment

All v0.1.0 alignment questions captured in earlier drafts have been resolved and folded into Sections 6, 7, 10, and 11. New questions arising during specification or architecture phases will be tracked here.

---

Status: Draft for collaborative review.