"""mechanics/combat/status_effects.py

First-class status effect lifecycle engine for Hikayat Phase 3 Combat Evolution.
Handles typed StatusEffectInstance normalization, intensity stacking on DoTs,
non-stacking hard crowd-control guardrails, defensive gear immunities, and turn timer ticks.
"""
from __future__ import annotations

import json
import re
from typing import Any, Dict, List, Optional, Set, Tuple, Union

from .types import StatusEffectInstance

# Set of hard crowd-control conditions that must never stack intensity (duration refresh only)
HARD_CC_NAMES: Set[str] = {
    "stunned", "stun", "prone", "staggered", "incapacitated",
    "paralyzed", "frozen", "asleep", "sleep", "unconscious"
}

# Base potencies and classifications for damage-over-time conditions
DOT_CONFIG: Dict[str, Tuple[float, float]] = {
    # tag: (base_potency, default_duration)
    "poison": (10.0, 3.0),
    "venom": (10.0, 3.0),
    "burn": (8.0, 3.0),
    "ignite": (8.0, 3.0),
    "bleed": (6.0, 3.0),
    "acid": (7.0, 3.0),
    "corrosive": (7.0, 3.0),
}

# Intensity multipliers: +50% per stack above stack 1
INTENSITY_MULTIPLIERS: Dict[int, float] = {
    1: 1.0,
    2: 1.5,
    3: 2.0,
}

# Tag keywords for non-combat / persistent conditions
NON_COMBAT_KEYWORDS: Set[str] = {
    "sensitive", "flustered", "breathless", "exhausted", "recovering",
    "rested", "drunk", "full", "smitten", "heartbroken", "aroused"
}


def normalize_status_effect(
    raw: Union[str, Dict[str, Any], StatusEffectInstance],
    source: str = ""
) -> StatusEffectInstance:
    """Converts a raw string or dictionary into a normalized StatusEffectInstance.

    Args:
        raw: Raw status effect tag (e.g. 'Poisoned [2 turns]') or dictionary.
        source: Entity or spell identifier that inflicted this condition.

    Returns:
        Structured StatusEffectInstance conforming to canonical schema.
    """
    if isinstance(raw, dict):
        raw_name = str(raw.get("name", "")).strip() or "Unknown"
        metadata = dict(raw.get("metadata") or {})
        if "[" in raw_name:
            metadata.setdefault("raw_tag", raw_name)
        clean_dict_name = re.sub(r"\s*\[.*?\]", "", raw_name).strip()
        name = clean_dict_name or raw_name
        category = raw.get("category", "combat")
        duration_type = raw.get("duration_type", "turns")
        rem_raw = raw.get("remaining_duration")
        if rem_raw is None:
            rem_raw = raw.get("duration", 2)
        remaining = int(rem_raw) if rem_raw is not None else 2

        max_dur_raw = raw.get("max_duration")
        max_duration = int(max_dur_raw) if max_dur_raw is not None else max(1, remaining)

        int_raw = raw.get("intensity_stacks")
        intensity = max(1, min(3, int(int_raw) if int_raw is not None else 1))

        pot_raw = raw.get("potency")
        potency = float(pot_raw) if pot_raw is not None else 0.0

        src = str(raw.get("source") or source or "").strip()

        # Auto-compute potency if not explicitly set for DoTs
        if potency == 0.0:
            name_lower = name.lower()
            for k, (base_p, _) in DOT_CONFIG.items():
                if k in name_lower:
                    potency = base_p
                    break

        return StatusEffectInstance(
            name=name,
            category=category,
            duration_type=duration_type,
            remaining_duration=remaining,
            max_duration=max_duration,
            duration=remaining,
            intensity_stacks=intensity,
            potency=potency,
            source=src,
            metadata=metadata,
        )

    # Legacy string normalization path
    raw_str = str(raw).strip()
    name_str = raw_str
    remaining_duration = 2
    max_duration = 2
    duration_type = "turns"
    category = "combat"

    eff_lower = raw_str.lower()
    turn_match = None

    # Minute-based tags (e.g. "Refractory Recovery [15 min]")
    min_match = re.search(r"\[(\d+)\s*(?:min|m)\]", raw_str, re.IGNORECASE)
    if min_match:
        remaining_duration = int(min_match.group(1))
        max_duration = remaining_duration
        duration_type = "minutes"
        category = "social" if "refractory" not in eff_lower else "intimate"
        name_str = raw_str[:min_match.start()].strip()
    else:
        # Turn-based tags (e.g. "Poisoned [3 turns]")
        turn_match = re.search(r"\[(\d+)\s*turns?\]", raw_str, re.IGNORECASE)
        if turn_match:
            remaining_duration = int(turn_match.group(1))
            max_duration = remaining_duration
            duration_type = "turns"
            name_str = raw_str[:turn_match.start()].strip()
        elif any(k in eff_lower for k in NON_COMBAT_KEYWORDS):
            category = "social" if "aroused" not in eff_lower else "intimate"
            duration_type = "permanent"
            remaining_duration = -1
            max_duration = -1

        # Strip any internal modifier brackets (e.g. [+6 DT, +30% Block] or [-10% ACC]) from name_str
        clean_name = re.sub(r"\s*\[.*?\]", "", name_str).strip()
        if clean_name:
            name_str = clean_name

    # Base potency for recognized DoT types
    potency = 0.0
    for k, (base_p, default_dur) in DOT_CONFIG.items():
        if k in eff_lower:
            potency = base_p
            if duration_type == "turns" and not turn_match:
                remaining_duration = int(default_dur)
                max_duration = int(default_dur)
            break

    # Stagger metadata & bracket modifier preservation for attribute parsing
    metadata: Dict[str, Any] = {}
    if "[" in raw_str:
        metadata["raw_tag"] = raw_str
    if "stagger" in eff_lower:
        metadata["stagger_vulnerable"] = True
        metadata["damage_taken_mult"] = 1.25

    return StatusEffectInstance(
        name=name_str or raw_str,
        category=category,  # type: ignore[arg-type]
        duration_type=duration_type,  # type: ignore[arg-type]
        remaining_duration=remaining_duration,
        max_duration=max_duration,
        duration=remaining_duration,
        intensity_stacks=1,
        potency=potency,
        source=source,
        metadata=metadata,
    )


