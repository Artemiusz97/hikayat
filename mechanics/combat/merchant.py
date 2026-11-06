from __future__ import annotations
"""
Merchant Mechanic Module for Hikayat.

Provides modular merchant encounters, shop generation, item sale evaluations,
and Discord UI views (MerchantView, MerchantVoteView, BuySelectView, SellSelectView, RumorView).
"""
import json
import logging
import random
from typing import Optional, Dict, Any, List, Tuple, Union

import db
import namegen
import scenario_data
from scenario_data import is_nsfw_scenario
from llm_client import call_llm_json

log = logging.getLogger(__name__)

def merchant_prompt_note(triggered: bool = False, scen_key: str = None) -> str:
    """Format GM prompt note for merchant presence."""
    from mechanics.world.locations import is_school_scenario
    if is_school_scenario(scen_key):
        return ("\nMERCHANTS: In modern high school settings, DO NOT generate wandering roadside merchants. "
                "Shopping is strictly handled at designated campus/commercial stores and via the smartphone delivery app.\n")
    return ("\nMERCHANTS: Do not force a merchant encounter. However, if the scene naturally takes place in a shop/bazaar, "
            "or if you generate a story choice to approach a roadside trader/caravan, set `merchant_encounter.present: true`. "
            "A dedicated UI button will handle opening the shop, so DO NOT generate skill-check choices for basic browsing/buying/selling.\n")


MERCHANT_ENCOUNTER_FIELD = """{"present": boolean, "name": "string (token if new)", "description": "short flavor sentence"}"""

MERCHANT_STOCK_ITEM_FIELD = ('{"name": "string", "item_type": "Weapon|Shield|Armor|Head|Top|Bottom|Gloves|Shoes|Accessory|Clothing|Lingerie|'
                             'Consumable|Item|Gift|Novelty|Potion|Food|Spellbook", "description": "short flavor sentence", "price": integer, "quantity": integer 1-5}')

MERCHANT_SHOP_SCHEMA = f"""{{
  "intro_narrative": "string, 1-2 immersive sentences introducing the merchant and their wares, in the moment",
  "stock": [{MERCHANT_STOCK_ITEM_FIELD}],
  "rumors": ["string", "string", "string"]
}}"""

# -----------------------------------------------------------------------------
# MERCHANT ARCHETYPES REGISTRY
# -----------------------------------------------------------------------------
MERCHANT_ARCHETYPES: dict[str, dict] = {
    # Standard & Combat Archetypes
    "weapon_merchant": {
        "title": "Weaponsmith & Armorer",
        "emoji": "⚔️",
        "intro_template": "The heat of the forge greets you. Looking for finely balanced steel, ranged arms, or heavy shields?",
        "instruction": "Exclusively generate weapons (swords, axes, bows, daggers, firearms, staves) and shields. Include Tier 2 (Superior/Enchanted) and Tier 1 (Masterwork) items with balanced pricing.",
        "allowed_types": ["Weapon", "Shield"],
        "tier_focus": [2, 1, 2, 3],
    },
    "armor_merchant": {
        "title": "Aegis Armory & Outfitter",
        "emoji": "🛡️",
        "intro_template": "Suits of polished armor and reinforced gear line the walls. Looking for sturdy protection?",
        "instruction": "Exclusively generate wearable protective equipment (Armor, Headwear/Helmets, Tops, Bottoms, Gloves, Shoes, Cloaks, and defensive Accessories). Include Tier 2 and Tier 1 gear.",
        "allowed_types": ["Armor", "Head", "Top", "Bottom", "Gloves", "Shoes", "Accessory"],
        "tier_focus": [2, 2, 1, 3],
    },
    "potion_merchant": {
        "title": "Apothecary & Alchemist",
        "emoji": "🧪",
        "intro_template": "Bubbling flasks and fragrant herbs fill the air. Need healing draughts, battle elixirs, or remedies?",
        "instruction": "Exclusively generate 3-tier potions: Healing Draughts (T3 Lesser, T2 Potent, T1 Supreme), Mana Tonics, Battle Elixirs (Iron Skin, Haste, Berserker), Antidotes/Panaceas, and Throwable Flasks (Fire, Acid, Toxin).",
        "allowed_types": ["Consumable", "Potion"],
        "tier_focus": [3, 2, 2, 1],
    },
    "magic_merchant": {
        "title": "Mystic Emporium",
        "emoji": "🔮",
        "intro_template": "Arcane energy hums softly in the chamber. Browse enchanted relics, wands, and magical talismans.",
        "instruction": "Generate magic-infused gear, staves, wands, enchanted amulets, elemental rings, and arcane cloaks with magical flavor.",
        "allowed_types": ["Weapon", "Accessory", "Top", "Item"],
        "tier_focus": [2, 1, 2, 2],
    },
    "spellbook_merchant": {
        "title": "Arcane Scribe & Library",
        "emoji": "📖",
        "intro_template": "Shelves of ancient grimoires and illuminated manuscripts beckon. Study new spells and lost rites.",
        "instruction": "Exclusively generate learnable spellbooks, tomes, and grimoires across Basic, Adept, and Master tiers.",
        "allowed_types": ["Spellbook"],
        "tier_focus": [3, 2, 1],
    },
    "food_merchant": {
        "title": "Bakery & Tavern Provisions",
        "emoji": "🍞",
        "intro_template": "The aroma of freshly baked bread, roasted meats, and hearty stews warms the room.",
        "instruction": "Exclusively generate 3-tier food items: Snacks/Rations (T3), Hearty Meals/Roasts/Bentos (T2), and Gourmet Banquets/Ambrosia (T1).",
        "allowed_types": ["Food", "Consumable"],
        "tier_focus": [3, 2, 2, 1],
    },
    "general_merchant": {
        "title": "General Trading Post",
        "emoji": "🎒",
        "intro_template": "A bit of everything for travelers on the road.",
        "instruction": "Generate a balanced mix of basic tools, torches, bandages, plain daggers, trail bread, and minor potions (mostly Tier 3).",
        "allowed_types": ["Weapon", "Consumable", "Food", "Item", "Top"],
        "tier_focus": [3, 3, 3, 2],
    },
    "adult_store_merchant": {
        "title": "Velvet Curtain Adult Boutique",
        "emoji": "🔞",
        "intro_template": "Dim velvet lighting and alluring scents greet you. Looking for sensual lingerie, discreet accessories, or intimate novelties?",
        "instruction": "Generate adult NSFW items: sensual lace lingerie, silk corsets, garter sets, satin cuffs/collars, massage oils, and adult novelties suitable for intimate roleplay.",
        "allowed_types": ["Lingerie", "Top", "Bottom", "Accessory", "Consumable", "Weapon", "Novelty"],
        "tier_focus": [2, 2, 1, 3],
    },
    # Non-Combat / High School Archetypes
    "school_merchant": {
        "title": "Campus Co-op & Bookshop",
        "emoji": "🏫",
        "intro_template": "Welcome to the school store! Grab your stationery, notebooks, replacement uniform ties, and student passes.",
        "instruction": "Generate school supplies, notebooks, fountain pens, uniform accessories, lunch vouchers, and study aids for high school drama.",
        "allowed_types": ["Item", "Accessory"],
        "tier_focus": [3, 3, 2],
    },
    "cafe_merchant": {
        "title": "Local Café & Bakery",
        "emoji": "☕",
        "intro_template": "Welcome! Would you like a warm matcha latte, fresh croissant, or artisanal dessert parfait?",
        "instruction": "Exclusively generate cafe beverages (coffees, matcha lattes, teas, boba, smoothies), bakery pastries (croissants, melon pan, scones), artisanal cakes/desserts, and light cafe snacks. Keep heavy hot restaurant entrees for the diner.",
        "allowed_types": ["Food", "Consumable"],
        "tier_focus": [3, 2, 2, 1],
    },
    "restaurant_merchant": {
        "title": "Downtown Diner & Family Restaurant",
        "emoji": "🍽️",
        "intro_template": "Welcome to a booth! Can we start you off with sizzling hamburger steak, omurice, tonkotsu ramen, or an ice-cold melon float?",
        "instruction": "Exclusively generate hearty hot restaurant meals, savory diner entrees (omurice, ramen, curry rice, steak platters, pasta, burgers), and soft drinks/floats across Tiers 3, 2, and 1.",
        "allowed_types": ["Food", "Consumable"],
        "tier_focus": [3, 2, 2, 1],
    },
    "convenience_merchant": {
        "title": "24-Hour Convenience Store",
        "emoji": "🏪",
        "intro_template": "Fluorescent konbini aisles hum quietly—fresh onigiri, warm steamed buns, chilled sodas, and everyday sundries line the shelves.",
        "instruction": "Generate convenience store items: onigiri rice balls, konbini bentos, instant noodles, canned coffee, sodas, vinyl umbrellas, and daily sundries (Tier 3 and Tier 2).",
        "allowed_types": ["Food", "Consumable", "Item"],
        "tier_focus": [3, 3, 2],
    },
    "clothes_merchant": {
        "title": "Streetwear & Casual Apparel",
        "emoji": "👕",
        "intro_template": "Welcome in! Browse everyday streetwear, hoodies, casual blouses, pleated skirts, slacks, and sneakers.",
        "instruction": "Generate everyday casual clothes and streetwear (Tier 3 Standard and Tier 2 Stylish): hoodies, graphic tees, blouses, sweaters, jeans, skirts, slacks, and casual sneakers.",
        "allowed_types": ["Top", "Bottom", "Shoes", "Clothing"],
        "tier_focus": [3, 3, 2, 2],
    },
    "brand_clothes_merchant": {
        "title": "Luxury Designer Boutique",
        "emoji": "✨",
        "intro_template": "Polished marble floors and spotlighted mannequins welcome you. Allow our stylist to present this season's high-fashion collection.",
        "instruction": "Exclusively generate high-tier luxury designer fashion (Tier 2 Stylish and Tier 1 Masterwork Haute Couture): tailored cashmere coats, silk blouses, runway dresses, bespoke slacks, and designer footwear.",
        "allowed_types": ["Top", "Bottom", "Shoes", "Accessory", "Clothing"],
        "tier_focus": [2, 1, 2, 1],
    },
    "accessories_merchant": {
        "title": "Accessories & Bijoux Emporium",
        "emoji": "💍",
        "intro_template": "Glass display cases gleam with silver lockets, delicate charm bracelets, wristwatches, silk ribbons, and designer eyewear.",
        "instruction": "Exclusively generate wearable accessories and jewelry across Tiers 3, 2, and 1: silver lockets, pendant necklaces, rings, charm bracelets, wristwatches, hairpins, silk ribbons, scarves, and stylish glasses.",
        "allowed_types": ["Accessory", "Gift"],
        "tier_focus": [3, 2, 1, 2],
    },
    "gift_merchant": {
        "title": "Curio & Gift Shop",
        "emoji": "🎁",
        "intro_template": "Looking for the perfect present? Check out our plushies, music boxes, scented candles, and keepsake charms.",
        "instruction": "Generate giftable items: plush toys, music boxes, lucky shrine amulets, scented candles, souvenir keychains, pressed-flower frames, and idol merch.",
        "allowed_types": ["Gift", "Accessory", "Item"],
        "tier_focus": [3, 2, 1, 2],
    },
    "night_market_merchant": {
        "title": "Lantern Night Market Bazaar",
        "emoji": "🏮",
        "intro_template": "String lanterns glow overhead while smoky grills sizzle! Grab hot street skewers, candied fruit, and handmade festival trinkets!",
        "instruction": "Generate vibrant night market street food (yakitori skewers, takoyaki, taiyaki, candied strawberries, ramune) alongside artisanal bazaar charms, hairpins, and trinkets.",
        "allowed_types": ["Food", "Consumable", "Gift", "Accessory"],
        "tier_focus": [3, 2, 2, 1],
    },
    "nightclub_merchant": {
        "title": "Neon Pulse VIP Lounge Bar",
        "emoji": "🍸",
        "intro_template": "Bass reverberates beneath neon strobes as the bartender slides a frosted menu across the glowing counter.",
        "instruction": "Generate nightclub lounge beverages and upscale bar bites: glowing house cocktails, sparkling mocktails, energy mixers, VIP bottle service, and lounge tapas.",
        "allowed_types": ["Consumable", "Food"],
        "tier_focus": [2, 2, 1, 3],
    },
    "student_merchant": {
        "title": "Student Dealer",
        "emoji": "🤫",
        "intro_template": "Psst... over here. Keep it quiet. What do you need?",
        "instruction": "Generate contraband and school secrets: exam cheat sheets, forged hall passes, smuggled sodas, locker gossip notes, and lockpick hairpins.",
        "allowed_types": ["Item", "Novelty"],
        "tier_focus": [2, 2, 3],
    },
    "club_merchant": {
        "title": "Club & Delinquent Hangout",
        "emoji": "🥊",
        "intro_template": "You stepped into the hangout. Here's what we have for members.",
        "instruction": "Generate club-specific gear, custom armbands, spray paint cans, sports tape, team badges, and locker tools.",
        "allowed_types": ["Accessory", "Item"],
        "tier_focus": [3, 2, 2],
    },
    "online_merchant": {
        "title": "Online Delivery Store",
        "emoji": "📱",
        "intro_template": "ChronoStore delivery app: Order everyday snacks, drinks, stationery, and study essentials for instant delivery.",
        "instruction": "Exclusively generate everyday snacks, bottled/canned drinks, stationery, study supplies, and basic daily essentials (Tier 3 and Tier 2 only). Specialty Downtown fashion, jewelry, gifts, hot diner meals, and adult boutique goods require in-person visits.",
        "allowed_types": ["Item", "Food", "Consumable"],
        "tier_focus": [3, 3, 2],
    }
}


