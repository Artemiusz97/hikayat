"""
Reputation-Driven 4-Tier Spirit Court Perks & Stackable 90+ Sworn Ally Native Summons.

Cohesive domain module for:
- `SPIRIT_COURT_SWORN_ALLY_SPECS`: Stackable passive stat boosts & native 3-turn summons at rep >= 90
- `SPIRIT_COURT_SUMMON_SPELLS` & `SPIRIT_COURT_SUMMON_TEMPLATES`
- `get_spirit_court_active_perks`: Drives `get_active_perks()` directly from `reputation_score` (`player_rank == 0`)
- Live rep >= 90 gating (`get_spirit_court_stat_bonuses`, `get_active_spirit_court_summon_spell_ids`, etc.)
  so perks and summons auto-deactivate immediately whenever court standing drops < 90.
"""
from __future__ import annotations

from typing import Any, Mapping

SPIRIT_COURT_VILLAGE_KEYS: tuple[str, ...] = ("kitsune", "bunian", "ghoul")

SPIRIT_COURT_FACTION_ID_BY_VILLAGE: dict[str, str] = {
    "kitsune": "faction_spirit_kitsune",
    "bunian": "faction_spirit_bunian",
    "ghoul": "faction_spirit_ghoul",
}

SPIRIT_COURT_VILLAGE_BY_FACTION_ID: dict[str, str] = {v: k for k, v in SPIRIT_COURT_FACTION_ID_BY_VILLAGE.items()}
SPIRIT_COURT_SWORN_ALLY_THRESHOLD: int = 90

SPIRIT_COURT_STAT_COL_MAP: dict[str, str] = {
    "STR": "str_", "PER": "per_", "END": "end_", "CHA": "cha", "INT": "int_", "AGI": "agi", "LUK": "luk",
}

SPIRIT_COURT_SWORN_ALLY_SPECS: dict[str, dict[str, Any]] = {
    "kitsune": {
        "faction_id": "faction_spirit_kitsune", "stat_bonuses": {"INT": 2, "PER": 1},
        "spell_id": "spirit_summon_myobu_fox", "spell_name": "Summon Myōbu Fox-Spirit",
        "role_label": "Caster/Striker", "duration": 3, "summon_template": "myobu_fox_spirit", "emoji": "🦊",
    },
    "bunian": {
        "faction_id": "faction_spirit_bunian", "stat_bonuses": {"AGI": 2, "CHA": 1},
        "spell_id": "spirit_summon_kayangan_guardian", "spell_name": "Summon Kayangan Mist-Guardian",
        "role_label": "Healer/Support", "duration": 3, "summon_template": "kayangan_mist_guardian", "emoji": "🌺",
    },
    "ghoul": {
        "faction_id": "faction_spirit_ghoul", "stat_bonuses": {"STR": 2, "END": 1},
        "spell_id": "spirit_summon_mirage_canid", "spell_name": "Summon Mirage Pack Canid",
        "role_label": "Bruiser/Skirmisher", "duration": 3, "summon_template": "mirage_pack_canid", "emoji": "🐺",
    },
}

SPIRIT_COURT_SUMMON_SPELLS: dict[str, dict[str, Any]] = {
    "spirit_summon_myobu_fox": {
        "id": "spirit_summon_myobu_fox", "name": "Summon Myōbu Fox-Spirit", "emoji": "🦊",
        "school": "Conjuration", "discipline": "summon", "damage_type": "fire", "element": "fire",
        "tier": 2, "tier_name": "Sworn Ally", "target_type": "summon", "mp_cost": 14,
        "stat": "INT", "requirement": 8, "summon_template": "myobu_fox_spirit",
        "summon_count": 1, "summon_duration": 3, "duration": 3, "summon_archetype": "Caster",
        "spirit_court": "kitsune",
        "description": "Invokes a consecrated Myōbu Fox-Spirit (Caster/Striker) from the Kitsune Shrine Court for 3 combat turns to sear enemies with azure fox-fire.",
    },
    "spirit_summon_kayangan_guardian": {
        "id": "spirit_summon_kayangan_guardian", "name": "Summon Kayangan Mist-Guardian", "emoji": "🌺",
        "school": "Conjuration", "discipline": "summon", "damage_type": "aether", "element": "aether",
        "tier": 2, "tier_name": "Sworn Ally", "target_type": "summon", "mp_cost": 14,
        "stat": "CHA", "requirement": 8, "summon_template": "kayangan_mist_guardian",
        "summon_count": 1, "summon_duration": 3, "duration": 3, "summon_archetype": "Support",
        "spirit_court": "bunian",
        "description": "Calls forth a Kayangan Mist-Guardian (Healer/Support) of the Royal Bunian Sanctuary for 3 combat turns to mend wounded allies and ward the line.",
    },
    "spirit_summon_mirage_canid": {
        "id": "spirit_summon_mirage_canid", "name": "Summon Mirage Pack Canid", "emoji": "🐺",
        "school": "Conjuration", "discipline": "summon", "damage_type": "physical", "element": "physical",
        "tier": 2, "tier_name": "Sworn Ally", "target_type": "summon", "mp_cost": 14,
        "stat": "STR", "requirement": 8, "summon_template": "mirage_pack_canid",
        "summon_count": 1, "summon_duration": 3, "duration": 3, "summon_archetype": "Bruiser",
        "spirit_court": "ghoul",
        "description": "Summons an ash-furred Mirage Pack Canid (Bruiser/Skirmisher) bound by Pale Ossuary oath for 3 combat turns to harry and rend foes.",
    },
}

