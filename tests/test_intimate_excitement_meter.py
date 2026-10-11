import unittest
from mechanics.social.intimate_excitement import (
    classify_intimate_act,
    get_actor_endurance,
    calculate_excitement_delta,
    roll_partner_demand,
    calculate_refractory_duration,
    compute_excitement_step,
    format_compact_discord_meter,
    check_and_resolve_refractory_clock,
    is_in_refractory_cooldown,
    build_intimate_choice_blueprints,
    has_state_contradiction_in_choice,
)
import db
from game_engine.choices_cleaner import clean_choices_impl


class TestIntimateExcitementMeter(unittest.TestCase):
    def setUp(self):
        self.session_id = db.create_session(
            host_user_id=1,
            mode="solo",
            capacity=1,
            verbosity="normal",
            dialogue_mode="turn_based",
            image_gen_enabled=False,
            scenario="nsfw_high_school_drama"
        )
        self.player_char = {
            "name": "Artemiusz",
            "gender": "Male",
            "end_": 6,
            "cha": 7,
            "agi": 6,
        }
        self.partner_contact = {
            "name": "Kana",
            "appearance": {
                "physique": "Athletic & Toned",
                "intimate_dynamic": "Boldly Proactive & Dominant",
                "erotic_openness": "bold",
                "sensitive_spots": ["Inner thighs", "Nape of neck"],
            },
            "traits": ["Athletic", "Determined"]
        }

    def test_classify_intimate_act_genital_vs_nongenital(self):
        """Verify direct genital acts are classified correctly while non-genital touch gives 0 gain."""
        # Non-genital
        res_kiss = classify_intimate_act("Kiss Kana softly on the cheek", "", "Artemiusz", "Kana")
        self.assertEqual(res_kiss["act_type"], "foreplay_nongenital")
        self.assertFalse(res_kiss["player_stimulated"])
        self.assertFalse(res_kiss["partner_stimulated"])

        res_hair = classify_intimate_act("Stroke her hair and hold her hands", "", "Artemiusz", "Kana")
        self.assertEqual(res_hair["act_type"], "foreplay_nongenital")
        self.assertFalse(res_hair["partner_stimulated"])

        # Penetrative Intercourse
        res_pen = classify_intimate_act("Thrust deeper inside Kana with steady rhythm", "", "Artemiusz", "Kana")
        self.assertEqual(res_pen["act_type"], "penetrative")
        self.assertTrue(res_pen["player_stimulated"])
        self.assertTrue(res_pen["partner_stimulated"])

        # Oral Give (player performs oral on Kana)
        res_oral_give = classify_intimate_act("Kneel between her thighs and taste her intimately", "", "Artemiusz", "Kana")
        self.assertEqual(res_oral_give["act_type"], "oral_give")
        self.assertFalse(res_oral_give["player_stimulated"])
        self.assertTrue(res_oral_give["partner_stimulated"])

        # Oral Receive (Kana performs oral on Artemiusz)
        res_oral_rec = classify_intimate_act("Let her take his shaft into her mouth and suck", "", "Artemiusz", "Kana")
        self.assertEqual(res_oral_rec["act_type"], "oral_receive")
        self.assertTrue(res_oral_rec["player_stimulated"])
        self.assertFalse(res_oral_rec["partner_stimulated"])

        # Manual Give
        res_manual = classify_intimate_act("Slip fingers inside her core and rub her clit", "", "Artemiusz", "Kana")
        self.assertEqual(res_manual["act_type"], "manual_give")
        self.assertFalse(res_manual["player_stimulated"])
        self.assertTrue(res_manual["partner_stimulated"])

    def test_sensitive_spot_bonus_triggering(self):
        """Verify targeting revealed sensitive spot awards a bonus flag and spot name."""
        res_spot = classify_intimate_act(
            action_str="Caress along her inner thighs while teasing her entrance",
            intimate_contact_str="",
            player_name="Artemiusz",
            partner_name="Kana",
            partner_contact=self.partner_contact
        )
        self.assertTrue(res_spot["partner_stimulated"])
        self.assertTrue(res_spot["sensitive_spot_matched"])
        self.assertEqual(res_spot["matched_spot"], "Inner thighs")

    def test_endurance_scaling_math(self):
        """Verify delta scales inversely with endurance rating."""
        # High END (10) should gain fewer points per turn (lasts longer)
        delta_high_end = calculate_excitement_delta(base_stim=18, endurance=10)
        # Low END (2) should gain more points per turn (finishes faster)
        delta_low_end = calculate_excitement_delta(base_stim=18, endurance=2)

        self.assertLess(delta_high_end, delta_low_end)
        self.assertGreaterEqual(delta_high_end, 10)
        self.assertLessEqual(delta_low_end, 30)

        # Sensitive spot bonus adds +6
        delta_bonus = calculate_excitement_delta(base_stim=18, endurance=6, sensitive_spot_bonus=True)
        delta_normal = calculate_excitement_delta(base_stim=18, endurance=6, sensitive_spot_bonus=False)
        self.assertEqual(delta_bonus, delta_normal + 6)

    def test_npc_derived_endurance(self):
        """Verify NPC intimate endurance derives consistently from physique and dynamic."""
        athletic_dominant = {
            "name": "Valeria",
            "appearance": {"physique": "Athletic & Toned", "intimate_dynamic": "Dominant"},
            "traits": ["Athletic"]
        }
        frail_receptive = {
            "name": "Lily",
            "appearance": {"physique": "Petite & Frail", "intimate_dynamic": "Gentle & Yielding"},
            "traits": ["Timid"]
        }
        end_high = get_actor_endurance(athletic_dominant, is_player=False)
        end_low = get_actor_endurance(frail_receptive, is_player=False)
        self.assertGreater(end_high, end_low)

    def test_female_multi_climax_vs_male_refractory_stop(self):
        """Verify female player drops to 35% hypersensitive baseline while male triggers spent refractory."""
        # Male Player Test
        male_char = {"name": "Artemiusz", "gender": "Male", "end_": 5}
        phys_state_m = {
            "excitement": {
                "actors": {
                    "Artemiusz": {"meter": 90, "max": 100, "delta": 0, "endurance": 5, "climaxes_count": 0, "status": ""},
                    "Kana": {"meter": 40, "max": 100, "delta": 0, "endurance": 7, "climaxes_count": 0, "status": ""},
                }
            }
        }
        session = {"current_day": 1, "current_minute": 600}
        res_m = compute_excitement_step(
            physical_state=phys_state_m,
            action_str="Thrust deeply inside Kana with intense rhythm",
            player_char=male_char,
            partner_contact=self.partner_contact,
            session=session
        )
        self.assertTrue(res_m["player_climaxed"])
        self.assertTrue(res_m["premature_finish"])
        self.assertEqual(phys_state_m["excitement"]["actors"]["Artemiusz"]["meter"], 100)
        self.assertIn("refractory_until_minute", phys_state_m["excitement"])

        # Female Player Test
        female_char = {"name": "Seraphina", "gender": "Female", "end_": 5}
        phys_state_f = {
            "excitement": {
                "actors": {
                    "Seraphina": {"meter": 90, "max": 100, "delta": 0, "endurance": 5, "climaxes_count": 0, "status": ""},
                    "Kana": {"meter": 40, "max": 100, "delta": 0, "endurance": 7, "climaxes_count": 0, "status": ""},
                }
            }
        }
        res_f = compute_excitement_step(
            physical_state=phys_state_f,
            action_str="Thrust deeply inside Kana with intense rhythm",
            player_char=female_char,
            partner_contact=self.partner_contact,
            session=session
        )
        self.assertTrue(res_f["player_climaxed"])
        # Hypersensitive baseline reset for multiorgasmic continuity
        self.assertEqual(phys_state_f["excitement"]["actors"]["Seraphina"]["meter"], 35)

    def test_in_game_clock_refractory_cooldown_and_toast(self):
        """Verify refractory timer compares against in-game clock and emits toast once."""
        phys_state = {
            "excitement": {
                "refractory_until_minute": (1 * 1440) + 640,  # Cooldown expires at Day 1, Minute 640 (10:40)
                "cooldown_notified": False,
            }
        }
        # Time at 620 (10:20): still in cooldown
        session_early = {"current_day": 1, "current_minute": 620}
        in_refr, left = is_in_refractory_cooldown(session_early, phys_state)
        self.assertTrue(in_refr)
        self.assertEqual(left, 20)

        recovered_early, toast_early = check_and_resolve_refractory_clock(session_early, phys_state)
        self.assertFalse(recovered_early)
        self.assertIsNone(toast_early)

        # Time at 645 (10:45): expired!
        session_later = {"current_day": 1, "current_minute": 645}
        recovered, toast = check_and_resolve_refractory_clock(session_later, phys_state)
        self.assertTrue(recovered)
        self.assertIn("Stamina Recovered", toast)

        # Subsequent check: already notified, returns False
        recovered_again, toast_again = check_and_resolve_refractory_clock(session_later, phys_state)
        self.assertFalse(recovered_again)
        self.assertIsNone(toast_again)

    def test_discord_compact_formatting_under_80_chars(self):
        """Verify the Discord formatting is strictly compact (< 80 characters total)."""
        line = format_compact_discord_meter(
            player_name="Artemiusz",
            player_meter=54,
            partner_name="Kana",
            partner_meter=82,
            partner_climaxed=False
        )
        self.assertLess(len(line), 80)
        self.assertIn("Artemiusz: 54%", line)
        self.assertIn("Kana: 82%", line)
        self.assertIn("▰", line)
        self.assertIn("▱", line)

    def test_choices_cleaner_premature_finish_negotiation(self):
        """Verify choices cleaner injects AGI/CHA/END negotiation choices when partner demands."""
        db.update_session_physical_state(self.session_id, {
            "intimate_contact": "Intimate encounter with Kana (player reached climax spent, partner unsatisfied)",
            "climax_state": {"partner_climaxed": False, "player_climaxed": True},
            "excitement": {
                "active": True,
                "premature_finish": True,
                "partner_demanded": True,
                "actors": {
                    "Artemiusz": {"meter": 100},
                    "Kana": {"meter": 45}
                }
            }
        })
        raw_choices = [
            {"label": "Look around the room", "stat": "PER"},
            {"label": "Sleep immediately", "stat": "FREE"},
        ]
        cleaned = clean_choices_impl(
            None,
            choices=raw_choices,
            scenario="nsfw_high_school_drama",
            location="Bedroom",
            char=self.player_char,
            dialogue_partner="Kana",
            session_id=self.session_id
        )
        labels = [c["label"] for c in cleaned]
        stats = [c["stat"] for c in cleaned]

        self.assertTrue(any("fingers" in l.lower() for l in labels))
        self.assertTrue(any("tongue" in l.lower() for l in labels))
        self.assertIn("AGI", stats)
        self.assertIn("CHA", stats)
        self.assertIn("END", stats)


    def test_colloquial_oral_action_detection(self):
        """Verify colloquial action like 'show you what that mouth can do' triggers oral_receive."""
        action = "Guide her head down toward your lap and ask her to show you what that mouth can do"
        partner = {"name": "Mia", "appearance": {"physique": "Slender", "intimate_dynamic": "Receptive"}}
        res = classify_intimate_act(
            action_str=action,
            intimate_contact_str="",
            player_name="Artemiusz",
            partner_name="Mia",
            partner_contact=partner
        )
        self.assertEqual(res["act_type"], "oral_receive")
        self.assertTrue(res["player_stimulated"])
        self.assertFalse(res["partner_stimulated"])

        # Test compute_excitement_step
        phys_state = {}
        session = {"current_day": 1, "current_minute": 500}
        step_res = compute_excitement_step(
            physical_state=phys_state,
            action_str=action,
            player_char=self.player_char,
            partner_contact=partner,
            session=session
        )
        self.assertTrue(step_res["active"])
        self.assertEqual(step_res["act_type"], "oral_receive")
        self.assertGreater(step_res["player_meter"], 0)
        self.assertEqual(step_res["partner_meter"], 0)
        self.assertEqual(step_res["player_name"], "Artemiusz")
        self.assertEqual(step_res["partner_name"], "Mia")

    def test_narrative_fallback_detection(self):
        """Verify narrative text detects oral when player prompt is subtle/euphemistic."""
        vague_action = "Lean back and let her take charge"
        narrative = (
            "Mia sinks between your parted thighs. Her lips part, and with slow reverence, "
            "she takes you into her mouth. Her tongue swirls around the sensitive crown, "
            "hollowing her cheeks to deepen the suction."
        )
        partner = {"name": "Mia", "appearance": {}}
        res = classify_intimate_act(
            action_str=vague_action,
            intimate_contact_str="",
            player_name="Artemiusz",
            partner_name="Mia",
            partner_contact=partner,
            narrative_str=narrative
        )
        self.assertEqual(res["act_type"], "oral_receive")
        self.assertTrue(res["player_stimulated"])
        self.assertFalse(res["partner_stimulated"])

    def test_mouth_kiss_non_genital_filtering(self):
        """Verify mouth kisses do not falsely trigger genital excitement."""
        action = "Kiss Mia softly on the mouth and pull her into a warm embrace"
        res = classify_intimate_act(
            action_str=action,
            intimate_contact_str="",
            player_name="Artemiusz",
            partner_name="Mia"
        )
        self.assertEqual(res["act_type"], "foreplay_nongenital")
        self.assertFalse(res["player_stimulated"])
        self.assertFalse(res["partner_stimulated"])

    def test_scunthorpe_word_boundary_collisions(self):
        """Verify substring collisions (cocktail, assassin, document, moral, stride, etc.) NEVER trigger intimate acts."""
        scunthorpe_samples = [
            "Order a cocktail at the tavern bar while chatting with the innkeeper",
            "The cunning assassin hid silently in the tall grass",
            "The clerk organized every document and accumulated records",
            "The cleric gave a lecture on moral philosophy and pastoral care",
            "He took a long stride across the stone bridge",
            "The candle began to flicker in the chilly draft",
            "Split the firewood with a heavy iron axe",
        ]
        for phrase in scunthorpe_samples:
            res = classify_intimate_act(phrase, "", "Artemiusz", "Kana")
            self.assertEqual(
                res["act_type"],
                "none",
                f"Scunthorpe collision failure on phrase: '{phrase}' -> got act_type '{res['act_type']}'"
            )
            self.assertFalse(res["player_stimulated"])
            self.assertFalse(res["partner_stimulated"])

    def test_scunthorpe_benign_idiom_disambiguation(self):
        """Verify benign idioms using ambiguous words (shaft of light, cocked eyebrow, horseback ride, etc.) are sanitized."""
        idiom_samples = [
            "A shaft of golden sunlight filtered through the tavern window",
            "He cocked an eyebrow at the merchant and crossed his fingers",
            "They went on a long horseback ride through the northern valley",
            "She swallowed hard, sucked in a sharp breath, and drew her bow",
            "The knight ran a lap around the training grounds before drinking water",
            "Taste the fine vintage wine and eat the roasted meat",
            "Flames lick at the hearth while the dog licked its paws",
            "Enter the dark dungeon chamber and investigate the chest",
            "The warrior's spear penetrated the shield and plunged into the river",
            "Pointed a finger at the map while eating finger food",
        ]
        for phrase in idiom_samples:
            res = classify_intimate_act(phrase, "", "Artemiusz", "Kana")
            self.assertEqual(
                res["act_type"],
                "none",
                f"Benign idiom false positive on phrase: '{phrase}' -> got act_type '{res['act_type']}'"
            )
            self.assertFalse(res["player_stimulated"])
            self.assertFalse(res["partner_stimulated"])

    def test_colloquial_intimacy_and_narrative_choices(self):
        """Verify rich colloquial narrative actions are classified accurately with correct directionality."""
        # Colloquial penetrative
        res_pen = classify_intimate_act("Slide inside her slowly and bury yourself deep", "", "Artemiusz", "Kana")
        self.assertEqual(res_pen["act_type"], "penetrative")
        self.assertTrue(res_pen["player_stimulated"])
        self.assertTrue(res_pen["partner_stimulated"])

        # Colloquial manual give
        res_man_give = classify_intimate_act("Circle her clit with gentle fingers and tease her folds", "", "Artemiusz", "Kana")
        self.assertEqual(res_man_give["act_type"], "manual_give")
        self.assertFalse(res_man_give["player_stimulated"])
        self.assertTrue(res_man_give["partner_stimulated"])

        # Colloquial manual receive
        res_man_rec = classify_intimate_act("She wraps her hand around his length and strokes your shaft", "", "Artemiusz", "Kana")
        self.assertEqual(res_man_rec["act_type"], "manual_receive")
        self.assertTrue(res_man_rec["player_stimulated"])
        self.assertFalse(res_man_rec["partner_stimulated"])

        # Colloquial oral give
        res_oral_give = classify_intimate_act("Bury your face between her parted thighs and lap at her core", "", "Artemiusz", "Kana")
        self.assertEqual(res_oral_give["act_type"], "oral_give")
        self.assertFalse(res_oral_give["player_stimulated"])
        self.assertTrue(res_oral_give["partner_stimulated"])

    def test_merge_physical_state_updates_preserves_excitement(self):
        """Verify merge_physical_state_updates preserves excitement state across turns."""
        from mechanics.social.physical_state import merge_physical_state_updates
        initial = {
            "actors": {"Artemiusz": {"posture": "seated", "clothing": {"top": "clothed"}}},
            "excitement": {
                "actors": {
                    "Artemiusz": {"meter": 30, "max": 100, "delta": 30, "endurance": 6},
                    "Mia Yamada": {"meter": 0, "max": 100, "delta": 0, "endurance": 5}
                },
                "active": True
            }
        }
        # 1. Non-dict updates (early return)
        res_empty = merge_physical_state_updates(initial, None)
        self.assertIn("excitement", res_empty)
        self.assertEqual(res_empty["excitement"]["actors"]["Artemiusz"]["meter"], 30)

        # 2. Dict updates with actor changes
        updates = {"actors": {"Artemiusz": {"posture": "standing"}}}
        res_merged = merge_physical_state_updates(initial, updates)
        self.assertIn("excitement", res_merged)
        self.assertEqual(res_merged["excitement"]["actors"]["Artemiusz"]["meter"], 30)

    def test_compute_excitement_step_strips_markdown_and_preserves_actors(self):
        """Verify compute_excitement_step matches markdown decorated keys (*Mia Yamada*) and does not reset meter."""
        phys_state = {
            "intimate_contact": "Intimate encounter with Mia Yamada (manual give)",
            "excitement": {
                "actors": {
                    "Artemiusz": {"meter": 30, "max": 100, "delta": 30, "endurance": 6, "climaxes_count": 0, "status": "Warming Up"},
                    "*Mia Yamada*": {"meter": 10, "max": 100, "delta": 10, "endurance": 5, "climaxes_count": 0, "status": "Warming Up"},
                },
                "active": True
            }
        }
        partner = {"name": "Mia Yamada", "appearance": {}, "traits": []}
        step_res = compute_excitement_step(
            physical_state=phys_state,
            action_str="stroke her clit and rub her thighs intimately",
            player_char=self.player_char,
            partner_contact=partner,
            session={"current_day": 1, "current_minute": 500}
        )
        # Artemiusz gave manual stimulation -> player_delta=0, player_meter stays 30!
        self.assertEqual(step_res["player_meter"], 30)
        self.assertEqual(step_res["player_delta"], 0)
        # Mia Yamada matched the *Mia Yamada* key -> meter increased from 10!
        self.assertGreater(step_res["partner_meter"], 10)
        # Clean key should be present in actors, dirty key should be migrated
        self.assertIn("Mia Yamada", phys_state["excitement"]["actors"])
        self.assertNotIn("*Mia Yamada*", phys_state["excitement"]["actors"])

    def test_reduce_social_deduplicates_relationship_updates(self):
        """Verify _reduce_social_and_milestones deduplicates duplicate NPC updates in the outcome."""
        from game_engine.state.social import _reduce_social_and_milestones
        outcome = {
            "relationship_updates": [
                {
                    "npc_name": "Mia Yamada",
                    "delta_score": 1,
                    "memory_summary": "First note",
                    'intimate_revealed": true': "malformed_key"
                },
                {
                    "npc_name": "Mia Yamada",
                    "delta_score": 1,
                    "memory_summary": "Second note"
                }
            ]
        }
        _reduce_social_and_milestones(
            session_id=self.session_id,
            session={"current_npcs": [{"name": "Mia Yamada"}]},
            party=[(self.player_char, [])],
            outcome=outcome,
            actions=[{"label": "Talk to Mia Yamada", "check": None}],
            scen_key="nsfw_high_school_drama",
            items_gained_by_user={},
            first_char_id=1,
            first_char_name="Artemiusz"
        )
        rel_ups = outcome.get("relationship_updates", [])
        self.assertEqual(len(rel_ups), 1, f"Expected 1 deduplicated update, got {len(rel_ups)}")
        self.assertEqual(rel_ups[0]["npc_name"], "Mia Yamada")

    def test_breast_touch_is_foreplay_and_never_triggers_climax(self):
        """Verify touching breasts/chest without genital stimulation is non-genital foreplay and awards 0% meter and cannot trigger climax."""
        action_text = "lustfully touch and caress her furry body especially her furry boobs"
        narrative_text = "You reach out, your fingers sinking into the dense, warm fur of her chest. Her body shivers under you..."

        # 1. Classification
        res = classify_intimate_act(
            action_str=action_text,
            intimate_contact_str="",
            player_name="Artemiusz",
            partner_name="Mia Yamada",
            narrative_str=narrative_text
        )
        self.assertEqual(res["act_type"], "foreplay_nongenital")
        self.assertFalse(res["player_stimulated"])
        self.assertFalse(res["partner_stimulated"])

        # 2. Excitement step preserves baseline meter without gain
        phys_state = {
            "intimate_contact": "Intimate encounter with Mia Yamada",
            "excitement": {
                "actors": {
                    "Artemiusz": {"meter": 30, "max": 100, "delta": 0, "endurance": 6, "climaxes_count": 0, "status": "Arousal Building"},
                    "Mia Yamada": {"meter": 0, "max": 100, "delta": 0, "endurance": 5, "climaxes_count": 0, "status": "Warming Up"},
                },
                "active": True
            }
        }
        partner = {"name": "Mia Yamada", "appearance": {"sensitive_spots": ["Breasts", "Shoulder blades"]}, "traits": []}
        step_res = compute_excitement_step(
            physical_state=phys_state,
            action_str=action_text,
            player_char=self.player_char,
            partner_contact=partner,
            session={"current_day": 1, "current_minute": 500},
            narrative_str=narrative_text
        )
        self.assertEqual(step_res["act_type"], "foreplay_nongenital")
        self.assertEqual(step_res["player_delta"], 0)
        self.assertEqual(step_res["partner_delta"], 0)
        self.assertEqual(step_res["player_meter"], 30)
        self.assertEqual(step_res["partner_meter"], 0)
        self.assertFalse(step_res["partner_climaxed"])

        # 3. Even if partner meter is already at 100%, non-genital foreplay cannot trigger climax
        phys_state["excitement"]["actors"]["Mia Yamada"]["meter"] = 100
        step_climax_check = compute_excitement_step(
            physical_state=phys_state,
            action_str=action_text,
            player_char=self.player_char,
            partner_contact=partner,
            session={"current_day": 1, "current_minute": 500},
            narrative_str=narrative_text
        )
        self.assertFalse(step_climax_check["partner_climaxed"], "Non-genital foreplay must NEVER trigger climax!")

    def test_false_positive_elimination_across_game(self):
        """Verify colloquial phrases, idioms, spatial references, and non-intimate actions return 'none' act_type."""
        false_positive_cases = [
            ("What the heck is going on?", "The guard looked around."),
            ("Filled her cup with warm tea", "She smiled politely at the host."),
            ("Licked his dry lips in nervousness", "He gripped the hilt of his sword."),
            ("Hide in shadows", "Her heart was pounding inside her chest as she hid from the guard."),
            ("Wait outside", "He waited for her to enter her house before departing."),
            ("Shoot arrow", "The arrow penetrated her shoulder with a sharp thud."),
            ("Check mail", "A letter slid into her pocket during the marketplace bustle."),
            ("Monster attack", "The beast sank its fangs into her neck in the wild."),
            ("Interrogate witness", "Pump the guard for information about the missing shipment."),
            ("Search dungeon", "Examine and open the heavy wooden chest for loot.")
        ]

        for action, narrative in false_positive_cases:
            res = classify_intimate_act(
                action_str=action,
                intimate_contact_str="",
                player_name="Artemiusz",
                partner_name="Mia Yamada",
                narrative_str=narrative
            )
            self.assertEqual(
                res["act_type"], "none",
                f"False positive triggered! '{action}' + '{narrative}' was classified as {res['act_type']}"
            )
            self.assertFalse(res["player_stimulated"])
            self.assertFalse(res["partner_stimulated"])

    def test_climax_negation_guards(self):
        """Verify negated climax mentions in narrative do not trigger false climax detections."""
        from mechanics.social.physical_state import detect_partner_climax, detect_player_climax

        negated_partner_narratives = [
            "Mia was breathing heavily, but she was nowhere near climax as they took their time.",
            "She was still far from reaching her climax, smiling at his measured pace.",
            "Before her climax could arrive, he paused to catch his breath.",
            "Without reaching climax, she rested her forehead against his shoulder.",
            "He held back, preventing her from reaching peak too early."
        ]
        for narrative in negated_partner_narratives:
            self.assertFalse(
                detect_partner_climax(narrative, partner_name="Mia"),
                f"Negated climax falsely triggered partner climax for: {narrative}"
            )

        negated_player_narratives = [
            "Artemiusz was nowhere near his own climax as he maintained an even rhythm.",
            "He fought the urge to reach his own climax, holding steady.",
            "Trying not to spill deep inside, he paused and drew a slow breath.",
            "He was far from his own release, savoring the warmth between them."
        ]
        for narrative in negated_player_narratives:
            self.assertFalse(
                detect_player_climax(narrative, player_name="Artemiusz"),
                f"Negated climax falsely triggered player climax for: {narrative}"
            )

        # Confirm genuine, non-negated climaxes still trigger properly
        genuine_partner = "Mia trembled violently as her shuddering climax tore through her core."
        self.assertTrue(detect_partner_climax(genuine_partner, partner_name="Mia"))

        genuine_player = "Artemiusz let out a breath as he reached his own climax, spilling deep inside."
        self.assertTrue(detect_player_climax(genuine_player, player_name="Artemiusz"))

    def test_disengagement_action_intent(self):
        """Verify explicit disengagement actions yield 'none' act_type and 0 stimulation even during intimate encounters."""
        disengagement_actions = [
            "Step back and catch my breath",
            "Gently pull away and rest",
            "Break contact and smile",
            "Withdraw and get dressed",
            "Slow down and rest"
        ]
        for act in disengagement_actions:
            res = classify_intimate_act(
                action_str=act,
                intimate_contact_str="Intimate encounter with Mia Yamada",
                player_name="Artemiusz",
                partner_name="Mia Yamada",
                narrative_str="She smiles warmly as they pause."
            )
            self.assertEqual(res["act_type"], "none", f"Action '{act}' should disengage, but got {res['act_type']}")
            self.assertFalse(res["player_stimulated"])
            self.assertFalse(res["partner_stimulated"])

    def test_oral_give_gerund_and_narrative_directionality(self):
        """Verify progressive verb forms like 'eating her out' classify as oral_give and stimulate the partner, not the player."""
        action_text = "get on your knees and begin eating her out"
        narrative_text = (
            "You drop to your knees on the cool wood floor, positioning yourself between her spread thighs. "
            "She breathes out as you take her into your mouth and deepen your suction."
        )
        res = classify_intimate_act(
            action_str=action_text,
            intimate_contact_str="Intimate encounter with Mia Yamada",
            player_name="Artemiusz",
            partner_name="Mia Yamada",
            narrative_str=narrative_text
        )
        self.assertEqual(res["act_type"], "oral_give")
        self.assertFalse(res["player_stimulated"])
        self.assertTrue(res["partner_stimulated"])

        phys_state = {
            "intimate_contact": "Intimate encounter with Mia Yamada",
            "excitement": {
                "actors": {
                    "Artemiusz": {"meter": 30, "max": 100, "delta": 0, "endurance": 1, "climaxes_count": 0, "status": "Arousal Building"},
                    "Mia Yamada": {"meter": 0, "max": 100, "delta": 0, "endurance": 2, "climaxes_count": 0, "status": "Warming Up"},
                },
                "active": True
            }
        }
        partner = {"name": "Mia Yamada", "appearance": {"sensitive_spots": ["Shoulder blades (Physical)", "Tail base & spine line (Physical)"]}, "traits": []}
        step_res = compute_excitement_step(
            physical_state=phys_state,
            action_str=action_text,
            player_char=self.player_char,
            partner_contact=partner,
            session={"current_day": 1, "current_minute": 500},
            narrative_str=narrative_text
        )
        self.assertEqual(step_res["act_type"], "oral_give")
        self.assertEqual(step_res["player_delta"], 0)
        self.assertEqual(step_res["player_meter"], 30)
        self.assertGreater(step_res["partner_delta"], 0)
        self.assertGreater(step_res["partner_meter"], 0)

    def test_manual_give_vs_manual_receive_directionality(self):
        """Verify manual_give and manual_receive resolve directionality accurately even when narrative mentions hands on shoulders."""
        # 1. Manual give with narrative mentioning partner's hand on player's shoulder
        res_give = classify_intimate_act(
            action_str="slide two fingers inside her and stroke her core",
            intimate_contact_str="Intimate encounter with Mia Yamada",
            player_name="Artemiusz",
            partner_name="Mia Yamada",
            narrative_str="She gasps sharply, placing her hand on your shoulder as your fingers move inside her."
        )
        self.assertEqual(res_give["act_type"], "manual_give")
        self.assertFalse(res_give["player_stimulated"])
        self.assertTrue(res_give["partner_stimulated"])

        # 2. Manual receive (partner stimulating male player)
        res_rec_male = classify_intimate_act(
            action_str="let her stroke your shaft",
            intimate_contact_str="Intimate encounter with Mia Yamada",
            player_name="Artemiusz",
            partner_name="Mia Yamada",
            narrative_str="She wraps her fingers around your length, pumping your shaft at a steady pace."
        )
        self.assertEqual(res_rec_male["act_type"], "manual_receive")
        self.assertTrue(res_rec_male["player_stimulated"])
        self.assertFalse(res_rec_male["partner_stimulated"])

        # 3. Manual receive (partner stimulating female player)
        res_rec_female = classify_intimate_act(
            action_str="let her slip fingers inside you and stroke your core",
            intimate_contact_str="Intimate encounter with Mia Yamada",
            player_name="Seraphina",
            partner_name="Mia Yamada",
            narrative_str="Her fingers slide between your thighs, stroking your core tenderly."
        )
        self.assertEqual(res_rec_female["act_type"], "manual_receive")
        self.assertTrue(res_rec_female["player_stimulated"])
        self.assertFalse(res_rec_female["partner_stimulated"])

    def test_anal_intimacy_directionality_turn_offs_and_preferences(self):
        """Verify penetrative anal (mutual unless turn_off), oral/manual anal (one-way), and act_likes bonuses."""
        # 1. Penetrative anal_give (default mutual stimulation)
        partner_neutral = {"name": "Mia Yamada", "appearance": {}, "traits": []}
        res_give = classify_intimate_act(
            action_str="penetrate her rear and thrust anally",
            intimate_contact_str="Intimate encounter with Mia Yamada",
            player_name="Artemiusz",
            partner_name="Mia Yamada",
            partner_contact=partner_neutral,
            narrative_str="You slowly slide into her rear, establishing a steady rhythm."
        )
        self.assertEqual(res_give["act_type"], "anal_give")
        self.assertTrue(res_give["player_stimulated"])
        self.assertTrue(res_give["partner_stimulated"])
        self.assertFalse(res_give["sensitive_spot_matched"])

        # 2. Penetrative anal_receive (pegging / receiving anal -> mutual stimulation)
        res_rec = classify_intimate_act(
            action_str="let her peg you",
            intimate_contact_str="Intimate encounter with Mia Yamada",
            player_name="Artemiusz",
            partner_name="Mia Yamada",
            partner_contact=partner_neutral,
            narrative_str="She takes you anally, thrusting into your rear with steady rhythm."
        )
        self.assertEqual(res_rec["act_type"], "anal_receive")
        self.assertTrue(res_rec["player_stimulated"])
        self.assertTrue(res_rec["partner_stimulated"])

        # 3. Partner with 'Anal play & backdoor intimacy' in turn_offs -> partner gets 0% while player still increases
        partner_turnoff = {
            "name": "Mia Yamada",
            "appearance": {"turn_offs": "Anal play & backdoor intimacy"},
            "traits": []
        }
        phys_state_to = {
            "intimate_contact": "Intimate encounter with Mia Yamada",
            "excitement": {"actors": {}, "active": True}
        }
        step_to = compute_excitement_step(
            physical_state=phys_state_to,
            action_str="penetrate her rear and thrust anally",
            player_char=self.player_char,
            partner_contact=partner_turnoff,
            session={"current_day": 1, "current_minute": 500},
            narrative_str="You slide into her rear."
        )
        self.assertEqual(step_to["act_type"], "anal_give")
        self.assertGreater(step_to["player_delta"], 0)
        self.assertEqual(step_to["partner_delta"], 0)
        self.assertEqual(step_to["partner_meter"], 0)

        # 4. Partner with 'Receiving anal intimacy' in act_likes -> partner gets +6% bonus
        partner_likes = {
            "name": "Mia Yamada",
            "appearance": {"act_likes": "Receiving anal intimacy"},
            "traits": []
        }
        phys_state_like = {
            "intimate_contact": "Intimate encounter with Mia Yamada",
            "excitement": {"actors": {}, "active": True}
        }
        step_like = compute_excitement_step(
            physical_state=phys_state_like,
            action_str="penetrate her rear and thrust anally",
            player_char=self.player_char,
            partner_contact=partner_likes,
            session={"current_day": 1, "current_minute": 500},
            narrative_str="You slide into her rear."
        )
        self.assertTrue(step_like["sensitive_spot_matched"])
        self.assertEqual(step_like["matched_spot"], "Anal Intimacy")

        # 5. Oral / Manual Anal (one-way receiver-only stimulation)
        res_rim_give = classify_intimate_act(
            action_str="kneel behind her and lick her anus",
            intimate_contact_str="Intimate encounter with Mia Yamada",
            player_name="Artemiusz",
            partner_name="Mia Yamada",
            partner_contact=partner_likes,
            narrative_str="You rim her tenderly."
        )
        self.assertEqual(res_rim_give["act_type"], "oral_give")
        self.assertFalse(res_rim_give["player_stimulated"])
        self.assertTrue(res_rim_give["partner_stimulated"])
        self.assertTrue(res_rim_give["sensitive_spot_matched"])

        res_finger_give = classify_intimate_act(
            action_str="tease and finger her rear",
            intimate_contact_str="Intimate encounter with Mia Yamada",
            player_name="Artemiusz",
            partner_name="Mia Yamada",
            partner_contact=partner_neutral,
            narrative_str="You slip a finger into her rear."
        )
        self.assertEqual(res_finger_give["act_type"], "manual_give")
        self.assertFalse(res_finger_give["player_stimulated"])
        self.assertTrue(res_finger_give["partner_stimulated"])

        # 6. Benign spatial 'rear' and 'peg' idioms must not trigger false positives
        for benign_act, benign_narr in [
            ("Enter through the rear door", "You slip through the rear entrance of the tavern."),
            ("Set up camp", "Hammer the wooden pegs into the ground and secure the tent."),
        ]:
            res_benign = classify_intimate_act(
                action_str=benign_act,
                intimate_contact_str="",
                player_name="Artemiusz",
                partner_name="Mia Yamada",
                narrative_str=benign_narr
            )
            self.assertEqual(res_benign["act_type"], "none")

    def test_choices_cleaner_preserves_dynamic_llm_choices_during_intimacy(self):
        """Verify clean_choices_impl preserves dynamic LLM choices during oral/foreplay without replacing them with hardcoded penetrative choices."""
        db.update_session_physical_state(self.session_id, {
            "intimate_contact": "Intimate encounter with Mia Yamada (oral give)",
            "climax_state": {"partner_climaxed": False, "player_climaxed": False},
            "excitement": {
                "active": True,
                "last_act": "oral_give",
                "actors": {
                    "Artemiusz": {"meter": 30, "status": "Arousal Building"},
                    "Mia Yamada": {"meter": 26, "status": "Arousal Building"}
                }
            }
        })
        dynamic_llm_choices = [
            {"label": "Hold Mia Yamada by the hips against the piano bench and lick her core", "stat": "AGI", "requirement": 6},
            {"label": "Trace her sensitive spine and tail base while teasing her with your tongue", "stat": "PER", "requirement": 6},
            {"label": "Rise from your knees and kiss up her stomach toward her lips", "stat": "CHA", "requirement": 5},
            {"label": "Step back gently, excuse yourself, and pause with Mia Yamada", "stat": "NONE", "requirement": 0},
        ]
        cleaned = clean_choices_impl(
            None,
            choices=dynamic_llm_choices,
            scenario="nsfw_furry_high_school_drama",
            location="Music Room",
            char=self.player_char,
            dialogue_partner="Mia Yamada",
            session_id=self.session_id
        )
        labels = [c["label"] for c in cleaned]
        self.assertIn("Hold Mia Yamada by the hips against the piano bench and lick her core", labels)
        self.assertIn("Trace her sensitive spine and tail base while teasing her with your tongue", labels)
        self.assertIn("Rise from your knees and kiss up her stomach toward her lips", labels)
        self.assertFalse(any("through her tremors" in l for l in labels))
        self.assertFalse(any("gently withdraw" in l for l in labels))
        # Ensure the exit choice stays a FREE/NONE action
        exit_choices = [c for c in cleaned if c["stat"] == "NONE"]
        self.assertEqual(len(exit_choices), 1)

    def test_hybrid_guided_blueprints_and_contradiction_pruning(self):
        """Verify Hybrid Guided System generates act/posture/meter-aware blueprints, injects prompt guides, and prunes state contradictions."""
        from mechanics.social.intimate_excitement import build_intimate_choice_blueprints
        from mechanics.social.physical_state import build_physical_prompt_block

        phys_state = {
            "actors": {
                "Artemiusz": {"posture": "Kneeling on the floor between her thighs", "holding": "Empty hands", "clothing": {"top": "Cardigan", "bottom": "Trousers"}},
                "Mia Yamada": {"posture": "Leaning back on the piano bench", "holding": "Gripping cardigan", "clothing": {"top": "Undone", "bottom": "Removed"}},
            },
            "intimate_contact": "Intimate encounter with Mia Yamada (oral give)",
            "climax_state": {"partner_climaxed": False, "player_climaxed": False},
            "excitement": {
                "active": True,
                "last_act": "oral_give",
                "actors": {
                    "Artemiusz": {"meter": 30, "status": "Arousal Building"},
                    "Mia Yamada": {"meter": 26, "status": "Arousal Building"},
                },
            },
        }
        db.update_session_physical_state(self.session_id, phys_state)

        # 1. Verify Layer 1 Prompt Blueprint Injection
        prompt_text = build_physical_prompt_block(
            session={"id": self.session_id, "scenario": "nsfw_furry_high_school_drama", "dialogue_partner": "Mia Yamada"},
            party=[(self.player_char, [])],
            is_nsfw=True,
        )
        self.assertIn("HYBRID CHOICE BLUEPRINTS", prompt_text)
        self.assertIn("deepen the teasing rhythm of your tongue", prompt_text)
        self.assertNotIn("through her tremors", prompt_text)
        self.assertNotIn("gently withdraw", prompt_text)

        # 2. Verify Layer 2 Contradiction Pruning & Act-Aware Replenishment
        contradictory_choices = [
            {"label": "Maintain a steady, deep rhythm and hold Mia Yamada through her tremors", "stat": "END", "requirement": 6},
            {"label": "Whisper breathless praise into Mia Yamada's ear and quicken your pace", "stat": "CHA", "requirement": 6},
            {"label": "Shift position to drive deeper and push over the edge together with Mia Yamada", "stat": "STR", "requirement": 7},
            {"label": "Slow your rhythm, gently withdraw, and hold Mia Yamada close in aftercare", "stat": "NONE", "requirement": 0},
        ]
        repaired = clean_choices_impl(
            None,
            choices=contradictory_choices,
            scenario="nsfw_furry_high_school_drama",
            location="Music Room",
            char=self.player_char,
            dialogue_partner="Mia Yamada",
            session_id=self.session_id,
        )
        repaired_labels = [c["label"] for c in repaired]
        # None of the contradictory penetrative/climax choices should survive during oral_give at 26% meter!
        self.assertFalse(any("through her tremors" in l for l in repaired_labels))
        self.assertFalse(any("drive deeper" in l for l in repaired_labels))
        self.assertFalse(any("gently withdraw" in l for l in repaired_labels))
        # Replaced by oral_give / kneeling blueprints + non-penetrative free exit
        self.assertTrue(any("tongue" in l.lower() or "oral" in l.lower() for l in repaired_labels))
        self.assertTrue(any("rise from your knees" in l.lower() for l in repaired_labels))
        free_exits = [c for c in repaired if c["stat"] == "NONE"]
        self.assertEqual(len(free_exits), 1)
        self.assertIn("Ease back gently, pause to catch your breath", free_exits[0]["label"])

        # 3. Verify High-Meter (>= 70%) Blueprint Unlocks Climax Option
        bp_high = build_intimate_choice_blueprints(
            partner_name="Mia Yamada",
            last_act="oral_give",
            player_posture="Kneeling",
            partner_meter=82,
            sensitive_spots=["Tail base & spine line (Physical)"],
        )
        high_labels = [c["label"] for c in bp_high["choices"]]
        self.assertTrue(any("tail base & spine line" in l.lower() for l in high_labels))
        self.assertTrue(any("push her over the edge" in l.lower() for l in high_labels))

    def test_reducer_guards_unverified_llm_climax_and_syncs_act_transitions(self):
        """
        Verify:
        1. Unverified LLM physical_updates['partner_climaxed']=True at low meter (<100%)
           does NOT falsely transition intimate_contact to 'partner reached climax'.
        2. When partner genuinely climaxes during oral_give, intimate_contact is set to
           '(oral give - partner reached climax, ongoing for player)' rather than 'intercourse'.
        3. Party recruitment and confession auto-injections in clean_choices_impl are suppressed
           during active intimate sessions.
        """
        from game_engine.state.reducers import _reduce_physical_state_and_memories
        from game_engine.choices_cleaner import clean_choices_impl

        session = db.get_session(self.session_id)
        session["dialogue_partner"] = "Mia Yamada"
        session["dialogue_partners"] = ["Mia Yamada"]
        session["physical_state"] = {
            "intimate_contact": "Intimate encounter with Mia Yamada (oral give)",
            "climax_state": {"partner_climaxed": False, "player_climaxed": False},
            "actors": {
                "Artemiusz": {"clothing": "shirtless", "posture": "Kneeling between Mia Yamada's thighs"},
                "Mia Yamada": {"clothing": "nude", "posture": "Sitting on the edge of the desk"},
            },
            "excitement": {
                "player_meter": 16,
                "partner_meter": 16,
                "partner_name": "Mia Yamada",
                "active": True,
                "last_act": "oral_give",
                "turn_count": 1,
                "partner_orgasm_count": 0,
                "player_orgasm_count": 0,
                "premature_finish": False,
                "refractory_until": None,
                "consecutive_same_move": 0,
                "last_action_sig": "",
            },
        }
        db.update_session_physical_state(self.session_id, session["physical_state"])

        # Case 1: LLM hallucinates partner_climaxed=True in physical_updates at 16% meter
        outcome_low = {
            "dialogue_partner": "Mia Yamada",
            "physical_updates": {
                "partner_climaxed": True,
                "player_climaxed": False,
            },
            "outcome_narrative": "Artemiusz traces slow circles with his tongue as Mia gasps softly.",
            "next_narrative": "She grips his shoulders.",
        }
        actions_low = [{"label": "Focus your tongue on Mia Yamada's most sensitive spot with a steady rhythm"}]
        _reduce_physical_state_and_memories(
            session_id=self.session_id,
            session=session,
            outcome=outcome_low,
            party=[(self.player_char, "1")],
            scen_key="nsfw_furry_high_school_drama",
            actions=actions_low,
        )
        phys_1 = db.get_session_physical_state(self.session_id)
        self.assertFalse(phys_1["climax_state"]["partner_climaxed"])
        self.assertNotIn("partner reached climax", phys_1["intimate_contact"].lower())
        self.assertIn("oral give", phys_1["intimate_contact"].lower())

        # Case 2: Partner meter is at 90% and she genuinely climaxes during oral_give
        phys_1["excitement"]["actors"]["Mia Yamada"]["meter"] = 90
        session["physical_state"] = phys_1
        db.update_session_physical_state(self.session_id, phys_1)
        outcome_peak = {
            "dialogue_partner": "Mia Yamada",
            "physical_updates": {
                "actors": {
                    "Artemiusz": {"posture": "Resting side by side"},
                    "Mia Yamada": {"posture": "Sleeping"},
                }
            },
            "outcome_narrative": "Mia cries out as she reaches a shattering climax against Artemiusz's tongue.",
            "next_narrative": "She trembles from the aftershocks.",
        }
        _reduce_physical_state_and_memories(
            session_id=self.session_id,
            session=session,
            outcome=outcome_peak,
            party=[(self.player_char, "1")],
            scen_key="nsfw_furry_high_school_drama",
            actions=actions_low,
        )
        phys_2 = db.get_session_physical_state(self.session_id)
        self.assertTrue(phys_2["climax_state"]["partner_climaxed"])
        self.assertIn("oral give - partner reached climax, ongoing for player", phys_2["intimate_contact"].lower())
        self.assertIn("kneeling between mia yamada's thighs", phys_2["actors"]["Artemiusz"]["posture"].lower())

        # Case 3: Verify party recruitment & romantic confession choices are NOT injected mid-intimacy
        db.upsert_contact(self.session_id, "mia_yamada", "Mia Yamada", delta_score=85, track="platonic", gender="Female")
        valid_oral_choices = [
            {"label": "Flatten your tongue and trace slow circles over Mia Yamada's sensitive spot", "stat": "DEX", "requirement": 6},
            {"label": "Hold Mia Yamada's hips steady and deepen your oral rhythm", "stat": "END", "requirement": 6},
            {"label": "Murmur warm praise against Mia Yamada's inner thigh", "stat": "CHA", "requirement": 6},
            {"label": "Ease back gently and pause to catch your breath with Mia Yamada", "stat": "NONE", "requirement": 0},
        ]
        cleaned = clean_choices_impl(
            None,
            choices=valid_oral_choices,
            scenario="nsfw_furry_high_school_drama",
            location="Music Room",
            char=self.player_char,
            dialogue_partner="Mia Yamada",
            session_id=self.session_id,
        )
        cleaned_labels = [c["label"].lower() for c in cleaned]
        self.assertFalse(any("join your party" in l for l in cleaned_labels))
        self.assertFalse(any("confess your feelings" in l for l in cleaned_labels))

    def test_blueprint_classification_and_inventory_offering_guardrails(self):
        """
        Verify:
        1. Choices using 'slide your fingers', 'give Mia a passionate kiss', 'share a breathless kiss'
           are NOT pruned by Step 6.5 unowned inventory offering filter in clean_choices_impl.
        2. Every active blueprint choice generated by build_intimate_choice_blueprints across
           oral_give, oral_receive, oral_mutual, manual_give, manual_receive, penetrative, and anal_give
           classifies to its exact intended act_type and directionality even when using the NPC's name
           and with empty narrative_str.
        3. Stale prior-turn intimate_contact ('oral give') does not pollute act transitions to penetrative/manual
           or falsely award genital delta on non-genital caresses.
        4. Non-penetrative exit blueprint ('Ease back gently, pause to catch your breath...') disengages cleanly.
        5. Partner post-climax meter resets to 35% warm baseline on the subsequent stimulated turn instead of
           re-triggering climax every turn.
        """
        from mechanics.social.intimate_excitement import build_intimate_choice_blueprints
        from mechanics.social.physical_state import detect_intimate_disengagement

        # 1. Step 6.5 Offering Filter Exemption for Body Parts & Intimate Gestures
        db.update_session_physical_state(self.session_id, {
            "intimate_contact": "Intimate encounter with Mia Yamada (manual give)",
            "climax_state": {"partner_climaxed": False, "player_climaxed": False},
            "excitement": {
                "active": True,
                "last_act": "manual_give",
                "actors": {
                    "Artemiusz": {"meter": 20, "status": "Arousal Building"},
                    "Mia Yamada": {"meter": 40, "status": "Arousal Building"},
                },
            },
        })
        offering_like_intimate_choices = [
            {"label": "Slide your fingers inside Mia Yamada and curl them with a steady pace", "stat": "AGI", "requirement": 6},
            {"label": "Give Mia Yamada a passionate kiss while caressing her neck", "stat": "CHA", "requirement": 5},
            {"label": "Share a breathless embrace with Mia Yamada and tease her thighs", "stat": "PER", "requirement": 5},
            {"label": "Ease back gently, pause to catch your breath, and hold Mia Yamada close", "stat": "NONE", "requirement": 0},
        ]
        cleaned = clean_choices_impl(
            None,
            choices=offering_like_intimate_choices,
            scenario="nsfw_furry_high_school_drama",
            location="Music Room",
            char=self.player_char,
            dialogue_partner="Mia Yamada",
            session_id=self.session_id,
        )
        cleaned_lbls = [c["label"] for c in cleaned]
        self.assertIn("Slide your fingers inside Mia Yamada and curl them with a steady pace", cleaned_lbls)
        self.assertIn("Give Mia Yamada a passionate kiss while caressing her neck", cleaned_lbls)
        self.assertIn("Share a breathless embrace with Mia Yamada and tease her thighs", cleaned_lbls)

        # 2. Blueprint Choice Classification Accuracy (with Partner Full Name & Empty Narrative)
        for act_key, expected_p_stim, expected_n_stim in [
            ("oral_give", False, True),
            ("oral_receive", True, False),
            ("oral_mutual", True, True),
            ("manual_give", False, True),
            ("manual_receive", True, False),
            ("penetrative", True, True),
            ("anal_give", True, True),
        ]:
            bp = build_intimate_choice_blueprints(
                partner_name="Mia Yamada",
                last_act=act_key,
                player_meter=75,
                partner_meter=75,
                sensitive_spots=["Tail base & spine line (Physical)"],
            )
            ic_tag = f"Intimate encounter with Mia Yamada ({act_key.replace('_', ' ')})"
            # Slots 0, 1, and 2 (at high meter >= 70) are all active stimulation choices for that act
            for slot_idx in (0, 1, 2):
                choice_lbl = bp["choices"][slot_idx]["label"]
                cls_res = classify_intimate_act(
                    action_str=choice_lbl,
                    intimate_contact_str=ic_tag,
                    player_name="Artemiusz",
                    partner_name="Mia Yamada",
                    partner_contact=self.partner_contact,
                    narrative_str="",
                )
                self.assertEqual(
                    cls_res["act_type"],
                    act_key,
                    f"Blueprint slot {slot_idx} for {act_key} ('{choice_lbl}') misclassified as {cls_res['act_type']}",
                )
                self.assertEqual(cls_res["player_stimulated"], expected_p_stim)
                self.assertEqual(cls_res["partner_stimulated"], expected_n_stim)

            # Slot 3 (exit choice) must classify as 'none' (disengagement)
            exit_lbl = bp["choices"][3]["label"]
            exit_cls = classify_intimate_act(
                action_str=exit_lbl,
                intimate_contact_str=ic_tag,
                player_name="Artemiusz",
                partner_name="Mia Yamada",
                partner_contact=self.partner_contact,
                narrative_str="You pause to catch your breath.",
            )
            self.assertEqual(exit_cls["act_type"], "none", f"Exit choice '{exit_lbl}' failed to disengage")

        # 3. Prior-turn intimate_contact ('oral give') must NOT hijack transition to penetrative or non-genital caress
        trans_pen = classify_intimate_act(
            action_str="Rise from your knees and thrust deeply inside Mia Yamada",
            intimate_contact_str="Intimate encounter with Mia Yamada (oral give)",
            player_name="Artemiusz",
            partner_name="Mia Yamada",
            narrative_str="After licking her clit, you rise and sink inside her warm folds.",
        )
        self.assertEqual(trans_pen["act_type"], "penetrative")
        self.assertTrue(trans_pen["player_stimulated"])
        self.assertTrue(trans_pen["partner_stimulated"])

        non_gen_in_oral = classify_intimate_act(
            action_str="Gently stroke Mia Yamada's hair and kiss her forehead",
            intimate_contact_str="Intimate encounter with Mia Yamada (oral give)",
            player_name="Artemiusz",
            partner_name="Mia Yamada",
            narrative_str="You brush a lock of hair from her forehead.",
        )
        self.assertEqual(non_gen_in_oral["act_type"], "foreplay_nongenital")
        self.assertFalse(non_gen_in_oral["partner_stimulated"])

        # 4. Non-penetrative exit blueprint triggers detect_intimate_disengagement in physical_state
        self.assertTrue(
            detect_intimate_disengagement([
                {"label": "Ease back gently, pause to catch your breath, and hold Mia Yamada close"}
            ])
        )

        # 5. Partner post-climax meter resets to 35% baseline on subsequent stimulated turn
        phys_multi = {
            "intimate_contact": "Intimate encounter with Kana (oral give)",
            "climax_state": {"partner_climaxed": False, "player_climaxed": False},
            "excitement": {
                "active": True,
                "last_act": "oral_give",
                "actors": {
                    "Artemiusz": {"meter": 30, "max": 100, "delta": 0, "endurance": 6, "climaxes_count": 0, "status": ""},
                    "Kana": {"meter": 92, "max": 100, "delta": 0, "endurance": 6, "climaxes_count": 0, "status": ""},
                },
            },
        }
        # Turn N: Kana reaches 100% climax
        step_n = compute_excitement_step(
            physical_state=phys_multi,
            action_str="Focus your tongue relentlessly on Kana's core to push her over the edge",
            player_char=self.player_char,
            partner_contact=self.partner_contact,
            session={"current_day": 1, "current_minute": 500},
        )
        self.assertEqual(step_n["partner_meter"], 100)
        self.assertTrue(step_n["partner_climaxed"])
        self.assertEqual(phys_multi["excitement"]["actors"]["Kana"]["climaxes_count"], 1)

        # Turn N+1: Player continues oral stimulation through her aftershocks -> resets to 35% + delta (not 100%!)
        step_n1 = compute_excitement_step(
            physical_state=phys_multi,
            action_str="Hold Kana steady by the hips and lick tenderly through her trembling aftershocks",
            player_char=self.player_char,
            partner_contact=self.partner_contact,
            session={"current_day": 1, "current_minute": 502},
        )
        self.assertGreater(step_n1["partner_meter"], 35)
        self.assertLess(step_n1["partner_meter"], 75)
        self.assertEqual(phys_multi["excitement"]["actors"]["Kana"]["climaxes_count"], 1)

    def test_post_premature_finish_resolution_intent_guards_and_quest_climax_isolation(self):
        """
        Verify:
        1. Satisfying an unsatisfied partner via manual_give/oral_give after a premature finish
           clears premature_finish=False, keeps male status as 'Climaxed (Spent)', and transitions
           _reduce_physical_state_and_memories into 'Cuddling / aftercare' with both climax flags True.
        2. Contradictory penetrative or 'through her tremors' choices are pruned during premature_finish.
        3. Refractory recovery and new-encounter start reset stale 100% meters so actors do not
           instantly climax on Turn 1 of a subsequent encounter.
        4. Intimate choices starting with 'Enter [Partner] slowly...', 'Move into a deeper angle...',
           or 'Rest beside [Partner] in tender aftercare' are not misclassified and stripped as
           MOVEMENT or REST_SLEEP in dialogue mode.
        5. Erotic choices containing 'climax' do not falsely auto-complete an active Story Quest.
        """
        from game_engine.state.reducers import _reduce_physical_state_and_memories, _reduce_quests_and_waypoints
        from mechanics.narrative.intent import classify_action_intent, IntentCategory

        # 1 & 2. Premature finish contradiction pruning & resolution to aftercare
        premature_phys = {
            "intimate_contact": "Intimate encounter with Mia Yamada (player reached climax spent, partner unsatisfied)",
            "climax_state": {"partner_climaxed": False, "player_climaxed": True},
            "actors": {
                "Artemiusz": {"posture": "Breathing heavily beside Mia Yamada"},
                "Mia Yamada": {"posture": "Flushed and gasping on the bed"},
            },
            "excitement": {
                "active": True,
                "last_act": "penetrative",
                "premature_finish": True,
                "partner_demanded": True,
                "refractory_until_minute": (1 * 1440) + 540,
                "cooldown_notified": False,
                "actors": {
                    "Artemiusz": {"meter": 100, "max": 100, "delta": 0, "endurance": 6, "climaxes_count": 1, "status": "💥 Climaxed (Spent)"},
                    "Mia Yamada": {"meter": 90, "max": 100, "delta": 0, "endurance": 6, "climaxes_count": 0, "status": "On the Brink 🔥"},
                },
            },
        }
        db.update_session_physical_state(self.session_id, premature_phys)

        mixed_premature_choices = [
            {"label": "Maintain a steady, deep rhythm and thrust deeper inside Mia Yamada", "stat": "END", "requirement": 6},
            {"label": "Hold Mia Yamada through her tremors", "stat": "CHA", "requirement": 6},
            {"label": "Use your fingers to stroke and please Mia Yamada toward her climax", "stat": "AGI", "requirement": 6},
            {"label": "Slow your rhythm, gently withdraw, and hold Mia Yamada close", "stat": "NONE", "requirement": 0},
        ]
        cleaned_prem = clean_choices_impl(
            None,
            choices=mixed_premature_choices,
            scenario="nsfw_furry_high_school_drama",
            location="Bedroom",
            char=self.player_char,
            dialogue_partner="Mia Yamada",
            session_id=self.session_id,
        )
        prem_lbls = [c["label"] for c in cleaned_prem]
        self.assertFalse(any("thrust deeper" in l.lower() for l in prem_lbls))
        self.assertFalse(any("through her tremors" in l.lower() for l in prem_lbls))
        self.assertIn("Use your fingers to stroke and please Mia Yamada toward her climax", prem_lbls)

        # Now resolve premature finish by bringing Mia Yamada to climax via manual_give
        session = db.get_session(self.session_id)
        session["current_day"] = 1
        session["current_minute"] = 505
        session["dialogue_partner"] = "Mia Yamada"
        session["dialogue_partners"] = ["Mia Yamada"]
        session["physical_state"] = premature_phys
        outcome_resolve = {
            "dialogue_partner": "Mia Yamada",
            "outcome_narrative": "Your fingers curl with steady devotion until Mia Yamada arches her back in a shuddering climax.",
            "next_narrative": "She melts against your chest with a satisfied sigh.",
        }
        _reduce_physical_state_and_memories(
            session_id=self.session_id,
            session=session,
            outcome=outcome_resolve,
            party=[(self.player_char, "1")],
            scen_key="nsfw_furry_high_school_drama",
            actions=[{"label": "Use your fingers to stroke and please Mia Yamada toward her climax"}],
        )
        phys_after = db.get_session_physical_state(self.session_id)
        self.assertTrue(phys_after["climax_state"]["partner_climaxed"])
        self.assertTrue(phys_after["climax_state"]["player_climaxed"])
        self.assertFalse(phys_after["excitement"]["premature_finish"])
        self.assertFalse(phys_after["excitement"]["active"])
        self.assertIn("cuddling / aftercare with mia yamada", phys_after["intimate_contact"].lower())
        self.assertEqual(
            phys_after["excitement"]["actors"]["Artemiusz"]["status"],
            "💥 Climaxed (Spent)",
        )

        # 3. Refractory clock recovery resets finished encounter meters to 0%
        session_recovered = {"current_day": 1, "current_minute": 550}
        recovered, toast = check_and_resolve_refractory_clock(session_recovered, phys_after)
        self.assertTrue(recovered)
        self.assertIsNotNone(toast)
        self.assertEqual(phys_after["excitement"]["actors"]["Artemiusz"]["meter"], 0)
        self.assertEqual(phys_after["excitement"]["actors"]["Mia Yamada"]["meter"], 0)
        self.assertFalse(phys_after["climax_state"]["partner_climaxed"])
        self.assertFalse(phys_after["climax_state"]["player_climaxed"])

        # 4. Intent guards preserve in-scene intimate 'Enter...', 'Move into...', 'Rest beside...' choices
        for lbl in (
            "Enter Mia Yamada slowly and establish a gentle rhythm",
            "Move into a deeper angle with Mia Yamada and hold her hips",
            "Rest beside Mia Yamada in tender aftercare and stroke her hair",
        ):
            parsed = classify_action_intent(lbl)
            self.assertNotIn(
                parsed.category,
                (IntentCategory.MOVEMENT, IntentCategory.REST_SLEEP),
                f"Intimate choice '{lbl}' was misclassified as {parsed.category}",
            )

        # 5. Story Quest Climax isolation from erotic 'climax' choices
        from unittest.mock import patch
        mock_sq = {
            "quest_id": "SQ-TEST-1",
            "title": "The Missing Archive",
            "is_story_quest": True,
            "sub_objectives": [{"id": 1, "text": "Search the library", "completed": True}],
        }
        with patch("db.get_active_story_quest", return_value=mock_sq), patch("game_engine.apply_quest_update") as mock_apply_sq:
            _reduce_quests_and_waypoints(
                session_id=self.session_id,
                session=session,
                party_uids=[1],
                outcome={},
                actions=[{"label": "Quicken your fingers' rhythm to push Mia Yamada over the edge into climax", "stat": "AGI", "requirement": 6, "check": {"succeeded": True}}],
                items_gained_by_user={},
            )
            mock_apply_sq.assert_not_called()

    def test_round5_cross_module_prompts_fallback_and_quest_isolation(self):
        """
        Verify Round 5 cross-module fixes:
        1. `build_dialogue_and_npc_prompts` uses act-aware continuity during `oral_give` (no hardcoded
           'Intercourse continues actively inside' or casual hangout 'playing a light game' choices).
        2. `clean_choices_impl` sets `is_fallback=False` when padding/repairing non-empty LLM choices
           (preventing false UI fallback banners), and returns act-aware `bp['choices']` with
           `is_fallback=True` when raw `choices=[]` during an active intimate scene.
        3. `clean_choices_impl` strips 'Redress / Get dressed' and 'Observe your surroundings' during
           active intimacy.
        4. `tag_and_enrich_quest_choices` never tags erotic 'climax' choices as `⚡ [Story Climax]`.
        5. `build_scene_escalation_and_consequence_directives` ignores intimate prose for ticking clock.
        6. `_is_social_or_non_combat_action` treats physical intimate actions (`END`/`AGI`/`STR`) as non-combat.
        """
        from game_engine.turn.dialogue import _build_dialogue_prompt_block
        from game_engine.turn_context import TurnContext
        from game_engine.choices_cleaner import clean_choices_impl
        from mechanics.world.waypoints.choices import tag_and_enrich_quest_choices
        from game_engine.npcs.dialogue_tracking import build_scene_escalation_and_consequence_directives
        from game_engine.turn.prompts import _is_social_or_non_combat_action

        oral_phys = {
            "intimate_contact": "Intimate encounter with Mia Yamada (oral give)",
            "climax_state": {"partner_climaxed": True, "player_climaxed": False},
            "actors": {
                "Artemiusz": {"clothing": {"top": "none", "bottom": "none"}, "posture": "Kneeling between Mia Yamada's thighs"},
                "Mia Yamada": {"clothing": {"top": "none", "bottom": "none"}, "posture": "Sitting on the edge of the desk"},
            },
            "excitement": {
                "active": True,
                "last_act": "oral_give",
                "premature_finish": False,
                "partner_demanded": True,
                "actors": {
                    "Artemiusz": {"meter": 35, "status": "Arousal Building"},
                    "Mia Yamada": {"meter": 25, "status": "✨ Climaxed (1x) — Sensitive"},
                },
            },
        }
        db.update_session_physical_state(self.session_id, oral_phys)
        session = db.get_session(self.session_id)
        session["scenario"] = "nsfw_furry_high_school_drama"
        session["dialogue_partner"] = "Mia Yamada"
        session["dialogue_partners"] = ["Mia Yamada"]
        session["physical_state"] = oral_phys
        session["current_npcs"] = [{"name": "Mia Yamada", "role": "Peer"}]

        # 1. Dialogue prompt is act-aware and replaces casual hangout choice archetypes
        ctx = TurnContext(session["id"], session, [(self.player_char, [])])
        dlg_prompt = _build_dialogue_prompt_block(
            session=session,
            ctx=ctx,
            new_partners=["Mia Yamada"],
            party=[(self.player_char, [])],
            actions=[{"label": "Hold Mia Yamada steady by the hips and lick tenderly"}],
        )
        self.assertIn("oral_give", dlg_prompt)
        self.assertIn("HYBRID CHOICE BLUEPRINTS", dlg_prompt)
        self.assertNotIn("Intercourse continues actively inside Mia Yamada", dlg_prompt)
        self.assertNotIn("playing a light game", dlg_prompt)

        # 2 & 3. Non-empty LLM choices repaired with blueprints have is_fallback=False, and redress/observe are stripped
        llm_choices_with_leaks = [
            {"label": "Maintain a steady, deep rhythm and drive deeper", "stat": "END", "requirement": 6},
            {"label": "Redress / Get dressed (Artemiusz)", "stat": "FREE", "requirement": 0},
            {"label": "Observe your surroundings and inspect those present", "stat": "FREE", "requirement": 0},
        ]
        repaired = clean_choices_impl(
            None,
            choices=llm_choices_with_leaks,
            scenario="nsfw_furry_high_school_drama",
            location="Music Room",
            char=self.player_char,
            dialogue_partner="Mia Yamada",
            session_id=self.session_id,
        )
        rep_labels = [c["label"].lower() for c in repaired]
        self.assertFalse(any(c.get("is_fallback") for c in repaired))
        self.assertFalse(any("redress" in l or "observe your surroundings" in l for l in rep_labels))
        self.assertTrue(any("tongue" in l or "oral" in l for l in rep_labels))

        # Empty choices=[] during active intimate scene returns oral_give blueprints with is_fallback=True
        empty_fallback = clean_choices_impl(
            None,
            choices=[],
            scenario="nsfw_furry_high_school_drama",
            location="Music Room",
            char=self.player_char,
            dialogue_partner="Mia Yamada",
            session_id=self.session_id,
        )
        self.assertTrue(any(c.get("is_fallback") for c in empty_fallback))
        self.assertTrue(any("tongue" in c["label"].lower() or "oral" in c["label"].lower() for c in empty_fallback))
        self.assertFalse(any("perspective on the situation" in c["label"].lower() for c in empty_fallback))

        # 4. tag_and_enrich_quest_choices skips active intimate scenes
        raw_erotic = [{"label": "Quicken your fingers' rhythm to push Mia Yamada over the edge into climax", "stat": "AGI", "requirement": 7}]
        tagged = tag_and_enrich_quest_choices(
            raw_erotic,
            self.session_id,
            "Music Room",
            scen_key="nsfw_furry_high_school_drama",
            char=self.player_char,
            dialogue_partner=["Mia Yamada"],
        )
        self.assertFalse(tagged[0].get("is_climax_action", False))
        self.assertNotIn("[Story Climax]", tagged[0]["label"])

        # 5. Ticking clock directive does not fire during intimate scenes
        session["scenario"] = "nsfw_fantasy"
        session["history"] = [
            "Heart pounding, seconds away from the edge of climax, she gasps.",
            "Locked in an embrace, pounding rhythm continues until they collapse onto the bed in orgasm.",
        ]
        esc_dir = build_scene_escalation_and_consequence_directives(
            session=session,
            party=[(self.player_char, [])],
            actions=[],
            story_quest=None,
        )
        self.assertNotIn("TICKING CLOCK DIRECTIVE", esc_dir)

        # 6. Physical intimate actions are treated as social/non-combat in combat-capable scenarios
        intimate_act = {"label": "Maintain a steady, deep rhythm and lock eyes with Mia Yamada", "stat": "END", "action_category": "general_action"}
        self.assertTrue(_is_social_or_non_combat_action(intimate_act, session))

    def test_round6_lifecycle_companion_disengagement_and_post_turn_reconciliation(self):
        """
        Verify Round 6 lifecycle & state-continuity fixes:
        1. `detect_intimate_disengagement` does NOT false-positive on active continuation phrases
           ('Don't stop', 'Pull back her hair', 'Pull out and finish'), while accurately matching
           aftercare/exit choices ('Ease into tender aftercare', 'Catch your breath').
        2. `build_physical_prompt_block` separates human player from recruited party companions
           (`session['party_npcs']`), updates act blueprints immediately from current-turn `actions`,
           and suppresses active erotic prompt mode when disengaging.
        3. `compute_excitement_step` preserves an active genital `last_act` across a mid-scene
           non-genital kiss/whisper turn.
        4. `_build_dialogue_prompt_block` suppresses bounty/quest interrogation modes, recruitment
           prompts, and stall directives during active intimacy.
        5. `_reduce_physical_state_and_memories` guards failed initiation checks, reconciles
           `outcome['choices']` against post-turn `updated_phys` (e.g., pruning penetrative choices
           when premature finish occurs on the current turn), and injects 'Redress / Get dressed'
           when transitioning into aftercare while undressed.
        """
        from mechanics.social.physical_state import (
            detect_intimate_disengagement,
            build_physical_prompt_block,
        )
        from mechanics.social.intimate_excitement import infer_last_act_from_state
        from game_engine.turn.dialogue import _build_dialogue_prompt_block
        from game_engine.turn_context import TurnContext
        from game_engine.state.reducers import _reduce_physical_state_and_memories
        from game_engine.turn.narration import _build_frozen_state_text

        # 1. Disengagement false-positive vs true-positive checks
        for active_lbl in (
            "Don't stop and maintain a steady rhythm with Kana",
            "Pull back Kana's hair and kiss her neck while moving deeper",
            "Pull out and finish across her stomach",
        ):
            self.assertFalse(
                detect_intimate_disengagement([{"label": active_lbl}]),
                f"Active intimate choice '{active_lbl}' falsely triggered disengagement",
            )
        for exit_lbl in (
            "Ease into tender aftercare and hold Kana close",
            "Ease back gently, pause to catch your breath, and rest together",
        ):
            self.assertTrue(
                detect_intimate_disengagement([{"label": exit_lbl}]),
                f"Exit choice '{exit_lbl}' failed to trigger disengagement",
            )

        # 2. Recruited party companion (`party_npcs`) meter/posture separation & current-turn act transition
        comp_phys = {
            "intimate_contact": "Intimate encounter with Kana (foreplay)",
            "climax_state": {"partner_climaxed": False, "player_climaxed": False},
            "actors": {
                "Artemiusz": {"posture": "Kneeling between Kana's thighs", "clothing": {"top": "removed", "bottom": "removed"}},
                "Kana": {"posture": "Sitting on the edge of the bed", "clothing": {"top": "removed", "bottom": "removed"}},
            },
            "excitement": {
                "active": True,
                "last_act": "foreplay_nongenital",
                "actors": {
                    "Artemiusz": {"meter": 25, "status": "Warming Up"},
                    "Kana": {"meter": 82, "status": "On the Brink 🔥"},
                },
            },
        }
        db.update_session_physical_state(self.session_id, comp_phys)
        comp_session = {
            "id": self.session_id,
            "scenario": "nsfw_furry_high_school_drama",
            "dialogue_partner": "Kana",
            "party_npcs": [{"name": "Kana", "role": "Companion"}],
        }
        # Current-turn action transitions from foreplay_nongenital -> oral_give
        oral_turn_actions = [{"label": "Kneel between Kana's thighs and lick her core with a steady rhythm"}]
        prompt_comp = build_physical_prompt_block(
            session=comp_session,
            party=[(self.player_char, [])],
            is_nsfw=True,
            actions=oral_turn_actions,
        )
        # Because Kana's meter (82%) is preserved separately from Artemiusz (25%) AND current action is oral_give,
        # the high-meter oral_give climax blueprint must be present!
        self.assertIn("push her over the edge", prompt_comp.lower())

        # When disengaging on the current turn, active erotic prompt block is suppressed
        prompt_disengage = build_physical_prompt_block(
            session=comp_session,
            party=[(self.player_char, [])],
            is_nsfw=True,
            actions=[{"label": "Ease into tender aftercare and hold Kana close"}],
        )
        self.assertNotIn("HYBRID CHOICE BLUEPRINTS", prompt_disengage)

        # 3. compute_excitement_step preserves active genital last_act across a mid-scene kiss/whisper turn
        pen_phys = {
            "intimate_contact": "Intimate encounter with Kana (intercourse)",
            "climax_state": {"partner_climaxed": False, "player_climaxed": False},
            "excitement": {
                "active": True,
                "last_act": "penetrative",
                "actors": {
                    "Artemiusz": {"meter": 45, "max": 100, "delta": 0, "endurance": 6, "climaxes_count": 0, "status": ""},
                    "Kana": {"meter": 50, "max": 100, "delta": 0, "endurance": 6, "climaxes_count": 0, "status": ""},
                },
            },
        }
        compute_excitement_step(
            physical_state=pen_phys,
            action_str="Kiss Kana softly on the lips and whisper warm praise",
            player_char=self.player_char,
            partner_contact=self.partner_contact,
            session={"current_day": 1, "current_minute": 510},
            narrative_str="You brush her cheek and kiss her lips tenderly.",
        )
        self.assertEqual(pen_phys["excitement"]["last_act"], "penetrative")
        self.assertEqual(infer_last_act_from_state(pen_phys), "penetrative")

        # 4. _build_dialogue_prompt_block suppresses bounty/quest interrogation & stall notes during intimacy
        db.update_session_physical_state(self.session_id, pen_phys)
        bounty_session = db.get_session(self.session_id)
        bounty_session["scenario"] = "nsfw_furry_high_school_drama"
        bounty_session["dialogue_partner"] = "Kana"
        bounty_session["dialogue_partners"] = ["Kana"]
        bounty_session["physical_state"] = pen_phys
        bounty_session["history"] = [
            {"type": "action", "label": "Ask Kana about the ruin", "narrative": "She answers."},
            {"type": "action", "label": "Inquire further about the ruin", "narrative": "She explains."},
            {"type": "action", "label": "Question Kana about the map", "narrative": "She nods."},
            {"type": "action", "label": "Discuss the plan with Kana", "narrative": "She agrees."},
        ]
        ctx_b = TurnContext(bounty_session["id"], bounty_session, [(self.player_char, [])])
        ctx_b._active_waypoints = [{"target_npc": "Kana", "title": "Investigate the Relic", "objective": "Question Kana"}]
        dlg_block = _build_dialogue_prompt_block(

            session=bounty_session,
            ctx=ctx_b,
            new_partners=["Kana"],
            party=[(self.player_char, [])],
            actions=[{"label": "Maintain a steady rhythm with Kana"}],
        )
        self.assertNotIn("QUEST INVESTIGATION & NEGOTIATION", dlg_block)
        self.assertNotIn("Invite Kana to join your party", dlg_block)
        self.assertNotIn("STALL", dlg_block.upper())

        # 5A. Failed initiation check when not in an erotic encounter does NOT start intimate_contact
        idle_phys = {
            "intimate_contact": "none",
            "climax_state": {"partner_climaxed": False, "player_climaxed": False},
            "actors": {
                "Artemiusz": {"posture": "Standing", "clothing": {"top": "Tunic", "bottom": "Trousers"}},
                "Kana": {"posture": "Standing", "clothing": {"top": "Blouse", "bottom": "Skirt"}},
            },
        }
        db.update_session_physical_state(self.session_id, idle_phys)
        bounty_session["physical_state"] = idle_phys
        failed_init_outcome = {
            "dialogue_partner": "Kana",
            "outcome_narrative": "Kana steps back with a flustered shake of her head.",
            "next_narrative": "She keeps a polite distance.",
        }
        _reduce_physical_state_and_memories(
            session_id=self.session_id,
            session=bounty_session,
            outcome=failed_init_outcome,
            party=[(self.player_char, "1")],
            scen_key="nsfw_furry_high_school_drama",
            actions=[{"label": "Kiss Kana passionately on the lips", "success": False, "check": {"succeeded": False}}],
        )
        phys_after_fail = db.get_session_physical_state(self.session_id)
        self.assertEqual(phys_after_fail["intimate_contact"], "none")

        # 5B. Post-turn choice reconciliation in _reduce_physical_state_and_memories:
        # When player reaches premature finish on this turn, pre-reducer penetrative choices in outcome['choices']
        # are automatically replaced with post-turn premature_finish finger/tongue/aftercare choices!
        near_premature_phys = {
            "intimate_contact": "Intimate encounter with Kana (intercourse)",
            "climax_state": {"partner_climaxed": False, "player_climaxed": False},
            "actors": {
                "Artemiusz": {"posture": "Moving above Kana", "clothing": {"top": "removed", "bottom": "removed"}},
                "Kana": {"posture": "Lying on the bed", "clothing": {"top": "removed", "bottom": "removed"}},
            },
            "excitement": {
                "active": True,
                "last_act": "penetrative",
                "actors": {
                    "Artemiusz": {"meter": 92, "max": 100, "delta": 0, "endurance": 5, "climaxes_count": 0, "status": ""},
                    "Kana": {"meter": 40, "max": 100, "delta": 0, "endurance": 7, "climaxes_count": 0, "status": ""},
                },
            },
        }
        db.update_session_physical_state(self.session_id, near_premature_phys)
        bounty_session["physical_state"] = near_premature_phys
        outcome_prem = {
            "dialogue_partner": "Kana",
            "outcome_narrative": "Artemiusz reaches his own climax early, spilling deep inside while Kana is still building.",
            "next_narrative": "Kana looks up with flushed cheeks, still aching for release.",
            "choices": [
                {"label": "Maintain a steady, deep rhythm and thrust deeper inside Kana", "stat": "END", "requirement": 6},
                {"label": "Shift position to drive deeper into Kana", "stat": "STR", "requirement": 7},
            ],
        }
        _reduce_physical_state_and_memories(
            session_id=self.session_id,
            session=bounty_session,
            outcome=outcome_prem,
            party=[(self.player_char, "1")],
            scen_key="nsfw_furry_high_school_drama",
            actions=[{"label": "Quicken your pace inside Kana", "success": True}],
        )
        reconciled_lbls = [c["label"].lower() for c in outcome_prem["choices"]]
        self.assertFalse(any("thrust deeper" in l or "drive deeper" in l for l in reconciled_lbls))
        self.assertTrue(any(k in l for l in reconciled_lbls for k in ("fingers", "tongue", "hands")))


        # 5C. Mutual climax transition to aftercare prunes stale active choices and injects Redress choice
        near_mutual_phys = {
            "intimate_contact": "Intimate encounter with Kana (intercourse)",
            "climax_state": {"partner_climaxed": True, "player_climaxed": False},
            "actors": {
                "Artemiusz": {"posture": "Moving above Kana", "clothing": {"top": "removed", "bottom": "removed"}},
                "Kana": {"posture": "Lying on the bed", "clothing": {"top": "removed", "bottom": "removed"}},
            },
            "excitement": {
                "active": True,
                "last_act": "penetrative",
                "actors": {
                    "Artemiusz": {"meter": 95, "max": 100, "delta": 0, "endurance": 5, "climaxes_count": 0, "status": ""},
                    "Kana": {"meter": 100, "max": 100, "delta": 0, "endurance": 7, "climaxes_count": 1, "status": ""},
                },
            },
        }
        db.update_session_physical_state(self.session_id, near_mutual_phys)
        bounty_session["physical_state"] = near_mutual_phys
        outcome_mutual = {
            "dialogue_partner": "Kana",
            "outcome_narrative": "Artemiusz reaches his own climax inside Kana as they rest together.",
            "next_narrative": "They breathe softly in warm aftercare.",
            "choices": [
                {"label": "Drive deeper to push over the edge", "stat": "STR", "requirement": 7},
                {"label": "Hold Kana close and whisper tenderly", "stat": "CHA", "requirement": 5},
            ],
        }
        _reduce_physical_state_and_memories(
            session_id=self.session_id,
            session=bounty_session,
            outcome=outcome_mutual,
            party=[(self.player_char, "1")],
            scen_key="nsfw_furry_high_school_drama",
            actions=[{"label": "Push over the edge into release with Kana", "success": True}],
        )
        aftercare_lbls = [c["label"].lower() for c in outcome_mutual["choices"]]
        self.assertFalse(any("drive deeper" in l for l in aftercare_lbls))
        self.assertTrue(any("redress / get dressed (artemiusz)" in l for l in aftercare_lbls))

        # 6. Narration retry snapshot frozen text includes intimate stage & meters
        frozen_txt = _build_frozen_state_text({
            "applied": {
                "_physical_state": {"intimate_contact": "Intimate encounter with Kana (oral give)"},
                "intimate_update": {
                    "active": True,
                    "act_type": "oral_give",
                    "player_name": "Artemiusz",
                    "player_meter": 30,
                    "partner_name": "Kana",
                    "partner_meter": 68,
                    "partner_climaxed": False,
                    "player_climaxed": False,
                    "premature_finish": False,
                },
            }
        })
        self.assertIn("Intimate Contact Stage: Intimate encounter with Kana (oral give)", frozen_txt)
        self.assertIn("Act=oral_give", frozen_txt)

    def test_round7_audit_fixes(self):
        """
        Verify Round 7 audit fixes:
        1. Benign non-genital exploration actions ('Touch the ancient rune with your hand') do not trigger
           intimate mode when intimate_contact is 'none'.
        2. Refractory clock recovery runs BEFORE compute_excitement_step and resets player_climaxed + spent
           meter even when excitement['active'] was True from a premature finish.
        3. 3rd-party room actors in physical_state['actors'] / excitement['actors'] do not overwrite
           player_posture or player_meter in clean_choices_impl or build_physical_prompt_block, and
           switching intimate partners prunes stale actors from excitement['actors'].
        4. Explicit aftercare choices and premature-finish apology transitions resolve to 'Cuddling / aftercare'
           and populate aftercare blueprints + Redress choice.
        5. Adapted dynamic continuation choices without explicit anatomical nouns preserve ongoing genital act
           classification during active encounters.
        6. Free exit choices in clean_choices_impl do not duplicate when an intimate exit choice is present,
           and recovered partners from intimate_contact are not pruned as absent contacts.
        7. Turn 1 explicit genital initiation injects HYBRID CHOICE BLUEPRINTS into build_physical_prompt_block
           and _build_dialogue_prompt_block.
        8. Hybrid Blueprint phrases match milestone keyword lists in game_engine/keywords.py, and
           relationship_updates milestone_event pre-infers intimate_contact before compute_excitement_step.
        """
        from game_engine.state.reducers import _reduce_physical_state_and_memories
        from game_engine.choices_cleaner import clean_choices_impl
        from game_engine.turn.dialogue import _build_dialogue_prompt_block
        from game_engine.turn_context import TurnContext
        from mechanics.social.physical_state import build_physical_prompt_block
        from mechanics.social.intimate_excitement import classify_intimate_act
        from game_engine.keywords import (
            NPC_ORAL_RECEIVE_KEYWORDS,
            NPC_ORAL_GIVE_KEYWORDS,
            NPC_MANUAL_RECEIVE_KEYWORDS,
            NPC_MANUAL_GIVE_KEYWORDS,
            INTERCOURSE_KEYWORDS,
        )

        # 1 & 5. Adapted continuation choice during active intercourse vs benign non-intimate action
        benign_res = classify_intimate_act(
            action_str="Touch the ancient rune with your hand",
            intimate_contact_str="none",
            player_name="Artemiusz",
            partner_name="Kana",
        )
        self.assertEqual(benign_res["act_type"], "none")

        adapted_cont = classify_intimate_act(
            action_str="Lift Kana onto the desk to deepen the angle and build the heat",
            intimate_contact_str="Intimate encounter with Kana (intercourse)",
            player_name="Artemiusz",
            partner_name="Kana",
            narrative_str="Artemiusz lifts her onto the edge of the desk, deepening the angle and quickening his rhythm.",
        )
        self.assertEqual(adapted_cont["act_type"], "penetrative")
        self.assertTrue(adapted_cont["player_stimulated"])
        self.assertTrue(adapted_cont["partner_stimulated"])

        # 2. Refractory clock recovery before compute_excitement_step on same turn
        refr_phys = {
            "intimate_contact": "Intimate encounter with Kana (player reached climax spent, partner unsatisfied)",
            "climax_state": {"partner_climaxed": False, "player_climaxed": True},
            "actors": {
                "Artemiusz": {"posture": "Lying on the bed", "clothing": {"top": "removed", "bottom": "removed"}},
                "Kana": {"posture": "Straddling Artemiusz", "clothing": {"top": "removed", "bottom": "removed"}},
            },
            "excitement": {
                "active": True,
                "last_act": "penetrative",
                "premature_finish": True,
                "partner_demanded": True,
                "refractory_until_minute": (1 * 1440) + 500,
                "cooldown_notified": False,
                "actors": {
                    "Artemiusz": {"meter": 100, "max": 100, "delta": 0, "endurance": 5, "climaxes_count": 1, "status": "💥 Climaxed (Spent)"},
                    "Kana": {"meter": 65, "max": 100, "delta": 0, "endurance": 7, "climaxes_count": 0, "status": "Deepening Pleasure"},
                },
            },
        }
        db.update_session_physical_state(self.session_id, refr_phys)
        sess_refr = db.get_session(self.session_id)
        sess_refr["current_day"] = 1
        sess_refr["current_minute"] = 510  # Past refractory_until_minute (500)
        sess_refr["dialogue_partner"] = "Kana"
        sess_refr["dialogue_partners"] = ["Kana"]
        sess_refr["physical_state"] = refr_phys
        outcome_refr = {
            "dialogue_partner": "Kana",
            "outcome_narrative": "Fully rested, Artemiusz slides inside Kana again with a steady rhythm.",
            "next_narrative": "Kana gasps as they resume.",
        }
        _reduce_physical_state_and_memories(
            session_id=self.session_id,
            session=sess_refr,
            outcome=outcome_refr,
            party=[(self.player_char, "1")],
            scen_key="nsfw_furry_high_school_drama",
            actions=[{"label": "Slide inside Kana and resume a steady rhythm", "success": True}],
        )
        self.assertIn("_refractory_recovered_notice", outcome_refr)
        after_refr = db.get_session_physical_state(self.session_id)
        self.assertFalse(after_refr["climax_state"]["player_climaxed"])
        # Player meter was reset from 100 to 0 upon recovery and then gained Turn 1 delta (> 0 and < 100)
        p_meter_after = after_refr["excitement"]["actors"]["Artemiusz"]["meter"]
        self.assertGreater(p_meter_after, 0)
        self.assertLess(p_meter_after, 100)

        # 3 & 6. Multi-actor posture/meter preservation + single exit choice + recovered partner not pruned
        multi_actor_phys = {
            "intimate_contact": "Intimate encounter with Kana (oral give)",
            "climax_state": {"partner_climaxed": False, "player_climaxed": False},
            "actors": {
                "Artemiusz": {"posture": "Kneeling between Kana's thighs", "clothing": {"top": "removed", "bottom": "removed"}},
                "Kana": {"posture": "Sitting on the desk", "clothing": {"top": "removed", "bottom": "removed"}},
                "Bystander Guard": {"posture": "Standing by the hallway", "clothing": {"top": "Clothed", "bottom": "Clothed"}},
            },
            "excitement": {
                "active": True,
                "last_act": "oral_give",
                "current_partner": "Kana",
                "actors": {
                    "Artemiusz": {"meter": 25, "max": 100, "delta": 0, "endurance": 5, "climaxes_count": 0, "status": "Warming Up"},
                    "Kana": {"meter": 80, "max": 100, "delta": 0, "endurance": 7, "climaxes_count": 0, "status": "On the Brink 🔥"},
                    "Stale NPC": {"meter": 99, "max": 100, "delta": 0, "endurance": 5, "climaxes_count": 0, "status": "On the Brink 🔥"},
                },
            },
        }
        db.update_session_physical_state(self.session_id, multi_actor_phys)
        sess_multi = db.get_session(self.session_id)
        sess_multi["dialogue_partner"] = None
        sess_multi["dialogue_partners"] = []
        sess_multi["physical_state"] = multi_actor_phys
        cleaned_multi = clean_choices_impl(
            None,
            choices=[
                {"label": "Keep a relentless pace with your tongue to push Kana over the edge", "stat": "END", "requirement": 7},
                {"label": "Gently withdraw and pull the blanket over Kana", "stat": "NONE", "requirement": 0},
            ],
            scenario="nsfw_furry_high_school_drama",
            location="Bedroom",
            char=self.player_char,
            dialogue_partner=None,  # Recovered from intimate_contact
            session_id=self.session_id,
        )
        # Only 1 free exit choice should be present, and Kana choices should not be pruned as absent contact
        free_exits_multi = [c for c in cleaned_multi if c["stat"] == "NONE"]
        self.assertEqual(len(free_exits_multi), 1)
        # Player posture 'Kneeling' must not be overwritten by 'Bystander Guard' ('Standing'), so 'hips and thighs' kneeling blueprint is injected
        self.assertTrue(any("hips and thighs" in c["label"].lower() for c in cleaned_multi))

        # 4. Premature finish aftercare choice transitions to 'Cuddling / aftercare' and populates aftercare choices
        prem_phys = {
            "intimate_contact": "Intimate encounter with Kana (player reached climax spent, partner unsatisfied)",
            "climax_state": {"partner_climaxed": False, "player_climaxed": True},
            "actors": {
                "Artemiusz": {"posture": "Lying on the bed", "clothing": {"top": "removed", "bottom": "removed"}},
                "Kana": {"posture": "Lying beside Artemiusz", "clothing": {"top": "removed", "bottom": "removed"}},
            },
            "excitement": {
                "active": True,
                "last_act": "penetrative",
                "premature_finish": True,
                "partner_demanded": False,
                "actors": {
                    "Artemiusz": {"meter": 100, "max": 100, "delta": 0, "endurance": 5, "climaxes_count": 1, "status": "💥 Climaxed (Spent)"},
                    "Kana": {"meter": 70, "max": 100, "delta": 0, "endurance": 7, "climaxes_count": 0, "status": "Deepening Pleasure"},
                },
            },
        }
        db.update_session_physical_state(self.session_id, prem_phys)
        sess_multi["dialogue_partner"] = "Kana"
        sess_multi["dialogue_partners"] = ["Kana"]
        sess_multi["physical_state"] = prem_phys
        outcome_ac = {
            "dialogue_partner": "Kana",
            "outcome_narrative": "Artemiusz apologizes breathlessly and holds Kana close in tender aftercare.",
            "next_narrative": "She rests her head on his chest.",
            "choices": [
                {"label": "Push through exhaustion to satisfy Kana", "stat": "END", "requirement": 8},
            ],
        }
        _reduce_physical_state_and_memories(
            session_id=self.session_id,
            session=sess_multi,
            outcome=outcome_ac,
            party=[(self.player_char, "1")],
            scen_key="nsfw_furry_high_school_drama",
            actions=[{"label": "Apologize breathlessly, hold Kana close, and promise to make it up to her", "success": True}],
        )
        phys_ac = db.get_session_physical_state(self.session_id)
        self.assertEqual(phys_ac["intimate_contact"], "Cuddling / aftercare with Kana")
        self.assertFalse(phys_ac["excitement"]["active"])
        ac_choice_lbls = [c["label"].lower() for c in outcome_ac["choices"]]
        self.assertFalse(any("push through exhaustion" in l for l in ac_choice_lbls))
        self.assertTrue(any("aftercare" in l or "kiss her softly" in l for l in ac_choice_lbls))
        self.assertTrue(any("redress / get dressed (artemiusz)" in l for l in ac_choice_lbls))

        # 7. Turn 1 explicit genital initiation injects HYBRID CHOICE BLUEPRINTS into prompt blocks
        fresh_phys = {
            "intimate_contact": "none",
            "climax_state": {"partner_climaxed": False, "player_climaxed": False},
            "actors": {
                "Artemiusz": {"posture": "Kneeling", "clothing": {"top": "Clothed", "bottom": "Clothed"}},
                "Kana": {"posture": "Sitting on the bed", "clothing": {"top": "Clothed", "bottom": "Removed"}},
            },
        }
        db.update_session_physical_state(self.session_id, fresh_phys)
        sess_multi["scenario"] = "nsfw_furry_high_school_drama"
        sess_multi["physical_state"] = fresh_phys
        turn1_actions = [{"label": "Kneel between Kana's thighs and use your tongue passionately to taste her", "success": True}]
        p_block_t1 = build_physical_prompt_block(
            sess_multi,
            [(self.player_char, "1")],
            is_combat=False,
            is_nsfw=True,
            actions=turn1_actions,
        )
        self.assertIn("HYBRID CHOICE BLUEPRINTS", p_block_t1)
        ctx_t1 = TurnContext(self.session_id, sess_multi, [(self.player_char, "1")])
        dlg_block_t1 = _build_dialogue_prompt_block(
            session=sess_multi,
            ctx=ctx_t1,
            new_partners=["Kana"],
            party=[(self.player_char, "1")],
            actions=turn1_actions,
        )
        self.assertIn("INTIMATE ENCOUNTER PACING & PLAYER PRIMACY", dlg_block_t1)

        # 8. Hybrid Blueprint phrases exist in milestone keyword lists
        self.assertIn("use your tongue passionately", NPC_ORAL_RECEIVE_KEYWORDS)
        self.assertIn("pleasures you with her mouth", NPC_ORAL_GIVE_KEYWORDS)
        self.assertIn("use your fingers to stroke", NPC_MANUAL_RECEIVE_KEYWORDS)
        self.assertIn("steady rhythm of her hand", NPC_MANUAL_GIVE_KEYWORDS)
        # 8. Hybrid Blueprint phrases exist in milestone keyword lists
        self.assertIn("use your tongue passionately", NPC_ORAL_RECEIVE_KEYWORDS)
        self.assertIn("pleasures you with her mouth", NPC_ORAL_GIVE_KEYWORDS)
        self.assertIn("use your fingers to stroke", NPC_MANUAL_RECEIVE_KEYWORDS)
        self.assertIn("steady rhythm of her hand", NPC_MANUAL_GIVE_KEYWORDS)
        self.assertIn("maintain a steady, deep rhythm", INTERCOURSE_KEYWORDS)

    def test_multi_partner_meter_tracking_and_spectator_warmth(self):
        """Verify multiple partners have simultaneous meters that are retained without purging, and unaddressed partners receive spectator warmth."""
        partner1 = {"name": "Kana", "appearance": {"endurance": 5}}
        partner2 = {"name": "Elena", "appearance": {"endurance": 5}}
        phys = {
            "intimate_contact": "none",
            "actors": {"Artemiusz": {}, "Kana": {}, "Elena": {}}
        }
        session = {"current_day": 1, "current_minute": 500, "dialogue_partners": ["Kana", "Elena"]}

        # Turn 1: Target Kana with manual stimulation
        res1 = compute_excitement_step(
            physical_state=phys,
            action_str="Use your fingers to stroke Kana intimately between her thighs",
            player_char=self.player_char,
            partner_contact=partner1,
            session=session,
            narrative_str="Kana shivers with pleasure as you stroke her folds.",
            partner_contacts=[partner1, partner2]
        )
        self.assertEqual(phys["excitement"]["actors"]["Kana"]["meter"], 14)
        self.assertEqual(phys["excitement"]["actors"]["Elena"]["meter"], 4)
        self.assertEqual(phys["excitement"]["actors"]["Elena"]["status"], "Watching with Arousal")
        self.assertIn("Elena", phys["excitement"]["actors"])

        # Turn 2: Switch focus to Elena with manual stimulation
        res2 = compute_excitement_step(
            physical_state=phys,
            action_str="Shift your focus and use your fingers to stroke Elena between her thighs",
            player_char=self.player_char,
            partner_contact=partner2,
            session=session,
            narrative_str="Elena gasps eagerly as your fingers find her wet entrance.",
            partner_contacts=[partner1, partner2]
        )
        # Kana was retained and gained 4 from spectator warmth; Elena gained full stimulation
        self.assertEqual(phys["excitement"]["actors"]["Kana"]["meter"], 18)
        self.assertGreater(phys["excitement"]["actors"]["Elena"]["meter"], 14)
        self.assertIn("Kana", phys["excitement"]["actors"])
        self.assertIn("Elena", phys["excitement"]["actors"])
        self.assertEqual(len(res2["partner_meters"]), 2)

    def test_multi_partner_climax_attribution_and_primacy(self):
        """Verify climax events are attributed specifically to the named partner, with aggregate and per-partner flags."""
        partner1 = {"name": "Kana", "appearance": {"endurance": 5}}
        partner2 = {"name": "Elena", "appearance": {"endurance": 5}}
        phys = {
            "intimate_contact": "Intercourse with Kana",
            "actors": {"Artemiusz": {}, "Kana": {}, "Elena": {}},
            "excitement": {
                "active": True,
                "actors": {
                    "Artemiusz": {"meter": 60, "endurance": 6, "status": "Maintaining Rhythm"},
                    "Kana": {"meter": 90, "endurance": 5, "status": "On the Brink 🔥"},
                    "Elena": {"meter": 40, "endurance": 5, "status": "Arousal Building"},
                }
            }
        }
        session = {"current_day": 1, "current_minute": 500, "dialogue_partners": ["Kana", "Elena"]}

        # Turn: Kana climaxes specifically in narrative
        res = compute_excitement_step(
            physical_state=phys,
            action_str="Stroke Kana with relentless intensity until she reaches climax",
            player_char=self.player_char,
            partner_contact=partner1,
            session=session,
            narrative_str="Kana arches her back with an intense cry in her shuddering climax.",
            partner_contacts=[partner1, partner2]
        )
        self.assertTrue(phys["climax_state"]["partner_climaxes"]["Kana"])
        self.assertFalse(phys["climax_state"]["partner_climaxes"]["Elena"])
        self.assertTrue(phys["climax_state"]["partner_climaxed"])
        self.assertFalse(phys["excitement"]["all_partners_climaxed"])
        self.assertEqual(phys["excitement"]["actors"]["Kana"]["meter"], 100)

        # Later turn: Elena climaxes
        res_elena = compute_excitement_step(
            physical_state=phys,
            action_str="Turn to Elena and stroke her relentlessly until she reaches climax",
            player_char=self.player_char,
            partner_contact=partner2,
            session=session,
            narrative_str="Elena cries out as she reaches her breathless climax.",
            partner_contacts=[partner1, partner2]
        )
        self.assertTrue(phys["climax_state"]["partner_climaxes"]["Kana"])
        self.assertTrue(phys["climax_state"]["partner_climaxes"]["Elena"])
        self.assertTrue(phys["climax_state"]["partner_climaxed"])
        self.assertTrue(phys["excitement"]["all_partners_climaxed"])

    def test_multi_partner_format_compact_discord_meter(self):
        """Verify format_compact_discord_meter renders multi-line and single-line progress bars cleanly."""
        # 1. Single partner legacy mode
        disp_single = format_compact_discord_meter("Artemiusz", 50, "Kana", 80, False)
        self.assertIn("💋 Artemiusz: 50%", disp_single)
        self.assertIn("Kana: 80%", disp_single)

        # 2. Multi-partner mode
        actors = {
            "Artemiusz": {"meter": 45, "status": "Maintaining Rhythm"},
            "Kana": {"meter": 100, "status": "💥 Climax Reached!"},
            "Elena": {"meter": 35, "status": "Arousal Building"},
        }
        disp_multi = format_compact_discord_meter("Artemiusz", 45, actors=actors)
        self.assertIn("Artemiusz: 45%", disp_multi)
        self.assertIn("Kana: 100%", disp_multi)
        self.assertIn("Elena: 35%", disp_multi)

    def test_multi_partner_reducers_integration(self):
        """Verify _reduce_physical_state_and_memories accurately updates and persists multiple partner meters."""
        from game_engine.state.reducers import _reduce_physical_state_and_memories

        session = db.get_session(self.session_id)
        session["current_day"] = 1
        session["current_minute"] = 500
        session["dialogue_partners"] = ["Kana", "Elena"]
        fresh_phys = {
            "intimate_contact": "none",
            "climax_state": {"partner_climaxed": False, "player_climaxed": False},
            "actors": {"Artemiusz": {}, "Kana": {}, "Elena": {}},
        }
        session["physical_state"] = fresh_phys
        db.update_session_physical_state(self.session_id, fresh_phys)

        outcome = {
            "dialogue_partners": ["Kana", "Elena"],
            "outcome_narrative": "You use your fingers to stroke Kana intimately between her thighs. Elena watches with heated breath.",
            "next_narrative": "Both of them look up at you with parted lips.",
        }
        _reduce_physical_state_and_memories(
            session_id=self.session_id,
            session=session,
            outcome=outcome,
            party=[(self.player_char, "1")],
            scen_key="nsfw_furry_high_school_drama",
            actions=[{"label": "Use your fingers to stroke Kana intimately between her thighs", "success": True}],
        )

        phys_after = db.get_session_physical_state(self.session_id)
        self.assertIn("excitement", phys_after)
        self.assertIn("Kana", phys_after["excitement"]["actors"])
        self.assertIn("Elena", phys_after["excitement"]["actors"])
        self.assertEqual(phys_after["excitement"]["actors"]["Kana"]["meter"], 14)
        self.assertEqual(phys_after["excitement"]["actors"]["Elena"]["meter"], 4)
        self.assertIn("partner_meters", outcome["intimate_update"])
        self.assertEqual(len(outcome["intimate_update"]["partner_meters"]), 2)

    def test_multi_partner_choice_blueprints(self):
        """Verify build_intimate_choice_blueprints creates balanced slots across multiple partners."""
        # 1. Active intimacy
        partner_actors = [
            {"name": "Kana", "meter": 80, "climaxed": False, "posture": "kneeling", "spots": "hips"},
            {"name": "Elena", "meter": 45, "climaxed": False, "posture": "sitting", "spots": "neck and shoulders"},
        ]
        bp = build_intimate_choice_blueprints(
            partner_name="Kana",
            last_act="manual_give",
            partner_actors=partner_actors,
        )
        choices = bp["choices"]
        self.assertEqual(len(choices), 4)
        self.assertIn("Kana", choices[0]["label"])
        self.assertIn("Elena", choices[1]["label"])
        # Slot 3 is climax push for highest meter (Kana at 80 >= 70)
        self.assertIn("Kana", choices[2]["label"])
        self.assertIn("edge", choices[2]["label"].lower())
        # Slot 4 is exit with both
        self.assertIn("Kana", choices[3]["label"])
        self.assertIn("Elena", choices[3]["label"])

        # 2. Premature finish with multiple partners
        bp_premature = build_intimate_choice_blueprints(
            partner_name="Kana",
            player_climaxed=True,
            premature_finish=True,
            partner_actors=partner_actors,
        )
        p_choices = bp_premature["choices"]
        self.assertEqual(len(p_choices), 4)
        self.assertTrue(any("Kana" in c["label"] and "fingers" in c["label"].lower() for c in p_choices))
        self.assertTrue(any("Elena" in c["label"] and "tongue" in c["label"].lower() for c in p_choices))
        self.assertTrue(any("Kana" in c["label"] and "Elena" in c["label"] and "apologiz" in c["label"].lower() for c in p_choices))
        self.assertIn("Kana", bp_premature["exit_label"])
        self.assertIn("Elena", bp_premature["exit_label"])

        # 3. Post-climax aftercare with multiple partners
        bp_aftercare = build_intimate_choice_blueprints(
            partner_name="Kana",
            player_climaxed=True,
            premature_finish=False,
            partner_actors=partner_actors,
        )
        ac_choices = bp_aftercare["choices"]
        self.assertEqual(len(ac_choices), 4)
        self.assertTrue(any("Kana" in c["label"] and "aftercare" in c["label"].lower() for c in ac_choices))
        self.assertTrue(any("Elena" in c["label"] and ("kiss" in c["label"].lower() or "hair" in c["label"].lower()) for c in ac_choices))
        self.assertTrue(any("Kana" in c["label"] and "Elena" in c["label"] and "arms" in c["label"].lower() for c in ac_choices))
        self.assertIn("Kana", bp_aftercare["exit_label"])
        self.assertIn("Elena", bp_aftercare["exit_label"])

    def test_multi_partner_contradiction_filtering(self):
        """Verify has_state_contradiction_in_choice checks climax per specific partner."""
        partner_climaxes = {"Kana": True, "Elena": False}

        # Kana climaxed -> aftermath phrase with Kana is valid (not contradictory)
        self.assertFalse(has_state_contradiction_in_choice(
            "Hold Kana through her tremors in sweet warmth",
            partner_climaxes=partner_climaxes,
        ))

        # Elena has NOT climaxed -> aftermath phrase with Elena is contradictory
        self.assertTrue(has_state_contradiction_in_choice(
            "Hold Elena through her tremors in sweet warmth",
            partner_climaxes=partner_climaxes,
        ))

        # Shared reference ("their tremors") when at least one partner peaked is valid
        self.assertFalse(has_state_contradiction_in_choice(
            "Hold them close through their tremors in sweet aftercare",
            partner_climaxes=partner_climaxes,
            partner_climaxed=True,
            player_climaxed=True,
        ))

    def test_multi_partner_choices_cleaner_integration(self):
        """Verify clean_choices_impl discovers multiple partners and generates balanced blueprints."""
        db.update_session_physical_state(self.session_id, {
            "intimate_contact": "Intimate encounter with Kana and Elena (manual give)",
            "climax_state": {"partner_climaxed": False, "player_climaxed": False, "partner_climaxes": {"Kana": False, "Elena": False}},
            "excitement": {
                "active": True,
                "actors": {
                    "Artemiusz": {"meter": 50},
                    "Kana": {"meter": 80},
                    "Elena": {"meter": 40},
                }
            }
        })
        cleaned = clean_choices_impl(
            None,
            choices=[],
            scenario="nsfw_furry_high_school_drama",
            location="Private Quarters",
            char=self.player_char,
            dialogue_partner=["Kana", "Elena"],
            session_id=self.session_id,
        )
        labels = [c["label"] for c in cleaned]
        self.assertTrue(any("Kana" in l for l in labels))
        self.assertTrue(any("Elena" in l for l in labels))
        exit_choice = next((c for c in cleaned if c.get("stat") == "NONE" or "Ease back" in c["label"] or "catch your breath" in c["label"]), None)
        self.assertIsNotNone(exit_choice)
        self.assertIn("Kana", exit_choice["label"])
        self.assertIn("Elena", exit_choice["label"])

    def test_multi_partner_aftercare_reducers_integration(self):
        """Verify _apply_dialogue_outcome_reducers populates multi-partner aftercare options."""
        from game_engine.state.reducers import _reduce_physical_state_and_memories

        session = db.get_session(self.session_id)
        session["current_day"] = 1
        session["current_minute"] = 510
        session["dialogue_partners"] = ["Kana", "Elena"]
        prev_phys = {
            "intimate_contact": "Intimate encounter with Kana (intercourse)",
            "climax_state": {"partner_climaxed": False, "player_climaxed": False},
            "actors": {"Artemiusz": {}, "Kana": {}, "Elena": {}},
            "excitement": {
                "active": True,
                "actors": {
                    "Artemiusz": {"meter": 95},
                    "Kana": {"meter": 95},
                    "Elena": {"meter": 50},
                }
            }
        }
        db.update_session_physical_state(self.session_id, prev_phys)
        session["physical_state"] = prev_phys

        outcome = {
            "dialogue_partners": ["Kana", "Elena"],
            "outcome_narrative": "You spill deep inside Kana as she trembles in intense orgasm. Elena exhales softly, holding your arm.",
            "next_narrative": "The room grows quiet in post-climax intimacy.",
            "choices": [
                {"label": "Keep thrusting relentlessly", "stat": "STR"},
                {"label": "Hold Elena through her tremors", "stat": "CHA"},  # Contradiction: Elena has not climaxed
            ],
        }
        _reduce_physical_state_and_memories(
            session_id=self.session_id,
            session=session,
            outcome=outcome,
            party=[(self.player_char, "1")],
            scen_key="nsfw_furry_high_school_drama",
            actions=[{"label": "Push over the edge together to finish inside", "success": True}],
        )

        res_choices = outcome.get("choices") or []
        res_labels = [c["label"] for c in res_choices]
        # Stale thrust choices removed
        self.assertFalse(any("keep thrusting relentlessly" in l.lower() for l in res_labels))
        # Contradictory Elena tremors removed
        self.assertFalse(any("hold elena through her tremors" in l.lower() for l in res_labels))
        # Aftercare options generated referencing both partners
        self.assertTrue(any("Kana" in l for l in res_labels))
        self.assertTrue(any("Elena" in l for l in res_labels))

    def test_tier3_simultaneous_and_mutual_group_climax(self):
        """Verify compute_excitement_step sets simultaneous_partner_climax and mutual_group_climax."""
        phys_state = {
            "intimate_contact": "Intimate encounter with Kana and Elena (intercourse)",
            "climax_state": {"partner_climaxed": False, "player_climaxed": False},
            "actors": {
                "Artemiusz": {"meter": 96, "max": 100, "delta": 0, "endurance": 5, "climaxes_count": 0, "status": "On the Brink 🔥"},
                "Kana": {"meter": 96, "max": 100, "delta": 0, "endurance": 5, "climaxes_count": 0, "status": "On the Brink 🔥"},
                "Elena": {"meter": 96, "max": 100, "delta": 0, "endurance": 5, "climaxes_count": 0, "status": "On the Brink 🔥"},
            },
        }
        res = compute_excitement_step(
            physical_state=phys_state,
            action_str="Thrust deep and bring both Kana and Elena over the edge together into climax",
            player_char=self.player_char,
            partner_contacts=[{"name": "Kana"}, {"name": "Elena"}],
            session={"current_day": 1, "current_minute": 500},
            narrative_str="Both Kana and Elena cry out in simultaneous shuddering orgasm as you spill deep inside.",
        )
        self.assertTrue(res["simultaneous_partner_climax"])
        self.assertTrue(res["mutual_group_climax"])
        self.assertTrue(res["player_climaxed"])
        self.assertTrue(res["partner_climaxes"]["Kana"])
        self.assertTrue(res["partner_climaxes"]["Elena"])

    def test_tier3_multi_partner_postures_and_spatial_continuity(self):
        """Verify _reduce_physical_state_and_memories grounds all partner postures and records memories."""
        from game_engine.state.reducers import _reduce_physical_state_and_memories

        session = db.get_session(self.session_id)
        session["current_day"] = 1
        session["current_minute"] = 520
        session["dialogue_partners"] = ["Kana", "Elena"]
        prev_phys = {
            "intimate_contact": "Intimate encounter with Kana and Elena (intercourse)",
            "climax_state": {"partner_climaxed": False, "player_climaxed": False},
            "actors": {
                "Artemiusz": {"posture": "Standing by the bed"},
                "Kana": {"posture": "Sitting on the bed"},
                "Elena": {"posture": "Lying on the bed"},
            },
            "excitement": {
                "active": True,
                "actors": {
                    "Artemiusz": {"meter": 50},
                    "Kana": {"meter": 98},
                    "Elena": {"meter": 50},
                }
            }
        }
        db.update_session_physical_state(self.session_id, prev_phys)
        session["physical_state"] = prev_phys

        # Turn 1: Only Kana climaxes, player continues (Primacy)
        outcome1 = {
            "dialogue_partners": ["Kana", "Elena"],
            "outcome_narrative": "Kana shudders in intense climax as you maintain your rhythm. Elena breathes heavily beside you.",
            "next_narrative": "Kana trembles in release while you and Elena remain close.",
        }
        _reduce_physical_state_and_memories(
            session_id=self.session_id,
            session=session,
            outcome=outcome1,
            party=[(self.player_char, "1")],
            scen_key="nsfw_furry_high_school_drama",
            actions=[{"label": "Stroke Kana to her climax while kissing Elena", "success": True}],
        )

        phys1 = db.get_session_physical_state(self.session_id)
        actors1 = phys1["actors"]
        # Kana posture references both Artemiusz and Elena
        self.assertIn("Trembling from aftershocks beside Artemiusz and Elena", actors1["Kana"]["posture"])
        # Elena posture is grounded close beside Artemiusz
        self.assertIn("Resting close beside Artemiusz", actors1["Elena"]["posture"])
        # intimate_contact string includes both Kana and Elena
        self.assertIn("with Kana and Elena", phys1["intimate_contact"])

        # Turn 2: Transition to aftercare
        outcome2 = {
            "dialogue_partners": ["Kana", "Elena"],
            "outcome_narrative": "You pull back and rest together in sweet aftercare with both Kana and Elena.",
            "next_narrative": "The quiet warmth settles over the room.",
            "choices": [{"label": "Rest together in sweet aftercare", "success": True}],
        }
        _reduce_physical_state_and_memories(
            session_id=self.session_id,
            session=session,
            outcome=outcome2,
            party=[(self.player_char, "1")],
            scen_key="nsfw_furry_high_school_drama",
            actions=[{"label": "Rest together in sweet aftercare", "success": True}],
        )

        phys2 = db.get_session_physical_state(self.session_id)
        actors2 = phys2["actors"]
        self.assertIn("Resting in aftercare, holding both Kana and Elena", actors2["Artemiusz"]["posture"])
        self.assertIn("Resting against Artemiusz in shared aftercare", actors2["Kana"]["posture"])
        self.assertIn("Resting against Artemiusz in shared aftercare", actors2["Elena"]["posture"])
        self.assertIn("Cuddling / aftercare with Kana and Elena", phys2["intimate_contact"])

        # Episodic memories and relationship updates were recorded for BOTH partners
        mems = outcome2.get("npc_memories") or []
        mem_names = [m.get("npc_name") for m in mems]
        self.assertIn("Kana", mem_names)
        self.assertIn("Elena", mem_names)

        rus = outcome2.get("relationship_updates") or []
        ru_names = [r.get("npc_name") for r in rus]
        self.assertIn("Kana", ru_names)
        self.assertIn("Elena", ru_names)

    def test_tier3_triadic_choice_blueprints(self):
        """Verify build_intimate_choice_blueprints generates dual edge release when both partners >= 70%."""
        partner_actors = [
            {"name": "Kana", "meter": 75, "climaxed": False, "posture": "kneeling", "spots": "hips"},
            {"name": "Elena", "meter": 78, "climaxed": False, "posture": "sitting", "spots": "neck and shoulders"},
        ]
        bp = build_intimate_choice_blueprints(
            partner_name="Kana",
            last_act="manual_give",
            partner_actors=partner_actors,
        )
        choices = bp["choices"]
        slot3 = choices[2]
        self.assertIn("Coordinate your touch between both Kana and Elena", slot3["label"])
        self.assertIn("edge together into climax", slot3["label"])

    def test_tier3_multi_partner_edge_cases(self):
        """Verify multi-partner action phrases, spectator warmth, and top-level actor meter adoption."""
        phys = {
            "intimate_contact": "Intimate encounter with Kana and Elena (intercourse)",
            "climax_state": {"partner_climaxed": False, "player_climaxed": False},
            "actors": {
                "Artemiusz": {"meter": 50, "max": 100, "delta": 0, "endurance": 5, "climaxes_count": 0, "status": "Arousal Building"},
                "Kana": {"meter": 50, "max": 100, "delta": 0, "endurance": 5, "climaxes_count": 0, "status": "Arousal Building"},
                "Elena": {"meter": 50, "max": 100, "delta": 0, "endurance": 5, "climaxes_count": 0, "status": "Arousal Building"},
            },
        }
        res1 = compute_excitement_step(
            physical_state=phys,
            action_str="Continue thrusting into both Kana and Elena",
            player_char=self.player_char,
            partner_contacts=[{"name": "Kana"}, {"name": "Elena"}],
            session={"current_day": 1, "current_minute": 500},
            narrative_str="Kana and Elena both gasp with pleasure.",
        )
        self.assertGreater(res1["player_meter"], 50)
        self.assertEqual(res1["act_type"], "penetrative")

        # Oral give targeting one partner while second gains spectator warmth
        phys_oral = {
            "intimate_contact": "Intimate encounter with Kana and Elena (oral give)",
            "climax_state": {"partner_climaxed": False, "player_climaxed": False},
            "excitement": {
                "active": True,
                "actors": {
                    "Artemiusz": {"meter": 20, "max": 100, "delta": 0, "endurance": 5, "climaxes_count": 0, "status": ""},
                    "Kana": {"meter": 30, "max": 100, "delta": 0, "endurance": 5, "climaxes_count": 0, "status": ""},
                    "Elena": {"meter": 30, "max": 100, "delta": 0, "endurance": 5, "climaxes_count": 0, "status": ""},
                },
            },
        }
        res_oral = compute_excitement_step(
            physical_state=phys_oral,
            action_str="Get on your knees and pleasure Kana orally",
            player_char=self.player_char,
            partner_contacts=[{"name": "Kana"}, {"name": "Elena"}],
            session={"current_day": 1, "current_minute": 500},
            narrative_str="You go down on Kana as Elena watches with flushed arousal.",
        )
        self.assertEqual(res_oral["act_type"], "oral_give")
        kana_meter = next((p["meter"] for p in res_oral["partner_meters"] if p["name"] == "Kana"), 0)
        elena_meter = next((p["meter"] for p in res_oral["partner_meters"] if p["name"] == "Elena"), 0)
        self.assertGreater(kana_meter, 30)
        self.assertGreater(elena_meter, 30)  # Spectator warmth (+4)

    def test_tier3_multi_partner_male_partners_gender_adaptation(self):
        """Verify female PC with male NPC partners generates masculine pronouns ('his', 'him', 'he')."""
        male_partners = [
            {"name": "Marcus", "gender": "Male", "meter": 75, "climaxed": False, "posture": "sitting", "spots": "chest"},
            {"name": "Arthur", "gender": "Male", "meter": 72, "climaxed": False, "posture": "kneeling", "spots": "shoulders"},
        ]
        bp = build_intimate_choice_blueprints(
            partner_name="Marcus",
            last_act="oral_receive",
            partner_actors=male_partners,
        )
        c1 = bp["choices"][0]["label"]
        c2 = bp["choices"][1]["label"]
        # In oral_receive with male partner A: "guide Marcus's head as he deepens his oral pace"
        self.assertIn("he deepens his oral pace", c1)
        self.assertNotIn("she deepens her", c1)
        # Partner B focus: "Pull Arthur close with your free arm, kissing his lips as Marcus pleasures you with his mouth"
        self.assertIn("kissing his lips as Marcus pleasures you with his mouth", c2)
        self.assertNotIn("kissing her lips", c2)

        # Single male partner check
        single_male_bp = build_intimate_choice_blueprints(
            partner_name="Arthur",
            last_act="manual_receive",
            partner_gender="Male",
        )
        sm_c1 = single_male_bp["choices"][0]["label"]
        sm_c2 = single_male_bp["choices"][1]["label"]
        self.assertIn("rhythm of his hand", sm_c1)
        self.assertIn("as he strokes you", sm_c2)

    def test_tier3_three_partner_scaling_postures_and_memories(self):
        """Verify 3+ partner encounters scale cleanly in choice blueprints, postures, and episodic memory."""
        three_partners = [
            {"name": "Kana", "gender": "Female", "meter": 80, "climaxed": False, "posture": "kneeling", "spots": "hips"},
            {"name": "Elena", "gender": "Female", "meter": 82, "climaxed": False, "posture": "sitting", "spots": "neck"},
            {"name": "Chloe", "gender": "Female", "meter": 75, "climaxed": False, "posture": "standing", "spots": "waist"},
        ]
        bp = build_intimate_choice_blueprints(
            partner_name="Kana",
            last_act="penetrative",
            partner_actors=three_partners,
        )
        slot3 = bp["choices"][2]["label"]
        slot4 = bp["choices"][3]["label"]
        self.assertIn("Coordinate your touch among Kana, Elena, and Chloe", slot3)
        self.assertIn("hold all of Kana, Elena, and Chloe close", slot4)

        # Reducer aftercare turn with 3 partners
        from game_engine.state.reducers import _reduce_physical_state_and_memories
        current_phys = {
            "intimate_contact": "Intimate encounter with Kana, Elena, and Chloe (intercourse)",
            "climax_state": {"partner_climaxed": True, "player_climaxed": True},
            "excitement": {
                "active": True,
                "actors": {
                    "Artemiusz": {"meter": 100, "status": "💥 Climaxed (Spent)", "delta": 0, "climaxes_count": 1},
                    "Kana": {"meter": 100, "status": "💥 Climax Reached!", "delta": 0, "climaxes_count": 1},
                    "Elena": {"meter": 100, "status": "💥 Climax Reached!", "delta": 0, "climaxes_count": 1},
                    "Chloe": {"meter": 100, "status": "💥 Climax Reached!", "delta": 0, "climaxes_count": 1},
                },
            },
            "actors": {
                "Artemiusz": {"posture": "Standing"},
                "Kana": {"posture": "Lying down spent"},
                "Elena": {"posture": "Lying down spent"},
                "Chloe": {"posture": "Lying down spent"},
            },
        }
        db.update_session_physical_state(self.session_id, current_phys)
        session = {
            "dialogue_partners": ["Kana", "Elena", "Chloe"],
            "current_day": 1,
            "current_minute": 500,
            "physical_state": current_phys,
        }
        outcome = {
            "dialogue_partners": ["Kana", "Elena", "Chloe"],
            "npc_memories": [],
            "relationship_updates": [],
        }
        _reduce_physical_state_and_memories(
            session_id=self.session_id,
            session=session,
            outcome=outcome,
            party=[(self.player_char, "1")],
            scen_key="nsfw_furry_high_school_drama",
            actions=[{"label": "Rest together in sweet aftercare, holding everyone close", "success": True}],
        )
        updated_phys = db.get_session_physical_state(self.session_id)
        self.assertIn("holding all of", updated_phys["actors"]["Artemiusz"]["posture"])
        kana_mem = next(m for m in outcome["npc_memories"] if m["npc_name"] == "Kana")
        self.assertIn("Elena and Chloe", kana_mem["memory_fact"])

    def test_tier3_multi_partner_turn_off_isolation_and_demand(self):
        """Verify turn-off recoil specifically freezes the averse partner without dampening the co-partner, and rolls demand against unsatisfied partner."""
        phys_state = {
            "intimate_contact": "Intimate encounter with Kana and Elena (intercourse)",
            "climax_state": {"partner_climaxed": False, "player_climaxed": False},
            "excitement": {
                "active": True,
                "actors": {
                    "Artemiusz": {"meter": 20, "endurance": 8, "delta": 0, "status": "Warming Up"},
                    "Kana": {"meter": 30, "endurance": 6, "delta": 0, "status": "Warming Up"},
                    "Elena": {"meter": 30, "endurance": 6, "delta": 0, "status": "Warming Up"},
                },
            },
        }
        kana_contact = {
            "name": "Kana",
            "gender": "Female",
            "appearance": {
                "turn_offs": "rough handling, choking",
                "erotic_openness": "moderate",
                "intimate_dynamic": "playful",
            },
        }
        elena_contact = {
            "name": "Elena",
            "gender": "Female",
            "appearance": {
                "turn_offs": "none",
                "erotic_openness": "bold",
                "intimate_dynamic": "dominant",
            },
        }
        # Act with rough handling targeting Kana
        step_res = compute_excitement_step(
            physical_state=phys_state,
            action_str="Rough handling and thrust into Kana while Elena watches",
            player_char=self.player_char,
            session={"id": self.session_id, "current_day": 1, "current_minute": 500},
            partner_contacts=[kana_contact, elena_contact],
        )
        actors = phys_state["excitement"]["actors"]
        # Kana recoils and gains 0 delta
        self.assertEqual(actors["Kana"]["delta"], 0)
        self.assertEqual(actors["Kana"]["status"], "Turned Off / Recoiling ⚠️")
        # Elena is unaffected by Kana's turn-off and receives spectator warmth
        self.assertGreater(actors["Elena"]["delta"], 0)
        self.assertEqual(actors["Elena"]["status"], "Watching with Arousal")

        # Now test unsatisfied demand rolling: Kana peaked, Player peaked spent, Elena unsatisfied
        phys_state["excitement"]["actors"]["Kana"]["meter"] = 100
        phys_state["excitement"]["actors"]["Elena"]["meter"] = 40
        phys_state["excitement"]["actors"]["Artemiusz"]["meter"] = 95
        phys_state["climax_state"]["partner_climaxes"] = {"Kana": True, "Elena": False}
        phys_state["climax_state"]["partner_climaxed"] = True

        step_premature = compute_excitement_step(
            physical_state=phys_state,
            action_str="Thrust deeply toward release",
            player_char=self.player_char,
            session={"id": self.session_id, "current_day": 1, "current_minute": 500},
            partner_contacts=[kana_contact, elena_contact],
        )
        self.assertTrue(step_premature["premature_finish"])
        self.assertIn("Elena", step_premature["actors"])
        self.assertEqual(phys_state["excitement"]["unsatisfied_partners"], ["Elena"])
        # Elena has bold/dominant dynamic, so demand is active
        self.assertTrue(phys_state["excitement"]["partner_demanded"])

    def test_tier3_multi_partner_dialogue_directive_isolation(self):
        """Verify dialogue directives accurately branch on individual partner climax states in multi-partner encounters."""
        current_phys = {
            "intimate_contact": "Intimate encounter with Kana and Elena (intercourse)",
            "climax_state": {
                "partner_climaxed": True,
                "player_climaxed": False,
                "partner_climaxes": {"Kana": True, "Elena": False},
            },
            "excitement": {
                "active": True,
                "actors": {
                    "Artemiusz": {"meter": 60, "delta": 15, "status": "Maintaining Rhythm"},
                    "Kana": {"meter": 100, "delta": 15, "status": "💥 Climax Reached!"},
                    "Elena": {"meter": 45, "delta": 15, "status": "Arousal Building"},
                },
            },
        }
        db.update_session_physical_state(self.session_id, current_phys)
        session = {
            "id": self.session_id,
            "scenario": "nsfw_furry_high_school_drama",
            "scenario_key": "nsfw_furry_high_school_drama",
            "dialogue_partners": ["Kana", "Elena"],
            "current_day": 1,
            "current_minute": 500,
            "physical_state": current_phys,
            "current_npcs": [
                {"name": "Kana", "appearance": {"intimate_dynamic": "sweet", "erotic_openness": "moderate"}},
                {"name": "Elena", "appearance": {"intimate_dynamic": "playful", "erotic_openness": "moderate"}},
            ],
        }
        from game_engine.turn.dialogue import _build_dialogue_prompt_block
        from game_engine.turn_context import TurnContext
        ctx = TurnContext(self.session_id, session, [(self.player_char, [])])
        dir_text = _build_dialogue_prompt_block(
            session=session,
            ctx=ctx,
            new_partners=["Kana", "Elena"],
            party=[(self.player_char, "1")],
            actions=[{"label": "Maintain deep rhythm"}],
        )
        # Kana peaked -> Primacy directive
        self.assertIn("[INTIMATE PACING & PLAYER CLIMAX PRIMACY (Kana)]", dir_text)
        # Elena has NOT peaked -> Pacing directive, NOT primacy aftershocks!
        self.assertNotIn("[INTIMATE PACING & PLAYER CLIMAX PRIMACY (Elena)]", dir_text)
        self.assertIn("Elena", dir_text)

    def test_multi_partner_sensitive_spot_aggregation_and_blueprint_resolution(self):
        """Verify secondary partner sensitive spot returns properly and triggers bonuses in compute_excitement_step."""
        from mechanics.social.intimate_excitement import compute_excitement_step, infer_last_act_from_state
        partner_contacts = [
            {"name": "Elena", "gender": "Female", "appearance": {"sensitive_spots": "Nape of neck", "turn_ons": "Gentle biting"}},
            {"name": "Kana", "gender": "Female", "appearance": {"sensitive_spots": "Fox ears", "turn_ons": "Tail strokes"}},
        ]
        phys = {
            "intimate_contact": "Intimate encounter with Elena and Kana (oral_give)",
            "actors": {
                "Artemiusz": {"meter": 40, "delta": 0, "status": "Arousal Building", "posture": "kneeling between his thighs"},
                "Elena": {"meter": 50, "delta": 0, "status": "Deepening Pleasure"},
                "Kana": {"meter": 50, "delta": 0, "status": "Deepening Pleasure"},
            },
            "climax_state": {"partner_climaxed": False, "player_climaxed": False, "partner_climaxes": {"Elena": False, "Kana": False}},
            "excitement": {"active": True, "actors": {
                "Artemiusz": {"meter": 40, "delta": 0, "status": "Arousal Building"},
                "Elena": {"meter": 50, "delta": 0, "status": "Deepening Pleasure"},
                "Kana": {"meter": 50, "delta": 0, "status": "Deepening Pleasure"},
            }},
        }
        session = {"id": self.session_id, "dialogue_partners": ["Elena", "Kana"], "scenario": "nsfw_furry_high_school_drama"}
        
        # Stroke Kana's fox ears while stimulating her (targeting secondary partner Kana)
        res = compute_excitement_step(
            action_str="Stroke Kana's fox ears tenderly while curling your fingers between her thighs",
            narrative_str="Kana shivers as her fox ears are touched.",
            physical_state=phys,
            player_char=self.player_char,
            partner_contacts=partner_contacts,
            session=session,
        )
        self.assertTrue(res["sensitive_spot_matched"])
        self.assertIn("Kana: Fox ears", str(res["matched_spot"]))
        
        # Test infer_last_act_from_state with male / plural thighs posture
        phys_male_thighs = {
            "intimate_contact": "none",
            "actors": {"Artemiusz": {"posture": "kneeling between his thighs"}},
        }
        self.assertEqual(infer_last_act_from_state(phys_male_thighs), "oral_give")
        
        phys_plural_thighs = {
            "intimate_contact": "none",
            "actors": {"Artemiusz": {"posture": "resting between their thighs"}},
        }
        self.assertEqual(infer_last_act_from_state(phys_plural_thighs), "oral_give")

    def test_multi_partner_refractory_and_disengagement_cleanup(self):
        """Verify refractory clock resolution and disengagement clear partner climaxes and unsatisfied partner tags."""
        from mechanics.social.intimate_excitement import check_and_resolve_refractory_clock
        phys = {
            "intimate_contact": "Intimate encounter with Elena and Kana (player reached climax spent, partner unsatisfied)",
            "climax_state": {
                "partner_climaxed": True,
                "player_climaxed": True,
                "partner_climaxes": {"Elena": True, "Kana": False},
            },
            "excitement": {
                "active": False,
                "refractory_until_minute": 500,
                "cooldown_notified": False,
                "premature_finish": True,
                "partner_demanded": True,
                "unsatisfied_partner": "Kana",
                "unsatisfied_partners": ["Kana"],
                "actors": {
                    "Artemiusz": {"meter": 100, "delta": 0, "status": "💥 Climaxed (Spent)"},
                    "Elena": {"meter": 100, "delta": 0, "status": "💥 Climax Reached!"},
                    "Kana": {"meter": 60, "delta": 0, "status": "Arousal Building"},
                },
            },
        }
        session = {"current_day": 1, "current_minute": 510}
        recovered, toast = check_and_resolve_refractory_clock(session, phys)
        self.assertTrue(recovered)
        self.assertFalse(phys["excitement"]["premature_finish"])
        self.assertFalse(phys["excitement"]["partner_demanded"])
        self.assertEqual(phys["excitement"]["unsatisfied_partner"], "")
        self.assertEqual(phys["excitement"]["unsatisfied_partners"], [])
        self.assertFalse(phys["climax_state"]["partner_climaxed"])
        self.assertFalse(phys["climax_state"]["partner_climaxes"]["Elena"])
        self.assertNotIn("player reached climax spent", phys["intimate_contact"])

    def test_multi_partner_case_a_unsatisfied_targeting_and_three_partner_slot3(self):
        """Verify Case A premature finish focuses exclusively on unsatisfied partner and Slot 3 evaluates 3+ partners."""
        from mechanics.social.intimate_excitement import build_intimate_choice_blueprints
        # Case A: Elena climaxed, Kana is unsatisfied
        bp = build_intimate_choice_blueprints(
            partner_name="Elena",
            last_act="penetrative",
            player_meter=100,
            partner_meter=60,
            player_climaxed=True,
            premature_finish=True,
            partner_actors=[
                {"name": "Elena", "meter": 100, "climaxed": True, "gender": "Female"},
                {"name": "Kana", "meter": 60, "climaxed": False, "gender": "Female"},
            ],
        )
        labels = [c["label"] for c in bp["choices"]]
        # Choices should target Kana (the unsatisfied partner), not Elena (who already climaxed)!
        self.assertTrue(any("Kana toward her climax" in l for l in labels))
        self.assertTrue(any("Kana over the edge" in l for l in labels))
        self.assertFalse(any("Elena toward her climax" in l for l in labels))
        
        # 3+ partners in active intimacy: Partner C (Rin) has highest meter (85%)
        bp3 = build_intimate_choice_blueprints(
            partner_name="Elena",
            last_act="penetrative",
            player_meter=50,
            partner_meter=85,
            player_climaxed=False,
            premature_finish=False,
            partner_actors=[
                {"name": "Elena", "meter": 40, "climaxed": False, "gender": "Female"},
                {"name": "Kana", "meter": 50, "climaxed": False, "gender": "Female"},
                {"name": "Rin", "meter": 85, "climaxed": False, "gender": "Female"},
            ],
        )
        slot3_label = bp3["choices"][2]["label"]
        # Slot 3 must focus on Rin, the highest meter partner!
        self.assertIn("Rin", slot3_label)
        self.assertIn("over the edge into climax", slot3_label)

        # Test Slot 2 when Partner A has climaxed
        bp_climax = build_intimate_choice_blueprints(
            partner_name="Elena",
            last_act="penetrative",
            player_meter=60,
            partner_meter=100,
            player_climaxed=False,
            premature_finish=False,
            partner_actors=[
                {"name": "Elena", "meter": 100, "climaxed": True, "gender": "Female"},
                {"name": "Kana", "meter": 70, "climaxed": False, "gender": "Female"},
            ],
        )
        s2_label = bp_climax["choices"][1]["label"]
        self.assertIn("Elena recovers through her aftershocks", s2_label)
        self.assertNotIn("maintaining rhythm with Elena", s2_label)

    def test_multi_partner_alone_together_bystander_filtering(self):
        """Verify co-dialogue-partners are not treated as public bystanders requiring decorum."""
        from game_engine.turn.dialogue import _build_dialogue_prompt_block
        from game_engine.turn_context import TurnContext
        session = {
            "id": self.session_id,
            "scenario": "nsfw_furry_high_school_drama",
            "scenario_key": "nsfw_furry_high_school_drama",
            "dialogue_partners": ["Kana", "Elena"],
            "current_location": "Music Room",
            "current_npcs": [
                {"name": "Kana", "role": "Peer", "appearance": {"intimate_dynamic": "receptive", "erotic_openness": "uninhibited"}},
                {"name": "Elena", "role": "Peer", "appearance": {"intimate_dynamic": "playful", "erotic_openness": "moderate"}},
            ],
            "physical_state": {"intimate_contact": "none"},
        }
        ctx = TurnContext(self.session_id, session, [(self.player_char, [])])
        block = _build_dialogue_prompt_block(
            session=session,
            ctx=ctx,
            new_partners=["Kana", "Elena"],
            party=[(self.player_char, "1")],
            actions=[{"label": "Talk with Kana and Elena"}],
        )
        # Kana and Elena are alone together with player; Elena should NOT be flagged as a bystander requiring public decorum!
        self.assertNotIn("PUBLIC DECORUM & DISCRETION", block)
        self.assertIn("ALONE TOGETHER & OPEN PASSION", block)

    def test_male_npc_climax_spent_and_single_increment(self):
        """Verify male NPC partners reach spent state and do not loop-increment climaxes_count on subsequent turns."""
        phys_state = {
            "intimate_contact": "Intimate encounter with Marcus (intercourse)",
            "actors": {
                "Artemis": {"gender": "Female", "posture": "Straddling Marcus", "clothing": "Nude"},
                "Marcus": {"gender": "Male", "posture": "Beneath Artemis", "clothing": "Nude"},
            },
            "excitement": {
                "active": True,
                "actors": {
                    "Artemis": {"meter": 50, "endurance": 6, "climaxes_count": 0, "status": "Maintaining Rhythm"},
                    "Marcus": {"meter": 90, "endurance": 5, "climaxes_count": 0, "status": "On the Brink 🔥"},
                }
            },
            "climax_state": {"player_climaxed": False, "partner_climaxed": False, "partner_climaxes": {"Marcus": False}}
        }
        player_char = {"name": "Artemis", "gender": "Female", "END": 6}
        marcus_contact = {"name": "Marcus", "gender": "Male", "appearance": {"gender": "Male", "physique": "Athletic"}}

        # Turn 1: Marcus pushes over the edge into climax
        res1 = compute_excitement_step(
            physical_state=phys_state,
            action_str="Maintain steady deep thrusts with Marcus",
            player_char=player_char,
            partner_contact=marcus_contact,
        )
        self.assertTrue(res1["partner_climaxed"])
        self.assertEqual(phys_state["excitement"]["actors"]["Marcus"]["meter"], 100)
        self.assertEqual(phys_state["excitement"]["actors"]["Marcus"]["climaxes_count"], 1)
        self.assertIn("Climax Reached", phys_state["excitement"]["actors"]["Marcus"]["status"])

        # Turn 2: Continued stimulation — Marcus is male, so he must remain spent with 0 delta and NO climaxes_count increment
        res2 = compute_excitement_step(
            physical_state=phys_state,
            action_str="Maintain steady deep thrusts with Marcus",
            player_char=player_char,
            partner_contact=marcus_contact,
        )
        m_actor = phys_state["excitement"]["actors"]["Marcus"]
        self.assertEqual(m_actor["meter"], 100)
        self.assertEqual(m_actor["delta"], 0)
        self.assertEqual(m_actor["climaxes_count"], 1, "Male NPC climaxes_count should NOT increment repeatedly while spent!")
        self.assertIn("Spent", m_actor["status"])

    def test_female_pc_with_two_male_npcs(self):
        """Verify female PC with 2 male NPCs maintains multiorgasmic ongoing rhythm while male NPCs reach spent state."""
        phys_state = {
            "intimate_contact": "Intimate encounter with Leon and Ethan (intercourse)",
            "actors": {
                "Elena": {"gender": "Female", "posture": "Between Leon and Ethan", "clothing": "Nude"},
                "Leon": {"gender": "Male", "posture": "Holding Elena", "clothing": "Nude"},
                "Ethan": {"gender": "Male", "posture": "Caressing Elena", "clothing": "Nude"},
            },
            "excitement": {
                "active": True,
                "actors": {
                    "Elena": {"meter": 95, "endurance": 6, "climaxes_count": 0, "status": "On the Brink 🔥"},
                    "Leon": {"meter": 95, "endurance": 5, "climaxes_count": 0, "status": "On the Brink 🔥"},
                    "Ethan": {"meter": 40, "endurance": 5, "climaxes_count": 0, "status": "Warming Up"},
                }
            },
            "climax_state": {"player_climaxed": False, "partner_climaxed": False, "partner_climaxes": {"Leon": False, "Ethan": False}}
        }
        player_char = {"name": "Elena", "gender": "Female", "END": 6}
        leon_c = {"name": "Leon", "gender": "Male", "appearance": {"gender": "Male"}}
        ethan_c = {"name": "Ethan", "gender": "Male", "appearance": {"gender": "Male"}}

        res = compute_excitement_step(
            physical_state=phys_state,
            action_str="Shift rhythm to drive deeper into release with Leon and Ethan",
            player_char=player_char,
            partner_contact=leon_c,
            partner_contacts=[leon_c, ethan_c],
        )
        # Female PC multiorgasmic drop to 35%
        self.assertTrue(res["player_climaxed"])
        self.assertEqual(phys_state["excitement"]["actors"]["Elena"]["meter"], 35)
        self.assertIn("Hypersensitive", phys_state["excitement"]["actors"]["Elena"]["status"])
        self.assertFalse(res.get("premature_finish", False), "Female PC should not have premature finish flags!")

        # Leon reached 100% climax
        self.assertTrue(phys_state["climax_state"]["partner_climaxes"]["Leon"])
        self.assertEqual(phys_state["excitement"]["actors"]["Leon"]["meter"], 100)

        # Ethan gained warmth but has not peaked
        self.assertFalse(phys_state["climax_state"]["partner_climaxes"]["Ethan"])

    def test_multi_partner_oral_mutual_blueprints(self):
        """Verify oral_mutual (69) in multi-partner generates act-appropriate choices without mouth kissing."""
        partner_actors = [
            {"name": "Kana", "meter": 60, "climaxed": False, "gender": "Female", "spots": "fox ears"},
            {"name": "Elena", "meter": 50, "climaxed": False, "gender": "Female", "spots": "nape"},
        ]
        bp = build_intimate_choice_blueprints(
            partner_name="Kana",
            last_act="oral_mutual",
            player_meter=55,
            partner_meter=60,
            partner_actors=partner_actors,
        )
        labels = [c["label"] for c in bp["choices"]]
        # Slot 1 should maintain oral rhythm with Kana
        self.assertTrue(any("oral rhythm with eager, unwavering focus" in l for l in labels))
        # Slot 2 should caress Elena while staying close to Kana
        self.assertTrue(any("caress Elena" in l and "staying close to Kana" in l for l in labels))
        # Should NOT tell the player to mouth-to-mouth kiss while in 69
        self.assertFalse(any("Deepen your kiss" in l for l in labels))

    def test_spent_male_npc_penetrative_blueprints(self):
        """Verify spent male NPC partner blueprints adapt to recovery rather than deep thrusting inside spent partner."""
        # Single-partner female PC with spent male NPC
        bp_single = build_intimate_choice_blueprints(
            partner_name="Marcus",
            last_act="penetrative",
            player_meter=75,
            partner_meter=100,
            partner_climaxed=True,
            player_climaxed=False,
            partner_gender="Male",
        )
        single_labels = [c["label"] for c in bp_single["choices"]]
        # Slot 1 must acknowledge male NPC catching breath, NOT maintain steady deep thrusts
        self.assertTrue(any("catches his breath through his climax aftershocks" in l for l in single_labels))
        self.assertFalse(any("Maintain a steady, deep rhythm and hold Marcus" in l for l in single_labels))
        # Slot 3 must push toward own release
        self.assertTrue(any("push over the edge into your own release in Marcus's arms" in l for l in single_labels))

        # Multi-partner with Partner A (male) climaxed
        partner_actors = [
            {"name": "Marcus", "meter": 100, "climaxed": True, "gender": "Male", "spots": "shoulders"},
            {"name": "Leon", "meter": 50, "climaxed": False, "gender": "Male", "spots": "chest"},
        ]
        bp_multi = build_intimate_choice_blueprints(
            partner_name="Marcus",
            last_act="penetrative",
            player_meter=60,
            partner_meter=100,
            partner_actors=partner_actors,
            partner_gender="Male",
        )
        multi_labels = [c["label"] for c in bp_multi["choices"]]
        self.assertTrue(any("Hold Marcus close as he catches his breath" in l for l in multi_labels))

    def test_short_npc_name_word_boundary_isolation(self):
        """Verify short NPC names (e.g. Al, Dan) are not falsely matched by substrings in non-intimate or other words."""
        phys_state = {
            "intimate_contact": "Intimate encounter with Kana and Al (oral give)",
            "excitement": {
                "active": True,
                "actors": {
                    "Player": {"meter": 20, "endurance": 5, "climaxes_count": 0},
                    "Kana": {"meter": 30, "endurance": 5, "climaxes_count": 0},
                    "Al": {"meter": 30, "endurance": 5, "climaxes_count": 0},
                }
            },
            "climax_state": {"player_climaxed": False, "partner_climaxed": False, "partner_climaxes": {"Kana": False, "Al": False}}
        }
        player_char = {"name": "Player", "gender": "Male", "END": 5}
        kana_c = {"name": "Kana", "gender": "Female"}
        al_c = {"name": "Al", "gender": "Male"}

        # Action mentions "oral" and "Kana" — "Al" appears as a substring inside "oral" but should NOT be targeted
        res = compute_excitement_step(
            physical_state=phys_state,
            action_str="Focus your oral pace on Kana's core with guidance",
            player_char=player_char,
            partner_contact=kana_c,
            partner_contacts=[kana_c, al_c],
        )
        # Kana was targeted and stimulated
        self.assertGreater(phys_state["excitement"]["actors"]["Kana"]["delta"], 10)
        # Al was NOT directly stimulated; only receives passive spectator warmth (+4%)
        self.assertEqual(phys_state["excitement"]["actors"]["Al"]["delta"], 4)

    def test_discord_embed_multi_unsatisfied_and_sensitive_spot(self):
        """Verify Discord breakdown embeds display both sensitive spot and multiple unsatisfied partners."""
        from cogs.adventure.embeds import build_outcome_embeds
        outcome = {
            "narrative": "A passionate moment concluded.",
            "character_outcomes": [{"name": "Artemiusz"}],
            "intimate_update": {
                "active": True,
                "player_meter": 100,
                "partner_meter": 50,
                "player_climaxed": True,
                "partner_climaxed": False,
                "sensitive_spot_matched": True,
                "matched_spot": "Fox ears",
                "premature_finish": True,
                "unsatisfied_partners": ["Kana", "Elena"],
                "partner_meters": [
                    {"name": "Kana", "meter": 60, "delta": 15, "climaxed": False},
                    {"name": "Elena", "meter": 45, "delta": 4, "climaxed": False},
                ]
            }
        }
        embeds = build_outcome_embeds(
            outcome=outcome,
            check_field_name="🎯 Check",
            check_field_value="",
            loot_text="",
            result_display="detailed",
        )
        all_fields = []
        for em in embeds:
            all_fields.extend(em.fields)
        intimate_fields = [f for f in all_fields if "Intimate Excitement" in f.name]
        self.assertEqual(len(intimate_fields), 1)
        val = intimate_fields[0].value
        self.assertIn("Sensitive Spot:** Fox ears", val)
        self.assertIn("Kana and Elena remain unsatisfied", val)

    def test_multi_partner_unclimaxed_slot3_selection(self):
        """Verify Slot 3 selects unclimaxed high-meter partner when another partner is already spent/climaxed."""
        partner_actors = [
            {"name": "Kana", "meter": 100, "climaxed": True, "gender": "Female"},
            {"name": "Elena", "meter": 85, "climaxed": False, "gender": "Female"},
        ]
        bp = build_intimate_choice_blueprints(
            partner_name="Kana",
            last_act="penetrative",
            player_meter=50,
            partner_meter=100,
            partner_actors=partner_actors,
        )
        labels = [c["label"] for c in bp["choices"]]
        slot3_label = bp["choices"][2]["label"]
        self.assertIn("Focus your rhythm relentlessly on Elena to push her over the edge into climax", slot3_label)

    def test_premature_finish_dynamic_multi_partner_resolution(self):
        """Verify premature finish dynamically tracks remaining unsatisfied partners across turns."""
        phys_state = {
            "intimate_contact": "Intimate encounter with Kana and Elena (intercourse)",
            "climax_state": {"partner_climaxed": False, "player_climaxed": False, "partner_climaxes": {"Kana": False, "Elena": False}},
            "actors": {
                "Artemiusz": {"meter": 95, "max": 100, "delta": 0, "endurance": 5, "climaxes_count": 0, "status": "On the Brink 🔥"},
                "Kana": {"meter": 40, "max": 100, "delta": 0, "endurance": 5, "climaxes_count": 0, "status": "Arousal Building"},
                "Elena": {"meter": 40, "max": 100, "delta": 0, "endurance": 5, "climaxes_count": 0, "status": "Arousal Building"},
            },
        }
        # Turn 1: Player climaxes; both Kana and Elena are unsatisfied
        res1 = compute_excitement_step(
            physical_state=phys_state,
            action_str="Thrust deep into Kana and reach climax",
            player_char=self.player_char,
            partner_contacts=[{"name": "Kana"}, {"name": "Elena"}],
            session={"current_day": 1, "current_minute": 500},
            narrative_str="You spill deep inside Kana as your stamina is spent.",
        )
        self.assertTrue(res1["player_climaxed"])
        self.assertTrue(res1["premature_finish"])
        self.assertEqual(res1["unsatisfied_partners"], ["Kana", "Elena"])

        # Turn 2: Player is spent, but manually stimulates Kana to climax. Elena is still at 40%.
        phys_state["actors"]["Kana"]["meter"] = 95
        res2 = compute_excitement_step(
            physical_state=phys_state,
            action_str="Use your hands to stroke Kana intimately",
            player_char=self.player_char,
            partner_contacts=[{"name": "Kana"}, {"name": "Elena"}],
            session={"current_day": 1, "current_minute": 501},
            narrative_str="Kana cries out as she reaches shuddering climax under your hands.",
        )
        # Kana climaxed, but Elena is still unsatisfied
        self.assertTrue(res2["partner_climaxes"]["Kana"])
        self.assertFalse(res2["partner_climaxes"]["Elena"])
        self.assertTrue(res2["premature_finish"])
        self.assertEqual(res2["unsatisfied_partners"], ["Elena"])
        self.assertEqual(res2["unsatisfied_partner"], "Elena")

        # Turn 3: Player stimulates Elena to climax. Now both are satisfied!
        phys_state["actors"]["Elena"]["meter"] = 95
        res3 = compute_excitement_step(
            physical_state=phys_state,
            action_str="Turn to Elena and use your tongue to bring Elena to climax",
            player_char=self.player_char,
            partner_contacts=[{"name": "Kana"}, {"name": "Elena"}],
            session={"current_day": 1, "current_minute": 502},
            narrative_str="Elena arches her back in intense climax.",
        )
        self.assertTrue(res3["partner_climaxes"]["Elena"])
        self.assertFalse(res3["premature_finish"])
        self.assertEqual(res3["unsatisfied_partners"], [])
        self.assertEqual(res3["unsatisfied_partner"], "")

    def test_single_partner_oral_mutual_aftermath_blueprints(self):
        """Verify 69 (oral_mutual) adapts choices gracefully when partner has climaxed."""
        bp = build_intimate_choice_blueprints(
            partner_name="Kana",
            last_act="oral_mutual",
            player_meter=80,
            partner_meter=100,
            partner_climaxed=True,
        )
        labels = [c["label"] for c in bp["choices"]]
        # Slot 1 acknowledges Kana's recovery
        self.assertTrue(any("licking tenderly as Kana recovers through her climax" in l for l in labels))
        # Slot 3 pushes player to own release
        self.assertTrue(any("push over the edge into your own release from her mouth" in l for l in labels))

    def test_subordinate_passive_clause_does_not_falsely_target_recovering_partner(self):
        """Verify that 'as Kana recovers through her aftershocks' does not mark Kana as actively stimulated."""
        phys_state = {
            "intimate_contact": "Intimate encounter with Kana and Elena (manual pleasure)",
            "climax_state": {
                "partner_climaxed": True,
                "player_climaxed": False,
                "partner_climaxes": {"Kana": True, "Elena": False},
            },
            "excitement": {
                "active": True,
                "last_act": "manual_give",
                "actors": {
                    "Artemiusz": {"meter": 45, "max": 100, "delta": 0, "endurance": 5, "climaxes_count": 0, "status": "Arousal Building"},
                    "Kana": {"meter": 35, "max": 100, "delta": 0, "endurance": 5, "climaxes_count": 1, "status": "Spent & Satisfied (Hypersensitive)"},
                    "Elena": {"meter": 60, "max": 100, "delta": 0, "endurance": 5, "climaxes_count": 0, "status": "Breathing Heavily"},
                },
            },
        }
        res = compute_excitement_step(
            physical_state=phys_state,
            action_str="Stroke Elena with your fingers, curling against her sensitive spot as Kana recovers through her aftershocks",
            player_char=self.player_char,
            partner_contacts=[{"name": "Kana"}, {"name": "Elena"}],
            session={"current_day": 1, "current_minute": 500},
            narrative_str="Elena gasps as your fingers stroke her intimately while Kana rests warmly beside you.",
        )
        # Elena receives full active manual stimulation (+14 -> 74); Kana only receives spectator warmth and does NOT recoil
        elena_entry = next(p for p in res["partner_meters"] if p["name"] == "Elena")
        self.assertEqual(elena_entry["meter"], 74)
        self.assertFalse(phys_state["excitement"]["actors"]["Kana"].get("recoiled", False))

    def test_npc_partner_redress_and_location_transition_cleanup(self):
        """Verify restore_equipped_outfit redresses NPC partners and handle_location_transition resets intimate postures/flags."""
        from mechanics.social.physical_state import restore_equipped_outfit, handle_location_transition

        state = {
            "intimate_contact": "Aftercare with Kana and Elena (resting together)",
            "combat_focus": "none",
            "props": {"Silk Bed": "Unmade"},
            "climax_state": {
                "partner_climaxed": True,
                "player_climaxed": True,
                "partner_climaxes": {"Kana": True, "Elena": True},
            },
            "excitement": {
                "active": True,
                "last_act": "penetrative",
                "premature_finish": True,
                "partner_demanded": True,
                "unsatisfied_partner": "Elena",
                "unsatisfied_partners": ["Elena"],
                "simultaneous_partner_climax": True,
                "mutual_group_climax": True,
                "actors": {},
            },
            "actors": {
                "Artemiusz": {
                    "posture": "Kneeling between Kana's thighs, maintaining oral rhythm",
                    "clothing": {"top": "Removed", "bottom": "Removed", "under_top": "None", "under_bottom": "Removed"},
                    "holding": "Empty hands",
                },
                "Kana": {
                    "posture": "Trembling from aftershocks beside Artemiusz and Elena",
                    "clothing": {"top": "Removed", "bottom": "Removed", "under_top": "Removed", "under_bottom": "Pulled aside"},
                    "holding": "Empty hands",
                },
                "Elena": {
                    "posture": "Resting close beside Artemiusz with flushed warmth",
                    "clothing": {"top": "Unbuttoned", "bottom": "Stripped", "under_top": "Worn", "under_bottom": "Removed"},
                    "holding": "Empty hands",
                },
            },
        }
        party = [({"name": "Artemiusz", "gender": "Male"}, [{"name": "Silk Tunic", "slot": "Top"}, {"name": "Trousers", "slot": "Bottom"}])]
        redressed = restore_equipped_outfit(dict(state), party)
        self.assertEqual(redressed["actors"]["Artemiusz"]["clothing"]["top"], "Silk Tunic")
        self.assertEqual(redressed["actors"]["Kana"]["clothing"]["top"], "Clothed")
        self.assertEqual(redressed["actors"]["Kana"]["clothing"]["bottom"], "Clothed")
        self.assertEqual(redressed["actors"]["Kana"]["clothing"]["under_top"], "Worn")
        self.assertEqual(redressed["actors"]["Kana"]["clothing"]["under_bottom"], "Worn")
        self.assertEqual(redressed["actors"]["Elena"]["clothing"]["top"], "Clothed")
        self.assertEqual(redressed["actors"]["Elena"]["clothing"]["bottom"], "Clothed")

        transitioned = handle_location_transition(state, party=party, retained_names=["Kana", "Elena"])
        self.assertEqual(transitioned["actors"]["Artemiusz"]["posture"], "Standing / arriving in new area")
        self.assertEqual(transitioned["actors"]["Kana"]["posture"], "Standing / arriving in new area")
        self.assertEqual(transitioned["actors"]["Elena"]["posture"], "Standing / arriving in new area")
        self.assertFalse(transitioned["excitement"]["active"])
        self.assertFalse(transitioned["excitement"]["premature_finish"])
        self.assertEqual(transitioned["excitement"]["unsatisfied_partners"], [])
        self.assertEqual(transitioned["climax_state"]["partner_climaxes"], {})

    def test_multi_partner_climax_map_preserved_across_reducer_turns(self):
        """Verify reducers.py preserves per-partner climax history across consecutive turns."""
        from unittest.mock import patch
        from game_engine.state.reducers import _reduce_physical_state_and_memories

        current_phys = {
            "intimate_contact": "Intimate encounter with Kana and Elena (intercourse - partner reached climax, player continuing)",
            "combat_focus": "none",
            "props": {},
            "climax_state": {
                "partner_climaxed": True,
                "player_climaxed": False,
                "partner_climaxes": {"Kana": False, "Elena": True},
            },
            "excitement": {
                "active": True,
                "last_act": "penetrative",
                "actors": {
                    "Artemiusz": {"meter": 70, "max": 100, "delta": 0, "endurance": 5, "climaxes_count": 0, "status": "Breathing Heavily"},
                    "Kana": {"meter": 65, "max": 100, "delta": 0, "endurance": 5, "climaxes_count": 0, "status": "Breathing Heavily"},
                    "Elena": {"meter": 35, "max": 100, "delta": 0, "endurance": 5, "climaxes_count": 1, "status": "Spent & Satisfied (Hypersensitive)"},
                },
            },
            "actors": {
                "Artemiusz": {"posture": "Maintaining rhythm with Kana", "clothing": {"top": "Removed", "bottom": "Removed"}},
                "Kana": {"posture": "Arching back on the bed", "clothing": {"top": "Removed", "bottom": "Removed"}},
                "Elena": {"posture": "Trembling from aftershocks beside Artemiusz and Kana", "clothing": {"top": "Removed", "bottom": "Removed"}},
            },
        }
        outcome = {
            "dialogue_partners": ["Kana", "Elena"],
            "outcome_narrative": "You shift your hips and drive deeper into Kana as Elena catches her breath beside you.",
            "next_narrative": "Kana gasps, her excitement rising rapidly.",
            "physical_updates": {
                "intimate_contact": "Intimate encounter with Kana and Elena (intercourse)",
            },
            "choices": [],
        }
        actions = [{"label": "Shift your focus to Kana and thrust deeper into her as Elena rests beside you", "success": True}]
        party = [({"name": "Artemiusz", "user_id": 1, "endurance": 5, "gender": "Male"}, [])]
        contacts = [{"name": "Kana", "gender": "Female"}, {"name": "Elena", "gender": "Female"}]
        sess = {"id": 999, "current_day": 1, "current_minute": 600, "dialogue_partners": ["Kana", "Elena"]}

        with patch("db.get_session_physical_state", return_value=current_phys), \
             patch("db.update_session_physical_state"), \
             patch("db.update_contact_in_person_timestamp"), \
             patch("db.get_contacts", return_value=contacts), \
             patch("db.get_session", return_value=sess), \
             patch("db.get_character", return_value={"name": "Artemiusz", "hp": 20}):
            _reduce_physical_state_and_memories(999, sess, outcome, party, "fantasy", actions)

        upd_phys = outcome["_physical_state"]
        p_climaxes = upd_phys["climax_state"]["partner_climaxes"]
        # Elena's prior climax must be preserved, and Kana is still building toward climax
        self.assertTrue(p_climaxes["Elena"])
        self.assertFalse(p_climaxes["Kana"])

    def test_coordinate_partner_names_pronoun_normalization_and_excitement(self):
        """Verify coordinate partner phrases ('Finger Kana and Elena', 'Stroke Kana and Elena with your fingers') stimulate both partners."""
        state = {
            "intimate_contact": "Intimate encounter with Kana and Elena (manual give)",
            "excitement": {
                "active": True,
                "last_act": "manual_give",
                "actors": {
                    "Artemiusz": {"meter": 40, "max": 100, "delta": 0, "endurance": 5, "climaxes_count": 0, "status": "Aroused"},
                    "Kana": {"meter": 50, "max": 100, "delta": 0, "endurance": 5, "climaxes_count": 0, "status": "Aroused"},
                    "Elena": {"meter": 50, "max": 100, "delta": 0, "endurance": 5, "climaxes_count": 0, "status": "Aroused"},
                },
            },
            "actors": {
                "Artemiusz": {"posture": "Kneeling between Kana and Elena", "clothing": {"top": "Removed", "bottom": "Removed"}},
                "Kana": {"posture": "Lying back on the bed", "clothing": {"top": "Removed", "bottom": "Removed"}},
                "Elena": {"posture": "Lying back beside Kana", "clothing": {"top": "Removed", "bottom": "Removed"}},
            },
        }
        player = {"name": "Artemiusz", "gender": "Male", "endurance": 5}
        partners = [
            {"name": "Kana", "gender": "Female", "affinity": 80},
            {"name": "Elena", "gender": "Female", "affinity": 80},
        ]
        res = compute_excitement_step(
            physical_state=state,
            action_str="Stroke Kana and Elena with your fingers simultaneously",
            player_char=player,
            partner_contact=partners[0],
            session={"current_day": 1, "current_minute": 600},
            narrative_str="Your fingers move deftly between both Kana and Elena, making them both gasp in unison.",
            partner_contacts=partners,
        )
        self.assertEqual(res["act_type"], "manual_give")
        p_by_name = {m["name"]: m for m in res["partner_meters"]}
        self.assertGreater(p_by_name["Kana"]["delta"], 10)
        self.assertGreater(p_by_name["Elena"]["delta"], 10)

    def test_secondary_partner_genital_act_initiation_in_reducer(self):
        """Verify initiating a genital act targeting Partner B ('Elena') when dps=['Kana', 'Elena'] triggers excitement and updates intimate_contact."""
        from unittest.mock import patch
        from game_engine.state.reducers import _reduce_physical_state_and_memories

        current_phys = {
            "intimate_contact": "Kissing with Kana and Elena",
            "combat_focus": "none",
            "props": {},
            "climax_state": {"partner_climaxed": False, "player_climaxed": False, "partner_climaxes": {}},
            "actors": {
                "Artemiusz": {"posture": "On the bed with Kana and Elena", "clothing": {"top": "Removed", "bottom": "Removed"}},
                "Kana": {"posture": "Lying on the bed", "clothing": {"top": "Removed", "bottom": "Removed"}},
                "Elena": {"posture": "Lying beside Kana", "clothing": {"top": "Removed", "bottom": "Removed"}},
            },
        }
        outcome = {
            "dialogue_partners": ["Kana", "Elena"],
            "outcome_narrative": "You kneel between Elena's thighs and kiss down her stomach, licking her slick core as Kana watches.",
            "next_narrative": "Elena arches her back with a breathless cry.",
            "physical_updates": {},
            "choices": [],
        }
        actions = [{"label": "Kneel and lick Elena's clit while caressing Kana's thigh", "success": True}]
        party = [({"name": "Artemiusz", "user_id": 1, "endurance": 5, "gender": "Male"}, [])]
        contacts = [{"name": "Kana", "gender": "Female"}, {"name": "Elena", "gender": "Female"}]
        sess = {"id": 999, "current_day": 1, "current_minute": 600, "dialogue_partners": ["Kana", "Elena"]}

        with patch("db.get_session_physical_state", return_value=current_phys), \
             patch("db.update_session_physical_state"), \
             patch("db.update_contact_in_person_timestamp"), \
             patch("db.get_contacts", return_value=contacts), \
             patch("db.get_session", return_value=sess), \
             patch("db.get_character", return_value={"name": "Artemiusz", "hp": 20}):
            _reduce_physical_state_and_memories(999, sess, outcome, party, "fantasy", actions)

        upd_phys = outcome["_physical_state"]
        self.assertIn("intimate encounter with kana and elena (oral give)", upd_phys["intimate_contact"].lower())
        self.assertIsNotNone(outcome.get("intimate_update"))
        self.assertEqual(outcome["intimate_update"]["act_type"], "oral_give")

    def test_dialogue_partner_switch_clears_erotic_state_without_triggering_on_new_npc(self):
        """Verify switching dialogue partner to an unrelated NPC clears intimate_contact and does not run excitement on the new NPC."""
        from unittest.mock import patch
        from game_engine.state.reducers import _reduce_physical_state_and_memories

        current_phys = {
            "intimate_contact": "Intimate encounter with Kana and Elena (intercourse)",
            "combat_focus": "none",
            "props": {},
            "climax_state": {"partner_climaxed": True, "player_climaxed": False, "partner_climaxes": {"Kana": True, "Elena": False}},
            "excitement": {
                "active": True,
                "last_act": "penetrative",
                "actors": {
                    "Artemiusz": {"meter": 60, "max": 100, "delta": 0, "endurance": 5, "climaxes_count": 0, "status": "Aroused"},
                    "Kana": {"meter": 35, "max": 100, "delta": 0, "endurance": 5, "climaxes_count": 1, "status": "Spent"},
                    "Elena": {"meter": 55, "max": 100, "delta": 0, "endurance": 5, "climaxes_count": 0, "status": "Aroused"},
                },
            },
            "actors": {
                "Artemiusz": {"posture": "Standing in the hallway", "clothing": {"top": "Clothed", "bottom": "Clothed"}},
                "Marcus": {"posture": "Standing by the door", "clothing": {"top": "Clothed", "bottom": "Clothed"}},
            },
        }
        outcome = {
            "dialogue_partners": ["Marcus"],
            "outcome_narrative": "You ask Marcus about the guard patrol schedule.",
            "next_narrative": "Marcus nods and hands you the roster.",
            "physical_updates": {},
            "choices": [],
        }
        actions = [{"label": "Ask Marcus about the patrol schedule", "success": True}]
        party = [({"name": "Artemiusz", "user_id": 1, "endurance": 5, "gender": "Male"}, [])]
        contacts = [{"name": "Marcus", "gender": "Male"}]
        sess = {"id": 999, "current_day": 1, "current_minute": 620, "dialogue_partners": ["Marcus"]}

        with patch("db.get_session_physical_state", return_value=current_phys), \
             patch("db.update_session_physical_state"), \
             patch("db.update_contact_in_person_timestamp"), \
             patch("db.get_contacts", return_value=contacts), \
             patch("db.get_session", return_value=sess), \
             patch("db.get_character", return_value={"name": "Artemiusz", "hp": 20}):
            _reduce_physical_state_and_memories(999, sess, outcome, party, "fantasy", actions)

        upd_phys = outcome["_physical_state"]
        self.assertEqual(upd_phys["intimate_contact"], "none")
        self.assertFalse(upd_phys["excitement"]["active"])
        self.assertIsNone(outcome.get("intimate_update"))

    def test_detect_partner_climax_transitive_and_cross_clause_disambiguation(self):
        """Verify detect_partner_climax disambiguates transitive climax phrases and prevents cross-clause false positives."""
        from mechanics.social.physical_state import detect_partner_climax

        txt1 = "You sent Kana over the edge while Elena watches breathlessly."
        self.assertTrue(detect_partner_climax(txt1, "Kana", ["Elena"]))
        self.assertFalse(detect_partner_climax(txt1, "Elena", ["Kana"]))

        txt2 = "While Elena watches, Kana climaxes hard against your hand."
        self.assertTrue(detect_partner_climax(txt2, "Kana", ["Elena"]))
        self.assertFalse(detect_partner_climax(txt2, "Elena", ["Kana"]))

        txt3 = "Kana climaxes first, and moments later you send Elena over the edge."
        self.assertTrue(detect_partner_climax(txt3, "Kana", ["Elena"]))
        self.assertTrue(detect_partner_climax(txt3, "Elena", ["Kana"]))

    def test_multi_partner_blueprint_choices_continuity_and_climax_classification(self):
        """Verify multi-partner Slot 2 & Slot 3 blueprint choices maintain active genital continuity and advance meters."""
        partner_actors = [
            {"name": "Kana", "gender": "Female", "meter": 85, "climaxed": False, "spots": ["inner thighs"]},
            {"name": "Elena", "gender": "Female", "meter": 82, "climaxed": False, "spots": ["nape of neck"]},
        ]
        bp = build_intimate_choice_blueprints(
            partner_name="Kana",
            last_act="penetrative",
            partner_gender="Female",
            player_meter=75,
            partner_meter=85,
            player_climaxed=False,
            partner_climaxed=False,
            premature_finish=False,
            partner_demanded=False,
            partner_actors=partner_actors,
        )
        slot3_dual = bp["choices"][2]["label"]
        self.assertIn("Coordinate your touch between both Kana and Elena", slot3_dual)

        phys_state = {
            "intimate_contact": "Intimate encounter with Kana and Elena (intercourse)",
            "climax_state": {"partner_climaxed": False, "player_climaxed": False, "partner_climaxes": {"Kana": False, "Elena": False}},
            "excitement": {
                "active": True,
                "last_act": "penetrative",
                "actors": {
                    "Artemiusz": {"meter": 75, "max": 100, "delta": 0, "endurance": 5, "climaxes_count": 0, "status": "On the Brink"},
                    "Kana": {"meter": 90, "max": 100, "delta": 0, "endurance": 5, "climaxes_count": 0, "status": "On the Brink"},
                    "Elena": {"meter": 90, "max": 100, "delta": 0, "endurance": 5, "climaxes_count": 0, "status": "On the Brink"},
                },
            },
        }
        contacts = [
            {"name": "Kana", "gender": "Female", "appearance": {"sensitive_spots": ["Inner thighs"]}},
            {"name": "Elena", "gender": "Female", "appearance": {"sensitive_spots": ["Nape of neck"]}},
        ]
        res = compute_excitement_step(
            physical_state=phys_state,
            action_str=slot3_dual,
            player_char=self.player_char,
            partner_contact=contacts[0],
            session={"current_day": 1, "current_minute": 600},
            narrative_str="You coordinate your rhythm between both Kana and Elena.",
            partner_contacts=contacts,
        )
        self.assertEqual(res["act_type"], "penetrative")
        self.assertTrue(res["partner_climaxes"]["Kana"])
        self.assertTrue(res["partner_climaxes"]["Elena"])
        self.assertTrue(res["simultaneous_partner_climax"])

        # Also verify Slot 2 for oral_give, manual_receive, and oral_mutual
        bp_og = build_intimate_choice_blueprints(
            partner_name="Kana",
            last_act="oral_give",
            partner_gender="Female",
            player_meter=40,
            partner_meter=50,
            player_climaxed=False,
            partner_climaxed=False,
            premature_finish=False,
            partner_demanded=False,
            partner_actors=partner_actors,
        )
        cl_og = classify_intimate_act(
            action_str=bp_og["choices"][1]["label"],
            intimate_contact_str="Intimate encounter with Kana and Elena (oral give)",
            player_name="Artemiusz",
            partner_name="Elena",
            partner_contact=contacts[1],
        )
        self.assertEqual(cl_og["act_type"], "oral_give")
        self.assertTrue(cl_og["partner_stimulated"])
        self.assertTrue(cl_og["sensitive_spot_matched"])

    def test_cross_clause_partner_scoping_prevents_act_spot_and_turn_off_bleed(self):
        """Verify multi-partner actions with separate clauses for each partner do not bleed genital acts or sensitive spots across partners."""
        phys_state = {
            "intimate_contact": "Intimate encounter with Kana and Elena (oral give)",
            "climax_state": {"partner_climaxed": False, "player_climaxed": False, "partner_climaxes": {"Kana": False, "Elena": False}},
            "excitement": {
                "active": True,
                "last_act": "oral_give",
                "actors": {
                    "Artemiusz": {"meter": 30, "max": 100, "delta": 0, "endurance": 6, "climaxes_count": 0, "status": "Warming Up"},
                    "Kana": {"meter": 40, "max": 100, "delta": 0, "endurance": 6, "climaxes_count": 0, "status": "Arousal Building"},
                    "Elena": {"meter": 40, "max": 100, "delta": 0, "endurance": 6, "climaxes_count": 0, "status": "Arousal Building"},
                },
            },
        }
        contacts = [
            {"name": "Kana", "gender": "Female", "appearance": {"sensitive_spots": ["Inner thighs"], "turn_offs": ["Rough handling"]}},
            {"name": "Elena", "gender": "Female", "appearance": {"sensitive_spots": ["Inner thighs"], "turn_offs": ["Rough handling"]}},
        ]
        # Player licks Elena's clit (no inner thighs mentioned for Elena) while caressing Kana's inner thighs (non-genital for Kana)
        res = compute_excitement_step(
            physical_state=phys_state,
            action_str="Kneel and lick Elena's clit while caressing Kana's inner thighs",
            player_char=self.player_char,
            partner_contact=contacts[0],
            session={"current_day": 1, "current_minute": 600},
            narrative_str="You lick Elena's clit while caressing Kana's inner thighs.",
            partner_contacts=contacts,
        )
        self.assertEqual(res["act_type"], "oral_give")
        # Elena gets oral_give without Kana's inner thighs sensitive spot bonus bleeding onto her
        expected_elena_delta = calculate_excitement_delta(18, phys_state["excitement"]["actors"]["Elena"]["endurance"], sensitive_spot_bonus=False)
        self.assertEqual(phys_state["excitement"]["actors"]["Elena"]["delta"], expected_elena_delta)
        # Kana gets non-genital secondary foreplay warmth (4 base + 6 sensitive spot bonus = 10), not full oral_give
        self.assertEqual(phys_state["excitement"]["actors"]["Kana"]["delta"], 10)

    def test_group_dialogue_confession_does_not_bleed_to_co_partner(self):
        """Verify confessing to Kana in a group dialogue with Kana and Elena does not promote Elena to romantic track."""
        from game_engine.state.reducers import _evaluate_npc_milestones

        sess = {"dialogue_partner": "Kana", "dialogue_partners": ["Kana", "Elena"]}
        actions = [{"label": "Confess your feelings to Kana and ask her to date you", "check": {"success": True}}]

        mem_k, _, _, _, track_k, _, _ = _evaluate_npc_milestones(
            npc_name="Kana",
            app_dict={},
            track="platonic",
            milestone_ev="confession",
            custom_summary=None,
            intercourse_exp="virgin",
            oral_exp="inexperienced",
            actions=actions,
            narrative_text="Kana blushes and accepts your confession while Elena smiles nearby.",
            overall_check_success=True,
            is_player_romantic_action=True,
            is_player_intimate_action=False,
            is_player_oral_action=False,
            is_player_intercourse_action=False,
            is_player_confession_action=True,
            is_player_affection_action=False,
            affection_target_npc=None,
            gift_target_npc=None,
            gift_item_name=None,
            confession_target_npc="Kana",
            first_char_name="Artemiusz",
            session=sess,
        )
        self.assertEqual(track_k, "romantic")
        self.assertIsNotNone(mem_k)

        mem_e, _, _, _, track_e, _, _ = _evaluate_npc_milestones(
            npc_name="Elena",
            app_dict={},
            track="platonic",
            milestone_ev="none",
            custom_summary=None,
            intercourse_exp="virgin",
            oral_exp="inexperienced",
            actions=actions,
            narrative_text="Kana blushes and accepts your confession while Elena smiles nearby.",
            overall_check_success=True,
            is_player_romantic_action=True,
            is_player_intimate_action=False,
            is_player_oral_action=False,
            is_player_intercourse_action=False,
            is_player_confession_action=True,
            is_player_affection_action=False,
            affection_target_npc=None,
            gift_target_npc=None,
            gift_item_name=None,
            confession_target_npc="Kana",
            first_char_name="Artemiusz",
            session=sess,
        )
        self.assertEqual(track_e, "platonic")
        self.assertIsNone(mem_e)

    def test_group_dialogue_tier2_intimate_milestone_does_not_bleed_to_co_partner(self):
        """Verify penetrative intercourse with Kana while kissing Elena does not mark Elena as non_virgin."""
        from game_engine.state.reducers import _evaluate_npc_milestones

        sess = {"dialogue_partner": "Kana", "dialogue_partners": ["Kana", "Elena"]}
        actions = [{"label": "Draw Elena into your embrace, kissing her passionately while thrusting deeply into Kana", "check": {"success": True}}]
        nar = "You kiss Elena passionately while thrusting deeply inside Kana."

        mem_k, exp_k, _, _, _, _, _ = _evaluate_npc_milestones(
            npc_name="Kana",
            app_dict={},
            track="platonic",
            milestone_ev="",
            custom_summary=None,
            intercourse_exp="virgin",
            oral_exp="inexperienced",
            actions=actions,
            narrative_text=nar,
            overall_check_success=True,
            is_player_romantic_action=True,
            is_player_intimate_action=True,
            is_player_oral_action=False,
            is_player_intercourse_action=True,
            is_player_confession_action=False,
            is_player_affection_action=False,
            affection_target_npc=None,
            gift_target_npc=None,
            gift_item_name=None,
            confession_target_npc=None,
            first_char_name="Artemiusz",
            session=sess,
        )
        self.assertEqual(exp_k, "non_virgin")
        self.assertIsNotNone(mem_k)

        mem_e, exp_e, _, _, _, _, _ = _evaluate_npc_milestones(
            npc_name="Elena",
            app_dict={},
            track="platonic",
            milestone_ev="",
            custom_summary=None,
            intercourse_exp="virgin",
            oral_exp="inexperienced",
            actions=actions,
            narrative_text=nar,
            overall_check_success=True,
            is_player_romantic_action=True,
            is_player_intimate_action=True,
            is_player_oral_action=False,
            is_player_intercourse_action=True,
            is_player_confession_action=False,
            is_player_affection_action=False,
            affection_target_npc=None,
            gift_target_npc=None,
            gift_item_name=None,
            confession_target_npc=None,
            first_char_name="Artemiusz",
            session=sess,
        )
        self.assertEqual(exp_e, "virgin")
        self.assertTrue(mem_e and "kiss" in mem_e.lower())

    def test_partial_partner_climax_during_premature_finish_updates_posture(self):
        """Verify that when a spent male player brings one of two unsatisfied partners to climax, her posture updates to aftershocks."""
        from unittest.mock import patch
        from game_engine.state.reducers import _reduce_physical_state_and_memories

        current_phys = {
            "intimate_contact": "Intimate encounter with Kana and Elena (player reached climax spent, partner unsatisfied)",
            "combat_focus": "none",
            "props": {},
            "climax_state": {"partner_climaxed": False, "player_climaxed": True, "partner_climaxes": {"Kana": False, "Elena": False}},
            "excitement": {
                "active": True,
                "last_act": "penetrative",
                "premature_finish": True,
                "partner_demanded": True,
                "unsatisfied_partner": "Kana",
                "unsatisfied_partners": ["Kana", "Elena"],
                "actors": {
                    "Artemiusz": {"meter": 100, "max": 100, "delta": 0, "endurance": 5, "climaxes_count": 1, "status": "Spent"},
                    "Kana": {"meter": 90, "max": 100, "delta": 0, "endurance": 5, "climaxes_count": 0, "status": "On the Brink"},
                    "Elena": {"meter": 50, "max": 100, "delta": 0, "endurance": 5, "climaxes_count": 0, "status": "Deepening Pleasure"},
                },
            },
            "actors": {
                "Artemiusz": {"posture": "Catching breath on the bed", "clothing": {"top": "Removed", "bottom": "Removed"}},
                "Kana": {"posture": "Resting close beside Artemiusz with flushed warmth", "clothing": {"top": "Removed", "bottom": "Removed"}},
                "Elena": {"posture": "Resting close beside Artemiusz with flushed warmth", "clothing": {"top": "Removed", "bottom": "Removed"}},
            },
        }
        outcome = {
            "dialogue_partners": ["Kana", "Elena"],
            "outcome_narrative": "You use your fingers to stroke Kana to a trembling climax while Elena watches.",
            "next_narrative": "Elena looks at you with lingering need.",
            "physical_updates": {},
            "choices": [],
        }
        actions = [{"label": "Use your fingers to stroke and please Kana toward her climax", "success": True}]
        party = [({"name": "Artemiusz", "user_id": 1, "endurance": 5, "gender": "Male"}, [])]
        contacts = [
            {"name": "Kana", "gender": "Female"},
            {"name": "Elena", "gender": "Female"},
        ]
        sess = {"id": 999, "current_day": 1, "current_minute": 620, "dialogue_partners": ["Kana", "Elena"]}

        with patch("db.get_session_physical_state", return_value=current_phys), \
             patch("db.update_session_physical_state"), \
             patch("db.update_contact_in_person_timestamp"), \
             patch("db.get_contacts", return_value=contacts), \
             patch("db.get_session", return_value=sess), \
             patch("db.get_character", return_value={"name": "Artemiusz", "hp": 20}):
            _reduce_physical_state_and_memories(999, sess, outcome, party, "nsfw_high_school_drama", actions)

        upd_phys = outcome["_physical_state"]
        self.assertTrue(upd_phys["climax_state"]["partner_climaxes"]["Kana"])
        self.assertFalse(upd_phys["climax_state"]["partner_climaxes"]["Elena"])
        self.assertIn("Trembling from aftershocks beside Artemiusz and Elena", upd_phys["actors"]["Kana"]["posture"])

    def test_dialogue_intent_preserves_multi_partner_group_on_single_partner_action(self):
        """Verify _compute_dialogue_intent keeps all current_partners when addressing one member of an active group."""
        from game_engine.turn.dialogue import _compute_dialogue_intent

        session = {
            "id": self.session_id,
            "scenario": "nsfw_furry_high_school_drama",
            "current_location": "Private Quarters",
            "dialogue_partner": "Kana",
            "dialogue_partners": ["Kana", "Elena"],
            "current_npcs": [{"name": "Kana"}, {"name": "Elena"}],
        }
        new_partners, exited = _compute_dialogue_intent(
            session,
            [{"label": "Shift your attention to Elena, caressing her nape while tasting her intimately", "stat": "PER"}],
        )
        self.assertFalse(exited)
        self.assertEqual(new_partners, ["Kana", "Elena"])

        new_partners_2, exited_2 = _compute_dialogue_intent(
            session,
            [{"label": "Use your fingers to stroke and please Kana toward her climax", "stat": "AGI"}],
        )
        self.assertFalse(exited_2)
        self.assertEqual(new_partners_2, ["Kana", "Elena"])

    def test_multi_partner_oral_mutual_staying_close_to_and_primacy_act(self):
        """Verify multi-partner oral_mutual Slot 2 ('while staying close to') stimulates both partners and player."""
        elena_contact = {
            "name": "Elena",
            "appearance": {
                "physique": "Slender & Graceful",
                "intimate_dynamic": "Switch",
                "erotic_openness": "warm",
                "sensitive_spots": ["Neck", "Ears"],
            },
            "traits": ["Gentle"],
        }
        phys_state = {
            "intimate_contact": "Intimate encounter with Kana and Elena (oral mutual)",
            "climax_state": {"partner_climaxed": False, "player_climaxed": False, "partner_climaxes": {"Kana": False, "Elena": False}},
            "excitement": {
                "active": True,
                "last_act": "oral_mutual",
                "current_partners": ["Kana", "Elena"],
                "actors": {
                    "Artemiusz": {"meter": 40, "max": 100, "delta": 0, "endurance": 8, "climaxes_count": 0, "status": "Arousal Building"},
                    "Kana": {"meter": 50, "max": 100, "delta": 0, "endurance": 6, "climaxes_count": 0, "status": "Maintaining Rhythm"},
                    "Elena": {"meter": 30, "max": 100, "delta": 0, "endurance": 6, "climaxes_count": 0, "status": "Arousal Building"},
                },
            },
        }
        res = compute_excitement_step(
            physical_state=phys_state,
            action_str="Reach with your hands to caress Elena's neck while staying close to Kana",
            player_char=self.player_char,
            partner_contact=self.partner_contact,
            session={"current_day": 1, "current_minute": 600},
            narrative_str="You caress Elena's sensitive neck while maintaining your mutual oral rhythm with Kana.",
            partner_contacts=[self.partner_contact, elena_contact],
        )
        self.assertEqual(res["act_type"], "oral_mutual")
        self.assertGreater(res["player_delta"], 0)
        self.assertGreater(res["actors"]["Kana"]["delta"], 0)
        self.assertGreater(res["actors"]["Elena"]["delta"], 0)
        self.assertTrue(res["sensitive_spot_matched"])

    def test_infer_last_act_and_multi_partner_discovery_with_single_dialogue_partner(self):
        """Verify infer_last_act_from_state normalizes partner names from phys_state and build_physical_prompt_block discovers co-partners."""
        from mechanics.social.physical_state import build_physical_prompt_block
        from mechanics.social.intimate_excitement import infer_last_act_from_state

        phys_state = {
            "intimate_contact": "Intimate encounter with Kana and Elena (oral receive)",
            "climax_state": {"partner_climaxed": False, "player_climaxed": False, "partner_climaxes": {"Kana": False, "Elena": False}},
            "excitement": {
                "active": True,
                "last_act": "oral_receive",
                "current_partners": ["Kana", "Elena"],
                "actors": {
                    "Artemiusz": {"meter": 50, "status": "Maintaining Rhythm"},
                    "Kana": {"meter": 60, "status": "Maintaining Rhythm"},
                    "Elena": {"meter": 40, "status": "Arousal Building"},
                },
            },
            "actors": {
                "Artemiusz": {"posture": "Sitting back on the bed", "clothing": {"top": "Removed", "bottom": "Removed"}},
                "Kana": {"posture": "Kneeling between Artemiusz's thighs", "clothing": {"top": "Removed", "bottom": "Removed"}},
                "Elena": {"posture": "Kneeling beside Artemiusz", "clothing": {"top": "Removed", "bottom": "Removed"}},
            },
        }
        # Action uses partner's name instead of pronoun ("Stroke Elena's core")
        inferred = infer_last_act_from_state(phys_state, action_str="Stroke Elena's core")
        self.assertEqual(inferred, "manual_give")

        # Session only has single dialogue_partner="Kana", but physical state has Kana and Elena
        sess_single_dp = {
            "id": 0,
            "scenario": "nsfw_furry_high_school_drama",
            "dialogue_partner": "Kana",
            "physical_state": phys_state,
        }
        prompt_block = build_physical_prompt_block(
            session=sess_single_dp,
            party=[(self.player_char, [])],
            is_nsfw=True,
        )
        self.assertIn("MULTI-PARTNER HYBRID CHOICE BLUEPRINTS", prompt_block)
        self.assertIn("Kana and Elena", prompt_block)

    def test_aftercare_contradiction_allows_unclimaxed_partner_when_spent_or_ended(self):
        """Verify has_state_contradiction_in_choice allows aftercare choices for unclimaxed partners once spent or ended."""
        partner_climaxes = {"Kana": True, "Elena": False}

        # Mid-encounter (last_act="penetrative", player_spent=False, partner_climaxed=False): aftercare is premature
        self.assertTrue(has_state_contradiction_in_choice(
            "Hold Elena close in sweet aftercare",
            last_act="penetrative",
            partner_climaxed=False,
            player_spent=False,
            partner_climaxes={"Kana": False, "Elena": False},
        ))

        # Encounter ended (last_act="none", player_spent=True): aftercare with Elena is valid even though Elena didn't climax
        self.assertFalse(has_state_contradiction_in_choice(
            "Hold Elena close in tender aftercare and trace gentle circles along her neck",
            last_act="none",
            partner_climaxed=True,
            player_spent=True,
            partner_climaxes=partner_climaxes,
        ))

        # However, claiming Elena is having climax tremors is still rejected
        self.assertTrue(has_state_contradiction_in_choice(
            "Hold Elena through her tremors in sweet warmth",
            last_act="none",
            partner_climaxed=True,
            player_spent=True,
            partner_climaxes=partner_climaxes,
        ))

    def test_intimate_choices_never_receive_bounty_or_story_quest_icons_or_prop_splicing(self):
        """Regression test: intimate choices must never get BOUNTY / STORY QUEST icons or splice investigation props."""
        from game_engine.choices_cleaner import clean_choices_impl
        from cogs.adventure.embeds import _get_choice_quest_icon
        from mechanics.social.physical_state import build_physical_prompt_block
        from mechanics.social.intimate_excitement import is_intimate_action_label

        polluted_bounty_lbl = (
            "Keep fucking her through the aftershocks and reach under her skirt to pull out "
            "that water-stained paper wedged by the bench"
        )
        polluted_story_lbl = (
            "Ease out, catch your breath, and smooth the doctored script page flat to study "
            "the handwriting properly"
        )

        self.assertTrue(is_intimate_action_label(polluted_bounty_lbl))
        self.assertTrue(
            has_state_contradiction_in_choice(
                polluted_bounty_lbl,
                last_act="penetrative",
                partner_climaxed=True,
                player_meter=65,
                partner_meter=100,
            )
        )
        self.assertTrue(
            has_state_contradiction_in_choice(
                polluted_story_lbl,
                last_act="penetrative",
                partner_climaxed=True,
                player_meter=65,
                partner_meter=100,
            )
        )

        # Even if a raw choice has quest flags or prefixes on an intimate label, _get_choice_quest_icon returns None
        self.assertIsNone(
            _get_choice_quest_icon({
                "label": f"🎯 {polluted_bounty_lbl}",
                "is_quest_action": True,
                "contract_type": "bounty",
            })
        )
        self.assertIsNone(
            _get_choice_quest_icon({
                "label": "⭐ Maintain a steady, deep rhythm and hold Kana through her climax aftershocks",
                "is_quest_action": True,
                "is_story_quest": True,
                "quest_id": "sq-1",
            })
        )

        # Active penetrative encounter in DB: clean_choices_impl strips spliced quest choices & clears all quest flags
        phys_state = {
            "intimate_contact": "Intimate encounter with Kana (intercourse; partner reached climax)",
            "climax_state": {"partner_climaxed": True, "player_climaxed": False, "partner_climaxes": {"Kana": True}},
            "props": {"water-stained paper": "wedged by the bench", "doctored script page": "on the bench"},
            "excitement": {
                "active": True,
                "last_act": "penetrative",
                "current_partners": ["Kana"],
                "actors": {
                    "Artemiusz": {"meter": 65, "status": "Maintaining Rhythm"},
                    "Kana": {"meter": 100, "status": "Climax! 💥"},
                },
            },
            "actors": {
                "Artemiusz": {"posture": "Standing behind Kana", "clothing": {"top": "Clothed", "bottom": "Displaced"}},
                "Kana": {"posture": "Bent over the bench", "clothing": {"top": "Clothed", "bottom": "Displaced"}},
            },
        }
        db.update_session_physical_state(self.session_id, phys_state)

        raw_choices = [
            {
                "label": f"🎯 [BOUNTY] {polluted_bounty_lbl}",
                "stat": "PER",
                "requirement": 7,
                "is_quest_action": True,
            },
            {
                "label": f"⭐ [STORY QUEST] {polluted_story_lbl}",
                "stat": "INT",
                "requirement": 6,
                "is_quest_action": True,
                "is_story_quest": True,
                "quest_id": "sq-main",
            },
        ]
        cleaned = clean_choices_impl(
            None,
            raw_choices,
            scenario="nsfw_furry_high_school_drama",
            location="Backstage Storage",
            char=self.player_char,
            dialogue_partner="Kana",
            session_id=self.session_id,
        )
        self.assertTrue(len(cleaned) >= 3)
        for c in cleaned:
            self.assertFalse(c.get("is_quest_action"))
            self.assertFalse(c.get("is_story_quest"))
            self.assertFalse(c.get("is_climax_action"))
            self.assertEqual(c.get("quest_id", ""), "")
            self.assertIsNone(_get_choice_quest_icon(c))
            self.assertNotIn("water-stained paper", c["label"].lower())
            self.assertNotIn("doctored script", c["label"].lower())

        # Physical prompt block during erotic contact omits leftover Props in Vicinity
        sess_dict = db.get_session(self.session_id)
        sess_dict["physical_state"] = phys_state
        p_block = build_physical_prompt_block(session=sess_dict, party=[(self.player_char, [])], is_nsfw=True)
        self.assertNotIn("Props in Vicinity", p_block)
        self.assertIn("NEVER splice quest objectives", p_block)

    def test_waypoint_prompt_and_erotic_climax_quest_guard(self):
        """Verify waypoint prompt block is suppressed during intimacy/aftercare and erotic climax does not complete story quest."""
        from mechanics.world.waypoints.core import build_waypoint_prompt_block
        from mechanics.world.waypoints.choices import tag_and_enrich_quest_choices

        phys_aftercare = {
            "intimate_contact": "Cuddling / aftercare with Kana",
            "climax_state": {"partner_climaxed": True, "player_climaxed": True},
        }
        db.update_session_physical_state(self.session_id, phys_aftercare)
        self.assertEqual(build_waypoint_prompt_block(self.session_id, "Backstage Storage"), "")

        tagged = tag_and_enrich_quest_choices(
            [{"label": "Hold Kana close in sweet aftercare", "stat": "CHA", "requirement": 5, "is_quest_action": True}],
            self.session_id,
            "Backstage Storage",
        )
        self.assertFalse(tagged[0].get("is_quest_action"))

    def test_through_word_boundary_and_turn_off_immunity(self):
        """Verify 'through' does not substring match 'rough', and liked acts prevent false turn-offs."""
        from mechanics.social.persona.intimacy.logic import is_turn_off_triggered

        to_str = "Clumsy / careless rough handling"
        likes_str = "Rough handling & firm grips, Face-to-face missionary"

        # 1. 'through her aftershocks' should NEVER trigger 'rough' turn-off
        self.assertFalse(is_turn_off_triggered("Keep fucking her through the aftershocks", to_str, likes_str))
        self.assertFalse(is_turn_off_triggered("Trembling through it softly", to_str, likes_str))

        # 2. Liked acts are immune to turn-off triggers
        self.assertFalse(is_turn_off_triggered("Use rough handling & firm grips on her waist", to_str, likes_str))

        # 3. Explicit clumsy/careless actions still correctly trigger turn-off
        self.assertTrue(is_turn_off_triggered("Carelessly yank her hair hard", to_str, likes_str))
        self.assertTrue(is_turn_off_triggered("Painful grip and clumsy bruising squeeze", to_str, likes_str))

    def test_item_retrieval_does_not_trigger_movement_or_disengagement(self):
        """Verify retrieving an item during intimacy does not trigger spatial movement or intimate disengagement."""
        from mechanics.world.locations.movement import is_movement_action, extract_movement_destination
        from mechanics.social.physical_state import detect_intimate_disengagement

        act_text = "Keep fucking her through the aftershocks and reach under her skirt to pull out that water-stained paper wedged by the bench"

        # Movement detection must be False
        self.assertFalse(is_movement_action(act_text))

        # Disengagement detection must be False
        self.assertFalse(detect_intimate_disengagement([{"label": act_text}]))

        # Destination extraction must not match 'keep' to a fantasy castle or trigger movement
        dest = extract_movement_destination(act_text, self.session_id, current_zone="Cultural Union & Performing Arts Annex", scen_key="nsfw_furry_high_school_drama")
        self.assertIsNone(dest)

    def test_decay_grace_period_two_turns_zero_loss(self):
        """Verify 2-turn grace period ('Lingering Heat' and 'Catching Breath') incurs 0% excitement decay."""
        phys_state = {
            "intimate_contact": "Intimate encounter with Kana (intercourse)",
            "climax_state": {"partner_climaxed": False, "player_climaxed": False},
            "excitement": {
                "active": True,
                "actors": {
                    "Artemiusz": {"meter": 60, "delta": 15, "status": "Maintaining Rhythm", "idle_turns": 0},
                    "Kana": {"meter": 60, "delta": 15, "status": "Deepening Pleasure", "idle_turns": 0},
                },
            },
        }

        # Turn 1: Conversational dialogue (Stimulation paused)
        step1 = compute_excitement_step(
            physical_state=phys_state,
            action_str="Look into her eyes and talk about our past together",
            player_char=self.player_char,
            partner_contact=self.partner_contact,
            session={"id": self.session_id, "current_day": 1, "current_minute": 500},
        )
        actors = phys_state["excitement"]["actors"]
        self.assertEqual(actors["Artemiusz"]["idle_turns"], 1)
        self.assertEqual(actors["Kana"]["idle_turns"], 1)
        self.assertEqual(actors["Artemiusz"]["meter"], 60)
        self.assertEqual(actors["Kana"]["meter"], 60)
        self.assertEqual(actors["Artemiusz"]["delta"], 0)
        self.assertEqual(actors["Kana"]["delta"], 0)
        self.assertEqual(actors["Artemiusz"]["status"], "Lingering Heat 🔥")
        self.assertEqual(actors["Kana"]["status"], "Lingering Heat 🔥")

        # Turn 2: Catching breath (Still within grace period)
        step2 = compute_excitement_step(
            physical_state=phys_state,
            action_str="Pause a moment to catch your breath together against the piano",
            player_char=self.player_char,
            partner_contact=self.partner_contact,
            session={"id": self.session_id, "current_day": 1, "current_minute": 502},
        )
        actors = phys_state["excitement"]["actors"]
        self.assertEqual(actors["Artemiusz"]["idle_turns"], 2)
        self.assertEqual(actors["Kana"]["idle_turns"], 2)
        self.assertEqual(actors["Artemiusz"]["meter"], 60)
        self.assertEqual(actors["Kana"]["meter"], 60)
        self.assertEqual(actors["Artemiusz"]["status"], "Catching Breath 💨")
        self.assertEqual(actors["Kana"]["status"], "Catching Breath 💨")

    def test_decay_after_grace_period_with_aroused_halved(self):
        """Verify Turn 3+ decay with active Aroused status is halved from -10% to -5%."""
        player_with_aroused = dict(self.player_char)
        player_with_aroused["status_effects"] = ["Aroused [3 turns]"]
        partner_with_aroused = dict(self.partner_contact)
        partner_with_aroused["status_effects"] = ["Aroused [3 turns]"]

        phys_state = {
            "intimate_contact": "Intimate encounter with Kana (intercourse)",
            "climax_state": {"partner_climaxed": False, "player_climaxed": False},
            "excitement": {
                "active": True,
                "actors": {
                    "Artemiusz": {"meter": 60, "delta": 0, "status": "Catching Breath 💨", "idle_turns": 2},
                    "Kana": {"meter": 60, "delta": 0, "status": "Catching Breath 💨", "idle_turns": 2},
                },
            },
        }

        # Turn 3: Idle pause -> Decay kicks in, halved to -5% due to Aroused
        step3 = compute_excitement_step(
            physical_state=phys_state,
            action_str="Look out the window silently without touching",
            player_char=player_with_aroused,
            partner_contact=partner_with_aroused,
            session={"id": self.session_id, "current_day": 1, "current_minute": 504},
        )
        actors = phys_state["excitement"]["actors"]
        self.assertEqual(actors["Artemiusz"]["idle_turns"], 3)
        self.assertEqual(actors["Kana"]["idle_turns"], 3)
        self.assertEqual(actors["Artemiusz"]["delta"], -5)
        self.assertEqual(actors["Kana"]["delta"], -5)
        self.assertEqual(actors["Artemiusz"]["meter"], 55)
        self.assertEqual(actors["Kana"]["meter"], 55)
        self.assertEqual(actors["Artemiusz"]["status"], "Cooling Down ⏳ (-5%)")
        self.assertEqual(actors["Kana"]["status"], "Cooling Down ⏳ (-5%)")

    def test_decay_after_grace_period_without_aroused_full(self):
        """Verify Turn 3+ decay without active Aroused status drops by full -10% per turn."""
        player_unexcited = dict(self.player_char)
        player_unexcited["status_effects"] = []
        partner_unexcited = dict(self.partner_contact)
        partner_unexcited["status_effects"] = []

        phys_state = {
            "intimate_contact": "Intimate encounter with Kana (intercourse)",
            "climax_state": {"partner_climaxed": False, "player_climaxed": False},
            "excitement": {
                "active": True,
                "actors": {
                    "Artemiusz": {"meter": 60, "delta": 0, "status": "Catching Breath 💨", "idle_turns": 2},
                    "Kana": {"meter": 60, "delta": 0, "status": "Catching Breath 💨", "idle_turns": 2},
                },
            },
        }

        # Turn 3: Idle pause -> Full decay -10% kicks in
        step3 = compute_excitement_step(
            physical_state=phys_state,
            action_str="Look at the floor in awkward silence",
            player_char=player_unexcited,
            partner_contact=partner_unexcited,
            session={"id": self.session_id, "current_day": 1, "current_minute": 504},
        )
        actors = phys_state["excitement"]["actors"]
        self.assertEqual(actors["Artemiusz"]["idle_turns"], 3)
        self.assertEqual(actors["Kana"]["idle_turns"], 3)
        self.assertEqual(actors["Artemiusz"]["delta"], -10)
        self.assertEqual(actors["Kana"]["delta"], -10)
        self.assertEqual(actors["Artemiusz"]["meter"], 50)
        self.assertEqual(actors["Kana"]["meter"], 50)
        self.assertEqual(actors["Artemiusz"]["status"], "Cooling Down ⏳ (-10%)")
        self.assertEqual(actors["Kana"]["status"], "Cooling Down ⏳ (-10%)")

    def test_sensual_maintenance_refreshes_aroused_and_resets_idle(self):
        """Verify non-genital sensual actions (whispering, kissing, caressing) reset idle turns without rushing climax."""
        phys_state = {
            "intimate_contact": "Intimate encounter with Kana (intercourse)",
            "climax_state": {"partner_climaxed": False, "player_climaxed": False},
            "excitement": {
                "active": True,
                "actors": {
                    "Artemiusz": {"meter": 70, "delta": 0, "status": "Catching Breath 💨", "idle_turns": 2},
                    "Kana": {"meter": 70, "delta": 0, "status": "Catching Breath 💨", "idle_turns": 2},
                },
            },
        }

        # Sensual Maintenance Action: Kissing and whispered praise
        step = compute_excitement_step(
            physical_state=phys_state,
            action_str="Whisper sweet praise against her neck and kiss her lips passionately while caressing her cheek",
            player_char=self.player_char,
            partner_contact=self.partner_contact,
            session={"id": self.session_id, "current_day": 1, "current_minute": 504},
        )
        actors = phys_state["excitement"]["actors"]
        # Idle turns reset to 0
        self.assertEqual(actors["Artemiusz"]["idle_turns"], 0)
        self.assertEqual(actors["Kana"]["idle_turns"], 0)
        # Meter does NOT decay and does NOT surge into climax
        self.assertEqual(actors["Artemiusz"]["meter"], 70)
        self.assertEqual(actors["Kana"]["meter"], 70)
        self.assertEqual(actors["Artemiusz"]["delta"], 0)
        self.assertEqual(actors["Kana"]["delta"], 0)
        # Status retains warm arousal
        self.assertIn(actors["Artemiusz"]["status"], ("Maintaining Rhythm", "Sensual Warmth 🔥", "On the Brink 🔥"))
        self.assertIn(actors["Kana"]["status"], ("Deepening Pleasure", "Sensual Warmth 🔥", "On the Brink 🔥"))

    def test_natural_fade_to_zero_dissolution(self):
        """Verify encounter dissolves naturally when excitement decays to 0% after extended idle turns."""
        phys_state = {
            "intimate_contact": "Intimate encounter with Kana (intercourse)",
            "climax_state": {"partner_climaxed": False, "player_climaxed": False},
            "excitement": {
                "active": True,
                "actors": {
                    "Artemiusz": {"meter": 5, "delta": -10, "status": "Cooling Down ⏳ (-10%)", "idle_turns": 3},
                    "Kana": {"meter": 5, "delta": -10, "status": "Cooling Down ⏳ (-10%)", "idle_turns": 3},
                },
            },
        }

        # Turn where meters hit 0
        step = compute_excitement_step(
            physical_state=phys_state,
            action_str="Stand still looking at the chalkboard",
            player_char=self.player_char,
            partner_contact=self.partner_contact,
            session={"id": self.session_id, "current_day": 1, "current_minute": 506},
        )
        actors = phys_state["excitement"]["actors"]
        self.assertEqual(actors["Artemiusz"]["meter"], 0)
        self.assertEqual(actors["Kana"]["meter"], 0)
        self.assertEqual(actors["Artemiusz"]["status"], "Cooled Down")
        self.assertEqual(actors["Kana"]["status"], "Cooled Down")
        self.assertTrue(step["all_cooled_down"])

    def test_non_combat_status_preserves_aroused_turn_timer(self):
        """Verify game_engine reducer exempts 'Aroused [3 turns]' from non-combat [N turns] purge."""
        from character_data import sanitize_status_effects
        import re

        raw_statuses = ["Aroused [3 turns]", "Iron Skin [3 turns]", "Bleeding [2 turns]"]
        cleaned_status = sanitize_status_effects(raw_statuses)

        # Replicate reducers.py line 520 non-combat logic
        non_combat_cleaned = [
            s for s in cleaned_status
            if not any(k in s for k in ("Iron Skin", "Aegis Warding", "Combat Booster", "Quickstep", "DT]", "DR]", "% ATK]", "% EVA]"))
            and not (re.search(r"\[\d+\s*turns?\]", s, re.IGNORECASE) and "aroused" not in s.lower())
        ]

        self.assertIn("Aroused [3 turns]", non_combat_cleaned)
        self.assertNotIn("Iron Skin [3 turns]", non_combat_cleaned)
        self.assertNotIn("Bleeding [2 turns]", non_combat_cleaned)

    def test_partner_climax_not_retriggered_on_idle_turn(self):
        """Verify that when a partner climaxed, subsequent idle/dialogue turns do NOT increment climaxes_count."""
        phys_state = {
            "intimate_contact": "Intimate encounter with Kana (intercourse)",
            "climax_state": {"partner_climaxed": True, "player_climaxed": False, "partner_climaxes": {"Kana": True}},
            "excitement": {
                "active": True,
                "actors": {
                    "Artemiusz": {"meter": 80, "delta": 15, "status": "Maintaining Rhythm", "idle_turns": 0},
                    "Kana": {"meter": 100, "delta": 0, "status": "💥 Climax Reached!", "climaxes_count": 1, "idle_turns": 0},
                },
            },
        }

        # Idle turn: Catch breath and talk
        step = compute_excitement_step(
            physical_state=phys_state,
            action_str="Catch your breath and look tenderly at Kana",
            player_char=self.player_char,
            partner_contact=self.partner_contact,
            session={"id": self.session_id, "current_day": 1, "current_minute": 502},
        )
        actors = phys_state["excitement"]["actors"]
        # Climax count must remain strictly 1
        self.assertEqual(actors["Kana"]["climaxes_count"], 1)
        # Meter remains at 100 during grace period, status indicates aftershocks or lingering heat
        self.assertEqual(actors["Kana"]["meter"], 100)
        self.assertIn(actors["Kana"]["status"], ("Lingering Heat 🔥", "Trembling from Aftershocks 🔥"))
        # newly_climaxed_partners must NOT contain Kana
        self.assertNotIn("Kana", step.get("newly_climaxed_partners", []))


if __name__ == "__main__":
    unittest.main()