def _apply_world_event_shop_multiplier(ctx: dict, session: dict | None, is_phone_shop: bool = False) -> dict:
    if is_phone_shop or not isinstance(session, dict) or not session.get("id"):
        return ctx
    try:
        from mechanics.world.world_events.modifiers import compute_merchant_event_multiplier
        snap = session.get("_world_events_snapshot") or db.get_world_events_snapshot(int(session["id"]))
        loc_nid = str(session.get("current_node_id") or session.get("current_location_id") or "")
        ev_mult = compute_merchant_event_multiplier(snap, location_node_id=loc_nid)
        if ev_mult != 1.0 and not ctx.get("is_monastic_free_shop"):
            base_m = float(ctx.get("price_multiplier", 1.0) or 1.0)
            ctx["price_multiplier"] = round(max(0.5, min(2.0, base_m * ev_mult)), 3)
            if ev_mult < 1.0:
                ctx["is_event_discounted_shop"] = True
    except Exception:
        pass
    return ctx



def stamp_discounted_purchase_metadata(item_eff: str, price_paid: int) -> str:
    """Embeds purchase_price_paid into item metadata/effect so resale cannot arbitrage festival discounts."""
    eff_str = str(item_eff or "")
    paid_int = max(0, int(price_paid))
    for prefix in ("[ITEM_JSON]", "[GEAR_JSON]", "[CONSUMABLE_JSON]"):
        if eff_str.startswith(prefix):
            try:
                meta_obj = json.loads(eff_str[len(prefix):])
                if isinstance(meta_obj, dict):
                    meta_obj["purchase_price_paid"] = paid_int
                    return f"{prefix}{json.dumps(meta_obj)}"
            except Exception:
                pass
            return eff_str
    return f"[CONSUMABLE_JSON]{json.dumps({'description': eff_str, 'purchase_price_paid': paid_int})}"


