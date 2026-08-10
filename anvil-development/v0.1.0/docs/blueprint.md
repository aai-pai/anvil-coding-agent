---
artifactId: blueprint-v1
phase: blueprint
derivedFrom:
  - docs/proposal.md
  - docs/spec.md
  - docs/architecture.md
inputHashes:
  docs/proposal.md: 1aa139f744458770f2ce8be24e10d9eb1aafb9e941cb27425a3bbcfc99a75bb9
  docs/spec.md: 6c01b6a168a26986fc4853b8a123f8f0ca3a80748da143ac58cd7bab80d6c428
  docs/architecture.md: a87bc5ed586c607815be089c04eef7c88dfa7820fabb6bf647766b41465c182e
generatedAt: 2026-05-31T00:00:00Z
runId: manual-draft-2026-05-31
---

# Anvil Blueprint (v0.1.0)

## 1. Overview

This blueprint converts the approved architecture into implementation-ready module boundaries, data contracts, and test scaffolding for Anvil v0.1.0. It remains Markdown-only and intentionally does not generate source files in this phase.

Implementation approach:
- Split the system into two deployable parts: a VS Code extension client (TypeScript) and a localhost runtime service (Python/FastAPI).
- Keep supervisor logic and phase execution in the Python runtime.
- Keep UI/chat participant and secret-storage bridge in the extension.
- Use stable API contracts between extension and runtime to preserve transport and language decoupling.
- Enforce single-writer ownership and phase contracts in runtime services, not in UI code.

## 2. Module Structure

### 2.1 Proposed Repository Tree

```text
.
├── docs/
│   ├── proposal.md
│   ├── spec.md
│   ├── architecture.md
│   ├── blueprint.md
│   └── plan.md
├── extension/
│   ├── package.json
│   ├── tsconfig.json
│   └── src/
│       ├── extension.ts
│       ├── chat/
│       │   ├── participant.ts
│       │   ├── commandRouter.ts
│       │   └── responseRenderer.ts
│       ├── runtime/
│       │   ├── runtimeClient.ts
│       │   ├── eventStreamClient.ts
│       │   └── healthProbe.ts
│       ├── ui/
│       │   ├── statusBar.ts
│       │   ├── approvals.ts
│       │   └── escalationPrompt.ts
│       ├── secrets/
│       │   ├── secretStore.ts
│       │   └── redactionClient.ts
│       ├── config/
│       │   ├── workspaceConfig.ts
│       │   └── modeSelector.ts
│       └── telemetry/
│           ├── extensionLogger.ts
│           └── eventMapper.ts
├── runtime/
│   ├── pyproject.toml
│   └── anvil_runtime/
│       ├── __init__.py
│       ├── app.py
│       ├── api/
│       │   ├── deps.py
│       │   ├── models.py
│       │   ├── routes_runs.py
│       │   ├── routes_artifacts.py
│       │   ├── routes_health.py
│       │   └── routes_events.py
│       ├── core/
│       │   ├── development_manager.py
│       │   ├── phase_dag.py
│       │   ├── phase_registry.py
│       │   ├── phase_contracts.py
│       │   ├── retry_controller.py
│       │   └── escalation_service.py
│       ├── agents/
│       │   ├── base_phase_agent.py
│       │   ├── factory.py
│       │   ├── specialist_registry.py
│       │   ├── phase_invocation.py
│       │   └── phases/
│       │       ├── proposal_agent.py
│       │       ├── factory_init_agent.py
│       │       ├── specification_agent.py
│       │       ├── architecture_agent.py
│       │       ├── blueprint_agent.py
│       │       ├── dev_plan_agent.py
│       │       ├── implementation_agent.py
│       │       ├── qa_agent.py
│       │       ├── packaging_agent.py
│       │       ├── documentation_agent.py
│       │       ├── deployment_agent.py
│       │       └── cleanup_agent.py
│       ├── config/
│       │   ├── loader.py
│       │   ├── merger.py
│       │   ├── validator.py
│       │   ├── projection.py
│       │   └── schema.py
│       ├── policy/
│       │   ├── engine.py
│       │   ├── models.py
│       │   ├── remediation.py
│       │   └── rule_evaluator.py
│       ├── hooks/
│       │   ├── adapter.py
│       │   ├── compiler.py
│       │   └── lifecycle_hooks.py
│       ├── artifacts/
│       │   ├── validator.py
│       │   ├── schemas.py
│       │   └── metadata.py
│       ├── drift/
│       │   ├── checker.py
│       │   ├── classifier.py
│       │   └── remediation.py
│       ├── state/
│       │   ├── event_bus.py
│       │   ├── checkpoint_store.py
│       │   └── run_summary.py
│       ├── tools/
│       │   ├── mcp_manager.py
│       │   ├── mcp_cache.py
│       │   ├── core_tools.py
│       │   └── tool_authorizer.py
│       ├── skills/
│       │   ├── loader.py
│       │   ├── resolver.py
│       │   └── manifest.py
│       ├── llm/
│       │   ├── openrouter_provider.py
│       │   ├── model_router.py
│       │   └── usage_tracker.py
│       ├── sdk/
│       │   ├── openhands_adapter.py
│       │   └── session_bridge.py
│       └── security/
│           ├── secret_adapter.py
│           └── redaction.py
└── tests/
    ├── unit/
    │   ├── runtime/
    │   └── extension/
    ├── integration/
    │   ├── api/
    │   ├── phase_flow/
    │   └── policy/
    └── e2e/
        ├── secure_mode_run/
        ├── checkpoint_resume/
        └── drift_remediation/
```

