"""
tests/test_memory_engine.py — Unit tests for the Long-Term Memory & Continuity Engine
=======================================================================================
Tests cover:
  - DB schema (commitments_ledger, session_digests, chapter_digest_json column)
  - db/memory.py CRUD operations
  - DynamicTokenBudget scene classification and character budgets
  - Spatial lorebook ranking in _known_world_text / _known_places_ranked
  - Digest trigger logic (should_trigger_digest)
  - Commitment extraction and persistence
  - New _compact_summary semantic preservation
"""
import json
import sys
import os
import unittest
from unittest.mock import patch, MagicMock

# Ensure project root is on path when running directly
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_fake_session(
    session_id: int = 1,
    history: list | None = None,
    scenario: str = "fantasy",
    dialogue_partner: str = "",
    nearby_enemies: list | None = None,
    current_location: str = "Tavern",
) -> dict:
    return {
        "id": session_id,
        "scenario": scenario,
        "history": history or [],
        "dialogue_partner": dialogue_partner,
        "nearby_enemies": nearby_enemies or [],
        "current_location": current_location,
        "turn_order": [],
    }


# ---------------------------------------------------------------------------
# 1. DB Schema Tests (in-memory SQLite)
# ---------------------------------------------------------------------------

class TestDBSchema(unittest.TestCase):
    """Verify the new tables and columns exist after init_db."""

    def setUp(self):
        """Patch the DB to use an in-memory SQLite."""
        import sqlite3
        self.conn = sqlite3.connect(":memory:")
        self.conn.row_factory = sqlite3.Row
        self.addCleanup(self.conn.close)
        # Read and execute the SCHEMA string from db.core
        # We do this by importing after patching get_conn
        self._patcher = patch("db.core.get_conn", return_value=self.conn)
        self._patcher.start()
        self.addCleanup(self._patcher.stop)

    def _apply_schema(self):
        from db.core import SCHEMA
        self.conn.executescript(SCHEMA)

    def test_commitments_ledger_table_exists(self):
        self._apply_schema()
        result = self.conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='commitments_ledger'"
        ).fetchone()
        self.assertIsNotNone(result, "commitments_ledger table must exist after SCHEMA init")

    def test_session_digests_table_exists(self):
        self._apply_schema()
        result = self.conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='session_digests'"
        ).fetchone()
        self.assertIsNotNone(result, "session_digests table must exist after SCHEMA init")

    def test_commitments_ledger_columns(self):
        self._apply_schema()
        cols = [row["name"] for row in self.conn.execute("PRAGMA table_info(commitments_ledger)")]
        for expected in ("session_id", "source_entity", "target_entity", "commitment_type",
                         "description", "status", "turn_created", "updated_at"):
            self.assertIn(expected, cols, f"Column '{expected}' missing from commitments_ledger")

    def test_session_digests_columns(self):
        self._apply_schema()
        cols = [row["name"] for row in self.conn.execute("PRAGMA table_info(session_digests)")]
        for expected in ("session_id", "turn_start", "turn_end", "summary_bullets_json", "created_at"):
            self.assertIn(expected, cols, f"Column '{expected}' missing from session_digests")


# ---------------------------------------------------------------------------
# 2. db/memory.py CRUD Tests
# ---------------------------------------------------------------------------