def normalize_status_list(effects: Any, source: str = "") -> List[StatusEffectInstance]:
    """Converts a raw status container (list, JSON str, dict, or mixed) into clean StatusEffectInstance items."""
    if not effects:
        return []
    raw_items: List[Any]
    if isinstance(effects, str):
        s = effects.strip()
        if not s:
            return []
        if s.startswith("["):
            try:
                parsed = json.loads(s)
                raw_items = parsed if isinstance(parsed, list) else [parsed]
            except Exception:
                raw_items = [s]
        else:
            raw_items = [s]
    elif isinstance(effects, dict):
        raw_items = [effects]
    elif isinstance(effects, (list, tuple, set)):
        raw_items = list(effects)
    else:
        return []

    normalized: List[StatusEffectInstance] = []
    for item in raw_items:
        if item is None:
            continue
        if isinstance(item, str) and not item.strip():
            continue
        if isinstance(item, dict) and not str(item.get("name", "")).strip():
            continue
        normalized.append(normalize_status_effect(item, source=source))
    return normalized


def apply_status_effect(
    entity: Dict[str, Any],
    effect: Union[str, Dict[str, Any], StatusEffectInstance],
    source: str = "",
    target_attrs: Optional[Dict[str, Any]] = None,
    combat_log: Optional[List[str]] = None,
) -> bool:
    """Applies a status effect to an entity with immunity checks and stacking rules.

    Stacking rules:
      - DoTs & Stat Debuffs: Refreshes duration to max, increments intensity_stacks (+1, max 3).
      - Hard CC: Refreshes duration to max, keeps intensity_stacks locked at 1.
      - Other effects: Refreshes duration.

    Args:
        entity: The target combatant or character dict.
        effect: String tag or StatusEffectInstance dict.
        source: Attacker or spell source tag.
        target_attrs: Attributes dict containing gear tags / immunity flags.
        combat_log: Optional narrative action log.

    Returns:
        True if successfully applied, False if repelled by immunity.
    """
    if not isinstance(entity, dict):
        return False

    instance = normalize_status_effect(effect, source=source)
    name_lower = instance["name"].lower()

    # Defensive gear immunity checks (Hazmat / Gas Mask against toxic hazards)
    attrs = target_attrs or {}
    target_tags: Set[str] = set(attrs.get("tags", [])) | set(attrs.get("gear_tags", []))
    for existing in entity.get("status_effects", []):
        if isinstance(existing, dict):
            target_tags.update(existing.get("name", "").lower().split())
        elif isinstance(existing, str):
            target_tags.update(existing.lower().split())

    is_toxic = any(k in name_lower for k in ("poison", "toxic", "acid", "corros", "gas", "suffocat", "chemical", "radiation", "fallout"))
    if is_toxic:
        hazmat_active = any(t in target_tags for t in ("hazmat", "gas_mask", "gas_immune", "environmental_isolation", "sealed_environment"))
        if hazmat_active:
            target_name = entity.get("name", "The target")
            if combat_log is not None:
                combat_log.append(f"🛡️ **{target_name}**'s sealed Hazmat gear repelled the toxic hazard (*{instance['name']}*)!")
            return False

    # Ensure status_effects list exists
    effects_list = entity.get("status_effects")
    if not isinstance(effects_list, list):
        effects_list = []
        entity["status_effects"] = effects_list

    # Search for matching existing condition
    for idx, existing in enumerate(effects_list):
        existing_inst = normalize_status_effect(existing)
        if existing_inst["name"].lower() == name_lower:
            # Refresh duration to maximum
            refreshed_duration = max(existing_inst["remaining_duration"], instance["max_duration"])
            existing_inst["remaining_duration"] = refreshed_duration
            existing_inst["duration"] = refreshed_duration
            existing_inst["max_duration"] = max(existing_inst["max_duration"], instance["max_duration"])

            is_hard_cc = any(cc in name_lower for cc in HARD_CC_NAMES)
            if is_hard_cc:
                # CC intensity stacks remain locked at 1
                existing_inst["intensity_stacks"] = 1
            else:
                # DoT / debuff intensity increments up to 3 stacks (+50% per stack)
                cur_stacks = existing_inst.get("intensity_stacks", 1)
                existing_inst["intensity_stacks"] = min(3, cur_stacks + 1)

            # Preserve or update metadata
            if instance.get("metadata"):
                existing_inst.setdefault("metadata", {}).update(instance["metadata"])

            effects_list[idx] = existing_inst
            return True

    # New condition: append normalized instance
    effects_list.append(instance)
    return True


