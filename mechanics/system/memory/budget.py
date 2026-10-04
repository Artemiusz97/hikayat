from __future__ import annotations
"""
mechanics/memory/budget.py — Dynamic Context Token Budget Manager
=================================================================
Classifies the current scene mode and distributes prompt token allowances
across context sections elastically, so high-priority sections get more
room while irrelevant sections are collapsed.

KEY PRINCIPLE:
  - Input budget governs the *prompt* sent to the LLM (context stuffed in).
  - Output capacity (max_tokens) is NEVER reduced — the model can always
    generate full narratives, long dialogue, etc.
  - This module only controls how many characters / tokens each *input*
    section may contribute to the user prompt.

Usage (in game_engine/context.py or turn.py)::

    from mechanics.system.memory.budget import DynamicTokenBudget, SceneMode
    budget = DynamicTokenBudget.from_session(session, party, actions)
    lore_limit = budget.chars_for("lore")
    history_limit = budget.chars_for("history")
"""

import enum
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

# ---------------------------------------------------------------------------
# Scene Mode Classifier
# ---------------------------------------------------------------------------

class SceneMode(str, enum.Enum):
    COMBAT        = "combat"
    DIALOGUE      = "dialogue"
    EXPLORATION   = "exploration"
    NSFW_INTIMATE = "nsfw_intimate"


# ---------------------------------------------------------------------------
# Per-mode character-count budgets for each prompt section
# (characters, not strict tokens — approximation: 1 token ≈ 4 chars)
# ---------------------------------------------------------------------------

#: Default budget allocations by scene mode.
#: Each value is max *characters* allowed in that prompt section.
_MODE_BUDGETS: dict[SceneMode, dict[str, int]] = {
    SceneMode.COMBAT: {
        "lore":          800,   # brief world anchoring
        "history":      2000,   # recent ~3 combat turns
        "dialogue":        0,   # no dialogue dossier during combat
        "commitments":     0,
        "quest":        1600,   # active objective + waypoints
        "digest":       1200,   # past arc summary still useful
        "caseboard":     600,
    },
    SceneMode.DIALOGUE: {
        "lore":         1000,   # place + NPC world context
        "history":      1600,   # last 3 raw turns
        "dialogue":    10000,   # rich dossier + commitments - biggest budget
        "commitments":   800,
        "quest":         800,   # active quest kept short in dialogue
        "digest":       1200,   # past arc bullets
        "caseboard":     400,
    },
    SceneMode.EXPLORATION: {
        "lore":         2400,   # spatial + factions important here
        "history":      2000,   # recent traversal history
        "dialogue":        0,
        "commitments":   400,   # any outstanding pacts worth remembering
        "quest":        2000,   # waypoints + clues front-and-centre
        "digest":       1600,   # past arc context
        "caseboard":     800,
    },
    SceneMode.NSFW_INTIMATE: {
        "lore":          600,
        "history":      1600,
        "dialogue":    10000,   # partner dossier is critical for continuity
        "commitments":  1200,
        "quest":         400,
        "digest":       1000,
        "caseboard":       0,
    },
}

# Fallback if scene mode cannot be determined
_DEFAULT_BUDGET = _MODE_BUDGETS[SceneMode.EXPLORATION]


@dataclass
class DynamicTokenBudget:
    """Resolved budget for a single turn's prompt assembly."""

    mode: SceneMode
    _budgets: dict[str, int] = field(default_factory=dict)

    # ------------------------------------------------------------------
    # Factory
    # ------------------------------------------------------------------

    @classmethod
    def from_session(
        cls,
        session: dict,
        party: list | None = None,
        actions: list | None = None,
    ) -> "DynamicTokenBudget":
        """Infer the current scene mode from session state and return a budget."""
        mode = _classify_scene(session, party, actions)
        budgets = dict(_MODE_BUDGETS.get(mode, _DEFAULT_BUDGET))
        return cls(mode=mode, _budgets=budgets)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def chars_for(self, section: str) -> int:
        """Return the character allowance for the named prompt section.

        Falls back to a generous default so callers never get zero unexpectedly
        for unknown section names.
        """
        return self._budgets.get(section, 2000)

    def trim(self, text: str, section: str) -> str:
        """Trim *text* to the character budget for *section*.

        Trims at the nearest sentence boundary where possible, otherwise
        hard-truncates with an ellipsis indicator.  If the text is already
        within budget, returns it unchanged.
        """
        limit = self.chars_for(section)
        if not text or limit <= 0 or len(text) <= limit:
            return text
        cut = text[:limit]
        # Try to end on a sentence boundary
        last_punct = max(cut.rfind("."), cut.rfind("!"), cut.rfind("?"), cut.rfind("\n"))
        if last_punct > limit // 2:
            return cut[: last_punct + 1].rstrip()
        return cut.rstrip() + "…"

    def is_combat(self) -> bool:
        return self.mode == SceneMode.COMBAT

    def is_dialogue(self) -> bool:
        return self.mode in (SceneMode.DIALOGUE, SceneMode.NSFW_INTIMATE)

    def is_exploration(self) -> bool:
        return self.mode == SceneMode.EXPLORATION


# ---------------------------------------------------------------------------
# Internal: Scene Mode Classifier
# ---------------------------------------------------------------------------

_INTIMATE_KEYWORDS = frozenset({
    "kiss", "undress", "strip", "bed", "bedroom", "naked", "intimate",
    "oral", "intercourse", "caress", "embrace", "touch sensually",
    "make love", "lie down together", "lie in bed",
})


def _is_intimate_turn(actions: list | None) -> bool:
    """Check whether any action in the turn represents an intimate/NSFW act using the central intent engine."""
    from mechanics.narrative.intent import classify_action_intent, IntentCategory
    for a in (actions or []):
        if isinstance(a, dict) and a.get("is_nsfw"):
            return True
        label = str(a.get("label", "")) if isinstance(a, dict) else str(a)
        label_lower = label.lower()
        if any(kw in label_lower for kw in _INTIMATE_KEYWORDS):
            return True
        intent = classify_action_intent(label)
        if intent.category == IntentCategory.INTIMATE_ACT or intent.metadata.get("is_nsfw"):
            return True
    return False


def _classify_scene(
    session: dict,
    party: list | None,
    actions: list | None,
) -> SceneMode:
    """Determine the dominant scene mode from session state."""
    # Combat: enemies present
    import game_engine
    if game_engine.get_active_enemies(session):
        return SceneMode.COMBAT

    from mechanics.world.mobility import get_session_dialogue_partners
    has_dialogue_partner = bool(get_session_dialogue_partners(session))

    # NSFW intimate (checked before generic dialogue)
    scenario = str(session.get("scenario", "")).lower()
    if any(kw in scenario for kw in ("nsfw", "adult", "erotic", "intimate")):
        if _is_intimate_turn(actions):
            return SceneMode.NSFW_INTIMATE

    # Dialogue: active dialogue partner set
    if has_dialogue_partner:
        # Even deeper intimate check in dialogue mode
        if _is_intimate_turn(actions):
            return SceneMode.NSFW_INTIMATE
        return SceneMode.DIALOGUE

    # Default: open exploration / hub
    return SceneMode.EXPLORATION
