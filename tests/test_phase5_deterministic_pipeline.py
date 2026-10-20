import unittest
from unittest.mock import patch, AsyncMock
import db
import game_engine
from models.llm_schemas import (
    CosmeticActorPose,
    DeterministicTurnNarration,
    DeterministicCombatNarration,
)
from game_engine.state.reducers import _reduce_physical_state_and_memories


class TestPhase5DeterministicPipeline(unittest.IsolatedAsyncioTestCase):

    def setUp(self):
        db.init_db()
        self.session_id = 950501
        with db.get_conn() as conn:
            conn.execute(
                "INSERT OR REPLACE INTO sessions (id, host_user_id, status, mode, capacity, scenario, current_location) "
                "VALUES (?, 12345, 'active', 'single', 1, 'fantasy', 'Sunfall Citadel ➔ Courtyard ➔ Fountain')",
                (self.session_id,),
            )
        self.player_char = {
            "id": 1,
            "user_id": 12345,
            "name": "Artemiusz",
            "hp": 30,
            "max_hp": 30,
            "mp": 15,
            "max_mp": 15,
            "gender": "male",
            "stats": {"STR": 6, "AGI": 6, "END": 6, "INT": 7, "PER": 6, "CHA": 7, "LUK": 5},
        }
        self.party = [(self.player_char, [])]

    def test_slim_narrator_and_combat_schemas(self):
        """Verify DeterministicTurnNarration and DeterministicCombatNarration schemas and field coercion."""
        turn_schema = DeterministicTurnNarration.model_json_schema()
        self.assertIn("outcome_narrative", turn_schema["properties"])
        self.assertIn("next_narrative", turn_schema["properties"])
        self.assertIn("next_choices", turn_schema["properties"])
        self.assertIn("actor_poses", turn_schema["properties"])
        self.assertIn("episodic_memory", turn_schema["properties"])
        self.assertNotIn("entity_audit", turn_schema["properties"])
        self.assertNotIn("character_outcomes", turn_schema["properties"])
        self.assertNotIn("physical_updates", turn_schema["properties"])

        combat_schema = DeterministicCombatNarration.model_json_schema()
        self.assertNotIn("next_choices", combat_schema["properties"])
        self.assertIn("actor_poses", combat_schema["properties"])

        parsed = DeterministicTurnNarration.model_validate({
            "scene_title": "Quiet Watch",
            "outcome_narrative": "You lean against the stone parapet.",
            "next_narrative": "Seraphina watches the horizon.",
            "next_choices": ["Ask Seraphina about the northern watchtower"],
            "actor_poses": {
                "Artemiusz": "Leaning against parapet",
                "Seraphina": {"posture": "Standing by railing", "holding": "Spyglass", "clothing": {"top": "off"}},
            },
            "episodic_memory": "Artemiusz joined Seraphina on the watchtower parapet.",
        })
        dumped = parsed.model_dump()
        self.assertEqual(dumped["actor_poses"]["Artemiusz"]["posture"], "Leaning against parapet")
        self.assertEqual(dumped["actor_poses"]["Seraphina"]["holding"], "Spyglass")
        self.assertNotIn("clothing", dumped["actor_poses"]["Seraphina"])

    def test_sanitize_narrator_prose_single_pass(self):
        """Verify sanitize_narrator_prose cleans comparative cliches and meta leaks in one call."""
        res = {
            "outcome_narrative": "It was not fear, but resolve that guided your blade. [OBJECTIVE COMPLETE]",
            "next_narrative": "The chamber settles into silence.",
        }
        cleaned = game_engine.sanitize_narrator_prose(
            res,
            session={"id": self.session_id, "scenario": "fantasy"},
            party=self.party,
            actions=[{"label": "Strike the ward"}],
        )
        self.assertNotIn("[OBJECTIVE COMPLETE]", cleaned["outcome_narrative"])

    def test_reducer_cosmetic_actor_poses_and_episodic_memory(self):
        """Verify _reduce_physical_state_and_memories merges cosmetic actor_poses and persists episodic_memory."""
        db.update_session_physical_state(self.session_id, {
            "actors": {
                "Artemiusz": {
                    "posture": "Standing",
                    "holding": "Empty hands",
                    "clothing": {"top": "Tunic", "bottom": "Trousers", "under_top": "Worn", "under_bottom": "Worn"},
                },
                "Lady Seraphina": {
                    "posture": "Standing",
                    "holding": "Empty hands",
                    "clothing": {"top": "Silk Gown", "bottom": "Skirt", "under_top": "Worn", "under_bottom": "Worn"},
                },
            },
            "props": {},
            "intimate_contact": "none",
        })
        session = {
            "id": self.session_id,
            "current_location": "Sunfall Citadel ➔ Courtyard ➔ Fountain",
            "dialogue_partners": ["Lady Seraphina"],
            "history": [{}, {}],
        }
        outcome = {
            "location": "Sunfall Citadel ➔ Courtyard ➔ Fountain",
            "dialogue_partners": ["Lady Seraphina"],
            "npcs_present": [{"name": "Lady Seraphina"}],
            "actor_poses": {
                "Lady Seraphina": {
                    "posture": "Seated on the fountain edge",
                    "holding": "Silver Locket",
                    "clothing": {"top": "Removed"},
                }
            },
            "episodic_memory": "Shared the story of the silver locket by the courtyard fountain.",
        }
        _reduce_physical_state_and_memories(
            self.session_id, session, outcome, self.party, "fantasy", actions=[{"label": "Ask about her locket"}]
        )
        persisted = db.get_session_physical_state(self.session_id)
        sera = persisted["actors"]["Lady Seraphina"]
        self.assertEqual(sera["posture"], "Seated on the fountain edge")
        self.assertEqual(sera["holding"], "Silver Locket")
        # Clothing must NOT be mutated by actor_poses
        self.assertEqual(sera["clothing"]["top"], "Silk Gown")

        memories = db.get_npc_memories(self.session_id, "Lady Seraphina")
        self.assertTrue(any("silver locket" in m.get("memory_fact", "").lower() for m in memories))

    def test_build_hybrid_turn_choices_slots_and_stat_dc_inference(self):
        """Verify build_hybrid_turn_choices combines priority buttons, inferred stat/DC LLM choices, and free slot."""
        session = {
            "id": self.session_id,
            "scenario": "fantasy",
            "current_location": "Sunfall Citadel ➔ Courtyard ➔ Fountain",
        }
        raw_choices = [
            "Investigate the ancient runes carved into the fountain basin",
            "Convince Guard Vance to reveal the patrol schedule",
        ]
        built = game_engine.build_hybrid_turn_choices(
            raw_choices,
            session=session,
            party=self.party,
            result={"location": session["current_location"], "npcs_present": [{"name": "Guard Vance"}]},
            actions=[{"label": "Step into the courtyard"}],
            schedule_transition_choice={"label": "Walk with Guard Vance to the Armory", "stat": "NONE", "requirement": 0},
        )
        labels = [c["label"] for c in built]
        self.assertEqual(built[0]["label"], "Walk with Guard Vance to the Armory")
        runes_choice = next(c for c in built if "runes" in c["label"].lower())
        self.assertEqual(runes_choice["stat"], "INT")
        self.assertGreaterEqual(runes_choice["requirement"], 5)
        self.assertTrue(any("observe your surroundings" in l.lower() for l in labels))

    async def test_resolve_turn_combat_uses_combat_schema_and_code_choices(self):
        """Verify resolve_turn in combat mode uses DeterministicCombatNarration and generates Python combat choices."""
        session = {
            "id": self.session_id,
            "scenario": "fantasy",
            "current_location": "Shadow Cavern",
            "nearby_enemies": [{"name": "Cave Troll", "hp": 25, "max_hp": 25, "atk": 8, "def": 5}],
            "history": [],
        }
        actions = [{
            "char": self.player_char,
            "label": "Strike Cave Troll with sword",
            "stat": "STR",
            "requirement": 6,
            "check": None,
        }]
        with patch("game_engine.call_llm_json", new_callable=AsyncMock) as mock_llm:
            mock_llm.return_value = {
                "scene_title": "Clash in the Cavern",
                "outcome_narrative": "Your blade bites into the Cave Troll's hide!",
                "next_narrative": "The troll roars and raises its club.",
                "actor_poses": {"Artemiusz": {"posture": "Low combat stance", "holding": "Longsword"}},
            }
            res = await game_engine.resolve_turn(session, self.party, actions)
            _, kwargs = mock_llm.call_args
            self.assertIs(kwargs.get("response_model"), DeterministicCombatNarration)
            self.assertTrue(len(res.get("next_choices") or []) >= 2)

    async def test_resolve_turn_active_intimate_turn_no_name_error(self):
        """Verify resolve_turn during an active intimate scene attaches _pre_turn_intimacy without NameError."""
        db.update_session_physical_state(self.session_id, {
            "intimate_contact": "Passionate kissing with Lady Seraphina",
            "actors": {
                "Artemiusz": {"clothing": {"top": "Tunic", "bottom": "Trousers", "under_top": "Worn", "under_bottom": "Worn"}},
                "Lady Seraphina": {"clothing": {"top": "Silk Gown", "bottom": "Skirt", "under_top": "Lace Bra", "under_bottom": "Panties"}},
            },
        })
        session = {
            "id": self.session_id,
            "scenario": "fantasy",
            "current_location": "Sunfall Citadel ➔ Private Quarters ➔ Bedchamber",
            "dialogue_partner": "Lady Seraphina",
            "dialogue_partners": ["Lady Seraphina"],
            "current_npcs": [{"name": "Lady Seraphina", "role": "Noblewoman"}],
            "history": [],
        }
        actions = [{
            "char": self.player_char,
            "label": "Kiss Lady Seraphina deeply and caress her waist",
            "stat": "CHA",
            "requirement": 5,
            "check": {"tier": "success", "roll": 15, "total": 18, "dc": 5},
        }]
        with patch("game_engine.call_llm_json", new_callable=AsyncMock) as mock_llm:
            mock_llm.return_value = {
                "scene_title": "Embrace in the Bedchamber",
                "outcome_narrative": "You kiss Lady Seraphina deeply as she leans into your embrace.",
                "next_narrative": "Her breath catches softly against your lips.",
                "next_choices": ["Whisper softly to Lady Seraphina", "Caress her cheek gently"],
            }
            res = await game_engine.resolve_turn(session, self.party, actions)
            self.assertIn("_pre_turn_intimacy", res)
            self.assertIsInstance(res["_pre_turn_intimacy"], dict)
            self.assertIn("_physical_state", res)

    def test_spawn_canonical_role_npc_pre_turn_persists_to_contacts(self):
        """Verify _spawn_canonical_role_npc_pre_turn generates a canonical NPC and persists to contacts without error."""
        from game_engine.npcs.stage_manager import _spawn_canonical_role_npc_pre_turn
        session = {"id": self.session_id, "scenario": "fantasy"}
        spawned = _spawn_canonical_role_npc_pre_turn(session, "barista", "Sunfall Citadel ➔ Market ➔ Cafe")
        self.assertTrue(spawned.get("name"))
        self.assertEqual(spawned.get("role"), "Barista")
        persisted = db.get_contact(self.session_id, spawned["name"])
        self.assertIsNotNone(persisted)
        self.assertEqual(persisted.get("name"), spawned["name"])

    def test_social_disclosures_persist_and_hydrate_appearance(self):
        """Verify resolve_pre_turn_social_and_disclosures hydrates missing appearance fields and persists to DB."""
        from game_engine.state.social import resolve_pre_turn_social_and_disclosures
        db.upsert_contact(self.session_id, "lady_seraphina", "Lady Seraphina", delta_score=5, gender="female", appearance={})
        session = {
            "id": self.session_id,
            "scenario": "fantasy",
            "current_location": "Sunfall Citadel ➔ Private Quarters",
            "dialogue_partner": "Lady Seraphina",
        }
        actions = [{
            "char": self.player_char,
            "label": "Ask Lady Seraphina about her sensitive spots and turn-ons",
            "stat": "CHA",
            "check": {"tier": "success", "roll": 16, "total": 19, "dc": 8},
        }]
        res = resolve_pre_turn_social_and_disclosures(session, self.party, actions, ["Lady Seraphina"])
        self.assertIn("sensitive_spots", res.get("revealed_attributes", []))
        self.assertTrue(any("[MANDATORY CANONICAL DISCLOSURE]" in d for d in res.get("directives", [])))
        updated_c = db.get_contact(self.session_id, "Lady Seraphina")
        self.assertTrue((updated_c.get("appearance") or {}).get("sensitive_spots_revealed"))

    def test_resolve_pre_turn_quests_sub_objective_resolution(self):
        """Verify resolve_pre_turn_quests_and_clues completes sub-objectives via resolves_sub_obj_id and persists."""
        from game_engine.quests import resolve_pre_turn_quests_and_clues
        db.upsert_quest(
            session_id=self.session_id,
            quest_id="SQ-TEST-1",
            quest_type="Story Quest",
            title="Shadows of the Citadel",
            objective="Uncover the conspiracy.",
            progress="0/1 Cleared",
            current_clues="",
            status="Active",
            reward_xp=250,
            reward_gold=60,
            is_story_quest=1,
            clues_required=1,
            sub_objectives=[{"id": "so_1", "text": "Inspect the cipher ledger in the study", "completed": False}],
        )
        session = {
            "id": self.session_id,
            "scenario": "fantasy",
            "current_location": "Sunfall Citadel ➔ Archives ➔ Study",
        }
        actions = [{
            "char": self.player_char,
            "label": "Decode the cipher ledger on the desk",
            "resolves_sub_obj_id": "so_1",
            "check": {"tier": "success", "roll": 15, "total": 18, "dc": 10},
        }]
        res = resolve_pre_turn_quests_and_clues(session, self.party, actions)
        self.assertTrue(any("[MANDATORY QUEST OBJECTIVE COMPLETE]" in d for d in res.get("directives", [])))
        sq = db.get_active_story_quest(self.session_id)
        self.assertTrue(sq["sub_objectives"][0]["completed"])


if __name__ == "__main__":
    unittest.main()
