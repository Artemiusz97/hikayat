"""
Unit tests for Hikayat Character Physical Appearance & Race Immutability Engine.
Verifies that established character physical attributes (race, gender, eyes, hair,
stature, physique, fur/coat/skin, and distinctive features) can never be arbitrarily
altered or downgraded across turns, LLM re-introductions, or database updates.
"""
import unittest
import json
import db
from mechanics.social.persona import merge_appearance_safely, IMMUTABLE_PHYSICAL_APPEARANCE_KEYS


class TestAppearanceImmutability(unittest.TestCase):
    def setUp(self):
        self.session_id = 991188
        self.user_id = 881199

        with db.get_conn() as conn:
            conn.execute("DELETE FROM sessions WHERE id = ?", (self.session_id,))
            conn.execute("DELETE FROM characters WHERE user_id = ?", (self.user_id,))
            conn.execute("DELETE FROM contacts WHERE session_id = ?", (self.session_id,))
            conn.execute("DELETE FROM lorebook WHERE session_id = ?", (self.session_id,))

        db.create_character(user_id=self.user_id, name="Protagonist", gender="male")
        self.char = db.get_character(self.user_id)
        self.session_id = db.create_session(
            self.user_id, "solo", 1, "vivid", "individual", False, scenario="nsfw_furry_high_school_drama"
        )

    def tearDown(self):
        with db.get_conn() as conn:
            conn.execute("DELETE FROM sessions WHERE id = ?", (self.session_id,))
            conn.execute("DELETE FROM characters WHERE user_id = ?", (self.user_id,))
            conn.execute("DELETE FROM contacts WHERE session_id = ?", (self.session_id,))
            conn.execute("DELETE FROM lorebook WHERE session_id = ?", (self.session_id,))

    def test_merge_appearance_safely_preserves_all_core_physical_traits(self):
        """Verify merge_appearance_safely strictly protects immutable physical traits from being overwritten."""
        established = {
            "eye_color": "amber",
            "hair_color": "golden-blonde",
            "hair_style": "ponytail",
            "hair_length": "short",
            "stature": "athletic/tall",
            "physique": "full-figured & voluptuous",
            "coat_color": "golden-blonde fur",
            "skin_type": "furry",
            "distinctive_features": "Fluffy Fox Tail & Twitching Ears",
            "breast_size": "C-Cup",
            "predetermined_intercourse": "virgin",
            "intercourse_experience": "virgin",
            "oral_experience": "has_received_oral",
            "intimate_revealed": True,
            "intercourse_experience_revealed": True,
            "intimate_memories": ["received oral"]
        }

        # Contradictory incoming payload (e.g. from generic LLM hallucination or turn update)
        incoming = {
            "eye_color": "blue",
            "hair_color": "black",
            "hair_style": "straight",
            "hair_length": "long",
            "stature": "average",
            "physique": "toned & athletic",
            "coat_color": "black fur",
            "distinctive_features": "None",
            "skin_color": "fair",
            "breast_size": "D-Cup",
            "predetermined_intercourse": "virgin",
            "intercourse_experience": "virgin",
            "intimate_revealed": False,
            "outfit_style": "Summer Festival Yukata"  # Non-immutable clothing can update
        }

        merged = merge_appearance_safely(established, incoming)

        # Core physical features MUST NOT CHANGE
        self.assertEqual(merged["eye_color"], "amber")
        self.assertEqual(merged["hair_color"], "golden-blonde")
        self.assertEqual(merged["hair_style"], "ponytail")
        self.assertEqual(merged["hair_length"], "short")
        self.assertEqual(merged["stature"], "athletic/tall")
        self.assertEqual(merged["physique"], "full-figured & voluptuous")
        self.assertEqual(merged["coat_color"], "golden-blonde fur")
        self.assertEqual(merged["distinctive_features"], "Fluffy Fox Tail & Twitching Ears")
        self.assertEqual(merged["breast_size"], "C-Cup")
        self.assertEqual(merged["predetermined_intercourse"], "virgin")
        self.assertEqual(merged["intercourse_experience"], "virgin")
        self.assertEqual(merged["oral_experience"], "has_received_oral")
        self.assertTrue(merged["intimate_revealed"])

        # Non-immutable outfit can update
        self.assertEqual(merged["outfit_style"], "Summer Festival Yukata")

    def test_merge_appearance_safely_populates_missing_fields(self):
        """Verify that previously missing/empty physical traits are properly populated on first discovery."""
        partial = {
            "eye_color": "emerald green",
            "hair_color": "silver",
            "distinctive_features": ""  # empty initially
        }
        incoming = {
            "distinctive_features": "Notched wolf ear & crescent scar",
            "stature": "tall",
            "eye_color": "brown"  # contradictory, should be rejected
        }

        merged = merge_appearance_safely(partial, incoming)
        self.assertEqual(merged["eye_color"], "emerald green", "Existing eye color must be preserved")
        self.assertEqual(merged["hair_color"], "silver", "Existing hair color must be preserved")
        self.assertEqual(merged["distinctive_features"], "Notched wolf ear & crescent scar", "Empty feature should be populated")
        self.assertEqual(merged["stature"], "tall", "Missing stature should be populated")

    def test_upsert_contact_immutability(self):
        """Verify db.upsert_contact locks race, gender, and physical appearance against turn overwrites."""
        initial_app = {
            "eye_color": "amber",
            "hair_color": "golden-blonde",
            "coat_color": "golden-blonde fur",
            "distinctive_features": "Fluffy Fox Tail & Twitching Ears",
            "stature": "athletic/tall"
        }

        db.upsert_contact(
            session_id=self.session_id,
            character_id=self.char["id"],
            npc_id="sofia_anderson",
            name="Sofia Anderson",
            race="beastfolk:fox",
            gender="female",
            appearance=initial_app
        )

        c1 = db.get_contact(self.session_id, "sofia_anderson", self.char["id"])
        self.assertEqual(c1["race"], "beastfolk:fox")
        self.assertEqual(c1["gender"], "female")
        self.assertEqual(c1["appearance"]["eye_color"], "amber")
        self.assertEqual(c1["appearance"]["coat_color"], "golden-blonde fur")
        self.assertEqual(c1["appearance"]["distinctive_features"], "Fluffy Fox Tail & Twitching Ears")

        # Turn 2: Subsequent turn re-introduces Sofia with contradictory human traits
        contradictory_app = {
            "eye_color": "blue",
            "hair_color": "black",
            "coat_color": "",
            "distinctive_features": "none",
            "stature": "average"
        }
        db.upsert_contact(
            session_id=self.session_id,
            character_id=self.char["id"],
            npc_id="sofia_anderson",
            name="Sofia Anderson",
            race="human",  # Attempted race downgrade
            gender="male",  # Attempted gender alteration
            appearance=contradictory_app
        )

        c2 = db.get_contact(self.session_id, "sofia_anderson", self.char["id"])
        self.assertEqual(c2["race"], "beastfolk:fox", "Race must remain immutable beastfolk:fox")
        self.assertEqual(c2["gender"], "female", "Gender must remain immutable female")
        self.assertEqual(c2["appearance"]["eye_color"], "amber", "Eye color must remain immutable amber")
        self.assertEqual(c2["appearance"]["hair_color"], "golden-blonde", "Hair color must remain immutable golden-blonde")
        self.assertEqual(c2["appearance"]["coat_color"], "golden-blonde fur", "Coat color must remain immutable golden-blonde fur")
        self.assertEqual(c2["appearance"]["distinctive_features"], "Fluffy Fox Tail & Twitching Ears", "Tail & ears must remain immutable")
        self.assertEqual(c2["appearance"]["stature"], "athletic/tall", "Stature must remain immutable athletic/tall")

    def test_upsert_lorebook_entity_immutability(self):
        """Verify db.upsert_lorebook_entity locks race and physical appearance against overwrites."""
        initial_app = {
            "eye_color": "sapphire blue",
            "coat_color": "snow white fur",
            "distinctive_features": "Feline Tail & Pointed Cat Ears"
        }

        db.upsert_lorebook_entity(
            session_id=self.session_id,
            entity_type="person",
            name="Luna Snow",
            description="Mysterious feline student",
            disposition="friendly",
            race="beastfolk:cat",
            appearance=initial_app
        )

        with db.get_conn() as conn:
            lb1 = conn.execute("SELECT * FROM lorebook WHERE session_id=? AND lower(name)=lower(?)", (self.session_id, "Luna Snow")).fetchone()
        self.assertEqual(lb1["race"], "beastfolk:cat")
        lb_app1 = json.loads(lb1["appearance_json"])
        self.assertEqual(lb_app1["coat_color"], "snow white fur")

        # Attempt to overwrite in lorebook on subsequent turn with human defaults
        db.upsert_lorebook_entity(
            session_id=self.session_id,
            entity_type="person",
            name="Luna Snow",
            description="Updated description",
            race="human",
            appearance={"eye_color": "brown", "coat_color": "none"}
        )

        with db.get_conn() as conn:
            lb2 = conn.execute("SELECT * FROM lorebook WHERE session_id=? AND lower(name)=lower(?)", (self.session_id, "Luna Snow")).fetchone()
        self.assertEqual(lb2["race"], "beastfolk:cat", "Lorebook race must remain immutable")
        lb_app2 = json.loads(lb2["appearance_json"])
        self.assertEqual(lb_app2["eye_color"], "sapphire blue", "Lorebook eye color must remain immutable")
        self.assertEqual(lb_app2["coat_color"], "snow white fur", "Lorebook coat color must remain immutable")
        self.assertEqual(lb_app2["distinctive_features"], "Feline Tail & Pointed Cat Ears", "Lorebook features must remain immutable")

    def test_dynamic_intercourse_experience_progression_across_intimate_encounters(self):
        """Verify live experiences dynamically advance forward across intimate encounters while preventing downgrades."""
        app = {
            "eye_color": "amber",
            "hair_color": "golden-blonde",
            "predetermined_intercourse": "virgin",
            "intercourse_experience": "virgin"
        }

        db.upsert_contact(
            session_id=self.session_id,
            character_id=self.char["id"],
            npc_id="sofia_anderson",
            name="Sofia Anderson",
            race="beastfolk:fox",
            appearance=app
        )

        c = db.get_contact(self.session_id, "sofia_anderson", self.char["id"])
        self.assertEqual(c["appearance"]["intercourse_experience"], "virgin")
        self.assertEqual(c["appearance"]["predetermined_intercourse"], "virgin")

        # Encounter 1: Receives oral intimacy
        db.upsert_contact(
            session_id=self.session_id,
            character_id=self.char["id"],
            npc_id="sofia_anderson",
            name="Sofia Anderson",
            appearance={"oral_experience": "has_received_oral", "oral_revealed": True, "intimate_memories": ["received oral"]}
        )
        c1 = db.get_contact(self.session_id, "sofia_anderson", self.char["id"])
        self.assertEqual(c1["appearance"]["oral_experience"], "has_received_oral", "Must dynamically transition to has_received_oral")
        self.assertEqual(c1["appearance"]["predetermined_intercourse"], "virgin", "Backstory must remain virgin")
        self.assertTrue(c1["appearance"]["oral_revealed"])

        # Encounter 2: Also performs oral intimacy (giving) -> combines into has_done_and_received_oral
        db.upsert_contact(
            session_id=self.session_id,
            character_id=self.char["id"],
            npc_id="sofia_anderson",
            name="Sofia Anderson",
            appearance={"oral_experience": "has_done_oral", "intimate_memories": ["received oral", "performed oral"]}
        )
        c2 = db.get_contact(self.session_id, "sofia_anderson", self.char["id"])
        self.assertEqual(c2["appearance"]["oral_experience"], "has_done_and_received_oral", "Must combine oral experiences into has_done_and_received_oral")
        self.assertEqual(c2["appearance"]["predetermined_intercourse"], "virgin", "Backstory must remain virgin")

        # Encounter 3: Intercourse milestone -> advances to non_virgin
        db.upsert_contact(
            session_id=self.session_id,
            character_id=self.char["id"],
            npc_id="sofia_anderson",
            name="Sofia Anderson",
            appearance={"intercourse_experience": "non_virgin", "intimate_memories": ["received oral", "performed oral", "shared intimate night"]}
        )
        c3 = db.get_contact(self.session_id, "sofia_anderson", self.char["id"])
        self.assertEqual(c3["appearance"]["intercourse_experience"], "non_virgin", "Must dynamically advance to non_virgin")
        self.assertEqual(c3["appearance"]["predetermined_intercourse"], "virgin", "Backstory must remain virgin")

        # Encounter 4: Ambient turn / re-introduction payload attempts to downgrade back to virgin or oral
        db.upsert_contact(
            session_id=self.session_id,
            character_id=self.char["id"],
            npc_id="sofia_anderson",
            name="Sofia Anderson",
            appearance={"intercourse_experience": "virgin"}
        )
        c4 = db.get_contact(self.session_id, "sofia_anderson", self.char["id"])
        self.assertEqual(c4["appearance"]["intercourse_experience"], "non_virgin", "non_virgin is permanent and cannot be downgraded")

        # Verify all core physical appearance traits remained 100% intact throughout
        self.assertEqual(c4["appearance"]["eye_color"], "amber")
        self.assertEqual(c4["appearance"]["hair_color"], "golden-blonde")
        self.assertEqual(c4["race"], "beastfolk:fox")

    def test_merge_appearance_safely_preserves_hair_dye_and_natural_base(self):
        """Verify merge_appearance_safely strictly protects hair dye status and natural base from being overwritten."""
        # 1. Dyed beastfolk NPC
        established_dyed = {
            "eye_color": "sapphire blue",
            "coat_color": "vibrant azure-blue fur",
            "hair_color": "crimson red",
            "is_dyed": True,
            "natural_hair_color": "vibrant azure-blue"
        }
        rogue_incoming_natural = {
            "hair_color": "vibrant azure-blue",
            "is_dyed": False,
            "natural_hair_color": "golden-blonde"
        }
        merged_dyed = merge_appearance_safely(established_dyed, rogue_incoming_natural)
        self.assertTrue(merged_dyed["is_dyed"], "Dyed status must not be wiped out")
        self.assertEqual(merged_dyed["hair_color"], "crimson red", "Dyed hair color must not be overwritten")
        self.assertEqual(merged_dyed["natural_hair_color"], "vibrant azure-blue", "Natural base hair color must not be overwritten")

        # 2. Natural beastfolk NPC
        established_natural = {
            "eye_color": "amber",
            "coat_color": "silky ocean-blue fur",
            "hair_color": "silky ocean-blue",
            "is_dyed": False
        }
        rogue_incoming_dyed = {
            "hair_color": "neon pink",
            "is_dyed": True,
            "natural_hair_color": "black"
        }
        merged_natural = merge_appearance_safely(established_natural, rogue_incoming_dyed)
        self.assertFalse(merged_natural["is_dyed"], "Natural status must not be flipped to dyed")
        self.assertEqual(merged_natural["hair_color"], "silky ocean-blue", "Natural hair color must not be overwritten")

    def test_actor_direction_card_tracks_coat_skin_dye_and_canon_guardrail(self):
        """Verify build_actor_direction_card explicitly formats coat/skin, dyed hair, and the canon guardrail."""
        from mechanics.social.persona.actor_card import build_actor_direction_card

        session = {"id": self.session_id, "current_location": "academy_hall"}
        dyed_fox_npc = {
            "name": "Kitsune Ren",
            "race": "beastfolk:fox",
            "gender": "female",
            "basic_info": {"description": "A clever fox student", "role": "Student"},
            "appearance": {
                "eye_color": "amber",
                "coat_color": "vibrant azure-blue fur",
                "hair_color": "crimson red",
                "hair_length": "medium",
                "hair_style": "twin-tails",
                "is_dyed": True,
                "natural_hair_color": "vibrant azure-blue",
                "distinctive_features": "fluffy fox tail"
            }
        }

        card = build_actor_direction_card(session=session, npc=dyed_fox_npc, in_active_erotic=False)

        # 1. Visual Presentation line must track coat and dyed status with natural base
        self.assertIn("Visual Presentation:", card)
        self.assertIn("vibrant azure-blue fur", card)
        self.assertIn("crimson red hair (dyed; naturally vibrant azure-blue)", card.lower())

        # 2. Canon Visual Appearance Guardrail must be present and warn the LLM
        self.assertIn("CANON VISUAL APPEARANCE GUARDRAIL (Kitsune Ren)", card)
        self.assertIn("coat/fur: vibrant azure-blue fur", card)
        self.assertIn("hair: Crimson Red (dyed; naturally vibrant azure-blue)", card)
        self.assertIn("Maintain strict descriptive fidelity", card)

        # 3. Test Humanoid with skin tone and natural hair
        human_npc = {
            "name": "Li Wei",
            "race": "human",
            "gender": "male",
            "basic_info": {"description": "A disciplined swordsman", "role": "Warrior"},
            "appearance": {
                "eye_color": "dark slate",
                "skin_color": "warm honey complexion",
                "hair_color": "ink-black",
                "hair_length": "short",
                "hair_style": "topknot",
                "is_dyed": False
            }
        }
        card_human = build_actor_direction_card(session=session, npc=human_npc, in_active_erotic=False)
        self.assertIn("Visual Presentation:", card_human)
        self.assertIn("warm honey complexion", card_human)
        self.assertIn("short topknot Ink-Black hair", card_human)
        self.assertIn("CANON VISUAL APPEARANCE GUARDRAIL (Li Wei)", card_human)
        self.assertIn("skin: warm honey complexion", card_human)
        self.assertIn("hair: Ink-Black (natural)", card_human)


if __name__ == "__main__":
    unittest.main()

