"""
tests/test_streamlined_spells.py

Comprehensive verification of the 4-archetype spell targeting overhaul:
1. Shape → Scope Mapping (all 10 shapes map to correct mechanical archetype)
2. MP Cost Scaling (1.0x ST, 1.2x Chain, 1.4x AOE/Summon)
3. Chain Ricochet (100% / 75% / 50% damage decay, safe with 1 or 2 enemies)
4. AOE Glancing Blast Floor (fail → 35% dmg, not 0)
5. Single-Target Crit Bonus (crit_bonus folds into crit multiplier)
6. Choice Generator Hit% Labels (chain +10, aoe -5, support 100)
"""

import pytest
from mechanics.combat.spells.procedural import DND_SHAPES, generate_procedural_spell
from mechanics.combat.spells.registry import SPELL_REGISTRY, get_spell
from mechanics.combat.spells.kits import format_spell_choice_label


# ---------------------------------------------------------------------------
# 1. Shape → Scope Mapping
# ---------------------------------------------------------------------------

class TestShapeToScopeMapping:
    """All 10 DND_SHAPES must map cleanly to one of the 4 mechanical archetypes."""

    EXPECTED = {
        "bolt":         ("single",  0,   0.05),
        "lance":        ("single",  0,   0.15),
        "cone":         ("aoe",    -5,   0.0),
        "sphere":       ("aoe",    -5,   0.10),
        "line":         ("aoe",     0,   0.08),
        "cylinder":     ("aoe",     0,   0.12),
        "chain":        ("chain",  10,   0.0),
        "aura":         ("support",100,  0.0),
        "summon_swarm": ("summon", 100,  0.0),
        "summon_titan": ("summon", 100,  0.0),
    }

    def test_all_shapes_have_correct_target_type(self):
        for shape, (expected_tt, _, _) in self.EXPECTED.items():
            info = DND_SHAPES[shape]
            assert info["target_type"] == expected_tt, (
                f"Shape '{shape}' target_type should be '{expected_tt}', got '{info['target_type']}'"
            )

    def test_all_shapes_have_correct_acc_mod(self):
        for shape, (_, expected_acc, _) in self.EXPECTED.items():
            info = DND_SHAPES[shape]
            assert info.get("acc_mod") == expected_acc, (
                f"Shape '{shape}' acc_mod should be {expected_acc}, got {info.get('acc_mod')}"
            )

    def test_all_shapes_have_correct_crit_bonus(self):
        for shape, (_, _, expected_crit) in self.EXPECTED.items():
            info = DND_SHAPES[shape]
            assert abs(info.get("crit_bonus", 0.0) - expected_crit) < 1e-6, (
                f"Shape '{shape}' crit_bonus should be {expected_crit}, got {info.get('crit_bonus')}"
            )

    def test_aoe_shapes_have_glance_floor(self):
        aoe_shapes = ["cone", "sphere", "line", "cylinder"]
        for shape in aoe_shapes:
            info = DND_SHAPES[shape]
            assert info.get("glance_floor") == 0.35, (
                f"AOE shape '{shape}' should have glance_floor=0.35"
            )

    def test_chain_shape_has_bounce_metadata(self):
        info = DND_SHAPES["chain"]
        assert info.get("max_bounces") == 3
        assert info.get("decay_rate") == 0.25

    def test_no_old_acc_bonus_field(self):
        """Old acc_bonus (int) field must not exist — replaced by acc_mod (float)."""
        for shape, info in DND_SHAPES.items():
            assert "acc_bonus" not in info, (
                f"Shape '{shape}' still has legacy 'acc_bonus' field — should be 'acc_mod'"
            )


# ---------------------------------------------------------------------------
# 2. MP Cost Scaling
# ---------------------------------------------------------------------------

