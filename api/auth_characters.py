import inspect
import random
from typing import Optional
from fastapi import APIRouter, HTTPException

import db
from db import adb
import scenario_data
import character_data as cd
from .deps import (
    logger,
    GuestAuthRequest,
    DiscordAuthRequest,
    CharacterCreateRequest,
    PreviewGearRequest,
    RegenerateGearRequest,
    CharacterSwitchRequest,
    SpendStatPointRequest,
)

if not hasattr(db, "delete_character_by_id") and hasattr(db, "delete_character"):
    db.delete_character_by_id = db.delete_character


async def _default_generate_class_starter_equipment(
    char_class: str,
    scenario: str = "fantasy",
    stats: Optional[dict] = None,
    class_description: str = "",
    gender: str = "Male",
    race: str = "Human",
    force_dynamic: bool = False,
    **kwargs,
) -> dict:
    """Generates starter equipment loadout with optional LLM dynamic generation and graceful fallback."""
    if force_dynamic or (class_description and len(class_description.strip()) > 3):
        try:
            import game_engine
            if hasattr(game_engine, "generate_custom_starter_gear"):
                res = await game_engine.generate_custom_starter_gear(
                    char_class=char_class,
                    class_description=class_description or "",
                    scenario=scenario or "fantasy",
                    gender=gender or "Male",
                    race=race or "Human",
                )
                if isinstance(res, dict) and res:
                    return res
        except Exception as e:
            logger.warning(f"Dynamic starter gear generation fallback: {e}")

    try:
        return cd.generate_starter_equipment_loadout(
            scenario=scenario or "fantasy",
            char_class=char_class or "Warrior",
            gender=gender or "Male",
            race=race or "Human",
            tier=3,
        )
    except Exception as e:
        logger.warning(f"Standard starter equipment loadout fallback: {e}")
        return {}


if not hasattr(cd, "generate_class_starter_equipment"):
    cd.generate_class_starter_equipment = _default_generate_class_starter_equipment


async def _invoke_starter_equipment_generator(
    chosen_class: str,
    scen_key: str,
    stats: dict,
    class_description: str = "",
    gender: str = "Male",
    force_dynamic: bool = False,
) -> dict:
    gen_fn = getattr(cd, "generate_class_starter_equipment", _default_generate_class_starter_equipment)
    try:
        try:
            res = gen_fn(
                chosen_class,
                scen_key,
                stats=stats,
                class_description=class_description,
                gender=gender,
                force_dynamic=force_dynamic,
            )
        except TypeError:
            res = gen_fn(
                chosen_class,
                scen_key,
                stats=stats,
                class_description=class_description,
                gender=gender,
            )
        if inspect.isawaitable(res):
            res = await res
        if isinstance(res, dict):
            return res
    except Exception as e:
        logger.warning(f"Starter equipment generator failed, falling back: {e}")
        try:
            return cd.generate_starter_equipment_loadout(
                scenario=scen_key,
                char_class=chosen_class,
                gender=gender,
                tier=3,
            )
        except Exception:
            pass
    return {}


def _resolve_slot_item_type(slot: str, raw_type: Optional[str] = None) -> str:
    """Maps an equipment slot to the canonical item_type expected by db.equip_item."""
    if slot == "Weapon":
        return "Weapon"
    if slot == "Shield":
        return "Shield"
    if slot in ("Top", "Bottom"):
        return "Clothing"
    if slot == "Armor":
        return "Armor"
    if slot == "Head":
        return "Headwear"
    if slot == "Gloves":
        return "Gloves"
    if slot == "Shoes":
        return "Shoes"
    if slot.startswith("Accessory"):
        return "Accessory"
    return raw_type or "Armor"


