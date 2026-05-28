---
artifactId: architecture-v1
phase: architecture
derivedFrom:
  - docs/proposal.md
  - docs/spec.md
  - domain-knowledge/background-information.md
inputHashes:
    docs/proposal.md: 1aa139f744458770f2ce8be24e10d9eb1aafb9e941cb27425a3bbcfc99a75bb9
    docs/spec.md: b5b485a99e5233d30c2ded6ded515a9e3a907db4cac8c5f9506284331c0ebe83
    domain-knowledge/background-information.md: 3091f31fb045c3447898da081c7aa0bb7bb5f1c58f62c40f2b0884bd8a7c3bd2
generatedAt: 2026-05-24T17:00:00Z
runId: manual-draft-2026-05-24
---

# Anvil Architecture (v0.1.0)

## 1. Overview

This document defines the component architecture for **Anvil v0.1.0**, a local-first, supervisor-orchestrated coding factory built on the OpenHands SDK and OpenRouter LLMs. It is derived from [docs/proposal.md](proposal.md) (intent and scope) and [docs/spec.md](spec.md) (testable requirements), and translates them into a concrete set of components, interactions, and runtime models that downstream phases (Blueprint, Plan, Implementation) can directly consume.

The architecture is shaped by three forces:

1. **Instruction fidelity and drift control** — explicit phase contracts, single-writer artifact ownership, and mandatory drift checks at phase boundaries.
2. **Token and latency efficiency** — progressive disclosure of skills, reference-based phase handoff, and serial execution with parallel-ready DAG semantics.
3. **Auditable governance** — policy-driven hooks at every lifecycle boundary, a structured event stream as the source of truth for escalation, and deterministic security profiles.

Section 3 enumerates the components; sections 4 and 5 show how they interact; sections 6–8 cover cross-cutting concerns (config/runtime, security, performance); section 9 maps every spec requirement to the component that owns it.

---

## 2. Architecture Principles

The following principles are normative — every component decision in §3 traces back to one or more of them.

1. **Supervisor-centric orchestration, single-writer artifacts.** Exactly one Development Manager coordinates phase progression; exactly one phase agent owns each artifact path. The supervisor never authors phase artifacts; phase agents never write outside their declared output paths. (Spec FR-ROLE-001 through FR-ROLE-005.)
2. **Contract-driven phase agents.** Each phase agent has explicit inputs, outputs, allowed tools, model constraints, and completion criteria. Contracts are the authoritative task boundary; prompt content cannot widen them. (Spec FR-PA-001 through FR-PA-010.)
3. **Artifact-first workflow.** Design intent (proposal → spec → architecture → blueprint → plan) precedes code. All artifacts carry lineage metadata (front-matter + SHA-256 checksums) so downstream consumers can verify they read the same version. (Spec §2.3, §4.1.)
4. **Policy and hook enforcement at lifecycle boundaries.** Policies declare intent; hooks enforce it deterministically at tool use, prompt submission, and session/phase transitions. Auto-remediation is attempted before escalation. (Proposal §8.4, §8.8; Spec §2.6, §5.1.)
5. **Layered configuration precedence with runtime projection.** A fixed four-level merge (run-time flag > workspace > user-root > built-in) produces effective configuration once per run; that snapshot is materialized into a workspace-local runtime projection so the run is reproducible and auditable. (Proposal §8.5, §8.10; Spec §2.7, §7.)
6. **Progressive disclosure for token efficiency.** Skills, prior artifacts, and context are loaded on demand by reference, not preloaded inline. Average phase context payload ≤ 4000 tokens. (Spec §2.9, NFR-TK-001/002.)
7. **Bounded self-healing with deterministic escalation.** Retries (default 2 per phase, exponential backoff), remediation attempts (separate budget of 2), and drift remediation are tried before escalation. Every escalation packet includes phase context and event references. (Spec §2.1.5, §2.5.3, §8.)
8. **Forward-compatible serial execution.** Phase dependencies are declared as a DAG, but v0.1.0 executes serially to preserve simple resume and self-heal semantics. The contract is parallel-ready; the scheduler is not. (Proposal §8.6.)
9. **Transport-agnostic agent contracts.** v0.1.0 uses in-process agent invocation and a localhost REST API; agent contracts are designed so a future message bus or A2A peer transport can be added without rewriting agent logic. (Proposal §6 non-goals; background §455–459.)
10. **Auditable by default, with named security profiles.** Every supervisor action is logged to a structured event stream. Three security profiles (`open`, `restricted`, `strict`) apply uniformly to MCP tools, network access, and policy strictness. (Spec §6.1, NFR-OB-001 through NFR-OB-005.)

---

## 3. Component Definitions

Components are grouped into seven logical layers. Each component lists its responsibility, the spec requirements it owns, its dependencies, and the interfaces it exposes.

### 3.1 Surfaces (User-Facing Layer)

#### 3.1.1 VS Code Chat Participant

**Responsibility.** The user's primary interaction surface. Implemented via `vscode.chat.createChatParticipant`, it accepts natural-language prompts, surfaces phase progress, approval requests, and escalations through native VS Code affordances (status bar, notifications, chat replies). It is a thin client — it holds no Anvil state and performs no LLM calls of its own.

**Owns.** Proposal §3 (chat participant + native affordances), §7 (mode display), §12 (Secret Storage access).

**Depends on.** Anvil Runtime API (§3.1.2), Secret Storage Adapter (§3.3.3).

**Interfaces.** Outbound HTTP/SSE calls to `http://localhost:<port>/v1/...`. Inbound VS Code chat events. Reads/writes OpenRouter API key via `vscode.SecretStorage`.

#### 3.1.2 Anvil Runtime API

