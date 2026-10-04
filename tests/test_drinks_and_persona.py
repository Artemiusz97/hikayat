import pytest
import random
from mechanics.combat.items.consumables import (
    generate_procedural_food,
    generate_procedural_drink,
    FOOD_TASTE_TAGS,
    DRINK_TASTE_TAGS,
    DRINK_EFFECT_TAGS,
    DRINK_SCALING,
    FOOD_SCALING,
    generate_drink_name,
    generate_food_name,
    parse_item_effect,
    classify_and_enrich_ad_hoc_item,
    evaluate_gift_reaction
)
from mechanics.combat.traits import (
    GROUNDED_FOOD_LIKES,
    GROUNDED_FOOD_DISLIKES,
    GROUNDED_DRINK_LIKES,
    GROUNDED_DRINK_DISLIKES,
    assign_npc_preferences,
    is_gift_item
)


class TestDrinkTaxonomyAndGeneration:
    """Verifies that Drinks and Foods have cleanly separated taxonomies, naming, and generation."""

    def test_taste_tag_separation(self):
        """Food and drink taste tag sets must not inappropriately overlap."""
        # Solid food tags must not contain drink-only descriptors
        drink_only_descriptors = {"caffeine", "tea", "coffee", "boba", "juice", "soda", "alcohol", "smoothie", "fizzy"}
        for t in FOOD_TASTE_TAGS:
            assert t not in drink_only_descriptors, f"Food taste tag '{t}' should not be in FOOD_TASTE_TAGS"

        # Drink tags must contain beverage profiles
        assert "caffeine" in DRINK_TASTE_TAGS
        assert "boba" in DRINK_TASTE_TAGS
        assert "tea" in DRINK_TASTE_TAGS
        assert "coffee" in DRINK_TASTE_TAGS
        assert "alcohol" in DRINK_TASTE_TAGS

    def test_procedural_drink_generation_attributes(self):
        """Drinks must be generated with item_type 'Drink', valid scaling, and proper tags."""
        drink = generate_procedural_drink(tier=2, genre="high_school_drama")
        assert drink["item_type"] == "Drink"
        assert drink["tier"] == 2
        assert drink["tags"]["consumable_type"] == "drink"
        assert "beverage" in drink["purpose_tags"]
        assert drink["effect"].startswith("[CONSUMABLE_JSON]")
        assert "mp_restore" in drink
        assert "taste_tags" in drink

    def test_food_never_generates_drinks_and_vice_versa(self):
        """Generating multiple foods and drinks must never produce cross-category names or tags."""
        drink_keywords = ["coffee", "latte", "boba", "tea", "cider", "ale", "wine", "soda", "smoothie", "ramune", "fizz", "water"]
        food_keywords = ["bento", "stew", "roast", "steak", "melon pan", "cake", "tart", "sandwich", "skewer", "dumplings", "omakase"]

        import re
        for tier in (1, 2, 3):
            for genre in ("fantasy", "scifi", "high_school_drama"):
                food = generate_procedural_food(tier=tier, genre=genre)
                drink = generate_procedural_drink(tier=tier, genre=genre)

                # Food validation
                assert food["item_type"] == "Food"
                food_name_low = food["name"].lower()
                for dkw in drink_keywords:
                    assert not re.search(r'\b' + re.escape(dkw) + r'\b', food_name_low), f"Food '{food['name']}' contains drink word '{dkw}'"

                # Drink validation
                assert drink["item_type"] == "Drink"
                drink_name_low = drink["name"].lower()
                for fkw in food_keywords:
                    assert not re.search(r'\b' + re.escape(fkw) + r'\b', drink_name_low), f"Drink '{drink['name']}' contains food word '{fkw}'"

    def test_ad_hoc_classification_distinguishes_drink_and_food(self):
        """Ad-hoc item classification enriches drinks as 'Drink' and foods as 'Food'."""
        boba = classify_and_enrich_ad_hoc_item("Iced Brown Sugar Boba Latte", "high_school_drama")
        assert boba["item_type"] == "Drink"

        bento = classify_and_enrich_ad_hoc_item("Deluxe Tonkatsu Bento Box", "high_school_drama")
        assert bento["item_type"] == "Food"

        ale = classify_and_enrich_ad_hoc_item("Aged Dwarven Fire Ale", "fantasy")
        assert ale["item_type"] == "Drink"

        roast = classify_and_enrich_ad_hoc_item("Dragonfire Roast Boar Skewer", "fantasy")
        assert roast["item_type"] == "Food"

    def test_parse_item_effect_for_drink(self):
        """parse_item_effect correctly reads structured Drink metadata."""
        drink = generate_procedural_drink(tier=2, taste_tags=["caffeine", "coffee"], effect_tags=["mana_restore"], genre="fantasy")
        parsed = parse_item_effect(drink)
        assert parsed["tier"] == 2
        assert parsed["mp_restore"] > 0