SPIRIT_COURT_SUMMON_TEMPLATES: dict[str, dict[str, Any]] = {
    "myobu_fox_spirit": {
        "name": "Myōbu Fox-Spirit", "archetype": "Caster", "combat_role": "Caster/Striker",
        "count": 1, "duration": 3, "hp_per_level": 6, "base_hp": 26, "max_mp": 42,
        "attack_type": "ranged", "damage_type": "fire", "element": "fire", "spirit_court": "kitsune",
        "stat_weights": {"STR": 4, "AGI": 9, "INT": 12, "PER": 10, "END": 6, "CHA": 8, "LUK": 6},
        "description": "Kitsune celestial messenger channeling azure fox-fire bolts.",
        "combat_loadout": [
            {"id": "kitsunebi_bolt", "slot": 1, "name": "Azure Kitsunebi Bolt", "category": "attack", "intent_code": "magic", "mana_cost": 0, "cooldown": 0, "damage_mult": 1.20, "damage_type": "fire", "uses_matk": True, "armor_penetration": 0.15, "target_type": "single_enemy"},
            {"id": "fox_illusive_step", "slot": 2, "name": "Shrine Mirage Feint", "category": "tactical", "intent_code": "magic", "mana_cost": 0, "cooldown": 2, "damage_mult": 1.05, "damage_type": "fire", "uses_matk": True, "status_ailment": "Demoralized [-15% ATK] [2 turns]", "target_type": "single_enemy"},
            {"id": "nine_fold_foxfire", "slot": 3, "name": "Nine-Fold Foxfire Barrage", "category": "attack", "intent_code": "magic", "mana_cost": 10, "cooldown": 2, "damage_mult": 1.55, "damage_type": "fire", "uses_matk": True, "armor_penetration": 0.20, "status_ailment": "Burning [2 turns]", "target_type": "single_enemy"},
        ],
    },
    "kayangan_mist_guardian": {
        "name": "Kayangan Mist-Guardian", "archetype": "Support", "combat_role": "Healer/Support",
        "count": 1, "duration": 3, "hp_per_level": 7, "base_hp": 32, "max_mp": 48,
        "attack_type": "ranged", "damage_type": "aether", "element": "aether", "spirit_court": "bunian",
        "stat_weights": {"STR": 5, "AGI": 10, "INT": 10, "PER": 9, "END": 8, "CHA": 12, "LUK": 6},
        "description": "Luminescent Bunian mist-warden mending wounded allies with Kayangan dew.",
        "combat_loadout": [
            {"id": "cempaka_veil_strike", "slot": 1, "name": "Cempaka Wind-Veil Strike", "category": "attack", "intent_code": "magic", "mana_cost": 0, "cooldown": 0, "damage_mult": 0.95, "damage_type": "aether", "uses_matk": True, "target_type": "single_enemy"},
            {"id": "kayangan_dew_mend", "slot": 2, "name": "Kayangan Mist-Dew Mend", "category": "support", "intent_code": "defensive", "mana_cost": 6, "cooldown": 1, "damage_mult": 0.0, "damage_type": "holy", "heal_amount": 28, "target_type": "ally"},
            {"id": "seri_mist_sanctuary", "slot": 3, "name": "Seri Mist Sanctuary", "category": "support", "intent_code": "defensive", "mana_cost": 10, "cooldown": 2, "damage_mult": 0.0, "damage_type": "holy", "heal_amount": 36, "status_ailment": "Fortified [+4 DT]", "target_type": "ally"},
        ],
    },
    "mirage_pack_canid": {
        "name": "Mirage Pack Canid", "archetype": "Bruiser", "combat_role": "Bruiser/Skirmisher",
        "count": 1, "duration": 3, "hp_per_level": 8, "base_hp": 36, "max_mp": 24,
        "attack_type": "slash", "damage_type": "physical", "element": "physical", "spirit_court": "ghoul",
        "stat_weights": {"STR": 12, "AGI": 10, "INT": 5, "PER": 9, "END": 11, "CHA": 4, "LUK": 5},
        "description": "Lean ash-maned Ossuary hound tearing through defenses in three furious bounds.",
        "combat_loadout": [
            {"id": "ashen_fang_lunge", "slot": 1, "name": "Ashen Fang Lunge", "category": "attack", "intent_code": "basic", "mana_cost": 0, "cooldown": 0, "damage_mult": 1.25, "damage_type": "physical", "armor_penetration": 0.15, "target_type": "single_enemy"},
            {"id": "ossuary_flank_snap", "slot": 2, "name": "Marrow-Hound Hamstring", "category": "attack", "intent_code": "heavy", "mana_cost": 0, "cooldown": 2, "damage_mult": 1.35, "damage_type": "physical", "armor_penetration": 0.25, "status_ailment": "Exposed [2 turns]", "target_type": "single_enemy"},
            {"id": "ossuary_pack_rend", "slot": 3, "name": "Ossuary Pack Rend", "category": "attack", "intent_code": "heavy", "mana_cost": 8, "cooldown": 2, "damage_mult": 1.55, "damage_type": "physical", "armor_penetration": 0.30, "status_ailment": "Bleeding [2 turns]", "target_type": "single_enemy"},
        ],
    },
}