**Responsibility.** A localhost FastAPI service that exposes versioned endpoints for run control, phase state, artifacts, events, and health. It is the integration boundary between the VS Code extension (and any future programmatic caller) and the in-process Development Manager. Streams events back to clients via Server-Sent Events.

**Owns.** Proposal §3 (localhost REST API), proposal §6 in-scope item (programmatic users), spec §2.1.7 (event stream exposure), spec §4.2.3 (run-control signal schemas).

**Depends on.** Development Manager (§3.2.1), Event Bus (§3.5.1), Checkpoint Store (§3.5.2).

**Interfaces.**
- `POST /v1/runs` — start a run (mode, profile, overrides).
- `GET /v1/runs/{id}` — run state and current phase.
- `POST /v1/runs/{id}/approve` — supply approval payload `{gateId, gateName, approved, comments?, requesterId}`; Secure-mode gates require explicit `approved: true` for the named checkpoint.
- `POST /v1/runs/{id}/override` — request `{action: force-advance|rollback|stop, targetPhase?, reason, comments?, requesterId}`; `targetPhase` is required for rollback.
- `GET /v1/runs/{id}/events` — SSE stream of audit events.
- `GET /v1/artifacts/{phase}` — artifact metadata + content.
- `GET /v1/health` — readiness/liveness with diagnostic summary.

### 3.2 Orchestration Core

#### 3.2.1 Development Manager (Supervisor)

**Responsibility.** The central orchestrator. Loads effective configuration, validates runtime prerequisites, maintains the phase DAG and logical artifact registry, dispatches phase agents in topological order, enforces operational mode gates (YOLO/Gated/Secure), runs validation and drift checks at phase boundaries, manages retry/remediation/escalation budgets, performs rollback by marking downstream outputs stale and invalidating checkpoints, validates checkpoint artifacts before resume, and persists checkpoints. It is a coordinator only — it never authors phase artifacts (FR-ROLE-001).

**Owns.** Spec FR-SV-001 through FR-SV-026; FR-OM-001 through FR-OM-014, FR-OM-008A; §2.1.5 retry/escalation; §2.1.6 checkpoint resume; §2.1.7 audit trail emission.

**Depends on.** Configuration Resolver (§3.3.1), Runtime Projection Layer (§3.3.2), Phase Agent Framework (§3.2.2), Specialist Role Registry (§3.2.3), Policy Engine (§3.4.1), Hook Layer (§3.4.2), Artifact Validator (§3.4.3), Drift Checker (§3.4.4), Event Bus (§3.5.1), Checkpoint Store (§3.5.2).

**Interfaces.**
- `start_run(config) → RunId` — begin a new run.
- `dispatch_phase(phase_id) → PhaseResult` — invoke a phase agent.
- `await_approval(gate_id, gate_name) → ApprovalSignal` — block on a gated phase.
- `rollback(target_phase, reason) → RollbackPlan` — mark downstream phases stale and clear their checkpoint entries.
- `escalate(packet) → UserDecision` — pause and surface an escalation.
- `resume(run_id) → ResumePlan` — restart from the earliest phase whose checkpoint and artifacts remain valid.

#### 3.2.2 Phase Agent Framework

**Responsibility.** A common runtime that hosts the twelve phase agents (proposal, factory_init, specification, architecture, blueprint, dev_plan, implementation, qa, packaging, documentation, deployment, cleanup). Each agent is a configured instance with a declarative contract (phase name, inputs, input schemas, outputs, phase context, previous phase outputs, allowed tools, model constraints, completion criteria). The framework enforces single-writer rules through a path-ownership map derived from the artifact contracts, mediates writes during agent execution, performs post-run diff validation, surfaces task-level events, and propagates supervisor timeouts/cancellations as unsuppressed phase failures.

**Owns.** Spec FR-PA-001 through FR-PA-010; proposal §9 (twelve-phase pipeline); per-artifact schemas in spec §4.1.

**Depends on.** OpenHands SDK Adapter (§3.7.2), MCP Integration Layer (§3.6.1), Skills Loader (§3.6.2), OpenRouter LLM Provider (§3.7.1), Event Bus (§3.5.1), Policy Engine (§3.4.1).

**Interfaces.**
- `invoke(contract, payload) → PhaseResult`
- `authorize_write(phase_id, path) → Allow | Deny` — enforce contract-owned output paths.
- `emit_event(event)` — task-level observability (`FileWritten`, `ReviewCompleted`, etc.).
- `propagate_signal(signal) → void` — forward timeout/cancel signals without suppression.
- Contract schema: `{phase_id, phase_name, inputs[], input_schemas[], outputs[], phase_context, previous_phase_outputs[], allowed_tools[], model_constraints, completion_criteria[]}`.

#### 3.2.3 Specialist Role Registry

**Responsibility.** Loads and merges the optional specialist role registries from `~/.anvil/specialist-roles.yaml` and `.anvil/specialist-roles.yaml` at run start, keyed by `roleId` with workspace-local definitions taking precedence. Provides the Development Manager with role definitions for bounded non-phase contributors (security review, performance analysis, etc.). Validates `roleSchemaVersion`, allowed invocation phases, protected-path boundaries, and policy compatibility, and ensures specialist invocations remain tied to the current phase and approval context.

**Owns.** Spec FR-SA-001 through FR-SA-017; spec §4.1.10 (registry artifact).

**Depends on.** Configuration Resolver (§3.3.1), Policy Engine (§3.4.1), Event Bus (§3.5.1).

**Interfaces.**
- `load_registry(user_path, workspace_path) → EffectiveRegistry`
- `validate(role_def, protected_paths) → ValidationResult`
- `effective_registry() → SpecialistRole[]`
- `invoke(role_id, context) → SpecialistResult`