def get_anomalous_shop_faction_context(
    session: dict | None,
    location: str = "",
    is_phone_shop: bool = False,
    user_id: int | None = None,
) -> dict:
    """
    Resolves Faction Merchant pricing, quality bias, access gates, and daily free stock rules
    for the Anomalous Incursions scenario.
    """
    ctx = {
        "is_anomalous": False,
        "allowed": True,
        "access_denied_reason": "",
        "shop_faction_archetype": None,
        "player_faction_archetype": "freelancer",
        "price_multiplier": 1.0,
        "private_agency_bonus": False,
        "is_monastic_free_shop": False,
        "is_monastic_free_ration": False,
        "shrine_free_remaining": 0,
        "is_public_discounted_shop": False,
        "pricing_badge": None,
    }
    if not session or is_phone_shop:
        return _apply_world_event_shop_multiplier(ctx, session, is_phone_shop=is_phone_shop)
    scen_key = session.get("scenario", "")
    if not scenario_data.is_anomalous_incursions_scenario(scen_key):
        return _apply_world_event_shop_multiplier(ctx, session, is_phone_shop=is_phone_shop)


    ctx["is_anomalous"] = True
    session_id = session.get("id")
    loc_str = str(location or session.get("current_location") or "").lower().strip()
    loc_id = str(session.get("current_node_id") or session.get("current_location_id") or "").lower().strip()
    if location and (location.startswith("loc_") or location.startswith("sub_")):
        loc_id = location.lower().strip()

    from mechanics.social.factions import get_anomalous_faction_state
    a_state = get_anomalous_faction_state(session_id, user_id=user_id) if session_id else {}
    player_arch = str(
        a_state.get("faction_archetype_key")
        or a_state.get("primary_faction_archetype")
        or "freelancer"
    )
    ctx["player_faction_archetype"] = player_arch
    suspended = bool(a_state.get("salary_ration_suspended", False))

    # Determine which faction owns the current shop location (or active Quartermaster shop)
    merch_state = session.get("merchant") or {}
    qm_arch = (
        str(merch_state.get("quartermaster_faction_arch") or "").strip().lower()
        if isinstance(merch_state, dict) and merch_state.get("is_faction_quartermaster") and not location
        else ""
    )
    shop_arch = qm_arch or None
    if not shop_arch and isinstance(merch_state, dict) and merch_state.get("is_faction_quartermaster") and merch_state.get("quartermaster_faction_arch"):
        # If player opened a Quartermaster catalogue explicitly, honor its faction archetype
        active_sk = str(merch_state.get("active_store_key") or "")
        if active_sk.startswith("faction_"):
            shop_arch = str(merch_state.get("quartermaster_faction_arch")).strip().lower()

    priv1_hq_name = ""
    priv2_hq_name = ""
    if session_id:
        try:
            for fac in (db.get_factions(session_id) or []):
                f_arch = str(fac.get("category") or fac.get("archetype_key") or "").lower()
                if f_arch == "private_agency_1":
                    priv1_hq_name = str(fac.get("name") or "").lower()
                elif f_arch == "private_agency_2":
                    priv2_hq_name = str(fac.get("name") or "").lower()
        except Exception:
            pass

    if shop_arch:
        pass
    elif (
        loc_id.startswith("sub_priv1_")
        or loc_id in ("loc_private_hq_1_armory", "loc_private_hq_1", "loc_private_hq_1_lobby")
        or "regional tower hq" in loc_str
        or "corporate tower hq" in loc_str
        or "tower hq" in loc_str
        or any(k in loc_str for k in (
            "in-house r&d ordnance", "exo-weave & ballistic atelier",
            "neural-cleanse suite", "skyline executive espresso",
        ))
        or (priv1_hq_name and priv1_hq_name in loc_str)
    ):
        shop_arch = "private_agency_1"
    elif (
        loc_id.startswith("sub_priv2_")
        or loc_id in ("loc_private_hq_2_armory", "loc_private_hq_2", "loc_private_hq_2_lobby")
        or "field office hq" in loc_str
        or "office hq" in loc_str
        or "operations spire hq" in loc_str
        or "operations hq" in loc_str
        or any(k in loc_str for k in (
            "back-room gun cage", "surplus locker", "patching corner",
            "first-aid cot", "drip-coffee kitchenette",
        ))
        or (priv2_hq_name and priv2_hq_name in loc_str)
    ):
        shop_arch = "private_agency_2"
    elif any(k in loc_str for k in (
        "syndicate anomalous armory", "syndicate tactical armory", "requisition shop",
        "requisition depot", "bespoke ballistic outfitter", "corporate trauma", "skyline executive espresso",
    )):
        shop_arch = player_arch if player_arch in ("private_agency_1", "private_agency_2") else "private_agency_1"
    elif (
        loc_id in ("loc_et_omikuji_shop", "loc_et_torii_approach", "loc_et_main_sanctuary", "loc_eastern_temple", "zone_eastern_temple")
        or any(k in loc_str for k in ("omikuji", "talisman stand", "grand shrine", "eastern temple", "eastern grand temple"))
    ):
        shop_arch = "monastic_order"
    elif (
        loc_id in (
            "loc_hq_tactical_armory", "loc_hq_field_outfitter", "loc_hq_cleansing_bay", "loc_hq_canteen_cafe",
            "loc_hq_armory", "loc_hq_outfitter", "loc_hq_medical_bay", "loc_hq_cafe", "zone_agency_hq",
        )
        or (
            any(k in loc_str for k in (
                "tactical armory", "ordnance depot", "field outfitter", "ballistic tailor",
                "psychic cleansing bay", "bureau canteen", "containment armory", "agents' breakroom",
                "agency hq", "headquarters",
            ))
            and "shadow exchange" not in loc_str
        )
    ):
        shop_arch = "public_agency"

    elif (
        loc_id == "sub_custodian_boiler_locker"
        or any(k in loc_str for k in ("custodian's boiler-room locker", "boiler-room locker", "custodian's boiler"))
    ):
        shop_arch = "student_boiler_locker"

    ctx["shop_faction_archetype"] = shop_arch

    if shop_arch == "public_agency":
        if player_arch == "public_agency":
            ctx["price_multiplier"] = 0.50
            ctx["is_public_discounted_shop"] = True
            ctx["pricing_badge"] = "🏛️ Public Agency Requisition (-50% Official Discount)"
        else:
            ctx["price_multiplier"] = 1.0
            ctx["pricing_badge"] = "🏛️ Public Agency Storefront (1.0x Standard Price for External Operatives)"
    elif shop_arch == "private_agency_1":
        ctx["private_agency_bonus"] = True
        if player_arch == shop_arch:
            ctx["price_multiplier"] = 1.35
            ctx["pricing_badge"] = "🏢 Corporate R&D Armory (1.35x Proprietary Markup • +20% Anomalous & Prototype Stock)"
        else:
            ctx["allowed"] = False
            ctx["access_denied_reason"] = (
                "Corporate R&D Armory requisition is restricted exclusively to operatives under conglomerate contract."
            )
            ctx["price_multiplier"] = 1.35
            ctx["pricing_badge"] = "🔒 Corporate R&D Armory (Conglomerate Staff Only)"
    elif shop_arch == "private_agency_2":
        ctx["private_agency_bonus"] = True
        if player_arch == shop_arch:
            ctx["price_multiplier"] = 1.35
            ctx["pricing_badge"] = "🏪 Agency Surplus & Broker Cage (1.35x Broker Markup • +20% Anomalous & Salvage Stock)"
        else:
            ctx["allowed"] = False
            ctx["access_denied_reason"] = (
                "The padlocked back-room gun cage and surplus locker are strictly for this local agency's contracted staff."
            )
            ctx["price_multiplier"] = 1.35
            ctx["pricing_badge"] = "🔒 Agency Surplus & Broker Cage (Local Agency Staff Only)"
    elif shop_arch == "monastic_order":
        if player_arch == "monastic_order":
            max_daily = int(a_state.get("shrine_free_max_daily", 3) or 3)
            claimed = int(a_state.get("shrine_free_claims_today", a_state.get("shrine_free_claimed_today", 0)) or 0)
            rem = 0 if suspended else max(0, max_daily - claimed)
            ctx["shrine_free_remaining"] = rem
            if not suspended and rem > 0:
                ctx["is_monastic_free_shop"] = True
                ctx["is_monastic_free_ration"] = True
                ctx["price_multiplier"] = 0.0
                ctx["pricing_badge"] = f"⛩️ Sacred Shrine Provision (FREE 0G • {rem}/{max_daily} Daily Grants Left)"
            elif suspended:
                ctx["price_multiplier"] = 1.0
                ctx["pricing_badge"] = "⚠️ Sacred Rations Suspended (0 Rep — Complete Mandatory Rite to Restore Free Grants)"
            else:
                ctx["shrine_daily_exhausted"] = True
                ctx["price_multiplier"] = 0.0
                ctx["pricing_badge"] = f"⛩️ Daily Sacred Grants Exhausted ({claimed}/{max_daily} Claimed Today — Refreshes Tomorrow)"
        else:
            ctx["price_multiplier"] = 1.0
            ctx["pricing_badge"] = "⛩️ Shrine Talisman & Curio Stand (Standard Visitor Pricing)"
    elif shop_arch == "student_boiler_locker":
        from mechanics.social.origin_mode import is_student_operative
        from mechanics.social.factions import is_school_club_faction
        if is_student_operative(session):
            ctx["allowed"] = True
            ctx["private_agency_bonus"] = True
            max_club_rep = 0
            if session_id:
                try:
                    for fac in (db.get_factions(session_id) or []):
                        if is_school_club_faction(fac):
                            max_club_rep = max(max_club_rep, int(fac.get("reputation_score") or 0))
                except Exception:
                    pass
            club_disc_pct = min(25, max(0, int(round(max_club_rep * 25 / 85)))) if max_club_rep > 0 else 0
            ctx["price_multiplier"] = round(max(0.75, 1.0 - (club_disc_pct / 100.0)), 2)
            disc_str = f" • -{club_disc_pct}% Club Standing Discount" if club_disc_pct > 0 else " • 1.0x Base Price"
            ctx["pricing_badge"] = f"🗝️ Custodian's Boiler-Room Locker (+20% Anomalous & Prototype Stock{disc_str})"
        else:
            ctx["allowed"] = False
            ctx["access_denied_reason"] = (
                "The Custodian's Boiler-Room Locker is an underground student-operative drop-box; adult agents are turned away at the boiler door."
            )
            ctx["price_multiplier"] = 1.0
            ctx["pricing_badge"] = "🔒 Custodian's Boiler-Room Locker (Student Operatives Only)"

    return _apply_world_event_shop_multiplier(ctx, session)




def compute_anomalous_resale_price(item_dict: dict, default_sell_price: int) -> int:
    """
    Enforces Anti-Exploit Resale Rules in Anomalous Incursions:
    - Monastic Shrine free items (`shrine_sacred_grant: True`) -> 0G resale value.
    - Public Agency 50%-discounted items (`purchase_price_paid`) -> capped at <= 50% of price paid.
    """
    if not item_dict or not isinstance(item_dict, dict):
        return default_sell_price

    from mechanics.combat.equipment import parse_equipment_metadata
    from mechanics.combat.items import parse_consumable_metadata

    eq_meta = parse_equipment_metadata(item_dict) or {}
    cons_meta = parse_consumable_metadata(item_dict) or {}
    raw_eff = str(item_dict.get("effect") or "")

    if (
        item_dict.get("shrine_sacred_grant")
        or eq_meta.get("shrine_sacred_grant")
        or cons_meta.get("shrine_sacred_grant")
        or '"shrine_sacred_grant": true' in raw_eff.lower()
        or '"shrine_sacred_grant":true' in raw_eff.lower()
    ):
        return 0

    paid = (
        item_dict.get("purchase_price_paid")
        if item_dict.get("purchase_price_paid") is not None
        else (
            eq_meta.get("purchase_price_paid")
            if eq_meta.get("purchase_price_paid") is not None
            else cons_meta.get("purchase_price_paid")
        )
    )
    if paid is not None:
        try:
            paid_int = int(paid)
            return min(default_sell_price, max(0, int(paid_int * 0.50)))
        except (TypeError, ValueError):
            pass
    return default_sell_price


def mark_vault_requisition_claimed(session: dict | None, item_name: str) -> list[dict] | None:
    """Marks a one-time Containment Vault requisition item as claimed in `session['anomalous_vault_requisitions']`."""
    if not isinstance(session, dict):
        return None
    req_list = [dict(r) for r in (session.get("anomalous_vault_requisitions") or []) if isinstance(r, dict)]
    bought_low = str(item_name or "").strip().lower()
    if not bought_low:
        return None
    for r_item in req_list:
        if str(r_item.get("name") or "").strip().lower() == bought_low and not r_item.get("requisitioned"):
            r_item["requisitioned"] = True
            session["anomalous_vault_requisitions"] = req_list
            return req_list
    return None


def calculate_balanced_price(
    item_type: str,
    item_name: str,
    tier: int = 3,
    scen_key: str = "fantasy",
    quality_tier: Optional[str] = None,
    enchantment_tier: Optional[str] = None,
    metadata: Optional[dict] = None
) -> int:
    """
    Calculates balanced base price according to item category and compound dual-axis tiers:
    Price = round(base_price * Quality_Multiplier) + Enchantment_Flat_Premium.
    Maintains 100% backward compatibility when only legacy `tier: int` is provided.
    """
    from mechanics.combat.equipment.tables import (
        QUALITY_PRICE_MULTIPLIERS,
        ENCHANTMENT_PREMIUMS,
        LEGACY_TIER_TO_DUAL_AXIS,
        derive_legacy_tier,
    )
    from mechanics.combat.items import parse_item_tier

    t = tier or parse_item_tier({"name": item_name, "item_type": item_type})
    q_tier = quality_tier
    e_tier = enchantment_tier

    if isinstance(metadata, str):
        try:
            metadata = json.loads(metadata)
        except Exception:
            metadata = None

    if metadata and isinstance(metadata, dict):
        q_tier = q_tier or metadata.get("quality_tier")
        e_tier = e_tier or metadata.get("enchantment_tier")

    if not q_tier or not e_tier:
        def_q, def_e = LEGACY_TIER_TO_DUAL_AXIS.get(t, ("regular", "none"))
        q_tier = q_tier or def_q
        e_tier = e_tier or def_e

    q_tier = str(q_tier).lower()
    e_tier = str(e_tier).lower()

    item_type_lower = (item_type or "").lower().strip()

    if item_type_lower in ("potion", "food", "consumable"):
        base_p = 15
    elif item_type_lower in ("weapon", "shield", "armor", "head", "top", "bottom", "gloves", "shoes", "accessory", "clothing", "lingerie", "outerwear"):
        base_p = 40
    elif item_type_lower == "spellbook":
        base_p = 80
    elif item_type_lower in ("gift", "novelty"):
        base_p = 20
    else:
        base_p = 18

    # Compound scale: base price scaled by quality multiplier + flat enchantment premium
    q_mult = QUALITY_PRICE_MULTIPLIERS.get(q_tier, 1.0)
    e_prem = ENCHANTMENT_PREMIUMS.get(e_tier, 0)
    final_price = int(round(base_p * q_mult)) + e_prem
    return max(1, final_price)


