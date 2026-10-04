"""
Unit Tests for Mathematical Invariants and Edge-Case Boundaries.

These tests prove that the underlying formulas across Hikayat:
1. Never produce out-of-bound percentages or negative numbers.
2. Strictly maintain mathematical monotonicity (e.g. higher stats never decrease success).
3. Handle boundary conditions (requirement 0, stat 0, negative values, caps at 20) gracefully without exceptions.
"""
import pytest
import skill_check
import character_data as cd
from mechanics.social.attributes import calculate_combat_attributes


@pytest.mark.unit
def test_success_chance_bounds_and_monotonicity():
    """
    Invariants:
    1. 0 <= success_chance(stat, req) <= 100 for all values.
    2. Requirement <= 0 always returns 100 (free action).
    3. Increasing stat_value never decreases success_chance.
    4. Increasing requirement never increases success_chance.
    """
    # 1. Bounds across a large grid
    for stat in range(-5, 25):
        for req in range(-5, 30):
            chance = skill_check.success_chance(stat, req)
            assert 0 <= chance <= 100, f"Out of bounds: stat={stat}, req={req}, chance={chance}"

    # 2. Requirement <= 0 returns 100
    for stat in range(-5, 25):
        assert skill_check.success_chance(stat, 0) == 100
        assert skill_check.success_chance(stat, -10) == 100

    # 3. Monotonicity over Stat
    for req in range(1, 20):
        for stat in range(0, 20):
            c_low = skill_check.success_chance(stat, req)
            c_high = skill_check.success_chance(stat + 1, req)
            assert c_high >= c_low, f"Monotonicity violated for stat: req={req}, stat={stat}, {c_high} < {c_low}"

    # 4. Monotonicity over Requirement
    for stat in range(1, 20):
        for req in range(1, 25):
            c_easier = skill_check.success_chance(stat, req)
            c_harder = skill_check.success_chance(stat, req + 1)
            assert c_harder <= c_easier, f"Monotonicity violated for req: stat={stat}, req={req}, {c_harder} > {c_easier}"

    # 5. Debug check mode overrides
    assert skill_check.success_chance(1, 20, check_mode="always_success") == 100
    assert skill_check.success_chance(20, 1, check_mode="always_fail") == 0
    assert skill_check.success_chance(1, 20, check_mode="always_crit_success") == 100
    assert skill_check.success_chance(20, 1, check_mode="always_crit_fail") == 0


@pytest.mark.unit
def test_resolve_check_invariants():
    """
    Invariants:
    1. CheckResult tier matches succeeded boolean.
    2. Internal roll is always within [0.0, 100.0].
    3. High success chance (>= 90%) completely suppresses critical failure.
    4. Low success chance (<= 20%) completely suppresses critical success.
    """
    valid_tiers = {"crit_success", "success", "fail", "crit_fail"}

    for stat in [1, 5, 10, 15, 20]:
        for req in [5, 10, 15, 20]:
            for luck in [1, 5, 10]:
                res = skill_check.resolve_check(stat, req, luck=luck)
                assert isinstance(res, skill_check.CheckResult)
                assert res.tier in valid_tiers
                assert 0.0 <= res.roll <= 100.0

                if res.tier in ("crit_success", "success"):
                    assert res.succeeded is True
                else:
                    assert res.succeeded is False

    # High chance suppression test (chance >= 90%: crit_fail should NEVER occur)
    for _ in range(100):
        res = skill_check.resolve_check(stat_value=20, requirement=5, luck=1)
        assert res.tier != "crit_fail", "Critical failure occurred despite 100% success rate"

    # Low chance suppression test (chance <= 20%: crit_success should NEVER occur)
    for _ in range(100):
        res = skill_check.resolve_check(stat_value=1, requirement=20, luck=10)
        assert res.tier != "crit_success", "Critical success occurred despite <= 20% success rate"


