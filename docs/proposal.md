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

- Runs locally as a VS Code extension.
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

## 7. Operating Modes

- YOLO: full autonomous progression with no user stops.
- Gated: user selects phases requiring approval.
- Secure: fixed mandatory approval checkpoints.

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

### 8.5 Runtime Projection Model

User-level intent and policy live in `~/.anvil/`. At run start, effective runtime files are materialized into workspace-local runtime folders (for hooks, MCP resolution, and policy snapshot) to ensure reproducible, auditable execution.

## 9. Proposed Phases and Deliverables

Anvil will execute a multi-phase pipeline including:

- Proposal development
- Factory initialization
- Specification development
- Architecture design
- Development plan creation
- Code blueprint creation
- Code implementation
- Quality assurance testing
- Packaging
- Documentation writing
- Deployment
- Factory cleanup and summary logging

Each phase will emit a defined artifact set in the repository (primarily under `docs/`, plus `src/`, `tests/`, `build/`, `deployment/`, and `logs/` as applicable).

## 10. Model and Tooling Strategy

- OpenRouter is the LLM provider abstraction.
- Initial model defaults:
	- Claude 3 Haiku for planning, analysis, and architecture.
	- DeepSeek Coder for coding-heavy generation and refactoring.
- User-configurable model overrides per phase.
- Extensible routing configuration for additional low-cost models.

## 11. Reliability, Recovery, and Escalation

- Self-heal first: retries and correction loops are default.
- Bounded retries: escalate only after non-convergence.
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

- Should v0.1.0 require packaging and deployment automation in full, or allow those as documentation-first outputs?
- What exact secure-mode checkpoints are mandatory by default?
- Which default routing policy should be first-class in v0.1.0: phase-based only, or phase+task hybrid?
- What are the required thresholds for auto-escalation (retry counts, time budgets, token budgets)?

---

Status: Draft for collaborative review.