from __future__ import annotations
from typing import Optional, Any, Dict, List
"""
Code-Driven Dynamic Combat Choice Generator.
Generates 4 non-repetitive combat choices based on:
 - Slot 1: Equipped weapon + primary attack stat
 - Slot 2: Monster weakness exploit (lowest monster stat)
 - Slot 3: Class ability / magic spell
 - Slot 4: Defensive / utility action
Formats: <EMOJI> <STAT> <PCT>% <action text>  (max 100 chars)
"""
import random
import db
from mechanics.combat import calculate_opposed_dc

STAT_ICONS = {
    "STR": "💪",
    "AGI": "⚡",
    "PER": "👁️",
    "INT": "🧠",
    "END": "🛡️",
    "CHA": "🗣️",
    "LUK": "🍀",
}

# Action-type icons (varied, contextual)
ATTACK_ICONS = {
    "melee":   ["🗡️", "⚔️", "🪃", "🔨", "🪓", "🏋️"],
    "ranged":  ["🏹", "🔫", "💥", "🎯", "🪃"],
    "magic":   ["🔮", "✨", "⚡", "🌀", "💫", "🌙", "🔥", "❄️", "🌊", "☄️"],
    "exploit": ["⚡", "🎯", "🔍", "💡", "🌀", "🕳️"],
    "defend":  ["🛡️", "🦺", "🤸", "🙈", "🫷"],
    "taunt":   ["🗣️", "😤", "👊", "📢", "🎭"],
    "social":  ["📚", "💬", "🤝", "📋", "🎭"],
}

# Scenario-flavored class ability templates
# Keys are substrings that may appear in char_class (case-insensitive)
CLASS_ABILITY_TEMPLATES = {
    # Fantasy
    "mage":       ("INT", "magic",   "{weapon_or_ability}: Channel arcane pulse against {enemy}"),
    "wizard":     ("INT", "magic",   "{weapon_or_ability}: Release a spell burst targeting {enemy}"),
    "sorcerer":   ("INT", "magic",   "{weapon_or_ability}: Unleash raw sorcerous energy on {enemy}"),
    "warlock":    ("INT", "magic",   "{weapon_or_ability}: Invoke eldritch hex against {enemy}"),
    "druid":      ("INT", "magic",   "{weapon_or_ability}: Summon natural force against {enemy}"),
    "cleric":     ("CHA", "magic",   "{weapon_or_ability}: Call divine smite on {enemy}"),
    "paladin":    ("STR", "melee",   "{weapon_or_ability}: Deliver a holy power strike on {enemy}"),
    "ranger":     ("PER", "ranged",  "{weapon_or_ability}: Track and fire on {enemy}'s weak spot"),
    "rogue":      ("AGI", "melee",   "{weapon_or_ability}: Strike from shadow — blade through {enemy}"),
    "assassin":   ("AGI", "melee",   "{weapon_or_ability}: Target vital point on {enemy}"),
    "warrior":    ("STR", "melee",   "{weapon_or_ability}: Execute a power strike on {enemy}"),
    "knight":     ("END", "melee",   "{weapon_or_ability}: Charge into {enemy} with shield raised"),
    "bard":       ("CHA", "taunt",   "{weapon_or_ability}: Taunt {enemy} with a cutting verse"),
    "monk":       ("AGI", "melee",   "{weapon_or_ability}: Deliver rapid strikes on {enemy}"),
    # Sci-fi / Cyberpunk
    "netrunner":  ("INT", "magic",   "{weapon_or_ability}: Inject neural glitch into {enemy}"),
    "techie":     ("INT", "exploit", "{weapon_or_ability}: Exploit {enemy}'s system firmware"),
    "solo":       ("STR", "melee",   "{weapon_or_ability}: Execute full-auto assault on {enemy}"),
    "fixer":      ("CHA", "taunt",   "{weapon_or_ability}: Bluff and goad {enemy} into error"),
    "hacker":     ("INT", "exploit", "{weapon_or_ability}: Disable {enemy}'s targeting subsystem"),
    "cyborg":     ("STR", "melee",   "{weapon_or_ability}: Unleash chrome-fist barrage on {enemy}"),
    "merc":       ("PER", "ranged",  "{weapon_or_ability}: Fire precision volley on {enemy}"),
    # Post-apoc
    "scavenger":  ("LUK", "exploit", "{weapon_or_ability}: Improvise a trap using scrap vs {enemy}"),
    "raider":     ("STR", "melee",   "{weapon_or_ability}: Brutal charge into {enemy}"),
    "mutant":     ("END", "melee",   "{weapon_or_ability}: Tank through {enemy}'s strikes"),
    # High school
    "student":    ("INT", "social",  "{weapon_or_ability}: Cite rulebook to outmaneuver {enemy}"),
    "athlete":    ("STR", "melee",   "{weapon_or_ability}: Tackle and overpower {enemy}"),
    "debater":    ("CHA", "taunt",   "{weapon_or_ability}: Rhetorically dismantle {enemy}"),
    "rep":        ("CHA", "social",  "{weapon_or_ability}: Rally bystanders against {enemy}"),
}

# Generic fallback ability templates per scenario
SCENARIO_FALLBACK_ABILITIES = {
    "fantasy":   ("INT", "magic",   "Elemental Strike: Force arcane energy into {enemy}"),
    "scifi":     ("INT", "exploit", "System Breach: Exploit {enemy}'s hardware vulnerability"),
    "cyberpunk": ("INT", "exploit", "Neural Spike: Jam {enemy}'s targeting uplink"),
    "highschool":("CHA", "social",  "Appeal to Authority: Call for intervention against {enemy}"),
    "postapoc":  ("LUK", "exploit", "Scrap Trap: Improvise debris into a weapon against {enemy}"),
}