### 3.3 Configuration and Runtime

#### 3.3.1 Configuration Resolver

**Responsibility.** Resolves the effective runtime configuration once per run by merging four precedence levels: run-time flags > workspace-local (`.anvil/config.yaml`) > user-root (`~/.anvil/config.yaml`) > extension built-ins. Applies the documented merge semantics: scalars override, lists union, maps deep-merge. Validates the merged schema against the current `configVersion`, resolves phase/subtask model-routing overrides, reports syntax/version errors with file-and-line diagnostics, and logs the effective configuration to the audit trail.

**Owns.** Spec FR-CF-001 through FR-CF-007, FR-ML-005; §7 (configuration management); proposal §8.10.

**Depends on.** Secret Storage Adapter (§3.3.3) for resolving secret references.

**Interfaces.**
- `resolve(invocation_flags) → EffectiveConfig`
- `validate(config) → ValidationResult` — includes file/line diagnostics for syntax or version failures.
- `snapshot(config) → JSON` — for the audit trail.

#### 3.3.2 Runtime Projection Layer

**Responsibility.** At run start, materializes user-root intent (`~/.anvil/`) and workspace overrides into a workspace-local runtime projection. Compiles canonical hooks, snapshots merged policy and MCP configuration, initializes run-state, and ensures audit outputs exist under `logs/`. Workspace-local `.anvil/skills/` and `.anvil/specialist-roles.yaml` remain source overrides rather than being relocated. Writes:
- `.openhands/hooks.json` — OpenHands-compatible compiled hook config.
- `.openhands/runtime/mcp.generated.json` — resolved MCP server config.
- `.openhands/runtime/policy-snapshot.json` — effective merged policy.
- `.anvil/run-state.json` — checkpoint store (initialized; written to by §3.5.2).
- `logs/events.jsonl` — structured audit trail.
- `logs/run-summary.log` — human-readable per-phase summaries.

This makes runs reproducible: the entire effective configuration is committed to a known set of files before any agent work begins.

**Owns.** Proposal §8.5 (runtime projection model); background-information lines 530–541 (directory mapping).

**Depends on.** Configuration Resolver (§3.3.1), Policy Engine (§3.4.1), Hook Layer (§3.4.2), MCP Integration Layer (§3.6.1).

**Interfaces.**
- `project(effective_config) → ProjectionManifest`
- `verify_projection() → ValidationResult`

#### 3.3.3 Secret Storage Adapter

**Responsibility.** Single point of access for the OpenRouter API key and any other secrets (e.g., MCP server credentials). Uses VS Code Secret Storage by default; falls back to the `OPENROUTER_API_KEY` environment variable for CI/headless scenarios. Exposes a redaction interface used by the Event Bus to scrub secrets from logs.

**Owns.** Spec NFR-SC-001 through NFR-SC-005; spec §3.5, §6.3, §6.4.

**Depends on.** None (leaf component).

**Interfaces.**
- `get_secret(name) → string`
- `redact(text) → string` — applies `SecretRedactionRules` policy.

### 3.4 Policy and Enforcement

#### 3.4.1 Policy Engine

**Responsibility.** Loads policy files from `~/.anvil/policies/` and `.anvil/policies/`, merges them through the same precedence model as configuration, validates `policyVersion`, applies the default `remediable=false` rule when omitted, and evaluates policy checks at runtime. Built-in policies include `AllowedModels`, `TokenBudgetPerPhase`, `MaxRetriesPerPhase`, `MCPToolWhitelist`/`Blacklist`, `SecretRedactionRules`, `NetworkAccessPolicy`, and `RequiredApprovalGates`. Policy decisions are remediable or non-remediable per policy definition; the engine routes remediable violations through the configured `remediationStrategy`, consumes model-route and token-usage events for budget enforcement, and emits file-and-line diagnostics for invalid policy files.

**Owns.** Spec FR-PL-001 through FR-PL-008, FR-PL-003A; §4.3 policy file schema; §2.6.2 core policies.

**Depends on.** Configuration Resolver (§3.3.1), Event Bus (§3.5.1).

**Interfaces.**
- `load() → PolicyBundle`
- `check(action_context) → AllowDecision | DenyDecision | RemediationRequest`
- `record_usage(phase, subtask, usage) → BudgetDecision`
- `enforce(decision) → EnforcementResult`
- `list_policies() → Policy[]`

#### 3.4.2 Hook Layer

**Responsibility.** Executes canonical lifecycle-boundary interceptors and compiles them into `.openhands/hooks.json`. The public contract covers `BeforeToolInvocation`, `AfterToolInvocation`, `BeforePromptSubmission`, `AfterPromptResponse`, `PhaseStart`, `PhaseComplete`, `BeforeApprovalDecision`, `AfterApprovalDecision`, `BeforeRetry`, and `BeforeEscalation`. OpenHands-native callbacks are one execution target; supervisor-managed adapters cover hook points that are not natively exposed by OpenHands while preserving the same allow/deny/mutate semantics and audit logging behavior.

**Owns.** Proposal §8.8; background §544–562; spec §4.2.2, §5.1.

**Depends on.** Policy Engine (§3.4.1), Event Bus (§3.5.1).

**Interfaces.**
- `compile(definitions) → HookManifest`
- `before_tool_invocation(tool, args) → Allow | Deny | Mutate`
- `after_tool_invocation(tool, result, duration) → void`
- `before_prompt_submission(prompt, model) → Allow | Deny | Mutate`
- `after_prompt_response(prompt, response, usage) → void`
- `phase_start(phase) → void`
- `phase_complete(phase, artifacts) → void`
- `before_approval_decision(gate, context) → Allow | Deny | Mutate`
- `after_approval_decision(gate, decision) → void`
- `before_retry(context) → Allow | Deny | Mutate`
- `before_escalation(packet) → Allow | Deny | Mutate`