def tick_status_instance_timers(
    entity: Dict[str, Any],
    non_lethal_mode: bool = False,
) -> Dict[str, Any]:
    """Ticks turn timers on active status effects and applies DoT damage.

    Calculates DoT damage based on potency and intensity stacks:
      - 1 stack:  1.0x potency
      - 2 stacks: 1.5x potency
      - 3 stacks: 2.0x potency

    Damage is deducted from temp_hp first, then hp (clamped at 0, or 1 HP when
    non_lethal_mode, sparring, or requires_non_lethal_subdue is active).
    Combat turn timers decrement by 1. Effects reaching 0 turns are expired.
    Non-combat, minute-based, and permanent conditions are preserved.

    Returns:
        The mutated entity dict.
    """
    raw_effects = entity.get("status_effects")
    if not raw_effects:
        return entity

    if isinstance(raw_effects, str):
        try:
            effects = json.loads(raw_effects) if raw_effects.strip().startswith("[") else [raw_effects]
        except Exception:
            effects = [raw_effects]
    else:
        effects = list(raw_effects)

    new_effects: List[Any] = []
    total_dot = 0.0

    for eff in effects:
        inst = normalize_status_effect(eff)
        name_lower = inst["name"].lower()
        eff_lower = eff.lower() if isinstance(eff, str) else name_lower

        # Check for DoT damage accumulation
        if inst["potency"] > 0.0:
            stacks = inst.get("intensity_stacks", 1)
            mult = INTENSITY_MULTIPLIERS.get(stacks, 1.0 + 0.5 * (stacks - 1))
            total_dot += inst["potency"] * mult

        # Check if timer tag already exists on raw string: "Stunned [2 turns]"
        if isinstance(eff, str):
            # 1. Social / Intimate tags that must NOT be managed by combat turn tick:
            # Aroused is managed exclusively by intimate excitement decay and physical state reducer
            if "aroused" in eff_lower:
                new_effects.append(eff)
                continue

            # 2. Minute-based tags (Refractory Recovery [X min], Satisfied [X min], etc.)
            if re.search(r"\[\d+\s*(?:min|m)\]", eff, re.IGNORECASE) or any(k in eff_lower for k in ("refractory", "satisfied")):
                new_effects.append(eff)
                continue

            # 3. Check for existing turn bracket
            match = re.search(r"\s*\[(\d+)\s*turns?\]$", eff, re.IGNORECASE)
            if match:
                turns = int(match.group(1)) - 1
                base = eff[:match.start()].strip()
                if turns > 0:
                    new_effects.append(f"{base} [{turns} turn{'s' if turns != 1 else ''}]")
            else:
                # Non-combat or persistent condition checks: do not attach turn timers to social/exploration traits
                if any(k in eff_lower for k in NON_COMBAT_KEYWORDS):
                    new_effects.append(eff)
                else:
                    # New combat effect without timer - attach default 2-turn timer
                    new_effects.append(f"{eff} [2 turns]")
            continue

        # Dict instance handling
        if inst["name"].lower() == "aroused":
            new_effects.append(inst)
            continue

        # Social / Intimate / Minute tags do not tick down on combat turns
        if inst["category"] in ("social", "intimate") or inst["duration_type"] in ("minutes", "permanent"):
            new_effects.append(inst)
            continue

        # Decrement turn duration for dict instances
        remaining = inst["remaining_duration"] - 1
        if remaining > 0:
            inst["remaining_duration"] = remaining
            inst["duration"] = remaining
            if isinstance(eff, dict):
                eff["remaining_duration"] = remaining
                eff["duration"] = remaining
            new_effects.append(inst)
        # If remaining <= 0: effect has expired, do not append to new_effects

    # Apply aggregated DoT damage
    dmg_int = int(round(total_dot))
    if dmg_int > 0:
        temp = int(entity.get("temp_hp") or 0)
        actual = dmg_int
        if temp > 0:
            if temp >= dmg_int:
                entity["temp_hp"] = temp - dmg_int
                actual = 0
            else:
                actual = dmg_int - temp
                entity["temp_hp"] = 0
        cur_hp = int(entity.get("hp") or 0)
        requires_dot_mercy = bool(
            non_lethal_mode
            or entity.get("sparring")
            or entity.get("is_subdued_ready")
            or entity.get("is_subdued")
            or entity.get("requires_non_lethal_subdue")
        )
        if requires_dot_mercy and cur_hp > 0:
            new_hp = max(1, cur_hp - actual)
            entity["hp"] = new_hp
            if new_hp == 1 and (cur_hp - actual) < 1:
                entity["is_subdued_ready"] = True
        else:
            entity["hp"] = max(0, cur_hp - actual)

    entity["status_effects"] = new_effects
    return entity


