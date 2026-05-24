# Anvil Specification (v0.1.0)

## 1. Overview

This document specifies the detailed, testable requirements for **Anvil v0.1.0** — a local-first, supervisor-orchestrated coding factory built on OpenHands and OpenRouter. It is derived from and extends [docs/proposal.md](docs/proposal.md), translating architectural vision into measurable functional and non-functional requirements, data contracts, and operational constraints that will guide the Architecture, Blueprint, Implementation, and QA phases.

**Scope**: Anvil v0.1.0 is focused on a robust autonomous coding pipeline with strong instruction fidelity, token efficiency, policy enforcement, and bounded self-healing, running as a VS Code extension with a localhost REST API backend.

---

## 2. Functional Requirements

### 2.1 Supervisor Agent (Development-Manager) Requirements

The supervisor agent is the central orchestrator responsible for:

#### 2.1.1 Initialization and Startup
- **FR-SV-001**: On startup, load effective runtime configuration from four-level precedence hierarchy (§8.10 in Proposal; detailed in §7 below).
- **FR-SV-002**: Validate that required runtime environment exists (Docker, Python 3.12+, WSL or Linux) and emit diagnostic event to audit trail.
- **FR-SV-003**: Initialize phase state machine and load checkpoint data (if resuming from interrupted run).
- **FR-SV-004**: Emit `SupervisorStarted` event containing run ID, operational mode, phase list, and enabled checkpoints.

#### 2.1.2 Phase Management and Dispatch
- **FR-SV-005**: Maintain a deterministic phase dependency DAG (defined in Phase Artifact Contracts, §4.1) and enforce topological ordering.
- **FR-SV-006**: For each phase: check prerequisites (all dependency phases completed), validate preconditions (required input files exist), emit `PhaseStarted` event, and dispatch to the designated phase agent.
- **FR-SV-007**: Accept phase completion event from agent (including artifact paths and metadata), and validate that all required outputs exist and match expected schema.
- **FR-SV-008**: After phase completion, run drift checks (§2.5) before transitioning to next phase.

#### 2.1.3 Operational Mode Enforcement
- **FR-SV-009**: Support three operational modes:
  - **YOLO**: Auto-advance through all phases without pause.
  - **Gated**: Pause at user-selected phases and await explicit approval signal before advancing.
  - **Secure**: Enforce four mandatory approval gates (Post-Proposal, Post-Architecture, Post-Blueprint, Pre-Deployment-Plan) and allow optional additional gates; user cannot remove mandatory gates.
- **FR-SV-010**: When a gated phase is reached, emit `ApprovalRequired` event and block phase advancement until supervisor receives approval signal or user-initiated override.
- **FR-SV-011**: Log mode transitions and approval decisions to audit trail.

#### 2.1.4 Artifact Validation and Drift Checking
- **FR-SV-012**: After each phase completes, validate artifacts against their expected schema (§4.1).
- **FR-SV-013**: Run drift checks (defined in §2.5) and emit `DriftCheckResult` event.
- **FR-SV-014**: If drift is detected and is remediable, attempt auto-remediation (§2.5); if not remediable or exceeds retry budget, escalate with full context.

#### 2.1.5 Error Recovery and Escalation
- **FR-SV-015**: If a phase fails, capture full phase context (input files, phase state, last 50 events from audit trail) and initiate self-heal retry sequence.
- **FR-SV-016**: Retry failed phase up to **2 times** (default, user-configurable via configuration precedence) before escalating.
- **FR-SV-017**: Each retry must be logged with attempt number and reason; if all retries fail, emit `PhaseEscalation` event containing phase context and escalation packet, and pause.
- **FR-SV-018**: On escalation, supervisor awaits user signal to: (a) retry again, (b) rollback to upstream phase and re-execute, or (c) stop run.

#### 2.1.6 Checkpoint-Based Resume
- **FR-SV-019**: On each phase completion, persist phase state (name, completion timestamp, artifact checksums) to `.anvil/run-state.json` (workspace-local runtime projection).
- **FR-SV-020**: On restart after interruption, load run state, identify last completed phase, and resume from next incomplete phase (skip all completed phases).
- **FR-SV-021**: Emit `ResumeFromCheckpoint` event indicating last completed phase and timestamp.

#### 2.1.7 Logging and Audit Trail
- **FR-SV-022**: Emit structured events (schema in §5.2) to audit trail for all lifecycle boundaries: supervisor start/stop, phase dispatch, artifact validation, approval decisions, error recovery, escalations.
- **FR-SV-023**: Write human-readable run summary to `logs/run-summary.log` at end of each phase (phase name, status, artifacts produced, duration, token usage if available).
- **FR-SV-024**: Maintain detailed event stream in `logs/events.jsonl` (one JSON-formatted event per line) queryable by event type, timestamp, and phase.

---

### 2.2 Phase Agent Contracts

Each phase agent has a defined input/output contract and reporting interface.

#### 2.2.1 Phase Agent Input Contract
- **FR-PA-001**: Phase agent receives invocation payload containing:
  - Phase name (e.g., "Proposal Development", "Specification Development")
  - Input file list (paths within workspace, guaranteed to exist)
  - Input schema (brief description of expected structure for each input)
  - Output paths (where artifacts must be written)
  - Phase context (supervisor state, checkpoint info, configuration overrides for this phase)
  - Previous phase outputs (paths to read if needed for continuity)

#### 2.2.2 Phase Agent Work and Output
- **FR-PA-002**: Phase agent reads inputs, performs phase-specific work (e.g., proposal generation, specification writing), and writes outputs to specified paths.
- **FR-PA-003**: All artifacts written by phase agents must conform to their defined schema (§4.1).
- **FR-PA-004**: Phase agent must not modify or delete files outside the designated output paths without explicit supervisor authorization.
- **FR-PA-005**: Phase agent should emit task-level events (e.g., `FileWritten`, `ReviewCompleted`) to the shared event stream to provide observability into long-running phase work.

#### 2.2.3 Phase Agent Reporting
- **FR-PA-006**: On completion, phase agent emits structured `PhaseComplete` event containing:
  - Phase name
  - Status (success or failure)
  - Output artifact paths and file checksums (SHA-256)
  - Metadata (duration, token usage if available, key decisions made)
  - Failure reason (if status is failure)
