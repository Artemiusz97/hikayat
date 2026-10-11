from __future__ import annotations
import pytest

from game_engine.matching import (
    MatchResult,
    find_keyword_match,
    matches_keyword,
    matches_keyword_boundary,
    normalize_text,
    detect_negation,
)
from game_engine.keywords import (
    PLAYER_ROMANTIC_ACTION_KEYWORDS,
    PLAYER_INTIMATE_ACTION_KEYWORDS,
)
from character_data import get_item_icon


class TestWordBoundaryAndScunthorpe:
    """Verifies strict token-boundary matching and elimination of Scunthorpe collisions."""

    def test_classic_scunthorpe_examples(self):
        assert not matches_keyword("Review the official document", ["cum"])
        assert not matches_keyword("Disarm the dangerous thug", ["hug"])
        assert not matches_keyword("Order a refreshing cocktail", ["cock"])
        assert not matches_keyword("Read the assignment instructions", ["ass"])
        assert not matches_keyword("A classic literature book", ["ass"])

    def test_item_scunthorpe_prevention(self):
        # Bow vs Soup Bowl / Elbow
        assert not matches_keyword("Ceramic Soup Bowl", ["bow"])
        assert not matches_keyword("Elbow Grease", ["bow"])
        assert matches_keyword("Elven Long Bow", ["bow"])
        assert matches_keyword("Hunting Crossbow", ["crossbow", "bow"])

        # Axe vs Taxes / Waxed
        assert not matches_keyword("Income Taxes Document", ["axe"])
        assert not matches_keyword("Waxed Cotton Jacket", ["axe"])
        assert matches_keyword("Heavy Battle Axe", ["axe"])

        # Ring vs String / Spring
        assert not matches_keyword("Ball of String", ["ring"])
        assert not matches_keyword("Spring Water Bottle", ["ring"])
        assert matches_keyword("Diamond Ring", ["ring"])

        # Phone vs Saxophone
        assert not matches_keyword("Vintage Saxophone", ["phone", "smartphone", "cellphone"])
        assert matches_keyword("Encrypted Smartphone", ["phone", "smartphone", "cellphone"])

        # Mail vs Blackmail / Email
        assert not matches_keyword("Blackmail Note", ["mail"])
        assert not matches_keyword("Email Notification", ["mail"])
        assert matches_keyword("Chain Mail Coif", ["mail"])

        # Tea vs Steam
        assert not matches_keyword("Pressurized Steam Valve", ["tea"])
        assert matches_keyword("Herbal Jasmine Tea", ["tea"])

        # Ale vs Scale
        assert not matches_keyword("Fish Scale Carapace", ["ale"])
        assert matches_keyword("Dwarven Dark Ale", ["ale"])

        # Key vs Monkey
        assert not matches_keyword("Curious Monkey Figurine", ["key"])
        assert matches_keyword("Rusty Skeleton Key", ["key"])

        # Card vs Placard
        assert not matches_keyword("Protest Placard", ["card"])
        assert matches_keyword("Access Card", ["card"])
        assert matches_keyword("Access Keycard", ["keycard", "card"])

    def test_casing_and_unicode_normalization(self):
        assert matches_keyword("KISS Alice", ["kiss"])
        assert matches_keyword("hug Bob", ["HUG"])
        assert matches_keyword("Café Latte", ["latte"])


class TestNegationDetection:
    """Verifies clause-aware refusal and negation markers."""

    def test_simple_negation_words(self):
        res = find_keyword_match("I do not want to kiss her", ["kiss"])
        assert res.matched
        assert res.is_negated
        assert not matches_keyword("I do not want to kiss her", ["kiss"], allow_negated=False)
        assert matches_keyword("I do not want to kiss her", ["kiss"], allow_negated=True)

    def test_refusal_verbs(self):
        assert not matches_keyword("I refuse to kiss her", ["kiss"], allow_negated=False)
        assert not matches_keyword("She refused to sleep together", ["sleep together"], allow_negated=False)
        assert not matches_keyword("We must stop touching", ["touching"], allow_negated=False)
        assert not matches_keyword("I will never touch you", ["touch"], allow_negated=False)
        assert not matches_keyword("I cannot make love tonight", ["make love"], allow_negated=False)
        assert not matches_keyword("Don't kiss me", ["kiss"], allow_negated=False)

    def test_contrast_clause_reset(self):
        # A contrast conjunction (but) resets the negation scope
        text = "I do not hate her, but I want to kiss her"
        res = find_keyword_match(text, ["kiss"])
        assert res.matched
        assert not res.is_negated
        assert matches_keyword(text, ["kiss"], allow_negated=False)

    def test_sentence_boundary_reset(self):
        # Sentence punctuation resets negation scope
        text = "I don't like fighting. Let us kiss and make up."
        res = find_keyword_match(text, ["kiss"])
        assert res.matched
        assert not res.is_negated
        assert matches_keyword(text, ["kiss"], allow_negated=False)


