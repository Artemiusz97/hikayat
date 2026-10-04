import unittest
from mechanics.social.persona.core import is_valid_persona_attribute_string, clean_attribute_list_string
from mechanics.social.persona.intimacy.appearance import normalize_appearance, merge_appearance_safely
from mechanics.social.persona.intimacy.formatting import format_intimate_profile_sections
from mechanics.social.relationships import reconcile_action_affinity_delta

class TestPersonaCorruptionAndBehavioralFidelity(unittest.TestCase):
    def test_is_valid_persona_attribute_string_rejects_schema_tokens_and_syntax_noise(self):
        # Corrupted / schema tokens must be rejected
        self.assertFalse(is_valid_persona_attribute_string("new_traits ["))
        self.assertFalse(is_valid_persona_attribute_string("new_turn_ons"))
        self.assertFalse(is_valid_persona_attribute_string("new_demeanor"))
        self.assertFalse(is_valid_persona_attribute_string("new_dynamic"))
        self.assertFalse(is_valid_persona_attribute_string("string or empty"))
        self.assertFalse(is_valid_persona_attribute_string("short 1-2 word"))
        self.assertFalse(is_valid_persona_attribute_string("none"))
        self.assertFalse(is_valid_persona_attribute_string("unknown"))
        self.assertFalse(is_valid_persona_attribute_string("["))
        self.assertFalse(is_valid_persona_attribute_string("]"))
        self.assertFalse(is_valid_persona_attribute_string("{"))
        self.assertFalse(is_valid_persona_attribute_string(""))
        self.assertFalse(is_valid_persona_attribute_string(None))

        # Authentic descriptions must be accepted
        self.assertTrue(is_valid_persona_attribute_string("Fox ears, base of tail"))
        self.assertTrue(is_valid_persona_attribute_string("Eagerly Receptive / Surrenders Control (Craves partner taking complete charge)"))
        self.assertTrue(is_valid_persona_attribute_string("Blunt & Teasing, energetic directness"))
        self.assertTrue(is_valid_persona_attribute_string("Whispered praise (Action)"))
        self.assertTrue(is_valid_persona_attribute_string("None (Vanilla)"))

    def test_clean_attribute_list_string_cleanses_schema_garbage(self):
        self.assertEqual(clean_attribute_list_string("new_turn_ons"), "")
        self.assertEqual(clean_attribute_list_string("new_demeanor"), "")
        self.assertEqual(clean_attribute_list_string("new_traits ["), "")
        self.assertEqual(clean_attribute_list_string(["new_turn_ons", "Ear Tips"]), "Ear Tips")
        self.assertEqual(clean_attribute_list_string("['new_turn_ons', 'Neck Nuzzling']"), "Neck Nuzzling")

    def test_normalize_appearance_self_heals_corrupted_dynamic_and_preferences(self):
        corrupted_app = {
            "intimate_dynamic": "new_traits [",
            "turn_ons": "new_turn_ons",
            "sensitive_spots": "new_turn_ons",
            "fetishes": "new_demeanor",
            "predetermined_intercourse": "virgin",
            "oral_experience": "inexperienced",
            "manual_experience": "inexperienced"
        }
        healed = normalize_appearance(corrupted_app, gender="female", race="beastfolk:fox", scen_key="nsfw_high_school_drama")
        
        # Corrupted dynamic is replaced by deterministic fallback
        self.assertNotEqual(healed["intimate_dynamic"], "new_traits [")
        self.assertTrue(len(healed["intimate_dynamic"]) > 3)
        self.assertTrue(is_valid_persona_attribute_string(healed["intimate_dynamic"]))

        # Corrupted turn_ons / sensitive_spots / fetishes are replaced by deterministic generation
        self.assertNotEqual(healed["turn_ons"], "new_turn_ons")
        self.assertNotEqual(healed["sensitive_spots"], "new_turn_ons")
        self.assertNotEqual(healed["fetishes"], "new_demeanor")
        self.assertTrue(is_valid_persona_attribute_string(healed["turn_ons"]))
        self.assertTrue(is_valid_persona_attribute_string(healed["fetishes"]))

    def test_format_intimate_profile_sections_never_displays_schema_garbage(self):
        corrupted_app = {
            "intimate_dynamic": "new_traits [",
            "turn_ons": "new_turn_ons",
            "sensitive_spots": "new_turn_ons",
            "fetishes": "new_demeanor",
            "dynamic_revealed": True,
            "turn_ons_revealed": True,
            "sensitive_spots_revealed": True,
            "fetishes_revealed": True
        }
        sec = format_intimate_profile_sections(
            corrupted_app, gender="female", race="beastfolk:fox", scen_key="nsfw_high_school_drama",
            info_level=1, revealed_flags=corrupted_app
        )
        rendered_dyn = "\n".join(sec.get("dynamic", []))
        rendered_sens = "\n".join(sec.get("sensitivities", []))
        
        self.assertNotIn("new_traits", rendered_dyn)
        self.assertNotIn("new_turn_ons", rendered_sens)
        self.assertNotIn("new_demeanor", rendered_sens)

    def test_merge_appearance_safely_protects_canonical_attributes_from_ungrounded_overwrite(self):
        canonical_app = {
            "intimate_dynamic": "Eagerly Receptive / Surrenders Control",
            "turn_ons": "Whispered praise, ear nibbling",
            "fetishes": "Sensory deprivation"
        }
        # Incoming LLM turn with garbage schema tokens or arbitrary new text
        incoming_garbage = {
            "intimate_dynamic": "new_traits [",
            "turn_ons": "new_turn_ons",
            "fetishes": "Foot worship"
        }
        merged = merge_appearance_safely(canonical_app, incoming_garbage)
        # Canonical dynamic and turn_ons must be preserved intact
        self.assertEqual(merged["intimate_dynamic"], "Eagerly Receptive / Surrenders Control")
        self.assertEqual(merged["turn_ons"], "Whispered praise, ear nibbling")
        self.assertEqual(merged["fetishes"], "Sensory deprivation")

    def test_reconcile_action_affinity_delta_allows_dislikes_penalty_on_free_actions(self):
        # A free conversational action where player touches on a dislike should allow negative delta
        action_free = {"label": "Argue aggressively with Yea-ji about club funds"}
        delta = reconcile_action_affinity_delta(
            raw_delta=-3,
            action=action_free,
            is_target=True,
            overall_check_success=True,
            is_hostile=False
        )
        self.assertEqual(delta, -3, "Free conversational action triggering an NPC dislike must allow negative delta")

        # But a rolled successful check still protects against hallucinated negative delta
        action_check_success = {"label": "[Charisma 12] Persuade Yea-ji", "check": {"tier": "success", "roll": 15, "dc": 12}}
        delta_check = reconcile_action_affinity_delta(
            raw_delta=-3,
            action=action_check_success,
            is_target=True,
            overall_check_success=True,
            is_hostile=False
        )
        self.assertGreater(delta_check, 0, "Successful d20 check must still enforce non-negative delta")

    def test_social_reducer_preserves_negative_delta_on_free_action_dislike(self):
        import db
        from game_engine.state.social import _reduce_social_and_milestones
        db.init_db()
        test_session_id = 999111
        user_id = 888222
        with db.get_conn() as conn:
            conn.execute("DELETE FROM sessions WHERE id = ?", (test_session_id,))
            conn.execute("DELETE FROM characters WHERE user_id = ?", (user_id,))
            conn.execute("DELETE FROM contacts WHERE session_id = ?", (test_session_id,))

        db.create_character(user_id=user_id, name="Hero", gender="male")
        char = db.get_character(user_id)
        db.create_session(user_id, "solo", 1, "vivid", "individual", False, scenario="nsfw_high_school_drama")

        db.upsert_contact(
            session_id=test_session_id,
            character_id=char["id"],
            npc_id="yea_ji",
            name="Yea-ji",
            delta_score=50,
            track="platonic"
        )

        outcome = {
            "relationship_updates": [
                {"npc_name": "Yea-ji", "delta_score": -2}
            ]
        }
        actions = [
            {"label": "Make fun of Yea-ji's awkward habits", "target_npc": "Yea-ji"}
        ]

        _reduce_social_and_milestones(
            session_id=test_session_id,
            session={"id": test_session_id, "scenario": "nsfw_high_school_drama"},
            party=[(char, [])],
            outcome=outcome,
            actions=actions,
            scen_key="nsfw_high_school_drama",
            items_gained_by_user={},
            first_char_id=char["id"],
            first_char_name="Hero"
        )

        contact = db.get_contact(test_session_id, "yea_ji", char["id"])
        self.assertEqual(contact["relationship_score"], 48, "Free conversational action triggering a dislike must decrement affinity score")

if __name__ == "__main__":
    unittest.main()
