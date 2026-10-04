import unittest
import namegen
from mechanics.social.persona import generate_past_intimate_history, generate_past_partner_role

class TestNamegenRoles(unittest.TestCase):
    def test_generate_role_scenarios(self):
        scenarios = [
            "fantasy", "dark_fantasy", "sci_fi", "cyberpunk",
            "steampunk", "isekai_fantasy", "high_school_drama",
            "nuclear_post_apocalypse", "default"
        ]
        for scen in scenarios:
            role = namegen.generate_role(scen)
            self.assertIsInstance(role, str)
            self.assertTrue(len(role) > 0)

            # Deterministic with hash_val
            role_hash_1 = namegen.generate_role(scen, hash_val=42)
            role_hash_2 = namegen.generate_role(scen, hash_val=42)
            self.assertEqual(role_hash_1, role_hash_2)

    def test_generate_neutral_npc(self):
        npc_male = namegen.generate_neutral_npc("fantasy", gender="male")
        self.assertIn("name", npc_male)
        self.assertIn("role", npc_male)
        self.assertEqual(npc_male["gender"], "male")

        npc_female = namegen.generate_neutral_npc("high_school_drama", gender="female")
        self.assertIn("name", npc_female)
        self.assertIn("role", npc_female)
        self.assertEqual(npc_female["gender"], "female")

    def test_resolve_tokens_deep_with_role(self):
        payload = {
            "narrative": "{{PERSON_1}}, a {{ROLE_1}}, approached {{PERSON_2}} at {{PLACE_1}}.",
            "characters": ["{{PERSON_1}}", "{{PERSON_2}}"],
            "roles": ["{{ROLE_1}}", "{{ROLE_2}}"]
        }
        resolved = namegen.resolve_tokens_deep(payload, scenario="high_school_drama")

        self.assertNotIn("{{PERSON_1}}", resolved["narrative"])
        self.assertNotIn("{{ROLE_1}}", resolved["narrative"])
        self.assertNotIn("{{PLACE_1}}", resolved["narrative"])
        self.assertNotIn("{{ROLE_2}}", resolved["roles"][1])

    def test_resolve_tokens_deep_with_single_braces(self):
        payload = {
            "npcs_present": [{"name": "{PERSON_MALE_1}", "status": "Pinned, Bleeding"}],
            "nearby_monsters": [{"name": "{ROLE_1}", "level": 2}],
            "narrative": "The wagon overturned, trapping {PERSON_MALE_1} while {ROLE_1} watched."
        }
        resolved = namegen.resolve_tokens_deep(payload, scenario="fantasy")

        self.assertNotIn("{PERSON_MALE_1}", resolved["npcs_present"][0]["name"])
        self.assertNotIn("{ROLE_1}", resolved["nearby_monsters"][0]["name"])
        self.assertNotIn("{PERSON_MALE_1}", resolved["narrative"])
        self.assertNotIn("{ROLE_1}", resolved["narrative"])
        self.assertTrue(len(resolved["npcs_present"][0]["name"]) > 2)
        self.assertTrue(len(resolved["nearby_monsters"][0]["name"]) > 2)

    def test_persona_generate_past_partner_role_integration(self):
        role_hs = generate_past_partner_role("high_school_drama", hash_val=10)
        self.assertIsInstance(role_hs, str)
        self.assertTrue(len(role_hs) > 0)

        past_history = generate_past_intimate_history(oral="has_done_oral", hash_val=99, gender="female", scenario="high_school_drama")
        self.assertIsNotNone(past_history)
        self.assertIn("Past History: Performed oral", past_history["entry"])
        self.assertTrue(any(c in past_history["entry"] for c in ("1 time", "2 times", "3 times", "4 times")))
        self.assertIn(past_history["partner_name"], past_history["entry"])
        self.assertIn(past_history["partner_role"], past_history["entry"])

    def test_namegen_gender_lookup_and_infer_gender(self):
        from mechanics.social.persona import infer_contact_gender

        # Test namegen fast lookup functions
        self.assertTrue(namegen.is_known_male_name("Julian"))
        self.assertTrue(namegen.is_known_male_name("Marcus Reed"))
        self.assertTrue(namegen.is_known_female_name("Elena"))
        self.assertTrue(namegen.is_known_female_name("Chloe Bennett"))

        # Test infer_contact_gender utilizing namegen
        contact_m = {"name": "Marcus Reed", "basic_info": {}, "appearance": {}}
        self.assertEqual(infer_contact_gender(contact_m), "male")

        contact_f = {"name": "Cassandra Ward", "basic_info": {}, "appearance": {}}
        self.assertEqual(infer_contact_gender(contact_f), "female")

    def test_generate_school_name(self):
        # High School
        s_hs = namegen.generate_school_name("high_school_drama", hash_val=42)
        self.assertIsInstance(s_hs, str)
        self.assertTrue(len(s_hs) > 0)
        self.assertEqual(s_hs, namegen.generate_school_name("high_school_drama", hash_val=42))

        # Fantasy
        s_fan = namegen.generate_school_name("fantasy", hash_val=10)
        self.assertIsInstance(s_fan, str)
        self.assertTrue(any(w in s_fan for w in ("Academy", "Scholomance", "Institute", "College", "Sorcery")))

        # Sci-Fi
        s_sci = namegen.generate_school_name("sci_fi", hash_val=10)
        self.assertIsInstance(s_sci, str)
        self.assertTrue(any(w in s_sci for w in ("Institute", "Collegiate", "Academy", "High", "Polytechnic")))

    def test_generate_classroom_name(self):
        # High School
        c_hs = namegen.generate_classroom_name("high_school_drama", hash_val=12)
        self.assertIsInstance(c_hs, str)
        self.assertTrue("Homeroom" in c_hs)
        self.assertEqual(c_hs, namegen.generate_classroom_name("high_school_drama", hash_val=12))

        # Fantasy
        c_fan = namegen.generate_classroom_name("fantasy", hash_val=12)
        self.assertTrue("Homeroom" in c_fan)

        # Token replacement deep
        deep_obj = {"location": "{{SCHOOL_1}} ➔ {{CLASSROOM_1}} ➔ {{PERSON_1}}'s Desk"}
        resolved = namegen.resolve_tokens_deep(deep_obj, scenario="high_school_drama")
        self.assertNotIn("{{SCHOOL_1}}", resolved["location"])
        self.assertNotIn("{{CLASSROOM_1}}", resolved["location"])
        self.assertNotIn("{{PERSON_1}}", resolved["location"])
        self.assertIn("Homeroom", resolved["location"])

    def test_generic_role_name_detection_and_sanitization(self):
        # Generic role names should be detected
        self.assertTrue(namegen.is_generic_role_name("Student Council President"))
        self.assertTrue(namegen.is_generic_role_name("Student Council Vice President"))
        self.assertTrue(namegen.is_generic_role_name("Class Representative"))
        self.assertTrue(namegen.is_generic_role_name("Guildmaster"))
        self.assertTrue(namegen.is_generic_role_name("Town Guard"))
        self.assertTrue(namegen.is_generic_role_name("Shopkeeper"))
        self.assertTrue(namegen.is_generic_role_name("Teacher"))

        # Real personal names should NOT be detected as roles
        self.assertFalse(namegen.is_generic_role_name("Skye Anderson"))
        self.assertFalse(namegen.is_generic_role_name("Sora"))
        self.assertFalse(namegen.is_generic_role_name("Yue Dubois"))
        self.assertFalse(namegen.is_generic_role_name("Artemiusz"))
        self.assertFalse(namegen.is_generic_role_name("Julian Vance"))

        # Sanitization replaces role name with proper name
        sanitized = namegen.sanitize_person_name("Student Council President", scenario="high_school_drama")
        self.assertNotEqual(sanitized, "Student Council President")
        self.assertFalse(namegen.is_generic_role_name(sanitized))

        # Real name remains untouched
        self.assertEqual(namegen.sanitize_person_name("Skye Anderson", scenario="high_school_drama"), "Skye Anderson")

    def test_split_name_and_role(self):
        # Combined Name (Role)
        name, role = namegen.split_name_and_role("Skye Anderson (Student Council President)", scenario="high_school_drama")
        self.assertEqual(name, "Skye Anderson")
        self.assertEqual(role, "Student Council President")

        # Just Role
        name_gen, role_gen = namegen.split_name_and_role("Student Council President", scenario="high_school_drama")
        self.assertNotEqual(name_gen, "Student Council President")
        self.assertEqual(role_gen, "Student Council President")

    def test_db_level_role_interception(self):
        import db
        # Create temp session and test DB layer interception
        user_id = 999999
        with db.get_conn() as conn:
            conn.execute("DELETE FROM characters WHERE user_id=?", (user_id,))
        db.create_character(user_id, "Tester", "Warrior", "fantasy")
        char = db.get_character(user_id)
        sess_id = db.create_session(user_id, "solo", 1, "vivid", "individual", False, scenario="high_school_drama")

        # Insert Student Council faction with roster
        db.upsert_faction(
            sess_id,
            "Student Council",
            delta_score=10,
            hierarchy_template="council",
            leadership_roster=[
                {"rank": 4, "title": "Student Council President", "name": "Skye Anderson", "is_player": False},
                {"rank": 3, "title": "Student Council Vice President", "name": "Jane Tanaka", "is_player": False},
            ]
        )

        # 1. Test upsert_contact with generic role title
        contact = db.upsert_contact(
            session_id=sess_id,
            character_id=char["id"],
            npc_id="Student Council President",
            name="Student Council President",
            basic_info={"description": "Authoritative leader"}
        )
        self.assertEqual(contact["name"], "Skye Anderson")
        self.assertIn("Student Council President", contact["basic_info"]["description"])
        self.assertEqual(contact["basic_info"]["role"], "Student Council President")

        # 2. Test upsert_lorebook_entity with generic role title
        db.upsert_lorebook_entity(
            session_id=sess_id,
            entity_type="person",
            name="Student Council President",
            description="Leader of student body"
        )
        lore = db.get_lorebook(sess_id)
        person_names = [p["name"] for p in lore.get("person", [])]
        self.assertNotIn("Student Council President", person_names)
        self.assertIn("Skye Anderson", person_names)

        # 3. Test save_session_scene sanitizing current_npcs
        db.save_session_scene(
            session_id=sess_id,
            scene_title="Classroom",
            narrative="Talking to the president.",
            choices=[],
            history=[],
            current_npcs=[{"name": "Student Council President", "hp": 100, "level": 10}]
        )
        # 4. Test get_contact flexibility (both (session_id, npc_id, character_id) and (session_id, character_id, npc_id))
        c1 = db.get_contact(sess_id, "Skye Anderson", char["id"])
        self.assertIsNotNone(c1)
        self.assertEqual(c1["name"], "Skye Anderson")

        c2 = db.get_contact(sess_id, char["id"], "Skye Anderson")
        self.assertIsNotNone(c2)
        self.assertEqual(c2["name"], "Skye Anderson")


if __name__ == "__main__":
    unittest.main()
