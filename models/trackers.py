from typing import List, Optional, Dict, Literal, Any, Union
from pydantic import BaseModel, Field, ConfigDict, model_validator, field_validator

class Appearance(BaseModel):
    model_config = ConfigDict(extra="allow")

    eye_color: Optional[str] = None
    hair_color: Optional[str] = None
    hair_length: Optional[str] = None
    hair_style: Optional[str] = None
    stature: Optional[str] = None
    skin_color: Optional[str] = None
    skin_type: Optional[str] = None
    coat_color: Optional[str] = None
    distinctive_features: Optional[str] = None
    outfit_style: Optional[str] = None
    breast_size: Optional[str] = None
    penis_size: Optional[str] = None
    intimate_demeanor: Optional[str] = None
    intimate_dynamic: Optional[str] = None
    sensitive_spots: Optional[str] = None
    turn_ons: Optional[str] = None
    fetishes: Optional[str] = None
    intercourse_experience: Optional[str] = None
    oral_experience: Optional[str] = None

class TrackerEntity(BaseModel):
    model_config = ConfigDict(extra="allow")

    name: str = Field(..., description="Exact character or entity name")
    role: Optional[str] = Field(default=None, description="Character role, title, or occupation")
    occupation: Optional[str] = Field(default=None)
    description: Optional[str] = Field(default=None, description="Brief identity or narrative summary")
    disposition: Optional[str] = Field(default=None, description="friendly, neutral, or hostile")
    faction: Optional[str] = Field(default=None, description="Faction or organization affiliation")
    club: Optional[str] = Field(default=None, description="School club or student organization")
    club_role: Optional[str] = Field(default=None, description="Position within club or faction, e.g. President, Captain")
    grade: Optional[str] = Field(default=None, description="Academic year or standing, e.g. Senior, Junior")
    clique: Optional[str] = Field(default=None, description="Social clique or group")
    race: Optional[str] = Field(default=None)
    gender: Optional[str] = Field(default=None)
    age: Optional[Union[int, str]] = Field(default=None)
    mannerisms: Optional[str] = Field(default=None)
    motivation: Optional[str] = Field(default=None)
    traits: List[str] = Field(default_factory=list)
    preferences: List[str] = Field(default_factory=list)
    appearance: Optional[Union[Appearance, Dict[str, Any], str]] = Field(default=None)
    level: Optional[int] = Field(default=None, description="Only if friendly companion or scaling enemy")
    hp: Optional[int] = Field(default=None)
    max_hp: Optional[int] = Field(default=None)
    mp: Optional[int] = Field(default=None)
    status_effects: List[str] = Field(default_factory=list, description="Short condition or mood tags (e.g. Bleeding, Stunned, Flustered, Angry, Scared, Aroused, Calm)")
    mood: Optional[str] = Field(default=None, description="Current emotional mood or state (e.g. Angry, Confused, Scared, Flustered, Aroused, Calm, Neutral)")


    @field_validator("level", mode="before")
    @classmethod
    def coerce_level(cls, v: Any) -> Optional[int]:
        """Ensure level is never None or <=0 when present; default hostile entities to 1."""
        if v is None:
            return 1
        try:
            v = int(v)
        except (TypeError, ValueError):
            return 1
        return max(1, v)

    @model_validator(mode="before")
    @classmethod
    def coerce_from_str(cls, data: Any) -> Any:
        if isinstance(data, str):
            return {"name": data.strip()}
        return data

class CharacterOutcome(BaseModel):
    name: str = Field(..., description="Exact character name")
    hp_change: int = Field(default=0)
    temp_hp_change: int = Field(default=0)
    mp_change: int = Field(default=0)
    gold_change: int = Field(default=0)
    items_gained: List[str] = Field(default_factory=list)
    items_lost: List[str] = Field(default_factory=list)
    status_effects: List[str] = Field(default_factory=list, description="Short condition tags")

    @field_validator("hp_change", "temp_hp_change", "mp_change", "gold_change", mode="before")
    @classmethod
    def coerce_int_zero(cls, v: Any) -> int:
        if v is None:
            return 0
        try:
            return int(v)
        except (TypeError, ValueError):
            return 0

