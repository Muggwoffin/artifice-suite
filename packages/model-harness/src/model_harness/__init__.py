"""Shared BYOM connector contract for the Artifice Suite.

`CLAUDE.md` requires that every model interaction pass through structured
schemas in this package. Until 2026-07-29 this module was 29 lines defining a
config object and a ``SchemaT`` TypeVar that nothing used — the "schema-validated
call shape" its docstring promised did not exist, and all four apps carried
their own client.

:mod:`model_harness.contract` now defines that call shape. Transport is still
per-app; adapters implement :class:`~model_harness.contract.ModelProvider`.
Porting is tracked as Phase 3 in ``IMPLEMENTATION_PLAN.md``.
"""

from __future__ import annotations

from model_harness.contract import (
    EndpointPolicy,
    EndpointRejected,
    HarnessError,
    HarnessResult,
    ModelConnectorConfig,
    ModelProvider,
    Provider,
    ProviderCapabilities,
    RawCompletion,
    SchemaT,
    SchemaValidationFailed,
    StructuredOutputMode,
    StructuredOutputUnsupported,
    StructuredRequest,
    select_mode,
)

__all__ = [
    "EndpointPolicy",
    "EndpointRejected",
    "HarnessError",
    "HarnessResult",
    "ModelConnectorConfig",
    "ModelProvider",
    "Provider",
    "ProviderCapabilities",
    "RawCompletion",
    "SchemaT",
    "SchemaValidationFailed",
    "StructuredOutputMode",
    "StructuredOutputUnsupported",
    "StructuredRequest",
    "select_mode",
]
