from __future__ import annotations
import db
import logging
import asyncio
import json
import time
from typing import Any, Optional
from contextlib import contextmanager
import re
import sqlite3
from config import DB_PATH
import character_data as cd
from .core import *
from .core import _delete_session_records
log = logging.getLogger(__name__)

def create_character(user_id: int, name: str, char_class: str = "Adventurer", class_description: str = "",
                     stats: dict = None, gold: int = cd.STARTING_GOLD, pending_stat_points: int = 0,
                     gender: str = "Male", scenario: str = "fantasy",
                     race: str = "human", race_description: str = "", appearance: dict = None,
                     attribute: str | None = None, combat_archetype: str | None = None,
                     ability_medium: str | None = None) -> dict:
    if stats is None:
        stats = {s: cd.BASE_STAT_VALUE for s in cd.STATS}
    existing = get_user_characters(user_id)
    if len(existing) >= 6:
        raise ValueError("Character creation limit reached (maximum 6 characters allowed per user).")
    from mechanics.system.input_sanitizer import sanitize_character_name, sanitize_prompt_lore
    from mechanics.social.races import normalize_race
    from mechanics.social.persona import normalize_appearance
    from scenario_data import is_anomalous_incursions_scenario
    name = sanitize_character_name(name, max_len=60, fallback="Adventurer")
    char_class = sanitize_character_name(char_class or "Adventurer", max_len=60, fallback="Adventurer")
    class_description = sanitize_prompt_lore(class_description or "", max_len=1500)
    gender = sanitize_character_name(gender or "Male", max_len=50, fallback="Male")
    race = sanitize_character_name(race or "human", max_len=60, fallback="human")
    race_description = sanitize_prompt_lore(race_description or "", max_len=600)
    norm_race = normalize_race(race, scen_key=scenario, seed=name) if race else "human"
    hp = cd.calculate_max_hp(stats["END"])
    mp = cd.calculate_max_mp(stats["END"])

    is_anom = is_anomalous_incursions_scenario(scenario)
    attr_val = str(attribute).strip().lower() if (is_anom and attribute) else None
    arch_val = str(combat_archetype).strip().lower() if (is_anom and combat_archetype) else None
    med_val = str(ability_medium).strip().lower() if (is_anom and ability_medium) else None

    app_dict = dict(appearance or {})
    is_male = any(kw in str(gender).lower() for kw in ("male", "man", "boy")) and "female" not in str(gender).lower()
    if is_male:
        app_dict.pop("breast_size", None)
        if not app_dict.get("penis_size"):
            app_dict["penis_size"] = "Average"
    else:
        app_dict.pop("penis_size", None)
        if not app_dict.get("breast_size"):
            app_dict["breast_size"] = "Modest B-Cup"
    norm_app = normalize_appearance(app_dict, gender=gender, race=norm_race, scen_key=scenario, desc=class_description)
    if app_dict.get("origin_mode"):
        norm_app["origin_mode"] = app_dict["origin_mode"]
    if app_dict.get("student_grade"):
        norm_app["student_grade"] = app_dict["student_grade"]
    app_json = json.dumps(norm_app)

    with UnitOfWork() as conn:
        char_count = conn.execute(
            "SELECT COUNT(*) FROM characters WHERE user_id=?",
            (user_id,),
        ).fetchone()[0]
        if int(char_count or 0) >= 6:
            raise ValueError("Character creation limit reached (maximum 6 characters allowed per user).")
        conn.execute("UPDATE characters SET is_active=0 WHERE user_id=?", (user_id,))
        cur = conn.execute(
            """INSERT INTO characters
               (user_id, is_active, name, char_class, class_description, gender, scenario, race, race_description, str_, per_, end_, cha, int_, agi, luk,
                hp, max_hp, temp_hp, mp, max_mp, level, xp, pending_stat_points, gold, status_effects,
                skill_progress, active_session_id, appearance_json, attribute, combat_archetype, ability_medium, created_at)
               VALUES (?,1,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,0,?,?,1,0,?,?,'[]','{}',NULL,?,?,?,?,?)""",
            (user_id, name, char_class, class_description, gender, scenario, norm_race, race_description,
             stats["STR"], stats["PER"], stats["END"], stats["CHA"], stats["INT"], stats["AGI"], stats["LUK"],
             hp, hp, mp, mp, pending_stat_points, gold, app_json, attr_val, arch_val, med_val, time.time()),
        )
        char_id = cur.lastrowid
    if is_anom and attr_val and arch_val and med_val:
        try:
            from mechanics.combat.spells.awakened_kits import build_awakened_kit_ids
            innate = list(build_awakened_kit_ids(attr_val, arch_val, med_val))
            db.set_skill_progress(user_id, {"innate_spells": innate, "equipped_granted_spells": [], "empowered_granted_spells": []})
            db.set_learned_spells(user_id, innate)
        except Exception as e:
            log.warning("Failed seeding innate 3-axis spells in create_character for user %s: %s", user_id, e)
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
    attribute: str | None = None,
    combat_archetype: str | None = None,
    ability_medium: str | None = None,
) -> dict:
    """Applies a scenario-specific class, weapon, and generated starting equipment
    to the active character at adventure start. Clears previous temporary equipment
    so the character gets a fresh scenario-tailored loadout."""
    char = db.get_character(user_id)
    if not char:
        raise ValueError("No active character found for user.")
    char_id = char["id"]

    from mechanics.system.input_sanitizer import sanitize_character_name, sanitize_prompt_lore
    from scenario_data import is_non_combat_scenario, is_anomalous_incursions_scenario
    char_class = sanitize_character_name(char_class or "Adventurer", max_len=60, fallback="Adventurer")
    class_description = sanitize_prompt_lore(class_description or "", max_len=1500)
    weapon_name = sanitize_character_name(weapon_name or "", max_len=80, fallback="")
    weapon_description = sanitize_prompt_lore(weapon_description or "", max_len=500)
    is_non_combat = is_non_combat_scenario(scenario)
    is_anomalous = is_anomalous_incursions_scenario(scenario)

    eff_attr = (str(attribute).strip().lower() if attribute else char.get("attribute")) if is_anomalous else None
    eff_arch = (str(combat_archetype).strip().lower() if combat_archetype else char.get("combat_archetype")) if is_anomalous else None
    eff_med = (str(ability_medium).strip().lower() if ability_medium else char.get("ability_medium")) if is_anomalous else None

    with get_conn() as conn:
        # Clear existing inventory/equipment for this character
        conn.execute(
            "DELETE FROM inventory WHERE character_id=? OR (character_id IS NULL AND user_id=?)",
            (char_id, user_id)
        )
        # Update character's scenario, class, description, and 3-axis resonance (NULL for non-anomalous)
        conn.execute(
            """UPDATE characters
               SET scenario=?, char_class=?, class_description=?, gold=?, hp=max_hp, mp=max_mp, status_effects='[]',
                   attribute=?, combat_archetype=?, ability_medium=?
               WHERE id=?""",
            (scenario, char_class, class_description, cd.STARTING_GOLD, eff_attr, eff_arch, eff_med, char_id)
        )

    from mechanics.combat.equipment import parse_equipment_metadata
    from mechanics.combat.items.envelope import serialize_item
    from mechanics.combat.items.weapons import generate_random_equipment as gen_weapon

    # 0. Seed 5 Fixed Innate Special Abilities for Anomalous Incursions before equipping gear
    if is_anomalous:
        try:
            innate_spells: list[str] = []
            if eff_attr and eff_arch and eff_med:
                try:
                    from mechanics.combat.spells.awakened_kits import build_awakened_kit_ids
                    innate_spells = list(build_awakened_kit_ids(eff_attr, eff_arch, eff_med))
                except ImportError:
                    innate_spells = []
            if not innate_spells:
                from mechanics.combat.spells.kits import get_anomalous_starting_innate_abilities
                innate_spells = list(get_anomalous_starting_innate_abilities(char_class, scenario, class_description))
            fresh_char = db.get_character(user_id) or char
            progress = db.get_skill_progress(fresh_char)
            progress["innate_spells"] = list(innate_spells)
            progress["equipped_granted_spells"] = []
            progress["empowered_granted_spells"] = []
            db.set_skill_progress(user_id, progress)
            db.set_learned_spells(user_id, list(innate_spells))
        except Exception as e:
            log.warning(f"Failed seeding innate anomalous spells for user {user_id}: {e}")

    # 1. Starting items / carried items
    if starting_items:
        for raw_entry in starting_items:
            if isinstance(raw_entry, dict):
                item_name = sanitize_character_name(str(raw_entry.get("name") or ""), max_len=80, fallback="")
                item_type = sanitize_character_name(str(raw_entry.get("item_type") or "Potion"), max_len=40, fallback="Potion")
                raw_eff = str(raw_entry.get("effect") or raw_entry.get("description") or "")
                effect = raw_eff if raw_eff.lstrip().startswith(("[ITEM_JSON]", "[GEAR_JSON]", "[SPELLBOOK_JSON]")) else sanitize_prompt_lore(raw_eff, max_len=500)
                try:
                    slot_cost = max(1, min(3, int(raw_entry.get("slot_cost", 1) or 1)))
                except (TypeError, ValueError):
                    slot_cost = 1
            elif isinstance(raw_entry, (tuple, list)) and len(raw_entry) >= 4:
                item_name = sanitize_character_name(str(raw_entry[0] or ""), max_len=80, fallback="")
                item_type = sanitize_character_name(str(raw_entry[1] or "Potion"), max_len=40, fallback="Potion")
                raw_eff = str(raw_entry[2] or "")
                effect = raw_eff if raw_eff.lstrip().startswith(("[ITEM_JSON]", "[GEAR_JSON]", "[SPELLBOOK_JSON]")) else sanitize_prompt_lore(raw_eff, max_len=500)
                try:
                    slot_cost = max(1, min(3, int(raw_entry[3] or 1)))
                except (TypeError, ValueError):
                    slot_cost = 1
            else:
                continue
            if not item_name or item_type in ("Weapon", "Armor", "Shield"):
                continue
            item_id = db.add_item(user_id, item_name, item_type, effect, slot_cost)
            default_slot = cd.DEFAULT_EQUIP_SLOT_FOR_ITEM_TYPE.get(item_type)
            if default_slot and item_id:
                try:
                    db.equip_item(user_id, item_id, default_slot)
                except ValueError as equip_err:
                    log.warning("Starter item %r could not be equipped to %s for user %s: %s", item_name, default_slot, user_id, equip_err)

    # 2. Starting armor / clothing / accessories from gear_map
    equipped_weapon = False
    if gear_map:
        from mechanics.combat.items.clothing import can_equip_item_in_scenario
        for slot, entry in gear_map.items():
            if not entry:
                continue

            # In non-combat scenarios, omit weapon, shield, and armor
            if is_non_combat and slot in ("Weapon", "Shield", "Armor"):
                continue

            # Preserve serialized procedural Weapon from preview if present; otherwise let weapon_name take priority
            has_serialized_weapon = (
                slot == "Weapon"
                and isinstance(entry, dict)
                and str(entry.get("effect") or "").startswith(("[GEAR_JSON]", "[ITEM_JSON]"))
            )
            if slot == "Weapon" and weapon_name and not has_serialized_weapon:
                continue

            if isinstance(entry, dict):
                # Generated item from new equipment generation system
                gear_name = sanitize_character_name(str(entry.get("name") or ""), max_len=80, fallback="")
                if not gear_name:
                    continue
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
                gear_type = sanitize_character_name(str(entry.get("item_type") or default_type), max_len=40, fallback=default_type)
                raw_gear_eff = str(entry.get("effect") or "")
                gear_effect = raw_gear_eff if raw_gear_eff.lstrip().startswith(("[ITEM_JSON]", "[GEAR_JSON]", "[SPELLBOOK_JSON]")) else sanitize_prompt_lore(raw_gear_eff, max_len=500)
                try:
                    gear_slot_cost = max(1, min(3, int(entry.get("slot_cost", 1) or 1)))
                except (TypeError, ValueError):
                    gear_slot_cost = 1
                cand_dict = dict(entry)
                cand_dict["name"] = gear_name
                cand_dict.setdefault("item_type", gear_type)
                cand_dict.setdefault("effect", gear_effect)
                if not can_equip_item_in_scenario(cand_dict, slot, scenario)[0]:
                    continue
                gear_id = db.add_item(user_id, gear_name, gear_type, gear_effect, gear_slot_cost)
                if gear_id:
                    try:
                        db.equip_item(user_id, gear_id, slot)
                        if slot == "Weapon":
                            equipped_weapon = True
                    except ValueError:
                        db.remove_item(user_id, gear_id)
                continue
            elif isinstance(entry, (tuple, list)) and len(entry) >= 2:
                if slot == "Weapon":
                    continue
                gear_name = sanitize_character_name(str(entry[0] or ""), max_len=80, fallback="")
                if not gear_name:
                    continue
                raw_gear_eff = str(entry[1] or "")
                gear_effect = raw_gear_eff if raw_gear_eff.lstrip().startswith(("[ITEM_JSON]", "[GEAR_JSON]", "[SPELLBOOK_JSON]")) else sanitize_prompt_lore(raw_gear_eff, max_len=500)
                try:
                    gear_slot_cost = max(1, min(3, int(entry[2]) if len(entry) > 2 else 1))
                except (TypeError, ValueError):
                    gear_slot_cost = 1
                if slot == "Shield":
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
                cand_dict = {
                    "name": gear_name,
                    "item_type": default_type,
                    "effect": gear_effect,
                    "slot_cost": gear_slot_cost,
                }
                if not can_equip_item_in_scenario(cand_dict, slot, scenario)[0]:
                    continue
                gear_id = db.add_item(user_id, gear_name, default_type, gear_effect, gear_slot_cost)
                if gear_id:
                    try:
                        db.equip_item(user_id, gear_id, slot)
                    except ValueError:
                        db.remove_item(user_id, gear_id)
                continue


    # 3. Starting weapon (utilizing new weapon generation system)
    if not is_non_combat and not equipped_weapon and (weapon_name or not equipped_weapon):
        target_w_name = weapon_name or f"{char_class or 'Adventurer'} Starter Weapon"
        w_item = gen_weapon(scenario=scenario, slot="Weapon", tier=3, name=target_w_name)
        weapon_id = db.add_item(user_id, w_item["name"], "Weapon", w_item["effect"], w_item.get("slot_cost", 1))
        if weapon_id:
            try:
                db.equip_item(user_id, weapon_id, "Weapon")
            except ValueError as equip_err:
                log.warning("Starter weapon %r could not be equipped for user %s: %s", w_item.get("name"), user_id, equip_err)

    if is_anomalous:
        try:
            from mechanics.combat.items.anomalous_gear import sync_equipped_anomalous_spells
            sync_equipped_anomalous_spells(user_id)
        except Exception as e:
            log.warning(f"Failed syncing anomalous spells after loadout for user {user_id}: {e}")

    return db.get_character(user_id)

