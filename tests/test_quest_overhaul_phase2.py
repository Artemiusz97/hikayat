import pytest
import time
import json
import db
from game_engine.quests import (
    resolve_pre_turn_quests_and_clues,
    apply_quest_approach_effects,
    apply_quest_failure_consequences,
    handle_failed_quest_skill_check,
    trigger_pending_retaliation_if_eligible,
)
from mechanics.world.waypoints.choices import (
    generate_quest_action_choices,
    tag_and_enrich_quest_choices,
)
from mechanics.narrative.blueprints import (
    classify_choice_approach,
    calculate_quest_buyout_cost,
    build_stage_contrasting_approaches,
)


def _setup_session(session_id: int, user_id: int, name: str = "Hero", gold: int = 50, stats: dict = None, scenario: str = "fantasy") -> dict:
    if stats is None:
        stats = {"STR": 6, "PER": 6, "END": 6, "CHA": 6, "INT": 6, "AGI": 6, "LUK": 5}
    with db.get_conn() as conn:
        conn.execute("DELETE FROM sessions WHERE id = ?", (session_id,))
        conn.execute("DELETE FROM quests WHERE session_id = ?", (session_id,))
        conn.execute("DELETE FROM quest_waypoints WHERE session_id = ?", (session_id,))
        conn.execute("DELETE FROM contacts WHERE session_id = ?", (session_id,))
        conn.execute("DELETE FROM factions WHERE session_id = ?", (session_id,))
        conn.execute("DELETE FROM lorebook WHERE session_id = ?", (session_id,))
        conn.execute("DELETE FROM phone_gossip_feed WHERE session_id = ?", (session_id,))
        conn.execute("DELETE FROM inventory WHERE user_id = ?", (user_id,))
        conn.execute("DELETE FROM characters WHERE user_id = ?", (user_id,))
        conn.execute(
            """INSERT INTO characters (
                id, user_id, name, char_class, level, is_active, str_, per_, end_, cha, int_, agi, luk, hp, max_hp, mp, max_mp, gold
            ) VALUES (?, ?, ?, 'Adventurer', 1, 1, ?, ?, ?, ?, ?, ?, ?, 100, 100, 50, 50, ?)""",
            (user_id, user_id, name, stats["STR"], stats["PER"], stats["END"], stats["CHA"], stats["INT"], stats["AGI"], stats["LUK"], gold)
        )
        conn.execute(
            """INSERT INTO sessions (
                id, mode, capacity, status, scenario, current_location, current_day, current_minute, host_user_id, turn_order, choices_json, history_json
            ) VALUES (?, 'solo', 1, 'active', ?, 'Starting Area', 1, 480, ?, ?, '[]', '[]')""",
            (session_id, scenario, user_id, json.dumps([user_id]))
        )
        conn.commit()
    char = db.get_character(user_id)
    return char


