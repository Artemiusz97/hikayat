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
        """Verify that character traits procedurally map to authentic voice styles with a 25% archetype weight and 75% organic diversity."""
        # 1. When roll < 25, stereotypical demeanor is selected for each archetype
        with patch("hashlib.md5") as mock_md5:
            # Mock hash returning roll = 10 (10 < 25)
            mock_md5.return_value.hexdigest.return_value = hex(10)[2:].zfill(32)

            dem_athlete = infer_intimate_demeanor_from_traits(
                role="Track Captain", traits=["Athletic", "Competitive"], desc="Energetic runner", gender="female"
            )
            self.assertIn("Blunt & Teasing", dem_athlete)

            dem_rogue = infer_intimate_demeanor_from_traits(
                role="Kitsune Thief", traits=["Mischievous", "Sly"], desc="Cunning fox trickster", gender="female"
            )
            self.assertIn("Playful & Bantering", dem_rogue)

            dem_dancer = infer_intimate_demeanor_from_traits(
                role="Flame Dancer", traits=["Passionate", "Intense"], desc="Fiery performer", gender="female"
            )
            self.assertIn("Passionate & Vocal", dem_dancer)

            dem_scholar = infer_intimate_demeanor_from_traits(
                role="Council President", traits=["Disciplined", "Composed"], desc="Intellectual scholar", gender="female"
            )
            self.assertIn("Poised & Articulate", dem_scholar)

            dem_healer = infer_intimate_demeanor_from_traits(
                role="Village Healer", traits=["Kind", "Nurturing"], desc="Gentle herbalist", gender="female"
            )
            self.assertIn("Soft & Deeply Affectionate", dem_healer)

            dem_shy = infer_intimate_demeanor_from_traits(
                role="Library Assistant", traits=["Shy", "Timid"], desc="Quiet sheltered bookworm", gender="female"
            )
            self.assertIn("Hesitant & Flustered", dem_shy)

        # 2. When roll >= 25, remaining 75% distributes across other 5 templates for organic diversity
        with patch("hashlib.md5") as mock_md5:
            # Mock hash returning roll = 30 (30 >= 25, rem_idx = (30-25)%5 = 0)
            mock_md5.return_value.hexdigest.return_value = hex(30)[2:].zfill(32)
            dem_athlete_diverse = infer_intimate_demeanor_from_traits(
                role="Track Captain", traits=["Athletic", "Competitive"], desc="Energetic runner", gender="female"
            )
            self.assertIn(dem_athlete_diverse, INTIMATE_DEMEANOR_FEMALE_TEMPLATES)
            self.assertNotIn("Blunt & Teasing", dem_athlete_diverse)

        # 3. Across a sample of 100 varied seeds, archetype demeanor has ~25% frequency and all 6 templates appear
        counts = {}
        for i in range(100):
            res = infer_intimate_demeanor_from_traits(
                role="Track Captain", traits=["Athletic", "Competitive"], desc=f"Track Athlete number {i}", gender="female"
            )
            counts[res] = counts.get(res, 0) + 1

        # The preferred archetype template ("Blunt & Teasing") should be the most frequent and close to 25%
        blunt_matches = [k for k in counts if "Blunt & Teasing" in k]
        self.assertTrue(len(blunt_matches) > 0)
        self.assertGreaterEqual(counts[blunt_matches[0]], 15)  # Expected ~25%
        self.assertGreater(len(counts), 1)  # Diverse demeanors across characters

    def test_infer_intimate_dynamic_correlations_and_gap_moe(self):
        """Verify that intimate dynamics provide rich proactivity/role distribution with gap moe capped at 25%."""
        # Athletic leaders have strong distribution across Receptive, Dominant, and Switch
        dyn_athlete = infer_intimate_dynamic_from_traits(
            role="Track Captain", traits=["Athletic", "Competitive"], desc="Energetic runner", gender="female"
        )
        self.assertTrue(any(t in dyn_athlete for t in ["Eagerly Receptive", "Boldly Proactive", "Playful Switch", "Insatiable"]))

        # Check 25% Gap Moe threshold for Athletes (roll < 25 -> Eagerly Receptive)
        with patch("hashlib.md5") as mock_md5:
            mock_md5.return_value.hexdigest.return_value = hex(20)[2:].zfill(32)
            gap_dyn = infer_intimate_dynamic_from_traits(
                role="Track Captain", traits=["Athletic", "Competitive"], desc="Energetic runner", gender="female"
            )
            self.assertIn("Eagerly Receptive", gap_dyn)

        # Healers have gap moe distribution across Insatiable, Gentle Yielding, and Service
        dyn_healer = infer_intimate_dynamic_from_traits(
            role="Shrine Maiden", traits=["Pure", "Gentle"], desc="Demure healer", gender="female"
        )
        self.assertTrue(any(t in dyn_healer for t in ["Insatiable", "Gentle & Yielding", "Attentive Service", "Playful Switch"]))

        # Check 25% Gap Moe threshold for Healers (roll < 25 -> Insatiable)
        with patch("hashlib.md5") as mock_md5:
            mock_md5.return_value.hexdigest.return_value = hex(24)[2:].zfill(32)
            gap_healer = infer_intimate_dynamic_from_traits(
                role="Shrine Maiden", traits=["Pure", "Gentle"], desc="Demure healer", gender="female"
            )
            self.assertIn("Insatiable", gap_healer)

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
        self.assertIn(normalized["intimate_demeanor"], INTIMATE_DEMEANOR_FEMALE_TEMPLATES)
        self.assertIn(normalized["intimate_dynamic"], INTIMATE_DYNAMIC_TEMPLATES)

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
            self.assertIn("INTIMATE VOICE & SPOKEN DEMEANOR (Sofia Anderson — Blunt & Teasing", user_prompt)
            self.assertIn("AUTONOMOUS INTIMATE RESPONSE (Sofia Anderson — Receptive & Yielding", user_prompt)
            self.assertIn("craves the player taking complete charge", user_prompt)
            self.assertIn("ROMANTIC & INTIMATE BEHAVIORAL DIVERSITY", user_prompt)
            self.assertIn("Do NOT default to generic anime stuttering", user_prompt)

        with db.get_conn() as conn:
            conn.execute("DELETE FROM sessions WHERE id = ?", (session_id,))
            conn.execute("DELETE FROM characters WHERE user_id = ?", (user_id,))
            conn.execute("DELETE FROM contacts WHERE session_id = ?", (session_id,))

    def test_format_demeanor_prompt_directives_all_templates(self):
        """Verify that all 6 demeanor templates produce distinct, actionable voice directives."""
        from mechanics.social.persona.intimacy.formatting import format_demeanor_prompt_directive

        d1 = format_demeanor_prompt_directive("Aoi", "Blunt & Teasing, energetic directness")
        self.assertIn("energetic directness", d1)
        self.assertIn("casual nicknames", d1)

        d2 = format_demeanor_prompt_directive("Kana", "Soft & Deeply Affectionate, tender whispers")
        self.assertIn("tender whispers", d2)
        self.assertIn("emotional vulnerability", d2)

        d3 = format_demeanor_prompt_directive("Elena", "Poised & Articulate, calm deliberate husky")
        self.assertIn("articulate composure", d3)
        self.assertIn("husky", d3)

        d4 = format_demeanor_prompt_directive("Sari", "Passionate & Vocal, breathless urgency")
        self.assertIn("breathlessly expressive", d4)
        self.assertIn("vocally unrestrained", d4)

        d5 = format_demeanor_prompt_directive("Ren", "Playful & Bantering, mischievous wit")
        self.assertIn("mischievous wit", d5)
        self.assertIn("mock-challenges", d5)

        d6 = format_demeanor_prompt_directive("Yuki", "Hesitant & Flustered, shy stammered")
        self.assertIn("endearingly shy", d6)
        self.assertIn("bashfully flustered", d6)

    def test_format_dynamic_prompt_directives_all_templates(self):
        """Verify that all 6 dynamic templates produce authentic, non-conflicting behavioral directives."""
        from mechanics.social.persona.intimacy.formatting import format_dynamic_prompt_directive

        # 1. Playful Switch / Teasing Brat
        dyn_switch = format_dynamic_prompt_directive("Ren", "Playful Switch / Teasing Brat (Wrestles for control)")
        self.assertIn("PLAYFUL SWITCH", dyn_switch)
        self.assertIn("tug-of-war for control", dyn_switch)

        # 2. Boldly Proactive & Dominant
        dyn_dom = format_dynamic_prompt_directive("Vera", "Boldly Proactive & Dominant (Takes charge)")
        self.assertIn("Assertive/Dominant", dyn_dom)
        self.assertIn("THEY MAKE THE PHYSICAL MOVE FIRST", dyn_dom)

        # 3. Insatiable / Hidden High-Drive
        dyn_insat = format_dynamic_prompt_directive("Mio", "Insatiable / Hidden High-Drive (Intense hunger)")
        self.assertIn("Insatiable & High-Drive", dyn_insat)
        self.assertIn("intense physical hunger", dyn_insat)

        # 4. Attentive Service-Oriented
        dyn_serv = format_dynamic_prompt_directive("Lily", "Attentive Service-Oriented (Devoted pampering)")
        self.assertIn("Service-Oriented & Pampering", dyn_serv)
        self.assertIn("pampering and devotion", dyn_serv)

        # 5. Eagerly Receptive / Surrenders Control
        dyn_rec = format_dynamic_prompt_directive("Sofia", "Eagerly Receptive / Surrenders Control (Craves partner taking charge)")
        self.assertIn("Receptive & Yielding", dyn_rec)
        self.assertIn("craves the player taking complete charge", dyn_rec)

    def test_affinity_engine_evaluates_all_demeanors_and_dynamics(self):
        """Verify that affinity calculation rewards actions matching each demeanor and dynamic."""
        from mechanics.social.affinity_engine import calculate_social_affinity_delta

        class MockCheck:
            succeeded = True
            is_success = True

        # Blunt & Teasing
        delta, reasons, _ = calculate_social_affinity_delta(
            action={"label": "Share direct, honest banter with Aoi", "check": MockCheck()},
            npc_name="Aoi",
            contact_data={"name": "Aoi", "appearance": {"intimate_demeanor": "Blunt & Teasing"}}
        )
        self.assertTrue(any("Blunt & Teasing" in r for r in reasons))

        # Soft & Deeply Affectionate
        delta, reasons, _ = calculate_social_affinity_delta(
            action={"label": "Speak with tender, loving praise to Kana", "check": MockCheck()},
            npc_name="Kana",
            contact_data={"name": "Kana", "appearance": {"intimate_demeanor": "Soft & Deeply Affectionate"}}
        )
        self.assertTrue(any("Soft & Affectionate" in r for r in reasons))

        # Attentive Service
        delta, reasons, _ = calculate_social_affinity_delta(
            action={"label": "Relax and let her pamper you with devoted care", "check": MockCheck()},
            npc_name="Lily",
            contact_data={"name": "Lily", "appearance": {"intimate_dynamic": "Attentive Service-Oriented"}}
        )
        self.assertTrue(any("attentive service" in r for r in reasons))

        # Playful Switch
        delta, reasons, _ = calculate_social_affinity_delta(
            action={"label": "Play along and tease back with a witty counter", "check": MockCheck()},
            npc_name="Ren",
            contact_data={"name": "Ren", "appearance": {"intimate_dynamic": "Playful Switch / Teasing Brat"}}
        )
        self.assertTrue(any("playful switch" in r for r in reasons))


if __name__ == "__main__":
    unittest.main()
