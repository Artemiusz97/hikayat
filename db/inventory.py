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

def get_learned_spells(user_id: int) -> list[str]:
    char = db.get_character(user_id)
    if not char:
        return []
    raw = char.get("learned_spells", "[]")
    if isinstance(raw, list):
        return raw
    try:
        return json.loads(raw)
    except Exception:
        return []

def learn_spell(user_id: int, spell_id: str, spell_data: dict | None = None) -> bool:
    char = db.get_character(user_id)
    if not char:
        return False
    if spell_data and isinstance(spell_data, dict):
        save_procedural_spell(spell_data)
    spells = get_learned_spells(user_id)
    if spell_id in spells:
        return False
    spells.append(spell_id)
    with get_conn() as conn:
        conn.execute("UPDATE characters SET learned_spells=? WHERE id=?", (json.dumps(spells), char["id"]))
    return True

def save_procedural_spell(spell_def: dict) -> None:
    if not isinstance(spell_def, dict) or not spell_def.get("id"):
        return
    spell_id = str(spell_def["id"]).strip()
    payload = json.dumps(spell_def)
    now = time.time()
    with get_conn() as conn:
        conn.execute(
            "INSERT OR REPLACE INTO procedural_spells (id, spell_data, created_at) VALUES (?, ?, ?)",
            (spell_id, payload, now)
        )

def get_procedural_spell(spell_id: str) -> dict | None:
    if not spell_id:
        return None
    with get_conn() as conn:
        row = conn.execute("SELECT spell_data FROM procedural_spells WHERE id=?", (spell_id,)).fetchone()
        if row and row["spell_data"]:
            try:
                return json.loads(row["spell_data"])
            except Exception:
                return None
    return None

def get_all_procedural_spells() -> list[dict]:
    with get_conn() as conn:
        rows = conn.execute("SELECT spell_data FROM procedural_spells").fetchall()
        spells = []
        for r in rows:
            try:
                spells.append(json.loads(r["spell_data"]))
            except Exception:
                pass
        return spells

def set_learned_spells(user_id: int, spells: list[str]) -> bool:
    char = db.get_character(user_id)
    if not char:
        return False
    with get_conn() as conn:
        conn.execute("UPDATE characters SET learned_spells=? WHERE id=?", (json.dumps(spells), char["id"]))
    return True

def has_learned_spell(user_id: int, spell_id: str) -> bool:
    spells = get_learned_spells(user_id)
    return spell_id in spells

def get_skill_progress(char: dict) -> dict:
    try:
        return json.loads(char.get("skill_progress") or "{}")
    except json.JSONDecodeError:
        return {}

def set_skill_progress(user_id: int, progress: dict):
    db.update_character_fields(user_id, skill_progress=json.dumps(progress))

def can_add_item(user_id: int, slot_cost: int = 1) -> bool:
    char = db.get_character(user_id)
    if not char:
        return True
    cap = cd.inventory_capacity(char.get("str_", 1))
    return (used_slots(user_id) + slot_cost) <= cap

def add_item(user_id: int, name: str, item_type: str, effect: str = "", slot_cost: int = 1, force: bool = False) -> int | None:
    char = db.get_character(user_id)
    char_id = char["id"] if char else None
    if not force and char:
        cap = cd.inventory_capacity(char.get("str_", 1))
        if (used_slots(user_id) + slot_cost) > cap:
            return None
    with get_conn() as conn:
        cur = conn.execute(
            "INSERT INTO inventory (user_id, character_id, name, item_type, effect, slot_cost) VALUES (?,?,?,?,?,?)",
            (user_id, char_id, name, item_type, effect, slot_cost),
        )
        return cur.lastrowid

def remove_item_by_name(user_id: int, name: str) -> bool:
    char = db.get_character(user_id)
    if not char:
        return False
    char_id = char["id"]
    target_clean = (name or "").strip().lower()
    if not target_clean:
        return False

    with get_conn() as conn:
        # 1. Exact case-insensitive match
        row = conn.execute(
            "SELECT id FROM inventory WHERE (character_id=? OR (character_id IS NULL AND user_id=?)) AND LOWER(name)=? LIMIT 1",
            (char_id, user_id, target_clean)
        ).fetchone()

        # 2. Substring match
        if not row:
            rows = conn.execute(
                "SELECT id, name FROM inventory WHERE character_id=? OR (character_id IS NULL AND user_id=?)",
                (char_id, user_id)
            ).fetchall()
            for r in rows:
                r_name = str(r["name"] or "").strip().lower()
                if target_clean in r_name or r_name in target_clean:
                    row = r
                    break

            # 3. Token overlap match
            if not row:
                target_tokens = set(target_clean.split()) - {"a", "an", "the", "of", "in", "my", "your", "lost", "item"}
                best_match = None
                best_score = 0
                for r in rows:
                    r_tokens = set(str(r["name"] or "").strip().lower().split())
                    overlap = len(target_tokens & r_tokens)
                    if overlap > best_score:
                        best_score = overlap
                        best_match = r
                if best_match and best_score >= 1:
                    row = best_match

        if row:
            cur = conn.execute("DELETE FROM inventory WHERE id=?", (row["id"],))
            return cur.rowcount > 0
    return False

