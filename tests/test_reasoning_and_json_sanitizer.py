import unittest
import json
from llm_client import _extract_json
from namegen import is_valid_entity_name
from cogs.adventure import build_outcome_embeds


class TestReasoningAndJsonSanitizer(unittest.TestCase):
    def test_extract_json_with_trailing_meta_correction(self):
        """Test extraction when LLM outputs a valid JSON block followed by self-correction commentary."""
        raw_output = """{
  "outcome_narrative": "Amélie listens quietly and nods.",
  "relationship_updates": [
    {"npc_name": "Amélie Yamashita", "delta_score": 1}
  ]
}
** (Wait - correcting JSON structure for consistency with requested output) : { "scene": "..." } (Actually providing full JSON now) : { "scene": "..." }"""
        
        result = _extract_json(raw_output)
        self.assertIsInstance(result, dict)
        self.assertEqual(result.get("outcome_narrative"), "Amélie listens quietly and nods.")
        self.assertEqual(len(result.get("relationship_updates", [])), 1)
        self.assertEqual(result["relationship_updates"][0]["npc_name"], "Amélie Yamashita")

    def test_extract_json_with_think_tags(self):
        """Test extraction when model outputs <think> reasoning blocks before JSON."""
        raw_output = """<think>
The user succeeded on their check with Amélie.
I should increment her affinity by 1 and write the dialogue resolution.
</think>
```json
{
  "outcome_narrative": "She smiles warmly.",
  "relationship_updates": [{"npc_name": "Amélie Yamashita", "delta_score": 1}]
}
```"""
        result = _extract_json(raw_output)
        self.assertIsInstance(result, dict)
        self.assertEqual(result.get("outcome_narrative"), "She smiles warmly.")

    def test_is_valid_entity_name(self):
        """Test entity name validator accurately discriminates authentic names from corrupted reasoning/JSON strings."""
        # Valid names
        self.assertTrue(is_valid_entity_name("Amélie Yamashita"))
        self.assertTrue(is_valid_entity_name("Sofia Anderson"))
        self.assertTrue(is_valid_entity_name("Zihan Moon"))
        self.assertTrue(is_valid_entity_name("Student Council"))

        # Invalid / Corrupted names from LLM reasoning leaks
        self.assertFalse(is_valid_entity_name('🔲"C:"; ⌛"}** (Wait - correcting JSON structure'))
        self.assertFalse(is_valid_entity_name('** (Wait - correcting JSON structure for consistency with requested output) : { "scene": "..." }'))
        self.assertFalse(is_valid_entity_name('{"scene": "..."}'))
        self.assertFalse(is_valid_entity_name('Amélie Yamashita\nNext line'))
        self.assertFalse(is_valid_entity_name('*Sofia*'))
        self.assertFalse(is_valid_entity_name('[NPC]'))
        self.assertFalse(is_valid_entity_name('A' * 60))

    def test_build_outcome_embeds_filters_corrupted_social_entries(self):
        """Test that build_outcome_embeds silently strips corrupted social lines while rendering valid ones."""
        outcome = {
            "outcome_narrative": "Conversation continues.",
            "character_outcomes": [{"name": "Artemiusz"}],
            "relationship_updates": [
                {"npc_name": "Amélie Yamashita", "delta_score": 1},
                {"npc_name": '🔲"C:"; ⌛"}** (Wait - correcting JSON structure for consistency with requested output)', "delta_score": 0}
            ]
        }
        
        embeds = build_outcome_embeds(
            outcome=outcome,
            check_field_name="🎯 Check",
            check_field_value="Success",
            loot_text="",
            result_display="detailed"
        )
        
        breakdown_embed = embeds[1]
        social_field = next((f for f in breakdown_embed.fields if "Social & Faction Updates" in f.name), None)
        self.assertIsNotNone(social_field)
        self.assertIn("Amélie Yamashita: +1", social_field.value)
        self.assertNotIn("correcting JSON", social_field.value)
        self.assertNotIn("🔲", social_field.value)


if __name__ == "__main__":
    unittest.main()