def _apply_debug_stat_override(
    char: dict | None,
    *,
    settings: dict | None = None,
    session_id: int | None = None,
    active_pacts: list[dict] | None = None,
) -> dict | None:
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

    raw_app = char.get("appearance_json")
    app_dict = {}
    if isinstance(raw_app, str) and raw_app.strip():
        try:
            app_dict = json.loads(raw_app)
        except Exception:
            app_dict = {}
    elif isinstance(raw_app, dict):
        app_dict = dict(raw_app)

    if not app_dict:
        from mechanics.social.persona import normalize_appearance
        is_m = any(kw in str(char.get("gender", "")).lower() for kw in ("male", "man", "boy")) and "female" not in str(char.get("gender", "")).lower()
        default_app = {"penis_size": "Average"} if is_m else {"breast_size": "Modest B-Cup"}
        app_dict = normalize_appearance(default_app, gender=char.get("gender", ""), race=char.get("race", "human"), scen_key=char.get("scenario", "fantasy"))
    char["appearance"] = app_dict

    # Preserve unmodified SQLite base stats & max_hp before Pact or Debug projection
    char.setdefault(
        "_base_stats",
        {s: int(char.get(STAT_COLUMN[s]) or 1) for s in cd.STATS if STAT_COLUMN.get(s)},
    )
    char.setdefault("_base_max_hp", int(char.get("max_hp") or 100))

    if settings is None:
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
    else:
        eff_sid = session_id or char.get("active_session_id")
        if active_pacts is not None or eff_sid:
            try:
                pacts = (
                    active_pacts
                    if active_pacts is not None
                    else db.get_player_active_pacts(int(eff_sid), int(user_id), character_id=char.get("id"))
                )
                grudges = (
                    db.get_session_active_grudges(int(eff_sid), holder_id=int(user_id))
                    if eff_sid else []
                )
                if pacts or grudges:
                    from mechanics.pacts.appraisal import apply_active_pact_modifiers
                    char = apply_active_pact_modifiers(char, pacts, active_grudges=grudges)
            except Exception:
                pass
    return char

