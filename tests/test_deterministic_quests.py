import unittest
import time
import db
import config
from game_engine.quests import (
    resolve_pre_turn_quests_and_clues,
    apply_quest_update,
    forfeit_side_bounty,
    can_accept_side_bounty,
    check_and_extract_defeated_suspect_evidence,
    ensure_story_quest_exists,
)
from mechanics.world.waypoints.choices import (
    generate_quest_action_choices,
    get_active_companion_for_waypoint,
)
from mechanics.world.waypoints.matching import get_story_quest_climax_location


class TestDeterministicQuests(unittest.TestCase):
    def setUp(self):
        db.init_db()
        config.DETERMINISTIC_QUESTS = True
        config.DETERMINISTIC_CAST = True
        config.DETERMINISTIC_MOVEMENT = True

        self.user_id = 999888111
        self.session_id = 888777111

        # Clear any existing user characters
        for c in db.get_user_characters(self.user_id):
            db.delete_character(self.user_id, c["id"])

        base_stats = {"STR": 6, "PER": 5, "END": 5, "CHA": 6, "INT": 7, "AGI": 5, "LUK": 5}
        self.char = db.create_character(
            user_id=self.user_id,
            name="Detective Hiro",
            char_class="Investigator",
            class_description="Test Investigator",
            stats=base_stats,
        )
        self.session_id = db.create_session(
            self.user_id, "solo", 1, "vivid", "individual", False, scenario="high_school_drama"
        )
        self.session = db.get_session(self.session_id)
        self.party = [(self.char, db.get_inventory(self.user_id))]

        # Clean tables for this session
        with db.get_conn() as conn:
            conn.execute("DELETE FROM quests WHERE session_id = ?", (self.session_id,))
            conn.execute("DELETE FROM quest_waypoints WHERE session_id = ?", (self.session_id,))
            conn.execute("DELETE FROM session_clues WHERE session_id = ?", (self.session_id,))
            conn.execute("DELETE FROM world_nodes WHERE session_id = ?", (self.session_id,))
            conn.execute("DELETE FROM world_edges WHERE session_id = ?", (self.session_id,))

    def test_zero_llm_objective_authority(self):
        """Under DETERMINISTIC_QUESTS=True, LLM outcome cannot complete or alter quest status/rewards (Q1, Q6)."""
        qid = "SQ-101"
        db.upsert_quest(
            session_id=self.session_id,
            quest_id=qid,
            quest_type="Story Quest",
            title="The Stolen Exam Papers",
            objective="Find who leaked the midterm exam.",
            progress="0/2 Cleared",
            status="Active",
            reward_xp=200,
            reward_gold=50,
            is_story_quest=1,
            sub_objectives=[
                {"id": 1, "text": "Inspect the faculty desk", "completed": False},
                {"id": 2, "text": "Interrogate the suspect", "completed": False},
            ],
        )

        fake_llm_outcome = {
            "scene": "The player easily wraps up the investigation and gets rich.",
            "quest_updates": [
                {
                    "quest_id": qid,
                    "title": "The Stolen Exam Papers",
                    "status": "Completed",
                    "reward_xp": 9999,
                    "reward_gold": 5000,
                }
            ],
        }

        # LLM outcome processing
        notice = apply_quest_update(
            self.session_id,
            fake_llm_outcome["quest_updates"][0],
            party_user_ids=[self.user_id],
            outcome=fake_llm_outcome,
            actions=[{"label": "Look around", "stat": "NONE", "requirement": 0}],
        )

        # Verification: Quest status must remain Active and rewards unchanged in DB
        q_after = db.get_quest_by_id(self.session_id, qid)
        self.assertEqual(q_after["status"], "Active")
        self.assertEqual(q_after["reward_xp"], 200)
        self.assertEqual(q_after["reward_gold"], 50)
        self.assertIsNone(notice)

    def test_legacy_direct_apply_quest_update_backward_compatibility(self):
        """Legacy direct calls without LLM outcome dictionary retain status mutation for unit test backwards compatibility."""
        qid = "LEGACY-001"
        db.upsert_quest(
            session_id=self.session_id,
            quest_id=qid,
            quest_type="Side Bounty",
            title="Legacy Errand",
            objective="Perform an errand.",
            status="Active",
            reward_xp=50,
            reward_gold=10,
            is_story_quest=0,
        )

        # Direct legacy call with outcome=None
        notice = apply_quest_update(
            self.session_id,
            {"quest_id": qid, "title": "Legacy Errand", "status": "Completed"},
            party_user_ids=[self.user_id],
            outcome=None,
        )

        q_after = db.get_quest_by_id(self.session_id, qid)
        self.assertEqual(q_after["status"], "Completed")
        self.assertIsNotNone(notice)
        self.assertTrue(notice.get("claimed"))

    def test_pre_registered_clue_discovery(self):
        """Completing an investigative sub-objective deterministically records structured clue to session_clues (Q2)."""
        qid = "SQ-102"
        db.upsert_quest(
            session_id=self.session_id,
            quest_id=qid,
            quest_type="Story Quest",
            title="The Vault Heist",
            objective="Uncover who unlocked the academy vault.",
            status="Active",
            reward_xp=250,
            reward_gold=60,
            is_story_quest=1,
            sub_objectives=[
                {
                    "id": 1,
                    "text": "Investigate the vault entrance for physical traces",
                    "clue": "Scratched bronze key fragment found jammed in the deadbolt",
                    "completed": False,
                }
            ],
        )

        db.save_quest_waypoints(
            session_id=self.session_id,
            quest_id=qid,
            waypoints=[
                {
                    "stage_index": 1,
                    "stage_label": "Examine the lock mechanism",
                    "target_location": "Academic Building ➔ Vault",
                    "target_npc": "Archivist Donald",
                    "completion_trigger": "skill_check",
                }
            ],
            sub_obj_id=1,
        )

        self.session["current_location"] = "Academic Building ➔ Vault"

        actions = [
            {
                "label": "Carefully examine the deadbolt with a magnifying glass",
                "stat": "INT",
                "requirement": 5,
                "quest_id": qid,
                "sub_obj_id": 1,
                "is_quest_action": True,
                "check": {"succeeded": True, "result_tier": "success"},
            }
        ]

        res = resolve_pre_turn_quests_and_clues(self.session, self.party, actions)

        # Verification: sub-objective completed and clue registered
        self.assertEqual(len(res["completed_sub_quests"]), 1)
        clues = db.get_session_clues(self.session_id)
        self.assertGreaterEqual(len(clues), 1)
        clue = clues[0]
        self.assertIn("bronze key fragment", clue["lead_text"].lower())
        self.assertEqual(clue["source_location"], "Academic Building ➔ Vault")

    def test_caseboard_deductive_synthesis(self):
        """Two corroborating evidence records sharing a suspect automatically synthesize a Breakthrough (Q3)."""
        qid = "SQ-103"
        cur_ch = 1

        # Add two corroborating clues implicating "Council President Kevin"
        c1 = db.add_session_clue(
            session_id=self.session_id,
            title="Encrypted USB Stick",
            lead_text="Found in the student council office containing student records.",
            category="digital",
            source_location="Student Council Room",
            linked_npc="Council President Kevin",
            quest_id=qid,
            chapter=cur_ch,
        )
        c2 = db.add_session_clue(
            session_id=self.session_id,
            title="Witness Statement",
            lead_text="A janitor observed Council President Kevin entering the archive room at midnight.",
            category="testimonial",
            source_location="Archive Room",
            linked_npc="Council President Kevin",
            quest_id=qid,
            chapter=cur_ch,
        )

        # Run pre-turn resolution
        res = resolve_pre_turn_quests_and_clues(self.session, self.party, actions=[])

        # Verification: verified deduction clue synthesized
        verified_clues = db.get_session_clues(self.session_id, is_verified=1)
        self.assertGreaterEqual(len(verified_clues), 1)
        deduction = [c for c in verified_clues if c.get("category") == "deduction"][0]
        self.assertIn("Breakthrough", deduction["title"])
        self.assertIn("Kevin", deduction["linked_npc"])

        # Check directive was emitted
        breakthrough_directives = [d for d in res.get("directives", []) if "MANDATORY BREAKTHROUGH DEDUCTION" in d]
        self.assertGreaterEqual(len(breakthrough_directives), 1)

    def test_two_phase_climax_gate_standard(self):
        """Clearing all sub-objectives primes climax; resolving the climax completes chapter and seeds next (Q4)."""
        qid = "SQ-104"
        cur_ch = 1
        db.set_session_chapter(self.session_id, cur_ch)

        db.upsert_quest(
            session_id=self.session_id,
            quest_id=qid,
            quest_type="Story Quest",
            title="Chapter 1 Crisis",
            objective="Solve the campus mystery.",
            status="Active",
            reward_xp=300,
            reward_gold=75,
            is_story_quest=1,
            sub_objectives=[
                {"id": 1, "text": "Gather lead 1", "completed": True},
                {"id": 2, "text": "Gather lead 2", "completed": True},
            ],
        )

        db.save_quest_waypoints(
            session_id=self.session_id,
            quest_id=qid,
            waypoints=[
                {
                    "stage_index": 99,
                    "stage_label": "Confront the mastermind",
                    "target_location": "Academy Rooftop",
                    "target_npc": "Mastermind Vance",
                    "completion_trigger": "skill_check",
                }
            ],
            sub_obj_id=None,
        )

        self.session["current_location"] = "Academy Rooftop"
        self.session["chapter"] = cur_ch

        # Action: execute standard story climax
        actions = [
            {
                "label": "⚡ [Story Climax] Confront Mastermind Vance with the evidence",
                "stat": "CHA",
                "requirement": 6,
                "quest_id": qid,
                "is_quest_action": True,
                "is_climax_action": True,
                "check": {"succeeded": True, "result_tier": "success"},
            }
        ]

        res = resolve_pre_turn_quests_and_clues(self.session, self.party, actions)

        # Verification: Chapter 1 marked completed, chapter incremented to 2, and new story quest seeded
        self.assertIn(qid, res["completed_quests"])
        self.assertTrue(res["chapter_climax"])
        self.assertEqual(db.get_session_chapter(self.session_id), 2)

        # Ensure Chapter 2 Story Quest exists in DB
        next_sq = db.get_active_story_quest(self.session_id)
        self.assertIsNotNone(next_sq)
        self.assertEqual(next_sq["status"], "Active")

    def test_premature_climax_confrontation_penalty(self):
        """Arriving at climax venue with incomplete sub-objectives incurs +4 DC penalty; failure escalates strikes (A11)."""
        qid = "SQ-105"
        db.upsert_quest(
            session_id=self.session_id,
            quest_id=qid,
            quest_type="Story Quest",
            title="Chapter 1 Mystery",
            objective="Investigate before confronting.",
            status="Active",
            reward_xp=300,
            reward_gold=75,
            is_story_quest=1,
            sub_objectives=[
                {"id": 1, "text": "Gather physical evidence", "completed": False},
                {"id": 2, "text": "Interview witness", "completed": False},
            ],
        )

        db.save_quest_waypoints(
            session_id=self.session_id,
            quest_id=qid,
            waypoints=[
                {
                    "stage_index": 99,
                    "stage_label": "Showdown",
                    "target_location": "Abandoned Gym",
                    "target_npc": "Rival Gary",
                    "completion_trigger": "skill_check",
                }
            ],
            sub_obj_id=None,
        )

        self.session["current_location"] = "Abandoned Gym"

        # 1. Choices generation must present premature climax with +4 DC penalty
        choices = generate_quest_action_choices(self.session_id, "Abandoned Gym", scen_key="high_school_drama", char=self.char)
        premature_choices = [c for c in choices if c.get("is_premature_climax")]
        self.assertEqual(len(premature_choices), 1)
        p_choice = premature_choices[0]
        # Base DC is 6 (char CHA is 6, req = min(10, 6) = 6), premature is 6 + 4 = 10
        self.assertEqual(p_choice["requirement"], 10)

        # 2. Executing premature confrontation and failing triggers +2 strikes
        fail_actions = [
            {
                "label": "⚡ [Story Climax - Premature Showdown] Force confrontation",
                "stat": "CHA",
                "requirement": 10,
                "quest_id": qid,
                "is_quest_action": True,
                "is_climax_action": True,
                "check": {"succeeded": False, "result_tier": "failure"},
            }
        ]

        res = resolve_pre_turn_quests_and_clues(self.session, self.party, fail_actions)
        q_after = db.get_quest_by_id(self.session_id, qid)
        self.assertEqual(int(q_after.get("strikes") or 0), 2)
        premature_directives = [d for d in res.get("directives", []) if "PREMATURE CLIMAX FAILED" in d]
        self.assertEqual(len(premature_directives), 1)

    def test_companion_privacy_gate_for_assists(self):
        """Companions waiting outside private rooms cannot assist with internal waypoint checks (A18)."""
        # Save a private room node
        db.save_world_node(
            self.session_id, "room_dorm_private", "fac_dorms", "Alice's Private Room",
            node_type="ROOM", privacy_level="private"
        )
        db.add_session_party_npc(self.session_id, {"name": "Bob"})
        db.update_session(self.session_id, extra={"current_node_id": "room_dorm_private"})

        sess = db.get_session(self.session_id)
        comp = get_active_companion_for_waypoint(sess, {"target_npc": ""})
        # Must return None because Bob is waiting outside
        self.assertIsNone(comp)

    def test_bounty_forfeiture(self):
        """Forfeiting an active side bounty applies -5 client affinity, clears waypoints, and marks Abandoned (A16)."""
        qid = "BNT-FORFEIT"
        client_name = "Chloe Davis"
        db.upsert_contact(self.session_id, "chloe_davis", client_name, basic_info={"role": "Student", "description": "Classmate"}, delta_score=20)

        db.upsert_quest(
            session_id=self.session_id,
            quest_id=qid,
            quest_type="Side Bounty",
            title="Escort Caravan",
            objective="Deliver cargo safely.",
            client_npc=client_name,
            status="Active",
            reward_xp=100,
            reward_gold=40,
            is_story_quest=0,
        )

        db.save_quest_waypoints(
            session_id=self.session_id,
            quest_id=qid,
            waypoints=[
                {
                    "stage_index": 1,
                    "stage_label": "Meet caravan",
                    "target_location": "East Gate",
                    "completion_trigger": "arrival",
                }
            ],
            sub_obj_id=None,
        )

        res = forfeit_side_bounty(self.session_id, qid, [self.user_id])
        self.assertTrue(res["success"])
        self.assertEqual(res["client_affinity_delta"], -5)

        q_after = db.get_quest_by_id(self.session_id, qid)
        self.assertEqual(q_after["status"], "Abandoned")

        # Contact affinity should have dropped from 20 to 15
        chloe = db.get_contact(self.session_id, client_name)
        self.assertIsNotNone(chloe)
        self.assertEqual(chloe["relationship_score"], 15)

    def test_bounty_concurrency_cap(self):
        """A session can hold at most 3 active side bounties concurrently (A17)."""
        self.assertTrue(can_accept_side_bounty(self.session_id))

        # Add 3 active bounties
        for i in range(1, 4):
            db.upsert_quest(
                session_id=self.session_id,
                quest_id=f"BNT-00{i}",
                quest_type="Side Bounty",
                title=f"Bounty #{i}",
                objective="Task",
                status="Active",
                reward_xp=50,
                reward_gold=20,
                is_story_quest=0,
            )

        # Now should be capped
        self.assertFalse(can_accept_side_bounty(self.session_id))

    def test_suspect_elimination_pocket_clue_drop(self):
        """Defeating an investigation suspect extracts vital pocket evidence fail-forward into session_clues (A14)."""
        qid = "SQ-106"
        suspect_name = "Smuggler Jax"
        db.upsert_quest(
            session_id=self.session_id,
            quest_id=qid,
            quest_type="Story Quest",
            title="The Contraband Ring",
            objective=f"Track down {suspect_name} and find the contraband source.",
            status="Active",
            reward_xp=250,
            reward_gold=60,
            is_story_quest=1,
            sub_objectives=[{"id": 1, "text": f"Interrogate {suspect_name}", "completed": False}],
        )

        res = check_and_extract_defeated_suspect_evidence(self.session_id, suspect_name, cur_loc="Underground Warehouse")
        self.assertIsNotNone(res)
        self.assertIn("Pocket Evidence", res["title"])

        clues = db.get_session_clues(self.session_id, linked_npc=suspect_name)
        self.assertEqual(len(clues), 1)
        self.assertIn("encrypted diary", clues[0]["lead_text"].lower())


if __name__ == "__main__":
    unittest.main()
