import unittest
import discord
from mechanics.social.persona import (
    enforce_intimacy_safeguard_invariants,
    normalize_appearance,
    merge_appearance_safely,
    format_intimate_profile_sections
)
from cogs.contacts import build_romantic_memories_embed, build_intimate_profile_embed

class TestIntimateSafeguardsHarmony(unittest.TestCase):
    def test_enforce_intimacy_safeguard_invariants_clamps_desynced_virgin(self):
        corrupt_app = {
            "predetermined_intercourse": "virgin",
            "intercourse_experience": "non_virgin",
            "oral_experience": "has_done_and_received_oral",
            "manual_experience": "has_done_and_received_manual",
            "intercourse_experience": "non_virgin"
        }
        healed = enforce_intimacy_safeguard_invariants(corrupt_app)
        self.assertEqual(healed["predetermined_intercourse"], "virgin")
        self.assertEqual(healed["intercourse_experience"], "virgin")
        self.assertEqual(healed["oral_experience"], "has_done_and_received_oral")
        self.assertEqual(healed["manual_experience"], "has_done_and_received_manual")
        self.assertEqual(healed["intercourse_experience"], "virgin")

    def test_enforce_intimacy_safeguard_invariants_allows_player_progression(self):
        player_experienced_app = {
            "predetermined_intercourse": "virgin",
            "had_first_time_with_player": True,
            "intercourse_experience": "non_virgin",
            "oral_experience": "has_done_oral",
            "manual_experience": "inexperienced",
            "intercourse_experience": "non_virgin"
        }
        result = enforce_intimacy_safeguard_invariants(player_experienced_app)
        self.assertEqual(result["predetermined_intercourse"], "virgin")
        self.assertEqual(result["intercourse_experience"], "non_virgin")
        self.assertEqual(result["oral_experience"], "has_done_oral")
        self.assertEqual(result["intercourse_experience"], "non_virgin")

    def test_enforce_intimacy_safeguard_invariants_preserves_predetermined_non_virgin(self):
        canon_experienced = {
            "predetermined_intercourse": "non_virgin",
            "intercourse_experience": "non_virgin",
            "oral_experience": "has_done_and_received_oral",
            "manual_experience": "has_done_and_received_manual",
            "intercourse_experience": "non_virgin"
        }
        result = enforce_intimacy_safeguard_invariants(canon_experienced)
        self.assertEqual(result["predetermined_intercourse"], "non_virgin")
        self.assertEqual(result["intercourse_experience"], "non_virgin")
        self.assertEqual(result["oral_experience"], "has_done_and_received_oral")

    def test_normalize_appearance_clamps_procedural_ratchet_for_virgin(self):
        # Pass predetermined_intercourse as virgin with a description seed that would roll non_virgin
        raw_app = {
            "predetermined_intercourse": "virgin"
        }
        norm = normalize_appearance(
            raw_app,
            gender="female",
            race="human",
            scen_key="nsfw_furry_high_school_drama",
            desc="Cheetah girl track star who is energetic and popular"
        )
        self.assertEqual(norm["predetermined_intercourse"], "virgin")
        self.assertEqual(norm["intercourse_experience"], "virgin")
        self.assertEqual(norm["oral_experience"], "inexperienced")
        self.assertEqual(norm["manual_experience"], "inexperienced")
        self.assertEqual(norm["intercourse_experience"], "virgin")

    def test_merge_appearance_safely_provenance_guard(self):
        existing = {
            "predetermined_intercourse": "virgin",
            "intercourse_experience": "virgin",
            "oral_experience": "inexperienced",
            "manual_experience": "inexperienced",
            "intercourse_experience": "virgin"
        }
        incoming_rogue = {
            "predetermined_intercourse": "non_virgin",
            "predetermined_intercourse": "non_virgin",
            "intercourse_experience": "non_virgin",
            "oral_experience": "has_done_and_received_oral",
            "manual_experience": "has_done_and_received_manual",
            "intercourse_experience": "non_virgin"
        }
        merged = merge_appearance_safely(existing, incoming_rogue)
        # Rogue incoming update should be rejected because no player milestone exists
        self.assertEqual(merged["intercourse_experience"], "virgin")
        self.assertEqual(merged["oral_experience"], "inexperienced")
        self.assertEqual(merged["manual_experience"], "inexperienced")
        self.assertEqual(merged["intercourse_experience"], "virgin")

    def test_merge_appearance_safely_accepts_verified_player_milestone(self):
        existing = {
            "predetermined_intercourse": "virgin",
            "intercourse_experience": "virgin",
            "oral_experience": "inexperienced",
            "manual_experience": "inexperienced",
            "intercourse_experience": "virgin"
        }
        incoming_with_player = {
            "had_first_time_with_player": True,
            "intercourse_experience": "non_virgin",
            "oral_experience": "has_done_oral",
            "intercourse_experience": "non_virgin"
        }
        merged = merge_appearance_safely(existing, incoming_with_player)
        self.assertEqual(merged["intercourse_experience"], "non_virgin")
        self.assertEqual(merged["oral_experience"], "has_done_oral")
        self.assertEqual(merged["intercourse_experience"], "non_virgin")

    def test_ui_embeds_harmonize_for_virgin(self):
        contact_virgin = {
            "name": "Rachel Vance",
            "gender": "female",
            "relationship_score": 84,  # Level 3 disclosure
            "appearance": {
                "predetermined_intercourse": "virgin",
                "intercourse_experience": "virgin",
                "oral_experience": "inexperienced",
                "manual_experience": "inexperienced",
                "intercourse_experience": "virgin"
            },
            "intimate_memories": []
        }

        # 1. Romantic Memories Embed
        mem_embed = build_romantic_memories_embed(contact_virgin, scenario_key="nsfw_furry_high_school_drama", user_id=0)
        past_hist_field = next((f for f in mem_embed.fields if f.name == "📜 Past Intimate History"), None)
        self.assertIsNotNone(past_hist_field)
        self.assertIn("Virgin (No prior intimate history before meeting you)", past_hist_field.value)

        # 2. Intimate Profile Embed
        intimate_embed = build_intimate_profile_embed(contact_virgin, scenario_key="nsfw_furry_high_school_drama", user_id=0)
        anatomy_field = next((f for f in intimate_embed.fields if f.name == "🔞 Anatomy & Experience"), None)
        self.assertIsNotNone(anatomy_field)
        self.assertIn("• **Intercourse**: Virgin", anatomy_field.value)
        self.assertIn("• **Oral Intimacy**: Inexperienced", anatomy_field.value)
        self.assertIn("• **Manual Intimacy**: Inexperienced", anatomy_field.value)

    def test_ui_embeds_harmonize_for_experienced_npc(self):
        contact_experienced = {
            "name": "Lyra Ravenwood",
            "gender": "female",
            "relationship_score": 84,  # Level 3 disclosure
            "appearance": {
                "predetermined_intercourse": "non_virgin",
                "intercourse_experience": "non_virgin",
                "oral_experience": "has_done_oral",
                "manual_experience": "has_done_manual",
                "intercourse_experience": "non_virgin"
            },
            "intimate_memories": []
        }

        # 1. Romantic Memories Embed generates past intimate history
        mem_embed = build_romantic_memories_embed(contact_experienced, scenario_key="nsfw_furry_high_school_drama", user_id=0)
        past_hist_field = next((f for f in mem_embed.fields if f.name == "📜 Past Intimate History"), None)
        self.assertIsNotNone(past_hist_field)
        self.assertNotIn("Virgin (No prior intimate history before meeting you)", past_hist_field.value)
        self.assertTrue(len(past_hist_field.value) > 10)

        # 2. Intimate Profile Embed displays experienced stats
        intimate_embed = build_intimate_profile_embed(contact_experienced, scenario_key="nsfw_furry_high_school_drama", user_id=0)
        anatomy_field = next((f for f in intimate_embed.fields if f.name == "🔞 Anatomy & Experience"), None)
        self.assertIsNotNone(anatomy_field)
        self.assertIn("• **Intercourse**: Non-Virgin", anatomy_field.value)
        self.assertIn("• **Oral Intimacy**: Has Performed", anatomy_field.value)
        self.assertIn("• **Manual Intimacy**: Has Given", anatomy_field.value)

    def test_merge_appearance_safely_protects_memories_against_empty_incoming(self):
        existing = {
            "intimate_memories": ["Shared intimate night with Maya"],
            "predetermined_intercourse": "virgin",
            "intercourse_experience": "non_virgin",
            "had_first_time_with_player": True,
            "past_intimate_history": "Past History: Sample entry"
        }
        incoming_empty = {
            "breast_size": "large",
            "intimate_memories": [],
            "past_intimate_history": ""
        }
        merged = merge_appearance_safely(existing, incoming_empty)
        self.assertEqual(merged["intimate_memories"], ["Shared intimate night with Maya"])
        self.assertEqual(merged["intercourse_experience"], "non_virgin")
        self.assertEqual(merged["past_intimate_history"], "Past History: Sample entry")

    def test_genealogy_topic_context_cleans_brackets_and_quotes(self):
        from mechanics.social.genealogy import build_topic_aware_npc_context
        # With turn_ons_revealed=True: sensitive spots should be injected AND cleaned
        contact = {
            "name": "Maya",
            "appearance": {
                "sensitive_spots": "['Fox ears', 'base of tail']",
                "turn_ons": "['whispered praise', 'tail grooming']",
                "turn_ons_revealed": True,
            }
        }
        ctx = build_topic_aware_npc_context(contact, actions=[{"label": "kiss Maya intimately"}])
        self.assertIn("Sensitive Spots: Fox ears, Base of tail", ctx)
        self.assertIn("Turn-Ons: Whispered praise, Tail grooming", ctx)
        self.assertNotIn("['", ctx)

        # Without any reveal flag: sensitive spots must NOT be injected even during intimacy
        contact_unrevealed = {
            "name": "Maya",
            "appearance": {
                "sensitive_spots": "['Fox ears', 'base of tail']",
                "turn_ons": "['whispered praise', 'tail grooming']",
            }
        }
        ctx2 = build_topic_aware_npc_context(contact_unrevealed, actions=[{"label": "kiss Maya intimately"}])
        self.assertNotIn("Sensitive Spots:", ctx2, "Sensitive spots must not leak before turn_ons_revealed is set")

    def test_enrich_contact_record_updates_experience_and_anatomy_when_intercourse_memory_exists(self):
        from api.codex_phone import _enrich_contact_record
        contact = {
            "name": "Kiyomi",
            "relationship_score": 85,
            "intimate_memories": ["Shared intimate night with Kiyomi and made love"],
            "appearance": {
                "predetermined_intercourse": "virgin",
                "intercourse_experience": "virgin",
                "experience": "Virgin",
                "anatomy": "Breast Size: Modest B-Cup • Intercourse: Virgin • Oral: Inexperienced • Manual: Inexperienced",
                "intimate_revealed": True
            }
        }
        enriched = _enrich_contact_record(contact, session_id=1, scen_key="fantasy", debug_reveal_all=False)
        app = enriched.get("appearance", {})
        self.assertEqual(app.get("experience"), "Non-Virgin")
        self.assertIn("Intercourse: Non-Virgin", app.get("anatomy", ""))
        self.assertIn("shared first time with you", enriched.get("past_intimate_history", ""))

    def test_generate_relationship_status_creates_past_partner_for_virgins_with_experience(self):
        """Regression: Procedural generation creates past partners for virgins if they have oral or manual experience."""
        from mechanics.social.genealogy import generate_relationship_status
        contact = {
            "name": "Jane",
            "appearance": {
                "predetermined_intercourse": "virgin",
                "oral_experience": "has_done_oral"
            }
        }
        res = generate_relationship_status(contact, hash_val=42)
        # Should generate an ex_partner since they have oral experience
        self.assertTrue(len(res.get("ex_partners", [])) > 0)
        self.assertIn("Past Romantic", res["ex_partners"][0].get("notes", ""))

    def test_upsert_contact_enforces_invariants_when_appearance_is_none(self):
        import db, time
        sess_id = int(time.time() * 1000)
        char_id = 99933
        # Create virgin contact
        c1 = db.upsert_contact(
            session_id=sess_id,
            character_id=char_id,
            npc_id="selena",
            name="Selena",
            appearance={"predetermined_intercourse": "virgin", "intercourse_experience": "virgin"}
        )
        self.assertEqual(c1["appearance"]["intercourse_experience"], "virgin")

        # Now add intercourse memory without passing appearance dict
        c2 = db.upsert_contact(
            session_id=sess_id,
            character_id=char_id,
            npc_id="selena",
            name="Selena",
            appearance=None,
            new_memory="Shared intimate night and made love with Selena"
        )
        # Invariants must have promoted intercourse_experience to non_virgin
        self.assertEqual(c2["appearance"]["intercourse_experience"], "non_virgin")
        self.assertTrue(c2["appearance"].get("had_first_time_with_player"))

    def test_merge_appearance_safely_preserves_underwear_revealed(self):
        existing = {"underwear_revealed": True}
        incoming = {"breast_size": "medium"}
        merged = merge_appearance_safely(existing, incoming)
        self.assertTrue(merged.get("underwear_revealed"))

    def test_normalize_appearance_preserves_all_fetishes_no_truncation(self):
        """Regression: normalize_appearance must NOT truncate fetishes to first comma-item."""
        app = {
            "predetermined_intercourse": "non_virgin",
            "intercourse_experience": "non_virgin",
            "fetishes": "Roleplay, Light bondage, Voyeurism",
        }
        result = normalize_appearance(app, gender="female", race="human", scen_key="fantasy")
        fetishes = result.get("fetishes", "")
        # All three fetishes must survive — not just "Roleplay"
        self.assertIn("bondage", fetishes.lower(), "Second fetish was truncated")
        self.assertIn("voyeurism", fetishes.lower(), "Third fetish was truncated")

    def test_normalize_appearance_fetishes_single_item_unchanged(self):
        """normalize_appearance must keep single-item fetishes unchanged."""
        app = {
            "predetermined_intercourse": "virgin",
            "fetishes": "Light bondage",
        }
        result = normalize_appearance(app, gender="female", race="human", scen_key="fantasy")
        self.assertIn("Light bondage", result.get("fetishes", ""))

    def test_evaluate_npc_milestones_date_sets_romantic_track(self):
        """Regression: date milestone must set track='romantic' in Tier 1 and Tier 2."""
        from game_engine.state.reducers import _evaluate_npc_milestones
        app = {"predetermined_intercourse": "virgin"}
        # Tier 1 path: LLM milestone_ev = "date"
        _, _, _, _, track, _, _ = _evaluate_npc_milestones(
            npc_name="Mia",
            app_dict=dict(app),
            track="platonic",
            milestone_ev="date",
            custom_summary="Had a wonderful date",
            intercourse_exp="",
            oral_exp="",
            actions=[],
            narrative_text="",
            overall_check_success=True,
            is_player_romantic_action=False,
            is_player_intimate_action=False,
            is_player_oral_action=False,
            is_player_intercourse_action=False,
            is_player_confession_action=False,
            is_player_affection_action=False,
            affection_target_npc=None,
            gift_target_npc=None,
            gift_item_name=None,
            confession_target_npc=None,
            first_char_name="Alex",
        )
        self.assertEqual(track, "romantic", "Tier 1 date milestone did not set track='romantic'")

    def test_evaluate_npc_milestones_confession_sets_romantic_track_unconditionally(self):
        """Regression: Tier 1 confession must unconditionally set track='romantic'."""
        from game_engine.state.reducers import _evaluate_npc_milestones
        app = {"predetermined_intercourse": "virgin"}
        _, _, _, _, track, _, _ = _evaluate_npc_milestones(
            npc_name="Lily",
            app_dict=dict(app),
            track="romantic",  # already romantic — should stay so
            milestone_ev="confession",
            custom_summary=None,
            intercourse_exp="",
            oral_exp="",
            actions=[],
            narrative_text="",
            overall_check_success=True,
            is_player_romantic_action=False,
            is_player_intimate_action=False,
            is_player_oral_action=False,
            is_player_intercourse_action=False,
            is_player_confession_action=False,
            is_player_affection_action=False,
            affection_target_npc=None,
            gift_target_npc=None,
            gift_item_name=None,
            confession_target_npc=None,
            first_char_name="Alex",
        )
        self.assertEqual(track, "romantic")

    def test_evaluate_npc_milestones_tier2_confession_reveals_intimate_flags(self):
        """Regression: Tier 2 confession branch must set intimate_revealed + demeanor_revealed."""
        from game_engine.state.reducers import _evaluate_npc_milestones
        app = {"predetermined_intercourse": "virgin"}
        app_copy = dict(app)
        _evaluate_npc_milestones(
            npc_name="Lily",
            app_dict=app_copy,
            track="platonic",
            milestone_ev="",  # no Tier 1
            custom_summary=None,
            intercourse_exp="",
            oral_exp="",
            actions=[],
            narrative_text="confess feelings to lily",
            overall_check_success=True,
            is_player_romantic_action=False,
            is_player_intimate_action=False,
            is_player_oral_action=False,
            is_player_intercourse_action=False,
            is_player_confession_action=True,
            is_player_affection_action=False,
            affection_target_npc=None,
            gift_target_npc=None,
            gift_item_name=None,
            confession_target_npc="Lily",
            first_char_name="Alex",
        )
        self.assertFalse(app_copy.get("intimate_revealed", False), "Confession should not fully unlock explicit intimate profile")
        self.assertTrue(app_copy.get("demeanor_revealed"), "demeanor_revealed not set by confession")
        self.assertTrue(app_copy.get("dynamic_revealed"), "dynamic_revealed not set by confession")

    def test_normalize_appearance_preserves_predetermined_non_virgin_from_default_experience(self):
        """Regression: normalize_appearance must not demote predetermined_intercourse='non_virgin'."""
        app = {
            "predetermined_intercourse": "non_virgin",
            "intercourse_experience": "virgin"
        }
        res = normalize_appearance(app, gender="female", race="human", scen_key="fantasy")
        self.assertEqual(res.get("predetermined_intercourse"), "non_virgin")
        self.assertEqual(res.get("intercourse_experience"), "non_virgin")

    def test_normalize_appearance_preserves_sensitive_spots(self):
        """Regression: normalize_appearance must not drop sensitive_spots."""
        app = {
            "predetermined_intercourse": "virgin",
            "sensitive_spots": "Behind ears, nape of neck"
        }
        res = normalize_appearance(app, gender="female", race="human", scen_key="fantasy")
        self.assertIn("sensitive_spots", res)
        self.assertIn("ears", res["sensitive_spots"].lower())

    def test_normalize_appearance_preserves_oral_manual_for_virgins(self):
        """Regression: normalize_appearance must not wipe oral or manual experience for virgins."""
        app = {
            "predetermined_intercourse": "virgin",
            "oral_experience": "has_done_oral",
            "manual_experience": "has_received_manual"
        }
        res = normalize_appearance(app, gender="female", race="human", scen_key="fantasy")
        self.assertEqual(res.get("predetermined_intercourse"), "virgin")
        self.assertEqual(res.get("oral_experience"), "has_done_oral")
        self.assertEqual(res.get("manual_experience"), "has_received_manual")

    def test_merge_appearance_safely_preserves_dynamic_and_openness(self):
        """Regression: merge_appearance_safely must protect dynamic and openness from arbitrary overwrite."""
        existing = {
            "intimate_dynamic": "Romantic switch",
            "erotic_openness": "shameless",
            "sensitive_spots": "Base of neck"
        }
        incoming = {
            "intimate_dynamic": "Gentle & Yielding",
            "erotic_openness": "prude",
            "sensitive_spots": "Collarbone"
        }
        merged = merge_appearance_safely(existing, incoming)
        self.assertEqual(merged["intimate_dynamic"], "Romantic switch")
        self.assertEqual(merged["erotic_openness"], "shameless")
        self.assertEqual(merged["sensitive_spots"], "Base of neck")

    def test_formatting_custom_bra_underwear_preservation(self):
        """Regression: format_intimate_profile_sections must preserve custom bra/underwear strings."""
        app = {
            "bra": "Black Lace Bralette",
            "underwear": "Matching Silk Panties",
            "underwear_revealed": True,
            "intimate_revealed": True
        }
        sections = format_intimate_profile_sections(app, gender="female", info_level=3)
        under_lines = sections.get("undergarments", [])
        combined = " ".join(under_lines)
        self.assertIn("Black Lace Bralette", combined)
        self.assertIn("Matching Silk Panties", combined)

    def test_reducers_intercourse_reveals_underwear(self):
        """Regression: intercourse milestone must set underwear_revealed=True."""
        from game_engine.state.reducers import _evaluate_npc_milestones
        app = {"predetermined_intercourse": "virgin"}
        app_copy = dict(app)
        _evaluate_npc_milestones(
            npc_name="Selena",
            app_dict=app_copy,
            track="romantic",
            milestone_ev="intercourse",
            custom_summary=None,
            intercourse_exp="virgin",
            oral_exp="inexperienced",
            actions=[],
            narrative_text="",
            overall_check_success=True,
            is_player_romantic_action=False,
            is_player_intimate_action=True,
            is_player_oral_action=False,
            is_player_intercourse_action=True,
            is_player_confession_action=False,
            is_player_affection_action=False,
            affection_target_npc=None,
            gift_target_npc=None,
            gift_item_name=None,
            confession_target_npc=None,
            first_char_name="Alex",
        )
        self.assertTrue(app_copy.get("underwear_revealed"), "underwear_revealed not set by intercourse milestone")

    def test_tag_turn_on_items_no_double_tagging(self):
        """Regression: tag_turn_on_items must not double-tag items with (Physical) or (Action)."""
        from mechanics.social.persona.intimacy.generation import tag_turn_on_items
        raw = "Nape of neck (physical), Ear whispering (action), Collarbone"
        tagged = tag_turn_on_items(raw)
        self.assertNotIn("(physical) (Physical)", tagged)
        self.assertNotIn("(action) (Action)", tagged)
        self.assertIn("Nape of neck (Physical)", tagged)
        self.assertIn("Ear whispering (Action)", tagged)
        self.assertIn("Collarbone (Physical)", tagged)

    def test_topic_aware_npc_context_excludes_past_history_from_shared_player_milestones(self):
        """Regression: build_topic_aware_npc_context must exclude Past History from shared player memories."""
        from mechanics.social.genealogy import build_topic_aware_npc_context
        contact = {
            "name": "Evelyn",
            "intimate_memories": [
                "Past History: Lost virginity and had intercourse 1 time with 'Julian' (Alchemist)",
                "Shared intimate night with Alex"
            ]
        }
        res = build_topic_aware_npc_context(contact, actions=[{"label": "remember when we were together"}])
        self.assertIn("Shared intimate night with Alex", res)
        # Past history with Julian must NOT be injected under established shared memories with the player
        if "[ESTABLISHED SHARED MEMORIES WITH PLAYER" in res:
            shared_block = res.split("[ESTABLISHED SHARED MEMORIES WITH PLAYER")[1]
            self.assertNotIn("Julian", shared_block)

    def test_upsert_contact_preserves_initial_appearance_memories_on_creation(self):
        """Regression: upsert_contact must preserve initial memories in appearance['intimate_memories'] on creation."""
        import db
        from db import get_conn
        with get_conn() as conn:
            conn.execute("INSERT OR IGNORE INTO sessions (id, scenario, narrative, status) VALUES (999991, 'fantasy', 'A cozy room', 'active')")
            conn.execute("DELETE FROM contacts WHERE session_id=999991")
        
        initial_app = {
            "predetermined_intercourse": "virgin",
            "intimate_memories": ["Shared a tender first kiss under the starry canopy"]
        }
        rec = db.upsert_contact(
            session_id=999991,
            character_id=1,
            npc_id="seraphina",
            name="Seraphina",
            appearance=initial_app
        )
        self.assertIn("Shared a tender first kiss under the starry canopy", rec.get("intimate_memories", []))
        self.assertIn("Shared a tender first kiss under the starry canopy", rec.get("appearance", {}).get("intimate_memories", []))

        # Verify reading from db
        fetched = db.get_contact(999991, "seraphina", character_id=1)
        self.assertIsNotNone(fetched)
        self.assertIn("Shared a tender first kiss under the starry canopy", fetched.get("intimate_memories", []))
        self.assertIn("Shared a tender first kiss under the starry canopy", fetched.get("appearance", {}).get("intimate_memories", []))

        # Verify bulk get_contacts
        contacts = db.get_contacts(999991, character_id=1)
        c_found = next((c for c in contacts if c["npc_id"] == "seraphina"), None)
        self.assertIsNotNone(c_found)
        self.assertIn("Shared a tender first kiss under the starry canopy", c_found.get("intimate_memories", []))
        self.assertIn("Shared a tender first kiss under the starry canopy", c_found.get("appearance", {}).get("intimate_memories", []))

    def test_upsert_contact_recovers_and_syncs_memories_bidirectionally(self):
        """Regression: upsert_contact and get_contact sync memories bidirectionally between column and appearance dict."""
        import db
        from db import get_conn
        with get_conn() as conn:
            conn.execute("INSERT OR IGNORE INTO sessions (id, scenario, narrative, status) VALUES (999992, 'fantasy', 'A tavern', 'active')")
            conn.execute("DELETE FROM contacts WHERE session_id=999992")
            # Manually insert row where intimate_memories_json is empty but appearance_json has memories
            import json, time
            app_json = json.dumps({"intimate_memories": ["Recovered memory from appearance blob"]})
            conn.execute(
                """INSERT INTO contacts (session_id, character_id, npc_id, name, basic_info_json,
                                          relationship_score, track, unlocked_traits_json, preferences_json, race, gender, appearance_json, intimate_memories_json, created_at, updated_at)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (999992, 1, "lyra", "Lyra", "{}", 10, "romantic", "[]", "[]", "human", "female", app_json, "[]", time.time(), time.time())
            )

        # get_contact should recover the memory into intimate_memories
        c = db.get_contact(999992, "lyra", character_id=1)
        self.assertIn("Recovered memory from appearance blob", c.get("intimate_memories", []))
        self.assertIn("Recovered memory from appearance blob", c.get("appearance", {}).get("intimate_memories", []))

        # Updating contact with a new memory should append without dropping the recovered memory
        updated = db.upsert_contact(
            session_id=999992,
            character_id=1,
            npc_id="lyra",
            name="Lyra",
            new_memory="Shared a passionate evening"
        )
        self.assertIn("Recovered memory from appearance blob", updated.get("intimate_memories", []))
        self.assertIn("Shared a passionate evening", updated.get("intimate_memories", []))

    def test_player_intimate_action_keywords_detects_manual_stimulation(self):
        """Regression: manual acts like handjob, fingering, and manual stimulation are tagged as intimate actions."""
        from game_engine.keywords import PLAYER_INTIMATE_ACTION_KEYWORDS
        self.assertIn("handjob", PLAYER_INTIMATE_ACTION_KEYWORDS)
        self.assertIn("fingering", PLAYER_INTIMATE_ACTION_KEYWORDS)
        self.assertIn("manual stimulation", PLAYER_INTIMATE_ACTION_KEYWORDS)

if __name__ == "__main__":
    unittest.main()

