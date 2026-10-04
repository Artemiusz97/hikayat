import unittest
from cogs.contacts import (
    build_contact_detail_embed,
    build_intimate_profile_embed,
    build_relations_embed
)

class TestContactsUIDeclutter(unittest.TestCase):
    def test_traits_and_likes_dislikes_declutter(self):
        """1. Verify effect descriptions removed from traits and affinity descriptions removed from likes/dislikes."""
        contact = {
            "name": "Rachel Vance",
            "relationship_score": 85,
            "track": "platonic",
            "unlocked_traits": ["Diligent", "Warm"],
            "preferences": [
                "Likes Glazed Honey Apple Tart",
                "Likes Vintage Vinyl Record",
                "Favors Emotional Empathy & Sincerity",
                "Dislikes Gaudy Accessories",
                "Resists Micromanagement & Forceful Orders",
                "Frustrated by Rigid Dogmatism"
            ],
            "basic_info": {
                "race": "Cheetah-Beastfolk",
                "gender": "female"
            }
        }

        embed = build_contact_detail_embed(contact, scenario_key="high_school_drama")
        field_map = {f.name: f.value for f in embed.fields}

        # Traits
        traits_val = field_map["🧠 Unlocked Traits"]
        self.assertIn("• **Diligent**", traits_val)
        self.assertIn("• **Warm**", traits_val)
        self.assertNotIn("Favors INT checks", traits_val)
        self.assertNotIn("+2 affinity", traits_val)
        self.assertNotIn("+20% bonus", traits_val)

        # Likes & Preferences
        likes_val = field_map["👍 Likes & Preferences"]
        self.assertIn("• **Likes Glazed Honey Apple Tart**", likes_val)
        self.assertIn("• **Likes Vintage Vinyl Record**", likes_val)
        self.assertIn("• **Favors Emotional Empathy & Sincerity**", likes_val)
        self.assertNotIn("+12 Affinity", likes_val)
        self.assertNotIn("Favorite Gift", likes_val)
        self.assertNotIn("+2 Affinity", likes_val)
        self.assertNotIn("(Favors PER)", likes_val)

        # Dislikes
        dislikes_val = field_map["👎 Dislikes"]
        self.assertIn("• **Dislikes Gaudy Accessories**", dislikes_val)
        self.assertIn("• **Resists Micromanagement & Forceful Orders**", dislikes_val)
        self.assertIn("• **Frustrated by Rigid Dogmatism**", dislikes_val)
        self.assertNotIn("-5 Affinity", dislikes_val)
        self.assertNotIn("Disliked Gift", dislikes_val)
        self.assertNotIn("-3 Penalty", dislikes_val)
        self.assertNotIn("-2 Penalty", dislikes_val)

    def test_intimate_profile_synergy_removed(self):
        """2. Verify 'Active Intimate Synergy & Modifiers' is completely removed from intimate profile."""
        contact = {
            "name": "Rachel Vance",
            "relationship_score": 90,
            "appearance": {
                "breast_size": "Modest B-Cup",
                "intercourse_experience": "non_virgin",
                "intimate_revealed": True,
                "all_revealed": True
            }
        }
        embed = build_intimate_profile_embed(contact, scenario_key="nsfw_high_school_drama")
        field_names = [f.name for f in embed.fields]

        self.assertNotIn("💡 Active Intimate Synergy & Modifiers", field_names)
        for name in field_names:
            self.assertNotIn("Synergy", name)

    def test_relations_friends_and_rivals_declutter(self):
        """3. Verify 'Inner Circle (Friends)' -> 'Friends', 'Rivals & Adversaries' -> 'Rivals', and bracketed status removed."""
        contact = {
            "name": "Rachel Vance",
            "relationship_score": 85,
            "relations": {
                "friends": [
                    {"name": "Jackson Noh", "role": "Drama Club Lead", "closeness": "Close Friend / Confidant"}
                ],
                "rivals": [
                    {"name": "Joyce Park", "role": "Neighborhood Friend", "type": "Fierce Rival / Competitor"}
                ]
            }
        }

        embed = build_relations_embed(contact, scenario_key="high_school_drama")
        field_map = {f.name: f.value for f in embed.fields}

        self.assertIn("🤝 Friends", field_map)
        self.assertNotIn("🤝 Inner Circle (Friends)", field_map)
        self.assertIn("⚔️ Rivals", field_map)
        self.assertNotIn("⚔️ Rivals & Adversaries", field_map)

        friends_val = field_map["🤝 Friends"]
        self.assertIn("• 🤝 **Jackson Noh** — *Drama Club Lead*", friends_val)
        self.assertNotIn("Close Friend / Confidant", friends_val)

        rivals_val = field_map["⚔️ Rivals"]
        self.assertIn("• ⚔️ **Joyce Park** — *Neighborhood Friend*", rivals_val)
        self.assertNotIn("Fierce Rival / Competitor", rivals_val)

    from unittest.mock import patch
    @patch("mechanics.social.genealogy.ensure_contact_relations")
    def test_family_tree_parents_career_and_status_emojis(self, mock_ensure):
        """4. Verify parents' career removed, alive/deceased text removed, and skull emoji used for deceased."""
        contact = {
            "name": "Rachel Vance",
            "relationship_score": 85,
            "relations": {
                "family": [
                    {
                        "relation": "Father",
                        "name": "Harry Vance",
                        "race": "beastfolk:cheetah",
                        "status": "Alive",
                        "occupation": "Architect"
                    },
                    {
                        "relation": "Mother",
                        "name": "Karolina Vance",
                        "race": "beastfolk:cheetah",
                        "status": "Deceased",
                        "occupation": "Athletic Director / Coach"
                    },
                    {
                        "relation": "Brother",
                        "name": "Margaux Vance",
                        "race": "beastfolk:cheetah",
                        "status": "Alive",
                        "occupation": "Student"
                    }
                ]
            }
        }
        mock_ensure.return_value = contact["relations"]

        embed = build_relations_embed(contact, scenario_key="high_school_drama")
        field_map = {f.name: f.value for f in embed.fields}

        fam_val = field_map["👨‍👩‍👧‍👦 Immediate Family Tree"]

        # Father: Alive parent -> 🟢 emoji, no "Alive", no "Architect"
        self.assertIn("👨 **Father**: Harry Vance (Cheetah-Beastfolk) — 🟢", fam_val)
        self.assertNotIn("Architect", fam_val)
        self.assertNotIn("Alive", fam_val)

        # Mother: Deceased parent -> 💀 emoji, no "Deceased", no "Athletic Director / Coach"
        self.assertIn("👩 **Mother**: Karolina Vance (Cheetah-Beastfolk) — 💀", fam_val)
        self.assertNotIn("Athletic Director", fam_val)
        self.assertNotIn("Deceased", fam_val)
        self.assertNotIn("⚪", fam_val)

        # Brother: Sibling -> 🟢 emoji, no "Alive", Student role displayed
        self.assertIn("👦 **Brother**: Margaux Vance (Cheetah-Beastfolk) — 🟢 *Student*", fam_val)
        self.assertNotIn("Alive", fam_val)

        # Internal tracking remains in relations dict
        self.assertEqual(contact["relations"]["family"][0]["occupation"], "Architect")
        self.assertEqual(contact["relations"]["family"][1]["occupation"], "Athletic Director / Coach")

if __name__ == "__main__":
    unittest.main()