def apply_stat_mode(user_id: int, mode: str):
    db.update_settings(user_id, debug_stat_mode=mode)
    return db.get_character(user_id)

def update_character_appearance(character_id: int, appearance_dict: dict) -> dict | None:
    char = get_character_by_id(character_id)
    if not char:
        return None
    from mechanics.social.persona import normalize_appearance
    existing_app = dict(char.get("appearance") or {})
    char_gen = char.get("gender", "male")
    is_char_male = any(kw in str(char_gen).lower() for kw in ("male", "man", "boy")) and "female" not in str(char_gen).lower()
    for k, v in (appearance_dict or {}).items():
        if v is not None:
            existing_app[k] = v
    if is_char_male:
        existing_app.pop("breast_size", None)
    else:
        existing_app.pop("penis_size", None)
    norm_app = normalize_appearance(
        existing_app,
        gender=char_gen,
        race=char.get("race", "human"),
        scen_key=char.get("scenario", "fantasy"),
        desc=char.get("class_description", "")
    )
    if existing_app.get("origin_mode"):
        norm_app["origin_mode"] = existing_app["origin_mode"]
    if existing_app.get("student_grade"):
        norm_app["student_grade"] = existing_app["student_grade"]
    with get_conn() as conn:
        conn.execute(
            "UPDATE characters SET appearance_json=? WHERE id=?",
            (json.dumps(norm_app), character_id)
        )
    return get_character_by_id(character_id)

