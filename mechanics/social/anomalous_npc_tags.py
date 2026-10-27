from __future__ import annotations
"""
Deterministic Special Agent vs. Civilian Tag Engine for Anomalous Incursions.

Enforces permanent NPC classification, recruitment eligibility, Tier-scaled Special Agent
combat vitals & MP-consuming innate ability AI, role-based Civilian mundane loadouts
(100 HP / 0 MP, zero abilities, reduced chip damage vs. supernatural anomalies), and
Civilian permadeath stakes when slain by hostile Anomalous Entities.
"""
import hashlib
import json
import random
import re
from typing import Any, Dict, List, Optional, Tuple

import db
import scenario_data

TAG_SPECIAL_AGENT = "special_agent"
TAG_CIVILIAN = "civilian"

CIVILIAN_BASE_HP = 100
CIVILIAN_BASE_MP = 0

# Tier 1..5 dedicated Special Agent baseline vitals (strictly outscaling Civilian 100 HP / 0 MP)
SPECIAL_AGENT_TIER_VITALS: Dict[int, Tuple[int, int]] = {
    1: (130, 60),
    2: (165, 85),
    3: (205, 110),
    4: (245, 135),
    5: (290, 165),
}

# Explicit awakened / mana-wielding operative patterns for emergent narrative NPCs
_AWAKENED_OPERATIVE_PATTERNS: List[str] = [
    r"\bspecial\s+agent\b",
    r"\bfield\s+operative\b",
    r"\bcontainment\s+(?:\w+[-\s]+)?(?:specialist|operative|marshal|officer|commander|agent)\b",
    r"\bbreach\s+(?:\w+[-\s]+)?(?:operative|breaker|specialist|vanguard|warden)\b",
    r"\b(?:incursion|anomaly|anomalous|relic|occult|paranormal|rogue|freelance)\s+(?:\w+[-\s]+)?(?:hunter|operative|specialist|exorcist|investigator|contractor|slayer|stalker|mercenary)\b",
    r"\b(?:exorcist|onmyoji|shrine\s+warden|shrine\s+maiden|purifier|barrier\s+master|monastic\s+sentinel|ascetic\s+monk|talisman\s+master)\b",
    r"\b(?:ritualist|blood[-\s]weaver|void[-\s]caller|covenant\s+apostle|occult\s+adept|thaumaturge|geomancer|hex[-\s]slinger|esper|psion|telekinetic|technomancer)\b",
    r"\bawakened\s+(?:\w+[-\s]+)?(?:enforcer|operative|mercenary|hunter|assassin|agent|fighter|brawler|ronin|specialist|guard)\b",
    r"\bmana[-\s](?:wielder|user|infused|adept|operative)\b",
    r"\b(?:aegis\s+vanguard|tactical\s+breacher|resonance\s+sniper|street\s+ronin|shadow\s+broker)\b",
]

# Mundane roles that NEVER get Special Agent unless an explicit awakened/mana marker is also present
_MUNDANE_CIVILIAN_PATTERNS: List[str] = [
    r"\b(?:quartermaster|requisition\s+clerk|armorer|supply\s+officer|logistics\s+clerk|archivist|receptionist|dispatcher|secretary)\b",
    r"\b(?:police|police\s+officer|cop|patrol\s+officer|precinct\s+detective|homicide\s+detective|traffic\s+warden|swat)\b",
    r"\b(?:security\s+guard|security\s+officer|campus\s+guard|night\s+watchman|bouncer|bodyguard|mall\s+cop)\b",
    r"\b(?:street\s+thug|gang\s+member|gangster|mugger|hooligan|delinquent|syndicate\s+grunt|cartel\s+thug|pickpocket)\b",
    r"\b(?:clerk|cashier|barista|bartender|waiter|waitress|chef|cook|butcher|janitor|mechanic|driver|taxi\s+driver|courier)\b",
    r"\b(?:student|teacher|professor|nurse|doctor|surgeon|paramedic|journalist|reporter|civilian|citizen|bystander|resident|neighbor)\b",
    r"\b(?:mother|father|sister|brother|cousin|uncle|aunt|grandmother|grandfather|parent|spouse|landlord|landlady|shopkeeper|merchant|vendor)\b",
]

_AWAKENED_RE = [re.compile(p, re.IGNORECASE) for p in _AWAKENED_OPERATIVE_PATTERNS]
_MUNDANE_RE = [re.compile(p, re.IGNORECASE) for p in _MUNDANE_CIVILIAN_PATTERNS]


def _stable_hash(seed_text: str) -> int:
    return int(hashlib.md5(seed_text.encode("utf-8", errors="ignore")).hexdigest()[:12], 16)


def _extract_basic_info(entity: Any) -> Dict[str, Any]:
    if not isinstance(entity, dict):
        return {}
    b = entity.get("basic_info")
    if isinstance(b, dict):
        return dict(b)
    if isinstance(b, str) and b.strip().startswith("{"):
        try:
            parsed = json.loads(b)
            if isinstance(parsed, dict):
                return parsed
        except Exception:
            pass
    return {}


def _get_known_faction_class_names_lower() -> set[str]:
    try:
        from mechanics.combat.items.anomalous_gear import ANOMALOUS_FACTION_CLASSES
        names: set[str] = set()
        for c_list in ANOMALOUS_FACTION_CLASSES.values():
            for c_entry in c_list:
                if isinstance(c_entry, dict) and c_entry.get("name"):
                    names.add(str(c_entry["name"]).strip().lower())
        return names
    except Exception:
        return set()


