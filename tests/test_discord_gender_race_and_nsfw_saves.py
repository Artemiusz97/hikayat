import pytest
import discord
from unittest.mock import AsyncMock, MagicMock
import db
from cogs.character import build_character_sheet_embed, CharacterCog
from cogs.adventure.views.loadout import (
    LoadoutEquipmentPreviewView,
    MALE_SIZE_OPTIONS,
    FEMALE_SIZE_OPTIONS,
    MALE_TEXTURE_OPTIONS,
    FEMALE_TEXTURE_OPTIONS,
)
from mechanics.system.save_system import build_saves_list_embed, build_save_slot_embed


def test_build_character_sheet_embed_with_race_gender_and_intimate():
    char = {
        "id": 101,
        "name": "Kaelen",
        "gender": "Male",
        "race": "kitsune",
        "char_class": "Rogue",
        "class_description": "A stealthy scout",
        "level": 3,
        "xp": 350,
        "hp": 25,
        "max_hp": 30,
        "mp": 15,
        "max_mp": 20,
        "gold": 120,
        "str_": 2, "per_": 4, "end_": 2, "cha": 3, "int_": 2, "agi": 4, "luk": 3,
        "scenario": "fantasy",
        "penis_size": "large",
        "asset_texture": "Veined & Firm"
    }
    equipment = {}
    embed = build_character_sheet_embed(char, equipment)
    
    # Check Identity field has race and gender
    fields = {f.name: f.value for f in embed.fields}
    assert "Identity" in fields
    assert "Kitsune" in fields["Identity"]
    assert "Male" in fields["Identity"]
    
    # Check Intimate Anatomy field
    assert "🔞 Intimate Anatomy" in fields
    assert "Large" in fields["🔞 Intimate Anatomy"]
    assert "Veined & Firm" in fields["🔞 Intimate Anatomy"]


@pytest.mark.asyncio
async def test_character_list_and_switch_embed_displays_race_and_gender():
    uid = 999980001
    db.delete_character(uid)
    
    # Create character with race & gender
    char = db.create_character(uid, "Elysia", "Mage", "Mystic seer", gender="Female", race="elf")
    
    cog = CharacterCog(MagicMock())
    
    # Mock Interaction for list_characters
    interaction = MagicMock(spec=discord.Interaction)
    interaction.user.id = uid
    interaction.user.display_name = "PlayerOne"
    interaction.response.send_message = AsyncMock()
    
    await cog.list_characters.callback(cog, interaction)
    
    interaction.response.send_message.assert_called_once()
    embed = interaction.response.send_message.call_args.kwargs.get("embed")
    assert embed is not None
    assert "PlayerOne's Characters (1/6)" in embed.title
    
    # Check that embed fields contain race and gender
    field_value = embed.fields[0].value
    assert "**Race & Gender:** Elf | Female" in field_value
    
    # Mock switch autocomplete
    choices = await cog.switch_autocomplete(interaction, "")
    assert len(choices) == 1
    assert "Elf Female" in choices[0].name
    
    # Mock switch command
    interaction_switch = MagicMock(spec=discord.Interaction)
    interaction_switch.user.id = uid
    interaction_switch.response.send_message = AsyncMock()
    await cog.switch.callback(cog, interaction_switch, "Elysia")
    
    interaction_switch.response.send_message.assert_called_once()
    switch_embed = interaction_switch.response.send_message.call_args.kwargs.get("embed")
    assert switch_embed is not None
    assert "**Race & Gender:** Elf | Female" in switch_embed.description
    
    db.delete_character(uid)


def test_nsfw_loadout_preview_male_gender_aware():
    uid = 999980002
    db.delete_character(uid)
    char = db.create_character(uid, "Brom", "Warrior", "Heavy brawler", gender="Male", race="human")
    
    cog_mock = MagicMock()
    session_config = {
        "mode": "solo",
        "scenario": "fantasy",
        "tags": "fantasy, nsfw",
        "verbosity": "normal",
        "dialogue": "balanced",
        "image_gen": False,
        "choices_style": "dropdown",
        "result_display": "detailed"
    }
    
    view = LoadoutEquipmentPreviewView(
        cog=cog_mock,
        user_id=uid,
        session_config=session_config,
        char_class="Warrior",
        class_description="Heavy brawler",
        weapon_name="Iron Broadsword",
        weapon_description="A sturdy blade"
    )
    
    assert view._is_nsfw() is True
    
    # Inspect children components
    selects = [c for c in view.children if isinstance(c, discord.ui.Select)]
    buttons = [c for c in view.children if isinstance(c, discord.ui.Button)]
    
    # Should have Roll Feature button in buttons
    roll_btns = [b for b in buttons if b.label == "Roll Feature"]
    assert len(roll_btns) == 1
    
    # Should have 2 Selects: Size (Penis) & Texture (Phallus)
    assert len(selects) == 2
    size_select = selects[0]
    tex_select = selects[1]
    
    assert "Penis" in size_select.placeholder
    assert "Phallus" in tex_select.placeholder
    
    # Verify male size options only
    size_values = [o.value for o in size_select.options]
    assert "small" in size_values
    assert "average" in size_values
    assert "huge" in size_values
    assert "flat" not in size_values  # flat is female-only breast size
    
    # Verify male textures only
    tex_labels = [o.label for o in tex_select.options]
    assert any("Veined" in l for l in tex_labels)
    assert not any("Teardrop" in l for l in tex_labels)  # female breast shape
    assert not any("Pillowy Soft" in l for l in tex_labels)
    
    db.delete_character(uid)