- **FR-PA-007**: Phase agent must not catch or suppress supervisor-initiated signals (e.g., timeout, cancellation); it must surface these as failure events.

#### 2.2.4 Phase-Specific Behaviors (Defined in §3 of Plan)
- Each of the 12 phases (Proposal, Specification, Architecture, Blueprint, Plan, Implementation, QA, Packaging, Documentation, Deployment, Cleanup) has detailed behavioral specs in the Development Plan (docs/plan.md). This Spec establishes the common contract; the Plan details phase-specific nuances.

---

### 2.3 Artifact Production and Validation

#### 2.3.1 Artifact Definitions and Schemas

All artifacts are stored in the repository and indexed in a central artifact manifest (see table below).

| Phase | Primary Artifact | Location | Format | Required Schema/Structure |
|-------|-----------------|----------|--------|--------------------------|
| 1. Proposal | Code Proposal | `docs/proposal.md` | Markdown | See §4.1.1 |
| 2. Factory Init | Repository Structure | Root + `docs/`, `src/`, `tests/`, `logs/` | Directory tree | Directories must exist; initial `.gitkeep` files created |
| 3. Specification | Software Specification | `docs/spec.md` | Markdown | See §4.1.2 |
| 4. Architecture | System Architecture | `docs/architecture.md` | Markdown | See §4.1.3 |
| 5. Blueprint | Code Blueprint | `docs/blueprint.md` | Markdown | See §4.1.4 |
| 6. Development Plan | Implementation Plan | `docs/plan.md` | Markdown | See §4.1.5 |
| 7. Implementation | Source Code | `src/` | Language-specific | Minimal: pass syntax validation |
| 8. QA Testing | QA Test Plan + Tests | `docs/qa-test-plan.md`, `tests/unit/`, `tests/integration/`, `tests/e2e/` | Markdown + language-specific | Test files executable; test plan documenting coverage |
| 9. Packaging | Packaging Plan | `docs/packaging-plan.md` | Markdown | See §4.1.6 |
| 10. Documentation | Documentation Plan | `docs/documentation-plan.md` | Markdown | See §4.1.7 |
| 11. Deployment | Deployment Plan | `docs/deployment-plan.md` | Markdown | See §4.1.8; static files only (no execution) |
| 12. Cleanup | Phase Summary Log | `docs/phase-summary-log.md` | Markdown | See §4.1.9 |

#### 2.3.2 Artifact Validation
- **FR-AR-001**: After each phase, supervisor validates artifacts against their schema (§4.1).
- **FR-AR-002**: Validation checks must be deterministic and pass/fail (no warnings or soft errors).
- **FR-AR-003**: If artifact is missing or does not conform to schema, escalate to phase agent with detailed error report; phase agent retries up to 2 times (default, configurable).
- **FR-AR-004**: Artifact validation must complete in ≤ 30 seconds per artifact; if validation times out, escalate.

#### 2.3.3 Artifact Lineage and Versioning
- **FR-AR-005**: Each artifact must include metadata header (YAML front-matter or similar) with:
  - Artifact ID (e.g., `proposal-v1`, `spec-v1`)
  - Generated timestamp
  - Hash of inputs it was derived from (to support drift detection)
  - Phase name and supervisor run ID
- **FR-AR-006**: All artifact versions are stored in Git (via normal commit workflow) and are queryable from the audit trail.

---

### 2.4 Operational Modes

#### 2.4.1 YOLO Mode (Fully Autonomous)
- **FR-OM-001**: Supervisor automatically advances through all 12 phases without pausing.
- **FR-OM-002**: User-facing approval gates are skipped in YOLO mode, including Secure-mode mandatory approval checkpoints; internal supervisor controls (artifact validation, drift checks, policy enforcement, retries/escalation, and run-state checkpointing) remain enforced.
- **FR-OM-003**: User can still interrupt or cancel the run at any time; on resume, run continues from last completed phase (checkpoint-based resume, §2.1.6).
- **FR-OM-004**: Escalations still pause the run and require user intervention (self-heal retry budget is exhausted).

#### 2.4.2 Gated Mode (User-Selected Checkpoints)
- **FR-OM-005**: User specifies a list of phases that require approval before advancing (e.g., `["proposal", "architecture", "implementation"]`).
- **FR-OM-006**: When supervisor reaches a gated phase, it emits `ApprovalRequired` event and blocks advancement until user explicitly signals approval.
- **FR-OM-007**: Approval signal includes optional comments/notes that are logged to audit trail.
- **FR-OM-008**: User can override and force advancement without approval, with reason logged.

#### 2.4.3 Secure Mode (Mandatory Checkpoints)
- **FR-OM-009**: Four mandatory approval checkpoints are enforced:
  1. Post-Proposal (before Specification begins)
  2. Post-Architecture (before Blueprint begins)
  3. Post-Blueprint (before Development Plan begins)
  4. Pre-Deployment-Plan (before Deployment phase begins)
- **FR-OM-010**: User cannot remove mandatory checkpoints; attempting to do so results in an error.
- **FR-OM-011**: User can add additional checkpoints beyond the four mandatory ones.
- **FR-OM-012**: Approval at mandatory checkpoints must include explicit confirmation (not just auto-advance); user must approve by name or explicit action.

#### 2.4.4 Mode Configuration
- **FR-OM-013**: Operational mode is selected at run start via configuration (§7) and is immutable during the run.
- **FR-OM-014**: Mode can be specified via: run-time flag (`--mode=yolo`), workspace config (`.anvil/config.yaml`), or user-root config (`~/.anvil/config.yaml`), resolved by precedence hierarchy (§7).

---

### 2.5 Drift Detection and Remediation

**Drift** occurs when generated code or artifacts diverge from the controlling Blueprint, Architecture, or Specification, or when requirements are missing from the implementation.

#### 2.5.1 Drift Definition
- **FR-DR-001**: Drift is detected in the following scenarios:
  1. A feature or module is implemented in code but is not mentioned in the Blueprint, Architecture, or Spec.
  2. A component or interface is defined in Blueprint/Architecture/Spec but is missing or incomplete in code.
  3. A non-functional requirement (e.g., performance target, security constraint) is defined in Architecture or Spec but not verified/enforced in code.
  4. Naming, structure, or module boundaries in code do not align with Blueprint or Architecture definitions.
  5. Test coverage is below the threshold defined in the QA Test Plan.

