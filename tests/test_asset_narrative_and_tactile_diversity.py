import pytest
import sqlite3
import json
from mechanics.social.persona.intimacy.constants import (
    ASSET_SIZE_TIERS,
    FEMALE_ASSET_TEXTURE_TEMPLATES,
    MALE_ASSET_TEXTURE_TEMPLATES,
    SPECIES_TEXTURE_AFFINITIES,
    TIER_INCOMPATIBLE_TEXTURES,
)
from mechanics.social.persona.intimacy.appearance import (
    classify_asset_size_tier,
    extract_asset_texture,
    roll_dynamic_asset_texture,
    normalize_appearance,
)
from mechanics.social.persona.intimacy.formatting import (
    format_body_asset_narrative_directive,
)
import db


class TestAssetNarrativeAndTactileDiversity:

    def test_classify_asset_size_tier_female(self):
        """Tests 5-tier classification across various chest descriptions."""
        # Flat
        assert classify_asset_size_tier("AA-Cup", "female") == "flat"
        assert classify_asset_size_tier("Flat Chest", "female") == "flat"
        assert classify_asset_size_tier("Almost flat", "female") == "flat"

        # Small
        assert classify_asset_size_tier("A-Cup", "female") == "small"
        assert classify_asset_size_tier("Modest B-Cup", "female") == "small"
        assert classify_asset_size_tier("Petite", "female") == "small"

        # Average
        assert classify_asset_size_tier("C-Cup", "female") == "average"
        assert classify_asset_size_tier("Medium", "female") == "average"
        assert classify_asset_size_tier("Proportional", "female") == "average"

        # Large
        assert classify_asset_size_tier("D-Cup", "female") == "large"
        assert classify_asset_size_tier("Voluptuous DD-Cup", "female") == "large"
        assert classify_asset_size_tier("Busty", "female") == "large"

        # Huge
        assert classify_asset_size_tier("E-Cup", "female") == "huge"
        assert classify_asset_size_tier("Bountiful F-Cup", "female") == "huge"
        assert classify_asset_size_tier("Massive", "female") == "huge"

    def test_classify_asset_size_tier_male(self):
        """Tests size tier classification across male asset descriptions."""
        assert classify_asset_size_tier("Tiny", "male") == "flat"
        assert classify_asset_size_tier("Compact", "male") == "small"
        assert classify_asset_size_tier("Average", "male") == "average"
        assert classify_asset_size_tier("Thick and Large", "male") == "large"
        assert classify_asset_size_tier("Huge", "male") == "huge"
        assert classify_asset_size_tier("Massive", "male") == "huge"

    def test_extract_asset_texture_from_compound_string(self):
        """Tests extraction of tactile descriptors from compound size strings."""
        assert extract_asset_texture("Perky B-Cup", "female") == "Perky & High-Set"
        assert extract_asset_texture("Firm & Toned D-Cup", "female") == "Firm & Toned"
        assert extract_asset_texture("Pillowy Soft C-Cup", "female") == "Pillowy Soft & Yielding"
        # Small / flat chests mapped to soft must never receive Pillowy Soft & Yielding
        assert extract_asset_texture("Soft A-Cup", "female") == "Tender & Delicate"
        assert extract_asset_texture("Veined & Firm Average", "male") == "Veined & Firm"

    def test_normalize_appearance_auto_corrects_incompatible_texture(self):
        """Ensures normalize_appearance detects contradictions and replaces incompatible textures."""
        # Flat chest with explicitly passed Pillowy Soft & Yielding
        norm = normalize_appearance(
            raw_app={"breast_size": "Flat AA-Cup", "asset_texture": "Pillowy Soft & Yielding"},
            gender="female",
            race="human",
            scen_key="fantasy_nsfw"
        )
        assert norm["asset_texture"] != "Pillowy Soft & Yielding"
        assert norm["asset_texture"] not in TIER_INCOMPATIBLE_TEXTURES["flat"]

        # Huge chest with explicitly passed Compact & Dense
        norm_huge = normalize_appearance(
            raw_app={"breast_size": "Bountiful F-Cup", "asset_texture": "Compact & Dense"},
            gender="female",
            race="human",
            scen_key="fantasy_nsfw"
        )
        assert norm_huge["asset_texture"] != "Compact & Dense"
        assert norm_huge["asset_texture"] not in TIER_INCOMPATIBLE_TEXTURES["huge"]

    def test_incompatible_texture_exclusion_filter(self):
        """Ensures flat/small never receives heavy/pillowy, and large/huge never receives compact."""
        flat_incompat = TIER_INCOMPATIBLE_TEXTURES.get("flat", set())
        assert "Heavy & Plush" in flat_incompat
        assert "Pillowy Soft & Yielding" in flat_incompat

        # Roll 100 times for flat female asset: must never roll incompatible texture
        for seed in range(100):
            tex = roll_dynamic_asset_texture(
                gender="female",
                size_tier="flat",
                race="Human",
                seed=f"seed_flat_{seed}"
            )
            assert tex not in flat_incompat, f"Flat received incompatible texture: {tex}"

        huge_incompat = TIER_INCOMPATIBLE_TEXTURES.get("huge", set())
        assert "Compact & Dense" in huge_incompat
        for seed in range(100):
            tex = roll_dynamic_asset_texture(
                gender="female",
                size_tier="huge",
                race="Human",
                seed=f"seed_huge_{seed}"
            )
            assert tex not in huge_incompat, f"Huge received incompatible texture: {tex}"

    def test_dynamic_roll_beastfolk_synergy(self):
        """Verifies beastfolk species can receive species-specific fur/scale traits."""
        furred_textures = set(SPECIES_TEXTURE_AFFINITIES["furred"])
        scaled_textures = set(SPECIES_TEXTURE_AFFINITIES["scaled"])

        # Roll across feline beastfolk seeds
        found_furred = False
        for seed in range(50):
            tex = roll_dynamic_asset_texture(
                gender="female",
                size_tier="average",
                race="Beastfolk: Cat / Feline",
                seed=f"cat_seed_{seed}"
            )
            if tex in furred_textures:
                found_furred = True
                break
        assert found_furred, "Beastfolk feline should roll fur-themed texture within 50 rolls"

        # Roll across dragonkin seeds
        found_scaled = False
        for seed in range(50):
            tex = roll_dynamic_asset_texture(
                gender="female",
                size_tier="large",
                race="Dragonkin",
                seed=f"dragon_seed_{seed}"
            )
            if tex in scaled_textures:
                found_scaled = True
                break
        assert found_scaled, "Dragonkin should roll scale-themed texture within 50 rolls"

    def test_directive_formatting_insecure_archetype(self):
        """Verifies small assets + timid/prude archetype produces acute vulnerability directive."""
        directive = format_body_asset_narrative_directive(
            npc_appearance={
                "breast_size": "Flat AA-Cup",
                "asset_texture": "Perky & High-Set",
                "intimate_demeanor": "timid",
            },
            npc_gender="female",
            npc_name="Aria",
            player_appearance={"breast_size": "Voluptuous D-Cup"},
            player_gender="female",
            affinity=70,
        )
        assert "INSECURITY" in directive
        assert "Aria" in directive
        assert "Perky & High-Set" in directive
        assert "REASSURANCE SYNERGY" in directive
        assert "+3 to +4 Affinity" in directive
        # Bidirectional awareness of player's assets (female player has breasts/bust, not pp/length)
        assert "Voluptuous D-Cup" in directive
        assert "breasts / bust" in directive
        assert "pp / length" not in directive

    def test_directive_formatting_boastful_archetype(self):
        """Verifies large assets + bold/dominant archetype produces confident/proud directive."""
        directive = format_body_asset_narrative_directive(
            npc_appearance={
                "breast_size": "Bountiful F-Cup",
                "asset_texture": "Heavy & Plush",
                "intimate_demeanor": "bold",
            },
            npc_gender="female",
            npc_name="Valeria",
            affinity=20,
        )
        assert "BOASTFUL" in directive or "CONFIDENCE" in directive
        assert "Heavy & Plush" in directive
        assert "Valeria" in directive

    def test_directive_beastfolk_nonverbal_cues(self):
        """Verifies beastfolk species include non-verbal anatomical cues."""
        directive = format_body_asset_narrative_directive(
            npc_appearance={
                "breast_size": "Modest B-Cup",
                "asset_texture": "Soft & Downy Chest Fur",
                "intimate_demeanor": "shy",
            },
            npc_gender="female",
            npc_race="Beastfolk: Fox / Vulpine",
            npc_name="Kitsune",
        )
        assert "Beastfolk" in directive or "Fur" in directive or "ears" in directive.lower()

    def test_db_persistence_and_migration_12(self):
        """Tests that character appearance_json persists in SQLite and can be updated."""
        user_id = 888777666555

        # Clean up any existing character for this test user
        with db.UnitOfWork() as conn:
            conn.execute("DELETE FROM characters WHERE user_id = ?", (user_id,))

        # Create character with appearance
        test_app = {
            "breast_size": "Voluptuous D-Cup",
            "asset_texture": "Firm & Toned",
            "eye_color": "amber",
        }
        db.create_character(
            user_id=user_id,
            name="Sylvia",
            gender="Female",
            race="Elf",
            appearance=test_app,
        )

        char = db.get_character(user_id)
        assert char is not None
        assert "appearance" in char
        assert char["appearance"]["breast_size"] == "Voluptuous D-Cup"
        assert char["appearance"]["asset_texture"] == "Firm & Toned"

        # Update character appearance
        updated_char_res = db.update_character_appearance(char["id"], {
            "breast_size": "Bountiful E-Cup",
            "asset_texture": "Pillowy Soft & Yielding",
        })
        assert isinstance(updated_char_res, dict)
        assert updated_char_res["appearance"]["breast_size"] == "Bountiful E-Cup"

        updated_char = db.get_character(user_id)
        assert updated_char["appearance"]["breast_size"] == "Bountiful E-Cup"
        assert updated_char["appearance"]["asset_texture"] == "Pillowy Soft & Yielding"
        # Previously set traits must be preserved
        assert updated_char["appearance"]["eye_color"] == "amber"

        # Clean up
        with db.UnitOfWork() as conn:
            conn.execute("DELETE FROM characters WHERE user_id = ?", (user_id,))

    def test_api_character_appearance_endpoints(self):
        """Tests /api/character/create with appearance payload and /api/character/appearance update."""
        from fastapi.testclient import TestClient
        import server
        client = TestClient(server.app)

        user_id = 99202
        with db.UnitOfWork() as conn:
            conn.execute("DELETE FROM characters WHERE user_id = ?", (user_id,))

        create_payload = {
            "user_id": user_id,
            "name": "Kallista",
            "gender": "Female",
            "race": "Beastfolk / Anthro",
            "race_description": "Feline",
            "char_class": "Rogue",
            "str_val": 1, "per": 2, "end": 1, "cha": 1, "int_val": 1, "agi": 2, "luk": 1,
            "breast_size": "Modest B-Cup",
            "asset_texture": "Soft & Downy Chest Fur",
            "appearance": {
                "breast_size": "Modest B-Cup",
                "asset_texture": "Soft & Downy Chest Fur"
            }
        }
        res = client.post("/api/character/create", json=create_payload)
        assert res.status_code == 200, res.text
        data = res.json()
        assert data["success"] is True
        char_data = data["character"]
        assert char_data["appearance"]["breast_size"] == "Modest B-Cup"
        assert char_data["appearance"]["asset_texture"] == "Soft & Downy Chest Fur"

        # Update appearance endpoint
        update_payload = {
            "user_id": user_id,
            "character_id": char_data["id"],
            "breast_size": "Voluptuous D-Cup",
            "asset_texture": "Pillowy Soft & Yielding"
        }
        up_res = client.post("/api/character/appearance", json=update_payload)
        assert up_res.status_code == 200, up_res.text
        up_data = up_res.json()
        assert up_data["success"] is True
        assert up_data["appearance"]["breast_size"] == "Voluptuous D-Cup"
        assert up_data["appearance"]["asset_texture"] == "Pillowy Soft & Yielding"

        # Clean up
        with db.UnitOfWork() as conn:
            conn.execute("DELETE FROM characters WHERE user_id = ?", (user_id,))

    def test_build_dialogue_prompt_block_party_tolerance(self):
        """Ensures _build_dialogue_prompt_block handles party entries as either (char, inv) tuples or plain char dicts."""
        from game_engine.turn.dialogue import _build_dialogue_prompt_block
        from game_engine.turn_context import TurnContext

        # Test with plain char dicts in party
        plain_char = {
            "name": "Valen",
            "gender": "male",
            "appearance": {"penis_size": "average", "asset_texture": "Veined & Firm"}
        }
        mock_session = {"id": 1, "history": [], "scenario": "fantasy", "current_location": "tavern"}
        ctx = TurnContext(1, mock_session)

        # Party as list of dicts
        block_dict = _build_dialogue_prompt_block(
            mock_session,
            ctx,
            new_partners=["Aria"],
            party=[plain_char],
            actions=[]
        )
        assert isinstance(block_dict, str)

        # Party as list of tuples
        block_tuple = _build_dialogue_prompt_block(
            mock_session,
            ctx,
            new_partners=["Aria"],
            party=[(plain_char, {})],
            actions=[]
        )
        assert isinstance(block_tuple, str)
