import os
import sys
import unittest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import db
import game_engine


class TestCompanionAndAmbientPatronLifecycle(unittest.TestCase):

    def setUp(self):
        self.test_session_id = db.create_session(
            host_user_id=99800,
            mode="solo",
            capacity=1,
            verbosity="vivid",
            dialogue_mode="balanced",
            image_gen_enabled=False,
            scenario="fantasy"
        )


        # Add Mara Vey as a companion contact
        db.upsert_contact(
            self.test_session_id,
            character_id=0,
            npc_id="mara_vey",
            name="Mara Vey",
            basic_info={"disposition": "companion", "role": "Expedition Partner", "is_companion": True},
            track="platonic"
        )

    def tearDown(self):
        with db.get_conn() as conn:
            conn.execute("DELETE FROM contacts WHERE session_id = ?", (self.test_session_id,))
            conn.execute("DELETE FROM sessions WHERE id = ?", (self.test_session_id,))
            conn.commit()

    def test_ambient_patrons_stay_behind_when_traveling_with_quest_guest(self):
        """Verify that when moving from tavern to guild hall, Mara travels but tavern patrons stay behind."""
        session = {
            "id": self.test_session_id,
            "scenario": "fantasy",
            "current_location": "Solaria ➔ The Boar's Tusk Tavern ➔ Hearthside Table",
            "current_npcs": [
                {"name": "Mara Vey"},
                {"name": "Severus Stormblessed", "role": "Dwarf"},
                {"name": "Elderly Archivist"},
                {"name": "Szeth Gryffindor", "role": "Caravan Guard"}
            ],
            "dialogue_partners": ["Mara Vey"]
        }

        # LLM erroneously hallucinates all 4 NPCs entering the guild hall plus the Guildmaster
        llm_result = {
            "location": "Solaria ➔ Adventurers' Guild Hall ➔ Contract Atrium",
            "npcs_present": [
                {"name": "Mara Vey"},
                {"name": "Severus Stormblessed"},
                {"name": "Elderly Archivist"},
                {"name": "Szeth Gryffindor"},
                {"name": "Guildmaster Elira Voss"}
            ]
        }

        processed_npcs = game_engine.process_scene_npcs(
            llm_result,
            session,
            new_loc="Solaria ➔ Adventurers' Guild Hall ➔ Contract Atrium",
            old_loc="Solaria ➔ The Boar's Tusk Tavern ➔ Hearthside Table"
        )

        names = [n["name"] for n in processed_npcs]

        # Mara Vey (bonded quest companion) and Guildmaster Elira Voss (new local NPC) must be present
        self.assertIn("Mara Vey", names)
        self.assertIn("Guildmaster Elira Voss", names)

        # Ambient tavern patrons must NOT be in the Guild Hall
        self.assertNotIn("Severus Stormblessed", names)
        self.assertNotIn("Elderly Archivist", names)
        self.assertNotIn("Szeth Gryffindor", names)

    def test_permanent_combat_companion_always_travels(self):
        """Verify that formal party NPCs (registered in session_party_npcs) always travel across establishments."""
        # Register Valerius as a formal party member
        db.add_session_party_npc(self.test_session_id, {
            "name": "Valerius Ironclad",
            "role": "Warrior",
            "level": 5,
            "hp": 45,
            "max_hp": 45,
            "mp": 20,
            "max_mp": 20,
            "status_effects": []
        })

        session = {
            "id": self.test_session_id,
            "scenario": "fantasy",
            "current_location": "Solaria ➔ The Boar's Tusk Tavern ➔ Hearthside Table",
            "current_npcs": [
                {"name": "Valerius Ironclad", "hp": 45, "max_hp": 45},
                {"name": "Tavern Barkeep"}
            ]
        }

        llm_result = {
            "location": "Solaria ➔ Adventurers' Guild Hall ➔ Contract Atrium",
            "npcs_present": []
        }

        processed_npcs = game_engine.process_scene_npcs(
            llm_result,
            session,
            new_loc="Solaria ➔ Adventurers' Guild Hall ➔ Contract Atrium",
            old_loc="Solaria ➔ The Boar's Tusk Tavern ➔ Hearthside Table"
        )

        names = [n["name"] for n in processed_npcs]

        # Valerius (formally registered party member) must travel
        self.assertIn("Valerius Ironclad", names)
        # Barkeep must stay behind
        self.assertNotIn("Tavern Barkeep", names)

    def test_explicit_recruitment_action_carries_patron(self):
        """Verify that an action explicitly inviting a patron promotes them to travel."""
        session = {
            "id": self.test_session_id,
            "scenario": "fantasy",
            "current_location": "Solaria ➔ The Boar's Tusk Tavern ➔ Hearthside Table",
            "current_npcs": [
                {"name": "Severus Stormblessed", "role": "Dwarf"},
                {"name": "Elderly Archivist"}
            ]
        }

        actions = [{"label": "Ask Severus Stormblessed to come with us to the Adventurers' Guild Hall"}]

        traveling, left_behind = game_engine.classify_scene_npcs(
            session,
            actions=actions,
            old_primary="The Boar's Tusk Tavern",
            dest_primary="Adventurers' Guild Hall"
        )

        traveling_names = [n["name"] for n in traveling]
        left_behind_names = [n["name"] for n in left_behind]

        self.assertIn("Severus Stormblessed", traveling_names)
        self.assertIn("Elderly Archivist", left_behind_names)

    def test_narrative_guest_departure(self):
        """Verify that npc_departures removes departing narrative guests from the scene."""
        session = {
            "id": self.test_session_id,
            "scenario": "fantasy",
            "current_location": "Solaria ➔ Adventurers' Guild Hall ➔ Contract Atrium",
            "current_npcs": [
                {"name": "Mara Vey"},
                {"name": "Guildmaster Elira Voss"}
            ]
        }

        llm_result = {
            "location": "Solaria ➔ Adventurers' Guild Hall ➔ Contract Atrium",
            "npcs_present": [{"name": "Mara Vey"}, {"name": "Guildmaster Elira Voss"}],
            "npc_departures": ["Mara Vey"]
        }

        processed_npcs = game_engine.process_scene_npcs(
            llm_result,
            session,
            new_loc="Solaria ➔ Adventurers' Guild Hall ➔ Contract Atrium",
            old_loc="Solaria ➔ Adventurers' Guild Hall ➔ Contract Atrium"
        )

        names = [n["name"] for n in processed_npcs]

        self.assertNotIn("Mara Vey", names)
        self.assertIn("Guildmaster Elira Voss", names)

    def test_go_alone_intent_leaves_companions_behind(self):
        """When player explicitly states 'going alone' or 'stay here', companions stay behind."""
        session = {
            "id": self.test_session_id,
            "scenario": "high_school_drama",
            "current_location": "Westlake Academy ➔ Rooftop ➔ Quiet Corner",
            "current_npcs": [
                {"name": "Zihan Moon", "hp": 100, "max_hp": 100, "role": "Companion"}
            ]
        }

        actions = [{"label": "Tell Zihan I'm going alone and head back down to the classroom"}]

        traveling, left_behind = game_engine.classify_scene_npcs(
            session,
            actions=actions,
            old_primary="Rooftop",
            dest_primary="Classroom 2-B"
        )

        traveling_names = [n["name"] for n in traveling]
        left_behind_names = [n["name"] for n in left_behind]

        self.assertNotIn("Zihan Moon", traveling_names)
        self.assertIn("Zihan Moon", left_behind_names)

    def test_non_formal_npc_with_hp_does_not_travel_without_invitation(self):
        """NPCs that have HP/stats but are not registered in formal party table must not automatically follow."""
        session = {
            "id": self.test_session_id,
            "scenario": "high_school_drama",
            "current_location": "Westlake Academy ➔ Rooftop ➔ Quiet Corner",
            "current_npcs": [
                {"name": "Zihan Moon", "hp": 100, "max_hp": 100, "role": "Companion"}
            ]
        }

        actions = [{"label": "Head back to the hallway to inspect the lockers"}]

        traveling, left_behind = game_engine.classify_scene_npcs(
            session,
            actions=actions,
            old_primary="Rooftop",
            dest_primary="Hallway"
        )

        traveling_names = [n["name"] for n in traveling]
        left_behind_names = [n["name"] for n in left_behind]

        self.assertNotIn("Zihan Moon", traveling_names)
        self.assertIn("Zihan Moon", left_behind_names)

    def test_sofia_departure_and_aftermath_memory_prose(self):
        """
        Verify that:
        Turn 1: Narrative describing Sofia departing the house removes Sofia from current_npcs.
        Turn 2: Aftermath prose describing lingering scent and memory does NOT re-inject Sofia.
        """
        session_turn1 = {
            "id": self.test_session_id,
            "scenario": "high_school_drama",
            "current_location": "Sakura Hill Residential Town ➔ Artemiusz's House ➔ Front Door",
            "current_npcs": [
                {"name": "Sofia Anderson", "hp": 1000, "max_hp": 1000, "role": "Peer"}
            ]
        }

        # Turn 1: Action result describes Sofia departing
        llm_turn1 = {
            "scene_title": "Departure",
            "outcome_narrative": "Artemiusz watches Sofia depart, the soft click of the front door signaling her exit and the return of a heavy, comfortable silence to the house.",
            "next_narrative": "He moves back through the quiet hallways, his footsteps echoing softly until he reaches the sanctuary of his bedroom.",
            "location": "Sakura Hill Residential Town ➔ Artemiusz's House ➔ Bedroom",
            "npcs_present": []
        }

        npcs_turn1 = game_engine.process_scene_npcs(
            llm_turn1,
            session_turn1,
            new_loc="Sakura Hill Residential Town ➔ Artemiusz's House ➔ Bedroom",
            old_loc="Sakura Hill Residential Town ➔ Artemiusz's House ➔ Front Door"
        )
        names_turn1 = [n["name"] for n in npcs_turn1]
        self.assertNotIn("Sofia Anderson", names_turn1)

        # Turn 2: Next turn in Bedroom. Prose mentions Sofia's lingering scent and memory of her.
        session_turn2 = {
            "id": self.test_session_id,
            "scenario": "high_school_drama",
            "current_location": "Sakura Hill Residential Town ➔ Artemiusz's House ➔ Bedroom",
            "current_npcs": []
        }

        # Add Sofia to contacts so prose scanner would normally detect her
        db.upsert_contact(
            self.test_session_id, character_id=0, npc_id="sofia_anderson",
            name="Sofia Anderson", basic_info={"location": "Sakura Hill Residential Town ➔ Sofia's House", "role": "Peer"}
        )

        llm_turn2 = {
            "scene_title": "Quiet Afterglow",
            "outcome_narrative": "He sinks onto the bed, the mattress dipping beneath his weight as he lies back and stares up at the ceiling. The silence is not empty; it is filled with the lingering resonance of their intimacy.",
            "next_narrative": "The air here still carries a faint, lingering scent of Sofia's presence—a mixture of warmth and a subtle, clean fragrance that clings to the sheets. The house feels larger and quieter now that she is gone.",
            "location": "Sakura Hill Residential Town ➔ Artemiusz's House ➔ Bedroom",
            "npcs_present": []
        }

        npcs_turn2 = game_engine.process_scene_npcs(
            llm_turn2,
            session_turn2,
            new_loc="Sakura Hill Residential Town ➔ Artemiusz's House ➔ Bedroom",
            old_loc="Sakura Hill Residential Town ➔ Artemiusz's House ➔ Bedroom"
        )
        names_turn2 = [n["name"] for n in npcs_turn2]
        self.assertNotIn("Sofia Anderson", names_turn2)

    def test_player_dismissal_action_removes_guest(self):
        """Verify that player action to dismiss a guest / ask them to head home cleanly removes them."""
        session = {
            "id": self.test_session_id,
            "scenario": "high_school_drama",
            "current_location": "Sakura Hill Residential Town ➔ Artemiusz's House ➔ Living Room",
            "current_npcs": [
                {"name": "Sofia Anderson", "role": "Peer"}
            ]
        }

        actions = [{"label": "Ask Sofia to head home as it's getting late"}]
        llm_result = {
            "scene_title": "Goodnight",
            "outcome_narrative": "Artemiusz walks Sofia to the entryway.",
            "next_narrative": "She smiles softly and steps outside into the evening cool.",
            "location": "Sakura Hill Residential Town ➔ Artemiusz's House ➔ Living Room",
            "npcs_present": [{"name": "Sofia Anderson"}]  # Even if LLM erroneously kept her in npcs_present
        }

        processed = game_engine.process_scene_npcs(
            llm_result,
            session,
            new_loc="Sakura Hill Residential Town ➔ Artemiusz's House ➔ Living Room",
            old_loc="Sakura Hill Residential Town ➔ Artemiusz's House ➔ Living Room",
            actions=actions
        )
        names = [n["name"] for n in processed]
        self.assertNotIn("Sofia Anderson", names)

    def test_anti_teleportation_false_positive_prevention(self):
        """
        Verify that a quiet bystander or companion is NOT removed when the LLM
        merely omitted them from npcs_present (no departure occurred).
        """
        session = {
            "id": self.test_session_id,
            "scenario": "fantasy",
            "current_location": "Solaria ➔ Royal Archives ➔ Reading Desk",
            "current_npcs": [
                {"name": "Elderly Archivist", "role": "Librarian"},
                {"name": "Elena Vance", "role": "Researcher"}
            ]
        }

        # LLM generated a scene focusing on the ledger, omitting Elena Vance from npcs_present
        llm_result = {
            "scene_title": "Deciphering the Runes",
            "outcome_narrative": "Artemiusz studies the ancient parchment under the candlelight.",
            "next_narrative": "The archivist nods approvingly as you make notes.",
            "location": "Solaria ➔ Royal Archives ➔ Reading Desk",
            "npcs_present": [{"name": "Elderly Archivist"}]  # Elena was omitted by model omission
        }

        processed = game_engine.process_scene_npcs(
            llm_result,
            session,
            new_loc="Solaria ➔ Royal Archives ➔ Reading Desk",
            old_loc="Solaria ➔ Royal Archives ➔ Reading Desk"
        )
        names = [n["name"] for n in processed]

        # Elena Vance must still be retained because no affirmative departure occurred
        self.assertIn("Elderly Archivist", names)
        self.assertIn("Elena Vance", names)

    def test_permanent_party_companion_immunity_from_guest_departure(self):
        """Verify that formal party members registered in session_party_npcs are never removed by guest departure text."""
        # Register Glorfindel as a formal party companion
        db.set_session_party_npcs(self.test_session_id, [{"name": "Glorfindel", "hp": 200, "max_hp": 200, "role": "Companion"}])

        session = {
            "id": self.test_session_id,
            "scenario": "fantasy",
            "current_location": "Solaria ➔ Tavern ➔ Common Room",
            "current_npcs": [
                {"name": "Glorfindel", "hp": 200, "max_hp": 200, "role": "Companion"},
                {"name": "Visiting Merchant", "role": "Guest"}
            ]
        }

        llm_result = {
            "scene_title": "Tavern Farewells",
            "outcome_narrative": "The visiting merchant departs into the snowy night.",
            "next_narrative": "Glorfindel cleans his blade by the hearth.",
            "location": "Solaria ➔ Tavern ➔ Common Room",
            "npc_departures": ["Visiting Merchant", "Glorfindel"],  # LLM erroneously included companion in npc_departures
            "npcs_present": []
        }

        processed = game_engine.process_scene_npcs(
            llm_result,
            session,
            new_loc="Solaria ➔ Tavern ➔ Common Room",
            old_loc="Solaria ➔ Tavern ➔ Common Room"
        )
        names = [n["name"] for n in processed]

        # Visiting Merchant departs, but Glorfindel is immune because he is a formal party member
        self.assertNotIn("Visiting Merchant", names)
        self.assertIn("Glorfindel", names)

    def test_date_companion_travels_between_establishments_while_ambient_patrons_stay_behind(self):
        """
        Verify that when switching location from Café Monolith to Convenience Store:
        - Maya Anderson (dialogue partner on a date) travels with Artemiusz into the new primary establishment.
        - Barista Dave (ambient cafe patron) remains behind at Café Monolith.
        """
        # Register Maya as a romance contact
        db.upsert_contact(
            self.test_session_id,
            character_id=0,
            npc_id="maya_anderson",
            name="Maya Anderson",
            delta_score=15,
            basic_info={"location": "Komorebi Commercial Strip ➔ Café Monolith", "role": "Student"},
            track="romance"
        )

        session = {
            "id": self.test_session_id,
            "scenario": "high_school_drama",
            "current_location": "Komorebi Commercial Strip ➔ Café Monolith ➔ Corner Table",
            "current_npcs": [
                {"name": "Maya Anderson", "role": "Student"},
                {"name": "Barista Dave", "role": "Barista"}
            ],
            "dialogue_partners": ["Maya Anderson"],
            "dialogue_partner": "Maya Anderson",
            "history": [
                "[Success] Artemiusz: Suggest having coffee at Café Monolith -> Maya smiles and agrees to the date.",
                "[Success] Artemiusz: Enjoy coffee together at a corner table -> Maya blushes happily."
            ]
        }

        actions = [{"label": "Step out into the cool evening air together toward the convenience store"}]
        llm_result = {
            "scene_title": "The Quiet Rhythm of the Street",
            "narrative": (
                "The neon lights of the Komorebi Commercial Strip blur into a soft, colorful haze as they move toward the vintage bookstore. "
                "Maya's grip on Artemiusz's hand tightens slightly, a small but deliberate gesture of affection that anchors her to him amidst the flow of pedestrians. "
                "As they walk, Maya glances up at him, her amethyst eyes reflecting the shimmering lights of the storefronts. "
                "'It's actually nice...' she murmurs, her voice barely above a whisper but clear and sincere."
            ),
            "location": "Komorebi Commercial Strip ➔ Convenience Store ➔ Bookstore Path",
            "npcs_present": [{"name": "Maya Anderson"}],
            "entity_audit": {
                "present_named_characters": ["Maya Anderson"],
                "speaking_characters": ["Maya Anderson"]
            }
        }

        processed = game_engine.process_scene_npcs(
            llm_result,
            session,
            new_loc="Komorebi Commercial Strip ➔ Convenience Store ➔ Bookstore Path",
            old_loc="Komorebi Commercial Strip ➔ Café Monolith ➔ Corner Table",
            actions=actions
        )
        names = [n["name"] if isinstance(n, dict) else n for n in processed]

        # Maya must be present (tracked by character tracker)
        self.assertIn("Maya Anderson", names)
        # Barista Dave must stay behind
        self.assertNotIn("Barista Dave", names)

    def test_uninvited_dialogue_partner_not_carried_or_reinjected_on_departure_to_home(self):
        """
        Verify that leaving an active dialogue partner (e.g. Denise Yamada) at the Student Council Office
        to head home does NOT carry her via has_narrative_continuity_bridge or re-inject her via known_contacts,
        even when outcome_narrative mentions her waving/standing at the old location.
        """
        db.upsert_contact(
            self.test_session_id,
            character_id=0,
            npc_id="denise_yamada",
            name="Denise Yamada",
            delta_score=10,
            basic_info={"location": "", "role": "Student Council President"},
            track="platonic",
        )

        old_loc = "St. Michael Academy ➔ Student Council Office ➔ President's Desk"
        new_loc = "Sakura Hill Residential District ➔ Artem's House ➔ Living Room"

        session = {
            "id": self.test_session_id,
            "scenario": "high_school_drama",
            "current_location": old_loc,
            "current_npcs": [
                {"name": "Denise Yamada", "role": "Student Council President"},
                {"name": "Random Bystander", "role": "Student"},
            ],
            "dialogue_partners": ["Denise Yamada"],
            "dialogue_partner": "Denise Yamada",
            "history": ["[Success] Artem: Discuss the budget with Denise -> Denise nods thoughtfully."],
        }

        actions = [{"label": "Head back home to Artem's House for the evening"}]
        llm_result = {
            "outcome_narrative": "Denise Yamada stands behind her desk and waves as Artem steps out of the office.",
            "next_narrative": "Artem arrives at his quiet living room as evening settles over the neighborhood.",
            "location": new_loc,
            "npcs_present": [{"name": "Denise Yamada"}],  # Hallucinated carry-over by LLM
        }

        processed = game_engine.process_scene_npcs(
            llm_result,
            session,
            new_loc=new_loc,
            old_loc=old_loc,
            actions=actions,
        )
        names = [n["name"] if isinstance(n, dict) else n for n in processed]
        self.assertNotIn("Denise Yamada", names)
        self.assertNotIn("Random Bystander", names)

        # Known contact Denise should have her blank location grounded to old_loc (not new_loc)
        denise_c = db.get_contact(self.test_session_id, "denise_yamada")
        self.assertEqual(denise_c["basic_info"].get("location"), old_loc)

        # Unengaged Random Bystander must NOT be created in contacts
        bystander_c = db.get_contact(self.test_session_id, "random_bystander")
        self.assertIsNone(bystander_c)

    def test_private_conversation_alone_does_not_trigger_solo_travel_intent(self):
        """Verify that 'speak with Denise alone' is not misclassified as solo travel."""
        from mechanics.world.mobility import is_solo_travel_intent

        self.assertFalse(is_solo_travel_intent([{"label": "Ask Denise to speak with me alone in the council room"}]))
        self.assertTrue(is_solo_travel_intent([{"label": "Excuse yourself and head to homeroom class alone"}]))
        self.assertFalse(
            is_solo_travel_intent([{"label": "Thank Sofia and excuse yourself to head home together"}])
        )


if __name__ == "__main__":
    unittest.main()