#### 3.4.3 Artifact Validator

**Responsibility.** After a phase agent reports completion, validates produced artifacts against their declared schema (spec §4.1). Checks include: required sections present, minimum content thresholds (e.g., spec ≥ 10 FRs; architecture ≥ 8 components), front-matter well-formed, required input hashes present, artifact/version identifiers compatible with the current runtime, and Markdown syntactically valid. Validation is deterministic pass/fail (no warnings), version-aware (dispatches compatibility validators for prior artifact formats or emits actionable rejection), and returns section/line diagnostics. On failure, it produces a structured validation error report that the Development Manager feeds back into the owning phase agent as retry context. Times out at 30 seconds per artifact (NFR-LT-004).

**Owns.** Spec FR-AR-001 through FR-AR-008; per-artifact validation criteria in §4.1.

**Depends on.** Event Bus (§3.5.1).

**Interfaces.**
- `validate(phase, artifact_paths) → ValidationResult`
- `schema(phase, artifact_version?) → ArtifactSchema`

#### 3.4.4 Drift Checker

**Responsibility.** After implementation and at every artifact boundary, compares downstream artifacts against upstream controlling artifacts in the required order: **Blueprint → Architecture → Spec** (FR-DR-002A). Detects five drift categories (spec §2.5.1): code features absent from blueprint/architecture/spec; missing/incomplete components; unverified non-functional requirements; naming and boundary violations; test coverage gaps. To evaluate coverage drift, it loads QA Test Plan targets and coverage reports into a normalized coverage snapshot. It also includes specialist-generated supplemental artifacts when they are declared normative inputs to downstream phases. Categorizes drift as minor/major/critical and routes through the appropriate remediation path: minor → phase agent re-invocation or explicitly logged tolerated drift, major → upstream phase rollback with stale marking, critical → escalation. Honors user-acknowledged drift overrides from effective configuration and records them through the Event Bus.

**Owns.** Spec FR-DR-001 through FR-DR-010.

**Depends on.** Artifact Validator (§3.4.3), Event Bus (§3.5.1).

**Interfaces.**
- `check(phase, code_or_artifact) → DriftReport`
- `collect_coverage(qa_plan, coverage_reports) → CoverageSnapshot`
- `remediate(drift_report) → RemediationResult`
- `accept(drift_id, override) → AcceptedDrift`

### 3.5 Observability and State

#### 3.5.1 Event Bus / Audit Trail

**Responsibility.** Single structured event stream and summary-log writer for all supervisor actions, hook executions, phase lifecycle transitions, approval/override decisions, artifact version records, and token/cost telemetry. Emits machine-readable events to `logs/events.jsonl` (one JSON event per line; monotonically increasing timestamps) and human-readable phase summaries to `logs/run-summary.log`. Applies secret redaction (via §3.3.3) before write. Indexed by event type, timestamp, phase, severity, run ID, and artifact ID for queryability. Also surfaces over Server-Sent Events through the Anvil Runtime API and prepares retention references consumed by the Cleanup/final-commit workflow.

**Owns.** Spec §4.2.1 event schema; NFR-OB-001 through NFR-OB-005; spec §5 hooks-and-events lifecycle.

**Depends on.** Secret Storage Adapter (§3.3.3) for redaction.

**Interfaces.**
- `emit(event)` — append to stream.
- `write_phase_summary(summary) → void`
- `record_artifact_version(metadata) → void`
- `query(filter) → Event[]` — by phase, type, severity, timeframe.
- `subscribe(filter) → Stream<Event>` — for SSE.

#### 3.5.2 Checkpoint and Resume Store

**Responsibility.** Persists run state after every phase completion to `.anvil/run-state.json`: phase name, completion timestamp, artifact checksums, mode, profile, retry counters, and stale-phase markers. On restart, loads the newest compatible format, migrates older formats when possible, validates referenced artifacts/checksums before phases are skipped, and returns the earliest valid resume point. Emits `ResumeFromCheckpoint` on success and `ResumeValidationFailed` when checkpoint metadata no longer matches workspace state. Versioned (`runStateVersion`) for forward compatibility.

**Owns.** Spec FR-SV-021 through FR-SV-023, FR-SV-022A; NFR-RB-004, NFR-RB-005.

**Depends on.** Event Bus (§3.5.1) for emitting `ResumeFromCheckpoint`.

**Interfaces.**
- `save(phase, metadata) → void`
- `load() → RunState | null`
- `validate_artifacts(run_state) → ResumeValidationResult`
- `migrate(run_state) → RunState`
- `last_completed_phase() → PhaseId | null`

### 3.6 Tools and Knowledge

#### 3.6.1 MCP Integration Layer

**Responsibility.** Discovers, authorizes, and invokes MCP (Model Context Protocol) servers declared in the runtime projection. Performs bounded discovery (5 second per-server timeout, NFR-LT-003), caches tool schemas in `.anvil/mcp-tools-cache.json`, validates agent tool arguments against discovered schemas, and enforces tool authorization per the active security profile (open/restricted/strict). Includes the built-in core toolset (file I/O, git ops, logging, sandboxed shell) that is always available regardless of profile.

**Owns.** Spec FR-MC-001 through FR-MC-014; §6.1 security profile applicability for tools.

**Depends on.** Policy Engine (§3.4.1), Hook Layer (§3.4.2), Event Bus (§3.5.1), Runtime Projection Layer (§3.3.2).

