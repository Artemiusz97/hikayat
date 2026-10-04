from typing import List, Optional, Dict, Literal, Any, Union
from pydantic import BaseModel, Field, ConfigDict, field_validator

from .trackers import (
    EntityAudit, CharacterOutcome, TrackerEntity,
    NewEntity, MerchantEncounter, RelationshipUpdate, FactionUpdate
)

_VALID_STATS = {"STR", "PER", "END", "CHA", "INT", "AGI", "LUK", "ITEM", "NONE", "FREE"}

class Choice(BaseModel):
    label: str = Field(..., description="Concise, max 6-8 words")
    stat: str = Field(default="NONE")  # Accept any string; validated below
    requirement: int = Field(default=0, ge=0, le=20)
    mp_cost: int = Field(default=0)

    @field_validator("stat", mode="before")
    @classmethod
    def coerce_stat(cls, v: Any) -> str:
        s = str(v).upper().strip() if v else "NONE"
        return s if s in _VALID_STATS else "NONE"

    @field_validator("requirement", "mp_cost", mode="before")
    @classmethod
    def coerce_int_zero(cls, v: Any) -> int:
        if v is None:
            return 0
        try:
            return int(v)
        except (TypeError, ValueError):
            return 0

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
            return v
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

class DictAccessibleModel(BaseModel):
    """Base Pydantic model that provides dict-like subscripting and .get() for legacy consumer compatibility."""
    def __getitem__(self, item: str) -> Any:
        try:
            return getattr(self, item)
        except AttributeError:
            raise KeyError(item)

    def get(self, item: str, default: Any = None) -> Any:
        return getattr(self, item, default)


class NarrationOutcome(DictAccessibleModel):
    model_config = ConfigDict(extra="allow")
    outcome_narrative: str = Field(default="")
    next_narrative: str = Field(default="")
    scene_title: str = Field(default="")
    next_choices: List[Choice] = Field(default_factory=list)

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
    merchant_encounter: Optional[MerchantEncounter] = None
    faction_updates: List[FactionUpdate] = Field(default_factory=list)
    faction_promotion_result: Optional[str] = None
    image_prompt: Optional[str] = None

    @field_validator("outcome_narrative", "next_narrative", "scene_title", "location", mode="before")
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

class ActionClassification(DictAccessibleModel):
    stat: str = Field(default="NONE")
    requirement: int = Field(default=6, ge=0, le=20)
    mp_cost: int = Field(default=0)
    is_memory_recall: bool = Field(default=False)
    recall_query: Optional[str] = None
    reasoning: Optional[str] = None

    @field_validator("stat", mode="before")
    @classmethod
    def coerce_stat(cls, v: Any) -> str:
        s = str(v).upper().strip() if v else "NONE"
        return s if s in _VALID_STATS else "NONE"

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