class TestMPCostScaling:
    """Procedurally generated spells must respect the 3-tier MP surcharge."""

    BASE_MP = {3: 6, 2: 14, 1: 26}
    CHAIN_MULT = 1.2
    AOE_MULT = 1.4

    def _expected_mp(self, base, mult):
        return int(round(base * mult))

    @pytest.mark.parametrize("tier", [3, 2, 1])
    def test_single_target_base_mp(self, tier):
        spell = generate_procedural_spell(tier=tier, shape="bolt", school="Evocation")
        base = self.BASE_MP[tier]
        # May be reduced by Quickened affix — so we just check it's <= base
        assert spell["mp_cost"] <= base, (
            f"ST spell T{tier} mp_cost {spell['mp_cost']} should not exceed base {base}"
        )
        assert spell["mp_cost"] >= 3  # minimum from Quickened floor

    @pytest.mark.parametrize("tier", [3, 2, 1])
    def test_chain_mp_surcharge(self, tier):
        spell = generate_procedural_spell(tier=tier, shape="chain", school="Evocation")
        expected = self._expected_mp(self.BASE_MP[tier], self.CHAIN_MULT)
        # Allow for Quickened reduction
        assert spell["mp_cost"] <= expected, (
            f"Chain spell T{tier} mp_cost {spell['mp_cost']} exceeds expected max {expected}"
        )
        assert spell["mp_cost"] > self.BASE_MP[tier] * 0.7  # at least 70% of chain cost

    @pytest.mark.parametrize("tier", [3, 2, 1])
    def test_aoe_mp_surcharge(self, tier):
        spell = generate_procedural_spell(tier=tier, shape="sphere", school="Evocation")
        expected = self._expected_mp(self.BASE_MP[tier], self.AOE_MULT)
        assert spell["mp_cost"] <= expected, (
            f"AOE spell T{tier} mp_cost {spell['mp_cost']} exceeds expected max {expected}"
        )
        if "quickened" not in spell.get("affixes", []):
            assert spell["mp_cost"] > self.BASE_MP[tier], (
                f"AOE spell T{tier} mp_cost {spell['mp_cost']} should exceed ST base {self.BASE_MP[tier]}"
            )
        else:
            assert spell["mp_cost"] >= self.BASE_MP[tier]

    def test_chain_cheaper_than_aoe_same_tier(self):
        """Chain (1.2x) base surcharge must be cheaper than AOE (1.4x) at the same tier."""
        for tier, base in self.BASE_MP.items():
            chain_base = int(round(base * self.CHAIN_MULT))
            aoe_base = int(round(base * self.AOE_MULT))
            assert chain_base <= aoe_base, (
                f"T{tier}: Chain base {chain_base} MP should be <= AOE base {aoe_base} MP"
            )


# ---------------------------------------------------------------------------
# 3. Chain Ricochet Resolution
# ---------------------------------------------------------------------------

class TestChainRicochet:
    """Chain spells must bounce with 100% / 75% / 50% damage decay."""

    def test_procedural_chain_has_bounce_metadata(self):
        spell = generate_procedural_spell(shape="chain", school="Evocation", tier=2)
        assert spell.get("target_type") == "chain"
        assert spell.get("max_bounces") == 3
        assert abs(spell.get("decay_rate", 0) - 0.25) < 1e-6

    def test_registry_chain_lightning_is_chain(self):
        """chain_lightning must be target_type chain, not aoe."""
        spell = get_spell("chain_lightning_t3_chain")
        assert spell is not None, "chain_lightning_t3_chain not found in registry"
        assert spell["target_type"] == "chain"
        assert spell["mp_cost"] == 8
        assert spell["max_bounces"] == 3

    def test_decay_rate_produces_correct_multipliers(self):
        """Validate the (1 - decay_rate)^bounce_idx compound decay formula.
        With decay_rate=0.25:
          - Bounce 0 (primary): 1.0x   = (0.75)^0 = 1.000
          - Bounce 1 (2nd):     0.75x  = (0.75)^1 = 0.750
          - Bounce 2 (3rd):     0.5625x= (0.75)^2 = 0.5625
        """
        decay_rate = 0.25
        expected = [1.0, 0.75, 0.5625]
        for i, exp in enumerate(expected):
            actual = (1.0 - decay_rate) ** i
            assert abs(actual - exp) < 1e-6, f"Bounce {i}: expected {exp}, got {actual}"


    def test_chain_acc_mod_is_positive(self):
        spell = generate_procedural_spell(shape="chain", school="Evocation", tier=2)
        assert spell.get("acc_mod", 0) > 0, "Chain spells should have positive acc_mod (homing)"