def _normalize_loadout_dict(loadout: dict) -> dict:
    """Normalizes any starter gear dictionary into slot -> {name, description, effect, slot_cost, item_type}."""
    if not isinstance(loadout, dict):
        return {}
    normalized = {}
    for slot, item_data in loadout.items():
        if not item_data or slot not in cd.EQUIPMENT_SLOTS:
            continue
        canonical_type = _resolve_slot_item_type(slot)
        if isinstance(item_data, dict):
            it_name = str(item_data.get("name") or "").strip()
            if not it_name:
                continue
            meta = item_data.get("metadata") or {}
            desc = (
                item_data.get("description")
                or meta.get("description")
                or ""
            )
            if not desc and isinstance(meta, dict):
                arch = str(meta.get("archetype") or "").replace("_", " ").title()
                tier_name = str(meta.get("tier_name") or "Standard")
                mods = meta.get("stat_modifiers") or {}
                mod_parts = [f"{k.upper().replace('_', ' ')} +{v}" for k, v in list(mods.items())[:3] if v]
                if mod_parts:
                    desc = f"{tier_name} {arch} ({', '.join(mod_parts)})".strip()
                elif arch:
                    desc = f"{tier_name} {arch} gear."
            raw_eff = str(item_data.get("effect") or "")
            if not desc and raw_eff and not raw_eff.startswith("["):
                desc = raw_eff
            it_effect = raw_eff or desc or "Starter gear"
            it_cost = int(item_data.get("slot_cost", 1) or 1)
            normalized[slot] = {
                "name": it_name,
                "description": desc or "Class-tailored starter equipment.",
                "effect": it_effect,
                "slot_cost": it_cost,
                "item_type": canonical_type,
            }
        elif isinstance(item_data, (list, tuple)) and len(item_data) >= 1:
            it_name = str(item_data[0] or "").strip()
            if not it_name:
                continue
            desc = str(item_data[1]).strip() if len(item_data) >= 2 and item_data[1] else "Class starter gear."
            it_cost = int(item_data[2]) if len(item_data) >= 3 and isinstance(item_data[2], (int, float)) else 1
            normalized[slot] = {
                "name": it_name,
                "description": desc,
                "effect": desc,
                "slot_cost": it_cost,
                "item_type": canonical_type,
            }
        elif isinstance(item_data, str) and item_data.strip():
            normalized[slot] = {
                "name": item_data.strip(),
                "description": "Starter gear",
                "effect": "Starter gear",
                "slot_cost": 1,
                "item_type": canonical_type,
            }
    return normalized


async def _equip_starter_loadout_dict(user_id: int, loadout: dict, skip_weapon: bool = False):
    if not isinstance(loadout, dict):
        return
    for slot, item_data in loadout.items():
        if skip_weapon and slot == "Weapon":
            continue
        if not item_data or slot not in cd.EQUIPMENT_SLOTS:
            continue
        canonical_type = _resolve_slot_item_type(slot)
        if isinstance(item_data, dict):
            it_name = (item_data.get("name") or "").strip()
            it_type = canonical_type
            it_effect = item_data.get("effect") or item_data.get("description") or "Starter gear"
            it_cost = int(item_data.get("slot_cost", 1) or 1)
        elif isinstance(item_data, (list, tuple)) and len(item_data) >= 1:
            it_name = str(item_data[0] or "").strip()
            it_type = canonical_type
            it_effect = str(item_data[1]).strip() if len(item_data) >= 2 and item_data[1] else "Starter gear"
            it_cost = int(item_data[2]) if len(item_data) >= 3 and isinstance(item_data[2], (int, float)) else 1
        else:
            it_name = str(item_data).strip()
            it_type = canonical_type
            it_effect = "Starter gear"
            it_cost = 1
        if not it_name:
            continue
        item_id = await adb(
            db.add_item,
            user_id,
            it_name,
            item_type=it_type,
            effect=it_effect,
            slot_cost=it_cost,
            force=True,
        )
        await adb(db.equip_item, user_id, item_id, slot)