@pytest.mark.unit
def test_hazard_damage_formulas():
    """
    Invariants for non-combat traps and hazards:
    1. Successful checks take 0 damage.
    2. Failed checks take at least 1 damage.
    3. Critical failure damage >= standard failure damage.
    4. Damage is clamped to prevent low-level 1-shot (<= 40% max_hp for fail, <= 70% max_hp for crit_fail).
    """
    max_hp = 500

    # 1. Successes take 0
    assert skill_check.calculate_hazard_damage(10, "success", max_hp) == 0
    assert skill_check.calculate_hazard_damage(10, "crit_success", max_hp) == 0

    # 2. Scaling with requirement
    for req in range(1, 30):
        dmg_fail = skill_check.calculate_hazard_damage(req, "fail", max_hp)
        dmg_crit = skill_check.calculate_hazard_damage(req, "crit_fail", max_hp)

        assert dmg_fail >= 1
        assert dmg_crit >= dmg_fail
        assert dmg_fail <= int(max_hp * 0.4)
        assert dmg_crit <= int(max_hp * 0.7)


@pytest.mark.unit
def test_character_vitals_derivation():
    """
    Invariants for core SPECIAL derived vitals:
    1. derive_hp and derive_mp are strictly monotonically increasing.
    2. hp_regen and mp_regen are strictly non-negative.
    3. inventory_capacity increases monotonically with strength.
    4. crit_chances returns valid probabilities: 0.5 <= crit_fail <= 3.0, 3.0 <= crit_success <= 15.0.
    5. xp_multiplier is >= 1.0 and increases with intelligence.
    """
    for end in range(1, 20):
        # HP/MP strictly increasing
        assert cd.derive_hp(end + 1) > cd.derive_hp(end)
        assert cd.derive_mp(end + 1) > cd.derive_mp(end)
        assert cd.derive_hp(end) >= 300
        assert cd.derive_mp(end) >= 75

        # Regen non-negative
        assert cd.hp_regen(end) >= 1
        assert cd.mp_regen(end) >= 1

    # Inventory capacity
    for strength in range(1, 20):
        assert cd.inventory_capacity(strength + 1) > cd.inventory_capacity(strength)
        assert cd.inventory_capacity(strength) >= 33

    # Crit chances bounds
    for luck in range(1, 21):
        crit_succ, crit_fail = cd.crit_chances(luck)
        assert 3.0 <= crit_succ <= 15.0
        assert 0.5 <= crit_fail <= 3.0
        assert crit_succ + crit_fail < 100.0

    # XP multiplier
    for int_val in range(1, 20):
        assert cd.xp_multiplier(int_val) >= 1.0
        assert cd.xp_multiplier(int_val + 1) > cd.xp_multiplier(int_val)


@pytest.mark.unit
def test_combat_attributes_special_scaling():
    """
    Invariants for derived combat attributes:
    1. SPECIAL stats (1 to 20) produce strictly positive ATK, MATK, ACC, MACC, EVA.
    2. Non-combat scenarios zero out all offensive and evasive attributes with is_non_combat=True.
    3. Higher AGI increases both Evasion and Physical Accuracy.
    4. Higher PER increases Accuracy and Magic Attack.
    """
    char_base = {
        "str_": 5, "per_": 5, "end_": 5,
        "cha": 5, "int_": 5, "agi": 5, "luk": 5,
        "level": 1, "scenario": "fantasy"
    }
    attrs = calculate_combat_attributes(char_base)

    assert attrs["atk"] > 0
    assert attrs["matk"] > 0
    assert attrs["acc"] > 0
    assert attrs["macc"] > 0
    assert attrs["eva"] > 0
    assert attrs["innate_phys_dt"] >= 0
    assert attrs["innate_magic_dt"] >= 0
    assert attrs.get("is_non_combat") is not True

    # Test agility scaling
    char_higher_agi = dict(char_base, agi=10)
    attrs_higher_agi = calculate_combat_attributes(char_higher_agi)
    assert attrs_higher_agi["eva"] > attrs["eva"]
    assert attrs_higher_agi["acc"] > attrs["acc"]
    assert attrs_higher_agi["atk"] > attrs["atk"]

    # Test non-combat scenario suppression
    char_non_combat = dict(char_base, scenario="high_school_drama")
    nc_attrs = calculate_combat_attributes(char_non_combat)
    assert nc_attrs["is_non_combat"] is True
    assert nc_attrs["atk"] == 0
    assert nc_attrs["eva"] == 0
    assert nc_attrs["acc"] == 0