**Interfaces.**
- `discover() → ToolCatalog`
- `authorize(tool_name, profile) → AuthDecision`
- `invoke(tool_name, args) → ToolResult`

#### 3.6.2 Skills Loader

**Responsibility.** Implements progressive-disclosure skill loading. Skills (Markdown or code bundles with `SKILL.md` or `skill.json` descriptors) are stored in `~/.anvil/skills/`, `.anvil/skills/`, and built-in extension skill packs, and are loaded on demand when (a) a phase contract references them by name, (b) an agent explicitly requests one, or (c) drift remediation suggests one. Workspace skills override user-root and built-in skills by name; the resolved skill list is frozen at phase start and is not hot-reloaded during agent execution.

**Owns.** Spec FR-SK-001 through FR-SK-008; proposal §8.7; background §581–600.

**Depends on.** Configuration Resolver (§3.3.1), Policy Engine (§3.4.1), Runtime Projection Layer (§3.3.2).

**Interfaces.**
- `resolve_for_phase(phase_id) → Skill[]`
- `load(skill_name) → SkillBundle`
- `freeze_manifest(phase_id) → SkillManifest`
- `emit_skill_loaded(skill) → void` — token-budget event.

### 3.7 External Integrations

#### 3.7.1 OpenRouter LLM Provider

**Responsibility.** Single abstraction over OpenRouter's model gateway. Implements **phase + subtask hybrid routing**: each phase declares a default model; subtasks within a phase (planning, analysis, coding, debugging, review) may route to different models. Initial defaults: Gemma 4 for planning, analysis, and architecture-oriented subtasks; DeepSeek Coder for coding-heavy and implementation-debugging subtasks; review subtasks inherit the phase default unless explicitly overridden. Supports user overrides at both phase and subtask granularity through configuration precedence. Tracks per-phase token usage, emits `ModelRouteSelected` and `TokenUsageReported`, and surfaces usage to the Policy Engine for `TokenBudgetPerPhase` enforcement.

**Owns.** Proposal §10; spec FR-ML-001 through FR-ML-006; spec §2.6 (model allowlist policy); NFR-TK-001 through NFR-TK-003.

**Depends on.** Secret Storage Adapter (§3.3.3), Policy Engine (§3.4.1), Event Bus (§3.5.1).

**Interfaces.**
- `complete(phase, subtask, prompt) → CompletionResult`
- `route(phase, subtask) → ModelId`
- `usage_report(phase) → TokenUsage`
- `report_usage(phase, subtask, usage) → BudgetDecision`

#### 3.7.2 OpenHands SDK Adapter

**Responsibility.** Wraps the OpenHands runtime (Tier-1 "agent core" in background §332). Manages the Dockerized execution sandbox, the OpenHands event stream, action/observation routing, and `LLM_CONFIG` wiring to the OpenRouter Provider. Consumes hook configuration from `.openhands/hooks.json`, invokes Hook Layer adapters for lifecycle boundaries that live above the SDK (approval, retry, escalation), and surfaces native OpenHands events into the Anvil Event Bus. v0.1.0 uses in-process agent invocation; transport-agnostic interface allows a future message-bus or A2A migration without contract change.

**Owns.** Proposal §3 (OpenHands as orchestration engine); background §327–367 (custom agent architecture).

**Depends on.** OpenRouter LLM Provider (§3.7.1), Hook Layer (§3.4.2), Event Bus (§3.5.1).

**Interfaces.**
- `start_session(agent_config) → SessionId`
- `dispatch_action(session, action) → Observation`
- `event_stream(session) → Stream<OpenHandsEvent>`

---

## 4. Data Flow Diagrams

### 4.1 System Context

```mermaid
graph TD
    User[Repo Owner / Developer] -->|chat prompt| VS[VS Code Chat Participant]
    VS -->|REST + SSE| API[Anvil Runtime API]
    API -->|in-process calls| DM[Development Manager]
    DM -->|invokes| Phase[Phase Agents 1..12]
    DM -->|invokes| Spec[Specialist Agents]
    Phase -->|via SDK Adapter| OH[OpenHands SDK]
    Spec -->|via SDK Adapter| OH
    OH -->|sandboxed| Sandbox[Docker Sandbox]
    OH -->|LLM calls via Provider| OR[OpenRouter Gateway]
    OR -->|route| Gemma[Gemma 4]
    OR -->|route| DSC[DeepSeek Coder]
    DM -->|reads| Workspace[(Workspace .anvil/, docs/, src/, tests/, logs/)]
    Phase -->|writes artifacts| Workspace
    DM -->|writes events| Workspace
```

### 4.2 Component Dependency Graph

Acyclic by construction; the Event Bus is a write-only sink for most components and is therefore not shown as introducing dependencies.

```mermaid
graph TD
    VSCode[VS Code Chat Participant] --> API[Anvil Runtime API]
    API --> DM[Development Manager]

    DM --> CR[Configuration Resolver]
    DM --> RP[Runtime Projection]
    DM --> PAF[Phase Agent Framework]
    DM --> SRR[Specialist Role Registry]
    DM --> PE[Policy Engine]
    DM --> HL[Hook Layer]
    DM --> AV[Artifact Validator]
    DM --> DC[Drift Checker]
    DM --> CS[Checkpoint Store]

    PAF --> OHA[OpenHands SDK Adapter]
    PAF --> MCP[MCP Integration]
    PAF --> SK[Skills Loader]
    PAF --> ORP[OpenRouter Provider]
    SRR --> PAF

    RP --> CR
    RP --> PE
    RP --> HL
    RP --> MCP
    PE --> CR
    HL --> PE
    MCP --> PE
    MCP --> HL
    SK --> CR
    SK --> PE
    DC --> AV

    ORP --> SSA[Secret Storage Adapter]
    ORP --> PE
    OHA --> ORP
    OHA --> HL
    CR --> SSA
    VSCode --> SSA
```