### 2.2 Architecture Component to Module Mapping

| Architecture Component | Primary Module(s) | Notes |
|---|---|---|
| VS Code Chat Participant | `extension/src/chat/participant.ts`, `extension/src/chat/commandRouter.ts` | User-facing interface and command parsing |
| Anvil Runtime API | `runtime/anvil_runtime/app.py`, `runtime/anvil_runtime/api/routes_*.py` | Versioned REST + SSE |
| Development Manager | `runtime/anvil_runtime/core/development_manager.py` | Supervisor state machine and orchestration |
| Phase Agent Framework | `runtime/anvil_runtime/agents/base_phase_agent.py`, `runtime/anvil_runtime/agents/factory.py` | Contract-driven phase invocation |
| Specialist Role Registry | `runtime/anvil_runtime/agents/specialist_registry.py` | Role loading/validation/invocation |
| Configuration Resolver | `runtime/anvil_runtime/config/loader.py`, `runtime/anvil_runtime/config/merger.py` | 4-level precedence merge |
| Runtime Projection Layer | `runtime/anvil_runtime/config/projection.py` | Writes effective runtime files |
| Secret Storage Adapter | `extension/src/secrets/secretStore.ts`, `runtime/anvil_runtime/security/secret_adapter.py` | Extension storage + runtime fallback |
| Policy Engine | `runtime/anvil_runtime/policy/engine.py` | Enforce policy checks and remediation |
| Hook Layer | `runtime/anvil_runtime/hooks/adapter.py`, `runtime/anvil_runtime/hooks/compiler.py` | Lifecycle enforcement hooks |
| Artifact Validator | `runtime/anvil_runtime/artifacts/validator.py` | Deterministic artifact validation |
| Drift Checker | `runtime/anvil_runtime/drift/checker.py` | Blueprint/architecture/spec drift detection |
| Event Bus / Audit Trail | `runtime/anvil_runtime/state/event_bus.py`, `runtime/anvil_runtime/state/run_summary.py` | JSONL events + summary log |
| Checkpoint and Resume Store | `runtime/anvil_runtime/state/checkpoint_store.py` | Save/load/validate run state |
| MCP Integration Layer | `runtime/anvil_runtime/tools/mcp_manager.py`, `tool_authorizer.py` | Discovery, auth, invocation |
| Skills Loader | `runtime/anvil_runtime/skills/loader.py`, `resolver.py` | Progressive disclosure |
| OpenRouter Provider | `runtime/anvil_runtime/llm/openrouter_provider.py`, `model_router.py` | Hybrid route per phase+subtask |
| OpenHands SDK Adapter | `runtime/anvil_runtime/sdk/openhands_adapter.py` | Session and tool bridge |

## 3. Class/Function Definitions

