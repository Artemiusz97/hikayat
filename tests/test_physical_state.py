"""
Unit tests for the Internal Micro-Spatial, Posture, Clothing, and Prop Continuity Engine.
"""
import unittest
import db
import game_engine
from mechanics.social.physical_state import (
    init_default_physical_state,
    build_physical_prompt_block,
    merge_physical_state_updates,
    handle_location_transition,
)


class TestPhysicalStateEngine(unittest.TestCase):

    def setUp(self):
        db.init_db()
        self.session_id = 999888
        with db.get_conn() as conn:
            conn.execute("INSERT OR REPLACE INTO sessions (id, host_user_id, status, mode, capacity) VALUES (?, 12345, 'active', 'single', 1)", (self.session_id,))
        self.party = [
            (
                {
                    "id": 1,
                    "user_id": 12345,
                    "name": "Artemiusz",
                    "hp": 20,
                    "max_hp": 20,
                    "mp": 10,
                    "max_mp": 10,
                    "stats": {"STR": 5, "AGI": 5, "END": 5, "INT": 5, "PER": 5, "CHA": 5, "LUK": 5},
                },
                [{"name": "Steel Longsword", "slot": "Weapon"}]
            )
        ]

    def test_init_default_physical_state(self):
        opening = {
            "npcs_present": [{"name": "Skye Anderson"}],
            "props": [{"name": "Mahogany Desk", "state": "Present"}]
        }
        state = init_default_physical_state(self.session_id, self.party, "fantasy", opening_scene=opening)
        
        self.assertIn("Artemiusz", state["actors"])
        self.assertIn("Skye Anderson", state["actors"])
        self.assertEqual(state["actors"]["Artemiusz"]["holding"], "Steel Longsword")
        self.assertEqual(state["actors"]["Artemiusz"]["clothing"]["top"], "Clothed")
        self.assertEqual(state["actors"]["Skye Anderson"]["clothing"]["bottom"], "Clothed")
        self.assertIn("Mahogany Desk", state["props"])

    def test_merge_physical_state_updates_clothing(self):
        initial_state = {
            "actors": {
                "Skye Anderson": {
                    "posture": "Sitting on chair",
                    "holding": "Cup of tea",
                    "clothing": {"top": "Clothed", "bottom": "Clothed", "under_top": "Worn", "under_bottom": "Worn"}
                }
            },
            "props": {"Mahogany Desk": "Present"},
            "intimate_contact": "none"
        }

        # Skye unbuttons top and sets down tea
        updates = {
            "actors": {
                "Skye Anderson": {
                    "posture": "Leaning back on couch",
                    "holding": "Empty hands",
                    "clothing": {"top": "Blouse removed", "under_top": "Bra unhooked"}
                }
            },
            "props": [{"name": "Mahogany Desk", "state": "Cup resting on surface"}],
            "intimate_contact": "Passionate kissing on couch"
        }

        merged = merge_physical_state_updates(initial_state, updates)
        skye = merged["actors"]["Skye Anderson"]
        self.assertEqual(skye["posture"], "Leaning back on couch")
        self.assertEqual(skye["holding"], "Empty hands")
        self.assertEqual(skye["clothing"]["top"], "Blouse removed")
        self.assertEqual(skye["clothing"]["under_top"], "Bra unhooked")
        self.assertEqual(skye["clothing"]["bottom"], "Clothed")  # Bottom remains clothed
        self.assertEqual(merged["props"]["Mahogany Desk"], "Cup resting on surface")
        self.assertEqual(merged["intimate_contact"], "Passionate kissing on couch")

    def test_build_physical_prompt_block_modes(self):
        session = {
            "id": self.session_id,
            "scenario": "fantasy",
            "physical_state": {
                "actors": {
                    "Artemiusz": {
                        "posture": "Kneeling",
                        "holding": "Steel Longsword",
                        "clothing": {"top": "Shirt off", "bottom": "Pants on", "under_top": "Worn", "under_bottom": "Worn"},
                        "stance": "Guarded"
                    }
                },
                "props": {"Stone Altar": "Glowing"},
                "intimate_contact": "Foreplay on altar"
            }
        }

        # 1. Social/Exploration mode
        social_prompt = build_physical_prompt_block(session, self.party, is_combat=False, is_nsfw=False)
        self.assertIn("PHYSICAL SCENE & MICRO-STATE", social_prompt)
        self.assertIn("Artemiusz", social_prompt)
        self.assertIn("Stone Altar", social_prompt)

        # 2. Sensual/NSFW mode
        nsfw_prompt = build_physical_prompt_block(session, self.party, is_combat=False, is_nsfw=True)
        self.assertIn("INTIMATE & PHYSICAL STATE", nsfw_prompt)
        self.assertIn("Shirt off", nsfw_prompt)
        self.assertIn("Foreplay on altar", nsfw_prompt)

        # 3. Tactical combat mode
        combat_prompt = build_physical_prompt_block(session, self.party, is_combat=True, is_nsfw=False)
        self.assertIn("TACTICAL COMBAT STANCES", combat_prompt)
        self.assertIn("Guarded", combat_prompt)
        self.assertIn("Steel Longsword", combat_prompt)

    def test_location_transition_purges_room_props(self):
        state = {
            "actors": {
                "Artemiusz": {
                    "posture": "Seated on leather armchair",
                    "holding": "Tome",
                    "clothing": {"top": "Clothed", "bottom": "Clothed"}
                }
            },
            "props": {"Mahogany Desk": "Open", "Armchair": "Present"},
            "intimate_contact": "none"
        }

        transitioned = handle_location_transition(state)
        # Room props are purged
        self.assertEqual(transitioned["props"], {})
        # Actor posture is reset from chair to standing in new area
        self.assertIn("Standing", transitioned["actors"]["Artemiusz"]["posture"])
        # Personal holding and clothing are preserved
        self.assertEqual(transitioned["actors"]["Artemiusz"]["holding"], "Tome")
        self.assertEqual(transitioned["actors"]["Artemiusz"]["clothing"]["top"], "Clothed")

    def test_unarmed_character_holding_empty_hands(self):
        """Verify unarmed characters default to 'Empty hands' rather than 'Weapon'."""
        unarmed_party = [
            (
                {
                    "id": 2,
                    "user_id": 12346,
                    "name": "Alex",
                    "gender": "male"
                },
                []  # Empty inventory
            )
        ]
        state = init_default_physical_state(self.session_id, unarmed_party, "high_school_drama")
        self.assertEqual(state["actors"]["Alex"]["holding"], "Empty hands")

    def test_pydantic_turn_outcome_microspatial_roundtrip(self):
        """Verify TurnOutcome Pydantic model preserves descriptive postures, clothing, and undergarments."""
        from models.llm_schemas import TurnOutcome
        raw_payload = {
            "scene_title": "Classroom Confrontation",
            "outcome_narrative": "A dramatic moment occurs.",
            "physical_updates": {
                "actors": {
                    "Skye Anderson": {
                        "posture": "Leaning back on couch",
                        "holding": "Empty hands",
                        "clothing": {
                            "top": "Blouse removed",
                            "bottom": "Clothed",
                            "under_top": "Bra unhooked",
                            "under_bottom": "None (Commando)"
                        },
                        "stance": "Relaxed"
                    }
                },
                "props": [{"name": "Mahogany Desk", "state": "Cup resting on surface"}],
                "intimate_contact": "Passionate kissing on couch"
            }
        }
        outcome = TurnOutcome.model_validate(raw_payload)
        dumped = outcome.model_dump()
        phys = dumped["physical_updates"]
        skye = phys["actors"]["Skye Anderson"]
        self.assertEqual(skye["posture"], "Leaning back on couch")
        self.assertEqual(skye["clothing"]["top"], "Blouse removed")
        self.assertEqual(skye["clothing"]["under_top"], "Bra unhooked")
        self.assertEqual(skye["clothing"]["under_bottom"], "None (Commando)")
        self.assertEqual(skye["stance"], "Relaxed")
        self.assertEqual(phys["props"][0]["name"], "Mahogany Desk")

    def test_merge_pydantic_physical_update_model(self):
        """Verify merge_physical_state_updates correctly processes Pydantic PhysicalUpdate model instances."""
        from models.llm_schemas import PhysicalUpdate
        initial_state = {
            "actors": {
                "Artemiusz": {
                    "posture": "Standing alert",
                    "holding": "Steel Longsword",
                    "clothing": {"top": "Clothed", "bottom": "Clothed", "under_top": "Worn", "under_bottom": "Worn"},
                    "stance": "Ready"
                }
            },
            "props": {},
            "intimate_contact": "none"
        }
        model_update = PhysicalUpdate.model_validate({
            "actors": {
                "Artemiusz": {
                    "posture": "Kneeling before altar",
                    "holding": "Shield",
                    "stance": "Guarded"
                }
            },
            "props": [{"name": "Stone Altar", "state": "Glowing runes"}]
        })
        merged = merge_physical_state_updates(initial_state, model_update)
        art = merged["actors"]["Artemiusz"]
        self.assertEqual(art["posture"], "Kneeling before altar")
        self.assertEqual(art["holding"], "Shield")
        self.assertEqual(art["stance"], "Guarded")
        self.assertEqual(merged["props"]["Stone Altar"], "Glowing runes")

    def test_reducer_lifecycle_location_transition_and_departures(self):
        """Verify _reduce_physical_state_and_memories purges old props before applying new ones, and prunes departed NPCs."""
        from game_engine.state.reducers import _reduce_physical_state_and_memories

        # Seed initial session physical state with old room props and an NPC who will depart
        initial_state = {
            "actors": {
                "Artemiusz": {
                    "posture": "Seated at desk",
                    "holding": "Quill",
                    "clothing": {"top": "Clothed", "bottom": "Clothed", "under_top": "Worn", "under_bottom": "Worn"},
                    "stance": "Neutral"
                },
                "Departing NPC": {
                    "posture": "Standing near doorway",
                    "holding": "Empty hands",
                    "clothing": {"top": "Clothed", "bottom": "Clothed", "under_top": "Worn", "under_bottom": "Worn"},
                    "stance": "Neutral"
                }
            },
            "props": {"Old Classroom Desk": "Present"},
            "intimate_contact": "none"
        }
        db.update_session_physical_state(self.session_id, initial_state)

        session = {
            "id": self.session_id,
            "current_location": "Westlake Academy ➔ Classroom 1-A",
            "scenario": "fantasy"
        }
        turn_outcome = {
            "location": "Westlake Academy ➔ Library ➔ Archive Stacks",  # Location changed!
            "physical_updates": {
                "actors": {
                    "Artemiusz": {
                        "posture": "Examining tome at reading desk",
                        "holding": "Ancient Tome"
                    }
                },
                "props": [{"name": "Reading Desk", "state": "Lit by candle"}]
            },
            "npc_departures": ["Departing NPC"],
            "npcs_present": [{"name": "Librarian Clara", "gender": "female"}]
        }

        _reduce_physical_state_and_memories(
            self.session_id, session, turn_outcome, self.party, "fantasy", actions=[]
        )

        persisted = db.get_session_physical_state(self.session_id)
        # Old Classroom Desk should be gone, but new Reading Desk should be preserved!
        self.assertNotIn("Old Classroom Desk", persisted["props"])
        self.assertIn("Reading Desk", persisted["props"])
        self.assertEqual(persisted["props"]["Reading Desk"], "Lit by candle")

        # Departing NPC should be removed from actors
        self.assertNotIn("Departing NPC", persisted["actors"])

        # Newly arrived NPC should have baseline physical grounding
        self.assertIn("Librarian Clara", persisted["actors"])
        self.assertEqual(persisted["actors"]["Librarian Clara"]["posture"], "Standing nearby")

        # Player character's new posture and holding in the destination room should be preserved!
        self.assertEqual(persisted["actors"]["Artemiusz"]["posture"], "Examining tome at reading desk")
        self.assertEqual(persisted["actors"]["Artemiusz"]["holding"], "Ancient Tome")

    def test_combat_focus_and_intimate_contact_mutual_exclusion(self):
        """Verify combat initiation purges intimate_contact, and combat exit purges combat_focus."""
        from game_engine.state.reducers import _reduce_physical_state_and_memories

        # Scenario 1: Ambush during intimacy -> intimate contact reset to 'none'
        initial_state = {
            "actors": {"Artemiusz": {"posture": "Embracing", "holding": "Empty hands"}},
            "props": {},
            "intimate_contact": "Kissing passionately",
            "combat_focus": "none"
        }
        db.update_session_physical_state(self.session_id, initial_state)

        session = {"id": self.session_id, "current_location": "Tavern", "scenario": "fantasy"}
        combat_outcome = {
            "outcome_narrative": "Goblins kick down the door!",
            "_combat_log": "Goblin strikes for 5 damage!",
            "physical_updates": {"combat_focus": "Defending against Goblin Spearman"}
        }
        _reduce_physical_state_and_memories(self.session_id, session, combat_outcome, self.party, "fantasy", [])
        persisted = db.get_session_physical_state(self.session_id)
        self.assertEqual(persisted["intimate_contact"], "none")
        self.assertEqual(persisted["combat_focus"], "Defending against Goblin Spearman")

        # Scenario 2: Combat concludes -> combat_focus reset to 'none'
        peace_outcome = {
            "outcome_narrative": "The goblins are defeated and flee into the dark.",
            "physical_updates": {}
        }
        _reduce_physical_state_and_memories(self.session_id, session, peace_outcome, self.party, "fantasy", [])
        persisted_peace = db.get_session_physical_state(self.session_id)
        self.assertEqual(persisted_peace["combat_focus"], "none")

    def test_milestone_event_infers_intimate_contact(self):
        """Verify relationship milestone events automatically populate intimate_contact if omitted by LLM."""
        from game_engine.state.reducers import _reduce_physical_state_and_memories

        initial_state = {
            "actors": {"Artemiusz": {"posture": "Sitting", "holding": "Empty hands"}},
            "props": {},
            "intimate_contact": "none",
            "combat_focus": "none"
        }
        db.update_session_physical_state(self.session_id, initial_state)

        session = {"id": self.session_id, "current_location": "Rooftop Garden", "scenario": "high_school_drama"}
        milestone_outcome = {
            "outcome_narrative": "Under the starry sky, they share a tender, unforgettable kiss.",
            "relationship_updates": [
                {
                    "npc_name": "Maya Anderson",
                    "milestone_event": "first_kiss",
                    "delta_score": 8
                }
            ],
            "physical_updates": {}  # LLM omitted intimate_contact
        }
        _reduce_physical_state_and_memories(self.session_id, session, milestone_outcome, self.party, "high_school_drama", [])
        persisted = db.get_session_physical_state(self.session_id)
        self.assertIn("Kissing / embrace with Maya Anderson", persisted["intimate_contact"])

    def test_downed_character_vitals_synchronization(self):
        """Verify character with 0 HP is synchronized to Prone / Incapacitated posture in physical anchor."""
        from game_engine.state.reducers import _reduce_physical_state_and_memories

        # Create character in DB with 0 HP
        user_id = 888777
        char_name = "FallenHero"
        db.create_character(user_id, char_name, "Warrior", gender="male", scenario="fantasy")
        db.apply_hp_mp_delta(user_id, -999, 0, 0)  # Drop HP to 0
        dead_party = [({"id": 99, "user_id": user_id, "name": char_name}, [])]

        initial_state = {
            "actors": {char_name: {"posture": "Standing alert", "holding": "Broadsword", "stance": "Ready"}},
            "props": {},
            "intimate_contact": "none",
            "combat_focus": "none"
        }
        db.update_session_physical_state(self.session_id, initial_state)

        session = {"id": self.session_id, "current_location": "Dungeon", "scenario": "fantasy"}
        turn_outcome = {"outcome_narrative": "The hero collapses from mortal wounds.", "physical_updates": {}}
        _reduce_physical_state_and_memories(self.session_id, session, turn_outcome, dead_party, "fantasy", [])

        persisted = db.get_session_physical_state(self.session_id)
        hero_phys = persisted["actors"][char_name]
        self.assertIn("Prone / Downed (Unconscious)", hero_phys["posture"])
        self.assertEqual(hero_phys["holding"], "Dropped / Empty hands")
        self.assertEqual(hero_phys["stance"], "Incapacitated")

    def test_dual_wield_and_shield_combat_synchronization(self):
        """Verify main-hand + off-hand shield or dual-wield weapon synchronization in combat anchor."""
        from mechanics.social.physical_state import build_physical_prompt_block

        dual_party = [({
            "name": "Duelist",
            "gender": "female",
            "scenario": "fantasy"
        }, [
            {"slot": "Weapon", "name": "Main Katana"},
            {"slot": "Shield", "name": "Offhand Wakizashi"}
        ])]
        session = {"id": self.session_id, "scenario": "fantasy"}
        anchor = build_physical_prompt_block(session, dual_party, is_combat=True)
        self.assertIn("Main Katana & Offhand Wakizashi", anchor)

        # Also verify weapon & shield
        session_id_2 = self.session_id + 999
        with db.get_conn() as conn:
            conn.execute("INSERT OR REPLACE INTO sessions (id, host_user_id, status, mode, capacity) VALUES (?, 12345, 'active', 'single', 1)", (session_id_2,))
        shield_party = [({
            "name": "Paladin",
            "gender": "male",
            "scenario": "fantasy"
        }, [
            {"slot": "Weapon", "name": "Holy Avenger"},
            {"slot": "Shield", "name": "Tower Shield"}
        ])]
        shield_anchor = build_physical_prompt_block({"id": session_id_2, "scenario": "fantasy"}, shield_party, is_combat=True)
        self.assertIn("Holy Avenger & Tower Shield", shield_anchor)

    def test_undergarments_non_existence_guard(self):
        """Verify characters going commando or bra-less cannot have non-existent undergarments unhooked/removed."""
        from mechanics.social.physical_state import merge_physical_state_updates

        initial = {
            "actors": {
                "Elena": {
                    "posture": "Lying back",
                    "holding": "Empty hands",
                    "clothing": {
                        "top": "Silk Blouse",
                        "bottom": "Pleated Skirt",
                        "under_top": "None (Bra-less)",
                        "under_bottom": "None (Commando)"
                    }
                }
            },
            "props": {},
            "intimate_contact": "none"
        }
        # LLM hallucinates removing bra and panties
        hallucinated_update = {
            "actors": {
                "Elena": {
                    "clothing": {
                        "top": "Removed",
                        "bottom": "Removed",
                        "under_top": "Bra unhooked and removed",
                        "under_bottom": "Panties pulled down and stripped"
                    }
                }
            }
        }
        merged = merge_physical_state_updates(initial, hallucinated_update)
        elena_cloth = merged["actors"]["Elena"]["clothing"]
        self.assertEqual(elena_cloth["top"], "Removed")
        self.assertEqual(elena_cloth["bottom"], "Removed")
        # Non-existent undergarments must remain strictly None
        self.assertEqual(elena_cloth["under_top"], "None (Bra-less)")
        self.assertEqual(elena_cloth["under_bottom"], "None (Commando)")

    def test_traveling_companion_preservation_across_locations(self):
        """Verify traveling companions retain garments and personal items while room props reset."""
        from game_engine.state.reducers import _reduce_physical_state_and_memories

        party = [({"id": 1, "user_id": 12345, "name": "Protagonist"}, [])]
        initial_state = {
            "actors": {
                "Protagonist": {
                    "posture": "Sitting on sofa",
                    "holding": "Tavern Mug",
                    "clothing": {"top": "Jacket", "bottom": "Jeans", "under_top": "Worn", "under_bottom": "Worn"}
                },
                "Alice": {
                    "posture": "Sitting on chair",
                    "holding": "Tavern Mug",
                    "clothing": {"top": "Silk Blouse", "bottom": "Skirt", "under_top": "Lace Bra", "under_bottom": "Silk Panties"}
                },
                "RandomPatron": {
                    "posture": "Standing by bar",
                    "holding": "Beer",
                    "clothing": {"top": "Clothed", "bottom": "Clothed", "under_top": "Worn", "under_bottom": "Worn"}
                }
            },
            "props": {"Tavern Mug": "Present", "Oak Bar": "Present"},
            "intimate_contact": "none"
        }
        db.update_session_physical_state(self.session_id, initial_state)

        session = {
            "id": self.session_id,
            "current_location": "Tavern Interior",
            "dialogue_partner": "Alice",
            "scenario": "fantasy"
        }
        turn_outcome = {
            "location": "Town Square",
            "npcs_present": [{"name": "Alice"}],
            "outcome_narrative": "Protagonist and Alice step out into the bustling Town Square.",
            "physical_updates": {}
        }
        _reduce_physical_state_and_memories(self.session_id, session, turn_outcome, party, "fantasy", [])

        persisted = db.get_session_physical_state(self.session_id)
        actors = persisted["actors"]

        # Alice and Protagonist should be retained, RandomPatron should be purged
        self.assertIn("Protagonist", actors)
        self.assertIn("Alice", actors)
        self.assertNotIn("RandomPatron", actors)

        # Alice's clothing and underwear must be preserved exactly
        self.assertEqual(actors["Alice"]["clothing"]["top"], "Silk Blouse")
        self.assertEqual(actors["Alice"]["clothing"]["under_top"], "Lace Bra")

        # Furniture posture should have transitioned to arriving in new area
        self.assertIn("arriving in new area", actors["Alice"]["posture"])

        # Holding the tavern room prop (Tavern Mug) should be cleared to Empty hands
        self.assertEqual(actors["Alice"]["holding"], "Empty hands")
        self.assertEqual(actors["Protagonist"]["holding"], "Empty hands")

        # Old tavern props must be purged
        self.assertNotIn("Oak Bar", persisted["props"])

    def test_opening_scene_with_physical_updates(self):
        """Verify OpeningScene with physical_updates initializes custom postures and interactive props."""
        from mechanics.social.physical_state import init_default_physical_state
        from models.llm_schemas import OpeningScene

        party = [({"id": 1, "user_id": 12345, "name": "Vanguard"}, [
            {"slot": "Weapon", "name": "Warhammer"},
            {"slot": "Shield", "name": "Kite Shield"},
            {"slot": "Top", "name": "Steel Cuirass"},
            {"slot": "Bottom", "name": "Iron Greaves"}
        ])]
        opening_data = {
            "scene_title": "Crisis at Breach",
            "narrative": "Explosions shake the trench.",
            "npcs_present": [{"name": "Medic"}],
            "props": [{"name": "Sandbag Barricade", "state": "Intact"}],
            "physical_updates": {
                "actors": {
                    "Vanguard": {"posture": "Bracing behind barricade", "stance": "Defensive"}
                },
                "props": [{"name": "Smoke Screen", "state": "Thick"}]
            }
        }
        opening_model = OpeningScene.model_validate(opening_data)
        state = init_default_physical_state(self.session_id, party, "fantasy", opening_scene=opening_model)

        # Warhammer & Kite Shield initialized
        self.assertEqual(state["actors"]["Vanguard"]["clothing"]["top"], "Steel Cuirass")
        self.assertEqual(state["actors"]["Vanguard"]["clothing"]["bottom"], "Iron Greaves")
        # Custom opening posture merged
        self.assertEqual(state["actors"]["Vanguard"]["posture"], "Bracing behind barricade")
        self.assertEqual(state["actors"]["Vanguard"]["stance"], "Defensive")
        # Both initial and physical update props present
        self.assertIn("Sandbag Barricade", state["props"])
        self.assertIn("Smoke Screen", state["props"])

    def test_partial_actor_and_clothing_update_preserves_untouched_state(self):
        """Verify delta updates only touching holding or top do not wipe posture, stance, or other garments."""
        from models.llm_schemas import PhysicalUpdate
        from mechanics.social.physical_state import merge_physical_state_updates

        initial = {
            "actors": {
                "Alice": {
                    "posture": "Sitting on sofa",
                    "holding": "Book",
                    "stance": "Relaxed",
                    "clothing": {
                        "top": "Silk Blouse",
                        "bottom": "Pleated Skirt",
                        "under_top": "Lace Bra",
                        "under_bottom": "Silk Panties"
                    }
                }
            },
            "props": {},
            "intimate_contact": "none"
        }
        # 1. Update only holding
        update1 = PhysicalUpdate.model_validate({"actors": {"Alice": {"holding": "Cup of tea"}}})
        merged1 = merge_physical_state_updates(initial, update1)
        self.assertEqual(merged1["actors"]["Alice"]["holding"], "Cup of tea")
        self.assertEqual(merged1["actors"]["Alice"]["posture"], "Sitting on sofa")
        self.assertEqual(merged1["actors"]["Alice"]["stance"], "Relaxed")
        self.assertEqual(merged1["actors"]["Alice"]["clothing"]["top"], "Silk Blouse")

        # 2. Update only top clothing slot
        update2 = PhysicalUpdate.model_validate({"actors": {"Alice": {"clothing": {"top": "Unbuttoned Chemise"}}}})
        merged2 = merge_physical_state_updates(initial, update2)
        alice_cloth = merged2["actors"]["Alice"]["clothing"]
        self.assertEqual(alice_cloth["top"], "Unbuttoned Chemise")
        self.assertEqual(alice_cloth["bottom"], "Pleated Skirt")
        self.assertEqual(alice_cloth["under_top"], "Lace Bra")
        self.assertEqual(alice_cloth["under_bottom"], "Silk Panties")

    def test_disengagement_action_clears_intimate_contact(self):
        """Verify action with step back / break contact intent clears lingering intimate contact."""
        from game_engine.state.reducers import _reduce_physical_state_and_memories

        party = [({"id": 1, "user_id": 12345, "name": "Hero"}, [])]
        initial_state = {
            "actors": {"Hero": {"posture": "Standing close"}, "Lyra": {"posture": "Standing close"}},
            "props": {},
            "intimate_contact": "Kissing / embrace with Lyra"
        }
        db.update_session_physical_state(self.session_id, initial_state)

        session = {"id": self.session_id, "current_location": "Balcony", "dialogue_partner": "Lyra", "scenario": "fantasy"}
        turn_outcome = {"outcome_narrative": "The hero steps back.", "physical_updates": {}}
        actions = [{"label": "I gently break the kiss and step back to look out over the city"}]

        _reduce_physical_state_and_memories(self.session_id, session, turn_outcome, party, "fantasy", actions)
        persisted = db.get_session_physical_state(self.session_id)
        self.assertEqual(persisted["intimate_contact"], "none")

    def test_action_intent_infers_intimate_contact(self):
        """Verify action taking partner's hand or cuddling infers intimate contact when LLM omitted it."""
        from game_engine.state.reducers import _reduce_physical_state_and_memories

        party = [({"id": 1, "user_id": 12345, "name": "Hero"}, [])]
        initial_state = {
            "actors": {"Hero": {"posture": "Walking"}, "Seraphina": {"posture": "Walking"}},
            "props": {},
            "intimate_contact": "none"
        }
        db.update_session_physical_state(self.session_id, initial_state)

        session = {"id": self.session_id, "current_location": "Gardens", "dialogue_partner": "Seraphina", "scenario": "fantasy"}
        turn_outcome = {"outcome_narrative": "They stroll peacefully through the roses.", "physical_updates": {}}
        actions = [{"label": "I take her hand and walk closely beside her"}]

        _reduce_physical_state_and_memories(self.session_id, session, turn_outcome, party, "fantasy", actions)
        persisted = db.get_session_physical_state(self.session_id)
        self.assertEqual(persisted["intimate_contact"], "Holding hands with Seraphina")


    def test_actor_name_matching_prevents_duplicate_entries(self):
        """Verify first-name and full-name updates merge into existing record rather than creating duplicates."""
        initial_state = {
            "actors": {
                "Elena Vance": {
                    "posture": "Sitting on sofa",
                    "holding": "Empty hands",
                    "clothing": {"top": "Silk Blouse", "bottom": "Skirt", "under_top": "Worn", "under_bottom": "Worn"},
                    "stance": "Relaxed"
                }
            },
            "props": {},
            "intimate_contact": "none"
        }
        # Update using only first name "Elena"
        update = {
            "actors": {
                "Elena": {
                    "posture": "Standing alert",
                    "holding": "Crossbow"
                }
            }
        }
        merged = merge_physical_state_updates(initial_state, update)
        self.assertEqual(len(merged["actors"]), 1)
        self.assertIn("Elena Vance", merged["actors"])
        self.assertEqual(merged["actors"]["Elena Vance"]["posture"], "Standing alert")
        self.assertEqual(merged["actors"]["Elena Vance"]["holding"], "Crossbow")
        # Clothing remains preserved
        self.assertEqual(merged["actors"]["Elena Vance"]["clothing"]["top"], "Silk Blouse")

    def test_recruited_party_npcs_physical_continuity_and_location_transition(self):
        """Verify recruited companions in session['party_npcs'] survive room transitions even with name variations."""
        state = {
            "actors": {
                "Artemiusz": {"posture": "Sitting on couch", "holding": "Steel Longsword"},
                "Elena Vance": {"posture": "Sitting on chair", "holding": "Recurve Bow"}
            },
            "props": {"Leather Chair": "Present"},
            "intimate_contact": "none"
        }
        party = [({"id": 1, "user_id": 12345, "name": "Artemiusz"}, [])]
        # Retained names uses first name "Elena"
        retained = {"Elena"}
        transitioned = handle_location_transition(state, party=party, retained_names=retained)

        self.assertIn("Artemiusz", transitioned["actors"])
        self.assertIn("Elena Vance", transitioned["actors"])
        self.assertIn("Standing", transitioned["actors"]["Elena Vance"]["posture"])
        self.assertEqual(transitioned["actors"]["Elena Vance"]["holding"], "Recurve Bow")
        self.assertEqual(transitioned["props"], {})

    def test_actor_holding_room_prop_removes_from_props(self):
        """Verify picking up a room prop removes it from room props to prevent duplicate existence."""
        initial_state = {
            "actors": {
                "Artemiusz": {"posture": "Standing", "holding": "Empty hands"}
            },
            "props": {"Tavern Mug": "On table", "Ancient Tome": "On shelf"},
            "intimate_contact": "none"
        }
        # Artemiusz picks up the Tavern Mug
        update = {
            "actors": {
                "Artemiusz": {"holding": "Tavern Mug"}
            }
        }
        merged = merge_physical_state_updates(initial_state, update)
        self.assertEqual(merged["actors"]["Artemiusz"]["holding"], "Tavern Mug")
        self.assertNotIn("Tavern Mug", merged["props"])
        self.assertIn("Ancient Tome", merged["props"])

    def test_deceased_combatants_synchronization_and_no_resurrection(self):
        """Verify slain enemies/NPCs get deceased postures and do not resurrect on location transition."""
        from game_engine.state.reducers import _reduce_physical_state_and_memories

        party = [({"id": 1, "user_id": 12345, "name": "Hero"}, [])]
        initial_state = {
            "actors": {
                "Hero": {"posture": "Standing alert", "holding": "Blade", "stance": "Guarded"},
                "Bandit Leader": {"posture": "Standing alert", "holding": "Axe", "stance": "Guarded"}
            },
            "props": {"Campfire": "Burning"},
            "intimate_contact": "none"
        }
        db.update_session_physical_state(self.session_id, initial_state)

        session = {"id": self.session_id, "current_location": "Bandit Camp", "scenario": "fantasy"}
        turn_outcome = {
            "outcome_narrative": "The bandit leader falls motionless.",
            "deceased_characters": ["Bandit Leader"]
        }

        _reduce_physical_state_and_memories(self.session_id, session, turn_outcome, party, "fantasy", [])
        persisted = db.get_session_physical_state(self.session_id)
        bandit = persisted["actors"]["Bandit Leader"]
        self.assertEqual(bandit["posture"], "Deceased / Motionless")
        self.assertEqual(bandit["holding"], "Dropped / Empty hands")
        self.assertEqual(bandit["stance"], "Dead")

        # Now transition location: bandit corpse should not transition or resurrect
        transitioned = handle_location_transition(persisted, party=party, retained_names=set())
        self.assertNotIn("Bandit Leader", transitioned["actors"])
        self.assertIn("Hero", transitioned["actors"])

    def test_downed_combatants_remain_downed_on_transition(self):
        """Verify 0 HP / incapacitated party members remain downed when carried into a new area."""
        state = {
            "actors": {
                "Hero": {"posture": "Standing alert", "holding": "Sword", "stance": "Guarded"},
                "Wounded Ally": {"posture": "Prone / Downed (Unconscious)", "holding": "Dropped / Empty hands", "stance": "Incapacitated"}
            },
            "props": {},
            "intimate_contact": "none"
        }
        party = [
            ({"id": 1, "user_id": 12345, "name": "Hero"}, []),
            ({"id": 2, "user_id": 12346, "name": "Wounded Ally"}, [])
        ]
        transitioned = handle_location_transition(state, party=party)
        ally = transitioned["actors"]["Wounded Ally"]
        self.assertEqual(ally["posture"], "Downed / Unconscious in new area")
        self.assertEqual(ally["stance"], "Incapacitated")
        self.assertEqual(ally["holding"], "Dropped / Empty hands")

    def test_canonical_clothing_slots_and_case_insensitive_prop_dedup(self):
        """Verify clothing slot synonyms normalize properly and prop casing variations deduplicate."""
        initial_state = {
            "actors": {
                "Lyra": {
                    "clothing": {"top": "Silk Blouse", "bottom": "Skirt", "under_top": "Worn", "under_bottom": "Worn"}
                }
            },
            "props": {"Crystal Goblet": "Full of wine"},
            "intimate_contact": "none"
        }
        # Update using "bra" and "underwear" synonyms and "crystal goblet" in lowercase
        update = {
            "actors": {
                "Lyra": {
                    "clothing": {"bra": "Unhooked lace bra", "underwear": "Removed"}
                }
            },
            "props": [{"name": "crystal goblet", "state": "Empty"}]
        }
        merged = merge_physical_state_updates(initial_state, update)
        cloth = merged["actors"]["Lyra"]["clothing"]
        self.assertEqual(cloth["under_top"], "Unhooked lace bra")
        self.assertEqual(cloth["under_bottom"], "Removed")
        # Prop casing deduplication: should not have both "Crystal Goblet" and "crystal goblet"
        self.assertEqual(len(merged["props"]), 1)
        self.assertIn("Crystal Goblet", merged["props"])
        self.assertEqual(merged["props"]["Crystal Goblet"], "Empty")

    def test_dialogue_switch_clears_prior_intimate_contact(self):
        """Verify speaking to a new character without referencing intimate partner clears contact."""
        from game_engine.state.reducers import _reduce_physical_state_and_memories

        party = [({"id": 1, "user_id": 12345, "name": "Hero"}, [])]
        initial_state = {
            "actors": {"Hero": {"posture": "Standing"}, "Elena": {"posture": "Standing"}, "Marcus": {"posture": "Standing"}},
            "props": {},
            "intimate_contact": "Holding hands with Elena"
        }
        db.update_session_physical_state(self.session_id, initial_state)

        # Player switches to talking to Marcus
        session = {"id": self.session_id, "current_location": "Tavern", "dialogue_partner": "Marcus", "scenario": "fantasy"}
        turn_outcome = {"outcome_narrative": "The hero talks to Marcus.", "physical_updates": {}}
        actions = [{"label": "I turn to Marcus and ask him about the mission"}]

        _reduce_physical_state_and_memories(self.session_id, session, turn_outcome, party, "fantasy", actions)
        persisted = db.get_session_physical_state(self.session_id)
        self.assertEqual(persisted["intimate_contact"], "none")

    def test_location_transition_clears_relative_position_and_fixture_tether(self):
        """Verify room-specific relative positions and fixture tethers do not leak across rooms."""
        state = {
            "actors": {
                "Artemiusz": {
                    "posture": "Standing",
                    "relative_position": "Behind the bar counter",
                    "tether": "Tied to wooden pillar"
                },
                "Lyra": {
                    "posture": "Standing",
                    "relative_position": "Crouching in shadows",
                    "tether": "Carrying Elena"
                }
            },
            "props": {"Bar Stool": "Present"},
            "intimate_contact": "none",
            "combat_focus": "none"
        }
        transitioned = handle_location_transition(state, party=self.party)
        art = transitioned["actors"]["Artemiusz"]
        # relative_position must be cleared
        self.assertNotIn("relative_position", art)
        # fixture tether must be cleared
        self.assertNotIn("tether", art)

    def test_dropped_loot_unpacked_with_label_action(self):
        """Verify dropped weapon from deceased combatant is unpacked into props on player 'Search' action with label key."""
        from game_engine.state.reducers import _reduce_physical_state_and_memories

        party = [({"id": 1, "user_id": 12345, "name": "Hero"}, [])]
        initial_state = {
            "actors": {
                "Hero": {"posture": "Standing", "holding": "Iron Sword"},
                "Goblin Raider": {"posture": "Standing", "holding": "Rusty Dagger", "stance": "Guarded"}
            },
            "props": {},
            "intimate_contact": "none",
            "dropped_items": []
        }
        db.update_session_physical_state(self.session_id, initial_state)

        # Turn 1: Goblin dies, drops weapon into dropped_items
        session = {"id": self.session_id, "current_location": "Cave", "scenario": "fantasy"}
        turn1_outcome = {
            "outcome_narrative": "The hero strikes down the goblin.",
            "deceased_characters": ["Goblin Raider"],
            "physical_updates": {}
        }
        actions1 = [{"label": "Strike with sword"}]
        _reduce_physical_state_and_memories(self.session_id, session, turn1_outcome, party, "fantasy", actions1)

        state1 = db.get_session_physical_state(self.session_id)
        self.assertIn("Rusty Dagger", state1["dropped_items"])
        self.assertNotIn("Rusty Dagger", state1["props"])

        # Turn 2: Player uses 'Search and loot the room' action (formatted with 'label')
        turn2_outcome = {
            "outcome_narrative": "The hero searches the room for loot.",
            "physical_updates": {}
        }
        actions2 = [{"label": "Search and loot the fallen enemies"}]
        _reduce_physical_state_and_memories(self.session_id, session, turn2_outcome, party, "fantasy", actions2)

        state2 = db.get_session_physical_state(self.session_id)
        self.assertEqual(len(state2["dropped_items"]), 0)
        self.assertIn("Rusty Dagger", state2["props"])
        self.assertEqual(state2["props"]["Rusty Dagger"], "Dropped on the floor")

    def test_deterministic_redress_action_restores_outfit(self):
        """Verify explicit 'Redress / Get dressed' action restores inventory clothing layers even if LLM physical_updates is empty."""
        from game_engine.state.reducers import _reduce_physical_state_and_memories

        party = [({"id": 1, "user_id": 12345, "name": "Hero"}, [{"slot": "Armor", "name": "Plate Armor"}, {"slot": "Bottom", "name": "Iron Greaves"}])]
        initial_state = {
            "actors": {
                "Hero": {
                    "posture": "Standing",
                    "clothing": {"top": "Stripped", "bottom": "Stripped", "under_top": "None", "under_bottom": "None"}
                }
            },
            "props": {},
            "intimate_contact": "none"
        }
        db.update_session_physical_state(self.session_id, initial_state)

        session = {"id": self.session_id, "current_location": "Bedroom", "scenario": "fantasy"}
        turn_outcome = {"outcome_narrative": "Hero gets dressed.", "physical_updates": {}}
        actions = [{"label": "Redress / Get dressed (Hero)"}]

        _reduce_physical_state_and_memories(self.session_id, session, turn_outcome, party, "fantasy", actions)

        persisted = db.get_session_physical_state(self.session_id)
        hero_cloth = persisted["actors"]["Hero"]["clothing"]
        self.assertEqual(hero_cloth["top"], "Plate Armor")
        self.assertEqual(hero_cloth["bottom"], "Iron Greaves")

    def test_deterministic_put_down_burden_and_break_free(self):
        """Verify putting down a carried burden and succeeding at breaking free deterministically clears tether."""
        from game_engine.state.reducers import _reduce_physical_state_and_memories
        from skill_check import CheckResult

        party = [({"id": 1, "user_id": 12345, "name": "Hero"}, [])]
        initial_state = {
            "actors": {
                "Hero": {"posture": "Standing", "tether": "Carrying Elena"},
                "Elena": {"posture": "Being carried"}
            },
            "props": {},
            "intimate_contact": "none"
        }
        db.update_session_physical_state(self.session_id, initial_state)

        # 1. Put down burden
        session = {"id": self.session_id, "current_location": "Camp", "scenario": "fantasy"}
        turn1 = {"outcome_narrative": "Hero sets Elena down gently.", "physical_updates": {}}
        actions1 = [{"label": "Put down what you are carrying / Carrying Elena"}]
        _reduce_physical_state_and_memories(self.session_id, session, turn1, party, "fantasy", actions1)

        state1 = db.get_session_physical_state(self.session_id)
        self.assertNotIn("tether", state1["actors"]["Hero"])
        self.assertEqual(state1["actors"]["Elena"]["posture"], "Resting safely on the ground")

        # 2. Hero gets grappled and successfully breaks free
        state1["actors"]["Hero"]["tether"] = "Restrained by ropes"
        db.update_session_physical_state(self.session_id, state1)

        turn2 = {"outcome_narrative": "Hero breaks the ropes with mighty strength!", "physical_updates": {}}
        actions2 = [{
            "label": "Struggle with all your might to break free from: Restrained by ropes",
            "check": CheckResult(chance=80, roll=20.0, tier="success", tier_label="Success", succeeded=True, requirement=14)
        }]
        _reduce_physical_state_and_memories(self.session_id, session, turn2, party, "fantasy", actions2)

        state2 = db.get_session_physical_state(self.session_id)
        self.assertNotIn("tether", state2["actors"]["Hero"])

    def test_merge_clears_none_strings_for_position_and_tether(self):
        """Verify passing 'none', 'clear', or 'null' pops relative_position and tether instead of string leaking."""
        initial_state = {
            "actors": {
                "Hero": {"posture": "Standing", "relative_position": "Behind desk", "tether": "Bound by chains"}
            },
            "props": {},
            "intimate_contact": "none"
        }
        # Update setting both to "none"
        update = {
            "actors": {
                "Hero": {"relative_position": "none", "tether": "clear"}
            }
        }
        merged = merge_physical_state_updates(initial_state, update)
        self.assertNotIn("relative_position", merged["actors"]["Hero"])
        self.assertNotIn("tether", merged["actors"]["Hero"])

    def test_free_actions_have_zero_time_cost(self):
        """Verify FREE actions like Observe, Redress, and Drop Burden cost 0 in-game minutes."""
        from mechanics.system.time_engine import calculate_action_time_cost

        cost_obs = calculate_action_time_cost({
            "label": "Observe your surroundings and inspect those present",
            "stat": "FREE"
        })
        self.assertEqual(cost_obs, 0)

        cost_redress = calculate_action_time_cost({
            "label": "Redress / Get dressed (Hero)",
            "stat": "FREE"
        })
        self.assertEqual(cost_redress, 0)


if __name__ == "__main__":
    unittest.main()