def get_character(user_id: int, session_id: int | None = None, *, settings: dict | None = None):
    user_id = resolve_canonical_user_id(user_id)
    with get_conn() as conn:
        row = None
        if session_id is not None:
            row = conn.execute(
                """SELECT c.*
                   FROM characters c
                   JOIN sessions s ON s.character_id = c.id
                   WHERE s.id = ? AND c.user_id = ?
                   LIMIT 1""",
                (int(session_id), user_id),
            ).fetchone()
            if not row:
                row = conn.execute(
                    """SELECT * FROM characters
                       WHERE user_id = ? AND active_session_id = ?
                       ORDER BY is_active DESC, id DESC
                       LIMIT 1""",
                    (user_id, int(session_id)),
                ).fetchone()
            if row:
                return _apply_debug_stat_override(dict(row), settings=settings, session_id=int(session_id))
        row = conn.execute("SELECT * FROM characters WHERE user_id=? AND is_active=1 LIMIT 1", (user_id,)).fetchone()
        if not row:
            row = conn.execute("SELECT * FROM characters WHERE user_id=? ORDER BY id DESC LIMIT 1", (user_id,)).fetchone()
            if row:
                conn.execute("UPDATE characters SET is_active=1 WHERE id=?", (row["id"],))
        return _apply_debug_stat_override(dict(row), settings=settings, session_id=session_id) if row else None

def get_session_player_character(session_id_or_session: int | dict | None) -> dict | None:
    """Retrieves the active player character associated with a session."""
    if not session_id_or_session:
        return None
    session_id = None
    character_id = None
    host_user_id = None
    if isinstance(session_id_or_session, dict):
        session_id = session_id_or_session.get("id")
        character_id = session_id_or_session.get("character_id")
        host_user_id = session_id_or_session.get("host_user_id")
    elif isinstance(session_id_or_session, (int, float)):
        session_id = int(session_id_or_session)

    if character_id:
        char = get_character_by_id(character_id)
        if char:
            return char

    if session_id:
        with get_conn() as conn:
            row = conn.execute(
                "SELECT c.* FROM characters c JOIN sessions s ON (s.character_id = c.id OR c.active_session_id = s.id) WHERE s.id = ? LIMIT 1",
                (session_id,)
            ).fetchone()
            if row:
                return _apply_debug_stat_override(dict(row))

    if host_user_id:
        char = get_character(host_user_id)
        if char:
            return char

    if session_id:
        with get_conn() as conn:
            s_row = conn.execute("SELECT character_id, host_user_id FROM sessions WHERE id = ?", (session_id,)).fetchone()
            if s_row:
                if s_row["character_id"]:
                    c = get_character_by_id(s_row["character_id"])
                    if c:
                        return c
                if s_row["host_user_id"]:
                    c = get_character(s_row["host_user_id"])
                    if c:
                        return c
    return None

