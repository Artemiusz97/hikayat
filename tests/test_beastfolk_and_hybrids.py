"""
Unit tests for Beastfolk species template expansion and Half-Beast / Hybrid race mechanics.
"""
import unittest
from mechanics.social.races import normalize_race, format_race_display, resolve_half_beast
from mechanics.social.persona import (
    SPECIES_TEMPLATES,
    is_half_beast_race,
    get_species_key_from_race,
    format_persona_embed_fields,
    infer_mannerism_default,
    generate_dynamic_intimate_attributes,
    SENSITIVE_SPOT_MAMMALIAN_BEASTFOLK_ITEMS
)


class TestBeastfolkAndHybrids(unittest.TestCase):

    def test_beastfolk_species_normalization(self):
        """Test normalization and aliases for all new and existing beastfolk species."""
        cases = {
            "tiger": "beastfolk:tiger",
            "tigress": "beastfolk:tiger",
            "lion": "beastfolk:lion",
            "lioness": "beastfolk:lion",
            "cheetah": "beastfolk:cheetah",
            "fennec": "beastfolk:fennec",
            "fennec_fox": "beastfolk:fennec",
            "mouse": "beastfolk:mouse",
            "rat": "beastfolk:mouse",
            "rodent": "beastfolk:mouse",
            "cat": "beastfolk:cat",
            "neko": "beastfolk:cat",
            "wolf": "beastfolk:wolf",
            "fox": "beastfolk:fox",
            "kitsune": "beastfolk:fox",
            "rabbit": "beastfolk:rabbit",
            "bunny": "beastfolk:rabbit",
            "bear": "beastfolk:bear",
        }
        for raw, expected in cases.items():
            self.assertEqual(normalize_race(raw, "fantasy"), expected, f"Failed for {raw}")

    def test_half_beast_normalization(self):
        """Test normalization of half-beast / hybrid inputs across formats."""
        cases = {
            "half-beast": "half_beast",
            "half_beast": "half_beast",
            "halfbeast": "half_beast",
            "hybrid": "hybrid",
            "beastkin": "half_beast",
            "demi-human": "half_beast",
            "half-cat": "half_beast:cat",
            "half_fox": "half_beast:fox",
            "wolf_hybrid": "hybrid:wolf",
            "half-tiger": "half_beast:tiger",
            "lion hybrid": "hybrid:lion",
            "cheetah half-beast": "half_beast:cheetah",
            "fennec hybrid": "hybrid:fennec",
            "half_mouse": "half_beast:mouse",
            "half_beast:bear": "half_beast:bear",
            "hybrid:rabbit": "hybrid:rabbit",
        }
        for raw, expected in cases.items():
            self.assertEqual(normalize_race(raw, "fantasy"), expected, f"Failed for {raw}")

    def test_race_display_formatting(self):
        """Test display formatting for beastfolk and half-beast / hybrids."""
        cases = {
            "beastfolk:tiger": "Tiger-Beastfolk",
            "beastfolk:lion": "Lion-Beastfolk",
            "beastfolk:cheetah": "Cheetah-Beastfolk",
            "beastfolk:fennec": "Fennec-Beastfolk",
            "beastfolk:mouse": "Mouse-Beastfolk",
            "half_beast:fox": "Fox Half-Beast",
            "half_beast:tiger": "Tiger Half-Beast",
            "hybrid:cat": "Cat Hybrid",
            "hybrid:wolf": "Wolf Hybrid",
            "half_beast": "Half-Beast",
            "hybrid": "Hybrid",
        }
        for code, expected in cases.items():
            self.assertEqual(format_race_display(code), expected, f"Failed display for {code}")

    def test_species_templates_integrity(self):
        """Verify all target species exist in SPECIES_TEMPLATES with full field sets."""
        target_species = ["cat", "wolf", "fox", "rabbit", "bear", "tiger", "lion", "cheetah", "fennec", "mouse"]
        for sp in target_species:
            self.assertIn(sp, SPECIES_TEMPLATES, f"Missing template for {sp}")
            tmpl = SPECIES_TEMPLATES[sp]
            self.assertTrue(len(tmpl["eyes"]) >= 4, f"{sp} eyes too small")
            self.assertTrue(len(tmpl["hair"]) >= 4, f"{sp} hair too small")
            self.assertTrue(len(tmpl["coats"]) >= 4, f"{sp} coats too small")
            self.assertTrue(len(tmpl["beastfolk_features"]) >= 3, f"{sp} beastfolk_features too small")
            self.assertTrue(len(tmpl["hybrid_features"]) >= 3, f"{sp} hybrid_features too small")
            self.assertTrue(len(tmpl["mannerisms"]) >= 4, f"{sp} mannerisms too small")

    def test_hybrid_features_color_harmony(self):
        """Verify all hybrid features contain color-matched ears/horns and tails."""
        for sp, tmpl in SPECIES_TEMPLATES.items():
            for feat in tmpl["hybrid_features"]:
                has_head_feat = any(k in feat for k in ("Ears", "Horns", "Horn", "Crests", "Crest", "Accents", "Buds"))
                self.assertTrue(has_head_feat, f"Hybrid feature missing Ears/Horns in {sp}: {feat}")
                self.assertIn("Tail", feat, f"Hybrid feature missing Tail in {sp}: {feat}")
                feat_lower = feat.lower()
                has_matching_keyword = any(k in feat_lower for k in ("matching", "and", "with", "&"))
                self.assertTrue(has_matching_keyword, f"Feature lacks cohesive descriptor in {sp}: {feat}")


    def test_embed_formatting_distinction(self):
        """Test that Discord profile embed fields display 'Hybrid Features' & 'Skin Color' for half-beasts, and 'Fur / Coat' for beastfolk."""
        # 1. Half-Beast
        hb_app = {
            "eye_color": "bright_amber",
            "hair_color": "flame_auburn",
            "skin_color": "fair",
            "skin_type": "skin",
            "distinctive_features": "Snow-White Fox Ears & Matching Bushy White Fox Tail"
        }
        hb_fields = format_persona_embed_fields(hb_app, race="half_beast:fox")
        hb_val = hb_fields[0]["value"]
        self.assertIn("Skin Color", hb_val)
        self.assertIn("Hybrid Features", hb_val)
        self.assertNotIn("Fur / Coat", hb_val)

        # 2. Full Beastfolk
        bf_app = {
            "eye_color": "burning_copper",
            "hair_color": "wild_black_striped_orange",
            "coat_color": "Flame-Orange Fur with Black Stripes",
            "skin_type": "furry",
            "distinctive_features": "Striped Tiger Ears & Powerful Ringed Tail"
        }
        bf_fields = format_persona_embed_fields(bf_app, race="beastfolk:tiger")
        bf_val = bf_fields[0]["value"]
        self.assertIn("Fur / Coat", bf_val)
        self.assertIn("Features", bf_val)
        self.assertNotIn("Hybrid Features", bf_val)

    def test_animalistic_mannerisms_generation(self):
        """Test that species-specific animalistic quirks are generated for each species."""
        for sp in ["cat", "wolf", "fox", "rabbit", "bear", "tiger", "lion", "cheetah", "fennec", "mouse"]:
            # Test beastfolk
            bf_manner = infer_mannerism_default(race=f"beastfolk:{sp}", desc=f"A {sp} character")
            self.assertTrue(len(bf_manner) > 0)
            self.assertIn(bf_manner, SPECIES_TEMPLATES[sp]["mannerisms"], f"Mannerism not in {sp} pool: {bf_manner}")

            # Test half-beast / hybrid
            hb_manner = infer_mannerism_default(race=f"half_beast:{sp}", desc=f"A {sp} hybrid")
            self.assertTrue(len(hb_manner) > 0)
            self.assertIn(hb_manner, SPECIES_TEMPLATES[sp]["mannerisms"], f"Mannerism not in {sp} pool: {hb_manner}")

    def test_furry_high_school_generation_distribution(self):
        """Verify the exact redistributed weights and categories for Furry High School Drama."""
        from mechanics.social.races import FURRY_HIGH_SCHOOL_RACES, FURRY_HIGH_SCHOOL_WEIGHTS
        self.assertEqual(len(FURRY_HIGH_SCHOOL_RACES), len(FURRY_HIGH_SCHOOL_WEIGHTS))
        self.assertAlmostEqual(sum(FURRY_HIGH_SCHOOL_WEIGHTS), 1.0, places=5)

        weight_map = dict(zip(FURRY_HIGH_SCHOOL_RACES, FURRY_HIGH_SCHOOL_WEIGHTS))

        # 1. Baseline Human (5%)
        self.assertAlmostEqual(weight_map["human"], 0.05)

        # 2. Cat (10%) & Fox (10%) Beastfolk
        self.assertAlmostEqual(weight_map["beastfolk:cat"], 0.10)
        self.assertAlmostEqual(weight_map["beastfolk:fox"], 0.10)

        # 3. Other 10 Beastfolk species (45% total -> 4.5% each)
        other_bf_species = [
            "beastfolk:wolf", "beastfolk:fennec", "beastfolk:tiger", "beastfolk:cheetah", "beastfolk:lion",
            "beastfolk:mouse", "beastfolk:rabbit", "beastfolk:bear", "beastfolk:bird", "beastfolk:reptile"
        ]
        for r in other_bf_species:
            self.assertAlmostEqual(weight_map[r], 0.045)
        self.assertAlmostEqual(sum(weight_map[r] for r in other_bf_species), 0.45)

        # 4. Cat & Fox Half-Beasts (10% total -> 5% each)
        self.assertAlmostEqual(weight_map["half_beast:cat"], 0.05)
        self.assertAlmostEqual(weight_map["half_beast:fox"], 0.05)

        # 5. Other 10 Half-Beast species (20% total -> 2% each)
        other_hb_species = [
            "half_beast:wolf", "half_beast:tiger", "half_beast:lion", "half_beast:cheetah",
            "half_beast:fennec", "half_beast:rabbit", "half_beast:mouse", "half_beast:bear",
            "half_beast:bird", "half_beast:reptile"
        ]
        for r in other_hb_species:
            self.assertAlmostEqual(weight_map[r], 0.02)
        self.assertAlmostEqual(sum(weight_map[r] for r in other_hb_species), 0.20)

        # Combined shares: Cat (15%), Fox (15%), Human (5%), All 10 others (6.5% each)
        for sp in ["wolf", "fennec", "tiger", "cheetah", "lion", "mouse", "rabbit", "bear", "bird", "reptile"]:
            comb = weight_map[f"beastfolk:{sp}"] + weight_map[f"half_beast:{sp}"]
            self.assertAlmostEqual(comb, 0.065)

        # Total Category Groupings
        bf_total = sum(w for r, w in weight_map.items() if r.startswith("beastfolk:"))
        hb_total = sum(w for r, w in weight_map.items() if r.startswith("half_beast:"))
        human_total = weight_map["human"]
        self.assertAlmostEqual(bf_total, 0.65)
        self.assertAlmostEqual(hb_total, 0.30)
        self.assertAlmostEqual(human_total, 0.05)

    def test_species_key_scunthorpe_collision_prevention(self):
        """Verify that substring collisions (e.g. 'rat' inside 'Preparatory' or 'Directorate')
        never override explicit race tags or cause false animal species classifications."""
        from mechanics.social.persona.core import is_scaly_race

        # 1. Explicit race tag with Scunthorpe-prone description
        mio_desc = "Junior at Northwood Preparatory Academy. High-energy, competitive. Role: Varsity Track Sprinter. Club: Athletic Directorate."
        self.assertEqual(get_species_key_from_race("beastfolk:cat", desc=mio_desc), "cat")
        self.assertEqual(get_species_key_from_race("Cat Beastfolk", desc=mio_desc), "cat")
        self.assertEqual(get_species_key_from_race("half_beast:cat", desc=mio_desc), "cat")

        # 2. Other explicit beastfolk races must never be overridden by description words
        fox_desc = "Student Council President with deep knowledge and bearing."
        self.assertEqual(get_species_key_from_race("beastfolk:fox", desc=fox_desc), "fox")

        rabbit_desc = "Received an accurate certificate in preparatory literature."
        self.assertEqual(get_species_key_from_race("beastfolk:rabbit", desc=rabbit_desc), "rabbit")

        # 3. Description without explicit race must NOT trigger false positive on substrings
        scunthorpe_prose = "Junior at Northwood Preparatory Academy under the Athletic Directorate."
        self.assertNotEqual(get_species_key_from_race("", desc=scunthorpe_prose), "mouse")
        self.assertIsNone(get_species_key_from_race("", desc=scunthorpe_prose))

        # 4. Description with actual word-boundary animal token correctly resolves
        valid_prose = "A nimble cat sprinter at Northwood Preparatory Academy."
        self.assertEqual(get_species_key_from_race("", desc=valid_prose), "cat")

        # 5. Scaly check Scunthorpe prevention
        self.assertFalse(is_scaly_race("human", desc="bearing accurate certificates"))


if __name__ == "__main__":
    unittest.main()
