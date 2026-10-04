"""
Unit tests for family lineage synchronization, romance intent scoping, and dynamic social relations.
"""
import unittest
import tempfile
import os
import shutil
import db
import mechanics.social.genealogy as genealogy
import game_engine

class TestFamilySyncAndDynamicRomance(unittest.TestCase):
    def setUp(self):
        db.init_db()
        with db.get_conn() as conn:
            conn.execute("DELETE FROM contacts")
            conn.execute("DELETE FROM sessions")

    def tearDown(self):
        with db.get_conn() as conn:
            conn.execute("DELETE FROM contacts")
            conn.execute("DELETE FROM sessions")

    def test_romance_milestone_strictly_scoped_to_target_npc(self):
        """
        Verify that confessing to Maya Anderson does NOT turn Sofia Anderson or Zihan Moon
        into romantic interests even when they are present or mentioned in narrative text.
        """
        sess_id = db.create_session(host_user_id=1, mode="solo", capacity=1, verbosity="normal", dialogue_mode="balanced", image_gen_enabled=False, scenario="high_school_drama")
        char_id = 101

        # 1. Create 3 contacts: Maya (platonic), Sofia (platonic), Zihan (platonic)
        db.upsert_contact(sess_id, "maya_anderson", "Maya Anderson", character_id=char_id, track="platonic", delta_score=80)
        db.upsert_contact(sess_id, "sofia_anderson", "Sofia Anderson", character_id=char_id, track="platonic", delta_score=80)
        db.upsert_contact(sess_id, "zihan_moon", "Zihan Moon", character_id=char_id, track="platonic", delta_score=75)

        session = db.get_session(sess_id)
        party = [({"id": char_id, "name": "Artemiusz", "user_id": 1}, {"id": 1, "username": "player"})]

        # 2. Player takes action specifically confessing to Maya Anderson
        actions = [{
            "label": "[Romance] Confess your feelings and ask Maya Anderson to be your girlfriend",
            "intent": "romantic_confession",
            "target_npc": "Maya Anderson",
            "check": {"succeeded": True, "tier": "SUCCESS"}
        }]

        # Narrative text contains Sofia Anderson and Zihan Moon mentioned in the background
        outcome = {
            "narrative": "Artemiusz looks into Maya Anderson's eyes and confesses his feelings. Maya blushes and agrees to be his girlfriend. Across the hall, Sofia Anderson and Zihan Moon walk past, smiling at the commotion.",
            "relationship_updates": [
                {"npc_name": "Maya Anderson", "delta_score": 10, "milestone_event": "confession"}
            ]
        }

        # Process outcome
        game_engine.apply_outcome(sess_id, party, outcome, actions=actions)

        # 3. Assert Maya became romantic
        maya = db.get_contact(sess_id, "maya_anderson", character_id=char_id)
        self.assertEqual(maya["track"], "romantic")
        self.assertTrue(any("Confessed feelings" in str(m) for m in maya.get("intimate_memories", [])))

        # 4. Assert Sofia and Zihan REMAIN STRICTLY PLATONIC with NO confession memories
        sofia = db.get_contact(sess_id, "sofia_anderson", character_id=char_id)
        self.assertEqual(sofia["track"], "platonic")
        self.assertFalse(any("Confessed feelings" in str(m) for m in sofia.get("intimate_memories", [])))

        zihan = db.get_contact(sess_id, "zihan_moon", character_id=char_id)
        self.assertEqual(zihan["track"], "platonic")
        self.assertFalse(any("Confessed feelings" in str(m) for m in zihan.get("intimate_memories", [])))

    def test_family_codex_full_synchronization(self):
        """
        Verify that Sofia Anderson and Maya Anderson share identical parents (Father & Mother names,
        careers, statuses, and races) and have consistent sibling rosters.
        """
        sess_id = db.create_session(host_user_id=1, mode="solo", capacity=1, verbosity="normal", dialogue_mode="balanced", image_gen_enabled=False, scenario="high_school_drama")
        char_id = 102

        db.upsert_contact(sess_id, "sofia_anderson", "Sofia Anderson", character_id=char_id,
                          basic_info={"role": "Robotics Apprentice", "grade": "Junior", "sibling_name": "Maya Anderson"},
                          race="beastfolk:fox", appearance={"eyes": "Amber", "hair": "Golden-Blonde", "fur": "Golden-Blonde Fur"})

        db.upsert_contact(sess_id, "maya_anderson", "Maya Anderson", character_id=char_id,
                          basic_info={"role": "Student", "grade": "Freshman", "sibling_name": "Sofia Anderson"},
                          race="beastfolk:fox", appearance={"eyes": "Amber", "hair": "Golden-Blonde", "fur": "Golden-Blonde Fur"})

        sofia = db.get_contact(sess_id, "sofia_anderson", char_id)
        maya = db.get_contact(sess_id, "maya_anderson", char_id)

        sofia_rel = genealogy.ensure_contact_relations(sofia, session_id=sess_id, scenario="high_school_drama")
        maya_rel = genealogy.ensure_contact_relations(maya, session_id=sess_id, scenario="high_school_drama")

        # Parents check
        s_parents = [m for m in sofia_rel["family"] if m["relation"] in ("Father", "Mother")]
        m_parents = [m for m in maya_rel["family"] if m["relation"] in ("Father", "Mother")]

        self.assertEqual(len(s_parents), 2)
        self.assertEqual(len(m_parents), 2)

        for sp, mp in zip(s_parents, m_parents):
            self.assertEqual(sp["name"], mp["name"])
            self.assertEqual(sp["occupation"], mp["occupation"])
            self.assertEqual(sp["race"], mp["race"])
            self.assertEqual(sp["status"], mp["status"])

        # Sibling relative relation check
        sofia_sibs = [m for m in sofia_rel["family"] if m["relation"] not in ("Father", "Mother")]
        maya_sibs = [m for m in maya_rel["family"] if m["relation"] not in ("Father", "Mother")]

        self.assertTrue(any(s["first_name"] == "Maya" and "Sister" in s["relation"] for s in sofia_sibs))
        self.assertTrue(any(s["first_name"] == "Sofia" and s["relation"] == "Older Sister" for s in maya_sibs))

    def test_dynamic_relationship_track_and_social_updates(self):
        """
        Verify that relationship track can transition back and forth and dynamic mutations take effect.
        """
        sess_id = db.create_session(host_user_id=1, mode="solo", capacity=1, verbosity="normal", dialogue_mode="balanced", image_gen_enabled=False, scenario="high_school_drama")
        char_id = 103

        # Start platonic
        db.upsert_contact(sess_id, "sofia_anderson", "Sofia Anderson", character_id=char_id, track="platonic", delta_score=50)
        c = db.get_contact(sess_id, "sofia_anderson", char_id)
        self.assertEqual(c["track"], "platonic")

        # Promote to romantic
        db.update_contact_track(sess_id, "sofia_anderson", "romantic", character_id=char_id)
        c_rom = db.get_contact(sess_id, "sofia_anderson", char_id)
        self.assertEqual(c_rom["track"], "romantic")
        rel_rom = genealogy.ensure_contact_relations(c_rom, session_id=sess_id, scenario="high_school_drama")
        self.assertEqual(rel_rom["romance"]["status"], "In a Relationship")

        # Demote back to platonic (break up)
        db.update_contact_track(sess_id, "sofia_anderson", "platonic", character_id=char_id)
        c_plat = db.get_contact(sess_id, "sofia_anderson", char_id)
        self.assertEqual(c_plat["track"], "platonic")
        rel_plat = genealogy.ensure_contact_relations(c_plat, session_id=sess_id, scenario="high_school_drama")
        self.assertEqual(rel_plat["romance"]["status"], "Single")
        self.assertIsNone(rel_plat["romance"]["current_partner"])

if __name__ == '__main__':
    unittest.main()
