import unittest
import db
import character_data as cd
import game_engine
import config
from game_engine.state.core import resolve_pre_turn_vitals_and_resources, apply_outcome


class TestDeterministicEconomy(unittest.TestCase):
    def setUp(self):
        db.init_db()
        self.user_id = 999888111
        self.session_id = 777666555
        
        # Clean up existing characters & sessions
        for c in db.get_user_characters(self.user_id):
            db.delete_character(self.user_id, c["id"])
            
        base_stats = {"STR": 5, "PER": 5, "END": 5, "CHA": 5, "INT": 5, "AGI": 5, "LUK": 10}
        self.char = db.create_character(
            user_id=self.user_id,
            name="Valen",
            char_class="Rogue",
            class_description="Test Rogue",
            stats=base_stats,
        )
        db.update_character_fields(self.user_id, hp=100, max_hp=100, mp=50, max_mp=50, gold=100, temp_hp=0)
        self.char = db.get_character(self.user_id)
        
        # Create session
        self.session_id = db.create_session(
            self.user_id, "solo", 1, "vivid", "individual", False, scenario="fantasy"
        )
        self.session = db.get_session(self.session_id)
        self.party = [(self.char, db.get_inventory(self.user_id))]

    def tearDown(self):
        for c in db.get_user_characters(self.user_id):
            db.delete_character(self.user_id, c["id"])
        if hasattr(self, "session_id"):
            db.delete_session(self.session_id)

    def test_unauthorized_item_hallucination_rejected(self):
        """Ungrounded items invented by the LLM in character_outcomes are rejected."""
        outcome = {
            "character_outcomes": [
                {
                    "name": "Valen",
                    "items_gained": ["Excalibur +10", "Diamond Ring"],
                    "gold_change": 0,
                    "hp_change": 0,
                }
            ],
            "outcome_narrative": "You suddenly find an Excalibur lying on the stone floor.",
        }
        gained = apply_outcome(self.session_id, self.party, outcome, actions=[])
        
        # Excalibur was not authorized by loot roll or quest
        user_gained = gained.get(self.user_id, [])
        self.assertNotIn("Excalibur +10", user_gained)
        self.assertNotIn("Diamond Ring", user_gained)
        
        inv = db.get_inventory(self.user_id)
        self.assertEqual(len(inv), 0, "Inventory must remain empty when items are ungrounded hallucinations")

    def test_authorized_loot_roll_accepted(self):
        """Action with triggers_loot_roll: True pre-rolls procedural loot and apply_outcome authorizes it."""
        action = {
            "label": "Search the ancient chest for supplies",
            "triggers_loot_roll": True,
            "stat": "PER",
            "check": {"succeeded": True, "tier": "success"},
        }
        pre_res = resolve_pre_turn_vitals_and_resources(self.session, self.party, [action])
        rolled_items = pre_res.get("loot_items_rolled", [])
        self.assertGreater(len(rolled_items), 0, "Loot roll must generate an item")
        rolled_item_name = rolled_items[0]

        outcome = {
            "character_outcomes": [
                {
                    "name": "Valen",
                    "items_gained": [rolled_item_name],
                    "gold_change": 0,
                    "hp_change": 0,
                }
            ],
            "_authorized_loot": rolled_items,
            "_pre_turn_vitals": pre_res,
        }
        gained = apply_outcome(self.session_id, self.party, outcome, actions=[action])
        user_gained = gained.get(self.user_id, [])
        self.assertIn(rolled_item_name, user_gained)
        
        inv = db.get_inventory(self.user_id)
        self.assertEqual(len(inv), 1)
        self.assertEqual(inv[0]["name"], rolled_item_name)

    def test_inventory_overflow_dropped_to_ground(self):
        """When gaining an authorized item with a full inventory, it drops into physical_state['dropped_items']."""
        cap = cd.inventory_capacity(self.char["str_"])
        for i in range(cap):
            db.add_item(self.user_id, f"Trinket_{i}", "Misc", "Test clutter", 1)
        
        self.assertEqual(db.used_slots(self.user_id), cap)

        outcome = {
            "character_outcomes": [
                {
                    "name": "Valen",
                    "items_gained": ["Rare Relic"],
                    "gold_change": 0,
                    "hp_change": 0,
                }
            ],
            "_authorized_loot": ["Rare Relic"],
        }
        gained = apply_outcome(self.session_id, self.party, outcome, actions=[])
        user_gained = gained.get(self.user_id, [])
        self.assertTrue(any("Dropped to ground" in g for g in user_gained))
        
        # Verify physical state has dropped item
        phys_st = db.get_session_physical_state(self.session_id) or {}
        dropped = phys_st.get("dropped_items", [])
        self.assertIn("Rare Relic", dropped, "Full inventory overflow must drop onto the room floor")

    def test_gold_double_deduction_prevented(self):
        """Action with gold_spent: 20 deducts exactly 20 gold once, even if LLM repeats gold_change: -20."""
        initial_gold = self.char["gold"]
        action = {
            "label": "Buy a sturdy iron lantern from the merchant",
            "gold_spent": 20,
            "stat": "CHA",
            "check": {"succeeded": True, "tier": "success"},
        }
        pre_res = resolve_pre_turn_vitals_and_resources(self.session, self.party, [action])
        self.assertTrue(action.get("_gold_already_deducted"))
        self.assertEqual(pre_res.get("gold_delta"), -20)
        
        # Apply pre-turn gold deduction
        char_after_pre = db.apply_hp_mp_delta(self.user_id, gold_delta=pre_res.get("gold_delta", 0))
        self.assertEqual(char_after_pre["gold"], initial_gold - 20)

        # Narrator outcome repeats -20 in character_outcomes
        outcome = {
            "character_outcomes": [
                {
                    "name": "Valen",
                    "gold_change": -20,
                    "hp_change": 0,
                }
            ],
            "_pre_turn_vitals": pre_res,
        }
        apply_outcome(self.session_id, [(char_after_pre, [])], outcome, actions=[action])
        final_char = db.get_character(self.user_id)
        self.assertEqual(final_char["gold"], initial_gold - 20, "Gold must not be double-deducted")

    def test_unauthorized_gold_gain_clamped_to_zero(self):
        """LLM outputting arbitrary gold_change in social dialogue without rewards gets clamped to 0."""
        initial_gold = self.char["gold"]
        action = {
            "label": "Chat with the barkeep about local gossip",
            "stat": "CHA",
            "check": {"succeeded": True, "tier": "success"},
        }
        outcome = {
            "character_outcomes": [
                {
                    "name": "Valen",
                    "gold_change": 500,  # Hallucinated gold duplication
                    "hp_change": 0,
                }
            ],
        }
        apply_outcome(self.session_id, self.party, outcome, actions=[action])
        final_char = db.get_character(self.user_id)
        self.assertEqual(final_char["gold"], initial_gold, "Arbitrary gold hallucinations must be clamped to 0")

    def test_pickpocket_deterministic_payout_and_anti_farm(self):
        """Pickpocket check grants structured gold, sets pockets_emptied, prevents repeat farming, and penalizes failure."""
        action_success = {
            "label": "Slip behind the wealthy merchant and pick his pockets",
            "sub_intent": "pickpocket",
            "target_npc": "Merchant Tobias",
            "stat": "AGI",
            "check": {"succeeded": True, "tier": "success"},
        }
        pre_res = resolve_pre_turn_vitals_and_resources(self.session, self.party, [action_success])
        bounty = pre_res.get("gold_delta", 0)
        self.assertGreater(bounty, 0, "Successful pickpocket on merchant must grant structured gold bounty")
        
        # Verify pockets_emptied stored in physical state
        phys_st = self.session.get("physical_state", {})
        self.assertIn("Merchant Tobias", phys_st.get("pockets_emptied", []))

        # Attempt 2: Repeat pickpocket on same NPC
        pre_res_repeat = resolve_pre_turn_vitals_and_resources(self.session, self.party, [action_success])
        self.assertEqual(pre_res_repeat.get("gold_delta", 0), 0, "Repeat pickpocket attempt must yield 0 gold")
        self.assertTrue(any("already empty" in d for d in pre_res_repeat.get("stage_directives", [])))

        # Attempt 3: Failed pickpocket check on another NPC
        action_fail = {
            "label": "Try to pick the guard captain's coin pouch",
            "sub_intent": "pickpocket",
            "target_npc": "Captain Kael",
            "stat": "AGI",
            "check": {"succeeded": False, "tier": "fail"},
        }
        pre_res_fail = resolve_pre_turn_vitals_and_resources(self.session, self.party, [action_fail])
        self.assertEqual(pre_res_fail.get("gold_delta", 0), 0)
        self.assertTrue(any("caught" in d.lower() for d in pre_res_fail.get("stage_directives", [])))
        contact = db.get_contact(self.session_id, "captain_kael") or db.get_contact(self.session_id, "Captain Kael")
        self.assertIsNotNone(contact)
        self.assertEqual(contact.get("relationship_score", 0), -15, "Failed pickpocket must apply -15 affinity penalty")

    def test_consumable_pre_turn_usage(self):
        """Consuming a healing potion via stat == 'ITEM' heals damage and removes item pre-turn."""
        db.update_character_fields(self.user_id, hp=40, max_hp=100)
        db.add_item(self.user_id, "Health Potion", "Consumable", "Heal 35 HP", 1)
        
        self.party = [(db.get_character(self.user_id), db.get_inventory(self.user_id))]
        action = {
            "label": "Drink Health Potion",
            "stat": "ITEM",
            "item_name": "Health Potion",
        }
        pre_res = resolve_pre_turn_vitals_and_resources(self.session, self.party, [action])
        self.assertIn("Health Potion", pre_res.get("items_lost", []))
        self.assertEqual(pre_res.get("hp_delta"), 35)
        
        # Verify HP was restored in DB
        char = db.get_character(self.user_id)
        self.assertEqual(char["hp"], 75)
        
        # Verify item was removed from DB inventory
        inv = db.get_inventory(self.user_id)
        self.assertEqual(len(inv), 0)

    def test_consumable_waste_prevention_on_full_vitals(self):
        """Using a healing potion when HP is already 100/100 blocks consumption to prevent accidental waste."""
        db.update_character_fields(self.user_id, hp=100, max_hp=100)
        db.add_item(self.user_id, "Health Potion", "Consumable", "Heal 35 HP", 1)
        
        self.party = [(db.get_character(self.user_id), db.get_inventory(self.user_id))]
        action = {
            "label": "Drink Health Potion",
            "stat": "ITEM",
            "item_name": "Health Potion",
        }
        pre_res = resolve_pre_turn_vitals_and_resources(self.session, self.party, [action])
        self.assertEqual(len(pre_res.get("items_lost", [])), 0, "Item must NOT be consumed when vitals full")
        self.assertTrue(any("already full" in d for d in pre_res.get("stage_directives", [])))
        
        inv = db.get_inventory(self.user_id)
        self.assertEqual(len(inv), 1, "Potion must remain safely in inventory")

    def test_equipped_gear_auto_unequip_and_physical_state_sync(self):
        """Dropping or removing an equipped weapon automatically unequips it and syncs physical state."""
        item_id = db.add_item(self.user_id, "Steel Longsword", "Weapon", "+10 ATK", 1)
        db.equip_item(self.user_id, item_id, "Weapon")
        
        # Verify holding state in physical state
        phys_st = db.get_session_physical_state(self.session_id) or {}
        actors = phys_st.get("actors", {})
        player_act = actors.get("Valen", {}) or actors.get("player", {})
        self.assertIn("Steel Longsword", player_act.get("holding", ""))

        # Remove item (simulating sale, gift, or discard)
        db.remove_item_by_name(self.user_id, "Steel Longsword")
        
        # Verify physical state holding reverted to Empty hands
        phys_st_after = db.get_session_physical_state(self.session_id) or {}
        actors_after = phys_st_after.get("actors", {})
        player_act_after = actors_after.get("Valen", {}) or actors_after.get("player", {})
        self.assertEqual(player_act_after.get("holding", ""), "Empty hands")

    def test_temp_hp_non_stacking_and_expiration(self):
        """Temporary HP uses non-stacking max(current, new) and expires upon transitioning outside combat."""
        # 1. First shield buff of 20
        char1 = db.apply_hp_mp_delta(self.user_id, temp_hp_delta=20)
        self.assertEqual(char1["temp_hp"], 20)

        # 2. Smaller shield buff of 15 does not stack to 35; max(20, 15) = 20
        char2 = db.apply_hp_mp_delta(self.user_id, temp_hp_delta=15)
        self.assertEqual(char2["temp_hp"], 20)

        # 3. Larger shield buff of 30 upgrades temp HP to max(20, 30) = 30
        char3 = db.apply_hp_mp_delta(self.user_id, temp_hp_delta=30)
        self.assertEqual(char3["temp_hp"], 30)

        # 4. In exploration turn (is_combat = False), apply_outcome clears lingering temp HP
        outcome = {
            "character_outcomes": [
                {
                    "name": "Valen",
                    "hp_change": 0,
                    "temp_hp_change": 0,
                }
            ]
        }
        apply_outcome(self.session_id, [(char3, [])], outcome)
        char_after_explore = db.get_character(self.user_id)
        self.assertEqual(char_after_explore["temp_hp"], 0, "Temp HP must expire outside combat")

    def test_social_turn_hp_damage_immunity(self):
        """Failed dialogue or social persuasion check never inflicts physical HP damage under DETERMINISTIC_ECONOMY."""
        initial_hp = self.char["hp"]
        action = {
            "label": "Try to persuade the magistrate to drop the charges",
            "stat": "CHA",
            "intent": "dialogue",
            "check": {"succeeded": False, "tier": "fail"},
        }
        outcome = {
            "character_outcomes": [
                {
                    "name": "Valen",
                    "hp_change": -25,  # Hallucinated damage on dialogue failure
                    "gold_change": 0,
                }
            ],
            "outcome_narrative": "The magistrate angrily points to the door and rejects your plea.",
        }
        apply_outcome(self.session_id, self.party, outcome, actions=[action])
        char = db.get_character(self.user_id)
        self.assertEqual(char["hp"], initial_hp, "Social turn must inflict 0 physical HP damage")

    def test_physical_hazard_damage_applied(self):
        """Failed physical hazard check (STR/AGI/END) inflicts authorized pre-turn hazard damage."""
        action = {
            "label": "Leap across the crumbling chasms of jagged obsidian",
            "stat": "AGI",
            "intent": "traversal",
            "check": {"succeeded": False, "tier": "fail"},
        }
        pre_res = resolve_pre_turn_vitals_and_resources(self.session, self.party, [action])
        self.assertEqual(pre_res.get("hp_delta"), -5, "Failed normal AGI hazard must inflict 5% max HP damage")
        self.assertTrue(any("HAZARD CONSEQUENCE" in d for d in pre_res.get("stage_directives", [])))

    def test_rollback_guard(self):
        """When DETERMINISTIC_ECONOMY is toggled False, legacy behavior functions as rollback."""
        try:
            config.DETERMINISTIC_ECONOMY = False
            curr_char = db.get_character(self.user_id)
            initial_hp = curr_char["hp"]
            initial_gold = curr_char["gold"]
            action = {
                "label": "Talk to the angry patron",
                "stat": "CHA",
                "intent": "dialogue",
                "check": {"succeeded": False, "tier": "fail"},
            }
            outcome = {
                "character_outcomes": [
                    {
                        "name": "Valen",
                        "hp_change": -10,
                        "gold_change": 50,
                        "items_gained": ["Wooden Flute"],
                    }
                ]
            }
            apply_outcome(self.session_id, self.party, outcome, actions=[action])
            char = db.get_character(self.user_id)
            expected_hp = initial_hp - 10 + cd.hp_regen(curr_char["end_"])
            self.assertEqual(char["hp"], expected_hp, "Under rollback, legacy arbitrary HP damage is applied (with passive regen)")
            self.assertEqual(char["gold"], initial_gold + 50, "Under rollback, legacy arbitrary gold change is applied")
            inv = db.get_inventory(self.user_id)
            self.assertTrue(any(i["name"] == "Wooden Flute" for i in inv), "Under rollback, legacy item grant is applied")
        finally:
            config.DETERMINISTIC_ECONOMY = True


if __name__ == "__main__":
    unittest.main()