def resolve_village_key_for_spirit_faction(faction_or_vk: Mapping[str, Any] | str | None) -> str:
    """Resolves `'kitsune'`, `'bunian'`, or `'ghoul'` from a village key or faction dict/ID."""
    if isinstance(faction_or_vk, str):
        low = faction_or_vk.strip().lower()
        return low if low in SPIRIT_COURT_VILLAGE_KEYS else SPIRIT_COURT_VILLAGE_BY_FACTION_ID.get(low, "")
    if isinstance(faction_or_vk, Mapping):
        fid = str(faction_or_vk.get("faction_id") or "").strip().lower()
        if fid in SPIRIT_COURT_VILLAGE_BY_FACTION_ID:
            return SPIRIT_COURT_VILLAGE_BY_FACTION_ID[fid]
        vk = str(faction_or_vk.get("village_key") or "").strip().lower()
        if vk in SPIRIT_COURT_VILLAGE_KEYS:
            return vk
        name_low = str(faction_or_vk.get("name") or "").strip().lower()
        for key in SPIRIT_COURT_VILLAGE_KEYS:
            if key in name_low:
                return key
    return ""


def get_spirit_court_standing_tier_boost(standing: int) -> float:
    """Returns spawn weight bonus for higher-tier themed items (+25% at 25+, +45% at 50+)."""
    score = int(standing or 0)
    if score >= 50:
        return 0.45
    if score >= 25:
        return 0.25
    return 0.0


def get_spirit_court_active_perks(
    faction_or_vk: Mapping[str, Any] | str,
    reputation_score: int | None = None,
) -> list[str]:
    """
    Returns active 4-tier Spirit Court perk descriptions driven directly by `reputation_score`
    (since `spirit_court` factions are non-joinable and remain `player_rank == 0`).
    """
    vk = resolve_village_key_for_spirit_faction(faction_or_vk)
    if reputation_score is not None:
        rep = int(reputation_score)
    elif isinstance(faction_or_vk, Mapping):
        rep = int(faction_or_vk.get("reputation_score") or 0)
    else:
        rep = 0

    perks: list[str] = []
    if rep >= 1:
        if vk == "ghoul":
            perks.append(
                "Threshold Guest (1+): Village HQ commission board unlocked, complimentary safe rest, "
                "and automatic waiver of the 35g Distrusted Sentinel entry toll."
            )
        else:
            perks.append(
                "Threshold Guest (1+): Village HQ commission board & complimentary enclave safe rest unlocked."
            )

    if rep >= 25:
        disc_pct = 15 if rep >= 70 else (10 if rep >= 50 else 5)
        tier_pct = 45 if rep >= 50 else 25
        perks.append(
            f"Court Confidant (25+): -{disc_pct}% merchant discount at enclave & Night Market court stalls "
            f"(+15% markup below -10) and +{tier_pct}% higher-tier themed stock spawn weight."
        )

    if rep >= 70:
        deed_label = "Cypress Mausoleum Guest-Suite" if vk == "ghoul" else "Permanent Guest-Cottage"
        perks.append(f"Cottage Honoree (70+): {deed_label} deed (1.25x rest) & guaranteed Tier-1 Relic stall stock.")

    if rep >= SPIRIT_COURT_SWORN_ALLY_THRESHOLD and vk in SPIRIT_COURT_SWORN_ALLY_SPECS:
        spec = SPIRIT_COURT_SWORN_ALLY_SPECS[vk]
        bonus_str = ", ".join(f"+{v} {k}" for k, v in spec["stat_bonuses"].items())
        perks.append(
            f"Sovereign's Sworn Ally (90+): Stackable {bonus_str} & native 3-turn summon spell "
            f"'{spec['spell_name']}' ({spec['role_label']})."
        )
    return perks


