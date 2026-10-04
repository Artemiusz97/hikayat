import unittest
import db
from cogs.contacts import build_contact_detail_embed, build_romantic_memories_embed, build_intimate_profile_embed
from cogs.debug import build_debug_embed

class TestDebugReveal(unittest.TestCase):
    def setUp(self):
        db.init_db()
        self.test_user_id = 99999123
        db.update_settings(self.test_user_id, debug_stat_mode="off", debug_check_mode="off", debug_reveal_all_info=0)

    def test_debug_settings_toggle_and_reset(self):
        # Default is 0
        s = db.get_settings(self.test_user_id)
        self.assertEqual(s.get("debug_reveal_all_info", 0), 0)

        # Toggle on
        db.update_settings(self.test_user_id, debug_reveal_all_info=1)
        s_on = db.get_settings(self.test_user_id)
        self.assertEqual(s_on.get("debug_reveal_all_info"), 1)

        # Toggle stat mode without breaking reveal mode
        db.update_settings(self.test_user_id, debug_stat_mode="max", debug_check_mode="always_success")
        s_combo = db.get_settings(self.test_user_id)
        self.assertEqual(s_combo.get("debug_reveal_all_info"), 1)
        self.assertEqual(s_combo.get("debug_stat_mode"), "max")
        self.assertEqual(s_combo.get("debug_check_mode"), "always_success")

        # Reset all resets all 3 overrides
        db.update_settings(self.test_user_id, debug_stat_mode="off", debug_check_mode="off", debug_reveal_all_info=0)
        s_reset = db.get_settings(self.test_user_id)
        self.assertEqual(s_reset.get("debug_reveal_all_info"), 0)
        self.assertEqual(s_reset.get("debug_stat_mode"), "off")
        self.assertEqual(s_reset.get("debug_check_mode"), "off")

    def test_debug_menu_embed_rendering(self):
        db.update_settings(self.test_user_id, debug_stat_mode="max", debug_check_mode="always_success", debug_reveal_all_info=1)
        embed = build_debug_embed(self.test_user_id)
        field_reveal = next(f for f in embed.fields if "Reveal All NPC Profiles" in f.name)
        self.assertIn("🟩 **ENABLED**", field_reveal.value)
        self.assertIn("NPC Reveal: `ENABLED`", embed.footer.text)

if __name__ == "__main__":
    unittest.main()