def get_session_player_gender(session_id_or_session: int | dict | str | None) -> str:
    """Returns the canonical gender string of the player character in a session, or empty string.

    Optimized with fast in-memory extraction and single-query indexed projection,
    handling NULL character_id and active_session_id links safely.
    """
    if not session_id_or_session:
        return ""

    # Fast in-memory check if dictionary
    if isinstance(session_id_or_session, dict):
        for k in ("player_gender", "character_gender", "gender"):
            val = session_id_or_session.get(k)
            if val and str(val).strip():
                return str(val).strip()
        char_obj = session_id_or_session.get("character")
        if isinstance(char_obj, dict) and char_obj.get("gender"):
            return str(char_obj["gender"]).strip()
        session_id = session_id_or_session.get("id")
    else:
        try:
            session_id = int(session_id_or_session)
        except (ValueError, TypeError):
            session_id = None

    if session_id:
        try:
            with get_conn() as conn:
                row = conn.execute(
                    "SELECT c.gender FROM characters c "
                    "JOIN sessions s ON (s.character_id = c.id OR c.active_session_id = s.id) "
                    "WHERE s.id = ? AND c.gender IS NOT NULL AND c.gender != '' LIMIT 1",
                    (session_id,)
                ).fetchone()
                if row and row["gender"]:
                    return str(row["gender"]).strip()

                # Fallback to host user active character
                row2 = conn.execute(
                    "SELECT c.gender FROM characters c "
                    "JOIN sessions s ON s.host_user_id = c.user_id "
                    "WHERE s.id = ? AND c.is_active = 1 AND c.gender IS NOT NULL AND c.gender != '' LIMIT 1",
                    (session_id,)
                ).fetchone()
                if row2 and row2["gender"]:
                    return str(row2["gender"]).strip()
        except Exception as exc:
            log.debug("Failed fast resolution of character gender for session %s: %s", session_id, exc)

    # Safe fallback to full object resolution
    char = get_session_player_character(session_id_or_session)
    if char and char.get("gender"):
        return str(char["gender"]).strip()
    return ""

def get_character_by_id(character_id: int):
    with get_conn() as conn:
        row = conn.execute("SELECT * FROM characters WHERE id=?", (character_id,)).fetchone()
        return _apply_debug_stat_override(dict(row)) if row else None

def get_user_characters(user_id: int) -> list[dict]:
    user_id = resolve_canonical_user_id(user_id)
    with get_conn() as conn:
        rows = conn.execute("SELECT * FROM characters WHERE user_id=? ORDER BY id ASC", (user_id,)).fetchall()
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

    with UnitOfWork() as conn:
        conn.execute("UPDATE characters SET is_active=0 WHERE user_id=?", (user_id,))
        conn.execute("UPDATE characters SET is_active=1 WHERE id=?", (target["id"],))
    return get_character_by_id(target["id"])

def set_character_active_session(character_id: int, session_id: int | None) -> bool:
    """Updates the active session ID for a character (Invariant 3)."""
    if not character_id:
        return False
    with get_conn() as conn:
        cur = conn.execute("UPDATE characters SET active_session_id=? WHERE id=?", (session_id, character_id))
        return cur.rowcount > 0