class TestQuestOverhaulPhase2:

    def test_1_multi_approach_choice_generation_and_tagging(self):
        """Verifies multi-approach choices are synthesized at Stage >= 2 and up to 3 distinct approaches are tagged."""
        session_id = 99201
        user_id = 88201
        char = _setup_session(session_id, user_id, name="Ranger Approach", gold=100)

        # Create a NEUTRALIZATION quest at Stage 2 Confrontation
        qid = "BOUNTY-CONFRONT-01"
        q = db.upsert_quest(
            session_id=session_id,
            quest_id=qid,
            quest_type="Bounty Hunt",
            title="Hunt the Bandit Renegade",
            objective="Confront and eliminate Renegade Garrick in Whispering Caves",
            status="Active",
            reward_gold=40,
            reward_xp=120,
            blueprint_id="NEUTRALIZATION",
            client_npc="Captain Vane",
            client_location="Ironpeak Garrison ➔ Guardhouse",
        )

        loc_caves = "Whispering Caves ➔ Inner Den"
        db.save_quest_waypoints(
            session_id=session_id,
            quest_id=qid,
            waypoints=[
                {
                    "stage_index": 1,
                    "stage_label": "Track the renegade trail to Whispering Caves",
                    "target_location": "Ironpeak Garrison ➔ North Trail",
                    "completion_trigger": "arrival",
                    "status": "completed",
                },
                {
                    "stage_index": 2,
                    "stage_label": "Confront Renegade Garrick in his den",
                    "target_location": loc_caves,
                    "target_npc": "Renegade Garrick",
                    "completion_trigger": "skill_check",
                    "status": "active",
                },
                {
                    "stage_index": 3,
                    "stage_label": "Return to Captain Vane and confirm the bounty",
                    "target_location": "Ironpeak Garrison ➔ Guardhouse",
                    "target_npc": "Captain Vane",
                    "completion_trigger": "talk_to_npc",
                    "status": "locked",
                },
            ]
        )

        db.update_session(session_id, current_location=loc_caves)
        gen_choices = generate_quest_action_choices(session_id, current_location=loc_caves, char=char)
        assert len(gen_choices) >= 2, f"Expected at least 2 contrasting choices, got: {gen_choices}"

        approaches = [c.get("approach") for c in gen_choices]
        assert "direct" in approaches, f"Expected direct approach, got {approaches}"
        assert "spare_deceive" in approaches, f"Expected spare_deceive approach, got {approaches}"
        assert "counter_offer" in approaches, f"Expected counter_offer approach, got {approaches}"

        # Test tagging up to 3 distinct approach choices from LLM output
        llm_choices = [
            {"label": "Draw your blades and strike down Renegade Garrick", "stat": "AGI", "requirement": 6},
            {"label": "Lower your weapon and offer Renegade Garrick a chance to vanish into exile with forged proof", "stat": "CHA", "requirement": 6},
            {"label": "Listen to Renegade Garrick's secret deal and take his counter offer bribe to turn on the captain", "stat": "FREE", "requirement": 0},
            {"label": "Search the stone chests for loose silver", "stat": "INT", "requirement": 4},
        ]

        tagged = tag_and_enrich_quest_choices(
            choices=llm_choices,
            session_id=session_id,
            current_location=loc_caves,
            char=char,
            dialogue_partner=None,
            current_npcs=[{"name": "Renegade Garrick"}],
        )

        quest_tagged = [c for c in tagged if c.get("is_quest_action")]
        assert len(quest_tagged) == 3, f"Expected exactly 3 tagged approaches, got {len(quest_tagged)}"
        tagged_apps = {c.get("approach") for c in quest_tagged}
        assert tagged_apps == {"direct", "spare_deceive", "counter_offer"}

    def test_2_spare_and_fake_death_resolution(self):
        """Verifies sparing the target marks them disappeared, gives affinity, and makes Stage 3 an auto turn-in."""
        session_id = 99202
        user_id = 88202
        char = _setup_session(session_id, user_id, name="Diplomat", gold=50)

        qid = "BOUNTY-MERCY-01"
        db.upsert_quest(
            session_id=session_id,
            quest_id=qid,
            quest_type="Bounty Hunt",
            title="Bounty on Mara",
            objective="Eliminate Mara the Outlaw",
            status="Active",
            reward_gold=60,
            client_npc="Guildmaster Orson",
            client_location="High Market ➔ Hunter Guild",
        )
        caves_loc = "Sunken Hollow ➔ Hideout"
        db.save_quest_waypoints(
            session_id=session_id,
            quest_id=qid,
            waypoints=[
                {
                    "stage_index": 1,
                    "stage_label": "Reach Sunken Hollow",
                    "target_location": caves_loc,
                    "completion_trigger": "arrival",
                    "status": "completed",
                },
                {
                    "stage_index": 2,
                    "stage_label": "Confront Mara the Outlaw",
                    "target_location": caves_loc,
                    "target_npc": "Mara the Outlaw",
                    "completion_trigger": "skill_check",
                    "status": "active",
                },
                {
                    "stage_index": 3,
                    "stage_label": "Turn in proof to Guildmaster Orson",
                    "target_location": "High Market ➔ Hunter Guild",
                    "target_npc": "Guildmaster Orson",
                    "completion_trigger": "talk_to_npc",
                    "status": "locked",
                },
            ]
        )

        db.update_session(session_id, current_location=caves_loc)
        sess = db.get_session(session_id)

        # Player chooses spare & fake death
        actions = [{
            "label": "🎯 [Bounty] [Spare & Fake Death] Convince Mara the Outlaw to vanish and forge proof of elimination",
            "stat": "CHA",
            "requirement": 5,
            "is_quest_action": True,
            "quest_id": qid,
            "sub_obj_id": None,
            "stage_index": 2,
            "approach": "spare_deceive",
            "check": {"result_tier": "success", "success": True},
        }]

        res = resolve_pre_turn_quests_and_clues(sess, party=[{"user_id": user_id}], actions=actions)
        q_updated = db.get_quest_by_id(session_id, qid)
        assert q_updated["resolution_approach"] == "spared_deception"

        # Check target lorebook status
        lb_target = db.get_lorebook_entity(session_id, "Mara the Outlaw")
        assert lb_target and lb_target.get("status") == "disappeared"

        # Check contact affinity (+15)
        contact = db.get_contact(session_id, "Mara the Outlaw")
        assert contact and contact.get("relationship_score", 0) >= 15

        # Verify Stage 3 choice generation at Guildmaster Orson
        guild_loc = "High Market ➔ Hunter Guild"
        db.update_session(session_id, current_location=guild_loc)
        sess = db.get_session(session_id)
        turn_in_choices = generate_quest_action_choices(session_id, current_location=guild_loc, char=char)
        spared_choice = next((c for c in turn_in_choices if c.get("approach") == "spared_turn_in"), None)
        assert spared_choice is not None
        assert spared_choice.get("requirement") == 0

        # Complete turn in
        turn_in_action = [{
            "label": spared_choice["label"],
            "stat": "NONE",
            "requirement": 0,
            "is_quest_action": True,
            "quest_id": qid,
            "sub_obj_id": None,
            "stage_index": 3,
            "approach": "spared_turn_in",
            "check": {"result_tier": "success", "success": True},
        }]
        res_final = resolve_pre_turn_quests_and_clues(sess, party=[{"user_id": user_id}], actions=turn_in_action)
        assert qid in res_final["completed_quests"]

    def test_3_target_counter_offer_betrayal(self):
        """Verifies accepting a counter-offer immediately fails bounty as betrayed_client, pays 1.5x Gold, and triggers Client Wrath."""
        session_id = 99203
        user_id = 88203
        char = _setup_session(session_id, user_id, name="Rogue", gold=20)

        qid = "BOUNTY-BETRAY-01"
        db.upsert_quest(
            session_id=session_id,
            quest_id=qid,
            quest_type="Bounty Hunt",
            title="Eliminate smuggler Jax",
            objective="Kill Jax the Smuggler",
            status="Active",
            reward_gold=100,
            client_npc="Magistrate Vance",
            client_location="Citadel ➔ High Court",
            quest_notes="Sponsoring faction:faction:iron_covenant",
        )
        db.upsert_faction(session_id, name="Iron Covenant", delta_score=10)
        db.upsert_contact(session_id, npc_id="magistrate_vance", name="Magistrate Vance", delta_score=20)

        loc_docks = "Docks ➔ Smuggler Bay"
        db.save_quest_waypoints(
            session_id=session_id,
            quest_id=qid,
            waypoints=[
                {
                    "stage_index": 2,
                    "stage_label": "Corner Jax the Smuggler",
                    "target_location": loc_docks,
                    "target_npc": "Jax the Smuggler",
                    "completion_trigger": "skill_check",
                    "status": "active",
                }
            ]
        )
        db.update_session(session_id, current_location=loc_docks)
        sess = db.get_session(session_id)

        # Player accepts counter offer
        actions = [{
            "label": "🎯 [Bounty] [Accept Counter-Offer] Strike a secret deal with Jax the Smuggler and betray your client for 1.5x Gold",
            "stat": "FREE",
            "requirement": 0,
            "is_quest_action": True,
            "quest_id": qid,
            "approach": "counter_offer",
            "check": {"result_tier": "success", "success": True},
        }]

        res = resolve_pre_turn_quests_and_clues(sess, party=[{"user_id": user_id}], actions=actions)
        q_final = db.get_quest_by_id(session_id, qid)
        assert q_final["status"] == "Failed"
        assert q_final["resolution_approach"] == "betrayed_client"

        # Check gold: 20 starting + 150 (1.5x of 100) = 170
        char_after = db.get_character(user_id)
        assert char_after["gold"] == 170

        # Check Magistrate Vance affinity: 20 - 15 = 5
        client_contact = db.get_contact(session_id, "Magistrate Vance")
        assert client_contact["relationship_score"] == 5

        # Check Iron Covenant reputation: 10 - 15 = -5
        cov_fac = db.get_faction(session_id, "Iron Covenant")
        assert cov_fac["reputation_score"] == -5

        # Check pending retaliation queued
        sess_after = db.get_session(session_id)
        retal = sess_after.get("pending_retaliation")
        assert retal and retal["quest_id"] == qid
        assert retal["reason"] == "betrayed_client"

    def test_4_gold_buyout_visibility_and_execution(self):
        """Verifies gold buyout choice visibility depends on player gold, deducts gold on choice, and advances stage."""
        session_id = 99204
        user_id = 88204
        char = _setup_session(session_id, user_id, name="Merchant Boy", gold=10)

        qid = "ACQ-BUYOUT-01"
        db.upsert_quest(
            session_id=session_id,
            quest_id=qid,
            quest_type="Acquisition",
            title="Procure Moonpetals",
            objective="Secure 1x Moonpetal Herb",
            status="Active",
            reward_gold=50, # Buyout cost = max(15, 50 * 0.5) = 25g
            required_item="Moonpetal Herb",
            required_item_count=1,
            blueprint_id="ACQUISITION",
        )
        garden_loc = "Alchemist Garden ➔ Rare Greenhouse"
        db.save_quest_waypoints(
            session_id=session_id,
            quest_id=qid,
            waypoints=[
                {
                    "stage_index": 1,
                    "stage_label": "Enter Greenhouse",
                    "target_location": garden_loc,
                    "completion_trigger": "arrival",
                    "status": "completed",
                },
                {
                    "stage_index": 2,
                    "stage_label": "Harvest Moonpetal Herb",
                    "target_location": garden_loc,
                    "required_item": "Moonpetal Herb",
                    "completion_trigger": "skill_check",
                    "status": "active",
                },
            ]
        )
        db.update_session(session_id, current_location=garden_loc)

        # Player only has 10g: buyout (25g) MUST NOT be generated
        choices_low_gold = generate_quest_action_choices(session_id, current_location=garden_loc, char=char)
        assert not any(c.get("approach") == "buyout_bribe" for c in choices_low_gold)

        # Give player 40g (enough for 25g buyout)
        db.update_character_fields(user_id, gold=40)
        char_rich = db.get_character(user_id)
        choices_rich = generate_quest_action_choices(session_id, current_location=garden_loc, char=char_rich)
        buyout_choice = next((c for c in choices_rich if c.get("approach") == "buyout_bribe"), None)
        assert buyout_choice is not None
        assert buyout_choice["gold_cost"] == 25
        assert buyout_choice["requirement"] == 0

        # Execute buyout choice
        sess = db.get_session(session_id)
        actions = [{
            "label": buyout_choice["label"],
            "stat": "FREE",
            "requirement": 0,
            "is_quest_action": True,
            "quest_id": qid,
            "stage_index": 2,
            "approach": "buyout_bribe",
            "gold_cost": 25,
            "check": {"result_tier": "success", "success": True},
        }]
        res = resolve_pre_turn_quests_and_clues(sess, party=[{"user_id": user_id}], actions=actions)
        char_after = db.get_character(user_id)
        # 40 starting - 25 buyout cost + 50 quest completion reward = 65
        assert char_after["gold"] == 65
        assert qid in res["completed_quests"]

        q_after = db.get_quest_by_id(session_id, qid)
        assert q_after["resolution_approach"] == "bought_or_bribed"

    def test_5_two_strike_alert_meter_and_stage1_immunity(self):
        """Verifies Stage 1 failed checks add 0 strikes, Stage 2 failure adds 1 strike, and 2nd failure fails side bounty."""
        session_id = 99205
        user_id = 88205
        char = _setup_session(session_id, user_id, name="Warrior", gold=10)

        qid = "BOUNTY-STRIKES-01"
        db.upsert_quest(
            session_id=session_id,
            quest_id=qid,
            quest_type="Bounty Hunt",
            title="Track the Poacher",
            objective="Capture the Poacher",
            status="Active",
            reward_gold=50,
            blueprint_id="NEUTRALIZATION",
            is_story_quest=0,
        )
        camp_loc = "Deep Woods ➔ Poacher Camp"
        trail_loc = "Deep Woods ➔ Outer Trail"
        db.save_quest_waypoints(
            session_id=session_id,
            quest_id=qid,
            waypoints=[
                {
                    "stage_index": 1,
                    "stage_label": "Search for tracks on Outer Trail",
                    "target_location": trail_loc,
                    "completion_trigger": "skill_check",
                    "status": "active",
                },
                {
                    "stage_index": 2,
                    "stage_label": "Apprehend the Poacher",
                    "target_location": camp_loc,
                    "completion_trigger": "skill_check",
                    "status": "locked",
                },
            ]
        )
        db.update_session(session_id, current_location=trail_loc)
        sess = db.get_session(session_id)

        # 1. Failed check on Stage 1 (Immunity Guard)
        actions_s1_fail = [{
            "label": "🎯 [Bounty] Search for tracks on Outer Trail",
            "stat": "PER",
            "requirement": 5,
            "is_quest_action": True,
            "quest_id": qid,
            "stage_index": 1,
            "check": {"result_tier": "failure", "success": False},
        }]
        resolve_pre_turn_quests_and_clues(sess, party=[{"user_id": user_id}], actions=actions_s1_fail)
        q1 = db.get_quest_by_id(session_id, qid)
        assert q1["strikes"] == 0, "Stage 1 failure must not add strikes"

        # Advance to Stage 2
        db.advance_waypoint(session_id, qid, stage_index=1)
        db.update_session(session_id, current_location=camp_loc)
        sess2 = db.get_session(session_id)

        # 2. First failure on Stage 2 (Adds Strike 1)
        actions_s2_fail1 = [{
            "label": "🎯 [Bounty] Apprehend the Poacher",
            "stat": "STR",
            "requirement": 6,
            "is_quest_action": True,
            "quest_id": qid,
            "stage_index": 2,
            "check": {"result_tier": "failure", "success": False},
        }]
        res_s2_1 = resolve_pre_turn_quests_and_clues(sess2, party=[{"user_id": user_id}], actions=actions_s2_fail1)
        q2 = db.get_quest_by_id(session_id, qid)
        assert q2["strikes"] == 1
        assert "[⚠️ 1/2 Strikes: Target Alerted]" in q2["progress"]
        assert any("1/2 STRIKES" in d for d in res_s2_1["directives"])

        # 3. Second failure on Stage 2 (Adds Strike 2 -> Hard Failure)
        res_s2_2 = resolve_pre_turn_quests_and_clues(sess2, party=[{"user_id": user_id}], actions=actions_s2_fail1)
        q3 = db.get_quest_by_id(session_id, qid)
        assert q3["status"] == "Failed"
        assert q3["resolution_approach"] == "failed_strikes"
        assert any("MANDATORY QUEST FAILURE" in d for d in res_s2_2["directives"])

    def test_6_dire_consequences_and_delayed_travel_ambush(self):
        """Verifies failed bounty queues retaliation ambush and triggers when moving to non-safe location."""
        session_id = 99206
        user_id = 88206
        char = _setup_session(session_id, user_id, name="Target Player", gold=10)

        qid = "BOUNTY-AMBUSH-01"
        db.upsert_quest(
            session_id=session_id,
            quest_id=qid,
            quest_type="Bounty Hunt",
            title="Slay the Golem",
            objective="Defeat the Stone Golem",
            status="Active",
            blueprint_id="NEUTRALIZATION",
            client_npc="Elder Justin",
        )
        origin_loc = "Crag Valley ➔ Quarry Site"
        db.update_session(session_id, current_location=origin_loc)
        sess = db.get_session(session_id)

        # Trigger failure consequences
        apply_quest_failure_consequences(session_id, db.get_quest_by_id(session_id, qid), [user_id], reason="failed_strikes", session=sess)
        sess_with_retal = db.get_session(session_id)
        assert sess_with_retal.get("pending_retaliation") is not None

        # 1. Staying in the same location does NOT trigger ambush
        no_ambush = trigger_pending_retaliation_if_eligible(session_id, origin_loc, session=sess_with_retal)
        assert no_ambush is None

        # 2. Moving to a safe bedroom does NOT trigger ambush
        dorm_loc = "Academy Campus ➔ Student Dormitory"
        no_ambush_dorm = trigger_pending_retaliation_if_eligible(session_id, dorm_loc, session=sess_with_retal)
        assert no_ambush_dorm is None

        # 3. Moving to a wild crossroads location triggers the ambush!
        wild_loc = "High Road ➔ Forest Crossroads"
        ambush = trigger_pending_retaliation_if_eligible(session_id, wild_loc, session=sess_with_retal)
        assert ambush is not None
        assert "MANDATORY RETALIATION AMBUSH" in ambush["directive"]

        sess_ambushed = db.get_session(session_id)
        assert any(e.get("is_retaliation_ambush") for e in sess_ambushed["nearby_enemies"])
        assert sess_ambushed.get("pending_retaliation") is None

    def test_7_story_quest_dire_cost_fail_forward(self):
        """Verifies Story Quests never soft-lock: sub-objectives at 2 strikes fail forward at dire cost, climax fails forward as pyrrhic."""
        session_id = 99207
        user_id = 88207
        char = _setup_session(session_id, user_id, name="Chosen Hero", gold=50)

        sq_id = "SQ-CH1-CORRUPTION"
        sub_objs = [
            {"id": 1, "text": "Investigate the crypt seal", "completed": False},
            {"id": 2, "text": "Extract the corrupted keystone", "completed": False},
        ]
        db.upsert_quest(
            session_id=session_id,
            quest_id=sq_id,
            quest_type="Story Quest",
            title="The Rising Dark",
            objective="Cleanse the ancient corruption",
            status="Active",
            reward_gold=100,
            reward_xp=250,
            is_story_quest=1,
            sub_objectives=sub_objs,
        )

        loc_crypt = "Ancient Catacombs ➔ Sealed Vault"
        db.save_quest_waypoints(
            session_id=session_id,
            quest_id=sq_id,
            sub_obj_id=1,
            waypoints=[
                {
                    "stage_index": 1,
                    "stage_label": "Enter the Crypt",
                    "target_location": loc_crypt,
                    "completion_trigger": "arrival",
                    "status": "completed",
                },
                {
                    "stage_index": 2,
                    "stage_label": "Break the Ward Runes",
                    "target_location": loc_crypt,
                    "completion_trigger": "skill_check",
                    "status": "active",
                },
            ]
        )
        db.update_session(session_id, current_location=loc_crypt)
        sess = db.get_session(session_id)

        # Fail twice on Sub-objective 1 Stage 2
        fail_action = [{
            "label": "⭐ [Story Quest] Break the Ward Runes",
            "stat": "INT",
            "requirement": 6,
            "is_quest_action": True,
            "quest_id": sq_id,
            "sub_obj_id": 1,
            "stage_index": 2,
            "check": {"result_tier": "failure", "success": False},
        }]

        # Strike 1
        resolve_pre_turn_quests_and_clues(sess, party=[{"user_id": user_id}], actions=fail_action)
        sq_strike1 = db.get_quest_by_id(session_id, sq_id)
        assert sq_strike1["strikes"] == 1

        # Strike 2 -> Fail-forward with Dire Cost!
        res_ff = resolve_pre_turn_quests_and_clues(sess, party=[{"user_id": user_id}], actions=fail_action)
        sq_strike2 = db.get_quest_by_id(session_id, sq_id)

        assert sq_strike2["status"] == "Active", "Story quest must remain Active (never failed)"
        assert sq_strike2["strikes"] == 0, "Strikes must reset to 0 after fail-forward"
        assert any("PYRRHIC BREAKTHROUGH" in d for d in res_ff["directives"])

        char_hurt = db.get_character(user_id)
        assert char_hurt["hp"] < char["hp"], "Player must suffer HP penalty on dire cost breakthrough"

        # Now test Story Climax Pyrrhic Resolution
        # Mark all sub-objectives complete to enable climax
        db.upsert_quest(
            session_id=session_id,
            quest_id=sq_id,
            quest_type="Story Quest",
            title="The Rising Dark",
            objective="Cleanse the ancient corruption",
            status="Active",
            reward_gold=100,
            reward_xp=250,
            is_story_quest=1,
            sub_objectives=[
                {"id": 1, "text": "Investigate the crypt seal", "completed": True},
                {"id": 2, "text": "Extract the corrupted keystone", "completed": True},
            ],
        )

        climax_fail_action = [{
            "label": "⚡ [Story Climax] Confront the threat and bring 'The Rising Dark' to a decisive resolution",
            "stat": "STR",
            "requirement": 6,
            "is_quest_action": True,
            "is_climax_action": True,
            "quest_id": sq_id,
            "stage_index": 99,
            "check": {"result_tier": "critical_failure", "success": False},
        }]

        res_climax = resolve_pre_turn_quests_and_clues(sess, party=[{"user_id": user_id}], actions=climax_fail_action)
        assert sq_id in res_climax["completed_quests"], "Story Climax must advance even on critical failure"
        sq_completed = db.get_quest_by_id(session_id, sq_id)
        assert sq_completed["resolution_approach"] == "pyrrhic_climax"
        assert any("PYRRHIC CLIMAX" in d for d in res_climax["directives"])
