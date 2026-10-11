"""
Tests for Codex Physical Profile presentation, Breast Size visibility,
and Past History multi-act synchronization.
"""
import unittest
import json
import db
from mechanics.social.persona.intimacy.formatting import format_intimate_profile_sections
from api.codex_phone import _enrich_contact_record
from api.adventure import _enrich_session_for_client
from scenario_data import is_nsfw_scenario


class TestCodexPhysicalProfileAndHistorySync(unittest.TestCase):
    def setUp(self):
        db.init_db()
        self.session_id = 888777
        self.user_id = 777888

        with db.get_conn() as conn:
            conn.execute("DELETE FROM sessions WHERE id = ?", (self.session_id,))
            conn.execute("DELETE FROM characters WHERE user_id = ?", (self.user_id,))
            conn.execute("DELETE FROM contacts WHERE session_id = ?", (self.session_id,))

        db.create_character(
            user_id=self.user_id,
            name="Artemiusz",
            gender="male",
            stats={"STR": 10, "AGI": 10, "END": 10, "INT": 12, "PER": 10, "CHA": 15, "LUK": 5}
        )
        self.char = db.get_character(self.user_id)
        self.session_id = db.create_session(
            self.user_id, "solo", 1, "vivid", "individual", False, scenario="nsfw_furry_high_school_drama"
        )

    def tearDown(self):
        with db.get_conn() as conn:
            conn.execute("DELETE FROM sessions WHERE id = ?", (self.session_id,))
            conn.execute("DELETE FROM characters WHERE user_id = ?", (self.user_id,))
            conn.execute("DELETE FROM contacts WHERE session_id = ?", (self.session_id,))

    def test_female_breast_size_always_revealed_at_level_0_and_1(self):
        """Verify female breast size is never obscured as Unknown in format_intimate_profile_sections."""
        app_dict = {
            "breast_size": "Soft A-Cup",
            "intercourse_experience": "non_virgin",
            "oral_experience": "has_done_oral",
            "intimate_revealed": False
        }
        # Info level 0 (acquaintance / unrevealed)
        sections_l0 = format_intimate_profile_sections(
            app_dict, gender="female", info_level=0, revealed_flags={}
        )
        anatomy_lines_l0 = sections_l0["anatomy"]
        self.assertTrue(any("• **Breast Size**: Soft A-Cup" in l for l in anatomy_lines_l0))
        self.assertFalse(any("• **Breast Size**: *Unknown*" in l for l in anatomy_lines_l0))

        # Info level 1
        sections_l1 = format_intimate_profile_sections(
            app_dict, gender="female", info_level=1, revealed_flags={}
        )
        anatomy_lines_l1 = sections_l1["anatomy"]
        self.assertTrue(any("• **Breast Size**: Soft A-Cup" in l for l in anatomy_lines_l1))

    def test_stale_past_history_resynchronization(self):
        """Verify _enrich_contact_record detects outdated past history lacking oral experience and regenerates."""
        # Insert a contact with stale past history that only has intercourse
        stale_mems = [
            "Past History: Had intercourse 5 times during a relationship with 'Harry Ikeda' (Dormitory Prefect)",
            "Past History: Secret affair (7 times) with 'Leon Lewandowski' behind partner's back"
        ]
        res = db.upsert_contact(
            session_id=self.session_id,
            character_id=self.char["id"],
            npc_id="mia_yamada",
            name="Mia Yamada",
            basic_info={
                "role": "Class Clown & Slacker",
                "race": "beastfolk:tiger",
                "gender": "female",
                "description": "Junior at Sakuragaoka Academy"
            },
            appearance={
                "breast_size": "Soft A-Cup",
                "intercourse_experience": "non_virgin",
                "oral_experience": "has_done_oral",
                "erotic_openness": "shameless",
                "eye_color": "ice_blue",
                "hair_color": "midnight black with shadow stripes",
                "coat_color": "Midnight Black with Shadow Stripes",
                "skin_type": "furry"
            }
        )
        cid = res["id"] if isinstance(res, dict) else res
        # Directly store stale memories in DB
        with db.get_conn() as conn:
            conn.execute(
                "UPDATE contacts SET intimate_memories_json = ? WHERE id = ?",
                (json.dumps(stale_mems), cid)
            )

        # Fetch contact and enrich with debug_reveal_all=True
        contacts = db.get_contacts(self.session_id, self.char["id"])
        mia_contact = [c for c in contacts if c["name"] == "Mia Yamada"][0]
        enriched = _enrich_contact_record(mia_contact, self.session_id, "nsfw_furry_high_school_drama", debug_reveal_all=True)

        # Must have regenerated to include oral experience
        past_hist = enriched.get("past_intimate_history", "")
        self.assertIn("performed oral", past_hist)
        self.assertTrue(enriched["is_nsfw"])

        # Also verify DB row was updated with fresh memories
        with db.get_conn() as conn:
            mems_raw = conn.execute("SELECT intimate_memories_json FROM contacts WHERE id = ?", (cid,)).fetchone()[0]
            self.assertIn("performed oral", mems_raw)

    def test_session_enrichment_has_nsfw_and_tags(self):
        """Verify _enrich_session_for_client tags is_nsfw and scenario_tags correctly."""
        raw_sess = db.get_session(self.session_id)
        enriched_sess = _enrich_session_for_client(raw_sess, self.user_id)
        self.assertTrue(enriched_sess.get("is_nsfw"))
        self.assertIn("nsfw", enriched_sess.get("scenario_tags", []))


if __name__ == "__main__":
    unittest.main()