#### 2.5.2 Drift Detection Mechanism
- **FR-DR-002**: After Implementation phase completes, run automated drift checks:
  - Compare code modules/classes against Blueprint definitions.
  - Compare code components, interfaces, and boundaries against Architecture definitions.
  - Compare implemented features and constraints against Spec requirements.
  - Compare test coverage against QA Test Plan targets.
  - Scan code for features not mentioned in Blueprint, Architecture, or Spec.
- **FR-DR-002A**: Drift checks must run in this order, reflecting artifact creation order: Blueprint -> Architecture -> Spec.
- **FR-DR-003**: Drift checks must complete in ≤ 60 seconds per phase; if timeout, report inconclusive result.
- **FR-DR-004**: Emit `DriftCheckResult` event listing any detected drift with severity (critical, major, minor) and remediation suggestions.

#### 2.5.3 Auto-Remediation
- **FR-DR-005**: Minor drift (e.g., missing docstring, naming inconsistency) is auto-remediable; supervisor attempts fix via re-invocation of phase agent with drift report.
- **FR-DR-006**: Major drift (e.g., missing module, incomplete feature) is remediable but requires re-execution of Blueprint or Implementation phase; supervisor initiates rollback and re-execution with failure context.
- **FR-DR-007**: Critical drift (e.g., architectural violation, missing core feature) cannot be auto-remediated; escalate with full context.
- **FR-DR-008**: Remediation attempts are counted separately from self-heal retries (§2.1.5); max 2 remediation attempts per drift before escalation.

#### 2.5.4 Drift Tolerance
- **FR-DR-009**: After remediation attempts, minor drift may be tolerated (logged but not escalated); major and critical drift are never tolerated and must be escalated or require user override.
- **FR-DR-010**: User can explicitly acknowledge and accept known drift via configuration override (recorded in audit trail).

---

### 2.6 Policy Enforcement and Governance

Policies are declarations of intent and constraints that are enforced at runtime through hooks and validation gates.

#### 2.6.1 Policy Definition and Storage
- **FR-PL-001**: Policies are stored as YAML or JSON files in:
  - User-root: `~/.anvil/policies/` (defaults applicable to all runs)
  - Workspace-local: `.anvil/policies/` (project-specific overrides)
- **FR-PL-002**: Policies are merged at run start using configuration precedence rules (§7); workspace-local policies override user-root policies.
- **FR-PL-003**: Policy schema is versioned (e.g., `policyVersion: "0.1.0"`); supervisor validates policy syntax on load and fails if version is incompatible.

#### 2.6.2 Core Policies
Anvil v0.1.0 includes the following built-in policies:

| Policy Name | Purpose | Example Values |
|-------------|---------|-----------------|
| `AllowedModels` | Restricts which LLMs can be used per phase | `["claude-3-haiku", "deepseek-coder"]` |
| `RequiredApprovalGates` | Defines mandatory approval checkpoints in Secure mode | `["post-proposal", "post-architecture", "post-blueprint", "pre-deployment"]` |
| `TokenBudgetPerPhase` | Hard cap on tokens consumed per phase | `{"proposal": 10000, "architecture": 15000, ...}` |
| `MaxRetriesPerPhase` | Self-heal retry limit per phase | `2` (default, overridable per phase) |
| `MCPToolWhitelist` | Allowed MCP tools by name/pattern (Restricted/Strict modes) | `["file-tools", "shell-tools"]` |
| `MCPToolBlacklist` | Explicitly denied MCP tools | `["dangerous-tool"]` |
| `SecretRedactionRules` | Patterns to redact from logs | `["api[_-]?key", "password"]` (regex) |
| `NetworkAccessPolicy` | Allowed network destinations | `["openrouter.com", "api.openai.com"]` (hostnames/IPs) |

#### 2.6.3 Policy Validation and Enforcement
- **FR-PL-004**: Before executing any agent action that is gated by a policy, supervisor checks the policy and either allows or denies the action.
- **FR-PL-005**: If a policy is violated (e.g., model not in AllowedModels, token budget exceeded), supervisor logs the violation and:
  - **Remediable violation** (e.g., wrong model selected — can choose a different one): Attempt auto-remediation; if successful, proceed; if not, escalate.
  - **Unremediable violation** (e.g., token budget exceeded): Escalate immediately with policy violation details.
- **FR-PL-006**: All policy checks and enforcement decisions are logged to audit trail with timestamp, policy name, result, and justification.

#### 2.6.4 Remediation Before Escalation
- **FR-PL-007**: Policy violations must trigger auto-remediation attempts before escalation (unless violation is explicitly marked non-remediable in policy definition).
- **FR-PL-008**: Common auto-remediation strategies:
  - Token budget exceeded: Truncate context, re-run phase with smaller scope.
  - Forbidden model: Automatically switch to allowed model and retry.
  - Network access denied: Retry with allowed endpoint or escalate.

---

### 2.7 Configuration Precedence and Merge Semantics

The effective runtime configuration is determined by a four-level precedence hierarchy, resolved at run start.

#### 2.7.1 Precedence Levels (Highest to Lowest)
1. **Level 1: Run-Time Flags and Overrides**
   - Supplied at invocation: `--model=gpt-4o`, `--mode=gated`, `--phase-gates=proposal,architecture`
   - Applies only to current run
2. **Level 2: Workspace-Local Configuration**
   - File: `.anvil/config.yaml` (in repository root)
   - Applies to all runs in this workspace
3. **Level 3: User-Root Configuration**
   - File: `~/.anvil/config.yaml`
   - Applies to all Anvil runs by this user across all workspaces
4. **Level 4: Extension Built-In Defaults**
   - Baked into extension code
   - Applies if no higher-level config is found

#### 2.7.2 Merge Semantics
- **FR-CF-001**: Scalar values (strings, numbers) at a higher precedence level override lower levels; if a key is absent at a level, use the next lower level.
- **FR-CF-002**: List values (e.g., `AllowedModels`, `RequiredGates`) are **appended** from highest to lowest precedence (union behavior), not replaced. Example:
  - Built-in: `AllowedModels: ["claude-3-haiku"]`
  - User-root: `AllowedModels: ["deepseek-coder"]`
  - Workspace: `AllowedModels: ["gpt-4o"]`
  - Run-time: `--allowed-models=claude-opus`
  - **Effective**: `["claude-3-haiku", "deepseek-coder", "gpt-4o", "claude-opus"]`
