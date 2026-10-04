"""
Unit tests for Beastfolk Reptile, Dragon, and Scaly Subspecies Template Mechanics.
"""
import unittest
from mechanics.social.races import normalize_race, format_race_display, resolve_half_beast
from mechanics.social.persona import (
    SPECIES_TEMPLATES,
    DIVERSE_BEASTFOLK_SCALES,
    is_scaly_race,
    is_half_beast_race,
    get_species_key_from_race,
    format_persona_embed_fields,
    infer_natural_hair_color_from_coat,
    infer_mannerism_default,
    normalize_appearance
)


class TestBeastfolkScales(unittest.TestCase):

    def test_scaly_race_detection(self):
        scaly_cases = [
            "reptile", "beastfolk:reptile", "Reptile-Beastfolk", "lizard", "gecko", "chameleon",
            "dragon", "beastfolk:dragon", "Dragonkin", "draconoid", "draconic", "drake", "wyvern",
            "snake", "beastfolk:snake", "serpent", "serpentine", "viper", "cobra", "naga",
            "alligator", "crocodile", "gator", "crocodilian", "saurian"
        ]
        for r in scaly_cases:
            self.assertTrue(is_scaly_race(r), f"Failed to identify scaly race: {r}")

        non_scaly_cases = ["cat", "wolf", "fox", "rabbit", "bear", "tiger", "lion", "mouse", "human", "elf"]
        for r in non_scaly_cases:
            self.assertFalse(is_scaly_race(r), f"Falsely identified scaly race: {r}")

    def test_species_key_extraction(self):
        self.assertEqual(get_species_key_from_race("beastfolk:reptile"), "reptile")
        self.assertEqual(get_species_key_from_race("Reptile-Beastfolk"), "reptile")
        self.assertEqual(get_species_key_from_race("lizard"), "reptile")
        self.assertEqual(get_species_key_from_race("gecko"), "reptile")
        self.assertEqual(get_species_key_from_race("beastfolk:dragon"), "dragon")
        self.assertEqual(get_species_key_from_race("Dragonkin"), "dragon")
        self.assertEqual(get_species_key_from_race("draconoid"), "dragon")
        self.assertEqual(get_species_key_from_race("drake"), "dragon")
        self.assertEqual(get_species_key_from_race("beastfolk:snake"), "snake")
        self.assertEqual(get_species_key_from_race("serpentine"), "snake")
        self.assertEqual(get_species_key_from_race("viper"), "snake")

    def test_scaly_species_templates_integrity(self):
        for sp in ["reptile", "dragon", "snake"]:
            self.assertIn(sp, SPECIES_TEMPLATES, f"Missing template for {sp}")
            tmpl = SPECIES_TEMPLATES[sp]
            self.assertTrue(len(tmpl["eyes"]) >= 4, f"{sp} eyes too small")
            self.assertTrue(len(tmpl["hair"]) >= 4, f"{sp} hair too small")
            self.assertTrue(len(tmpl["coats"]) >= 4, f"{sp} coats/scales too small")
            self.assertTrue(len(tmpl["scales"]) >= 4, f"{sp} scales too small")
            self.assertTrue(len(tmpl["beastfolk_features"]) >= 3, f"{sp} beastfolk_features too small")
            self.assertTrue(len(tmpl["hybrid_features"]) >= 3, f"{sp} hybrid_features too small")
            self.assertTrue(len(tmpl["mannerisms"]) >= 4, f"{sp} mannerisms too small")

            for scale in tmpl["scales"]:
                self.assertNotIn("fur", scale.lower(), f"{sp} scale template contained fur: {scale}")
                self.assertIn("scale", scale.lower(), f"{sp} scale template missing scale word: {scale}")

    def test_diverse_scale_palette_templates(self):
        self.assertTrue(len(DIVERSE_BEASTFOLK_SCALES) >= 12)
        scale_str = " ".join(DIVERSE_BEASTFOLK_SCALES).lower()
        self.assertIn("smooth", scale_str)
        self.assertIn("gecko", scale_str)
        self.assertIn("flame", scale_str)
        self.assertIn("blue", scale_str)
        self.assertIn("emerald", scale_str)
        self.assertIn("obsidian", scale_str)
        self.assertIn("iridescent", scale_str)


    def test_embed_display_scales_formatting(self):
        reptile_app = {
            "eye_color": "ruby_red",
            "hair_color": "black",
            "hair_length": "medium",
            "hair_style": "straight",
            "stature": "average",
            "physique": "soft & curved",
            "coat_color": "Shiny Smooth Emerald Scales",
            "skin_type": "scaly",
            "distinctive_features": "Reptilian Horns & Scaled Tail",
            "outfit_style": "Standard Westlake Academy School Uniform"
        }
        fields = format_persona_embed_fields(reptile_app, gender="female", race="beastfolk:reptile")
        appearance_text = fields[0]["value"]
        self.assertIn("• **Scales**: Shiny Smooth Emerald Scales", appearance_text)
        self.assertNotIn("Fur / Coat", appearance_text)
        self.assertNotIn("Fur", appearance_text)

        dragon_app = {
            "eye_color": "molten_gold",
            "hair_color": "crimson",
            "coat_color": "Flame-Red Dragon Scales",
            "skin_type": "scaly",
            "distinctive_features": "Draconic Horns & Heavy Spined Dragon Tail"
        }
        dragon_fields = format_persona_embed_fields(dragon_app, gender="female", race="beastfolk:dragon")
        dragon_text = dragon_fields[0]["value"]
        self.assertIn("• **Scales**: Flame-Red Dragon Scales", dragon_text)
        self.assertNotIn("Fur / Coat", dragon_text)

        hb_dragon_app = {
            "eye_color": "molten_gold",
            "hair_color": "crimson",
            "skin_color": "Pale White",
            "skin_type": "skin",
            "distinctive_features": "Flame-Red Dragon Horns & Matching Spined Flame Tail"
        }
        hb_fields = format_persona_embed_fields(hb_dragon_app, gender="female", race="half_beast:dragon")
        hb_text = hb_fields[0]["value"]
        self.assertIn("• **Skin Color**: Pale White", hb_text)
        self.assertIn("• **Hybrid Features**: Flame-Red Dragon Horns & Matching Spined Flame Tail", hb_text)
        self.assertNotIn("Scales", hb_text)
        self.assertNotIn("Fur / Coat", hb_text)

    def test_natural_hair_color_inference_from_scales(self):
        self.assertEqual(infer_natural_hair_color_from_coat("Shiny Smooth Emerald Scales", "beastfolk:reptile"), "emerald")
        self.assertEqual(infer_natural_hair_color_from_coat("Flame-Red Dragon Scales", "beastfolk:dragon"), "flame-red")
        self.assertEqual(infer_natural_hair_color_from_coat("Shiny Blue Cerulean Scales", "beastfolk:dragon"), "blue cerulean")
        self.assertEqual(infer_natural_hair_color_from_coat("Gecko-Like Pale Mint Scales", "beastfolk:reptile"), "pale mint")


if __name__ == "__main__":
    unittest.main()
