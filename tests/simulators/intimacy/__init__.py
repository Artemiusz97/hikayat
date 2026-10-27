"""
Intimate Moment & Excitement Meter Simulator Harness for Hikayat.

Provides:
- IntimacyActorAI & IntimacyAction: Blueprint-guided action selection and scenario drivers.
- IntimacyFuzzer: Multi-tier action perturbation and procedural session generator (7 partner configs).
- IntimacyInvariantAuditor & IntimacyViolation: Zero-tolerance 8-category invariant checking engine.
- IntimacySimulator, IntimacyJourneyResult, IntimacySimulationReport: Orchestration engine and telemetry aggregator.
"""
from .actor_ai import (
    IntimacyActorAI,
    IntimacyAction,
    SUPPORTED_SCENARIOS,
)
from .fuzzer import (
    IntimacyFuzzer,
    SUPPORTED_PARTNER_CONFIGS,
    SUPPORTED_FUZZ_MODES,
)
from .auditor import (
    IntimacyInvariantAuditor,
    IntimacyViolation,
)
from .engine import (
    IntimacySimulator,
    IntimacyJourneyResult,
    IntimacySimulationReport,
)

__all__ = [
    "IntimacyActorAI",
    "IntimacyAction",
    "SUPPORTED_SCENARIOS",
    "IntimacyFuzzer",
    "SUPPORTED_PARTNER_CONFIGS",
    "SUPPORTED_FUZZ_MODES",
    "IntimacyInvariantAuditor",
    "IntimacyViolation",
    "IntimacySimulator",
    "IntimacyJourneyResult",
    "IntimacySimulationReport",
]