async def generate_merchant_shop(party: list, merchant_name: str, merchant_description: str,
                                  session: dict, is_phone_shop: bool = False, merchant_type: str = "general_merchant") -> dict:
    """Generate shop stock and rumors via LLM for a specific merchant archetype."""
    names = ", ".join(char["name"] for char, _ in party)
    scen_key = session.get("scenario", "fantasy")
    scen_info = scenario_data.get_scenario(scen_key)

    archetype = MERCHANT_ARCHETYPES.get(merchant_type, MERCHANT_ARCHETYPES["general_merchant"])
    arch_title = archetype["title"]
    arch_instruction = archetype["instruction"]
    arch_intro = archetype["intro_template"]

    active_hs_clerk = None
    if not is_phone_shop and merchant_type != "online_merchant":
        from mechanics.world.locations import is_school_scenario
        if is_school_scenario(scen_key) and isinstance(session, dict) and session.get("id"):
            try:
                from mechanics.social.town_roster import get_active_shop_clerk_for_location
                lead_uid = None
                if party and isinstance(party[0], (tuple, list)) and len(party[0]) > 1:
                    lead_uid = party[0][1]
                elif isinstance(party[0], dict) if party else False:
                    lead_uid = party[0].get("user_id")
                active_hs_clerk = get_active_shop_clerk_for_location(
                    session_id=int(session["id"]),
                    location_str=str(session.get("current_location") or ""),
                    merchant_type=merchant_type,
                    user_id=lead_uid,
                )
                if active_hs_clerk and (
                    not merchant_name
                    or merchant_name.strip().lower() in ("merchant", "clerk", "shopkeeper", "vendor", arch_title.lower())
                ):
                    merchant_name = active_hs_clerk["name"]
                    merchant_description = active_hs_clerk.get("description") or merchant_description
            except Exception:
                active_hs_clerk = None

    if is_phone_shop or merchant_type == "online_merchant":
        from mechanics.system.phone import get_phone_branding
        branding = get_phone_branding(scen_key)
        shop_title = branding["shop_app_name"]
        system_prompt = (
            f"Generate catalog wares for an in-game online storefront / delivery app ({shop_title}) appropriate to the active scenario.\n"
            f"- Intro narrative: A short, welcoming 1-2 sentence app interface greeting or catalog summary (e.g. 'Welcome to {shop_title}! Select your everyday snacks, drinks, study supplies, and daily essentials for immediate delivery.').\n"
            f"- Stock: 6-10 everyday items strictly limited to packaged snacks, bottled/canned drinks, stationery, study aids, and basic daily essentials (Tier 3 and Tier 2 only; NO luxury fashion, jewelry, boutique gifts, hot restaurant meals, or adult items), quantity 1-5 each.\n"
            f"- Rumors: Return empty list [] (rumors are browsed separately via the Gossip Feed app).\n"
            f"Respond with ONLY a single valid JSON object matching the schema exactly, no prose or code fences."
        )
        user_prompt = (
            f"{scenario_data.scenario_prompt_block(scen_info)}\n\n"
            f"Store App: {shop_title}\n"
            f"Party: {names}\n\n"
            f"Respond with JSON matching exactly this schema:\n{MERCHANT_SHOP_SCHEMA}"
        )
    else:
        system_prompt = (
            f"Generate stock wares and rumors for a {arch_title} appropriate to the active scenario/genre.\n"
            f"- Merchant Specialization Instruction: {arch_instruction}\n"
            f"- Stock: 4-6 items matching the specialization with vivid descriptive flavor. Prices should be placeholder integers.\n"
            f"- Rumors: Exactly 3 short rumors (hooks/gossip) relevant to the merchant's profession.\n"
            f"Respond with ONLY a single valid JSON object matching the schema exactly, no prose or code fences."
        )
        user_prompt = (
            f"{scenario_data.scenario_prompt_block(scen_info)}\n\n"
            f"Merchant: {merchant_name or arch_title} -- {merchant_description or arch_intro}\n"
            f"Location: {session.get('current_location', 'unknown')}\n"
            f"Party: {names}\n\n"
            f"Respond with JSON matching exactly this schema:\n{MERCHANT_SHOP_SCHEMA}"
        )

    _is_llm_mocked = hasattr(call_llm_json, "_mock_name")
    shop_ctx = get_anomalous_shop_faction_context(session, location=session.get("current_location", ""), is_phone_shop=is_phone_shop)
    priv_bonus = bool(shop_ctx.get("private_agency_bonus", False))
    tier_choices = [2, 2, 1, 2] if priv_bonus else [3, 3, 2]

    if _is_llm_mocked:
        result = await call_llm_json(system_prompt, user_prompt, temperature=0.8,
                                      is_nsfw=scenario_data.uses_nsfw_model(scen_key), use_utility=True)
        result = namegen.resolve_tokens_deep(result, scenario=scen_key)
    else:
        from mechanics.combat.items import generate_random_equipment as _gen_eq, generate_random_clothing as _gen_clothing
        from mechanics.combat.items.consumables import generate_procedural_potion, generate_procedural_food, generate_procedural_drink
        from mechanics.combat.items.envelope import serialize_item as _serialize_item
        procedural_stock = []
        if is_phone_shop or merchant_type == "online_merchant":
            procedural_stock.extend([
                generate_procedural_food(tier=3, taste_tags=["savory"], genre=scen_key),
                generate_procedural_drink(tier=3, genre=scen_key),
                {
                    "name": "Spiral Study Notebook & Gel Pens",
                    "item_type": "Item",
                    "description": "Everyday campus stationery bundle delivered in a padded mailer.",
                    "price": 18,
                    "quantity": 3,
                    "tier": 3,
                },
                {
                    "name": "Pocket Flashcard & Highlighter Kit",
                    "item_type": "Item",
                    "description": "Color-coded revision tabs and study cards for exam prep.",
                    "price": 32,
                    "quantity": 2,
                    "tier": 2,
                },
            ])
            if scenario_data.is_anomalous_high_school_scenario(scen_key):
                for _courier_slot in ("Weapon", "Armor", "Accessory 1"):
                    _c_eq = _gen_eq(
                        scenario=scen_key,
                        slot=_courier_slot,
                        tier=2,
                        private_agency_bonus=(_courier_slot == "Weapon"),
                    )
                    if _c_eq:
                        _c_eq["price"] = calculate_balanced_price(
                            _c_eq.get("item_type", "Item"),
                            _c_eq.get("name", ""),
                            tier=_c_eq.get("tier", 2),
                            scen_key=scen_key,
                            metadata=_c_eq.get("metadata"),
                        )
                        _c_eq["quantity"] = 1
                        procedural_stock.append(_c_eq)
                procedural_stock.append(generate_procedural_potion(tier=2, genre=scen_key))
        elif merchant_type in ("blacksmith", "armorer", "weaponsmith", "quartermaster", "general_merchant", "weapon_merchant", "armor_merchant"):
            slots = ["Weapon", "Weapon", "Armor", "Shield", "Top", "Accessory 1", "Gloves", "Shoes"]
            random.shuffle(slots)
            for s in slots[:4]:
                eq = _gen_eq(scenario=scen_key, slot=s, tier=random.choice(tier_choices), private_agency_bonus=priv_bonus)
                if eq:
                    eq["price"] = calculate_balanced_price(eq.get("item_type", "Item"), eq.get("name", ""), tier=eq.get("tier", 3), scen_key=scen_key, metadata=eq.get("metadata"))
                    eq["quantity"] = 1
                    procedural_stock.append(eq)
        elif merchant_type == "potion_merchant":
            p1 = generate_procedural_potion(tier=2 if priv_bonus else 3, genre=scen_key)
            p2 = generate_procedural_potion(tier=1 if priv_bonus else 2, genre=scen_key)
            procedural_stock.extend([p1, p2])
        elif merchant_type in ("food_merchant", "cafe_merchant", "tavern_merchant"):
            f1 = generate_procedural_food(tier=3, taste_tags=["sweet", "bakery"] if merchant_type == "cafe_merchant" else None, genre=scen_key)
            d1 = generate_procedural_drink(tier=3, genre=scen_key)
            procedural_stock.extend([f1, d1])
        elif merchant_type == "restaurant_merchant":
            procedural_stock.extend([
                generate_procedural_food(tier=3, taste_tags=["savory", "comfort"], genre=scen_key),
                generate_procedural_food(tier=2, taste_tags=["savory", "comfort"], genre=scen_key),
                generate_procedural_food(tier=1, taste_tags=["savory", "gourmet"], genre=scen_key),
                generate_procedural_drink(tier=3, genre=scen_key),
            ])
        elif merchant_type == "convenience_merchant":
            procedural_stock.extend([
                generate_procedural_food(tier=3, taste_tags=["savory"], genre=scen_key),
                generate_procedural_drink(tier=3, genre=scen_key),
                {
                    "name": "Clear Vinyl Umbrella",
                    "item_type": "Item",
                    "description": "Sturdy transparent umbrella racked beside the konbini entrance.",
                    "price": 15,
                    "quantity": 4,
                    "tier": 3,
                },
                {
                    "name": "Chilled Konbini Bento Box",
                    "item_type": "Food",
                    "description": "Balanced convenience store bento ready to warm behind the counter.",
                    "price": 24,
                    "quantity": 3,
                    "tier": 3,
                },
            ])
        elif merchant_type == "clothes_merchant":
            for s, t in (("Top", 3), ("Bottom", 3), ("Top", 2), ("Bottom", 2)):
                cl = _gen_clothing(scenario=scen_key, slot=s, tier=t)
                if cl:
                    cl["price"] = calculate_balanced_price("Clothing", cl.get("name", ""), tier=t, scen_key=scen_key, metadata=cl.get("metadata"))
                    cl["quantity"] = 1
                    procedural_stock.append(cl)
        elif merchant_type == "brand_clothes_merchant":
            for s, t in (("Top", 2), ("Bottom", 2), ("Top", 1), ("Bottom", 1)):
                cl = _gen_clothing(scenario=scen_key, slot=s, tier=t)
                if cl:
                    cl["price"] = calculate_balanced_price("Clothing", cl.get("name", ""), tier=t, scen_key=scen_key, metadata=cl.get("metadata"))
                    cl["quantity"] = 1
                    procedural_stock.append(cl)
        elif merchant_type == "accessories_merchant":
            for t in (3, 2, 2, 1):
                eq = _gen_eq(scenario=scen_key, slot="Accessory 1", tier=t, private_agency_bonus=False)
                if eq:
                    eq["item_type"] = "Accessory"
                    eq["price"] = calculate_balanced_price("Accessory", eq.get("name", ""), tier=t, scen_key=scen_key, metadata=eq.get("metadata"))
                    eq["quantity"] = 1
                    procedural_stock.append(eq)
        elif merchant_type == "gift_merchant":
            procedural_stock.extend([
                {
                    "name": "Soft Pastel Plush Mascot",
                    "item_type": "Gift",
                    "description": "Huggable stitched plushie wrapped in a satin ribbon.",
                    "price": 28,
                    "quantity": 3,
                    "tier": 3,
                },
                {
                    "name": "Artisanal Lavender Scented Candle",
                    "item_type": "Gift",
                    "description": "Hand-poured glass jar candle with calming floral notes.",
                    "price": 75,
                    "quantity": 2,
                    "tier": 2,
                },
                {
                    "name": "Handcrafted Silver Music Box",
                    "item_type": "Gift",
                    "description": "Delicate mechanical music box that plays a nostalgic crystalline melody.",
                    "price": 290,
                    "quantity": 1,
                    "tier": 1,
                },
            ])
        elif merchant_type == "night_market_merchant":
            procedural_stock.extend([
                generate_procedural_food(tier=3, taste_tags=["savory"], genre=scen_key),
                generate_procedural_food(tier=2, taste_tags=["sweet"], genre=scen_key),
                generate_procedural_drink(tier=3, genre=scen_key),
                {
                    "name": "Hand-Painted Lantern Hairpin",
                    "item_type": "Accessory",
                    "description": "Artisanal bazaar hairpin enameled with warm festival motifs.",
                    "price": 95,
                    "quantity": 2,
                    "tier": 2,
                },
            ])
        elif merchant_type == "nightclub_merchant":
            procedural_stock.extend([
                generate_procedural_drink(tier=2, genre=scen_key),
                generate_procedural_drink(tier=1, genre=scen_key),
                generate_procedural_food(tier=2, taste_tags=["savory"], genre=scen_key),
            ])
        elif merchant_type == "adult_store_merchant":
            lace_meta = {
                "name": "Sheer Midnight Lace Lingerie Set",
                "tier": 2,
                "tier_name": "Superior",
                "slot": "Lingerie",
                "item_type": "Lingerie",
                "base_dt": 0,
                "dt": 0,
                "type_dt": {},
                "social_modifiers": {"cha": 1},
                "stat_modifiers": {"cha": 1},
                "social_affinity_bonus": 2,
                "social_flags": ["seductive", "delicate", "intimate"],
            }
            corset_meta = {
                "name": "Crimson Silk Couture Corset & Garter",
                "tier": 1,
                "tier_name": "Masterwork",
                "slot": "Lingerie",
                "item_type": "Lingerie",
                "base_dt": 0,
                "dt": 0,
                "type_dt": {},
                "social_modifiers": {"cha": 1},
                "stat_modifiers": {"cha": 1},
                "social_affinity_bonus": 4,
                "social_flags": ["seductive", "luxury", "intimate"],
            }
            procedural_stock.extend([
                {
                    "name": lace_meta["name"],
                    "item_type": "Lingerie",
                    "slot": "Lingerie",
                    "description": "Delicate scalloped black lace lingerie set boxed in discreet velvet tissue.",
                    "price": 165,
                    "quantity": 2,
                    "tier": 2,
                    "metadata": lace_meta,
                    "effect": _serialize_item(lace_meta),
                },
                {
                    "name": corset_meta["name"],
                    "item_type": "Lingerie",
                    "slot": "Lingerie",
                    "description": "Bespoke crimson silk corset with matching satin garter straps.",
                    "price": 520,
                    "quantity": 1,
                    "tier": 1,
                    "metadata": corset_meta,
                    "effect": _serialize_item(corset_meta),
                },
                {
                    "name": "Velvet Ribbon Wrist Cuffs",
                    "item_type": "Accessory",
                    "description": "Plush satin-lined cuffs secured with a quick-release silver clasp.",
                    "price": 130,
                    "quantity": 2,
                    "tier": 2,
                },
                {
                    "name": "Warm Jasmine Massage Oil",
                    "item_type": "Consumable",
                    "description": "Aromatic warming body oil bottled in dark amber glass.",
                    "price": 65,
                    "quantity": 3,
                    "tier": 2,
                },
            ])
        elif merchant_type == "school_merchant":
            procedural_stock.extend([
                {
                    "name": "Campus Co-op Notebook Set",
                    "item_type": "Item",
                    "description": "Crisp grid-lined notebooks stamped with the academy crest.",
                    "price": 15,
                    "quantity": 5,
                    "tier": 3,
                },
                {
                    "name": "Spare Silk Uniform Ribbon & Tie",
                    "item_type": "Accessory",
                    "description": "Freshly pressed replacement academy neckwear.",
                    "price": 35,
                    "quantity": 3,
                    "tier": 3,
                },
            ])
        else:
            slots = ["Weapon", "Accessory 1", "Top", "Shoes"]
            for s in slots[:3]:
                eq = _gen_eq(scenario=scen_key, slot=s, tier=random.choice(tier_choices), private_agency_bonus=priv_bonus)
                if eq:
                    eq["price"] = calculate_balanced_price(eq.get("item_type", "Item"), eq.get("name", ""), tier=eq.get("tier", 3), scen_key=scen_key, metadata=eq.get("metadata"))
                    eq["quantity"] = 1
                    procedural_stock.append(eq)
        result = {
            "intro_narrative": f"{merchant_name or arch_title} welcomes you into the shop.",
            "stock": procedural_stock,
            "rumors": [
                "Trade routes have been lively lately.",
                "Word is, rare goods may be arriving from the capital soon."
            ]
        }

    from mechanics.combat.items import parse_item_tier
    from mechanics.world.locations import is_school_scenario as _is_hs_scen
    stock = []
    for entry in result.get("stock", []) or []:
        if not isinstance(entry, dict) or not entry.get("name"):
            continue
        item_name = str(entry["name"])[:60]
        item_type = str(entry.get("item_type", "Item"))[:30]
        if scenario_data.is_anomalous_incursions_scenario(scen_key) and (
            item_type.lower() == "spellbook"
            or any(item_name.lower().startswith(p) for p in ("spellbook:", "grimoire:", "tome:", "scroll:"))
        ):
            continue
        if (is_phone_shop or merchant_type == "online_merchant") and _is_hs_scen(scen_key):
            if item_type.lower() in ("lingerie", "weapon", "shield", "armor", "spellbook"):
                continue
        desc = str(entry.get("description", ""))[:200]
        tier = parse_item_tier({"name": item_name, "description": desc, "item_type": item_type, "metadata": entry.get("metadata")})
        if (is_phone_shop or merchant_type == "online_merchant") and _is_hs_scen(scen_key) and tier == 1:
            tier = 2

        # Calculate balanced pricing
        balanced_price = int(entry.get("price") or 0) or calculate_balanced_price(item_type, item_name, tier=tier, scen_key=scen_key, metadata=entry.get("metadata"))
        try:
            quantity = max(1, min(9, int(entry.get("quantity", 1))))
        except (TypeError, ValueError):
            quantity = 1

        st_entry = {
            "name": item_name,
            "item_type": item_type,
            "description": desc,
            "price": balanced_price,
            "quantity": quantity,
            "tier": tier,
        }
        for keep_k in ("effect", "metadata", "slot", "slot_cost"):
            if entry.get(keep_k) is not None:
                st_entry[keep_k] = entry[keep_k]
        stock.append(st_entry)

    # Integrate Procedural Potions for Potion Merchants
    if merchant_type == "potion_merchant":
        from mechanics.combat.items import generate_procedural_potion
        # Add a mix of Tier 3, Tier 2, and potential Tier 1 potion
        p_t3 = generate_procedural_potion(tier=3, genre=scen_key)
        p_t2 = generate_procedural_potion(tier=2, genre=scen_key)
        stock.insert(0, p_t3)
        stock.insert(1, p_t2)
        if random.random() < 0.35:
            p_t1 = generate_procedural_potion(tier=1, genre=scen_key)
            stock.insert(2, p_t1)

    # Integrate Procedural Foods & Drinks
    if merchant_type in ("food_merchant", "cafe_merchant", "tavern_merchant"):
        from mechanics.combat.items import generate_procedural_food, generate_procedural_drink
        if merchant_type == "cafe_merchant":
            # Cafes specialize in artisanal drinks and light desserts
            d_t3 = generate_procedural_drink(tier=3, genre=scen_key)
            d_t2 = generate_procedural_drink(tier=2, genre=scen_key)
            f_pastry = generate_procedural_food(tier=3, taste_tags=["sweet", "bakery"], genre=scen_key)
            stock.insert(0, d_t3)
            stock.insert(1, d_t2)
            stock.insert(2, f_pastry)
            if random.random() < 0.40:
                d_t1 = generate_procedural_drink(tier=1, genre=scen_key)
                stock.insert(3, d_t1)
        elif merchant_type == "tavern_merchant":
            # Taverns stock both hearty tavern meals and ales/ciders
            f_meal = generate_procedural_food(tier=3, taste_tags=["savory", "comfort"], genre=scen_key)
            d_ale = generate_procedural_drink(tier=3, taste_tags=["alcohol"], genre=scen_key)
            stock.insert(0, f_meal)
            stock.insert(1, d_ale)
            if random.random() < 0.40:
                d_aged = generate_procedural_drink(tier=2, taste_tags=["alcohol"], genre=scen_key)
                stock.insert(2, d_aged)
        else:
            # Food merchants stock hearty solid meals
            f_t3 = generate_procedural_food(tier=3, genre=scen_key)
            f_t2 = generate_procedural_food(tier=2, genre=scen_key)
            stock.insert(0, f_t3)
            stock.insert(1, f_t2)
            if random.random() < 0.35:
                f_t1 = generate_procedural_food(tier=1, genre=scen_key)
                stock.insert(2, f_t1)

    # Integrate Learnable Spellbooks if spellbook merchant or general magic store (Disabled in Anomalous Incursions)
    if (
        scenario_data.is_combat_enabled(scen_key)
        and not scenario_data.is_anomalous_incursions_scenario(scen_key)
        and (merchant_type in ("spellbook_merchant", "magic_merchant", "general_merchant"))
    ):
        from mechanics.combat.spells import get_all_spells
        all_spells = get_all_spells()
        available_keys = list(all_spells.keys())
        random.shuffle(available_keys)
        count = 4 if merchant_type == "spellbook_merchant" else 2
        chosen_spell_keys = available_keys[:count]

        for s_key in chosen_spell_keys:
            sp = all_spells[s_key]
            tier = sp.get("tier", 3)
            tier_prefix = "Grimoire" if tier == 1 else ("Tome" if tier == 2 else "Spellbook")
            sp_price = 80 if tier == 3 else (300 if tier == 2 else 1200)
            spell_meta = {
                "item_type": "Spellbook",
                "spell_id": sp.get("id", s_key),
                "spell_name": sp["name"],
                "discipline": sp.get("discipline", "attack"),
                "school": sp.get("school", "Evocation"),
                "tier": tier,
                "damage_type": sp.get("damage_type", "magical"),
                "is_spellbook": True,
                "tags": sp.get("tags", [sp.get("school", "Evocation"), f"Tier {tier}"]),
            }
            stock.append({
                "name": f"{tier_prefix}: {sp['name']}",
                "item_type": "Spellbook",
                "description": f"Teaches {sp['name']} ({sp.get('tier_name', 'Basic')} {sp.get('discipline', 'attack').title()} Magic). Consumed on read.",
                "price": sp_price,
                "quantity": 1,
                "tier": tier,
                "metadata": spell_meta,
                "effect": f"[SPELLBOOK_JSON]{json.dumps(spell_meta)}"
            })

    from mechanics.combat.equipment import enrich_equipment_item
    from mechanics.combat.items.anomalous_gear import apply_anomalous_incursions_gear_rules
    EQUIP_TYPES = {"weapon", "armor", "shield", "head", "top", "bottom", "gloves", "shoes", "accessory", "clothing", "headwear", "lingerie", "outerwear"}
    for item in stock:
        itype = str(item.get("item_type", "")).lower()
        if not item.get("effect"):
            if itype in EQUIP_TYPES or any(k in item.get("name", "").lower() for k in ["sword", "axe", "bow", "dagger", "shield", "armor", "helm", "glove", "boot", "ring", "amulet", "robe", "tunic", "pistol", "rifle", "shotgun", "katana", "baton"]):
                enrich_equipment_item(item, scenario=scen_key)
                if scenario_data.is_anomalous_incursions_scenario(scen_key):
                    apply_anomalous_incursions_gear_rules(
                        item,
                        scenario=scen_key,
                        slot=item.get("slot", "Weapon"),
                        tier=item.get("tier", 3),
                        private_agency_bonus=priv_bonus,
                    )

    # Folklore Wards & Offerings stock for Anomalous Incursions shops (Shrines, Quartermasters, Urban Markets)
    if scenario_data.is_anomalous_incursions_scenario(scen_key):
        from mechanics.world.folklore_mechanics import build_folklore_shop_stock_items

        shop_arch = str(shop_ctx.get("shop_faction_archetype") or "")
        loc_low = str((session or {}).get("current_location") or "").lower()
        m_name_low = str(merchant_name or "").lower()
        if shop_arch == "monastic_order" or any(k in loc_low or k in m_name_low for k in ("shrine", "torii", "temple", "talisman")):
            folklore_pool = "shrine"
        elif shop_arch in ("public_agency", "private_agency_1", "private_agency_2") or merchant_type in ("quartermaster", "armory_merchant", "weapon_merchant"):
            folklore_pool = "quartermaster"
        elif merchant_type in (
            "convenience_merchant",
            "food_merchant",
            "night_market_merchant",
            "general_merchant",
            "potion_merchant",
            "gift_merchant",
            "alchemist",
        ) or is_phone_shop:
            folklore_pool = "urban_market"
        else:
            folklore_pool = None

        if folklore_pool:
            f_items = build_folklore_shop_stock_items(folklore_pool)
            existing_stock_names = {str(s.get("name", "")).lower() for s in stock if isinstance(s, dict)}
            formatted_f_items = []
            for f_spec in f_items:
                if f_spec["name"].lower() in existing_stock_names:
                    continue
                formatted_f_items.append({
                    "name": f_spec["name"],
                    "type": "Consumable",
                    "item_type": "Consumable",
                    "description": f_spec["desc"],
                    "desc": f_spec["desc"],
                    "price": int(f_spec["price"]),
                    "quantity": 3,
                    "tier": 3,
                    "effect": f_spec["effect"],
                    "appeasement_tags": list(f_spec.get("appeasement_tags") or []),
                })
            if (
                shop_ctx.get("shop_faction_archetype") == "monastic_order"
                and shop_ctx.get("player_faction_archetype") == "monastic_order"
                and formatted_f_items
            ):
                # Rotate 1 consecrated folklore ward into the 3-item daily monastic ration
                day_idx = int((session or {}).get("current_day") or (session or {}).get("in_game_day") or 1) % len(formatted_f_items)
                stock = stock[:2] + [formatted_f_items[day_idx]]
            else:
                stock.extend(formatted_f_items)

    # Monastic Shrine Order member daily stock cap (2-3 items/day, quantity 1 each)
    if (
        shop_ctx.get("shop_faction_archetype") == "monastic_order"
        and shop_ctx.get("player_faction_archetype") == "monastic_order"
    ):
        stock = stock[:3]
        for s_it in stock:
            s_it["quantity"] = 1

    # Public Agency Bureau Vault Requisition: unlock secured Object Anomalies at the HQ Tactical Armory
    # Gated strictly to formal enlisted operatives of public_agency (freelancers & student operatives do not have vault clearance)
    if (
        shop_ctx.get("shop_faction_archetype") == "public_agency"
        and shop_ctx.get("player_faction_archetype") == "public_agency"
        and isinstance(session, dict)
    ):
        req_items = list(session.get("anomalous_vault_requisitions") or [])
        if not req_items and session.get("id"):
            try:
                sess_db = db.get_session(int(session["id"])) or {}
                req_items = list(sess_db.get("anomalous_vault_requisitions") or [])
            except Exception:
                req_items = []
        existing_names = {str(s.get("name", "")).lower() for s in stock if isinstance(s, dict)}
        for req_it in req_items:
            if not isinstance(req_it, dict) or req_it.get("requisitioned"):
                continue
            if req_it.get("name") and str(req_it["name"]).lower() not in existing_names:
                req_copy = dict(req_it)
                base_p = int(req_copy.get("price") or calculate_balanced_price(
                    req_copy.get("item_type", "Weapon"),
                    req_copy["name"],
                    tier=int(req_copy.get("tier", 2) or 2),
                    scen_key=scen_key,
                    metadata=req_copy.get("metadata"),
                ))
                req_copy["price"] = base_p
                req_copy["requisition_price"] = max(1, int(round(base_p * 0.50)))
                req_copy["quantity"] = 1
                req_copy["is_vault_requisition"] = True
                stock.insert(0, req_copy)
                existing_names.add(str(req_copy["name"]).lower())

    llm_rumors = [str(r)[:300] for r in (result.get("rumors") or []) if str(r).strip()]
    if is_phone_shop or merchant_type == "online_merchant":
        rumor_entries = []
    else:
        rumor_entries = generate_grounded_merchant_rumors(
            session.get("id") if isinstance(session, dict) else None,
            scen_key=scen_key,
            fallback_rumors=llm_rumors,
        )

    default_intro = f"{merchant_name or arch_title} welcomes you into the shop."
    intro_text = str(result.get("intro_narrative", "")) or default_intro

    if active_hs_clerk:
        mult = float(active_hs_clerk.get("price_multiplier") or 1.0)
        if mult < 1.0:
            for s_it in stock:
                s_it["price"] = max(1, round(int(s_it.get("price") or 1) * mult))
        if active_hs_clerk.get("pricing_badge"):
            hookup_note = (
                f"{merchant_name} spots you from behind the counter with a warm grin and quietly rings you up with a friend hookup."
            )
            if merchant_name.lower() not in intro_text.lower():
                intro_text = f"{hookup_note} {intro_text}".strip()
            else:
                intro_text = f"{intro_text.rstrip()} {hookup_note}".strip()

    out_shop = {
        "intro_narrative": intro_text,
        "stock": stock,
        "rumors": rumor_entries,
        "merchant_type": merchant_type,
    }
    if active_hs_clerk:
        out_shop["merchant_name"] = merchant_name
        out_shop["is_student_part_timer"] = bool(active_hs_clerk.get("is_student_part_timer"))
        if active_hs_clerk.get("pricing_badge"):
            out_shop["pricing_badge"] = active_hs_clerk["pricing_badge"]
    return out_shop



