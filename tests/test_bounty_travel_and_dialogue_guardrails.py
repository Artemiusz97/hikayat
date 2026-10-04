import json
import unittest
import db
import game_engine
from mechanics.world.waypoints import (
    try_advance_on_arrival,
    try_complete_on_skill_check,
    check_action_matches_waypoint
)


class TestBountyTravelAndDialogueGuardrails(unittest.TestCase):
    def setUp(self):
        self.session_id = 998899
        self.user_id = 998899
        with db.get_conn() as conn:
            conn.execute("DELETE FROM sessions WHERE id = ?", (self.session_id,))
            conn.execute("DELETE FROM characters WHERE user_id = ?", (self.user_id,))
            conn.execute("DELETE FROM quests WHERE session_id = ?", (self.session_id,))
            conn.execute("DELETE FROM quest_waypoints WHERE session_id = ?", (self.session_id,))
            conn.execute("DELETE FROM contacts WHERE session_id = ?", (self.session_id,))
            conn.commit()

        db.create_character(
            self.user_id, "Artemiusz", char_class="Strategist",
            stats={"STR": 5, "PER": 8, "END": 6, "CHA": 7, "INT": 9, "AGI": 7, "LUK": 5}
        )
        self.char = db.get_character(self.user_id)

    def tearDown(self):
        with db.get_conn() as conn:
            conn.execute("DELETE FROM sessions WHERE id = ?", (self.session_id,))
            conn.execute("DELETE FROM characters WHERE user_id = ?", (self.user_id,))
            conn.execute("DELETE FROM quests WHERE session_id = ?", (self.session_id,))
            conn.execute("DELETE FROM quest_waypoints WHERE session_id = ?", (self.session_id,))
            conn.execute("DELETE FROM contacts WHERE session_id = ?", (self.session_id,))
            conn.commit()

    def test_travel_action_does_not_complete_skill_check_waypoint(self):
        """
        Verify that traveling into a classroom does NOT complete a skill_check waypoint,
        even if the travel action had a stat check (e.g. AGI 100%) and the room narrative
        mentions the target NPC sitting at their desk.
        """
        qid = "BNT-TEST-001"
        loc = "Westlake Academy ➔ Classroom 2-B (Homeroom) ➔ Student Desks"

        with db.get_conn() as conn:
            conn.execute("""
                INSERT INTO sessions (id, channel_id, host_user_id, status, mode, capacity, scenario, current_location, turn_order)
                VALUES (?, 100, ?, 'active', 'solo', 1, 'high_school_drama', ?, ?)
            """, (self.session_id, self.user_id, loc, json.dumps([self.user_id])))

            conn.execute("""
                INSERT INTO quests (session_id, quest_id, title, objective, status, progress, reward_xp, reward_gold, clues_required)
                VALUES (?, ?, 'The Anonymous Note Delivery', 'Deliver secret note', 'Active', '2/3 Milestones', 100, 50, 3)
            """, (self.session_id, qid))

            conn.execute("""
                INSERT INTO quest_waypoints (session_id, quest_id, stage_index, stage_label, target_location, target_npc, completion_trigger, status)
                VALUES (?, ?, 3, 'Return to Justin Anderson at Classroom 2-B to confirm the secret delivery', ?, 'Justin Anderson', 'skill_check', 'active')
            """, (self.session_id, qid, loc))
            conn.commit()

        # Player travels to classroom with an AGI check
        travel_action = {
            "char": self.char,
            "label": "I travel to Westlake Academy ➔ Classroom 2-B (Homeroom).",
            "stat": "AGI",
            "requirement": 0,
            "mp_spent": 0,
            "is_quest_action": False,
            "check": type("Check", (), {"succeeded": True, "tier": "success"})()
        }

        outcome = {
            "location": loc,
            "character_outcomes": [{"name": "Artemiusz", "hp_change": 0}],
            "outcome_narrative": "Artemiusz walks into Classroom 2-B. Justin Anderson is sitting at his desk reviewing notes.",
            "next_narrative": "The classroom hums with quiet conversation as students settle in."
        }

        # Apply outcome
        game_engine.apply_outcome(self.session_id, [(self.char, [])], outcome, actions=[travel_action])

        # Waypoint must REMAIN active!
        active_wp = db.get_active_waypoint(self.session_id, qid, None)
        self.assertIsNotNone(active_wp, "Waypoint should not be completed on a travel action!")
        self.assertEqual(active_wp["status"], "active")

        # Quest must REMAIN active!
        quests = db.get_session_quests(self.session_id)
        quest = next((q for q in quests if q["quest_id"] == qid), None)
        self.assertIsNotNone(quest)
        self.assertEqual(quest["status"], "Active")
        self.assertEqual(quest["progress"], "2/3 Milestones")

    def test_explicit_interaction_action_completes_skill_check_waypoint(self):
        """
        Verify that actively approaching and talking to Justin Anderson DOES advance
        the skill_check waypoint and complete the bounty.
        """
        qid = "BNT-TEST-002"
        loc = "Westlake Academy ➔ Classroom 2-B (Homeroom) ➔ Student Desks"

        with db.get_conn() as conn:
            conn.execute("""
                INSERT INTO sessions (id, channel_id, host_user_id, status, mode, capacity, scenario, current_location, turn_order)
                VALUES (?, 100, ?, 'active', 'solo', 1, 'high_school_drama', ?, ?)
            """, (self.session_id, self.user_id, loc, json.dumps([self.user_id])))

            conn.execute("""
                INSERT INTO quests (session_id, quest_id, title, objective, status, progress, reward_xp, reward_gold, clues_required)
                VALUES (?, ?, 'The Anonymous Note Delivery', 'Deliver secret note', 'Active', '2/3 Milestones', 100, 50, 3)
            """, (self.session_id, qid))

            conn.execute("""
                INSERT INTO quest_waypoints (session_id, quest_id, stage_index, stage_label, target_location, target_npc, completion_trigger, status)
                VALUES (?, ?, 1, 'Stage 1', ?, 'Justin Anderson', 'arrival', 'completed'),
                       (?, ?, 2, 'Stage 2', ?, 'Rachel Vance', 'skill_check', 'completed'),
                       (?, ?, 3, 'Return to Justin Anderson at Classroom 2-B to confirm the secret delivery', ?, 'Justin Anderson', 'skill_check', 'active')
            """, (self.session_id, qid, loc, self.session_id, qid, loc, self.session_id, qid, loc))
            conn.commit()

        # Player approaches Justin Anderson
        approach_action = {
            "char": self.char,
            "label": "Approach Justin and confirm the secret delivery",
            "stat": "CHA",
            "requirement": 0,
            "mp_spent": 0,
            "is_quest_action": False,
            "check": type("Check", (), {"succeeded": True, "tier": "success"})()
        }

        outcome = {
            "location": loc,
            "character_outcomes": [{"name": "Artemiusz", "hp_change": 0}],
            "outcome_narrative": "Artemiusz approaches Justin Anderson's desk and quietly nods, confirming the delivery is done.",
            "next_narrative": "Justin breathes a sigh of immense relief and offers his gratitude."
        }

        game_engine.apply_outcome(self.session_id, [(self.char, [])], outcome, actions=[approach_action])

        # Waypoint must now be completed!
        active_wp = db.get_active_waypoint(self.session_id, qid, None)
        self.assertIsNone(active_wp, "Waypoint should be completed after talking to Justin!")

        # Quest must now be completed and reward claimed!
        quests = db.get_session_quests(self.session_id)
        quest = next((q for q in quests if q["quest_id"] == qid), None)
        self.assertIsNotNone(quest)
        self.assertEqual(quest["status"], "Completed")
        self.assertEqual(quest["progress"], "3/3 Milestones")

    def test_dialogue_partner_with_high_affinity_does_not_follow_without_invitation(self):
        """
        Verify that talking to Rachel Vance in the Student Council Office (even with high affinity
        or romantic track) does NOT cause her to follow the player when moving to another location.
        """
        with db.get_conn() as conn:
            conn.execute(
                "INSERT INTO contacts (session_id, character_id, npc_id, name, relationship_score, basic_info_json, updated_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                (self.session_id, 0, "rachel_vance", "Rachel Vance", 25,
                 json.dumps({"location": "Creative Arts & Student Union Wing ➔ Student Council Office", "role": "Student Council President", "track": "romance"}), 1000)
            )
            conn.commit()

        session = {
            "id": self.session_id,
            "scenario": "high_school_drama",
            "current_location": "Creative Arts & Student Union Wing ➔ Student Council Office ➔ Main Office Area",
            "current_npcs": [{"name": "Rachel Vance", "role": "President"}],
            "dialogue_partners": ["Rachel Vance"],
            "dialogue_partner": "Rachel Vance",
            "history": [
                "[Success] Artemiusz: Deliver paperwork to Rachel -> Rachel accepts the files and smiles."
            ]
        }

        actions = [{"label": "I travel to Westlake Academy ➔ Classroom 2-B (Homeroom)."}]

        traveling, left_behind = game_engine.classify_scene_npcs(
            session,
            actions=actions,
            old_primary="Student Council Office",
            dest_primary="Classroom 2-B"
        )

        traveling_names = [n["name"] for n in traveling]
        left_behind_names = [n["name"] for n in left_behind]

        self.assertNotIn("Rachel Vance", traveling_names, "Rachel Vance should not follow the player when traveling to class!")
        self.assertIn("Rachel Vance", left_behind_names, "Rachel Vance should stay behind at the Student Council Office!")

    def test_dialogue_action_does_not_complete_physical_room_waypoint(self):
        """
        Verify that asking questions in dialogue (e.g. asking about Guild members) does NOT
        complete an unrelated physical room waypoint (e.g. securing a clockwork prototype),
        even if the background room narrative mentions the prototype.
        """
        qid = "SQ-STEAMPUNK-001"
        loc = "HMS Leviathan ➔ Command Bridge & Pilot Helm"

        with db.get_conn() as conn:
            conn.execute("""
                INSERT INTO sessions (id, channel_id, host_user_id, status, mode, capacity, scenario, current_location, turn_order, dialogue_partner)
                VALUES (?, 100, ?, 'active', 'solo', 1, 'steampunk', ?, ?, ?)
            """, (self.session_id, self.user_id, loc, json.dumps([self.user_id]), json.dumps(["Beatrice Sterling", "Felix Lockhart"])))

            sub_objs = [
                {"id": 1, "archetype": "Securing Evidence", "text": "Secure the contested clockwork prototype from the airship's command deck before it is confiscated or sabotaged.", "completed": False}
            ]
            conn.execute("""
                INSERT INTO quests (session_id, quest_id, title, objective, status, progress, reward_xp, reward_gold, is_story_quest, sub_objectives_json)
                VALUES (?, ?, 'The Pressure Valve Gambit', 'Investigate prototype', 'Active', 'Stage 3/3', 250, 60, 1, ?)
            """, (self.session_id, qid, json.dumps(sub_objs)))

            conn.execute("""
                INSERT INTO quest_waypoints (session_id, quest_id, sub_obj_id, stage_index, stage_label, target_location, target_npc, completion_trigger, status)
                VALUES (?, ?, 1, 3, 'Secure Prototype for Safe Transport', ?, '', 'skill_check', 'active')
            """, (self.session_id, qid, loc))
            conn.commit()

        # Conversational inquiry action
        dialogue_action = {
            "char": self.char,
            "label": "Ask which specific Guild members are involved",
            "stat": "INT",
            "requirement": 5,
            "mp_spent": 0,
            "is_quest_action": False,
            "check": type("Check", (), {"succeeded": True, "tier": "success"})()
        }

        outcome = {
            "location": loc,
            "character_outcomes": [{"name": "Artemiusz", "hp_change": 0}],
            "outcome_narrative": "Artemiusz inquires into Guild membership. Beatrice and Felix exchange a knowing look.",
            "next_narrative": "The prototype's hissing grows slightly louder near the control console."
        }

        game_engine.apply_outcome(self.session_id, [(self.char, [])], outcome, actions=[dialogue_action])

        # Waypoint must REMAIN ACTIVE!
        active_wp = db.get_active_waypoint(self.session_id, qid, 1)
        self.assertIsNotNone(active_wp, "Physical prototype waypoint must NOT complete on conversational inquiry!")
        self.assertEqual(active_wp["status"], "active")

        # Sub-objective must NOT be completed!
        quests = db.get_session_quests(self.session_id)
        quest = next((q for q in quests if q["quest_id"] == qid), None)
        self.assertIsNotNone(quest)
        sub_obj = quest["sub_objectives"][0]
        self.assertFalse(sub_obj.get("completed", False))

    def test_physical_action_targeting_prototype_completes_waypoint(self):
        """
        Verify that a physical action targeting the prototype DO advance and complete the waypoint.
        """
        qid = "SQ-STEAMPUNK-002"
        loc = "HMS Leviathan ➔ Command Bridge & Pilot Helm"

        with db.get_conn() as conn:
            conn.execute("""
                INSERT INTO sessions (id, channel_id, host_user_id, status, mode, capacity, scenario, current_location, turn_order)
                VALUES (?, 100, ?, 'active', 'solo', 1, 'steampunk', ?, ?)
            """, (self.session_id, self.user_id, loc, json.dumps([self.user_id])))

            sub_objs = [
                {"id": 1, "archetype": "Securing Evidence", "text": "Secure the contested clockwork prototype from the airship's command deck before it is confiscated or sabotaged.", "completed": False}
            ]
            conn.execute("""
                INSERT INTO quests (session_id, quest_id, title, objective, status, progress, reward_xp, reward_gold, is_story_quest, sub_objectives_json)
                VALUES (?, ?, 'The Pressure Valve Gambit', 'Investigate prototype', 'Active', 'Stage 3/3', 250, 60, 1, ?)
            """, (self.session_id, qid, json.dumps(sub_objs)))

            conn.execute("""
                INSERT INTO quest_waypoints (session_id, quest_id, sub_obj_id, stage_index, stage_label, target_location, target_npc, completion_trigger, status)
                VALUES (?, ?, 1, 3, 'Secure Prototype for Safe Transport', ?, '', 'skill_check', 'active')
            """, (self.session_id, qid, loc))
            conn.commit()

        # Dedicated securing action
        secure_action = {
            "char": self.char,
            "label": "Carefully secure the clockwork prototype into the transport harness",
            "stat": "AGI",
            "requirement": 5,
            "mp_spent": 0,
            "is_quest_action": False,
            "check": type("Check", (), {"succeeded": True, "tier": "success"})()
        }

        outcome = {
            "location": loc,
            "character_outcomes": [{"name": "Artemiusz", "hp_change": 0}],
            "outcome_narrative": "Artemiusz secures the prototype safely onto the transport rack.",
            "next_narrative": "The prototype is stabilized."
        }

        game_engine.apply_outcome(self.session_id, [(self.char, [])], outcome, actions=[secure_action])

        # Waypoint must now be completed!
        active_wp = db.get_active_waypoint(self.session_id, qid, 1)
        self.assertIsNone(active_wp, "Waypoint should be completed when physically securing prototype!")

        # Sub-objective must now be marked complete!
        quests = db.get_session_quests(self.session_id)
        quest = next((q for q in quests if q["quest_id"] == qid), None)
        self.assertIsNotNone(quest)
        sub_obj = quest["sub_objectives"][0]
        self.assertTrue(sub_obj.get("completed", False))


if __name__ == "__main__":
    unittest.main()

