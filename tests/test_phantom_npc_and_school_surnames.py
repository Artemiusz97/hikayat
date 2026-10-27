from __future__ import annotations
import pytest
import namegen
import game_engine
from game_engine.npcs.reconciliation import process_scene_npcs


class TestPhantomNpcAndSchoolSurnames:
    def test_high_school_names_always_have_surname(self):
        """Verifies that high school person name generation always produces first + surname."""
        for _ in range(100):
            name = namegen.generate_person_name("high_school_drama", gender="female")
            parts = name.split()
            assert len(parts) >= 2, f"Expected full name with surname, got: {name}"

        for _ in range(100):
            name = namegen.generate_person_name("high_school_drama", gender="male")
            parts = name.split()
            assert len(parts) >= 2, f"Expected full name with surname, got: {name}"

    def test_phantom_npc_filtered_when_not_in_narrative_prose(self):
        """Verifies that a brand-new NPC hallucinated in npcs_present by the LLM is dropped if absent from the narrative."""
        session = {
            "id": 999999,
            "scenario": "high_school_drama",
            "current_location": "School Grounds ➔ Central Courtyard ➔ Old Cherry Tree",
            "current_npcs": [{"name": "Seo-ah Vance"}, {"name": "Kazuya Halloway"}],
            "turn_order": [],
            "party": [],
        }

        result = {
            "npcs_present": [
                {"name": "Seo-ah Vance"},
                {"name": "Kazuya Halloway"},
                {"name": "Manon Davis"},
            ],
            "outcome_narrative": "You shift your textbook and speak with Seo-ah Vance. In the background, Kazuya Halloway listens closely.",
            "next_narrative": "Seo-ah smirks and swishes her fennec tail. Kazuya checks his watch.",
            "location": "School Grounds ➔ Central Courtyard ➔ Old Cherry Tree",
            "npc_departures": [],
        }

        final_npcs = process_scene_npcs(
            result,
            session,
            new_loc="School Grounds ➔ Central Courtyard ➔ Old Cherry Tree",
            old_loc="School Grounds ➔ Central Courtyard ➔ Old Cherry Tree",
            actions=[],
        )

        final_names = [game_engine._get_npc_name(n) for n in final_npcs]
        assert "Seo-ah Vance" in final_names
        assert "Kazuya Halloway" in final_names
        assert "Manon Davis" not in final_names, f"Phantom NPC should have been filtered out, got: {final_names}"

    def test_legitimate_new_npc_kept_when_present_in_narrative_prose(self):
        """Verifies that when a new character is actually introduced in the narrative and structured npcs_present, they are retained."""
        session = {
            "id": 999999,
            "scenario": "high_school_drama",
            "current_location": "School Grounds ➔ Central Courtyard ➔ Old Cherry Tree",
            "current_npcs": [{"name": "Seo-ah Vance"}],
            "turn_order": [],
            "party": [],
        }

        result = {
            "npcs_present": [
                {"name": "Seo-ah Vance"},
                {"name": "Gary Davis"},
            ],
            "outcome_narrative": "You talk to Seo-ah Vance.",
            "next_narrative": "A quiet sophomore named Gary Davis walks over and nervously hands a club brochure to Seo-ah.",
            "location": "School Grounds ➔ Central Courtyard ➔ Old Cherry Tree",
            "npc_departures": [],
        }

        final_npcs = process_scene_npcs(
            result,
            session,
            new_loc="School Grounds ➔ Central Courtyard ➔ Old Cherry Tree",
            old_loc="School Grounds ➔ Central Courtyard ➔ Old Cherry Tree",
            actions=[],
        )

        final_names = [game_engine._get_npc_name(n) for n in final_npcs]
        assert "Seo-ah Vance" in final_names
        assert "Gary Davis" in final_names, f"Legitimate narrative NPC should be retained, got: {final_names}"

    def test_dialogue_partner_title_and_surname_disambiguation(self):
        """Verifies that is_dialogue_partner does not conflate characters with different titles/genders sharing a surname."""
        from mechanics.world.mobility import is_dialogue_partner
        assert not is_dialogue_partner("Ruoxi Kobayashi", ["Mr. Sebastian Kobayashi"])
        assert not is_dialogue_partner("Mr. Sebastian Kobayashi", ["Ruoxi Kobayashi"])
        assert is_dialogue_partner("Mr. Sebastian Kobayashi", ["Sebastian Kobayashi"])
        assert is_dialogue_partner("Mr. Sebastian Kobayashi", ["Mr. Kobayashi"])

    def test_school_faculty_reconciliation_preserves_title_over_student(self):
        """Verifies that when faculty members are staged in Chemistry Lab, reconciliation preserves faculty titles over homeroom students sharing surnames."""
        session = {
            "id": 999999,
            "scenario": "high_school_drama",
            "current_location": "Shiranui Senior High ➔ Chemistry & Science Lab ➔ Main Area",
            "current_npcs": [{"name": "Henry Sterling", "role": "Class Representative"}],
            "turn_order": [12345],
            "party": [],
        }

        result = {
            "npcs_present": [
                {"name": "Dr. Kento Satou", "role": "Chemistry Teacher"},
                {"name": "Mr. Sebastian Kobayashi", "role": "Computer Science & Robotics Teacher"},
            ],
            "outcome_narrative": "You step into the Chemistry Lab. Dr. Kento Satou stands near the fume hoods scribbling notes.",
            "next_narrative": "Mr. Sebastian Kobayashi gestures toward the chemical demonstration wreckage.",
            "location": "Shiranui Senior High ➔ Chemistry & Science Lab ➔ Main Area",
            "npc_departures": [],
        }

        import db
        orig_roster = db.get_school_roster
        orig_contacts = db.get_contacts
        try:
            db.get_school_roster = lambda sess_id: [
                {"name": "Dr. Kento Satou", "role": "Chemistry Teacher", "primary_facility": "Shiranui Senior High ➔ Chemistry & Science Lab ➔ Lab Workbenches"},
                {"name": "Mr. Sebastian Kobayashi", "role": "Computer Science & Robotics Teacher", "primary_facility": "Shiranui Senior High ➔ Chemistry & Science Lab ➔ Lab Workbenches"},
                {"name": "Satou Kento", "role": "Art & Set Designer", "primary_facility": "Shiranui Senior High ➔ Room 204 (Homeroom) ➔ Main Area"},
                {"name": "Kobayashi Ryota", "role": "Art Club Member", "primary_facility": "Shiranui Senior High ➔ Room 204 (Homeroom) ➔ Main Area"},
            ]
            db.get_contacts = lambda sess_id, char_id=None: [
                {"name": "Henry Sterling", "location": "Shiranui Senior High ➔ Room 204 (Homeroom) ➔ Main Area"},
                {"name": "Satou Kento", "location": "Shiranui Senior High ➔ Room 204 (Homeroom) ➔ Main Area"},
                {"name": "Kobayashi Ryota", "location": "Shiranui Senior High ➔ Room 204 (Homeroom) ➔ Main Area"},
            ]

            final_npcs = process_scene_npcs(
                result,
                session,
                new_loc="Shiranui Senior High ➔ Chemistry & Science Lab ➔ Main Area",
                old_loc="Shiranui Senior High ➔ Room 204 (Homeroom) ➔ Main Area",
                actions=["approach Kobayashi"],
            )
            final_names = [game_engine._get_npc_name(n) for n in final_npcs]
            assert "Dr. Kento Satou" in final_names
            assert "Mr. Sebastian Kobayashi" in final_names
            assert "Satou Kento" not in final_names
            assert "Kobayashi Ryota" not in final_names
        finally:
            db.get_school_roster = orig_roster
            db.get_contacts = orig_contacts

    def test_spatial_or_object_homonym_names_rejected_in_namegen(self):
        """Verifies cross-cultural namegen never produces architectural/place homonyms like 'Long Hall' or 'West Wing'."""
        assert namegen.is_spatial_or_object_homonym_name("Long Hall")
        assert namegen.is_spatial_or_object_homonym_name("West Wing")
        assert namegen.is_spatial_or_object_homonym_name("North Gate")
        assert namegen.is_spatial_or_object_homonym_name("Stone Wall")
        assert not namegen.is_spatial_or_object_homonym_name("Marcus Hall")
        assert not namegen.is_spatial_or_object_homonym_name("Long Chen")
        assert not namegen.is_spatial_or_object_homonym_name("Sofia Anderson")

        for seed_idx in range(250):
            generated = namegen.generate_person_name("urban_anomalies", gender="male", cross_culture_chance=1.0, seed=seed_idx)
            assert not namegen.is_spatial_or_object_homonym_name(generated), f"Generated homonym name: {generated}"
            with_hall = namegen.generate_person_name_with_surname("Hall", scenario="urban_anomalies", gender="male", cross_culture_chance=1.0, seed=seed_idx)
            assert not namegen.is_spatial_or_object_homonym_name(with_hall), f"Generated homonym surname combo: {with_hall}"