The following signatures are normative scaffolding for implementation.

### 3.1 Runtime Core (Python)

```python
# runtime/anvil_runtime/core/development_manager.py
class DevelopmentManager:
    """Coordinates phase lifecycle, approvals, retries, drift checks, and resume."""

    def start_run(self, request: "RunStartRequest") -> "RunStarted": ...
    def resume_run(self, run_id: str) -> "ResumePlan": ...
    def dispatch_phase(self, run_id: str, phase_id: str) -> "PhaseDispatchResult": ...
    def await_approval(self, run_id: str, gate_id: str, gate_name: str) -> "ApprovalDecision": ...
    def apply_override(self, run_id: str, override: "OverrideRequest") -> "OverrideResult": ...
    def rollback(self, run_id: str, target_phase: str, reason: str) -> "RollbackPlan": ...
    def escalate(self, run_id: str, packet: "EscalationPacket") -> None: ...
```

```python
# runtime/anvil_runtime/core/phase_dag.py
class PhaseDAG:
    """Defines phase dependencies and validates topological ordering."""

    def ready_phases(self, completed: set[str]) -> list[str]: ...
    def validate(self) -> None: ...
```

```python
# runtime/anvil_runtime/agents/base_phase_agent.py
class BasePhaseAgent:
    """Base contract for all phase agents."""

    phase_id: str

    def run(self, payload: "PhaseInvocationPayload") -> "PhaseCompleteEvent": ...
    def allowed_outputs(self) -> list[str]: ...
```

```python
# runtime/anvil_runtime/agents/factory.py
class PhaseAgentFactory:
    """Builds agents by phase ID with policy/model/tool constraints."""

    def create(self, phase_id: str) -> BasePhaseAgent: ...
```

```python
# runtime/anvil_runtime/agents/specialist_registry.py
class SpecialistRegistry:
    """Loads, merges, validates, and dispatches specialist roles."""

    def load(self) -> "SpecialistRegistryModel": ...
    def validate_role(self, role: "SpecialistRole") -> list[str]: ...
    def invoke(self, role_id: str, context: "SpecialistInvocationContext") -> "SpecialistResult": ...
```

```python
# runtime/anvil_runtime/config/loader.py
class ConfigLoader:
    """Loads config from run flags, workspace, user root, and defaults."""

    def load_sources(self, run_flags: dict[str, object]) -> "ConfigSources": ...
```

```python
# runtime/anvil_runtime/config/merger.py
class ConfigMerger:
    """Merges config sources with scalar/list/map semantics."""

    def merge(self, sources: "ConfigSources") -> "EffectiveConfig": ...
```

```python
# runtime/anvil_runtime/config/projection.py
class RuntimeProjectionWriter:
    """Materializes effective runtime files under .openhands/, .anvil/, and logs/."""

    def write_projection(self, cfg: "EffectiveConfig") -> "ProjectionManifest": ...
```

```python
# runtime/anvil_runtime/policy/engine.py
class PolicyEngine:
    """Evaluates policy checks and orchestrates remediation before escalation."""

    def check(self, ctx: "PolicyActionContext") -> "PolicyDecision": ...
    def apply_remediation(self, violation: "PolicyViolation") -> "RemediationOutcome": ...
```

```python
# runtime/anvil_runtime/hooks/adapter.py
class HookAdapter:
    """Executes lifecycle hook callbacks and captures allow/deny/mutate outcomes."""

    def before_tool_invocation(self, tool: str, args: dict[str, object]) -> "HookDecision": ...
    def after_tool_invocation(self, tool: str, result: object, duration_ms: int) -> None: ...
    def before_prompt_submission(self, prompt: str, model: str) -> "HookDecision": ...
    def after_prompt_response(self, prompt: str, response: str, usage: "TokenUsage") -> None: ...
```

```python
# runtime/anvil_runtime/artifacts/validator.py
class ArtifactValidator:
    """Validates phase artifacts against schema and structure requirements."""

    def validate(self, phase_id: str, artifact_paths: list[str]) -> "ArtifactValidationResult": ...
```

```python
# runtime/anvil_runtime/drift/checker.py
class DriftChecker:
    """Finds and classifies blueprint/architecture/spec drift."""

    def check(self, phase_id: str, context: "DriftContext") -> "DriftReport": ...
```

