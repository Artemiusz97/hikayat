"""
Hikayat - Faction & Reputation System Unit Tests
Tests faction tiers, hierarchy templates, procedural roster generation,
promotion trials, sparring duels, quartermaster discounts, and database persistence.
"""
import unittest
import os
import tempfile
import json
import time

import db
from mechanics import factions, merchant, combat, bounty


class TestFactionMechanics(unittest.TestCase):

    def test_reputation_tiers(self):
        self.assertEqual(factions.get_faction_tier(100)["name"], "Exalted")
        self.assertEqual(factions.get_faction_tier(85)["name"], "Exalted")
        self.assertEqual(factions.get_faction_tier(60)["name"], "Honored")
        self.assertEqual(factions.get_faction_tier(30)["name"], "Friendly")
        self.assertEqual(factions.get_faction_tier(10)["name"], "Liked")
        self.assertEqual(factions.get_faction_tier(0)["name"], "Neutral")
        self.assertEqual(factions.get_faction_tier(-20)["name"], "Distrusted")
        self.assertEqual(factions.get_faction_tier(-45)["name"], "Adversary")
        self.assertEqual(factions.get_faction_tier(-75)["name"], "Hostile")
        self.assertEqual(factions.get_faction_tier(-95)["name"], "Hated Enemy")

    def test_tier_discounts_and_modifiers(self):
        self.assertEqual(factions.get_faction_discount(90), 15)
        self.assertEqual(factions.get_faction_discount(60), 10)
        self.assertEqual(factions.get_faction_discount(30), 5)
        self.assertEqual(factions.get_faction_discount(10), 0)
        self.assertEqual(factions.get_faction_modifier(90), 2)
        self.assertEqual(factions.get_faction_modifier(-90), -3)

    def test_hierarchy_templates(self):
        templates = ["council", "discipline", "club", "delinquents", "guild", "order", "corpo", "syndicate", "settlement", "default"]
        for tmpl in templates:
            hier = factions.get_hierarchy(tmpl)
            self.assertEqual(len(hier), 4)
            self.assertEqual(hier[0]["rank"], 1)
            self.assertEqual(hier[3]["rank"], 4)
            self.assertTrue(hier[3]["is_leader"])
        # Check student council titles specifically
        council_hier = factions.get_hierarchy("council")
        self.assertEqual(council_hier[3]["title"], "Student Council President")
        self.assertEqual(council_hier[2]["title"], "Student Council Vice President")
        self.assertEqual(council_hier[1]["title"], "Council Secretary")
        self.assertEqual(council_hier[0]["title"], "Council Representative")

    def test_eligible_rank(self):
        self.assertEqual(factions.get_eligible_rank("guild", 0), 0)
        self.assertEqual(factions.get_eligible_rank("guild", 15), 1)
        self.assertEqual(factions.get_eligible_rank("guild", 45), 2)
        self.assertEqual(factions.get_eligible_rank("guild", 70), 3)
        self.assertEqual(factions.get_eligible_rank("guild", 90), 4)

    def test_guess_hierarchy_template(self):
        self.assertEqual(factions.guess_hierarchy_template("Student Council", "high_school_drama"), "council")
        self.assertEqual(factions.guess_hierarchy_template("Disciplinary Committee", "high_school_drama"), "discipline")
        self.assertEqual(factions.guess_hierarchy_template("Drama Club", "high_school_drama"), "club")
        self.assertEqual(factions.guess_hierarchy_template("Iron Biker Gang", "high_school_drama"), "delinquents")
        self.assertEqual(factions.guess_hierarchy_template("Arasaka Megacorp", "cyberpunk"), "corpo")
        self.assertEqual(factions.guess_hierarchy_template("Night Syndicate", "cyberpunk"), "syndicate")
        self.assertEqual(factions.guess_hierarchy_template("Wasteland Raiders", "post_apocalypse"), "delinquents")
        self.assertEqual(factions.guess_hierarchy_template("Oasis Settlement", "post_apocalypse"), "settlement")
        self.assertEqual(factions.guess_hierarchy_template("Silver Order", "fantasy"), "order")
        self.assertEqual(factions.guess_hierarchy_template("Adventurers Guild", "fantasy"), "guild")

    def test_roster_generation_and_promotion(self):
        roster = factions.generate_procedural_leadership_roster("Arcane Circle", "order", "fantasy")
        self.assertEqual(len(roster), 4)
        self.assertEqual(roster[0]["rank"], 4)
        self.assertEqual(roster[3]["rank"], 1)
        for entry in roster:
            self.assertFalse(entry["is_player"])
            self.assertTrue(bool(entry["name"]))

        # Promote player to Rank 2
        updated = factions.promote_player_in_roster(roster, "Arthur", 2, "order")
        r2 = next(r for r in updated if r["rank"] == 2)
        self.assertTrue(r2["is_player"])
        self.assertEqual(r2["name"], "Arthur")

        # Promote player to Rank 4 (Guildmaster / Grand Master)
        updated4 = factions.promote_player_in_roster(updated, "Arthur", 4, "order")
        r4 = next(r for r in updated4 if r["rank"] == 4)
        self.assertTrue(r4["is_player"])
        self.assertEqual(r4["name"], "Arthur")

        # Remove player from roster on defection
        defected = factions.remove_player_from_roster(updated4, "Arthur", "order", "fantasy")
        r4_new = next(r for r in defected if r["rank"] == 4)
        self.assertFalse(r4_new["is_player"])
        self.assertNotEqual(r4_new["name"], "Arthur")

    def test_promotion_trial_directive(self):
        directive_hs = factions.get_promotion_trial_directive(3, 4, "President Sato", "Student Council", "club", "high_school_drama")
        self.assertIn("FACTION PROMOTION TRIAL DIRECTIVE", directive_hs)
        self.assertIn("President Sato", directive_hs)
        self.assertIn("debate", directive_hs.lower())

        directive_fantasy = factions.get_promotion_trial_directive(3, 4, "Grand Master Vane", "Holy Knights", "order", "fantasy")
        self.assertIn("sparring duel", directive_fantasy.lower())

    def test_social_modifiers_and_perks(self):
        # Same faction
        mod_same = factions.get_player_faction_social_modifier("knights", "knights", 50)
        self.assertEqual(mod_same, 2)
        # Rival faction
        mod_rival = factions.get_player_faction_social_modifier("knights", "dark_cult", -70, is_rival=True)
        self.assertEqual(mod_rival, -3)
        # Different non-rival faction
        mod_other = factions.get_player_faction_social_modifier("knights", "merchants", 10)
        self.assertEqual(mod_other, 0)

        # Perks
        perks_unranked = factions.get_active_perks({"name": "Knights"}, 0, 90)
        self.assertEqual(len(perks_unranked), 0)

        perks_ranked = factions.get_active_perks({"name": "Knights"}, 4, 85)
        self.assertTrue(any("Quartermaster" in p for p in perks_ranked))
        self.assertTrue(any("Safehouse Rest" in p for p in perks_ranked))
        self.assertTrue(any("Social Advantage" in p for p in perks_ranked))
        self.assertTrue(any("Call Reinforcements" in p for p in perks_ranked))

    def test_combat_sparring_and_patrol(self):
        spar_mon = combat.make_sparring_monster("Guildmaster Roland", 5, "fantasy")
        self.assertTrue(combat.is_sparring_monster(spar_mon))
        self.assertEqual(spar_mon["xp_multiplier"], 0.0)
        self.assertEqual(spar_mon["gold_drop"], 0)

        patrol = factions.generate_faction_patrol({"name": "City Watch", "category": "guild"}, 3, "fantasy")
        self.assertIsInstance(patrol, list)
        self.assertGreaterEqual(len(patrol), 1)
        self.assertTrue(patrol[0].get("faction_patrol"))

    def test_merchant_discounts(self):
        self.assertEqual(merchant.discounted_price(100, 15), 85)
        self.assertEqual(merchant.get_total_buy_discount(10, 15), 25)
        self.assertEqual(merchant.get_total_buy_discount(30, 20), 40)  # Capped at 40%

    def test_bounty_rep_parsing(self):
        quest = {"quest_notes": "faction:silver_knights|rep_reward:15"}
        rep = bounty.get_faction_rep_reward_from_quest(quest)
        self.assertEqual(rep, 15)

        quest_empty = {"quest_notes": ""}
        self.assertEqual(bounty.get_faction_rep_reward_from_quest(quest_empty), 0)