---

## 5. System Interactions and Sequencing

### 5.1 Run Start

```mermaid
sequenceDiagram
    participant U as User
    participant VS as VS Code Chat
    participant API as Anvil Runtime API
    participant DM as Development Manager
    participant CR as Config Resolver
    participant RP as Runtime Projection
    participant PE as Policy Engine
    participant SRR as Specialist Registry
    participant EB as Event Bus

    U->>VS: /anvil start --mode=secure
    VS->>API: POST /v1/runs {mode, flags}
    API->>DM: start_run(config)
    DM->>CR: resolve(flags)
    CR-->>DM: EffectiveConfig
    DM->>RP: project(effective_config)
    RP->>PE: load policies (merged)
    DM->>SRR: load_registry(user, workspace)
    SRR-->>DM: EffectiveRegistry
    RP-->>DM: ProjectionManifest
    DM->>EB: emit SupervisorStarted
    DM->>API: RunId
    API-->>VS: 201 Created {run_id}
    VS-->>U: Run started (mode=secure)
```

### 5.2 Phase Execution Lifecycle

State machine for a single phase, executed inside `dispatch_phase`:

```mermaid
stateDiagram-v2
    [*] --> PreconditionsCheck
    PreconditionsCheck --> Dispatch: deps satisfied
    PreconditionsCheck --> Escalate: missing inputs
    Dispatch --> ContractGuard
    ContractGuard --> AgentRunning: contract + path guard OK
    ContractGuard --> Escalate: contract violation
    AgentRunning --> ArtifactValidate: PhaseComplete
    AgentRunning --> Retry: agent failure
    Retry --> Dispatch: attempts < 2
    Retry --> Escalate: budget exhausted
    ArtifactValidate --> DriftCheck: schema OK
    ArtifactValidate --> Retry: schema fail
    DriftCheck --> ApprovalGate: drift OK or remediated
    DriftCheck --> Remediate: minor/major drift
    DriftCheck --> Escalate: critical drift
    Remediate --> Dispatch: remediation attempts < 2
    Remediate --> Escalate: remediation budget exhausted
    ApprovalGate --> Checkpoint: approved or no gate
    ApprovalGate --> OverrideHandling: override requested
    OverrideHandling --> Checkpoint: force-advance
    OverrideHandling --> Rollback: rollback requested
    Rollback --> [*]: downstream phases marked stale
    ApprovalGate --> [*]: user blocked
    Checkpoint --> [*]: phase complete
    Escalate --> [*]: paused
```

### 5.3 Failure, Retry, and Escalation

```mermaid
sequenceDiagram
    participant DM as Dev Manager
    participant PA as Phase Agent
    participant CS as Checkpoint Store
    participant EB as Event Bus
    participant U as User

    DM->>PA: invoke(contract, payload)
    PA-->>DM: failure(reason)
    DM->>EB: emit RetryAttempt(1)
    Note over DM: backoff 2s
    DM->>PA: invoke (retry 1)
    PA-->>DM: failure(reason)
    DM->>EB: emit RetryAttempt(2)
    Note over DM: backoff 4s
    DM->>PA: invoke (retry 2)
    PA-->>DM: failure(reason)
    DM->>EB: emit PhaseEscalation(packet)
    DM->>U: EscalationRequired (via API/VS Code)
    alt user retries
        U-->>DM: retry
        DM->>EB: emit RetryAttempt(user_override)
        DM->>PA: invoke(contract, payload)
    else user rolls back
        U-->>DM: rollback(target_phase, reason)
        DM->>EB: emit RollbackRequested
        DM->>CS: invalidate checkpoints >= target_phase
        DM->>DM: mark downstream artifacts stale
    else user stops
        U-->>DM: stop(reason)
        DM->>EB: emit RunStopped
    end
```

### 5.4 Resume from Checkpoint

```mermaid
sequenceDiagram
    participant API as Anvil Runtime API
    participant DM as Dev Manager
    participant CS as Checkpoint Store
    participant EB as Event Bus

    API->>DM: resume(run_id)
    DM->>CS: load()
    CS-->>DM: RunState{last_completed: blueprint}
    DM->>CS: validate_artifacts(run_state)
    alt checkpoint valid
        CS-->>DM: ResumeValidationResult{resume_from: plan}
        DM->>EB: emit ResumeFromCheckpoint
        DM->>DM: dispatch_phase(plan)
    else checkpoint invalid
        CS-->>DM: ResumeValidationResult{resume_from: architecture, invalid: [blueprint]}
        DM->>EB: emit ResumeValidationFailed
        DM->>DM: dispatch_phase(architecture)
    end
```

### 5.5 Approval Gate and Override Handling

```mermaid
sequenceDiagram
    participant DM as Dev Manager
    participant HL as Hook Layer
    participant EB as Event Bus
    participant API as Runtime API
    participant U as User

    DM->>HL: before_approval_decision(gate, context)
    DM->>EB: emit ApprovalRequired
    U->>API: POST /approve or /override
    API->>DM: approval_or_override(payload)
    alt approval granted
        DM->>HL: after_approval_decision(gate, approved)
        DM->>EB: emit ApprovalGranted
    else override accepted
        DM->>HL: after_approval_decision(gate, override)
        DM->>EB: emit ApprovalOverrideAccepted
    end
```

### 5.6 Specialist Invocation