```python
# runtime/anvil_runtime/state/event_bus.py
class EventBus:
    """Writes structured events to logs/events.jsonl and streams to subscribers."""

    def emit(self, event: "EventEnvelope") -> None: ...
    def stream(self, run_id: str) -> "EventStream": ...
```

```python
# runtime/anvil_runtime/state/checkpoint_store.py
class CheckpointStore:
    """Persists and validates run-state checkpoints in .anvil/run-state.json."""

    def save_phase_completion(self, run_id: str, phase: "PhaseCheckpoint") -> None: ...
    def load_run_state(self, run_id: str) -> "RunState | None": ...
    def earliest_invalid_phase(self, run_id: str) -> "str | None": ...
```

```python
# runtime/anvil_runtime/tools/mcp_manager.py
class MCPManager:
    """Discovers MCP tools, caches metadata, and executes authorized invocations."""

    def discover(self) -> "MCPDiscoveryResult": ...
    def invoke(self, request: "ToolInvocationRequest") -> "ToolInvocationResult": ...
```

```python
# runtime/anvil_runtime/skills/loader.py
class SkillLoader:
    """Loads and resolves phase-relevant skills with progressive disclosure."""

    def resolve_for_phase(self, phase_id: str) -> list["SkillRef"]: ...
    def load(self, skill_name: str) -> "SkillBundle": ...
```

```python
# runtime/anvil_runtime/llm/openrouter_provider.py
class OpenRouterProvider:
    """Submits prompts to OpenRouter using policy-approved model routing."""

    def complete(self, req: "CompletionRequest") -> "CompletionResponse": ...
```

```python
# runtime/anvil_runtime/llm/model_router.py
class ModelRouter:
    """Selects model by phase and subtask category (planning/analysis/coding/debugging/review)."""

    def route(self, phase_id: str, subtask: str) -> str: ...
```

```python
# runtime/anvil_runtime/sdk/openhands_adapter.py
class OpenHandsAdapter:
    """Bridges phase execution into OpenHands sessions and tools."""

    def start_session(self, cfg: "AgentRuntimeConfig") -> str: ...
    def run_phase_step(self, session_id: str, step: "PhaseStep") -> "StepResult": ...
```

### 3.2 Extension Layer (TypeScript)

```typescript
// extension/src/chat/participant.ts
export class AnvilChatParticipant {
  // Registers chat participant and dispatches commands to runtime client.
  async handleRequest(message: string, context: ChatContext): Promise<ChatResponse> {}
}
```

```typescript
// extension/src/runtime/runtimeClient.ts
export class RuntimeClient {
  // Typed client for localhost REST API.
  startRun(request: RunStartRequest): Promise<RunStarted> {}
  approve(runId: string, req: ApprovalRequest): Promise<void> {}
  override(runId: string, req: OverrideRequest): Promise<void> {}
  getRun(runId: string): Promise<RunStateResponse> {}
}
```

```typescript
// extension/src/runtime/eventStreamClient.ts
export class EventStreamClient {
  // Subscribes to SSE event stream and forwards updates to UI surfaces.
  subscribe(runId: string, onEvent: (e: EventEnvelope) => void): Disposable {}
}
```

```typescript
// extension/src/secrets/secretStore.ts
export class SecretStore {
  // Persists/retrieves OpenRouter API key via vscode.SecretStorage.
  async getOpenRouterKey(): Promise<string | undefined> {}
  async setOpenRouterKey(value: string): Promise<void> {}
}
```

```typescript
// extension/src/ui/approvals.ts
export async function promptApproval(gate: ApprovalGate): Promise<ApprovalRequest> {
  // Collects explicit secure-mode approvals with optional comments.
}
```

### 3.3 Module and Class Count

Defined modules in this blueprint: 60+.
Defined primary classes/functions above: 25+.
This satisfies the minimum schema requirement of at least 20 modules/classes.

## 4. Data Models

### 4.1 Core Runtime Models (Python/Pydantic)