DEFENSIVE_TEMPLATES = [
    ("END", "defend", "Brace for Impact: Absorb {enemy}'s next strike through endurance"),
    ("AGI", "defend", "Tactical Dodge: Sidestep {enemy}'s attack and reposition"),
    ("PER", "defend", "Read the Stance: Analyze {enemy}'s movement to anticipate attack"),
    ("CHA", "taunt",  "Provoke and Parry: Taunt {enemy} to break its focus"),
    ("LUK", "defend", "Desperate Gamble: Attempt a risky counter-movement on {enemy}"),
]

WEAPON_ATTACK_TEMPLATES = {
    # Weapon type -> (stat, action_type, template)
    "sword":     ("STR", "melee",   "{weapon} slash across {enemy}'s guard"),
    "blade":     ("STR", "melee",   "{weapon} cut through {enemy}'s exposed side"),
    "dagger":    ("AGI", "melee",   "{weapon} swift stab targeting {enemy}'s gap"),
    "knife":     ("AGI", "melee",   "{weapon} thrust into {enemy}'s blind spot"),
    "staff":     ("INT", "magic",   "{weapon} channel focused power into {enemy}"),
    "wand":      ("INT", "magic",   "{weapon} focus arcane bolt at {enemy}"),
    "bow":       ("PER", "ranged",  "{weapon} fire aimed shot at {enemy}'s weak point"),
    "gun":       ("PER", "ranged",  "{weapon} precision shot at {enemy}'s core"),
    "rifle":     ("PER", "ranged",  "{weapon} burst fire targeting {enemy}"),
    "revolver":  ("PER", "ranged",  "{weapon} precision shot at {enemy}'s core"),
    "pistol":    ("PER", "ranged",  "{weapon} quick-draw shot at {enemy}"),
    "axe":       ("STR", "melee",   "{weapon} overhead cleave into {enemy}"),
    "hammer":    ("STR", "melee",   "{weapon} smash down on {enemy}"),
    "spear":     ("STR", "melee",   "{weapon} thrust through {enemy}'s guard"),
    "shield":    ("END", "defend",  "{weapon} shield slam into {enemy}"),
    "tome":      ("INT", "magic",   "{weapon} read incantation unleashing power on {enemy}"),
    "focus":     ("INT", "magic",   "{weapon} amplify arcane charge against {enemy}"),
    "fists":     ("STR", "melee",   "Bare-fisted strike directly into {enemy}"),
    "gauntlet":  ("STR", "melee",   "{weapon} reinforced fist crash into {enemy}"),
    "blade rifle": ("PER", "ranged", "{weapon} fire precision shot on {enemy}"),
    "carbine":   ("PER", "ranged",  "{weapon} rapid burst at {enemy}"),
    "katana":    ("AGI", "melee",   "{weapon} iaido draw-cut against {enemy}"),
    "rulebook":  ("INT", "social",  "{weapon} cite regulation to challenge {enemy}"),
    "textbook":  ("INT", "social",  "{weapon} reference to intellectually overwhelm {enemy}"),
}

EXPLOIT_DESCRIPTIONS = {
    "STR": ["physical guard", "brute posture", "exposed stance"],
    "AGI": ["sluggish movement", "slow reflexes", "clumsy recovery", "predictable footing"],
    "END": ["compromised armor", "brittle defense", "exhaustion", "weakened frame"],
    "INT": ["predictable pattern", "blind routine", "tactical blunder", "command loop"],
    "PER": ["sensory blind spot", "tunnel vision", "narrow focus", "unseen flank"],
    "CHA": ["unstable focus", "shaken morale", "hesitation", "erratic response"],
    "LUK": ["unfavorable positioning", "awkward footing", "overextended guard"],
}

EXPLOIT_TEMPLATES = [
    "Target exposed opening — {enemy}'s {weakness_phrase} leaves it vulnerable",
    "Exploit {enemy}'s {weakness_phrase} with precision",
    "Strike vulnerable opening — capitalize on {enemy}'s {weakness_phrase}",
    "Probe {enemy}'s defenses and exploit its {weakness_phrase}",
]

def _dc_to_pct(dc: int) -> int:
    """Convert DC (2-12) to success percentage."""
    pct = (21 - dc) * 5
    return max(5, min(95, pct))

def _pick_icon(action_type: str, used: set) -> str:
    pool = ATTACK_ICONS.get(action_type, ["⚔️"])
    unused = [i for i in pool if i not in used]
    chosen = random.choice(unused) if unused else random.choice(pool)
    used.add(chosen)
    return chosen

def _get_stat_val(char: dict, stat_name: str) -> int:
    """Get player stat value from character dict using DB naming convention."""
    key = f"{stat_name.lower()}_" if stat_name in ("STR", "PER", "END", "INT") else stat_name.lower()
    return int(char.get(key, 5))

def _truncate_label(label: str, max_len: int = 98) -> str:
    if len(label) <= max_len:
        return label
    return label[:max_len - 1] + "…"

def _get_weapon_info(char: dict, inventory: list) -> tuple[str, str, str]:
    """
    Returns (weapon_name, weapon_type_key, weapon_display).
    Looks at equipped items first, then falls back to class name.
    """
    import db
    try:
        equipment = db.get_equipment(char.get("user_id", 0))
        weapon_item = equipment.get("Weapon")
        if weapon_item and weapon_item.get("name"):
            wname = weapon_item["name"]
            wname_lower = wname.lower()
            for key in WEAPON_ATTACK_TEMPLATES:
                if key in wname_lower:
                    return wname, key, wname
            return wname, "generic", wname
    except Exception:
        pass
    return "Bare Fists", "fists", "Bare Fists"

def _get_class_ability(char: dict, scenario: str, enemy_name: str) -> tuple[str, str, str]:
    """Returns (stat_name, action_type, label_text) for the class ability slot."""
    char_class_lower = (char.get("char_class") or "").lower()
    for key, (stat, atype, tmpl) in CLASS_ABILITY_TEMPLATES.items():
        if key in char_class_lower:
            weapon, _, _ = _get_weapon_info(char, [])
            text = tmpl.format(weapon_or_ability=weapon, enemy=enemy_name)
            return stat, atype, text
    # Scenario fallback
    stat, atype, tmpl = SCENARIO_FALLBACK_ABILITIES.get(
        scenario.lower(), ("INT", "magic", "Strike: Force power into {enemy}")
    )
    return stat, atype, tmpl.format(enemy=enemy_name)