def _build_starting_weapon_effect(weapon_name: str, weapon_desc: str, scen_key: str) -> str:
    try:
        import mechanics.combat.equipment as eq_mod
        if hasattr(eq_mod, "classify_weapon_profile") and hasattr(eq_mod, "format_gear_effect_string"):
            prof = eq_mod.classify_weapon_profile(weapon_name, weapon_desc or "", scenario=scen_key)
            return eq_mod.format_gear_effect_string(prof, description=weapon_desc or "Starting weapon")
    except Exception:
        pass
    try:
        from mechanics.combat.items.weapons import generate_random_equipment as gen_weapon
        from mechanics.combat.items.envelope import serialize_item
        w_item = gen_weapon(scenario=scen_key, slot="Weapon", tier=3, name=weapon_name)
        if isinstance(w_item, dict) and w_item.get("metadata"):
            meta = dict(w_item["metadata"])
            if weapon_desc:
                meta["description"] = weapon_desc
            return serialize_item(meta)
        if isinstance(w_item, dict) and w_item.get("effect"):
            return w_item["effect"]
    except Exception:
        pass
    return weapon_desc.strip() if (weapon_desc and weapon_desc.strip()) else "Starting weapon"


router = APIRouter()


@router.post("/api/auth/guest")
async def auth_guest(req: GuestAuthRequest):
    """Generates a random unique guest user_id for instant browser play."""
    guest_id = random.randint(900_000_000_000_000_000, 999_000_000_000_000_000)
    raw_name = (req.display_name or req.guest_name or "").strip()
    name = (
        raw_name
        if (raw_name and raw_name != "Adventurer")
        else f"Guest-{str(guest_id)[-4:]}"
    )
    return {
        "user_id": guest_id,
        "username": name,
        "display_name": name,
        "is_guest": True
    }


@router.post("/api/auth/discord")
async def auth_discord(req: DiscordAuthRequest):
    """Authenticates or resolves a Discord User ID / Username to load existing Discord characters."""
    val = (req.user_id_or_name or req.discord_id or "").strip()
    if not val:
        raise HTTPException(status_code=400, detail="Discord User ID or username is required")
    if val.isdigit():
        user_id = int(val)
    else:
        user_id = abs(hash(val)) % (10**18)

    char = await adb(db.get_character, user_id)
    return {
        "user_id": user_id,
        "username": val,
        "display_name": val,
        "has_character": char is not None,
        "character_name": char["name"] if char else None,
        "is_guest": False
    }


@router.get("/api/scenarios")
async def get_scenarios():
    """Returns available scenario templates."""
    try:
        scenarios = scenario_data.load_scenarios()
        scenario_list = [
            {
                "key": k,
                "name": v.get("name", k),
                "emoji": v.get("emoji", "🗺️"),
                "description": v.get("description", ""),
            }
            for k, v in (scenarios.items() if isinstance(scenarios, dict) else [])
        ]
        return {"scenarios": scenarios, "scenario_list": scenario_list}
    except Exception as e:
        logger.error(f"Error loading scenarios: {e}")
        return {
            "scenarios": {"fantasy": {"name": "Classic Fantasy", "description": "High fantasy realm"}},
            "scenario_list": [{"key": "fantasy", "name": "Classic Fantasy", "emoji": "🏰", "description": "High fantasy realm"}],
        }


@router.get("/api/tags")
async def get_tags():
    """Returns available tags dictionary."""
    try:
        tags = scenario_data.load_tags()
        return {"tags": tags}
    except Exception as e:
        logger.error(f"Error loading tags: {e}")
        return {"tags": {}}


