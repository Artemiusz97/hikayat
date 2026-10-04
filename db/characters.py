import db
import asyncio
import json
import time
from contextlib import contextmanager
import re
import sqlite3
from config import DB_PATH
import character_data as cd
from .core import *
from .core import _delete_session_records, _to_str, _is_suspicious_entity_text, _safe_int_db, _sanitize_npcs_list

def create_character(user_id: int, name: str, char_class: str = "Adventurer", class_description: str = "",
                     stats: dict = None, gold: int = cd.STARTING_GOLD, pending_stat_points: int = 0,
                     gender: str = "Male", scenario: str = "fantasy",
                     race: str = "human", race_description: str = "") -> dict:
    if stats is None:
        stats = {s: cd.BASE_STAT_VALUE for s in cd.STATS}
    existing = get_user_characters(user_id)
    if len(existing) >= 6:
        raise ValueError("Character creation limit reached (maximum 6 characters allowed per user).")
    from mechanics.social.races import normalize_race
    norm_race = normalize_race(race, scen_key=scenario, seed=name) if race else "human"
    hp = cd.calculate_max_hp(stats["END"])
    mp = cd.calculate_max_mp(stats["END"])
    with get_conn() as conn:
        conn.execute("UPDATE characters SET is_active=0 WHERE user_id=?", (user_id,))
        cur = conn.execute(
            """INSERT INTO characters
               (user_id, is_active, name, char_class, class_description, gender, scenario, race, race_description, str_, per_, end_, cha, int_, agi, luk,
                hp, max_hp, temp_hp, mp, max_mp, level, xp, pending_stat_points, gold, status_effects,
                skill_progress, active_session_id, created_at)
               VALUES (?,1,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,0,?,?,1,0,?,?,'[]','{}',NULL,?)""",
            (user_id, name, char_class, class_description, gender, scenario, norm_race, race_description,
             stats["STR"], stats["PER"], stats["END"], stats["CHA"], stats["INT"], stats["AGI"], stats["LUK"],
             hp, hp, mp, mp, pending_stat_points, gold, time.time()),
        )
        char_id = cur.lastrowid
    return get_character_by_id(char_id)

def apply_adventure_loadout(
    user_id: int,
    scenario: str,
    char_class: str,
    class_description: str = "",
    weapon_name: str = "",
    weapon_description: str = "",
    gear_map: dict | None = None,
    starting_items: list | None = None,
) -> dict:
    """Applies a scenario-specific class, weapon, and generated starting equipment
    to the active character at adventure start. Clears previous temporary equipment
    so the character gets a fresh scenario-tailored loadout."""
    char = db.get_character(user_id)
    if not char:
        raise ValueError("No active character found for user.")
    char_id = char["id"]

    with get_conn() as conn:
        # Clear existing inventory/equipment for this character
        conn.execute(
            "DELETE FROM inventory WHERE character_id=? OR (character_id IS NULL AND user_id=?)",
            (char_id, user_id)
        )
        # Update character's scenario, class, and description
        conn.execute(
            """UPDATE characters
               SET scenario=?, char_class=?, class_description=?, gold=?, hp=max_hp, mp=max_mp, status_effects='[]'
               WHERE id=?""",
            (scenario, char_class, class_description, cd.STARTING_GOLD, char_id)
        )

    from mechanics.combat.equipment import parse_equipment_metadata
    from mechanics.combat.items.envelope import serialize_item
    from mechanics.combat.items.weapons import generate_random_equipment as gen_weapon

    # 1. Starting items / carried items
    if starting_items:
        for item_name, item_type, effect, slot_cost in starting_items:
            if item_type in ("Weapon", "Armor", "Shield"):
                continue
            item_id = db.add_item(user_id, item_name, item_type, effect, slot_cost)
            default_slot = cd.DEFAULT_EQUIP_SLOT_FOR_ITEM_TYPE.get(item_type)
            if default_slot:
                db.equip_item(user_id, item_id, default_slot)

    # 2. Starting armor / clothing / accessories from gear_map
    equipped_weapon = False
    if gear_map:
        for slot, entry in gear_map.items():
            if not entry:
                continue

            # If weapon_name was explicitly chosen by the player, let weapon_name take priority
            if slot == "Weapon" and weapon_name:
                continue

            if isinstance(entry, dict):
                # Generated item from new equipment generation system
                gear_name = entry["name"]
                if slot == "Weapon":
                    default_type = "Weapon"
                elif slot == "Shield":
                    default_type = "Shield"
                elif slot in ("Top", "Bottom"):
                    default_type = "Clothing"
                elif slot == "Armor":
                    default_type = "Armor"
                elif slot == "Head":
                    default_type = "Headwear"
                elif slot == "Gloves":
                    default_type = "Gloves"
                elif slot == "Shoes":
                    default_type = "Shoes"
                elif slot.startswith("Accessory"):
                    default_type = "Accessory"
                else:
                    default_type = "Armor"
                gear_type = entry.get("item_type") or default_type
                gear_effect = entry.get("effect", "")
                gear_slot_cost = entry.get("slot_cost", 1)
                gear_id = db.add_item(user_id, gear_name, gear_type, gear_effect, gear_slot_cost)
                db.equip_item(user_id, gear_id, slot)
                if slot == "Weapon":
                    equipped_weapon = True
                continue


    # 3. Starting weapon (utilizing new weapon generation system)
    if weapon_name or not equipped_weapon:
        target_w_name = weapon_name or f"{char_class or 'Adventurer'} Starter Weapon"
        w_item = gen_weapon(scenario=scenario, slot="Weapon", tier=3, name=target_w_name)
        weapon_id = db.add_item(user_id, w_item["name"], "Weapon", w_item["effect"], w_item.get("slot_cost", 1))
        db.equip_item(user_id, weapon_id, "Weapon")

    return db.get_character(user_id)