def classify_anomalous_npc_tag(
    entity: Any,
    session_id: int = 0,
    scen_key: str = "",
) -> str:
    """
    Deterministically classifies an NPC in Anomalous Incursions as either
    `special_agent` or `civilian`.

    Immutability Rule:
    - Once `anomalous_npc_tag` is persisted on the NPC, Contact, or Lorebook record,
      that tag is permanent and never changes mid-campaign.
    """
    if isinstance(entity, str):
        name = entity.strip()
        ent_dict: Dict[str, Any] = {"name": name}
    elif isinstance(entity, dict):
        ent_dict = entity
        name = str(ent_dict.get("name") or ent_dict.get("title") or "").strip()
    else:
        return TAG_CIVILIAN

    basic = _extract_basic_info(ent_dict)

    # 1. Check direct persisted tag on entity or basic_info (Strictly Permanent)
    for raw_tag in (
        ent_dict.get("anomalous_npc_tag"),
        basic.get("anomalous_npc_tag"),
    ):
        clean_t = str(raw_tag or "").strip().lower()
        if clean_t in (TAG_SPECIAL_AGENT, TAG_CIVILIAN):
            return clean_t

    if ent_dict.get("is_special_agent") is True or basic.get("is_special_agent") is True:
        return TAG_SPECIAL_AGENT
    if ent_dict.get("is_special_agent") is False and ent_dict.get("anomalous_npc_tag") == TAG_CIVILIAN:
        return TAG_CIVILIAN

    # 2. Check 44 Pre-Seeded Special Agents Roster + Persisted DB Contact / Lorebook
    if session_id and name:
        try:
            from mechanics.social.agent_roster import find_special_agent_by_name
            if find_special_agent_by_name(session_id, name, scen_key=scen_key):
                return TAG_SPECIAL_AGENT
        except Exception:
            pass

        try:
            c_rec = db.get_contact(session_id, name)
            if not isinstance(c_rec, dict):
                for cand in (db.get_contacts(session_id) or []):
                    if isinstance(cand, dict) and str(cand.get("name") or "").strip().lower() == name.lower():
                        c_rec = cand
                        break
            if isinstance(c_rec, dict):
                cb = _extract_basic_info(c_rec)
                persisted_c_tag = str(cb.get("anomalous_npc_tag") or c_rec.get("anomalous_npc_tag") or "").strip().lower()
                if persisted_c_tag in (TAG_SPECIAL_AGENT, TAG_CIVILIAN):
                    return persisted_c_tag
                if cb.get("is_special_agent") is True:
                    return TAG_SPECIAL_AGENT
                if not ent_dict.get("role") and cb.get("role"):
                    ent_dict = {**ent_dict, "role": cb.get("role"), "description": cb.get("description", "")}
                    basic = {**cb, **basic}
        except Exception:
            pass

        try:
            lore_ent = db.get_lorebook_entity(session_id, name)
            if isinstance(lore_ent, dict):
                l_meta = lore_ent.get("metadata") if isinstance(lore_ent.get("metadata"), dict) else {}
                persisted_l_tag = str(
                    lore_ent.get("anomalous_npc_tag")
                    or l_meta.get("anomalous_npc_tag")
                    or ""
                ).strip().lower()
                if persisted_l_tag in (TAG_SPECIAL_AGENT, TAG_CIVILIAN):
                    return persisted_l_tag
                if not ent_dict.get("role") and (lore_ent.get("role") or lore_ent.get("description")):
                    ent_dict = {
                        **ent_dict,
                        "role": ent_dict.get("role") or lore_ent.get("role", ""),
                        "description": ent_dict.get("description") or lore_ent.get("description", ""),
                    }
        except Exception:
            pass

    # 3. Evaluate Role / Class / Description for Emergent Awakened Operatives vs. Mundane Civilians
    agent_cls = str(ent_dict.get("agent_class") or basic.get("agent_class") or ent_dict.get("char_class") or "").strip()
    role = str(ent_dict.get("role") or ent_dict.get("occupation") or basic.get("role") or basic.get("occupation") or "").strip()
    desc = str(ent_dict.get("description") or basic.get("description") or ent_dict.get("personality_summary") or "").strip()

    known_classes = _get_known_faction_class_names_lower()
    if agent_cls and agent_cls.lower() in known_classes:
        return TAG_SPECIAL_AGENT
    if role and role.lower() in known_classes:
        return TAG_SPECIAL_AGENT

    role_and_cls = f"{agent_cls} {role}".strip()
    combined = f"{name} {role_and_cls} {desc}".strip()

    has_awakened_in_role = any(rx.search(role_and_cls) for rx in _AWAKENED_RE)
    has_awakened_in_desc = any(rx.search(combined) for rx in _AWAKENED_RE)
    has_mundane_in_role = any(rx.search(role_and_cls) for rx in _MUNDANE_RE)

    # HQ quartermasters, clerks, regular police, security guards, street thugs -> Civilian unless explicitly Awakened
    if has_mundane_in_role:
        if re.search(r"\b(awakened|mana[-\s]wielder|special\s+agent|exorcist|esper|thaumaturge|ritualist)\b", role_and_cls, re.IGNORECASE):
            return TAG_SPECIAL_AGENT
        return TAG_CIVILIAN

    if has_awakened_in_role:
        return TAG_SPECIAL_AGENT

    # Description match only counts if it explicitly describes THE NPC as an operative/awakened (and not a mundane role)
    if has_awakened_in_desc and not any(rx.search(combined) for rx in _MUNDANE_RE):
        if re.search(
            r"\b(freelance\s+hunter|rogue\s+exorcist|awakened\s+operative|awakened\s+enforcer|mana[-\s]wielder|containment\s+specialist|special\s+agent)\b",
            combined,
            re.IGNORECASE,
        ):
            return TAG_SPECIAL_AGENT

    return TAG_CIVILIAN


def _infer_emergent_agent_faction_and_class(role_text: str, seed_val: int) -> Tuple[str, str, str, int]:
    """
    Deterministically infers `(faction_id, faction_name, agent_class, agent_tier)` for an
    emergent narrative Special Agent outside the 44 pre-seeded roster.
    """
    low = role_text.lower()
    tier = 2
    if any(k in low for k in ("commander", "director", "grand", "master", "arch", "chief", "veteran", "senior", "elite")):
        tier = 3 + (seed_val % 2)  # Tier 3 or 4
    elif any(k in low for k in ("junior", "rookie", "initiate", "novice", "apprentice", "probationary")):
        tier = 1
    else:
        tier = 1 + (seed_val % 2)  # Tier 1 or 2

    if any(k in low for k in ("cult", "covenant", "ritualist", "blood-weaver", "apostle", "heretic")):
        return ("cult_faction", "Obsidian Covenant", "Esoteric Ritualist", tier)
    if any(k in low for k in ("syndicate", "assassin", "black-market", "clandestine", "smuggler", "fixer", "enforcer")):
        return ("clandestine_faction", "Hollow Syndicate", "Relic Assassin", tier)
    if any(k in low for k in ("exorcist", "shrine", "monk", "monastic", "talisman", "onmyoji", "purifier", "ward")):
        return ("monastic_order", "Eastern Shrine Order", "Shinto Shrine Exorcist", tier)
    if any(k in low for k in ("marshal", "bureau", "directorate", "public containment", "federal")):
        return ("public_agency", "Public Containment Bureau", "Field Containment Agent", tier)
    if any(k in low for k in ("corporate", "contractor", "executive")):
        return ("private_agency_1", "Private Defense Syndicate", "Corporate Strike Contractor", tier)

    freelance_classes = [
        "Freelance Anomaly Hunter",
        "Street Ronin",
        "Rogue Exorcist",
        "Hex-Slinger",
        "Relic Hound",
    ]
    chosen_cls = freelance_classes[seed_val % len(freelance_classes)]
    return ("freelancer", "Independent Freelancer", chosen_cls, tier)


