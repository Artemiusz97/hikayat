"""
Social Dynamics & Persona Simulator Harness for Hikayat.

Provides:
- SocialActorAI & SocialAction: Archetype-driven behavioral agents (diplomat, operative, provocateur, romance_seeker).
- SocialFuzzer: Conversational and adversarial perturbation generator (clean, realistic_llm, adversarial_stress).
- SocialInvariantAuditor & SocialViolation: Zero-tolerance invariant verification engine.
- SocialDynamicsSimulator, SocialJourneyResult, SocialSimulationReport: Orchestration engine and telemetry aggregator.
"""
from .actor_ai import (
    SocialActorAI,
    SocialAction,
    SUPPORTED_ARCHETYPES,
)
from .fuzzer import (
    SocialFuzzer,
)
from .auditor import (
    SocialInvariantAuditor,
    SocialViolation,
)
from .engine import (
    SocialDynamicsSimulator,
    SocialJourneyResult,
    SocialSimulationReport,
)

__all__ = [
    "SocialActorAI",
    "SocialAction",
    "SUPPORTED_ARCHETYPES",
    "SocialFuzzer",
    "SocialInvariantAuditor",
    "SocialViolation",
    "SocialDynamicsSimulator",
    "SocialJourneyResult",
    "SocialSimulationReport",
]