class TestMultiWordPhrases:
    """Verifies phrase handling and flexible whitespace matching."""

    def test_collapsed_whitespace_phrases(self):
        assert matches_keyword("make   love under the stars", ["make love"])
        assert matches_keyword("make\nlove under the stars", ["make love"])
        assert matches_keyword("have   sex in private", ["have sex"])

    def test_prefix_sorting_preference(self):
        # Longer phrases should match before shorter tokens
        res = find_keyword_match("I have a modern smartphone in hand", ["phone", "smartphone"])
        assert res.matched
        assert res.matched_term == "smartphone"


class TestItemIconScunthorpeFixes:
    """Verifies that character_data.get_item_icon no longer falls into Scunthorpe traps."""

    def test_bowl_does_not_become_bow_weapon(self):
        icon = get_item_icon("Ceramic Soup Bowl")
        assert icon != "🏹"  # Should NOT be bow emoji!

    def test_taxes_does_not_become_axe(self):
        icon = get_item_icon("Unpaid Taxes Ledger")
        assert icon != "🪓"  # Should NOT be axe emoji!

    def test_string_does_not_become_ring(self):
        icon = get_item_icon("Twisted Ball of String")
        assert icon != "💍"  # Should NOT be ring emoji!

    def test_saxophone_does_not_become_smartphone(self):
        icon = get_item_icon("Brass Alto Saxophone")
        assert icon != "📱"  # Should NOT be phone emoji!

    def test_blackmail_does_not_become_shirt_armor(self):
        icon = get_item_icon("Incriminating Blackmail Letter")
        assert icon != "👕"  # Should NOT be shirt/mail emoji!
        assert icon == "📜"  # Quest/Letter item

    def test_legitimate_items_retain_correct_icons(self):
        assert get_item_icon("Recurve Bow") == "🏹"
        assert get_item_icon("Battle Axe") == "🪓"
        assert get_item_icon("Silver Ring") == "💍"
        assert get_item_icon("Tactical Smartphone") == "📱"
        assert get_item_icon("Chainmail Armor") == "👕"
        assert get_item_icon("Health Salve") == "❤️"
        assert get_item_icon("Green Tea") == "🍵"


class TestBackwardCompatibility:
    """Verifies backward compatibility with game_engine.keywords and callers."""

    def test_matches_keyword_boundary_backward_compatible(self):
        assert matches_keyword_boundary("Give Alice a warm hug", ["hug"])
        assert matches_keyword_boundary("Share a passionate kiss with Alice", ["kiss"])
        assert not matches_keyword_boundary("Disarm the dangerous thug", ["hug"])

    def test_social_refusal_guard(self):
        # When allow_negated=False, refusals are suppressed
        assert not matches_keyword_boundary("Refuse to kiss Maya", PLAYER_ROMANTIC_ACTION_KEYWORDS, allow_negated=False)
        assert not matches_keyword_boundary("Do not make love with him", PLAYER_INTIMATE_ACTION_KEYWORDS, allow_negated=False)
        # Legitimate romantic/intimate actions pass
        assert matches_keyword_boundary("Gently kiss Maya", PLAYER_ROMANTIC_ACTION_KEYWORDS, allow_negated=False)
        assert matches_keyword_boundary("Make love with Maya", PLAYER_INTIMATE_ACTION_KEYWORDS, allow_negated=False)
