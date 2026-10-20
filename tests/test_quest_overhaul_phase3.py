import unittest
import pytest
import json
import db
from game_engine.quests import (
    resolve_pre_turn_quests_and_clues,
    check_and_expire_overdue_quests,
    is_quest_in_turn_in_grace_period,
)
from mechanics.world.waypoints.choices import (
    generate_quest_action_choices,
    tag_and_enrich_quest_choices,
)
from mechanics.world.waypoints.matching import (
    resolve_effective_waypoint_location,
    get_waypoint_npc_schedule_info,
    is_hostile_or_lair_waypoint,
)
from mechanics.narrative.blueprints import (
    evaluate_waypoint_time_window,
    is_purely_time_locked_stage,
    roll_quest_deadline,
    infer_valid_time_phases_for_stage,
)
from mechanics.narrative.bounty import (
    generate_bounty_board,
    resolve_or_seed_bounty_client,
)


def _setup_session(
    session_id: int,
    user_id: int,
    name: str = "Chronos Hero",
    gold: int = 50,
    current_day: int = 1,
    current_minute: int = 480,
    current_location: str = "Old Docks",
    scenario: str = "fantasy",
) -> dict:
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
            ) VALUES (?, ?, ?, 'Ranger', 1, 1, 6, 6, 6, 6, 6, 6, 5, 100, 100, 50, 50, ?)""",
            (user_id, user_id, name, gold),
        )
        conn.execute(
            """INSERT INTO sessions (
                id, mode, capacity, status, scenario, current_location, current_day, current_minute, host_user_id, turn_order, choices_json, history_json
            ) VALUES (?, 'solo', 1, 'active', ?, ?, ?, ?, ?, ?, '[]', '[]')""",
            (session_id, scenario, current_location, current_day, current_minute, user_id, json.dumps([user_id])),
        )
        conn.commit()
    return db.get_character(user_id)


class TestQuestOverhaulPhase3(unittest.TestCase):

    def test_1_time_window_infiltration_wait_shortcut_and_risky_override(self):
        """Verifies nocturnal infiltration stages at Morning (08:00) offer wait shortcut and risky daytime override (+3 DC)."""
        session_id = 99301
        user_id = 88301
        _setup_session(session_id, user_id, current_day=1, current_minute=480, current_location="Old Docks")

        qid = "BOUNTY-NIGHT-INFILTRATE-01"
        db.upsert_quest(
            session_id=session_id,
            quest_id=qid,
            quest_type="Bounty Hunt",
            title="Infiltrate Smuggler Warehouse",
            objective="Infiltrate the Smuggler Warehouse at night to steal the cargo ledger",
            status="Active",
            reward_gold=50,
        )

        wps = [
            {
                "stage_index": 1,
                "stage_label": "Infiltrate Smuggler Warehouse at Night",
                "target_location": "Old Docks",
                "target_npc": "",
                "completion_trigger": "skill_check",
                "valid_time_phases": ["Night", "Midnight"],
                "status": "active",
            },
            {
                "stage_index": 2,
                "stage_label": "Deliver Cargo Ledger to Guildmaster Ronald",
                "target_location": "Adventurer's Guild",
                "target_npc": "Guildmaster Ronald",
                "completion_trigger": "arrival",
                "status": "locked",
            },
        ]
        db.save_quest_waypoints(session_id, qid, wps)

        # 1. Generate choices at 08:00 Morning (out of window: valid is Night/Midnight)
        choices = generate_quest_action_choices(session_id, "Old Docks")
        self.assertTrue(len(choices) >= 2, f"Expected wait shortcut and risky choice, got: {choices}")

        wait_choice = next((c for c in choices if c.get("approach") == "wait_for_window"), None)
        self.assertIsNotNone(wait_choice, "Expected 'wait_for_window' choice to be generated")
        self.assertIn("Wait Until Night", wait_choice["label"])
        self.assertEqual(wait_choice["wait_minutes"], 720)  # 480 + 720 = 1200 (Night)
        self.assertEqual(wait_choice.get("stat"), "FREE")

        risky_choice = next((c for c in choices if c.get("approach") != "wait_for_window"), None)
        self.assertIsNotNone(risky_choice, "Expected risky daytime override choice")
        self.assertEqual(risky_choice.get("dc_mod"), 3, "Risky daylight override must have +3 DC penalty")
        self.assertIn("High Alert", risky_choice["label"])

        # 2. Player selects wait shortcut: time advances by 720 min without failing/advancing waypoint
        sess = db.get_session(session_id)
        turn_actions = [
            {
                "label": wait_choice["label"],
                "approach": "wait_for_window",
                "wait_minutes": 720,
                "is_quest_action": True,
                "quest_id": qid,
            }
        ]
        turn_res = resolve_pre_turn_quests_and_clues(
            session=sess,
            actions=turn_actions,
            party=[{"user_id": user_id}],
        )

        # Waypoint must still be active at stage 1
        active_wp = db.get_active_waypoint(session_id, qid, None)
        self.assertIsNotNone(active_wp)
        self.assertEqual(active_wp["stage_index"], 1)
        self.assertEqual(active_wp["status"], "active")

        # Session clock must now be at 1200 (Night 20:00)
        updated_sess = db.get_session(session_id)
        self.assertEqual(updated_sess["current_minute"], 1200)

        # Directives should include wait report
        self.assertTrue(any("waited 720 minutes" in d for d in turn_res.get("directives", [])))

        # 3. Generating choices again at 1200 (Night): now in window!
        # Risky override penalty is removed, normal approaches presented
        night_choices = generate_quest_action_choices(session_id, "Old Docks")
        self.assertFalse(any(c.get("approach") == "wait_for_window" for c in night_choices))
        for nc in night_choices:
            self.assertEqual(nc.get("dc_mod", 0), 0, "No DC penalty when inside valid time window")

    def test_2_pure_time_locked_phenomenon_requires_waiting(self):
        """Verifies pure time-locked supernatural events (ghost lights at midnight) disallow risky overrides."""
        session_id = 99302
        user_id = 88302
        _setup_session(session_id, user_id, current_day=1, current_minute=480, current_location="Haunted Cemetery")

        # Verify helper functions
        self.assertTrue(is_purely_time_locked_stage("Investigate Ghost Lights at Midnight", ""))
        self.assertFalse(is_purely_time_locked_stage("Assassinate Corrupt Guard at Night", ""))

        qid = "GHOST-LIGHTS-01"
        db.upsert_quest(
            session_id=session_id,
            quest_id=qid,
            quest_type="Supernatural",
            title="Apparition at the Grave",
            objective="Witness and record the ghostly phenomenon at midnight",
            status="Active",
        )

        wps = [
            {
                "stage_index": 1,
                "stage_label": "Investigate Ghost Lights at Midnight",
                "target_location": "Haunted Cemetery",
                "completion_trigger": "action",
                "valid_time_phases": ["Midnight"],
                "status": "active",
            }
        ]
        db.save_quest_waypoints(session_id, qid, wps)

        # Generate choices at 08:00 (Morning)
        choices = generate_quest_action_choices(session_id, "Haunted Cemetery")
        self.assertEqual(len(choices), 1, "Purely time-locked stage should only offer the wait choice")
        self.assertEqual(choices[0]["approach"], "wait_for_window")
        self.assertIn("Wait Until Midnight", choices[0]["label"])

    def test_3_generous_deadlines_and_story_quest_immunity(self):
        """Verifies story quests never receive deadlines while side/bounties receive generous 5-7 day deadlines."""
        session_id = 99303
        user_id = 88303
        _setup_session(session_id, user_id, current_day=2, current_minute=600)

        # 1. Story quest immunity
        story_deadline = roll_quest_deadline(current_day=2, is_story_quest=True)
        self.assertEqual(story_deadline, (None, None))

        story_qid = "MAIN-QUEST-CH1"
        db.upsert_quest(
            session_id=session_id,
            quest_id=story_qid,
            quest_type="Main Quest",
            title="The Awakening",
            objective="Seek the elder in the mountain temple",
            status="Active",
            is_story_quest=1,
            deadline_day=None,
            deadline_minute=None,
        )
        sq = db.get_quest_by_id(session_id, story_qid)
        self.assertIsNone(sq.get("deadline_day"))
        self.assertIsNone(sq.get("deadline_minute"))

        # Updating story quest status preserves deadline immunity
        db.update_quest_status(session_id, story_qid, "Active")
        sq_after = db.get_quest_by_id(session_id, story_qid)
        self.assertIsNone(sq_after.get("deadline_day"))
        self.assertIsNone(sq_after.get("deadline_minute"))

        # 2. Bounty generous deadlines (5 to 7 days)
        for i in range(10):
            d_day, d_min = roll_quest_deadline(blueprint_id="NEUTRALIZATION", title=f"Urgent Bounty {i}", current_day=2, is_story_quest=False)
            self.assertIsNotNone(d_day)
            self.assertGreaterEqual(d_day, 7)  # 2 + 5 = 7
            self.assertLessEqual(d_day, 9)     # 2 + 7 = 9
            self.assertEqual(d_min, 1200)      # Night/Evening cutoff

        # Activating an accepted bounty guarantees at least 5 days from activation day
        bounty_qid = "BOUNTY-TIMED-01"
        db.upsert_quest(
            session_id=session_id,
            quest_id=bounty_qid,
            quest_type="Bounty Hunt",
            title="Hunt the Marauder",
            objective="Eliminate the marauder leader",
            status="Offered",
            is_story_quest=0,
            deadline_day=3,  # Short / outdated deadline from board
        )
        # Activation at day 2 should re-anchor deadline to >= day 7
        db.update_quest_status(session_id, bounty_qid, "Active")
        bq_after = db.get_quest_by_id(session_id, bounty_qid)
        self.assertGreaterEqual(bq_after.get("deadline_day"), 7)

    def test_4_stage_3_turn_in_grace_rule_prevents_expiration(self):
        """Verifies Stage 3 Client Turn-In Grace Rule prevents bounty expiration while returning the trophy."""
        session_id = 99304
        user_id = 88304
        _setup_session(session_id, user_id, current_day=1, current_minute=480, current_location="Outlaw Hideout")

        qid = "BOUNTY-GRACE-01"
        db.upsert_quest(
            session_id=session_id,
            quest_id=qid,
            quest_type="Bounty Hunt",
            title="Bring Down the Bandit Captain",
            objective="Defeat Bandit Captain and return proof to Ronald",
            status="Active",
            deadline_day=2,
            deadline_minute=1020,
        )

        wps = [
            {
                "stage_index": 1,
                "stage_label": "Scout the Outlaw Hideout",
                "target_location": "Outlaw Hideout",
                "completion_trigger": "arrival",
                "status": "completed",
            },
            {
                "stage_index": 2,
                "stage_label": "Defeat Bandit Captain",
                "target_location": "Outlaw Hideout",
                "completion_trigger": "skill_check",
                "status": "completed",
            },
            {
                "stage_index": 3,
                "stage_label": "Return to Guildmaster Ronald with Proof",
                "target_location": "Guild Hall",
                "target_npc": "Guildmaster Ronald",
                "completion_trigger": "arrival",
                "status": "active",
            },
        ]
        db.save_quest_waypoints(session_id, qid, wps)

        # Verify grace period helper
        self.assertTrue(is_quest_in_turn_in_grace_period(session_id, qid))

        # Fast forward time to Day 5 (3 days past Day 2 deadline!)
        db.update_session_time(session_id, current_day=5, current_minute=1200)

        # Run sweep
        exp_res = check_and_expire_overdue_quests(session_id)
        self.assertEqual(len(exp_res.get("expired_quest_ids", [])), 0)

        # Quest MUST remain Active!
        q = db.get_quest_by_id(session_id, qid)
        self.assertEqual(q.get("status"), "Active")

    def test_5_expired_deadline_mild_fallout_rival_claim(self):
        """Verifies expired deadline marks quest Failed with mild -5 affinity/-5 reputation, rival notice, and no ambush."""
        session_id = 99305
        user_id = 88305
        _setup_session(session_id, user_id, current_day=1, current_minute=480, current_location="Town Square")

        client_name = "Sheriff Vance"
        faction_name = "Town Watch"
        with db.get_conn() as conn:
            conn.execute(
                """INSERT INTO contacts (session_id, character_id, npc_id, name, relationship_score, basic_info_json, updated_at)
                   VALUES (?, 0, ?, ?, 10, ?, ?)""",
                (session_id, "sheriff_vance", client_name, json.dumps({"role": "sheriff", "location": "Sheriff Office"}), 1000)
            )
            conn.execute(
                """INSERT INTO factions (session_id, faction_id, name, reputation_score, created_at, updated_at)
                   VALUES (?, ?, ?, 10, 1000, 1000)""",
                (session_id, "town_watch", faction_name)
            )
            conn.commit()

        qid = "BOUNTY-EXPIRE-01"
        db.upsert_quest(
            session_id=session_id,
            quest_id=qid,
            quest_type="Bounty Hunt",
            title="Track the Highwaymen",
            objective="Scout highwaymen camp in Whispering Woods",
            status="Active",
            deadline_day=2,
            deadline_minute=1020,
            client_npc=client_name,
            quest_notes=f"faction:{faction_name}",
        )

        wps = [
            {
                "stage_index": 1,
                "stage_label": "Scout Highwaymen Camp",
                "target_location": "Whispering Woods",
                "completion_trigger": "arrival",
                "status": "active",
            },
            {
                "stage_index": 2,
                "stage_label": "Report to Sheriff Vance",
                "target_location": "Sheriff Office",
                "target_npc": client_name,
                "completion_trigger": "arrival",
                "status": "locked",
            },
        ]
        db.save_quest_waypoints(session_id, qid, wps)

        # Advance session clock past deadline (Day 3, 11:00 AM)
        db.update_session_time(session_id, current_day=3, current_minute=660)

        # Trigger deadline expiration check
        exp_res = check_and_expire_overdue_quests(session_id)
        self.assertIn(qid, exp_res.get("expired_quest_ids", []))

        # Check quest state
        q_after = db.get_quest_by_id(session_id, qid)
        self.assertEqual(q_after.get("status"), "Failed")
        self.assertEqual(q_after.get("resolution_approach"), "expired_deadline")

        # Waypoint marked failed
        all_wps = db.get_quest_waypoints(session_id, qid)
        self.assertTrue(all(w.get("status") == "failed" for w in all_wps))

        # Check mild affinity penalty (-5: 10 -> 5)
        contact = db.get_contact(session_id, client_name)
        self.assertEqual(contact.get("relationship_score"), 5)

        # Check mild faction penalty (-5: 10 -> 5)
        fac = db.get_faction(session_id, faction_name)
        self.assertEqual(fac.get("reputation_score"), 5)

        # Verify rival mercenary claim directive
        self.assertTrue(any("rival mercenary company claimed the target" in d.lower() for d in exp_res.get("directives", [])))

        # Ambush is NOT scheduled for deadline expiration (mild fallout only)
        sess = db.get_session(session_id)
        self.assertIsNone(sess.get("pending_retaliation_ambush"))

    def test_6_smart_npc_schedule_sync_and_nighttime_off_duty_guard(self):
        """Verifies friendly client follows daytime schedule and offers off-duty wait guard at night, while outlaw remains anchored."""
        session_id = 99306
        user_id = 88306
        _setup_session(session_id, user_id, current_day=1, current_minute=840, current_location="Adventurer's Guild")

        # 1. Seed Ronald with contact and schedule
        client_name = "Guildmaster Ronald"
        with db.get_conn() as conn:
            conn.execute(
                """INSERT INTO contacts (session_id, character_id, npc_id, name, relationship_score, basic_info_json, updated_at)
                   VALUES (?, 0, ?, ?, 20, ?, ?)""",
                (session_id, "guildmaster_ronald", client_name, json.dumps({"role": "guildmaster", "location": "Adventurer's Guild ➔ Guild Hall", "occupation": "guildmaster"}), 1000)
            )
            conn.commit()

        # Client turn-in waypoint
        friendly_wp = {
            "quest_id": "BOUNTY-CLIENT-SYNC",
            "stage_index": 2,
            "stage_label": "Report to Guildmaster Ronald",
            "target_location": "Adventurer's Guild",
            "target_npc": client_name,
            "completion_trigger": "talk_to_npc",
            "follow_npc_schedule": 1,
            "status": "active",
        }

        # 2. Daytime (14:00 / 840 min): Ronald is on-duty
        info_day = get_waypoint_npc_schedule_info(session_id, friendly_wp, current_minute=840)
        self.assertFalse(info_day["is_off_duty"])
        self.assertIsNotNone(info_day["scheduled_location"])

        # 3. Nighttime (23:00 / 1380 min): Ronald is off-duty sleeping
        info_night = get_waypoint_npc_schedule_info(session_id, friendly_wp, current_minute=1380)
        self.assertTrue(info_night["is_off_duty"])
        self.assertIn("Off-Duty", info_night["status_label"])
        self.assertEqual(info_night["wake_minute"], 450)  # 07:30 AM wake up in fantasy setting

        # Save quest and waypoint for night choice generation test
        db.upsert_quest(
            session_id=session_id,
            quest_id="BOUNTY-CLIENT-SYNC",
            quest_type="Bounty Hunt",
            title="Guild Commission",
            objective="Report completion to Guildmaster Ronald",
            status="Active",
        )
        db.save_quest_waypoints(session_id, "BOUNTY-CLIENT-SYNC", [friendly_wp])

        # Set session time to 23:00
        db.update_session_time(session_id, current_day=1, current_minute=1380)

        # Generate choices at night: must generate off-duty wait choice instead of talk
        night_choices = generate_quest_action_choices(session_id, "Adventurer's Guild")
        off_duty_choice = next((c for c in night_choices if c.get("approach") == "wait_until_morning"), None)
        self.assertIsNotNone(off_duty_choice, f"Expected off-duty wait choice, got: {night_choices}")
        self.assertIn("Off-Duty: Wait Until Morning", off_duty_choice["label"])
        self.assertEqual(off_duty_choice.get("stat"), "FREE")
        self.assertEqual(off_duty_choice.get("wait_minutes"), 510)  # (1440 - 1380) + 450 = 510 min to 07:30

        # Normal talk approach is suppressed while target is sleeping off-duty
        self.assertFalse(any("Talk to Guildmaster Ronald" in c.get("label", "") and c.get("approach") != "wait_until_morning" for c in night_choices))

        # 4. Hostile Outlaw Boss waypoint: never follows schedule
        hostile_wp = {
            "quest_id": "BOUNTY-OUTLAW-01",
            "stage_index": 2,
            "stage_label": "Confront Bandit King Vane",
            "target_location": "Bloodfang Stronghold",
            "target_npc": "Bandit King Vane",
            "completion_trigger": "skill_check",
            "status": "active",
        }
        self.assertTrue(is_hostile_or_lair_waypoint(hostile_wp))

        # Even at 23:00, hostile waypoint location remains anchored at Stronghold
        resolved_loc = resolve_effective_waypoint_location(session_id, hostile_wp)
        self.assertEqual(resolved_loc, "Bloodfang Stronghold")