def delete_character(user_id: int, character_id: int = None) -> bool:
    with UnitOfWork() as conn:
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
        owned_sess_rows = conn.execute(
            "SELECT id FROM sessions WHERE character_id=?",
            (target_id,),
        ).fetchall()
        candidate_sids = {int(r["id"]) for r in owned_sess_rows if r and r["id"]}
        if active_sess_id:
            candidate_sids.add(int(active_sess_id))

        conn.execute("DELETE FROM inventory WHERE character_id=?", (target_id,))
        conn.execute("DELETE FROM adventure_saves WHERE character_id=?", (target_id,))
        conn.execute("DELETE FROM characters WHERE id=?", (target_id,))

        remaining = conn.execute("SELECT id FROM characters WHERE user_id=? ORDER BY id DESC", (user_id,)).fetchall()
        if not remaining:
            user_sessions = conn.execute("SELECT session_id FROM session_members WHERE user_id=?", (user_id,)).fetchall()
            for us in user_sessions:
                if us and us["session_id"]:
                    candidate_sids.add(int(us["session_id"]))
            conn.execute("DELETE FROM inventory WHERE user_id=?", (user_id,))
            conn.execute("DELETE FROM user_settings WHERE user_id=?", (user_id,))
        elif was_active:
            conn.execute("UPDATE characters SET is_active=1 WHERE id=?", (remaining[0]["id"],))

        for sid in sorted(candidate_sids):
            same_user_other_char = conn.execute(
                "SELECT id FROM characters WHERE user_id=? AND active_session_id=? ORDER BY id DESC LIMIT 1",
                (user_id, sid),
            ).fetchone()
            other_member_rows = conn.execute(
                "SELECT user_id FROM session_members WHERE session_id=? AND user_id!=? ORDER BY COALESCE(joined_at, 0) ASC, rowid ASC",
                (sid, user_id),
            ).fetchall()
            other_uids = [int(r["user_id"]) for r in other_member_rows if r and r["user_id"] is not None]
            if not other_uids:
                other_active_rows = conn.execute(
                    "SELECT user_id FROM characters WHERE active_session_id=? AND user_id!=? ORDER BY id ASC",
                    (sid, user_id),
                ).fetchall()
                other_uids = [int(r["user_id"]) for r in other_active_rows if r and r["user_id"] is not None]

            if same_user_other_char:
                same_other_cid = int(same_user_other_char["id"])
                conn.execute(
                    "UPDATE OR IGNORE contacts SET character_id=? WHERE session_id=? AND character_id=?",
                    (same_other_cid, sid, target_id),
                )
                conn.execute(
                    """UPDATE world_events
                       SET implicated_contact_id = (
                           SELECT c_keep.id FROM contacts c_old
                           JOIN contacts c_keep
                             ON c_keep.session_id = c_old.session_id
                            AND c_keep.npc_id = c_old.npc_id
                            AND c_keep.character_id = ?
                           WHERE c_old.id = world_events.implicated_contact_id
                             AND c_old.session_id = ?
                             AND c_old.character_id = ?
                           LIMIT 1
                       )
                       WHERE session_id = ?
                         AND implicated_contact_id IN (
                             SELECT id FROM contacts WHERE session_id = ? AND character_id = ?
                         )""",
                    (same_other_cid, sid, target_id, sid, sid, target_id),
                )
                conn.execute(
                    "UPDATE sessions SET character_id=?, updated_at=? WHERE id=? AND character_id=?",
                    (same_other_cid, time.time(), sid, target_id),
                )
                continue

            if not other_uids:
                conn.execute("DELETE FROM session_members WHERE session_id=?", (sid,))
                _delete_session_records(conn, sid)
            else:
                conn.execute("DELETE FROM session_members WHERE session_id=? AND user_id=?", (sid, user_id))
                sess_row = conn.execute(
                    "SELECT host_user_id, character_id, turn_order, current_turn_index, pending_picks_json FROM sessions WHERE id=?",
                    (sid,),
                ).fetchone()
                if sess_row:
                    try:
                        raw_order = json.loads(sess_row["turn_order"] or "[]")
                    except Exception:
                        raw_order = []
                    clean_old = [int(u) for u in raw_order if u is not None]
                    old_idx = int(sess_row["current_turn_index"] or 0)
                    old_active_uid = clean_old[old_idx % len(clean_old)] if clean_old else None
                    new_order = [u for u in clean_old if u != int(user_id)]
                    if not new_order:
                        new_order = list(dict.fromkeys(other_uids))
                    if not new_order:
                        new_turn_idx = 0
                    elif old_active_uid is not None and old_active_uid in new_order:
                        new_turn_idx = new_order.index(old_active_uid)
                    else:
                        norm_old_idx = (old_idx % len(clean_old)) if clean_old else 0
                        new_turn_idx = norm_old_idx % len(new_order)

                    try:
                        picks = json.loads(sess_row["pending_picks_json"] or "{}")
                        if not isinstance(picks, dict):
                            picks = {}
                    except Exception:
                        picks = {}
                    picks.pop(str(user_id), None)

                    new_host_uid = sess_row["host_user_id"]
                    new_char_id = sess_row["character_id"]
                    if new_host_uid is None or int(new_host_uid) == int(user_id):
                        new_host_uid = int(other_uids[0])
                    if (
                        new_char_id is None
                        or int(new_char_id) == int(target_id)
                        or (sess_row["host_user_id"] is not None and int(sess_row["host_user_id"]) == int(user_id))
                    ):
                        lookup_uid = int(new_host_uid) if new_host_uid is not None else int(other_uids[0])
                        host_char = (
                            conn.execute(
                                "SELECT id FROM characters WHERE user_id=? AND active_session_id=? ORDER BY id DESC LIMIT 1",
                                (lookup_uid, sid),
                            ).fetchone()
                            or conn.execute(
                                "SELECT id FROM characters WHERE user_id=? AND is_active=1 ORDER BY id DESC LIMIT 1",
                                (lookup_uid,),
                            ).fetchone()
                            or conn.execute(
                                "SELECT id FROM characters WHERE user_id=? ORDER BY id DESC LIMIT 1",
                                (lookup_uid,),
                            ).fetchone()
                        )
                        new_char_id = int(host_char["id"]) if host_char else None

                    if new_char_id is not None:
                        conn.execute(
                            "UPDATE OR IGNORE contacts SET character_id=? WHERE session_id=? AND character_id=?",
                            (new_char_id, sid, target_id),
                        )
                        conn.execute(
                            """UPDATE world_events
                               SET implicated_contact_id = (
                                   SELECT c_keep.id FROM contacts c_old
                                   JOIN contacts c_keep
                                     ON c_keep.session_id = c_old.session_id
                                    AND c_keep.npc_id = c_old.npc_id
                                    AND c_keep.character_id = ?
                                   WHERE c_old.id = world_events.implicated_contact_id
                                     AND c_old.session_id = ?
                                     AND c_old.character_id = ?
                                   LIMIT 1
                               )
                               WHERE session_id = ?
                                 AND implicated_contact_id IN (
                                     SELECT id FROM contacts WHERE session_id = ? AND character_id = ?
                                 )""",
                            (new_char_id, sid, target_id, sid, sid, target_id),
                        )

                    conn.execute(
                        """UPDATE sessions
                           SET host_user_id=?, character_id=?, turn_order=?, current_turn_index=?, pending_picks_json=?, updated_at=?
                           WHERE id=?""",
                        (
                            new_host_uid,
                            new_char_id,
                            json.dumps(new_order),
                            new_turn_idx,
                            json.dumps(picks),
                            time.time(),
                            sid,
                        ),
                    )

        conn.execute("DELETE FROM contacts WHERE character_id=?", (target_id,))
        if not remaining:
            conn.execute("DELETE FROM session_members WHERE user_id=?", (user_id,))
        return True