def generate_categorized_combat_actions(party: list, monster: dict, location: str = "area", scenario: str = "fantasy", session: Optional[dict] = None) -> dict:
    """
    Generates structured, categorized combat actions:
    - attacks: list of basic weapon / unarmed strikes using ACC - EVA %
    - magic: list of spells with MACC - EVA % and MP costs
    - tactics: list of tactical/environmental/social skill checks (PER, STR/AGI, CHA, END)
    - flee: flee attempt action (AGI check)
    """
    if not party:
        return {"attacks": [], "magic": [], "tactics": [], "flee": None, "flat_choices": [], "weapon_name": "Fists"}

    char, inventory = (party[0] if isinstance(party[0], tuple) else (party[0], []))
    if not isinstance(char, dict):
        return {"attacks": [], "magic": [], "tactics": [], "flee": None, "flat_choices": [], "weapon_name": "Fists"}

    monster_stats = monster.get("stats", {})
    monster_name = monster.get("name", "Enemy")
    player_luk = _get_stat_val(char, "LUK")

    from mechanics.social.attributes import calculate_combat_attributes
    from mechanics.combat.equipment import parse_equipment_metadata

    equipped_items = [item for item in inventory if isinstance(item, dict) and item.get("equipped")] if inventory else []
    p_attrs = calculate_combat_attributes(char, equipped_items)
    m_attrs = calculate_combat_attributes(monster_stats)

    acc_val = p_attrs.get("acc", 66)
    macc_val = p_attrs.get("macc", 66)
    m_eva = m_attrs.get("eva", 11)

    hit_pct = max(10, min(100, acc_val - m_eva))
    m_hit_pct = max(10, min(100, macc_val - m_eva))

    weapon_item = None
    offhand_item = None
    for item in equipped_items:
        slot_check = item.get("slot")
        type_check = (item.get("item_type") or "").lower()
        if slot_check == "Weapon" or (not weapon_item and type_check == "weapon"):
            weapon_item = item
        elif slot_check == "Shield" or (slot_check != "Weapon" and type_check == "weapon" and weapon_item and item != weapon_item):
            offhand_item = item

    weapon_meta = parse_equipment_metadata(weapon_item) if weapon_item else {}
    weapon_name = weapon_meta.get("name") or (weapon_item.get("name") if weapon_item else "Fists")
    attack_types = weapon_meta.get("attack_types", ["blunt" if not weapon_item else "slash"])

    offhand_meta = parse_equipment_metadata(offhand_item) if offhand_item else {}
    offhand_name = offhand_meta.get("name") or (offhand_item.get("name") if offhand_item else "Offhand")
    is_offhand_weapon = bool(
        offhand_item and (
            offhand_meta.get("item_type") == "Weapon"
            or (offhand_item.get("item_type") or "").lower() == "weapon"
            or "attack_types" in offhand_meta
            or "multiplier" in offhand_meta
        )
    )
    is_dual_wield = bool(
        weapon_item and offhand_item and is_offhand_weapon
        and weapon_meta.get("handedness") in ("1H", "Versatile", None)
        and offhand_meta.get("handedness") in ("1H", "Versatile", None)
    )

    # 1. ATTACKS CATEGORY
    attacks = []
    if not weapon_item:
        attacks.append({
            "label": f"👊 Unarmed Punch ({hit_pct}% • STR)",
            "stat": "STR",
            "requirement": 0,
            "hit_chance": hit_pct,
            "mp_cost": 0,
            "choice_type": "MELEE_SLASHING_PIERCING",
            "attack_type": "blunt",
            "action_category": "attack"
        })
        attacks.append({
            "label": f"🥋 Roundhouse Kick ({max(10, hit_pct - 10)}% • AGI)",
            "stat": "AGI",
            "requirement": 0,
            "hit_chance": max(10, hit_pct - 10),
            "mp_cost": 0,
            "choice_type": "MELEE_BLUNT",
            "attack_type": "blunt",
            "action_category": "attack"
        })
        attacks.append({
            "label": f"🤼 Grapple & Takedown ({max(10, hit_pct - 5)}% • STR)",
            "stat": "STR",
            "requirement": 0,
            "hit_chance": max(10, hit_pct - 5),
            "mp_cost": 0,
            "choice_type": "MELEE_BLUNT",
            "attack_type": "blunt",
            "action_category": "attack"
        })
    elif is_dual_wield:
        pri_type = attack_types[0] if attack_types else "slash"
        off_type = (offhand_meta.get("attack_types") or ["slash"])[0]
        attacks.append({
            "label": f"⚔️ Dual Flurry with {weapon_name} & {offhand_name} ({hit_pct}% • AGI)",
            "stat": "AGI",
            "requirement": 0,
            "hit_chance": hit_pct,
            "mp_cost": 0,
            "choice_type": "MELEE_SLASHING_PIERCING",
            "attack_type": pri_type,
            "action_category": "attack",
            "dual_wield": True,
            "stance": "dual_wield",
            "label_detail": f"Dual-wield flurry with {weapon_name} & {offhand_name}: +15% flurry damage"
        })
        attacks.append({
            "label": f"🗡️ Off-Hand Strike with {offhand_name} ({min(100, hit_pct + 4)}% • AGI)",
            "stat": "AGI",
            "requirement": 0,
            "hit_chance": min(100, hit_pct + 4),
            "mp_cost": 0,
            "choice_type": "MELEE_SLASHING_PIERCING",
            "attack_type": off_type,
            "action_category": "attack",
            "label_detail": f"Quick secondary attack using {offhand_name}"
        })
        attacks.append({
            "label": f"🗡️ Lead Strike with {weapon_name} ({hit_pct}% • STR)",
            "stat": "STR",
            "requirement": 0,
            "hit_chance": hit_pct,
            "mp_cost": 0,
            "choice_type": "MELEE_SLASHING_PIERCING",
            "attack_type": pri_type,
            "action_category": "attack",
            "label_detail": f"Primary lead strike with {weapon_name}"
        })
    else:
        handedness = str(weapon_meta.get("handedness", "")).capitalize()
        is_versatile = (handedness == "Versatile") or (weapon_meta.get("archetype") in ("sword", "axe", "mace", "spear"))

        if "slash" in attack_types:
            if is_versatile:
                attacks.append({
                    "label": f"🗡️ Slash (1H) with {weapon_name} ({hit_pct}% • STR)",
                    "stat": "STR",
                    "requirement": 0,
                    "hit_chance": hit_pct,
                    "mp_cost": 0,
                    "choice_type": "MELEE_SLASHING_PIERCING",
                    "attack_type": "slash",
                    "action_category": "attack",
                    "stance": "1H",
                    "label_detail": "1H grip: standard power, retains shield guard"
                })
                attacks.append({
                    "label": f"⚔️ Slash (2H) with {weapon_name} ({hit_pct}% • STR)",
                    "stat": "STR",
                    "requirement": 0,
                    "hit_chance": hit_pct,
                    "mp_cost": 0,
                    "choice_type": "MELEE_SLASHING_PIERCING",
                    "attack_type": "slash",
                    "action_category": "attack",
                    "stance": "2H",
                    "label_detail": "2H grip: +15% dmg & +4% crit, lowers shield guard"
                })
            else:
                attacks.append({
                    "label": f"🗡️ Slash with {weapon_name} ({hit_pct}% • STR)",
                    "stat": "STR",
                    "requirement": 0,
                    "hit_chance": hit_pct,
                    "mp_cost": 0,
                    "choice_type": "MELEE_SLASHING_PIERCING",
                    "attack_type": "slash",
                    "action_category": "attack"
                })
        if "thrust" in attack_types:
            if is_versatile and not any(a.get("stance") == "2H" for a in attacks):
                attacks.append({
                    "label": f"🔱 Thrust (1H) with {weapon_name} ({min(100, hit_pct + 5)}% • AGI)",
                    "stat": "AGI",
                    "requirement": 0,
                    "hit_chance": min(100, hit_pct + 5),
                    "mp_cost": 0,
                    "choice_type": "MELEE_SLASHING_PIERCING",
                    "attack_type": "thrust",
                    "action_category": "attack",
                    "stance": "1H",
                    "label_detail": "1H grip: standard power, retains shield guard"
                })
                attacks.append({
                    "label": f"⚔️ Thrust (2H) with {weapon_name} ({min(100, hit_pct + 5)}% • AGI)",
                    "stat": "AGI",
                    "requirement": 0,
                    "hit_chance": min(100, hit_pct + 5),
                    "mp_cost": 0,
                    "choice_type": "MELEE_SLASHING_PIERCING",
                    "attack_type": "thrust",
                    "action_category": "attack",
                    "stance": "2H",
                    "label_detail": "2H grip: +15% dmg & +4% crit, lowers shield guard"
                })
            else:
                attacks.append({
                    "label": f"🔱 Thrust with {weapon_name} ({min(100, hit_pct + 5)}% • AGI)",
                    "stat": "AGI",
                    "requirement": 0,
                    "hit_chance": min(100, hit_pct + 5),
                    "mp_cost": 0,
                    "choice_type": "MELEE_SLASHING_PIERCING",
                    "attack_type": "thrust",
                    "action_category": "attack"
                })
        if "hack" in attack_types:
            if is_versatile and not any(a.get("stance") == "2H" for a in attacks):
                attacks.append({
                    "label": f"🪓 Cleave (1H) with {weapon_name} ({hit_pct}% • STR)",
                    "stat": "STR",
                    "requirement": 0,
                    "hit_chance": hit_pct,
                    "mp_cost": 0,
                    "choice_type": "MELEE_SLASHING_PIERCING",
                    "attack_type": "hack",
                    "action_category": "attack",
                    "stance": "1H",
                    "label_detail": "1H grip: standard power, retains shield guard"
                })
                attacks.append({
                    "label": f"⚔️ Cleave (2H) with {weapon_name} ({hit_pct}% • STR)",
                    "stat": "STR",
                    "requirement": 0,
                    "hit_chance": hit_pct,
                    "mp_cost": 0,
                    "choice_type": "MELEE_SLASHING_PIERCING",
                    "attack_type": "hack",
                    "action_category": "attack",
                    "stance": "2H",
                    "label_detail": "2H grip: +15% dmg & +4% crit, lowers shield guard"
                })
            else:
                attacks.append({
                    "label": f"🪓 Cleave / Hack with {weapon_name} ({hit_pct}% • STR)",
                    "stat": "STR",
                    "requirement": 0,
                    "hit_chance": hit_pct,
                    "mp_cost": 0,
                    "choice_type": "MELEE_SLASHING_PIERCING",
                    "attack_type": "hack",
                    "action_category": "attack"
                })
        if "blunt" in attack_types or "club" in attack_types:
            if is_versatile and not any(a.get("stance") == "2H" for a in attacks):
                attacks.append({
                    "label": f"🔨 Strike (1H) with {weapon_name} ({hit_pct}% • STR)",
                    "stat": "STR",
                    "requirement": 0,
                    "hit_chance": hit_pct,
                    "mp_cost": 0,
                    "choice_type": "MELEE_BLUNT",
                    "attack_type": "blunt",
                    "action_category": "attack",
                    "stance": "1H",
                    "label_detail": "1H grip: standard power, retains shield guard"
                })
                attacks.append({
                    "label": f"⚔️ Strike (2H) with {weapon_name} ({hit_pct}% • STR)",
                    "stat": "STR",
                    "requirement": 0,
                    "hit_chance": hit_pct,
                    "mp_cost": 0,
                    "choice_type": "MELEE_BLUNT",
                    "attack_type": "blunt",
                    "action_category": "attack",
                    "stance": "2H",
                    "label_detail": "2H grip: +15% dmg & +4% crit, lowers shield guard"
                })
            else:
                attacks.append({
                    "label": f"🔨 Strike / Sweep with {weapon_name} ({hit_pct}% • STR)",
                    "stat": "STR",
                    "requirement": 0,
                    "hit_chance": hit_pct,
                    "mp_cost": 0,
                    "choice_type": "MELEE_BLUNT",
                    "attack_type": "blunt",
                    "action_category": "attack"
                })
        if "magic_channel" in attack_types:
            attacks.append({
                "label": f"🔮 Arcane Burst with {weapon_name} ({hit_pct}% • INT)",
                "stat": "INT",
                "requirement": 0,
                "hit_chance": hit_pct,
                "mp_cost": 0,
                "choice_type": "MAGIC_SPELL",
                "attack_type": "magical",
                "action_category": "attack"
            })
        if "ranged" in attack_types or "firearm" in attack_types:
            attacks.append({
                "label": f"🎯 Aimed Shot with {weapon_name} ({min(100, hit_pct + 5)}% • PER)",
                "stat": "PER",
                "requirement": 0,
                "hit_chance": min(100, hit_pct + 5),
                "mp_cost": 0,
                "choice_type": "RANGED_ATTACK",
                "attack_type": "ranged",
                "action_category": "attack"
            })
            attacks.append({
                "label": f"⚡ Quick Shot with {weapon_name} ({max(10, hit_pct - 10)}% • AGI)",
                "stat": "AGI",
                "requirement": 0,
                "hit_chance": max(10, hit_pct - 10),
                "mp_cost": 0,
                "choice_type": "RANGED_ATTACK",
                "attack_type": "ranged",
                "action_category": "attack"
            })

        if len(attacks) < 2:
            attacks.append({
                "label": f"💥 Heavy Power Strike ({max(10, hit_pct - 10)}% • STR)",
                "stat": "STR",
                "requirement": 0,
                "hit_chance": max(10, hit_pct - 10),
                "mp_cost": 0,
                "choice_type": "MELEE_SLASHING_PIERCING",
                "attack_type": attack_types[0] if attack_types else "slash",
                "action_category": "attack"
            })

    # Flanking Backstab from Shadows
    from mechanics.stealth import is_actor_combat_vanished
    is_vanished = bool(
        char.get("combat_vanished")
        or (isinstance(session, dict) and is_actor_combat_vanished(session, char.get("user_id")))
        or any("Hidden in Shadows" in str(s) for s in char.get("status_effects", []))
    )
    if is_vanished:
        attacks.insert(0, {
            "label": f"🗡️ Flanking Backstab / Critical Snipe ({min(100, hit_pct + 15)}% • AGI)",
            "stat": "AGI",
            "requirement": 0,
            "hit_chance": min(100, hit_pct + 15),
            "mp_cost": 0,
            "choice_type": "MELEE_SLASHING_PIERCING",
            "attack_type": "pierce",
            "action_category": "attack",
            "stance": "stealth",
            "label_detail": "Strike from unseen angle: +50% surprise damage, 50% armor pierce, and high critical rate"
        })

    # 2. MAGIC & SPELLS CATEGORY
    magic = []
    from mechanics.combat.spells import get_spell, get_starter_spells, format_spell_choice_label
    user_id = char.get("user_id")
    learned_spells = db.get_learned_spells(user_id) if user_id else []

    # If character has no learned spells yet, populate starter spell kit scaled by INT
    if not learned_spells:
        int_val = _get_stat_val(char, "INT")
        class_desc = char.get("class_description", "")
        learned_spells = get_starter_spells(scenario or "fantasy", char.get("char_class", ""), int_stat=int_val, class_description=class_desc)
        if user_id:
            db.set_learned_spells(user_id, learned_spells)

    for spell_id in learned_spells:
        spell = get_spell(spell_id)
        if not spell:
            continue
        disc = spell.get("discipline", "attack")
        target_type = spell.get("target_type", "single")
        acc_mod = spell.get("acc_mod", 0)

        # Determine hit chance based on target archetype
        if target_type in ("support", "summon"):
            hit_chance = 100
        elif target_type == "chain":
            hit_chance = min(100, m_hit_pct + abs(acc_mod))  # +10 homing
        elif target_type == "aoe":
            hit_chance = max(10, m_hit_pct + acc_mod)        # -5 blast spread
        else:
            hit_chance = m_hit_pct

        stat_type = "INT" if disc not in ("support",) else "END"

        label = format_spell_choice_label(spell, hit_chance, char.get("mp", 0))
        magic.append({
            "label": label,
            "stat": stat_type,
            "requirement": 0,
            "hit_chance": hit_chance,
            "mp_cost": spell.get("mp_cost", 0),
            "spell_id": spell["id"],
            "choice_type": "MAGIC_SPELL",
            "action_category": "magic",
            "is_chain": target_type == "chain",
            "discipline": disc
        })


    # 3. TACTICS & ENVIRONMENT CATEGORY
    tactics = []
    p_per = _get_stat_val(char, "PER")
    m_per = monster_stats.get("PER", 3)
    dc_per = calculate_opposed_dc(p_per, m_per, player_luk)
    pct_per = _dc_to_pct(dc_per)
    tactics.append({
        "label": f"👁️ Scan Weakpoint ({pct_per}% • PER)",
        "stat": "PER",
        "requirement": dc_per,
        "hit_chance": pct_per,
        "mp_cost": 0,
        "choice_type": "WEAKNESS_EXPLOIT",
        "action_category": "tactics"
    })

    p_str = _get_stat_val(char, "STR")
    m_agi = monster_stats.get("AGI", 3)
    dc_env = calculate_opposed_dc(p_str, m_agi, player_luk)
    pct_env = _dc_to_pct(dc_env)
    tactics.append({
        "label": f"🪑 Use Environment Hazard ({pct_env}% • STR)",
        "stat": "STR",
        "requirement": dc_env,
        "hit_chance": pct_env,
        "mp_cost": 0,
        "choice_type": "ENVIRONMENTAL_TRAP",
        "action_category": "tactics"
    })

    p_cha = _get_stat_val(char, "CHA")
    m_cha = monster_stats.get("CHA", 3)
    dc_cha = calculate_opposed_dc(p_cha, m_cha, player_luk)
    pct_cha = _dc_to_pct(dc_cha)
    tactics.append({
        "label": f"🗣️ Intimidate & Taunt ({pct_cha}% • CHA)",
        "stat": "CHA",
        "requirement": dc_cha,
        "hit_chance": pct_cha,
        "mp_cost": 0,
        "choice_type": "DIPLOMACY_TAUNT",
        "action_category": "tactics"
    })

    p_end = _get_stat_val(char, "END")
    m_str = monster_stats.get("STR", 3)
    dc_end = calculate_opposed_dc(p_end, m_str, player_luk)
    pct_end = _dc_to_pct(dc_end)
    tactics.append({
        "label": f"🛡️ Defensive Guard & Brace ({pct_end}% • END)",
        "stat": "END",
        "requirement": dc_end,
        "hit_chance": pct_end,
        "mp_cost": 0,
        "choice_type": "DEFENSIVE_GUARD",
        "action_category": "tactics"
    })

    # AGI Tactic: Vanish into Shadows (only if not already vanished)
    if not is_vanished:
        dc_vanish = calculate_opposed_dc(p_agi if 'p_agi' in locals() else _get_stat_val(char, "AGI"), m_per, player_luk)
        pct_vanish = _dc_to_pct(dc_vanish)
        tactics.append({
            "label": f"💨 Vanish into Shadows ({pct_vanish}% • AGI)",
            "stat": "AGI",
            "requirement": dc_vanish,
            "hit_chance": pct_vanish,
            "mp_cost": 0,
            "choice_type": "STEALTH_VANISH",
            "action_category": "tactics",
            "label_detail": "Slip into shadows: sheds enemy aggro onto companions and primes Flanking Backstab (+50% dmg)"
        })

    # Non-Hostile Agitated Entity Containment Tactics (Persuade/Calm at any HP + Subdue at <= 35% HP)
    if monster.get("requires_non_lethal_subdue"):
        m_cur_hp = int(monster.get("hp", 10) or 10)
        m_max_hp = max(1, int(monster.get("max_hp", 40) or 40))
        sub_pct = float(monster.get("subdue_threshold_pct") or 0.35)
        persuade_dc = 6 if m_cur_hp <= max(1, int(m_max_hp * 0.50)) else 8
        persuade_pct = _dc_to_pct(persuade_dc)
        tactics.insert(0, {
            "label": f"🗣️ Persuade / Calm {monster_name} (De-escalate)",
            "stat": "CHA",
            "requirement": persuade_dc,
            "hit_chance": persuade_pct,
            "mp_cost": 0,
            "choice_type": "DIPLOMACY_TAUNT",
            "action_category": "tactics",
            "intent": "anomalous_incursion_action",
            "incursion_action": "combat_persuade",
            "incursion_id": monster.get("incursion_id", ""),
            "quest_id": monster.get("linked_quest_id", ""),
            "label_detail": "Non-lethally calm and contain the agitated entity alive without dealing lethal damage",
        })
        if 0 < m_cur_hp <= max(1, int(m_max_hp * sub_pct)):
            tactics.insert(0, {
                "label": f"🛡️ Subdue & Contain {monster_name}",
                "stat": "FREE",
                "requirement": 0,
                "hit_chance": 100,
                "mp_cost": 0,
                "choice_type": "DEFENSIVE_GUARD",
                "action_category": "tactics",
                "intent": "anomalous_incursion_action",
                "incursion_action": "subdue",
                "incursion_id": monster.get("incursion_id", ""),
                "quest_id": monster.get("linked_quest_id", ""),
                "label_detail": "Safely capture and seal the weakened entity (<= 35% HP) alive",
            })

    # 4. FLEE CATEGORY
    p_agi = _get_stat_val(char, "AGI")
    dc_flee = calculate_opposed_dc(p_agi, m_agi, player_luk)
    pct_flee = _dc_to_pct(dc_flee)
    flee_action = {
        "label": f"🏃 Disengage & Flee ({pct_flee}% • AGI)",
        "stat": "AGI",
        "requirement": dc_flee,
        "hit_chance": pct_flee,
        "mp_cost": 0,
        "choice_type": "EVADE_TACTICAL_FLEE",
        "action_category": "flee"
    }

    # Ensure all actions have target_entity, intent, sub_intent, and target_npc
    for act in attacks:
        if act:
            act.setdefault("intent", "general_action")
            act.setdefault("sub_intent", "combat_attack")
            act.setdefault("target_npc", monster_name)
            act.setdefault("target_entity", monster_name)
    for act in magic:
        if act:
            act.setdefault("intent", "general_action")
            act.setdefault("sub_intent", "combat_magic")
            act.setdefault("target_npc", monster_name)
            act.setdefault("target_entity", monster_name)
    for act in tactics:
        if act:
            act.setdefault("intent", "general_action")
            act.setdefault("sub_intent", "combat_tactic")
            act.setdefault("target_npc", monster_name)
            act.setdefault("target_entity", monster_name)
    if flee_action:
        flee_action.setdefault("intent", "movement")
        flee_action.setdefault("sub_intent", "combat_flee")
        flee_action.setdefault("target_npc", monster_name)
        flee_action.setdefault("target_entity", monster_name)

    return {
        "attacks": attacks,
        "magic": magic,
        "tactics": tactics,
        "flee": flee_action,
        "weapon_name": weapon_name
    }


