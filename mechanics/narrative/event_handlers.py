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
    try:
        from game_engine.quests import evaluate_quest_state_predicates, trigger_pending_retaliation_if_eligible
        evaluate_quest_state_predicates(event.session_id, user_id=event.party_uids[0] if event.party_uids else None)
        sess = db.get_session(event.session_id)
        if sess:
            trigger_pending_retaliation_if_eligible(event.session_id, event.new_location, session=sess)
    except Exception as e:
        log.warning(f"Error evaluating quest predicates on location changed: {e}")

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
    try:
        from game_engine.quests import evaluate_quest_state_predicates
        evaluate_quest_state_predicates(
            event.session_id,
            event_info={"type": "NPCStatusChanged", "name": event.name, "status": event.status}
        )
    except Exception as e:
        log.warning(f"Error evaluating quest predicates on npc status changed: {e}")

def handle_item_gifted(event: ItemGiftedEvent):
    # Lookup item metadata before removing from user inventory so wearable gifts equip cleanly
    inv = db.get_inventory(event.user_id) or []
    gifted_obj = next(
        (it for it in inv if isinstance(it, dict) and str(it.get("name", "")).lower() == str(event.item_name or "").lower()),
        None,
    )
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
    try:
        from mechanics.social.physical_state import apply_wearable_gift_to_npc
        apply_wearable_gift_to_npc(
            session_id=event.session_id,
            character_id=char_id,
            npc_name=npc_clean,
            item_dict=gifted_obj,
            item_name=event.item_name,
        )
    except Exception as e:
        log.warning(f"Error equipping wearable gift on {npc_clean}: {e}")
    try:
        from game_engine.quests import evaluate_quest_state_predicates
        evaluate_quest_state_predicates(event.session_id, user_id=event.user_id)
    except Exception as e:
        log.warning(f"Error evaluating quest predicates on item gifted: {e}")

def handle_item_gained(event: ItemGainedEvent):
    db.add_item(event.user_id, event.item_name, event.source, event.item_desc)
    try:
        from game_engine.quests import evaluate_quest_state_predicates
        evaluate_quest_state_predicates(event.session_id, user_id=event.user_id)
    except Exception as e:
        log.warning(f"Error evaluating quest predicates on item gained: {e}")

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