```python
class RunStartRequest(BaseModel):
    mode: Literal["yolo", "gated", "secure"]
    security_profile: Literal["open", "restricted", "strict"]
    phase_gates: list[str] = []
    run_overrides: dict[str, object] = {}

class RunStarted(BaseModel):
    run_id: str
    started_at: datetime
    mode: str

class ApprovalRequest(BaseModel):
    gateId: str
    gateName: str
    approved: bool
    comments: str | None = None
    requesterId: str

class OverrideRequest(BaseModel):
    action: Literal["force-advance", "rollback", "stop"]
    targetPhase: str | None = None
    reason: str
    comments: str | None = None
    requesterId: str
```

```python
class PhaseInvocationPayload(BaseModel):
    phase_name: str
    input_files: list[str]
    input_schema: dict[str, object]
    output_paths: list[str]
    phase_context: dict[str, object]
    previous_phase_outputs: list[str]

class PhaseCompleteEvent(BaseModel):
    phase_name: str
    status: Literal["success", "failure"]
    artifact_paths: list[str]
    checksums: dict[str, str]
    duration_ms: int
    token_usage: dict[str, int] | None = None
    failure_reason: str | None = None
```

```python
class EventEnvelope(BaseModel):
    timestamp: datetime
    eventType: str
    runId: str
    phase: str
    severity: Literal["info", "warning", "error", "critical"]
    userId: str | None = None
    data: dict[str, object]
```

```python
class EffectiveConfig(BaseModel):
    configVersion: str
    mode: Literal["yolo", "gated", "secure"]
    allowedModels: list[str]
    tokenBudgetPerPhase: dict[str, int]
    maxRetriesPerPhase: int
    requiredApprovalGates: list[str]
    mcpServers: list[dict[str, object]]
    securityProfile: Literal["open", "restricted", "strict"]
```

```python
class RunState(BaseModel):
    runStateVersion: str
    run_id: str
    mode: str
    completed_phases: list[dict[str, object]]
    stale_phases: list[str]
    retry_counters: dict[str, int]
```

### 4.2 JSON Schemas (Stored as constants)

- `APPROVAL_REQUEST_SCHEMA`
- `OVERRIDE_REQUEST_SCHEMA`
- `EVENT_ENVELOPE_SCHEMA`
- `PHASE_COMPLETE_SCHEMA`
- `POLICY_RULE_SCHEMA`
- `SPECIALIST_ROLE_SCHEMA`

These schemas will be defined in:
- `runtime/anvil_runtime/api/models.py`
- `runtime/anvil_runtime/policy/models.py`
- `runtime/anvil_runtime/agents/specialist_registry.py`

## 5. API Contracts

### 5.1 REST Endpoints (runtime/anvil_runtime/api)

1. `POST /v1/runs`
Request:
```json
{
  "mode": "secure",
  "security_profile": "restricted",
  "phase_gates": ["proposal", "architecture"],
  "run_overrides": {
    "tokenBudgetPerPhase": {"implementation": 25000}
  }
}
```
Response:
```json
{
  "run_id": "3f4c4c0b-17e3-4b20-bf9f-bf3478ecf2d8",
  "started_at": "2026-05-31T00:00:00Z",
  "mode": "secure"
}
```

2. `GET /v1/runs/{run_id}`
Response:
```json
{
  "run_id": "3f4c4c0b-17e3-4b20-bf9f-bf3478ecf2d8",
  "status": "running",
  "current_phase": "architecture",
  "completed_phases": ["proposal", "factory-init", "specification"],
  "pending_approval_gate": "post-architecture"
}
```

3. `POST /v1/runs/{run_id}/approve`
Request uses `ApprovalRequest` model. Returns `204 No Content`.

4. `POST /v1/runs/{run_id}/override`
Request uses `OverrideRequest` model. Returns:
```json
{
  "status": "accepted",
  "action": "rollback",
  "targetPhase": "architecture"
}
```

5. `GET /v1/runs/{run_id}/events`
- Content type: `text/event-stream`
- Event payload: `EventEnvelope` JSON per message

6. `GET /v1/artifacts/{phase}`
Response:
```json
{
  "phase": "architecture",
  "path": "docs/architecture.md",
  "checksum": "a87bc5ed586c607815be089c04eef7c88dfa7820fabb6bf647766b41465c182e",
  "generatedAt": "2026-05-24T17:00:00Z"
}
```