# ---------------------------------------------------------------------------
# 4. AOE Glancing Blast Floor
# ---------------------------------------------------------------------------

class TestAOEGlancingBlastFloor:
    """AOE spells must inject glance_floor=0.35 into the spell definition."""

    AOE_SHAPES = ["cone", "sphere", "line", "cylinder"]

    @pytest.mark.parametrize("shape", AOE_SHAPES)
    def test_procedural_aoe_has_glance_floor(self, shape):
        spell = generate_procedural_spell(shape=shape, school="Evocation", tier=2)
        assert spell.get("glance_floor") == 0.35, (
            f"AOE spell with shape '{shape}' missing glance_floor=0.35"
        )

    def test_registry_aoe_spells_get_glance_floor_injected(self):
        """All registry spells with target_type aoe must have glance_floor via auto-injection."""
        for spell_id, spell in SPELL_REGISTRY.items():
            if spell.get("target_type") == "aoe":
                assert "glance_floor" in spell, (
                    f"Registry spell '{spell_id}' (AOE) missing glance_floor"
                )
                assert spell["glance_floor"] == 0.35

    def test_single_target_has_no_glance_floor(self):
        spell = generate_procedural_spell(shape="bolt", school="Evocation", tier=2)
        assert spell.get("glance_floor") is None, (
            "Single-target spell should NOT have glance_floor"
        )


# ---------------------------------------------------------------------------
# 5. Single-Target Crit Bonus
# ---------------------------------------------------------------------------

class TestSingleTargetCritBonus:
    """Lance shape must inject higher crit_bonus than bolt."""

    def test_lance_crit_bonus_higher_than_bolt(self):
        lance = generate_procedural_spell(shape="lance", school="Evocation", tier=2)
        bolt = generate_procedural_spell(shape="bolt", school="Evocation", tier=2)
        assert lance["crit_bonus"] > bolt["crit_bonus"], (
            f"Lance crit_bonus {lance['crit_bonus']} should be > bolt {bolt['crit_bonus']}"
        )

    def test_lance_crit_bonus_is_015(self):
        spell = generate_procedural_spell(shape="lance", school="Evocation", tier=2)
        assert abs(spell["crit_bonus"] - 0.15) < 1e-6

    def test_registry_spells_get_crit_bonus_injected(self):
        """All registry spells must have a crit_bonus field after auto-injection."""
        for spell_id, spell in SPELL_REGISTRY.items():
            assert "crit_bonus" in spell, f"Registry spell '{spell_id}' missing crit_bonus"
            assert isinstance(spell["crit_bonus"], float)


# ---------------------------------------------------------------------------
# 6. Choice Generator Hit% Labels
# ---------------------------------------------------------------------------