def _apply_debug_stat_override(char: dict | None) -> dict | None:
    if not char:
        return char
    user_id = char.get("user_id")
    if not user_id:
        return char

    # Retroactively clean up existing bloated status effects in active sessions
    raw_status = char.get("status_effects")
    if isinstance(raw_status, str):
        try:
            parsed_status = json.loads(raw_status)
        except Exception:
            parsed_status = []
    else:
        parsed_status = raw_status or []
        
    cleaned_status = cd.sanitize_status_effects(parsed_status)
    # Overwrite the dict's status_effects so it heals itself on the next turn save
    char["status_effects"] = json.dumps(cleaned_status)

    settings = db.get_settings(user_id)
    stat_mode = settings.get("debug_stat_mode", "off")
    if stat_mode == "max":
        for s in cd.STATS:
            col = STAT_COLUMN.get(s)
            if col:
                char[col] = cd.MAX_STAT_VALUE
    elif stat_mode == "min":
        for s in cd.STATS:
            col = STAT_COLUMN.get(s)
            if col:
                char[col] = cd.BASE_STAT_VALUE
    return char

def get_character(user_id: int):
    with get_conn() as conn:
        row = conn.execute("SELECT * FROM characters WHERE user_id=? AND is_active=1 LIMIT 1", (user_id,)).fetchone()
        if not row:
            row = conn.execute("SELECT * FROM characters WHERE user_id=? ORDER BY id DESC LIMIT 1", (user_id,)).fetchone()
            if row:
                conn.execute("UPDATE characters SET is_active=1 WHERE id=?", (row["id"],))
        return _apply_debug_stat_override(dict(row)) if row else None

def get_character_by_id(character_id: int):
    with get_conn() as conn:
        row = conn.execute("SELECT * FROM characters WHERE id=?", (character_id,)).fetchone()
        return _apply_debug_stat_override(dict(row)) if row else None

def get_user_characters(user_id: int) -> list[dict]:
    with get_conn() as conn:
        rows = conn.execute("SELECT * FROM characters WHERE user_id=? ORDER BY is_active DESC, id ASC", (user_id,)).fetchall()
        return [_apply_debug_stat_override(dict(r)) for r in rows]

def switch_character(user_id: int, character_id_or_name) -> dict | None:
    chars = get_user_characters(user_id)
    if not chars:
        return None

    target = None
    if isinstance(character_id_or_name, int):
        target = next((c for c in chars if c["id"] == character_id_or_name), None)
    else:
        name_str = str(character_id_or_name).strip().lower()
        target = next((c for c in chars if c["name"].lower() == name_str), None)

    if not target:
        return None

    with get_conn() as conn:
        conn.execute("UPDATE characters SET is_active=0 WHERE user_id=?", (user_id,))
        conn.execute("UPDATE characters SET is_active=1 WHERE id=?", (target["id"],))
    return get_character_by_id(target["id"])

