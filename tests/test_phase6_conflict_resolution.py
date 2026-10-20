import pytest
import db
import game_engine
from game_engine.quests import resolve_pre_turn_quests_and_clues
from game_engine.state.reducers import (
    _reduce_quests_and_waypoints,
    _reduce_deterministic_waypoints,
)
from game_engine.state.social import (
    resolve_pre_turn_social_and_disclosures,
    _reduce_social_and_milestones,
)
from game_engine.npcs.stage_manager import _spawn_canonical_role_npc_pre_turn


def test_pre_turn_quest_does_not_double_advance_or_lose_reward_item():
    """Conflict 1: Pre-turn waypoint advancement must not cascade a second stage post-turn,
    and pre-turn completed quests must grant their reward_item and preserve _quest_reward_notices."""
    db.init_db()
    session_id = 99001
    user_id = 99001
    with db.get_conn() as conn:
        conn.execute(
            "INSERT OR REPLACE INTO sessions (id, host_user_id, status, mode, capacity, scenario, current_location) "
            "VALUES (?, ?, 'active', 'single', 1, 'fantasy', 'Town ➔ Watchtower')",
            (session_id, user_id),
        )
        conn.execute(
            "INSERT OR REPLACE INTO characters (user_id, name, char_class, race, gender, hp, max_hp, mp, max_mp, str_, agi, end_, int_, per_, cha, luk, active_session_id) "
            "VALUES (?, 'Alden', 'Warrior', 'Human', 'M', 30, 30, 15, 15, 6, 6, 6, 6, 6, 6, 5, ?)",
            (user_id, session_id),
        )

    # Quest 1: 2-stage arrival quest at the same location (must advance only Stage 1 -> Stage 2 on 1 turn)
    db.upsert_quest(
        session_id=session_id,
        quest_id="Q-TWO-STAGE",
        quest_type="Side Bounty",
        title="Scout the Watchtower",
        objective="Scout twice",
        progress="0/2",
        current_clues="",
        status="Active",
        reward_xp=100,
        reward_gold=40,
    )
    db.save_quest_waypoints(
        session_id=session_id,
        quest_id="Q-TWO-STAGE",
        waypoints=[
            {"stage_index": 1, "stage_label": "Arrive at Watchtower", "target_location": "Town ➔ Watchtower", "completion_trigger": "arrival"},
            {"stage_index": 2, "stage_label": "Check upper floor", "target_location": "Town ➔ Watchtower", "completion_trigger": "arrival"},
        ],
        sub_obj_id=None,
    )

    # Quest 2: 1-stage arrival quest with a reward_item
    db.upsert_quest(
        session_id=session_id,
        quest_id="Q-REWARD-ITEM",
        quest_type="Side Bounty",
        title="Recover the Silver Signet",
        objective="Reach the Watchtower",
        progress="0/1",
        current_clues="",
        status="Active",
        reward_xp=120,
        reward_gold=50,
        reward_item="Silver Signet Ring",
    )
    db.save_quest_waypoints(
        session_id=session_id,
        quest_id="Q-REWARD-ITEM",
        waypoints=[
            {"stage_index": 1, "stage_label": "Reach Watchtower", "target_location": "Town ➔ Watchtower", "completion_trigger": "arrival"},
        ],
        sub_obj_id=None,
    )

    session = {"id": session_id, "current_location": "Town ➔ Watchtower", "scenario": "fantasy"}
    char = db.get_character(user_id)
    party = [(char, [])]
    actions = [{"label": "Travel to Watchtower", "stat": "FREE", "requirement": 0}]

    pre_q = resolve_pre_turn_quests_and_clues(session, party, actions)
    assert "Q-REWARD-ITEM" in pre_q["completed_quests"]
    assert "Q-TWO-STAGE" not in pre_q["completed_quests"]

    outcome = {
        "location": "Town ➔ Watchtower",
        "quest_updates": [{"quest_id": "Q-REWARD-ITEM", "status": "Completed"}],
        "_pre_turn_quests": pre_q,
        "_quest_reward_notices": list(pre_q["reward_notices"]),
        "_waypoint_notices": list(pre_q["waypoint_notices"]),
    }
    items_gained_by_user = {}
    _reduce_quests_and_waypoints(session_id, session, [user_id], outcome, actions, items_gained_by_user)
    _reduce_deterministic_waypoints(session_id, session, outcome, [user_id], actions)

    # Verify Q-TWO-STAGE is still on Stage 2 (not cascaded to complete in the same turn)
    active_wp = db.get_active_waypoint(session_id, "Q-TWO-STAGE", None)
    assert active_wp is not None
    assert active_wp["stage_index"] == 2

    # Verify Q-REWARD-ITEM granted its reward item once (no duplicate insertion) and preserved its reward notice
    assert any(rn.get("quest_id") == "Q-REWARD-ITEM" for rn in outcome.get("_quest_reward_notices", []))
    assert items_gained_by_user.get(user_id, []).count("Silver Signet Ring") == 1
    inv_items = [it for it in db.get_inventory(user_id) if it.get("name") == "Silver Signet Ring"]
    assert len(inv_items) == 1


