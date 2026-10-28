from __future__ import annotations
from typing import List, Optional, Dict, Literal, Any, Union
from pydantic import BaseModel, Field, ConfigDict, field_validator, model_validator

from .trackers import (
    EntityAudit, CharacterOutcome, TrackerEntity,
    NewEntity, MerchantEncounter, RelationshipUpdate, FactionUpdate
)

_VALID_STATS = {"STR", "PER", "END", "CHA", "INT", "AGI", "LUK", "ITEM", "NONE", "FREE"}

_VALID_INTENTS = {
    "romantic_confession", "intimate_act", "affection_touch", "disclosure_inquiry",
    "gift_offer", "media_capture", "phone_comm", "phone_contact_exchange",
    "dialogue_exit", "social_invite", "party_recruit", "merchant_trade",
    "inspect_board", "area_scout", "investigate_clue", "rest_sleep",
    "stealth_covert", "movement", "appointment_meetup", "dialogue_init",
    "general_action"
}

_VALID_SUB_INTENTS = {
    "", "kiss", "foreplay", "manual_give", "manual_receive", "manual_mutual",
    "oral_give", "oral_receive", "oral_mutual", "intercourse",
    "anal_give", "anal_receive", "anal_mutual", "aftercare", "redress", "date", "confession",
    "lockpick", "pickpocket", "gamble", "use_item", "deduce_clues", "explore",
    "hide", "eavesdrop", "combat_attack", "combat_magic", "combat_tactic", "combat_flee"
}


def _coerce_bool_value(v: Any) -> bool:
    if isinstance(v, bool):
        return v
    if isinstance(v, (int, float)):
        return bool(v)
    if isinstance(v, str):
        return v.strip().lower() in ("true", "1", "yes")
    return False


def _filter_valid_cast_events_list(v: Any) -> List[Any]:
    if not v or not isinstance(v, list):
        return []
    cleaned = []
    for item in v:
        if isinstance(item, BaseModel):
            ev_type = str(getattr(item, "type", "") or "").strip().lower()
            ev_npc = str(getattr(item, "npc", "") or "").strip()
            if ev_type in ("arrive", "depart", "engage") and ev_npc:
                cleaned.append(item)
        elif isinstance(item, dict):
            ev_type = str(item.get("type") or "").strip().lower()
            ev_npc = str(item.get("npc") or "").strip()
            if ev_type in ("arrive", "depart", "engage") and ev_npc:
                cleaned.append({
                    "type": ev_type,
                    "npc": ev_npc,
                    "reason": str(item.get("reason") or "").strip(),
                })
    return cleaned


class DictAccessibleModel(BaseModel):
    """Base Pydantic model that provides dict-like subscripting and .get() for legacy consumer compatibility."""
    def __getitem__(self, item: str) -> Any:
        try:
            return getattr(self, item)
        except AttributeError:
            raise KeyError(item)

    def get(self, item: str, default: Any = None) -> Any:
        return getattr(self, item, default)


class Choice(DictAccessibleModel):
    model_config = ConfigDict(extra="allow")
    label: str = Field(..., description="Concise, max 6-8 words")
    stat: str = Field(default="NONE")  # Accept any string; validated below
    requirement: int = Field(default=0, ge=0, le=20)
    mp_cost: int = Field(default=0)
    gold_spent: int = Field(default=0, ge=0)
    triggers_loot_roll: bool = Field(default=False)
    intent: str = Field(default="general_action")
    sub_intent: Optional[str] = Field(default="")
    target_npc: Optional[str] = Field(default="")
    target_node_id: Optional[str] = Field(default="")
    target_location: Optional[str] = Field(default="")
    ends_dialogue: bool = Field(default=False)
    dismisses_npc: bool = Field(default=False)
    quest_id: Optional[str] = Field(default="")
    sub_obj_id: Optional[Any] = Field(default=None)
    stage_index: Optional[int] = Field(default=0)
    is_quest_action: bool = Field(default=False)
    is_climax_action: bool = Field(default=False)
    breakthrough_leveraged: bool = Field(default=False)

    @field_validator("stat", mode="before")
    @classmethod
    def coerce_stat(cls, v: Any) -> str:
        s = str(v).upper().strip() if v else "NONE"
        return s if s in _VALID_STATS else "NONE"

    @field_validator("requirement", "mp_cost", "gold_spent", "stage_index", mode="before")
    @classmethod
    def coerce_int_zero(cls, v: Any) -> int:
        if v is None:
            return 0
        try:
            return max(0, int(v)) if v != "" else 0
        except (TypeError, ValueError):
            return 0

    @field_validator("intent", mode="before")
    @classmethod
    def coerce_intent(cls, v: Any) -> str:
        if not v:
            return "general_action"
        s = str(v).lower().strip()
        if s in ("move", "travel"):
            return "movement"
        return s if s in _VALID_INTENTS else "general_action"

    @field_validator(
        "ends_dialogue", "dismisses_npc", "is_quest_action",
        "is_climax_action", "breakthrough_leveraged", "triggers_loot_roll",
        mode="before",
    )
    @classmethod
    def coerce_bool_fields(cls, v: Any) -> bool:
        return _coerce_bool_value(v)

    @field_validator("sub_intent", mode="before")
    @classmethod
    def coerce_sub_intent(cls, v: Any) -> str:
        if v is None:
            return ""
        s = str(v).strip().lower()
        if s in ("none", "null", "undefined", ""):
            return ""
        return s if s in _VALID_SUB_INTENTS else ""

    @field_validator("target_npc", "target_node_id", "target_location", "quest_id", mode="before")
    @classmethod
    def coerce_str_empty(cls, v: Any) -> str:
        if v is None:
            return ""
        s = str(v).strip()
        return "" if s.lower() in ("none", "null", "undefined") else s