def delete_character(user_id: int, character_id: int = None) -> bool:
    with get_conn() as conn:
        if character_id is None:
            char = db.get_character(user_id)
            if not char:
                return False
            target_id = char["id"]
            was_active = True
        else:
            char = get_character_by_id(character_id)
            if not char or char["user_id"] != user_id:
                return False
            target_id = char["id"]
            was_active = bool(char.get("is_active"))

        active_sess_id = char.get("active_session_id")

        conn.execute("DELETE FROM inventory WHERE character_id=?", (target_id,))
        conn.execute("DELETE FROM adventure_saves WHERE character_id=?", (target_id,))
        conn.execute("DELETE FROM characters WHERE id=?", (target_id,))

        if active_sess_id:
            other_chars = conn.execute("SELECT id FROM characters WHERE active_session_id=?", (active_sess_id,)).fetchall()
            if not other_chars:
                _delete_session_records(conn, active_sess_id)

        remaining = conn.execute("SELECT id FROM characters WHERE user_id=? ORDER BY id DESC", (user_id,)).fetchall()
        if not remaining:
            user_sessions = conn.execute("SELECT session_id FROM session_members WHERE user_id=?", (user_id,)).fetchall()
            conn.execute("DELETE FROM session_members WHERE user_id=?", (user_id,))
            conn.execute("DELETE FROM user_settings WHERE user_id=?", (user_id,))
            for us in user_sessions:
                s_id = us["session_id"]
                has_active = conn.execute("SELECT 1 FROM characters WHERE active_session_id=?", (s_id,)).fetchone()
                if not has_active:
                    _delete_session_records(conn, s_id)
        elif was_active:
            conn.execute("UPDATE characters SET is_active=1 WHERE id=?", (remaining[0]["id"],))
        return True

def update_character_fields(user_id: int, **fields):
    if not fields:
        return
    char = db.get_character(user_id)
    if not char:
        return
    cols = ", ".join(f"{k}=?" for k in fields)
    with get_conn() as conn:
        conn.execute(f"UPDATE characters SET {cols} WHERE id=?",
                     (*fields.values(), char["id"]))

def apply_hp_mp_delta(user_id: int, hp_delta: int = 0, mp_delta: int = 0, gold_delta: int = 0, temp_hp_delta: int = 0):
    char = db.get_character(user_id)
    if not char:
        return None
    
    current_temp_hp = char.get("temp_hp", 0)
    current_hp = char.get("hp", 0)
    
    # Handle damage absorption through Temp HP
    if hp_delta < 0:
        damage = abs(hp_delta)
        if current_temp_hp >= damage:
            new_temp_hp = current_temp_hp - damage
            new_hp = current_hp
        else:
            remaining_damage = damage - current_temp_hp
            new_temp_hp = 0
            new_hp = max(0, min(char.get("max_hp", 100), current_hp - remaining_damage))
    else:
        # Healing only applies to base HP, never Temp HP
        new_temp_hp = current_temp_hp
        new_hp = max(0, min(char.get("max_hp", 100), current_hp + hp_delta))
        
    # Apply explicit temp HP buffs/drains
    if temp_hp_delta != 0:
        new_temp_hp = max(0, new_temp_hp + temp_hp_delta)
        
    new_mp = max(0, min(char.get("max_mp", 50), char.get("mp", 0) + mp_delta))
    new_gold = max(0, char.get("gold", 0) + gold_delta)
    db.update_character_fields(user_id, hp=new_hp, temp_hp=new_temp_hp, mp=new_mp, gold=new_gold)
    return db.get_character(user_id)

def apply_turn_regen(user_id: int):
    """Passive HP/MP regen tied to Endurance, applied once per resolved turn."""
    char = db.get_character(user_id)
    if not char or char.get("hp", 0) <= 0:
        return
    db.apply_hp_mp_delta(user_id, hp_delta=cd.hp_regen(char["end_"]), mp_delta=cd.mp_regen(char["end_"]))

def set_status_effects(user_id: int, effects: list):
    db.update_character_fields(user_id, status_effects=json.dumps(effects, default=str))

def get_status_effects(user_id: int) -> list:
    char = db.get_character(user_id)
    if not char:
        return []
    raw = char.get("status_effects")
    if isinstance(raw, str):
        try:
            return json.loads(raw)
        except Exception:
            return []
    return raw if isinstance(raw, list) else []

def remove_status_effect(user_id: int, effect_name: str):
    effects = get_status_effects(user_id)
    target = str(effect_name).strip().lower()
    new_effects = [e for e in effects if (e.get("name", "").lower() if isinstance(e, dict) else str(e).lower()) != target]
    set_status_effects(user_id, new_effects)

get_active_character = get_character

def heal_full(user_id: int):
    char = db.get_character(user_id)
    if char:
        db.update_character_fields(user_id, hp=char["max_hp"], mp=char["max_mp"])