@router.get("/api/class-templates")
async def get_class_templates(scenario: Optional[str] = None, tags: Optional[str] = None):
    """Returns preset class options and starting weapons, supporting custom multi-tag scenarios and all-genre browsing."""
    raw_templates = cd.load_class_templates()
    all_classes = {}
    for s_key, cls_dict in raw_templates.items():
        if isinstance(cls_dict, dict):
            for c_name, c_info in cls_dict.items():
                if isinstance(c_info, dict):
                    all_classes[c_name] = {**c_info, "source_scenario": s_key}

    all_starting_weapons = cd.get_all_starting_weapons()
    resolved_scenario = scenario or "fantasy"

    if not scenario or scenario == "all":
        classes = all_classes
        starting_weapons = all_starting_weapons
    elif scenario == "custom" or (tags and tags.strip()):
        raw_tag_list = [t.strip() for t in (tags or "").split(",") if t.strip()]
        valid_tags = scenario_data.resolve_tag_keys(raw_tag_list) if raw_tag_list else ["fantasy"]
        resolved_scenario = scenario_data.resolve_scenario_or_custom_key(valid_tags)

        matched_scen_keys = []
        for t in valid_tags:
            t_key = None
            if t in raw_templates:
                t_key = t
            elif cd.TAG_TO_TEMPLATE_KEY.get(t) in raw_templates:
                t_key = cd.TAG_TO_TEMPLATE_KEY[t]
            else:
                resolved_t = cd._resolve_template_scenario_key(t, raw_templates)
                if resolved_t in raw_templates and (resolved_t != "fantasy" or t == "fantasy"):
                    t_key = resolved_t
            if t_key and t_key not in matched_scen_keys:
                matched_scen_keys.append(t_key)

        if not matched_scen_keys:
            fallback_key = cd._resolve_template_scenario_key(resolved_scenario, raw_templates)
            matched_scen_keys.append(fallback_key)

        classes = {}
        starting_weapons = []
        seen_weapons = set()
        for m_key in matched_scen_keys:
            for c_name, c_info in (raw_templates.get(m_key) or {}).items():
                if isinstance(c_info, dict) and c_name not in classes:
                    classes[c_name] = {**c_info, "source_scenario": m_key}
            for w in cd.get_starting_weapons(m_key):
                w_name = w.get("name") if isinstance(w, dict) else w
                if w_name and w_name not in seen_weapons:
                    seen_weapons.add(w_name)
                    starting_weapons.append(w)

        if not classes:
            classes = all_classes
        if not starting_weapons:
            starting_weapons = all_starting_weapons
    else:
        target_key = cd._resolve_template_scenario_key(scenario, raw_templates)
        raw_scen_classes = cd.get_class_templates(scenario)
        classes = {
            c_name: ({**c_info, "source_scenario": target_key} if isinstance(c_info, dict) else c_info)
            for c_name, c_info in (raw_scen_classes or {}).items()
        }
        starting_weapons = cd.get_starting_weapons(scenario)

    race_options = [
        "Human", "Elf", "Dwarf", "Dark Elf", "Orc", "Goblin", "Gnome", "Halfling",
        "Beastfolk / Anthro", "Half-Beast / Hybrid", "Cyborg", "Android / Synth",
        "Mutant", "Alien", "Dragonkin", "Angel", "Demon", "Tiefling"
    ]
    return {
        "classes": classes,
        "starting_weapons": starting_weapons,
        "all_classes": all_classes,
        "all_starting_weapons": all_starting_weapons,
        "resolved_scenario": resolved_scenario,
        "gender_options": cd.GENDER_OPTIONS,
        "race_options": race_options,
        "equipment_slots": cd.EQUIPMENT_SLOTS,
        "stat_names": cd.STAT_NAMES,
        "stat_effects": cd.STAT_EFFECTS,
        "base_stat_value": cd.BASE_STAT_VALUE,
        "point_buy_pool": cd.POINT_BUY_POOL,
        "max_total_points": len(cd.STATS) * cd.BASE_STAT_VALUE + cd.POINT_BUY_POOL,
    }


