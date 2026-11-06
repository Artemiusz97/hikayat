from __future__ import annotations

import json
from typing import Any, Optional
from pydantic import BaseModel, ConfigDict, Field, field_validator


class DictAccessibleModel(BaseModel):
    """Base Pydantic model guaranteeing dual-access parity (obj.field & obj['field'] / obj.get())."""
    model_config = ConfigDict(extra="ignore", populate_by_name=True)

    def __getitem__(self, item: str) -> Any:
        try:
            return getattr(self, item)
        except AttributeError as exc:
            raise KeyError(item) from exc

    def get(self, item: str, default: Any = None) -> Any:
        return getattr(self, item, default)


class EventModifierSpec(DictAccessibleModel):
    """Modifier specifications produced by macro events and rumors, clamped to safe game boundaries."""
    dc_modifiers: dict[str, int] = Field(default_factory=dict)
    price_multiplier: float = 1.0
    arousal_multiplier: float = 1.0
    faction_rep_delta: int = 0
    virtual_faction_rep: dict[str, int] = Field(default_factory=dict)
    lockdown_nodes: list[str] = Field(default_factory=list)
    is_locked: bool = False
    stealth_modifier: int = 0
    crowd_density: str = ""

    @field_validator("dc_modifiers", mode="before")
    @classmethod
    def _validate_dc_modifiers(cls, v: Any) -> dict[str, int]:
        if not v or not isinstance(v, dict):
            return {}
        clamped: dict[str, int] = {}
        for k, val in v.items():
            stat_name = str(k).upper().strip()
            try:
                num = int(val)
                clamped[stat_name] = max(-4, min(4, num))
            except (TypeError, ValueError):
                continue
        return clamped

    @field_validator("price_multiplier", mode="before")
    @classmethod
    def _validate_price_multiplier(cls, v: Any) -> float:
        if v in (None, ""):
            return 1.0
        try:
            val = float(v)
            return max(0.5, min(2.0, val))
        except (TypeError, ValueError):
            return 1.0

    @field_validator("arousal_multiplier", mode="before")
    @classmethod
    def _validate_arousal_multiplier(cls, v: Any) -> float:
        if v in (None, ""):
            return 1.0
        try:
            val = float(v)
            return max(0.5, min(2.0, val))
        except (TypeError, ValueError):
            return 1.0

    @field_validator("stealth_modifier", mode="before")
    @classmethod
    def _validate_stealth_modifier(cls, v: Any) -> int:
        if v in (None, ""):
            return 0
        try:
            val = int(v)
            return max(-4, min(4, val))
        except (TypeError, ValueError):
            return 0


class WorldEventRecord(DictAccessibleModel):
    """Normalized procedural macro event or rumor record matching SQLite world_events table."""
    id: Optional[int] = None
    session_id: int
    event_key: str
    template_key: str = ""
    entity_type: str = "macro_event"
    event_subtype: str = "crisis"
    title: str = ""
    description: str = ""
    sfw_fallback_description: str = ""
    faction_id: str = ""
    implicated_contact_id: Optional[int] = None
    location_node_id: str = ""
    location_name: str = ""
    is_discovered: bool = False
    discovery_source: str = ""
    discovered_turn: Optional[int] = None
    claimed_turn: Optional[int] = None
    linked_quest_id: str = ""
    status: str = "active"
    prior_status_before_resolve: str = "active"
    turn_created: int = 1
    resolved_turn: Optional[int] = None
    original_expires_day: Optional[int] = None
    original_expires_minute: Optional[int] = None
    expires_day: Optional[int] = None
    expires_minute: Optional[int] = None
    escalation_chance: float = 0.0
    escalation_event_key: str = ""
    is_nsfw: bool = False
    modifiers: EventModifierSpec = Field(default_factory=EventModifierSpec)
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: float = 0.0
    updated_at: float = 0.0

    @field_validator("modifiers", mode="before")
    @classmethod
    def _coerce_modifiers(cls, v: Any) -> Any:
        if isinstance(v, EventModifierSpec):
            return v
        if isinstance(v, str):
            try:
                v = json.loads(v or "{}")
            except Exception:
                v = {}
        if isinstance(v, dict):
            return EventModifierSpec(**v)
        return EventModifierSpec()

    @field_validator("metadata", mode="before")
    @classmethod
    def _coerce_metadata(cls, v: Any) -> dict[str, Any]:
        if isinstance(v, str):
            try:
                parsed = json.loads(v or "{}")
                return parsed if isinstance(parsed, dict) else {}
            except Exception:
                return {}
        if isinstance(v, dict):
            return v
        return {}


class WorldPityState(DictAccessibleModel):
    """Session-scoped procedural event and rumor pity counters and scandal states."""
    event_pity_counter: float = 0.0
    rumor_pity_counter: float = 0.0
    minor_event_pity_counter: float = 0.0
    player_scandal_cooldown_until_day: int = 0
    recent_witness_catches: list[Any] = Field(default_factory=list)
    npc_gossip_shared_today: dict[str, Any] = Field(default_factory=dict)


class WorldPulseClientPayload(DictAccessibleModel):
    """API & WebSocket payload structure consumed by React SPA and Discord views."""
    session_id: int
    current_day: int = 1
    current_minute: int = 480
    active_macro_events: list[WorldEventRecord] = Field(default_factory=list)
    active_rumors: list[WorldEventRecord] = Field(default_factory=list)
    active_minor_events: list[WorldEventRecord] = Field(default_factory=list)
    all_events: list[WorldEventRecord] = Field(default_factory=list)
    can_track_rumor: bool = True
    tracked_rumor_count: int = 0
    max_tracked_rumors: int = 2
    can_track_minor_bounty: bool = True
    tracked_minor_bounty_count: int = 0
    max_tracked_minor_bounties: int = 2
    event_pity_counter: float = 0.0
    rumor_pity_counter: float = 0.0
    minor_event_pity_counter: float = 0.0
    recent_events_feed: list[dict[str, Any]] = Field(default_factory=list)


WorldPulsePayload = WorldPulseClientPayload


class WorldEventsSnapshot(DictAccessibleModel):
    """Single-roundtrip snapshot prefetch structure for TurnService and pure modifiers."""
    session_id: int = 0
    active_macro_events: list[dict[str, Any]] = Field(default_factory=list)
    active_rumors: list[dict[str, Any]] = Field(default_factory=list)
    active_minor_events: list[dict[str, Any]] = Field(default_factory=list)
    discovered_rumors: list[dict[str, Any]] = Field(default_factory=list)
    all_events: list[dict[str, Any]] = Field(default_factory=list)
    pity_state: WorldPityState = Field(default_factory=WorldPityState)
