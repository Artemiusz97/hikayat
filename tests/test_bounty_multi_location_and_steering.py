import json
import os
import sys
import unittest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import db
import game_engine
import mechanics.world.waypoints as waypoints
from cogs.adventure import _build_bounties_embed


class TestBountyMultiLocationAndSteering(unittest.TestCase):

    def setUp(self):
        self.session_id = 88776655
        db.init_db()
        with db.get_conn() as conn:
            conn.execute("DELETE FROM session_locations WHERE session_id = ?", (self.session_id,))
            conn.execute("DELETE FROM quests WHERE session_id = ?", (self.session_id,))
            conn.execute("DELETE FROM quest_waypoints WHERE session_id = ?", (self.session_id,))
            conn.execute("DELETE FROM sessions WHERE id = ?", (self.session_id,))
            conn.execute(
                "INSERT INTO sessions (id, mode, capacity, scenario, current_location) VALUES (?, 'solo', 1, 'high_school_drama', 'Westlake Academy -> Academic Wing -> Classroom 3-B')",
                (self.session_id,)
            )
            conn.commit()

        self.char = {
            "name": "Artemiusz",
            "gender": "Male",
            "cha_": 8,
            "int_": 9,
            "per_": 7,
            "agi_": 6,
            "str_": 5,
            "end_": 6
        }

    def tearDown(self):
        with db.get_conn() as conn:
            conn.execute("DELETE FROM session_locations WHERE session_id = ?", (self.session_id,))
            conn.execute("DELETE FROM quests WHERE session_id = ?", (self.session_id,))
            conn.execute("DELETE FROM quest_waypoints WHERE session_id = ?", (self.session_id,))
            conn.execute("DELETE FROM sessions WHERE id = ?", (self.session_id,))
            conn.commit()

    def test_bounty_overview_ui_shows_only_name_and_objective(self):
        """Verify overview mode embed shows only title and objective, not progress or rewards."""
        db.upsert_quest(
            session_id=self.session_id,
            quest_id="BNT-SECRET",
            quest_type="Secret Admirer",
            title="The Anonymous Note Delivery",
            objective="Justin has a crush on a senior; deliver the notes without being caught.",
            progress="Stage 1/3: Meet Justin",
            current_clues="",
            status="Active",
            reward_xp=120,
            reward_gold=50,
            reward_stat_points=0,
            reward_item="Custom Scented Stationery Set"
        )
        db.save_quest_waypoints(
            session_id=self.session_id,
            quest_id="BNT-SECRET",
            waypoints=[
                {"stage_index": 1, "stage_label": "Meet Justin", "target_location": "Westlake Academy -> Classroom 3-B", "target_npc": "Justin Anderson", "completion_trigger": "arrival"},
                {"stage_index": 2, "stage_label": "Deliver note", "target_location": "Westlake Academy -> Student Council Office", "target_npc": "Senior", "completion_trigger": "skill_check"},
                {"stage_index": 3, "stage_label": "Confirm delivery", "target_location": "Westlake Academy -> Classroom 3-B", "target_npc": "Justin Anderson", "completion_trigger": "skill_check"},
            ],
            sub_obj_id=None
        )

        # 1. Overview Mode (selected_quest_id is None)
        overview_embed = _build_bounties_embed(self.session_id, selected_quest_id=None)
        self.assertEqual(len(overview_embed.fields), 1)
        f_name = overview_embed.fields[0].name
        f_val = overview_embed.fields[0].value

        self.assertIn("The Anonymous Note Delivery", f_name)
        self.assertIn("Secret Admirer", f_name)
        self.assertIn("Justin has a crush on a senior", f_val)
        # Must NOT show progress stages or rewards in overview
        self.assertNotIn("Stage 1/3", f_val)
        self.assertNotIn("Custom Scented Stationery Set", f_val)
        self.assertNotIn("Rewards:", f_val)

        # 2. Detailed Inspector Mode (selected_quest_id is "BNT-SECRET")
        detail_embed = _build_bounties_embed(self.session_id, selected_quest_id="BNT-SECRET")
        detail_text = " ".join(f.value for f in detail_embed.fields)
        self.assertTrue(any("Progression Roadmap" in f.name for f in detail_embed.fields))
        self.assertIn("Custom Scented Stationery Set", detail_text)
        self.assertIn("Classroom 3-B", detail_text)

    def test_multi_location_archetypes_and_no_anomaly_barrier(self):
        """Verify school and delivery archetypes have templates and don't inject anomaly barriers."""
        for arch in ("secret admirer", "matchmaking", "courier", "delivery", "academic rescue", "gossip control"):
            self.assertIn(arch, waypoints.ARCHETYPE_WAYPOINT_TEMPLATES)
            stages = waypoints.ARCHETYPE_WAYPOINT_TEMPLATES[arch]
            self.assertGreaterEqual(len(stages), 3)

        # Expanding 2 stages for Secret Admirer must not contain fantasy anomaly barriers
        two_stages = [
            {"stage_index": 1, "stage_label": "Meet Justin to take the note", "target_location": "Academy -> Classroom 3-B", "target_npc": "Justin Anderson", "completion_trigger": "arrival"},
            {"stage_index": 2, "stage_label": "Deliver the note to the senior", "target_location": "Academy -> Student Council Office", "target_npc": "Senior", "completion_trigger": "skill_check"},
        ]
        expanded = waypoints.ensure_multi_stage_waypoints(
            two_stages,
            default_loc="Academy -> Classroom 3-B",
            archetype="Secret Admirer"
        )
        self.assertEqual(len(expanded), 3)
        mid_label = expanded[1]["stage_label"]
        self.assertNotIn("Investigate anomalies", mid_label)
        self.assertNotIn("barrier", mid_label.lower())
        self.assertIn("delivery destination", mid_label.lower())

    def test_bounty_dialogue_steering_directive_and_choice_enrichment(self):
        """Verify talking to a bounty client injects BOUNTY COOPERATION directive and tags quest action."""
        db.upsert_quest(
            session_id=self.session_id,
            quest_id="BNT-NOTE",
            quest_type="Secret Admirer",
            title="The Anonymous Note Delivery",
            objective="Deliver Justin's love letter secretly.",
            progress="Stage 1/3: Meet Justin",
            current_clues="",
            status="Active"
        )
        db.save_quest_waypoints(
            session_id=self.session_id,
            quest_id="BNT-NOTE",
            waypoints=[{
                "stage_index": 1,
                "stage_label": "Meet with Justin Anderson to receive the secret letter",
                "target_location": "Westlake Academy -> Academic Wing -> Classroom 3-B",
                "target_npc": "Justin Anderson",
                "completion_trigger": "skill_check"
            }],
            sub_obj_id=None
        )

        db.save_session_scene(
            self.session_id,
            scene_title="Classroom Conversation",
            narrative="Justin Anderson clutches a sealed envelope tightly against his chest.",
            choices=[],
            history=["Turn 1"],
            location="Westlake Academy -> Academic Wing -> Classroom 3-B",
            current_npcs=[{"name": "Justin Anderson", "role": "Student"}],
            dialogue_partner="Justin Anderson"
        )

        # 1. When raw choice contains a substantive task keyword ("secret letter"), it gets tagged
        raw_choices_1 = [
            {"label": "Agree to take the secret letter from Justin and help him", "stat": "CHA", "requirement": 6},
            {"label": "Ask about homework assignments", "stat": "INT", "requirement": 5},
            {"label": "Thank Justin and excuse yourself to step away", "stat": "NONE", "requirement": 0}
        ]

        enriched_1 = waypoints.tag_and_enrich_quest_choices(
            raw_choices_1,
            session_id=self.session_id,
            current_location="Westlake Academy -> Academic Wing -> Classroom 3-B",
            scen_key="high_school_drama",
            char=self.char
        )
        bounty_choices_1 = [c for c in enriched_1 if c.get("is_quest_action") and c.get("quest_id") == "BNT-NOTE"]
        self.assertEqual(len(bounty_choices_1), 1)
        self.assertIn("secret letter", bounty_choices_1[0]["label"].lower())

        # 2. When raw choices are off-topic (e.g. video games, homework), the off-topic choices are NOT tagged,
        # and Hikayat guarantees an injected in-dialogue bounty choice
        raw_choices_2 = [
            {"label": "Ask Justin what video games he likes to play", "stat": "INT", "requirement": 5},
            {"label": "Talk about tomorrow's math quiz", "stat": "INT", "requirement": 6},
            {"label": "Thank him and excuse yourself to step away", "stat": "NONE", "requirement": 0}
        ]
        enriched_2 = waypoints.tag_and_enrich_quest_choices(
            raw_choices_2,
            session_id=self.session_id,
            current_location="Westlake Academy -> Academic Wing -> Classroom 3-B",
            scen_key="high_school_drama",
            char=self.char
        )
        bounty_choices_2 = [c for c in enriched_2 if c.get("is_quest_action") and c.get("quest_id") == "BNT-NOTE"]
        self.assertEqual(len(bounty_choices_2), 1)
        # The injected choice is about the task with Justin Anderson
        self.assertIn("Justin Anderson", bounty_choices_2[0]["label"])
        # The gaming choice must NOT be tagged as quest action
        gaming_choice = next(c for c in enriched_2 if "video games" in c["label"])
        self.assertFalse(gaming_choice.get("is_quest_action", False))


if __name__ == "__main__":
    unittest.main()
