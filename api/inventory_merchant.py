from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query, Request

_PHONE_MERCHANT_TYPES = frozenset({"online_general", "online_delivery", "school_mart"})

import db
from db import adb
import character_data as cd
import scenario_data
from mechanics.combat import is_in_combat
from mechanics.combat.merchant import (
    generate_merchant_shop,
    generate_grounded_merchant_rumors,
    reveal_hidden_node_from_rumor,
    get_store_key,
    get_or_create_merchant_catalogue,
    update_merchant_catalogue,
    get_anomalous_shop_faction_context,
    compute_charisma_discount,
    compute_item_resale_payout,
    compute_effective_shop_item_price,
    mark_vault_requisition_claimed,
    stamp_discounted_purchase_metadata,
    validate_or_clear_faction_quartermaster,
)
from mechanics.combat.online_store import (
    SCHOOL_MART_STUDENT_DISCOUNT_PCT,
    STORE_MODE_ONLINE_GENERAL,
    STORE_MODE_SCHOOL_MART,
    compute_phone_item_badges,
    get_eligible_phone_store_categories,
    infer_item_category,
    is_legacy_flat_phone_stock,
    is_school_mart_requested,
    normalize_phone_store_mode,
)
from mechanics.social.origin_mode import resolve_player_age_profile
from mechanics.combat.items import (
    apply_item_to_target,
    is_key_item,
    is_digital_item,
    parse_consumable_metadata,
    classify_and_enrich_ad_hoc_item,
    classify_consumable_usage_mode,
    is_hostile_or_covert_consumable,
)
from mechanics.combat.merchant import MERCHANT_ARCHETYPES
from mechanics.system.concurrency import distributed_adventure_lock, distributed_session_lock
from .security import verify_session_participant, verify_user_access
from mechanics.world import evaluate_shop_staff_availability
from mechanics.world.locations import (
    get_available_merchant_types_for_location,
    is_school_scenario,
)
from skill_check import resolve_check
import game_engine
from services.examine_service import invalidate_examine_cache
from .deps import (
    EquipRequest,
    UnequipRequest,
    ItemDropRequest,
    ItemUseRequest,
    MerchantBuyRequest,
    MerchantSellRequest,
    MerchantHaggleRequest,
    MerchantRumorRequest,
    ensure_realm_comms_available,
)

router = APIRouter()


async def _get_session_character(user_id: int, session_id: int) -> dict | None:
    """Resolve the session-bound character first, falling back to the user's active character."""
    char = await adb(db.get_character, user_id, session_id=session_id)
    if not char:
        char = await adb(db.get_character, user_id)
    return char


def _resolve_validated_request_merchant_type(
    req_mtype: str | None,
    merchant: dict,
    loc: str,
    scen_key: str,
) -> str:
    """Reject client-supplied merchant_type overrides that are not active or permitted at `loc`."""
    fallback_mtype = str(merchant.get("merchant_type") or "")
    if merchant.get("is_phone_shop") or fallback_mtype.strip().lower() in _PHONE_MERCHANT_TYPES:
        fallback_mtype = ""
    req_clean = str(req_mtype or "").strip()
    if not req_clean or req_clean == fallback_mtype:
        return fallback_mtype
    loc_stores = get_available_merchant_types_for_location(loc, scen_key=scen_key) or []
    allowed_loc_types = {str(s.get("type") or "").strip() for s in loc_stores if isinstance(s, dict) and s.get("type")}
    if req_clean in allowed_loc_types:
        return req_clean
    return fallback_mtype


def _validate_or_clear_faction_quartermaster(session_id: int, loc: str, merchant: dict) -> tuple[bool, dict]:
    """Verify `is_faction_quartermaster` is anchored to a Faction HQ; clear stale flags if not."""
    return validate_or_clear_faction_quartermaster(session_id, loc, merchant)


def _stock_item_qty(entry: dict) -> int:
    """Safely parse stock entry quantity, defaulting missing key to 1 and malformed/None to 0."""
    if "quantity" not in entry:
        return 1
    raw_qty = entry.get("quantity")
    if raw_qty is None:
        return 0
    try:
        return int(raw_qty)
    except (TypeError, ValueError):
        return 0


def _annotate_stock_items(raw_stock: list[dict], shop_ctx: dict, discount_pct: int) -> list[dict]:
    """Annotate in-stock merchant items with effective prices and faction pricing badges."""
    annotated: list[dict] = []
    for item in raw_stock or []:
        if not isinstance(item, dict) or not str(item.get("name") or "").strip() or _stock_item_qty(item) <= 0:
            continue
        base_price = int(item.get("price", 15) or 15)
        final_price = compute_effective_shop_item_price(item, shop_ctx=shop_ctx, discount_pct=discount_pct)
        entry = dict(item)
        entry["base_price"] = base_price
        entry["final_price"] = final_price
        if shop_ctx.get("pricing_badge"):
            entry["faction_pricing_badge"] = shop_ctx["pricing_badge"]
        annotated.append(entry)
    return annotated


def _is_spellbook(item: dict) -> bool:
    if not item or not isinstance(item, dict):
        return False
    it_type = str(item.get("item_type") or "").strip().lower()
    effect = str(item.get("effect") or "").strip()
    name_low = str(item.get("name") or "").strip().lower()
    if it_type == "spellbook" or effect.startswith("[SPELLBOOK_JSON]"):
        return True
    if any(name_low.startswith(p) for p in ("spellbook:", "grimoire:", "tome:", "scroll:", "schematic:", "datapad:", "data shard:", "master plan:", "black-ice drive:", "forbidden grimoire:", "blighted tome:", "foul parchment:")):
        return True
    return False


def _resolve_valid_slots(item: dict, eq_meta: dict) -> list[str]:
    if not item or not isinstance(item, dict):
        return []
    if is_key_item(item) or is_digital_item(item) or _is_spellbook(item):
        return []
    it_type = str(item.get("item_type") or "").strip()
    it_type_low = it_type.lower()
    if it_type_low in ("potion", "food", "drink", "consumable", "misc", "gift", "key item", "quest", "spellbook"):
        return []

    raw_slot = str(item.get("slot") or eq_meta.get("slot") or cd.DEFAULT_EQUIP_SLOT_FOR_ITEM_TYPE.get(it_type, "") or "").strip()
    if it_type_low == "accessory" or raw_slot.startswith("Accessory"):
        return ["Accessory 1", "Accessory 2", "Accessory 3", "Accessory 4"]
    if it_type_low == "weapon" or raw_slot == "Weapon":
        from mechanics.combat.equipment import is_two_handed
        if is_two_handed(item) or str(eq_meta.get("handedness") or "").upper() == "2H":
            return ["Weapon"]
        return ["Weapon", "Shield"]
    if it_type_low == "shield" or raw_slot == "Shield":
        return ["Shield"]
    if it_type_low in ("headwear", "head", "helmet", "hat") or raw_slot == "Head":
        return ["Head"]
    if it_type_low == "armor" or raw_slot == "Armor":
        return ["Armor"]
    if it_type_low == "top" or raw_slot == "Top":
        return ["Top"]
    if it_type_low == "bottom" or raw_slot == "Bottom":
        return ["Bottom"]
    if it_type_low == "gloves" or raw_slot == "Gloves":
        return ["Gloves"]
    if it_type_low in ("shoes", "boots", "footwear") or raw_slot == "Shoes":
        return ["Shoes"]
    if raw_slot in cd.EQUIPMENT_SLOTS:
        return [raw_slot]
    return []