def remove_item(user_id: int, item_id: int) -> bool:
    char = db.get_character(user_id)
    if not char:
        return False
    with get_conn() as conn:
        cur = conn.execute(
            "DELETE FROM inventory WHERE id=? AND (character_id=? OR (character_id IS NULL AND user_id=?))",
            (item_id, char["id"], user_id),
        )
        return cur.rowcount > 0

def get_inventory(user_id: int):
    char = db.get_character(user_id)
    if not char:
        return []
    with get_conn() as conn:
        rows = conn.execute("SELECT * FROM inventory WHERE character_id=? OR (character_id IS NULL AND user_id=?)",
                            (char["id"], user_id)).fetchall()
        return [dict(r) for r in rows]

def equip_item(user_id: int, item_id: int, slot: str) -> dict | None:
    if slot not in cd.EQUIPMENT_SLOTS:
        raise ValueError(f"'{slot}' is not a valid equipment slot.")
    char = db.get_character(user_id)
    if not char:
        raise ValueError("No active character found.")
    char_id = char["id"]

    from mechanics.combat.equipment import is_two_handed

    with get_conn() as conn:
        owned = conn.execute("SELECT * FROM inventory WHERE id=? AND (character_id=? OR (character_id IS NULL AND user_id=?))",
                              (item_id, char_id, user_id)).fetchone()
        if not owned:
            raise ValueError("That item isn't in your inventory.")
        item_dict = dict(owned)

        # 0. Slot-Type Compatibility Validation
        from mechanics.combat.equipment import parse_equipment_metadata
        item_meta = parse_equipment_metadata(item_dict) or {}
        item_type = str(item_dict.get("item_type") or item_meta.get("item_type") or "").strip().title()
        archetype = str(item_meta.get("archetype") or "").strip().lower()

        # Check combat body armor vs civilian clothing vs headwear vs weapon vs shield
        is_civilian_clothing = (item_type == "Clothing") or (archetype in ("casual_shirt", "blouse", "school_uniform_top", "jacket", "hoodie", "robe", "tunic", "trousers", "skirt", "shorts", "slacks", "jeans"))
        is_headwear = (item_type in ("Headwear", "Helmet", "Head")) or (archetype in ("cloth_hood", "cap", "open_helm", "full_greathelm", "tech_visor", "gas_mask", "circlet", "formal_hat"))
        is_shield = (item_type == "Shield") or (archetype in ("buckler", "heater_shield", "tower_shield", "riot_shield", "energy_shield"))
        is_accessory = (item_type == "Accessory") or (archetype in ("ring", "amulet", "belt", "necklace", "charm", "cloak", "bracelet", "earring", "talisman"))
        is_gloves = (item_type in ("Gloves", "Handwear")) or (archetype in ("gloves", "heavy_gauntlets", "cloth_wraps", "fingerless_gloves", "precision_gloves", "insulated_gloves", "arcane_gloves", "leather_gloves", "formal_gloves", "gauntlets", "mitts"))
        is_shoes = (item_type in ("Shoes", "Footwear", "Boots")) or (archetype in ("boots", "shoes", "sandals", "greaves", "heavy_greaves", "light_sneakers", "stealth_boots", "riding_boots", "hazard_boots", "formal_shoes", "combat_boots"))

        non_armor_types = ("Clothing", "Headwear", "Helmet", "Head", "Gloves", "Handwear", "Shoes", "Footwear", "Boots", "Accessory", "Shield", "Weapon")
        non_armor_slots = ("Top", "Bottom", "Head", "Gloves", "Shoes", "Shield", "Weapon", "Accessory 1", "Accessory 2", "Accessory 3", "Accessory 4")

        is_combat_armor = (
            (item_type == "Armor")
            or (slot == "Armor" and item_meta.get("base_dt", 0) > 2)
            or (
                item_type not in non_armor_types
                and slot not in non_armor_slots
                and not (is_headwear or is_gloves or is_shoes or is_accessory or is_shield or is_civilian_clothing)
                and archetype in ("plate", "kevlar", "chainmail", "lamellar", "ceramic", "composite", "power_armor", "magic_robe", "cuirass", "leather")
            )
        )
        # Only classify as weapon via archetype/multiplier heuristics when item_type doesn't
        # already identify the item as something else (the heuristic archetype defaults to
        # "sword" for unrecognised names, which would otherwise misclassify non-weapon gear).
        _type_already_known = is_combat_armor or is_civilian_clothing or is_headwear or is_shield or is_accessory or is_gloves or is_shoes
        is_weapon = (item_type == "Weapon") or (
            not _type_already_known and (("multiplier" in item_meta) or (archetype in ("dagger", "shortsword", "wand", "pistol", "throwing", "sword", "axe", "mace", "spear", "revolver", "greatsword", "polearm", "warhammer", "staff", "bow", "crossbow", "rifle", "shotgun", "machinegun", "explosive", "katana")))
        )

        if is_combat_armor and slot not in ("Armor",):
            raise ValueError("Combat body armor can only be equipped in the dedicated 'Armor' slot.")
        if is_civilian_clothing and slot not in ("Top", "Bottom"):
            raise ValueError("Civilian clothing can only be equipped in 'Top' or 'Bottom' slots.")
        if is_headwear and slot not in ("Head",):
            raise ValueError("Headwear and helmets can only be equipped in the 'Head' slot.")
        if is_shield and slot not in ("Shield",):
            raise ValueError("Shields can only be equipped in the 'Shield' slot.")
        if is_weapon and slot not in ("Weapon", "Shield"):
            raise ValueError("Weapons can only be equipped in 'Weapon' (main-hand) or 'Shield' (off-hand) slots.")
        if is_accessory and slot not in ("Accessory 1", "Accessory 2", "Accessory 3", "Accessory 4"):
            raise ValueError("Accessories can only be equipped in 'Accessory 1-4' slots.")
        if is_gloves and slot not in ("Gloves",):
            raise ValueError("Gloves can only be equipped in the 'Gloves' slot.")
        if is_shoes and slot not in ("Shoes",):
            raise ValueError("Shoes can only be equipped in the 'Shoes' slot.")

        # 1. 2-Handed Weapon & Shield / Off-Hand mutual exclusion
        if slot == "Weapon" and is_two_handed(item_dict):
            # Unequip shield/off-hand if equipping a 2H weapon
            shield_row = conn.execute(
                "SELECT * FROM inventory WHERE (character_id=? OR (character_id IS NULL AND user_id=?)) AND slot='Shield' AND equipped=1",
                (char_id, user_id)).fetchone()
            if shield_row:
                conn.execute("UPDATE inventory SET equipped=0, slot=NULL WHERE id=?", (shield_row["id"],))
        elif slot == "Shield":
            if is_two_handed(item_dict):
                raise ValueError("Two-handed weapons cannot be equipped in the off-hand slot.")
            # Unequip 2H weapon if equipping a shield or off-hand weapon
            weapon_row = conn.execute(
                "SELECT * FROM inventory WHERE (character_id=? OR (character_id IS NULL AND user_id=?)) AND slot='Weapon' AND equipped=1",
                (char_id, user_id)).fetchone()
            if weapon_row and is_two_handed(dict(weapon_row)):
                conn.execute("UPDATE inventory SET equipped=0, slot=NULL WHERE id=?", (weapon_row["id"],))

        # 2. Unequip whatever was previously in this slot
        previous_row = conn.execute(
            "SELECT * FROM inventory WHERE (character_id=? OR (character_id IS NULL AND user_id=?)) AND slot=? AND equipped=1 AND id!=?",
            (char_id, user_id, slot, item_id)).fetchone()
        previous = dict(previous_row) if previous_row else None
        if previous:
            conn.execute("UPDATE inventory SET equipped=0, slot=NULL WHERE id=?", (previous["id"],))

        conn.execute("UPDATE inventory SET equipped=1, slot=?, character_id=? WHERE id=?", (slot, char_id, item_id))
    return previous