```mermaid
sequenceDiagram
    participant DM as Dev Manager
    participant SRR as Specialist Registry
    participant SA as Specialist Agent
    participant EB as Event Bus

    DM->>SRR: validate(role_id, phase_context)
    SRR-->>DM: role allowed + protected paths OK
    DM->>SA: invoke(role_id, context, approval_context)
    SA-->>DM: SpecialistResult{status, outputs, checksums}
    DM->>EB: emit SpecialistInvocationComplete
    Note over DM: source-code changes requested by specialist are routed to Implementation phase
```

---

## 6. Configuration and Runtime Model

### 6.1 Configuration Precedence

```
Level 1 — Run-time flags          (highest priority)
Level 2 — Workspace config         .anvil/config.yaml
Level 3 — User-root config         ~/.anvil/config.yaml
Level 4 — Extension built-ins      (lowest priority)
```

Merge semantics:
- **Scalars**: higher level overrides lower.
- **Lists**: appended (union behavior) — e.g., `AllowedModels` accumulates entries from every level.
- **Maps**: deep-merged — keys at higher levels override; lower-level keys are retained when not overridden.

The merged result is validated against `configVersion: "0.1.0"` and logged at run start (FR-CF-005).

### 6.2 Runtime Projection

User intent lives in `~/.anvil/`; the run's actual runtime config is materialized into the workspace at run start:

```
~/.anvil/                     (source of truth)
├── skills/
├── specialist-roles.yaml
├── mcp/servers.json
├── hooks/hooks.json
├── policies/*.yaml
└── runtime/defaults.yaml

<workspace>/                  (generated and referenced per run)
├── .anvil/
│   ├── config.yaml          (workspace overrides)
│   ├── policies/            (workspace policy overrides)
│   ├── skills/              (workspace skill overrides)
│   ├── specialist-roles.yaml (workspace specialist overrides)
│   ├── run-state.json       (checkpoint)
│   └── mcp-tools-cache.json
├── logs/
│   ├── events.jsonl         (audit trail)
│   └── run-summary.log      (phase summaries)
└── .openhands/
    ├── hooks.json           (compiled effective hooks)
    └── runtime/
        ├── mcp.generated.json
        └── policy-snapshot.json
```

The projection is the durable record of "what configuration this run actually used."

### 6.3 Operational Modes

- **YOLO** — auto-advance through all phases; user-facing approval gates skipped; supervisor controls (validation, drift, policy, retries, checkpoints) remain enforced.
- **Gated** — user pre-selects a list of phases requiring approval; supervisor pauses at those.
- **Secure** — four mandatory gates enforced (Post-Proposal, Post-Architecture, Post-Blueprint, Pre-Deployment-Plan); user may add more but cannot remove the four. Explicit approval signal required at each.

Mode is set at run start and immutable for the duration of the run.

---

## 7. Security Architecture

### 7.1 Security Profiles

| Profile | MCP tool access | Network access | Policy strictness | Default for |
|---|---|---|---|---|
| `open` | All discovered tools allowed unless explicitly blacklisted | Configured endpoints | Advisory; violations logged | Single-user local dev |
| `restricted` | Whitelist required (`MCPToolWhitelist`) | Policy-approved hosts only | Violations escalate | Team workspaces, CI |
| `strict` | Built-in core tools only unless explicitly enabled per-tool | Approved destinations only | No auto-remediation; immediate escalation | Regulated environments |

Profile is selected at run start and applies uniformly to all phases (FR-SC-001/002).

### 7.2 Secret Management

- OpenRouter API key stored in VS Code Secret Storage (`vscode.SecretStorage`) by default.
- `OPENROUTER_API_KEY` environment variable fallback for headless/CI.
- All secrets accessed exclusively through the Secret Storage Adapter (§3.3.3).
- The Event Bus invokes the adapter's `redact()` before writing any event; `SecretRedactionRules` policy supplies the regex patterns.
- MCP server connection strings and webhook URLs marked `sensitive: true` in config are redacted from the audit trail.

### 7.3 Network Policy

- Enforced via `NetworkAccessPolicy` and the `PreToolUse` hook.
- Default allowlist for `restricted` profile: OpenRouter endpoint, configured MCP server hosts, the project's git remote.
- Outbound requests to non-allowlisted hosts are blocked by the hook (exit code 2) and logged as `PolicyViolation` events.

### 7.4 MCP Tool Authorization

- Authorization is checked at invocation time, not discovery time.
- Discovery is bounded at 5 seconds per server; transient discovery failures fall back to the on-disk cache, and absence of cache escalates with actionable diagnostics.
- Tool argument schemas are validated before invocation; mismatch fails the operation and emits `MCPToolInvocationFailed`.

---

## 8. Scalability and Performance Considerations

### 8.1 Token Efficiency

- Phase-to-phase handoff uses file paths and git checksums by default; inline content only when < 500 tokens (NFR-TK-002).
- Average phase context payload budget: ≤ 4000 tokens (NFR-TK-001).
- Token usage tracked per phase by the OpenRouter Provider; `TokenBudgetPerPhase` policy enforces hard caps.
- Skills loaded only when triggered; never preloaded wholesale.

### 8.2 Latency Targets

| Operation | Target | Source |
|---|---|---|
| Phase handoff (dispatch + validation) | ≤ 500 ms | NFR-LT-001 |
| Drift check (per phase) | ≤ 60 s | NFR-LT-002 |
| MCP tool discovery (per server) | ≤ 5 s | NFR-LT-003 |
| Artifact validation (per artifact) | ≤ 30 s | NFR-LT-004 |
| Policy evaluation (per check) | ≤ 100 ms | NFR-LT-005 |
| Mean time to recovery (transient failure) | < 10 s | NFR-RB-006 |

