"""
Unit tests for the Appearance System Overhaul:
1. Full Beastfolk vs Half-Beast distinction (coat_color vs skin_color).
2. Elimination of color words from Beastfolk features.
3. Cultural name-based skin tone inference for Humans and Half-Beasts (~70% primary, ~30% global).
4. Race-weighted skin tones for Fantasy Humanoids.
"""
import unittest
from mechanics.social.persona.core import (
    SPECIES_TEMPLATES,
    is_beast_race,
    is_half_beast_race,
    sanitize_beastfolk_features,
    infer_humanoid_skin_color,
    CULTURE_SKIN_TONE_POOLS,
    GLOBAL_SKIN_TONE_POOL,
    HUMANOID_RACE_SKIN_TONES,
    roll_hair_color_and_dye,
    infer_natural_hair_color,
    is_unnatural_hair_color,
    EXPANDED_HAIR_DYE_TEMPLATES,
    CULTURE_NATURAL_HAIR_POOLS,
    HUMANOID_RACE_NATURAL_HAIR_POOLS,
    get_color_families,
    is_contrasting_shade,
)
from mechanics.social.persona.intimacy.appearance import normalize_appearance, extract_appearance_from_text


class TestAppearanceSystemOverhaul(unittest.TestCase):

    def test_beastfolk_templates_no_color_in_features(self):
        """Verify that beastfolk_features in SPECIES_TEMPLATES across all species have 0 color adjectives."""
        color_words = {
            "black", "white", "gray", "grey", "silver", "golden", "gold",
            "cream", "calico", "brown", "ash", "red", "orange", "blue",
            "green", "pink", "chestnut", "auburn", "tawny", "charcoal", "amber"
        }
        for spec, tmpl in SPECIES_TEMPLATES.items():
            feats = tmpl.get("beastfolk_features", [])
            for feat in feats:
                words = [w.strip(",.&-").lower() for w in feat.split()]
                found_colors = set(words) & color_words
                self.assertFalse(
                    found_colors,
                    f"Species '{spec}' beastfolk_feature '{feat}' contains color words: {found_colors}"
                )

    def test_full_beastfolk_vs_half_beast_appearance(self):
        """Verify Full Beastfolk gets coat_color (no skin_color), while Half-Beast gets skin_color (no coat_color)."""
        # Full Beastfolk: rabbit
        app_rabbit = normalize_appearance(
            {}, gender="female", race="beastfolk:rabbit", scen_key="nsfw_high_school_drama", desc="A rabbit girl student", name="Mimi"
        )
        self.assertIsNotNone(app_rabbit.get("coat_color"))
        self.assertEqual(app_rabbit.get("skin_type"), "furry")
        self.assertIsNone(app_rabbit.get("skin_color"))
        self.assertIsNotNone(app_rabbit.get("distinctive_features"))

        # Half-Beast: rabbit
        app_half_rabbit = normalize_appearance(
            {}, gender="female", race="half_beast:rabbit", scen_key="nsfw_high_school_drama", desc="A demi-human bunny girl", name="Ruoxi Kobayashi"
        )
        self.assertIsNone(app_half_rabbit.get("coat_color"))
        self.assertEqual(app_half_rabbit.get("skin_type"), "skin")
        self.assertIsNotNone(app_half_rabbit.get("skin_color"))
        # Half-beast distinctive features should keep animal ear/tail features with colors
        self.assertIsNotNone(app_half_rabbit.get("distinctive_features"))

    def test_sanitize_beastfolk_features_runtime(self):
        """Verify sanitize_beastfolk_features cleans color words from legacy or LLM-generated features."""
        dirty = "Sleek Black Feline Tail & Twitching Ears"
        clean = sanitize_beastfolk_features(dirty)
        self.assertNotIn("black", clean.lower())
        self.assertIn("feline tail", clean.lower())

        dirty_calico = "Fluffy Calico Tail & Cat Ears"
        clean_calico = sanitize_beastfolk_features(dirty_calico)
        self.assertNotIn("calico", clean_calico.lower())
        self.assertIn("tail", clean_calico.lower())

    def test_cultural_humanoid_skin_tones_humans(self):
        """Verify Humans receive skin tones influenced by their cultural name origin."""
        # Scandinavian name: Andersson
        nordic_tones = {t[0] for t in CULTURE_SKIN_TONE_POOLS["scandinavian"]} | {t[0] for t in GLOBAL_SKIN_TONE_POOL}
        tone = infer_humanoid_skin_color("human", name="Freja Andersson", seed="fixed_seed_1")
        self.assertIn(tone, nordic_tones)

        # English name: Sterling
        english_tones = {t[0] for t in CULTURE_SKIN_TONE_POOLS["celtic_germanic"]} | {t[0] for t in GLOBAL_SKIN_TONE_POOL}
        tone_eng = infer_humanoid_skin_color("human", name="Henry Sterling", seed="fixed_seed_2")
        self.assertIn(tone_eng, english_tones)

        # African name: Mensah
        african_tones = {t[0] for t in CULTURE_SKIN_TONE_POOLS["african"]} | {t[0] for t in GLOBAL_SKIN_TONE_POOL}
        tone_afr = infer_humanoid_skin_color("human", name="Kwame Mensah", seed="fixed_seed_3")
        self.assertIn(tone_afr, african_tones)

    def test_fantasy_humanoid_skin_tones(self):
        """Verify fantasy humanoid races roll from their respective race-weighted distributions."""
        # Elf
        elf_tones = {t[0] for t in HUMANOID_RACE_SKIN_TONES["elf"]}
        elf_tone = infer_humanoid_skin_color("elf", seed="elf_seed_1")
        self.assertIn(elf_tone, elf_tones)

        # Dark Elf / Drow
        dark_elf_tones = {t[0] for t in HUMANOID_RACE_SKIN_TONES["dark_elf"]}
        drow_tone = infer_humanoid_skin_color("dark_elf", seed="drow_seed_1")
        self.assertIn(drow_tone, dark_elf_tones)

        # Dwarf
        dwarf_tones = {t[0] for t in HUMANOID_RACE_SKIN_TONES["dwarf"]}
        dwarf_tone = infer_humanoid_skin_color("dwarf", seed="dwarf_seed_1")
        self.assertIn(dwarf_tone, dwarf_tones)

    def test_half_beast_independent_hair_and_features(self):
        """Verify Half-Beasts retain distinct colors for animal ears/tail and head hair alongside skin tone."""
        app = normalize_appearance(
            {
                "distinctive_features": "Ash-Brown Rabbit Ears & Matching Soft Brown Puff Tail",
                "hair_color": "snow-white"
            },
            gender="female",
            race="half_beast:rabbit",
            name="Ruoxi Kobayashi"
        )
        self.assertEqual(app["distinctive_features"], "Ash-Brown Rabbit Ears & Matching Soft Brown Puff Tail")
        self.assertEqual(app["hair_color"], "snow-white")
        self.assertIsNotNone(app.get("skin_color"))
        self.assertEqual(app.get("skin_type"), "skin")
        self.assertIsNone(app.get("coat_color"))

    def test_hair_dye_rate_35_percent(self):
        """Verify the unified 35% hair dye rate produces approximately 35% dyed hair across large samples."""
        dyed_count = 0
        total = 500
        for i in range(total):
            hair_color, is_dyed, natural_color = roll_hair_color_and_dye(
                race="human",
                name="Character Name",
                seed=f"seed_test_{i}"
            )
            if is_dyed:
                dyed_count += 1
                self.assertIsNotNone(natural_color)
                # Dyed color should differ or be an unnatural/dye tone
                self.assertNotEqual(hair_color.lower(), natural_color.lower())
            else:
                self.assertEqual(hair_color.lower(), natural_color.lower())

        ratio = dyed_count / total
        # Expected around 0.35 +/- 0.06
        self.assertGreater(ratio, 0.28, f"Dyed ratio {ratio} too low for 35% target")
        self.assertLess(ratio, 0.42, f"Dyed ratio {ratio} too high for 35% target")

    def test_half_beast_ear_fur_vs_human_heritage_hair(self):
        """Verify Half-Beasts can express natural hair matching ear/tail fur or human name cultural heritage."""
        ear_feature = "Silver-White Fox Ears & Bushy Tail"
        # Test Japanese name
        match_ear_count = 0
        match_human_count = 0
        total = 200
        for i in range(total):
            nat = infer_natural_hair_color(
                race="half_beast:fox",
                name="Ruoxi Kobayashi",
                ear_tail_feature=ear_feature,
                seed=f"half_beast_seed_{i}"
            )
            if "silver" in nat or "white" in nat:
                match_ear_count += 1
            else:
                match_human_count += 1

        self.assertGreater(match_ear_count, 0, "Expected some ear/tail fur color matches")
        self.assertGreater(match_human_count, 0, "Expected some human heritage color matches")

    def test_llm_custom_dye_color_detection(self):
        """Verify LLM-provided unnatural hair colors (e.g. bubblegum pink, neon blue) are detected as dyed."""
        # Unnatural / Anime color from LLM
        app_dyed = normalize_appearance(
            {"hair_color": "neon electric magenta"},
            gender="female",
            race="human",
            name="Alice Sterling"
        )
        self.assertTrue(app_dyed.get("is_dyed"))
        self.assertEqual(app_dyed.get("hair_color"), "neon electric magenta")
        self.assertIsNotNone(app_dyed.get("natural_hair_color"))
        self.assertNotEqual(app_dyed.get("natural_hair_color"), "neon electric magenta")

        # Natural color from LLM
        app_nat = normalize_appearance(
            {"hair_color": "dark raven-black"},
            gender="male",
            race="human",
            name="Ruoxi Kobayashi"
        )
        self.assertFalse(app_nat.get("is_dyed", False))
        self.assertEqual(app_nat.get("hair_color"), "dark raven-black")
        self.assertIsNone(app_nat.get("natural_hair_color"))

    def test_mammalian_beastfolk_varied_and_fantasy_coat_colors(self):
        """Verify mammalian beastfolk templates contain both natural and vibrant/fantasy coat colors."""
        mammals = ["cat", "fox", "wolf", "rabbit", "bear", "tiger", "lion", "cheetah", "fennec", "mouse"]
        for spec in mammals:
            coats = SPECIES_TEMPLATES[spec].get("coats", [])
            self.assertGreater(len(coats), 5, f"Species {spec} should have rich coat variety")
            # Check for chromatic variety (blue, pink, green, violet, etc.)
            all_fams = set()
            for c in coats:
                all_fams.update(get_color_families(c))
            self.assertTrue(
                any(f in all_fams for f in ("blue", "pink", "green", "purple")),
                f"Species {spec} should have fantasy/varied chromatic coats, found: {all_fams}"
            )

    def test_beastfolk_natural_hair_matches_coat_shade(self):
        """Verify beastfolk natural hair inherits the coat color family and is NOT flagged as dyed."""
        # Blue cat with matching blue hair
        app_blue = normalize_appearance(
            {"coat_color": "Vibrant Azure-Blue Fur", "hair_color": "azure-blue"},
            gender="female",
            race="beastfolk:cat",
            name="Aoi"
        )
        self.assertFalse(app_blue.get("is_dyed", False), "Matching blue hair should NOT be flagged as dyed")
        self.assertEqual(app_blue.get("coat_color"), "Vibrant Azure-Blue Fur")
        self.assertEqual(app_blue.get("hair_color"), "azure-blue")

        # Pink rabbit with matching pink hair
        app_pink = normalize_appearance(
            {"coat_color": "Pastel Sakura-Pink Fur", "hair_color": "soft sakura pink"},
            gender="female",
            race="beastfolk:rabbit",
            name="Mimi"
        )
        self.assertFalse(app_pink.get("is_dyed", False), "Matching pink hair should NOT be flagged as dyed")

    def test_beastfolk_dyed_hair_strictly_contrasting_shade(self):
        """Verify dyed hair on a beastfolk is guaranteed to be a completely different shade family than their coat."""
        # Test 100 forced dye rolls on a blue-furred fox
        coat = "Vibrant Azure-Blue Fur"
        coat_fams = get_color_families(coat)
        self.assertIn("blue", coat_fams)

        for i in range(100):
            hair_color, is_dyed, natural_color = roll_hair_color_and_dye(
                race="beastfolk:fox",
                name="Kitsune Character",
                coat_color=coat,
                seed=f"test_dye_seed_{i}",
                force_dye=True
            )
            self.assertTrue(is_dyed)
            hair_fams = get_color_families(hair_color)
            # The dye must NEVER share any family with the coat (no blue/cyan/azure/teal)
            overlap = hair_fams & coat_fams
            self.assertFalse(
                overlap,
                f"Dyed hair '{hair_color}' shares color family {overlap} with coat '{coat}'"
            )
            self.assertTrue(
                is_contrasting_shade(coat, hair_color),
                f"Dyed hair '{hair_color}' must contrast with coat '{coat}'"
            )

        # Test contrasting detection in normalize_appearance: blue fur + red hair = dyed
        app_contrast = normalize_appearance(
            {"coat_color": "Vibrant Azure-Blue Fur", "hair_color": "crimson red"},
            gender="female",
            race="beastfolk:cat",
            name="Aoi"
        )
        self.assertTrue(app_contrast.get("is_dyed"))
        self.assertEqual(app_contrast.get("hair_color"), "crimson red")
        self.assertEqual(app_contrast.get("natural_hair_color"), "vibrant azure-blue")

    def test_custom_llm_coat_and_hair_in_prose_and_json(self):
        """Verify custom LLM coats and hair colors are supported in both narrative prose and JSON."""
        # 1. Custom LLM coat in narrative prose
        prose = "A slender fox girl with shimmering cerulean-blue fur and alert ears enters the room."
        extracted = extract_appearance_from_text(prose)
        self.assertIn("coat_color", extracted)
        self.assertIn("cerulean-blue", extracted["coat_color"])

        # 2. Custom LLM exotic coat in JSON with matching hair
        app_custom = normalize_appearance(
            {"coat_color": "holographic mint-green fur", "hair_color": "mint-green"},
            gender="female",
            race="beastfolk:fox",
            name="Minty"
        )
        self.assertFalse(app_custom.get("is_dyed", False))
        self.assertEqual(app_custom.get("coat_color"), "holographic mint-green fur")

        # 3. Custom LLM exotic coat with contrasting dyed hair
        app_custom_dyed = normalize_appearance(
            {"coat_color": "holographic mint-green fur", "hair_color": "jet-black"},
            gender="female",
            race="beastfolk:fox",
            name="Minty"
        )
        self.assertTrue(app_custom_dyed.get("is_dyed"))
        self.assertEqual(app_custom_dyed.get("hair_color"), "jet-black")
        self.assertIn("mint-green", app_custom_dyed.get("natural_hair_color"))

    def test_extract_appearance_from_copula_verbs_and_complexions(self):
        """Verify extract_appearance_from_text reliably parses 'fur was X', 'hair was dyed Y', and complexion tones."""
        # 1. Copula verb structures (fur was ..., hair was dyed ...)
        text1 = "A Kitsune maiden whose fur was snow-white and her hair was dyed crimson-red."
        ex1 = extract_appearance_from_text(text1)
        self.assertEqual(ex1.get("coat_color"), "snow-white fur")
        self.assertEqual(ex1.get("skin_type"), "furry")
        self.assertEqual(ex1.get("hair_color"), "crimson-red")
        self.assertTrue(ex1.get("is_dyed"))

        # 2. Humanoid with eyes of X and complexion
        text2 = "A tall warrior with eyes of smoldering amber and porcelain skin."
        ex2 = extract_appearance_from_text(text2)
        self.assertEqual(ex2.get("stature"), "tall")
        self.assertEqual(ex2.get("eye_color"), "smoldering_amber")
        self.assertEqual(ex2.get("skin_color"), "porcelain skin")

        # 3. Scaly beastfolk with iridescent scales and jet-black hair
        text3 = "A fierce dragonkin with iridescent emerald scales and short jet-black hair."
        ex3 = extract_appearance_from_text(text3)
        self.assertEqual(ex3.get("coat_color"), "iridescent emerald scales")
        self.assertEqual(ex3.get("skin_type"), "scaly")
        self.assertEqual(ex3.get("hair_color"), "jet-black")


if __name__ == "__main__":
    unittest.main()
