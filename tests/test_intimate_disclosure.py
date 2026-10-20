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
        self.assertEqual(get_unlocked_info_level(50), 1)
        self.assertEqual(get_unlocked_info_level(99), 1)
        self.assertEqual(get_unlocked_info_level(100), 2)
        self.assertEqual(get_unlocked_info_level(150), 2)
        self.assertEqual(get_unlocked_info_level(199), 2)
        self.assertEqual(get_unlocked_info_level(200), 3)
        self.assertEqual(get_unlocked_info_level(300), 3)

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
        self.assertEqual(get_information_disclosure_penalty(20, 2), -4)
        self.assertEqual(get_information_disclosure_penalty(60, 2), -2)
        self.assertEqual(get_information_disclosure_penalty(100, 2), 0)

        # Level 3 target: Preferences / Intimate Profile / Deep Secrets
        self.assertEqual(get_information_disclosure_penalty(0, 3), -8)
        self.assertEqual(get_information_disclosure_penalty(20, 3), -8)
        self.assertEqual(get_information_disclosure_penalty(60, 3), -5)
        self.assertEqual(get_information_disclosure_penalty(120, 3), -3)
        self.assertEqual(get_information_disclosure_penalty(200, 3), 0)

        # Requirement calculation
        self.assertEqual(get_disclosure_check_requirement(4, current_score=0, target_info_level=3), 12)
        self.assertEqual(get_disclosure_check_requirement(4, current_score=60, target_info_level=3), 9)
        self.assertEqual(get_disclosure_check_requirement(4, current_score=120, target_info_level=3), 7)
        self.assertEqual(get_disclosure_check_requirement(4, current_score=200, target_info_level=3), 4)
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

    def test_dialogue_prompt_virginity_and_dating_history_grounding(self):
        from game_engine.turn.dialogue import _build_dialogue_prompt_block
        from game_engine.turn_context import TurnContext
        import db, time

        db.init_db()
        sess_id = int(time.time() * 1000)
        char_id = 99933
        party = [({"id": char_id, "user_id": 99933, "name": "Artemiusz", "gender": "male", "hp": 20, "max_hp": 20, "mp": 10, "max_mp": 10, "stats": {"STR": 5, "AGI": 5, "END": 5, "INT": 5, "PER": 5, "CHA": 5, "LUK": 5}}, [])]

        session = {
            "id": sess_id,
            "scenario": "nsfw_furry_high_school_drama",
            "host_user_id": 99933,
            "current_location": "School Courtyard",
            "dialogue_partner": "Seo-ah Vance",
            "history": []
        }
        with db.get_conn() as conn:
            conn.execute(
                "INSERT INTO sessions (id, mode, capacity, scenario, current_location, history_json) VALUES (?, 'solo', 1, ?, ?, ?)",
                (sess_id, "nsfw_furry_high_school_drama", "School Courtyard", "[]")
            )
            conn.commit()

        db.upsert_contact(
            session_id=sess_id,
            character_id=char_id,
            npc_id="seo-ah_vance",
            name="Seo-ah Vance",
            delta_score=5,
            appearance={
                "intercourse_experience": "virgin",
                "oral_experience": "inexperienced",
                "manual_experience": "inexperienced",
                "erotic_openness": "shameless",
                "intimate_demeanor": "Poised & Articulate",
                "intimate_dynamic": "Attentive Service-Oriented"
            }
        )
        db.update_contact_relations(
            sess_id,
            "seo-ah_vance",
            {
                "romance": {
                    "status": "Single",
                    "current_partner": None,
                    "secret_partner": None,
                    "ex_partners": []
                }
            },
            char_id
        )

        ctx = TurnContext(sess_id, session)

        actions = [{
            "char": party[0][0],
            "label": "ask her if she has had any experience handling guys",
            "stat": "CHA"
        }]

        block = _build_dialogue_prompt_block(session, ctx, ["Seo-ah Vance"], party, actions)

        # 1. Grounding in virginity AND zero dating history
        self.assertIn("CANON VIRGINITY & PAST EXPERIENCE GROUNDING", block)
        self.assertIn("ZERO prior dating, relationship, or suitor history", block)
        self.assertIn("balancing suitors/guys on their schedule", block)
        self.assertIn("NEVER fabricate fake past suitors", block)

        # 2. Protagonist Gender & Attraction Target Integrity
        self.assertIn("PROTAGONIST GENDER & ATTRACTION TARGET INTEGRITY", block)
        self.assertIn("The player character (Artemiusz) is canonically MALE", block)
        self.assertIn("a GIRL / WOMAN / FEMALE PARTNER", block)
        self.assertIn("NEVER invert attraction or mistakenly ask a male player flirting with a female NPC 'what are you looking for in a guy?'", block)

    def test_deterministic_dialogue_canon_sanitization(self):
        from game_engine.keywords import (
            sanitize_dialogue_canon_and_attraction_integrity,
            validate_canon_dialogue_invariants,
        )
        import db, time

        db.init_db()
        sess_id = int(time.time() * 1000)
        char_id = 99944
        party = [({"id": char_id, "user_id": 99944, "name": "Artemiusz", "gender": "male"}, [])]

        session = {
            "id": sess_id,
            "host_user_id": 99944,
            "dialogue_partner": "Seo-ah Vance",
        }

        db.upsert_contact(
            session_id=sess_id,
            character_id=char_id,
            npc_id="seo-ah_vance",
            name="Seo-ah Vance",
            delta_score=5,
            appearance={
                "intercourse_experience": "virgin",
            }
        )
        db.update_contact_relations(
            sess_id,
            "seo-ah_vance",
            {
                "romance": {
                    "status": "Single",
                    "current_partner": None,
                    "secret_partner": None,
                    "ex_partners": []
                }
            },
            char_id
        )

        raw_hallucinated_prose = (
            'Handling guys?" she repeats, her tone dripping with smooth amusement. '
            '"I\'ve had plenty of practice balancing them on my schedule—though most of them break under the pressure." '
            'She tilts her head with a gleam. "But if you\'re asking about the physical kind? '
            'I\'m still a virgin, Artemiusz. I like to keep my options open until I find someone who '
            'doesn\'t make me want to strangle them for being boring." She taps the keychain. '
            '"So tell me—what exactly are you looking for in a guy?'
        )

        # 1. Validator detects violations in raw hallucinated prose
        violations = validate_canon_dialogue_invariants(raw_hallucinated_prose, session=session, party=party)
        self.assertTrue(len(violations) >= 2)
        self.assertTrue(any("MALE" in v for v in violations))
        self.assertTrue(any("VIRGIN" in v for v in violations))

        # 2. Deterministic sanitizer cleanly repairs both violations
        sanitized = sanitize_dialogue_canon_and_attraction_integrity(raw_hallucinated_prose, session=session, party=party)

        # Invariant 1: No fabricated schedule balancing / suitor rosters
        self.assertNotIn("balancing them on my schedule", sanitized)
        self.assertNotIn("strangle them for being boring", sanitized)

        # Invariant 2: Attraction target flipped from guy to girl for male player
        self.assertIn("what exactly are you looking for in a girl?", sanitized)
        self.assertNotIn("looking for in a guy?", sanitized)

        # Invariant 3: Cleaned text passes validation
        cleaned_violations = validate_canon_dialogue_invariants(sanitized, session=session, party=party)
        self.assertEqual(len(cleaned_violations), 0)

    def test_deterministic_commando_canon_sanitization(self):
        from game_engine.keywords import (
            sanitize_dialogue_canon_and_attraction_integrity,
            validate_canon_dialogue_invariants,
        )
        from mechanics.social.persona.intimacy.formatting import format_body_asset_narrative_directive
        import db, time

        db.init_db()
        sess_id = int(time.time() * 1000) + 1
        char_id = 99945
        party = [({"id": char_id, "user_id": 99945, "name": "Artemiusz", "gender": "male"}, [])]

        session = {
            "id": sess_id,
            "host_user_id": 99945,
            "dialogue_partner": "Seo-ah Vance",
        }

        db.upsert_contact(
            session_id=sess_id,
            character_id=char_id,
            npc_id="seo-ah_vance",
            name="Seo-ah Vance",
            delta_score=5,
            appearance={
                "breast_size": "Voluptuous D-Cup",
                "undergarments": {
                    "bra": "Baby Pink low-cut halter lace bralette",
                    "underwear": "None (Commando)",
                },
            }
        )

        # 1. Verify format_body_asset_narrative_directive outputs commando directive
        directive = format_body_asset_narrative_directive(
            partner_name="Seo-ah Vance",
            gender="female",
            asset_size="Voluptuous D-Cup",
            undergarments={
                "bra": "Baby Pink low-cut halter lace bralette",
                "underwear": "None (Commando)",
            },
        )
        self.assertIn("UNDERGARMENT CANON (Seo-ah Vance - COMMANDO)", directive)
        self.assertIn("wearing NO UNDERWEAR / PANTIES (going completely commando underneath)", directive)
        self.assertIn("STRICTLY FORBIDDEN: NEVER narrate peeling back, sliding aside, pulling down, or snapping panties", directive)
        self.assertIn("LINGERIE FIT & UNDRESSING (Bra: Baby Pink low-cut halter lace bralette)", directive)
        self.assertNotIn("Underwear: None (Commando)): When undressing", directive)

        # 2. Raw hallucinated prose with phantom panties
        raw_prose = (
            "She looked into Artemiusz's eyes and gave a sultry smirk as her fingers found the hem of her pleated skirt. "
            "With deliberate slowness, she lifted the fabric and peeled back the damp fabric of her soaked panties from between her swollen lips with a soft snap against her thigh."
        )

        # 3. Validator detects commando violation
        violations = validate_canon_dialogue_invariants(raw_prose, session=session, party=party)
        self.assertTrue(any("COMMANDO" in v for v in violations))

        # 4. Sanitizer rewrites phantom panty removal to commando-accurate prose
        sanitized = sanitize_dialogue_canon_and_attraction_integrity(raw_prose, session=session, party=party)
        self.assertNotIn("soaked panties", sanitized)
        self.assertNotIn("fabric of her soaked panties", sanitized)
        self.assertNotIn("snap against her thigh", sanitized)
        self.assertIn("bare underneath", sanitized)

        # 5. Cleaned text passes validation
        cleaned_violations = validate_canon_dialogue_invariants(sanitized, session=session, party=party)
        self.assertEqual(len(cleaned_violations), 0)