class PropUpdate(BaseModel):
    model_config = ConfigDict(extra="allow")
    name: str = Field(default="")
    state: str = Field(default="")

    @field_validator("name", "state", mode="before")
    @classmethod
    def coerce_str(cls, v: Any) -> str:
        return str(v).replace("\x00", "").strip()[:100] if v else ""

class ActorClothing(BaseModel):
    model_config = ConfigDict(extra="allow")
    top: Optional[str] = None
    bottom: Optional[str] = None
    under_top: Optional[str] = None
    under_bottom: Optional[str] = None

    @field_validator("top", "bottom", "under_top", "under_bottom", mode="before")
    @classmethod
    def coerce_clothing_slot(cls, v: Any) -> Optional[str]:
        if v is None:
            return None
        s = str(v).replace("\x00", "").strip()[:80]
        return s if s else None

class ActorUpdate(BaseModel):
    model_config = ConfigDict(extra="allow")
    posture: Optional[str] = None
    holding: Optional[str] = None
    clothing: Optional[Union[ActorClothing, Dict[str, Any]]] = None
    stance: Optional[str] = None
    relative_position: Optional[str] = None
    tether: Optional[str] = None

    @field_validator("posture", mode="before")
    @classmethod
    def coerce_posture(cls, v: Any) -> Optional[str]:
        if not v:
            return None
        return str(v).replace("\x00", "").strip()[:100]

    @field_validator("holding", mode="before")
    @classmethod
    def coerce_holding(cls, v: Any) -> Optional[str]:
        if v is None:
            return None
        return str(v).replace("\x00", "").strip()[:100]

    @field_validator("stance", mode="before")
    @classmethod
    def coerce_stance(cls, v: Any) -> Optional[str]:
        if not v:
            return None
        return str(v).replace("\x00", "").strip()[:60]

    @field_validator("relative_position", mode="before")
    @classmethod
    def coerce_relative_position(cls, v: Any) -> Optional[str]:
        if not v:
            return None
        return str(v).replace("\x00", "").strip()[:100]

    @field_validator("tether", mode="before")
    @classmethod
    def coerce_tether(cls, v: Any) -> Optional[str]:
        if not v:
            return None
        return str(v).replace("\x00", "").strip()[:100]

class PhysicalUpdate(BaseModel):
    model_config = ConfigDict(extra="allow")
    actors: Dict[str, Union[ActorUpdate, Dict[str, Any]]] = Field(default_factory=dict)
    props: List[Union[PropUpdate, Dict[str, Any]]] = Field(default_factory=list)
    intimate_contact: Optional[str] = None

    @field_validator("actors", mode="before")
    @classmethod
    def coerce_actors(cls, v: Any) -> Dict[str, Any]:
        if not v:
            return {}
        if isinstance(v, list):
            res = {}
            for item in v:
                if isinstance(item, dict) and item.get("name"):
                    res[str(item["name"])] = item
                elif hasattr(item, "model_dump"):
                    d = item.model_dump()
                    if d.get("name"):
                        res[str(d["name"])] = d
            return res
        if hasattr(v, "model_dump"):
            return v.model_dump()
        if isinstance(v, dict):
            cleaned = {}
            for k, val in v.items():
                name_str = str(k).strip()
                if not name_str:
                    continue
                if isinstance(val, dict):
                    cleaned[name_str] = val
                elif hasattr(val, "model_dump"):
                    cleaned[name_str] = val.model_dump()
                elif isinstance(val, str) and val.strip():
                    cleaned[name_str] = {"posture": val.strip()[:100]}
                else:
                    cleaned[name_str] = {}
            return cleaned
        return {}

    @field_validator("props", mode="before")
    @classmethod
    def coerce_props(cls, v: Any) -> List[Any]:
        if not v:
            return []
        if isinstance(v, dict):
            return [{"name": str(k), "state": str(val)} for k, val in v.items()]
        if isinstance(v, list):
            res = []
            for item in v:
                if isinstance(item, str) and item.strip():
                    res.append({"name": item.strip(), "state": "Present"})
                elif isinstance(item, dict):
                    res.append(item)
                elif hasattr(item, "model_dump"):
                    res.append(item)
            return res
        return []

    combat_focus: Optional[str] = None
    dropped_items: List[str] = Field(default_factory=list)
    player_climaxed: Optional[bool] = None
    partner_climaxed: Optional[bool] = None

    @field_validator("player_climaxed", "partner_climaxed", mode="before")
    @classmethod
    def coerce_climax_bool(cls, v: Any) -> Optional[bool]:
        if v is None:
            return None
        if isinstance(v, bool):
            return v
        if isinstance(v, str):
            return v.strip().lower() in ("true", "1", "yes")
        return bool(v)

    @field_validator("intimate_contact", mode="before")
    @classmethod
    def coerce_intimate_contact(cls, v: Any) -> Optional[str]:
        if not v:
            return None
        return str(v).replace("\x00", "").strip()[:150]

    @field_validator("combat_focus", mode="before")
    @classmethod
    def coerce_combat_focus(cls, v: Any) -> Optional[str]:
        if not v:
            return None
        return str(v).replace("\x00", "").strip()[:150]

    @field_validator("dropped_items", mode="before")
    @classmethod
    def coerce_dropped_items(cls, v: Any) -> List[str]:
        if not v:
            return []
        if isinstance(v, list):
            return [str(x).replace("\x00", "").strip()[:100] for x in v if str(x).strip()]
        return []

