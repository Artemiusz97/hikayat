"""
Unit tests for Hikayat Romantic & Intimate Behavioral Diversity,
Voice Continuity, and Anti-Stutter Engine.
"""
import unittest
from unittest.mock import patch, AsyncMock
import db
import game_engine
from mechanics.social.persona import (
    infer_intimate_demeanor_from_traits,
    infer_intimate_dynamic_from_traits,
    normalize_appearance,
    generate_dynamic_intimate_attributes,
    INTIMATE_DEMEANOR_FEMALE_TEMPLATES,
    INTIMATE_DEMEANOR_MALE_TEMPLATES,
    INTIMATE_DYNAMIC_TEMPLATES
)


class TestRomanticBehavioralDiversity(unittest.IsolatedAsyncioTestCase):
    def test_infer_intimate_demeanor_correlations(self):
        """Verify that character traits and roles procedurally map to authentic voice and communication styles."""
        # 1. Athletic / Leader -> Energetic, blunt, and direct
        dem_athlete = infer_intimate_demeanor_from_traits(
            role="Track Captain", traits=["Athletic", "Competitive"], desc="Energetic runner", gender="female"
        )
        self.assertIn("Blunt & Teasing", dem_athlete)
        self.assertIn("energetic directness", dem_athlete)

        dem_warrior = infer_intimate_demeanor_from_traits(
            role="Vanguard Knight", traits=["Brave", "Confident"], desc="Seasoned warrior", gender="male"
        )
        self.assertIn("Blunt & Teasing", dem_warrior)

        # 2. Teasing / Rogue -> Playful & Bantering
        dem_rogue = infer_intimate_demeanor_from_traits(
            role="Kitsune Thief", traits=["Mischievous", "Sly"], desc="Cunning fox trickster", gender="female"
        )
        self.assertIn("Playful & Bantering", dem_rogue)
        self.assertIn("teases warmly", dem_rogue)

        # 3. Passionate / Wild -> Passionate & Vocal
        dem_dancer = infer_intimate_demeanor_from_traits(
            role="Flame Dancer", traits=["Passionate", "Intense"], desc="Fiery performer", gender="female"
        )
        self.assertIn("Passionate & Vocal", dem_dancer)

        # 4. Scholar / Council -> Poised & Articulate
        dem_scholar = infer_intimate_demeanor_from_traits(
            role="Council President", traits=["Disciplined", "Composed"], desc="Intellectual scholar", gender="female"
        )
        self.assertIn("Poised & Articulate", dem_scholar)

        # 5. Gentle / Healer -> Soft & Deeply Affectionate
        dem_healer = infer_intimate_demeanor_from_traits(
            role="Village Healer", traits=["Kind", "Nurturing"], desc="Gentle herbalist", gender="female"
        )
        self.assertIn("Soft & Deeply Affectionate", dem_healer)

        # 6. Shy / Timid -> Hesitant & Flustered (Only for characters with explicit shy traits)
        dem_shy = infer_intimate_demeanor_from_traits(
            role="Library Assistant", traits=["Shy", "Timid"], desc="Quiet sheltered bookworm", gender="female"
        )
        self.assertIn("Hesitant & Flustered", dem_shy)

    def test_infer_intimate_dynamic_correlations_and_gap_moe(self):
        """Verify that intimate dynamics provide rich proactivity/role distribution with gap moe."""
        # Athletic leaders have strong distribution across Receptive, Dominant, and Switch
        dyn_athlete = infer_intimate_dynamic_from_traits(
            role="Track Captain", traits=["Athletic", "Competitive"], desc="Energetic runner", gender="female"
        )
        self.assertTrue(any(t in dyn_athlete for t in ["Eagerly Receptive", "Boldly Proactive", "Playful Switch", "Insatiable"]))

        # Healers have gap moe distribution across Insatiable, Gentle Yielding, and Service
        dyn_healer = infer_intimate_dynamic_from_traits(
            role="Shrine Maiden", traits=["Pure", "Gentle"], desc="Demure healer", gender="female"
        )
        self.assertTrue(any(t in dyn_healer for t in ["Insatiable", "Gentle & Yielding", "Attentive Service", "Playful Switch"]))

    def test_normalize_appearance_backfills_correlated_demeanor_and_dynamic(self):
        """Verify that normalize_appearance applies both intimate demeanor and dynamic for NSFW scenarios."""
        raw_app = {
            "eye_color": "amber",
            "hair_color": "golden-blonde",
            "traits": ["Athletic", "Competitive"],
            "role": "Track Captain"
        }
        normalized = normalize_appearance(
            raw_app, gender="female", race="human", scen_key="nsfw_high_school_drama", desc="Athletic track captain"
        )
        self.assertIn("intimate_demeanor", normalized)
        self.assertIn("intimate_dynamic", normalized)
        self.assertIn("Blunt & Teasing", normalized["intimate_demeanor"])

    def test_generate_dynamic_intimate_attributes_synergy(self):
        """Verify that Turn-Ons and Fetishes synergize with the character's intimate dynamic."""
        # Receptive dynamic should synergistically prioritize being pinned, dominant whispers, praise kink, restraints
        receptive_attrs = generate_dynamic_intimate_attributes(
            hash_val=500, race="human", gender="female", dynamic="Eagerly Receptive / Surrenders Control"
        )
        turns = receptive_attrs.get("turn_ons", "")
        fets = receptive_attrs.get("fetishes", "")
        self.assertTrue(len(turns) > 0)
        self.assertTrue(len(fets) > 0)

    def test_system_prompt_enforces_romantic_behavioral_diversity_and_anti_stutter(self):
        """Verify that SYSTEM_PROMPT contains the anti-stutter directive and authentic romantic voice rules."""
        sys_prompt = game_engine.SYSTEM_PROMPT
        self.assertIn("ROMANTIC & INTIMATE BEHAVIORAL DIVERSITY & VOICE CONTINUITY", sys_prompt)
        self.assertIn("BANNED ROMANCE CLICHÉS & UNIVERSAL STUTTERING", sys_prompt)
        self.assertIn("NEVER write artificial stutters or stammers", sys_prompt)
        self.assertIn("Athletic / Leader / Direct", sys_prompt)
        self.assertIn("Bold, physical, and proactive", sys_prompt)

    async def test_dialogue_prompt_block_injects_intimate_demeanor_and_voice_rules(self):
        """Verify that when active dialogue is formed, the NPC's intimate demeanor and dynamic are injected."""
        session_id = 887766
        user_id = 776655

        with db.get_conn() as conn:
            conn.execute("DELETE FROM sessions WHERE id = ?", (session_id,))
            conn.execute("DELETE FROM characters WHERE user_id = ?", (user_id,))
            conn.execute("DELETE FROM contacts WHERE session_id = ?", (session_id,))

        db.create_character(user_id=user_id, name="Hero", gender="male")
        char = db.get_character(user_id)
        session_id = db.create_session(user_id, "solo", 1, "vivid", "individual", False, scenario="nsfw_high_school_drama")

        db.upsert_contact(
            session_id=session_id,
            character_id=char["id"],
            npc_id="sofia_anderson",
            name="Sofia Anderson",
            basic_info={"role": "Track Captain"},
            appearance={
                "breast_size": "C-cup",
                "intimate_demeanor": "Blunt & Teasing, energetic directness, confident remarks",
                "intimate_dynamic": "Eagerly Receptive / Surrenders Control (Craves partner taking complete charge)"
            },
            new_traits=["Athletic", "Competitive"],
            track="romantic"
        )

        db.save_session_scene(
            session_id=session_id,
            scene_title="Rooftop",
            narrative="Sofia leans against the railing, grinning warmly.",
            choices=[],
            history=["Turn 1"],
            location="Westlake Academy ➔ School Rooftop",
            current_npcs=[{"name": "Sofia Anderson", "role": "Track Captain"}],
            dialogue_partner="Sofia Anderson"
        )

        class MockCheck:
            succeeded = True
            is_success = True
            tier = "success"
            chance = 90

        actions = [{
            "char": char,
            "label": "Chat with Sofia about the track tournament",
            "stat": "CHA",
            "check": MockCheck(),
            "mp_spent": 0
        }]
        session = db.get_session(session_id)

        with patch("game_engine.call_llm_json", new_callable=AsyncMock) as mock_call:
            mock_call.return_value = {
                "outcome_narrative": "They talk about the tournament.",
                "next_narrative": "Sofia smiles enthusiastically.",
                "next_choices": [{"label": "Continue conversation", "stat": "CHA", "requirement": 6}]
            }
            await game_engine.resolve_turn(session, [(char, [])], actions)

            self.assertTrue(mock_call.called)
            user_prompt = mock_call.call_args_list[0][0][1]
            self.assertIn("Intimate Demeanor: Blunt & Teasing", user_prompt)
            self.assertIn("Intimate Dynamic: Eagerly Receptive", user_prompt)
            self.assertIn("ROMANTIC & INTIMATE BEHAVIORAL DIVERSITY", user_prompt)
            self.assertIn("Do NOT default to generic anime stuttering", user_prompt)

        with db.get_conn() as conn:
            conn.execute("DELETE FROM sessions WHERE id = ?", (session_id,))
            conn.execute("DELETE FROM characters WHERE user_id = ?", (user_id,))
            conn.execute("DELETE FROM contacts WHERE session_id = ?", (session_id,))


if __name__ == "__main__":
    unittest.main()