def _extract_court_reps_from_factions(
    session_id: int | None,
    *,
    preloaded_factions: list[Mapping[str, Any]] | None = None,
) -> dict[str, int]:
    rows = list(preloaded_factions) if preloaded_factions is not None else []
    if preloaded_factions is None and session_id:
        try:
            import db
            rows = list(db.get_factions(int(session_id)) or [])
        except Exception:
            rows = []
    reps: dict[str, int] = {}
    for row in rows:
        if not isinstance(row, Mapping):
            continue
        vk = SPIRIT_COURT_VILLAGE_BY_FACTION_ID.get(str(row.get("faction_id") or "").strip().lower())
        if vk:
            reps[vk] = int(row.get("reputation_score") or 0)
    return reps


def get_active_sworn_ally_courts(
    session_id: int | None,
    *,
    preloaded_factions: list[Mapping[str, Any]] | None = None,
) -> list[str]:
    """Returns ordered list of Spirit Court keys where live `reputation_score >= 90`."""
    reps = _extract_court_reps_from_factions(session_id, preloaded_factions=preloaded_factions)
    return [vk for vk in SPIRIT_COURT_VILLAGE_KEYS if reps.get(vk, -999) >= SPIRIT_COURT_SWORN_ALLY_THRESHOLD]


def get_spirit_court_stat_bonuses(
    session_id: int | None,
    *,
    preloaded_factions: list[Mapping[str, Any]] | None = None,
) -> dict[str, int]:
    """Stacks passive stat boosts across all currently active (>= 90) Spirit Courts."""
    totals: dict[str, int] = {}
    for vk in get_active_sworn_ally_courts(session_id, preloaded_factions=preloaded_factions):
        spec = SPIRIT_COURT_SWORN_ALLY_SPECS.get(vk) or {}
        for stat_k, val in (spec.get("stat_bonuses") or {}).items():
            totals[stat_k] = int(totals.get(stat_k, 0)) + int(val)
    return totals


def apply_spirit_court_stat_bonuses(
    char_dict: Mapping[str, Any],
    session_id: int | None = None,
    *,
    bonuses: Mapping[str, int] | None = None,
    preloaded_factions: list[Mapping[str, Any]] | None = None,
) -> dict[str, Any]:
    """Returns an augmented copy of `char_dict` with live 90+ Sworn Ally stat boosts synchronized idempotently."""
    out = dict(char_dict or {})
    eff_bonuses = (
        dict(bonuses)
        if bonuses is not None
        else get_spirit_court_stat_bonuses(session_id, preloaded_factions=preloaded_factions)
    )
    prev_applied = bool(out.get("_spirit_court_bonuses_applied"))
    prev_bonuses = (
        {str(k): int(v or 0) for k, v in (out.get("_spirit_court_stat_bonuses") or {}).items()}
        if prev_applied
        else {}
    )
    eff_clean = {str(k): int(v or 0) for k, v in eff_bonuses.items() if int(v or 0) != 0}
    if prev_applied and prev_bonuses == eff_clean:
        return out

    out["_spirit_court_stat_bonuses"] = dict(eff_clean)
    out["_spirit_court_bonuses_applied"] = True
    delta_map = {
        stat_u: int(eff_clean.get(stat_u, 0)) - int(prev_bonuses.get(stat_u, 0))
        for stat_u in (set(prev_bonuses.keys()) | set(eff_clean.keys()))
    }
    if not any(delta_map.values()):
        return out

    nested_stats = dict(out["stats"]) if isinstance(out.get("stats"), dict) else None
    for stat_u, add_val in delta_map.items():
        if not add_val:
            continue
        col_k = SPIRIT_COURT_STAT_COL_MAP.get(stat_u, stat_u.lower())
        low_k = stat_u.lower()
        if col_k in out or low_k not in out:
            base_v = out.get(col_k, out.get(low_k, out.get(stat_u)))
            if base_v is None and nested_stats:
                base_v = nested_stats.get(stat_u, nested_stats.get(col_k, nested_stats.get(low_k)))
            out[col_k] = max(1, int(base_v or 1) + int(add_val))
        if low_k in out and low_k != col_k:
            out[low_k] = max(1, int(out[low_k] or 1) + int(add_val))
        if stat_u in out:
            out[stat_u] = max(1, int(out[stat_u] or 1) + int(add_val))
        if nested_stats is not None:
            for nk in (stat_u, col_k, low_k):
                if nk in nested_stats or nk == stat_u:
                    nested_stats[nk] = max(1, int(nested_stats.get(nk) or 1) + int(add_val))
    if nested_stats is not None:
        out["stats"] = nested_stats
    return out


