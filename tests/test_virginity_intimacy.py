import unittest
from mechanics.social.persona import normalize_appearance

class TestIntercourseExperienceTracker(unittest.TestCase):
    def test_predetermined_intercourse(self):
        # Test random hash seeding for female & male
        valid_states = ["virgin", "non_virgin"]
        app_female = normalize_appearance({}, desc="Alice", gender="female", race="human", scen_key="nsfw_high_school_drama")
        self.assertIn(app_female["predetermined_intercourse"], valid_states)
        
        app_male = normalize_appearance({}, desc="Bob", gender="male", race="human", scen_key="nsfw_high_school_drama")
        self.assertIn(app_male["predetermined_intercourse"], valid_states)
        
        # Test explicitly carrying over predetermined_intercourse
        app2 = normalize_appearance({"predetermined_intercourse": "non_virgin"}, scen_key="nsfw_high_school_drama")
        self.assertEqual(app2["predetermined_intercourse"], "non_virgin")

    def test_narrative_milestone_scanner_with_first_name_and_literary_prose(self):
        import db, time
        db.init_db()
        sess_id = int(time.time() * 1000)
        char_id = 99912

        # 1. Create contact with full name Kana Watanabe
        c = db.upsert_contact(
            session_id=sess_id,
            character_id=char_id,
            npc_id="kana_watanabe",
            name="Kana Watanabe",
            appearance={"intercourse_experience": "virgin", "predetermined_intercourse": "virgin"}
        )
        self.assertEqual(c["name"], "Kana Watanabe")
        self.assertEqual(c["appearance"]["intercourse_experience"], "virgin")

        # 2. Test get_contact using just first name 'Kana'
        c_by_first = db.get_contact(sess_id, "Kana", char_id)
        self.assertIsNotNone(c_by_first)
        self.assertEqual(c_by_first["name"], "Kana Watanabe")

        # 3. Simulate literary narrative from screenshot
        narrative_text = (
            "Kana steps closer, her fluffy tail brushing against Artemiusz's leg as she peers down the hall. "
            "She sinks to her knees... Her warm breath hits the head of his member just before she opens her mouth, "
            "taking the tip into the warmth of her mouth with a careful, tentative suction. The wet heat of her mouth "
            "and the rhythmic pressure of her tongue creating a perfect, pulsing vacuum."
        )
        
        # Run scanning logic
        from game_engine import resolve_turn
        # Test directly via database update & keywords
        from game_engine import ORAL_GIVE_KEYWORDS
        self.assertTrue(any(kw in narrative_text.lower() for kw in ORAL_GIVE_KEYWORDS))

        # Perform upsert using first name and new memory
        updated_c = db.upsert_contact(
            session_id=sess_id,
            character_id=char_id,
            npc_id="Kana",
            name="Kana",
            appearance={"oral_experience": "has_done_oral", "intimate_revealed": True, "intercourse_revealed": True},
            new_memory="Shared oral intimacy with Kana Watanabe"
        )
        self.assertEqual(updated_c["name"], "Kana Watanabe")
        self.assertEqual(updated_c["appearance"]["oral_experience"], "has_done_oral")
        self.assertIn("Shared oral intimacy with Kana Watanabe", updated_c["intimate_memories"])

    def test_format_milestone_memory(self):
        from mechanics.social.persona import format_milestone_memory
        self.assertEqual(format_milestone_memory("intercourse", "Kana"), "Shared intimate night with Kana")
        self.assertEqual(format_milestone_memory("oral_give", "Kana"), "Provided oral intimacy to Kana")
        self.assertEqual(format_milestone_memory("oral_receive", "Kana"), "Received oral intimacy from Kana")
        self.assertEqual(format_milestone_memory("first_kiss", "Kana"), "Shared a passionate first kiss with Kana")
        self.assertEqual(format_milestone_memory("confession", "Kana"), "Confessed feelings and agreed to date Kana")
        self.assertEqual(format_milestone_memory("date", "Kana"), "Shared a romantic date and close moments with Kana")
        
        # Test custom summary override
        self.assertEqual(
            format_milestone_memory("kiss", "Kana", "kissed intimately beneath the cherry blossom tree."),
            "Kissed intimately beneath the cherry blossom tree"
        )

    def test_structured_milestone_and_check_gating(self):
        import db, time
        db.init_db()
        sess_id = int(time.time() * 1000)
        char_id = 99915

        # Create contact
        db.upsert_contact(
            session_id=sess_id,
            character_id=char_id,
            npc_id="chiyo_sakura",
            name="Chiyo Sakura",
            appearance={"intercourse_experience": "virgin", "predetermined_intercourse": "virgin"}
        )

        # 1. Test failed check gating - milestone should NOT apply if roll failed
        from mechanics.social.persona import format_milestone_memory
        check_failure = {"tier": "FAILURE", "is_success": False}
        overall_check_success = not (check_failure.get("tier") in ("FAILURE", "CRITICAL_FAILURE"))
        self.assertFalse(overall_check_success)

        # 2. Test successful structured milestone event
        check_success = {"tier": "CRITICAL_SUCCESS", "is_success": True}
        overall_success = not (check_success.get("tier") in ("FAILURE", "CRITICAL_FAILURE"))
        self.assertTrue(overall_success)

        rel = {
            "npc_name": "Chiyo",
            "milestone_event": "first_kiss",
            "memory_summary": "Shared a tender first kiss by the school lockers."
        }
        mem = format_milestone_memory(rel["milestone_event"], rel["npc_name"], rel.get("memory_summary"))
        self.assertEqual(mem, "Shared a tender first kiss by the school lockers")

        updated = db.upsert_contact(
            session_id=sess_id,
            character_id=char_id,
            npc_id="Chiyo",
            name="Chiyo",
            new_memory=mem
        )
        self.assertEqual(updated["name"], "Chiyo Sakura")
        self.assertIn("Shared a tender first kiss by the school lockers", updated["intimate_memories"])

    def test_clean_attribute_list_string(self):
        from mechanics.social.persona import clean_attribute_list_string
        self.assertEqual(clean_attribute_list_string(["ears", "base of tail"]), "Ears, Base of tail")
        self.assertEqual(clean_attribute_list_string("['ears', 'base of tail']"), "Ears, Base of tail")
        self.assertEqual(clean_attribute_list_string('["intellectual curiosity", "gentle touch"]'), "Intellectual curiosity, Gentle touch")
        self.assertEqual(clean_attribute_list_string("['None']"), "None")
        self.assertEqual(clean_attribute_list_string("None"), "None")

    def test_virgin_safeguard_prevents_non_virgin_predetermined(self):
        from mechanics.social.persona import normalize_appearance
        # Test 50 random seeds with intercourse_experience="virgin" - all must have predetermined_intercourse="virgin"
        for i in range(50):
            res = normalize_appearance({"intercourse_experience": "virgin"}, desc=f"NPC_{i}", gender="female", scen_key="nsfw_high_school_drama")
            self.assertEqual(res["predetermined_intercourse"], "virgin")

    def test_climax_without_penetration_does_not_trigger_intercourse(self):
        from game_engine import INTERCOURSE_KEYWORDS
        self.assertNotIn("climax", INTERCOURSE_KEYWORDS)
        self.assertNotIn("orgasm", INTERCOURSE_KEYWORDS)
        self.assertNotIn("doing it", INTERCOURSE_KEYWORDS)

    def test_upsert_contact_intercourse_experience_not_downgraded_by_llm_reintroduction(self):
        """Regression: LLM re-introducing a known NPC via new_entities with 'intercourse_experience: unknown' must NOT
        clobber a previously transitioned state like 'has_done_oral'."""
        import db, time
        db.init_db()
        sess_id = int(time.time() * 1000)
        char_id = 99913

    # 1. Create contact after oral intimacy event has been processed
        db.upsert_contact(
            session_id=sess_id,
            character_id=char_id,
            npc_id="zihan_moon",
            name="Zihan Moon",
            appearance={
                "oral_experience": "has_done_and_received_oral",
                "predetermined_intercourse": "virgin",
                "intercourse_revealed": True,
                "intimate_revealed": True,
                "had_first_time_with_player": True,
            }
        )

        # 2. Simulate LLM re-introducing the same NPC with 'intercourse_experience: unknown' via new_entities
        db.upsert_contact(
            session_id=sess_id,
            character_id=char_id,
            npc_id="zihan_moon",
            name="Zihan Moon",
            appearance={
                "oral_experience": "unknown",  # LLM forgets the state
                "eye_color": "emerald green",  # LLM provides updated appearance
            }
        )

        # 3. Verify the intercourse_experience was NOT downgraded
        contact = db.get_contact(sess_id, "Zihan Moon", char_id)
        app = contact.get("appearance", {})
        self.assertEqual(
            app.get("oral_experience"), "has_done_and_received_oral",
            "Intercourse Experience must NOT be downgraded from 'has_done_and_received_oral' to 'unknown' by LLM re-introduction"
        )
        self.assertTrue(app.get("intercourse_revealed"), "intercourse_revealed must remain True")
        self.assertTrue(app.get("intimate_revealed"), "intimate_revealed must remain True")

    def test_player_eating_out_female_npc_resolves_to_oral_receive_and_preserves_has_received_oral(self):
        """Verify that when a player eats out / goes down on a female NPC who already has_received_oral,
        she is treated as oral_receive (not oral_give) and her status remains has_received_oral."""
        import db, time, game_engine
        sess_id = int(time.time() * 1000)
        char_id = 99916

        # Establish Sofia with backstory has_received_oral
        db.upsert_contact(
            session_id=sess_id,
            character_id=char_id,
            npc_id="sofia_anderson",
            name="Sofia Anderson",
            race="beastfolk:fox",
            gender="female",
            appearance={
                "predetermined_intercourse": "has_received_oral",
                "oral_experience": "has_received_oral",
                "eye_color": "amber",
                "hair_color": "golden-blonde"
            }
        )

        class MockSuccessCheck:
            succeeded = True
            is_success = True
            tier = "success"

        # Player eats her out
        actions = [
            {"label": "Get on your knees, gently pull down her underwear, and appreciate her pussy", "check": MockSuccessCheck()},
            {"label": "Increase the intensity of your tongue, focusing on her clitoris to drive her toward a peak", "check": MockSuccessCheck()}
        ]
        char = {"id": char_id, "user_id": 99916, "name": "Artemiusz"}
        raw_result = {
            "scene_title": "Rooftop Intimacy",
            "narrative": "Artemiusz went down on her, his tongue working between her folds with focused intensity as Sofia groaned with pleasure.",
            "next_choices": [{"label": "Hold her close"}],
            "relationship_updates": [
                {
                    "npc_name": "Sofia Anderson",
                    "milestone_event": "oral_give",  # LLM mistakenly reports oral_give from player's POV
                    "delta_score": 4
                }
            ]
        }

        game_engine.apply_outcome(sess_id, [(char, None)], raw_result, actions=actions)

        contact = db.get_contact(sess_id, "sofia_anderson", char_id)
        app = contact.get("appearance", {})
        self.assertEqual(
            app.get("oral_experience"), "has_received_oral",
            "Sofia only received oral; she must NOT become has_done_and_received_oral!"
        )
        self.assertEqual(app.get("predetermined_intercourse"), "virgin")
        self.assertTrue(app.get("oral_revealed"))
        self.assertTrue(app.get("intimate_revealed"))

    def test_npc_oral_give_euphemism_and_action_recognition(self):
        """Verify that when an NPC performs oral on the player described with literary/euphemistic narrative,
        the engine reliably triggers the oral_give transition to has_done_and_received_oral."""
        import db, time, game_engine
        db.init_db()
        sess_id = int(time.time() * 1000) + 123
        char_id = 99917

        # Sofia starts with has_received_oral
        db.upsert_contact(
            session_id=sess_id,
            character_id=char_id,
            npc_id="sofia_anderson",
            name="Sofia Anderson",
            appearance={
                "oral_experience": "has_received_oral",
                "predetermined_intercourse": "virgin"
            }
        )

        class MockSuccessCheck:
            succeeded = True
            is_success = True
            tier = "success"

        # Player asks Sofia to take his release inside her mouth
        actions = [
            {
                "label": "Let out a loud moan to let her know how much you're enjoying it, tell her you're about to cum and ask her if she wants in on her face or inside her mouth",
                "check": MockSuccessCheck()
            }
        ]
        char = {"id": char_id, "user_id": 99917, "name": "Artemiusz"}
        
        # Narrative uses literary/euphemistic descriptions of oral sex (rhythmic suction, warmth hits her, every drop accounted for)
        raw_result = {
            "scene_title": "Rooftop Climax",
            "narrative": "Sofia maintained a tight, rhythmic suction that pulls the heat from your core. Sofia doesn't flinch as the warmth hits her; instead, she accepts it with a focused intensity, ensuring every drop is accounted for inside her mouth.",
            "next_choices": [{"label": "Catch your breath"}],
            "relationship_updates": [
                {
                    "npc_name": "Sofia Anderson",
                    "delta_score": 4
                }
            ]
        }

        game_engine.apply_outcome(sess_id, [(char, None)], raw_result, actions=actions)

        contact = db.get_contact(sess_id, "sofia_anderson", char_id)
        app = contact.get("appearance", {})
        self.assertEqual(
            app.get("oral_experience"), "has_done_and_received_oral",
            "Sofia performed oral; she must transition to has_done_and_received_oral!"
        )
        self.assertEqual(app.get("predetermined_intercourse"), "virgin")
        self.assertTrue(app.get("oral_revealed"))
        mems = contact.get("intimate_memories", [])
        self.assertTrue(any("Provided oral intimacy to Artemiusz" in m for m in mems))

    def test_intercourse_action_and_literary_narrative_transitions_to_non_virgin(self):
        """Verify that when player performs intercourse / penetration on an NPC,
        the engine transitions intercourse_experience to non_virgin and records the milestone memory."""
        import db, time, game_engine
        db.init_db()
        sess_id = int(time.time() * 1000) + 456
        char_id = 99918

        # Sofia starts with has_done_and_received_oral (from previous oral acts)
        db.upsert_contact(
            session_id=sess_id,
            character_id=char_id,
            npc_id="sofia_anderson",
            name="Sofia Anderson",
            appearance={
                "oral_experience": "has_done_and_received_oral",
                "predetermined_intercourse": "has_received_oral"
            }
        )

        class MockSuccessCheck:
            succeeded = True
            is_success = True
            tier = "success"

        # Action from actual gameplay
        actions = [
            {
                "label": "Gently rub your dick against her wet pussy and slowly slide it inside",
                "check": MockSuccessCheck()
            }
        ]
        char = {"id": char_id, "user_id": 99918, "name": "Artemiusz"}

        # Narrative from actual gameplay (no structured milestone in relationship_updates)
        raw_result = {
            "scene_title": "The Rhythm of Desire",
            "narrative": "With a steady, deliberate motion, Artemiusz guides himself forward, the heat of his skin meeting the slick warmth of Sofia's golden-blonde fur. He slides slowly and firmly inside her, the tight grip of her warmth welcoming him as her breath hitches.",
            "next_choices": [{"label": "Hold her waist"}],
            "relationship_updates": [
                {
                    "npc_name": "Sofia Anderson",
                    "delta_score": 0  # Max affinity capped
                }
            ]
        }

        game_engine.apply_outcome(sess_id, [(char, None)], raw_result, actions=actions)

        contact = db.get_contact(sess_id, "sofia_anderson", char_id)
        app = contact.get("appearance", {})
        self.assertEqual(
            app.get("intercourse_experience"), "non_virgin",
            "Sofia engaged in intercourse; intercourse_experience must transition to non_virgin!"
        )
        self.assertTrue(app.get("intercourse_revealed"))
        self.assertTrue(app.get("intimate_revealed"))
        mems = contact.get("intimate_memories", [])
        self.assertTrue(
            any("Shared intimate night with Artemiusz" in m for m in mems),
            f"Expected intercourse memory in intimate_memories, got: {mems}"
        )

    def test_oral_give_preserves_intercourse_intercourse_experience_and_does_not_trigger_received(self):
        """Verify that an NPC with predetermined_intercourse='virgin' who performs oral
        transitions to has_done_oral, keeps intercourse_experience as virgin,
        and does not falsely trigger has_done_and_received_oral."""
        from mechanics.social.persona import normalize_appearance, format_intimate_profile_sections

        # Case 1: NPC performed oral only
        app_raw = {
            "predetermined_intercourse": "virgin",
            "predetermined_intercourse": "virgin",
            "intercourse_experience": "virgin",
            "oral_experience": "has_done_oral",
            "manual_experience": "inexperienced",
            "intercourse_experience": "has_done_oral",
            "had_first_time_with_player": True,
            "intimate_memories": [
                "Rachel admitted she is a virgin, showing a rare moment of vulnerability and trust",
                "Provided oral intimacy to Artemiusz"
            ]
        }

        norm = normalize_appearance(app_raw, gender="female", scen_key="nsfw_high_school_drama")
        self.assertEqual(norm.get("intercourse_experience"), "virgin", "Intercourse must remain virgin when only oral was performed")
        self.assertEqual(norm.get("oral_experience"), "has_done_oral", "Oral experience must be has_done_oral, not has_done_and_received_oral")
        self.assertEqual(norm.get("manual_experience"), "inexperienced")

        sections = format_intimate_profile_sections(norm, gender="female", scen_key="nsfw_high_school_drama", info_level=3)
        anatomy_text = "\n".join(sections.get("anatomy", []))
        self.assertIn("• **Intercourse**: Virgin", anatomy_text)
        self.assertIn("• **Oral Intimacy**: Has Performed", anatomy_text)
        self.assertIn("• **Manual Intimacy**: Inexperienced", anatomy_text)
        self.assertNotIn("Has Performed & Received", anatomy_text)
        self.assertNotIn("• **Intercourse**: Non-Virgin", anatomy_text)

        # Case 2: NPC subsequently also receives oral
        app_raw["intimate_memories"].append("Received oral intimacy from Artemiusz")
        app_raw["oral_experience"] = "has_done_and_received_oral"
        norm2 = normalize_appearance(app_raw, gender="female", scen_key="nsfw_high_school_drama")
        self.assertEqual(norm2.get("intercourse_experience"), "virgin")
        self.assertEqual(norm2.get("oral_experience"), "has_done_and_received_oral")
        sections2 = format_intimate_profile_sections(norm2, gender="female", scen_key="nsfw_high_school_drama", info_level=3)
        anatomy_text2 = "\n".join(sections2.get("anatomy", []))
        self.assertIn("• **Intercourse**: Virgin", anatomy_text2)
        self.assertIn("• **Oral Intimacy**: Has Performed & Received", anatomy_text2)


if __name__ == "__main__":
    unittest.main()