def generate_procedural_scene_choices(scenario: str = "fantasy", location: str = "", char: dict = None) -> list[dict]:
    """Synthesizes 4 rich, distinct scenario-appropriate tactical choices
    when an LLM fails to return choices, ensuring no turn is left empty."""
    scen_key = str(scenario or "fantasy").lower()

    TEMPLATES = {
        "highschool": [
            ("INT", "Review student council records and notes for clues", 6),
            ("PER", "Search the surrounding area carefully for evidence", 5),
            ("CHA", "Initiate a conversation to learn more details", 5),
            ("AGI", "Check the hallway and monitor movement nearby", 4),
        ],
        "slice_of_life": [
            ("CHA", "Greet those nearby and strike up a casual conversation", 5),
            ("PER", "Take in the surroundings and notice subtle details", 4),
            ("INT", "Check your daily schedule and organize your tasks", 5),
            ("AGI", "Stroll through the area to see what is happening", 4),
        ],
        "cyberpunk": [
            ("INT", "Scan local datalinks and breach subnet security", 7),
            ("PER", "Inspect surveillance angles and optical feeds", 5),
            ("CHA", "Interrogate local contacts for actionable intel", 6),
            ("AGI", "Maneuver quietly into an advantageous position", 5),
        ],
        "fantasy": [
            ("INT", "Analyze ambient magical resonance in the room", 6),
            ("PER", "Search the chamber for hidden compartments or runes", 5),
            ("CHA", "Converse with companions to assess the next move", 5),
            ("STR", "Exert force to breach or test the heavy doorway", 6),
        ],
        "scifi": [
            ("INT", "Access the console terminal to run diagnostics", 6),
            ("PER", "Scan atmospheric readings and sensor arrays", 5),
            ("CHA", "Open comms channel to hail nearby entities", 5),
            ("AGI", "Reposition along the primary corridor defensively", 5),
        ],
        "steampunk": [
            ("INT", "Examine pressure gauges and pneumatic valves", 6),
            ("PER", "Investigate aetheric residue and steam vents", 5),
            ("CHA", "Negotiate with the station crew and tinkers", 5),
            ("AGI", "Navigate across the elevated catwalks and pipes", 5),
        ],
        "postapoc": [
            ("INT", "Examine old world blueprints and machinery", 6),
            ("PER", "Scout the ruins for salvageable supplies and tracks", 5),
            ("LUK", "Scavenge debris in search of useful tools", 4),
            ("AGI", "Move quietly across the rubble avoiding noise", 5),
        ],
    }

    norm_key = scen_key.replace("-", "_")
    options = None
    if any(k in norm_key for k in ("high_school", "highschool", "school", "academy")):
        options = TEMPLATES["highschool"]
    elif any(k in norm_key for k in ("slice_of_life", "sliceoflife", "sol")):
        options = TEMPLATES["slice_of_life"]
    elif any(k in norm_key for k in ("cyberpunk", "cyber")):
        options = TEMPLATES["cyberpunk"]
    elif any(k in norm_key for k in ("sci_fi", "scifi", "space")):
        options = TEMPLATES["scifi"]
    elif any(k in norm_key for k in ("steampunk", "steam")):
        options = TEMPLATES["steampunk"]
    elif any(k in norm_key for k in ("post_apoc", "postapoc", "apocalypse", "nuclear")):
        options = TEMPLATES["postapoc"]
    elif any(k in norm_key for k in ("fantasy", "isekai")):
        options = TEMPLATES["fantasy"]
    else:
        options = TEMPLATES.get(scen_key)
        if not options:
            for k in TEMPLATES:
                if k.replace("_", "") in norm_key.replace("_", ""):
                    options = TEMPLATES[k]
                    break
        if not options:
            options = TEMPLATES["fantasy"]

    choices = []
    for stat, label, req in options:
        intent = "investigate_clue" if stat in ("INT", "PER") else ("dialogue_init" if stat == "CHA" else "area_scout")
        choices.append({
            "label": label,
            "stat": stat,
            "requirement": req,
            "mp_cost": 0,
            "intent": intent,
            "sub_intent": "",
            "target_npc": "",
            "is_fallback": True,
        })
    return choices