def _enrich_inventory_item(item: dict, char: dict, equipment: dict) -> dict:
    from mechanics.combat.equipment import parse_equipment_metadata
    from mechanics.combat.items import parse_digital_item_metadata, parse_item_effect
    from mechanics.combat.spells import get_spell, get_all_spells

    it = dict(item)
    key_flag = bool(is_key_item(it))
    dig_flag = bool(is_digital_item(it))
    sb_flag = bool(_is_spellbook(it))

    it["is_key_item"] = key_flag
    it["is_digital_item"] = dig_flag
    it["is_spellbook"] = sb_flag
    pact_locked_flag = bool(it.get("is_pact_locked"))
    it["is_pact_locked"] = pact_locked_flag
    if pact_locked_flag:
        it["can_drop"] = False
        it["can_sell"] = False
        it["can_unequip"] = False

    raw_effect = str(it.get("effect") or "").strip()
    eq_meta = parse_equipment_metadata(it) if not (key_flag or dig_flag) else {}
    cons_meta = parse_consumable_metadata(it)
    dig_meta = parse_digital_item_metadata(it) if dig_flag else None

    valid_slots = _resolve_valid_slots(it, eq_meta)
    it["valid_slots"] = valid_slots
    target_slot = it.get("slot") if it.get("slot") in cd.EQUIPMENT_SLOTS else (valid_slots[0] if valid_slots else "")

    clean_effect = raw_effect
    category_label = str(it.get("item_type") or "Item").title()
    stats_badges: list[str] = []
    arcane_compatible = True
    from mechanics.combat.items.tags import is_narrative_item
    item_is_narrative = is_narrative_item(it) or is_narrative_item(eq_meta)

    if key_flag:
        category_label = "Key Item / Narrative Artifact"
        clean_effect = raw_effect.replace("Important narrative item:", "").strip() or "Essential story artifact."
        stats_badges = ["Plot Artifact", "Indestructible"]
    elif dig_flag:
        category_label = "Digital Media"
        caption = (dig_meta or {}).get("caption") or raw_effect
        contact_name = (dig_meta or {}).get("contact_name") or ""
        clean_effect = f"From {contact_name}: \"{caption}\"" if contact_name else str(caption)
        stats_badges = [str((dig_meta or {}).get("media_type", "photo")).replace("_", " ").title()]
    elif sb_flag:
        category_label = "Spellbook / Grimoire"
        spell_id = eq_meta.get("spell_id")
        sp = eq_meta.get("spell_data") or (get_spell(spell_id) if spell_id else None)
        if not sp:
            parts = str(it.get("name") or "").split(":", 1)
            if len(parts) > 1:
                sp_name_q = parts[1].strip().lower()
                for sid, sdef in get_all_spells().items():
                    if sdef.get("name", "").lower() == sp_name_q:
                        sp = sdef
                        break
        if sp:
            mp_cost = int(sp.get("mp_cost", 0) or 0)
            max_mp = int((char or {}).get("max_mp", 0) or 0)
            arcane_compatible = bool(max_mp >= mp_cost)
            clean_effect = sp.get("description") or f"Teaches {sp.get('name', 'Spell')} ({mp_cost} MP)."
            stats_badges = [
                f"{sp.get('tier_name', 'Basic')} {str(sp.get('discipline', 'Magic')).title()}",
                f"{mp_cost} MP",
                str(sp.get("damage_type", "arcane")).title(),
            ]
        else:
            clean_effect = "Ancient arcane tome that teaches a spell when studied."
            stats_badges = ["Spell Tome"]
    elif cons_meta or str(it.get("item_type") or "").lower() in ("potion", "food", "drink", "consumable"):
        category_label = f"Consumable ({it.get('item_type') or 'Item'})"
        parsed_eff = parse_item_effect(it)
        if parsed_eff.get("hp_restore"):
            stats_badges.append(f"+{parsed_eff['hp_restore']} HP")
        if parsed_eff.get("mp_restore"):
            stats_badges.append(f"+{parsed_eff['mp_restore']} MP")
        if parsed_eff.get("damage"):
            stats_badges.append(f"{parsed_eff['damage']} DMG")
        for bk, bv in (parsed_eff.get("buffs") or {}).items():
            if bk.endswith("_pct") or bk == "dr":
                stats_badges.append(f"+{int(float(bv) * 100)}% {bk.replace('_pct', '').upper()}")
            else:
                stats_badges.append(f"+{bv} {bk.upper()}")
        if parsed_eff.get("cure_status"):
            stats_badges.append(f"Cures {', '.join(parsed_eff['cure_status'])}")
        clean_effect = (
            (cons_meta or {}).get("description")
            or (cons_meta or {}).get("desc")
            or (cons_meta or {}).get("effect_desc")
            or (", ".join(stats_badges) if stats_badges else "Consumable item.")
        )
    elif valid_slots:
        if item_is_narrative:
            category_label = f"Narrative Gear ({target_slot})"
            stats_badges.append("Narrative Item")
            mods = dict(eq_meta.get("stat_modifiers") or {})
            for sk, sv in (eq_meta.get("social_modifiers") or {}).items():
                mods[sk] = mods.get(sk, 0) + sv
            for mk, mv in mods.items():
                if mv:
                    stats_badges.append(f"{mv:+g} {mk.upper()}")
            desc_from_meta = eq_meta.get("description") or ""
            clean_effect = desc_from_meta or "Cosmetic / narrative item for roleplay and social actions."
        else:
            category_label = f"Equipment ({target_slot})"
            if "Weapon" in valid_slots:
                mult = float(eq_meta.get("multiplier", 1.0) or 1.0)
                crit = int(eq_meta.get("crit_bonus", 0) or 0)
                hand = eq_meta.get("handedness", "1H")
                stats_badges.append(f"{mult:.2f}x DMG")
                if crit:
                    stats_badges.append(f"+{crit}% Crit")
                stats_badges.append(str(hand))
            if eq_meta.get("base_dt"):
                stats_badges.append(f"+{int(eq_meta['base_dt'])} DT")
            if eq_meta.get("block_chance"):
                stats_badges.append(f"+{int(eq_meta['block_chance'])}% Block")
            if eq_meta.get("is_anomalous"):
                stats_badges.append(f"⚡ Anomalous ({str(eq_meta.get('element') or 'Arcane').title()})")
            granted_sp = eq_meta.get("granted_spell")
            if isinstance(granted_sp, dict) and granted_sp.get("name"):
                stats_badges.append(f"✨ Grants: {granted_sp['name']}")
            mods = dict(eq_meta.get("stat_modifiers") or {})
            for sk, sv in (eq_meta.get("social_modifiers") or {}).items():
                mods[sk] = mods.get(sk, 0) + sv
            for mk, mv in mods.items():
                if mv:
                    if mk.endswith("_pct"):
                        stats_badges.append(f"{int(float(mv) * 100):+d}% {mk.replace('_pct', '').upper()}")
                    else:
                        stats_badges.append(f"{mv:+g} {mk.upper()}")
            desc_from_meta = eq_meta.get("description") or ""
            if desc_from_meta:
                clean_effect = f"{desc_from_meta} ({', '.join(stats_badges)})" if stats_badges else desc_from_meta
            else:
                clean_effect = ", ".join(stats_badges) if stats_badges else "Standard equipment."
    else:
        for prefix in ("[GEAR_JSON]", "[ITEM_JSON]", "[SPELLBOOK_JSON]", "[CONSUMABLE_JSON]", "[DIGITAL_JSON]"):
            if clean_effect.startswith(prefix):
                clean_effect = eq_meta.get("description") or it.get("name") or "Item"

    vs_equipped: list[dict] = []
    if target_slot and valid_slots and not item_is_narrative:
        cur_item = (equipment or {}).get(target_slot)
        cur_meta = parse_equipment_metadata(cur_item) if isinstance(cur_item, dict) else {}

        if "Weapon" in valid_slots:
            cur_mult = float(cur_meta.get("multiplier", 1.0) if cur_item else 0.0)
            new_mult = float(eq_meta.get("multiplier", 1.0) or 1.0)
            d_mult = round(new_mult - cur_mult, 2)
            vs_equipped.append({
                "label": "Multiplier",
                "current": f"{cur_mult:.2f}x",
                "new": f"{new_mult:.2f}x",
                "delta": d_mult,
                "is_upgrade": d_mult > 0,
            })
            cur_crit = float(cur_meta.get("crit_bonus", 0) if cur_item else 0.0)
            new_crit = float(eq_meta.get("crit_bonus", 0) or 0.0)
            d_crit = round(new_crit - cur_crit, 1)
            vs_equipped.append({
                "label": "Crit Bonus",
                "current": f"+{int(cur_crit)}%",
                "new": f"+{int(new_crit)}%",
                "delta": d_crit,
                "is_upgrade": d_crit > 0,
            })
        else:
            cur_dt = float(cur_meta.get("base_dt", 0) if cur_item else 0.0)
            new_dt = float(eq_meta.get("base_dt", 0) or 0.0)
            if cur_dt or new_dt or target_slot in ("Armor", "Head", "Gloves", "Shoes", "Shield"):
                d_dt = round(new_dt - cur_dt, 1)
                vs_equipped.append({
                    "label": "Defense (DT)",
                    "current": f"{int(cur_dt)} DT",
                    "new": f"{int(new_dt)} DT",
                    "delta": d_dt,
                    "is_upgrade": d_dt > 0,
                })
            if target_slot == "Shield" or cur_meta.get("block_chance") or eq_meta.get("block_chance"):
                cur_blk = float(cur_meta.get("block_chance", 0) if cur_item else 0.0)
                new_blk = float(eq_meta.get("block_chance", 0) or 0.0)
                d_blk = round(new_blk - cur_blk, 1)
                vs_equipped.append({
                    "label": "Block Chance",
                    "current": f"{int(cur_blk)}%",
                    "new": f"{int(new_blk)}%",
                    "delta": d_blk,
                    "is_upgrade": d_blk > 0,
                })

        cur_mods = dict(cur_meta.get("stat_modifiers") or {})
        for sk, sv in (cur_meta.get("social_modifiers") or {}).items():
            cur_mods[sk] = cur_mods.get(sk, 0) + sv

        new_mods = dict(eq_meta.get("stat_modifiers") or {})
        for sk, sv in (eq_meta.get("social_modifiers") or {}).items():
            new_mods[sk] = new_mods.get(sk, 0) + sv

        for k in sorted(set(cur_mods.keys()) | set(new_mods.keys())):
            c_val = float(cur_mods.get(k, 0) or 0)
            n_val = float(new_mods.get(k, 0) or 0)
            if c_val == 0 and n_val == 0:
                continue
            d_val = round(n_val - c_val, 2)
            vs_equipped.append({
                "label": k.upper(),
                "current": f"{c_val:+g}",
                "new": f"{n_val:+g}",
                "delta": d_val,
                "is_upgrade": d_val > 0,
            })

    it["clean_effect"] = clean_effect
    raw_type_low = str(it.get("item_type") or it.get("type") or "").lower()
    if key_flag:
        canonical_category = "Quest"
    elif dig_flag:
        canonical_category = "Digital"
    elif sb_flag or cons_meta or raw_type_low in ("potion", "food", "drink", "consumable", "scroll", "spellbook"):
        canonical_category = "Usables"
    elif "Weapon" in valid_slots:
        canonical_category = "Weapons"
    elif any(s in valid_slots for s in ("Armor", "Shield", "Head", "Gloves", "Shoes", "Top", "Bottom")):
        canonical_category = "Armor"
    else:
        canonical_category = "Misc"

    parsed_eff_check = parse_item_effect(it)
    item_is_usable = bool(
        canonical_category in ("Usables", "Digital", "Quest", "Misc")
        or parsed_eff_check.get("hp_restore")
        or parsed_eff_check.get("mp_restore")
    )

    if pact_locked_flag and "[Pact-Bound]" not in stats_badges:
        stats_badges.insert(0, "[Pact-Bound]")

    it["inspect_data"] = {
        "category": canonical_category,
        "category_label": category_label,
        "is_usable": item_is_usable,
        "is_equippable": bool(valid_slots),
        "usage_mode": classify_consumable_usage_mode(it),
        "is_hostile_consumable": bool(is_hostile_or_covert_consumable(it)),
        "is_key_item": bool(key_flag),
        "stats_summary": " • ".join(stats_badges) if stats_badges else clean_effect,
        "stat_badges": stats_badges,
        "arcane_compatible": arcane_compatible,
        "target_slot": target_slot,
        "vs_equipped": vs_equipped,
    }
    return it