class ClueDiscovery(BaseModel):
    model_config = ConfigDict(extra="allow")
    clue_id: Optional[str] = Field(default="")
    quest_id: Optional[str] = Field(default="")
    lead_text: str = Field(default="", description="Concrete investigative evidence text")
    title: Optional[str] = Field(default="Evidence Lead")
    category: str = Field(default="physical", description="physical, testimonial, archival, digital, supernatural")
    linked_npc: Optional[str] = Field(default="")
    source_location: Optional[str] = Field(default="")
    importance: str = Field(default="medium")

class BreakthroughLeverage(BaseModel):
    model_config = ConfigDict(extra="allow")
    title: str = Field(default="Breakthrough Leverage")
    target_npc: str = Field(default="")
    quest_id: str = Field(default="")
    deduction_text: str = Field(default="")

class SubQuestDefinition(BaseModel):
    id: int
    archetype: str
    text: str
    waypoints: Optional[List[Dict[str, Any]]] = None

class NextStoryQuest(BaseModel):
    title: str = Field(..., description="Unique evocative Story Quest title")
    archetype: str = Field(..., description="Creative scenario-appropriate main quest archetype")
    objective: str = Field(..., description="Rich 2-3 sentence objective")
    sub_quests: List[SubQuestDefinition] = Field(default_factory=list)

class QuestUpdate(BaseModel):
    model_config = ConfigDict(extra="allow")
    quest_id: str = Field(default="SQ-Active")
    title: str = Field(default="Active Quest")
    quest_type: str = Field(default="Story Quest")
    archetype: str = Field(default="Story Quest")
    objective: str = Field(default="")
    completed_sub_quest_ids: List[int] = Field(default_factory=list)
    # Relaxed to Any values because LLMs sometimes put comments in dict values
    goal_progress_updates: Dict[str, Any] = Field(default_factory=dict)
    progress: Optional[str] = None
    current_clues: Optional[str] = None
    status: str = Field(default="Active")  # Literal relaxed; validated below
    reward_xp: Optional[int] = None
    reward_gold: Optional[int] = None
    reward_item: Optional[str] = None
    next_chapter_quest: Optional[NextStoryQuest] = None

    @field_validator("quest_id", mode="before")
    @classmethod
    def coerce_quest_id(cls, v: Any) -> str:
        s = str(v).strip() if v else ""
        return s or "SQ-Active"

    @field_validator("title", mode="before")
    @classmethod
    def coerce_title(cls, v: Any) -> str:
        s = str(v).strip() if v else ""
        return s or "Active Quest"

    @field_validator("status", mode="before")
    @classmethod
    def coerce_status(cls, v: Any) -> str:
        if not v or not str(v).strip():
            return "Active"
        s = str(v).strip().capitalize()
        return s if s in ("Active", "Completed", "Failed") else "Active"

    @field_validator("goal_progress_updates", mode="before")
    @classmethod
    def coerce_goal_progress(cls, v: Any) -> Dict[str, Any]:
        if not isinstance(v, dict):
            return {}
        # Filter out keys/values that aren't valid int-convertible entries
        clean = {}
        for k, val in v.items():
            if "//" in str(k):  # LLM comment leak inside the key
                continue
            try:
                clean[k] = int(val) if isinstance(val, (int, float, str)) and str(val).lstrip("-").isdigit() else val
            except Exception:
                clean[k] = val
        return clean

