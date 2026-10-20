"""
Tests for Phase 3: Living Scene Stage & Legacy Purge
Covers:
1. Deterministic micro-blocking & prop grounding (derive_initial_micro_blocking)
2. In-scene composure momentum tracking & TTL decay (update_stage_blocking_and_composure_post_turn)
3. 3-Ring Scene Attention architecture (ring_1_primary, ring_2_attentive_peer, ring_3_bystander)
4. Graduated Organic Initiative (compute_scene_beat_linger_turns & format_organic_npc_initiative_directive)
5. Post-turn stage delta resolution (resolve_post_turn_stage_delta) end-to-end in process_scene_npcs
"""
import unittest
import pytest

import db
import game_engine
from game_engine.npcs import (
    compute_pre_turn_stage,
    format_ring2_attentive_peer_cues,
    evaluate_scene_attention_transition,
    compute_scene_beat_linger_turns,
    format_organic_npc_initiative_directive,
    resolve_post_turn_stage_delta,
    update_stage_blocking_and_composure_post_turn,
    derive_initial_micro_blocking,
    process_scene_npcs,
)
from mechanics.social.persona.actor_card import build_actor_direction_card


class TestLivingSceneStage(unittest.TestCase):

    def test_derive_initial_micro_blocking(self):
        """Verify deterministic physical micro-blocking assigns sensible props, spots, and focus."""
        # Classroom desk setting
        mb_desk = derive_initial_micro_blocking(
            npc={"name": "Mia Yamada"},
            current_location="Westlake Academy ➔ Classroom 2-B ➔ Teacher Desk",
            time_slot="Morning Classes",
            stage_role="active_partner",
        )
        self.assertIn("spot_and_posture", mb_desk)
        self.assertIn("active_prop", mb_desk)
        self.assertIn("proximity", mb_desk)
        self.assertEqual(mb_desk["proximity"], "conversational_distance")

        # Casual courtyard / hallway
        mb_hall = derive_initial_micro_blocking(
            npc={"name": "Justin"},
            current_location="Westlake Academy ➔ Main Hallway",
            time_slot="Lunch",
            stage_role="room_bystander",
        )
        self.assertEqual(mb_hall["proximity"], "across_room")

    def test_in_scene_composure_momentum_and_decay(self):
        """Verify composure transitions on emotional deltas and decays turn-by-turn."""
        session = {
            "scene_stage_state": {
                "mia_yamada": {
                    "composure_state": "composed",
                    "composure_ttl": 0,
                    "blocking": {"active_prop": "a textbook"},
                }
            }
        }

        # 1. Warm compliment / flirtation -> shifts to warm_softened or flustered with TTL
        update_stage_blocking_and_composure_post_turn(
            session=session,
            actions=[{"label": "Give Mia a sweet compliment and hold her hand"}],
            narrative="Mia's cheeks flushed as she smiled warmly.",
            rel_deltas={"mia yamada": 5},
        )
        mia_state = session["scene_stage_state"]["mia_yamada"]
        self.assertIn(mia_state["composure_state"], ("flustered", "warm_softened"))
        self.assertGreaterEqual(mia_state["composure_ttl"], 2)

        # 2. Next turn: neutral action decays TTL
        initial_ttl = mia_state["composure_ttl"]
        update_stage_blocking_and_composure_post_turn(
            session=session,
            actions=[{"label": "Discuss the upcoming exam"}],
            narrative="Mia flipped to chapter 4 calmly.",
            rel_deltas={"mia yamada": 0},
        )
        self.assertEqual(session["scene_stage_state"]["mia_yamada"]["composure_ttl"], initial_ttl - 1)

        # 3. Decay to 0 restores composed state
        session["scene_stage_state"]["mia_yamada"]["composure_ttl"] = 1
        update_stage_blocking_and_composure_post_turn(
            session=session,
            actions=[{"label": "Take notes quietly"}],
            narrative="The clock ticked on the classroom wall.",
            rel_deltas={"mia yamada": 0},
        )
        self.assertEqual(session["scene_stage_state"]["mia_yamada"]["composure_state"], "composed")
        self.assertEqual(session["scene_stage_state"]["mia_yamada"]["composure_ttl"], 0)

    def test_3_ring_attention_assignment_and_peer_cues(self):
        """Verify stage NPCs receive correct attention rings and Ring 2 cues are generated."""
        stage_npcs = [
            {"name": "Mia Yamada", "stage_role": "active_partner", "attention_ring": "ring_1_primary"},
            {"name": "Leo Thorne", "stage_role": "party_companion", "attention_ring": "ring_2_attentive_peer"},
            {"name": "Justin", "stage_role": "room_bystander", "attention_ring": "ring_3_bystander"},
        ]

        cues = format_ring2_attentive_peer_cues(stage_npcs, active_partners=["Mia Yamada"])
        self.assertIn("[RING 2: ATTENTIVE IN-ROOM PEERS", cues)
        self.assertIn("Leo Thorne", cues)
        self.assertIn("MUST NEVER hijack the primary dialogue", cues)
        # Justin is in Ring 3 so not in Ring 2 prompt section
        self.assertNotIn("Justin", cues)

    def test_evaluate_scene_attention_transition(self):
        """Verify attention transition allows legitimate chime-ins but isolates ambient bystanders."""
        retained = ["Mia Yamada"]

        # Player explicitly addresses bystander -> transition allowed
        self.assertTrue(
            evaluate_scene_attention_transition(
                "Justin",
                retained_partners=retained,
                actions=[{"label": "Turn to Justin and ask his opinion"}],
            )
        )

        # Ambient background activity -> blocked from hijacking
        self.assertFalse(
            evaluate_scene_attention_transition(
                "Coach Kai",
                retained_partners=retained,
                narrative="Across the field, Coach Kai shouted at the players.",
            )
        )

    def test_graduated_organic_initiative_stages(self):
        """Verify graduated initiative directives for Stage 1 beat pivot and Stage 2 physical momentum."""
        npc = {
            "name": "Evelyn",
            "micro_blocking": {"active_prop": "a brass telescope"},
            "immediate_agenda": "calibrate the observatory lenses",
        }

        # Stage 0: Early natural flow
        self.assertEqual(format_organic_npc_initiative_directive(1, npc, dialogue_type="social"), "")

        # Stage 1: Natural beat pivot (turn 2)
        stage1 = format_organic_npc_initiative_directive(2, npc, dialogue_type="social")
        self.assertIn("Stage 1 — Natural Beat Pivot", stage1)
        self.assertIn("brass telescope", stage1)

        # Stage 2: Physical & schedule progression (turn 3+)
        stage2 = format_organic_npc_initiative_directive(3, npc, dialogue_type="social")
        self.assertIn("SOCIAL HANGOUT PROGRESSION", stage2)
        self.assertIn("help with a brass telescope", stage2)

    def test_resolve_post_turn_stage_delta_departures_and_absences(self):
        """Verify post-turn stage delta removes departed NPCs and rejects absence mentions."""
        session = {
            "pre_turn_stage_npcs": [
                {"name": "Mia Yamada", "stage_role": "active_partner"},
                {"name": "Justin", "stage_role": "room_bystander"},
            ],
            "turn_order": [],
        }

        # Justin departs, and Alice is only mentioned in absence/memory
        narrative = "Justin leaves the room and heads home. Mia remembers how Alice used to study here."
        raw_npcs = [
            {"name": "Mia Yamada"},
            {"name": "Alice"},  # Mentioned only in memory
        ]

        resolved = resolve_post_turn_stage_delta(
            session=session,
            raw_npcs_present=raw_npcs,
            narrative=narrative,
            actions=[{"label": "Wave goodbye to Justin"}],
            location_changed=False,
            new_loc="Westlake Academy ➔ Classroom 2-B",
        )

        resolved_names = [n["name"] for n in resolved]
        # Mia should be preserved
        self.assertIn("Mia Yamada", resolved_names)
        # Justin departed -> removed
        self.assertNotIn("Justin", resolved_names)
        # Alice was mentioned only in memory -> rejected
        self.assertNotIn("Alice", resolved_names)

    def test_resolve_post_turn_stage_delta_location_change_companions(self):
        """Verify location change carries over companions and drops ambient room bystanders."""
        session = {
            "pre_turn_stage_npcs": [
                {"name": "Leo Thorne", "stage_role": "party_companion"},
                {"name": "Justin", "stage_role": "room_bystander"},
            ],
            "turn_order": [],
        }

        narrative = "The party heads out into the sunny courtyard, where Coach Kai stands watching the drills."
        raw_npcs = [
            {"name": "Leo Thorne"},
            {"name": "Coach Kai", "stage_role": "room_bystander"},
        ]

        resolved = resolve_post_turn_stage_delta(
            session=session,
            raw_npcs_present=raw_npcs,
            narrative=narrative,
            actions=[{"label": "Walk to the courtyard with Leo"}],
            location_changed=True,
            new_loc="Westlake Academy ➔ Courtyard",
        )

        resolved_names = [n["name"] for n in resolved]
        # Leo Thorne (party companion) travels
        self.assertIn("Leo Thorne", resolved_names)
        # Justin was a room bystander in the classroom -> left behind
        self.assertNotIn("Justin", resolved_names)
        # Coach Kai is present at the new location
        self.assertIn("Coach Kai", resolved_names)

    def test_sanitize_npcs_list_preserves_stage_attributes(self):
        """Verify _sanitize_npcs_list retains micro_blocking, composure_state, and ring tags."""
        raw_npcs = [{
            "name": "Valerie",
            "role": "Student Council President",
            "micro_blocking": {
                "spot_and_posture": "seated at council desk",
                "active_prop": "ledger",
                "proximity": "conversational_distance",
                "prop_focus": "paused_attentive",
            },
            "composure_state": "flustered",
            "composure_ttl": 2,
            "stage_role": "active_partner",
            "attention_ring": "ring_1_primary",
        }]

        sanitized = db._sanitize_npcs_list(session_id=1, npcs=raw_npcs)
        self.assertEqual(len(sanitized), 1)
        entry = sanitized[0]
        self.assertEqual(entry["name"], "Valerie")
        self.assertEqual(entry["composure_state"], "flustered")
        self.assertEqual(entry["composure_ttl"], 2)
        self.assertEqual(entry["stage_role"], "active_partner")
        self.assertEqual(entry["attention_ring"], "ring_1_primary")
        self.assertEqual(entry["micro_blocking"]["proximity"], "conversational_distance")

    def test_compute_pre_turn_stage_contact_hydration_and_proximity_upgrade(self):
        """Verify compute_pre_turn_stage hydrates shallow contacts and upgrades across_room on dialogue init."""
        session = {
            "id": 999123,
            "current_location": "Westlake Academy ➔ Classroom 2-B",
            "current_npcs": [{"name": "Valerie", "role": "Student"}],
            "scene_stage_state": {
                "valerie": {
                    "micro_blocking": {
                        "spot_and_posture": "seated at desk",
                        "active_prop": "notebook",
                        "proximity": "across_room",
                        "prop_focus": "absorbed",
                    },
                    "composure_state": "composed",
                    "composure_ttl": 0,
                }
            },
            "turn_order": [],
        }

        class MockCtx:
            contacts = [{
                "name": "Valerie",
                "track": "romantic",
                "relationship_score": 65,
                "unlocked_traits": ["studious", "flirtatious"],
                "club": "Student Council",
            }]

        # 1. Player initiates conversation with Valerie: should promote to active_partner and upgrade proximity
        actions = [{"label": "Walk over and speak with Valerie"}]
        stage_info = compute_pre_turn_stage(session, actions, ctx=MockCtx())

        valerie_stg = next(n for n in stage_info["stage_npcs"] if n["name"] == "Valerie")
        self.assertEqual(valerie_stg["stage_role"], "active_partner")
        self.assertEqual(valerie_stg["attention_ring"], "ring_1_primary")
        self.assertEqual(valerie_stg["track"], "romantic")
        self.assertEqual(valerie_stg["relationship_score"], 65)
        # Upgraded from across_room / absorbed to conversational_distance / paused_attentive
        self.assertEqual(valerie_stg["micro_blocking"]["proximity"], "conversational_distance")
        self.assertEqual(valerie_stg["micro_blocking"]["prop_focus"], "paused_attentive")

    def test_update_stage_blocking_and_composure_suspicious_trigger(self):
        """Verify suspicious composure triggers on failed stealth/snooping actions."""
        session = {
            "scene_stage_state": {
                "valerie": {
                    "micro_blocking": {
                        "spot_and_posture": "seated behind desk",
                        "active_prop": "ledger",
                        "proximity": "conversational_distance",
                        "prop_focus": "paused_attentive",
                    },
                    "composure_state": "composed",
                    "composure_ttl": 0,
                }
            }
        }

        # Failed stealth check near Valerie
        actions = [{"label": "Attempt stealth to search Valerie's desk", "success": False}]
        narrative = "You fumble with the drawer; Valerie narrows her eyes at you suspiciously."

        update_stage_blocking_and_composure_post_turn(
            session=session,
            actions=actions,
            narrative=narrative,
            rel_deltas={},
        )

        valerie_state = session["scene_stage_state"]["valerie"]
        self.assertEqual(valerie_state["composure_state"], "suspicious")
        self.assertEqual(valerie_state["composure_ttl"], 2)

    def test_resolve_post_turn_stage_delta_excludes_left_behind_and_enemies(self):
        """Verify resolve_post_turn_stage_delta does not resurrect left-behind or enemy NPCs."""
        session = {
            "pre_turn_stage_npcs": [
                {"name": "Mia Yamada", "stage_role": "active_partner"},
                {"name": "Garrick", "stage_role": "room_bystander"},
            ],
            "nearby_enemies": [{"name": "Goblin Raider"}],
            "current_location": "Classroom 2-B",
        }
        raw_npcs = [
            {"name": "Mia Yamada"},
            {"name": "Garrick"},
            {"name": "Goblin Raider"},
            {"name": "New Walkin"},
        ]
        excluded = {"garrick"}

        result_stage = resolve_post_turn_stage_delta(
            session=session,
            raw_npcs_present=raw_npcs,
            narrative="Mia smiled as New Walkin stepped into the room.",
            actions=[],
            location_changed=False,
            new_loc="Classroom 2-B",
            excluded_names=excluded,
        )

        names = [n["name"] for n in result_stage]
        self.assertIn("Mia Yamada", names)
        self.assertIn("New Walkin", names)
        self.assertNotIn("Garrick", names)
        self.assertNotIn("Goblin Raider", names)

    def test_actor_card_suppresses_blocking_and_prop_in_active_erotic(self):
        """Verify Physical Blocking & Prop and CHOICE & PROP GROUNDING are suppressed in active erotic scenes."""
        session = {
            "current_location": "Bedroom",
            "current_minute": 600,
            "scenario": "fantasy",
        }
        npc = {
            "name": "Evelyn",
            "role": "Mage",
            "relationship_score": 80,
            "micro_blocking": {
                "spot_and_posture": "kneeling on the velvet rug",
                "active_prop": "a silver quill",
                "prop_focus": "absorbed",
                "proximity": "arm_reach",
            },
        }

        # In standard social scene
        card_social = build_actor_direction_card(session=session, npc=npc, in_active_erotic=False)
        self.assertIn("Physical Blocking & Prop:", card_social)
        self.assertIn("[CHOICE & PROP GROUNDING:", card_social)

        # In active erotic scene
        card_erotic = build_actor_direction_card(session=session, npc=npc, in_active_erotic=True)
        self.assertNotIn("Physical Blocking & Prop:", card_erotic)
        self.assertNotIn("[CHOICE & PROP GROUNDING:", card_erotic)

    def test_context_scene_activity_uses_micro_blocking(self):
        """Verify _scene_context_text surfaces micro_blocking spot and prop in the Activity field."""
        from game_engine.context import _scene_context_text
        session = {
            "current_location": "Library Study Nook",
            "current_minute": 600,
            "scene_stage_state": {
                "chloe": {
                    "micro_blocking": {
                        "spot_and_posture": "leaning against the bookshelf",
                        "active_prop": "a leather journal",
                    }
                }
            }
        }
        world = {
            "session": session,
            "scen_key": "fantasy",
            "lore": {"place": [], "person": []},
            "contacts": [],
            "factions": [],
        }
        current_npcs = [{"name": "Chloe"}]
        ctx_text = _scene_context_text(
            session_id=1,
            current_location="Library Study Nook",
            current_npcs=current_npcs,
            world=world,
        )
        self.assertIn("Activity: leaning against the bookshelf with a leather journal", ctx_text)

    def test_open_room_exploration_uses_pre_turn_stage_npcs(self):
        """Verify open room exploration prompt block respects pre_turn_stage_npcs when current_npcs is empty."""
        from game_engine.turn.dialogue import _build_dialogue_prompt_block
        session = {
            "pre_turn_stage_npcs": [{"name": "Iris"}, {"name": "Chloe"}],
            "current_npcs": [],
            "current_location": "Courtyard",
            "scenario": "fantasy",
        }
        prompt = _build_dialogue_prompt_block(
            session=session,
            ctx=None,
            new_partners=[],
            party=[],
            actions=[],
        )
        self.assertIn("OPEN ROOM / HUB EXPLORATION MODE (Active Characters Present: Iris, Chloe)", prompt)


if __name__ == "__main__":
    unittest.main()
