// Workspace-level configuration shape for the Anvil extension.
//
// Slice 1 deliverable (blueprint §2.1, §6). This module defines the typed
// workspace config and a pure resolver that layers user overrides on top of
// defaults. Reading values from the live VS Code settings store is wired in
// Slice 4; keeping resolution pure here makes it unit-testable without the
// VS Code API.

import {
  DEFAULT_MODE,
  DEFAULT_SECURITY_PROFILE,
  normalizeMode,
  type OperatingMode,
  type SecurityProfile,
} from "./modeSelector";

export interface WorkspaceConfig {
  mode: OperatingMode;
  securityProfile: SecurityProfile;
  extraApprovalGates: string[];
}

export const DEFAULT_WORKSPACE_CONFIG: WorkspaceConfig = {
  mode: DEFAULT_MODE,
  securityProfile: DEFAULT_SECURITY_PROFILE,
  extraApprovalGates: [],
};

export interface WorkspaceConfigOverrides {
  mode?: string;
  securityProfile?: SecurityProfile;
  extraApprovalGates?: string[];
}

/** Resolve effective workspace config by applying overrides over the defaults. */
export function resolveWorkspaceConfig(
  overrides: WorkspaceConfigOverrides = {}
): WorkspaceConfig {
  return {
    mode: normalizeMode(overrides.mode),
    securityProfile:
      overrides.securityProfile ?? DEFAULT_WORKSPACE_CONFIG.securityProfile,
    extraApprovalGates:
      overrides.extraApprovalGates ?? [...DEFAULT_WORKSPACE_CONFIG.extraApprovalGates],
  };
}
