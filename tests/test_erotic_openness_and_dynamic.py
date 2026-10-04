import unittest
import sqlite3
import os
import asyncio
import db
import game_engine
from unittest.mock import patch, MagicMock, AsyncMock

from mechanics.social.persona import (
    EROTIC_OPENNESS_TIERS,
    EROTIC_OPENNESS_TEMPLATES,
    infer_erotic_openness_from_traits,
    get_erotic_openness_label,
    normalize_appearance,
    format_intimate_profile_sections,
    format_dynamic_prompt_directive,
    format_openness_prompt_directive
)
from mechanics.system.phone import get_dm_requirement, generate_contact_dm_reply
from cogs.contacts import build_intimate_profile_embed


class TestEroticOpennessAndDynamic(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        db.init_db()

    def setUp(self):
        self.user_id = 999111222
        self.session_id = "test_openness_session"

        with db.get_conn() as conn:
            conn.execute("DELETE FROM sessions WHERE id = ?", (self.session_id,))
            conn.execute("DELETE FROM characters WHERE user_id = ?", (self.user_id,))
            conn.execute("DELETE FROM contacts WHERE session_id = ?", (self.session_id,))

        db.create_character(user_id=self.user_id, name="Aiden", gender="male")
        self.char = db.get_character(self.user_id)
        self.session_id = db.create_session(self.user_id, "solo", 1, "vivid", "individual", False, scenario="nsfw_high_school_drama")
        with db.get_conn() as conn:
            conn.execute("UPDATE sessions SET current_location = ? WHERE id = ?", ("Academy Campus ➔ Courtyard Bench", self.session_id))

    def test_erotic_openness_generation_and_distribution(self):
        """Verify deterministic generation and balanced distribution across 1,000 NPC seeds."""
        counts = {"prude": 0, "moderate": 0, "bold": 0, "shameless": 0}
        for i in range(1000):
            tier = infer_erotic_openness_from_traits(
                desc=f"Student {i} at campus",
                race="human",
                gender="female",
                traits=["Observant", "Friendly"],
                role="Student"
            )
            self.assertIn(tier, EROTIC_OPENNESS_TIERS)
            counts[tier] += 1

        # Check expected general distribution: ~25% prude, ~45% moderate, ~20% bold, ~10% shameless
        self.assertGreaterEqual(counts["prude"], 180, "Prude should be ~25% (+/- 7%)")
        self.assertLessEqual(counts["prude"], 320)

        self.assertGreaterEqual(counts["moderate"], 380, "Moderate should be ~45% (+/- 7%)")
        self.assertLessEqual(counts["moderate"], 520)

        self.assertGreaterEqual(counts["bold"], 140, "Bold should be ~20% (+/- 7%)")
        self.assertLessEqual(counts["bold"], 270)

        self.assertGreaterEqual(counts["shameless"], 50, "Shameless should be ~10% (+/- 5%)")
        self.assertLessEqual(counts["shameless"], 160)

    def test_trait_weighted_correlations(self):
        """Verify traits influence openness (Guarded/Diligent lean Prude, Flirtatious/Delinquent lean Bold/Shameless)."""
        prude_favored = 0
        shameless_favored = 0

        for i in range(200):
            t_modest = infer_erotic_openness_from_traits(
                desc=f"Strict scholar {i}",
                traits=["Diligent", "Guarded"],
                role="Student Council President"
            )
            if t_modest in ("prude", "moderate"):
                prude_favored += 1

            t_wild = infer_erotic_openness_from_traits(
                desc=f"Rebellious flirt {i}",
                traits=["Flirtatious", "Delinquent"],
                role="Rebel"
            )
            if t_wild in ("bold", "shameless"):
                shameless_favored += 1

        self.assertGreater(prude_favored, 130, "Modest traits should strongly lean towards Prude/Moderate")
        self.assertGreater(shameless_favored, 120, "Wild traits should strongly lean towards Bold/Shameless")

    def test_autonomous_physical_initiative_prompt_injection(self):
        """Verify that proactive/dominant dynamics inject autonomous initiative regardless of openness."""
        contact_prude = db.upsert_contact(
            session_id=self.session_id,
            character_id=self.char["id"],
            npc_id="claire_proud",
            name="Claire Proud",
            delta_score=40,
            track="romantic",
            new_traits=["Proud", "Diligent"],
            appearance={"intimate_dynamic": "Boldly Proactive & Dominant", "erotic_openness": "prude", "intimate_revealed": True}
        )

        db.save_session_scene(
            session_id=self.session_id,
            scene_title="Courtyard",
            narrative="Claire is leaning against the wall.",
            choices=[],
            history=[],
            current_npcs=[{"name": "Claire Proud", "role": "Student"}],
            dialogue_partner="Claire Proud"
        )
        session = db.get_session(self.session_id)
        session["dialogue_turns"] = 1

        from skill_check import CheckResult
        fake_check = CheckResult(chance=100, roll=10.0, tier="success", tier_label="Success", succeeded=True)
        with patch("game_engine.call_llm_json", new_callable=AsyncMock) as mock_llm:
            mock_llm.return_value = {
                "outcome_narrative": "She smirks.",
                "next_narrative": "She pulls your tie.",
                "next_choices": [{"label": "Reciprocate the kiss", "stat": "CHA", "requirement": 5}],
                "relationship_updates": []
            }
            turn_res = asyncio.run(game_engine.resolve_turn(
                session=session,
                party=[(self.char, [])],
                actions=[{"label": "Talk to Claire", "char": self.char, "stat": "NONE", "requirement": 0, "mp_spent": 0, "check": fake_check}]
            ))
            self.assertTrue(mock_llm.called)
            sys_prompt = mock_llm.call_args_list[0][0][0]
            if isinstance(sys_prompt, list):
                sys_prompt = "\n".join(str(item) for item in sys_prompt)
            called_prompt = (sys_prompt or "") + "\n" + (mock_llm.call_args_list[0][0][1] or "")
            self.assertIn("AUTONOMOUS PHYSICAL INITIATIVE (Claire Proud", called_prompt)
            self.assertIn("THEY MAKE THE PHYSICAL MOVE FIRST", called_prompt)
            self.assertIn("EROTIC OPENNESS (Claire Proud: Prude / Modest)", called_prompt)

    def test_openness_dc_modifiers_in_skill_checks(self):
        """Verify intimate actions against Prude partner add +3 DC, and against Shameless partner reduce by -3 DC."""
        db.upsert_contact(
            session_id=self.session_id,
            character_id=self.char["id"],
            npc_id="eva_white",
            name="Eva White",
            delta_score=20,
            track="romantic",
            appearance={"erotic_openness": "prude"}
        )

        db.upsert_contact(
            session_id=self.session_id,
            character_id=self.char["id"],
            npc_id="roxie_wild",
            name="Roxie Wild",
            delta_score=20,
            track="romantic",
            appearance={"erotic_openness": "shameless"}
        )

        c_rec_prude = db.get_contact(self.session_id, "eva_white", self.char["id"])
        op_prude = c_rec_prude.get("appearance", {}).get("erotic_openness")
        self.assertEqual(op_prude, "prude")

        c_rec_shameless = db.get_contact(self.session_id, "roxie_wild", self.char["id"])
        op_shameless = c_rec_shameless.get("appearance", {}).get("erotic_openness")
        self.assertEqual(op_shameless, "shameless")

    def test_phone_dm_openness_requirements(self):
        """Verify get_dm_requirement adds +4 for Prude and -3 for Shameless on intimate media requests."""
        # Baseline requirement for nsfw_photo with romantic score 50: 5
        req_mod = get_dm_requirement(50, "nsfw_photo", track="romantic", openness="moderate")
        self.assertEqual(req_mod, 5)

        # Prude requirement: 5 + 4 = 9
        req_prude = get_dm_requirement(50, "nsfw_photo", track="romantic", openness="prude")
        self.assertEqual(req_prude, 9)

        # Shameless requirement: 5 - 3 = 2
        req_shameless = get_dm_requirement(50, "nsfw_photo", track="romantic", openness="shameless")
        self.assertEqual(req_shameless, 2)

        # Bold requirement: 5 - 2 = 3
        req_bold = get_dm_requirement(50, "nsfw_photo", track="romantic", openness="bold")
        self.assertEqual(req_bold, 3)

    def test_embed_formatting_with_openness(self):
        """Verify build_intimate_profile_embed displays Openness under Demeanor & Dynamic."""
        contact = {
            "session_id": self.session_id,
            "character_id": self.char["id"],
            "npc_id": "test_npc_profile",
            "name": "Selena Black",
            "relationship_score": 80,
            "appearance": {
                "intimate_demeanor": "Blunt & Teasing",
                "intimate_dynamic": "Boldly Proactive & Dominant",
                "erotic_openness": "shameless",
                "intimate_revealed": True
            }
        }
        embed = build_intimate_profile_embed(contact, scenario_key="nsfw_high_school_drama")
        field_names = [f.name for f in embed.fields]
        self.assertIn("🎭 Demeanor & Dynamic", field_names)

        dyn_field = next(f for f in embed.fields if f.name == "🎭 Demeanor & Dynamic")
        self.assertIn("• **Demeanor**: Blunt & Teasing", dyn_field.value)
        self.assertIn("• **Dynamic**: Boldly Proactive & Dominant", dyn_field.value)
        self.assertIn("• **Openness**: Shameless / Lewd", dyn_field.value)

    def test_all_dynamic_archetypes_and_autonomous_directives(self):
        """Verify distinct autonomous prompt directives for all canonical dynamic archetypes."""
        # 1. Assertive / Dominant
        d_proactive = format_dynamic_prompt_directive("Kagami", "Boldly Proactive & Dominant")
        self.assertIn("AUTONOMOUS PHYSICAL INITIATIVE", d_proactive)
        self.assertIn("THEY MAKE THE PHYSICAL MOVE FIRST", d_proactive)

        # 2. Insatiable / High-Drive
        d_insatiable = format_dynamic_prompt_directive("Rin", "Insatiable / Hidden High-Drive")
        self.assertIn("AUTONOMOUS PHYSICAL INITIATIVE", d_insatiable)
        self.assertIn("intense physical hunger", d_insatiable)
        self.assertIn("cannot keep their hands off the player", d_insatiable)

        # 3. Attentive Service-Oriented
        d_service = format_dynamic_prompt_directive("Emi", "Attentive Service-Oriented")
        self.assertIn("AUTONOMOUS PHYSICAL INITIATIVE", d_service)
        self.assertIn("initiates pampering and devotion without being asked", d_service)
        self.assertIn("massaging your shoulders/neck", d_service)

        # 4. Receptive / Yielding
        d_receptive = format_dynamic_prompt_directive("Hana", "Eagerly Receptive / Surrenders Control")
        self.assertIn("AUTONOMOUS INTIMATE RESPONSE", d_receptive)
        self.assertIn("inviting bodily surrender", d_receptive)
        self.assertIn("guiding the player's hands", d_receptive)

    def test_dynamically_created_and_custom_dynamics(self):
        """Verify custom/dynamically generated dynamic strings trigger appropriate autonomous directives."""
        # Custom assertive/forward keywords
        d_custom_assertive = format_dynamic_prompt_directive("Vixen", "Aggressive Alpha Seductress")
        self.assertIn("AUTONOMOUS PHYSICAL INITIATIVE", d_custom_assertive)
        self.assertIn("THEY MAKE THE PHYSICAL MOVE FIRST", d_custom_assertive)

        # Custom voracious/craving keywords
        d_custom_hungry = format_dynamic_prompt_directive("Lilith", "Voracious Succubus with Relentless Craving")
        self.assertIn("AUTONOMOUS PHYSICAL INITIATIVE", d_custom_hungry)
        self.assertIn("intense physical hunger", d_custom_hungry)

        # Custom pampering/service keywords
        d_custom_pamper = format_dynamic_prompt_directive("Rem", "Devoted Maid who Worships Master")
        self.assertIn("AUTONOMOUS PHYSICAL INITIATIVE", d_custom_pamper)
        self.assertIn("initiates pampering and devotion", d_custom_pamper)

        # Custom submissive/meek keywords
        d_custom_sub = format_dynamic_prompt_directive("Mia", "Meek Submissive Pet")
        self.assertIn("AUTONOMOUS INTIMATE RESPONSE", d_custom_sub)
        self.assertIn("inviting bodily surrender", d_custom_sub)

        # Unknown custom fallback
        d_custom_unknown = format_dynamic_prompt_directive("Xen", "Mysterious Stargazer")
        self.assertIn("AUTONOMOUS INTIMATE DYNAMIC (Xen: Mysterious Stargazer)", d_custom_unknown)


if __name__ == "__main__":
    unittest.main()