class TestFactionDatabase(unittest.TestCase):

    def setUp(self):
        # Create a test session
        with db.get_conn() as conn:
            cur = conn.execute(
                "INSERT INTO sessions (mode, capacity, status, scenario, current_location) "
                "VALUES ('solo', 1, 'active', 'fantasy', 'Silverwood Citadel')"
            )
            self.session_id = cur.lastrowid
            cur_char = conn.execute(
                "INSERT INTO characters (user_id, name, char_class, gender, race, hp, max_hp, mp, max_mp, created_at) "
                "VALUES (99901, 'TestHero', 'Warrior', 'male', 'human', 100, 100, 50, 50, ?)",
                (time.time(),)
            )
            self.char_id = cur_char.lastrowid

    def test_faction_embeds(self):
        from cogs.factions import build_faction_list_embed, build_faction_detail_embed
        db.upsert_faction(
            self.session_id, "Silver Knights", delta_score=85,
            hq_location_id="Citadel", notes="Righteous holy order."
        )
        factions_list = db.get_factions(self.session_id)
        char = db.get_character_by_id(self.char_id)

        # 1. Overview List Embed
        list_embed = build_faction_list_embed(factions_list, char, "fantasy")
        self.assertTrue(list_embed.title)
        self.assertIn("Silver Knights", str(list_embed.fields[0].name))
        self.assertIn("Exalted", str(list_embed.fields[0].value))

        # 2. Detail Embed
        detail_embed = build_faction_detail_embed(factions_list[0], char)
        self.assertIn("Silver Knights", detail_embed.title)
        self.assertIn("Exalted", str(detail_embed.fields[0].value))


if __name__ == "__main__":
    unittest.main()