class EntityAudit(BaseModel):
    present_named_characters: List[str] = Field(default_factory=list, description="EVERY named individual physically present in the immediate room right now")
    speaking_characters: List[str] = Field(default_factory=list, description="NPCs who speak aloud in this scene")
    departed_characters: List[str] = Field(default_factory=list, description="NPCs who departed, exited, said goodbye, or left during this turn")

class NewEntity(BaseModel):
    model_config = ConfigDict(extra="allow")

    type: str = Field(default="person", description="person, place, or faction")
    name: str = Field(..., description="Token if new")
    role: Optional[str] = None
    occupation: Optional[str] = None
    faction: Optional[str] = None
    club: Optional[str] = None
    club_role: Optional[str] = None
    grade: Optional[str] = None
    clique: Optional[str] = None
    location: Optional[str] = None
    race: Optional[str] = None
    gender: Optional[str] = None
    age: Optional[Union[int, str]] = None
    appearance: Optional[Union[Appearance, Dict[str, Any], str]] = None
    description: Optional[str] = None
    disposition: Optional[str] = None
    traits: List[str] = Field(default_factory=list, description="2-3 traits")
    preferences: List[str] = Field(default_factory=list)
    motivation: Optional[str] = None
    mannerisms: Optional[str] = None

class MerchantEncounter(BaseModel):
    model_config = ConfigDict(extra="allow")

    present: bool = False
    name: Optional[str] = None
    description: Optional[str] = None

    @model_validator(mode="before")
    @classmethod
    def coerce_merchant_dict(cls, data: Any) -> Any:
        if not data:
            return {"present": False}
        if isinstance(data, dict):
            # Check for dummy/filler keys e.g. {'_this_field_is_intentionally_left_blank...': 'OK'}
            has_valid_info = bool(data.get("name") or data.get("description") or data.get("goods"))
            if "present" not in data:
                return {"present": has_valid_info, "name": data.get("name"), "description": data.get("description")}
            p_val = data["present"]
            if isinstance(p_val, str):
                data["present"] = p_val.lower() in ("true", "1", "yes")
        return data

class RelationshipUpdate(BaseModel):
    model_config = ConfigDict(extra="allow")

    npc_name: str
    delta_score: int = Field(default=0, description="-10 to +10")
    track: Optional[Literal["platonic", "romantic"]] = None
    role: Optional[str] = None
    description: Optional[str] = None
    faction: Optional[str] = None
    club: Optional[str] = None
    club_role: Optional[str] = None
    grade: Optional[str] = None
    milestone_event: Optional[Literal["first_kiss", "kiss", "date", "confession", "oral_give", "oral_receive", "intercourse", "none"]] = None
    memory_summary: Optional[str] = None
    revealed_attributes: List[str] = Field(default_factory=list)
    intimate_revealed: Optional[bool] = None
    sensitive_spots_revealed: Optional[bool] = None
    turn_ons_revealed: Optional[bool] = None
    fetishes_revealed: Optional[bool] = None
    demeanor_revealed: Optional[bool] = None
    dynamic_revealed: Optional[bool] = None
    intercourse_revealed: Optional[bool] = None
    oral_revealed: Optional[bool] = None
    intercourse_experience: Optional[str] = None
    oral_experience: Optional[str] = None
    new_sensitive_spots: Optional[str] = None
    new_turn_ons: Optional[str] = None
    new_fetishes: Optional[str] = None
    new_demeanor: Optional[str] = None
    new_dynamic: Optional[str] = None
    new_traits: List[str] = Field(default_factory=list)
    new_preferences: List[str] = Field(default_factory=list)

    @field_validator("delta_score", mode="before")
    @classmethod
    def coerce_delta_score(cls, v: Any) -> int:
        if v is None:
            return 0
        try:
            return int(v)
        except (TypeError, ValueError):
            return 0

class FactionUpdate(BaseModel):
    faction_name: str
    delta_score: int = Field(default=0)
    notes: Optional[str] = None

    @field_validator("delta_score", mode="before")
    @classmethod
    def coerce_delta_score(cls, v: Any) -> int:
        if v is None:
            return 0
        try:
            return int(v)
        except (TypeError, ValueError):
            return 0

