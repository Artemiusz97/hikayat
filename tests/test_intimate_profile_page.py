import unittest
import db
import discord
from cogs.contacts import (
    build_contact_detail_embed,
    build_intimate_profile_embed,
    IntimateProfileButton,
    IntimateProfileView,
    BackToProfileButton,
    RelationsButton,
    RomanticMemoriesButton,
    ContactView
)

class TestIntimateProfilePage(unittest.TestCase):
    def setUp(self):
        db.init_db()
        self.test_user_id = 99887766
        db.update_settings(self.test_user_id, debug_reveal_all_info=0)

        self.female_contact = {
            "npc_id": "maya_anderson",
            "name": "Maya Anderson",
            "relationship_score": 15,
            "track": "platonic",
            "race": "Fox-Beastfolk",
            "gender": "female",
            "mannerisms": "Fluffy Fox Tail & Soft Twitching Fox Ears",
            "traits": ["Ambitious", "Organized"],
            "preferences": ["Likes Logistics", "Prefers Independence"],
            "appearance": {
                "hair_color": "black",
                "hair_length": "medium",
                "hair_style": "straight",
                "is_dyed": True,
                "natural_hair_color": "golden-blonde",
                "eye_color": "blue",
                "coat_color": "golden-blonde",
                "skin_type": "furry",
                "predetermined_intercourse_experience": "virgin",
                "breast_size": "plump",
                "intimate_demeanor": "Secretly Teasing",
                "intimate_dynamic": "Switch / Sensual",
                "sensitive_spots": "Fox ears, base of tail",
                "turn_ons": "Tail grooming, whispered praise",
                "fetishes": "Sensory deprivation"
            },
            "basic_info": {
                "grade": "Freshman",
                "club": "Student Council"
            }
        }

    def test_main_contact_profile_embed_is_decluttered(self):
        """Verify that the main contact detail embed excludes Intimate Profile."""
        embed = build_contact_detail_embed(self.female_contact, "nsfw_high_school_drama", user_id=self.test_user_id)
        field_names = [f.name for f in embed.fields]

        # Intimate Profile should NOT be on main profile
        self.assertNotIn("🔞 Intimate Profile", field_names)

        # Standard components should remain
        self.assertIn("Relationship Standing", field_names)
        self.assertIn("Basic Details", field_names)
        self.assertIn("✨ Physical Appearance", field_names)
        self.assertIn("🎭 Mannerisms & Habits", field_names)
        self.assertIn("🧠 Unlocked Traits", field_names)
        self.assertIn("👍 Likes & Preferences", field_names)
        self.assertIn("👎 Dislikes", field_names)

        basic_field = next(f for f in embed.fields if f.name == "Basic Details")
        self.assertIn("• **Grade / Standing**: Freshman", basic_field.value)
        self.assertIn("• **Role**: Member", basic_field.value)
        self.assertIn("• **Faction Affiliation**: Student Council", basic_field.value)
        self.assertIn("• **Details**: None", basic_field.value)
        self.assertNotIn("Sibling", basic_field.value)

    def test_build_intimate_profile_embed_level_1_masked(self):
        """Verify that level 1 intimacy masks fields as Unknown and displays locked synergy helper."""
        embed = build_intimate_profile_embed(self.female_contact, "nsfw_high_school_drama", user_id=self.test_user_id)
        self.assertEqual(embed.title, "🔞 Intimate Profile: Maya Anderson")
        self.assertEqual(embed.color, discord.Color.magenta())

        field_map = {f.name: f for f in embed.fields}
        self.assertIn("🔞 Anatomy & Experience", field_map)
        self.assertIn("🎭 Demeanor & Dynamic", field_map)
        self.assertIn("🔥 Turn-Ons & Desires", field_map)
        self.assertIn("❤️ Act & Position Preferences", field_map)
        self.assertNotIn("🔒 Intimate Synergy", field_map)

        # In-line side-by-side checks
        self.assertTrue(field_map["🔞 Anatomy & Experience"].inline)
        self.assertTrue(field_map["🎭 Demeanor & Dynamic"].inline)
        self.assertFalse(field_map["🔥 Turn-Ons & Desires"].inline)
        self.assertFalse(field_map["❤️ Act & Position Preferences"].inline)

        # Values are masked
        self.assertIn("• **Breast Size**: *Unknown*", field_map["🔞 Anatomy & Experience"].value)
        self.assertIn("• **Intercourse**: *Unknown*", field_map["🔞 Anatomy & Experience"].value)
        self.assertIn("• **Oral Intimacy**: *Unknown*", field_map["🔞 Anatomy & Experience"].value)
        self.assertIn("• **Manual Intimacy**: *Unknown*", field_map["🔞 Anatomy & Experience"].value)
        self.assertIn("• **Demeanor**: *Unknown*", field_map["🎭 Demeanor & Dynamic"].value)
        self.assertIn("• **Dynamic**: *Unknown*", field_map["🎭 Demeanor & Dynamic"].value)
        self.assertIn("• **Turn-Ons**: *Unknown*", field_map["🔥 Turn-Ons & Desires"].value)
        self.assertIn("• **Fetishes & Kinks**: *Unknown*", field_map["🔥 Turn-Ons & Desires"].value)
        self.assertIn("• **Preferred / Likes**: *Unknown*", field_map["❤️ Act & Position Preferences"].value)
        self.assertIn("• **Aversions / Dislikes**: *Unknown*", field_map["❤️ Act & Position Preferences"].value)

        # Level 1 has disclosure unlock guidance in footer
        self.assertIn("Information Disclosure Level: 1/3", embed.footer.text)

    def test_build_intimate_profile_embed_level_3_revealed(self):
        """Verify that level 3 (score >= 71) reveals intimate details and active synergy helper."""
        high_score_contact = dict(self.female_contact)
        high_score_contact["relationship_score"] = 85

        embed = build_intimate_profile_embed(high_score_contact, "nsfw_high_school_drama", user_id=self.test_user_id)
        field_map = {f.name: f for f in embed.fields}

        self.assertIn("🔞 Anatomy & Experience", field_map)
        self.assertIn("🎭 Demeanor & Dynamic", field_map)
        self.assertIn("🔥 Turn-Ons & Desires", field_map)
        self.assertIn("❤️ Act & Position Preferences", field_map)
        self.assertNotIn("💡 Active Intimate Synergy & Modifiers", field_map)

        self.assertIn("• **Breast Size**: Plump", field_map["🔞 Anatomy & Experience"].value)
        self.assertIn("• **Intercourse**: Virgin", field_map["🔞 Anatomy & Experience"].value)
        self.assertIn("• **Oral Intimacy**: Inexperienced", field_map["🔞 Anatomy & Experience"].value)
        self.assertIn("• **Manual Intimacy**: Inexperienced", field_map["🔞 Anatomy & Experience"].value)
        self.assertIn("• **Demeanor**: Secretly Teasing", field_map["🎭 Demeanor & Dynamic"].value)
        self.assertIn("• **Dynamic**: Switch / Sensual", field_map["🎭 Demeanor & Dynamic"].value)
        self.assertIn("Tail grooming", field_map["🔥 Turn-Ons & Desires"].value)
        self.assertIn("whispered praise", field_map["🔥 Turn-Ons & Desires"].value)
        self.assertIn("• **Fetishes & Kinks**: Sensory deprivation", field_map["🔥 Turn-Ons & Desires"].value)

    def test_intimate_profile_view_has_back_button(self):
        """Verify IntimateProfileView has BackToProfileButton."""
        view = IntimateProfileView(self.female_contact, "nsfw_high_school_drama", self.test_user_id, [self.female_contact])
        back_btns = [item for item in view.children if isinstance(item, BackToProfileButton)]
        self.assertEqual(len(back_btns), 1)
        self.assertEqual(back_btns[0].label, "Back to Profile")

    def test_contact_view_buttons_nsfw_vs_sfw(self):
        """Verify IntimateProfileButton appears only in NSFW scenarios."""
        # NSFW Scenario -> Button present
        nsfw_view = ContactView([self.female_contact], "nsfw_high_school_drama", self.test_user_id, active_contact=self.female_contact)
        nsfw_intimate_btns = [item for item in nsfw_view.children if isinstance(item, IntimateProfileButton)]
        self.assertEqual(len(nsfw_intimate_btns), 1)
        self.assertEqual(nsfw_intimate_btns[0].row, 1)

        # SFW Scenario -> Button absent
        sfw_view = ContactView([self.female_contact], "fantasy", self.test_user_id, active_contact=self.female_contact)
        sfw_intimate_btns = [item for item in sfw_view.children if isinstance(item, IntimateProfileButton)]
        self.assertEqual(len(sfw_intimate_btns), 0)

    def test_contact_view_button_rows_safe_from_overflow(self):
        """Verify that under phone view with active contact, no row exceeds 5 items."""
        phone_view = ContactView(
            [self.female_contact],
            "nsfw_high_school_drama",
            self.test_user_id,
            active_contact=self.female_contact,
            session_id=12345,
            from_phone=True
        )

        rows = {}
        for item in phone_view.children:
            row_idx = getattr(item, "row", 0)
            rows.setdefault(row_idx, []).append(item)

        for row_idx, items in rows.items():
            self.assertLessEqual(len(items), 5, f"Row {row_idx} exceeds maximum allowed 5 items: {len(items)}")

        # Row 1 should contain dossier buttons: Relations, Memories, Intimate Profile
        row1_types = [type(item) for item in rows.get(1, [])]
        self.assertIn(RelationsButton, row1_types)
        self.assertIn(RomanticMemoriesButton, row1_types)
        self.assertIn(IntimateProfileButton, row1_types)
        self.assertEqual(len(rows.get(1, [])), 3)

        # Row 2 should contain phone action buttons: Text, Contact List, Phone Home
        self.assertEqual(len(rows.get(2, [])), 3)

if __name__ == "__main__":
    unittest.main()