def update_character_fields(user_id: int, **fields):
    if not fields:
        return
    char = db.get_character(user_id)
    if not char:
        return
    from mechanics.system.input_sanitizer import sanitize_character_name, sanitize_prompt_lore
    if "name" in fields and fields["name"] is not None:
        fields["name"] = sanitize_character_name(str(fields["name"]), max_len=60, fallback=char.get("name") or "Adventurer")
    if "char_class" in fields and fields["char_class"] is not None:
        fields["char_class"] = sanitize_character_name(str(fields["char_class"]), max_len=60, fallback="Adventurer")
    if "gender" in fields and fields["gender"] is not None:
        fields["gender"] = sanitize_character_name(str(fields["gender"]), max_len=50, fallback="Male")
    if "race" in fields and fields["race"] is not None:
        fields["race"] = sanitize_character_name(str(fields["race"]), max_len=60, fallback="human")
    if "class_description" in fields and fields["class_description"] is not None:
        fields["class_description"] = sanitize_prompt_lore(str(fields["class_description"]), max_len=1500)
    if "race_description" in fields and fields["race_description"] is not None:
        fields["race_description"] = sanitize_prompt_lore(str(fields["race_description"]), max_len=600)
    cols = ", ".join(f"{k}=?" for k in fields)
    with get_conn() as conn:
        conn.execute(f"UPDATE characters SET {cols} WHERE id=?",
                     (*fields.values(), char["id"]))

def apply_hp_mp_delta(
    user_id: int,
    hp_delta: int = 0,
    mp_delta: int = 0,
    gold_delta: int = 0,
    temp_hp_delta: int = 0,
    *,
    character_id: int | None = None,
):
    char = None
    if character_id:
        with get_conn() as conn:
            row = conn.execute("SELECT * FROM characters WHERE id=?", (int(character_id),)).fetchone()
            char = _apply_debug_stat_override(dict(row)) if row else None
    if not char:
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
        if temp_hp_delta > 0:
            new_temp_hp = max(current_temp_hp, temp_hp_delta)
        else:
            new_temp_hp = max(0, new_temp_hp + temp_hp_delta)
        
    new_mp = max(0, min(char.get("max_mp", 50), char.get("mp", 0) + mp_delta))
    new_gold = max(0, char.get("gold", 0) + gold_delta)
    if character_id:
        with get_conn() as conn:
            conn.execute(
                "UPDATE characters SET hp=?, temp_hp=?, mp=?, gold=? WHERE id=?",
                (new_hp, new_temp_hp, new_mp, new_gold, int(char["id"])),
            )
            updated_row = conn.execute("SELECT * FROM characters WHERE id=?", (int(char["id"]),)).fetchone()
            return _apply_debug_stat_override(dict(updated_row)) if updated_row else None
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

def add_status_effect(user_id: int, effect: str | dict):
    effects = get_status_effects(user_id)
    eff_str = effect if isinstance(effect, str) else effect.get("name", str(effect))
    if not any((e if isinstance(e, str) else e.get("name", "")) == eff_str for e in effects):
        effects.append(effect)
        set_status_effects(user_id, effects)

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
    base_val = int((char.get("_base_stats") or {}).get(stat, char[col]))
    new_value = min(cd.MAX_STAT_VALUE, base_val + amount)
    if new_value == base_val:
        return
    db.update_character_fields(user_id, **{col: new_value})

    if stat == "END":
        old_base_max_hp = int(char.get("_base_max_hp") or char["max_hp"])
        old_max_mp = char["max_mp"]
        new_base_max_hp, new_max_mp = cd.derive_hp(new_value), cd.derive_mp(new_value)
        hp_gain, mp_gain = new_base_max_hp - old_base_max_hp, new_max_mp - old_max_mp
        eff_char = db.get_character(user_id)
        eff_cap_hp = int(eff_char["max_hp"]) if eff_char else new_base_max_hp
        db.update_character_fields(
            user_id,
            max_hp=new_base_max_hp,
            max_mp=new_max_mp,
            hp=min(eff_cap_hp, max(0, char["hp"] + hp_gain)),
            mp=min(new_max_mp, char["mp"] + mp_gain),
        )

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
    base_val = int((char.get("_base_stats") or {}).get(stat, char[col]))
    if base_val >= cd.MAX_STAT_VALUE:
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
    base_stats = char.get("_base_stats") or {}
    str_val = int(stats.get('str') or stats.get('STR') or base_stats.get('STR', char.get('str_', 1)))
    per_val = int(stats.get('per') or stats.get('PER') or base_stats.get('PER', char.get('per_', 1)))
    end_val = int(stats.get('end') or stats.get('END') or base_stats.get('END', char.get('end_', 1)))
    cha_val = int(stats.get('cha') or stats.get('CHA') or base_stats.get('CHA', char.get('cha', 1)))
    int_val = int(stats.get('int') or stats.get('INT') or base_stats.get('INT', char.get('int_', 1)))
    agi_val = int(stats.get('agi') or stats.get('AGI') or base_stats.get('AGI', char.get('agi', 1)))
    luk_val = int(stats.get('luk') or stats.get('LUK') or base_stats.get('LUK', char.get('luk', 1)))
    
    max_hp = int(stats.get('max_hp')) if stats.get('max_hp') is not None else cd.calculate_max_hp(end_val)
    max_mp = int(stats.get('max_mana') or stats.get('max_mp')) if (stats.get('max_mana') is not None or stats.get('max_mp') is not None) else cd.calculate_max_mp(end_val)
    current_hp = int(char.get('hp') if char.get('hp') is not None else max_hp)
    current_mp = int(char.get('mp') if char.get('mp') is not None else max_mp)
    hp_val = int(stats.get('hp')) if stats.get('hp') is not None else min(current_hp, max_hp)
    mp_val = int(stats.get('mana') or stats.get('mp')) if (stats.get('mana') is not None or stats.get('mp') is not None) else min(current_mp, max_mp)
    
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
        hp=hp_val,
        max_mp=max_mp,
        mp=mp_val
    )


