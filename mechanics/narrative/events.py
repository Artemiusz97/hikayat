"""
Event Bus for decoupling domain state mutations.
Allows modules to publish events without tightly coupling to the database or other mechanics.
"""

from dataclasses import dataclass
from typing import Callable, Type, Dict, List, Any
import logging

log = logging.getLogger("hikayat.events")

class EventBus:
    def __init__(self):
        self._handlers: Dict[Type, List[Callable]] = {}
        
    def subscribe(self, event_type: Type, handler: Callable):
        if event_type not in self._handlers:
            self._handlers[event_type] = []
        self._handlers[event_type].append(handler)
        
    def publish(self, event: Any):
        handlers = self._handlers.get(type(event), [])
        for handler in handlers:
            try:
                handler(event)
            except Exception as e:
                log.exception(f"Error handling event {type(event).__name__}: {e}")

bus = EventBus()

# --- Core Events ---

@dataclass
class LocationChangedEvent:
    session_id: int
    old_location: str
    new_location: str
    party_uids: list[int]
    actions: list[dict]

@dataclass
class NPCSpawnedEvent:
    session_id: int
    name: str
    description: str
    appearance: dict
    disposition: str = "neutral"
    faction: str = ""
    traits: list = None
    motivation: str = ""
    mannerisms: str = ""
    race: str = "human"

@dataclass
class NPCStatusChangedEvent:
    session_id: int
    name: str
    status: str  # e.g., 'deceased', 'captured'
    
@dataclass
class ItemGiftedEvent:
    session_id: int
    user_id: int
    npc_name: str
    item_name: str
    
@dataclass
class ItemGainedEvent:
    session_id: int
    user_id: int
    item_name: str
    item_desc: str = ""
    source: str = ""
    
@dataclass
class FactionLeadershipChangedEvent:
    session_id: int
    faction_id: str
    new_leader_name: str
    new_roster: dict
    character_id: int
    title: str
    
@dataclass
class QuestCompletedEvent:
    session_id: int
    quest_id: str
    party_uids: list[int]
    result: dict = None