def reveal_hidden_node_from_rumor(session_id: int, node_id: str) -> bool:
    """Marks a hidden spatial node as discovered in world_nodes.state_json when revealed by a grounded rumor (D19)."""
    if not session_id or not node_id:
        return False
    try:
        with db.get_conn() as conn:
            row = conn.execute(
                "SELECT state_json FROM world_nodes WHERE session_id = ? AND node_id = ?",
                (session_id, node_id),
            ).fetchone()
            if not row:
                return False
            try:
                st = json.loads(row["state_json"] or "{}") if row["state_json"] else {}
            except Exception:
                st = {}
            if not isinstance(st, dict):
                st = {}
            st["is_hidden"] = False
            st["discovered"] = True
            conn.execute(
                "UPDATE world_nodes SET state_json = ? WHERE session_id = ? AND node_id = ?",
                (json.dumps(st), session_id, node_id),
            )
            return True
    except Exception:
        return False


def generate_grounded_merchant_rumors(
    session_id: int | None,
    scen_key: str = "fantasy",
    fallback_rumors: list | None = None,
) -> list[dict]:
    """
    Deterministically generates up to 3 merchant rumors grounded in active/available quests
    or hidden world_nodes (D19). Ambient fallback rumors carry no linked_quest_id/linked_node_id
    so they never pollute session_clues.
    """
    rumor_entries: list[dict] = []
    seen_texts: set[str] = set()

    if session_id:
        try:
            quests = (db.get_session_quests(session_id, status="Active") or []) + (
                db.get_session_quests(session_id, status="Available") or []
            )
            for q in quests:
                if len(rumor_entries) >= 2:
                    break
                qid = str(q.get("quest_id") or "").strip()
                if not qid:
                    continue
                q_title = str(q.get("title") or "an ongoing matter").strip()
                wp = db.get_active_waypoint(session_id, qid, None)
                if not wp and isinstance(q.get("sub_objectives"), list):
                    for so in q["sub_objectives"]:
                        if isinstance(so, dict) and not so.get("completed") and so.get("id") is not None:
                            wp = db.get_active_waypoint(session_id, qid, so["id"])
                            if wp:
                                break
                t_loc = str((wp or {}).get("target_location") or "").strip()
                t_npc = str((wp or {}).get("target_npc") or q.get("target_npc") or "").strip()
                if t_npc and t_loc:
                    r_txt = f"Word around here is {t_npc} was recently spotted near {t_loc} regarding {q_title}."
                elif t_loc:
                    r_txt = f"Locals keep whispering about unusual activity around {t_loc} tied to {q_title}."
                elif t_npc:
                    r_txt = f"People have been asking quiet questions about {t_npc} and {q_title}."
                else:
                    obj_txt = str(q.get("objective") or q_title).strip().rstrip(".")
                    r_txt = f"Have you heard about {q_title}? Folks say someone needs to {obj_txt[:120].lower()}."
                if r_txt.lower() not in seen_texts:
                    seen_texts.add(r_txt.lower())
                    rumor_entries.append({
                        "text": r_txt[:300],
                        "revealed": False,
                        "linked_quest_id": qid,
                        "linked_npc": t_npc,
                        "linked_location": t_loc,
                    })
        except Exception:
            pass

        if len(rumor_entries) < 3:
            try:
                from mechanics.world.locations.pathfinding import is_node_hidden
                nodes = db.get_session_world_nodes(session_id) or []
                node_by_id = {n.get("node_id"): n for n in nodes if isinstance(n, dict)}
                for n in nodes:
                    if len(rumor_entries) >= 3:
                        break
                    if not isinstance(n, dict) or not is_node_hidden(n):
                        continue
                    nid = str(n.get("node_id") or "").strip()
                    nname = str(n.get("name") or "").strip()
                    if not nid or not nname:
                        continue
                    parent_obj = node_by_id.get(n.get("parent_id")) or {}
                    p_name = str(parent_obj.get("name") or "nearby").strip()
                    r_txt = f"Not many outsiders know this, but there's a hidden passage to {nname} tucked away near {p_name}."
                    if r_txt.lower() not in seen_texts:
                        seen_texts.add(r_txt.lower())
                        rumor_entries.append({
                            "text": r_txt[:300],
                            "revealed": False,
                            "linked_node_id": nid,
                            "linked_location": nname,
                        })
            except Exception:
                pass

    for raw_r in (fallback_rumors or []):
        if len(rumor_entries) >= 3:
            break
        txt = str(raw_r.get("text") if isinstance(raw_r, dict) else raw_r or "").strip()[:300]
        if txt and txt.lower() not in seen_texts:
            seen_texts.add(txt.lower())
            rumor_entries.append({"text": txt, "revealed": False})

    while len(rumor_entries) < 3:
        amb = "Business has been steady lately, though everyone's keeping a close eye on local affairs."
        if len(rumor_entries) == 1:
            amb = "Regulars say supplies have been tighter than usual this week."
        elif len(rumor_entries) == 2:
            amb = "The merchant has nothing more to share on that front."
        rumor_entries.append({"text": amb, "revealed": False})

    return rumor_entries[:3]


