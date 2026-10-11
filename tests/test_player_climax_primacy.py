"""
Unit tests for Player Climax Primacy and Anti-Premature-Conclusion Engine in Intimate Encounters.
"""
import unittest
import db
import game_engine
from game_engine.prompts import SYSTEM_PROMPT
from mechanics.social.physical_state import (
    build_physical_prompt_block,
    merge_physical_state_updates,
    is_erotic_intimate_contact,
    detect_partner_climax,
    detect_player_climax,
    detect_intimate_disengagement,
)
from mechanics.social.persona.intimacy.formatting import format_dynamic_prompt_directive
from game_engine.turn.dialogue import _build_dialogue_prompt_block
from game_engine.turn_context import TurnContext
from game_engine.state.reducers import _reduce_physical_state_and_memories
from game_engine.choices_cleaner import clean_choices_impl


class TestPlayerClimaxPrimacy(unittest.TestCase):

    def setUp(self):
        db.init_db()
        self.session_id = 998811
        with db.get_conn() as conn:
            conn.execute(
                "INSERT OR REPLACE INTO sessions (id, host_user_id, status, mode, capacity, scenario) "
                "VALUES (?, 12345, 'active', 'single', 1, 'fantasy')",
                (self.session_id,)
            )
        self.player_char = {
            "id": 1,
            "user_id": 12345,
            "name": "Artemiusz",
            "hp": 20,
            "max_hp": 20,
            "mp": 10,
            "max_mp": 10,
            "gender": "male",
            "stats": {"STR": 6, "AGI": 5, "END": 7, "INT": 5, "PER": 5, "CHA": 6, "LUK": 5},
        }
        self.party = [(self.player_char, [])]

    def test_system_prompt_enforces_player_climax_primacy(self):
        """Ensure SYSTEM_PROMPT contains the inviolable player climax primacy rules."""
        self.assertIn("INTIMATE PACING & PLAYER CLIMAX PRIMACY", SYSTEM_PROMPT)
        self.assertIn("PARTNER CLIMAX IS NOT SESSION CONCLUSION", SYSTEM_PROMPT)
        self.assertIn("STRICTLY FORBIDDEN PREMATURE COLLAPSE & FORCED AFTERCARE", SYSTEM_PROMPT)
        self.assertIn("UNINTERRUPTED CONTINUITY & ACTIVE MOMENTUM", SYSTEM_PROMPT)
        self.assertIn("PLAYER CLIMAX AUTHORITY", SYSTEM_PROMPT)
        self.assertIn("CHOICE PRIMACY IN `next_choices`", SYSTEM_PROMPT)

    def test_dynamic_formatting_injects_post_climax_continuation(self):
        """Ensure all dynamic directives instruct the model that intercourse does not stop when partner peaks."""
        for dyn in [
            "Playful Switch / Teasing Brat",
            "Assertive & Dominant",
            "Insatiable / High-Drive",
            "Service-Oriented & Pampering",
            "Receptive & Yielding",
        ]:
            dir_text = format_dynamic_prompt_directive("Kana", dyn)
            self.assertIn("WHEN CLIMAXING", dir_text)
            self.assertIn("DOES NOT stop", dir_text)

    def test_climax_detection_helpers(self):
        """Verify linguistic detection of partner climax, player climax, and disengagement."""
        # Partner climax
        self.assertTrue(detect_partner_climax("Kana shuddered as her climax took her.", partner_name="Kana"))
        self.assertTrue(detect_partner_climax("Elena cried out in ecstasy, arching her back as her walls clenched around him.", partner_name="Elena"))
        self.assertTrue(detect_partner_climax("The intense friction sent her over the edge."))
        self.assertFalse(detect_partner_climax("She kissed him gently on the forehead."))

        # Player climax
        self.assertTrue(detect_player_climax("He spilled inside her with a ragged gasp."))
        self.assertTrue(detect_player_climax("Artemiusz reached his own climax, filling her completely.", player_name="Artemiusz"))
        self.assertTrue(detect_player_climax("Pushed over the edge to finish together inside."))
        self.assertFalse(detect_player_climax("He stroked her hair and whispered softly."))

        # Disengagement
        self.assertTrue(detect_intimate_disengagement([{"label": "Slow your rhythm, gently withdraw, and hold Kana close in aftercare"}]))
        self.assertTrue(detect_intimate_disengagement(["Step back and break contact with her"]))
        self.assertFalse(detect_intimate_disengagement([{"label": "Maintain a steady rhythm and thrust deeper"}]))

    def test_physical_prompt_block_anchors_climax_primacy(self):
        """Verify build_physical_prompt_block injects active continuation anchor when partner has peaked."""
        session = {
            "id": self.session_id,
            "scenario": "fantasy",
            "physical_state": {
                "actors": {
                    "Artemiusz": {"posture": "Maintaining rhythm inside Kana", "clothing": {"top": "off", "bottom": "off"}},
                    "Kana": {"posture": "Trembling from aftershocks in Artemiusz's embrace", "clothing": {"top": "off", "bottom": "off"}},
                },
                "intimate_contact": "Intimate encounter with Kana (intercourse - partner reached climax, ongoing for player)",
                "climax_state": {"partner_climaxed": True, "player_climaxed": False},
            }
        }
        prompt_block = build_physical_prompt_block(session, self.party, is_combat=False, is_nsfw=True)
        self.assertIn("PLAYER CLIMAX PRIMACY ACTIVE", prompt_block)
        self.assertIn("The NPC partner reached climax in the previous beat, but the player character has NOT finished yet", prompt_block)
        self.assertIn("DO NOT narrate collapsing together or ending the session", prompt_block)

    def test_dialogue_prompt_block_injects_player_climax_primacy(self):
        """Verify _build_dialogue_prompt_block injects primacy directive when intimate contact is active."""
        db.update_session_physical_state(self.session_id, {
            "actors": {
                "Artemiusz": {"posture": "Maintaining rhythm", "clothing": {"top": "off", "bottom": "off"}},
                "Kana": {"posture": "Trembling in embrace", "clothing": {"top": "off", "bottom": "off"}},
            },
            "intimate_contact": "Intimate encounter with Kana (intercourse)",
            "climax_state": {"partner_climaxed": True, "player_climaxed": False},
        })
        session = db.get_session(self.session_id)
        session["scenario"] = "nsfw_isekai_fantasy"
        session["current_npcs"] = [{"name": "Kana"}]
        ctx = TurnContext(self.session_id, session)

        prompt_block = _build_dialogue_prompt_block(
            session, ctx, ["Kana"], self.party, [{"label": "Hold Kana close and maintain rhythm"}]
        )
        self.assertIn("INTIMATE PACING & PLAYER CLIMAX PRIMACY", prompt_block)
        self.assertIn("Kana reached climax in the previous beat, but the player character is STILL GOING", prompt_block)

    def test_reducers_partner_climax_preserves_intercourse_and_guards_posture(self):
        """Verify when partner peaks in narrative, reducers keep intercourse active and prevent premature collapse."""
        initial_phys = {
            "actors": {
                "Artemiusz": {"posture": "Engaged in intercourse", "clothing": {"top": "off", "bottom": "off"}},
                "Kana": {"posture": "Engaged in intercourse", "clothing": {"top": "off", "bottom": "off"}},
            },
            "intimate_contact": "Intimate encounter with Kana (intercourse)",
            "climax_state": {"partner_climaxed": False, "player_climaxed": False},
        }
        db.update_session_physical_state(self.session_id, initial_phys)
        session = db.get_session(self.session_id)
        session["current_npcs"] = [{"name": "Kana"}]

        # Turn outcome where partner peaks, and LLM mistakenly attempted to set sleeping posture and intimate_contact: none
        outcome = {
            "outcome_narrative": "Kana screamed out in release as her walls clenched tightly around him, tremors rippling through her body.",
            "next_narrative": "She panting against his chest as the intense sensations slowly subsided.",
            "dialogue_partner": "Kana",
            "relationship_updates": [{"npc_name": "Kana", "milestone_event": "intercourse"}],
            "physical_updates": {
                "actors": {
                    "Artemiusz": {"posture": "Lying down spent"},
                    "Kana": {"posture": "Sleeping beside him"},
                },
                "intimate_contact": "none",
            }
        }
        actions = [{"label": "Thrust deeply and bring Kana over the edge"}]

        _reduce_physical_state_and_memories(self.session_id, session, outcome, self.party, "fantasy", actions=actions)

        updated = db.get_session_physical_state(self.session_id)
        # Intercourse must remain active!
        self.assertIn("partner reached climax, ongoing for player", updated["intimate_contact"])
        self.assertTrue(updated["climax_state"]["partner_climaxed"])
        self.assertFalse(updated["climax_state"]["player_climaxed"])

        # Postures must be guarded from sleeping/collapse!
        kana_posture = updated["actors"]["Kana"]["posture"]
        artemiusz_posture = updated["actors"]["Artemiusz"]["posture"]
        self.assertNotIn("Sleeping", kana_posture)
        self.assertIn("Trembling from aftershocks", kana_posture)
        self.assertNotIn("Lying down spent", artemiusz_posture)
        self.assertIn("Maintaining rhythm", artemiusz_posture)

    def test_reducers_player_climax_transitions_to_aftercare(self):
        """Verify when player character subsequently climaxes, session transitions to aftercare/cuddling."""
        ongoing_phys = {
            "actors": {
                "Artemiusz": {"posture": "Maintaining rhythm inside Kana", "clothing": {"top": "off", "bottom": "off"}},
                "Kana": {"posture": "Trembling from aftershocks", "clothing": {"top": "off", "bottom": "off"}},
            },
            "intimate_contact": "Intimate encounter with Kana (intercourse - partner reached climax, ongoing for player)",
            "climax_state": {"partner_climaxed": True, "player_climaxed": False},
        }
        db.update_session_physical_state(self.session_id, ongoing_phys)
        session = db.get_session(self.session_id)
        session["current_npcs"] = [{"name": "Kana"}]

        outcome = {
            "outcome_narrative": "With a low growl, Artemiusz spilled deep inside her, his own climax overtaking him.",
            "next_narrative": "They caught their breath together, chests heaving in the quiet room.",
            "dialogue_partner": "Kana",
            "relationship_updates": [{"npc_name": "Kana", "milestone_event": "intercourse"}],
            "physical_updates": {
                "player_climaxed": True,
            }
        }
        actions = [{"label": "Drive deep and reach your own climax inside Kana"}]

        _reduce_physical_state_and_memories(self.session_id, session, outcome, self.party, "fantasy", actions=actions)

        updated = db.get_session_physical_state(self.session_id)
        self.assertIn("Cuddling / aftercare with Kana", updated["intimate_contact"])
        self.assertTrue(updated["climax_state"]["player_climaxed"])
        self.assertTrue(updated["climax_state"]["partner_climaxed"])

    def test_reducers_voluntary_withdrawal_transitions_to_aftercare(self):
        """Verify when player explicitly chooses to withdraw/slow down, session transitions cleanly."""
        ongoing_phys = {
            "actors": {
                "Artemiusz": {"posture": "Maintaining rhythm inside Kana", "clothing": {"top": "off", "bottom": "off"}},
                "Kana": {"posture": "Trembling from aftershocks", "clothing": {"top": "off", "bottom": "off"}},
            },
            "intimate_contact": "Intimate encounter with Kana (intercourse - partner reached climax, ongoing for player)",
            "climax_state": {"partner_climaxed": True, "player_climaxed": False},
        }
        db.update_session_physical_state(self.session_id, ongoing_phys)
        session = db.get_session(self.session_id)
        session["current_npcs"] = [{"name": "Kana"}]

        outcome = {
            "outcome_narrative": "Artemiusz gently eased his rhythm, slowly withdrawing and pulling Kana into a protective embrace.",
            "next_narrative": "She melted against his shoulder, smiling softly as he stroked her back.",
            "dialogue_partner": "Kana",
            "relationship_updates": [],
            "physical_updates": {}
        }
        actions = [{"label": "Slow your rhythm, gently withdraw, and hold Kana close in aftercare"}]

        _reduce_physical_state_and_memories(self.session_id, session, outcome, self.party, "fantasy", actions=actions)

        updated = db.get_session_physical_state(self.session_id)
        self.assertEqual(updated["intimate_contact"], "none")
        self.assertFalse(updated["climax_state"]["player_climaxed"])

    def test_choices_cleaner_injects_active_continuation_choices(self):
        """Verify choices_cleaner replaces passive sleep choices with active continuation options during intercourse."""
        ongoing_phys = {
            "actors": {
                "Artemiusz": {"posture": "Maintaining rhythm inside Kana"},
                "Kana": {"posture": "Trembling from aftershocks in embrace"},
            },
            "intimate_contact": "Intimate encounter with Kana (intercourse - partner reached climax, ongoing for player)",
            "climax_state": {"partner_climaxed": True, "player_climaxed": False},
        }
        db.update_session_physical_state(self.session_id, ongoing_phys)

        # Passive choices mistakenly generated by LLM
        passive_raw_choices = [
            {"label": "Fall asleep together on the bed", "stat": "NONE", "requirement": 0},
            {"label": "Talk about tomorrow's classes", "stat": "CHA", "requirement": 6},
            {"label": "Pull up the blanket", "stat": "AGI", "requirement": 5},
            {"label": "Thank Kana, excuse yourself, and look around the room", "stat": "NONE", "requirement": 0},
        ]

        cleaned = clean_choices_impl(
            None,
            passive_raw_choices,
            scenario="fantasy",
            location="Bedroom",
            char=self.player_char,
            dialogue_partner="Kana",
            current_npcs=[{"name": "Kana"}],
            session_id=self.session_id,
        )

        labels = [c["label"] for c in cleaned]
        # Active continuation options must be injected!
        self.assertTrue(any("rhythm" in lbl.lower() for lbl in labels))
        self.assertTrue(any("praise" in lbl.lower() for lbl in labels))
        self.assertTrue(any("edge" in lbl.lower() or "finish" in lbl.lower() for lbl in labels))
        # Exit choice must be contextual withdrawal, not generic look around the room!
        self.assertTrue(any("gently withdraw" in lbl.lower() for lbl in labels))
        self.assertFalse(any("look around the room" in lbl.lower() for lbl in labels))

    def test_aftercare_suppressed_before_player_climax_exact_scenario(self):
        """Verify aftercare option is strictly suppressed when player has not climaxed (Turn #4 Artemiusz 90% vs Mia 75%)."""
        from mechanics.social.intimate_excitement import has_state_contradiction_in_choice

        # 1. State contradiction test: unspent player (90% meter, player_climaxed=False)
        premature_aftercare_choice = "Slow your rhythm, gently withdraw, and pull Mia Yamada close into aftercare"
        self.assertTrue(has_state_contradiction_in_choice(
            premature_aftercare_choice,
            last_act="penetrative",
            partner_climaxed=False,
            player_meter=90,
            partner_meter=75,
            player_spent=False,
            player_climaxed=False,
        ))

        # Even if partner had climaxed, unspent player MUST reject aftercare
        self.assertTrue(has_state_contradiction_in_choice(
            premature_aftercare_choice,
            last_act="penetrative",
            partner_climaxed=True,
            player_meter=90,
            partner_meter=100,
            player_spent=False,
            player_climaxed=False,
        ))

        # 2. choices_cleaner pipeline test:
        phys_st = {
            "actors": {
                "Artemiusz": {"posture": "Maintaining rhythm inside Mia Yamada"},
                "Mia Yamada": {"posture": "Arching back in pleasure"},
            },
            "intimate_contact": "Intimate encounter with Mia Yamada (intercourse)",
            "climax_state": {"partner_climaxed": False, "player_climaxed": False},
            "excitement": {
                "active": True,
                "actors": {
                    "Artemiusz": {"meter": 90, "status": "Edging / Peak"},
                    "Mia Yamada": {"meter": 75, "status": "High Arousal"},
                },
                "last_act": "penetrative",
            },
        }
        db.update_session_physical_state(self.session_id, phys_st)

        raw_choices = [
            {"label": "Maintain a steady, deep rhythm and lock eyes with Mia Yamada", "stat": "END", "requirement": 6},
            {"label": "Caress Mia Yamada's waist and whisper breathless praise", "stat": "CHA", "requirement": 6},
            {"label": "Shift position for a deeper angle and build the heat", "stat": "STR", "requirement": 7},
            {"label": premature_aftercare_choice, "stat": "NONE", "requirement": 0},
        ]

        cleaned = clean_choices_impl(
            None,
            raw_choices,
            scenario="fantasy",
            location="Bedroom",
            char=self.player_char,
            dialogue_partner="Mia Yamada",
            current_npcs=[{"name": "Mia Yamada"}],
            session_id=self.session_id,
        )

        labels = [c["label"] for c in cleaned]
        # Absolutely NO choice may offer or mention "aftercare" while player has not climaxed!
        self.assertFalse(any("aftercare" in lbl.lower() for lbl in labels), f"Aftercare leaked into choices: {labels}")
        # The exit choice must be sanitized to natural pause / withdrawal without aftercare
        exit_choice = next((c for c in cleaned if c.get("stat") in ("NONE", "FREE") or c.get("requirement", 0) <= 0), None)
        self.assertIsNotNone(exit_choice)
        self.assertNotIn("aftercare", exit_choice["label"].lower())
        self.assertIn("withdraw", exit_choice["label"].lower())

    def test_aftercare_allowed_after_player_reaches_climax(self):
        """Verify aftercare option DOES appear once player reaches climax."""
        from mechanics.social.intimate_excitement import has_state_contradiction_in_choice

        aftercare_choice = "Rest together in aftercare, excuse yourself gently, and catch your breath with Mia Yamada"
        # Player has reached climax (player_climaxed=True, player_spent=True)
        self.assertFalse(has_state_contradiction_in_choice(
            aftercare_choice,
            last_act="none",
            partner_climaxed=True,
            player_meter=100,
            partner_meter=100,
            player_spent=True,
            player_climaxed=True,
        ))

        # choices_cleaner pipeline test with climaxed player
        phys_st = {
            "actors": {
                "Artemiusz": {"posture": "Resting against Mia Yamada in shared aftercare"},
                "Mia Yamada": {"posture": "Resting against Artemiusz in shared aftercare"},
            },
            "intimate_contact": "Cuddling / aftercare with Mia Yamada",
            "climax_state": {"partner_climaxed": True, "player_climaxed": True},
            "excitement": {
                "active": False,
                "actors": {
                    "Artemiusz": {"meter": 0, "status": "Refractory Rest"},
                    "Mia Yamada": {"meter": 0, "status": "Satisfied"},
                },
                "last_act": "none",
            },
        }
        db.update_session_physical_state(self.session_id, phys_st)

        raw_choices = [
            {"label": "Hold Mia Yamada close in tender aftercare and trace gentle circles", "stat": "CHA", "requirement": 5},
            {"label": "Brush Mia Yamada's hair back, kiss her softly, and share quiet warmth", "stat": "PER", "requirement": 5},
            {"label": "Catch your breath against Mia Yamada and keep her wrapped securely in your arms", "stat": "END", "requirement": 5},
            {"label": aftercare_choice, "stat": "NONE", "requirement": 0},
        ]

        cleaned = clean_choices_impl(
            None,
            raw_choices,
            scenario="fantasy",
            location="Bedroom",
            char=self.player_char,
            dialogue_partner="Mia Yamada",
            current_npcs=[{"name": "Mia Yamada"}],
            session_id=self.session_id,
        )

        labels = [c["label"] for c in cleaned]
        # Aftercare options ARE present now that player has reached climax
        self.assertTrue(any("aftercare" in lbl.lower() for lbl in labels), f"Expected aftercare choices: {labels}")


if __name__ == "__main__":
    unittest.main()