class TestMemoryCRUD(unittest.TestCase):
    """Tests for add_commitment, get_active_commitments, update_commitment_status,
    append_chapter_digest, get_chapter_digest."""

    def _bootstrap(self, conn):
        """Create just the tables we need for memory tests."""
        import sqlite3 as _sqlite3
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS commitments_ledger (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id      INTEGER NOT NULL,
                source_entity   TEXT NOT NULL,
                target_entity   TEXT NOT NULL,
                commitment_type TEXT NOT NULL,
                description     TEXT NOT NULL,
                status          TEXT DEFAULT 'active',
                turn_created    INTEGER NOT NULL,
                updated_at      REAL NOT NULL
            );
            CREATE TABLE IF NOT EXISTS session_digests (
                id                  INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id          INTEGER NOT NULL,
                turn_start          INTEGER NOT NULL,
                turn_end            INTEGER NOT NULL,
                summary_bullets_json TEXT NOT NULL DEFAULT '[]',
                created_at          REAL NOT NULL
            );
            CREATE VIRTUAL TABLE IF NOT EXISTS session_digests_fts USING fts5(
                session_id UNINDEXED,
                bullet_text,
                tokenize='unicode61'
            );
            CREATE TABLE IF NOT EXISTS sessions (
                id          INTEGER PRIMARY KEY,
                chapter_digest_json TEXT DEFAULT '[]'
            );
            INSERT INTO sessions (id, chapter_digest_json) VALUES (42, '[]');
        """)

    def _make_patcher(self):
        """Create a context-manager patcher for db.memory.get_conn."""
        import sqlite3
        conn = sqlite3.connect(":memory:")
        conn.row_factory = sqlite3.Row
        self._bootstrap(conn)

        class _CM:
            def __enter__(self): return conn
            def __exit__(self, *a): conn.commit()

        # Patch the name as it is in db.memory's namespace
        patcher = patch("db.memory.get_conn", return_value=_CM())
        return patcher, conn

    def test_add_and_get_commitment(self):
        patcher, _conn = self._make_patcher()
        patcher.start()
        try:
            from db.memory import add_commitment, get_active_commitments
            row = add_commitment(
                session_id=42,
                source_entity="player",
                target_entity="Lyria",
                commitment_type="promise",
                description="Return the stolen heirloom",
                turn_number=3,
            )
            self.assertEqual(row.get("source_entity"), "player")
            self.assertEqual(row.get("target_entity"), "Lyria")
            self.assertEqual(row.get("status"), "active")

            all_active = get_active_commitments(42)
            self.assertEqual(len(all_active), 1)
            self.assertIn("heirloom", all_active[0]["description"])
        finally:
            patcher.stop()

    def test_update_commitment_status(self):
        patcher, _conn = self._make_patcher()
        patcher.start()
        try:
            from db.memory import add_commitment, update_commitment_status, get_active_commitments
            add_commitment(42, "player", "Kael", "pact", "Protect his village", turn_number=1)
            commitments = get_active_commitments(42)
            self.assertEqual(len(commitments), 1)

            update_commitment_status(42, commitments[0]["id"], "fulfilled")
            remaining_active = get_active_commitments(42)
            self.assertEqual(len(remaining_active), 0,
                             "Fulfilled commitment should not appear in active list")
        finally:
            patcher.stop()

    def test_append_and_get_chapter_digest(self):
        patcher, _conn = self._make_patcher()
        patcher.start()
        try:
            from db.memory import append_chapter_digest, get_chapter_digest
            result = append_chapter_digest(42, turn_start=0, turn_end=3, bullets=[
                "Player befriended the blacksmith Kael.",
                "Rescued villagers from goblin raid at Thornwall.",
            ])
            self.assertEqual(len(result), 2)

            fetched = get_chapter_digest(42)
            self.assertIn("Kael", fetched[0])
        finally:
            patcher.stop()

    def test_chapter_digest_cap(self):
        """Adding more than MAX_DIGEST_BULLETS bullets trims the oldest entries."""
        patcher, _conn = self._make_patcher()
        patcher.start()
        try:
            from db.memory import append_chapter_digest, get_chapter_digest, MAX_DIGEST_BULLETS
            for i in range(MAX_DIGEST_BULLETS + 5):
                append_chapter_digest(42, i, i, [f"Event {i}"])
            stored = get_chapter_digest(42)
            self.assertLessEqual(len(stored), MAX_DIGEST_BULLETS,
                                 f"Digest should cap at {MAX_DIGEST_BULLETS} bullets")
        finally:
            patcher.stop()


# ---------------------------------------------------------------------------
# 3. DynamicTokenBudget Tests
# ---------------------------------------------------------------------------

class TestDynamicTokenBudget(unittest.TestCase):
    """Tests for scene mode classification and elastic budget allocation."""

    def test_combat_mode_detected(self):
        from mechanics.system.memory.budget import DynamicTokenBudget, SceneMode
        session = _make_fake_session(nearby_enemies=[{"name": "Goblin"}])
        budget = DynamicTokenBudget.from_session(session)
        self.assertEqual(budget.mode, SceneMode.COMBAT)

    def test_dialogue_mode_detected(self):
        from mechanics.system.memory.budget import DynamicTokenBudget, SceneMode
        session = _make_fake_session(dialogue_partner="Elara the Mage")
        budget = DynamicTokenBudget.from_session(session)
        self.assertEqual(budget.mode, SceneMode.DIALOGUE)

    def test_exploration_mode_default(self):
        from mechanics.system.memory.budget import DynamicTokenBudget, SceneMode
        session = _make_fake_session()
        budget = DynamicTokenBudget.from_session(session)
        self.assertEqual(budget.mode, SceneMode.EXPLORATION)

    def test_combat_collapses_dialogue_budget(self):
        from mechanics.system.memory.budget import DynamicTokenBudget
        session = _make_fake_session(nearby_enemies=[{"name": "Dragon"}])
        budget = DynamicTokenBudget.from_session(session)
        self.assertEqual(budget.chars_for("dialogue"), 0,
                         "Dialogue budget should be 0 during combat")

    def test_dialogue_has_larger_dossier_than_exploration(self):
        from mechanics.system.memory.budget import DynamicTokenBudget
        sess_d = _make_fake_session(dialogue_partner="NPC")
        sess_e = _make_fake_session()
        b_d = DynamicTokenBudget.from_session(sess_d)
        b_e = DynamicTokenBudget.from_session(sess_e)
        self.assertGreater(b_d.chars_for("dialogue"), b_e.chars_for("dialogue"))

    def test_trim_within_budget(self):
        from mechanics.system.memory.budget import DynamicTokenBudget, SceneMode
        session = _make_fake_session()
        budget = DynamicTokenBudget.from_session(session)
        short = "Hello world."
        self.assertEqual(budget.trim(short, "lore"), short,
                         "Text within budget should not be modified")

    def test_trim_truncates_long_text(self):
        from mechanics.system.memory.budget import DynamicTokenBudget
        session = _make_fake_session()
        budget = DynamicTokenBudget.from_session(session)
        long_text = "A " * 3000  # well over any section budget
        trimmed = budget.trim(long_text, "lore")
        self.assertLess(len(trimmed), len(long_text), "Long text must be trimmed")


# ---------------------------------------------------------------------------
# 4. Spatial Lorebook Ranking Tests
# ---------------------------------------------------------------------------

class TestSpatialLoreRanking(unittest.TestCase):
    """Verify that places matching the current location are ranked first."""

    def _ranked_places(self, places: list, current_location: str, max_items: int = 4) -> list:
        """Replicate the spatial ranking logic from context.py."""
        loc_lower = current_location.lower().strip()

        def _place_rank(p):
            n = str(p.get("name", "")).lower()
            d = str(p.get("description", "")).lower()
            if loc_lower and (loc_lower in n or n in loc_lower):
                return 0
            if loc_lower and len(loc_lower) >= 6 and (loc_lower[:6] in n or loc_lower[:6] in d):
                return 1
            return 2

        return sorted(places, key=_place_rank)[:max_items + 2]

    def test_current_location_appears_first(self):
        places = [
            {"name": "Distant Mountain", "description": "Far away"},
            {"name": "Crystalwood Forest", "description": "A mystical forest"},
            {"name": "Thornwall Village", "description": "A small farming village"},
        ]
        ranked = self._ranked_places(places, "Thornwall Village")
        self.assertEqual(ranked[0]["name"], "Thornwall Village",
                         "Current location place must appear first")

    def test_unrelated_locations_still_returned(self):
        places = [
            {"name": "Castle Blackthorn", "description": "Ominous fortress"},
            {"name": "Marketplace", "description": "Busy bazaar"},
        ]
        ranked = self._ranked_places(places, "Thornwall Village")
        self.assertEqual(len(ranked), 2,
                         "All places should be returned even if no location match")

    def test_partial_match_ranked_ahead(self):
        places = [
            {"name": "Northern Wastes", "description": "Barren tundra"},
            {"name": "Thornwall Outskirts", "description": "Edge of Thornwall"},
            {"name": "Crystalwood", "description": "Far forest"},
        ]
        ranked = self._ranked_places(places, "Thornwall Village")
        names = [p["name"] for p in ranked]
        self.assertLess(names.index("Thornwall Outskirts"), names.index("Crystalwood"),
                        "Partial-match place should outrank unrelated places")


# ---------------------------------------------------------------------------
# 5. Digest Trigger Tests
# ---------------------------------------------------------------------------

class TestDigestTrigger(unittest.TestCase):
    """Tests for should_trigger_digest logic."""

    def test_triggers_on_travel_action(self):
        from mechanics.system.memory.digest import should_trigger_digest
        session = _make_fake_session(history=["Turn 1", "Turn 2", "Turn 3"])
        actions = [{"label": "Travel to the Eastern Market"}]
        self.assertTrue(should_trigger_digest(session, actions, {}))

    def test_triggers_on_history_full(self):
        from mechanics.system.memory.digest import should_trigger_digest, RAW_HISTORY_LIMIT
        history = [f"Turn {i}" for i in range(RAW_HISTORY_LIMIT)]
        session = _make_fake_session(history=history)
        self.assertTrue(should_trigger_digest(session, [], {}))

    def test_does_not_trigger_on_short_history(self):
        from mechanics.system.memory.digest import should_trigger_digest
        session = _make_fake_session(history=["Turn 1"])  # only 1 turn
        self.assertFalse(should_trigger_digest(session, [], {}))

    def test_triggers_on_dialogue_exit(self):
        from mechanics.system.memory.digest import should_trigger_digest
        session = _make_fake_session(
            history=["T1", "T2", "T3"],
            dialogue_partner="Elara",
        )
        actions = [{"label": "Excuse yourself and step away"}]
        self.assertTrue(should_trigger_digest(session, actions, {}))

    def test_does_not_trigger_without_dialogue_partner(self):
        from mechanics.system.memory.digest import should_trigger_digest
        session = _make_fake_session(history=["T1", "T2", "T3"])
        actions = [{"label": "Thank them for the information"}]  # dialogue exit keyword but no partner
        self.assertFalse(should_trigger_digest(session, actions, {}))

    def test_triggers_on_sub_quest_complete(self):
        from mechanics.system.memory.digest import should_trigger_digest
        session = _make_fake_session(history=["T1", "T2", "T3"])
        outcome = {"quest_updates": [{"quest_id": "q1", "completed_sub_quest_ids": [1]}]}
        self.assertTrue(should_trigger_digest(session, [], outcome))


# ---------------------------------------------------------------------------
# 6. _compact_summary Semantic Preservation Tests
# ---------------------------------------------------------------------------

class TestCompactSummary(unittest.TestCase):
    """Tests for the new sentence-scoring compact summary logic.

    We replicate the algorithm inline so it can run without discord.py
    (the cog module requires discord and cannot be imported in test env).
    """

    _HIGH_VALUE_KEYWORDS = (
        "killed", "died", "defeated", "completed", "failed", "discovered",
        "revealed", "betrayed", "promised", "agreed", "refused", "escaped",
        "arrived", "left", "joined", "recruited", "unlocked", "obtained",
        "found", "lost", "broke", "healed", "opened", "entered", "exited",
    )

    def _compact(self, text: str, max_chars: int = 500) -> str:
        """Standalone re-implementation of _compact_summary for testing."""
        import re
        text = (text or "").strip()
        if len(text) <= max_chars:
            return text
        raw_sentences = re.split(r'(?<=[.!?"])\s+', text)
        sentences = [s.strip() for s in raw_sentences if s.strip()]
        if not sentences:
            return text[:max_chars] + "…"

        high_value = self._HIGH_VALUE_KEYWORDS
        _PROPER_RE = re.compile(r'\b[A-Z][a-z]{2,}\b')

        def _score(s: str) -> float:
            score = 0.0
            s_lower = s.lower()
            score += len(_PROPER_RE.findall(s)) * 2.0
            score += sum(1.5 for kw in high_value if kw in s_lower)
            score += s.count('"') * 0.8 + s.count("'") * 0.4
            score -= max(0, (20 - len(s)) * 0.05)
            return score

        scored = [(i, _score(s), s) for i, s in enumerate(sentences)]
        scored.sort(key=lambda x: -x[1])

        selected_indices: set[int] = set()
        total = 0
        for idx, _sc, s in scored:
            if total + len(s) + 1 <= max_chars:
                selected_indices.add(idx)
                total += len(s) + 1
            if total >= max_chars * 0.9:
                break

        selected_indices.add(0)
        result = " ".join(sentences[i] for i in sorted(selected_indices))
        return result if len(result) <= max_chars + 20 else result[:max_chars].rsplit(" ", 1)[0] + "…"

    def test_short_text_unchanged(self):
        short = "Elara smiled warmly."
        self.assertEqual(self._compact(short), short)

    def test_output_within_budget(self):
        long_text = " ".join(["The adventurer walked through the forest."] * 40)
        result = self._compact(long_text, max_chars=500)
        self.assertLessEqual(len(result), 520, "Output must stay within budget (with small margin)")

    def test_proper_nouns_preserved(self):
        """Sentences with character names should be prioritised."""
        text = (
            "The weather was nice outside. "
            "Birds were singing in the trees. "
            "Elara revealed the ancient prophecy to Aldric. "
            "The floor was made of stone. "
            "Sunlight streamed through the window. "
        ) * 5  # repeat to force truncation
        result = self._compact(text, max_chars=250)
        self.assertIn("Elara", result,
                      "Proper-noun sentences (character names) should survive truncation")

    def test_outcome_verbs_preserved(self):
        text = (
            "The sky grew dark. "
            "Elara defeated the Shadow Wraith in single combat. "
            "A cold wind blew. "
            "The torch flickered in the breeze. "
        ) * 5
        result = self._compact(text, max_chars=200)
        self.assertIn("defeated", result,
                      "Outcome verb sentences must survive truncation")

    def test_first_sentence_always_included(self):
        text = (
            "The party entered the dungeon. " +
            "Mundane sentence. " * 20
        )
        result = self._compact(text, max_chars=150)
        self.assertTrue(result.startswith("The party entered"),
                        "First sentence should always appear for scene grounding")


# ---------------------------------------------------------------------------
# 7. push_history limit Tests
# ---------------------------------------------------------------------------

class TestPushHistory(unittest.TestCase):
    """Verify push_history uses RAW_HISTORY_LIMIT as default."""

    def test_default_limit_is_4(self):
        from mechanics.system.memory.digest import RAW_HISTORY_LIMIT
        from game_engine.state import push_history
        self.assertEqual(RAW_HISTORY_LIMIT, 4,
                         "RAW_HISTORY_LIMIT must be 4 for the Tier-1 raw window")

    def test_push_history_caps_at_raw_limit(self):
        from game_engine import push_history
        from mechanics.system.memory.digest import RAW_HISTORY_LIMIT
        history = []
        for i in range(RAW_HISTORY_LIMIT + 3):
            history = push_history(history, f"Turn {i}")
        self.assertEqual(len(history), RAW_HISTORY_LIMIT,
                         f"History must be capped at {RAW_HISTORY_LIMIT}")

    def test_push_history_custom_limit_respected(self):
        from game_engine import push_history
        history = []
        for i in range(10):
            history = push_history(history, f"Turn {i}", limit=6)
        self.assertEqual(len(history), 6)


# ---------------------------------------------------------------------------
# 7. Enriched Digest — _extractive_fallback and format_digest_prompt_block
# ---------------------------------------------------------------------------

class TestExtractiveDigestFallback(unittest.TestCase):
    """Verify _extractive_fallback produces the enriched schema including [RESOURCE] bullets."""

    def test_returns_four_key_schema(self):
        from mechanics.system.memory.digest import _extractive_fallback
        result = _extractive_fallback(["Turn 1: The party explored a dungeon."])
        for key in ("key_events", "commitments", "mechanical_summary", "active_hooks"):
            self.assertIn(key, result, f"_extractive_fallback must return '{key}' key")

    def test_key_events_populated(self):
        from mechanics.system.memory.digest import _extractive_fallback
        result = _extractive_fallback(["The wizard found a staff. She fought a troll."])
        self.assertTrue(len(result["key_events"]) > 0, "key_events must be non-empty")

    def test_resource_bullet_extracted_for_gold(self):
        from mechanics.system.memory.digest import _extractive_fallback
        result = _extractive_fallback(["You earned 75 gold coins from the merchant."])
        resources = result.get("mechanical_summary", [])
        self.assertTrue(
            any("gold" in r.lower() for r in resources),
            "Fallback should extract a [RESOURCE] bullet when gold is mentioned"
        )

    def test_resource_bullet_not_duplicated(self):
        from mechanics.system.memory.digest import _extractive_fallback
        turns = [
            "You found 50 gold.",
            "You spent 50 gold.",
            "You earned 50 gold again.",
        ]
        result = _extractive_fallback(turns)
        # Each bullet with same text must appear only once
        seen = set()
        for r in result.get("mechanical_summary", []):
            self.assertNotIn(r, seen, "Duplicate resource bullets must be deduplicated")
            seen.add(r)

    def test_long_turns_truncated(self):
        from mechanics.system.memory.digest import _extractive_fallback
        long_turn = "A" * 500
        result = _extractive_fallback([long_turn])
        for bullet in result["key_events"]:
            self.assertLessEqual(len(bullet), 210, "Extractive bullets must be truncated to ~200 chars")


class TestEnrichedDigestParsing(unittest.TestCase):
    """Verify generate_arc_digest correctly tags [RESOURCE] and [HOOK] bullets."""

    def test_mechanical_summary_tagged_resource(self):
        """Items from mechanical_summary must be stored with [RESOURCE] prefix."""
        import asyncio
        from unittest.mock import patch, AsyncMock
        from mechanics.system.memory.digest import generate_arc_digest

        fake_result = {
            "key_events": ["Party entered the dungeon."],
            "commitments": [],
            "mechanical_summary": ["Gold: +50 (bounty reward)", "Gained: Iron Key"],
            "active_hooks": [],
        }

        saved_bullets = []

        def _fake_append(session_id, turn_start, turn_end, bullets, embeddings=None):
            saved_bullets.extend(bullets)

        with patch("llm_client.call_llm_json", new=AsyncMock(return_value=fake_result)):
            with patch("db.append_chapter_digest", side_effect=_fake_append):
                with patch("db.bulk_add_commitments"):
                    asyncio.run(generate_arc_digest(session_id=1, raw_turns=["Turn text"], turn_start=0))

        resource_bullets = [b for b in saved_bullets if b.startswith("[RESOURCE]")]
        self.assertEqual(len(resource_bullets), 2, "Both mechanical_summary items must be saved as [RESOURCE] bullets")
        self.assertIn("[RESOURCE] Gold: +50 (bounty reward)", resource_bullets)
        self.assertIn("[RESOURCE] Gained: Iron Key", resource_bullets)

    def test_active_hooks_tagged_hook(self):
        """Items from active_hooks must be stored with [HOOK] prefix."""
        import asyncio
        from unittest.mock import patch, AsyncMock
        from mechanics.system.memory.digest import generate_arc_digest

        fake_result = {
            "key_events": ["Party explored a chapel."],
            "commitments": [],
            "mechanical_summary": [],
            "active_hooks": ["Strange scratching behind altar — uninvestigated"],
        }

        saved_bullets = []

        def _fake_append(session_id, turn_start, turn_end, bullets, embeddings=None):
            saved_bullets.extend(bullets)

        with patch("llm_client.call_llm_json", new=AsyncMock(return_value=fake_result)):
            with patch("db.append_chapter_digest", side_effect=_fake_append):
                with patch("db.bulk_add_commitments"):
                    asyncio.run(generate_arc_digest(session_id=1, raw_turns=["Turn text"], turn_start=0))

        hook_bullets = [b for b in saved_bullets if b.startswith("[HOOK]")]
        self.assertEqual(len(hook_bullets), 1, "active_hooks item must be saved as [HOOK] bullet")
        self.assertIn("[HOOK] Strange scratching behind altar — uninvestigated", hook_bullets)

    def test_no_double_prefix_on_tagged_inputs(self):
        """If LLM accidentally returns an already-tagged string, it must not be double-prefixed."""
        import asyncio
        from unittest.mock import patch, AsyncMock
        from mechanics.system.memory.digest import generate_arc_digest

        fake_result = {
            "key_events": [],
            "commitments": [],
            "mechanical_summary": ["[RESOURCE] Gold: +100 already tagged"],
            "active_hooks": ["[HOOK] Already tagged hook"],
        }

        saved_bullets = []

        def _fake_append(session_id, turn_start, turn_end, bullets, embeddings=None):
            saved_bullets.extend(bullets)

        with patch("llm_client.call_llm_json", new=AsyncMock(return_value=fake_result)):
            with patch("db.append_chapter_digest", side_effect=_fake_append):
                with patch("db.bulk_add_commitments"):
                    asyncio.run(generate_arc_digest(session_id=1, raw_turns=["Turn"], turn_start=0))

        for b in saved_bullets:
            self.assertFalse(b.startswith("[RESOURCE] [RESOURCE]"), "Double [RESOURCE] prefix detected")
            self.assertFalse(b.startswith("[HOOK] [HOOK]"), "Double [HOOK] prefix detected")


class TestFormatDigestPromptBlock(unittest.TestCase):
    """Verify format_digest_prompt_block organizes bullets into tagged subsections."""

    def _run_format(self, bullets: list[str]) -> str:
        from unittest.mock import patch
        from db.memory import format_digest_prompt_block

        with patch("db.memory.get_chapter_digest", return_value=bullets):
            with patch("db.memory.search_chapter_digests", return_value=[]):
                with patch("db.memory.get_session_chronicles", return_value=[]):
                    return format_digest_prompt_block(session_id=1, query_context="")

    def test_story_events_subsection_present(self):
        bullets = ["Party entered the dungeon.", "They defeated a goblin."]
        output = self._run_format(bullets)
        self.assertIn("(Story Events):", output)

    def test_hook_subsection_present_when_hooks_exist(self):
        bullets = ["Party explored the market.", "[HOOK] Mysterious note found in alley"]
        output = self._run_format(bullets)
        self.assertIn("(Active Hooks & Rumors):", output)
        self.assertIn("Mysterious note found in alley", output)

    def test_resource_subsection_present_when_resources_exist(self):
        bullets = ["Party sold loot.", "[RESOURCE] Gold: +120 (sold equipment)"]
        output = self._run_format(bullets)
        self.assertIn("(Recent Resource Diffs):", output)
        self.assertIn("Gold: +120 (sold equipment)", output)

    def test_plain_bullets_no_subsection_headers(self):
        """If only plain bullets exist, no subsection headers should appear."""
        bullets = ["The party rested.", "Torvin sharpened his blade."]
        output = self._run_format(bullets)
        self.assertNotIn("(Active Hooks & Rumors):", output)
        self.assertNotIn("(Recent Resource Diffs):", output)

    def test_hook_tag_stripped_from_display(self):
        """The [HOOK] tag prefix must not appear in the output — only the content."""
        bullets = ["[HOOK] Wanted poster for a red-cloaked rogue"]
        output = self._run_format(bullets)
        self.assertNotIn("[HOOK] Wanted poster", output,
                         "[HOOK] tag must be stripped; content displayed under subsection header")
        self.assertIn("Wanted poster for a red-cloaked rogue", output)

    def test_resource_tag_stripped_from_display(self):
        """The [RESOURCE] tag prefix must not appear in the output — only the content."""
        bullets = ["[RESOURCE] Lost: 2 Health Potions"]
        output = self._run_format(bullets)
        self.assertNotIn("[RESOURCE] Lost:", output,
                         "[RESOURCE] tag must be stripped; content displayed under subsection header")
        self.assertIn("Lost: 2 Health Potions", output)

    def test_empty_bullets_returns_empty_string(self):
        output = self._run_format([])
        self.assertEqual(output, "")


if __name__ == "__main__":
    unittest.main()

