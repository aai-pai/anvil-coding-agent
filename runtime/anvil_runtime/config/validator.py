"""Effective-configuration validation.

Slice 3 deliverable (spec FR-CF-004/006). After merging, validate that the
effective configuration is internally consistent and schema-compatible, failing
loudly otherwise. Field-type/literal validation is handled by the pydantic
:class:`EffectiveConfig` model; this layer adds version and cross-field
consistency checks.
"""

from __future__ import annotations

from anvil_runtime.config.schema import (
    CONFIG_VERSION,
    OPERATING_MODES,
    SECURITY_PROFILES,
    EffectiveConfig,
)


class ConfigValidationError(ValueError):
    """Raised when the effective configuration is invalid or inconsistent."""


class ConfigValidator:
    """Validates a merged :class:`EffectiveConfig`."""

    def __init__(self, supported_versions: tuple[str, ...] = (CONFIG_VERSION,)) -> None:
        self._supported_versions = supported_versions

    def validate(self, config: EffectiveConfig | dict[str, object]) -> EffectiveConfig:
        cfg = config if isinstance(config, EffectiveConfig) else EffectiveConfig.model_validate(config)
        errors: list[str] = []

        # FR-CF-006: schema version must be supported.
        if cfg.configVersion not in self._supported_versions:
            errors.append(
                f"unsupported configVersion '{cfg.configVersion}' "
                f"(supported: {', '.join(self._supported_versions)})"
            )

        # Defensive: literals are already validated by pydantic, but keep an
        # explicit consistency guard for clear error messaging.
        if cfg.mode not in OPERATING_MODES:
            errors.append(f"invalid mode '{cfg.mode}'")
        if cfg.securityProfile not in SECURITY_PROFILES:
            errors.append(f"invalid securityProfile '{cfg.securityProfile}'")

        # FR-CF-004: no contradictory settings.
        if cfg.maxRetriesPerPhase < 0:
            errors.append("maxRetriesPerPhase must be >= 0")
        for phase, budget in cfg.tokenBudgetPerPhase.items():
            if budget < 0:
                errors.append(f"tokenBudgetPerPhase['{phase}'] must be >= 0")

        if errors:
            raise ConfigValidationError("; ".join(errors))
        return cfg


__all__ = ["ConfigValidator", "ConfigValidationError"]