def resolve_special_agent_weapon_profile(faction_id: str, agent_class: str, agent_tier: int, seed_val: int = 0) -> Dict[str, Any]:
    """Returns a dedicated mana-resonant weapon profile for a Special Agent."""
    tier_clamped = max(1, min(5, int(agent_tier or 1)))
    atk_bonus = 6 + tier_clamped * 3
    matk_bonus = 5 + tier_clamped * 3
    cls_low = f"{faction_id} {agent_class}".lower()

    if "monastic" in cls_low or "exorcist" in cls_low or "shrine" in cls_low:
        return {
            "name": "Sanctified Shakujo & Ofuda Blade",
            "atk_bonus": atk_bonus,
            "matk_bonus": matk_bonus + 2,
            "damage_types": {"holy": 0.6, "slashing": 0.4},
            "mundane_weapon": False,
            "mana_infused": True,
        }
    if "cult" in cls_low or "ritual" in cls_low:
        return {
            "name": "Sacrificial Obsidian Athame",
            "atk_bonus": atk_bonus - 1,
            "matk_bonus": matk_bonus + 3,
            "damage_types": {"dark": 0.7, "piercing": 0.3},
            "mundane_weapon": False,
            "mana_infused": True,
        }
    if "clandestine" in cls_low or "assassin" in cls_low or "ronin" in cls_low:
        return {
            "name": "Phase-Edge Relic Wakizashi",
            "atk_bonus": atk_bonus + 2,
            "matk_bonus": matk_bonus,
            "damage_types": {"slashing": 0.6, "magical": 0.4},
            "mundane_weapon": False,
            "mana_infused": True,
        }
    if "private" in cls_low or "contractor" in cls_low or "sniper" in cls_low:
        return {
            "name": "Aether-Core Rail Carbine",
            "atk_bonus": atk_bonus + 2,
            "matk_bonus": matk_bonus + 1,
            "damage_types": {"piercing": 0.5, "shock": 0.5},
            "mundane_weapon": False,
            "mana_infused": True,
        }
    if "freelancer" in cls_low or "hex" in cls_low:
        return {
            "name": "Custom Rune-Etched Revolver",
            "atk_bonus": atk_bonus + 1,
            "matk_bonus": matk_bonus + 1,
            "damage_types": {"piercing": 0.5, "magical": 0.5},
            "mundane_weapon": False,
            "mana_infused": True,
        }
    return {
        "name": "Bureau Resonance Suppressor Sidearm",
        "atk_bonus": atk_bonus + 1,
        "matk_bonus": matk_bonus + 1,
        "damage_types": {"piercing": 0.5, "magical": 0.5},
        "mundane_weapon": False,
        "mana_infused": True,
    }


def resolve_civilian_weapon_profile(role_text: str, seed_str: str = "") -> Dict[str, Any]:
    """
    Assigns a mundane role-appropriate or improvised weapon when a Civilian is forced to fight.
    Civilians have 0 MP and lack mana infusion, so mundane weapons deal normal damage to humans
    and reduced chip damage against supernatural Anomalous Entities.
    """
    low = str(role_text or "").lower()
    h = _stable_hash(seed_str or low or "civilian")

    if any(k in low for k in ("police", "cop", "detective", "officer", "swat", "sheriff", "marshal")):
        return {
            "name": "Service Pistol",
            "atk_bonus": 6,
            "matk_bonus": 0,
            "damage_types": {"piercing": 1.0},
            "is_armed_role": True,
            "mundane_weapon": True,
            "mana_infused": False,
        }
    if any(k in low for k in ("security", "guard", "watchman", "bodyguard", "bouncer", "warden")):
        return {
            "name": "Tactical Baton",
            "atk_bonus": 5,
            "matk_bonus": 0,
            "damage_types": {"bludgeoning": 1.0},
            "is_armed_role": True,
            "mundane_weapon": True,
            "mana_infused": False,
        }
    if any(k in low for k in ("thug", "gang", "mugger", "delinquent", "hooligan", "enforcer", "grunt", "raider", "criminal")):
        if h % 2 == 0:
            return {
                "name": "Concealed Switchblade",
                "atk_bonus": 5,
                "matk_bonus": 0,
                "damage_types": {"slashing": 1.0},
                "is_armed_role": True,
                "mundane_weapon": True,
                "mana_infused": False,
            }
        return {
            "name": "Weighted Steel Pipe",
            "atk_bonus": 5,
            "matk_bonus": 0,
            "damage_types": {"bludgeoning": 1.0},
            "is_armed_role": True,
            "mundane_weapon": True,
            "mana_infused": False,
        }
    if any(k in low for k in ("chef", "cook", "butcher", "baker")):
        return {
            "name": "Kitchen Cleaver",
            "atk_bonus": 4,
            "matk_bonus": 0,
            "damage_types": {"slashing": 1.0},
            "is_armed_role": False,
            "mundane_weapon": True,
            "mana_infused": False,
        }
    if any(k in low for k in ("mechanic", "janitor", "custodian", "engineer", "worker", "dockworker")):
        return {
            "name": "Heavy Pipe Wrench",
            "atk_bonus": 4,
            "matk_bonus": 0,
            "damage_types": {"bludgeoning": 1.0},
            "is_armed_role": False,
            "mundane_weapon": True,
            "mana_infused": False,
        }
    if any(k in low for k in ("quartermaster", "armorer")):
        return {
            "name": "Depot Sidearm",
            "atk_bonus": 6,
            "matk_bonus": 0,
            "damage_types": {"piercing": 1.0},
            "is_armed_role": True,
            "mundane_weapon": True,
            "mana_infused": False,
        }

    improvised_pool = [
        ("Pepper Spray Canister", 2, {"bludgeoning": 1.0}),
        ("Improvised Metal Chair", 3, {"bludgeoning": 1.0}),
        ("Improvised Glass Bottle", 3, {"slashing": 1.0}),
        ("Desperate Unarmed Swings", 2, {"bludgeoning": 1.0}),
    ]
    w_name, w_atk, w_dmg = improvised_pool[h % len(improvised_pool)]
    return {
        "name": w_name,
        "atk_bonus": w_atk,
        "matk_bonus": 0,
        "damage_types": w_dmg,
        "is_armed_role": False,
        "mundane_weapon": True,
        "mana_infused": False,
    }