@router.get("/api/inventory/{user_id}")
async def get_inventory(user_id: int, session_id: int | None = None, request: Request = None):
    """Fetches user inventory items and equipped gear with rich inspection metadata."""
    if session_id is not None:
        await verify_session_participant(request, session_id, user_id)
        active_sid = int(session_id)
    else:
        await verify_user_access(request, user_id)
        active_sid = await adb(db.get_active_session_id_for_user, user_id)

    char = (
        (await _get_session_character(user_id, int(active_sid)) if active_sid else None)
        or await adb(db.get_character, user_id)
    )
    if not char:
        raise HTTPException(status_code=404, detail="Character not found")

    char_dict = dict(char)
    if not active_sid:
        active_sid = char_dict.get("active_session_id")
    items = await adb(db.get_inventory, user_id, char=char_dict, session_id=active_sid)
    equipment = await adb(db.get_equipment, user_id, char=char_dict, session_id=active_sid)
    capacity = await adb(db.get_character_inventory_capacity, user_id, char_dict, active_sid)
    base_capacity = cd.inventory_capacity(char_dict["str_"])
    property_bonus_slots = max(0, int(capacity) - int(base_capacity))
    used_slots = db.compute_inventory_used_slots(items)

    enriched_items = [_enrich_inventory_item(dict(i), char_dict, equipment) for i in (items or [])]
    enriched_equipment = {}
    for slot, eq_item in (equipment or {}).items():
        if eq_item and isinstance(eq_item, dict):
            enriched_equipment[slot] = _enrich_inventory_item(dict(eq_item), char_dict, equipment)
        else:
            enriched_equipment[slot] = eq_item

    return {
        "items": enriched_items,
        "equipment": enriched_equipment,
        "capacity": capacity,
        "property_bonus_slots": property_bonus_slots,
        "used_slots": used_slots,
        "gold": char_dict.get("gold", 0)
    }


@router.post("/api/inventory/equip")
async def equip_item(req: EquipRequest, request: Request = None):
    """Equips an inventory item into a slot."""
    if req.session_id:
        _, canonical_id = await verify_session_participant(request, req.session_id, req.user_id)
    else:
        canonical_id = await verify_user_access(request, req.user_id)
    if req.slot not in cd.EQUIPMENT_SLOTS:
        raise HTTPException(status_code=400, detail="Invalid equipment slot")

    lock_sid = req.session_id or await adb(db.get_active_session_id_for_user, req.user_id)
    async with distributed_adventure_lock(canonical_id, lock_sid):
        try:
            prev = await adb(db.equip_item, req.user_id, req.item_id, req.slot, session_id=lock_sid)
            return {"success": True, "unequipped_previous": prev}
        except Exception as e:
            raise HTTPException(status_code=400, detail=str(e))


@router.post("/api/inventory/unequip")
async def unequip_slot(req: UnequipRequest, request: Request = None):
    """Unequips an item from an equipment slot."""
    if req.session_id:
        _, canonical_id = await verify_session_participant(request, req.session_id, req.user_id)
    else:
        canonical_id = await verify_user_access(request, req.user_id)
    if req.slot not in cd.EQUIPMENT_SLOTS:
        raise HTTPException(status_code=400, detail="Invalid equipment slot")

    lock_sid = req.session_id or await adb(db.get_active_session_id_for_user, req.user_id)
    async with distributed_adventure_lock(canonical_id, lock_sid):
        item = await adb(db.unequip_slot, req.user_id, req.slot, session_id=lock_sid)
        return {"success": True, "unequipped_item": item}


@router.post("/api/inventory/drop")
async def drop_item(req: ItemDropRequest, request: Request = None):
    """Drops/discards an item from the user's inventory onto the active room floor (D20)."""
    if req.session_id:
        _, canonical_id = await verify_session_participant(request, req.session_id, req.user_id)
    else:
        canonical_id = await verify_user_access(request, req.user_id)
    lock_sid = req.session_id or await adb(db.get_active_session_id_for_user, req.user_id)
    async with distributed_adventure_lock(canonical_id, lock_sid):
        actor_char = (
            await _get_session_character(req.user_id, int(lock_sid))
            if lock_sid
            else await adb(db.get_character, req.user_id)
        )
        items = await adb(db.get_inventory, req.user_id, char=actor_char)
        target_item = next((dict(i) for i in (items or []) if i.get("id") == req.item_id), None)
        if target_item and is_key_item(target_item):
            raise HTTPException(status_code=400, detail="Key items cannot be dropped or discarded.")

        removed = await adb(db.remove_item, req.user_id, req.item_id, char=actor_char, session_id=lock_sid)
        if not removed:
            raise HTTPException(status_code=404, detail="Item not found or could not be removed")
        if target_item and not is_digital_item(target_item):
            await adb(db.drop_item_to_session_floor, req.user_id, target_item, session_id=lock_sid)
        if lock_sid:
            try:
                invalidate_examine_cache(lock_sid)
            except Exception:
                pass
        return {"success": True}


@router.post("/api/inventory/use")
async def use_item(req: ItemUseRequest, request: Request = None):
    """Uses a consumable item, reads a spellbook, or inspects a key/digital item."""
    if req.session_id:
        _, canonical_id = await verify_session_participant(request, req.session_id, req.user_id)
    else:
        canonical_id = await verify_user_access(request, req.user_id)
    lock_sid = req.session_id or await adb(db.get_active_session_id_for_user, req.user_id)
    async with distributed_adventure_lock(canonical_id, lock_sid):
        actor_char = (
            await _get_session_character(req.user_id, int(lock_sid))
            if lock_sid
            else await adb(db.get_character, req.user_id)
        )
        items = await adb(db.get_inventory, req.user_id, char=actor_char)
        target_item = next((dict(i) for i in items if i.get("id") == req.item_id), None)
        if not target_item:
            raise HTTPException(status_code=404, detail="Item not found in inventory")

        session = None
        if lock_sid:
            sess_row = await adb(db.get_session, lock_sid)
            if sess_row:
                session = dict(sess_row)

        eff_ttype = str(req.target_type or "self").strip().lower()
        if isinstance(session, dict):
            from mechanics.combat import is_in_combat as _inv_is_combat
            if _inv_is_combat(session):
                raise HTTPException(status_code=400, detail="In combat, using an item consumes a turn.")
        if eff_ttype in ("npc", "contact"):
            raise HTTPException(status_code=400, detail="Using an item on an NPC requires a story turn.")
        u_mode = classify_consumable_usage_mode(target_item)
        if u_mode == "narrative":
            raise HTTPException(status_code=400, detail="Narrative consumables must be used during a story turn.")

        eff_target_uid = int(req.user_id)
        if eff_ttype == "player" and req.target_user_id is not None:
            if not lock_sid:
                raise HTTPException(status_code=400, detail="Active session required to target another player.")
            allowed_uids = set(await adb(db.get_session_participant_user_ids, lock_sid) or [])
            if allowed_uids and int(req.target_user_id) not in allowed_uids:
                raise HTTPException(status_code=403, detail="Target player is not in your session.")
            eff_target_uid = int(req.target_user_id)

        if (
            target_item.get("item_type") in ("Potion", "Food", "Drink", "Consumable")
            and not parse_consumable_metadata(target_item)
        ):
            scen_key = (session or {}).get("scenario", "fantasy")
            enriched = classify_and_enrich_ad_hoc_item(target_item.get("name", "Item"), scen_key)
            if enriched.get("effect"):
                target_item["effect"] = enriched["effect"]

        success, message = await adb(
            apply_item_to_target,
            req.user_id,
            target_item,
            eff_ttype or "self",
            req.target_name or "self",
            session=session,
            target_user_id=eff_target_uid,
            mode="use",
        )
        if not success:
            raise HTTPException(status_code=400, detail=message)

        char = (
            await _get_session_character(req.user_id, int(lock_sid))
            if lock_sid
            else await adb(db.get_character, req.user_id)
        )
        return {
            "success": True,
            "message": message,
            "character": dict(char) if char else None
        }