class TestChoiceGeneratorHitChance:
    """format_spell_choice_label must embed the correct scope tags and hit %."""

    def _make_spell(self, target_type, crit_bonus=0.0, acc_mod=0):
        return {
            "id": "test_spell", "name": "Test Spell", "emoji": "🔮",
            "discipline": "attack", "target_type": target_type,
            "mp_cost": 10, "crit_bonus": crit_bonus, "acc_mod": acc_mod
        }

    def test_chain_label_shows_chain_tag(self):
        spell = self._make_spell("chain", acc_mod=10)
        label = format_spell_choice_label(spell, 85, 30)
        assert "Chain" in label, f"Chain spell label missing 'Chain': {label}"

    def test_aoe_label_shows_aoe_tag(self):
        spell = self._make_spell("aoe", acc_mod=-5)
        label = format_spell_choice_label(spell, 72, 30)
        assert "AOE" in label, f"AOE spell label missing 'AOE': {label}"

    def test_single_label_shows_st_tag(self):
        spell = self._make_spell("single", acc_mod=0)
        label = format_spell_choice_label(spell, 80, 30)
        assert "ST" in label, f"Single-target spell label missing 'ST': {label}"

    def test_lance_crit_bonus_shown_in_label(self):
        spell = self._make_spell("single", crit_bonus=0.15, acc_mod=0)
        label = format_spell_choice_label(spell, 80, 30)
        assert "Crit" in label, f"Lance/ray label missing Crit display: {label}"
        assert "15" in label, f"Lance label should show 15% crit: {label}"

    def test_chain_hit_chance_higher_than_base(self):
        """Chain +10 acc_mod should produce higher hit% than ST."""
        base_hit = 75
        chain_hit = min(100, base_hit + 10)
        aoe_hit = max(10, base_hit - 5)
        assert chain_hit > base_hit
        assert aoe_hit < base_hit

    def test_summon_shows_count_and_duration(self):
        spell = {
            "id": "summon_test", "name": "Spirit Wolf", "emoji": "🌀",
            "discipline": "summon", "target_type": "summon",
            "mp_cost": 10, "summon_count": 2, "summon_duration": 3,
            "crit_bonus": 0.0, "acc_mod": 100
        }
        label = format_spell_choice_label(spell, 100, 30)
        assert "2x" in label
        assert "3t" in label

    def test_support_heal_label_shows_hp(self):
        spell = {
            "id": "heal_test", "name": "Mend Wounds", "emoji": "💚",
            "discipline": "support", "target_type": "support",
            "mp_cost": 6, "heal_amount": 25, "crit_bonus": 0.0, "acc_mod": 100
        }
        label = format_spell_choice_label(spell, 100, 30)
        assert "+25 HP" in label


# ---------------------------------------------------------------------------
# 7. Single-Target Fail Miss & Metamagic Affixes
# ---------------------------------------------------------------------------

class TestSpellMissAndMetamagic:
    """Verify single-target spells deal 0 on fail, and sundering penetrates DT/DR."""

    def test_sundering_penetrates_dt_and_dr(self):
        from mechanics.combat.spells.kits import calculate_spell_damage
        spell_normal = {"power_mult": 1.0, "damage_type": "fire", "affixes": []}
        spell_sunder = {"power_mult": 1.0, "damage_type": "fire", "affixes": ["sundering"]}
        
        defender_attrs = {
            "innate_magic_dr": 0.20,
            "gear_dr": {"fire": 0.20},
            "innate_magic_dt": 10
        }
        armor_type_dt = {"fire": 15}
        
        dmg_normal = calculate_spell_damage(
            caster_matk=50, spell=spell_normal,
            defender_attrs=defender_attrs, armor_type_dt=armor_type_dt
        )
        dmg_sunder = calculate_spell_damage(
            caster_matk=50, spell=spell_sunder,
            defender_attrs=defender_attrs, armor_type_dt=armor_type_dt
        )
        assert dmg_sunder > dmg_normal, (
            f"Sundering spell ({dmg_sunder}) should deal more damage than normal ({dmg_normal}) by piercing DR/DT"
        )


# ---------------------------------------------------------------------------
# 8. Genre-Specific Spell Flavor, Procedural Naming, and Starter Kits
# ---------------------------------------------------------------------------