### 8.3 Serial Execution Today, Parallel-Ready Tomorrow

v0.1.0 executes the phase DAG serially in topological order. The DAG declaration is the durable contract; the scheduler is the swappable part. A future release can introduce a parallel scheduler that respects the same dependency declarations without changing phase agent contracts. Independent specialist invocations are similarly forward-compatible: their role contracts declare allowed invocation phases but do not assume serial execution.

### 8.4 Bounded Self-Healing

Three independent retry budgets, each defaulting to 2 attempts (overridable through configuration precedence):

- **Phase retry budget** (FR-SV-018) — covers agent execution failures.
- **Remediation budget** (FR-DR-008) — covers drift remediation.
- **MCP tool retry budget** (FR-MC-013) — covers transient tool invocation failures.

Exponential backoff (2 s base, 4 s second attempt). All budgets exhausted → escalation packet emitted to user with full phase context, last 50 events, retry history, and suggested recovery actions.

---

## 9. Gap Analysis (Spec vs. Architecture)

Every spec section maps to one or more components. Empty rows would indicate drift; this table has none.

| Spec Section | Requirements | Owning Component(s) |
|---|---|---|
| §2.1.1 Supervisor Initialization | FR-SV-001 – FR-SV-004 | Development Manager, Configuration Resolver, Runtime Projection |
| §2.1.2 Phase Management & Dispatch | FR-SV-005 – FR-SV-010 | Development Manager, Phase Agent Framework, Artifact Validator |
| §2.1.3 Role Separation (single-writer) | FR-ROLE-001 – FR-ROLE-005 | Development Manager, Phase Agent Framework |
| §2.1.3 Operational Mode Enforcement | FR-SV-011 – FR-SV-013 | Development Manager, Anvil Runtime API |
| §2.1.4 Artifact Validation & Drift | FR-SV-014 – FR-SV-016 | Artifact Validator, Drift Checker |
| §2.1.5 Error Recovery & Escalation | FR-SV-017 – FR-SV-020, FR-SV-020A, FR-SV-020B | Development Manager, Event Bus, Checkpoint Store |
| §2.1.6 Checkpoint-Based Resume | FR-SV-021 – FR-SV-023, FR-SV-022A | Checkpoint Store, Development Manager |
| §2.1.7 Logging & Audit Trail | FR-SV-024 – FR-SV-026 | Event Bus |
| §2.2 Phase Agent Contracts | FR-PA-001 – FR-PA-010 | Phase Agent Framework |
| §2.3 Artifact Production & Validation | FR-AR-001 – FR-AR-008 | Artifact Validator, Development Manager, Phase Agent Framework |
| §2.4 Operational Modes | FR-OM-001 – FR-OM-014, FR-OM-008A | Development Manager, Anvil Runtime API, Event Bus |
| §2.5 Drift Detection & Remediation | FR-DR-001 – FR-DR-010 | Drift Checker, Development Manager |
| §2.6 Policy Enforcement | FR-PL-001 – FR-PL-008, FR-PL-003A | Policy Engine, Hook Layer |
| §2.7 Configuration Precedence | FR-CF-001 – FR-CF-007 | Configuration Resolver, Runtime Projection |
| §2.7.4 Phase/Subtask Model Routing | FR-ML-001 – FR-ML-006 | OpenRouter Provider, Policy Engine, Configuration Resolver |
| §2.8 MCP Tool Integration | FR-MC-001 – FR-MC-014 | MCP Integration Layer, Policy Engine, Runtime Projection |
| §2.9 Skills Loading | FR-SK-001 – FR-SK-008 | Skills Loader |
| §2.10 Specialist Agent Extensibility | FR-SA-001 – FR-SA-017 | Specialist Role Registry, Development Manager, Phase Agent Framework |
| §3.1 Token Efficiency | NFR-TK-001 – NFR-TK-003 | OpenRouter Provider, Skills Loader, Phase Agent Framework |
| §3.2 Latency & Performance | NFR-LT-001 – NFR-LT-005 | Development Manager, MCP Integration, Artifact Validator, Policy Engine |
| §3.3 Observability | NFR-OB-001 – NFR-OB-005 | Event Bus, Secret Storage Adapter |
| §3.4 Reliability & Recovery | NFR-RB-001 – NFR-RB-006 | Development Manager, Drift Checker, Checkpoint Store |
| §3.5 Security & Secrets | NFR-SC-001 – NFR-SC-005 | Secret Storage Adapter, Event Bus, OpenRouter Provider |
| §3.6 Backward Compatibility | NFR-BC-001 – NFR-BC-004 | Configuration Resolver, Checkpoint Store, Artifact Validator, Specialist Role Registry |
| §4.1 Phase Artifact Schemas | §4.1.1 – §4.1.10 | Artifact Validator (schemas), Phase Agent Framework (production) |
| §4.2 Event & Hook Schemas | §4.2.1, §4.2.2, §4.2.3 | Event Bus, Hook Layer, Anvil Runtime API |
| §4.3 Policy File Schema | — | Policy Engine |
| §5 Hooks & Events Lifecycle | §5.1 – §5.3 | Hook Layer, Event Bus |
| §6 Security & Access Control | FR-SC-001 – FR-SC-003 | Policy Engine, Secret Storage Adapter, MCP Integration |
| §7 Configuration Management | — (summary of §2.7) | Configuration Resolver |
| §8 Error Handling & Recovery | §8.1 – §8.4 | Development Manager, Event Bus |

**No gaps identified.** Every functional and non-functional requirement traces to at least one component.

---

**Status**: Draft v1, ready for collaborative review.

**Next phase**: Upon approval, proceed to [docs/blueprint.md](blueprint.md) derivation.
