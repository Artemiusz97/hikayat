import unittest
import db
import game_engine
from mechanics.social.genealogy import build_topic_aware_npc_context

class TestTopicAwareNPCContext(unittest.TestCase):
    def setUp(self):
        self.session_id = 99882211
        self.user_id = 77665544
        self.char_name = "Artemiusz"

        with db.get_conn() as conn:
            conn.execute("DELETE FROM characters WHERE user_id = ?", (self.user_id,))
            conn.execute("DELETE FROM sessions WHERE id = ?", (self.session_id,))
            conn.execute("DELETE FROM contacts WHERE session_id = ?", (self.session_id,))

        db.create_character(
            user_id=self.user_id,
            name=self.char_name,
            gender="male",
            stats={"STR": 10, "AGI": 10, "END": 10, "INT": 12, "PER": 10, "CHA": 15, "LUK": 5}
        )
        self.char = db.get_character(self.user_id)

        self.session_id = db.create_session(
            self.user_id, "solo", 1, "vivid", "individual", False, scenario="nsfw_high_school_drama"
        )

        self.sample_contact = {
            "name": "Sofia Anderson",
            "relationship_score": 60,
            "track": "romantic",
            "intimate_memories": [
                "Shared intimate night with Artemiusz",
                "Shared a passionate first kiss with Artemiusz"
            ],
            "relations": {
                "family": [
                    {"relation": "Father", "name": "Jason Anderson", "occupation": "Published Author", "status": "Alive"},
                    {"relation": "Mother", "name": "So-hee Anderson (née Abe)", "occupation": "Corporate Executive", "status": "Alive"},
                    {"relation": "Sister", "name": "Maya Anderson", "occupation": "Student", "status": "Alive"},
                    {"relation": "Older Sister", "name": "Amanda Anderson", "occupation": "Drama Club Lead", "status": "Alive"}
                ],
                "romance": {
                    "status": "Single",
                    "current_partner": None,
                    "secret_partner": None,
                    "ex_partners": [{"name": "Piotr Xu", "role": "Science Club President", "notes": "Past Romantic Partner"}]
                },
                "friends": [{"name": "Judy Huh", "role": "Class Representative", "closeness": "Close Friend / Confidant"}],
                "rivals": [{"name": "Christina Zhu", "role": "Class Representative", "type": "Fierce Rival / Competitor"}]
            },
            "appearance": {
                "intimate_demeanor": "Confident & Bold",
                "intimate_dynamic": "Teasing Switch",
                "sensitive_spots": ["Back of the neck", "Inner thighs", "Fox ears"],
                "turn_ons": ["Confident partners", "Playful banter"]
            }
        }

    def tearDown(self):
        with db.get_conn() as conn:
            conn.execute("DELETE FROM sessions WHERE id = ?", (self.session_id,))
            conn.execute("DELETE FROM characters WHERE user_id = ?", (self.user_id,))
            conn.execute("DELETE FROM contacts WHERE session_id = ?", (self.session_id,))

    def test_family_inquiry_injects_exact_family_tree_and_sibling_count(self):
        """Verify that asking about family triggers the lineage grounding with exact sibling counts and parents."""
        actions = [{"label": "[CHA] Ask Sofia about her family, siblings, and upbringing"}]
        ctx = build_topic_aware_npc_context(self.sample_contact, actions=actions, scenario="nsfw_high_school_drama")

        self.assertIn("CANON FAMILY & LINEAGE GROUNDING - Sofia Anderson", ctx)
        self.assertIn("Jason Anderson", ctx)
        self.assertIn("So-hee Anderson", ctx)
        self.assertIn("Amanda Anderson", ctx)
        self.assertIn("Maya Anderson", ctx)
        self.assertIn("EXACTLY 2 sister(s), 0 brother(s)", ctx)
        self.assertIn("DO NOT invent non-existent siblings", ctx)

    def test_romance_inquiry_injects_past_exes_without_hallucination(self):
        """Verify that asking about past relationships or exes injects canon romance records."""
        actions = [{"label": "Ask Sofia if she has dated anyone before or has an ex"}]
        ctx = build_topic_aware_npc_context(self.sample_contact, actions=actions, scenario="nsfw_high_school_drama")

        self.assertIn("CANON ROMANCE & DATING HISTORY - Sofia Anderson", ctx)
        self.assertIn("Piotr Xu", ctx)
        self.assertIn("Science Club President", ctx)
        self.assertIn("Single", ctx)

    def test_social_circle_inquiry_injects_friends_and_rivals(self):
        """Verify that asking about friends or rivals injects her social circle."""
        actions = [{"label": "Inquire about her close friends and rivals in student council"}]
        ctx = build_topic_aware_npc_context(self.sample_contact, actions=actions, scenario="nsfw_high_school_drama")

        self.assertIn("CANON SOCIAL CIRCLE & RIVALS - Sofia Anderson", ctx)
        self.assertIn("Judy Huh", ctx)
        self.assertIn("Christina Zhu", ctx)

    def test_shared_milestones_always_ground_past_memories(self):
        """Verify that shared memories with the player are preserved in active dialogue context."""
        actions = [{"label": "Pass the tea over to Sofia"}]
        ctx = build_topic_aware_npc_context(self.sample_contact, actions=actions, scenario="nsfw_high_school_drama")

        self.assertIn("ESTABLISHED SHARED MEMORIES WITH PLAYER - Sofia Anderson", ctx)
        self.assertIn("Shared intimate night with Artemiusz", ctx)
        self.assertIn("Shared a passionate first kiss with Artemiusz", ctx)
        # Verify family is NOT injected during unrelated tea drinking
        self.assertNotIn("CANON FAMILY & LINEAGE GROUNDING", ctx)
        self.assertNotIn("CANON ROMANCE & DATING HISTORY", ctx)

    def test_database_persistence_of_contact_relations(self):
        """Verify that get_contacts automatically generates and writes relations to SQLite."""
        db.upsert_contact(
            self.session_id,
            "sofia_anderson",
            "Sofia Anderson",
            character_id=self.char["id"],
            delta_score=50,
            track="romantic"
        )
        contacts = db.get_contacts(self.session_id)
        self.assertTrue(len(contacts) > 0)
        sofia = next(c for c in contacts if c["name"] == "Sofia Anderson")
        self.assertIn("family", sofia["relations"])
        self.assertIn("romance", sofia["relations"])
        self.assertIn("friends", sofia["relations"])
        self.assertIn("rivals", sofia["relations"])

        # Check raw database row
        with db.get_conn() as conn:
            row = conn.execute("SELECT relations_json FROM contacts WHERE session_id = ? AND name = 'Sofia Anderson'", (self.session_id,)).fetchone()
            self.assertIsNotNone(row)
            self.assertNotEqual(row["relations_json"], "{}")
            self.assertIn("family", row["relations_json"])

if __name__ == "__main__":
    unittest.main()