SELL_EVALUATION_SCHEMA = """{
  "prices": [{"name": "string, exact item name from the list given", "price": integer}]
}"""

SELL_EVALUATION_SYSTEM_PROMPT = """Evaluate items a player wants to sell. Gear has zero stats.
Price items based on name/description flavor. Keep buy prices modest (merchants buy low).
Respond with ONLY a single valid JSON object matching the schema exactly, no prose or code fences."""


async def evaluate_items_for_sale(items: list) -> dict:
    """Price items for player selling."""
    if not items:
        return {}
    _is_llm_mocked = hasattr(call_llm_json, "_mock_name")
    if not _is_llm_mocked:
        from mechanics.combat.items import parse_item_tier
        prices = {}
        for i in items:
            t = parse_item_tier(i)
            p = calculate_balanced_price(i.get("item_type", "Item"), i.get("name", ""), tier=t, metadata=i.get("metadata"))
            sell_p = compute_anomalous_resale_price(i, max(1, p // 3))
            prices[str(i["name"])] = sell_p
        return prices

    lines = "\n".join(f"- {i['name']} ({i['item_type']}): {i['effect'] or ''}" for i in items)
    user_prompt = (
        f"Items for sale:\n{lines}\n\n"
        f"Respond with JSON matching exactly this schema:\n{SELL_EVALUATION_SCHEMA}"
    )
    result = await call_llm_json(SELL_EVALUATION_SYSTEM_PROMPT, user_prompt, temperature=0.5, use_utility=True)
    by_name = {str(i.get("name")): i for i in items if isinstance(i, dict) and i.get("name")}
    prices = {}
    for entry in result.get("prices", []) or []:
        if not isinstance(entry, dict) or not entry.get("name"):
            continue
        try:
            price = max(1, int(entry.get("price", 3)))
        except (TypeError, ValueError):
            price = 3
        orig_it = by_name.get(str(entry["name"]))
        if orig_it:
            price = compute_anomalous_resale_price(orig_it, price)
        prices[str(entry["name"])] = price
    return prices


def apply_merchant_encounter_result(session_id: int, encounter: dict | list | None) -> dict:
    session = db.get_session(session_id)
    merchant = (session.get("merchant") if session else None) or {"available": False, "flavor_name": "", "tier": 1, "inventory": []}
    if isinstance(encounter, list):
        encounter = encounter[0] if encounter and isinstance(encounter[0], dict) else {}
    elif not isinstance(encounter, dict):
        encounter = {}

    present = bool(encounter.get("present"))
    scen_key = session.get("scenario", "") if session else ""
    from mechanics.world.locations import is_school_scenario
    if is_school_scenario(scen_key):
        present = False  # In high school settings, never spawn random wandering roadside merchants
    elif present and not scenario_data.is_mechanic_enabled(scen_key, "merchant_encounters"):
        present = False

    merchant["available"] = present
    merchant["flavor_name"] = encounter.get("name", "") if present else ""
    merchant["flavor_description"] = encounter.get("description", "") if present else ""
    db.save_merchant_state(session_id, merchant)
    return merchant


def discounted_price(base_price: int, discount_pct: int) -> int:
    return max(1, round(base_price * (1 - discount_pct / 100)))


def compute_effective_shop_item_price(
    item: Dict[str, Any],
    shop_ctx: Optional[Dict[str, Any]] = None,
    discount_pct: int = 0,
) -> int:
    """Single source of truth for effective shop item purchase price across Web API and Discord."""
    ctx = shop_ctx or {}
    base_price = int(item.get("price", 15) or 15) if isinstance(item, dict) else 15
    if ctx.get("is_monastic_free_shop"):
        return 0
    if isinstance(item, dict) and item.get("is_vault_requisition"):
        req_p = item.get("requisition_price")
        if req_p is not None:
            return max(1, int(req_p))
        return max(1, int(round(base_price * 0.50)))
    if ctx.get("is_public_discounted_shop"):
        return max(1, int(round(base_price * 0.50)))
    mult = float(ctx.get("price_multiplier", 1.0) or 1.0)
    if mult != 1.0:
        marked_up = int(round(base_price * mult))
        return discounted_price(marked_up, int(discount_pct or 0))
    return discounted_price(base_price, int(discount_pct or 0))


def sell_bonus_price(base_price: int, discount_pct: int) -> int:
    return max(1, round(base_price * (1 + discount_pct / 100)))


def get_total_buy_discount(haggle_discount_pct: int, faction_discount_pct: int) -> int:
    """Return cumulative buy discount (capped at 40%) from haggling + faction standing."""
    return min(40, haggle_discount_pct + faction_discount_pct)


def get_store_key(merchant: dict, is_phone_shop: bool = False, merchant_type: str = "general_merchant", location: str = "") -> str:
    """Return a unique, stable key for a store instance."""
    if is_phone_shop or merchant_type == "online_merchant":
        return "phone_shop"
    if merchant.get("is_faction_quartermaster") or merchant_type == "faction_quartermaster":
        return f"faction_{location or 'hq'}"
    name = merchant.get("flavor_name") or merchant_type
    return f"{location or 'local'}:{merchant_type}:{name}"


def should_restock_merchant(catalogue: dict | None, current_day: int, current_minute: int) -> bool:
    """Determine if a merchant's inventory should be restocked/regenerated.
    Restocks at the start of a new in-game day (current_day > restock_day)
    or when 24 in-game hours (1440 minutes) have passed since the last restock.
    """
    if not catalogue or "stock" not in catalogue or not catalogue.get("stock"):
        return True

    last_day = int(catalogue.get("restock_day", 0))
    last_min = int(catalogue.get("restock_minute", 0))

    if last_day <= 0:
        return True

    # 1. New in-game day has started
    if current_day > last_day:
        return True

    # 2. 24 in-game hours (1440 minutes) elapsed
    curr_total = (current_day - 1) * 1440 + current_minute
    last_total = (last_day - 1) * 1440 + last_min
    if (curr_total - last_total) >= 1440:
        return True

    # 3. Guard against clock rollbacks
    if current_day < last_day:
        return True

    return False


def get_or_create_merchant_catalogue(
    merchant: dict,
    store_key: str,
    current_day: int,
    current_minute: int
) -> tuple[dict | None, bool]:
    """Retrieve existing catalogue if still valid, or return (None, True) if it needs restocking."""
    catalogues = merchant.setdefault("catalogues", {})
    if not isinstance(catalogues, dict):
        catalogues = {}
        merchant["catalogues"] = catalogues

    existing = catalogues.get(store_key)
    if existing and not should_restock_merchant(existing, current_day, current_minute):
        return existing, False
    return None, True


def update_merchant_catalogue(
    merchant: dict,
    store_key: str,
    shop_data: dict,
    current_day: int,
    current_minute: int
) -> dict:
    """Store fresh shop stock and reset daily haggle/discount counters."""
    catalogues = merchant.setdefault("catalogues", {})
    if not isinstance(catalogues, dict):
        catalogues = {}
        merchant["catalogues"] = catalogues

    cat_entry = {
        "store_key": store_key,
        "restock_day": current_day,
        "restock_minute": current_minute,
        "intro_narrative": shop_data.get("intro_narrative", ""),
        "stock": shop_data.get("stock", []),
        "rumors": shop_data.get("rumors", []),
        "haggle_attempts": 0,
        "discount_pct": shop_data.get("faction_discount_pct", shop_data.get("discount_pct", 0)),
    }
    catalogues[store_key] = cat_entry
    return cat_entry


# ---------------------------------------------------------------- Faction Quartermaster

FACTION_QUARTERMASTER_SCHEMA = """{
  "intro_narrative": "string, 1-2 sentences from the quartermaster greeting a member",
  "stock": [
    {"name": "string", "item_type": "Weapon|Shield|Top|Bottom|Gloves|Shoes|Consumable|Item",
     "description": "short faction-themed flavor, no stats", "price": integer, "quantity": integer 1-5}
  ]
}"""

FACTION_QUARTERMASTER_SYSTEM_PROMPT = """Generate a faction quartermaster's exclusive stock.
Items MUST be strongly themed around the faction's identity and purpose.
Prices: Modest (a few gold to a few dozen gold). Stock: 4-6 items, quantity 1-5 each.
Respond with ONLY a single valid JSON object matching the schema exactly, no prose or code fences."""


async def generate_faction_quartermaster_shop(faction: dict, session: dict) -> dict:
    """
    Generate a faction-exclusive quartermaster shop with themed stock.
    The session's faction discount is applied automatically at purchase time.
    """
    scen_key = session.get("scenario", "fantasy")
    scen_info = scenario_data.get_scenario(scen_key)
    faction_name = faction.get("name", "Faction")
    category = faction.get("category", "guild")
    rep_score = faction.get("reputation_score", 0)
    from mechanics.social.factions import get_faction_discount, infer_anomalous_faction_archetype
    auto_discount = get_faction_discount(rep_score)
    fac_arch = infer_anomalous_faction_archetype(faction) if scenario_data.is_anomalous_incursions_scenario(scen_key) else ""
    theme_hint = ""
    if fac_arch == "private_agency_1":
        theme_hint = "Theme: Massive corporate conglomerate — sleek, serialized, proprietary weapons and armor developed in-house by corporate R&D.\n"
    elif fac_arch == "private_agency_2":
        theme_hint = "Theme: Humble small-business private agency — eclectic off-the-shelf, surplus, pawn-shop, and multi-vendor gear sourced from whatever supplier they could find.\n"

    user_prompt = (
        f"{scenario_data.scenario_prompt_block(scen_info)}\n"
        f"Faction: {faction_name} (Category: {category})\n"
        f"{theme_hint}"
        f"Player Reputation: {rep_score:+d} (Discount: {auto_discount}%)\n"
        f"Generate exclusive member-only quartermaster stock for {faction_name}.\n"
        f"Respond with JSON matching exactly this schema:\n{FACTION_QUARTERMASTER_SCHEMA}"
    )
    _is_llm_mocked = hasattr(call_llm_json, "_mock_name")
    if _is_llm_mocked:
        result = await call_llm_json(FACTION_QUARTERMASTER_SYSTEM_PROMPT, user_prompt,
                                      temperature=0.7, is_nsfw=scenario_data.uses_nsfw_model(scen_key),
                                      use_utility=True)
        result = namegen.resolve_tokens_deep(result, scenario=scen_key)
    else:
        from mechanics.combat.items import generate_random_equipment as _gen_eq
        q_stock = []
        from mechanics.social.factions import is_school_club_faction as _is_hs_club_qm_gen
        _priv_gen_qm = fac_arch in ("private_agency_1", "private_agency_2") or (
            scenario_data.is_anomalous_high_school_scenario(scen_key) and _is_hs_club_qm_gen(faction)
        )
        for slot in ["Weapon", "Armor", "Accessory 1"]:
            eq = _gen_eq(scenario=scen_key, slot=slot, tier=2, private_agency_bonus=_priv_gen_qm)
            if eq:
                eq["price"] = calculate_balanced_price(eq.get("item_type", "Item"), eq.get("name", ""), tier=eq.get("tier", 2), scen_key=scen_key, metadata=eq.get("metadata"))
                eq["quantity"] = 1
                q_stock.append(eq)
        if fac_arch == "private_agency_1":
            intro_str = f"The {faction_name} R&D ordnance officer scans your biometric badge and unlocks a backlit case of proprietary in-house gear."
        elif fac_arch == "private_agency_2":
            intro_str = f"The {faction_name} supply clerk unhooks a padlock on the chain-link cage and slides over crates of assorted surplus and brokered gear."
        else:
            intro_str = f"The {faction_name} quartermaster nods at you."
        result = {
            "intro_narrative": intro_str,
            "stock": q_stock,
        }
    from mechanics.combat.equipment import enrich_equipment_item
    from mechanics.combat.items.anomalous_gear import apply_anomalous_incursions_gear_rules
    from mechanics.social.factions import is_school_club_faction as _is_hs_club_qm
    priv_bonus_qm = fac_arch in ("private_agency_1", "private_agency_2") or (
        scenario_data.is_anomalous_high_school_scenario(scen_key) and _is_hs_club_qm(faction)
    )

    stock = []
    for entry in result.get("stock", []) or []:
        if not isinstance(entry, dict) or not entry.get("name"):
            continue
        it_name = str(entry["name"])[:60]
        it_type = str(entry.get("item_type", "Item"))[:30]
        if scenario_data.is_anomalous_incursions_scenario(scen_key) and (
            it_type.lower() == "spellbook"
            or any(it_name.lower().startswith(p) for p in ("spellbook:", "grimoire:", "tome:", "scroll:"))
        ):
            continue
        try:
            price = max(1, int(entry.get("price", 5)))
        except (TypeError, ValueError):
            price = 5
        try:
            quantity = max(1, min(9, int(entry.get("quantity", 1))))
        except (TypeError, ValueError):
            quantity = 1
        qm_item = {
            "name": it_name,
            "item_type": it_type,
            "description": str(entry.get("description", ""))[:200],
            "price": price,
            "quantity": 1 if fac_arch == "monastic_order" else quantity,
        }
        for keep_k in ("effect", "metadata", "slot", "slot_cost", "tier"):
            if entry.get(keep_k) is not None:
                qm_item[keep_k] = entry[keep_k]
        if not qm_item.get("effect") and it_type.lower() in {"weapon", "armor", "shield", "head", "top", "bottom", "gloves", "shoes", "accessory"}:
            enrich_equipment_item(qm_item, scenario=scen_key)
            if scenario_data.is_anomalous_incursions_scenario(scen_key):
                apply_anomalous_incursions_gear_rules(
                    qm_item,
                    scenario=scen_key,
                    slot=qm_item.get("slot", "Weapon"),
                    tier=qm_item.get("tier", 2),
                    private_agency_bonus=priv_bonus_qm,
                )
        stock.append(qm_item)
    if scenario_data.is_anomalous_incursions_scenario(scen_key):
        from mechanics.world.folklore_mechanics import build_folklore_shop_stock_items
        qm_pool = "shrine" if fac_arch == "monastic_order" else "quartermaster"
        f_qm_items = build_folklore_shop_stock_items(qm_pool)
        existing_qm_f = {str(s.get("name", "")).lower() for s in stock if isinstance(s, dict)}
        formatted_qm_f = []
        for f_spec in f_qm_items:
            if f_spec["name"].lower() in existing_qm_f:
                continue
            formatted_qm_f.append({
                "name": f_spec["name"],
                "type": "Consumable",
                "item_type": "Consumable",
                "description": f_spec["desc"],
                "desc": f_spec["desc"],
                "price": int(f_spec["price"]),
                "quantity": 1 if fac_arch == "monastic_order" else 3,
                "tier": 3,
                "effect": f_spec["effect"],
                "appeasement_tags": list(f_spec.get("appeasement_tags") or []),
            })
        if fac_arch == "monastic_order" and formatted_qm_f:
            day_idx_qm = int((session or {}).get("current_day") or (session or {}).get("in_game_day") or 1) % len(formatted_qm_f)
            stock = stock[:2] + [formatted_qm_f[day_idx_qm]]
        else:
            stock.extend(formatted_qm_f)
    if fac_arch == "monastic_order" and len(stock) > 3:
        stock = stock[:3]
    from mechanics.social.factions import get_anomalous_faction_state
    a_st = get_anomalous_faction_state(int(session.get("id", 0)), int(session.get("user_id", 0))) if session.get("id") else {}
    player_arch = str(a_st.get("faction_archetype_key") or session.get("joined_faction") or "freelancer")
    if fac_arch == "public_agency" and player_arch == "public_agency" and isinstance(session, dict):
        req_items = list(session.get("anomalous_vault_requisitions") or [])
        if not req_items and session.get("id"):
            try:
                sess_db = db.get_session(int(session["id"])) or {}
                req_items = list(sess_db.get("anomalous_vault_requisitions") or [])
            except Exception:
                req_items = []
        existing_qm_names = {str(s.get("name", "")).lower() for s in stock if isinstance(s, dict)}
        for req_it in req_items:
            if not isinstance(req_it, dict) or req_it.get("requisitioned"):
                continue
            if req_it.get("name") and str(req_it["name"]).lower() not in existing_qm_names:
                req_copy = dict(req_it)
                base_p = int(req_copy.get("price") or calculate_balanced_price(
                    req_copy.get("item_type", "Weapon"),
                    req_copy["name"],
                    tier=int(req_copy.get("tier", 2) or 2),
                    scen_key=scen_key,
                    metadata=req_copy.get("metadata"),
                ))
                req_copy["price"] = base_p
                req_copy["requisition_price"] = max(1, int(round(base_p * 0.50)))
                req_copy["quantity"] = 1
                req_copy["is_vault_requisition"] = True
                stock.insert(0, req_copy)
                existing_qm_names.add(str(req_copy["name"]).lower())
    return {
        "intro_narrative": str(result.get("intro_narrative", f"The {faction_name} quartermaster nods at you."))[:300],
        "stock": stock,
        "faction_id": faction.get("faction_id", ""),
        "faction_discount_pct": auto_discount,
        "is_faction_quartermaster": True,
    }


# -----------------------------------------------------------------------------
# FACADE & BACKWARD COMPATIBILITY
# Dynamically re-export UI views extracted to cogs.adventure.views.merchant
# -----------------------------------------------------------------------------
def __getattr__(name: str):
    if name in (
        "BazaarStoreSelectDropdown",
        "BazaarStoreSelectView",
        "MerchantVoteView",
        "BuySelectView",
        "SellSelectView",
        "RumorView",
        "MerchantView",
        "build_merchant_embed",
        "handle_talk_to_merchant",
    ):
        import cogs.adventure.views.merchant as _merchant_views
        val = getattr(_merchant_views, name)
        globals()[name] = val
        return val
    raise AttributeError(f"module '{__name__}' has no attribute '{name}'")
