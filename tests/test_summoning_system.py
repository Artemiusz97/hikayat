import unittest
import db
from mechanics.combat import precompute_combat_turn, reconcile_combat_results

class TestSummoningSystem(unittest.TestCase):
    def setUp(self):
        db.init_db()
        self.user_id = 998877665
        chars = db.get_user_characters(self.user_id)
        for c in chars:
            db.delete_character(self.user_id, c["id"])
        db.create_character(
            user_id=self.user_id,
            name="Alice",
            char_class="Necromancer",
            stats={"STR": 2, "PER": 5, "END": 4, "CHA": 3, "INT": 8, "AGI": 4, "LUK": 3}
        )

    def tearDown(self):
        chars = db.get_user_characters(self.user_id)
        for c in chars:
            db.delete_character(self.user_id, c["id"])

    def test_summon_spell_execution_and_lifecycle(self):
        char = db.get_character(self.user_id)
        char_dict = dict(char)
        char_dict["user_id"] = self.user_id
        party = [(char_dict, None)]

        session = {
            "id": 8888,
            "scenario": "fantasy",
            "nearby_enemies": [
                {"name": "Orc Brute", "archetype": "Brute", "level": 3, "hp": 250, "max_hp": 250}
            ],
            "current_npcs": []
        }

        # 1. Player casts "Raise Skeletons" (summons 2 Dread Skeletons)
        actions = [{
            "stat": "INT",
            "tier": "success",
            "label": "💀 Raise Skeletons (2x • 3t • 10 MP)",
            "spell_id": "raise_skeletons_t3_st",
            "action_category": "magic",
            "discipline": "summon"
        }]

        res = precompute_combat_turn(session, party, actions)
        
        # Verify combat log announces the summoning
        log_text = "\n".join(res["combat_log"])
        self.assertIn("Raise Skeletons", log_text)
        self.assertIn("Dread Skeleton", log_text)

        # Verify summons were added to current_npcs
        npcs = res["current_npcs"]
        summons = [n for n in npcs if n.get("is_summon")]
        self.assertGreaterEqual(len(summons), 1)
        self.assertEqual(summons[0]["archetype"], "Skirmisher")
        self.assertGreater(summons[0]["hp"], 0)

        # 2. Next Round: Summons auto-attack and decrement duration
        session["current_npcs"] = npcs
        actions_round2 = [{
            "stat": "INT",
            "tier": "success",
            "label": "Cast Firebolt",
            "spell_id": "firebolt_t3_st",
            "action_category": "magic",
            "discipline": "attack"
        }]

        res2 = precompute_combat_turn(session, party, actions_round2)
        log2_text = "\n".join(res2["combat_log"])
        # Summons attacked during Phase 2
        self.assertTrue("Dread Skeleton" in log2_text and "attacked" in log2_text)

        # 3. Verify post-combat cleanup on victory
        precomputed_victory = {
            "dead_enemies": ["Orc Brute"],
            "surviving_enemies": [],
            "xp_gain": 100,
            "gold_gain": 50,
            "combat_log": ["Victory!"]
        }
        session["nearby_enemies"] = []
        session["nearby_monsters"] = []
        session["current_npcs"] = [
            {"name": "Dread Skeleton #1", "is_summon": True, "hp": 20},
            {"name": "Town Mayor", "is_summon": False, "hp": 50}
        ]

        llm_outcome = {"nearby_enemies": [], "choices": []}
        reconciled = reconcile_combat_results(session, llm_outcome, precomputed_victory)
        
        # Summons must be cleanly purged from session current_npcs, regular NPCs remain
        surviving_npcs = session["current_npcs"]
        self.assertFalse(any(n.get("is_summon") for n in surviving_npcs))
        self.assertTrue(any(n.get("name") == "Town Mayor" for n in surviving_npcs))