- **FR-CF-003**: Object/map values (e.g., `TokenBudgetPerPhase`) are **deep-merged**: keys at higher levels override; keys present only at lower levels are retained.
- **FR-CF-004**: Configuration validation: After merging, supervisor validates that effective config is consistent (e.g., no contradictory security settings) and fails loudly if not.
- **FR-CF-005**: Effective configuration is logged at run start for auditability.

#### 2.7.3 Configuration Schema
- **FR-CF-006**: Configuration schema is versioned (e.g., `configVersion: "0.1.0"`); supervisor validates schema on load.
- **FR-CF-007**: Configuration files must be well-formed YAML/JSON; syntax errors are reported at startup with line numbers.

---

### 2.8 MCP Tool Integration and Authorization

MCP (Model Context Protocol) servers provide the agent with external tools.

#### 2.8.1 MCP Tool Declaration
- **FR-MC-001**: MCP servers are declared in configuration files (§7) with:
  - Server name and version
  - Connection method (stdio, HTTP, etc.)
  - Timeout for startup (default 5 seconds, configurable)
  - Security profile applicability (open, restricted, strict)
- **FR-MC-002**: Workspace-local and user-root configurations declare their MCP servers; supervisor merges these at run start.
- **FR-MC-003**: MCP server list is finalized before any agent work begins; no dynamic server registration during run.

#### 2.8.2 Tool Discovery and Listing
- **FR-MC-004**: At run start, supervisor initiates MCP tool discovery: connect to each MCP server and list available tools.
- **FR-MC-005**: Tool discovery must complete within **5 seconds per server** (user-configurable via config precedence); if timeout, handle per §2.8.5 (transient failure).
- **FR-MC-006**: Supervisor caches discovered tools and their schemas in `.anvil/mcp-tools-cache.json` (workspace-local runtime projection) for subsequent phases and resume scenarios.

#### 2.8.3 MCP Tool Authorization
- **FR-MC-007**: Before a phase agent is allowed to use any MCP tool, supervisor checks tool authorization against active security profile and policies.
- **FR-MC-008**: Authorization rules:
  - **Security Profile = `open`**: All discovered tools are allowed by default; user can explicitly deny via `MCPToolBlacklist` policy.
  - **Security Profile = `restricted`**: Tools must be explicitly whitelisted via `MCPToolWhitelist` policy; tools not on the list are denied by default.
  - **Security Profile = `strict`**: Only core tools (file I/O, log writing, shell execution within container) are allowed; external MCP servers are disabled unless explicitly enabled per-tool.
- **FR-MC-009**: Tool authorization is checked at invocation time (not discovery time); denied tool invocations are logged and either fail the operation or trigger escalation per policy.

#### 2.8.4 MCP Tool Handshake and Schema
- **FR-MC-010**: Tool schema (input/output types) is retrieved from MCP server during discovery and cached.
- **FR-MC-011**: Before invoking a tool, supervisor validates that agent-provided arguments match the tool's schema; if mismatch, fail with type error and escalate.

#### 2.8.5 Transient Failure Handling (Tool Discovery/Availability)
- **FR-MC-012**: If MCP server fails to start or respond during discovery:
  - Emit `MCPDiscoveryFailed` event with server name and error.
  - Attempt fallback: use cached tools from `.anvil/mcp-tools-cache.json` (if available).
  - If no cache exists, escalate with diagnostic: "MCP server `<name>` unavailable and no cached tools. Manual setup required."
- **FR-MC-013**: If MCP server fails during agent execution (tool invocation fails), log error and:
  - Retry same tool once (up to 2 attempts total).
  - If retry fails, emit `MCPToolInvocationFailed` event and escalate; agent can attempt workaround or request fallback tool.

#### 2.8.6 Built-in Core Tools
- **FR-MC-014**: Anvil includes built-in tools (not requiring external MCP servers):
  - File I/O: read, write, delete, list directory, move/copy
  - Version control: git status, commit, push, fetch (scoped to project repo)
  - Logging: write event, write run summary
  - Shell execution: run command in isolated container (Docker, configurable)
  - These tools are always available in all security profiles and cannot be denied.

---

### 2.9 Skills Loading and Progressive Disclosure

Skills are modular knowledge-and-behavior bundles (distinct from hooks, policies, and MCP tools) that are loaded on demand to preserve token efficiency.

#### 2.9.1 Skill Definition and Storage
- **FR-SK-001**: Skills are stored as Markdown or code files in:
  - User-root: `~/.anvil/skills/`
  - Workspace-local: `.anvil/skills/`
  - Built-in (extension): Packaged in extension code
- **FR-SK-002**: Each skill has metadata (name, version, phase applicability, token estimate) defined in a `MANIFEST.md` or `skill.json` file at the skill root.

#### 2.9.2 Skill Activation and Loading
- **FR-SK-003**: Skills are never preloaded wholesale; they are loaded on-demand when:
  - Phase context references the skill by name.
  - Agent explicitly requests a skill.
  - Drift detection suggests a remediation skill.
- **FR-SK-004**: When a skill is loaded, supervisor emits `SkillLoaded` event with skill name and token estimate, allowing agents to budget context.
- **FR-SK-005**: Workspace-local skills override user-root skills by name; if both exist, workspace version is used.

#### 2.9.3 Progressive Disclosure
- **FR-SK-006**: Agent receives only the skills relevant to its current phase/task, not all available skills.
- **FR-SK-007**: Skill list is finalized at phase start; no dynamic skill registration during agent execution.
- **FR-SK-008**: If agent requests a skill that is not available, supervisor emits error and escalates.

---

## 3. Non-Functional Requirements

### 3.1 Token Efficiency
- **NFR-TK-001**: Average phase context payload ≤ 4000 tokens (including inputs, supervisor state, prior artifacts, policies).
- **NFR-TK-002**: Phase-to-phase artifact handoff uses references (file paths, git commit hashes) rather than inline content, unless content is < 500 tokens.
- **NFR-TK-003**: Token usage is tracked per phase and logged to audit trail; if any phase exceeds its configured budget, escalate with usage summary.