def _compute_charisma_discount(char: dict, merchant: dict) -> int:
    return compute_charisma_discount(char, merchant)


async def _ensure_merchant_session_member(session_id: int, user_id: int, session: dict) -> None:
    if int(user_id) <= 0 or int(session_id) <= 0:
        raise HTTPException(status_code=400, detail="Invalid user_id or session_id.")
    allowed_uids = set(await adb(db.get_session_participant_user_ids, session_id) or [])
    if allowed_uids and int(user_id) not in allowed_uids:
        raise HTTPException(status_code=403, detail="You are not an active participant of this session.")


def _resolve_open_venue_stall(
    *,
    session_id: int,
    loc: str,
    scen_key: str,
    cur_day: int,
    cur_min: int,
    turn_no: int,
    skip_type: str,
    venue_avail: dict,
    is_anom_scen: bool,
) -> tuple[str, dict] | None:
    """Finds an open specialist stall or roamer at a multi-stall venue when default merchant_type is off-shift."""
    loc_stores = get_available_merchant_types_for_location(loc, scen_key=scen_key) or []
    open_archs = list(((venue_avail.get("staff_npc") or {}).get("basic_info") or {}).get("merchant_archetypes") or [])
    cand_order: list[str] = []
    for raw_arch in open_archs:
        arch_name = str(raw_arch or "").strip()
        if arch_name and arch_name != skip_type and arch_name not in cand_order and not (is_anom_scen and arch_name in ("spellbook_merchant", "magic_merchant")):
            cand_order.append(arch_name)
    for store_entry in loc_stores:
        st = str(store_entry.get("type") or "").strip()
        if st and st != skip_type and st not in cand_order and not (is_anom_scen and st in ("spellbook_merchant", "magic_merchant")):
            cand_order.append(st)
    for cand in cand_order:
        res = evaluate_shop_staff_availability(
            session_id,
            location_str=loc,
            merchant_type=cand,
            is_phone_shop=False,
            scen_key=scen_key,
            current_day=cur_day,
            current_minute=cur_min,
            turn_number=turn_no,
        )
        if res.get("available"):
            return cand, res
    return None