def compute_special_agent_combat_stats(
    agent_tier: int = 1,
    player_level: int = 1,
    agent_class: str = "",
    faction_id: str = "",
    is_party_companion: bool = False,
    seed_str: str = "",
) -> Dict[str, Any]:
    """
    Computes Tier-scaled dedicated HP, MP, 7-stat spread, and faction weapon for a Special Agent.
    - Tier 1 starts at 130 HP / 60 MP up to Tier 5 at 290 HP / 165 MP.
    - When recruited as a party companion, adds player-level scaling (+12 HP & +6 MP per level > 1).
    """
    tier_clamped = max(1, min(5, int(agent_tier or 1)))
    lvl_clamped = max(1, int(player_level or 1))
    base_hp, base_mp = SPECIAL_AGENT_TIER_VITALS.get(tier_clamped, (130, 60))

    if is_party_companion and lvl_clamped > 1:
        base_hp += (lvl_clamped - 1) * 12
        base_mp += (lvl_clamped - 1) * 6

    cls_low = str(agent_class or "").lower()
    if any(k in cls_low for k in ("exorcist", "ritual", "technomancer", "analyst", "forensics", "esper", "hex", "ward")):
        primary = ("INT", "PER", "CHA")
    elif any(k in cls_low for k in ("breacher", "vanguard", "brawler", "sentinel", "marshal")):
        primary = ("STR", "END", "AGI")
    elif any(k in cls_low for k in ("assassin", "ronin", "sniper", "hunter", "stalker", "hound")):
        primary = ("AGI", "PER", "STR")
    else:
        primary = ("PER", "AGI", "INT")

    base_floor = 3 + (tier_clamped // 2)
    stats: Dict[str, int] = {
        "STR": base_floor,
        "PER": base_floor,
        "END": base_floor,
        "CHA": base_floor,
        "INT": base_floor,
        "AGI": base_floor,
        "LUK": base_floor,
    }
    extra_budget = 6 + (tier_clamped * 4) + (max(0, lvl_clamped - 1) * 2 if is_party_companion else 0)
    rng = random.Random(_stable_hash(f"sa_stats:{seed_str}:{tier_clamped}:{agent_class}"))
    all_keys = ["STR", "PER", "END", "CHA", "INT", "AGI", "LUK"]
    weights = [4 if k in primary else 1 for k in all_keys]
    for _ in range(extra_budget):
        pick = rng.choices(all_keys, weights=weights, k=1)[0]
        stats[pick] = min(18, stats[pick] + 1)

    weapon = resolve_special_agent_weapon_profile(faction_id, agent_class, tier_clamped, _stable_hash(seed_str))
    effective_level = max(tier_clamped * 2 - 1, lvl_clamped if is_party_companion else 1)

    return {
        "hp": base_hp,
        "max_hp": base_hp,
        "mp": base_mp,
        "max_mp": base_mp,
        "level": effective_level,
        "stats": stats,
        "weapon_profile": weapon,
    }


def compute_civilian_combat_stats(role_text: str = "", seed_str: str = "") -> Dict[str, Any]:
    """
    Computes fixed Civilian vitals: strictly 100 HP, 0 MP, zero abilities, mundane stats,
    and a role-based mundane/improvised weapon.
    """
    weapon = resolve_civilian_weapon_profile(role_text, seed_str=seed_str)
    is_armed = bool(weapon.get("is_armed_role"))
    stats = {
        "STR": 4 if is_armed else 2,
        "PER": 4 if is_armed else 3,
        "END": 3 if is_armed else 2,
        "CHA": 3,
        "INT": 3,
        "AGI": 3 if is_armed else 2,
        "LUK": 3,
    }
    return {
        "hp": CIVILIAN_BASE_HP,
        "max_hp": CIVILIAN_BASE_HP,
        "mp": CIVILIAN_BASE_MP,
        "max_mp": CIVILIAN_BASE_MP,
        "level": 1,
        "stats": stats,
        "weapon_profile": weapon,
        "innate_abilities": [],
    }


def format_innate_ability_details(innate_abilities: List[Any]) -> List[Dict[str, Any]]:
    """Resolves spell IDs or dicts into rich UI/dossier metadata."""
    if not innate_abilities:
        return []
    from mechanics.combat.spells.registry import get_spell
    details: List[Dict[str, Any]] = []
    for item in innate_abilities:
        sp = get_spell(item) if isinstance(item, str) else (item if isinstance(item, dict) else None)
        if not isinstance(sp, dict):
            if isinstance(item, str) and item.strip():
                details.append({
                    "id": item,
                    "name": item.replace("_", " ").title(),
                    "emoji": "⚡",
                    "mp_cost": 8,
                    "tier": 3,
                    "tier_name": "Tactical",
                    "is_ultimate": False,
                    "description": "Innate anomalous field ability.",
                })
            continue
        tier_num = int(sp.get("tier", 3) or 3)
        is_ult = tier_num == 1 or "ultimate" in str(sp.get("name", "")).lower()
        details.append({
            "id": str(sp.get("id") or item),
            "name": str(sp.get("name") or item),
            "emoji": str(sp.get("emoji") or ("🌟" if is_ult else "⚡")),
            "mp_cost": int(sp.get("mp_cost", 8) or 8),
            "tier": tier_num,
            "tier_name": "Signature Ultimate" if is_ult else str(sp.get("tier_name") or "Tactical"),
            "discipline": str(sp.get("discipline") or "attack"),
            "target_type": str(sp.get("target_type") or "single"),
            "is_ultimate": is_ult,
            "description": str(sp.get("description") or ""),
        })
    return details


def hydrate_anomalous_npc_profile(
    entity: Dict[str, Any],
    session_id: int = 0,
    scen_key: str = "anomalous_incursions",
    player_level: int = 1,
    is_party_companion: bool = False,
) -> Dict[str, Any]:
    """
    Produces a complete normalized profile for any NPC in Anomalous Incursions,
    whether a pre-seeded Special Agent, an emergent Special Agent, or a Civilian.
    """
    name = str(entity.get("name") or entity.get("title") or "Unknown").strip()
    basic = _extract_basic_info(entity)
    tag = classify_anomalous_npc_tag(entity, session_id=session_id, scen_key=scen_key)
    role_text = str(
        entity.get("role")
        or entity.get("occupation")
        or basic.get("role")
        or basic.get("occupation")
        or ""
    ).strip()

    if tag == TAG_SPECIAL_AGENT:
        sp_agent = None
        if session_id and name:
            try:
                from mechanics.social.agent_roster import find_special_agent_by_name
                sp_agent = find_special_agent_by_name(session_id, name, scen_key=scen_key)
            except Exception:
                sp_agent = None

        seed_val = _stable_hash(f"{session_id}:{name.lower()}")
        inf_fid, inf_fname, inf_cls, inf_tier = _infer_emergent_agent_faction_and_class(
            f"{role_text} {basic.get('description', '')} {entity.get('description', '')}",
            seed_val,
        )

        faction_id = str(
            (sp_agent or {}).get("faction_id")
            or entity.get("faction_id")
            or basic.get("faction_id")
            or inf_fid
        ).strip()
        faction_name = str(
            (sp_agent or {}).get("faction_name")
            or entity.get("faction_name")
            or basic.get("faction")
            or inf_fname
        ).strip()
        agent_tier = int(
            (sp_agent or {}).get("agent_tier")
            or entity.get("agent_tier")
            or basic.get("agent_tier")
            or inf_tier
        )
        agent_class = str(
            (sp_agent or {}).get("agent_class")
            or entity.get("agent_class")
            or basic.get("agent_class")
            or inf_cls
        ).strip()
        rank_title = str(
            (sp_agent or {}).get("rank_title")
            or entity.get("rank_title")
            or basic.get("rank_title")
            or ("Independent Hunter" if faction_id == "freelancer" else f"Tier {agent_tier} Operative")
        ).strip()

        innate_abilities = list(
            (sp_agent or {}).get("innate_abilities")
            or entity.get("innate_abilities")
            or basic.get("innate_abilities")
            or []
        )
        if not innate_abilities:
            from mechanics.combat.spells import get_anomalous_starting_innate_abilities
            innate_abilities = get_anomalous_starting_innate_abilities(
                agent_class,
                scenario=scen_key or "anomalous_incursions",
                class_description=role_text,
                seed=f"{session_id}:{name.lower()}:{agent_class}",
            )

        combat_stats = compute_special_agent_combat_stats(
            agent_tier=agent_tier,
            player_level=player_level,
            agent_class=agent_class,
            faction_id=faction_id,
            is_party_companion=is_party_companion,
            seed_str=f"{session_id}:{name.lower()}",
        )
        return {
            "anomalous_npc_tag": TAG_SPECIAL_AGENT,
            "anomalous_tag_label": "Special Agent",
            "is_special_agent": True,
            "can_recruit_companion": True,
            "agent_tier": agent_tier,
            "rank_title": rank_title,
            "agent_class": agent_class,
            "faction_id": faction_id,
            "faction_name": faction_name,
            "innate_abilities": innate_abilities,
            "innate_ability_details": format_innate_ability_details(innate_abilities),
            **combat_stats,
        }

    # Civilian Branch
    civ_stats = compute_civilian_combat_stats(role_text=role_text, seed_str=f"{session_id}:{name.lower()}")
    return {
        "anomalous_npc_tag": TAG_CIVILIAN,
        "anomalous_tag_label": "Civilian",
        "is_special_agent": False,
        "can_recruit_companion": False,
        "agent_tier": 0,
        "rank_title": "Civilian",
        "agent_class": "Civilian",
        "faction_id": "",
        "faction_name": "",
        "innate_abilities": [],
        "innate_ability_details": [],
        **civ_stats,
    }


def is_supernatural_anomalous_entity(target: Dict[str, Any]) -> bool:
    """
    Returns True if a combatant is a supernatural Anomalous Entity (rather than a human
    Civilian or Special Agent). Used for:
    1. Civilian mundane weapon damage reduction (lack of mana infusion).
    2. Civilian permadeath trigger when slain by a hostile Anomalous Entity.
    """
    if not isinstance(target, dict):
        return False
    t_tag = str(target.get("anomalous_npc_tag") or "").strip().lower()
    if t_tag in (TAG_CIVILIAN, TAG_SPECIAL_AGENT) or target.get("is_human_npc"):
        return False
    if target.get("incursion_id") or target.get("category_tag") or target.get("requires_non_lethal_subdue"):
        return True

    name_low = str(target.get("name") or "").lower()
    arch_low = str(target.get("archetype") or "").lower()
    cats = [str(c).lower() for c in (target.get("categories") or [])]
    essence = str(target.get("essence") or "").lower()

    human_words = (
        "thug", "guard", "police", "cop", "officer", "agent", "operative", "mercenary",
        "bandit", "bouncer", "cultist", "enforcer", "grunt", "citizen", "civilian", "assassin",
    )
    if "humanoid" in cats and essence in ("biological", "mundane", ""):
        if any(w in name_low or w in arch_low for w in human_words):
            return False
    if any(w in name_low for w in ("street thug", "security guard", "police officer", "syndicate grunt")):
        return False

    return True


def is_civilian_forced_to_fight_as_ally(npc: Dict[str, Any], session: Optional[Dict[str, Any]] = None) -> bool:
    """
    Determines whether a friendly/neutral Civilian present in `current_npcs` fights alongside
    the player during combat (as a temporary non-party scene ally) vs. taking cover off-stage:
    - Armed mundane personnel (police, security guards, bodyguards, thugs) fight.
    - Explicitly cornered / forced civilians or active dialogue partners caught directly
      in an ambush fight in self-defense.
    - Unarmed background bystanders take cover unless targeted.
    """
    if not isinstance(npc, dict):
        return False
    basic = _extract_basic_info(npc)
    if basic.get("deceased") or npc.get("deceased") or npc.get("is_dead"):
        return False
    if npc.get("forced_to_fight") or npc.get("cornered"):
        return True

    role_text = str(npc.get("role") or npc.get("occupation") or basic.get("role") or basic.get("occupation") or "")
    weapon = npc.get("weapon_profile") or resolve_civilian_weapon_profile(role_text, seed_str=str(npc.get("name") or ""))
    if weapon.get("is_armed_role"):
        return True

    # If the player was actively conversing with this contact right when an ambush/incursion erupted, they are cornered with the player
    if isinstance(session, dict):
        dps: set[str] = set()
        for dp_key in ("dialogue_partner", "active_dialogue_partner", "dialogue_partners"):
            raw_dp = session.get(dp_key)
            if isinstance(raw_dp, str) and raw_dp.strip():
                for part in raw_dp.split(","):
                    if part.strip():
                        dps.add(part.strip().lower())
            elif isinstance(raw_dp, list):
                for part in raw_dp:
                    if part and str(part).strip():
                        dps.add(str(part).strip().lower())
        try:
            from game_engine.npcs import get_session_dialogue_partners
            for p in (get_session_dialogue_partners(session) or []):
                if p and str(p).strip():
                    dps.add(str(p).strip().lower())
        except Exception:
            pass
        n_name = str(npc.get("name") or "").strip().lower()
        if n_name and n_name in dps:
            return True
    return False


def build_anomalous_human_combatant_enemy(
    entity: Dict[str, Any],
    session_id: int = 0,
    scen_key: str = "anomalous_incursions",
) -> Dict[str, Any]:
    """
    Hydrates a hostile human NPC (either a provoked/hostile Civilian or a rival Special Agent)
    into a deterministic combat enemy statblock for `nearby_enemies`.
    """
    prof = hydrate_anomalous_npc_profile(
        entity,
        session_id=session_id,
        scen_key=scen_key,
        player_level=1,
        is_party_companion=False,
    )
    name = str(entity.get("name") or "Hostile Individual").strip()
    tag = prof["anomalous_npc_tag"]
    weapon = prof["weapon_profile"]

    if tag == TAG_SPECIAL_AGENT:
        tier = int(prof.get("agent_tier", 2) or 2)
        return {
            "name": name,
            "archetype": prof.get("agent_class") or "Special Agent",
            "level": prof["level"],
            "tier_rank": max(2, min(5, tier)),
            "hp": prof["hp"],
            "max_hp": prof["max_hp"],
            "mp": prof["mp"],
            "max_mp": prof["max_mp"],
            "stats": prof["stats"],
            "anomalous_npc_tag": TAG_SPECIAL_AGENT,
            "is_special_agent": True,
            "is_human_npc": True,
            "agent_tier": tier,
            "agent_class": prof.get("agent_class", "Special Agent"),
            "faction_id": prof.get("faction_id", ""),
            "faction_name": prof.get("faction_name", ""),
            "innate_abilities": prof.get("innate_abilities", []),
            "weapon_profile": weapon,
            "intent": f"Channeling anomalous resonance through {weapon['name']}",
            "status_effects": list(entity.get("status_effects") or []),
            "weaknesses": [],
            "resistances": ["magical"] if tier >= 3 else [],
            "immunities": [],
            "affixes": [],
        }

    return {
        "name": name,
        "archetype": "Civilian Combatant",
        "level": 1,
        "tier_rank": 1,
        "hp": CIVILIAN_BASE_HP,
        "max_hp": CIVILIAN_BASE_HP,
        "mp": CIVILIAN_BASE_MP,
        "max_mp": CIVILIAN_BASE_MP,
        "stats": prof["stats"],
        "anomalous_npc_tag": TAG_CIVILIAN,
        "is_special_agent": False,
        "is_human_npc": True,
        "innate_abilities": [],
        "weapon_profile": weapon,
        "intent": f"Brandishing {weapon['name']} in mundane combat",
        "status_effects": list(entity.get("status_effects") or []),
        "weaknesses": [],
        "resistances": [],
        "immunities": [],
        "affixes": [],
    }


def apply_civilian_permadeath(
    session_id: int,
    session: Optional[Dict[str, Any]],
    npc_name: Any,
    killer_name: str = "anomalous entity",
) -> Dict[str, Any]:
    """
    Executes permanent death for a friendly Civilian slain by a hostile Anomalous Entity
    (due to lacking a mana barrier):
    1. Marks `deceased: True` and `status_effects: ["Deceased"]` in `contacts` (preserving memorial record).
    2. Updates `lorebook` (`person`) status/description with permanent death record.
    3. Removes the slain Civilian from `session["current_npcs"]` and `db.update_session_npcs`.
    """
    if isinstance(npc_name, dict):
        if classify_anomalous_npc_tag(npc_name, session_id=session_id) == TAG_SPECIAL_AGENT:
            return {"deceased": False, "permadeath": False}
        clean_name = str(npc_name.get("name") or "").strip()
    else:
        clean_name = str(npc_name or "").strip()
        if clean_name and classify_anomalous_npc_tag(clean_name, session_id=session_id) == TAG_SPECIAL_AGENT:
            return {"deceased": False, "permadeath": False}
    if not clean_name:
        return {"deceased": False, "permadeath": False}

    if session_id:
        try:
            with db.get_conn() as conn:
                rows = conn.execute(
                    "SELECT id, basic_info_json FROM contacts WHERE session_id=? AND LOWER(name)=LOWER(?)",
                    (session_id, clean_name),
                ).fetchall()
                for r in rows:
                    try:
                        b_info = json.loads(r["basic_info_json"] or "{}")
                    except Exception:
                        b_info = {}
                    if not isinstance(b_info, dict):
                        b_info = {}
                    b_info["anomalous_npc_tag"] = TAG_CIVILIAN
                    b_info["deceased"] = True
                    b_info["cause_of_death"] = f"Slain by {killer_name} (unprotected civilian — no mana barrier)"
                    b_info["status_effects"] = ["Deceased"]
                    conn.execute(
                        "UPDATE contacts SET basic_info_json=? WHERE id=?",
                        (json.dumps(b_info), r["id"]),
                    )
        except Exception:
            pass

        try:
            lore_ent = db.get_lorebook_entity(session_id, clean_name)
            prev_desc = str((lore_ent or {}).get("description") or "Civilian resident.").strip()
            death_note = f" [DECEASED: Slain by {killer_name} during an anomalous incursion.]"
            if "[DECEASED:" not in prev_desc:
                prev_desc = f"{prev_desc}{death_note}"
            db.upsert_lorebook_entity(
                session_id=session_id,
                entity_type="person",
                name=clean_name,
                description=prev_desc,
                disposition="dead",
            )
        except Exception:
            pass

    if isinstance(session, dict):
        curr = session.get("current_npcs") or []
        filtered = [
            n for n in curr
            if (str(n.get("name") or "") if isinstance(n, dict) else str(n)).strip().lower() != clean_name.lower()
        ]
        session["current_npcs"] = filtered
        if session_id:
            try:
                db.update_session_npcs(session_id, filtered)
            except Exception:
                pass

    return {
        "deceased": True,
        "npc_name": clean_name,
        "killer_name": killer_name,
    }


def resolve_anomalous_ally_combat_action(
    comp: Dict[str, Any],
    living_enemies: List[Dict[str, Any]],
    living_allies: List[Dict[str, Any]],
    current_npcs: List[Dict[str, Any]],
    apply_damage_fn: Any,
    combat_log: List[str],
    rng: Optional[random.Random] = None,
) -> None:
    """
    Executes a Phase 2 combat action for an Anomalous Incursions ally:
    - `special_agent`: Actively spends MP to cast tactical abilities (heals, wards, debuffs,
      shikigami summons, elemental strikes) and their Signature Ultimate, or falls back to
      their mana-infused faction weapon.
    - `civilian`: Uses strictly their role-based mundane/improvised weapon (0 MP, no abilities),
      dealing normal damage to humans and reduced chip damage (0.45x) against supernatural Anomalous Entities.
    """
    if not living_enemies:
        return
    r = rng or random
    comp_name = str(comp.get("name") or "Ally")
    tag = str(comp.get("anomalous_npc_tag") or (TAG_SPECIAL_AGENT if comp.get("is_special_agent") else TAG_CIVILIAN)).lower()
    comp_stats = comp.get("stats") if isinstance(comp.get("stats"), dict) else {}

    # --- BRANCH A: CIVILIAN (Weapon-Only, 0 MP, Reduced Chip vs Supernatural Anomalies) ---
    if tag == TAG_CIVILIAN:
        target_m = r.choice(living_enemies)
        role_txt = str(comp.get("role") or "")
        weapon = comp.get("weapon_profile") or resolve_civilian_weapon_profile(role_txt, seed_str=comp_name)
        w_name = str(weapon.get("name") or "Improvised Object")
        w_atk = int(weapon.get("atk_bonus", 3) or 3)
        stat_val = max(comp_stats.get("STR", 2), comp_stats.get("PER", 3), comp_stats.get("AGI", 2))
        m_def = int((target_m.get("stats") or {}).get("END", 3) or 3)

        hit_chance = max(25, min(85, 52 + (stat_val - m_def) * 6))
        if r.randint(1, 100) <= hit_chance:
            raw_dmg = r.randint(8, 14) + w_atk + stat_val
            if is_supernatural_anomalous_entity(target_m):
                civ_dmg = max(2, min(10, int(round(raw_dmg * 0.42))))
                civ_dmg = min(target_m.get("hp", 100), civ_dmg)
                apply_damage_fn(target_m, civ_dmg)
                combat_log.append(
                    f"🔫 **{comp_name}** (*Civilian — {w_name}*) struck **{target_m['name']}**: "
                    f"Dealt **{civ_dmg} chip damage** *(mundane weapon — lacks mana infusion vs. anomaly)*."
                )
            else:
                civ_dmg = max(5, min(target_m.get("hp", 100), raw_dmg))
                apply_damage_fn(target_m, civ_dmg)
                combat_log.append(
                    f"🔫 **{comp_name}** (*Civilian — {w_name}*) attacked **{target_m['name']}**: Dealt **{civ_dmg} damage**."
                )
        else:
            combat_log.append(
                f"💨 **{comp_name}** (*Civilian — {w_name}*) swung at **{target_m['name']}**, but failed to connect."
            )
        return

    # --- BRANCH B: SPECIAL AGENT (MP-Driven Innate Abilities + Mana-Infused Weapon) ---
    from mechanics.combat.spells.registry import get_spell
    cur_mp = int(comp.get("mp", 0) or 0)
    agent_tier = max(1, int(comp.get("agent_tier", 1) or 1))
    raw_abilities = list(comp.get("innate_abilities") or [])
    resolved_spells = []
    for ab in raw_abilities:
        sp = get_spell(ab) if isinstance(ab, str) else (ab if isinstance(ab, dict) else None)
        if isinstance(sp, dict):
            resolved_spells.append(sp)

    # 1. Check Emergency Heal if an ally is < 55% HP
    wounded_allies = [
        a for a in living_allies
        if a.get("hp", 0) > 0 and (a.get("hp", 100) / max(1, a.get("max_hp", 100))) < 0.55
    ]
    heal_spells = [s for s in resolved_spells if int(s.get("heal_amount", 0) or 0) > 0 and cur_mp >= int(s.get("mp_cost", 8))]
    if wounded_allies and heal_spells:
        sp = heal_spells[0]
        cost = int(sp.get("mp_cost", 8))
        comp["mp"] = max(0, cur_mp - cost)
        heal_target = min(wounded_allies, key=lambda a: a.get("hp", 100) / max(1, a.get("max_hp", 100)))
        heal_amt = int(sp.get("heal_amount", 28)) + agent_tier * 4
        t_max = int(heal_target.get("max_hp", 100))
        heal_target["hp"] = min(t_max, int(heal_target.get("hp", 1)) + heal_amt)
        combat_log.append(
            f"{sp.get('emoji', '💚')} **{comp_name}** cast **{sp['name']}** (-{cost} MP), restoring **+{heal_amt} HP** to **{heal_target.get('name', 'Ally')}**!"
        )
        return

    # 2. Check Signature Ultimate (Tier 1 spell) when fighting an Elite/Boss or wounded
    ult_spells = [
        s for s in resolved_spells
        if (int(s.get("tier", 3) or 3) == 1 or "ultimate" in str(s.get("name", "")).lower())
        and cur_mp >= int(s.get("mp_cost", 28))
    ]
    high_threat = any(int(e.get("tier_rank", 2) or 2) >= 3 or int(e.get("hp", 0)) >= 110 for e in living_enemies)
    self_low = (comp.get("hp", 100) / max(1, comp.get("max_hp", 100))) <= 0.50
    if ult_spells and not comp.get("_used_ultimate_this_combat") and (high_threat or self_low):
        sp = ult_spells[0]
        cost = int(sp.get("mp_cost", 28))
        comp["mp"] = max(0, cur_mp - cost)
        comp["_used_ultimate_this_combat"] = True
        p_mult = float(sp.get("power_mult", 3.0) or 3.0)
        int_stat = max(comp_stats.get("INT", 5), comp_stats.get("PER", 5), comp_stats.get("STR", 5))
        base_power = 18 + agent_tier * 6 + int_stat * 2
        targets = list(living_enemies) if sp.get("target_type") == "aoe" else [max(living_enemies, key=lambda e: e.get("hp", 0))]
        total_dealt = 0
        hit_names = []
        for tm in targets:
            if tm.get("hp", 0) <= 0:
                continue
            dmg = max(18, min(tm.get("hp", 100), int(round(base_power * p_mult * (0.75 if len(targets) > 1 else 1.0)))))
            apply_damage_fn(tm, dmg)
            total_dealt += dmg
            hit_names.append(f"{tm['name']} ({dmg} dmg)")
            if sp.get("status_ailment"):
                tm.setdefault("status_effects", []).append(f"{sp['status_ailment']} [2 turns]")
        if "vampiric" in (sp.get("affixes") or []) and total_dealt > 0:
            leech = max(4, int(total_dealt * 0.25))
            comp["hp"] = min(comp.get("max_hp", 130), comp.get("hp", 1) + leech)
        combat_log.append(
            f"{sp.get('emoji', '🌟')} **{comp_name}** unleashed Signature Ultimate **{sp['name']}** (-{cost} MP) -> {', '.join(hit_names)}!"
        )
        return

    # 3. Tactical Ability Cast (Tier 2 / Tier 3 offensive, curse, ward, or summon)
    tactical_spells = [
        s for s in resolved_spells
        if int(s.get("tier", 3) or 3) > 1
        and int(s.get("heal_amount", 0) or 0) == 0
        and cur_mp >= int(s.get("mp_cost", 6))
    ]
    if tactical_spells and r.random() < 0.72:
        sp = r.choice(tactical_spells)
        cost = int(sp.get("mp_cost", 6))
        disc = str(sp.get("discipline") or "attack")
        comp["mp"] = max(0, cur_mp - cost)

        if disc == "summon":
            has_summon = any(n.get("is_summon") and n.get("summoner") == comp_name for n in current_npcs)
            if not has_summon:
                hound_hp = 35 + agent_tier * 10
                current_npcs.append({
                    "name": f"{comp_name.split()[0]}'s Shikigami Hound",
                    "role": "Shikigami Construct",
                    "archetype": "Stalker",
                    "level": max(1, agent_tier * 2),
                    "hp": hound_hp,
                    "max_hp": hound_hp,
                    "is_summon": True,
                    "summoner": comp_name,
                    "summon_duration": int(sp.get("summon_duration", 3) or 3),
                    "stats": {"STR": 4 + agent_tier, "AGI": 5 + agent_tier, "PER": 5, "END": 3, "INT": 3, "CHA": 1, "LUK": 4},
                })
                combat_log.append(
                    f"{sp.get('emoji', '🐺')} **{comp_name}** cast **{sp['name']}** (-{cost} MP), conjuring a Shikigami Hound into the fray!"
                )
                return

        if disc == "support" and sp.get("buff_pct"):
            for ally in living_allies:
                if ally.get("hp", 0) > 0:
                    ally["temp_hp"] = max(int(ally.get("temp_hp", 0) or 0), 10 + agent_tier * 4)
            combat_log.append(
                f"{sp.get('emoji', '🛡️')} **{comp_name}** deployed **{sp['name']}** (-{cost} MP), projecting a protective containment ward over the party!"
            )
            return

        if disc == "curse":
            target_m = max(living_enemies, key=lambda e: e.get("hp", 0))
            eff = "Weakened [-20% ATK] [2 turns]"
            if eff not in (target_m.get("status_effects") or []):
                target_m.setdefault("status_effects", []).append(eff)
            chip = max(6, min(target_m.get("hp", 100), 8 + agent_tier * 3))
            apply_damage_fn(target_m, chip)
            combat_log.append(
                f"{sp.get('emoji', '🧠')} **{comp_name}** cast **{sp['name']}** (-{cost} MP) on **{target_m['name']}**: Dealt **{chip} damage** and suppressed its attack power!"
            )
            return

        # Offensive single/AoE spell
        p_mult = float(sp.get("power_mult", 1.35) or 1.35)
        int_stat = max(comp_stats.get("INT", 5), comp_stats.get("PER", 5), comp_stats.get("AGI", 5))
        base_power = 12 + agent_tier * 5 + int_stat * 2
        targets = list(living_enemies) if sp.get("target_type") == "aoe" else [r.choice(living_enemies)]
        hit_parts = []
        total_dealt = 0
        for tm in targets:
            if tm.get("hp", 0) <= 0:
                continue
            dmg = max(10, min(tm.get("hp", 100), int(round(base_power * p_mult * (0.75 if len(targets) > 1 else 1.0)))))
            apply_damage_fn(tm, dmg)
            total_dealt += dmg
            hit_parts.append(f"**{tm['name']}** (**{dmg} damage**)")
            if sp.get("status_ailment"):
                tm.setdefault("status_effects", []).append(f"{sp['status_ailment']} [2 turns]")
        if "vampiric" in (sp.get("affixes") or []) and total_dealt > 0:
            comp["hp"] = min(comp.get("max_hp", 130), comp.get("hp", 1) + max(3, int(total_dealt * 0.25)))
        if hit_parts:
            combat_log.append(
                f"{sp.get('emoji', '⚡')} **{comp_name}** cast **{sp['name']}** (-{cost} MP) -> {', '.join(hit_parts)}."
            )
            return

    # 4. Mana-Infused Faction Weapon Fallback (when conserving or out of MP)
    target_m = r.choice(living_enemies)
    weapon = comp.get("weapon_profile") or resolve_special_agent_weapon_profile(
        str(comp.get("faction_id") or ""),
        str(comp.get("agent_class") or ""),
        agent_tier,
    )
    w_name = str(weapon.get("name") or "Resonance Weapon")
    best_stat = max(["STR", "AGI", "INT", "PER"], key=lambda s: comp_stats.get(s, 5))
    stat_val = int(comp_stats.get(best_stat, 5))
    m_def = int((target_m.get("stats") or {}).get("END", 3) or 3)
    hit_chance = max(35, min(92, 62 + (stat_val - m_def) * 6))
    if r.randint(1, 100) <= hit_chance:
        dmg = max(10, min(target_m.get("hp", 100), r.randint(10, 18) + int(weapon.get("atk_bonus", 8)) + stat_val))
        apply_damage_fn(target_m, dmg)
        combat_log.append(
            f"⚔️ **{comp_name}** struck **{target_m['name']}** with **{w_name}**: Dealt **{dmg} damage**."
        )
    else:
        combat_log.append(
            f"⚔️ **{comp_name}** attacked **{target_m['name']}** with **{w_name}**, but it was deflected."
        )


def resolve_hostile_special_agent_ability_modifier(
    enemy: Dict[str, Any],
    combat_log: List[str],
    rng: Optional[random.Random] = None,
) -> Optional[Dict[str, Any]]:
    """
    Allows a hostile Special Agent in `nearby_enemies` to spend MP on their innate abilities
    or Signature Ultimate during Phase 3 enemy counter-attacks.
    Returns an optional spell override dict `{"spell": sp, "damage_mult": float}` or heals/buffs directly.
    """
    if str(enemy.get("anomalous_npc_tag") or "").lower() != TAG_SPECIAL_AGENT:
        return None
    cur_mp = int(enemy.get("mp", 0) or 0)
    if cur_mp <= 0:
        return None

    from mechanics.combat.spells.registry import get_spell
    r = rng or random
    resolved = []
    for ab in (enemy.get("innate_abilities") or []):
        sp = get_spell(ab) if isinstance(ab, str) else (ab if isinstance(ab, dict) else None)
        if isinstance(sp, dict) and cur_mp >= int(sp.get("mp_cost", 6)):
            resolved.append(sp)
    if not resolved:
        return None

    hp_ratio = enemy.get("hp", 100) / max(1, enemy.get("max_hp", 100))
    # Emergency self-heal
    heals = [s for s in resolved if int(s.get("heal_amount", 0) or 0) > 0]
    if hp_ratio < 0.45 and heals and r.random() < 0.65:
        sp = heals[0]
        cost = int(sp.get("mp_cost", 8))
        enemy["mp"] = max(0, cur_mp - cost)
        heal_amt = int(sp.get("heal_amount", 28)) + int(enemy.get("agent_tier", 2)) * 4
        enemy["hp"] = min(enemy.get("max_hp", 150), enemy.get("hp", 1) + heal_amt)
        combat_log.append(
            f"{sp.get('emoji', '💚')} **{enemy['name']}** cast **{sp['name']}** (-{cost} MP), restoring **+{heal_amt} HP**!"
        )
        return {"skip_attack": True}

    # Signature Ultimate when wounded <= 55% HP
    ults = [s for s in resolved if int(s.get("tier", 3) or 3) == 1]
    if hp_ratio <= 0.55 and ults and not enemy.get("_used_ultimate_this_combat"):
        sp = ults[0]
        cost = int(sp.get("mp_cost", 28))
        enemy["mp"] = max(0, cur_mp - cost)
        enemy["_used_ultimate_this_combat"] = True
        return {"spell": sp, "damage_mult": 1.65, "is_ultimate": True, "cost": cost}

    # Tactical offensive ability (60% chance)
    attacks = [s for s in resolved if int(s.get("tier", 3) or 3) > 1 and sp_is_offensive(s)]
    if attacks and r.random() < 0.60:
        sp = r.choice(attacks)
        cost = int(sp.get("mp_cost", 6))
        enemy["mp"] = max(0, cur_mp - cost)
        return {"spell": sp, "damage_mult": 1.25, "is_ultimate": False, "cost": cost}

    return None


def sp_is_offensive(sp: Dict[str, Any]) -> bool:
    return str(sp.get("discipline") or "attack") in ("attack", "curse")