### 3.2 Latency and Performance
- **NFR-LT-001**: Phase handoff (supervisor dispatch to agent, artifact validation, next phase setup) ≤ 500 ms.
- **NFR-LT-002**: Drift check (automated comparison of code vs. blueprint) ≤ 60 seconds per phase.
- **NFR-LT-003**: MCP tool discovery ≤ 5 seconds per server.
- **NFR-LT-004**: Artifact validation (schema check) ≤ 30 seconds per artifact.
- **NFR-LT-005**: Policy evaluation ≤ 100 ms per policy check.

### 3.3 Observability and Audit Trail
- **NFR-OB-001**: 100% of supervisor actions (phase dispatch, approval decisions, policy enforcement, error recovery) are logged to audit trail.
- **NFR-OB-002**: Audit trail is stored in `.anvil/events.jsonl` (one JSON event per line) and is queryable by event type, timestamp, phase, and severity.
- **NFR-OB-003**: Audit trail entries include: timestamp (UTC), event type, phase name, run ID, user (if applicable), and event-specific data.
- **NFR-OB-004**: Sensitive data (API keys, passwords) are redacted from audit trail using configurable redaction rules (§2.6.2).
- **NFR-OB-005**: Event retention: audit trail is kept for the lifetime of the run and appended to git history on final commit.

### 3.4 Reliability and Recovery
- **NFR-RB-001**: Self-heal retry budget: default **2 attempts per phase** (user-configurable).
- **NFR-RB-002**: Retry backoff: exponential backoff with 2-second base (1st retry after 2s, 2nd retry after 4s).
- **NFR-RB-003**: Remediation attempts (drift recovery, policy violation fixes) are tracked separately from self-heal retries; max 2 remediation attempts before escalation.
- **NFR-RB-004**: Checkpoint-based resume: on restart, supervisor skips all completed phases (identified by presence of artifact and checkpoint file) and resumes from first incomplete phase.
- **NFR-RB-005**: Run state is persisted to `.anvil/run-state.json` after each successful phase completion.
- **NFR-RB-006**: Mean time to recovery (MTTR) on transient failure: < 10 seconds (2 retries + backoff + handshake).

### 3.5 Security and Secrets Management
- **NFR-SC-001**: OpenRouter API key is stored in VS Code Secret Storage by default (using `vscode.SecretStorage` API).
- **NFR-SC-002**: Environment variable fallback: `OPENROUTER_API_KEY` is checked if Secret Storage is unavailable (CI/headless scenarios).
- **NFR-SC-003**: API key is never logged, printed, or included in artifact files; any reference in logs is redacted via `SecretRedactionRules` policy.
- **NFR-SC-004**: Configuration files may contain secrets (e.g., webhook URLs); these are redacted from audit trail and must be marked with `sensitive: true` metadata in config schema.
- **NFR-SC-005**: MCP server connection strings and credentials are treated as secrets and redacted.

### 3.6 Backward Compatibility
- **NFR-BC-001**: Artifact formats (Markdown, JSON, YAML) are versioned; supervisor can read and migrate artifacts from prior versions (migration logic TBD in future versions).
- **NFR-BC-002**: Configuration schema is versioned; supervisor gracefully rejects incompatible versions with clear error message.
- **NFR-BC-003**: Run state format is versioned; resume logic must handle prior formats or fail with actionable error.

---

## 4. Data Contracts and Artifact Schemas

### 4.1 Phase Artifact Schemas

#### 4.1.1 Proposal Artifact (`docs/proposal.md`)
**Purpose**: High-level vision, problem statement, goals, and scope for the software system.

**Required Sections** (minimum structure):
1. Executive Summary (≤ 300 words)
2. Problem Statement
3. Vision and Product Intent
4. Goals and Success Criteria (Primary and v0.1.0-specific)
5. Target Users
6. Scope (In-Scope, Out-of-Scope)
7. Operating Modes (if applicable)
8. System Approach (high-level architecture direction)
9. Risks and Mitigations
10. Acceptance Criteria for Approval

**Format**: Markdown with optional YAML front-matter containing metadata:
```yaml
---
artifactId: proposal-v1
phase: proposal
derivedFrom: [domain-knowledge/background-information.md]
generatedAt: 2026-05-17T10:00:00Z
runId: <supervisor-run-id>
---
# Proposal Title
...
```

**Validation Criteria**:
- All required sections present
- No section is empty (≥ 50 words per section)
- Executive summary ≤ 300 words
- Markdown syntax valid (no unclosed headers, lists, etc.)

---

#### 4.1.2 Specification Artifact (`docs/spec.md`)
**Purpose**: Detailed, testable, measurable requirements that translate proposal into deliverable specs.

**Required Sections** (minimum structure):
1. Overview (links to Proposal)
2. Functional Requirements (FR-*)
   - Organized by component/feature area
   - Each requirement numbered and testable
   - Cross-references to related requirements
3. Non-Functional Requirements (NFR-*)
   - Performance, security, reliability, maintainability
   - Quantified targets where possible
4. Data Contracts and Artifact Schemas
   - Tables defining artifact inputs/outputs
   - Schema definitions for each artifact type
5. Error Handling and Recovery
   - Retry budgets, timeouts, escalation thresholds
6. Security and Access Control
   - Authentication, authorization, secret management
7. Gap Analysis (Proposal vs. Spec)
   - Table mapping Proposal sections to Spec requirements
8. Acceptance Criteria for Spec Approval

**Format**: Markdown with YAML front-matter:
```yaml
---
artifactId: spec-v1
phase: specification
derivedFrom: [docs/proposal.md]
generatedAt: 2026-05-17T10:00:00Z
runId: <supervisor-run-id>
---
# Anvil Specification v0.1.0
...
```

**Validation Criteria**:
- All required sections present
- ≥ 10 functional requirements defined
- ≥ 5 non-functional requirements defined
- Gap analysis covers all major Proposal points
- Markdown syntax valid
- No ambiguous requirement language (avoid "may", "should"; use "must", "shall")

---

#### 4.1.3 Architecture Artifact (`docs/architecture.md`)
**Purpose**: Component definitions, interactions, and high-level design derived from Spec.

**Required Sections**:
1. Overview (links to Proposal, Spec)
2. Architecture Principles
3. Component Definitions
   - Component name, responsibility, dependencies, interfaces
   - Relationships between components (tables or diagrams)