class CastEvent(BaseModel):
    model_config = ConfigDict(extra="ignore")
    type: Literal["arrive", "depart", "engage"] = Field(..., description="arrive (walk into scene), depart (walk out of scene), or engage (walk up to player to initiate conversation)")
    npc: str = Field(..., description="Exact NPC name")
    reason: Optional[str] = Field(default="", description="Narrative rationale for the event")
    gender: Optional[str] = Field(default=None, description="male or female (arrive only)")
    descriptor: Optional[str] = Field(default=None, description="Short physical descriptor matching the prose (arrive only)")
    role: Optional[str] = Field(default=None, description="Role or occupation (arrive only)")

    @field_validator("gender", "descriptor", "role", mode="before")
    @classmethod
    def coerce_optional_cast_meta(cls, v: Any) -> Optional[str]:
        if v is None:
            return None
        s = str(v).strip()
        return s or None

    @field_validator("type", mode="before")
    @classmethod
    def coerce_type(cls, v: Any) -> str:
        s = str(v or "").strip().lower()
        if s not in ("arrive", "depart", "engage"):
            raise ValueError(f"Invalid cast event type: {v!r}")
        return s

    @field_validator("npc", "reason", mode="before")
    @classmethod
    def coerce_str(cls, v: Any) -> str:
        return str(v or "").strip()


class NarrationOutcome(DictAccessibleModel):
    model_config = ConfigDict(extra="ignore")
    outcome_narrative: str = Field(default="")
    next_narrative: str = Field(default="")
    scene_title: str = Field(default="")
    next_choices: List[Choice] = Field(default_factory=list)
    cast_events: List[CastEvent] = Field(default_factory=list)

    @field_validator("cast_events", mode="before")
    @classmethod
    def coerce_cast_events(cls, v: Any) -> List[Any]:
        return _filter_valid_cast_events_list(v)

    @field_validator("next_choices", mode="before")
    @classmethod
    def coerce_next_choices(cls, v: Any) -> List[Any]:
        if not v or not isinstance(v, list):
            return []
        cleaned = []
        for item in v:
            if isinstance(item, str) and item.strip():
                cleaned.append({"label": item.strip()})
            elif isinstance(item, (dict, BaseModel)):
                if isinstance(item, dict):
                    valid_keys = [str(k).strip() for k in item.keys() if str(k).strip()]
                    if not valid_keys or not str(item.get("label") or "").strip():
                        continue
                cleaned.append(item)
        return cleaned


class CosmeticActorPose(BaseModel):
    """Cosmetic-only actor pose update (posture and held prop). Mechanical clothing/intimacy/tether are Python-owned."""
    model_config = ConfigDict(extra="ignore")
    posture: Optional[str] = None
    holding: Optional[str] = None

    @field_validator("posture", "holding", mode="before")
    @classmethod
    def coerce_pose_str(cls, v: Any) -> Optional[str]:
        if v is None:
            return None
        s = str(v).replace("\x00", "").strip()[:100]
        return s if s else None


class DeterministicTurnNarration(DictAccessibleModel):
    """Prose-first narrator schema for deterministic-first exploration, social, and intimate turns."""
    model_config = ConfigDict(extra="allow")
    scene_title: str = Field(default="")
    outcome_narrative: str = Field(default="")
    next_narrative: str = Field(default="")
    next_choices: List[Choice] = Field(default_factory=list)
    actor_poses: Dict[str, Union[CosmeticActorPose, Dict[str, Any]]] = Field(default_factory=dict)
    episodic_memory: Optional[str] = Field(default=None)
    image_prompt: Optional[str] = Field(default=None)
    cast_events: List[CastEvent] = Field(default_factory=list)

    @field_validator("cast_events", mode="before")
    @classmethod
    def coerce_cast_events(cls, v: Any) -> List[Any]:
        return _filter_valid_cast_events_list(v)

    @field_validator("outcome_narrative", "next_narrative", "scene_title", mode="before")
    @classmethod
    def coerce_text_fields(cls, v: Any) -> str:
        if not v:
            return ""
        if isinstance(v, str):
            return v.strip()
        if isinstance(v, list):
            return "\n\n".join(str(x).strip() for x in v if str(x).strip())
        return str(v).strip()

    @field_validator("next_choices", mode="before")
    @classmethod
    def coerce_next_choices(cls, v: Any) -> List[Any]:
        if not v or not isinstance(v, list):
            return []
        cleaned = []
        for item in v:
            if isinstance(item, str) and item.strip():
                cleaned.append({"label": item.strip()})
            elif isinstance(item, (dict, BaseModel)):
                if isinstance(item, dict):
                    valid_keys = [str(k).strip() for k in item.keys() if str(k).strip()]
                    if not valid_keys or not str(item.get("label") or "").strip():
                        continue
                cleaned.append(item)
        return cleaned

    @field_validator("actor_poses", mode="before")
    @classmethod
    def coerce_actor_poses(cls, v: Any) -> Dict[str, Any]:
        if not v or not isinstance(v, dict):
            return {}
        out = {}
        for k, val in v.items():
            k_str = str(k).strip()
            if not k_str:
                continue
            if isinstance(val, str) and val.strip():
                out[k_str] = {"posture": val.strip()}
            elif isinstance(val, dict):
                pose_dict = {}
                if val.get("posture") is not None and str(val.get("posture")).strip():
                    pose_dict["posture"] = str(val["posture"]).strip()[:100]
                if val.get("holding") is not None and str(val.get("holding")).strip():
                    pose_dict["holding"] = str(val["holding"]).strip()[:100]
                out[k_str] = pose_dict
            elif isinstance(val, BaseModel):
                out[k_str] = val
        return out

    @field_validator("episodic_memory", "image_prompt", mode="before")
    @classmethod
    def coerce_optional_str(cls, v: Any) -> Optional[str]:
        if not v:
            return None
        if isinstance(v, str):
            s = v.strip()
            return None if s.lower() in ("none", "null", "n/a", "") else s[:300]
        return None

    @model_validator(mode="after")
    def coerce_extra_list_fields(self) -> "DeterministicTurnNarration":
        _extra = getattr(self, "__pydantic_extra__", None)
        if isinstance(_extra, dict):
            for _k in (
                "character_outcomes",
                "relationship_updates",
                "quest_updates",
                "faction_updates",
                "npcs_present",
                "nearby_enemies",
                "new_entities",
                "choices",
                "npc_departures",
                "dead_enemies",
                "dead_monsters",
                "deceased_characters",
                "speaking_characters",
            ):
                if _k in _extra and not isinstance(_extra[_k], list):
                    _val = _extra[_k]
                    if isinstance(_val, dict):
                        _extra[_k] = [_val] if _val else []
                    elif isinstance(_val, str) and _val.strip():
                        _extra[_k] = [_val.strip()]
                    else:
                        _extra[_k] = []
        return self


