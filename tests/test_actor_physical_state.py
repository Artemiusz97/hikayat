"""
Comprehensive Test Suite for Normalized Actor Physical State & Garment Layer Model.
Covers all 15 locked invariants from physical_state_garment_model_implementation_plan.md.
"""
import json
import os
import unittest
import pytest

import db
import mechanics.social.physical_state as ps


class TestActorPhysicalStateEngine(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        db.init_db()

    def setUp(self):
        self.user_id = 888899
        self.session_id = 999888
        with db.get_conn() as conn:
            conn.execute("DELETE FROM sessions WHERE id=?", (self.session_id,))
            conn.execute("DELETE FROM characters WHERE id=?", (self.user_id,))
            conn.execute("""
                INSERT OR REPLACE INTO characters (id, user_id, name, char_class, level, hp, max_hp, mp, max_mp, gold, active_session_id)
                VALUES (?, ?, 'Aria', 'Warrior', 1, 100, 100, 50, 50, 100, ?)
            """, (self.user_id, self.user_id, self.session_id))
            conn.execute("""
                INSERT OR REPLACE INTO sessions (id, host_user_id, status, mode, capacity, scenario, physical_state_json)
                VALUES (?, ?, 'active', 'single', 1, 'fantasy', '{}')
            """, (self.session_id, self.user_id))

    def tearDown(self):
        try:
            with db.get_conn() as conn:
                conn.execute("DELETE FROM sessions WHERE id=?", (self.session_id,))
                conn.execute("DELETE FROM characters WHERE id=?", (self.user_id,))
                conn.execute("DELETE FROM adventure_saves WHERE character_id=?", (self.user_id,))
        except Exception:
            pass

    def test_01_schema_initialization_and_layer_topology(self):
        """Invariant 1: Verifies 6 slots per actor with correct default layer depths."""
        garments_data = {
            ps.SLOT_OUTERWEAR: {"state": ps.STATE_WORN, "item_name": "Traveler Cloak", "layer_depth": 3},
            ps.SLOT_TOP: {"state": ps.STATE_WORN, "item_name": "Silk Tunic", "layer_depth": 2},
            ps.SLOT_BOTTOM: {"state": ps.STATE_WORN, "item_name": "Leather Breeches", "layer_depth": 2},
            ps.SLOT_UNDER_TOP: {"state": ps.STATE_WORN, "item_name": "Lace Bra", "layer_depth": 1},
            ps.SLOT_UNDER_BOTTOM: {"state": ps.STATE_WORN, "item_name": "Lace Panties", "layer_depth": 1},
            ps.SLOT_FOOTWEAR: {"state": ps.STATE_WORN, "item_name": "Riding Boots", "layer_depth": 1},
        }
        actor_state = {
            "posture": "standing",
            "holding": "Steel Shortsword",
            "stance": "Ready",
            "composure": ps.COMPOSURE_COMPOSED,
        }
        ps.upsert_actor_physical_state(self.session_id, "Aria", actor_state, garments=garments_data)

        fetched = ps.get_actor_physical_state(self.session_id, "Aria")
        self.assertIsNotNone(fetched)
        self.assertEqual(fetched["canonical_key"], "aria")
        self.assertEqual(fetched["posture"], "standing")
        self.assertEqual(fetched["holding"], "Steel Shortsword")

        garments = ps.get_actor_garments(self.session_id, "aria")
        self.assertEqual(len(garments), 6)
        depth_map = {g["slot"]: g["layer_depth"] for g in garments}
        self.assertEqual(depth_map[ps.SLOT_OUTERWEAR], 3)
        self.assertEqual(depth_map[ps.SLOT_TOP], 2)
        self.assertEqual(depth_map[ps.SLOT_BOTTOM], 2)
        self.assertEqual(depth_map[ps.SLOT_UNDER_TOP], 1)
        self.assertEqual(depth_map[ps.SLOT_UNDER_BOTTOM], 1)
        self.assertEqual(depth_map[ps.SLOT_FOOTWEAR], 1)

    def test_02_auto_cascading_garment_fsm_transitions(self):
        """Invariant 1: Displacing underwear auto-cascades worn pants/skirt/top to disheveled."""
        base_cloth = {
            ps.SLOT_OUTERWEAR: "Traveler Cloak",
            ps.SLOT_TOP: "Silk Tunic",
            ps.SLOT_BOTTOM: "Leather Breeches",
            ps.SLOT_UNDER_TOP: "Lace Bra",
            ps.SLOT_UNDER_BOTTOM: "Lace Panties",
            ps.SLOT_FOOTWEAR: "Boots",
        }

        # 1. Displace under_bottom: bottom and outerwear must cascade to disheveled
        updated = ps.apply_garment_transition(base_cloth, ps.SLOT_UNDER_BOTTOM, ps.STATE_DISPLACED)
        self.assertIn(ps.STATE_DISPLACED, updated[ps.SLOT_UNDER_BOTTOM].lower())
        self.assertIn("disheveled", updated[ps.SLOT_BOTTOM].lower())
        self.assertIn("disheveled", updated[ps.SLOT_OUTERWEAR].lower())
        # Top remains worn/unaffected
        self.assertEqual(updated[ps.SLOT_TOP], "Silk Tunic")

        # 2. Displace under_top: top must cascade to disheveled
        updated2 = ps.apply_garment_transition(updated, ps.SLOT_UNDER_TOP, ps.STATE_DISPLACED)
        self.assertIn(ps.STATE_DISPLACED, updated2[ps.SLOT_UNDER_TOP].lower())
        self.assertIn("disheveled", updated2[ps.SLOT_TOP].lower())

    def test_03_environmental_composure_flags(self):
        """Invariant 3: Toggling is_wet, is_bloodied, and composure persists cleanly."""
        state_data = {
            "posture": "kneeling",
            "holding": "Empty hands",
            "composure": ps.COMPOSURE_FLUSTERED,
            "is_wet": 1,
            "is_bloodied": 1,
        }
        ps.upsert_actor_physical_state(self.session_id, "Elena", state_data)

        fetched = ps.get_actor_physical_state(self.session_id, "Elena")
        self.assertIsNotNone(fetched)
        self.assertEqual(fetched["composure"], ps.COMPOSURE_FLUSTERED)
        self.assertEqual(fetched["is_wet"], 1)
        self.assertEqual(fetched["is_bloodied"], 1)

        # Transition composure to exhausted
        state_data["composure"] = ps.COMPOSURE_EXHAUSTED
        ps.upsert_actor_physical_state(self.session_id, "Elena", state_data)
        updated = ps.get_actor_physical_state(self.session_id, "Elena")
        self.assertEqual(updated["composure"], ps.COMPOSURE_EXHAUSTED)

    def test_04_contextual_aftercare_redressing(self):
        """Invariant 2: Intimate conclusion preserves disarray; travel/rest restores canonical outfit."""
        curr_state = {
            "actors": {
                "Elena": {
                    "posture": "Resting / Embracing on bed",
                    "holding": "Empty hands",
                    "clothing": {
                        "top": "Removed",
                        "bottom": "Disheveled",
                        "under_top": "Removed",
                        "under_bottom": "Worn",
                    },
                }
            },
            "intimate_contact": "Tender aftercare resting",
            "props": {},
            "dropped_items": ["Elena's top", "Elena's under_top"],
        }
        # In-scene updates preserve aftercare state
        merged = ps.merge_physical_state_updates(curr_state, {"actors": {}})
        self.assertIn("aftercare", merged["intimate_contact"].lower())
        self.assertEqual(merged["actors"]["Elena"]["clothing"]["top"], "Removed")

        # Location transition or explicit redress triggers restoration
        party = [{"name": "Aria"}, {"name": "Elena"}]
        restored = ps.handle_location_transition(merged, party=party, session_id=self.session_id)
        elena_cloth = restored["actors"]["Elena"]["clothing"]
        self.assertEqual(elena_cloth["top"], "Clothed")
        self.assertEqual(elena_cloth["bottom"], "Clothed")
        self.assertEqual(restored["dropped_items"], [])

    def test_05_three_tier_wardrobe_resolution(self):
        """Invariant 3: Contact appearance parsed into named garments instead of generic 'Clothed'."""
        npc_data = {
            "name": "Lady Vivienne",
            "gender": "female",
            "appearance": {
                "attire": "Velvet Corset Gown",
                "undergarments": {"bra": "Black Silk Balconette", "underwear": "Matching Silk Briefs"},
            },
            "inventory": [
                {"slot": "Outerwear", "name": "Ermine Mantle"},
                {"slot": "Footwear", "name": "Embroidered Slippers"},
            ],
        }
        wardrobe = ps.resolve_canonical_wardrobe(npc_data, scen_key="fantasy")
        self.assertEqual(wardrobe[ps.SLOT_OUTERWEAR]["item_name"], "Ermine Mantle")
        self.assertEqual(wardrobe[ps.SLOT_TOP]["item_name"], "Velvet Corset Gown")
        self.assertEqual(wardrobe[ps.SLOT_FOOTWEAR]["item_name"], "Embroidered Slippers")
        self.assertIn("Black Silk Balconette", wardrobe[ps.SLOT_UNDER_TOP]["item_name"])
        self.assertIn("Matching Silk Briefs", wardrobe[ps.SLOT_UNDER_BOTTOM]["item_name"])

    def test_06_venue_aware_indecency_detection(self):
        """Invariant 4: Public exposure triggers shock tags and gossip roll; private rooms are quiet."""
        naked_cloth = {
            ps.SLOT_TOP: "removed",
            ps.SLOT_BOTTOM: "removed",
            ps.SLOT_UNDER_TOP: "none",
            ps.SLOT_UNDER_BOTTOM: "removed",
        }
        # Public Grand Bazaar
        pub_result = ps.check_venue_indecency_exposure(naked_cloth, "Grand Bazaar Town Square", gender="female")
        self.assertTrue(pub_result["is_exposed"])
        self.assertTrue(pub_result["requires_reaction"])
        self.assertEqual(pub_result["exposure_type"], "fully_naked")
        self.assertEqual(pub_result["gossip_topic"], "#Scandal")

        # Private Royal Bedchamber
        priv_result = ps.check_venue_indecency_exposure(naked_cloth, "Private Royal Bedchamber", gender="female")
        self.assertTrue(priv_result["is_exposed"])
        self.assertFalse(priv_result["requires_reaction"])
        self.assertTrue(priv_result["is_private_venue"])

    def test_07_inventory_sync_and_transient_decoupling(self):
        """Invariant 5 & 14: Disarming combatant moves holding to empty hands and adds weapon to dropped_items without deleting inventory."""
        curr_state = {
            "actors": {
                "Warrior": {
                    "posture": "Standing alert",
                    "holding": "Warhammer",
                    "stance": "Ready",
                }
            },
            "dropped_items": [],
        }
        # Knock down warrior
        updates = {
            "actors": {
                "Warrior": {
                    "posture": "Downed on cobblestones",
                    "stance": "Incapacitated",
                }
            }
        }
        merged = ps.merge_physical_state_updates(curr_state, updates)
        warrior = merged["actors"]["Warrior"]
        self.assertEqual(warrior["holding"], "Dropped / Empty hands")
        self.assertTrue(any("Warhammer" in it for it in merged["dropped_items"]))

    def test_08_startup_cutover_migration_from_legacy_json(self):
        """Invariant 6 (Clean Cutover): Migration 30 migrates legacy physical_state_json actors into relational tables once and strips actors JSON."""
        from db.core import _migrate_clean_cutover_v30
        legacy_state = {
            "actors": {
                "Sora": {
                    "posture": "Sitting on sofa",
                    "holding": "Teacup",
                    "stance": "Neutral",
                    "clothing": {
                        "top": "Silk Kimono",
                        "bottom": "Hakama Pants",
                        "under_top": "Worn",
                        "under_bottom": "Worn",
                    },
                }
            },
            "props": {"Tea Table": "Set with kettle"},
            "intimate_contact": "none",
        }
        with db.get_conn() as conn:
            conn.execute("DELETE FROM actor_physical_states WHERE session_id=?", (self.session_id,))
            conn.execute("DELETE FROM actor_garments WHERE session_id=?", (self.session_id,))
            conn.execute("UPDATE sessions SET physical_state_json=? WHERE id=?", (json.dumps(legacy_state), self.session_id))
            _migrate_clean_cutover_v30(conn)

        migrated = ps.get_actor_physical_state(self.session_id, "Sora")
        self.assertIsNotNone(migrated)
        self.assertEqual(migrated["actor_name"], "Sora")
        self.assertEqual(migrated["posture"], "Sitting on sofa")
        self.assertEqual(migrated["holding"], "Teacup")
        self.assertIn("top", migrated["clothing"])
        with db.get_conn() as conn:
            raw_meta = json.loads(conn.execute("SELECT physical_state_json FROM sessions WHERE id=?", (self.session_id,)).fetchone()["physical_state_json"] or "{}")
            self.assertNotIn("actors", raw_meta)
            self.assertIn("Tea Table", raw_meta.get("props", {}))

    def test_09_save_load_cloning_persistence(self):
        """Invariant 15: Saving and loading adventure slot clones actor_physical_states and actor_garments."""
        actor_state = {"posture": "standing", "holding": "Silver Bow", "composure": "composed"}
        garments = {
            ps.SLOT_TOP: {"state": ps.STATE_WORN, "item_name": "Ranger Tunic", "layer_depth": 2},
            ps.SLOT_BOTTOM: {"state": ps.STATE_WORN, "item_name": "Leather Trousers", "layer_depth": 2},
        }
        ps.upsert_actor_physical_state(self.session_id, "Lyra", actor_state, garments=garments)

        # Save adventure slot
        save_res = db.save_adventure_slot(self.user_id, slot_name="Checkpoint", overwrite=True)
        self.assertEqual(save_res["status"], "saved")

        # Load adventure slot into new active session
        load_res = db.load_adventure_slot(self.user_id, slot_name="Checkpoint")
        new_sess_id = load_res["id"]
        self.assertIsNotNone(new_sess_id)
        self.assertNotEqual(new_sess_id, self.session_id)

        cloned_actor = ps.get_actor_physical_state(new_sess_id, "Lyra")
        self.assertIsNotNone(cloned_actor)
        self.assertEqual(cloned_actor["holding"], "Silver Bow")

        cloned_garments = ps.get_actor_garments(new_sess_id, "lyra")
        self.assertTrue(len(cloned_garments) >= 2)
        top_g = next((g for g in cloned_garments if g["slot"] == ps.SLOT_TOP), None)
        self.assertIsNotNone(top_g)
        self.assertEqual(top_g["item_name"], "Ranger Tunic")

        # Cleanup new session
        with db.get_conn() as conn:
            conn.execute("DELETE FROM sessions WHERE id=?", (new_sess_id,))

    def test_10_posture_and_tether_restraint_linkages(self):
        """Invariant 8: Pinned/restrained postures link relative targets and flags."""
        actor_state = {
            "posture": "pinned",
            "posture_qualifier": "against wall",
            "relative_target": "orc_berserker",
            "relative_relation": "pinned_by",
            "tether_type": "restrained",
            "tether_partner": "heavy chains",
        }
        ps.upsert_actor_physical_state(self.session_id, "Thorne", actor_state)
        thorne = ps.get_actor_physical_state(self.session_id, "Thorne")
        self.assertEqual(thorne["posture"], "pinned")
        self.assertEqual(thorne["relative_target"], "orc_berserker")
        self.assertTrue(ps.is_actor_restrained(thorne))

    def test_11_anatomical_barrier_auto_displacement(self):
        """Invariant 9: Genital intimacy automatically shifts blocking worn bottom garments to displaced."""
        cloth = {
            ps.SLOT_TOP: "Clothed",
            ps.SLOT_BOTTOM: "Leather Pants",
            ps.SLOT_UNDER_TOP: "Bra",
            ps.SLOT_UNDER_BOTTOM: "Boxer Briefs",
        }
        # Oral intimacy act on genital area
        displaced_cloth = ps.enforce_anatomical_barriers_on_act(cloth, "perform oral cunnilingus on partner")
        self.assertIn("displaced", displaced_cloth[ps.SLOT_BOTTOM].lower())
        self.assertIn("displaced", displaced_cloth[ps.SLOT_UNDER_BOTTOM].lower())

    def test_12_room_ground_drop_and_departure_cleanup(self):
        """Invariant 11: Stripped clothes enter dropped_items during scene and clean up upon venue departure."""
        curr_state = {
            "actors": {
                "Aria": {
                    "clothing": {
                        "top": "Silk Blouse",
                        "bottom": "Leather Pants",
                        "under_bottom": "Linen Briefs",
                    }
                }
            },
            "dropped_items": [],
        }
        updates = {
            "actors": {
                "Aria": {
                    "clothing": {
                        "bottom": "Removed",
                        "under_bottom": "Removed",
                    }
                }
            }
        }
        merged = ps.merge_physical_state_updates(curr_state, updates)
        self.assertTrue(any("bottom" in it for it in merged["dropped_items"]))

        # Depart venue
        cleaned = ps.handle_location_transition(merged, party=[{"name": "Aria"}], session_id=self.session_id)
        self.assertEqual(cleaned["dropped_items"], [])

    def test_13_restraint_inhibition_and_companion_release(self):
        """Invariant 12: Restrained actors blocked from travel; freeing bindings unblocks them."""
        actor_state = {"tether_type": "restrained", "tether_partner": "iron shackles"}
        can_travel, reason = ps.can_actor_travel_or_dual_wield(actor_state)
        self.assertFalse(can_travel)
        self.assertIn("restrained", reason.lower())

        # Companion frees bindings
        actor_state["tether_type"] = "none"
        actor_state["tether_partner"] = ""
        can_travel_now, _ = ps.can_actor_travel_or_dual_wield(actor_state)
        self.assertTrue(can_travel_now)

    def test_14_climax_physical_consequences(self):
        """Invariant 13: Climax increments count, sets refractory, sets is_wet=1, and composure=exhausted."""
        curr_state = {
            "actors": {
                "player": {"posture": "Standing alert", "holding": "Empty hands", "climax_count": 0},
                "Elena": {"posture": "Kneeling beside you", "holding": "Empty hands", "climax_count": 0},
            },
            "intimate_contact": "partner reached climax together with you",
            "climax_state": {"player_climaxed": True, "partner_climaxed": True},
        }
        merged = ps.merge_physical_state_updates(curr_state, {"player_climaxed": True, "partner_climaxed": True})

        p_actor = merged["actors"]["player"]
        e_actor = merged["actors"]["Elena"]

        self.assertEqual(p_actor["climax_count"], 1)
        self.assertEqual(p_actor["in_refractory"], 1)
        self.assertEqual(p_actor["composure"], ps.COMPOSURE_EXHAUSTED)
        self.assertEqual(p_actor["is_wet"], 1)
        self.assertIn("Resting", p_actor["posture"])

        self.assertEqual(e_actor["climax_count"], 1)
        self.assertEqual(e_actor["in_refractory"], 1)
        self.assertEqual(e_actor["composure"], ps.COMPOSURE_EXHAUSTED)
        self.assertEqual(e_actor["is_wet"], 1)

    def test_15_write_through_prompt_block_materialization(self):
        """Invariant 7: LLM prompt blocks reflect normalized table updates without desync."""
        actor_state = {
            "posture": "leaning against archway",
            "holding": "Obsidian Dagger",
            "stance": "Ready",
            "composure": "composed",
        }
        garments = {
            ps.SLOT_TOP: {"state": ps.STATE_WORN, "item_name": "Velvet Doublet", "layer_depth": 2},
            ps.SLOT_BOTTOM: {"state": ps.STATE_WORN, "item_name": "Silk Hose", "layer_depth": 2},
            ps.SLOT_UNDER_TOP: {"state": ps.STATE_NONE, "item_name": "", "layer_depth": 1},
            ps.SLOT_UNDER_BOTTOM: {"state": ps.STATE_WORN, "item_name": "Linen Briefs", "layer_depth": 1},
            ps.SLOT_FOOTWEAR: {"state": ps.STATE_WORN, "item_name": "Boots", "layer_depth": 1},
        }
        ps.upsert_actor_physical_state(self.session_id, "Aria", actor_state, garments=garments)
        ps.materialize_session_physical_state(self.session_id)

        session_dict = db.get_session(self.session_id)
        party = [{"name": "Aria"}]
        prompt_block = ps.build_physical_prompt_block(session_dict, party)
        self.assertIn("Aria", prompt_block)
        self.assertIn("Obsidian Dagger", prompt_block)

    def test_16_player_actor_resolution_with_custom_char_name(self):
        """Invariant 13: Climax consequences reliably resolve custom character names like 'Aria'."""
        curr_state = {
            "actors": {
                "Aria": {"posture": "Standing alert", "holding": "Empty hands", "climax_count": 0},
                "Elena": {"posture": "Kneeling beside you", "holding": "Empty hands", "climax_count": 0},
            },
            "intimate_contact": "player reached climax in passionate embrace",
            "climax_state": {"player_climaxed": True, "partner_climaxed": False},
        }
        party = [{"name": "Aria"}]
        merged = ps.merge_physical_state_updates(
            curr_state,
            {"player_climaxed": True, "partner_climaxed": False},
            party=party,
            session_id=self.session_id
        )
        # Aria is player, Elena is partner
        aria = merged["actors"]["Aria"]
        elena = merged["actors"]["Elena"]
        self.assertEqual(aria["climax_count"], 1)
        self.assertEqual(aria["composure"], ps.COMPOSURE_EXHAUSTED)
        self.assertEqual(aria["is_wet"], 1)
        self.assertEqual(elena["climax_count"], 0)

    def test_17_public_indecency_witness_and_phone_gossip_integration(self):
        """Invariant 4: Public indecency generates in-game phone gossip feed post and stage direction."""
        from mechanics.system.phone.social_graph import evaluate_pre_turn_witness_detection
        session_row = {
            "id": self.session_id,
            "current_location": "Grand Academy Courtyard",
            "physical_state": {
                "actors": {
                    "Aria": {
                        "clothing": {
                            "top": "removed",
                            "bottom": "removed",
                            "under_top": "none",
                            "under_bottom": "removed",
                        }
                    }
                }
            },
            "current_npcs": [{"name": "Prefect Marcus"}],
        }
        actions = [{"label": "Look around nervously", "action": "look_around"}]
        res = evaluate_pre_turn_witness_detection(
            session=session_row,
            actions=actions,
            player_name="Aria",
            target_npc="Prefect Marcus",
            location_str="Grand Academy Courtyard"
        )
        self.assertTrue(res["witness_spotted"])
        self.assertIn("PUBLIC INDECENCY", res["directive"])
        self.assertEqual(res["event_kind"], "scandal")

        # Verify gossip feed in database has the post with #Scandal tag
        feed = db.get_gossip_feed(self.session_id)
        self.assertTrue(len(feed) > 0)
        self.assertEqual(feed[0]["tag"], "#Scandal")
        self.assertIn("Aria", feed[0]["content"])

    def test_18_restraint_travel_filtering_and_choice_generation(self):
        """Invariant 12: Restrained actor choices filter out travel and offer struggle/companion help."""
        from mechanics.world.waypoints.choices import tag_and_enrich_quest_choices

        phys_st = {
            "actors": {
                "Aria": {
                    "posture": "pinned to wall",
                    "tether_type": "restrained",
                    "tether_partner": "iron chains",
                    "clothing": {"top": "Clothed", "bottom": "Clothed"},
                }
            }
        }
        db.update_session_physical_state(self.session_id, phys_st)

        raw_choices = [
            {"label": "Travel to the City Gate", "action": "travel"},
            {"label": "Walk to the Harbor Market", "action": "walk to harbor market"},
            {"label": "Speak with the guard", "action": "speak"},
        ]
        enriched = tag_and_enrich_quest_choices(
            raw_choices,
            session_id=self.session_id,
            current_location="Dungeon Cell",
            char={"name": "Aria"},
            current_npcs=[{"name": "Elena"}]
        )
        # Travel actions must be suppressed
        labels = [c.get("label", "") for c in enriched if isinstance(c, dict)]
        self.assertFalse(any("travel to" in l.lower() for l in labels))
        self.assertFalse(any("walk to" in l.lower() for l in labels))
        # Struggle and companion help must be prepended
        self.assertTrue(any("struggle" in l.lower() or "break" in l.lower() for l in labels))
        self.assertTrue(any("companion" in l.lower() or "help" in l.lower() for l in labels))

    def test_19_companion_freeing_bonds_reducer(self):
        """Invariant 12: Companion action cutting bonds clears tether, tether_type, and tether_partner."""
        from game_engine.state.reducers import _reduce_physical_state_and_memories

        phys_st = {
            "actors": {
                "Aria": {
                    "posture": "tied up",
                    "tether": "Bound in rope",
                    "tether_type": "restrained",
                    "tether_partner": "rope",
                }
            }
        }
        db.update_session_physical_state(self.session_id, phys_st)
        session_row = db.get_session(self.session_id)
        party = [{"id": 1, "user_id": self.user_id, "name": "Aria", "hp": 100, "max_hp": 100}]

        outcome = {
            "outcome_narrative": "Elena quickly slices through your rope bindings.",
            "next_narrative": "You are free.",
            "location": "Dungeon Cell",
            "physical_updates": {},
        }
        actions = [{"label": "Elena, cut my bonds!", "action": "companion cut bonds"}]

        _reduce_physical_state_and_memories(
            session_id=self.session_id,
            session=session_row,
            outcome=outcome,
            party=party,
            scen_key="fantasy",
            actions=actions,
        )

        updated = ps.get_actor_physical_state(self.session_id, "Aria")
        self.assertEqual(updated.get("tether_type"), "none")
        self.assertEqual(updated.get("tether_partner"), "")

    def test_20_aftercare_redressing_choice_injection(self):
        """Invariant 2: In aftercare, tag_and_enrich_quest_choices injects [Get Dressed] choice."""
        from mechanics.world.waypoints.choices import tag_and_enrich_quest_choices

        phys_st = {
            "actors": {
                "Aria": {
                    "posture": "Resting on bed",
                    "clothing": {
                        "top": "Removed",
                        "bottom": "Disheveled",
                        "under_top": "Removed",
                        "under_bottom": "Worn",
                    },
                }
            },
            "intimate_contact": "Tender aftercare cuddling",
        }
        db.update_session_physical_state(self.session_id, phys_st)

        raw_choices = [
            {"label": "Rest a little longer against their chest", "action": "cuddle"},
            {"label": "Whisper softly to them", "action": "whisper"},
        ]
        enriched = tag_and_enrich_quest_choices(
            raw_choices,
            session_id=self.session_id,
            current_location="Private Bedroom",
            char={"name": "Aria"},
        )
        labels = [c.get("label", "") for c in enriched if isinstance(c, dict)]
        self.assertTrue(any("get dressed" in l.lower() or "redress" in l.lower() for l in labels))

    def test_21_two_way_inventory_equipment_loadout_sync(self):
        """Invariant 5: Equipping/unequipping weapons and armor writes through to actor physical state and garments."""
        from db.inventory import equip_item, unequip_slot

        # Initialize character with active session
        db.update_character_fields(self.user_id, active_session_id=self.session_id)
        # Give character sword, shield, plate armor, and boots
        from db.core import get_conn
        with get_conn() as conn:
            conn.execute(
                "INSERT INTO inventory (character_id, user_id, name, item_type, slot_cost, equipped) VALUES (?, ?, ?, ?, ?, ?)",
                (self.user_id, self.user_id, "Silver Longsword", "Weapon", 1, 0)
            )
            w_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]

            conn.execute(
                "INSERT INTO inventory (character_id, user_id, name, item_type, slot_cost, equipped) VALUES (?, ?, ?, ?, ?, ?)",
                (self.user_id, self.user_id, "Dragon Crest Shield", "Shield", 1, 0)
            )
            s_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]

            conn.execute(
                "INSERT INTO inventory (character_id, user_id, name, item_type, slot_cost, equipped) VALUES (?, ?, ?, ?, ?, ?)",
                (self.user_id, self.user_id, "Steel Full Plate", "Armor", 2, 0)
            )
            a_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]

            conn.execute(
                "INSERT INTO inventory (character_id, user_id, name, item_type, slot_cost, equipped) VALUES (?, ?, ?, ?, ?, ?)",
                (self.user_id, self.user_id, "Riding Boots", "Shoes", 1, 0)
            )
            b_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]

        # Equip weapon and shield
        equip_item(self.user_id, w_id, "Weapon")
        equip_item(self.user_id, s_id, "Shield")

        # Equip armor and boots
        equip_item(self.user_id, a_id, "Armor")
        equip_item(self.user_id, b_id, "Shoes")

        # Verify active session physical state was synchronized
        sess_phys = db.get_session_physical_state(self.session_id)
        actors = sess_phys.get("actors", {})
        self.assertIn("Aria", actors)
        aria = actors["Aria"]
        self.assertEqual(aria["holding"], "Silver Longsword & Dragon Crest Shield")
        self.assertEqual(aria["clothing"]["outerwear"], "Steel Full Plate")
        self.assertEqual(aria["clothing"]["footwear"], "Riding Boots")

        # Unequip weapon
        unequip_slot(self.user_id, "Weapon")
        sess_phys = db.get_session_physical_state(self.session_id)
        self.assertEqual(sess_phys["actors"]["Aria"]["holding"], "Dragon Crest Shield")

        # Unequip shield -> empty hands
        unequip_slot(self.user_id, "Shield")
        sess_phys = db.get_session_physical_state(self.session_id)
        self.assertEqual(sess_phys["actors"]["Aria"]["holding"], "Empty hands")

    def test_22_full_6_slot_environmental_prompt_block(self):
        """Invariant 3 & 7: LLM prompt blocks include Outerwear, Footwear, Composure, Wet, and Bloodied."""
        phys_st = {
            "actors": {
                "Aria": {
                    "posture": "Standing alert",
                    "holding": "Silver Longsword",
                    "composure": ps.COMPOSURE_FLUSTERED,
                    "is_wet": True,
                    "is_bloodied": True,
                    "clothing": {
                        "outerwear": "worn (Crimson Cloak)",
                        "top": "Silk Blouse",
                        "bottom": "Leather Trousers",
                        "under_top": "Lace Bra",
                        "under_bottom": "Silk Panties",
                        "footwear": "worn (Knee-high Boots)",
                    },
                }
            },
            "props": {},
            "intimate_contact": "none",
        }
        db.update_session_physical_state(self.session_id, phys_st)
        sess = db.get_session(self.session_id)
        prompt = ps.build_physical_prompt_block(sess, [{"name": "Aria"}], is_combat=False, is_nsfw=False)

        self.assertIn("Outerwear: worn (Crimson Cloak)", prompt)
        self.assertIn("Footwear: worn (Knee-high Boots)", prompt)
        self.assertIn("[Composure: flustered]", prompt)
        self.assertIn("[Wet]", prompt)
        self.assertIn("[Bloodied]", prompt)

    def test_23_bidirectional_lazy_hydration_sessions_db(self):
        """Invariant 6: Bi-directional hydration between physical_state_json and relational tables."""
        from db.core import get_conn

        # 1. physical_state_json is empty, but relational tables have rows
        with get_conn() as conn:
            conn.execute("UPDATE sessions SET physical_state_json=NULL WHERE id=?", (self.session_id,))
            conn.execute("DELETE FROM actor_physical_states WHERE session_id=?", (self.session_id,))
            conn.execute("DELETE FROM actor_garments WHERE session_id=?", (self.session_id,))

        ps.upsert_actor_physical_state(
            self.session_id,
            "Elena",
            {"posture": "Sitting gracefully", "holding": "Tea Cup", "composure": ps.COMPOSURE_COMPOSED},
            garments={ps.SLOT_TOP: "Silk Gown", ps.SLOT_BOTTOM: "none"}
        )

        hydrated = db.get_session_physical_state(self.session_id)
        self.assertIn("Elena", hydrated.get("actors", {}))
        self.assertEqual(hydrated["actors"]["Elena"]["holding"], "Tea Cup")

        # 2. Clean-cutover Migration 30 migrates legacy physical_state_json actors into relational tables and strips actors from sessions
        from db.core import _migrate_clean_cutover_v30
        with get_conn() as conn:
            conn.execute("DELETE FROM actor_physical_states WHERE session_id=?", (self.session_id,))
            conn.execute("DELETE FROM actor_garments WHERE session_id=?", (self.session_id,))
            legacy_data = {
                "actors": {
                    "Marcus": {"posture": "Standing guard", "holding": "Halberd", "clothing": {"top": "Chainmail", "bottom": "Breeches"}}
                },
                "props": {"Banner": "Hanging on wall"},
            }
            conn.execute("UPDATE sessions SET physical_state_json=? WHERE id=?", (json.dumps(legacy_data), self.session_id))
            _migrate_clean_cutover_v30(conn)

        retrieved = db.get_session_physical_state(self.session_id)
        self.assertIn("Marcus", retrieved.get("actors", {}))
        self.assertEqual(retrieved.get("props", {}).get("Banner"), "Hanging on wall")

        # Verify relational tables were migrated
        all_actors = ps.get_all_actor_physical_states(self.session_id)
        self.assertTrue(any(a["actor_name"] == "Marcus" for a in all_actors))

    def test_24_multi_npc_targeted_climax_isolation(self):
        """Invariant 13: Climax consequences target only the intimate partner in multi-NPC scenes."""
        curr_state = {
            "actors": {
                "Aria": {"posture": "Standing alert", "holding": "Empty hands", "climax_count": 0},
                "Elena": {"posture": "Embracing partner", "holding": "Empty hands", "climax_count": 0},
                "Bartender": {"posture": "Wiping glasses behind counter", "holding": "Cloth", "climax_count": 0},
                "Guard": {"posture": "Standing near entrance", "holding": "Spear", "climax_count": 0},
            },
            "intimate_contact": "partner reached climax with Elena",
            "climax_state": {"player_climaxed": False, "partner_climaxed": True},
        }
        party = [{"name": "Aria"}]
        merged = ps.merge_physical_state_updates(
            curr_state,
            {"partner_climaxed": True},
            party=party,
            session_id=self.session_id
        )

        # Elena climaxed and is exhausted
        self.assertEqual(merged["actors"]["Elena"]["climax_count"], 1)
        self.assertEqual(merged["actors"]["Elena"]["composure"], ps.COMPOSURE_EXHAUSTED)

        # Bystanders Bartender and Guard are unaffected
        self.assertEqual(merged["actors"]["Bartender"]["climax_count"], 0)
        self.assertEqual(merged["actors"]["Guard"]["climax_count"], 0)
        self.assertEqual(merged["actors"]["Bartender"]["holding"], "Cloth")

    def test_25_sync_state_dict_prunes_departed_npcs(self):
        """Invariant 15: sync_state_dict_to_db prunes departed NPCs so they do not resurrect in later scenes."""
        # Scene 1: Party + NPC
        scene1 = {
            "actors": {
                "Aria": {"posture": "Standing", "holding": "Dagger"},
                "TemporaryMerchant": {"posture": "Sitting", "holding": "Ledger"},
            }
        }
        ps.sync_state_dict_to_db(self.session_id, scene1)
        all_actors = ps.get_all_actor_physical_states(self.session_id)
        self.assertEqual(len(all_actors), 2)

        # Scene 2: Party transitions room, Merchant departs
        scene2 = {
            "actors": {
                "Aria": {"posture": "Standing", "holding": "Dagger"},
            }
        }
        ps.sync_state_dict_to_db(self.session_id, scene2)
        all_actors_after = ps.get_all_actor_physical_states(self.session_id)
        self.assertEqual(len(all_actors_after), 1)
        self.assertEqual(all_actors_after[0]["actor_name"], "Aria")


if __name__ == "__main__":
    unittest.main()