def format_status_badge(
    effect: Union[str, Dict[str, Any], StatusEffectInstance],
    include_duration: bool = False,
) -> str:
    """Formats a player-facing status badge string without raw numerical stat leakage."""
    inst = normalize_status_effect(effect)
    clean_name = re.sub(r"\s*\[.*?\]", "", inst["name"]).strip() or inst["name"]
    stacks = inst.get("intensity_stacks", 1)
    stack_suffix = f" x{stacks}" if stacks > 1 else ""
    dur_suffix = ""
    if include_duration and inst.get("duration_type") == "turns":
        rem = int(inst.get("remaining_duration", 0) or 0)
        if rem > 0:
            dur_suffix = f" ({rem}t)"
    elif include_duration and inst.get("duration_type") == "minutes":
        rem = int(inst.get("remaining_duration", 0) or 0)
        if rem > 0:
            dur_suffix = f" ({rem}m)"
    return f"[{clean_name}{stack_suffix}{dur_suffix}]"


def get_status_stat_modifiers(entity: Dict[str, Any]) -> Dict[str, float]:
    """Calculates active stat, damage, and accuracy modifiers from status effects."""
    mods: Dict[str, float] = {
        "damage_taken_mult": 1.0,
        "damage_dealt_mult": 1.0,
        "accuracy_mult": 1.0,
        "accuracy_bonus": 0.0,
    }
    effects = entity.get("status_effects", [])
    if not isinstance(effects, list):
        return mods

    for eff in effects:
        if eff is None or (isinstance(eff, str) and not eff.strip()):
            continue
        inst = normalize_status_effect(eff)
        name_lower = inst["name"].lower()
        if "stagger" in name_lower:
            mods["damage_taken_mult"] *= 1.25
        if "weakened" in name_lower or "enfeebled" in name_lower:
            mods["damage_dealt_mult"] *= 0.8
        if "demoralized" in name_lower:
            mods["damage_dealt_mult"] *= 0.85
        if "enraged" in name_lower:
            mods["damage_dealt_mult"] *= 1.30
        if "blinded" in name_lower:
            mods["accuracy_mult"] *= 0.6
        if "weakpoint analyzed" in name_lower:
            mods["accuracy_bonus"] += 15.0
        if "swarmed" in name_lower:
            mods["accuracy_bonus"] -= 10.0

    return mods
