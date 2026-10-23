"""
Deterministic Stealth Formulas.

Computes opposed stealth ratings (Player Agility/Luck vs Sentry Perception),
armor noise penalties, companion interference, environmental lighting concealment,
and sensory separation for optical invisibility.
"""
from typing import Dict, Any, List, Optional, Tuple
import random

import skill_check
from skill_check import CheckResult
import character_data as cd
from mechanics.stealth.alert_tracker import ALERT_UNAWARE, ALERT_SUSPICIOUS, ALERT_SEARCHING, ALERT_DETECTED


def calculate_armor_noise(equipped_items: Optional[List[Dict[str, Any]]] = None) -> Tuple[int, int]:
    """
    Computes acoustic noise penalty and stealth bonus from equipped items.
    Returns:
        (noise_penalty, stealth_bonus)
        - noise_penalty is a positive number subtracting from Stealth Rating.
        - stealth_bonus is a positive number adding to Stealth Rating.
    """
    if not equipped_items:
        return 0, 0

    noise_penalty = 0
    stealth_bonus = 0

    for item in equipped_items:
        if not isinstance(item, dict):
            continue

        slot = str(item.get("slot") or "").lower()
        item_type = str(item.get("item_type") or "").lower()
        name = str(item.get("name") or "").lower()
        tags = item.get("tags") or {}

        # Flatten tags
        flat_tags = []
        if isinstance(tags, dict):
            for v in tags.values():
                if isinstance(v, list):
                    flat_tags.extend([str(x).lower() for x in v])
                elif isinstance(v, str):
                    flat_tags.append(v.lower())
        elif isinstance(tags, list):
            flat_tags = [str(x).lower() for x in tags]

        # Check armor class & weight
        is_heavy = (
            "heavy" in flat_tags
            or "plate" in flat_tags
            or "power_armor" in flat_tags
            or any(kw in name for kw in ("plate", "greathelm", "sabatons", "tower shield", "iron boots", "greaves"))
        )
        is_medium = (
            "medium" in flat_tags
            or any(kw in name for kw in ("chainmail", "scale", "brigandine", "boiled leather", "studded"))
        )
        is_stealthy = (
            any(t in flat_tags for t in ("stealth", "silent_step", "muffled", "shadow", "camouflage", "camo"))
            or any(kw in name for kw in ("shadow silk", "muffled", "silent", "stalker", "camo", "wraith-hide", "rogue"))
        )

        if is_heavy and (slot in ("armor", "top", "bottom", "shield", "shoes", "head") or "armor" in item_type):
            noise_penalty += 25
        elif is_medium and (slot in ("armor", "top", "bottom") or "armor" in item_type):
            noise_penalty += 10

        if is_stealthy:
            stealth_bonus += 15

    # Cap noise penalty and bonus to prevent runaway extreme outliers
    noise_penalty = min(50, noise_penalty)
    stealth_bonus = min(35, stealth_bonus)

    return noise_penalty, stealth_bonus


def calculate_companion_noise_penalty(party: Optional[List[Any]] = None) -> int:
    """
    Computes party noise interference when moving in a group.
    Player acts as lead scout; noisy companions add a flat -10 to -15 penalty.
    """
    if not party or len(party) <= 1:
        return 0

    has_heavy_companion = False
    for comp in party[1:]:
        comp_char = comp[0] if isinstance(comp, (list, tuple)) and comp else comp
        if not isinstance(comp_char, dict):
            continue
        
        # Check companion's gear or tags
        c_inv = comp[1] if isinstance(comp, (list, tuple)) and len(comp) > 1 and isinstance(comp[1], list) else []
        c_penalty, _ = calculate_armor_noise(c_inv)
        if c_penalty >= 20:
            has_heavy_companion = True
            break
        
        # Check companion's archetype
        c_desc = str(comp_char.get("description", "")).lower()
        c_class = str(comp_char.get("class", "")).lower()
        if any(kw in c_desc or kw in c_class for kw in ("paladin", "knight", "tank", "heavy", "golem", "iron")):
            has_heavy_companion = True
            break

    return 15 if has_heavy_companion else 5