def test_nsfw_loadout_preview_female_gender_aware():
    uid = 999980003
    db.delete_character(uid)
    char = db.create_character(uid, "Lyra", "Priestess", "Holy healer", gender="Female", race="elf")
    
    cog_mock = MagicMock()
    session_config = {
        "mode": "solo",
        "scenario": "custom_combinator_fantasy_nsfw",
        "tags": "fantasy, nsfw",
        "verbosity": "normal",
        "dialogue": "balanced",
        "image_gen": False,
        "choices_style": "dropdown",
        "result_display": "detailed"
    }
    
    view = LoadoutEquipmentPreviewView(
        cog=cog_mock,
        user_id=uid,
        session_config=session_config,
        char_class="Priestess",
        class_description="Holy healer",
        weapon_name="Oak Staff",
        weapon_description="Healing staff"
    )
    
    assert view._is_nsfw() is True
    
    selects = [c for c in view.children if isinstance(c, discord.ui.Select)]
    assert len(selects) == 2
    size_select = selects[0]
    tex_select = selects[1]
    
    assert "Breast" in size_select.placeholder
    assert "Breasts" in tex_select.placeholder
    
    # Verify female size options
    size_values = [o.value for o in size_select.options]
    assert "flat" in size_values
    assert "small" in size_values
    assert "large" in size_values
    assert "huge" in size_values
    
    # Verify female textures only
    tex_labels = [o.label for o in tex_select.options]
    assert any("Perky" in l for l in tex_labels)
    assert any("Teardrop" in l for l in tex_labels)
    assert not any("Veined" in l for l in tex_labels)
    
    db.delete_character(uid)


def test_non_nsfw_loadout_preview_hides_intimate_selectors():
    uid = 999980004
    db.delete_character(uid)
    char = db.create_character(uid, "Arthur", "Paladin", "Holy knight", gender="Male", race="human")
    
    cog_mock = MagicMock()
    session_config = {
        "mode": "solo",
        "scenario": "fantasy",
        "tags": "fantasy",
        "verbosity": "normal",
        "dialogue": "balanced",
        "image_gen": False,
        "choices_style": "dropdown",
        "result_display": "detailed"
    }
    
    view = LoadoutEquipmentPreviewView(
        cog=cog_mock,
        user_id=uid,
        session_config=session_config,
        char_class="Paladin",
        class_description="Holy knight",
        weapon_name="Sword of Light",
        weapon_description="A radiant blade"
    )
    
    assert view._is_nsfw() is False
    
    selects = [c for c in view.children if isinstance(c, discord.ui.Select)]
    buttons = [c for c in view.children if isinstance(c, discord.ui.Button)]
    
    assert len(selects) == 0
    assert not any(b.label == "Roll Feature" for b in buttons)
    
    db.delete_character(uid)


def test_save_list_embed_displays_race_gender_and_character_isolation():
    char = {
        "id": 201,
        "name": "Valerius",
        "race": "demon",
        "gender": "Male",
        "char_class": "Warlock",
        "level": 4
    }
    saves = [
        {
            "slot_name": "Gate of Shadows",
            "scenario": "dark_fantasy",
            "current_location": "Underworld Spire",
            "scene_title": "Before the Portal",
            "saved_at": 1700000000,
            "narrative_snippet": "Dark flames lick the pillars..."
        }
    ]
    embed = build_saves_list_embed(saves, char)
    
    assert "Valerius" in embed.title
    assert "Demon | Male | Lvl 4 Warlock" in embed.description
    assert "Showing **1/6** saved adventure slots" in embed.description
    assert "Valerius" in embed.footer.text
    assert "up to 6 slots" in embed.footer.text
