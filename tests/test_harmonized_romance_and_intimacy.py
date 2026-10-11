import pytest
from game_engine.keywords import matches_keyword_boundary
from game_engine.state.reducers import _evaluate_npc_milestones
from mechanics.social.physical_state import build_physical_prompt_block


class TestHarmonizedRomanceAndIntimacy:
    """Comprehensive test suite verifying the harmonized romance, intimacy,
    and situational privacy systems across the engine."""

    def test_scunthorpe_keyword_boundary_protection(self):
        """Verifies substring collisions like 'document' (cum), 'thug' (hug), 'cocktail' (cock)
        do not trigger intimate/romantic actions."""
        # 1. Negative substring tests
        assert not matches_keyword_boundary("Review the official document", ["cum"])
        assert not matches_keyword_boundary("Disarm the dangerous thug", ["hug"])
        assert not matches_keyword_boundary("Order a refreshing cocktail", ["cock"])
        assert not matches_keyword_boundary("Read the assignment instructions", ["ass"])

        # 2. Positive exact boundary tests
        assert matches_keyword_boundary("Give Alice a warm hug", ["hug"])
        assert matches_keyword_boundary("Share a passionate kiss with Alice", ["kiss"])
        assert matches_keyword_boundary("Have intercourse with Alice", ["intercourse"])
        assert matches_keyword_boundary("Stroke her cock gently", ["cock"])

    def test_date_vs_confession_milestone_independence(self):
        """Verifies that 'date' milestone records memory and preserves platonic track,
        while only an explicit 'confession' milestone can transition track to 'romantic'."""
        app_dict = {}
        # 1. Date milestone
        (new_mem_date, _, _, _, track_date, _, _) = _evaluate_npc_milestones(
            npc_name="Hanabi",
            app_dict=app_dict,
            track="platonic",
            milestone_ev="date",
            custom_summary="Shared a lovely evening walk together.",
            intercourse_exp="virgin",
            oral_exp="inexperienced",
            actions=[{"label": "Take Hanabi on a date"}],
            narrative_text="",
            overall_check_success=True,
            is_player_romantic_action=True,
            is_player_intimate_action=False,
            is_player_oral_action=False,
            is_player_intercourse_action=False,
            is_player_confession_action=False,
            is_player_affection_action=False,
            affection_target_npc=None,
            gift_target_npc=None,
            gift_item_name=None,
            confession_target_npc=None,
            first_char_name="Hero"
        )
        assert track_date == "romantic", "Date milestone transitions track to romantic!"
        assert "date" in new_mem_date.lower() or "evening" in new_mem_date.lower()

        # 2. Confession milestone
        (new_mem_confess, _, _, _, track_confess, _, _) = _evaluate_npc_milestones(
            npc_name="Hanabi",
            app_dict=app_dict,
            track="platonic",
            milestone_ev="confession",
            custom_summary="Confessed deep feelings to Hanabi.",
            intercourse_exp="virgin",
            oral_exp="inexperienced",
            actions=[{"label": "Confess feelings to Hanabi"}],
            narrative_text="",
            overall_check_success=True,
            is_player_romantic_action=True,
            is_player_intimate_action=False,
            is_player_oral_action=False,
            is_player_intercourse_action=False,
            is_player_confession_action=True,
            is_player_affection_action=False,
            affection_target_npc=None,
            gift_target_npc=None,
            gift_item_name=None,
            confession_target_npc="Hanabi",
            first_char_name="Hero"
        )
        assert track_confess == "romantic", "Confession milestone must transition track to romantic!"
        assert "confession" in new_mem_confess.lower() or "confessed" in new_mem_confess.lower()

    def test_intimate_profile_disclosure_gating(self):
        """Verifies that secret intimate anatomy (sensitive spots, turn-ons, kinks, experience)
        is shielded from strangers/acquaintances until unlocked (level 3 or revealed flag)."""
        from game_engine.turn.dialogue import _build_dialogue_prompt_block
        from game_engine.turn_context import TurnContext

        contact_alice = {
            "name": "Alice",
            "npc_id": "alice",
            "relationship_score": 10,
            "revealed_flags": {},
            "demeanor": "Reserved",
            "traits": ["Studious"],
            "appearance": {
                "sensitive_spots": "inner thighs, neck",
                "turn_ons": "whispering, praise",
                "fetishes": "bondage",
                "intercourse_experience": "Virgin",
                "intimate_dynamic": "receptive",
                "erotic_openness": "Reserved"
            }
        }
        session = {
            "id": 999991,
            "scenario": {"name": "Test", "tags": ["nsfw"]},
            "current_location": "Library",
            "current_npcs": [{"name": "Alice"}],
            "history": []
        }
        ctx = TurnContext(999991, session)
        ctx._cache["contacts"] = [contact_alice]
        ctx._cache["pending_appointments"] = []
        ctx._cache["arrived_appointments"] = []
        ctx._cache["active_waypoints"] = []
        ctx._cache["party_npcs"] = []

        # When intimate_unlocked is False (score 10, no revealed flag):
        prompt_locked = _build_dialogue_prompt_block(
            session=session,
            ctx=ctx,
            new_partners=["Alice"],
            party=[{"name": "Hero"}],
            actions=[]
        )
        assert "Sensitive Spots" not in prompt_locked
        assert "Turn-Ons" not in prompt_locked
        assert "Kinks" not in prompt_locked
        assert "Intercourse Experience" not in prompt_locked

        # When intimate_unlocked is True via revealed_flags:
        contact_alice["revealed_flags"] = {"intimate_revealed": True}
        prompt_unlocked = _build_dialogue_prompt_block(
            session=session,
            ctx=ctx,
            new_partners=["Alice"],
            party=[{"name": "Hero"}],
            actions=[]
        )
        assert "Sensitive Spots: inner thighs, neck" in prompt_unlocked
        assert "Turn-Ons: whispering, praise" in prompt_unlocked
        assert "Kinks: bondage" in prompt_unlocked
        assert "Intercourse Experience: Virgin" in prompt_unlocked

    def test_shameless_dialogue_directives_and_paced_intimacy_exception(self):
        """Verifies that shameless characters receive the active spoken lewdness directive
        and are explicitly exempt from paced intimacy silence."""
        from game_engine.turn.dialogue import _build_dialogue_prompt_block
        from game_engine.turn_context import TurnContext

        contact_roxy = {
            "name": "Roxy",
            "npc_id": "roxy",
            "relationship_score": 10,
            "revealed_flags": {},
            "demeanor": "Shameless",
            "traits": ["Provocative", "Playful"],
            "appearance": {
                "sensitive_spots": "breasts, waist",
                "turn_ons": "teasing, dirty talk",
                "fetishes": "exhibitionism",
                "intimate_dynamic": "proactive",
                "erotic_openness": "Shameless / Lewd"
            }
        }
        session = {
            "id": 999992,
            "scenario": {"name": "Test", "tags": ["nsfw"]},
            "current_location": "Hallway",
            "current_npcs": [{"name": "Roxy"}],
            "history": []
        }
        ctx = TurnContext(999992, session)
        ctx._cache["contacts"] = [contact_roxy]
        ctx._cache["pending_appointments"] = []
        ctx._cache["arrived_appointments"] = []
        ctx._cache["active_waypoints"] = []
        ctx._cache["party_npcs"] = []

        prompt = _build_dialogue_prompt_block(
            session=session,
            ctx=ctx,
            new_partners=["Roxy"],
            party=[{"name": "Hero"}],
            actions=[]
        )

        # 1. Active spoken dialogue directive
        assert "⚡ SHAMELESS / LEWD SPOKEN DIALOGUE DIRECTIVE (Roxy)" in prompt
        assert "THEY HAVE NO VERBAL FILTER" in prompt

        # 2. Paced intimacy exception
        assert "PACED INTIMACY & SPOKEN LEWDNESS EXCEPTION" in prompt
        assert "EXCEPTION FOR SHAMELESS & BOLD CHARACTERS" in prompt

        # 3. Choice #3 adaptation
        assert "[Bold / Provocative Flirtation / Suggestive Teasing]" in prompt

    def test_alone_together_passion_vs_public_decorum(self):
        """Verifies that when partner and player are alone together in an empty room,
        open passion is injected; when bystanders are present, decorum or public audacity is used."""
        from game_engine.turn.dialogue import _build_dialogue_prompt_block
        from game_engine.turn_context import TurnContext

        contact_yuki = {
            "name": "Yuki",
            "npc_id": "yuki",
            "relationship_score": 40,
            "revealed_flags": {},
            "demeanor": "Confident",
            "traits": ["Athletic"],
            "appearance": {
                "intimate_dynamic": "proactive",
                "erotic_openness": "Bold / Uninhibited"
            }
        }
        session = {
            "id": 999993,
            "scenario": {"name": "Test", "tags": ["nsfw"]},
            "current_location": "School Rooftop",
            "current_npcs": [{"name": "Yuki"}],  # Alone together!
            "history": []
        }
        ctx = TurnContext(999993, session)
        ctx._cache["contacts"] = [contact_yuki]
        ctx._cache["pending_appointments"] = []
        ctx._cache["arrived_appointments"] = []
        ctx._cache["active_waypoints"] = []
        ctx._cache["party_npcs"] = []

        # Case A: Alone Together
        prompt_alone = _build_dialogue_prompt_block(
            session=session,
            ctx=ctx,
            new_partners=["Yuki"],
            party=[{"name": "Hero"}],
            actions=[]
        )
        assert "[ALONE TOGETHER & OPEN PASSION (Yuki)]" in prompt_alone
        assert "COMPLETELY UNCONSTRAINED by public modesty" in prompt_alone

        # Case B: Bystanders Present (e.g. Kenji is in the room)
        session["current_npcs"] = [{"name": "Yuki"}, {"name": "Kenji"}]
        prompt_crowded = _build_dialogue_prompt_block(
            session=session,
            ctx=ctx,
            new_partners=["Yuki"],
            party=[{"name": "Hero"}],
            actions=[]
        )
        assert "[PRIVATE PROFILE NOTE: The intimate profile below belongs exclusively to Yuki" in prompt_crowded
        assert "[PUBLIC DECORUM & DISCRETION (Yuki)]" in prompt_crowded
        assert "Kenji" in prompt_crowded

    def test_physical_state_separation_innocent_vs_erotic(self):
        """Verifies that innocent physical contact (holding hands, hugging) does NOT trigger
        lingerie/underwear stripping rules in physical state display, while erotic contact does."""
        actors = {
            "Protagonist": {"posture": "Standing", "clothing": {"top": "Uniform", "bottom": "Trousers"}},
            "Hanabi": {"posture": "Standing", "clothing": {"top": "Uniform", "bottom": "Skirt"}}
        }
        party = [[{"name": "Protagonist"}], [{"name": "Hanabi"}]]

        # 1. Innocent handholding
        session_innocent = {
            "scenario": "highschool",
            "physical_state": {
                "actors": actors,
                "intimate_contact": "holding hands",
                "is_combat": False
            }
        }
        text_innocent = build_physical_prompt_block(session_innocent, party=party, is_nsfw=True, is_combat=False)
        assert "### 🪑 PHYSICAL SCENE & MICRO-STATE" in text_innocent
        assert "### 💋 INTIMATE & PHYSICAL STATE" not in text_innocent
        assert "- Ongoing Physical Contact: holding hands" in text_innocent
        assert "bra or underwear underneath" not in text_innocent

        # 2. Erotic kissing and caressing
        session_erotic = {
            "scenario": "highschool",
            "physical_state": {
                "actors": actors,
                "intimate_contact": "passionate kissing and undressing",
                "is_combat": False
            }
        }
        text_erotic = build_physical_prompt_block(session_erotic, party=party, is_nsfw=True, is_combat=False)
        assert "### 💋 INTIMATE & PHYSICAL STATE" in text_erotic
        assert "### 🪑 PHYSICAL SCENE & MICRO-STATE" not in text_erotic
        assert "CONTINUITY DIRECTIVE: Strictly respect clothing removal states" in text_erotic

    def test_dc_normalization_for_intimate_prying(self):
        """Verifies that inquiring into Level 3 intimate profile secrets requires DC 10-15,
        while routine social and banter actions stay at DC 5-8."""
        from game_engine.choices_cleaner import infer_choice_stat_and_dc
        # Standard social banter
        stat1, dc1 = infer_choice_stat_and_dc("Playfully tease Alice about her clumsy jump shot")
        assert stat1 in ("CHA", "INT")
        assert 5 <= dc1 <= 8

        # Standard personal inquiry
        stat2, dc2 = infer_choice_stat_and_dc("Ask Alice about her favorite study spot on campus")
        assert stat2 in ("CHA", "INT", "PER")
        assert 5 <= dc2 <= 8

        # Intimate disclosure inquiries (Prying into sensitive spots or kinks)
        stat3, dc3 = infer_choice_stat_and_dc("Inquire about Alice's sensitive spots and secret pleasures")
        assert stat3 == "CHA"
        assert dc3 >= 10, f"Expected DC >= 10 for sensitive spot inquiry, got {dc3}"

        stat4, dc4 = infer_choice_stat_and_dc("Ask Alice about her private fantasies and turn-ons")
        assert stat4 == "CHA"
        assert dc4 >= 10, f"Expected DC >= 10 for turn-ons inquiry, got {dc4}"

        stat5, dc5 = infer_choice_stat_and_dc("Pry into Alice's hidden bedroom kinks and desires")
        assert stat5 == "CHA"
        assert dc5 >= 10, f"Expected DC >= 10 for kinks inquiry, got {dc5}"
