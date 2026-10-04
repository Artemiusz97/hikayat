import unittest
from mechanics.social.persona import (
    generate_dynamic_intimate_attributes,
    normalize_appearance,
    format_persona_embed_fields,
    generate_past_intimate_history
)
from mechanics.social.relationships import (
    get_information_disclosure_penalty,
    get_disclosure_check_requirement,
    get_unlocked_info_level
)

class TestIntimateDisclosure(unittest.TestCase):
    def test_unlocked_info_level_1_to_3_scale(self):
        # 1-3 scale
        self.assertEqual(get_unlocked_info_level(0), 1)
        self.assertEqual(get_unlocked_info_level(15), 1)
        self.assertEqual(get_unlocked_info_level(30), 1)
        self.assertEqual(get_unlocked_info_level(31), 2)
        self.assertEqual(get_unlocked_info_level(65), 2)
        self.assertEqual(get_unlocked_info_level(70), 2)
        self.assertEqual(get_unlocked_info_level(71), 3)
        self.assertEqual(get_unlocked_info_level(100), 3)

    def test_past_intimate_history_safeguards(self):
        # Strict safeguard: Virgins or unknowns MUST NEVER generate past history
        self.assertIsNone(generate_past_intimate_history(intercourse="virgin", hash_val=10, gender="female"))
        self.assertIsNone(generate_past_intimate_history(intercourse="unknown", hash_val=10, gender="female"))
        self.assertIsNone(generate_past_intimate_history(intercourse="", hash_val=10, gender="female"))

        # Experienced characters generate clean past history records with opposite gender partners & specific counts
        res_oral = generate_past_intimate_history(oral="has_done_oral", hash_val=42, gender="female", scenario="high_school_drama")
        self.assertIsNotNone(res_oral)
        self.assertIn("Past History: Performed oral", res_oral["entry"])
        self.assertTrue(any(c in res_oral["entry"] for c in ("1 time", "2 times", "3 times", "4 times", "5 times")))
        self.assertIn(res_oral["partner_name"], res_oral["entry"])

        res_non_virg = generate_past_intimate_history(intercourse="non_virgin", hash_val=15, gender="male", scenario="fantasy")
        self.assertIsNotNone(res_non_virg)
        self.assertIn("Past History:", res_non_virg["entry"])
        self.assertTrue(any(c in res_non_virg["entry"] for c in ("1 time", "2 times", "3 times", "4 times", "5 times")))
        self.assertIn(res_non_virg["partner_name"], res_non_virg["entry"])

    def test_disclosure_penalties_and_requirements(self):
        # Level 1 target: surface info always accessible
        self.assertEqual(get_information_disclosure_penalty(0, 1), 0)
        self.assertEqual(get_information_disclosure_penalty(15, 1), 0)

        # Level 2 target: Mannerisms / Traits
        self.assertEqual(get_information_disclosure_penalty(0, 2), -4)
        self.assertEqual(get_information_disclosure_penalty(20, 2), -2)
        self.assertEqual(get_information_disclosure_penalty(40, 2), 0)

        # Level 3 target: Preferences / Intimate Profile / Deep Secrets
        self.assertEqual(get_information_disclosure_penalty(0, 3), -8)
        self.assertEqual(get_information_disclosure_penalty(20, 3), -5)
        self.assertEqual(get_information_disclosure_penalty(50, 3), -3)
        self.assertEqual(get_information_disclosure_penalty(75, 3), 0)

        # Requirement calculation
        self.assertEqual(get_disclosure_check_requirement(4, current_score=0, target_info_level=3), 12)
        self.assertEqual(get_disclosure_check_requirement(4, current_score=50, target_info_level=3), 7)
        self.assertEqual(get_disclosure_check_requirement(4, current_score=80, target_info_level=3), 4)
    def test_db_get_known_world_data_loads_appearance(self):
        import db, time
        db.init_db()
        sess_id = int(time.time() * 1000)
        db.upsert_lorebook_entity(
            session_id=sess_id,
            entity_type="person",
            name="Kana Watanabe",
            race="fox-beastfolk",
            appearance={
                "eye_color": "amethyst",
                "breast_size": "c-cup",
                "sensitive_spots": "Base of tail",
                "turn_ons": "Neck kisses"
            }
        )
        world_data = db.get_known_world_data(sess_id)
        persons = world_data["lore"]["person"]
        self.assertTrue(len(persons) > 0)
        kana = next(p for p in persons if p["name"] == "Kana Watanabe")
        self.assertIsNotNone(kana.get("appearance"))
    def test_apply_outcome_actions_handling(self):
        import db, time, game_engine
        db.init_db()
        sess_id = int(time.time() * 1000)
        party = [({"id": 1, "user_id": 99999, "name": "Artemiusz", "hp": 20, "max_hp": 20, "mp": 10, "max_mp": 10, "stats": {"STR": 5, "AGI": 5, "END": 5, "INT": 5, "PER": 5, "CHA": 5, "LUK": 5}}, [])]
        outcome = {
            "outcome_narrative": "You ask Skye about her favorite hobbies.",
            "next_narrative": "She smiles warmly.",
            "relationship_updates": [{"npc_name": "Skye Anderson", "delta_score": 3, "track": "platonic"}]
        }
        action = {
            "char": {"name": "Artemiusz", "user_id": 99999},
            "label": "Ask about sensitive spots",
            "stat": "CHA",
            "check": type("Check", (), {"is_success": True, "tier": "SUCCESS", "tier_label": "SUCCESS", "chance": 80})(),
            "mp_spent": 0
        }
        # Test with actions passed
        res1 = game_engine.apply_outcome(sess_id, party, outcome, {99999: 0}, actions=[action])
        self.assertIsInstance(res1, dict)

        # Test with actions=None
        res2 = game_engine.apply_outcome(sess_id, party, outcome, {99999: 0})
        self.assertIsInstance(res2, dict)

    def test_failed_check_disclosure_gating(self):
        import db, time, game_engine
        db.init_db()
        sess_id = int(time.time() * 1000)
        char_id = 99925
        party = [({"id": char_id, "user_id": 99925, "name": "Artemiusz", "hp": 20, "max_hp": 20, "mp": 10, "max_mp": 10, "stats": {"STR": 5, "AGI": 5, "END": 5, "INT": 5, "PER": 5, "CHA": 5, "LUK": 5}}, [])]

        db.upsert_contact(
            session_id=sess_id,
            character_id=char_id,
            npc_id="ren_tanaka",
            name="Ren Tanaka",
            appearance={
                "intercourse_experience": "virgin",
                "sensitive_spots": "Lower back"
            }
        )

        outcome_failed = {
            "outcome_narrative": "Ren turns away uncomfortably and refuses to answer.",
            "next_narrative": "The conversation stalls.",
            "relationship_updates": [{
                "npc_name": "Ren",
                "delta_score": -2,
                "revealed_attributes": ["sensitive_spots"]
            }]
        }
        failed_action = {
            "char": {"name": "Artemiusz", "user_id": 99925},
            "label": "Press Ren about personal secrets",
            "stat": "CHA",
            "check": type("Check", (), {"is_success": False, "tier": "FAILURE", "tier_label": "FAILURE", "chance": 30})(),
            "mp_spent": 0
        }
        game_engine.apply_outcome(sess_id, party, outcome_failed, {99925: 0}, actions=[failed_action])

        contact = db.get_contact(sess_id, "Ren", char_id)
        app = contact.get("appearance", {})
        self.assertFalse(app.get("sensitive_spots_revealed", False))