def test_pre_turn_non_erotic_turn_blocks_narrative_prose_virginity_scraping():
    """Conflict 3: When pre-turn pipeline ran and classified the action as non-erotic,
    suggestive metaphors in LLM narrative prose must NOT trigger virginity loss."""
    db.init_db()
    session_id = 99002
    user_id = 99002
    with db.get_conn() as conn:
        conn.execute(
            "INSERT OR REPLACE INTO sessions (id, host_user_id, status, mode, capacity, scenario, current_location) "
            "VALUES (?, ?, 'active', 'single', 1, 'high_school', 'Campus ➔ Courtyard')",
            (session_id, user_id),
        )
        conn.execute(
            "INSERT OR REPLACE INTO characters (user_id, name, char_class, race, gender, hp, max_hp, mp, max_mp, str_, agi, end_, int_, per_, cha, luk, active_session_id) "
            "VALUES (?, 'Ren', 'Student', 'Human', 'M', 30, 30, 15, 15, 6, 6, 6, 6, 6, 6, 5, ?)",
            (user_id, session_id),
        )

    char = db.get_character(user_id)
    char_id = char["id"]

    db.upsert_contact(
        session_id=session_id,
        npc_id="elena_vance",
        name="Elena Vance",
        character_id=char_id,
        delta_score=40,
        track="romantic",
        appearance={"intercourse_experience": "virgin", "oral_experience": "inexperienced"},
    )

    session = {
        "id": session_id,
        "scenario": "high_school",
        "current_location": "Campus ➔ Courtyard",
        "dialogue_partner": "Elena Vance",
        "dialogue_partners": ["Elena Vance", "Maya Lin"],
        "current_npcs": [{"name": "Elena Vance", "role": "Classmate"}, {"name": "Maya Lin", "role": "Classmate"}],
    }
    actions = [{"label": "Chat warmly with Elena and Maya about the festival", "stat": "CHA", "requirement": 5, "check": {"succeeded": True, "tier": "success"}}]

    # Simulate LLM prose containing accidental substring that used to trip INTERCOURSE_KEYWORDS
    outcome = {
        "outcome_narrative": "Elena and Maya laugh warmly as they make love-themed decorations for the festival booth.",
        "next_narrative": "She smiles beside the banner.",
        "relationship_updates": [{"npc_name": "Elena Vance", "delta_score": 2, "_pre_turn_resolved": True}],
        "_pre_turn_social": {"affinity_deltas": {"Elena Vance": 2}},
        "_pre_turn_intimacy": {"action_classified": {"act_type": "none"}},
    }

    _reduce_social_and_milestones(
        session_id=session_id,
        session=session,
        party=[(char, [])],
        outcome=outcome,
        actions=actions,
        scen_key="high_school",
        items_gained_by_user={},
        first_char_id=char_id,
        first_char_name="Ren",
    )

    updated_contact = db.get_contact(session_id, "Elena Vance", char_id)
    assert updated_contact["appearance"].get("intercourse_experience") == "virgin"
    # Verify pre-turn affinity delta was preserved without double calculation
    assert outcome["relationship_updates"][0]["delta_score"] == 2


def test_spawn_canonical_role_npc_syncs_lorebook_and_commitments_resolve():
    """Conflict 4: Pre-turn spawned role NPCs must be added to lorebook, and active commitments
    must resolve deterministically pre-turn."""
    db.init_db()
    session_id = 99003
    user_id = 99003
    with db.get_conn() as conn:
        conn.execute(
            "INSERT OR REPLACE INTO sessions (id, host_user_id, status, mode, capacity, scenario, current_location) "
            "VALUES (?, ?, 'active', 'single', 1, 'fantasy', 'Market ➔ Apothecary')",
            (session_id, user_id),
        )
        conn.execute(
            "INSERT OR REPLACE INTO characters (user_id, name, char_class, race, gender, hp, max_hp, mp, max_mp, str_, agi, end_, int_, per_, cha, luk, active_session_id) "
            "VALUES (?, 'Kael', 'Rogue', 'Human', 'M', 30, 30, 15, 15, 6, 6, 6, 6, 6, 6, 5, ?)",
            (user_id, session_id),
        )

    char = db.get_character(user_id)

    session = {"id": session_id, "scenario": "fantasy", "current_location": "Market ➔ Apothecary"}
    spawned = _spawn_canonical_role_npc_pre_turn(session, "alchemist", "Market ➔ Apothecary")
    npc_name = spawned["name"]

    lore_entries = db.get_lorebook(session_id)
    assert any(e.get("name") == npc_name for e in lore_entries.get("person", []))

    # Add an active commitment with this NPC and fulfill it pre-turn
    from db.memory import add_commitment
    cm = add_commitment(session_id, "player", npc_name, "promise", f"Deliver rare herbs to {npc_name}", turn_number=1)
    assert cm.get("id")

    session["current_npcs"] = [spawned]
    session["dialogue_partners"] = [npc_name]
    actions = [{"label": f"Deliver the rare herbs and fulfill promise to {npc_name}", "stat": "CHA", "check": {"succeeded": True, "tier": "success"}}]

    pre_soc = resolve_pre_turn_social_and_disclosures(session, [(char, [])], actions, new_dialogue_partners=[npc_name])
    assert cm["id"] in pre_soc["fulfilled_commitments"]
    assert any("[MANDATORY COMMITMENT FULFILLED]" in d for d in pre_soc["directives"])

    # Also verify priority choice slot preservation across re-invocation of build_hybrid_turn_choices
    first_pass = game_engine.build_hybrid_turn_choices(
        [{"label": f"Ask {npc_name} about potion brewing", "stat": "INT", "requirement": 8}],
        session=session,
        party=[(char, [])],
        result={"npcs_present": [spawned], "dialogue_partners": [npc_name]},
        actions=actions,
        schedule_transition_choice={"label": f"Walk with {npc_name} to the Greenhouse", "stat": "NONE", "requirement": 0},
    )
    assert any("Walk with" in c.get("label", "") and c.get("_priority_slot") for c in first_pass)
    second_pass = game_engine.build_hybrid_turn_choices(
        first_pass,
        session=session,
        party=[(char, [])],
        result={"npcs_present": [spawned], "dialogue_partners": [npc_name]},
        actions=actions,
    )
    assert any("Walk with" in c.get("label", "") for c in second_pass)

