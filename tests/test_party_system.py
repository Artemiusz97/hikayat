import unittest
import db
import game_engine
import mechanics.combat as combat
from mechanics.world.locations import resolve_companion_origin_location
from cogs.adventure import _party_vitals_text


class TestPartySystem(unittest.TestCase):
    def setUp(self):
        db.init_db()
        with db.get_conn() as conn:
            conn.execute("DELETE FROM characters WHERE user_id IN (99880, 99881, 99882, 99883, 99884)")
            conn.execute("DELETE FROM sessions WHERE turn_order LIKE '%99880%' OR turn_order LIKE '%99881%' OR turn_order LIKE '%99882%' OR turn_order LIKE '%99883%'")

    def test_party_vitals_rendering(self):
        """Verify _party_vitals_text includes human player and recruited companions in combat scenarios."""
        uid = 99880
        char = db.create_character(uid, "Alice", "Mage", "fantasy")
        sess_id = db.create_session(uid, "solo", 1, "vivid", "individual", False, scenario="fantasy")
        
        # Add companion
        comp = {
            "name": "Mara Vey",
            "role": "Scout",
            "level": 14,
            "hp": 52,
            "max_hp": 52,
            "mp": 20,
            "max_mp": 20,
            "status_effects": [],
            "origin_location": "Solaria ➔ The Boar's Tusk Tavern ➔ Hearthside Table"
        }
        db.add_session_party_npc(sess_id, comp)
        sess = db.get_session(sess_id)

        vitals_text = _party_vitals_text(sess)
        self.assertIn("Alice", vitals_text)
        self.assertIn("Mara Vey", vitals_text)
        self.assertIn("(Scout)", vitals_text)
        self.assertIn("52/52", vitals_text)

    def test_origin_location_tracking_and_settlement_resolution(self):
        """Hub location preserves exact hub, while wilderness resolves to zone settlement."""
        uid = 99881
        char = db.create_character(uid, "Bob", "Warrior", "fantasy")
        sess_id = db.create_session(uid, "solo", 1, "vivid", "individual", False, scenario="fantasy")

        # 1. Hub location
        hub_loc = "Solaria ➔ The Boar's Tusk Tavern ➔ Hearthside Table"
        res_hub = resolve_companion_origin_location(sess_id, hub_loc, "fantasy")
        self.assertEqual(res_hub, hub_loc)

        # 2. Add local settlement to lorebook
        db.upsert_lorebook_entity(sess_id, "place", "Whispering Woods ➔ Forest Haven Village ➔ Lodge", "Local village lodge", "friendly")

        # Wilderness location in same zone
        wild_loc = "Whispering Woods ➔ Monster Den ➔ Deep Cavern"
        res_wild = resolve_companion_origin_location(sess_id, wild_loc, "fantasy")
        self.assertIn("Forest Haven Village", res_wild)

    def test_party_recruitment_success_and_cap(self):
        """Successful recruitment adds companion, respects 4-member cap, and blocks excess."""
        uid = 99882
        char = db.create_character(uid, "Charlie", "Rogue", "fantasy")
        sess_id = db.create_session(uid, "solo", 1, "vivid", "individual", False, scenario="fantasy")
        party = [(char, db.get_inventory(uid))]

        # Pre-seed friendly NPC in scene
        db.update_session_npcs(sess_id, [{"name": "Mara Vey", "disposition": "friendly"}])
        db.upsert_lorebook_entity(sess_id, "person", "Mara Vey", "Expert caravan scout", "friendly")

        # Recruitment action with successful check
        outcome = {
            "scene_title": "Recruiting Mara",
            "narrative": "Mara agrees to join your journey.",
            "location": "Solaria ➔ The Boar's Tusk Tavern ➔ Table",
            "next_choices": []
        }
        actions = [{
            "label": "🤝 [CHA] Invite Mara Vey to join your party as a permanent companion",
            "check": {"is_success": True, "tier": "SUCCESS"},
            "user_id": uid
        }]

        game_engine.apply_outcome(sess_id, party, outcome, actions=actions)

        # Verify recruited
        party_npcs = db.get_session_party_npcs(sess_id)
        self.assertEqual(len(party_npcs), 1)
        self.assertEqual(party_npcs[0]["name"], "Mara Vey")
        self.assertEqual(party_npcs[0]["role"], "Scout")

        # Add 2 more to reach max cap of 4 (1 human + 3 companions)
        db.add_session_party_npc(sess_id, {"name": "Companion 2", "level": 1, "hp": 20, "max_hp": 20, "mp": 10, "max_mp": 10})
        db.add_session_party_npc(sess_id, {"name": "Companion 3", "level": 1, "hp": 20, "max_hp": 20, "mp": 10, "max_mp": 10})
        self.assertEqual(len(db.get_session_party_npcs(sess_id)), 3)

        # Attempt to add 4th companion (Total would be 5) -> must be rejected
        added = db.add_session_party_npc(sess_id, {"name": "Companion 4", "level": 1, "hp": 20, "max_hp": 20, "mp": 10, "max_mp": 10})
        self.assertFalse(added)
        self.assertEqual(len(db.get_session_party_npcs(sess_id)), 3)

    def test_recruitment_anti_spam_cooldown(self):
        """Failed recruitment sets 3-turn cooldown and decrements per turn."""
        uid = 99883
        char = db.create_character(uid, "Dave", "Cleric", "fantasy")
        sess_id = db.create_session(uid, "solo", 1, "vivid", "individual", False, scenario="fantasy")
        party = [(char, db.get_inventory(uid))]

        db.update_session_npcs(sess_id, [{"name": "Severus", "disposition": "friendly"}])

        # Failed recruitment action
        outcome = {
            "scene_title": "Recruitment Failed",
            "narrative": "Severus shakes his head.",
            "location": "Solaria ➔ Tavern",
            "next_choices": []
        }
        actions = [{
            "label": "🤝 [CHA] Invite Severus to join your party",
            "check": {"is_success": False, "tier": "FAILURE"},
            "user_id": uid
        }]

        game_engine.apply_outcome(sess_id, party, outcome, actions=actions)

        # Verify not recruited and cooldown is active
        self.assertEqual(len(db.get_session_party_npcs(sess_id)), 0)
        cd = db.get_recruitment_cooldown(sess_id, "Severus")
        self.assertEqual(cd, 3)

        # Next turn tick
        db.decrement_recruitment_cooldowns(sess_id)
        self.assertEqual(db.get_recruitment_cooldown(sess_id, "Severus"), 2)

    def test_companion_dismissal_and_return(self):
        """Dismissing companion removes from party and returns origin location."""
        uid = 99884
        char = db.create_character(uid, "Eve", "Mage", "fantasy")
        sess_id = db.create_session(uid, "solo", 1, "vivid", "individual", False, scenario="fantasy")

        comp = {
            "name": "Elowen",
            "role": "Mage",
            "level": 5,
            "hp": 30,
            "max_hp": 30,
            "mp": 20,
            "max_mp": 20,
            "status_effects": [],
            "origin_location": "Solaria ➔ The Boar's Tusk Tavern ➔ Hearthside Table"
        }
        db.add_session_party_npc(sess_id, comp)
        self.assertEqual(len(db.get_session_party_npcs(sess_id)), 1)

        removed = db.remove_session_party_npc(sess_id, "Elowen")
        self.assertIsNotNone(removed)
        self.assertEqual(removed["name"], "Elowen")
        self.assertEqual(removed["origin_location"], "Solaria ➔ The Boar's Tusk Tavern ➔ Hearthside Table")
        self.assertEqual(len(db.get_session_party_npcs(sess_id)), 0)

    def test_downed_state_and_post_combat_revive(self):
        """When player is at 0 HP and combat ends with victory while companion is alive, player revives with 1 HP."""
        uid = 99880
        char = db.create_character(uid, "Fiona", "Warrior", "fantasy")
        # Set player to 5 HP
        with db.get_conn() as conn:
            conn.execute("UPDATE characters SET hp=5 WHERE user_id=?", (uid,))
        char = db.get_character(uid)

        sess_id = db.create_session(uid, "solo", 1, "vivid", "individual", False, scenario="fantasy")
        db.add_session_party_npc(sess_id, {"name": "Mara Vey", "role": "Scout", "level": 5, "hp": 30, "max_hp": 30, "mp": 20, "max_mp": 20})
        sess = db.get_session(sess_id)
        party = [(char, db.get_inventory(uid))]

        precomputed = {
            "acting_char_name": "Fiona",
            "player_damage_taken": 10, # Fatal damage: 5 HP - 10 = -5 HP
            "total_xp_gain": 50,
            "total_gold_gain": 10,
            "acting_char_xp": 50,
            "acting_char_gold": 10,
            "dead_enemies": ["Goblin Scout"],
            "enemies": [] # All enemies defeated!
        }
        llm_outcome = {
            "outcome_narrative": "Fiona collapsed, but Mara felled the last goblin!",
            "next_choices": []
        }

        result = combat.reconcile_combat_results(sess, llm_outcome, precomputed, party=party)

        # Verify player revived at 1 HP
        co = next((c for c in result["character_outcomes"] if c["name"] == "Fiona"), None)
        self.assertIsNotNone(co)
        # 5 HP + (-4 hp_change) = 1 HP
        self.assertEqual(char["hp"] + co["hp_change"], 1)
        self.assertIn("revived with **1 HP**", result["_combat_resolved_notice"])

    def test_dialogue_recruitment_choice_auto_injection(self):
        """When talking to a friendly NPC partner in combat scenario, recruitment option is auto-injected."""
        uid = 99881
        char = db.create_character(uid, "Alice", "Mage", "fantasy")
        sess_id = db.create_session(uid, "solo", 1, "vivid", "individual", False, scenario="fantasy")

        raw_choices = [
            {"label": "Ask Seraphine about guild records", "stat": "INT", "requirement": 6},
            {"label": "Thank Seraphine and step away", "stat": "NONE", "requirement": 0}
        ]

        from cogs.adventure import AdventureCog
        cleaned = AdventureCog._clean_choices(
            raw_choices,
            scenario="fantasy",
            location="Solaria ➔ The Boar's Tusk Tavern ➔ Hearthside Table",
            char=char,
            dialogue_partner="Seraphine Quill",
            current_npcs=[{"name": "Seraphine Quill"}],
            session_id=sess_id
        )

        labels = [c["label"] for c in cleaned]
        self.assertTrue(any("Invite Seraphine Quill to join your party" in l for l in labels))
        # Ensure it appears before the exit choice
        exit_idx = next(i for i, l in enumerate(labels) if "step away" in l.lower() or "thank" in l.lower())
        recruit_idx = next(i for i, l in enumerate(labels) if "Invite Seraphine Quill" in l)
        self.assertLess(recruit_idx, exit_idx)


if __name__ == "__main__":
    unittest.main()
