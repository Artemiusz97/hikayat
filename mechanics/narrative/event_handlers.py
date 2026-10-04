import logging
import db
from mechanics.narrative.events import (
    bus,
    LocationChangedEvent,
    NPCSpawnedEvent,
    NPCStatusChangedEvent,
    ItemGiftedEvent,
    ItemGainedEvent,
    FactionLeadershipChangedEvent,
    QuestCompletedEvent
)

log = logging.getLogger("hikayat.event_handlers")

def handle_location_changed(event: LocationChangedEvent):
    # This might trigger passive encounters, but for now we just log it or handle specific hooks.
    log.info(f"Session {event.session_id} party moved from {event.old_location} to {event.new_location}")

def handle_npc_spawned(event: NPCSpawnedEvent):
    db.upsert_lorebook_entity(
        session_id=event.session_id,
        entity_type="person",
        name=event.name.strip(),
        description=event.description,
        disposition=event.disposition,
        faction=event.faction,
        traits=event.traits or [],
        motivation=event.motivation,
        mannerisms=event.mannerisms,
        race=event.race,
        appearance=event.appearance
    )

def handle_npc_status_changed(event: NPCStatusChangedEvent):
    db.upsert_lorebook_entity(
        session_id=event.session_id,
        entity_type="person",
        name=event.name.strip(),
        status=event.status
    )

def handle_item_gifted(event: ItemGiftedEvent):
    # The gift is given, we remove from user and modify contact disposition
    db.remove_item_by_name(event.user_id, event.item_name)
    char = db.get_character(event.user_id)
    char_id = char["id"] if char else 0
    npc_clean = (event.npc_name or "NPC").strip()
    db.upsert_contact(
        session_id=event.session_id,
        npc_id=npc_clean.lower().replace(" ", "_"),
        name=npc_clean,
        character_id=char_id,
        delta_score=2,  # Gifting gives +2 disposition
    )

def handle_item_gained(event: ItemGainedEvent):
    db.add_item(event.user_id, event.item_name, event.source, event.item_desc)

def handle_faction_leadership_changed(event: FactionLeadershipChangedEvent):
    db.update_faction_leadership_roster(event.session_id, event.faction_id, event.new_roster)
    db.set_character_faction_membership(event.character_id, event.faction_id, 3, event.title) # 3 is leader rank
    db.update_session(event.session_id, extra={"pending_promotion": None})

def handle_quest_completed(event: QuestCompletedEvent):
    event.result = db.claim_quest_reward(event.session_id, event.quest_id, event.party_uids)

# Register Handlers
bus.subscribe(LocationChangedEvent, handle_location_changed)
bus.subscribe(NPCSpawnedEvent, handle_npc_spawned)
bus.subscribe(NPCStatusChangedEvent, handle_npc_status_changed)
bus.subscribe(ItemGiftedEvent, handle_item_gifted)
bus.subscribe(ItemGainedEvent, handle_item_gained)
bus.subscribe(FactionLeadershipChangedEvent, handle_faction_leadership_changed)
bus.subscribe(QuestCompletedEvent, handle_quest_completed)
