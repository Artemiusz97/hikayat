"""
Comprehensive test suite for Hikayat's 6 Modernized Legacy Systems:
1. Campus Directory & School Roster Canonicalization
2. Ad-Hoc Loot Classification & Item Enrichment
3. Fuzzy Item Removal in SQLite
4. Non-Combat Social Companions & Universal Escorts
5. Deterministic Campaign Goal Pacing & Clamping
6. Grounded Clue Discovery on Sub-Objective Completion
7. Hostile Entity Consolidation via get_active_enemies
"""
import unittest
import db
import game_engine
import mechanics.combat.items as items_mod
import mechanics.social.school_roster as roster_mod


class TestModernizedLegacySystems(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        db.init_db()
        cls.test_session_id = 998877
        with db.get_conn() as conn:
            conn.execute("DELETE FROM sessions WHERE id=?", (cls.test_session_id,))
            conn.execute("DELETE FROM quests WHERE session_id=?", (cls.test_session_id,))
            conn.execute("DELETE FROM school_directory WHERE session_id=?", (cls.test_session_id,))
            conn.execute("DELETE FROM characters WHERE user_id=?", (99887701,))
            conn.execute("DELETE FROM inventory WHERE user_id=?", (99887701,))

        cls.user_id = 99887701
        db.create_character(cls.user_id, "Alex Tester", char_class="Student", gender="male", scenario="high_school_drama", race="human")
        cls.test_session_id = db.create_session(
            host_user_id=cls.user_id,
            mode="single",
            capacity=1,
            verbosity="normal",
            dialogue_mode="balanced",
            image_gen_enabled=False,
            scenario="high_school_drama"
        )

    @classmethod
    def tearDownClass(cls):
        with db.get_conn() as conn:
            conn.execute("DELETE FROM sessions WHERE id=?", (cls.test_session_id,))
            conn.execute("DELETE FROM quests WHERE session_id=?", (cls.test_session_id,))
            conn.execute("DELETE FROM school_directory WHERE session_id=?", (cls.test_session_id,))
            conn.execute("DELETE FROM characters WHERE user_id=?", (cls.user_id,))
            conn.execute("DELETE FROM inventory WHERE user_id=?", (cls.user_id,))

    def test_01_school_roster_canonical_facilities(self):
        directory = roster_mod.generate_campus_directory(self.test_session_id, scen_key="high_school_drama")
        self.assertGreaterEqual(len(directory), 45)
        for entry in directory:
            for f in (entry.get("primary_facility", ""), entry.get("secondary_facility", "")):
                if f:
                    for wing in ("Administration Wing", "Science Wing", "Academic Wing", "Faculty Wing", "Arts & Music Wing", "Media Center"):
                        self.assertNotIn(wing, f, f"Intermediate wing '{wing}' found in {f}")



    def test_03_ad_hoc_loot_enrichment(self):
        w = items_mod.classify_and_enrich_ad_hoc_item("Masterwork Katana", "fantasy")
        self.assertEqual(w["item_type"], "Weapon")
        self.assertEqual(w["slot"], "Weapon")
        self.assertEqual(w["tier"], 2)
        self.assertIn("[GEAR_JSON]", w["effect"])

        p = items_mod.classify_and_enrich_ad_hoc_item("Greater Mana Potion", "fantasy")
        self.assertEqual(p["item_type"], "Potion")
        self.assertIn("[CONSUMABLE_JSON]", p["effect"])
        meta_p = items_mod.parse_consumable_metadata(p)
        self.assertEqual(meta_p["purpose_tags"], ["mana"])

        f = items_mod.classify_and_enrich_ad_hoc_item("Sweet Strawberry Pastry", "high_school_drama")
        self.assertEqual(f["item_type"], "Food")
        meta_f = items_mod.parse_consumable_metadata(f)
        self.assertIn("sweet", meta_f["taste_tags"])

        k = items_mod.classify_and_enrich_ad_hoc_item("Library Archive Key", "high_school_drama")
        self.assertEqual(k["item_type"], "Key Item")
        self.assertEqual(k["slot_cost"], 0)
        self.assertTrue(items_mod.is_key_item(k))
        parsed_k = items_mod.parse_item_effect(k)
        self.assertEqual(parsed_k["category"], "key_item")

        # Test safe examination on usage (item must NOT be consumed)
        db.add_item(self.user_id, k["name"], k["item_type"], k["effect"], slot_cost=k["slot_cost"], force=True)
        ok, msg = items_mod.apply_item_to_target(self.user_id, k, "self", "Yourself")
        self.assertTrue(ok)
        self.assertIn("Examining Narrative Artifact", msg)
        inv = db.get_inventory(self.user_id)
        self.assertTrue(any(i["name"] == k["name"] for i in inv), "Key Item should not be consumed on use")

        # Test icon resolution
        from character_data import get_item_icon
        self.assertEqual(get_item_icon(k["name"], k["item_type"]), "📜")
        self.assertEqual(get_item_icon("Holy Relic", "Quest"), "📜")

    def test_04_fuzzy_item_removal(self):
        db.add_item(self.user_id, "Reinforced Steel Longsword", "Weapon", "test gear", force=True)
        success = db.remove_item_by_name(self.user_id, "steel sword")
        self.assertTrue(success)
        inv = db.get_inventory(self.user_id)
        self.assertFalse(any(i["name"] == "Reinforced Steel Longsword" for i in inv))

    def test_05_social_companions_travel(self):
        comp_data = {
            "name": "Maya",
            "role": "Friend",
            "level": 1,
            "hp": 100,
            "max_hp": 100,
            "mp": 100,
            "max_mp": 100,
            "origin_location": "Sakura Hill Residential Town ➔ Anderson Residence ➔ Living Room"
        }
        db.add_session_party_npc(self.test_session_id, comp_data)
        sess = db.get_session(self.test_session_id)
        sess["current_npcs"] = [{"name": "Maya"}, {"name": "Classmate Bystander"}]
        sess["current_location"] = "Westlake Academy ➔ Classroom 2-B (Homeroom) ➔ Main Area"

        traveling, left_behind = game_engine.classify_scene_npcs(
            session=sess,
            actions=[{"label": "Walk over to the cafeteria for lunch"}],
            old_primary="Classroom 2-B (Homeroom)",
            dest_primary="Cafeteria"
        )
        self.assertTrue(any(t.get("name") == "Maya" for t in traveling))
        self.assertTrue(any(lb.get("name") == "Classmate Bystander" for lb in left_behind))

    def test_06_campaign_goal_pacing(self):
        # 1. Chapter 1: ceiling is 10%
        db.set_session_chapter(self.test_session_id, 1)
        test_goals = [{"id": "G_MAIN", "title": "Main Mystery", "progress_pct": 0, "status": "Active"}]
        db.update_session_campaign_goals(self.test_session_id, test_goals)

        game_engine.apply_quest_update(
            session_id=self.test_session_id,
            quest_update={"goal_progress_updates": {"G_MAIN": 85}},
            party_user_ids=[self.user_id]
        )
        updated = db.get_session_campaign_goals(self.test_session_id)
        self.assertEqual(updated[0]["progress_pct"], 10, "Chapter 1 must clamp to 10%")

        # 2. Chapter 5 (Midpoint): ceiling is 50%
        db.set_session_chapter(self.test_session_id, 5)
        game_engine.apply_quest_update(
            session_id=self.test_session_id,
            quest_update={"goal_progress_updates": {"G_MAIN": 90}},
            party_user_ids=[self.user_id]
        )
        updated5 = db.get_session_campaign_goals(self.test_session_id)
        self.assertEqual(updated5[0]["progress_pct"], 50, "Chapter 5 must clamp to 50%")

        # 3. Chapter 10 (Grand Finale): allows 100% and completion
        db.set_session_chapter(self.test_session_id, 10)
        game_engine.apply_quest_update(
            session_id=self.test_session_id,
            quest_update={"goal_progress_updates": {"G_MAIN": 100}},
            party_user_ids=[self.user_id]
        )
        updated10 = db.get_session_campaign_goals(self.test_session_id)
        self.assertEqual(updated10[0]["progress_pct"], 100, "Chapter 10 must reach 100%")
        self.assertEqual(updated10[0]["status"], "Completed")

    def test_07_deterministic_clue_grounding(self):
        db.upsert_quest(
            session_id=self.test_session_id,
            quest_id="QST-INVESTIGATE-01",
            quest_type="Story Quest",
            title="The Lost Notebook",
            objective="Discover who took the notebook.",
            progress="0/1 Cleared",
            current_clues="",
            status="Active",
            sub_objectives=[{"id": 1, "text": "Search the chemistry counter for fingerprints", "completed": False}]
        )
        notice = game_engine.apply_quest_update(
            session_id=self.test_session_id,
            quest_update={"quest_id": "QST-INVESTIGATE-01", "completed_sub_objective_ids": [1]},
            party_user_ids=[self.user_id]
        )
        q = db.get_quest_by_id(self.test_session_id, "QST-INVESTIGATE-01")
        self.assertIn("Search the chemistry counter", q.get("current_clues", ""))
        self.assertIsNotNone(notice.get("newly_discovered_clue"))

    def test_08_get_active_enemies(self):
        data_new = {"nearby_enemies": [{"name": "Goblin Scout", "hp": 15}]}
        self.assertEqual(len(game_engine.get_active_enemies(data_new)), 1)
        self.assertEqual(game_engine.get_active_enemies(data_new)[0]["name"], "Goblin Scout")
        self.assertEqual(game_engine.get_active_enemies({}), [])


if __name__ == "__main__":
    unittest.main()

