"""
Skill Check Engine (no dice).

Every action tests a Core Attribute against a "requirement" number set by
the AI for that scene (roughly on the same scale as the attributes
themselves). Your success chance is a function of how your stat compares
to the requirement:

    success_chance = clamp(stat / requirement * 100, 0, 100)

On top of that, Luck adds a flat critical-success / critical-failure sliver
that applies regardless of the base skill roll -- see
character_data.crit_chances().
"""
import random
from dataclasses import dataclass

from character_data import crit_chances

MIN_CHANCE = 0
MAX_CHANCE = 100
HIGH_CRIT_MULTIPLIER = 2.0


def success_chance(stat_value: int, requirement: int, check_mode: str = "off") -> int:
    """Return an integer percent chance of success, clamped to [0, 100]."""
    if check_mode in ("always_success", "always_crit_success"):
        return MAX_CHANCE
    if check_mode in ("always_fail", "always_crit_fail"):
        return MIN_CHANCE
    if requirement <= 0:
        return MAX_CHANCE
    pct = (stat_value / requirement) * 100
    return int(max(MIN_CHANCE, min(MAX_CHANCE, round(pct))))


@dataclass
class CheckResult:
    chance: int          # the success % that was used
    roll: float          # internal roll, 0-100 (for debugging/logging only)
    tier: str            # crit_fail | fail | success | crit_success
    tier_label: str
    succeeded: bool
    requirement: int = 10 # the DC that was checked against


def calculate_hazard_damage(requirement: int, tier: str, max_hp: int) -> int:
    """
    Deterministically calculate non-combat hazard or trap damage based on the check requirement (DC)
    and the failure tier.
    """
    if tier not in ("fail", "crit_fail"):
        return 0
    
    # Base damage driven by requirement
    base_dmg = requirement * 2
    if tier == "crit_fail":
        base_dmg = int(requirement * 3.5)
        
    # Cap at a reasonable % of max hp so a single trap doesn't instakill unless very low level
    cap = max_hp * 0.4 if tier == "fail" else max_hp * 0.7
    
    # Ensure at least 1 damage
    return max(1, int(min(base_dmg, cap)))


def resolve_check(stat_value: int, requirement: int = None, luck: int = 3, check_mode: str = "off", **kwargs) -> CheckResult:
    if requirement is None:
        requirement = kwargs.get("dc", 10)
    requirement = int(requirement)
    if check_mode == "always_success":
        return CheckResult(MAX_CHANCE, 50.0, "success", "Success", True, requirement=requirement)
    if check_mode == "always_fail":
        return CheckResult(MIN_CHANCE, 50.0, "fail", "Failure", False, requirement=requirement)
    if check_mode == "always_crit_success":
        return CheckResult(MAX_CHANCE, 99.0, "crit_success", "Critical Success", True, requirement=requirement)
    if check_mode == "always_crit_fail":
        return CheckResult(MIN_CHANCE, 1.0, "crit_fail", "Critical Failure", False, requirement=requirement)

    chance = success_chance(stat_value, requirement)
    crit_success_pct, crit_fail_pct = crit_chances(luck)

    # Threshold rules for critical failure / success chances:
    # 1. Success rate >= 90%: Impossible to get critical failure.
    if chance >= 90:
        crit_fail_pct = 0.0
    # 2. Success rate == 100%: High chance for critical success.
    if chance == 100:
        crit_success_pct = min(50.0, crit_success_pct * HIGH_CRIT_MULTIPLIER)

    # 3. Success rate <= 20%: Impossible to get critical success.
    if chance <= 20:
        crit_success_pct = 0.0
    # 4. Success rate <= 5%: High chance for critical failure.
    if chance <= 5:
        crit_fail_pct = min(50.0, crit_fail_pct * HIGH_CRIT_MULTIPLIER)

    roll = random.uniform(0, 100)

    if roll < crit_fail_pct:
        return CheckResult(chance, roll, "crit_fail", "Critical Failure", False, requirement=requirement)
    if roll > 100 - crit_success_pct:
        return CheckResult(chance, roll, "crit_success", "Critical Success", True, requirement=requirement)

    # Rescale the remaining middle band back to 0-100 so the flat crit
    # slivers don't skew the effective success rate away from `chance`.
    band = 100 - crit_fail_pct - crit_success_pct
    band = max(0.001, band)
    rescaled = (roll - crit_fail_pct) / band * 100

    if rescaled <= chance:
        return CheckResult(chance, roll, "success", "Success", True, requirement=requirement)
    return CheckResult(chance, roll, "fail", "Failure", False, requirement=requirement)
