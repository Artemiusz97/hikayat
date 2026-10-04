from fastapi import APIRouter, HTTPException, Query

import db
from db import adb
import character_data as cd
from mechanics.combat.merchant import (
    generate_merchant_shop,
    discounted_price,
    sell_bonus_price,
    calculate_balanced_price,
    get_store_key,
    get_or_create_merchant_catalogue,
    update_merchant_catalogue,
)
from mechanics.combat.items import (
    apply_item_to_target,
    parse_item_tier,
    is_key_item,
    is_digital_item,
    parse_consumable_metadata,
    classify_and_enrich_ad_hoc_item,
)
from mechanics.combat.merchant import MERCHANT_ARCHETYPES
from mechanics.world.locations import get_available_merchant_types_for_location, is_school_scenario
from skill_check import resolve_check
import game_engine
from .deps import (
    EquipRequest,
    UnequipRequest,
    ItemDropRequest,
    ItemUseRequest,
    MerchantBuyRequest,
    MerchantSellRequest,
    MerchantHaggleRequest,
    MerchantRumorRequest,
)

router = APIRouter()


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
        clean_effect = (cons_meta or {}).get("description") or (", ".join(stats_badges) if stats_badges else "Consumable item.")
    elif valid_slots:
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
    if target_slot and valid_slots:
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
    it["inspect_data"] = {
        "category_label": category_label,
        "stats_summary": " • ".join(stats_badges) if stats_badges else clean_effect,
        "stat_badges": stats_badges,
        "arcane_compatible": arcane_compatible,
        "target_slot": target_slot,
        "vs_equipped": vs_equipped,
    }
    return it


@router.get("/api/inventory/{user_id}")
async def get_inventory(user_id: int):
    """Fetches user inventory items and equipped gear with rich inspection metadata."""
    char = await adb(db.get_character, user_id)
    if not char:
        raise HTTPException(status_code=404, detail="Character not found")

    char_dict = dict(char)
    items = await adb(db.get_inventory, user_id)
    equipment = await adb(db.get_equipment, user_id)
    capacity = cd.inventory_capacity(char_dict["str_"])
    used_slots = await adb(db.used_slots, user_id)

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
        "used_slots": used_slots,
        "gold": char_dict.get("gold", 0)
    }


@router.post("/api/inventory/equip")
async def equip_item(req: EquipRequest):
    """Equips an inventory item into a slot."""
    if req.slot not in cd.EQUIPMENT_SLOTS:
        raise HTTPException(status_code=400, detail="Invalid equipment slot")

    try:
        prev = await adb(db.equip_item, req.user_id, req.item_id, req.slot)
        return {"success": True, "unequipped_previous": prev}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/api/inventory/unequip")
async def unequip_slot(req: UnequipRequest):
    """Unequips an item from an equipment slot."""
    if req.slot not in cd.EQUIPMENT_SLOTS:
        raise HTTPException(status_code=400, detail="Invalid equipment slot")

    item = await adb(db.unequip_slot, req.user_id, req.slot)
    return {"success": True, "unequipped_item": item}


@router.post("/api/inventory/drop")
async def drop_item(req: ItemDropRequest):
    """Drops/discards an item from the user's inventory."""
    items = await adb(db.get_inventory, req.user_id)
    target_item = next((dict(i) for i in (items or []) if i.get("id") == req.item_id), None)
    if target_item and is_key_item(target_item):
        raise HTTPException(status_code=400, detail="Key items cannot be dropped or discarded.")

    removed = await adb(db.remove_item, req.user_id, req.item_id)
    if not removed:
        raise HTTPException(status_code=404, detail="Item not found or could not be removed")
    return {"success": True}


@router.post("/api/inventory/use")
async def use_item(req: ItemUseRequest):
    """Uses a consumable item, reads a spellbook, or inspects a key/digital item."""
    items = await adb(db.get_inventory, req.user_id)
    target_item = next((dict(i) for i in items if i.get("id") == req.item_id), None)
    if not target_item:
        raise HTTPException(status_code=404, detail="Item not found in inventory")

    session = None
    if req.session_id:
        sess_row = await adb(db.get_session, req.session_id)
        if sess_row:
            session = dict(sess_row)
    else:
        active_sid = await adb(db.get_active_session_id_for_user, req.user_id)
        if active_sid:
            sess_row = await adb(db.get_session, active_sid)
            if sess_row:
                session = dict(sess_row)

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
        req.target_type or "self",
        req.target_name or "self",
        session=session,
        target_user_id=req.user_id
    )
    if not success:
        raise HTTPException(status_code=400, detail=message)

    char = await adb(db.get_character, req.user_id)
    return {
        "success": True,
        "message": message,
        "character": dict(char) if char else None
    }