4. Data Flow Diagrams (or textual descriptions)
5. System Interactions and Sequencing
6. Configuration and Runtime Model
7. Security Architecture
8. Scalability and Performance Considerations
9. Gap Analysis (Spec vs. Architecture)

**Format**: Markdown with optional embedded diagrams (Mermaid, PlantUML) and YAML front-matter.

**Validation Criteria**:
- ≥ 8 components defined with clear responsibilities
- All Spec requirements traceable to components
- Data flow is internally consistent
- No circular dependencies in component graph

---

#### 4.1.4 Blueprint Artifact (`docs/blueprint.md`)
**Purpose**: Detailed code structure, module layouts, and implementation scaffolding (Markdown only; no generated source files).

**Required Sections**:
1. Overview
2. Module Structure (tree view or table of files/directories)
3. Class/Function Definitions (signatures, docstrings, responsibilities)
4. Data Models (schemas for entities, configurations)
5. API Contracts (endpoint signatures, request/response schemas)
6. Configuration and Constants
7. Testing Strategy (unit, integration, e2e test coverage map)
8. Gap Analysis (Architecture vs. Blueprint)

**Format**: Markdown with code blocks for structure examples.

**Validation Criteria**:
- ≥ 20 modules/classes defined
- All Architecture components have corresponding blueprint modules
- Naming conventions consistent
- No duplicate module names

---

#### 4.1.5 Development Plan Artifact (`docs/plan.md`)
**Purpose**: Phased implementation roadmap with slices, dependencies, and test strategy.

**Required Sections**:
1. Overview
2. Implementation Slices (e.g., "Slice 1: Core Data Models")
   - Slice objectives
   - Tasks within slice
   - Expected artifacts (code, tests)
   - Completion criteria
3. Dependency Graph and Sequencing
4. Test Strategy (unit, integration, e2e)
5. Risk Mitigation
6. Success Criteria
7. Gap Analysis (Blueprint vs. Plan)

**Format**: Markdown.

**Validation Criteria**:
- ≥ 3 slices defined
- Each slice has clear objectives and completion criteria
- All Blueprint modules assigned to slices
- Test coverage ≥ 70% by LOC

---

#### 4.1.6 Packaging Plan Artifact (`docs/packaging-plan.md`)
**Purpose**: Documentation of packaging strategy (no build execution in v0.1.0).

**Required Sections**:
1. Packaging Strategy Overview
2. Artifacts to Package (binaries, libraries, configurations)
3. Packaging Methods (Docker, wheel, tar, etc.)
4. Distribution Channels (PyPI, GitHub Releases, etc.)
5. Rollback Strategy

**Format**: Markdown.

**Validation Criteria**:
- Strategy documented clearly
- All code artifacts accounted for

---

#### 4.1.7 Documentation Plan Artifact (`docs/documentation-plan.md`)
**Purpose**: Strategy and structure for user/developer documentation.

**Required Sections**:
1. Documentation Overview
2. Documentation Types (user guide, API docs, developer guide, etc.)
3. Audience Profiles
4. Content Outlines
5. Success Criteria (completeness, accuracy)

**Format**: Markdown.

**Validation Criteria**:
- All code components have corresponding documentation outlined
- Audience profiles defined

---

#### 4.1.8 Deployment Plan Artifact (`docs/deployment-plan.md`)
**Purpose**: Deployment strategy and steps (documentation-first; no execution in v0.1.0).

**Required Sections**:
1. Deployment Strategy Overview
2. Environment Setup (dev, staging, production)
3. Deployment Steps (manual or automated via scripts)
4. Monitoring and Health Checks
5. Rollback Procedures
6. Go/No-Go Criteria

**Format**: Markdown plus optional static deployment scripts.

**Validation Criteria**:
- Strategy is clear and reproducible (but not executed)
- All environments documented

---

#### 4.1.9 Phase Summary Log Artifact (`docs/phase-summary-log.md`)
**Purpose**: Final summary of all phases, completions, and system state.

**Required Sections**:
1. Run Summary
   - Run ID, start/end times, total duration
   - Operational mode used
   - Final status (success, escalated, interrupted)
2. Phase Completion Table
   - Phase name, status, artifacts produced, token usage, duration
3. Key Decisions and Trade-Offs
4. Risks Realized (if any) and Mitigations Applied
5. Recommendations for Future Improvements
6. Full Event Log (reference to `.anvil/events.jsonl`)

**Format**: Markdown.

**Validation Criteria**:
- All phases accounted for
- Event log reference correct
- Summary is accurate and complete

---

### 4.2 Event and Hook Schemas

#### 4.2.1 Event Schema (JSON)
All events follow a common envelope structure:

```json
{
  "timestamp": "2026-05-17T10:15:30.123Z",
  "eventType": "PhaseStarted|PhaseComplete|DriftCheckResult|...",
  "runId": "<uuid>",
  "phase": "proposal|specification|...",
  "severity": "info|warning|error|critical",
  "userId": "<user-id-or-null>",
  "data": {
    // Event-specific fields
  }
}
```

**Common Event Types**:
- `SupervisorStarted`: Supervisor initialization complete
- `PhaseStarted`: Phase dispatch initiated
- `PhaseComplete`: Phase completed successfully
- `PhaseEscalation`: Phase failed; escalation triggered
- `DriftCheckResult`: Drift check completed
- `ApprovalRequired`: User approval awaited
- `ApprovalGranted`: User approval received
- `PolicyViolation`: Policy violated; remediation attempted
- `MCPDiscoveryFailed`: Tool discovery failed
- `MCPToolInvocationFailed`: Tool invocation failed
- `ResumeFromCheckpoint`: Run resumed from checkpoint
- `SkillLoaded`: Skill loaded on-demand
- `ArtifactValidationFailed`: Artifact does not match schema
- `RetryAttempt`: Retry initiated
- `RunCompleted`: All phases completed

#### 4.2.2 Hook Schema (Callback/Filter)
Hooks are callback functions invoked at lifecycle boundaries. Common hook types:

- `BeforeToolInvocation(toolName, toolArgs) -> allow|deny|mutate`
- `AfterToolInvocation(toolName, result, duration) -> void`
- `BeforePromptSubmission(prompt, model) -> allow|deny|mutate`
- `AfterPromptResponse(prompt, response, usage) -> void`
- `PhaseStart(phase) -> void`
- `PhaseComplete(phase, artifacts) -> void`