def get_active_spirit_court_summon_spell_ids(
    session_id: int | None,
    *,
    preloaded_factions: list[Mapping[str, Any]] | None = None,
) -> list[str]:
    """Returns native 3-turn summon spell IDs currently unlocked by rep >= 90."""
    return [
        SPIRIT_COURT_SWORN_ALLY_SPECS[vk]["spell_id"]
        for vk in get_active_sworn_ally_courts(session_id, preloaded_factions=preloaded_factions)
        if vk in SPIRIT_COURT_SWORN_ALLY_SPECS
    ]


def is_spirit_court_summon_spell_active(
    session_id: int | None,
    spell_id: str,
    *,
    preloaded_factions: list[Mapping[str, Any]] | None = None,
) -> bool:
    """Checks whether `spell_id` is unlocked right now (`reputation_score >= 90` for its court)."""
    sid_str = str(spell_id or "").strip()
    if sid_str not in SPIRIT_COURT_SUMMON_SPELLS:
        return False
    return sid_str in get_active_spirit_court_summon_spell_ids(session_id, preloaded_factions=preloaded_factions)


def register_spirit_court_summons(
    spell_registry: dict[str, dict[str, Any]],
    summon_templates: dict[str, dict[str, Any]] | None = None,
) -> None:
    """Idempotently injects Spirit Court Sworn Ally summon spells and templates."""
    if summon_templates is not None:
        for t_key, tmpl in SPIRIT_COURT_SUMMON_TEMPLATES.items():
            summon_templates[t_key] = {
                **tmpl,
                "stat_weights": dict(tmpl.get("stat_weights") or {}),
                "combat_loadout": [dict(x) for x in (tmpl.get("combat_loadout") or ())],
            }
    for sp_id, sp_def in SPIRIT_COURT_SUMMON_SPELLS.items():
        sp_copy = dict(sp_def)
        sp_copy.setdefault("acc_mod", 100)
        sp_copy.setdefault("crit_bonus", 0.0)
        sp_copy.setdefault(
            "tags",
            {
                "discipline": "summon", "school": "Conjuration",
                "element": sp_copy.get("damage_type", "aether"),
                "target_type": "summon", "tier": sp_copy.get("tier", 2),
                "delivery": "summon", "status_infliction": [],
            },
        )
        spell_registry[sp_id] = sp_copy


__all__ = [
    "SPIRIT_COURT_VILLAGE_KEYS", "SPIRIT_COURT_FACTION_ID_BY_VILLAGE",
    "SPIRIT_COURT_VILLAGE_BY_FACTION_ID", "SPIRIT_COURT_SWORN_ALLY_THRESHOLD",
    "SPIRIT_COURT_SWORN_ALLY_SPECS", "SPIRIT_COURT_SUMMON_SPELLS", "SPIRIT_COURT_SUMMON_TEMPLATES",
    "resolve_village_key_for_spirit_faction", "get_spirit_court_standing_tier_boost",
    "get_spirit_court_active_perks", "get_active_sworn_ally_courts",
    "get_spirit_court_stat_bonuses", "apply_spirit_court_stat_bonuses",
    "get_active_spirit_court_summon_spell_ids", "is_spirit_court_summon_spell_active",
    "register_spirit_court_summons",
]
