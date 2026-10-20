import unittest
from mechanics.social.persona.intimacy.constants import (
    STATURE_TIERS,
    STATURES,
    STATURE_WEIGHTS_MINIATURE,
    STATURE_WEIGHTS_TINY_BEASTFOLK,
    STATURE_WEIGHTS_SMALL_BEASTFOLK,
    STATURE_WEIGHTS_LARGE_BEASTFOLK,
    STATURE_WEIGHTS_STANDARD,
    STATURE_INCOMPATIBLE_PHYSIQUES,
    PHYSIQUE_FEMALE_TEMPLATES,
    PHYSIQUE_MALE_TEMPLATES,
)
from mechanics.social.persona.intimacy.appearance import (
    normalize_stature_tier,
    get_stature_distribution_for_race,
    roll_dynamic_stature,
    roll_dynamic_physique,
    normalize_appearance,
    extract_appearance_from_text,
)
from mechanics.social.persona.core import format_persona_summary
from mechanics.social.persona.intimacy.formatting import format_persona_embed_fields


class TestStatureAndPhysiqueDiversity(unittest.TestCase):
    def test_canonical_stature_tiers_and_normalization(self):
        """Verifies the 5 canonical stature tiers and normalization aliases."""
        self.assertEqual(STATURE_TIERS, ("short", "below_average", "average", "tall", "towering"))
        for tier in STATURE_TIERS:
            self.assertIn(tier, STATURES)

        # Aliases and normalization
        self.assertEqual(normalize_stature_tier("short"), "short")
        self.assertEqual(normalize_stature_tier("dwarf"), "short")
        self.assertEqual(normalize_stature_tier("petite"), "short")
        self.assertEqual(normalize_stature_tier("below average"), "below_average")
        self.assertEqual(normalize_stature_tier("below-average"), "below_average")
        self.assertEqual(normalize_stature_tier("average"), "average")
        self.assertEqual(normalize_stature_tier("tall"), "tall")
        self.assertEqual(normalize_stature_tier("statuesque"), "tall")
        self.assertEqual(normalize_stature_tier("towering"), "towering")
        self.assertEqual(normalize_stature_tier("gigantic"), "towering")
        self.assertEqual(normalize_stature_tier("towering / gigantic"), "towering")

    def test_race_stature_distribution_weights(self):
        """Verifies exact user-requested probability weights per species archetype and gender."""
        # 1. Miniature races: 100% short for both genders
        for mini_race in ["dwarf", "gnome", "halfling", "goblin"]:
            for g in ["male", "female"]:
                dist = get_stature_distribution_for_race(mini_race, gender=g)
                self.assertEqual(dist["short"], 1.0)
                self.assertEqual(dist["below_average"], 0.0)
                self.assertEqual(dist["average"], 0.0)
                self.assertEqual(dist["tall"], 0.0)
                self.assertEqual(dist["towering"], 0.0)

        # 2. Male Standard Races (Default): 5, 15, 50, 25, 5
        for std_race in ["human", "elf", "dark_elf", "half-beast (fox)", "hybrid", "cheetah"]:
            dist_m = get_stature_distribution_for_race(std_race, gender="male")
            self.assertAlmostEqual(dist_m["short"], 0.05)
            self.assertAlmostEqual(dist_m["below_average"], 0.15)
            self.assertAlmostEqual(dist_m["average"], 0.50)
            self.assertAlmostEqual(dist_m["tall"], 0.25)
            self.assertAlmostEqual(dist_m["towering"], 0.05)
            self.assertAlmostEqual(sum(dist_m.values()), 1.0)

        # 3. Female Standard Races (Default): 10, 34, 45, 10, 1
        for std_race in ["human", "elf", "dark_elf", "half-beast (fox)", "hybrid", "cheetah"]:
            dist_f = get_stature_distribution_for_race(std_race, gender="female")
            self.assertAlmostEqual(dist_f["short"], 0.10)
            self.assertAlmostEqual(dist_f["below_average"], 0.34)
            self.assertAlmostEqual(dist_f["average"], 0.45)
            self.assertAlmostEqual(dist_f["tall"], 0.10)
            self.assertAlmostEqual(dist_f["towering"], 0.01)
            self.assertAlmostEqual(sum(dist_f.values()), 1.0)

        # 4. Male Large Beastfolk: 1, 4, 25, 45, 25 (No changes)
        for large_race in ["wolf", "tiger", "lion", "bear", "dragon", "orc"]:
            dist_m = get_stature_distribution_for_race(large_race, gender="male")
            self.assertAlmostEqual(dist_m["short"], 0.01)
            self.assertAlmostEqual(dist_m["below_average"], 0.04)
            self.assertAlmostEqual(dist_m["average"], 0.25)
            self.assertAlmostEqual(dist_m["tall"], 0.45)
            self.assertAlmostEqual(dist_m["towering"], 0.25)
            self.assertAlmostEqual(sum(dist_m.values()), 1.0)

        # 5. Female Large Beastfolk: 1, 14, 55, 20, 10
        for large_race in ["wolf", "tiger", "lion", "bear", "dragon", "orc"]:
            dist_f = get_stature_distribution_for_race(large_race, gender="female")
            self.assertAlmostEqual(dist_f["short"], 0.01)
            self.assertAlmostEqual(dist_f["below_average"], 0.14)
            self.assertAlmostEqual(dist_f["average"], 0.55)
            self.assertAlmostEqual(dist_f["tall"], 0.20)
            self.assertAlmostEqual(dist_f["towering"], 0.10)
            self.assertAlmostEqual(sum(dist_f.values()), 1.0)

        # 6. Small Agile Beastfolk
        # Male: 10, 30, 43, 15, 2
        for small_race in ["cat", "neko", "fox", "kitsune", "fennec"]:
            dist_m = get_stature_distribution_for_race(small_race, gender="male")
            self.assertAlmostEqual(dist_m["short"], 0.10)
            self.assertAlmostEqual(dist_m["below_average"], 0.30)
            self.assertAlmostEqual(dist_m["average"], 0.43)
            self.assertAlmostEqual(dist_m["tall"], 0.15)
            self.assertAlmostEqual(dist_m["towering"], 0.02)
            self.assertAlmostEqual(sum(dist_m.values()), 1.0)

            # Female: 15, 45, 34, 5, 1
            dist_f = get_stature_distribution_for_race(small_race, gender="female")
            self.assertAlmostEqual(dist_f["short"], 0.15)
            self.assertAlmostEqual(dist_f["below_average"], 0.45)
            self.assertAlmostEqual(dist_f["average"], 0.34)
            self.assertAlmostEqual(dist_f["tall"], 0.05)
            self.assertAlmostEqual(dist_f["towering"], 0.01)
            self.assertAlmostEqual(sum(dist_f.values()), 1.0)

        # 7. Tiny Beastfolk
        # Male: 34, 45, 15, 5, 1
        for tiny_race in ["rabbit", "bunny", "mouse", "rat", "hamster"]:
            dist_m = get_stature_distribution_for_race(tiny_race, gender="male")
            self.assertAlmostEqual(dist_m["short"], 0.34)
            self.assertAlmostEqual(dist_m["below_average"], 0.45)
            self.assertAlmostEqual(dist_m["average"], 0.15)
            self.assertAlmostEqual(dist_m["tall"], 0.05)
            self.assertAlmostEqual(dist_m["towering"], 0.01)
            self.assertAlmostEqual(sum(dist_m.values()), 1.0)

            # Female: 55, 35, 7, 2, 1
            dist_f = get_stature_distribution_for_race(tiny_race, gender="female")
            self.assertAlmostEqual(dist_f["short"], 0.55)
            self.assertAlmostEqual(dist_f["below_average"], 0.35)
            self.assertAlmostEqual(dist_f["average"], 0.07)
            self.assertAlmostEqual(dist_f["tall"], 0.02)
            self.assertAlmostEqual(dist_f["towering"], 0.01)
            self.assertAlmostEqual(sum(dist_f.values()), 1.0)

    def test_roll_dynamic_stature_outcomes(self):
        """Verifies dynamic rolling behavior and miniature locking with gender awareness."""
        # Dwarf is always short
        for seed in range(50):
            stat_m = roll_dynamic_stature("dwarf", gender="male", seed=f"dwarf_seed_m_{seed}")
            self.assertEqual(stat_m, "short")
            stat_f = roll_dynamic_stature("dwarf", gender="female", seed=f"dwarf_seed_f_{seed}")
            self.assertEqual(stat_f, "short")

        # Female rabbit is predominantly short (55%) or below average (35%)
        fem_rabbit_rolls = [roll_dynamic_stature("rabbit", gender="female", seed=f"fem_rab_{i}") for i in range(100)]
        short_count = sum(1 for s in fem_rabbit_rolls if s == "short")
        self.assertGreater(short_count, 35)

        # Large beastfolk male rolls predominantly tall/towering (70% combined)
        wolf_rolls = [roll_dynamic_stature("wolf", gender="male", seed=f"wolf_seed_{i}") for i in range(100)]
        tall_or_towering = sum(1 for s in wolf_rolls if s in ("tall", "towering"))
        self.assertGreater(tall_or_towering, 50)

    def test_physique_template_purification_and_new_entries(self):
        """Verifies template naming purification and new thick, overweight, and average templates."""
        # Muscular & Tall was removed in favor of Muscular & Powerful
        self.assertNotIn("Muscular & Tall", PHYSIQUE_MALE_TEMPLATES)
        self.assertIn("Muscular & Powerful", PHYSIQUE_MALE_TEMPLATES)

        # New female physiques
        self.assertIn("Thick & Curvy", PHYSIQUE_FEMALE_TEMPLATES)
        self.assertIn("Soft & Overweight", PHYSIQUE_FEMALE_TEMPLATES)

        # New male physiques
        self.assertIn("Average & Proportionate", PHYSIQUE_MALE_TEMPLATES)
        self.assertIn("Stocky & Thick", PHYSIQUE_MALE_TEMPLATES)
        self.assertIn("Heavy & Overweight", PHYSIQUE_MALE_TEMPLATES)

    def test_physique_stature_incompatibility(self):
        """Verifies that tall and towering characters CANNOT be Petite & Soft."""
        self.assertIn("Petite & Soft", STATURE_INCOMPATIBLE_PHYSIQUES["tall"])
        self.assertIn("Petite & Soft", STATURE_INCOMPATIBLE_PHYSIQUES["towering"])

        # Dynamic roll never gives Petite & Soft to tall or towering characters
        for seed in range(100):
            p_tall = roll_dynamic_physique(gender="female", stature="tall", race="human", seed=f"tall_{seed}")
            p_towering = roll_dynamic_physique(gender="female", stature="towering", race="human", seed=f"towering_{seed}")
            self.assertNotEqual(p_tall, "Petite & Soft")
            self.assertNotEqual(p_towering, "Petite & Soft")

        # normalize_appearance heals invalid Petite & Soft for tall/towering
        norm = normalize_appearance(
            raw_app={"stature": "tall", "physique": "Petite & Soft"},
            gender="female",
            race="human"
        )
        self.assertNotEqual(norm["physique"], "Petite & Soft")

    def test_physique_race_awareness_and_rollability(self):
        """Verifies race-awareness in physique weighting while keeping all options open."""
        # Large beastfolk generate toned/muscular with higher frequency
        large_rolls = [
            roll_dynamic_physique(gender="male", stature="average", race="tiger", seed=f"tiger_{i}")
            for i in range(100)
        ]
        athletic_count = sum(1 for p in large_rolls if p in ("Toned & Athletic", "Muscular & Powerful"))
        self.assertGreater(athletic_count, 35)

        # But large beastfolk can still roll other physiques (not locked out)
        unique_rolls = set(large_rolls)
        self.assertGreater(len(unique_rolls), 2)

        # Thick and overweight have low roll frequency but are rollable
        female_rolls = [
            roll_dynamic_physique(gender="female", stature="average", race="human", seed=f"fem_{i}")
            for i in range(200)
        ]
        thick_or_overweight = sum(1 for p in female_rolls if p in ("Thick & Curvy", "Soft & Overweight"))
        standard_count = sum(1 for p in female_rolls if p not in ("Thick & Curvy", "Soft & Overweight"))
        self.assertGreater(standard_count, thick_or_overweight)

    def test_narrative_extraction_and_formatting(self):
        """Verifies narrative extraction of below-average and UI formatting."""
        extracted = extract_appearance_from_text("Elena was of below-average height with soft curves.")
        self.assertEqual(extracted.get("stature"), "below_average")

        # Summary formatting
        summary = format_persona_summary({"stature": "below_average", "physique": "Soft & Curved"})
        self.assertIn("below average stature", summary)
        self.assertNotIn("below_average", summary)

        # Embed fields formatting
        fields = format_persona_embed_fields({"stature": "below_average", "physique": "Soft & Curved"})
        stat_field = next(f for f in fields if "Physical Appearance" in f["name"])
        self.assertIn("• **Stature**: Below Average", stat_field["value"])
        self.assertNotIn("below_average", stat_field["value"])

    def test_stature_and_physique_narrative_directive_content(self):
        """Verifies format_stature_and_physique_narrative_directive generates rich spatial and height-contrast rules."""
        from mechanics.social.persona.intimacy.formatting import format_stature_and_physique_narrative_directive

        # 1. Towering NPC vs Short Protagonist
        dir_towering = format_stature_and_physique_narrative_directive(
            partner_name="Goliath",
            npc_stature="towering",
            npc_physique="Muscular & Powerful",
            npc_gender="male",
            npc_race="orc",
            player_stature="short",
            player_physique="Petite & Soft",
            player_gender="female"
        )
        self.assertIn("[PHYSICAL SCALE & STATURE DYNAMICS (Goliath — Towering • Muscular & Powerful)]", dir_towering)
        self.assertIn("ducking slightly under standard doorframes", dir_towering)
        self.assertIn("Muscular & Powerful", dir_towering)
        self.assertIn("NPC Significantly Towers", dir_towering)
        self.assertIn("crane their neck upward and stand on tiptoes", dir_towering)

        # 2. Short NPC vs Tall Protagonist
        dir_short = format_stature_and_physique_narrative_directive(
            partner_name="Mimi",
            npc_stature="short",
            npc_physique="Petite & Soft",
            npc_gender="female",
            npc_race="mouse",
            player_stature="tall",
            player_physique="Broad Shoulders & Lean",
            player_gender="male"
        )
        self.assertIn("[PHYSICAL SCALE & STATURE DYNAMICS (Mimi — Short • Petite & Soft)]", dir_short)
        self.assertIn("Petite & Delicate", dir_short)
        self.assertIn("Protagonist Significantly Towers", dir_short)
        self.assertIn("effortlessly lifted", dir_short)

        # 3. Equal Eye-Level Height
        dir_equal = format_stature_and_physique_narrative_directive(
            partner_name="Aoi",
            npc_stature="average",
            npc_physique="Toned & Athletic",
            npc_gender="female",
            npc_race="human",
            player_stature="average",
            player_physique="Average & Proportionate",
            player_gender="male"
        )
        self.assertIn("Equal Eye-Level", dir_equal)
        self.assertIn("foreheads resting together", dir_equal)

        # 4. Thick & Curvy and Overweight physiques
        dir_thick = format_stature_and_physique_narrative_directive(
            partner_name="Livia",
            npc_stature="below_average",
            npc_physique="Thick & Curvy",
            npc_gender="female",
            npc_race="fox"
        )
        self.assertIn("Thick & Curvy", dir_thick)
        self.assertIn("heavy, prominent hips, thick thighs", dir_thick)

    def test_protagonist_physical_build_context_tracking(self):
        """Verifies _character_sheet_text tracks protagonist stature and physique in turn context."""
        from game_engine.context import _character_sheet_text

        char_data = {
            "name": "Kael",
            "gender": "male",
            "race": "human",
            "class_": "Warrior",
            "appearance": {
                "stature": "tall",
                "physique": "Broad Shoulders & Lean",
                "penis_size": "average"
            }
        }
        ctx_str = _character_sheet_text(char_data, [])
        self.assertIn("Physical Build: Stature: Tall | Physique: Broad Shoulders & Lean", ctx_str)
        self.assertIn("Incorporate the protagonist's physical scale", ctx_str)

    def test_dialogue_prompt_block_injects_stature_directive(self):
        """Ensures _build_dialogue_prompt_block injects the stature and physique spatial directive into prompts."""
        from game_engine.turn.dialogue import _build_dialogue_prompt_block
        from game_engine.turn_context import TurnContext

        mock_session = {"id": 999, "history": [], "scenario": "fantasy", "current_location": "tavern"}
        ctx = TurnContext(999, mock_session)

        # Save an NPC contact with stature and physique in TurnContext cache
        ctx._cache["contacts"] = [{
            "name": "Valen",
            "gender": "male",
            "race": "wolf",
            "relationship_score": 10,
            "appearance": {
                "stature": "towering",
                "physique": "Muscular & Powerful",
                "penis_size": "large"
            }
        }]

        protagonist = {
            "name": "Aria",
            "gender": "female",
            "appearance": {
                "stature": "short",
                "physique": "Petite & Soft",
                "breast_size": "B-Cup"
            }
        }

        dlg_prompt = _build_dialogue_prompt_block(
            mock_session,
            ctx,
            new_partners=["Valen"],
            party=[protagonist],
            actions=[]
        )

        self.assertIn("[PHYSICAL SCALE & STATURE DYNAMICS (Valen", dlg_prompt)
        self.assertIn("Towering", dlg_prompt)
        self.assertIn("Muscular & Powerful", dlg_prompt)
        self.assertIn("NPC Significantly Towers", dlg_prompt)


if __name__ == "__main__":
    unittest.main()