class DeterministicCombatNarration(DictAccessibleModel):
    """Prose-first narrator schema for active combat turns (next_choices omitted; 100% Python-generated)."""
    model_config = ConfigDict(extra="allow")
    scene_title: str = Field(default="")
    outcome_narrative: str = Field(default="")
    next_narrative: str = Field(default="")
    actor_poses: Dict[str, Union[CosmeticActorPose, Dict[str, Any]]] = Field(default_factory=dict)
    episodic_memory: Optional[str] = Field(default=None)
    image_prompt: Optional[str] = Field(default=None)
    cast_events: List[CastEvent] = Field(default_factory=list)

    @field_validator("cast_events", mode="before")
    @classmethod
    def coerce_cast_events(cls, v: Any) -> List[Any]:
        return _filter_valid_cast_events_list(v)

    @field_validator("outcome_narrative", "next_narrative", "scene_title", mode="before")
    @classmethod
    def coerce_text_fields(cls, v: Any) -> str:
        if not v:
            return ""
        if isinstance(v, str):
            return v.strip()
        if isinstance(v, list):
            return "\n\n".join(str(x).strip() for x in v if str(x).strip())
        return str(v).strip()

    @field_validator("actor_poses", mode="before")
    @classmethod
    def coerce_actor_poses(cls, v: Any) -> Dict[str, Any]:
        return DeterministicTurnNarration.coerce_actor_poses(v)

    @field_validator("episodic_memory", "image_prompt", mode="before")
    @classmethod
    def coerce_optional_str(cls, v: Any) -> Optional[str]:
        return DeterministicTurnNarration.coerce_optional_str(v)

    @model_validator(mode="after")
    def coerce_extra_list_fields(self) -> "DeterministicCombatNarration":
        return DeterministicTurnNarration.coerce_extra_list_fields(self)  # type: ignore[return-value]


