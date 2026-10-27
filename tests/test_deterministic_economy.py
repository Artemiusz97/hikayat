from __future__ import annotations
import os
import tempfile
import unittest
import db
import db.core
import character_data as cd
from game_engine.state.core import resolve_pre_turn_vitals_and_resources, apply_outcome
from mechanics.system.time_engine import apply_sleep_rest


class TestDeterministicEconomy(unittest.TestCase):
    def setUp(self):
        self._tmp_dir = tempfile.TemporaryDirectory()
        self._isolated_db = os.path.join(self._tmp_dir.name, "test_det_economy.db")
        self._orig_db_path = db.DB_PATH
        self._orig_core_db_path = db.core.DB_PATH
        db.DB_PATH = self._isolated_db
        db.core.DB_PATH = self._isolated_db
        db.init_db()

        self.user_id = 999888111
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

        self.session_id = db.create_session(
            self.user_id, "solo", 1, "vivid", "individual", False, scenario="fantasy"
        )
        self.session = db.get_session(self.session_id)
        self.party = [(self.char, db.get_inventory(self.user_id))]

    def tearDown(self):
        if hasattr(db, "close_all_connections"):
            db.close_all_connections()
        db.DB_PATH = self._orig_db_path
        db.core.DB_PATH = self._orig_core_db_path
        self._tmp_dir.cleanup()

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

        phys_st = db.get_session_physical_state(self.session_id) or {}
        dropped = phys_st.get("dropped_items", [])
        self.assertIn("Rare Relic", dropped, "Full inventory overflow must drop onto the room floor")

    def test_gold_double_deduction_prevented_and_atomic_staging(self):
        """D3: persist_db=False stages gold_spent without mutating SQLite until apply_outcome commits it atomically once."""
        initial_gold = self.char["gold"]
        action = {
            "label": "Buy a sturdy iron lantern from the merchant",
            "gold_spent": 20,
            "stat": "CHA",
            "check": {"succeeded": True, "tier": "success"},
        }
        pre_res = resolve_pre_turn_vitals_and_resources(self.session, self.party, [action], persist_db=False)
        self.assertFalse(bool(action.get("_gold_already_deducted")))
        self.assertEqual(pre_res.get("gold_delta"), -20)

        # Before apply_outcome (e.g. if LLM failed), DB gold MUST remain untouched!
        self.assertEqual(db.get_character(self.user_id)["gold"], initial_gold)

        outcome = {
            "character_outcomes": [
                {
                    "name": "Valen",
                    "gold_change": -20,  # Narrator repeats -20
                    "hp_change": 0,
                }
            ],
            "_pre_turn_vitals": pre_res,
        }
        apply_outcome(self.session_id, self.party, outcome, actions=[action])
        final_char = db.get_character(self.user_id)
        self.assertEqual(final_char["gold"], initial_gold - 20, "Gold must be deducted exactly once inside apply_outcome")

    def test_failed_gold_spent_only_deducted_on_gamble(self):
        """D7: Failed check with gold_spent > 0 deducts 0 gold except when sub_intent == 'gamble'."""
        action_haggle_fail = {
            "label": "Try to haggle for the ruby dagger",
            "sub_intent": "haggle",
            "gold_spent": 30,
            "stat": "CHA",
            "check": {"succeeded": False, "tier": "fail"},
        }
        pre_haggle = resolve_pre_turn_vitals_and_resources(self.session, self.party, [action_haggle_fail], persist_db=False)
        self.assertEqual(pre_haggle.get("gold_delta"), 0)

        action_gamble_fail = {
            "label": "Bet 25 gold on the dice table",
            "sub_intent": "gamble",
            "gold_spent": 25,
            "stat": "LUK",
            "check": {"succeeded": False, "tier": "fail"},
        }
        pre_gamble = resolve_pre_turn_vitals_and_resources(self.session, self.party, [action_gamble_fail], persist_db=False)
        self.assertEqual(pre_gamble.get("gold_delta"), -25)

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
                    "gold_change": 500,
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

        phys_st = self.session.get("physical_state", {})
        self.assertIn("Merchant Tobias", phys_st.get("pockets_emptied", []))

        pre_res_repeat = resolve_pre_turn_vitals_and_resources(self.session, self.party, [action_success])
        self.assertEqual(pre_res_repeat.get("gold_delta", 0), 0, "Repeat pickpocket attempt must yield 0 gold")
        self.assertTrue(any("already empty" in d for d in pre_res_repeat.get("stage_directives", [])))

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

    def test_consumable_pre_turn_usage_and_atomic_staging(self):
        """Consuming a healing potion heals damage and removes item (immediately when persist_db=True, or deferred when persist_db=False)."""
        db.update_character_fields(self.user_id, hp=40, max_hp=100)
        db.add_item(self.user_id, "Health Potion", "Consumable", "Heal 35 HP", 1)

        self.party = [(db.get_character(self.user_id), db.get_inventory(self.user_id))]
        action = {
            "label": "Drink Health Potion",
            "stat": "ITEM",
            "item_name": "Health Potion",
        }

        # Staged mode (persist_db=False): leaves DB intact until apply_outcome!
        pre_staged = resolve_pre_turn_vitals_and_resources(self.session, self.party, [dict(action)], persist_db=False)
        self.assertEqual(pre_staged.get("hp_delta"), 35)
        self.assertEqual(db.get_character(self.user_id)["hp"], 40)
        self.assertEqual(len(db.get_inventory(self.user_id)), 1)

        # Direct mode (persist_db=True): commits immediately
        pre_res = resolve_pre_turn_vitals_and_resources(self.session, self.party, [action], persist_db=True)
        self.assertIn("Health Potion", pre_res.get("items_lost", []))
        self.assertEqual(db.get_character(self.user_id)["hp"], 75)
        self.assertEqual(len(db.get_inventory(self.user_id)), 0)

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
        self.assertEqual(len(db.get_inventory(self.user_id)), 1)

    def test_virtual_5x_consumable_stacking_at_full_capacity(self):
        """D9: 5 identical consumables occupy 1 slot; adding 2nd..5th into a full inventory succeeds, 6th is blocked."""
        cap = cd.inventory_capacity(self.char["str_"])  # e.g. 15 slots
        for i in range(cap - 1):
            db.add_item(self.user_id, f"Iron Ingot {i}", "Misc", "Heavy ingot", 1)

        # Add 1st Health Potion -> occupies final free slot (cap / cap)
        db.add_item(self.user_id, "Health Potion", "Consumable", "Heal 35 HP", 1)
        self.assertEqual(db.used_slots(self.user_id), cap)

        # Adding 2nd, 3rd, 4th, 5th Health Potion must ALL fit into that existing 5x stack!
        for _ in range(4):
            self.assertTrue(db.can_add_item(self.user_id, name="Health Potion", item_type="Consumable", effect="Heal 35 HP"))
            db.add_item(self.user_id, "Health Potion", "Consumable", "Heal 35 HP", 1)

        self.assertEqual(db.used_slots(self.user_id), cap)
        potions = [i for i in db.get_inventory(self.user_id) if i["name"] == "Health Potion"]
        self.assertEqual(len(potions), 5)

        # 6th Health Potion starts a new stack and must be blocked at cap/cap!
        self.assertFalse(db.can_add_item(self.user_id, name="Health Potion", item_type="Consumable", effect="Heal 35 HP"))

    def test_drop_item_to_session_floor_preserves_gear_json_and_caps_at_10(self):
        """D20: Dropping an item places it on room floor (capped at 10) and preserves [GEAR_JSON] metadata."""
        desc = 'Fine elven blade [GEAR_JSON]{"atk": 12, "rarity": "rare"}[/GEAR_JSON]'
        item_id = db.add_item(self.user_id, "Elven Sabre", "Weapon", desc, 1)
        sabre_row = next(i for i in db.get_inventory(self.user_id) if i["id"] == item_id)
        res = db.drop_item_to_session_floor(self.user_id, sabre_row, self.session_id)
        self.assertTrue(res)

        phys = db.get_session_physical_state(self.session_id) or {}
        self.assertIn("Elven Sabre", phys.get("dropped_items", []))
        self.assertIn("[GEAR_JSON]", (phys.get("dropped_item_meta") or {}).get("elven sabre", {}).get("effect", ""))

        # Drop 12 more items -> floor must cap at 10!
        for i in range(12):
            iid = db.add_item(self.user_id, f"Pebble_{i}", "Misc", "Small stone", 1, force=True)
            prow = next(it for it in db.get_inventory(self.user_id) if it["id"] == iid)
            db.drop_item_to_session_floor(self.user_id, prow, self.session_id)
        phys_capped = db.get_session_physical_state(self.session_id) or {}
        self.assertLessEqual(len(phys_capped.get("dropped_items", [])), 10)

    def test_non_anomalous_zero_hp_hazard_knockout_recovery(self):
        """D8: Dropping to 0 HP outside combat in non-Anomalous scenario stabilizes at 50% HP, adds Exhausted / Recovering, +60m, and 3 recovery choices."""
        db.update_character_fields(self.user_id, hp=4, max_hp=100)
        party_low = [(db.get_character(self.user_id), [])]
        _, start_min, _ = db.get_session_time(self.session_id)

        action = {
            "label": "Scale the crumbling cliff face",
            "stat": "AGI",
            "intent": "traversal",
            "check": {"succeeded": False, "tier": "critical_failure"},
        }
        pre_res = resolve_pre_turn_vitals_and_resources(self.session, party_low, [action], persist_db=False)
        outcome = {
            "character_outcomes": [{"name": "Valen", "hp_change": pre_res.get("hp_delta", -15)}],
            "_pre_turn_vitals": pre_res,
        }
        apply_outcome(self.session_id, party_low, outcome, actions=[action])

        char_after = db.get_character(self.user_id)
        self.assertEqual(char_after["hp"], 50)
        self.assertIn("Exhausted / Recovering", char_after.get("status_effects") or [])
        self.assertTrue(bool(outcome.get("_party_defeated_notice")))
        self.assertEqual(len(outcome.get("next_choices") or []), 3)
        self.assertTrue(all(c.get("_server_stamped") for c in outcome["next_choices"]))
        _, end_min, _ = db.get_session_time(self.session_id)
        self.assertGreaterEqual(end_min - start_min, 60)

    def test_sleep_rest_clears_recovery_and_refractory_keeps_pockets_emptied(self):
        """D17: Overnight sleep clears recovery/refractory statuses, restores outfit, retains private romantic partner, and preserves pockets_emptied."""
        db.update_character_fields(self.user_id, hp=40, max_hp=100)
        db.set_status_effects(self.user_id, ["Exhausted / Recovering", "Spent"])
        db.save_world_node(self.session_id, "room_inn_priv", None, "Private Inn Suite", node_type="ROOM", privacy_level="private")
        db.upsert_contact(self.session_id, "aria_vale", "Aria Vale", delta_score=110, track="romantic")
        db.update_session(
            self.session_id,
            current_node_id="room_inn_priv",
            current_location="Private Inn Suite",
            current_npcs=[{"name": "Aria Vale"}, {"name": "Random Patron"}],
        )
        db.update_session_physical_state(self.session_id, {
            "intimate_contact": "intercourse with Aria Vale",
            "pockets_emptied": ["Merchant Tobias"],
            "excitement": {"active": True, "refractory_until_turn": 99, "player_in_refractory": True},
            "actors": {
                "Valen": {"clothing": {"top": "Removed", "bottom": "Displaced", "under_top": "Worn", "under_bottom": "Removed"}},
            },
        })

        apply_sleep_rest(self.session_id, [self.user_id], scen_key="fantasy", recovery_ratio=1.0, surface_label="Bed")

        char_morning = db.get_character(self.user_id)
        self.assertEqual(char_morning["hp"], 100)
        self.assertNotIn("Exhausted / Recovering", char_morning.get("status_effects") or [])

        phys_morning = db.get_session_physical_state(self.session_id) or {}
        self.assertEqual(phys_morning.get("intimate_contact"), "none")
        self.assertIn("Merchant Tobias", phys_morning.get("pockets_emptied", []), "pockets_emptied must remain permanent across sleep")
        valen_cloth = (phys_morning.get("actors") or {}).get("Valen", {}).get("clothing", {})
        self.assertIn(str(valen_cloth.get("top") or "").lower(), ("worn", "clothed"))
        self.assertIn(str(valen_cloth.get("bottom") or "").lower(), ("worn", "clothed"))

        sess_morning = db.get_session(self.session_id)
        morning_npcs = [n.get("name") for n in (sess_morning.get("current_npcs") or []) if isinstance(n, dict)]
        self.assertIn("Aria Vale", morning_npcs, "Romantic partner in private room must stay through morning")

    def test_equipped_gear_auto_unequip_and_physical_state_sync(self):
        """Dropping or removing an equipped weapon automatically unequips it and syncs physical state."""
        item_id = db.add_item(self.user_id, "Steel Longsword", "Weapon", "+10 ATK", 1)
        db.equip_item(self.user_id, item_id, "Weapon")

        phys_st = db.get_session_physical_state(self.session_id) or {}
        actors = phys_st.get("actors", {})
        player_act = actors.get("Valen", {}) or actors.get("player", {})
        self.assertIn("Steel Longsword", player_act.get("holding", ""))

        db.remove_item_by_name(self.user_id, "Steel Longsword")

        phys_st_after = db.get_session_physical_state(self.session_id) or {}
        actors_after = phys_st_after.get("actors", {})
        player_act_after = actors_after.get("Valen", {}) or actors_after.get("player", {})
        self.assertEqual(player_act_after.get("holding", ""), "Empty hands")

    def test_temp_hp_non_stacking_and_expiration(self):
        """Temporary HP uses non-stacking max(current, new) and expires upon transitioning outside combat."""
        char1 = db.apply_hp_mp_delta(self.user_id, temp_hp_delta=20)
        self.assertEqual(char1["temp_hp"], 20)

        char2 = db.apply_hp_mp_delta(self.user_id, temp_hp_delta=15)
        self.assertEqual(char2["temp_hp"], 20)

        char3 = db.apply_hp_mp_delta(self.user_id, temp_hp_delta=30)
        self.assertEqual(char3["temp_hp"], 30)

        outcome = {"character_outcomes": [{"name": "Valen", "hp_change": 0, "temp_hp_change": 0}]}
        apply_outcome(self.session_id, [(char3, [])], outcome)
        char_after_explore = db.get_character(self.user_id)
        self.assertEqual(char_after_explore["temp_hp"], 0, "Temp HP must expire outside combat")

    def test_social_turn_hp_damage_immunity(self):
        """Failed dialogue or social persuasion check never inflicts physical HP damage."""
        initial_hp = self.char["hp"]
        action = {
            "label": "Try to persuade the magistrate to drop the charges",
            "stat": "CHA",
            "intent": "dialogue",
            "check": {"succeeded": False, "tier": "fail"},
        }
        outcome = {
            "character_outcomes": [{"name": "Valen", "hp_change": -25, "gold_change": 0}],
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


if __name__ == "__main__":
    unittest.main()