7. `GET /v1/health`
Response:
```json
{
  "status": "ok",
  "runtime": "anvil-runtime",
  "checks": {
    "config": "ok",
    "mcp_discovery": "ok",
    "openhands": "ok"
  }
}
```

### 5.2 Internal Service Interfaces

- `DevelopmentManager.start_run(request) -> RunStarted`
- `PhaseAgentFactory.create(phase_id) -> BasePhaseAgent`
- `PolicyEngine.check(action_context) -> PolicyDecision`
- `ArtifactValidator.validate(phase_id, artifact_paths) -> ArtifactValidationResult`
- `DriftChecker.check(phase_id, context) -> DriftReport`
- `CheckpointStore.load_run_state(run_id) -> RunState | None`

## 6. Configuration and Constants

### 6.1 Configuration Files

- `~/.anvil/config.yaml` (user defaults)
- `.anvil/config.yaml` (workspace overrides)
- `.openhands/runtime/mcp.generated.json` (projection output)
- `.openhands/runtime/policy-snapshot.json` (projection output)
- `.anvil/run-state.json` (checkpoint state)
- `.anvil/mcp-tools-cache.json` (discovery cache)

### 6.2 Key Constants

Python constants module target: `runtime/anvil_runtime/config/schema.py`

```python
DEFAULT_MODE = "gated"
DEFAULT_SECURITY_PROFILE = "restricted"
DEFAULT_MAX_RETRIES_PER_PHASE = 2
DEFAULT_MCP_DISCOVERY_TIMEOUT_SECONDS = 5
DEFAULT_ARTIFACT_VALIDATION_TIMEOUT_SECONDS = 30
DEFAULT_DRIFT_CHECK_TIMEOUT_SECONDS = 60
RUNTIME_API_VERSION_PREFIX = "/v1"
EVENTS_LOG_PATH = "logs/events.jsonl"
RUN_SUMMARY_LOG_PATH = "logs/run-summary.log"
CHECKPOINT_PATH = ".anvil/run-state.json"
MANDATORY_SECURE_GATES = [
    "post-proposal",
    "post-architecture",
    "post-blueprint",
    "pre-deployment"
]
```

TypeScript constants module target: `extension/src/config/modeSelector.ts`

```typescript
export const API_BASE_URL = "http://127.0.0.1:8765";
export const DEFAULT_MODE: "yolo" | "gated" | "secure" = "gated";
export const SECURE_MANDATORY_GATES = [
  "post-proposal",
  "post-architecture",
  "post-blueprint",
  "pre-deployment"
] as const;
```

### 6.3 Naming Conventions

- Python: `snake_case` files/functions, `PascalCase` classes.
- TypeScript: `camelCase` functions/variables, `PascalCase` classes.
- Event types: `PascalCase` enumerations (`PhaseStarted`, `PolicyViolation`).
- Phase IDs: kebab-case (`factory-init`, `dev-plan`).
- Avoid duplicate module names across layers by keeping explicit domain folders (`core`, `policy`, `drift`, `state`).

## 7. Testing Strategy

### 7.1 Unit Tests

Target directory: `tests/unit/`

Coverage map:
- `tests/unit/runtime/test_config_merger.py`
- `tests/unit/runtime/test_policy_engine.py`
- `tests/unit/runtime/test_hook_adapter.py`
- `tests/unit/runtime/test_artifact_validator.py`
- `tests/unit/runtime/test_drift_checker.py`
- `tests/unit/runtime/test_checkpoint_store.py`
- `tests/unit/runtime/test_model_router.py`
- `tests/unit/runtime/test_mcp_authorization.py`
- `tests/unit/extension/test_runtime_client.ts`
- `tests/unit/extension/test_command_router.ts`

Assertions include:
- Precedence merge semantics (scalar override, list union, deep map merge).
- Secure-mode mandatory gate enforcement.
- Retry/remediation counter behavior.
- Schema validation pass/fail determinism.

### 7.2 Integration Tests

Target directory: `tests/integration/`

