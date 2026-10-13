import unittest
import db
import scenario_data
from mechanics.social.relationships import (
    get_relationship_tier,
    get_recruitment_cost,
    is_martial_npc,
    is_contact_eligible,
    clamp_score,
    MAX_RELATIONSHIP,
)
from cogs.contacts import filter_unlocked_contacts, build_world_codex_embed
import game_engine
from game_engine.context import _scene_context_text
from game_engine.state.reducers import _reduce_entities_and_gifts
from game_engine.state.social import _reduce_social_and_milestones


class TestAffinityAndCombatStance(unittest.TestCase):
    def setUp(self):
        self.user_id = 99887711
        self.char_info = db.create_character(
            user_id=self.user_id,
            name="Aidan",
            gender="male",
            scenario="fantasy"
        )
        self.char_dict = db.get_character(self.user_id)
        self.char_id = self.char_dict["id"]
        self.session_id = db.create_session(
            self.user_id, "solo", 1, "vivid", "individual", False,
            scenario="fantasy"
        )

    def tearDown(self):
        with db.get_conn() as conn:
            db.core._delete_session_records(conn, self.session_id)
            conn.execute("DELETE FROM characters WHERE user_id = ?", (self.user_id,))

    def test_affinity_milestones_and_scale(self):
        """Verify the 0-300 affinity scale milestones and platonic/romantic tiers."""
        self.assertEqual(MAX_RELATIONSHIP, 300)
        self.assertEqual(clamp_score(350), 300)
        self.assertEqual(clamp_score(-150), -100)

        # Platonic milestones
        stranger = get_relationship_tier(25, "platonic", "fantasy")
        self.assertEqual(stranger["name"], "Stranger")

        acquaintance = get_relationship_tier(75, "platonic", "fantasy")
        self.assertEqual(acquaintance["name"], "Acquaintance")

        friend = get_relationship_tier(120, "platonic", "fantasy")
        self.assertEqual(friend["name"], "Friend")

        close_friend = get_relationship_tier(175, "platonic", "fantasy")
        self.assertEqual(close_friend["name"], "Close Friend")

        confidant = get_relationship_tier(220, "platonic", "fantasy")
        self.assertEqual(confidant["name"], "Confidant")

        lifelong_ally = get_relationship_tier(280, "platonic", "fantasy")
        self.assertEqual(lifelong_ally["name"], "Sworn Lifelong Ally")

        # Romantic milestones
        crush = get_relationship_tier(120, "romantic", "fantasy")
        self.assertEqual(crush["name"], "Mutual Attraction / Crush")

        dating = get_relationship_tier(175, "romantic", "fantasy")
        self.assertEqual(dating["name"], "Dating / Confessed Partners")

        devoted = get_relationship_tier(220, "romantic", "fantasy")
        self.assertEqual(devoted["name"], "Devoted Lovers")

        soulmate = get_relationship_tier(280, "romantic", "fantasy")
        self.assertEqual(soulmate["name"], "Soulmate / Eternal Bond")

    def test_recruitment_cost_scaling(self):
        """Verify gold cost scaling for hirelings based on affinity and level."""
        # Level 1 (base 250)
        self.assertEqual(get_recruitment_cost(0, level=1), 250)      # Stranger: full cost
        self.assertEqual(get_recruitment_cost(50, level=1), 125)     # Acquaintance: 50% discount
        self.assertEqual(get_recruitment_cost(100, level=1), 0)      # Friend: free!
        self.assertEqual(get_recruitment_cost(200, level=1), 0)      # Higher affinity: free

        # Level 3 (base 200 + 3*50 = 350)
        self.assertEqual(get_recruitment_cost(0, level=3), 350)
        self.assertEqual(get_recruitment_cost(50, level=3), 175)
        self.assertEqual(get_recruitment_cost(100, level=3), 0)

    def test_contact_gating_unlocked_vs_world_codex(self):
        """Verify contacts list only exposes Friends (>= 100) and Party Members."""
        raw_contacts = [
            {"name": "Town Guard Alex", "relationship_score": 10, "basic_info": {"role": "Town Guard"}},
            {"name": "Villager Jack", "relationship_score": 45, "basic_info": {"role": "Farmer"}},
            {"name": "Elena the Rogue", "relationship_score": 110, "basic_info": {"role": "Scout"}},
            {"name": "Hireling Bob", "relationship_score": 20, "basic_info": {"role": "Mercenary"}},
        ]
        party_names = {"hireling bob"}

        unlocked = filter_unlocked_contacts(raw_contacts, party_names, scenario_key="fantasy")
        unlocked_names = [c["name"] for c in unlocked]

        # Elena (score 110 >= 100) and Bob (in party) must be included
        self.assertIn("Elena the Rogue", unlocked_names)
        self.assertIn("Hireling Bob", unlocked_names)

        # Alex and Jack (score < 100, not in party) must NOT be in contacts
        self.assertNotIn("Town Guard Alex", unlocked_names)
        self.assertNotIn("Villager Jack", unlocked_names)

    def test_high_school_contact_peer_restriction(self):
        """Verify faculty/adults are excluded from contacts in high school even if affinity is high."""
        hs_contacts = [
            {"name": "Student Maya", "relationship_score": 120, "basic_info": {"role": "Student", "grade": "Junior"}},
            {"name": "Teacher Harrison", "relationship_score": 150, "basic_info": {"role": "Chemistry Teacher", "grade": "Faculty"}},
            {"name": "Clerk Dave", "relationship_score": 130, "basic_info": {"role": "Convenience Store Clerk"}},
        ]
        unlocked = filter_unlocked_contacts(hs_contacts, party_names=set(), scenario_key="high_school_drama")
        unlocked_names = [c["name"] for c in unlocked]

        self.assertIn("Student Maya", unlocked_names)
        self.assertNotIn("Teacher Harrison", unlocked_names)
        self.assertNotIn("Clerk Dave", unlocked_names)

    def test_ambient_spawns_do_not_create_contacts_cards(self):
        """Verify newly encountered NPCs are registered to lorebook (World Codex) but not contacts."""
        outcome = {
            "narrative": "Aidan enters the village square and notices Rowan the merchant and Guard Alex.",
            "new_entities": [
                {
                    "type": "person",
                    "name": "Guard Alex",
                    "role": "Town Guard",
                    "disposition": "neutral",
                    "race": "Human",
                    "gender": "male",
                    "description": "A dutiful watchman standing near the gates."
                },
                {
                    "type": "person",
                    "name": "Rowan",
                    "role": "Merchant",
                    "disposition": "neutral",
                    "race": "Elf",
                    "gender": "female",
                    "description": "An apple merchant tending to her cart."
                }
            ]
        }
        session = db.get_session(self.session_id)
        party = [[self.char_dict, {}]]

        # Run turn outcome reducer
        _reduce_entities_and_gifts(self.session_id, session, outcome, party, actions=[], is_combat=False, scen_key="fantasy")

        # Verify both appear in Lorebook (World Codex)
        lore = db.get_lorebook(self.session_id)
        lore_names = [p["name"] for p in lore.get("person", [])]
        self.assertIn("Guard Alex", lore_names)
        self.assertIn("Rowan", lore_names)

        # Verify NEITHER was added to contacts
        alex_contact = db.get_contact(self.session_id, "Guard Alex", self.char_id)
        rowan_contact = db.get_contact(self.session_id, "Rowan", self.char_id)
        self.assertIsNone(alex_contact)
        self.assertIsNone(rowan_contact)

    def test_world_codex_embed_generation(self):
        """Verify build_world_codex_embed formats discovered NPCs cleanly with affinity meters."""
        # Insert lorebook person
        db.upsert_lorebook_entity(
            self.session_id, "person", "Scholar Alfred", "An elderly historian studying ruins.",
            "neutral", race="Human", appearance={"gender": "male"}
        )
        embed, total_pages, unique_persons = build_world_codex_embed(self.session_id, "fantasy", "Aidan", page=0)
        self.assertEqual(total_pages, 1)
        self.assertTrue(any(p["name"] == "Scholar Alfred" for p in unique_persons))

        # Check embed contents
        field = next((f for f in embed.fields if "Scholar Alfred" in f.name), None)
        self.assertIsNotNone(field)
        self.assertIn("**Affinity**: 0", field.value)
        self.assertIn("Detailed Profile Locked", field.value)

    def test_combat_reaction_matrix_in_prompt_context(self):
        """Verify prompt context formats binary stance and combat reaction matrix correctly."""
        # Setup session with active nearby enemy
        db.update_session_enemies(self.session_id, [{"name": "Goblin Raider", "hp": 15, "max_hp": 15, "disposition": "hostile"}])

        # Add 3 NPCs present in the scene:
        # 1. Guard Brandon (Martial on duty -> Allied Defender)
        # 2. Sellsword Kane (Unaligned martial -> Cautious Observer)
        # 3. Villager Sam (Civilian -> Civilian Bystander)
        db.upsert_lorebook_entity(self.session_id, "person", "Guard Brandon", "Town guard on patrol.", "neutral")
        db.upsert_lorebook_entity(self.session_id, "person", "Sellsword Kane", "Hired mercenary relaxing at the inn.", "neutral")
        db.upsert_lorebook_entity(self.session_id, "person", "Villager Sam", "Farmer carrying baskets.", "neutral")

        current_npcs = [
            {"name": "Guard Brandon", "role": "Town Guard", "description": "Town guard on patrol."},
            {"name": "Sellsword Kane", "role": "Mercenary", "description": "Hired mercenary relaxing at the inn."},
            {"name": "Villager Sam", "role": "Farmer", "description": "Farmer carrying baskets."}
        ]

        context_text = _scene_context_text(
            self.session_id,
            current_location="Town Square",
            current_npcs=current_npcs,
            max_items=4,
            history_text=""
        )

        # Check Guard Brandon: Allied Defender
        self.assertIn("Guard Brandon", context_text)
        self.assertIn("Stance: Non-Hostile | Combat: Allied Defender", context_text)

        # Check Sellsword Kane: Cautious Observer
        self.assertIn("Sellsword Kane", context_text)
        self.assertIn("Stance: Non-Hostile | Combat: Cautious Observer", context_text)

        # Check Villager Sam: Civilian Bystander
        self.assertIn("Villager Sam", context_text)
        self.assertIn("Stance: Non-Hostile | Combat: Civilian Bystander", context_text)

    def test_non_combat_scenario_disables_hostility(self):
        """Verify non-combat scenarios disable hostile stance completely."""
        hs_session_id = db.create_session(
            self.user_id, "solo", 1, "vivid", "individual", False,
            scenario="high_school_drama"
        )
        try:
            db.upsert_lorebook_entity(hs_session_id, "person", "Bully Trent", "Aggressive delinquent.", "hostile")
            current_npcs = [{"name": "Bully Trent", "disposition": "hostile"}]

            context_text = _scene_context_text(
                hs_session_id,
                current_location="Hallway",
                current_npcs=current_npcs,
                max_items=4,
                history_text=""
            )
            # In High School, hostile stance is disabled -> strictly Non-Hostile
            self.assertIn("Bully Trent", context_text)
            self.assertIn("Stance: Non-Hostile", context_text)
            self.assertNotIn("Stance: Hostile", context_text)
        finally:
            with db.get_conn() as conn:
                db.core._delete_session_records(conn, hs_session_id)

    def test_non_combat_scenario_blocks_party_recruitment_turn_and_api(self):
        """Verify party recruitment is completely disabled in non-combat scenarios."""
        hs_session_id = db.create_session(
            self.user_id, "solo", 1, "vivid", "individual", False,
            scenario="high_school_drama"
        )
        try:
            # 1. Turn-based recruitment reducer blocks recruitment in High School
            outcome = {"recruited_npc": "Student Maya"}
            db.update_session_npcs(hs_session_id, [{"name": "Student Maya", "role": "Student"}])
            session = db.get_session(hs_session_id)
            party = [[self.char_dict, {}]]
            _reduce_social_and_milestones(
                hs_session_id, session, party, outcome, actions=[],
                scen_key="high_school_drama", items_gained_by_user={},
                first_char_id=self.char_id, first_char_name="Aidan"
            )
            party_npcs = db.get_session_party_npcs(hs_session_id)
            self.assertEqual(len(party_npcs), 0)

            # 2. Web API endpoint POST /api/party/companion returns HTTP 400
            from fastapi.testclient import TestClient
            import server
            client = TestClient(server.app)
            res = client.post("/api/party/companion", json={
                "user_id": self.user_id,
                "session_id": hs_session_id,
                "npc_name": "Student Maya",
                "action": "recruit"
            })
            self.assertEqual(res.status_code, 400)
            self.assertIn("disabled in non-combat scenarios", res.json()["detail"])
        finally:
            with db.get_conn() as conn:
                db.core._delete_session_records(conn, hs_session_id)

    def test_stranger_lorebook_recruitment_gold_and_auto_contact(self):
        """Verify recruiting a stranger from world codex charges gold and auto-registers contact card."""
        # Setup stranger in lorebook
        db.upsert_lorebook_entity(
            self.session_id, "person", "Valen Swift", "A mercenary scout resting at the tavern.",
            "neutral", race="Elf", appearance={"gender": "male"}
        )

        from fastapi.testclient import TestClient
        import server
        client = TestClient(server.app)

        # 1. Player has 0 gold -> recruitment fails
        db.apply_hp_mp_delta(self.user_id, gold_delta=-99999)  # Reset to 0
        res_fail = client.post("/api/party/companion", json={
            "user_id": self.user_id,
            "session_id": self.session_id,
            "npc_name": "Valen Swift",
            "action": "recruit"
        })
        self.assertEqual(res_fail.status_code, 400)
        self.assertIn("requires at least Friend standing", res_fail.json()["detail"])

        # 2. Give player 500 gold -> recruitment succeeds
        db.apply_hp_mp_delta(self.user_id, gold_delta=500)
        res_ok = client.post("/api/party/companion", json={
            "user_id": self.user_id,
            "session_id": self.session_id,
            "npc_name": "Valen Swift",
            "action": "recruit"
        })
        self.assertEqual(res_ok.status_code, 200)
        rec_data = res_ok.json()
        self.assertEqual(rec_data["status"], "recruited")
        self.assertTrue(any(p["name"] == "Valen Swift" for p in rec_data["party_npcs"]))

        # 3. Contact is auto-registered per Rule 1b
        contact = db.get_contact(self.session_id, "Valen Swift", self.char_id)
        self.assertIsNotNone(contact)
        self.assertEqual(contact["name"], "Valen Swift")
        self.assertEqual(contact["race"].lower(), "elf")


if __name__ == "__main__":
    unittest.main()