class TurnOutcome(DictAccessibleModel):
    model_config = ConfigDict(extra="allow")
    scene_title: str = Field(default="")
    entity_audit: EntityAudit = Field(default_factory=EntityAudit)
    outcome_narrative: str = Field(default="")
    next_narrative: str = Field(default="")
    next_choices: List[Choice] = Field(default_factory=list)
    character_outcomes: List[CharacterOutcome] = Field(default_factory=list)
    physical_updates: Optional[PhysicalUpdate] = None
    location: str = Field(default="")
    npcs_present: List[TrackerEntity] = Field(default_factory=list)
    npc_departures: List[str] = Field(default_factory=list)
    nearby_enemies: List[TrackerEntity] = Field(default_factory=list)
    cast_events: List[CastEvent] = Field(default_factory=list)
    merchant_encounter: Optional[MerchantEncounter] = None
    faction_updates: List[FactionUpdate] = Field(default_factory=list)
    faction_promotion_result: Optional[str] = None
    image_prompt: Optional[str] = None

    @field_validator("cast_events", mode="before")
    @classmethod
    def coerce_cast_events(cls, v: Any) -> List[Any]:
        return _filter_valid_cast_events_list(v)

    @field_validator("location", mode="before")
    @classmethod
    def coerce_location(cls, v: Any) -> str:
        if not v:
            return ""
        if isinstance(v, dict):
            from mechanics.world.locations.hierarchy import parse_structured_location_dict, format_tiered_location_string
            parsed = parse_structured_location_dict(v)
            if parsed:
                return format_tiered_location_string(*parsed)
            return str(v.get("name") or v.get("location") or "")
        v_str = str(v).strip()
        if v_str.startswith("{") and ("tier" in v_str.lower() or "zone" in v_str.lower()):
            try:
                import json
                d = json.loads(v_str)
                if isinstance(d, dict):
                    from mechanics.world.locations.hierarchy import parse_structured_location_dict, format_tiered_location_string
                    parsed = parse_structured_location_dict(d)
                    if parsed:
                        return format_tiered_location_string(*parsed)
            except Exception:
                pass
        return v_str

    @field_validator("outcome_narrative", "next_narrative", "scene_title", mode="before")
    @classmethod
    def coerce_text_fields(cls, v: Any) -> str:
        if not v:
            return ""
        if isinstance(v, str):
            return v.strip()
        if isinstance(v, list):
            return "\n\n".join(str(x).strip() for x in v if str(x).strip())
        return str(v).strip()

    @field_validator("image_prompt", mode="before")
    @classmethod
    def coerce_image_prompt(cls, v: Any) -> Optional[str]:
        if not v:
            return None
        if isinstance(v, str):
            s = v.strip()
            return s if s else None
        if isinstance(v, list):
            str_parts = [str(x).strip() for x in v if isinstance(x, str) and str(x).strip()]
            return " ".join(str_parts) if str_parts else None
        if isinstance(v, dict):
            p = v.get("prompt") or v.get("image_prompt") or v.get("description")
            return p.strip() if isinstance(p, str) and p.strip() else None
        return None

    @field_validator("merchant_encounter", mode="before")
    @classmethod
    def coerce_merchant_encounter(cls, v: Any) -> Optional[Any]:
        if not v:
            return None
        if isinstance(v, dict):
            valid_keys = [k for k in v.keys() if not str(k).startswith("_")]
            if not valid_keys:
                return None
            has_name = bool(v.get("name") and str(v.get("name")).strip())
            has_desc = bool(v.get("description") and str(v.get("description")).strip())
            if "present" not in v:
                if not has_name and not has_desc:
                    return None
                v["present"] = True
            elif not v["present"] and not has_name and not has_desc:
                return None
        return v

    @field_validator("character_outcomes", mode="before")
    @classmethod
    def coerce_character_outcomes(cls, v: Any) -> List[Any]:
        if not v or not isinstance(v, list):
            return []
        cleaned = []
        for item in v:
            if not isinstance(item, (dict, BaseModel)):
                continue
            if isinstance(item, dict):
                valid_keys = [str(k).strip() for k in item.keys() if str(k).strip()]
                if not valid_keys or not str(item.get("name") or "").strip():
                    continue
            cleaned.append(item)
        return cleaned

    @field_validator("next_choices", mode="before")
    @classmethod
    def coerce_next_choices(cls, v: Any) -> List[Any]:
        if not v or not isinstance(v, list):
            return []
        cleaned = []
        for item in v:
            if isinstance(item, str) and item.strip():
                cleaned.append({"label": item.strip()})
            elif isinstance(item, (dict, BaseModel)):
                if isinstance(item, dict):
                    valid_keys = [str(k).strip() for k in item.keys() if str(k).strip()]
                    if not valid_keys or not str(item.get("label") or "").strip():
                        continue
                cleaned.append(item)
        return cleaned

    @field_validator("npcs_present", "nearby_enemies", mode="before")
    @classmethod
    def coerce_entity_lists(cls, v: Any) -> List[Any]:
        if not v or not isinstance(v, list):
            return []
        cleaned = []
        for item in v:
            if isinstance(item, str) and item.strip():
                cleaned.append({"name": item.strip()})
            elif isinstance(item, (dict, BaseModel)):
                if isinstance(item, dict):
                    valid_keys = [str(k).strip() for k in item.keys() if str(k).strip()]
                    if not valid_keys or not str(item.get("name") or "").strip():
                        continue
                cleaned.append(item)
        return cleaned

    @field_validator("faction_updates", mode="before")
    @classmethod
    def coerce_faction_updates(cls, v: Any) -> List[Any]:
        if not v or not isinstance(v, list):
            return []
        cleaned = []
        for item in v:
            if not isinstance(item, (dict, BaseModel)):
                continue
            if isinstance(item, dict):
                valid_keys = [str(k).strip() for k in item.keys() if str(k).strip()]
                if not valid_keys or not str(item.get("faction_name") or "").strip():
                    continue
            cleaned.append(item)
        return cleaned

    @field_validator("faction_promotion_result", mode="before")
    @classmethod
    def coerce_faction_promotion(cls, v: Any) -> Optional[str]:
        """Accept empty string, None, or any non-valid value — coerce to None."""
        if not v or str(v).strip().lower() not in ("success", "failure"):
            return None
        return str(v).strip().lower()

    @field_validator("physical_updates", mode="before")
    @classmethod
    def coerce_physical_updates(cls, v: Any) -> Optional[Any]:
        if not v or not isinstance(v, (dict, BaseModel)):
            return None
        return v