@router.get("/api/merchant/{session_id}")
async def get_merchant_shop(
    session_id: int,
    user_id: int = Query(...),
    merchant_type: str | None = Query(None),
    is_phone_shop: bool = Query(False),
    store_mode: str | None = Query(None),
    request: Request = None,
):
    """Fetches or generates the active merchant shop (or Smartphone E-Shop) stock and player sell valuations."""
    if int(user_id) <= 0 or int(session_id) <= 0:
        raise HTTPException(status_code=400, detail="Invalid user_id or session_id.")
    session, _ = await verify_session_participant(request, session_id, user_id)
    if is_phone_shop:
        await ensure_realm_comms_available(session_id, session=session)

    char = await _get_session_character(user_id, session_id)
    if not char:
        raise HTTPException(status_code=404, detail="Character not found")

    merchant = dict(session.get("merchant") or {})
    cur_day = int(session.get("current_day", 1) or 1)
    cur_min = int(session.get("current_minute", 480) or 480)
    loc = session.get("current_location", "")
    scen_key = session.get("scenario", "fantasy")
    player_profile = resolve_player_age_profile(session, char)
    is_student = bool(player_profile.get("is_student"))
    in_combat = bool(session.get("in_combat") or is_in_combat(session))

    if is_phone_shop and is_school_mart_requested(store_mode) and not is_student:
        raise HTTPException(status_code=403, detail="SchoolMart student store is only available to student characters.")
    effective_store_mode = (
        normalize_phone_store_mode(store_mode, is_student=is_student)
        if is_phone_shop
        else ""
    )

    if is_phone_shop and merchant_type and (MERCHANT_ARCHETYPES.get(merchant_type) or {}).get("in_person_only"):
        raise HTTPException(
            status_code=403,
            detail="Sanctuary spirit merchants trade strictly in person and never accept remote Smartphone E-Shop orders.",
        )
    explicit_merchant_type = str(merchant_type or "").strip() or None
    prev_m_type = merchant.get("merchant_type") or "general_merchant"
    m_type = (
        ("school_mart" if effective_store_mode == STORE_MODE_SCHOOL_MART else "online_delivery")
        if is_phone_shop
        else (explicit_merchant_type or prev_m_type)
    )
    from scenario_data import is_anomalous_incursions_scenario as _is_anom_merch
    is_anom_scen = bool(_is_anom_merch(scen_key))
    if is_anom_scen and m_type in ("spellbook_merchant", "magic_merchant"):
        m_type = "general_merchant"
    # If player explicitly switches store tabs at a street location, clear stale Quartermaster flag
    if not is_phone_shop and explicit_merchant_type and merchant.get("is_faction_quartermaster"):
        merchant["is_faction_quartermaster"] = False
        merchant.pop("quartermaster_faction_arch", None)
    pre_shop_ctx = await adb(
        get_anomalous_shop_faction_context,
        session,
        loc,
        is_phone_shop,
        user_id,
    )
    if not pre_shop_ctx.get("allowed", True):
        raise HTTPException(status_code=403, detail=pre_shop_ctx.get("access_denied_reason") or "Access denied to this faction store.")
    is_monastic_member_shrine = (
        not is_phone_shop
        and pre_shop_ctx.get("shop_faction_archetype") == "monastic_order"
        and pre_shop_ctx.get("player_faction_archetype") == "monastic_order"
    )

    is_qm_active = False
    if not is_phone_shop:
        is_qm_active, updated_m = await adb(_validate_or_clear_faction_quartermaster, session_id, loc, merchant)
        merchant.clear()
        merchant.update(updated_m)

    shop_avail: dict | None = None
    is_shop_open = True
    shop_closed_reason = ""
    staff_keeper_name = ""
    valid_loc_types: list[str] = []
    if not is_phone_shop and not explicit_merchant_type and not is_qm_active:
        loc_stores_init = get_available_merchant_types_for_location(loc, scen_key=scen_key) or []
        valid_loc_types = [
            str(s.get("type") or "").strip()
            for s in loc_stores_init
            if s.get("type") and not (is_anom_scen and s.get("type") in ("spellbook_merchant", "magic_merchant"))
        ]
        if valid_loc_types and m_type not in valid_loc_types:
            m_type = valid_loc_types[0]
    if not is_phone_shop and not is_qm_active:
        turn_no = int(session.get("turn_count") or 0)
        shop_avail = await adb(
            evaluate_shop_staff_availability,
            session_id,
            location_str=loc,
            merchant_type=m_type,
            is_phone_shop=False,
            scen_key=scen_key,
            current_day=cur_day,
            current_minute=cur_min,
            turn_number=turn_no,
        )
        if not shop_avail.get("available") and not explicit_merchant_type:
            venue_avail = await adb(
                evaluate_shop_staff_availability,
                session_id,
                location_str=loc,
                merchant_type="",
                is_phone_shop=False,
                scen_key=scen_key,
                current_day=cur_day,
                current_minute=cur_min,
                turn_number=turn_no,
            )
            if venue_avail.get("available"):
                picked = await adb(
                    _resolve_open_venue_stall,
                    session_id=session_id,
                    loc=loc,
                    scen_key=scen_key,
                    cur_day=cur_day,
                    cur_min=cur_min,
                    turn_no=turn_no,
                    skip_type=m_type,
                    venue_avail=venue_avail,
                    is_anom_scen=is_anom_scen,
                )
                if picked is not None:
                    m_type, shop_avail = picked
            elif venue_avail.get("reason"):
                shop_avail = venue_avail

        if shop_avail and shop_avail.get("reason") == "club_quartermaster" and valid_loc_types and m_type not in valid_loc_types:
            m_type = "club_merchant" if "club_merchant" in valid_loc_types else valid_loc_types[0]

        is_shop_open = bool(shop_avail.get("available"))
        if not is_shop_open:
            shop_closed_reason = str(shop_avail.get("reason") or "no_merchant")
        elif shop_avail.get("staff_npc"):
            staff_keeper_name = str(shop_avail["staff_npc"].get("name") or "").strip()

    switched_store = bool(
        not is_phone_shop
        and not is_monastic_member_shrine
        and m_type != prev_m_type
        and (bool(explicit_merchant_type) or is_shop_open)
    )
    store_key = (
        f"{loc or 'monastic_shrine'}:monastic_shrine_daily"
        if is_monastic_member_shrine
        else get_store_key(
            merchant,
            is_phone_shop=is_phone_shop,
            merchant_type=m_type,
            location=loc,
            store_mode=effective_store_mode,
        )
    )

    stock_field = (
        ("school_mart_stock" if effective_store_mode == STORE_MODE_SCHOOL_MART else "phone_stock")
        if is_phone_shop
        else "stock"
    )
    moved_store = bool(
        not is_phone_shop
        and not is_monastic_member_shrine
        and merchant.get("active_store_key")
        and store_key != merchant.get("active_store_key")
    )
    catalogue, needs_restock = get_or_create_merchant_catalogue(merchant, store_key, cur_day, cur_min)
    if (
        is_phone_shop
        and effective_store_mode == STORE_MODE_ONLINE_GENERAL
        and (
            is_legacy_flat_phone_stock(merchant.get(stock_field))
            or is_legacy_flat_phone_stock((catalogue or {}).get("stock"))
        )
    ):
        needs_restock = True
        merchant[stock_field] = []

    if is_shop_open and needs_restock and (switched_store or moved_store or not merchant.get(stock_field)):
        inv = await adb(db.get_inventory, user_id, char=char)
        party = [(dict(char), inv)]
        arch_meta = MERCHANT_ARCHETYPES.get(m_type, MERCHANT_ARCHETYPES.get("general_merchant", {}))
        restock_name = (
            ("SchoolMart Campus Store" if effective_store_mode == STORE_MODE_SCHOOL_MART else "Express E-Shop Delivery")
            if is_phone_shop
            else (staff_keeper_name or (arch_meta.get("title") if (switched_store or moved_store) else (merchant.get("flavor_name") or arch_meta.get("title") or "Local Merchant")))
        )
        try:
            gen_kwargs = {
                "party": party,
                "merchant_name": restock_name,
                "merchant_description": (
                    arch_meta.get("intro_template", "Order daily essentials for fast delivery.")
                    if is_phone_shop
                    else (arch_meta.get("intro_template") if (switched_store or moved_store) else (merchant.get("flavor_description") or ""))
                ),
                "session": session,
                "is_phone_shop": is_phone_shop,
                "merchant_type": m_type,
            }
            if is_phone_shop:
                gen_kwargs["store_mode"] = effective_store_mode
            shop_data = await generate_merchant_shop(**gen_kwargs)
        except Exception:
            if is_phone_shop:
                from mechanics.combat.online_store import build_phone_store_catalog

                cur_meta_fb = scenario_data.get_scenario_currency(scen_key)
                shop_data = build_phone_store_catalog(
                    scen_key,
                    store_mode=effective_store_mode,
                    day=cur_day,
                    is_nsfw=scenario_data.is_nsfw_scenario(scen_key),
                    player_level=int(char.get("level", 1) or 1),
                    currency=cur_meta_fb.get("name", "Credits"),
                )
            else:
                shop_data = {
                    "intro_narrative": arch_meta.get("intro_template") or "Browse wares and trade gear.",
                    "stock": [
                        {"name": "Express Energy Drink", "item_type": "Drink", "description": "Restores 10 HP and 10 MP.", "price": 20, "quantity": 3, "tier": 2},
                        {"name": "Artisan Gift Box", "item_type": "Gift", "description": "A thoughtful gift for a close friend.", "price": 35, "quantity": 2, "tier": 2},
                    ],
                    "rumors": await adb(generate_grounded_merchant_rumors, session_id, scen_key),
                }
        catalogue = update_merchant_catalogue(merchant, store_key, shop_data, cur_day, cur_min)
        merchant[stock_field] = catalogue.get("stock", [])
        if not is_phone_shop:
            merchant["is_phone_shop"] = False
            merchant["merchant_type"] = m_type
            merchant["in_person_only"] = bool(shop_data.get("in_person_only") or arch_meta.get("in_person_only"))
            merchant["active_store_key"] = store_key
            merchant["intro_narrative"] = catalogue.get("intro_narrative", "")
            merchant["rumors"] = catalogue.get("rumors", [])
            merchant["haggle_attempts"] = catalogue.get("haggle_attempts", 0)
            merchant["discount_pct"] = catalogue.get("discount_pct", 0)
            merchant["available"] = True
        await adb(db.save_merchant_state, session_id, merchant)
    elif is_shop_open and catalogue and (
        switched_store
        or moved_store
        or not merchant.get(stock_field)
        or (not is_phone_shop and bool(merchant.get("is_phone_shop")))
    ):
        merchant[stock_field] = catalogue.get("stock", [])
        if not is_phone_shop:
            was_phone_flag = bool(merchant.get("is_phone_shop"))
            merchant["is_phone_shop"] = False
            merchant["merchant_type"] = m_type
            merchant["in_person_only"] = bool((MERCHANT_ARCHETYPES.get(m_type) or {}).get("in_person_only"))
            merchant["active_store_key"] = store_key
            merchant["intro_narrative"] = catalogue.get("intro_narrative", "")
            merchant["rumors"] = catalogue.get("rumors", [])
            merchant["haggle_attempts"] = catalogue.get("haggle_attempts", merchant.get("haggle_attempts", 0))
            merchant["discount_pct"] = catalogue.get("discount_pct", merchant.get("discount_pct", 0))
            merchant["available"] = True
            if switched_store or moved_store or was_phone_flag:
                await adb(db.save_merchant_state, session_id, merchant)

    if is_phone_shop:
        if effective_store_mode == STORE_MODE_SCHOOL_MART:
            cha_disc = _compute_charisma_discount(char, {"discount_pct": 0})
            student_discount_pct = SCHOOL_MART_STUDENT_DISCOUNT_PCT
            discount_pct = min(40, student_discount_pct + cha_disc)
        else:
            student_discount_pct = 0
            discount_pct = 0
    else:
        student_discount_pct = 0
        discount_pct = _compute_charisma_discount(char, merchant)
    shop_ctx = await adb(
        get_anomalous_shop_faction_context,
        session,
        loc,
        is_phone_shop,
        user_id,
    )
    if not shop_ctx.get("allowed", True):
        raise HTTPException(status_code=403, detail=shop_ctx.get("access_denied_reason") or "Access denied to this faction store.")
    raw_stock = merchant.get(stock_field) or (catalogue.get("stock", []) if catalogue else [])
    if (
        shop_ctx.get("shop_faction_archetype") == "monastic_order"
        and shop_ctx.get("player_faction_archetype") == "monastic_order"
    ):
        raw_stock = raw_stock[:3]
        for s_it in raw_stock:
            if isinstance(s_it, dict) and int(s_it.get("quantity", 1) or 1) > 1:
                s_it["quantity"] = 1
    stock = _annotate_stock_items(raw_stock, shop_ctx, discount_pct) if is_shop_open else []
    if is_phone_shop:
        for st_it in stock:
            if isinstance(st_it, dict):
                if not st_it.get("category"):
                    st_it["category"] = infer_item_category(st_it, store_mode=effective_store_mode)
                if not st_it.get("badges"):
                    st_it["badges"] = compute_phone_item_badges(st_it)

    # Compute sellable items from player inventory
    inv_items = await adb(db.get_inventory, user_id, char=char, session_id=session_id)
    sellable = []
    for it in inv_items:
        it_dict = dict(it)
        sell_price, reject_reason = compute_item_resale_payout(it_dict, session, char)
        if reject_reason:
            continue
        it_dict["sell_price"] = sell_price
        sellable.append(it_dict)

    available_stores = []
    loc_node_id = str(session.get("current_node_id") or "").strip()
    is_spirit_market_loc = False
    if not is_phone_shop:
        loc_stores = get_available_merchant_types_for_location(loc, scen_key=scen_key)
        seen_types = set()
        for s in loc_stores:
            st = s.get("type", "general_merchant")
            if _is_anom_merch(scen_key) and st in ("spellbook_merchant", "magic_merchant"):
                continue
            seen_types.add(st)
            available_stores.append({
                "type": st,
                "title": s.get("title", st),
                "emoji": s.get("emoji", "🛍️"),
                "description": s.get("intro_template", "")
            })
        from mechanics.world.locations.folklore_spirit_realm import is_node_in_spirit_realm
        in_spirit_realm_loc = await adb(is_node_in_spirit_realm, session_id, loc_node_id) if loc_node_id else False
        is_spirit_market_loc = bool(
            in_spirit_realm_loc
            or any(
                (MERCHANT_ARCHETYPES.get(s.get("type"), {}) or {}).get("is_night_market_stall")
                for s in loc_stores
            )
        )
        # Ensure specialist tabs are browsable in standard fantasy/sci-fi hubs (suppressed at Veiled Night Market / Spirit Realm stalls)
        from scenario_data import is_anomalous_incursions_scenario
        default_tabs = (
            []
            if is_spirit_market_loc
            else (
                ["school_merchant", "cafe_merchant", "clothes_merchant", "gift_merchant"]
                if is_school_scenario(scen_key)
                else (
                    ["general_merchant", "weapon_merchant", "armor_merchant", "potion_merchant", "food_merchant"]
                    if is_anomalous_incursions_scenario(scen_key)
                    else ["general_merchant", "weapon_merchant", "armor_merchant", "potion_merchant", "magic_merchant", "spellbook_merchant", "food_merchant"]
                )
            )
        )
        for dt in default_tabs:
            if dt not in seen_types and dt in MERCHANT_ARCHETYPES:
                arch = MERCHANT_ARCHETYPES[dt]
                available_stores.append({
                    "type": dt,
                    "title": arch.get("title", dt),
                    "emoji": arch.get("emoji", "🛍️"),
                    "description": arch.get("intro_template", "")
                })

    raw_rumors = [] if is_phone_shop else (merchant.get("rumors") or [])
    normalized_rumors = []
    for r in raw_rumors:
        if isinstance(r, str):
            normalized_rumors.append({"text": r, "revealed": False})
        elif isinstance(r, dict):
            r_entry = {
                "text": r.get("text", ""),
                "revealed": bool(r.get("revealed", False)),
                "succeeded": r.get("succeeded", True),
            }
            for _rk in ("linked_quest_id", "linked_node_id", "linked_npc", "linked_location"):
                if r.get(_rk):
                    r_entry[_rk] = r[_rk]
            normalized_rumors.append(r_entry)

    arch_info = MERCHANT_ARCHETYPES.get(m_type, {})
    if is_phone_shop:
        from mechanics.system.phone import get_phone_branding

        ph_brand = get_phone_branding(scen_key, session=session, is_student=is_student)
        if effective_store_mode == STORE_MODE_SCHOOL_MART:
            merchant_name = ph_brand.get("school_shop_app_name", "SchoolMart")
            merchant_desc = "Student co-op essentials with automatic -20% student discount."
        else:
            merchant_name = ph_brand.get("shop_app_name", "Online Store")
            merchant_desc = "Order food, drinks, meds, gifts, apparel, and tactical supplies for fast doorstep delivery."
    else:
        merchant_name = (
            staff_keeper_name or (arch_info.get("title") if (switched_store or moved_store) else (merchant.get("flavor_name") or arch_info.get("title") or "Traveling Merchant"))
        )
        if not is_shop_open:
            merchant_desc = str((shop_avail or {}).get("reason_message") or "This shop is currently closed.")
        else:
            merchant_desc = merchant.get("intro_narrative") or merchant.get("flavor_description") or arch_info.get("intro_template") or "Browse wares and trade gear."
    haggle_attempts = 0 if is_phone_shop else int(merchant.get("haggle_attempts", 0) or 0)
    haggle_discount_pct = 0 if is_phone_shop else int(merchant.get("discount_pct", 0) or 0)
    phone_categories = (
        get_eligible_phone_store_categories(
            scen_key,
            store_mode=effective_store_mode,
            is_nsfw=scenario_data.is_nsfw_scenario(scen_key),
        )
        if is_phone_shop
        else []
    )
    delivery_blocked_reason = (
        "Courier delivery is unavailable while in active combat."
        if (is_phone_shop and in_combat)
        else ""
    )

    from mechanics.world.world_events.spirit_realm_events import get_active_spirit_events
    active_spirit_evts = await adb(get_active_spirit_events, session_id)
    active_evt_keys = {str(e.get("template_key") or "") for e in (active_spirit_evts or []) if isinstance(e, dict)}
    fair_active = "evt_spirit_twin_moon_fair" in active_evt_keys
    auction_active = "evt_spirit_midnight_curio_auction" in active_evt_keys
    lanterns_active = "evt_spirit_drifting_lanterns" in active_evt_keys

    return {
        "available": True if is_phone_shop else is_shop_open,
        "shop_closed_reason": "" if is_phone_shop else shop_closed_reason,
        "staff_keeper": "" if is_phone_shop else staff_keeper_name,
        "is_phone_shop": is_phone_shop,
        "is_night_market": is_spirit_market_loc,
        "twin_moon_fair_active": bool(fair_active),
        "curio_auction_active": bool(auction_active),
        "drifting_lanterns_active": bool(lanterns_active),
        "store_mode": effective_store_mode if is_phone_shop else "",
        "categories": phone_categories,
        "in_combat": in_combat,
        "delivery_blocked_reason": delivery_blocked_reason,
        "student_discount_pct": student_discount_pct,
        "merchant_type": m_type,
        "available_stores": available_stores,
        "merchant_name": merchant_name,
        "flavor_name": merchant_name,
        "merchant_description": merchant_desc,
        "greeting": merchant_desc,
        "discount_pct": discount_pct,
        "haggle_discount_pct": haggle_discount_pct,
        "haggle_attempts": haggle_attempts,
        "haggle_attempts_left": max(0, 3 - haggle_attempts),
        "gold": char.get("gold", 0),
        "stock": stock,
        "inventory": stock,
        "sellable_items": sellable,
        "rumors": normalized_rumors
    }