def _compute_charisma_discount(char: dict, merchant: dict) -> int:
    cha = int(char.get("cha", 1) or 1) if char else 1
    cha_bonus = max(0, (cha - 2) * 3)
    haggle_disc = int(merchant.get("discount_pct", 0) or 0)
    return min(40, cha_bonus + haggle_disc)


@router.get("/api/merchant/{session_id}")
async def get_merchant_shop(
    session_id: int,
    user_id: int = Query(...),
    merchant_type: str | None = Query(None),
    is_phone_shop: bool = Query(False),
):
    """Fetches or generates the active merchant shop (or Smartphone E-Shop) stock and player sell valuations."""
    session = await adb(db.get_session, session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    char = await adb(db.get_character, user_id)
    if not char:
        raise HTTPException(status_code=404, detail="Character not found")

    merchant = dict(session.get("merchant") or {})
    cur_day = int(session.get("current_day", 1) or 1)
    cur_min = int(session.get("current_minute", 480) or 480)
    loc = session.get("current_location", "")
    scen_key = session.get("scenario", "fantasy")

    prev_m_type = merchant.get("merchant_type") or "general_merchant"
    m_type = "online_delivery" if is_phone_shop else (merchant_type or prev_m_type)
    switched_store = bool(not is_phone_shop and merchant_type and merchant_type != prev_m_type)
    store_key = get_store_key(merchant, is_phone_shop=is_phone_shop, merchant_type=m_type, location=loc)

    stock_field = "phone_stock" if is_phone_shop else "stock"
    catalogue, needs_restock = get_or_create_merchant_catalogue(merchant, store_key, cur_day, cur_min)
    if needs_restock and (switched_store or not merchant.get(stock_field)):
        inv = await adb(db.get_inventory, user_id)
        party = [(dict(char), inv)]
        arch_meta = MERCHANT_ARCHETYPES.get(m_type, MERCHANT_ARCHETYPES.get("general_merchant", {}))
        try:
            shop_data = await generate_merchant_shop(
                party=party,
                merchant_name="Express E-Shop Delivery" if is_phone_shop else (arch_meta.get("title") if switched_store else (merchant.get("flavor_name") or arch_meta.get("title") or "Local Merchant")),
                merchant_description="Instant drone & courier delivery straight to your location." if is_phone_shop else (arch_meta.get("intro_template") if switched_store else (merchant.get("flavor_description") or "")),
                session=session,
                is_phone_shop=is_phone_shop,
                merchant_type=m_type
            )
        except Exception:
            shop_data = {
                "intro_narrative": arch_meta.get("intro_template") or "Welcome! Browse our selection.",
                "stock": [
                    {"name": "Express Energy Drink", "item_type": "Drink", "description": "Restores 10 HP and 10 MP.", "price": 20, "quantity": 3, "tier": 2},
                    {"name": "Artisan Gift Box", "item_type": "Gift", "description": "A thoughtful gift for a close friend.", "price": 35, "quantity": 2, "tier": 2},
                ],
                "rumors": [{"text": "Strange lights were spotted near the old ruins last night.", "revealed": False}],
            }
        catalogue = update_merchant_catalogue(merchant, store_key, shop_data, cur_day, cur_min)
        merchant[stock_field] = catalogue.get("stock", [])
        if not is_phone_shop:
            merchant["merchant_type"] = m_type
            merchant["active_store_key"] = store_key
            merchant["intro_narrative"] = catalogue.get("intro_narrative", "")
            merchant["rumors"] = catalogue.get("rumors", [])
            merchant["haggle_attempts"] = catalogue.get("haggle_attempts", 0)
            merchant["discount_pct"] = catalogue.get("discount_pct", 0)
            merchant["available"] = True
        await adb(db.save_merchant_state, session_id, merchant)
    elif catalogue and (switched_store or not merchant.get(stock_field)):
        merchant[stock_field] = catalogue.get("stock", [])
        if not is_phone_shop:
            merchant["merchant_type"] = m_type
            merchant["active_store_key"] = store_key
            merchant["intro_narrative"] = catalogue.get("intro_narrative", "")
            merchant["rumors"] = catalogue.get("rumors", [])
            merchant["haggle_attempts"] = catalogue.get("haggle_attempts", merchant.get("haggle_attempts", 0))
            merchant["discount_pct"] = catalogue.get("discount_pct", merchant.get("discount_pct", 0))
            if switched_store:
                await adb(db.save_merchant_state, session_id, merchant)

    discount_pct = _compute_charisma_discount(char, merchant)
    raw_stock = merchant.get(stock_field) or (catalogue.get("stock", []) if catalogue else [])
    stock = []
    for item in raw_stock:
        if item.get("quantity", 1) <= 0:
            continue
        base_price = int(item.get("price", 15) or 15)
        final_price = discounted_price(base_price, discount_pct)
        entry = dict(item)
        entry["base_price"] = base_price
        entry["final_price"] = final_price
        stock.append(entry)

    # Compute sellable items from player inventory
    inv_items = await adb(db.get_inventory, user_id)
    sellable = []
    for it in inv_items:
        it_dict = dict(it)
        if it_dict.get("equipped") or is_key_item(it_dict) or is_digital_item(it_dict):
            continue
        tier = parse_item_tier(it_dict)
        base_val = max(2, calculate_balanced_price(it_dict.get("item_type", "Item"), it_dict.get("name", "Item"), tier=tier, scen_key=scen_key) // 3)
        sell_price = sell_bonus_price(base_val, discount_pct // 2)
        it_dict["sell_price"] = sell_price
        sellable.append(it_dict)

    available_stores = []
    if not is_phone_shop:
        loc_stores = get_available_merchant_types_for_location(loc, scen_key=scen_key)
        seen_types = set()
        for s in loc_stores:
            st = s.get("type", "general_merchant")
            seen_types.add(st)
            available_stores.append({
                "type": st,
                "title": s.get("title", st),
                "emoji": s.get("emoji", "🛍️"),
                "description": s.get("intro_template", "")
            })
        # Ensure specialist tabs are browsable in standard fantasy/sci-fi hubs
        default_tabs = (
            ["school_merchant", "cafe_merchant", "clothes_merchant", "gift_merchant"]
            if is_school_scenario(scen_key)
            else ["general_merchant", "weapon_merchant", "armor_merchant", "potion_merchant", "magic_merchant", "spellbook_merchant", "food_merchant"]
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
            normalized_rumors.append({
                "text": r.get("text", ""),
                "revealed": bool(r.get("revealed", False)),
                "succeeded": r.get("succeeded", True)
            })

    arch_info = MERCHANT_ARCHETYPES.get(m_type, {})
    merchant_name = "Express E-Shop" if is_phone_shop else (
        arch_info.get("title") if switched_store else (merchant.get("flavor_name") or arch_info.get("title") or "Traveling Merchant")
    )
    merchant_desc = "Order snacks, gifts, and gear for immediate delivery." if is_phone_shop else (
        merchant.get("intro_narrative") or merchant.get("flavor_description") or arch_info.get("intro_template") or "Browse wares and trade gear."
    )
    haggle_attempts = int(merchant.get("haggle_attempts", 0) or 0)
    haggle_discount_pct = int(merchant.get("discount_pct", 0) or 0)

    return {
        "available": True if is_phone_shop else bool(merchant.get("available", True)),
        "is_phone_shop": is_phone_shop,
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
async def merchant_haggle(req: MerchantHaggleRequest):
    """Attempts a Charisma + Luck skill check to haggle for an extra +10% shop discount (up to 3 attempts)."""
    session = await adb(db.get_session, req.session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    char = await adb(db.get_character, req.user_id)
    if not char:
        raise HTTPException(status_code=404, detail="Character not found")

    merchant = dict(session.get("merchant") or {})
    attempts = int(merchant.get("haggle_attempts", 0) or 0)
    if attempts >= 3:
        raise HTTPException(status_code=400, detail="The merchant has grown tired of haggling (3/3 attempts used).")

    requirement = 4 + attempts * 2
    settings = await adb(db.get_settings, req.user_id)
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
    if active_key and isinstance(merchant.get("catalogues"), dict) and active_key in merchant["catalogues"]:
        merchant["catalogues"][active_key]["haggle_attempts"] = merchant["haggle_attempts"]
        merchant["catalogues"][active_key]["discount_pct"] = merchant.get("discount_pct", 0)

    await adb(db.save_merchant_state, req.session_id, merchant)
    total_discount = _compute_charisma_discount(char, merchant)

    return {
        "success": True,
        "haggle_succeeded": check.succeeded,
        "chance": check.chance,
        "tier_label": check.tier_label,
        "haggle_attempts": merchant["haggle_attempts"],
        "haggle_attempts_left": max(0, 3 - merchant["haggle_attempts"]),
        "haggle_discount_pct": int(merchant.get("discount_pct", 0) or 0),
        "discount_pct": total_discount,
        "message": note,
    }


@router.post("/api/merchant/rumor")
async def merchant_reveal_rumor(req: MerchantRumorRequest):
    """Runs a Charisma check to investigate a merchant rumor and logs it to the session Quest & Clue Caseboard."""
    session = await adb(db.get_session, req.session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    char = await adb(db.get_character, req.user_id)
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

    settings = await adb(db.get_settings, req.user_id)
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
        cur_ch = await adb(db.get_session_chapter, req.session_id) or 1
        await adb(
            db.add_session_clue,
            session_id=req.session_id,
            title=rumor_text[:60],
            lead_text=rumor_text,
            category="testimonial",
            source_location=session.get("current_location", "Merchant Shop"),
            linked_npc=merchant.get("flavor_name") or merchant.get("name") or "Merchant",
            chapter=cur_ch
        )
        msg = f'"{rumor_text}" — Logged to your Clue Caseboard!'
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
async def merchant_buy(req: MerchantBuyRequest):
    """Purchases an item from the active session merchant or Smartphone E-Shop."""
    session = await adb(db.get_session, req.session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    char = await adb(db.get_character, req.user_id)
    if not char:
        raise HTTPException(status_code=404, detail="Character not found")

    merchant = dict(session.get("merchant") or {})
    stock_field = "phone_stock" if req.is_phone_shop and merchant.get("phone_stock") else "stock"
    stock = list(merchant.get(stock_field) or [])
    target_idx = next(
        (idx for idx, s in enumerate(stock) if s.get("name", "").lower() == req.item_name.strip().lower() and s.get("quantity", 1) > 0),
        None
    )
    if target_idx is None:
        raise HTTPException(status_code=404, detail=f"Item '{req.item_name}' is not in stock")

    stock_item = dict(stock[target_idx])
    discount_pct = _compute_charisma_discount(char, merchant)
    price = discounted_price(int(stock_item.get("price", 15) or 15), discount_pct)

    if (char.get("gold", 0) or 0) < price:
        raise HTTPException(status_code=400, detail=f"Not enough gold! Need {price}g, have {char.get('gold', 0)}g.")

    capacity = cd.inventory_capacity(char["str_"])
    used = await adb(db.used_slots, req.user_id)
    slot_cost = int(stock_item.get("slot_cost", 1) or 1)
    if used + slot_cost > capacity:
        raise HTTPException(status_code=400, detail="Inventory is full!")

    await adb(db.apply_hp_mp_delta, req.user_id, gold_delta=-price)
    item_id = await adb(
        db.add_item,
        req.user_id,
        stock_item["name"],
        item_type=stock_item.get("item_type", "Item"),
        effect=stock_item.get("effect") or stock_item.get("description", ""),
        slot_cost=slot_cost
    )

    # Decrement stock quantity
    stock_item["quantity"] = max(0, int(stock_item.get("quantity", 1)) - 1)
    if stock_item["quantity"] <= 0:
        stock.pop(target_idx)
    else:
        stock[target_idx] = stock_item
    merchant[stock_field] = stock

    # Sync with active catalogue if present
    active_key = merchant.get("active_store_key")
    catalogues = merchant.get("catalogues")
    if isinstance(catalogues, dict) and not req.is_phone_shop:
        if active_key and active_key in catalogues and isinstance(catalogues[active_key], dict):
            catalogues[active_key]["stock"] = stock
        else:
            for cat in catalogues.values():
                if isinstance(cat, dict) and "stock" in cat:
                    cat["stock"] = stock

    await adb(db.save_merchant_state, req.session_id, merchant)
    updated_char = await adb(db.get_character, req.user_id)

    return {
        "success": True,
        "item_id": item_id,
        "item_name": stock_item["name"],
        "price_paid": price,
        "gold": updated_char.get("gold", 0) if updated_char else 0,
        "stock": stock
    }


@router.post("/api/merchant/sell")
async def merchant_sell(req: MerchantSellRequest):
    """Sells an unequipped item from the player's inventory to the merchant."""
    session = await adb(db.get_session, req.session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    char = await adb(db.get_character, req.user_id)
    if not char:
        raise HTTPException(status_code=404, detail="Character not found")

    items = await adb(db.get_inventory, req.user_id)
    target_item = next((dict(i) for i in items if i.get("id") == req.item_id), None)
    if not target_item:
        raise HTTPException(status_code=404, detail="Item not found in inventory")

    if target_item.get("equipped"):
        raise HTTPException(status_code=400, detail="Unequip this item before selling it")
    if is_key_item(target_item) or is_digital_item(target_item):
        raise HTTPException(status_code=400, detail="This item cannot be sold")

    scen_key = session.get("scenario", "fantasy")
    merchant = dict(session.get("merchant") or {})
    discount_pct = _compute_charisma_discount(char, merchant)
    tier = parse_item_tier(target_item)
    base_val = max(2, calculate_balanced_price(target_item.get("item_type", "Item"), target_item.get("name", "Item"), tier=tier, scen_key=scen_key) // 3)
    sell_price = sell_bonus_price(base_val, discount_pct // 2)

    removed = await adb(db.remove_item, req.user_id, req.item_id)
    if not removed:
        raise HTTPException(status_code=400, detail="Could not remove item from inventory")

    await adb(db.apply_hp_mp_delta, req.user_id, gold_delta=sell_price)
    updated_char = await adb(db.get_character, req.user_id)

    return {
        "success": True,
        "item_name": target_item.get("name"),
        "gold_earned": sell_price,
        "gold": updated_char.get("gold", 0) if updated_char else 0
    }
