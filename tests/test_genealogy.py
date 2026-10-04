"""
Unit tests for the Genealogy & Social Relations Engine (mechanics/genealogy.py).
Tests reverse-genealogy, interracial inheritance, surname consistency, species locking,
intercourse_experience decoupling, and 3-tier progressive information disclosure.
"""
import unittest
import tempfile
import os
import shutil
import db
import mechanics.social.genealogy as genealogy
from mechanics.social.relationships import get_unlocked_info_level


class TestGenealogy(unittest.TestCase):
    def test_extract_species_from_race(self):
        self.assertEqual(genealogy.extract_species_from_race("beastfolk:fox"), "fox")
        self.assertEqual(genealogy.extract_species_from_race("half_beast:cat"), "cat")
        self.assertEqual(genealogy.extract_species_from_race("hybrid:wolf"), "wolf")
        self.assertEqual(genealogy.extract_species_from_race("Fox-Beastfolk"), "fox")
        self.assertEqual(genealogy.extract_species_from_race("human"), "")
        self.assertEqual(genealogy.extract_species_from_race("elf"), "")

    def test_extract_surname_and_firstname(self):
        self.assertEqual(genealogy.extract_surname_and_firstname("Sofia Anderson"), ("Sofia", "Anderson"))
        self.assertEqual(genealogy.extract_surname_and_firstname("Marcus"), ("Marcus", ""))
        self.assertEqual(genealogy.extract_surname_and_firstname("Elena Vance Anderson"), ("Elena", "Vance Anderson"))

    def test_reverse_generate_parents_surname_and_phenotype(self):
        child_appearance = {
            "eyes": "Amber",
            "hair": "Short Ponytail Golden-Blonde",
            "fur": "Golden-Blonde Fur"
        }
        father, mother = genealogy.reverse_generate_parents(
            child_race="beastfolk:fox",
            child_appearance=child_appearance,
            child_surname="Anderson",
            scenario="high_school_drama",
            hash_val=12345
        )

        # Surname checks
        self.assertEqual(father["surname"], "Anderson")
        self.assertIn("Anderson", father["name"])
        self.assertIn("Anderson", mother["name"])
        self.assertTrue("née" in mother["name"] or mother["surname"] == "Anderson")

        # Species consistency
        f_species = genealogy.extract_species_from_race(father["race"])
        m_species = genealogy.extract_species_from_race(mother["race"])
        if father["race"] != "human":
            self.assertEqual(f_species, "fox")
        if mother["race"] != "human":
            self.assertEqual(m_species, "fox")

        # Features consistency
        self.assertIn("Amber", father["features"])
        self.assertIn("Amber", mother["features"])

    def test_human_beastfolk_hybrid_sibling_split(self):
        """Tests that Human + Beastfolk cross rolls only Human, Half-Beast, or Beastfolk of the same species."""
        parent1_race = "human"
        parent2_race = "beastfolk:fox"
        species = "fox"

        races_seen = set()
        for seed in range(30):
            r = genealogy.roll_sibling_race(parent1_race, parent2_race, species, seed)
            races_seen.add(r)
            # Verify strict species locking (fox never turns into cat or wolf)
            if r != "human":
                self.assertIn("fox", r)
                self.assertNotIn("cat", r)
                self.assertNotIn("wolf", r)

        self.assertIn("human", races_seen)
        self.assertIn("half_beast:fox", races_seen)
        self.assertIn("beastfolk:fox", races_seen)

    def test_other_interracial_sibling_split(self):
        """Tests that non-hybrid interracial crosses (e.g. Elf + Human) split 50/50 between parent races."""
        parent1_race = "elf"
        parent2_race = "human"

        seen = set()
        for seed in range(20):
            r = genealogy.roll_sibling_race(parent1_race, parent2_race, "", seed)
            seen.add(r)
            self.assertIn(r, ("elf", "human"))

        self.assertEqual(seen, {"elf", "human"})

    def test_relationship_status_intercourse_experience_decoupling(self):
        """Tests that intercourse_experience status and romantic relationship status remain strictly decoupled."""
        # 1. Virgin contact with an ex-partner generated
        virgin_contact = {
            "name": "Hana Vance",
            "gender": "female",
            "appearance": {"predetermined_intercourse_experience": "virgin"},
            "intimate_memories": []
        }
        status = genealogy.generate_relationship_status(virgin_contact, scenario="fantasy", hash_val=42)
        self.assertIsInstance(status, dict)
        # Even if they have exes or current partner, predetermined_intercourse_experience remains untouched
        self.assertEqual(virgin_contact["appearance"]["predetermined_intercourse_experience"], "virgin")

        # 2. Non-virgin contact with past intimate partner synchronizes into exes
        non_virgin_contact = {
            "name": "Sofia Anderson",
            "gender": "female",
            "appearance": {"predetermined_intercourse_experience": "non_virgin"},
            "intimate_memories": ["Past History: Had intercourse during a relationship with 'Marcus Vance' (Former Classmate)"]
        }
        status_synced = genealogy.generate_relationship_status(non_virgin_contact, scenario="high_school_drama", hash_val=99)
        self.assertGreaterEqual(len(status_synced["ex_partners"]), 1)
        self.assertTrue(any("Marcus Vance" in ex["name"] for ex in status_synced["ex_partners"]))

    def test_information_disclosure_filtering(self):
        """Tests 3-tier information disclosure for relations."""
        relations = {
            "family": [
                {"relation": "Father", "name": "Marcus Anderson", "race": "beastfolk:fox", "status": "Alive", "occupation": "Coach"},
                {"relation": "Mother", "name": "Elena Anderson", "race": "beastfolk:fox", "status": "Alive", "occupation": "Doctor"},
                {"relation": "Older Brother", "name": "Leo Anderson", "race": "beastfolk:fox", "status": "Alive", "occupation": "Student"}
            ],
            "romance": {
                "status": "In a Relationship",
                "current_partner": {"name": "Adrian Reed", "role": "Student"},
                "secret_partner": {"name": "Damian Cole", "role": "Bad Boy"},
                "ex_partners": [{"name": "Marcus Vance", "role": "Ex"}]
            },
            "friends": [{"name": "Maya Sterling", "role": "Co-Captain", "closeness": "Close Friend"}],
            "rivals": [{"name": "Cassandra Cross", "role": "Rival Captain", "type": "Track Rival"}]
        }

        # Level 1 Disclosure (Score 0-30)
        d1 = genealogy.format_relations_for_disclosure(relations, info_level=1, debug_reveal=False)
        self.assertFalse(d1["family"]["revealed"])
        self.assertIn("🔒", d1["family"]["locked_message"])
        self.assertFalse(d1["romance"]["revealed"])
        self.assertIsNone(d1["romance"]["secret_partner"])
        self.assertEqual(d1["romance"]["ex_partners"], [])
        self.assertFalse(d1["friends"]["revealed"])
        self.assertFalse(d1["rivals"]["revealed"])

        # Level 2 Disclosure (Score 31-70)
        d2 = genealogy.format_relations_for_disclosure(relations, info_level=2, debug_reveal=False)
        self.assertFalse(d2["family"]["revealed"])
        self.assertTrue(d2["romance"]["revealed"])
        self.assertTrue(d2["romance"]["secret_partner"]["locked"])
        self.assertTrue(d2["romance"]["ex_partners"][0]["locked"])
        self.assertTrue(d2["friends"]["revealed"])
        self.assertTrue(d2["rivals"]["revealed"])

        # Level 3 Disclosure (Score 71+)
        d3 = genealogy.format_relations_for_disclosure(relations, info_level=3, debug_reveal=False)
        self.assertTrue(d3["family"]["revealed"])
        self.assertEqual(len(d3["family"]["members"]), 3)
        self.assertTrue(d3["romance"]["revealed"])
        self.assertEqual(d3["romance"]["secret_partner"]["name"], "Damian Cole")
        self.assertEqual(d3["romance"]["ex_partners"][0]["name"], "Marcus Vance")
        self.assertTrue(d3["friends"]["revealed"])
        self.assertTrue(d3["rivals"]["revealed"])

        # Debug reveal flag overrides any level to Level 3
        d_debug = genealogy.format_relations_for_disclosure(relations, info_level=1, debug_reveal=True)
        self.assertTrue(d_debug["family"]["revealed"])
        self.assertEqual(d_debug["romance"]["secret_partner"]["name"], "Damian Cole")

    def test_db_contact_relations_persistence(self):
        """Tests that db.py loads and persists relations."""
        sess_id = db.create_session(host_user_id=1, mode="solo", capacity=1, verbosity="normal", dialogue_mode="balanced", image_gen_enabled=False, scenario="high_school_drama")
        try:
            db.upsert_contact(
                session_id=sess_id,
                character_id=1,
                npc_id="sofia_anderson",
                name="Sofia Anderson",
                basic_info={"role": "Club President", "description": "Athletic fox girl."},
                delta_score=75,
                track="platonic",
                race="beastfolk:fox",
                gender="female",
                appearance={"eyes": "Amber", "hair": "Golden-Blonde", "fur": "Golden-Blonde Fur"}
            )

            contacts = db.get_contacts(sess_id, character_id=1)
            self.assertEqual(len(contacts), 1)
            loaded = contacts[0]
            self.assertIn("relations", loaded)
            self.assertIn("family", loaded["relations"])
            self.assertGreaterEqual(len(loaded["relations"]["family"]), 2)

            father = loaded["relations"]["family"][0]
            self.assertIn("Anderson", father["name"])
            self.assertIn(father["race"], ("beastfolk:fox", "human"))
        finally:
            with db.get_conn() as conn:
                db.core._delete_session_records(conn, sess_id)

    def test_player_interest_or_single_suppresses_random_current_partner(self):
        """Verify that contacts with high score, romantic track, or explicitly single never get an auto-generated partner."""
        contact_romantic = {
            "name": "Maya Anderson",
            "gender": "female",
            "relationship_score": 50,
            "track": "romantic",
            "appearance": {"intercourse_experience": "virgin"}
        }
        rom_status = genealogy.generate_relationship_status(contact_romantic, scenario="high_school_drama", hash_val=0)
        self.assertIsNotNone(rom_status["current_partner"])
        self.assertEqual(rom_status["current_partner"]["name"], "Player")
        self.assertEqual(rom_status["status"], "In a Relationship")

        contact_high_score = {
            "name": "Maya Anderson",
            "gender": "female",
            "relationship_score": 45,
            "track": "platonic",
            "appearance": {"intercourse_experience": "virgin"}
        }
        rom_status_2 = genealogy.generate_relationship_status(contact_high_score, scenario="high_school_drama", hash_val=0)
        self.assertIsNone(rom_status_2["current_partner"])
        self.assertEqual(rom_status_2["status"], "Single")


    def test_sibling_family_synchronization_and_identical_parents(self):
        """Verify that siblings (Sofia Anderson and Maya Anderson) share 100% identical parents and careers."""
        sess_id = db.create_session(host_user_id=1, mode="solo", capacity=1, verbosity="normal", dialogue_mode="balanced", image_gen_enabled=False, scenario="high_school_drama")
        try:
            # 1. Add Sofia Anderson
            db.upsert_contact(
                session_id=sess_id,
                character_id=1,
                npc_id="sofia_anderson",
                name="Sofia Anderson",
                basic_info={"role": "Junior Robotics Apprentice", "grade": "Junior", "sibling_name": "Maya Anderson"},
                delta_score=50,
                track="platonic",
                race="beastfolk:fox",
                gender="female",
                appearance={"eyes": "Amber", "hair": "Golden-Blonde", "fur": "Golden-Blonde Fur"}
            )

            # 2. Add Maya Anderson
            db.upsert_contact(
                session_id=sess_id,
                character_id=1,
                npc_id="maya_anderson",
                name="Maya Anderson",
                basic_info={"role": "Freshman Student", "grade": "Freshman", "sibling_name": "Sofia Anderson"},
                delta_score=50,
                track="platonic",
                race="beastfolk:fox",
                gender="female",
                appearance={"eyes": "Amber", "hair": "Golden-Blonde", "fur": "Golden-Blonde Fur"}
            )

            sofia = db.get_contact(sess_id, "sofia_anderson", character_id=1)
            maya = db.get_contact(sess_id, "maya_anderson", character_id=1)

            sofia_rel = genealogy.ensure_contact_relations(sofia, session_id=sess_id, scenario="high_school_drama")
            maya_rel = genealogy.ensure_contact_relations(maya, session_id=sess_id, scenario="high_school_drama")

            sofia_fam = sofia_rel["family"]
            maya_fam = maya_rel["family"]

            # Father comparison
            s_father = next(m for m in sofia_fam if m["relation"] == "Father")
            m_father = next(m for m in maya_fam if m["relation"] == "Father")
            self.assertEqual(s_father["name"], m_father["name"])
            self.assertEqual(s_father["occupation"], m_father["occupation"])
            self.assertEqual(s_father["race"], m_father["race"])
            self.assertEqual(s_father["status"], m_father["status"])

            # Mother comparison
            s_mother = next(m for m in sofia_fam if m["relation"] == "Mother")
            m_mother = next(m for m in maya_fam if m["relation"] == "Mother")
            self.assertEqual(s_mother["name"], m_mother["name"])
            self.assertEqual(s_mother["occupation"], m_mother["occupation"])
            self.assertEqual(s_mother["race"], m_mother["race"])
            self.assertEqual(s_mother["maiden_name"], m_mother["maiden_name"])

            # Cross-sibling presence and relative label
            sofia_sibs = [m for m in sofia_fam if "Sister" in m["relation"] or "Brother" in m["relation"]]
            maya_sibs = [m for m in maya_fam if "Sister" in m["relation"] or "Brother" in m["relation"]]

            self.assertTrue(any(s["first_name"] == "Maya" and "Sister" in s["relation"] for s in sofia_sibs))
            self.assertTrue(any(s["first_name"] == "Sofia" and s["relation"] == "Older Sister" for s in maya_sibs))
        finally:
            with db.get_conn() as conn:
                db.core._delete_session_records(conn, sess_id)

    def test_dynamic_track_transition_and_social_mutations(self):
        """Verify dynamic transitions between platonic and romantic tracks and social graph modifications."""
        sess_id = db.create_session(host_user_id=1, mode="solo", capacity=1, verbosity="normal", dialogue_mode="balanced", image_gen_enabled=False, scenario="high_school_drama")
        try:
            db.upsert_contact(
                session_id=sess_id,
                character_id=1,
                npc_id="zihan_moon",
                name="Zihan Moon",
                delta_score=75,
                track="romantic"
            )

            contact = db.get_contact(sess_id, "zihan_moon", character_id=1)
            self.assertEqual(contact["track"], "romantic")
            rel = genealogy.ensure_contact_relations(contact, session_id=sess_id, scenario="high_school_drama")
            self.assertEqual(rel["romance"]["status"], "In a Relationship")

            # Dynamically switch back to platonic
            db.update_contact_track(sess_id, "zihan_moon", "platonic", character_id=1)
            contact_platonic = db.get_contact(sess_id, "zihan_moon", character_id=1)
            self.assertEqual(contact_platonic["track"], "platonic")

            rel_platonic = genealogy.ensure_contact_relations(contact_platonic, session_id=sess_id, scenario="high_school_drama")
            self.assertEqual(rel_platonic["romance"]["status"], "Single")
            self.assertIsNone(rel_platonic["romance"]["current_partner"])

            # Test dynamic friend and rival mutations
            genealogy.add_friend_relation(contact_platonic, "Yea-ji Kang", role="Student Council President", closeness="Sworn Bestie")
            self.assertTrue(any(f["name"] == "Yea-ji Kang" and f["closeness"] == "Sworn Bestie" for f in contact_platonic["relations"]["friends"]))

            genealogy.add_rival_relation(contact_platonic, "Cassandra Cross", role="Track Star", rival_type="Bitter Nemesis")
            self.assertTrue(any(r["name"] == "Cassandra Cross" and r["type"] == "Bitter Nemesis" for r in contact_platonic["relations"]["rivals"]))

            genealogy.remove_relation(contact_platonic, "Yea-ji Kang")
            self.assertFalse(any(f["name"] == "Yea-ji Kang" for f in contact_platonic["relations"]["friends"]))
        finally:
            with db.get_conn() as conn:
                db.core._delete_session_records(conn, sess_id)

    def test_race_compatibility_with_parents(self):
        """Verify is_race_compatible_with_parents rejects genetically impossible child races."""
        # Fox + Fox parents CANNOT have a Rabbit child
        self.assertFalse(genealogy.is_race_compatible_with_parents("beastfolk:rabbit", "beastfolk:fox", "beastfolk:fox"))
        self.assertFalse(genealogy.is_race_compatible_with_parents("half_beast:rabbit", "beastfolk:fox", "beastfolk:fox"))
        # Fox + Fox CAN have Fox
        self.assertTrue(genealogy.is_race_compatible_with_parents("beastfolk:fox", "beastfolk:fox", "beastfolk:fox"))

        # Human + Fox can have Human, Half-Beast:fox, or Beastfolk:fox
        self.assertTrue(genealogy.is_race_compatible_with_parents("human", "human", "beastfolk:fox"))
        self.assertTrue(genealogy.is_race_compatible_with_parents("half_beast:fox", "human", "beastfolk:fox"))
        self.assertTrue(genealogy.is_race_compatible_with_parents("beastfolk:fox", "human", "beastfolk:fox"))
        # But NOT rabbit
        self.assertFalse(genealogy.is_race_compatible_with_parents("beastfolk:rabbit", "human", "beastfolk:fox"))

        # Pure human parents cannot have beastfolk child
        self.assertFalse(genealogy.is_race_compatible_with_parents("beastfolk:cat", "human", "human"))

    def test_canonical_anderson_family_strictly_locked_to_three_fox_sisters(self):
        """Verify that the Anderson family is strictly locked to Amanda, Sofia, and Maya (all fox sisters)."""
        sess_id = db.create_session(host_user_id=1, mode="solo", capacity=1, verbosity="normal", dialogue_mode="balanced", image_gen_enabled=False, scenario="high_school_drama")
        try:
            # 1. Add Sofia Anderson (Fox)
            db.upsert_contact(
                session_id=sess_id,
                character_id=1,
                npc_id="sofia_anderson",
                name="Sofia Anderson",
                basic_info={"role": "Robotics & Tech Apprentice", "grade": "Junior", "sibling_name": "Maya Anderson"},
                race="beastfolk:fox",
                gender="female"
            )

            # 2. Add an unrelated NPC with surname Anderson (e.g. Justin Anderson, rabbit)
            db.upsert_contact(
                session_id=sess_id,
                character_id=1,
                npc_id="justin_anderson",
                name="Justin Anderson",
                basic_info={"role": "Student", "grade": "Junior", "sibling_name": "Yue Anderson"},
                race="beastfolk:rabbit",
                gender="male"
            )

            sofia = db.get_contact(sess_id, "sofia_anderson", character_id=1)
            sofia_rel = genealogy.ensure_contact_relations(sofia, session_id=sess_id, scenario="high_school_drama")
            fam = sofia_rel["family"]

            # Anderson family members must ONLY be Father, Mother, and the sisters (Amanda, Maya)
            names = [m["name"] for m in fam]
            self.assertNotIn("Justin Anderson", names)
            self.assertTrue(any("Amanda Anderson" in n for n in names))
            self.assertTrue(any("Maya Anderson" in n for n in names))

            # All Anderson family members must be Fox-Beastfolk
            for m in fam:
                self.assertIn("fox", m["race"].lower())

            # Female sisters only
            for m in fam:
                if "Sister" in m["relation"]:
                    self.assertEqual(m["gender"], "female")
        finally:
            with db.get_conn() as conn:
                db.core._delete_session_records(conn, sess_id)

    def test_male_sibling_never_labeled_sister(self):
        """Verify that male siblings with male names or gender male are never labeled Sister."""
        household = {
            "surname": "Vance",
            "father": {"name": "Harry Vance", "first_name": "Harry", "relation": "Father", "race": "human", "gender": "male", "status": "Alive"},
            "mother": {"name": "Sara Vance", "first_name": "Sara", "relation": "Mother", "race": "human", "gender": "female", "status": "Alive"},
            "children": [
                {"name": "Rachel Vance", "first_name": "Rachel", "gender": "female", "grade_val": 3, "race": "human", "status": "Alive"},
                {"name": "Justin Vance", "first_name": "Justin", "gender": "male", "grade_val": 4, "race": "human", "status": "Alive"},
                {"name": "Lucas Vance", "first_name": "Lucas", "gender": "", "grade_val": 1, "race": "human", "status": "Alive"}
            ]
        }
        tree = genealogy.build_family_tree_for_member(household, "Rachel Vance")
        sibs = [m for m in tree if m["relation"] not in ("Father", "Mother")]

        justin = next(s for s in sibs if s["first_name"] == "Justin")
        self.assertEqual(justin["relation"], "Older Brother")
        self.assertNotEqual(justin["relation"], "Older Sister")

        lucas = next(s for s in sibs if s["first_name"] == "Lucas")
        self.assertEqual(lucas["relation"], "Brother")
        self.assertNotEqual(lucas["relation"], "Sister")

    def test_get_contacts_no_recursion_on_unpopulated_relations(self):
        """Verify that get_contacts resolves relations for multiple contacts without recursion."""
        sess_id = db.create_session(
            host_user_id=1, mode="solo", capacity=1, verbosity="normal",
            dialogue_mode="balanced", image_gen_enabled=False, scenario="fantasy"
        )
        try:
            # Insert contacts with different surnames and NO relations populated
            db.upsert_contact(
                session_id=sess_id, character_id=1, npc_id="elena_vance",
                name="Elena Vance", basic_info={"role": "Merchant"}
            )
            db.upsert_contact(
                session_id=sess_id, character_id=1, npc_id="lucas_vance",
                name="Lucas Vance", basic_info={"role": "Apprentice", "sibling_name": "Elena Vance"}
            )
            db.upsert_contact(
                session_id=sess_id, character_id=1, npc_id="garrick_ironthorne",
                name="Garrick Ironthorne", basic_info={"role": "Blacksmith"}
            )

            # Clear any relations_json directly in the database
            with db.get_conn() as conn:
                conn.execute("UPDATE contacts SET relations_json = NULL WHERE session_id = ?", (sess_id,))

            # Call get_contacts: must terminate quickly and populate relations
            contacts = db.get_contacts(sess_id)
            self.assertEqual(len(contacts), 3)
            for c in contacts:
                self.assertIsNotNone(c.get("relations"))
                self.assertTrue(bool(c["relations"].get("family")))
        finally:
            with db.get_conn() as conn:
                db.core._delete_session_records(conn, sess_id)


if __name__ == "__main__":
    unittest.main()