@router.post("/api/merchant/haggle")
async def merchant_haggle(req: MerchantHaggleRequest, request: Request = None):
    """Attempts a Charisma + Luck skill check to haggle for an extra +10% shop discount (up to 3 attempts)."""
    if int(req.user_id) <= 0 or int(req.session_id) <= 0:
        raise HTTPException(status_code=400, detail="Invalid user_id or session_id.")
    _, canonical_id = await verify_session_participant(request, req.session_id, req.user_id)
    async with distributed_session_lock(req.session_id):
        session = await adb(db.get_session, req.session_id)
        if not session:
            raise HTTPException(status_code=404, detail="Session not found")
        await _ensure_merchant_session_member(req.session_id, req.user_id, session)

        char = await _get_session_character(req.user_id, req.session_id)
        if not char:
            raise HTTPException(status_code=404, detail="Character not found")

        merchant = dict(session.get("merchant") or {})
        is_phone = bool(req.is_phone_shop)
        if is_phone:
            await ensure_realm_comms_available(req.session_id, session=session)
            raise HTTPException(
                status_code=400,
                detail="Haggling is only available in person at physical merchant stalls.",
            )
        is_qm_haggle = False
        if not is_phone:
            is_qm_haggle, updated_m = await adb(
                _validate_or_clear_faction_quartermaster,
                req.session_id,
                session.get("current_location") or "",
                merchant,
            )
            merchant.clear()
            merchant.update(updated_m)
        if not is_phone and not is_qm_haggle:
            loc_str = session.get("current_location") or ""
            scen_str = session.get("scenario") or "fantasy"
            val_mtype = _resolve_validated_request_merchant_type(req.merchant_type, merchant, loc_str, scen_str)
            shop_avail = await adb(
                evaluate_shop_staff_availability,
                req.session_id,
                location_str=loc_str,
                merchant_type=val_mtype,
                is_phone_shop=False,
                scen_key=scen_str,
                current_day=session.get("current_day"),
                current_minute=session.get("current_minute"),
                turn_number=int(session.get("turn_count") or 0),
            )
            if not shop_avail.get("available"):
                raise HTTPException(
                    status_code=400,
                    detail=shop_avail.get("reason_message") or "The merchant counter is closed.",
                )
        attempts = int(merchant.get("haggle_attempts", 0) or 0)
        if attempts >= 3:
            raise HTTPException(status_code=400, detail="The merchant has grown tired of haggling (3/3 attempts used).")

        requirement = 4 + attempts * 2
        settings = await adb(db.get_settings, canonical_id)
        check_mode = (settings or {}).get("debug_check_mode", "off")
        check = resolve_check(int(char.get("cha", 1) or 1), requirement, int(char.get("luk", 1) or 1), check_mode=check_mode)

        merchant["haggle_attempts"] = attempts + 1
        if check.succeeded:
            merchant["discount_pct"] = min(30, int(merchant.get("discount_pct", 0) or 0) + 10)
            note = (
                f"{char['name']} haggles skillfully! ({check.chance}% chance — {check.tier_label}) "
                f"Shop haggle discount increased to -{merchant['discount_pct']}%!"
            )
        else:
            note = (
                f"{char['name']}'s haggling falls flat ({check.chance}% chance — {check.tier_label}). "
                f"Prices remain unchanged."
            )

        active_key = merchant.get("active_store_key")
        if not bool(req.is_phone_shop) and active_key and isinstance(merchant.get("catalogues"), dict) and active_key in merchant["catalogues"]:
            merchant["catalogues"][active_key]["haggle_attempts"] = merchant["haggle_attempts"]
            merchant["catalogues"][active_key]["discount_pct"] = merchant.get("discount_pct", 0)

        await adb(db.save_merchant_state, req.session_id, merchant)
        total_discount = _compute_charisma_discount(char, merchant)
        haggle_shop_ctx = await adb(
            get_anomalous_shop_faction_context,
            session,
            session.get("current_location", ""),
            bool(req.is_phone_shop),
            canonical_id,
        )
        raw_haggle_stock = list(
            (merchant.get("phone_stock") if bool(req.is_phone_shop) else merchant.get("stock"))
            or (
                (merchant.get("catalogues") or {}).get(active_key, {}).get("stock", [])
                if (not bool(req.is_phone_shop) and active_key and isinstance(merchant.get("catalogues"), dict))
                else []
            )
        )
        if (
            haggle_shop_ctx.get("shop_faction_archetype") == "monastic_order"
            and haggle_shop_ctx.get("player_faction_archetype") == "monastic_order"
        ):
            raw_haggle_stock = [dict(s_it, quantity=1) if isinstance(s_it, dict) and int(s_it.get("quantity", 1) or 1) > 1 else s_it for s_it in raw_haggle_stock[:3]]
        annotated_stock = _annotate_stock_items(raw_haggle_stock, haggle_shop_ctx, total_discount)

        return {
            "success": True,
            "haggle_succeeded": check.succeeded,
            "chance": check.chance,
            "tier_label": check.tier_label,
            "haggle_attempts": merchant["haggle_attempts"],
            "haggle_attempts_left": max(0, 3 - merchant["haggle_attempts"]),
            "haggle_discount_pct": int(merchant.get("discount_pct", 0) or 0),
            "discount_pct": total_discount,
            "stock": annotated_stock,
            "message": note,
        }


