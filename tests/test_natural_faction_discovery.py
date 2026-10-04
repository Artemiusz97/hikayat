"""
Unit tests for Natural Faction Discovery & Dedicated Tier 2 HQ Location Provisioning.
"""
import unittest
import db
from mechanics.world.locations import provision_faction_hq_tier2_location
from mechanics.social.factions import infer_default_hq_location, get_hierarchy
from cogs.factions import get_faction_emoji


class TestNaturalFactionDiscovery(unittest.TestCase):

    def setUp(self):
        self.session_id = 88888
        db.init_db()

    def test_default_hq_naming(self):
        """Verify thematic Tier 2 HQ names are inferred for various clubs/factions."""
        self.assertEqual(infer_default_hq_location("Esports & Gaming Club", "high_school_drama"), "Esports Clubroom & Media Lab")
        self.assertEqual(infer_default_hq_location("Science & Robotics Club", "high_school_drama"), "Science & Robotics Lab 2-A")
        self.assertEqual(infer_default_hq_location("Traditional Martial Arts Club", "high_school_drama"), "Traditional Martial Arts Dojo")
        self.assertEqual(infer_default_hq_location("Art & Manga Society", "high_school_drama"), "Art & Design Studio")
        self.assertEqual(infer_default_hq_location("School Newspaper & Journalism", "high_school_drama"), "Newspaper & Media Room")
        self.assertEqual(infer_default_hq_location("Music & Band Club", "high_school_drama"), "Music Wing Rehearsal Hall")
        self.assertEqual(infer_default_hq_location("Ashen Rook Delinquent Gang", "high_school_drama"), "Behind Gym Storage Sheds")

    def test_tier2_hq_provisioning_and_sub_areas(self):
        """Verify dedicated Tier 2 Primary HQ and rich Tier 3 Sub-Areas are created in SQLite."""
        hq_name = provision_faction_hq_tier2_location(self.session_id, "Esports & Gaming Club", "high_school_drama")
        self.assertEqual(hq_name, "Esports Clubroom & Media Lab")

        locs = db.get_session_locations(self.session_id)
        esports_locs = [l for l in locs if l["primary_name"] == "Esports Clubroom & Media Lab"]
        self.assertEqual(len(esports_locs), 3)

        sub_names = {l["sub_name"] for l in esports_locs}
        self.assertIn("PC Battle Stations", sub_names)
        self.assertIn("Strategy Meeting Area", sub_names)
        self.assertIn("Console Lounge & Trophy Shelf", sub_names)

    def test_faction_dynamic_emojis(self):
        """Verify dynamic emojis match the faction category/club theme."""
        self.assertEqual(get_faction_emoji("Esports & Gaming Club"), "🎮")
        self.assertEqual(get_faction_emoji("Journalism & Media"), "📰")
        self.assertEqual(get_faction_emoji("Culinary & Baking Club"), "🍳")
        self.assertEqual(get_faction_emoji("Astronomy Society"), "🔭")
        self.assertEqual(get_faction_emoji("Drama Club"), "🎭")
        self.assertEqual(get_faction_emoji("Occult & Mystery Club"), "🔮")
        self.assertEqual(get_faction_emoji("Science & Robotics Club"), "🧪")
        self.assertEqual(get_faction_emoji("Kendo & Martial Arts Club"), "🥋")
        self.assertEqual(get_faction_emoji("Ashen Rook Rebels"), "🐺")
        self.assertEqual(get_faction_emoji("Alchemists' Guild"), "⚗️")
        self.assertEqual(get_faction_emoji("Grand Alchemists Union"), "⚗️")
        self.assertEqual(get_faction_emoji("Unknown", template="alchemy"), "⚗️")
        self.assertEqual(get_faction_emoji("Unknown", template="academy"), "📜")

    def test_alchemy_and_academy_hierarchy_routing(self):
        """Verify guess_hierarchy_template routes alchemical and academic organizations correctly."""
        from mechanics.social.factions import guess_hierarchy_template, generate_procedural_leadership_roster

        # Alchemy routing across scenarios
        self.assertEqual(guess_hierarchy_template("Alchemists' Guild", "steampunk"), "alchemy")
        self.assertEqual(guess_hierarchy_template("Grand Alchemists Union", "fantasy"), "alchemy")
        self.assertEqual(guess_hierarchy_template("Plague Alchemists Guild", "dark_fantasy"), "alchemy")
        self.assertEqual(guess_hierarchy_template("Mechanists & Alchemists Fellowship", "steampunk"), "alchemy")
        self.assertEqual(guess_hierarchy_template("Apothecary Guild", "fantasy"), "alchemy")

        # Academy routing
        self.assertEqual(guess_hierarchy_template("Grand Aetheric Research Society", "steampunk"), "academy")
        self.assertEqual(guess_hierarchy_template("Arcane Academy of Sorcery", "fantasy"), "academy")
        self.assertEqual(guess_hierarchy_template("Imperial Institute of Technology", "steampunk"), "academy")

        # Verify leadership roster ranks for alchemy
        alch_roster = generate_procedural_leadership_roster("Alchemists' Guild", "alchemy", "steampunk")
        titles = {r["rank"]: r["title"] for r in alch_roster}
        self.assertEqual(titles[4], "Grand Alchemical Magister")
        self.assertEqual(titles[3], "Master Alchemist")
        self.assertEqual(titles[2], "Journeyman Brewer")
        self.assertEqual(titles[1], "Apprentice Alchemist")

        # Verify leadership roster ranks for academy
        acad_roster = generate_procedural_leadership_roster("Royal Academy", "academy", "steampunk")
        acad_titles = {r["rank"]: r["title"] for r in acad_roster}
        self.assertEqual(acad_titles[4], "Grand Rector")
        self.assertEqual(acad_titles[3], "Senior Fellow")
        self.assertEqual(acad_titles[2], "Journeyman Researcher")
        self.assertEqual(acad_titles[1], "Apprentice Scholar")

    def test_seed_location_hq_matching(self):
        """Verify infer_default_hq_location matches existing primary locations in seed data."""
        # In steampunk, "Alchemists' Guild Hall" is pre-seeded in data/locations_seed.json
        hq = infer_default_hq_location("Alchemists' Guild", "steampunk")
        self.assertEqual(hq, "Alchemists' Guild Hall")

        # Unseeded alchemy in fantasy falls back to Alchemical Sanctuary
        hq_fantasy = infer_default_hq_location("Order of the Golden Crucible", "fantasy")
        self.assertIn("Alchemical Sanctuary", hq_fantasy)

    def test_alchemy_hq_provisioning_sub_areas(self):
        """Verify dedicated alchemical sub-locations are generated when provisioning HQ."""
        hq_name = provision_faction_hq_tier2_location(self.session_id, "Alchemists' Guild", "steampunk", "Alchemists' Guild Hall")
        self.assertEqual(hq_name, "Alchemists' Guild Hall")

        locs = db.get_session_locations(self.session_id)
        alch_locs = [l for l in locs if l["primary_name"] == "Alchemists' Guild Hall"]
        self.assertGreaterEqual(len(alch_locs), 3)

        sub_names = {l["sub_name"] for l in alch_locs}
        self.assertIn("Brewing & Distillation Station", sub_names)
        self.assertIn("Reagent Vault & Ingredient Shelves", sub_names)
        self.assertIn("Classified Alchemical Archive", sub_names)

    def test_alchemy_promotion_trial_directive(self):
        """Verify promotion trials for alchemy produce scholarly/distillation directives rather than sword sparring."""
        from mechanics.social.factions import get_promotion_trial_directive

        # Rank 4 trial (Leader)
        top_trial = get_promotion_trial_directive(
            current_rank=3, target_rank=4, incumbent_name="Master Vane",
            faction_name="Alchemists' Guild", template="alchemy", scen_key="steampunk"
        )
        self.assertIn("Symposium Defense", top_trial)
        self.assertIn("magnum opus", top_trial)
        self.assertNotIn("sparring", top_trial)

        # Rank 2 trial (Mid-rank)
        mid_trial = get_promotion_trial_directive(
            current_rank=1, target_rank=2, incumbent_name="Brewer Silas",
            faction_name="Alchemists' Guild", template="alchemy", scen_key="fantasy"
        )
        self.assertIn("elixir", mid_trial)
        self.assertIn("reagent", mid_trial)
        self.assertNotIn("sparring", mid_trial)

    def test_cross_scenario_archetype_routing_and_rosters(self):
        """Verify routing and procedural leadership rosters for the 6 new cross-scenario archetypes."""
        from mechanics.social.factions import guess_hierarchy_template, generate_procedural_leadership_roster

        # 1. union (Steampunk & industrial)
        self.assertEqual(guess_hierarchy_template("Iron Foundry Machinists Union", "steampunk"), "union")
        self.assertEqual(guess_hierarchy_template("Locomotive Boilermakers Union", "steampunk"), "union")
        self.assertEqual(guess_hierarchy_template("Smelters Trade Union", "fantasy"), "union")
        union_roster = generate_procedural_leadership_roster("Machinists Union", "union", "steampunk")
        u_titles = {r["rank"]: r["title"] for r in union_roster}
        self.assertEqual(u_titles[1], "Apprentice Machinist")
        self.assertEqual(u_titles[2], "Shop Steward")
        self.assertEqual(u_titles[3], "Chief Engineer")
        self.assertEqual(u_titles[4], "Union President")

        # 2. fleet (Dirigible / space / navy)
        self.assertEqual(guess_hierarchy_template("Imperial Airship Fleet", "steampunk"), "fleet")
        self.assertEqual(guess_hierarchy_template("7th Orbital Starship Fleet", "space"), "fleet")
        self.assertEqual(guess_hierarchy_template("Aeronaut Flotilla", "steampunk"), "fleet")
        fleet_roster = generate_procedural_leadership_roster("Imperial Fleet", "fleet", "steampunk")
        f_titles = {r["rank"]: r["title"] for r in fleet_roster}
        self.assertEqual(f_titles[1], "Flight Ensign")
        self.assertEqual(f_titles[2], "Lieutenant Commander")
        self.assertEqual(f_titles[3], "Airship Captain")
        self.assertEqual(f_titles[4], "Lord Admiral")

        # 3. merchant (Banking / trade / caravan)
        self.assertEqual(guess_hierarchy_template("Golden Caravan Traders", "fantasy"), "merchant")
        self.assertEqual(guess_hierarchy_template("Grand Trade League", "steampunk"), "merchant")
        self.assertEqual(guess_hierarchy_template("Highland Banking House", "fantasy"), "merchant")
        merch_roster = generate_procedural_leadership_roster("Trade League", "merchant", "fantasy")
        m_titles = {r["rank"]: r["title"] for r in merch_roster}
        self.assertEqual(m_titles[1], "Caravan Agent")
        self.assertEqual(m_titles[2], "Trade Factor")
        self.assertEqual(m_titles[3], "High Burgher")
        self.assertEqual(m_titles[4], "Merchant Prince")

        # 4. inquisition (Witch hunters / purifiers)
        self.assertEqual(guess_hierarchy_template("Holy Office of the Inquisition", "dark_fantasy"), "inquisition")
        self.assertEqual(guess_hierarchy_template("Order of Witch Hunters", "dark_fantasy"), "inquisition")
        self.assertEqual(guess_hierarchy_template("Purifiers of the Sacred Flame", "fantasy"), "inquisition")
        inq_roster = generate_procedural_leadership_roster("Holy Inquisition", "inquisition", "dark_fantasy")
        i_titles = {r["rank"]: r["title"] for r in inq_roster}
        self.assertEqual(i_titles[1], "Initiate Inquisitor")
        self.assertEqual(i_titles[2], "Witch Hunter")
        self.assertEqual(i_titles[3], "High Inquisitor")
        self.assertEqual(i_titles[4], "Grand Inquisitor")

        # 5. cult (Eldritch covens / blood pacts)
        self.assertEqual(guess_hierarchy_template("Cult of the Void", "dark_fantasy"), "cult")
        self.assertEqual(guess_hierarchy_template("Coven of Whispers", "dark_fantasy"), "cult")
        self.assertEqual(guess_hierarchy_template("Circle of Blood Pacts", "fantasy"), "cult")
        self.assertEqual(guess_hierarchy_template("Necromancers Circle", "fantasy"), "cult")
        cult_roster = generate_procedural_leadership_roster("Cult of the Void", "cult", "dark_fantasy")
        c_titles = {r["rank"]: r["title"] for r in cult_roster}
        self.assertEqual(c_titles[1], "Acolyte")
        self.assertEqual(c_titles[2], "Adept")
        self.assertEqual(c_titles[3], "Hierophant")
        self.assertEqual(c_titles[4], "Cult Archon")

        # 6. scavenger (Wasteland salvage & scrapping)
        self.assertEqual(guess_hierarchy_template("Wasteland Salvage Crew", "post_apocalypse"), "scavenger")
        self.assertEqual(guess_hierarchy_template("Junkers & Scrappers Guild", "post_apocalypse"), "scavenger")
        self.assertEqual(guess_hierarchy_template("Scrap Prospectors", "post_apocalypse"), "scavenger")
        scav_roster = generate_procedural_leadership_roster("Scrap Crew", "scavenger", "post_apocalypse")
        s_titles = {r["rank"]: r["title"] for r in scav_roster}
        self.assertEqual(s_titles[1], "Scrap Runner")
        self.assertEqual(s_titles[2], "Salvage Specialist")
        self.assertEqual(s_titles[3], "Wreckmaster")
        self.assertEqual(s_titles[4], "Scrap Baron")

    def test_cross_scenario_archetype_hq_and_sub_locations(self):
        """Verify thematic Tier 2 HQ naming and Tier 3 sub-area generation for all 6 archetypes."""
        archetype_cases = [
            ("Machinists Union", "steampunk", "Machinists Union Foundry & Labor Hall",
             {"Piston Foundry & Forge Floor", "Union Steward's Office", "Boiler Pressure Testing Array"}),
            ("Royal Airship Fleet", "steampunk", "Royal Airship Fleet Aerodrome Gantry",
             {"Bridge & Navigation Helm", "Flight Deck & Launch Catapult", "Officer's Mess & Briefing Room"}),
            ("Orbital Fleet", "space", "Orbital Fleet Command Bridge",
             {"Bridge & Navigation Helm", "Flight Deck & Launch Catapult", "Officer's Mess & Briefing Room"}),
            ("Golden Caravan", "fantasy", "Golden Caravan Grand Exchange & Trading Post",
             {"Bourse & Ledger Counting Room", "Vault & Secured Lockboxes", "Caravan Staging Yard"}),
            ("Holy Inquisition", "dark_fantasy", "Holy Inquisition Iron Sanctum & Citadel",
             {"Sanctified Interrogation Chamber", "Relic & Purging Armory", "Lord Inquisitor's Private Quarters"}),
            ("Obsidian Coven", "dark_fantasy", "Obsidian Coven Hidden Catacomb & Altar",
             {"Sacrificial Obsidian Altar", "Forbidden Reliquary & Tome Shelves", "Chanting Catacomb Vault"}),
            ("Wasteland Salvage Crew", "post_apocalypse", "Wasteland Salvage Crew Scrapyard Depot & Workshop",
             {"Salvage Sifting Bay", "Scrap Smelting Crucible", "Prospector's Trade Outpost"}),
        ]

        for faction_name, scen_key, expected_hq, expected_subs in archetype_cases:
            inferred_hq = infer_default_hq_location(faction_name, scen_key)
            self.assertEqual(inferred_hq, expected_hq)

            hq_name = provision_faction_hq_tier2_location(self.session_id, faction_name, scen_key, inferred_hq)
            self.assertEqual(hq_name, expected_hq)

            locs = db.get_session_locations(self.session_id)
            matching_subs = {l["sub_name"] for l in locs if l["primary_name"] == expected_hq}
            for expected_sub in expected_subs:
                self.assertIn(expected_sub, matching_subs)

    def test_cross_scenario_archetype_promotion_trials(self):
        """Verify non-combat, archetype-appropriate promotion trial directives."""
        from mechanics.social.factions import get_promotion_trial_directive

        # 1. union
        u_top = get_promotion_trial_directive(3, 4, "President Thorne", "Machinists Union", "union", "steampunk")
        self.assertIn("Master Machining & Pressure Overhaul", u_top)
        self.assertIn("[STR 8]", u_top)
        self.assertNotIn("sparring", u_top)

        u_mid = get_promotion_trial_directive(1, 2, "Steward Gary", "Machinists Union", "union", "steampunk")
        self.assertIn("precision lathe machining", u_mid)

        # 2. fleet
        f_top = get_promotion_trial_directive(3, 4, "Admiral Vance", "Royal Fleet", "fleet", "steampunk")
        self.assertIn("Flagship Tactical Simulation Drill", f_top)
        self.assertIn("[INT 9]", f_top)
        self.assertNotIn("sparring", f_top)

        f_mid = get_promotion_trial_directive(1, 2, "Commander Drake", "Royal Fleet", "fleet", "space")
        self.assertIn("high-speed evasive piloting", f_mid)

        # 3. merchant
        m_top = get_promotion_trial_directive(3, 4, "Prince Goldwin", "Trade Consortium", "merchant", "fantasy")
        self.assertIn("High-Stakes Bourse Auction", m_top)
        self.assertIn("[CHA 9]", m_top)
        self.assertNotIn("sparring", m_top)

        m_mid = get_promotion_trial_directive(1, 2, "Factor Silas", "Trade Consortium", "merchant", "fantasy")
        self.assertIn("commercial persuasion", m_mid)

        # 4. inquisition
        i_top = get_promotion_trial_directive(3, 4, "Grand Inquisitor Marrok", "Holy Office", "inquisition", "dark_fantasy")
        self.assertIn("High Inquisitorial Tribunal & Trial of Purity", i_top)
        self.assertIn("[INT 9]", i_top)
        self.assertNotIn("sparring", i_top)

        i_mid = get_promotion_trial_directive(1, 2, "Hunter Sean", "Holy Office", "inquisition", "dark_fantasy")
        self.assertIn("tracking occult residue", i_mid)

        # 5. cult
        c_top = get_promotion_trial_directive(3, 4, "Archon Moros", "Cult of the Void", "cult", "dark_fantasy")
        self.assertIn("Forbidden Rite of Ascension", c_top)
        self.assertIn("[INT 9]", c_top)
        self.assertNotIn("sparring", c_top)

        c_mid = get_promotion_trial_directive(1, 2, "Hierophant Nyx", "Cult of the Void", "cult", "dark_fantasy")
        self.assertIn("occult cipher translation", c_mid)

        # 6. scavenger
        s_top = get_promotion_trial_directive(3, 4, "Baron Rusty", "Scrap Syndicate", "scavenger", "post_apocalypse")
        self.assertIn("High-Danger Salvage Run", s_top)
        self.assertIn("[PER 9]", s_top)
        self.assertNotIn("sparring", s_top)

        s_mid = get_promotion_trial_directive(1, 2, "Wreckmaster Jax", "Scrap Syndicate", "scavenger", "post_apocalypse")
        self.assertIn("scrap jury-rigging", s_mid)

    def test_cross_scenario_archetype_emojis(self):
        """Verify emojis for all 6 archetypes via keyword detection and template fallbacks."""
        # Keyword matching
        self.assertEqual(get_faction_emoji("Machinists Union"), "⚒️")
        self.assertEqual(get_faction_emoji("Royal Airship Fleet"), "🚢")
        self.assertEqual(get_faction_emoji("Orbital Fleet"), "🚀")
        self.assertEqual(get_faction_emoji("Highland Banking House"), "🪙")
        self.assertEqual(get_faction_emoji("Grand Trade League"), "🪙")
        self.assertEqual(get_faction_emoji("Holy Inquisition"), "🔥")
        self.assertEqual(get_faction_emoji("Witch Hunters Order"), "🔥")
        self.assertEqual(get_faction_emoji("Cult of the Black Sun"), "👁️")
        self.assertEqual(get_faction_emoji("Coven of Whispers"), "👁️")
        self.assertEqual(get_faction_emoji("Wasteland Scavengers"), "🔧")
        self.assertEqual(get_faction_emoji("Junkers Scrap Crew"), "🔧")

        # Template fallback matching
        self.assertEqual(get_faction_emoji("Unknown", template="union"), "⚒️")
        self.assertEqual(get_faction_emoji("Unknown", template="fleet"), "🚢")
        self.assertEqual(get_faction_emoji("Unknown", template="merchant"), "🪙")
        self.assertEqual(get_faction_emoji("Unknown", template="inquisition"), "🔥")
        self.assertEqual(get_faction_emoji("Unknown", template="cult"), "👁️")
        self.assertEqual(get_faction_emoji("Unknown", template="scavenger"), "🔧")


if __name__ == "__main__":
    unittest.main()
