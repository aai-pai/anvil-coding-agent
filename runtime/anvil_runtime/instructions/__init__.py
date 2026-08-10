"""Standing-instructions resolution (v0.1.2 #14)."""

from anvil_runtime.instructions.resolver import (
    INSTRUCTIONS_FILENAME,
    MAX_INSTRUCTIONS_CHARS,
    RUN_LEVEL_REL,
    ResolvedInstructions,
    resolve_instructions,
)

__all__ = [
    "INSTRUCTIONS_FILENAME",
    "MAX_INSTRUCTIONS_CHARS",
    "RUN_LEVEL_REL",
    "ResolvedInstructions",
    "resolve_instructions",
]
