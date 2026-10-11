"""
Narrative & Turn Lifecycle Simulator Harness for Hikayat.

Provides:
- NarrativeActorAI & NarrativeAction: Archetype-driven behavioral agents (conversationalist, cautious_explorer, bold_adventurer, chaotic_provocateur).
- NarrativeFuzzer: Conversational, collective entity, and adversarial perturbation generator (clean, realistic_llm, adversarial_stress).
- NarrativeInvariantAuditor & NarrativeViolation: Zero-tolerance invariant verification engine across 6 categories.
- NarrativeSimulator, NarrativeJourneyResult, NarrativeSimulationReport: Orchestration engine and telemetry aggregator.
"""
from .actor_ai import (
    NarrativeActorAI,
    NarrativeAction,
    SUPPORTED_ARCHETYPES,
)
from .fuzzer import (
    NarrativeFuzzer,
)
from .auditor import (
    NarrativeInvariantAuditor,
    NarrativeViolation,
)
from .engine import (
    NarrativeSimulator,
    NarrativeJourneyResult,
    NarrativeSimulationReport,
)

__all__ = [
    "NarrativeActorAI",
    "NarrativeAction",
    "SUPPORTED_ARCHETYPES",
    "NarrativeFuzzer",
    "NarrativeInvariantAuditor",
    "NarrativeViolation",
    "NarrativeSimulator",
    "NarrativeJourneyResult",
    "NarrativeSimulationReport",
]