Coverage map:
- `tests/integration/api/test_runs_endpoints.py`
- `tests/integration/api/test_events_stream.py`
- `tests/integration/phase_flow/test_secure_gate_pause.py`
- `tests/integration/phase_flow/test_resume_with_invalid_checkpoint.py`
- `tests/integration/policy/test_forbidden_model_remediation.py`
- `tests/integration/policy/test_mcp_restricted_profile.py`

Assertions include:
- End-to-end lifecycle of `start -> phase dispatch -> approval -> next phase`.
- Escalation path after bounded retries.
- Cache fallback when MCP discovery fails.

### 7.3 End-to-End Tests

Target directory: `tests/e2e/`

Coverage map:
- `tests/e2e/secure_mode_run/test_secure_approval_journey.py`
- `tests/e2e/checkpoint_resume/test_resume_after_restart.py`
- `tests/e2e/drift_remediation/test_major_drift_rollback.py`

Assertions include:
- Full 12-phase run progression under secure mode.
- Resume from checkpoint after simulated runtime interruption.
- Drift detection order: blueprint -> architecture -> spec.

### 7.4 Test Data and Fixtures

- Fixture directory: `tests/fixtures/`
- Synthetic artifacts with controlled schema errors for validator tests.
- Event stream fixtures for SSE and log redaction tests.
- Mock MCP server stubs with timeout/failure modes.

## 8. Gap Analysis (Architecture vs. Blueprint)

| Architecture Expectation | Blueprint Coverage | Gap Status | Notes |
|---|---|---|---|
| Chat participant as primary user surface | `extension/src/chat/*` modules and signatures | Closed | Includes routing and response rendering |
| Localhost versioned runtime API with SSE | `runtime/anvil_runtime/api/*` route modules + endpoint contracts | Closed | Includes run control, events, health, artifacts |
| Supervisor-only orchestration and no artifact writing | `core/development_manager.py` and phase agent boundaries | Closed | Single-writer rules delegated to agent framework |
| 12 phase agents with explicit contracts | `agents/phases/*.py`, `phase_contracts.py` | Closed | All 12 phases named and mapped |
| Specialist role extensibility | `agents/specialist_registry.py` + model contracts | Closed | Includes registry merge and validation |
| 4-level config precedence and runtime projection | `config/loader.py`, `merger.py`, `projection.py` | Closed | Includes output files under `.openhands/` and `.anvil/` |
| Policy-driven enforcement and remediation | `policy/engine.py`, `policy/remediation.py` | Closed | Includes remediable vs non-remediable paths |
| Hooks lifecycle execution model | `hooks/adapter.py`, `hooks/compiler.py`, `hooks/lifecycle_hooks.py` | Closed | Matches allow/deny/mutate semantics |
| Deterministic artifact validation | `artifacts/validator.py`, `artifacts/schemas.py` | Closed | Deterministic pass/fail behavior |
| Drift detection and classification | `drift/checker.py`, `drift/classifier.py`, `drift/remediation.py` | Closed | Includes severity and rollback behavior |
| Structured audit trail and run summary | `state/event_bus.py`, `state/run_summary.py` | Closed | Logs and SSE stream alignment |
| Checkpoint resume with validation | `state/checkpoint_store.py` | Closed | Includes earliest invalid phase logic |
| MCP discovery/auth/cache/fallback | `tools/mcp_manager.py`, `mcp_cache.py`, `tool_authorizer.py` | Closed | Includes security profile behavior |
| Progressive skill loading | `skills/loader.py`, `skills/resolver.py`, `skills/manifest.py` | Closed | Phase-frozen skill manifest |
| Hybrid model routing via OpenRouter | `llm/openrouter_provider.py`, `llm/model_router.py`, `llm/usage_tracker.py` | Closed | Phase+subtask routing with usage tracking |
| OpenHands execution adapter | `sdk/openhands_adapter.py`, `sdk/session_bridge.py` | Closed | In-process now, transport-agnostic later |

Residual risks to carry into planning phase:
- Exact shape of OpenHands SDK callback payloads may require adapter refinements.
- Final choice of Python validation stack (`pydantic` vs stdlib dataclasses + validators) is pending implementation spike.
- Extension test runner and VS Code API mocks need final selection in implementation plan.