class TestCharacterPersonaDrinkIntegration:
    """Verifies that NPC personality (Likes / Dislikes) and gift evaluations handle drinks cleanly."""

    def test_grounded_drink_likes_and_dislikes_exist(self):
        """Grounded drink likes and dislikes must be populated with thematic beverages."""
        assert len(GROUNDED_DRINK_LIKES) >= 5
        assert len(GROUNDED_DRINK_DISLIKES) >= 4
        assert any("boba" in d.lower() for d in GROUNDED_DRINK_LIKES)
        assert any("coffee" in d.lower() for d in GROUNDED_DRINK_LIKES)
        assert any("bitter coffee" in d.lower() for d in GROUNDED_DRINK_DISLIKES)

    def test_is_gift_item_recognizes_drinks(self):
        """is_gift_item must identify drinks as tangible gifts, not abstract stances."""
        assert is_gift_item("Likes Iced Brown Sugar Boba Latte") is True
        assert is_gift_item("Likes Chilled Canned Black Coffee") is True
        assert is_gift_item("Likes Aged Dwarven Fire Ale") is True
        assert is_gift_item("Dislikes Bitter Coffee") is True
        assert is_gift_item("Dislikes Strong Alcohol") is True
        # Negative control: abstract stances
        assert is_gift_item("Favors Direct Candor & Honesty") is False
        assert is_gift_item("Intolerant of Slacking & Flakiness") is False

    def test_assign_npc_preferences_includes_drinks(self):
        """assign_npc_preferences deterministically distributes drinks to some NPCs."""
        assigned_drinks = 0
        for i in range(20):
            likes, dislikes = assign_npc_preferences(f"npc_seed_{i}")
            all_prefs = " ".join(likes + dislikes).lower()
            if any(k in all_prefs for k in ["boba", "coffee", "tea", "cider", "ale", "soda", "drink"]):
                assigned_drinks += 1

        assert assigned_drinks > 0, "NPC preferences should assign drinks to some NPCs"

    def test_gift_evaluation_favorite_drink(self):
        """Gifting a favorite drink (e.g. Boba Latte) triggers Loved / Favorite Gift flow."""
        import uuid
        from mechanics.combat.items.consumables import serialize_consumable_metadata
        sess_id = uuid.uuid4().int & 0x7FFFFFFF
        target_name = f"Yuki_{sess_id}"
        drink = generate_procedural_drink(tier=2, taste_tags=["boba", "sweet"], genre="high_school_drama")
        drink["name"] = "Iced Brown Sugar Boba Latte"
        meta = {"tier": 2, "taste_tags": ["boba", "sweet"], "item_type": "Drink"}
        drink["effect"] = serialize_consumable_metadata(meta)

        # Mock target NPC who loves Boba
        mock_session = {
            "id": sess_id,
            "current_npcs": [{
                "name": target_name,
                "traits": ["warm", "playful"],
                "preferences": ["Likes Iced Brown Sugar Boba Latte", "Likes Strawberry Parfait"]
            }]
        }

        ok, msg, delta = evaluate_gift_reaction(
            user_id=9999,
            item=drink,
            target_name=target_name,
            session=mock_session
        )
        assert ok is True
        assert delta == 10  # Tier 2 loved gift base gain
        assert "Favorite Gift!" in msg
        assert target_name in msg