def save_discord_user(user_id: int, username: str = "", display_name: str = "") -> bool:
    if not user_id:
        return False
    with get_conn() as conn:
        conn.execute(
            """INSERT INTO discord_users (user_id, username, display_name, updated_at)
               VALUES (?, ?, ?, ?)
               ON CONFLICT(user_id) DO UPDATE SET
               username=COALESCE(NULLIF(excluded.username, ''), discord_users.username),
               display_name=COALESCE(NULLIF(excluded.display_name, ''), discord_users.display_name),
               updated_at=excluded.updated_at""",
            (int(user_id), (username or "").strip(), (display_name or "").strip(), time.time())
        )
    return True


def find_user_id_by_name(query: str) -> Optional[int]:
    if not query:
        return None
    q = str(query).strip()
    if not q:
        return None
    if q.startswith("<@") and q.endswith(">"):
        digits = "".join(ch for ch in q if ch.isdigit())
        if digits:
            return resolve_canonical_user_id(int(digits))
    clean_q = q.lstrip("@").strip()
    with get_conn() as conn:
        # 1. Exact or case-insensitive match in discord_users
        row = conn.execute(
            "SELECT user_id FROM discord_users WHERE LOWER(username) = LOWER(?) OR LOWER(display_name) = LOWER(?) OR LOWER(username) = LOWER(?) OR LOWER(display_name) = LOWER(?) LIMIT 1",
            (q, q, clean_q, clean_q)
        ).fetchone()
        if row:
            return row["user_id"]
        # 2. Check characters table for character name
        char_row = conn.execute(
            "SELECT user_id FROM characters WHERE LOWER(name) = LOWER(?) OR LOWER(name) = LOWER(?) LIMIT 1",
            (q, clean_q)
        ).fetchone()
        if char_row:
            return char_row["user_id"]
    return None


def resolve_canonical_user_id(user_id: Any) -> int:
    """Resolves a user_id (even if precision-truncated by JS IEEE-754 float rounding)
    to the exact canonical user_id present in the database.
    """
    if not user_id:
        return 0
    try:
        raw_id = int(str(user_id).strip())
    except (ValueError, TypeError):
        return 0

    with get_conn() as conn:
        # 1. Exact match in characters or discord_users
        row = conn.execute("SELECT user_id FROM characters WHERE user_id = ? LIMIT 1", (raw_id,)).fetchone()
        if row:
            return row["user_id"]
        row_du = conn.execute("SELECT user_id FROM discord_users WHERE user_id = ? LIMIT 1", (raw_id,)).fetchone()
        if row_du:
            return row_du["user_id"]
        # 2. Check if within float precision rounding window (±128 for 64-bit float around 10^17 - 10^19)
        if raw_id > 10**16:
            near_row = conn.execute(
                "SELECT user_id FROM characters WHERE user_id BETWEEN ? AND ? LIMIT 1",
                (raw_id - 128, raw_id + 128)
            ).fetchone()
            if near_row:
                return near_row["user_id"]
            near_du = conn.execute(
                "SELECT user_id FROM discord_users WHERE user_id BETWEEN ? AND ? LIMIT 1",
                (raw_id - 128, raw_id + 128)
            ).fetchone()
            if near_du:
                return near_du["user_id"]
    return raw_id


def get_discord_user(user_id: int) -> Optional[dict]:
    user_id = resolve_canonical_user_id(user_id)
    with get_conn() as conn:
        row = conn.execute("SELECT * FROM discord_users WHERE user_id = ? LIMIT 1", (int(user_id),)).fetchone()
        return dict(row) if row else None


def delete_character_by_id(user_id: int, character_id: int) -> bool:
    return delete_character(user_id, character_id)


def get_character_3axis(user_id: int) -> dict[str, Optional[str]]:
    """Returns the active character's 3-axis awakened resonance fields (all None for non-anomalous characters)."""
    char = get_character(user_id)
    if not char:
        return {"attribute": None, "combat_archetype": None, "ability_medium": None}
    return {
        "attribute": char.get("attribute") or None,
        "combat_archetype": char.get("combat_archetype") or None,
        "ability_medium": char.get("ability_medium") or None,
    }


def set_character_3axis(
    user_id: int,
    attribute: Optional[str] = None,
    combat_archetype: Optional[str] = None,
    ability_medium: Optional[str] = None,
) -> bool:
    """Updates the active character's 3-axis awakened resonance columns."""
    char = get_character(user_id)
    if not char:
        return False
    attr_val = str(attribute).strip().lower() if attribute else None
    arch_val = str(combat_archetype).strip().lower() if combat_archetype else None
    med_val = str(ability_medium).strip().lower() if ability_medium else None
    with get_conn() as conn:
        conn.execute(
            """UPDATE characters
               SET attribute = ?, combat_archetype = ?, ability_medium = ?
               WHERE id = ?""",
            (attr_val, arch_val, med_val, char["id"]),
        )
    if attr_val and arch_val and med_val:
        try:
            from mechanics.combat.spells.awakened_kits import build_awakened_kit_ids
            from mechanics.combat.items.anomalous_gear import sync_equipped_anomalous_spells
            refreshed = get_character(user_id)
            prog = db.get_skill_progress(refreshed)
            innate = list(build_awakened_kit_ids(attr_val, arch_val, med_val))
            prog["innate_spells"] = innate
            db.set_skill_progress(user_id, prog)
            db.set_learned_spells(user_id, innate + [s for s in (prog.get("equipped_granted_spells") or []) if s not in innate])
            sync_equipped_anomalous_spells(user_id)
        except Exception as e:
            log.warning("Failed re-syncing innate 3-axis spells in set_character_3axis for user %s: %s", user_id, e)
    return True


