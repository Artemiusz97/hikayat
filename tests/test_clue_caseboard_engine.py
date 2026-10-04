import unittest
import time
import db
import game_engine
from mechanics.narrative.clues import categorize_clue, evaluate_clue_deduction, format_caseboard_prompt_context
from mechanics.system.phone import log_gossip_clue_to_quest
from cogs.adventure import _build_caseboard_embed, _build_main_quest_embed


class TestClueCaseboardEngine(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        db.init_db()
        cls.user_id = 99912345
        cls.session_id = 88877766
        with db.get_conn() as conn:
            conn.execute("DELETE FROM session_clues WHERE session_id=?", (cls.session_id,))
            conn.execute("DELETE FROM quests WHERE session_id=?", (cls.session_id,))
            conn.execute("DELETE FROM sessions WHERE id=?", (cls.session_id,))
            conn.execute("DELETE FROM characters WHERE user_id=?", (cls.user_id,))

        db.create_character(cls.user_id, "Detective Maya", char_class="Student", gender="female", scenario="high_school_drama", race="human")
        cls.session_id = db.create_session(
            host_user_id=cls.user_id,
            mode="single",
            capacity=1,
            verbosity="normal",
            dialogue_mode="balanced",
            image_gen_enabled=False,
            scenario="high_school_drama"
        )
        db.set_session_chapter(cls.session_id, 1)

    @classmethod
    def tearDownClass(cls):
        with db.get_conn() as conn:
            conn.execute("DELETE FROM session_clues WHERE session_id=?", (cls.session_id,))
            conn.execute("DELETE FROM quests WHERE session_id=?", (cls.session_id,))
            conn.execute("DELETE FROM sessions WHERE id=?", (cls.session_id,))
            conn.execute("DELETE FROM characters WHERE user_id=?", (cls.user_id,))

    def setUp(self):
        with db.get_conn() as conn:
            conn.execute("DELETE FROM session_clues WHERE session_id=?", (self.session_id,))
            conn.execute("DELETE FROM quests WHERE session_id=?", (self.session_id,))
        db.set_session_chapter(self.session_id, 1)

    def test_01_clue_table_crud(self):
        # 1. Add clues of different categories
        c1 = db.add_session_clue(
            session_id=self.session_id,
            title="Muddy Sneaker Print",
            lead_text="Found reddish clay sneaker footprint outside chemistry lab window.",
            category="physical",
            source_location="Science Lab",
            linked_npc="Dr. Legacy",
            chapter=1
        )
        self.assertGreater(c1, 0)

        c2 = db.add_session_clue(
            session_id=self.session_id,
            title="Locker Whispers",
            lead_text="Overheard Vice President saying the schedule was switched yesterday.",
            category="testimonial",
            source_location="Hallway",
            linked_npc="Vice President",
            chapter=1
        )
        self.assertGreater(c2, 0)

        # 2. Deduplication: exact or near-duplicate returns existing id
        c1_dup = db.add_session_clue(
            session_id=self.session_id,
            title="Muddy Sneaker Print",
            lead_text="Found reddish clay sneaker footprint outside chemistry lab window.",
            category="physical"
        )
        self.assertEqual(c1, c1_dup, "Duplicate clue must return existing ID")

        # 3. Querying & Filtering
        all_clues = db.get_session_clues(self.session_id)
        self.assertEqual(len(all_clues), 2)

        phys_clues = db.get_session_clues(self.session_id, category="physical")
        self.assertEqual(len(phys_clues), 1)
        self.assertEqual(phys_clues[0]["id"], c1)

        npc_clues = db.get_session_clues(self.session_id, linked_npc="Dr. Legacy")
        self.assertEqual(len(npc_clues), 1)
        self.assertEqual(npc_clues[0]["id"], c1)

        # 4. Verify clue
        self.assertFalse(bool(all_clues[0]["is_verified"]))
        db.verify_session_clue(c1)
        updated_c1 = db.get_session_clue_by_id(c1)
        self.assertTrue(bool(updated_c1["is_verified"]))

    def test_03_cross_chapter_persistence(self):
        # Add clue in Chapter 1
        db.add_session_clue(
            session_id=self.session_id,
            title="Ancient Sealed Pendant",
            lead_text="An engraved obsidian pendant discovered in Chapter 1.",
            category="physical",
            chapter=1
        )

        # Advance session to Chapter 5
        db.set_session_chapter(self.session_id, 5)

        # Clue must still exist in session_clues
        all_clues = db.get_session_clues(self.session_id)
        self.assertEqual(len(all_clues), 1)
        self.assertEqual(all_clues[0]["chapter"], 1)
        self.assertEqual(all_clues[0]["title"], "Ancient Sealed Pendant")

    def test_04_investigation_sub_objective_hook(self):
        db.upsert_quest(
            session_id=self.session_id,
            quest_id="SQ-INVEST",
            quest_type="Story Quest",
            title="Lab Intrusion",
            objective="Find the culprit",
            sub_objectives=[
                {"id": 1, "text": "Search the chemistry counter for fingerprints", "completed": False}
            ]
        )

        game_engine.apply_quest_update(
            session_id=self.session_id,
            quest_update={
                "title": "Lab Intrusion",
                "completed_sub_quest_ids": [1]
            },
            party_user_ids=[self.user_id]
        )

        clues = db.get_session_clues(self.session_id)
        self.assertEqual(len(clues), 1)
        self.assertIn("chemistry counter for fingerprints", clues[0]["lead_text"].lower())

    def test_05_smartphone_rumor_integration(self):
        success = log_gossip_clue_to_quest(
            self.session_id,
            "Anonymous Post: Saw Maya talking to Dr. Legacy near the rooftop garden after 6 PM."
        )
        self.assertTrue(success)

        clues = db.get_session_clues(self.session_id)
        self.assertEqual(len(clues), 1)
        self.assertEqual(clues[0]["category"], "digital")
        self.assertIn("Maya talking to Dr. Legacy", clues[0]["lead_text"])

    def test_06_deduction_breakthrough_synthesis(self):
        c1 = db.add_session_clue(
            session_id=self.session_id,
            title="Red Clay on Sneaker",
            lead_text="Found red clay footprint matching student shoes.",
            source_location="Courtyard",
            linked_npc="Dr. Legacy",
            chapter=1
        )
        c2 = db.add_session_clue(
            session_id=self.session_id,
            title="Greenhouse Soil Sample",
            lead_text="Exclusive red clay soil stored only in Dr. Legacy's greenhouse.",
            source_location="Greenhouse",
            linked_npc="Dr. Legacy",
            chapter=1
        )

        clue_a = db.get_session_clue_by_id(c1)
        clue_b = db.get_session_clue_by_id(c2)

        is_valid, title, detail_text = evaluate_clue_deduction(clue_a, clue_b, scen_key="high_school_drama")
        self.assertTrue(is_valid)
        self.assertIn("Dr. Legacy", title)

        # Synthesize into DB
        breakthrough_id = db.synthesize_deduction_clue(
            self.session_id,
            [c1, c2],
            title,
            detail_text,
            chapter=1
        )
        self.assertGreater(breakthrough_id, 0)

        # Parents verified
        updated_c1 = db.get_session_clue_by_id(c1)
        updated_c2 = db.get_session_clue_by_id(c2)
        self.assertTrue(bool(updated_c1["is_verified"]))
        self.assertTrue(bool(updated_c2["is_verified"]))

        # Deduction row verified
        d_row = db.get_session_clue_by_id(breakthrough_id)
        self.assertEqual(d_row["category"], "deduction")
        self.assertTrue(bool(d_row["is_verified"]))
        self.assertEqual(d_row["deduction_parents"], [c1, c2])

    def test_07_main_quest_ui_clue_visibility(self):
        # Add a clue to session_clues
        db.add_session_clue(
            session_id=self.session_id,
            title="Burned Note Fragment",
            lead_text="Contains the initials D.L. and locker 14.",
            chapter=1
        )

        db.upsert_quest(
            session_id=self.session_id,
            quest_id="SQ-ACTIVE",
            quest_type="Story Quest",
            title="Active Mystery",
            objective="Discover the truth",
            current_clues="",  # empty string in quests table
            is_story_quest=1
        )

        # Embed must fallback to chapter's session_clues and display it
        embed = _build_main_quest_embed(self.session_id)
        field_names = [f.name for f in embed.fields]
        self.assertTrue(any("Investigation Notes" in name for name in field_names))
        notes_field = next(f for f in embed.fields if "Investigation Notes" in f.name)
        self.assertIn("Burned Note Fragment", notes_field.value)

    def test_08_choice_view_with_party_companion(self):
        from cogs.adventure import ChoiceView
        db.set_session_party_npcs(self.session_id, [
            {"name": "Maya", "role": "Companion", "hp": 25, "max_hp": 25, "dismissed": False}
        ])
        char = db.get_character(self.user_id)
        choices = [{"label": "Investigate classroom", "stat": "INT", "requirement": 10}]
        view = ChoiceView(None, self.session_id, self.user_id, choices, char)
        
        # Verify companion button exists and callback is callable
        companion_btn = next((item for item in view.children if getattr(item, "label", None) in ("Party", "Companions")), None)
        self.assertIsNotNone(companion_btn, "Companion button must be present in ChoiceView when party_npcs exist")
        self.assertTrue(callable(companion_btn.callback))
        self.assertEqual(companion_btn.callback, view._party_dialogue_callback)


if __name__ == "__main__":
    unittest.main()