def get_scenario_dialogue_fallbacks(
    partner_name: str,
    scenario: str = "fantasy",
    present_bystanders: list = None,
    location: str = "",
    char: dict = None,
    affinity_score: int = 0,
    relationship_track: str = "platonic",
    is_private_meetup: bool = False,
) -> list[dict]:
    """Generates rich, scenario-appropriate conversational and social interaction fallback choices
    addressing the active dialogue partner, present room bystanders, and immediate setting."""
    partner = str(partner_name or "your companion").strip()
    scen_key = str(scenario or "fantasy").lower().replace("-", "_")
    warm_social = bool(is_private_meetup or affinity_score >= 50 or str(relationship_track).lower() == "romantic")

    # 1. Partner-focused conversational templates per scenario genre (Stranger-safe by default)
    TEMPLATES = {
        "highschool": [
            (
                "CHA",
                f"Playfully comment on {partner}'s reaction and joke about the situation"
                if warm_social
                else f"Ask {partner} directly about their role on campus and current activities",
                6,
            ),
            ("INT", f"Ask {partner} about upcoming classes, homeroom duties, or campus rumors", 6),
            ("PER", f"Notice {partner}'s expression and ask what is on their mind", 5),
        ],
        "slice_of_life": [
            (
                "CHA",
                f"Share a lighthearted observation and tease {partner} casually"
                if warm_social
                else f"Ask {partner} politely about their routine around the neighborhood",
                5,
            ),
            ("INT", f"Ask {partner} about their schedule, plans, and what they are working on", 5),
            ("PER", f"Pay close attention to {partner}'s mood and ask how their day is going", 5),
        ],
        "cyberpunk": [
            (
                "CHA",
                f"Exchange street-smart banter and probe {partner} with casual swagger"
                if warm_social
                else f"Question {partner} directly about local crew activity and sector conditions",
                6,
            ),
            ("INT", f"Inquire into local network rumors, fixer jobs, and street alerts with {partner}", 6),
            ("PER", f"Read {partner}'s body language and gauge their nervous cyber-ticks", 5),
        ],
        "scifi": [
            (
                "CHA",
                f"Exchange casual banter over comms and compare notes with {partner}"
                if warm_social
                else f"Ask {partner} for a status update on their current assignment",
                5,
            ),
            ("INT", f"Query {partner} regarding sensor logs, sector news, and station diagnostics", 6),
            ("PER", f"Monitor {partner}'s vital telemetry and ask how they are holding up", 5),
        ],
        "steampunk": [
            (
                "CHA",
                f"Share a wry observation and converse casually with {partner}"
                if warm_social
                else f"Ask {partner} about their craft and current work in the district",
                5,
            ),
            ("INT", f"Inquire with {partner} about local inventor guilds, patents, and aetheric currents", 6),
            ("PER", f"Assess {partner}'s demeanor amidst the steam pressure and machinery hum", 5),
        ],
        "postapoc": [
            (
                "CHA",
                f"Share a brief bit of dry wasteland humor with {partner}"
                if warm_social
                else f"Ask {partner} directly about settlement conditions and patrol status",
                5,
            ),
            ("INT", f"Inquire into supply routes, safe havens, and local scav reports with {partner}", 6),
            ("PER", f"Gauge {partner}'s fatigue and check if they have spotted any threats", 5),
        ],
        "fantasy": [
            (
                "CHA",
                f"Share friendly banter and discuss the journey with {partner}"
                if warm_social
                else f"Ask {partner} about recent bounties, travelers, and trouble along the road",
                5,
            ),
            ("INT", f"Inquire into local lore, guild contracts, and background details with {partner}", 6),
            ("PER", f"Observe {partner}'s demeanor and assess their readiness for what lies ahead", 5),
        ],
    }

    if any(k in scen_key for k in ("high_school", "highschool", "school", "academy")):
        options = TEMPLATES["highschool"]
    elif any(k in scen_key for k in ("slice_of_life", "sliceoflife", "sol")):
        options = TEMPLATES["slice_of_life"]
    elif any(k in scen_key for k in ("cyberpunk", "cyber")):
        options = TEMPLATES["cyberpunk"]
    elif any(k in scen_key for k in ("sci_fi", "scifi", "space")):
        options = TEMPLATES["scifi"]
    elif any(k in scen_key for k in ("steampunk", "steam")):
        options = TEMPLATES["steampunk"]
    elif any(k in scen_key for k in ("post_apoc", "postapoc", "apocalypse", "nuclear")):
        options = TEMPLATES["postapoc"]
    else:
        options = TEMPLATES.get(scen_key, TEMPLATES["fantasy"])

    choices = []
    for stat, label, req in options:
        choices.append({
            "label": label,
            "stat": stat,
            "requirement": req,
            "mp_cost": 0,
            "intent": "dialogue_init",
            "sub_intent": "",
            "target_npc": partner,
            "is_fallback": False,
            "_deterministic_supplement": True,
        })

    # 2. Add lightweight engagement options with other present room bystanders if available
    if present_bystanders and isinstance(present_bystanders, list):
        import game_engine
        added_bystanders = 0
        for b in present_bystanders:
            b_name = game_engine._get_npc_name(b) if hasattr(game_engine, "_get_npc_name") else (b.get("name") if isinstance(b, dict) else str(b))
            if not b_name or b_name.lower() in ("none", partner.lower()):
                continue
            b_role = (b.get("role") if isinstance(b, dict) else "") or ""
            b_role_low = b_role.lower()

            if any(k in scen_key for k in ("high_school", "highschool", "school", "academy")):
                if any(cr in b_role_low for cr in ("rep", "council", "president", "lead")):
                    b_label = f"Approach {b_name} ({b_role}) to check morning announcements or roll call"
                    b_stat = "INT"
                    b_req = 6
                else:
                    b_label = f"Wave over to {b_name} and greet them before the bell rings"
                    b_stat = "CHA"
                    b_req = 5
            elif any(k in scen_key for k in ("slice_of_life", "sliceoflife", "sol")):
                b_label = f"Give a friendly wave to {b_name} and see how they are doing"
                b_stat = "CHA"
                b_req = 5
            elif any(k in scen_key for k in ("cyberpunk", "cyber")):
                b_label = f"Nod in {b_name}'s direction and assess what angle they are working"
                b_stat = "PER"
                b_req = 5
            else:
                b_label = f"Acknowledge {b_name} nearby with a respectful nod and casual greeting"
                b_stat = "CHA"
                b_req = 5

            choices.append({
                "label": b_label,
                "stat": b_stat,
                "requirement": b_req,
                "mp_cost": 0,
                "intent": "dialogue_init",
                "sub_intent": "",
                "target_npc": b_name,
                "is_fallback": False,
                "_deterministic_supplement": True,
            })
            added_bystanders += 1
            if added_bystanders >= 2:
                break

    # 3. Ambient room/desk activity fallback if location indicates a homeroom / study desk / room
    loc_low = str(location or "").lower()
    if any(k in scen_key for k in ("high_school", "highschool", "school", "academy")):
        if "desk" in loc_low or "room 201" in loc_low or "homeroom" in loc_low or "classroom" in loc_low:
            choices.append({
                "label": "Take your seat at your desk and organize your study materials",
                "stat": "PER",
                "requirement": 5,
                "mp_cost": 0,
                "intent": "general_action",
                "sub_intent": "",
                "target_npc": "",
                "is_fallback": False,
                "_deterministic_supplement": True,
            })

    return choices

