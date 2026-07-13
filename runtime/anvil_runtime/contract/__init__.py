"""Task-contract channel: the contract/context split (#20) and the
``contract-manifest`` mechanical check (#21). See ``resolver.py`` for the
transport design and ``manifest.py`` for the validation design.
"""

from anvil_runtime.contract.manifest import (
    MANIFEST_FENCE,
    ContractManifest,
    ManifestSymbol,
    parse_contract_manifest,
    validate_manifest,
)
from anvil_runtime.contract.resolver import (
    CONTRACT_MARKER,
    CONTRACT_PREAMBLE,
    CONTEXT_MARKER,
    DOMAIN_KNOWLEDGE_REL,
    ContractSplit,
    ResolvedContract,
    append_block,
    resolve_contract,
    split_contract,
)

__all__ = [
    "CONTRACT_MARKER",
    "CONTEXT_MARKER",
    "CONTRACT_PREAMBLE",
    "DOMAIN_KNOWLEDGE_REL",
    "ContractSplit",
    "ResolvedContract",
    "split_contract",
    "resolve_contract",
    "append_block",
    "MANIFEST_FENCE",
    "ManifestSymbol",
    "ContractManifest",
    "parse_contract_manifest",
    "validate_manifest",
]
