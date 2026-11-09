from __future__ import annotations
import re
from typing import List, Optional, Dict, Literal, Any, Union
from pydantic import BaseModel, Field, ConfigDict, field_validator, model_validator

from .trackers import (
    DictAccessibleModel,
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


AgeGroup = Literal["teen", "adult"]


class CharacterBadges(DictAccessibleModel):
    model_config = ConfigDict(extra="ignore", populate_by_name=True)

    standing: str = ""           # "Freshman" | "Sophomore" | "Junior" | "Senior" | "Faculty" | "Staff" | "Citizen" | "Youth Peer"
    primary_role: str = ""       # Grounded public title ("Chemistry Teacher", "Student", "Flustered Cyclist")
    club: str = ""               # Formal club ("Broadcasting Club")
    clique: str = ""             # Social clique ("Athletes", "Musicians")
    badges: List[str] = Field(default_factory=list) # Visual badge pills in strict precedence order
    age_group: AgeGroup = "teen" # "teen" | "adult"

    # Typed Boolean Flags for UI & Business Logic
    is_student: bool = False
    is_faculty: bool = False
    is_staff: bool = False
    is_citizen: bool = False
    is_merchant: bool = False
    is_special_agent: bool = False
    is_contact: bool = False
    is_in_party: bool = False
    is_blocked: bool = False


_MALFORMED_CHOICE_LABEL_RE = re.compile(
    r"(?:"
    r"\\?(?:text|mathbf|mathrm|textnormal|ext)\s*\{"  # LaTeX tokens: \text{, text{, ext{
    r"|\b(?:stat|requirement|mp_cost)\s*:\s*['\"]?[a-zA-Z0-9]+['\"]?"  # Schema syntax leaks
    r"|\b(?:must\s+require\s+a\s+skill\s+check|dedicated\s+conversational\s+exit)\b"  # Leaked prompt rules
    r")",
    re.IGNORECASE,
)


def _filter_valid_choices_list(v: Any) -> List[Any]:
    if not v or not isinstance(v, list):
        return []
    cleaned = []
    for item in v:
        if isinstance(item, str):
            s = item.strip()
            if s and not _MALFORMED_CHOICE_LABEL_RE.search(s):
                cleaned.append({"label": s})
        elif isinstance(item, (dict, BaseModel)):
            if isinstance(item, dict):
                valid_keys = [str(k).strip() for k in item.keys() if str(k).strip()]
                lbl = str(item.get("label") or "").strip()
                if not valid_keys or not lbl or _MALFORMED_CHOICE_LABEL_RE.search(lbl):
                    continue
            elif hasattr(item, "label"):
                lbl = str(getattr(item, "label", "") or "").strip()
                if not lbl or _MALFORMED_CHOICE_LABEL_RE.search(lbl):
                    continue
            cleaned.append(item)
    return cleaned


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
    topic_id: Optional[str] = Field(default="")
    category: Optional[str] = Field(default="")

    @field_validator("topic_id", "category", mode="before")
    @classmethod
    def coerce_optional_seed_str(cls, v: Any) -> str:
        if v is None:
            return ""
        s = str(v).strip()
        if not s or s.lower() in ("null", "none", "undefined", "n/a"):
            return ""
        return s

    @field_validator("label", mode="before")
    @classmethod
    def coerce_label(cls, v: Any) -> str:
        if v is None:
            return "Take action"
        s = str(v).strip()
        if not s or _MALFORMED_CHOICE_LABEL_RE.search(s):
            return "Take action"
        return s
    target_npc: Optional[str] = Field(default="")
    target_node_id: Optional[str] = Field(default="")
    target_location: Optional[str] = Field(default="")
    ends_dialogue: bool = Field(default=False)
    dismisses_npc: bool = Field(default=False)
    quest_id: Optional[str] = Field(default="")
    incursion_action: Optional[str] = Field(default="")
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

    @field_validator("target_npc", "target_node_id", "target_location", "quest_id", "incursion_action", mode="before")
    @classmethod
    def coerce_str_empty(cls, v: Any) -> str:
        if v is None:
            return ""
        s = str(v).strip()
        return "" if s.lower() in ("none", "null", "undefined") else s

class PropUpdate(DictAccessibleModel):
    model_config = ConfigDict(extra="allow")
    name: str = Field(default="")
    state: str = Field(default="")

    @field_validator("name", "state", mode="before")
    @classmethod
    def coerce_str(cls, v: Any) -> str:
        return str(v).replace("\x00", "").strip()[:100] if v else ""

class ActorClothing(DictAccessibleModel):
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

class ActorUpdate(DictAccessibleModel):
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

class PhysicalUpdate(DictAccessibleModel):
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

class ClueDiscovery(DictAccessibleModel):
    model_config = ConfigDict(extra="allow")
    clue_id: Optional[str] = Field(default="")
    quest_id: Optional[str] = Field(default="")
    lead_text: str = Field(default="", description="Concrete investigative evidence text")
    title: Optional[str] = Field(default="Evidence Lead")
    category: str = Field(default="physical", description="physical, testimonial, archival, digital, supernatural")
    linked_npc: Optional[str] = Field(default="")
    source_location: Optional[str] = Field(default="")
    importance: str = Field(default="medium")

class BreakthroughLeverage(DictAccessibleModel):
    model_config = ConfigDict(extra="allow")
    title: str = Field(default="Breakthrough Leverage")
    target_npc: str = Field(default="")
    quest_id: str = Field(default="")
    deduction_text: str = Field(default="")

class SubQuestDefinition(DictAccessibleModel):
    id: int
    archetype: str
    text: str
    waypoints: Optional[List[Dict[str, Any]]] = None

class NextStoryQuest(DictAccessibleModel):
    title: str = Field(..., description="Unique evocative Story Quest title")
    archetype: str = Field(..., description="Creative scenario-appropriate main quest archetype")
    objective: str = Field(..., description="Rich 2-3 sentence objective")
    sub_quests: List[SubQuestDefinition] = Field(default_factory=list)

class QuestUpdate(DictAccessibleModel):
    """Comprehensive defensive quest update schema supporting both legacy sub_objectives and 1 Main + 1-3 Optionals."""
    model_config = ConfigDict(extra="allow")
    quest_id: str = Field(default="SQ-Active")
    title: str = Field(default="Active Quest")
    quest_type: str = Field(default="Story Quest")
    archetype: str = Field(default="Story Quest")
    objective: str = Field(default="")
    status: str = Field(default="Active")
    progress: Optional[str] = None
    current_clues: Optional[str] = None
    reward_xp: Optional[int] = None
    reward_gold: Optional[int] = None
    reward_item: Optional[str] = None
    next_chapter_quest: Optional[NextStoryQuest] = None
    completed_sub_quest_ids: List[int] = Field(default_factory=list)
    goal_progress_updates: Dict[str, Any] = Field(default_factory=dict)
    sub_objectives: List[Dict[str, Any]] = Field(default_factory=list)
    optional_objectives: List[Dict[str, Any]] = Field(default_factory=list)
    completed_sub_objective_ids: List[Any] = Field(default_factory=list)

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

    @field_validator("reward_xp", "reward_gold", mode="before")
    @classmethod
    def _coerce_qu_rewards(cls, v: Any) -> Optional[int]:
        if v is None or v == "" or str(v).lower() in ("none", "null"):
            return None
        try:
            return int(v)
        except (ValueError, TypeError):
            return None

    @field_validator("completed_sub_quest_ids", mode="before")
    @classmethod
    def _coerce_sub_quest_ids(cls, v: Any) -> List[int]:
        if v is None or v == "":
            return []
        items = [v] if isinstance(v, (int, str)) else (list(v) if isinstance(v, list) else [])
        out = []
        for x in items:
            try:
                if str(x).strip().isdigit():
                    out.append(int(x))
            except Exception:
                pass
        return out

    @field_validator("goal_progress_updates", mode="before")
    @classmethod
    def coerce_goal_progress(cls, v: Any) -> Dict[str, Any]:
        if not isinstance(v, dict):
            return {}
        clean = {}
        for k, val in v.items():
            if "//" in str(k):
                continue
            try:
                clean[k] = int(val) if isinstance(val, (int, float, str)) and str(val).lstrip("-").isdigit() else val
            except Exception:
                clean[k] = val
        return clean

    @field_validator("sub_objectives", "optional_objectives", mode="before")
    @classmethod
    def _coerce_qu_obj_list(cls, v: Any) -> List[Dict[str, Any]]:
        if not v:
            return []
        if isinstance(v, dict):
            return [v]
        if not isinstance(v, list):
            return []
        out: List[Dict[str, Any]] = []
        for idx, item in enumerate(v, 1):
            if isinstance(item, dict):
                out.append(item)
            elif isinstance(item, str) and item.strip():
                out.append({"id": idx, "text": item.strip(), "completed": False})
        return out

    @field_validator("completed_sub_objective_ids", mode="before")
    @classmethod
    def _coerce_qu_ids(cls, v: Any) -> List[Any]:
        if v is None or v == "":
            return []
        if isinstance(v, (int, str)):
            return [v]
        return list(v) if isinstance(v, list) else []

class CastEvent(DictAccessibleModel):
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
        return _filter_valid_choices_list(v)


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
        return _filter_valid_choices_list(v)

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
        return _filter_valid_choices_list(v)

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
    topic_id: Optional[str] = Field(default="")
    category: Optional[str] = Field(default="")

    @field_validator("topic_id", "category", mode="before")
    @classmethod
    def coerce_optional_seed_str(cls, v: Any) -> str:
        if v is None:
            return ""
        s = str(v).strip()
        if not s or s.lower() in ("null", "none", "undefined", "n/a"):
            return ""
        return s
    target_npc: Optional[str] = Field(default="")
    target_node_id: Optional[str] = Field(default="")
    target_location: Optional[str] = Field(default="")
    ends_dialogue: bool = Field(default=False)
    dismisses_npc: bool = Field(default=False)
    quest_id: Optional[str] = Field(default="")
    incursion_action: Optional[str] = Field(default="")
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

    @field_validator("target_npc", "target_node_id", "target_location", "spawns_npc_role", "quest_id", "incursion_action", mode="before")
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


class CampaignEndGoal(DictAccessibleModel):
    model_config = ConfigDict(extra="allow")
    id: str = "G1"
    title: str = "Campaign Goal"
    description: str = ""

    @field_validator("id", "title", "description", mode="before")
    @classmethod
    def coerce_goal_str(cls, v: Any) -> str:
        return str(v or "").strip()


class PitchStub(DictAccessibleModel):
    """Lightweight Stage-1 Bounty board entry before player commitment."""
    model_config = ConfigDict(extra="allow")
    quest_id: str = ""
    title: str = ""
    engine: str = "MYSTERY_CASE"
    public_pitch: str = ""
    client_npc: str = ""
    client_location: str = ""
    origin_location: str = ""
    reward_gold: int = 25
    reward_xp: int = 100
    reward_item: str = ""
    danger_tier: int = 1
    deadline_day: Optional[int] = None
    deadline_minute: Optional[int] = None
    uses_nsfw_routing: bool = False


class DossierLeadNode(DictAccessibleModel):
    model_config = ConfigDict(extra="allow")
    lead_id: str = ""
    optional_id: str = ""
    sub_obj_id: int = 1
    title: str = ""
    role: str = "aid"
    is_optional: bool = True
    stakes_hint: str = ""
    target_npc: str = ""
    target_location: str = ""
    approaches: List[Dict[str, Any]] = Field(default_factory=list)
    encounter_roster: List[Dict[str, Any]] = Field(default_factory=list)
    field_bonus: Dict[str, Any] = Field(default_factory=dict)
    rival_faction_slug: str = ""
    opposing_faction_slug: str = ""
    unlock_trigger: str = ""
    bonus_claimed: bool = False
    lockout_reason: str = ""
    status: str = "active"  # active | completed | failed | bypassed | locked | locked_out
    is_discovered: bool = True

    @field_validator(
        "lead_id", "optional_id", "title", "role", "stakes_hint",
        "target_npc", "target_location", "rival_faction_slug",
        "opposing_faction_slug", "unlock_trigger", "lockout_reason", "status",
        mode="before",
    )
    @classmethod
    def _coerce_lead_str(cls, v: Any) -> str:
        if v is None:
            return ""
        return str(v).strip()

    @field_validator("is_optional", "bonus_claimed", "is_discovered", mode="before")
    @classmethod
    def _coerce_lead_bool(cls, v: Any) -> bool:
        return _coerce_bool_value(v)

    @field_validator("approaches", "encounter_roster", mode="before")
    @classmethod
    def _coerce_lists(cls, v: Any) -> List[Dict[str, Any]]:
        if not v or not isinstance(v, list):
            return []
        return [item for item in v if isinstance(item, dict)]

    @field_validator("field_bonus", mode="before")
    @classmethod
    def _coerce_bonus_dict(cls, v: Any) -> Dict[str, Any]:
        return dict(v) if isinstance(v, dict) else {}


class DossierClueEdge(DictAccessibleModel):
    model_config = ConfigDict(extra="allow")
    clue_key: str = ""
    clue_id: Optional[int] = None
    title: str = ""
    lead_text: str = ""
    paired_with: List[Any] = Field(default_factory=list)
    conclusion: str = ""
    unlocks_climax: bool = False
    reveals_twist: bool = False
    is_red_herring: bool = False


class QuestDossierSchema(DictAccessibleModel):
    """Full predetermined Stage-2 QuestDossier schema with dual dict/attr access."""
    model_config = ConfigDict(extra="allow")
    quest_id: str = ""
    engine: str = "MYSTERY_CASE"
    family_tier: str = "bounty"
    danger_tier: int = 1
    status_stage: str = "compiled"
    compiled_at_turn: int = 0
    pitch_stub: Dict[str, Any] = Field(default_factory=dict)
    cast_bindings: Dict[str, Any] = Field(default_factory=dict)
    leads_graph: List[DossierLeadNode] = Field(default_factory=list)
    clue_graph: List[DossierClueEdge] = Field(default_factory=list)
    climax_spec: Dict[str, Any] = Field(default_factory=dict)
    twist_spec: Dict[str, Any] = Field(default_factory=dict)
    tangible_item: Dict[str, Any] = Field(default_factory=dict)
    contract_economy: Dict[str, Any] = Field(default_factory=dict)
    turn_in_rules: Dict[str, Any] = Field(default_factory=dict)
    outcomes_matrix: Dict[str, Any] = Field(default_factory=dict)


class MicroDossierSchema(DictAccessibleModel):
    """Compact 1-2 beat dossier for RMR- Rumors and MNR- Minor Events."""
    model_config = ConfigDict(extra="allow")
    quest_id: str = ""
    engine: str = "MYSTERY_CASE"
    family_tier: str = "rumor"
    status_stage: str = "compiled"
    compiled_at_turn: int = 0
    leads_graph: List[DossierLeadNode] = Field(default_factory=list)
    outcomes_matrix: Dict[str, Any] = Field(default_factory=dict)


class DossierEnrichment(DictAccessibleModel):
    """Bounded utility-LLM flavor enrichment payload (never overrides deterministic graph topology)."""
    model_config = ConfigDict(extra="allow")
    title: str = ""
    public_pitch: str = ""
    objective_flavor: str = ""
    main_stage_labels: List[str] = Field(default_factory=list)
    lead_titles: List[str] = Field(default_factory=list)
    lead_descriptions: List[str] = Field(default_factory=list)
    stakes_hints: List[str] = Field(default_factory=list)
    twist_summary: str = ""
    climax_hook: str = ""

    @field_validator("title", "public_pitch", "objective_flavor", "twist_summary", "climax_hook", mode="before")
    @classmethod
    def _coerce_str(cls, v: Any) -> str:
        if v is None:
            return ""
        s = str(v).strip()
        return "" if s.lower() in ("none", "null", "undefined") else s

    @field_validator("main_stage_labels", "lead_titles", "lead_descriptions", "stakes_hints", mode="before")
    @classmethod
    def _coerce_str_list(cls, v: Any) -> List[str]:
        if not v:
            return []
        if isinstance(v, str):
            return [v.strip()] if v.strip() else []
        if not isinstance(v, list):
            return []
        return [str(x).strip() for x in v if str(x or "").strip()]





class CampaignSpineEnrichment(DictAccessibleModel):
    """Bounded utility-LLM flavor enrichment for macro 11-chapter CampaignSpine."""
    model_config = ConfigDict(extra="ignore")
    mastermind_name: str = ""
    mastermind_title: str = ""
    mastermind_goal: str = ""
    omen_sign: str = ""

    @field_validator("mastermind_name", "mastermind_title", "mastermind_goal", "omen_sign", mode="before")
    @classmethod
    def _coerce_spine_str(cls, v: Any) -> str:
        return str(v or "").strip()

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

    @model_validator(mode="before")
    @classmethod
    def coerce_opening_scene_payload(cls, data: Any) -> Any:
        if not isinstance(data, dict):
            return data
        d = dict(data)
        raw_nar = d.get("narrative")
        nar_str = (
            "\n\n".join(str(x).strip() for x in raw_nar if str(x).strip())
            if isinstance(raw_nar, list)
            else str(raw_nar or "").strip()
        )
        if not nar_str:
            out_nar = str(d.get("outcome_narrative") or "").strip()
            nxt_nar = str(d.get("next_narrative") or "").strip()
            if out_nar and nxt_nar and out_nar != nxt_nar:
                nar_str = f"{out_nar}\n\n{nxt_nar}"
            else:
                nar_str = str(
                    out_nar
                    or nxt_nar
                    or d.get("scene_text")
                    or d.get("story")
                    or d.get("description")
                    or ""
                ).strip()
        d["narrative"] = nar_str

        if not d.get("choices"):
            d["choices"] = d.get("next_choices") or d.get("actions") or d.get("options") or []

        if not d.get("entity_audit") or not isinstance(d.get("entity_audit"), (dict, BaseModel)):
            d["entity_audit"] = {}

        goals = d.get("campaign_end_goals")
        if isinstance(goals, dict):
            goals = [goals]
        if isinstance(goals, list):
            coerced_goals = []
            for idx, g in enumerate(goals, 1):
                if isinstance(g, str) and g.strip():
                    coerced_goals.append({"id": f"G{idx}", "title": g.strip(), "description": ""})
                elif isinstance(g, dict):
                    title_v = str(g.get("title") or g.get("name") or g.get("goal") or f"Goal {idx}").strip()
                    coerced_goals.append({
                        "id": str(g.get("id") or f"G{idx}").strip(),
                        "title": title_v,
                        "description": str(g.get("description") or "").strip(),
                    })
                elif hasattr(g, "model_dump"):
                    coerced_goals.append(g)
            d["campaign_end_goals"] = coerced_goals
        else:
            d["campaign_end_goals"] = []
        return d

    @field_validator("scene_title", "narrative", mode="before")
    @classmethod
    def coerce_opening_text_fields(cls, v: Any) -> str:
        if not v:
            return ""
        if isinstance(v, str):
            return v.strip()
        if isinstance(v, list):
            return "\n\n".join(str(x).strip() for x in v if str(x).strip())
        return str(v).strip()

    @field_validator("choices", mode="before")
    @classmethod
    def coerce_opening_choices(cls, v: Any) -> List[Any]:
        return _filter_valid_choices_list(v)

    @field_validator("npcs_present", "nearby_enemies", mode="before")
    @classmethod
    def coerce_opening_entity_lists(cls, v: Any) -> List[Any]:
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

    @field_validator("new_entities", mode="before")
    @classmethod
    def coerce_opening_new_entities(cls, v: Any) -> List[Any]:
        if not v or not isinstance(v, list):
            return []
        cleaned = []
        for item in v:
            if isinstance(item, str) and item.strip():
                cleaned.append({"name": item.strip()})
            elif isinstance(item, (dict, BaseModel)):
                if isinstance(item, dict) and not str(item.get("name") or "").strip():
                    continue
                cleaned.append(item)
        return cleaned

    @field_validator("npc_departures", mode="before")
    @classmethod
    def coerce_opening_departures(cls, v: Any) -> List[str]:
        if not v or not isinstance(v, list):
            return []
        return [str(x).strip() for x in v if str(x or "").strip()]

    @field_validator("merchant_encounter", mode="before")
    @classmethod
    def coerce_opening_merchant(cls, v: Any) -> Optional[Any]:
        return TurnOutcome.coerce_merchant_encounter(v)

    @field_validator("image_prompt", mode="before")
    @classmethod
    def coerce_opening_image_prompt(cls, v: Any) -> Optional[str]:
        return TurnOutcome.coerce_image_prompt(v)

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