def calculate_lighting_modifier(current_minute: Optional[int] = None, environment: str = "") -> int:
    """
    Calculates concealment from ambient light, shadows, and time-of-day.
    Positive value adds to Stealth Rating (makes hiding easier).
    Negative value subtracts from Stealth Rating (bright visibility).
    """
    env_lower = str(environment or "").lower()
    if any(k in env_lower for k in ("pitch black", "deep darkness", "dark cave", "fog", "heavy fog", "smoke")):
        return 25

    if current_minute is None:
        return 0

    try:
        from mechanics.system.time_engine import get_time_of_day_phase
        phase_tuple = get_time_of_day_phase(current_minute)
        phase_name = phase_tuple[0] if isinstance(phase_tuple, (tuple, list)) and phase_tuple else ""
    except Exception:
        phase_name = "Afternoon"

    # Concealment table by time phase
    if phase_name in ("Midnight", "Night"):
        return 20
    if phase_name in ("Evening", "Early Morning"):
        return 10
    if phase_name in ("Morning", "Afternoon"):
        return -15
    return 0


def calculate_action_noise(action_type: str = "creep", custom_text: str = "") -> int:
    """
    Returns acoustic sound footprint for the action being attempted.
    Higher noise alerts sentries more rapidly on failure.
    """
    act = (str(action_type or "") + " " + str(custom_text or "")).lower()
    if any(k in act for k in ("gunshot", "firearm", "explode", "bomb", "shout", "roar", "scream")):
        return 50
    if any(k in act for k in ("magic", "cast", "fireball", "thunder", "smash", "breach")):
        return 25
    if any(k in act for k in ("sprint", "run", "kick", "takedown", "melee", "attack", "strike")):
        return 10
    if any(k in act for k in ("distract", "throw stone", "stone", "pebble")):
        return 0  # Sound thrown away from player
    return 0


def calculate_opposed_stealth_odds(
    actor_stats: Dict[str, Any],
    target_per: int = 3,
    equipped_items: Optional[List[Dict[str, Any]]] = None,
    current_minute: Optional[int] = None,
    party: Optional[List[Any]] = None,
    alert_stage: str = ALERT_UNAWARE,
    is_invisible: bool = False,
    environment: str = "",
    action_noise: int = 0
) -> Dict[str, Any]:
    """
    Computes deterministic success chance for an opposed stealth contest.
    
    Returns:
        dict with odds, stealth_rating, perception_rating, dc_equivalent, modifiers
    """
    agi = int(actor_stats.get("AGI", actor_stats.get("agi", cd.BASE_STAT_VALUE)) or cd.BASE_STAT_VALUE)
    luk = int(actor_stats.get("LUK", actor_stats.get("luk", cd.BASE_STAT_VALUE)) or cd.BASE_STAT_VALUE)
    sentry_per = max(1, int(target_per or 3))

    armor_noise, gear_stealth_bonus = calculate_armor_noise(equipped_items)
    companion_penalty = calculate_companion_noise_penalty(party)
    lighting_mod = calculate_lighting_modifier(current_minute, environment=environment)

    # Invisibility / Optical Camo grants 100% visual concealment:
    # Negates daylight visibility penalties and adds massive optical cover (+40),
    # but armor clank and action noise still apply!
    if is_invisible:
        optical_concealment = max(40, lighting_mod + 40)
    else:
        optical_concealment = lighting_mod

    # Alert stage vigilance modifier
    alert_vigilance = 0
    if alert_stage == ALERT_SUSPICIOUS:
        alert_vigilance = 15  # Guard is actively looking
    elif alert_stage == ALERT_SEARCHING:
        alert_vigilance = 30  # Sweeping with torches / lanterns
    elif alert_stage == ALERT_DETECTED:
        alert_vigilance = 50

    # Net ratings
    stealth_rating = (agi * 10) + (luk * 2) + gear_stealth_bonus - armor_noise + optical_concealment - companion_penalty - action_noise
    perception_rating = (sentry_per * 10) + alert_vigilance

    diff = stealth_rating - perception_rating
    # Center at 50% for equal ratings; scale 2.5% per point of rating difference
    raw_chance = 50 + int(round(diff * 2.5))
    success_pct = max(5, min(95, raw_chance))

    # Virtual DC equivalent (for compatibility with standard skill_check reporting)
    virtual_dc = max(4, int(round(10 - (diff / 10))))

    return {
        "success_chance": success_pct,
        "virtual_dc": virtual_dc,
        "stealth_rating": stealth_rating,
        "perception_rating": perception_rating,
        "armor_noise": armor_noise,
        "gear_stealth_bonus": gear_stealth_bonus,
        "companion_penalty": companion_penalty,
        "lighting_mod": lighting_mod,
        "is_invisible": is_invisible,
        "optical_concealment": optical_concealment,
        "alert_vigilance": alert_vigilance,
        "diff": diff
    }