@router.post("/api/merchant/rumor")
async def merchant_reveal_rumor(req: MerchantRumorRequest, request: Request = None):
    """Runs a Charisma check to investigate a merchant rumor and logs it to the session Quest & Clue Caseboard."""
    if int(req.user_id) <= 0 or int(req.session_id) <= 0:
        raise HTTPException(status_code=400, detail="Invalid user_id or session_id.")
    _, canonical_id = await verify_session_participant(request, req.session_id, req.user_id)
    async with distributed_session_lock(req.session_id):
        session = await adb(db.get_session, req.session_id)
        if not session:
            raise HTTPException(status_code=404, detail="Session not found")
        await _ensure_merchant_session_member(req.session_id, req.user_id, session)

        char = await _get_session_character(req.user_id, req.session_id)
        if not char:
            raise HTTPException(status_code=404, detail="Character not found")

        merchant = dict(session.get("merchant") or {})
        raw_rumors = list(merchant.get("rumors") or [])
        rumors = [
            {"text": r, "revealed": False} if isinstance(r, str) else dict(r)
            for r in raw_rumors
        ]

        if req.rumor_index < 0 or req.rumor_index >= len(rumors):
            raise HTTPException(status_code=404, detail="Rumor not found")

        target_rumor = rumors[req.rumor_index]
        if target_rumor.get("revealed"):
            return {
                "success": True,
                "already_revealed": True,
                "rumor_succeeded": bool(target_rumor.get("succeeded", True)),
                "rumor_text": target_rumor.get("text", ""),
                "message": "This rumor has already been investigated.",
                "rumors": rumors,
            }

        settings = await adb(db.get_settings, canonical_id)
        check_mode = (settings or {}).get("debug_check_mode", "off")
        check = resolve_check(int(char.get("cha", 1) or 1), 5, int(char.get("luk", 1) or 1), check_mode=check_mode)

        target_rumor["revealed"] = True
        target_rumor["succeeded"] = check.succeeded
        rumors[req.rumor_index] = target_rumor
        merchant["rumors"] = rumors

        active_key = merchant.get("active_store_key")
        if active_key and isinstance(merchant.get("catalogues"), dict) and active_key in merchant["catalogues"]:
            merchant["catalogues"][active_key]["rumors"] = rumors

        await adb(db.save_merchant_state, req.session_id, merchant)

        rumor_text = target_rumor.get("text", "")
        if check.succeeded and rumor_text:
            new_history = game_engine.push_history(
                session.get("history", []),
                f"[Rumor] {char['name']} learned: {rumor_text}"
            )
            await adb(
                db.save_session_scene,
                req.session_id,
                session.get("scene_title", ""),
                session.get("narrative", ""),
                session.get("choices", []),
                new_history
            )
            linked_qid = str(target_rumor.get("linked_quest_id") or "").strip()
            linked_nid = str(target_rumor.get("linked_node_id") or "").strip()
            if linked_nid:
                await adb(reveal_hidden_node_from_rumor, req.session_id, linked_nid)
            if linked_qid or linked_nid:
                cur_ch = await adb(db.get_session_chapter, req.session_id) or 1
                await adb(
                    db.add_session_clue,
                    session_id=req.session_id,
                    title=rumor_text[:60],
                    lead_text=rumor_text,
                    category="testimonial",
                    source_location=session.get("current_location", "Merchant Shop"),
                    linked_npc=str(target_rumor.get("linked_npc") or merchant.get("flavor_name") or merchant.get("name") or "Merchant"),
                    quest_id=linked_qid,
                    chapter=cur_ch,
                )
                msg = f'"{rumor_text}" — Logged to your Clue Caseboard!'
            else:
                msg = f'"{rumor_text}"'
        else:
            msg = f"{char['name']} couldn't get a straight answer ({check.chance}% chance — {check.tier_label})."

        return {
            "success": True,
            "rumor_succeeded": check.succeeded,
            "chance": check.chance,
            "tier_label": check.tier_label,
            "rumor_text": rumor_text if check.succeeded else "",
            "message": msg,
            "rumors": rumors,
        }