def set_hp_to_one(user_id: int):
    char = db.get_character(user_id)
    if char:
        db.update_character_fields(user_id, hp=1)

def bump_stat(user_id: int, stat: str, amount: int = 1):
    """Increase a stat and recompute any derived values that depend on it
    (max HP/MP from END, inventory capacity is computed live from STR so
    nothing to store there). Clamps to cd.MAX_STAT_VALUE -- this is the one
    function that ever writes a stat column, so enforcing the cap here
    guarantees no code path can push a stat past it."""
    char = db.get_character(user_id)
    if not char:
        return
    col = STAT_COLUMN[stat]
    new_value = min(cd.MAX_STAT_VALUE, char[col] + amount)
    if new_value == char[col]:
        return
    db.update_character_fields(user_id, **{col: new_value})

    if stat == "END":
        old_max_hp, old_max_mp = char["max_hp"], char["max_mp"]
        new_max_hp, new_max_mp = cd.derive_hp(new_value), cd.derive_mp(new_value)
        hp_gain, mp_gain = new_max_hp - old_max_hp, new_max_mp - old_max_mp
        db.update_character_fields(user_id, max_hp=new_max_hp, max_mp=new_max_mp,
                                 hp=min(new_max_hp, char["hp"] + hp_gain),
                                 mp=min(new_max_mp, char["mp"] + mp_gain))

def spend_stat_point(user_id: int, stat: str) -> str:
    """Spend one pending stat point on `stat`. This -- fed exclusively by
    level-ups via db.add_xp() -- is the ONLY sanctioned way stat points are
    earned and spent; there is no other passive/alternative source.
    Returns one of:
      "ok"        -- point spent, stat increased
      "no_points" -- character has no pending stat points to spend
      "capped"    -- stat is already at cd.MAX_STAT_VALUE; point NOT spent
                     (kept pending so the player can choose a different stat)
    """
    char = db.get_character(user_id)
    if not char or char["pending_stat_points"] <= 0:
        return "no_points"
    col = STAT_COLUMN[stat]
    if char[col] >= cd.MAX_STAT_VALUE:
        return "capped"
    bump_stat(user_id, stat, 1)
    db.update_character_fields(user_id, pending_stat_points=char["pending_stat_points"] - 1)
    return "ok"

def add_xp(user_id: int, amount: int):
    """Adds XP (scaled by INT) and hands out level-up stat points, capped at
    MAX_LEVEL. Returns the list of new levels reached (empty if none)."""
    char = db.get_character(user_id)
    if not char:
        return []
    if char["level"] >= cd.MAX_LEVEL:
        return []

    scaled = round(amount * cd.xp_multiplier(char["int_"]))
    xp = char["xp"] + scaled
    level = char["level"]
    pending = char["pending_stat_points"]
    levels_gained = []

    needed = level * cd.XP_PER_LEVEL
    while xp >= needed and level < cd.MAX_LEVEL:
        xp -= needed
        level += 1
        pending += 1
        levels_gained.append(level)
        needed = level * cd.XP_PER_LEVEL

    if level >= cd.MAX_LEVEL:
        xp = 0  # no XP grinding needed/shown past the cap

    db.update_character_fields(user_id, xp=xp, level=level, pending_stat_points=pending)
    return levels_gained


def update_character_stats(user_id: int, stats: dict):
    char = db.get_character(user_id)
    if not char:
        return
    str_val = int(stats.get('str') or stats.get('STR') or char.get('str_', 1))
    per_val = int(stats.get('per') or stats.get('PER') or char.get('per_', 1))
    end_val = int(stats.get('end') or stats.get('END') or char.get('end_', 1))
    cha_val = int(stats.get('cha') or stats.get('CHA') or char.get('cha', 1))
    int_val = int(stats.get('int') or stats.get('INT') or char.get('int_', 1))
    agi_val = int(stats.get('agi') or stats.get('AGI') or char.get('agi', 1))
    luk_val = int(stats.get('luk') or stats.get('LUK') or char.get('luk', 1))
    
    max_hp = cd.calculate_max_hp(end_val)
    max_mp = cd.calculate_max_mp(end_val)
    
    db.update_character_fields(
        user_id,
        str_=str_val,
        per_=per_val,
        end_=end_val,
        cha=cha_val,
        int_=int_val,
        agi=agi_val,
        luk=luk_val,
        max_hp=max_hp,
        hp=max_hp,
        max_mp=max_mp,
        mp=max_mp
    )