def resolve_opposed_stealth_check(
    actor_stats: Dict[str, Any],
    target_per: int = 3,
    equipped_items: Optional[List[Dict[str, Any]]] = None,
    current_minute: Optional[int] = None,
    party: Optional[List[Any]] = None,
    alert_stage: str = ALERT_UNAWARE,
    is_invisible: bool = False,
    environment: str = "",
    action_noise: int = 0,
    luck: int = 3,
    check_mode: str = "off"
) -> Tuple[CheckResult, Dict[str, Any]]:
    """
    Executes an opposed stealth roll and returns the canonical (CheckResult, odds_meta).
    """
    odds = calculate_opposed_stealth_odds(
        actor_stats=actor_stats,
        target_per=target_per,
        equipped_items=equipped_items,
        current_minute=current_minute,
        party=party,
        alert_stage=alert_stage,
        is_invisible=is_invisible,
        environment=environment,
        action_noise=action_noise
    )

    chance = odds["success_chance"]
    dc = odds["virtual_dc"]

    if check_mode == "always_success":
        result = CheckResult(chance=100, roll=50.0, tier="success", tier_label="Success", succeeded=True, requirement=dc)
        return result, odds
    if check_mode == "always_fail":
        result = CheckResult(chance=0, roll=50.0, tier="fail", tier_label="Failure", succeeded=False, requirement=dc)
        return result, odds
    if check_mode == "always_crit_success":
        result = CheckResult(chance=100, roll=99.0, tier="crit_success", tier_label="Critical Success", succeeded=True, requirement=dc)
        return result, odds
    if check_mode == "always_crit_fail":
        result = CheckResult(chance=0, roll=1.0, tier="crit_fail", tier_label="Critical Failure", succeeded=False, requirement=dc)
        return result, odds

    crit_success_pct, crit_fail_pct = cd.crit_chances(luck)

    if chance >= 90:
        crit_fail_pct = 0.0
    if chance == 100:
        crit_success_pct = min(50.0, crit_success_pct * 2.0)
    if chance <= 20:
        crit_success_pct = 0.0
    if chance <= 5:
        crit_fail_pct = min(50.0, crit_fail_pct * 2.0)

    roll = random.uniform(0, 100)

    if roll < crit_fail_pct:
        result = CheckResult(chance=chance, roll=roll, tier="crit_fail", tier_label="Critical Failure", succeeded=False, requirement=dc)
        return result, odds
    if roll > 100 - crit_success_pct:
        result = CheckResult(chance=chance, roll=roll, tier="crit_success", tier_label="Critical Success", succeeded=True, requirement=dc)
        return result, odds

    band = max(0.001, 100 - crit_fail_pct - crit_success_pct)
    rescaled = (roll - crit_fail_pct) / band * 100

    if rescaled <= chance:
        result = CheckResult(chance=chance, roll=roll, tier="success", tier_label="Success", succeeded=True, requirement=dc)
    else:
        result = CheckResult(chance=chance, roll=roll, tier="fail", tier_label="Failure", succeeded=False, requirement=dc)

    return result, odds
