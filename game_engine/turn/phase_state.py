"""Typed phase-state dataclasses passed between pre-turn, prompt-assembly, and post-turn stages."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class PreTurnState:
    """Data bundle emitted by `run_pre_turn_phase` and consumed by prompt assembly and post-turn."""

    _anom_domain_res: Any = None
    _in_aftercare_for_core: bool = False
    _in_intimate_for_core: bool = False
    _pre_turn_dialogue_partners: list[Any] = field(default_factory=list)
    _pre_turn_incursion_notice: str = ""
    _pre_turn_site_items_by_uid: dict[Any, Any] = field(default_factory=dict)
    _pre_turn_sleep_info: Any = None
    _pre_turn_time_info: Any = None
    _staged_domain_vitals: Any = None
    _staged_time_op: Any = None
    _we_snap: Any = None
    actions_text: str = ""
    active_quests_str: str = ""
    active_recall_blocks: list[str] = field(default_factory=list)
    ambush_monsters: list[Any] = field(default_factory=list)
    ambush_triggered: bool = False
    budget: Any = None
    caseboard_block: str = ""
    cast_plan: Any = None
    ctx: Any = None
    dialogue_prompt_block: str = ""
    directive_note: str = ""
    effective_location: str = ""
    fow_dossier_block: str = ""
    has_exited_convo: bool = False
    hist_text: str = ""
    hs_turn_events: list[Any] = field(default_factory=list)
    mode: str = "narrative"
    new_partners: list[Any] = field(default_factory=list)
    phys_prompt_block: str = ""
    pre_intimate_res: Any = None
    pre_quest_res: Any = None
    pre_social_res: Any = None
    pre_turn_enemy_names: set[str] = field(default_factory=set)
    pre_turn_stage_npcs: list[Any] = field(default_factory=list)
    pre_vitals_res: Any = None
    precomputed: Any = None
    raw_scene_ctx: str = ""
    scen_key: str = "fantasy"
    scene_loc: str = ""
    scene_npcs_for_prompt: list[Any] = field(default_factory=list)
    session_id_val: Any = None
    simultaneity_note: str = ""
    stage_info: dict[str, Any] = field(default_factory=dict)
    time_prompt_block: str = ""
    world_bundle: dict[str, Any] = field(default_factory=dict)
    wp_block: str = ""

    def get(self, key: str, default: Any = None) -> Any:
        """Read a phase-state field by name with fallback default for dict-compatible callers."""
        return getattr(self, key, default)


@dataclass
class PromptAssemblyState:
    """Data bundle emitted by `assemble_and_call_turn_llm` and consumed by post-turn reconciliation."""

    _next_prompt_epoch: int = 0
    departing_for_schedule: list[Any] = field(default_factory=list)
    final_system_prompt_list: list[str] = field(default_factory=list)
    new_partners: list[Any] = field(default_factory=list)
    result: Any = None
    schedule_stay_choice: Any = None
    schedule_transition_choice: Any = None
    user_prompt: str = ""

    def get(self, key: str, default: Any = None) -> Any:
        """Read an assembly-state field by name with fallback default for dict-compatible callers."""
        return getattr(self, key, default)