def unequip_slot(user_id: int, slot: str) -> dict | None:
    if slot not in cd.EQUIPMENT_SLOTS:
        raise ValueError(f"'{slot}' is not a valid equipment slot.")
    char = db.get_character(user_id)
    if not char:
        return None
    char_id = char["id"]
    with get_conn() as conn:
        row = conn.execute("SELECT * FROM inventory WHERE (character_id=? OR (character_id IS NULL AND user_id=?)) AND slot=? AND equipped=1",
                            (char_id, user_id, slot)).fetchone()
        if not row:
            return None
        conn.execute("UPDATE inventory SET equipped=0, slot=NULL WHERE id=?", (row["id"],))
    return dict(row)

def get_equipment(user_id: int) -> dict:
    char = db.get_character(user_id)
    if not char:
        return {slot: None for slot in cd.EQUIPMENT_SLOTS}
    char_id = char["id"]
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM inventory WHERE (character_id=? OR (character_id IS NULL AND user_id=?)) AND equipped=1 AND slot IS NOT NULL",
            (char_id, user_id)).fetchall()
    by_slot = {r["slot"]: dict(r) for r in rows}
    return {slot: by_slot.get(slot) for slot in cd.EQUIPMENT_SLOTS}

def used_slots(user_id: int) -> int:
    return sum(i.get("slot_cost", 1) for i in get_inventory(user_id))


