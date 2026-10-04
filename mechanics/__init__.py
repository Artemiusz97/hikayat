import sys
from .combat import equipment, items, spells, traits, enemies, merchant
from .social import persona, relationships, genealogy, school_roster, factions, races, physical_state, attributes
from .world import locations, waypoints, world_forge, mobility
from .narrative import events, event_handlers, clues, bounty, intent, choice_generator
from .system import memory, phone, save_system, time_engine, concurrency

_MODS = [
    ("equipment", equipment), ("items", items), ("spells", spells), ("traits", traits),
    ("enemies", enemies), ("merchant", merchant),
    ("persona", persona), ("relationships", relationships), ("genealogy", genealogy),
    ("school_roster", school_roster), ("factions", factions), ("races", races),
    ("physical_state", physical_state), ("attributes", attributes),
    ("locations", locations), ("waypoints", waypoints), ("world_forge", world_forge),
    ("mobility", mobility),
    ("events", events), ("event_handlers", event_handlers), ("clues", clues),
    ("bounty", bounty), ("intent", intent), ("choice_generator", choice_generator),
    ("memory", memory), ("phone", phone), ("save_system", save_system),
    ("time_engine", time_engine), ("concurrency", concurrency),
]

for name, mod in _MODS:
    sys.modules[f"mechanics.{name}"] = mod