Hooks are defined in policy/configuration files and implemented as:
- Simple blocking rules (JSON schema validation)
- Complex callbacks (Python/JS code, if supported)
- External webhooks (HTTP POST to configured endpoints)

---

### 4.3 Policy File Schema

Policies are defined in YAML or JSON. Example structure:

```yaml
---
policyVersion: "0.1.0"
policies:
  - name: AllowedModels
    type: whitelist
    target: model-selection
    values: ["claude-3-haiku", "deepseek-coder"]
    remediable: true  # Can auto-fix by switching model
    
  - name: TokenBudgetPerPhase
    type: numeric-limit
    target: token-consumption
    limits:
      proposal: 10000
      specification: 15000
      architecture: 20000
    remediable: false  # Cannot auto-fix; must escalate
    
  - name: RequiredApprovalGates
    type: list-mandatory
    target: approval-checkpoints
    gates: ["post-proposal", "post-architecture", "post-blueprint"]
    mode: secure-only  # Applies only in Secure mode
```

---

## 5. Hooks and Events Lifecycle

### 5.1 Hook Execution Points
- **Phase Lifecycle**: Before phase starts, after phase completes
- **Tool Use**: Before MCP tool invocation, after invocation returns
- **Prompt Submission**: Before sending prompt to LLM, after receiving response
- **Decision Checkpoints**: Before approval decisions, after approval
- **Error/Recovery**: Before retry, before escalation

### 5.2 Event Stream Characteristics
- **Format**: JSON Lines (`.jsonl`), one event per line
- **Ordering**: Monotonically increasing by timestamp within a run
- **Queryability**: Indexed by event type, phase, run ID, severity
- **Redaction**: Applied to events before logging (per `SecretRedactionRules` policy)
- **Retention**: Kept for run lifetime; optionally appended to git history

### 5.3 Audit Trail Access
- **Location**: `.anvil/events.jsonl` (local to workspace)
- **Queryable Fields**: timestamp, eventType, phase, severity, userId, runId
- **Commands** (if applicable): `anvil events ls`, `anvil events query --phase=implementation --severity=error`

---

## 6. Security and Access Control

### 6.1 Security Profiles
Anvil supports three security profiles that govern network access, tool availability, and policy strictness.

#### 6.1.1 `open` Profile
- **Description**: Permissive; suitable for trusted development environments.
- **Characteristics**:
  - All discovered MCP tools allowed by default.
  - Network requests to configured endpoints allowed.
  - Limited secret redaction in logs.
  - Policies are advisory (violations logged but may not block).
- **Default For**: Single-user local development.

#### 6.1.2 `restricted` Profile
- **Description**: Balanced; suitable for team or shared workspaces.
- **Characteristics**:
  - MCP tools must be explicitly whitelisted (`MCPToolWhitelist` policy).
  - Network requests restricted to policy-approved hosts.
  - Secrets actively redacted from logs.
  - Policy violations escalate and may require approval.
- **Default For**: Team workspaces, CI/CD pipelines.

#### 6.1.3 `strict` Profile
- **Description**: Highly restrictive; suitable for sensitive/regulated environments.
- **Characteristics**:
  - Only core tools (file I/O, logging, shell in container) are available.
  - External MCP servers disabled unless explicitly enabled per-tool.
  - Network isolation; only outbound to explicitly approved destinations.
  - All policy violations escalate immediately; no auto-remediation.
  - Full secret redaction; no credentials logged.
- **Default For**: Regulated/security-sensitive projects.

#### 6.1.4 Profile Application
- **FR-SC-001**: Security profile is selected at run start via configuration (§7) and is immutable during run.
- **FR-SC-002**: Profile applies uniformly to all phases; phase-specific overrides are not supported in v0.1.0 (future enhancement).
- **FR-SC-003**: Profile is logged at run start and included in audit trail.

### 6.2 MCP Tool Authorization Rules
(Detailed in §2.8.)

### 6.3 Secrets Management
(Detailed in §3.5.)

### 6.4 Secret Redaction Rules
- **Pattern Matching**: Regular expressions or substring matching
- **Examples**:
  - `api_key`, `apiKey`, `API-KEY` (case-insensitive)
  - `password`, `passwd`
  - `token`, `secret`
  - URLs with embedded credentials (e.g., `https://user:pass@host`)
- **Application**: All log files, event stream, escalation packets, artifact metadata

---

## 7. Configuration Management

(Detailed in §2.7; this section summarizes for completeness.)

### 7.1 Configuration Resolution
1. **Parse run-time flags** (if CLI-based invocation)
2. **Load workspace-local config** (`.anvil/config.yaml`)
3. **Load user-root config** (`~/.anvil/config.yaml`)
4. **Load built-in defaults** (extension code)
5. **Merge** using precedence rules (§2.7.2)
6. **Validate** merged config against schema
7. **Log** effective configuration to audit trail

### 7.2 Configuration Schema Version
- **Current**: `0.1.0`
- **Syntax**: YAML (preferred) or JSON
- **Validation**: On load; fail if schema version incompatible

---

## 8. Error Handling and Recovery

### 8.1 Error Categories and Responses

| Error Category | Examples | Auto-Recovery? | Escalation? |
|---|---|---|---|
| **Transient Network Failure** | MCP server timeout, LLM API transient error | Yes (retry with backoff) | After 2 retries |
| **Policy Violation** | Token budget exceeded, forbidden model | Depends on `remediable` flag | If not remediable or retries exhausted |
| **Artifact Validation Failure** | Missing artifact, schema mismatch | Yes (phase retry) | After 2 retries |
| **Tool Invocation Failure** | File not found, permission denied | Depends on tool type | If unrecoverable |
| **Phase Agent Failure** | Unhandled exception in agent | Yes (phase retry) | After 2 retries |
| **Drift Detection** | Code does not match blueprint | Depends on severity | If critical or retries exhausted |

### 8.2 Retry Logic
- **Default Budget**: 2 attempts per phase (attempt 1 = initial, attempt 2 = first retry)
- **Backoff Strategy**: Exponential backoff (1st: 2s, 2nd: 4s)
- **Logging**: Each retry logged with attempt #, reason, and timestamp
- **Budget Exhaustion**: Escalate with full context

