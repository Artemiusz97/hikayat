"""
Unit tests for Beastfolk Hair Harmony and Dyed/Natural Hair Tracking.
"""
import unittest
from mechanics.social.persona import (
    normalize_appearance,
    format_persona_embed_fields,
    format_persona_summary,
    is_contrasting_shade,
    infer_natural_hair_color_from_coat
)


class TestBeastfolkHairDyeAndHarmony(unittest.TestCase):
    def test_infer_natural_hair_color_from_coat(self):
        self.assertEqual(infer_natural_hair_color_from_coat("golden-blonde fur"), "golden-blonde")
        self.assertEqual(infer_natural_hair_color_from_coat("Snow-White Kitsune Fur"), "snow-white kitsune")
        self.assertEqual(infer_natural_hair_color_from_coat("Dense Ash-Gray Fur"), "ash-gray")
        self.assertEqual(infer_natural_hair_color_from_coat("", race="beastfolk:fox"), "golden-blonde")

    def test_harmonious_coat_and_hair_not_contrasting(self):
        # Matching families
        self.assertFalse(is_contrasting_shade("golden-blonde fur", "golden-blonde"))
        self.assertFalse(is_contrasting_shade("golden-blonde fur", "blonde"))
        # Compatible warm shades (blonde + red/copper or warm light brown)
        self.assertFalse(is_contrasting_shade("golden-blonde fur", "red"))
        self.assertFalse(is_contrasting_shade("golden-blonde fur", "copper"))
        self.assertFalse(is_contrasting_shade("golden-blonde fur", "honey"))
        self.assertFalse(is_contrasting_shade("golden-blonde fur", "auburn"))
        # White coat + silver or platinum
        self.assertFalse(is_contrasting_shade("snow-white fur", "platinum blonde"))
        self.assertFalse(is_contrasting_shade("snow-white fur", "silver"))

    def test_contrasting_coat_and_hair_detected(self):
        # Golden-blonde fur with black hair (Maya Anderson case)
        self.assertTrue(is_contrasting_shade("golden-blonde fur", "black"))
        # Golden-blonde fur with blue hair
        self.assertTrue(is_contrasting_shade("golden-blonde fur", "blue"))
        # Snow-white fur with black hair
        self.assertTrue(is_contrasting_shade("snow-white fur", "black"))
        # Midnight-black fur with blonde hair
        self.assertTrue(is_contrasting_shade("midnight-black fur", "blonde"))

    def test_normalize_appearance_auto_tags_contrasting_beastfolk(self):
        app = {
            "hair_color": "black",
            "hair_length": "medium",
            "hair_style": "straight",
            "coat_color": "golden-blonde fur",
            "skin_type": "furry"
        }
        normalized = normalize_appearance(app, race="beastfolk:fox", scen_key="high_school_drama")
        self.assertTrue(normalized.get("is_dyed"))
        self.assertEqual(normalized.get("natural_hair_color"), "golden-blonde")

    def test_normalize_appearance_harmonious_beastfolk_not_dyed(self):
        app = {
            "hair_color": "golden-blonde",
            "hair_length": "short",
            "hair_style": "ponytail",
            "coat_color": "golden-blonde fur",
            "skin_type": "furry"
        }
        normalized = normalize_appearance(app, race="beastfolk:fox", scen_key="high_school_drama")
        self.assertFalse(normalized.get("is_dyed", False))

    def test_format_persona_embed_fields_displays_dyed_and_natural(self):
        app = {
            "hair_color": "black",
            "hair_length": "medium",
            "hair_style": "straight",
            "coat_color": "golden-blonde fur",
            "skin_type": "furry",
            "is_dyed": True,
            "natural_hair_color": "golden-blonde"
        }
        fields = format_persona_embed_fields(app, race="beastfolk:fox", scen_key="high_school_drama")
        app_text = fields[0]["value"]
        self.assertIn("• **Hair**: Medium Straight Black (Dyed; Natural: Golden-Blonde)", app_text)
        self.assertIn("• **Fur / Coat**: Golden-Blonde Fur", app_text)

    def test_format_persona_summary_includes_dye_context(self):
        app = {
            "hair_color": "black",
            "hair_length": "medium",
            "hair_style": "straight",
            "coat_color": "golden-blonde fur",
            "skin_type": "furry",
            "is_dyed": True,
            "natural_hair_color": "golden-blonde"
        }
        summary = format_persona_summary(app, scen_key="high_school_drama")
        self.assertIn("(dyed; naturally golden-blonde)", summary)


if __name__ == "__main__":
    unittest.main()