@router.post("/api/character/preview-gear")
async def preview_character_gear(req: PreviewGearRequest):
    """Generates or retrieves a preview of starting equipment for Character Creation Studio without requiring an existing DB character."""
    chosen_class = (req.char_class or "Warrior").strip()
    scen_key = req.scenario or "fantasy"
    if scen_key == "custom" or req.tags:
        scen_key = scenario_data.resolve_scenario_or_custom_key(req.tags or "fantasy")

    gender = req.gender or "Male"
    race = req.race or "Human"
    weapon_name = (req.starting_weapon or "").strip()

    all_templates = cd.get_all_class_templates()
    is_preset_class = chosen_class in all_templates

    raw_loadout = {}
    if not req.force_dynamic and is_preset_class:
        raw_loadout = cd.get_starter_gear_by_class(scen_key, chosen_class, gender=gender, race=race)
    else:
        try:
            raw_loadout = cd.generate_starter_equipment_loadout(
                scenario=scen_key,
                char_class=chosen_class,
                gender=gender,
                race=race,
                weapon_name=weapon_name,
                tier=3,
            )
        except Exception as e:
            logger.warning(f"Preview procedural loadout fallback: {e}")
            if is_preset_class:
                raw_loadout = cd.get_starter_gear_by_class(scen_key, chosen_class, gender=gender, race=race)

    normalized = _normalize_loadout_dict(raw_loadout)
    starting_items = [
        {"name": item[0], "item_type": item[1], "description": item[2], "slot_cost": item[3]}
        for item in (cd.get_starting_items(scen_key, chosen_class) or [])
        if isinstance(item, (list, tuple)) and len(item) >= 4
    ]
    return {
        "success": True,
        "scenario": scen_key,
        "loadout": normalized,
        "starting_items": starting_items,
    }


@router.get("/api/characters/{user_id}")
async def get_user_characters(user_id: int):
    """Fetches all characters for a given user (up to 6 maximum)."""
    chars = await adb(db.get_user_characters, user_id)
    return {"characters": chars, "max_limit": 6}


@router.post("/api/character/switch")
async def switch_character(req: CharacterSwitchRequest):
    """Switches active character for a user by character_id."""
    char = await adb(db.switch_character, req.user_id, req.character_id)
    if not char:
        raise HTTPException(status_code=404, detail="Character not found")
    return {"success": True, "active_character": dict(char)}