class SocialArbiterOutcome(DictAccessibleModel):
    model_config = ConfigDict(extra="allow")
    relationship_updates: List[RelationshipUpdate] = Field(default_factory=list)
    new_entities: List[NewEntity] = Field(default_factory=list)
    quest_updates: List[QuestUpdate] = Field(default_factory=list)
    npc_memories: List[Dict[str, Any]] = Field(default_factory=list)

    @field_validator("relationship_updates", mode="before")
    @classmethod
    def coerce_relationship_updates(cls, v: Any) -> List[Any]:
        if not v or not isinstance(v, list):
            return []
        cleaned = []
        for item in v:
            if not isinstance(item, (dict, BaseModel)):
                continue
            if isinstance(item, dict):
                valid_keys = [str(k).strip() for k in item.keys() if str(k).strip()]
                if not valid_keys or not str(item.get("npc_name") or "").strip():
                    continue
            cleaned.append(item)
        return cleaned

    @field_validator("new_entities", mode="before")
    @classmethod
    def coerce_entity_lists(cls, v: Any) -> List[Any]:
        if not v or not isinstance(v, list):
            return []
        cleaned = []
        for item in v:
            if isinstance(item, str) and item.strip():
                cleaned.append({"name": item.strip()})
            elif isinstance(item, (dict, BaseModel)):
                if isinstance(item, dict):
                    valid_keys = [str(k).strip() for k in item.keys() if str(k).strip()]
                    if not valid_keys or not str(item.get("name") or "").strip():
                        continue
                cleaned.append(item)
        return cleaned

    @field_validator("quest_updates", mode="before")
    @classmethod
    def coerce_quest_updates(cls, v: Any) -> List[Any]:
        if not v or not isinstance(v, list):
            return []
        cleaned = []
        for item in v:
            if not isinstance(item, (dict, BaseModel)):
                continue
            if isinstance(item, dict):
                valid_keys = [str(k).strip() for k in item.keys() if str(k).strip()]
                if not valid_keys:
                    continue
                q_id = str(item.get("quest_id") or "").strip()
                q_title = str(item.get("title") or "").strip()
                if not q_id and not q_title:
                    continue
            cleaned.append(item)
        return cleaned

    @field_validator("npc_memories", mode="before")
    @classmethod
    def coerce_npc_memories(cls, v: Any) -> List[Any]:
        if not v or not isinstance(v, list):
            return []
        cleaned = []
        for item in v:
            if not isinstance(item, (dict, BaseModel)):
                continue
            if isinstance(item, dict):
                n_name = str(item.get("npc_name") or "").strip()
                fact = str(item.get("memory_fact") or item.get("fact") or "").strip()
                if not n_name or not fact:
                    continue
                cleaned.append({
                    "npc_name": n_name,
                    "memory_fact": fact,
                    "sentiment_delta": int(item.get("sentiment_delta", 0)),
                    "importance": int(item.get("importance", 1)),
                    "is_secret": bool(item.get("is_secret", False)),
                    "emotional_tone": str(item.get("emotional_tone") or "").strip(),
                    "open_thread": str(item.get("open_thread") or "").strip(),
                })
            else:
                cleaned.append(item)
        return cleaned

_VALID_TACTICAL_ARCHETYPES = {
    "", "environmental_hazard", "tactical_debuff", "combat_parley", "called_shot", "reposition"
}

class ActionClassification(DictAccessibleModel):
    stat: str = Field(default="NONE")
    requirement: int = Field(default=6, ge=0, le=20)
    mp_cost: int = Field(default=0)
    intent: str = Field(default="general_action")
    sub_intent: Optional[str] = Field(default="")
    target_npc: Optional[str] = Field(default="")
    target_node_id: Optional[str] = Field(default="")
    target_location: Optional[str] = Field(default="")
    ends_dialogue: bool = Field(default=False)
    dismisses_npc: bool = Field(default=False)
    quest_id: Optional[str] = Field(default="")
    sub_obj_id: Optional[Any] = Field(default=None)
    stage_index: Optional[int] = Field(default=0)
    is_quest_action: bool = Field(default=False)
    is_climax_action: bool = Field(default=False)
    breakthrough_leveraged: bool = Field(default=False)
    combat_tactical_archetype: Optional[str] = Field(default="")
    gold_spent: int = Field(default=0, ge=0)
    spawns_npc_role: Optional[str] = Field(default="")
    triggers_loot_roll: bool = Field(default=False)
    is_memory_recall: bool = Field(default=False)
    recall_query: Optional[str] = None
    reasoning: Optional[str] = None

    @field_validator("stat", mode="before")
    @classmethod
    def coerce_stat(cls, v: Any) -> str:
        s = str(v).upper().strip() if v else "NONE"
        return s if s in _VALID_STATS else "NONE"

    @field_validator("intent", mode="before")
    @classmethod
    def coerce_intent(cls, v: Any) -> str:
        if not v:
            return "general_action"
        s = str(v).lower().strip()
        if s in ("move", "travel"):
            return "movement"
        return s if s in _VALID_INTENTS else "general_action"

    @field_validator(
        "ends_dialogue", "dismisses_npc", "is_quest_action",
        "is_climax_action", "breakthrough_leveraged", "triggers_loot_roll",
        "is_memory_recall",
        mode="before",
    )
    @classmethod
    def coerce_action_bools(cls, v: Any) -> bool:
        return _coerce_bool_value(v)

    @field_validator("sub_intent", mode="before")
    @classmethod
    def coerce_sub_intent(cls, v: Any) -> str:
        if v is None:
            return ""
        s = str(v).strip().lower()
        if s in ("none", "null", "undefined", ""):
            return ""
        return s if s in _VALID_SUB_INTENTS else ""

    @field_validator("target_npc", "target_node_id", "target_location", "spawns_npc_role", "quest_id", mode="before")
    @classmethod
    def coerce_str_empty(cls, v: Any) -> str:
        if v is None:
            return ""
        s = str(v).strip()
        return "" if s.lower() in ("none", "null", "undefined") else s

    @field_validator("requirement", "mp_cost", "stage_index", mode="before")
    @classmethod
    def coerce_int_fields(cls, v: Any) -> int:
        if v is None or v == "":
            return 0
        try:
            return max(0, int(v))
        except (ValueError, TypeError):
            return 0

    @field_validator("combat_tactical_archetype", mode="before")
    @classmethod
    def coerce_tactical_archetype(cls, v: Any) -> str:
        if not v:
            return ""
        s = str(v).lower().strip()
        return s if s in _VALID_TACTICAL_ARCHETYPES else ""

    @field_validator("gold_spent", mode="before")
    @classmethod
    def coerce_gold_spent(cls, v: Any) -> int:
        try:
            return max(0, int(v or 0))
        except (ValueError, TypeError):
            return 0