@router.post("/api/merchant/buy")
async def merchant_buy(req: MerchantBuyRequest, request: Request = None):
    """Purchases an item from the active session merchant or Smartphone E-Shop."""
    if int(req.user_id) <= 0 or int(req.session_id) <= 0:
        raise HTTPException(status_code=400, detail="Invalid user_id or session_id.")
    _, canonical_id = await verify_session_participant(request, req.session_id, req.user_id)
    async with distributed_adventure_lock(canonical_id, req.session_id):
        session = await adb(db.get_session, req.session_id)
        if not session:
            raise HTTPException(status_code=404, detail="Session not found")
        await _ensure_merchant_session_member(req.session_id, req.user_id, session)

        char = await _get_session_character(req.user_id, req.session_id)
        if not char:
            raise HTTPException(status_code=404, detail="Character not found")

        merchant = dict(session.get("merchant") or {})
        is_qm_buy = False
        if not bool(req.is_phone_shop):
            is_qm_buy, updated_m = await adb(
                _validate_or_clear_faction_quartermaster,
                req.session_id,
                session.get("current_location") or "",
                merchant,
            )
            merchant.clear()
            merchant.update(updated_m)
        if not bool(req.is_phone_shop) and not is_qm_buy:
            buy_loc = session.get("current_location") or ""
            buy_scen = session.get("scenario") or "fantasy"
            val_buy_mtype = _resolve_validated_request_merchant_type(req.merchant_type, merchant, buy_loc, buy_scen)
            shop_avail = await adb(
                evaluate_shop_staff_availability,
                req.session_id,
                location_str=buy_loc,
                merchant_type=val_buy_mtype,
                is_phone_shop=False,
                scen_key=buy_scen,
                current_day=session.get("current_day"),
                current_minute=session.get("current_minute"),
                turn_number=int(session.get("turn_count") or 0),
            )
            if not shop_avail.get("available"):
                raise HTTPException(
                    status_code=400,
                    detail=shop_avail.get("reason_message") or "The shop is currently closed.",
                )
        m_arch = MERCHANT_ARCHETYPES.get(str(merchant.get("merchant_type") or merchant.get("type") or ""), {})
        is_in_person_store = bool(merchant.get("in_person_only") or m_arch.get("in_person_only"))
        buy_player_profile = resolve_player_age_profile(session, char)
        buy_is_student = bool(buy_player_profile.get("is_student"))
        buy_store_mode = ""
        target_name_low = req.item_name.strip().lower()
        if req.is_phone_shop:
            await ensure_realm_comms_available(req.session_id, session=session)
            if is_school_mart_requested(req.store_mode) and not buy_is_student:
                raise HTTPException(status_code=403, detail="SchoolMart student store is only available to student characters.")
            if bool(session.get("in_combat") or is_in_combat(session)):
                raise HTTPException(status_code=400, detail="Courier delivery is unavailable while in active combat.")
            buy_store_mode = normalize_phone_store_mode(req.store_mode, is_student=buy_is_student)
            stock_field = "school_mart_stock" if buy_store_mode == STORE_MODE_SCHOOL_MART else "phone_stock"
            phone_list = list(merchant.get(stock_field) or [])
            in_phone_stock = any(
                isinstance(s, dict) and str(s.get("name") or "").strip().lower() == target_name_low
                for s in phone_list
            )
            in_person_match = any(
                isinstance(s, dict) and str(s.get("name") or "").strip().lower() == target_name_low
                for s in (merchant.get("stock") or [])
            )
            explicit_in_person_req = bool(
                (MERCHANT_ARCHETYPES.get(str(req.merchant_type or ""), {}) or {}).get("in_person_only")
            )
            if explicit_in_person_req or (is_in_person_store and not in_phone_stock and (not phone_list or in_person_match)):
                raise HTTPException(
                    status_code=403,
                    detail="Sanctuary spirit merchants trade strictly in person and never accept remote Smartphone E-Shop orders.",
                )
        else:
            stock_field = "stock"
        stock = list(merchant.get(stock_field) or [])
        target_idx = next(
            (
                idx
                for idx, s in enumerate(stock)
                if isinstance(s, dict)
                and str(s.get("name") or "").strip().lower() == target_name_low
                and _stock_item_qty(s) > 0
            ),
            None,
        )
        if target_idx is None:
            raise HTTPException(status_code=404, detail=f"Item '{req.item_name}' is not in stock")

        stock_item = dict(stock[target_idx])
        if req.is_phone_shop and (
            (stock_item.get("metadata") or {}).get("in_person_only")
            or (stock_item.get("metadata") or {}).get("folklore_village")
        ):
            raise HTTPException(
                status_code=403,
                detail="Sanctuary spirit relics can only be acquired in person within the veiled enclave.",
            )
        if req.is_phone_shop:
            if buy_store_mode == STORE_MODE_SCHOOL_MART:
                discount_pct = min(40, SCHOOL_MART_STUDENT_DISCOUNT_PCT + _compute_charisma_discount(char, {"discount_pct": 0}))
            else:
                discount_pct = 0
        else:
            discount_pct = _compute_charisma_discount(char, merchant)
        shop_ctx = await adb(
            get_anomalous_shop_faction_context,
            session,
            session.get("current_location", ""),
            bool(req.is_phone_shop),
            canonical_id,
        )
        if not shop_ctx.get("allowed", True):
            raise HTTPException(status_code=403, detail=shop_ctx.get("access_denied_reason") or "Access denied to this faction store.")
        if shop_ctx.get("shrine_daily_exhausted"):
            raise HTTPException(status_code=400, detail="Daily Sacred Shrine provisions (3/3) have been claimed today. Stock refreshes tomorrow morning.")
        price = compute_effective_shop_item_price(stock_item, shop_ctx=shop_ctx, discount_pct=discount_pct)

        if (char.get("gold", 0) or 0) < price:
            scen_key = session.get("scenario", "fantasy")
            cur_meta = scenario_data.get_scenario_currency(scen_key)
            need_fmt = scenario_data.format_scenario_currency(price, scen_key)
            have_fmt = scenario_data.format_scenario_currency(char.get("gold", 0) or 0, scen_key)
            raise HTTPException(
                status_code=400,
                detail=f"Not enough {cur_meta['name'].lower()}! Need {need_fmt}, have {have_fmt}.",
            )

        slot_cost = int(stock_item.get("slot_cost", 1) or 1)

        # Embed anti-exploit resale metadata (universal across anomalous shops + SchoolMart + all discount/grant shops)
        item_eff = str(stock_item.get("effect") or stock_item.get("description", ""))
        is_anom_purchase = scenario_data.is_anomalous_incursions_scenario(session.get("scenario", ""))
        if (
            is_anom_purchase
            or buy_store_mode == STORE_MODE_SCHOOL_MART
            or shop_ctx.get("is_monastic_free_shop")
            or shop_ctx.get("is_public_discounted_shop")
            or shop_ctx.get("is_event_discounted_shop")
            or shop_ctx.get("is_cult_discounted_shop")
        ):
            item_eff = stamp_discounted_purchase_metadata(
                item_eff,
                price,
                shrine_sacred_grant=bool(shop_ctx.get("is_monastic_free_shop")),
                public_requisition_item=bool(shop_ctx.get("is_public_discounted_shop")),
            )

        # Decrement stock quantity on a working copy before atomic commit
        stock_item["quantity"] = max(0, _stock_item_qty(stock_item) - 1)
        if stock_item["quantity"] <= 0:
            stock.pop(target_idx)
        else:
            stock[target_idx] = stock_item
        merchant[stock_field] = stock

        # Sync with active catalogue if present
        active_key = merchant.get("active_store_key")
        catalogues = merchant.get("catalogues")
        if isinstance(catalogues, dict):
            if req.is_phone_shop:
                p_cat_key = "phone_school_mart" if buy_store_mode == STORE_MODE_SCHOOL_MART else "phone_shop"
                if isinstance(catalogues.get(p_cat_key), dict):
                    catalogues[p_cat_key]["stock"] = stock
            else:
                eff_cat_key = active_key or get_store_key(
                    merchant,
                    is_phone_shop=False,
                    merchant_type=str(merchant.get("merchant_type") or ""),
                    location=str(session.get("current_location") or ""),
                )
                if eff_cat_key and isinstance(catalogues.get(eff_cat_key), dict):
                    catalogues[eff_cat_key]["stock"] = stock

        claimed_reqs = (
            mark_vault_requisition_claimed(session, stock_item.get("name", ""))
            if stock_item.get("is_vault_requisition")
            else None
        )

        target_char_id = int(char["id"])

        def _commit_merchant_purchase():
            with db.UnitOfWork():
                bought_id = db.atomic_merchant_purchase(
                    req.user_id,
                    stock_item["name"],
                    stock_item.get("item_type", "Item"),
                    item_eff,
                    slot_cost,
                    price,
                    character_id=target_char_id,
                )
                if shop_ctx.get("is_monastic_free_shop"):
                    from mechanics.social.factions import get_anomalous_faction_state, save_anomalous_faction_state
                    a_state = get_anomalous_faction_state(req.session_id, req.user_id)
                    new_claims = int(a_state.get("shrine_free_claims_today", a_state.get("shrine_free_claimed_today", 0)) or 0) + 1
                    a_state["shrine_free_claims_today"] = new_claims
                    a_state["shrine_free_claimed_today"] = new_claims
                    save_anomalous_faction_state(req.session_id, a_state, req.user_id)
                if claimed_reqs is not None:
                    db.update_session(req.session_id, extra={"anomalous_vault_requisitions": claimed_reqs})
                db.save_merchant_state(req.session_id, merchant)
                q_upd = game_engine.evaluate_quest_state_predicates(req.session_id, req.user_id)
                return bought_id, q_upd

        try:
            item_id, quest_updates = await adb(_commit_merchant_purchase)
        except LookupError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

        updated_char = await _get_session_character(req.user_id, req.session_id)

        # Re-annotate stock with updated faction pricing / remaining daily Shrine grants
        post_shop_ctx = await adb(
            get_anomalous_shop_faction_context,
            session,
            session.get("current_location", ""),
            bool(req.is_phone_shop),
            req.user_id,
        )
        annotated_stock = _annotate_stock_items(stock, post_shop_ctx, discount_pct)

        return {
            "success": True,
            "item_id": item_id,
            "item_name": stock_item["name"],
            "price_paid": price,
            "gold": updated_char.get("gold", 0) if updated_char else 0,
            "stock": annotated_stock,
            "quest_updates": quest_updates or [],
        }


@router.post("/api/merchant/sell")
async def merchant_sell(req: MerchantSellRequest, request: Request = None):
    """Sells an unequipped item from the player's inventory to the merchant."""
    if int(req.user_id) <= 0 or int(req.session_id) <= 0:
        raise HTTPException(status_code=400, detail="Invalid user_id or session_id.")
    _, canonical_id = await verify_session_participant(request, req.session_id, req.user_id)
    async with distributed_adventure_lock(canonical_id, req.session_id):
        session = await adb(db.get_session, req.session_id)
        if not session:
            raise HTTPException(status_code=404, detail="Session not found")
        await _ensure_merchant_session_member(req.session_id, req.user_id, session)

        char = await _get_session_character(req.user_id, req.session_id)
        if not char:
            raise HTTPException(status_code=404, detail="Character not found")

        merchant = dict(session.get("merchant") or {})
        is_phone = bool(req.is_phone_shop)
        if is_phone:
            await ensure_realm_comms_available(req.session_id, session=session)
            raise HTTPException(
                status_code=400,
                detail="Selling items is only available in person at physical merchant stalls.",
            )
        is_qm_haggle = False
        if not is_phone:
            is_qm_haggle, updated_m = await adb(
                _validate_or_clear_faction_quartermaster,
                req.session_id,
                session.get("current_location") or "",
                merchant,
            )
            merchant.clear()
            merchant.update(updated_m)
        if not is_phone and not is_qm_haggle:
            sell_loc = session.get("current_location") or ""
            sell_scen = session.get("scenario") or "fantasy"
            val_sell_mtype = _resolve_validated_request_merchant_type(req.merchant_type, merchant, sell_loc, sell_scen)
            shop_avail = await adb(
                evaluate_shop_staff_availability,
                req.session_id,
                location_str=sell_loc,
                merchant_type=val_sell_mtype,
                is_phone_shop=False,
                scen_key=sell_scen,
                current_day=session.get("current_day"),
                current_minute=session.get("current_minute"),
                turn_number=int(session.get("turn_count") or 0),
            )
            if not shop_avail.get("available"):
                raise HTTPException(
                    status_code=400,
                    detail=shop_avail.get("reason_message") or "The shop is currently closed.",
                )

        items = await adb(db.get_inventory, req.user_id, char=char)
        target_item = next((dict(i) for i in items if i.get("id") == req.item_id), None)
        if not target_item:
            raise HTTPException(status_code=404, detail="Item not found in inventory")

        sell_price, reject_reason = compute_item_resale_payout(target_item, session, char)
        if reject_reason:
            raise HTTPException(status_code=400, detail=reject_reason)

        sold = await adb(db.sell_inventory_item, req.user_id, req.item_id, sell_price, character_id=int(char["id"]))
        if not sold:
            raise HTTPException(status_code=400, detail="Could not remove item from inventory")

        updated_char = await _get_session_character(req.user_id, req.session_id)

        return {
            "success": True,
            "item_name": target_item.get("name"),
            "gold_earned": sell_price,
            "gold": updated_char.get("gold", 0) if updated_char else 0
        }