@router.delete("/api/character/{user_id}/{character_id}")
async def delete_character_endpoint(user_id: int, character_id: int):
    """Deletes a specific character by character_id and returns updated character roster."""
    deleted = await adb(db.delete_character_by_id, user_id, character_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Character not found")
    chars = await adb(db.get_user_characters, user_id)
    active = await adb(db.get_character, user_id)
    return {
        "success": True,
        "characters": chars,
        "active_character": dict(active) if active else None,
    }


@router.get("/api/character/{user_id}")
async def get_character(user_id: int):
    """Fetches full character sheet, stats, HP/MP, level, and unspent stat points."""
    char = await adb(db.get_character, user_id)
    if not char:
        raise HTTPException(status_code=404, detail="Character not found")

    char_dict = dict(char)
    capacity = cd.inventory_capacity(char_dict["str_"])
    items = await adb(db.get_inventory, user_id)
    used_slots = sum(i.get("slot_cost", 1) for i in items if not i.get("equipped"))

    equipment = await adb(db.get_equipment, user_id)
    equipped_list = [item for item in equipment.values() if item] if equipment else None
    from scenario_data import is_non_combat_scenario
    char_scen = char_dict.get("scenario", "fantasy")
    is_non_combat = is_non_combat_scenario(char_scen)
    combat_attrs = cd.calculate_combat_attributes(char_dict, equipped_list)

    from mechanics.combat.spells import get_spell
    known_sids = await adb(db.get_learned_spells, user_id)
    known_spells = [get_spell(sid) for sid in known_sids if get_spell(sid)]

    return {
        "character": char_dict,
        "combat_attributes": combat_attrs,
        "is_non_combat": is_non_combat,
        "learned_spells": known_spells,
        "inventory_capacity": capacity,
        "used_inventory_slots": used_slots,
        "equipment": equipment,
        "stat_names": cd.STAT_NAMES,
        "stat_effects": cd.STAT_EFFECTS
    }


@router.post("/api/character/create")
async def create_character(req: CharacterCreateRequest):
    """Creates a new character in SQLite database."""
    total_stats = req.str_val + req.per + req.end + req.cha + req.int_val + req.agi + req.luk
    if total_stats > 12:
        raise HTTPException(status_code=400, detail="Stat allocation exceeds maximum allowed points!")

    stats = {
        "STR": req.str_val,
        "PER": req.per,
        "END": req.end,
        "CHA": req.cha,
        "INT": req.int_val,
        "AGI": req.agi,
        "LUK": req.luk
    }
    chosen_class = (req.class_name or req.char_class or "Warrior").strip()
    scen_key = req.scenario or "fantasy"
    if scen_key == "custom" or req.tags:
        scen_key = scenario_data.resolve_scenario_or_custom_key(req.tags or "fantasy")

    leftover_points = max(0, 12 - total_stats)
    try:
        await adb(
            db.create_character,
            user_id=req.user_id,
            name=req.name,
            char_class=chosen_class,
            class_description=req.class_description or "",
            stats=stats,
            pending_stat_points=leftover_points,
            gender=req.gender or "Male",
            scenario=scen_key,
            race=req.race or "Human",
            race_description=req.race_description or ""
        )

        if isinstance(req.starter_loadout, dict) and len(req.starter_loadout) > 0:
            starter_loadout = req.starter_loadout
        else:
            starter_loadout = await _invoke_starter_equipment_generator(
                chosen_class,
                scen_key,
                stats=stats,
                class_description=req.class_description or "",
                gender=req.gender or "Male",
                force_dynamic=False,
            )
        await _equip_starter_loadout_dict(
            req.user_id,
            starter_loadout,
            skip_weapon=bool(req.starting_weapon),
        )

        starting_weapon = req.starting_weapon or "Rusty Sword"
        weapon_effect = _build_starting_weapon_effect(
            starting_weapon,
            req.starting_weapon_description or "",
            scen_key,
        )
        weapon_id = await adb(
            db.add_item,
            req.user_id,
            starting_weapon,
            item_type="Weapon",
            effect=weapon_effect,
            slot_cost=1,
            force=True,
        )
        await adb(db.equip_item, req.user_id, weapon_id, "Weapon")

        created = await adb(db.get_character, req.user_id)
        return {"success": True, "character": dict(created), "resolved_scenario": scen_key}
    except Exception as e:
        logger.error(f"Error creating character: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/api/character/regenerate-gear")
async def regenerate_character_gear(req: RegenerateGearRequest):
    """Regenerates and equips a fresh class-tailored starter outfit for the active character."""
    char = await adb(db.get_character, req.user_id)
    if not char:
        raise HTTPException(status_code=404, detail="Character not found")

    char_dict = dict(char)
    stats = {
        "STR": char_dict.get("str_", 1),
        "PER": char_dict.get("per_", 1),
        "END": char_dict.get("end_", 1),
        "CHA": char_dict.get("cha", 1),
        "INT": char_dict.get("int_", 1),
        "AGI": char_dict.get("agi", 1),
        "LUK": char_dict.get("luk", 1),
    }
    chosen_class = char_dict.get("char_class") or "Warrior"
    scen_key = char_dict.get("scenario") or "fantasy"
    class_desc = char_dict.get("class_description") or ""
    gender = char_dict.get("gender") or "Male"

    loadout = await _invoke_starter_equipment_generator(
        chosen_class,
        scen_key,
        stats=stats,
        class_description=class_desc,
        gender=gender,
        force_dynamic=True,
    )
    await _equip_starter_loadout_dict(req.user_id, loadout, skip_weapon=False)

    updated_char = await adb(db.get_character, req.user_id)
    updated_equipment = await adb(db.get_equipment, req.user_id)
    return {
        "success": True,
        "character": dict(updated_char) if updated_char else char_dict,
        "equipment": updated_equipment,
    }


@router.post("/api/character/allocate")
async def spend_stat_point(req: SpendStatPointRequest):
    """Allocates 1 pending stat point into a stat."""
    stat = req.stat.upper()
    if stat not in cd.STATS:
        raise HTTPException(status_code=400, detail="Invalid stat name")

    res = await adb(db.spend_stat_point, req.user_id, stat)
    if res == "no_points":
        raise HTTPException(status_code=400, detail="No unspent stat points available")
    elif res == "capped":
        raise HTTPException(status_code=400, detail=f"{stat} is already at maximum level")

    char = await adb(db.get_character, req.user_id)
    return {"success": True, "character": dict(char)}