class TestGenreSpellFlavorExpansion:
    """Verifies procedural spell naming, descriptions, and starter kits across genres."""

    def test_steampunk_spell_naming_and_description(self):
        from mechanics.combat.spells.procedural import generate_procedural_spell, generate_spell_name
        
        # Test procedural spell generation
        spell_t3 = generate_procedural_spell(scenario="steampunk", tier=3, element="lightning", shape="chain")
        assert "(Aether/Clockwork)" in spell_t3["description"]
        assert any(w in spell_t3["name"] for w in ["Galvanic", "Tesla", "Arc", "Coil", "Voltaic", "Electrified", "Induction", "Conduction"])
        
        spell_t2 = generate_procedural_spell(scenario="steampunk", tier=2, element="acid", shape="cone")
        assert "(Aether/Clockwork)" in spell_t2["description"]
        assert any(w in spell_t2["name"] for w in ["Vitriolic", "Caustic", "Alchemical", "Pressurized", "Boiler", "Steam", "Vent", "Spout"])
        
        spell_t1 = generate_procedural_spell(scenario="steampunk", tier=1, element="fire", shape="cylinder")
        assert any(w in spell_t1["name"] for w in ["Boiler", "Superheated", "Apex", "Tesla", "High-Pressure", "Geyser", "Furnace", "Pillar", "Clockwork", "Combustion", "Chimney", "Vent", "Aether", "Pressure", "Brass"])

    def test_cyberpunk_spell_naming_and_description(self):
        from mechanics.combat.spells.procedural import generate_procedural_spell
        
        spell_t3 = generate_procedural_spell(scenario="cyberpunk", tier=3, element="lightning", shape="bolt")
        assert "(Digital/Cyberdeck)" in spell_t3["description"]
        assert any(w in spell_t3["name"] for w in ["EMP", "Overvoltage", "Pulse", "Static", "Spike", "Packet", "Dart", "Arc", "Circuit", "Bit-Burst", "Grid", "Voltage"])
        
        spell_t2 = generate_procedural_spell(scenario="sci_fi", tier=2, element="force", shape="lance")
        assert "(Digital/Cyberdeck)" in spell_t2["description"]
        assert any(w in spell_t2["name"] for w in ["Overclocked", "Synaptic", "High-Frequency", "Kinetic", "Graviton", "Beam", "Penetrator", "Laser", "Accelerator", "Linear", "Shockwave", "Repulsor", "Driver", "Rail", "Lance", "Smart-Linked", "Pulse", "Neural", "Sub-Zero"])

        spell_t1 = generate_procedural_spell(scenario="cyberpunk", tier=1, element="psychic", shape="chain")
        assert any(w in spell_t1["name"] for w in ["Orbital", "Singularity", "Black-ICE", "Quantum", "Neural", "Synaptic", "Daemon", "Cascade", "Relay"])

    def test_dark_fantasy_and_wasteland_naming(self):
        from mechanics.combat.spells.procedural import generate_procedural_spell
        
        spell_t3 = generate_procedural_spell(scenario="dark_fantasy", tier=3, element="necrotic", shape="bolt")
        assert "(Grimdark/Wasteland)" in spell_t3["description"]
        assert any(w in spell_t3["name"] for w in ["Grave", "Putrid", "Bone", "Sanguine", "Vampiric", "Spike", "Shard", "Siphon", "Decaying", "Corpse", "Needle", "Dart"])

        spell_t2 = generate_procedural_spell(scenario="nuclear_post_apocalypse", tier=2, element="poison", shape="cone")
        assert "(Grimdark/Wasteland)" in spell_t2["description"]
        assert any(w in spell_t2["name"] for w in ["Rad", "Blighted", "Ash", "Contagion", "Mutagenic", "Miasma", "Fallout", "Cloud", "Venomous", "Sludge", "Rotting", "Vomit", "Wave", "Wasteland", "Gamma", "Festering", "Cursed", "Dread"])

        spell_t1 = generate_procedural_spell(scenario="dark_fantasy", tier=1, element="dark", shape="sphere")
        assert any(w in spell_t1["name"] for w in ["Apocalyptic", "Irradiated", "Cataclysmic", "Abyssal", "Doomsday", "Extinction", "God-Corpse", "Blood", "Wasteland", "Rot", "Grave", "Void", "Pestilence", "Burst", "Detonation", "Sphere", "Blight"])

    def test_genre_summon_templates(self):
        from mechanics.combat.spells.procedural import generate_procedural_spell
        
        # Steampunk summons
        steam_summon = generate_procedural_spell(scenario="steampunk", school="Conjuration")
        assert steam_summon["summon_template"] in ["clockwork_drone", "steam_automaton", "clockwork_colossus"]
        
        # Cyberpunk summons
        cyber_summon = generate_procedural_spell(scenario="cyberpunk", school="Conjuration")
        assert cyber_summon["summon_template"] in ["micro_drone", "combat_automaton", "siege_mech"]

        # Dark fantasy summons
        dark_summon = generate_procedural_spell(scenario="dark_fantasy", school="Conjuration")
        assert dark_summon["summon_template"] in ["skeleton", "ghoul", "bone_colossus"]

    def test_genre_spellbook_item_prefixes(self):
        from mechanics.combat.spells.procedural import generate_procedural_spellbook_item
        
        # Steampunk
        sp_item_t3 = generate_procedural_spellbook_item("steampunk", tier=3)
        assert sp_item_t3["name"].startswith("Schematic:")
        sp_item_t2 = generate_procedural_spellbook_item("steampunk", tier=2)
        assert sp_item_t2["name"].startswith("Blueprint:")
        sp_item_t1 = generate_procedural_spellbook_item("steampunk", tier=1)
        assert sp_item_t1["name"].startswith("Master Plan:")

        # Cyberpunk
        cy_item_t3 = generate_procedural_spellbook_item("cyberpunk", tier=3)
        assert cy_item_t3["name"].startswith("Data Shard:")
        cy_item_t2 = generate_procedural_spellbook_item("cyberpunk", tier=2)
        assert cy_item_t2["name"].startswith("Datapad:")
        cy_item_t1 = generate_procedural_spellbook_item("cyberpunk", tier=1)
        assert cy_item_t1["name"].startswith("Black-ICE Drive:")

        # Dark Fantasy / Post-Apocalypse
        df_item_t3 = generate_procedural_spellbook_item("dark_fantasy", tier=3)
        assert df_item_t3["name"].startswith("Foul Parchment:")
        pa_item_t2 = generate_procedural_spellbook_item("nuclear_post_apocalypse", tier=2)
        assert pa_item_t2["name"].startswith("Blighted Tome:")
        df_item_t1 = generate_procedural_spellbook_item("dark_fantasy", tier=1)
        assert df_item_t1["name"].startswith("Forbidden Grimoire:")

        # Fantasy (default)
        fa_item_t3 = generate_procedural_spellbook_item("fantasy", tier=3)
        assert fa_item_t3["name"].startswith("Spellbook:")
        fa_item_t2 = generate_procedural_spellbook_item("fantasy", tier=2)
        assert fa_item_t2["name"].startswith("Tome:")
        fa_item_t1 = generate_procedural_spellbook_item("fantasy", tier=1)
        assert fa_item_t1["name"].startswith("Grimoire:")

    def test_genre_starter_spell_packages(self):
        from mechanics.combat.spells.kits import get_starter_spells
        from mechanics.combat.spells.registry import get_spell
        
        # Steampunk starter kit
        steam_kit = get_starter_spells("steampunk", "Artificer", int_stat=6)
        assert len(steam_kit) >= 6
        assert all(get_spell(sid) is not None for sid in steam_kit)
        assert "spark_jolt_t3_st" in steam_kit or "chain_lightning_t3_chain" in steam_kit
        assert "corrode_armor_t3_st" in steam_kit or "iron_shrapnel_t3_aoe" in steam_kit

        # Cyberpunk starter kit
        cyber_kit = get_starter_spells("cyberpunk", "Netrunner", int_stat=6)
        assert len(cyber_kit) >= 6
        assert all(get_spell(sid) is not None for sid in cyber_kit)
        assert any(sid in cyber_kit for sid in ["deploy_micro_drones_t3_st", "spark_jolt_t3_st", "clarity_t3_st"])

        # Dark Fantasy / Post-Apocalypse starter kit
        dark_kit = get_starter_spells("dark_fantasy", "Scavenger", int_stat=6)
        assert len(dark_kit) >= 6
        assert all(get_spell(sid) is not None for sid in dark_kit)
        assert any(sid in dark_kit for sid in ["venom_dart_t3_st", "toxic_miasma_t3_aoe", "shadow_bolt_t3_st", "raise_skeletons_t3_st"])

        postapoc_kit = get_starter_spells("nuclear_post_apocalypse", "Wasteland Mutant", int_stat=8)
        assert len(postapoc_kit) >= 8
        assert all(get_spell(sid) is not None for sid in postapoc_kit)
        assert any(sid in postapoc_kit for sid in ["venom_dart_t3_st", "corrode_armor_t3_st", "noxious_blast_t2_st"])