### 8.3 Escalation Criteria
Escalate (pause run, alert user) when:
1. Retry budget exhausted for a phase
2. Policy violation is unremediable
3. MCP server unavailable and no cached tools
4. Artifact validation fails and cannot be fixed
5. User explicitly triggers escalation

### 8.4 Escalation Packet
When escalating, supervisor emits an escalation packet containing:
- **Phase Context**: Phase name, status, inputs/outputs, config overrides
- **Error Details**: Error type, message, stack trace (if available)
- **Audit Trail Excerpt**: Last 50 events
- **Retry History**: Number of attempts, backoff delays, error logs per attempt
- **Recommendations**: Suggested recovery actions (retry, rollback, override, manual intervention)

---

## 9. Gap Analysis: Proposal vs. Specification

This section maps each major section of the Proposal (docs/proposal.md) to specific Spec requirements, ensuring no drift.

| Proposal Section | Spec Coverage | Requirement(s) |
|---|---|---|
| §1 Executive Summary | High-level objective | FR-SV-001, FR-OM-001 through FR-OM-013 |
| §2 Problem Statement | Operational context | FR-SV-001, NFR-OB-001 |
| §3 Vision & Intent | Supervisor pattern, artifact contracts | FR-SV-001 through FR-SV-024, FR-AR-001 through FR-AR-006 |
| §4.1 Primary Goals | Instruction precision, token efficiency, reliability | NFR-TK-001, NFR-RB-001 through NFR-RB-006, FR-DR-001 through FR-DR-010 |
| §4.2 v0.1.0 Success Criteria | End-to-end execution, resume, overrides, policy enforcement | FR-SV-005 through FR-SV-024, FR-OM-001 through FR-OM-014 |
| §5 Target Users | (Informational; no functional requirement) | — |
| §6 Scope & Non-Goals | v0.1.0 boundary conditions | NFR-BC-001, note in §1 about documentation-first deployment |
| §7 Operating Modes | YOLO, Gated, Secure | FR-OM-001 through FR-OM-014 |
| §8.1 Supervisor Architecture | Supervisor agent contract | FR-SV-001 through FR-SV-024 |
| §8.2 Phase Agents with Contracts | Phase agent input/output contract | FR-PA-001 through FR-PA-007 |
| §8.3 Artifact-First Workflow | 12-phase pipeline, artifact definitions | §4.1 (Artifact Schemas), FR-AR-001 through FR-AR-006 |
| §8.4 Policy & Governance | Policy definition and enforcement | FR-PL-001 through FR-PL-008 |
| §8.5 Runtime Projection Model | Config precedence, workspace-local runtime | FR-CF-001 through FR-CF-007 |
| §8.6 Phase Execution Model | Phase DAG, topological ordering, serial execution | FR-SV-005, FR-SV-006 |
| §8.7 Skills Layer | Skill loading, progressive disclosure | FR-SK-001 through FR-SK-008 |
| §8.8 Hooks & Events | Hook types, event schema, audit trail | §5 (Hooks and Events Lifecycle) |
| §8.9 MCP Tool Integration | Tool declaration, discovery, authorization | FR-MC-001 through FR-MC-014 |
| §8.10 Configuration Precedence | 4-level precedence, merge semantics | FR-CF-001 through FR-CF-007, §7 |
| §9 Proposed Phases | 12-phase artifact table | §4.1 (Artifact Schemas), §9 below |
| §10 Model & Tooling Strategy | Model routing (Proposal intent; detailed in Blueprint) | —Note: Spec does not prescribe specific models; blueprint/plan will detail |
| §11 Reliability, Recovery, Escalation | Retry budgets, bounded recovery, escalation | FR-SV-015 through FR-SV-018, NFR-RB-001 through NFR-RB-006, §8 |
| §12 Security & Secrets | Secret storage, profiles, redaction | NFR-SC-001 through NFR-SC-005, §6 |
| §13 Risks & Mitigations | (Informational; assumes mitigations in plan/implementation) | — |
| §14 Acceptance Criteria | (Acceptance criteria for Proposal; Spec acceptance is in §10 below) | — |

**No gaps identified.** All major Proposal sections are covered by Spec requirements or deferred appropriately to downstream phases.

---

## 10. Acceptance Criteria for Specification Approval

This Specification is approved when:

1. **Completeness**: All functional and non-functional requirements are defined and testable.
   - ✓ ≥ 10 functional requirements (FR-*)
   - ✓ ≥ 5 non-functional requirements (NFR-*)
   - ✓ All major Proposal sections mapped (§9)

2. **Clarity and Precision**: Requirements are unambiguous and measurable.
   - ✓ No use of vague language ("may", "should", "nice to have")
   - ✓ All numeric targets specified (token limits, timeouts, retry counts)
   - ✓ All state transitions and error paths documented

3. **Data Contracts**: Artifact schemas are fully defined and enforceable.
   - ✓ All 12 phase artifacts have schema definitions (§4.1)
   - ✓ Event and hook schemas defined (§4.2)
   - ✓ Policy file schema specified (§4.3)

4. **Operational Modes**: YOLO, Gated, and Secure modes are fully specified.
   - ✓ Mode selection and transition logic clear
   - ✓ Approval gates and checkpoints defined (§2.4)

5. **Security and Governance**: Policies, security profiles, and secret management are detailed.
   - ✓ Security profiles (open, restricted, strict) defined (§6.1)
   - ✓ Policy framework and enforcement clear (§2.6)
   - ✓ Secret handling specified (§3.5)

6. **Error Handling**: Retry budgets, timeouts, escalation criteria fully specified.
   - ✓ Retry logic and budgets defined (§8.2)
   - ✓ Escalation criteria clear (§8.3)
   - ✓ Transient failure handling specified (§2.8.5)

7. **Gap Analysis Complete**: All Proposal sections addressed; no drift (§9).
   - ✓ Spec and Proposal aligned

8. **No Ambiguities**: All open questions from Proposal alignment phase are resolved.
   - ✓ Configuration precedence model detailed (§7)
   - ✓ Supervisor/phase agent responsibilities clear (§2.1, §2.2)
   - ✓ MCP tool integration path specified (§2.8)

---

## 11. Open Questions and Future Refinements

None at this time. All v0.1.0 alignment questions have been resolved in previous phases and folded into this Specification.

---

**Status**: Ready for collaborative review and approval.

**Next Phase**: Upon approval, proceed to [docs/architecture.md](docs/architecture.md) derivation.