class ActionCommand(DictAccessibleModel):
    """Unified pre-rolled player action command produced by TurnService.prepare_and_roll_action."""
    model_config = ConfigDict(extra="allow", arbitrary_types_allowed=True)
    user_id: int = 0
    character_name: str = ""
    char: Dict[str, Any] = Field(default_factory=dict)
    label: str = "Action"
    text: str = "Action"
    type: str = "choice"
    choice_type: str = ""
    action_category: str = "general_action"
    intent: str = "general_action"
    sub_intent: str = ""
    stat: str = "NONE"
    requirement: int = 0
    mp_cost: int = 0
    mp_spent: int = 0
    gold_spent: int = 0
    rate: int = 100
    check: Any = None
    success: bool = True
    tier: str = "success"
    crit: bool = False
    roll: float = 100.0
    target_npc: Optional[str] = None
    target_node_id: str = ""
    target_location: str = ""
    ends_dialogue: bool = False
    dismisses_npc: bool = False
    combat_target: Optional[str] = None
    combat_tactical_archetype: str = ""
    spawns_npc_role: str = ""
    triggers_loot_roll: bool = False
    spell_id: str = ""
    is_quest_action: bool = False
    is_climax_action: bool = False
    breakthrough_leveraged: bool = False
    quest_id: str = ""
    sub_obj_id: Optional[str] = None
    stage_index: Optional[int] = None
    contract_type: str = ""
    item_name: str = ""
    item: Optional[Dict[str, Any]] = None
    item_consumed: bool = False
    active_recall: Optional[Any] = None


class CampaignEndGoal(BaseModel):
    id: str
    title: str
    description: str

class OpeningScene(DictAccessibleModel):
    model_config = ConfigDict(extra="allow")
    scene_title: str = Field(default="")
    entity_audit: EntityAudit = Field(default_factory=EntityAudit)
    narrative: str = Field(default="")
    choices: List[Choice] = Field(default_factory=list)
    campaign_end_goals: List[CampaignEndGoal] = Field(default_factory=list)
    story_quest_title: Optional[str] = Field(default=None)
    story_quest_objective: Optional[str] = Field(default=None)
    new_entities: List[NewEntity] = Field(default_factory=list)
    npcs_present: List[TrackerEntity] = Field(default_factory=list)
    npc_departures: List[str] = Field(default_factory=list)
    nearby_enemies: List[TrackerEntity] = Field(default_factory=list)
    merchant_encounter: Optional[MerchantEncounter] = None
    props: List[Union[PropUpdate, Dict[str, Any]]] = Field(default_factory=list)
    physical_updates: Optional[PhysicalUpdate] = None
    location: Optional[str] = None
    image_prompt: Optional[str] = None

    @field_validator("physical_updates", mode="before")
    @classmethod
    def coerce_physical_updates(cls, v: Any) -> Optional[Any]:
        if not v or not isinstance(v, (dict, BaseModel)):
            return None
        return v

    @field_validator("props", mode="before")
    @classmethod
    def coerce_props(cls, v: Any) -> List[Any]:
        if not v:
            return []
        if isinstance(v, dict):
            return [{"name": str(k), "state": str(val)} for k, val in v.items()]
        if isinstance(v, list):
            res = []
            for item in v:
                if isinstance(item, str) and item.strip():
                    res.append({"name": item.strip(), "state": "Present"})
                elif isinstance(item, dict):
                    res.append(item)
                elif hasattr(item, "model_dump"):
                    res.append(item)
            return res
        return []

