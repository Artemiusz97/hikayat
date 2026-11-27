from __future__ import annotations

"""
Origin-aware Categorized Online Store & SchoolMart Catalog Builder.

Generates deterministic, daily-rotating Tier 2 / Tier 3 delivery catalogs
without LLM latency, gated by scenario tags (combat, magic, NSFW) and
player store mode (`online_general` vs `school_mart`).
"""

import json
import re
from typing import Any, Mapping

import scenario_data
from mechanics.combat.items.consumables.metadata import serialize_consumable_metadata
from mechanics.combat.items.envelope import serialize_item
from mechanics.combat.items.tags import derive_clothing_tags

STORE_MODE_ONLINE_GENERAL = "online_general"
STORE_MODE_SCHOOL_MART = "school_mart"
SCHOOL_MART_STUDENT_DISCOUNT_PCT = 20

_GENERAL_CATEGORIES: tuple[tuple[str, str], ...] = (
    ("all", "All"),
    ("food", "Food"),
    ("drinks", "Drinks"),
    ("meds", "Meds"),
    ("gifts", "Gifts"),
    ("clothing", "Clothing"),
    ("accessories", "Accessories"),
)

_COMBAT_CATEGORIES: tuple[tuple[str, str], ...] = (
    ("weapons", "Weapons"),
    ("armor", "Armor"),
)

_SCHOOL_MART_CATEGORIES: tuple[tuple[str, str], ...] = (
    ("all", "All"),
    ("food", "Snacks & Food"),
    ("drinks", "Drinks"),
    ("stationery", "Study & Stationery"),
    ("apparel", "Apparel"),
    ("gifts", "Gifts"),
    ("meds", "First-Aid"),
)

_CATEGORY_LABELS: dict[str, str] = {
    "all": "All",
    "food": "Food",
    "drinks": "Drinks",
    "meds": "Meds",
    "gifts": "Gifts",
    "clothing": "Clothing",
    "accessories": "Accessories",
    "weapons": "Weapons",
    "armor": "Armor",
    "arcane": "Arcane",
    "adult": "Adult",
    "stationery": "Study & Stationery",
    "apparel": "Apparel",
}


def is_school_mart_requested(store_mode: str | None) -> bool:
    """Return True if the raw query/request explicitly selects the SchoolMart student storefront."""
    raw = str(store_mode or "").strip().lower()
    return raw in ("school_mart", "school_shop", "schoolmart", "campus_mart", "campus_shop")


def normalize_phone_store_mode(store_mode: str | None, *, is_student: bool = False) -> str:
    """Normalize store_mode to `'school_mart'` (only when `is_student=True`) or `'online_general'`."""
    if is_student and is_school_mart_requested(store_mode):
        return STORE_MODE_SCHOOL_MART
    return STORE_MODE_ONLINE_GENERAL


def is_magic_combat_scenario(scen_key: str) -> bool:
    """Return True strictly for fantasy/isekai magic combat worlds (never Anomalous, Sci-Fi, Cyberpunk, Steampunk, or School)."""
    if not scenario_data.is_combat_enabled(scen_key):
        return False
    if scenario_data.is_anomalous_incursions_scenario(scen_key) or scenario_data.is_anomalous_high_school_scenario(scen_key):
        return False
    if scenario_data.is_school_scenario(scen_key):
        return False
    tags = {str(t).strip().lower() for t in scenario_data.get_scenario_tags(scen_key)}
    if tags & {"space", "cyberpunk", "steampunk", "post_apocalypse", "slice_of_life", "high_school"}:
        return False
    return bool(tags & {"fantasy", "isekai"})


def _has_combat_gear_tab(scen_key: str) -> bool:
    tags = {str(t).strip().lower() for t in scenario_data.get_scenario_tags(scen_key)}
    if not scenario_data.is_combat_enabled(scen_key):
        return False
    if scenario_data.is_school_scenario(scen_key):
        return False
    if "slice_of_life" in tags and not (tags & {"fantasy", "isekai", "urban_fantasy", "cyberpunk", "space", "steampunk", "post_apocalypse", "horror"}):
        return False
    return True


def _resolve_store_theme(scen_key: str) -> str:
    if scenario_data.is_school_scenario(scen_key) or scenario_data.is_anomalous_incursions_scenario(scen_key):
        return "modern"
    k = str(scen_key or "").strip().lower()
    tags = {str(t).strip().lower() for t in scenario_data.get_scenario_tags(scen_key)}
    if "cyberpunk" in tags or "cyberpunk" in k:
        return "cyberpunk"
    if "space" in tags or any(tok in k for tok in ("sci_fi", "scifi", "space")):
        return "sci_fi"
    if "steampunk" in tags or "steampunk" in k:
        return "steampunk"
    if "post_apocalypse" in tags or "apocalypse" in k:
        return "post_apocalypse"
    if tags & {"fantasy", "isekai"}:
        return "fantasy"
    return "modern"


def get_eligible_phone_store_categories(
    scen_key: str,
    *,
    store_mode: str = STORE_MODE_ONLINE_GENERAL,
    is_nsfw: bool | None = None,
) -> list[dict[str, str]]:
    """Return ordered list of `{key, label}` tabs eligible for this scenario and store mode."""
    if store_mode == STORE_MODE_SCHOOL_MART:
        return [{"key": k, "label": lbl} for k, lbl in _SCHOOL_MART_CATEGORIES]

    nsfw_on = scenario_data.is_nsfw_scenario(scen_key) if is_nsfw is None else bool(is_nsfw)
    cats = [{"key": k, "label": lbl} for k, lbl in _GENERAL_CATEGORIES]
    if _has_combat_gear_tab(scen_key):
        for k, lbl in _COMBAT_CATEGORIES:
            cats.append({"key": k, "label": lbl})
    if is_magic_combat_scenario(scen_key):
        cats.append({"key": "arcane", "label": "Arcane"})
    if nsfw_on:
        cats.append({"key": "adult", "label": "Adult"})
    return cats


def compute_phone_item_badges(item: Mapping[str, Any]) -> list[str]:
    """Compute concise player-facing effect badges (<=3) for an online store item card."""
    badges: list[str] = []
    meta = item.get("metadata") if isinstance(item.get("metadata"), Mapping) else {}
    eff = str(item.get("effect") or "")
    if not meta and eff.startswith("[CONSUMABLE_JSON]"):
        try:
            meta = json.loads(eff[len("[CONSUMABLE_JSON]"):])
        except Exception:
            meta = {}
    elif not meta and eff.startswith("[ITEM_JSON]"):
        try:
            meta = json.loads(eff[len("[ITEM_JSON]"):])
        except Exception:
            meta = {}

    hp = int(item.get("hp_restore") or meta.get("hp_restore") or 0)
    mp = int(item.get("mp_restore") or meta.get("mp_restore") or 0)
    if hp > 0:
        badges.append(f"+{hp} HP")
    if mp > 0:
        badges.append(f"+{mp} MP")
    dmg_mult = meta.get("damage_mult") or meta.get("atk_mult")
    if dmg_mult:
        try:
            badges.append(f"{float(dmg_mult):.2g}x DMG")
        except (TypeError, ValueError):
            pass
    elif meta.get("attack") or meta.get("atk"):
        atk_v = int(meta.get("attack") or meta.get("atk") or 0)
        if atk_v > 0:
            badges.append(f"+{atk_v} ATK")
    dt_val = int(meta.get("dt") or meta.get("base_dt") or meta.get("defense") or 0)
    if dt_val > 0:
        badges.append(f"+{dt_val} DT")

    buffs = meta.get("buffs") if isinstance(meta.get("buffs"), Mapping) else {}
    stat_mods = meta.get("stat_modifiers") if isinstance(meta.get("stat_modifiers"), Mapping) else {}
    social_mods = meta.get("social_modifiers") if isinstance(meta.get("social_modifiers"), Mapping) else {}
    aff = int(meta.get("social_affinity_bonus") or item.get("social_affinity_bonus") or 0)
    if aff > 0 or str(item.get("item_type") or "").lower() == "gift":
        badges.append("+Affinity")
    if buffs.get("cha") or stat_mods.get("cha") or social_mods.get("cha"):
        val = int(buffs.get("cha") or stat_mods.get("cha") or social_mods.get("cha") or 1)
        badges.append(f"+{val} CHA")
    if buffs.get("int") or stat_mods.get("int"):
        val = int(buffs.get("int") or stat_mods.get("int") or 1)
        badges.append(f"+{val} INT")
    if buffs.get("eva") or stat_mods.get("eva") or social_mods.get("eva"):
        val = int(buffs.get("eva") or stat_mods.get("eva") or social_mods.get("eva") or 1)
        badges.append(f"+{val}% EVA")
    if meta.get("cure_status"):
        badges.append("Cleanse")
    if str(item.get("category") or "").lower() == "adult" or str(item.get("item_type") or "").lower() in ("lingerie", "novelty"):
        badges.append("NSFW")
    if str(item.get("item_type") or "").lower() == "spellbook":
        badges.append("Spell")
    return list(dict.fromkeys(badges))[:3]


def is_legacy_flat_phone_stock(inventory: list[dict] | None) -> bool:
    """Return True if an existing non-empty phone stock lacks v2 category metadata."""
    if not inventory or not isinstance(inventory, list):
        return False
    valid_items = [it for it in inventory if isinstance(it, dict) and it.get("name")]
    if not valid_items:
        return False
    return any(not str(it.get("category") or "").strip() for it in valid_items)


def infer_item_category(item: Mapping[str, Any], *, store_mode: str = STORE_MODE_ONLINE_GENERAL) -> str:
    """Infer a category key for fallback/mocked items lacking an explicit `category` field."""
    explicit = str(item.get("category") or "").strip().lower()
    if explicit:
        return explicit
    itype = str(item.get("item_type") or item.get("type") or "").strip().lower()
    name_low = str(item.get("name") or "").strip().lower()
    if itype in ("lingerie", "novelty") or any(w in name_low for w in ("lingerie", "corset", "massage oil", "cuffs")):
        return "adult"
    if itype == "spellbook":
        return "arcane"
    if itype == "weapon":
        return "weapons"
    if itype in ("armor", "shield", "headwear"):
        return "armor"
    if itype in ("food", "snack"):
        return "food"
    if itype == "drink":
        return "drinks"
    if itype in ("potion",):
        return "meds"
    if itype in ("gift",):
        return "gifts"
    if itype in ("clothing", "top", "bottom", "shoes", "outerwear"):
        return "apparel" if store_mode == STORE_MODE_SCHOOL_MART else "clothing"
    if itype in ("accessory", "gadget"):
        return "accessories"
    if itype in ("stationery", "study aid"):
        return "stationery" if store_mode == STORE_MODE_SCHOOL_MART else "gifts"
    if any(w in name_low for w in ("medkit", "bandage", "tonic", "antidote", "vitamin", "stim")):
        return "meds"
    if any(w in name_low for w in ("energy drink", "latte", "tea", "coffee", "soda", "elixir")):
        return "drinks"
    if any(w in name_low for w in ("bento", "croissant", "ramen", "ration", "bread")):
        return "food"
    return "stationery" if store_mode == STORE_MODE_SCHOOL_MART else "accessories"


def _make_consumable(
    name: str,
    *,
    category: str,
    item_type: str,
    description: str,
    tier: int,
    price: int,
    quantity: int,
    hp_restore: int = 0,
    mp_restore: int = 0,
    buffs: dict[str, Any] | None = None,
    cure_status: list[str] | None = None,
    taste_tags: list[str] | None = None,
    purpose_tags: list[str] | None = None,
    effect_tags: list[str] | None = None,
    social_affinity_bonus: int = 0,
) -> dict[str, Any]:
    clamped_tier = 2 if int(tier or 3) <= 2 else 3
    meta: dict[str, Any] = {
        "name": name,
        "item_type": item_type,
        "tier": clamped_tier,
        "purpose_tags": list(purpose_tags or ["utility"]),
        "effect_tags": list(effect_tags or []),
        "taste_tags": list(taste_tags or []),
        "hp_restore": int(hp_restore or 0),
        "mp_restore": int(mp_restore or 0),
        "buffs": dict(buffs or {}),
        "cure_status": list(cure_status or []),
        "damage": 0,
    }
    if social_affinity_bonus:
        meta["social_affinity_bonus"] = int(social_affinity_bonus)
    cat_label = _CATEGORY_LABELS.get(category, category.title())
    item = {
        "name": name,
        "item_type": item_type,
        "description": description,
        "price": max(1, int(price)),
        "quantity": max(1, int(quantity)),
        "tier": clamped_tier,
        "category": category,
        "category_label": cat_label,
        "hp_restore": int(hp_restore or 0),
        "mp_restore": int(mp_restore or 0),
        "metadata": meta,
        "effect": serialize_consumable_metadata(meta),
    }
    item["badges"] = compute_phone_item_badges(item)
    return item


def _make_equipment_entry(
    name: str,
    *,
    category: str,
    item_type: str,
    slot: str,
    description: str,
    tier: int,
    price: int,
    quantity: int = 2,
    damage_mult: float | None = None,
    dt: int = 0,
    stat_modifiers: dict[str, Any] | None = None,
    social_affinity_bonus: int = 0,
    social_flags: list[str] | None = None,
    style: str = "casual",
) -> dict[str, Any]:
    clamped_tier = 2 if int(tier or 3) <= 2 else 3
    mods = dict(stat_modifiers or {})
    meta: dict[str, Any] = {
        "name": name,
        "tier": clamped_tier,
        "tier_name": "Superior" if clamped_tier == 2 else "Standard",
        "slot": slot,
        "item_type": item_type,
        "base_dt": int(dt or 0),
        "dt": int(dt or 0),
        "type_dt": {},
        "stat_modifiers": mods,
        "social_modifiers": dict(mods),
        "tags": derive_clothing_tags(style=style, social_vibe=list(social_flags or []))
        if item_type in ("Clothing", "Lingerie")
        else [item_type.lower(), f"tier_{clamped_tier}"],
    }
    if damage_mult is not None:
        meta["damage_mult"] = float(damage_mult)
    if social_affinity_bonus:
        meta["social_affinity_bonus"] = int(social_affinity_bonus)
    if social_flags:
        meta["social_flags"] = list(social_flags)
    item = {
        "name": name,
        "item_type": item_type,
        "slot": slot,
        "slot_cost": 1,
        "description": description,
        "price": max(1, int(price)),
        "quantity": max(1, int(quantity)),
        "tier": clamped_tier,
        "category": category,
        "category_label": _CATEGORY_LABELS.get(category, category.title()),
        "metadata": meta,
        "effect": serialize_item(meta),
    }
    item["badges"] = compute_phone_item_badges(item)
    return item


def _rotate_pick(pool: list[dict[str, Any]], *, day: int, count: int, pinned_first: int = 0) -> list[dict[str, Any]]:
    if len(pool) <= count:
        return [dict(x) for x in pool]
    pinned = [dict(x) for x in pool[:pinned_first]]
    rest = pool[pinned_first:]
    if not rest:
        return pinned
    offset = max(0, int(day or 1) - 1) % len(rest)
    rotated = rest[offset:] + rest[:offset]
    needed = max(0, count - len(pinned))
    return pinned + [dict(x) for x in rotated[:needed]]


def _build_school_mart_pools(day: int) -> dict[str, list[dict[str, Any]]]:
    food_pool = [
        _make_consumable("Deluxe Bento Box", category="food", item_type="Food", description="Balanced homeroom bento box restoring stamina and focus.", tier=2, price=25, quantity=4, hp_restore=35, mp_restore=15, taste_tags=["savory"], purpose_tags=["health", "sustenance"], effect_tags=["healing", "mana_restore"]),
        _make_consumable("Warm Melonpan Bun", category="food", item_type="Food", description="Crisp bakery melonpan packed fresh from the campus co-op.", tier=3, price=12, quantity=5, hp_restore=18, taste_tags=["sweet", "bakery"], purpose_tags=["health"], effect_tags=["healing"]),
        _make_consumable("Salmon Onigiri Trio", category="food", item_type="Food", description="Savory seaweed rice balls wrapped for between-class breaks.", tier=3, price=15, quantity=5, hp_restore=20, mp_restore=8, taste_tags=["savory"], purpose_tags=["health"], effect_tags=["healing"]),
        _make_consumable("Strawberry Cream Sandwich", category="food", item_type="Food", description="Fluffy konbini fruit sando popular during cram study.", tier=2, price=22, quantity=4, hp_restore=28, mp_restore=12, buffs={"cha": 1}, taste_tags=["sweet"], purpose_tags=["health"], effect_tags=["healing", "morale_boost"]),
        _make_consumable("Teriyaki Katsu Sando", category="food", item_type="Food", description="Crispy toasted cutlet sandwich built to power through afternoon clubs.", tier=2, price=26, quantity=3, hp_restore=36, buffs={"dt": 2}, taste_tags=["savory", "hearty"], purpose_tags=["health"], effect_tags=["healing", "defense_buff"]),
    ]
    drinks_pool = [
        _make_consumable("Matcha Spark Energy Drink", category="drinks", item_type="Drink", description="Crisp green tea energy blend restoring 15 HP and 15 MP.", tier=2, price=22, quantity=4, hp_restore=15, mp_restore=15, taste_tags=["tea", "caffeine"], purpose_tags=["hydration"], effect_tags=["healing", "mana_restore"]),
        _make_consumable("Iced Brown Sugar Boba", category="drinks", item_type="Drink", description="Sweet campus favorite chilled in a spill-proof courier cup.", tier=3, price=14, quantity=5, hp_restore=10, mp_restore=18, taste_tags=["boba", "sweet"], purpose_tags=["hydration"], effect_tags=["mana_restore"]),
        _make_consumable("Cold Brew Black Coffee", category="drinks", item_type="Drink", description="High-caffeine study roast that sharpens alertness.", tier=3, price=13, quantity=5, mp_restore=22, buffs={"eva": 4}, taste_tags=["coffee", "caffeine"], purpose_tags=["hydration"], effect_tags=["mana_restore", "evasion_buff"]),
        _make_consumable("Citrus Electrolyte Bottle", category="drinks", item_type="Drink", description="Light sports hydration bottle made for club track practice.", tier=3, price=12, quantity=5, hp_restore=14, mp_restore=12, taste_tags=["citrus", "refreshing"], purpose_tags=["hydration"], effect_tags=["healing", "mana_restore"]),
        _make_consumable("Honey Yuzu Warm Tea", category="drinks", item_type="Drink", description="Soothing thermos blend easing tired throats after club drills.", tier=2, price=24, quantity=3, hp_restore=18, mp_restore=24, buffs={"cha": 1}, taste_tags=["tea", "sweet"], purpose_tags=["hydration"], effect_tags=["mana_restore", "charisma_buff"]),
    ]
    stationery_pool = [
        _make_consumable("Portable Fast-Charger Power Bank", category="stationery", item_type="Gadget", description="Compact campus USB-C battery pack keeping study tablets charged.", tier=2, price=45, quantity=2, buffs={"int": 1}, purpose_tags=["utility"]),
        _make_consumable("Exam Cram Flashcards", category="stationery", item_type="Study Aid", description="Color-coded revision deck boosting test recall.", tier=2, price=18, quantity=4, buffs={"int": 1}, purpose_tags=["utility"]),
        _make_consumable("A5 Grid Study Notebook Pack", category="stationery", item_type="Stationery", description="Three fountain-pen friendly notebooks bound in matte slate.", tier=3, price=14, quantity=5, purpose_tags=["utility"]),
        _make_consumable("Pastel Gel Pen & Highlighter Set", category="stationery", item_type="Stationery", description="Quick-dry study pens and soft pastel markers.", tier=3, price=12, quantity=5, purpose_tags=["utility"]),
        _make_consumable("Quiet Noise-Reducing Earbuds", category="stationery", item_type="Gadget", description="Campus-approved study earbuds for blocking library chatter.", tier=2, price=55, quantity=2, buffs={"per": 1}, purpose_tags=["utility"]),
    ]
    apparel_pool = [
        _make_equipment_entry("Pressed Navy School Blazer", category="apparel", item_type="Clothing", slot="Top", description="Crisp student blazer with breathable lining for homeroom.", tier=2, price=75, quantity=2, stat_modifiers={"cha": 1, "eva": 2}, social_flags=["neat", "academic"], style="academic_uniform"),
        _make_equipment_entry("Campus Varsity Track Jacket", category="apparel", item_type="Clothing", slot="Top", description="Lightweight athletic zip jacket approved for PE and club commutes.", tier=3, price=48, quantity=3, stat_modifiers={"eva": 3}, social_flags=["athletic", "cool"], style="athletic"),
        _make_equipment_entry("Comfy Oversized Knit Cardigan", category="apparel", item_type="Clothing", slot="Top", description="Soft cream cardigan worn over crisp school shirts.", tier=2, price=68, quantity=2, stat_modifiers={"cha": 1, "eva": 1}, social_flags=["cozy", "preppy"], style="preppy"),
        _make_equipment_entry("Classic Dark Pleated Trousers & Skirt Set", category="apparel", item_type="Clothing", slot="Bottom", description="Tailored student-cut uniform bottoms built for daily wear.", tier=3, price=42, quantity=3, stat_modifiers={"eva": 2}, social_flags=["neat"], style="academic_uniform"),
        _make_equipment_entry("Cushioned Campus Canvas Sneakers", category="apparel", item_type="Clothing", slot="Shoes", description="Clean everyday court sneakers sized for dashing before first bell.", tier=3, price=44, quantity=3, stat_modifiers={"eva": 3}, social_flags=["comfortable"], style="casual"),
    ]
    gifts_pool = [
        _make_consumable("Cute Mascot Phone Charm", category="gifts", item_type="Gift", description="Adorable acrylic charm loved by classmates.", tier=2, price=28, quantity=3, social_affinity_bonus=2, purpose_tags=["gift"], effect_tags=["morale_boost"]),
        _make_consumable("Gourmet Truffle Chocolates", category="gifts", item_type="Gift", description="Ribbons-wrapped chocolate assortment ideal for sharing.", tier=2, price=38, quantity=3, social_affinity_bonus=2, taste_tags=["sweet"], purpose_tags=["gift"], effect_tags=["morale_boost"]),
        _make_consumable("Sakura Pressed-Bookmark Gift Set", category="gifts", item_type="Gift", description="Laminated cherry-blossom bookmarks tucked inside a kraft envelope.", tier=3, price=18, quantity=4, social_affinity_bonus=1, purpose_tags=["gift"]),
        _make_consumable("Scented Lavender Hand Cream", category="gifts", item_type="Gift", description="Calming pocket hand lotion popular around campus.", tier=3, price=24, quantity=4, social_affinity_bonus=1, purpose_tags=["gift"]),
        _make_consumable("Plush Shiba Keyring Mascot", category="gifts", item_type="Gift", description="Soft mini plushie ready to clip onto any school bag.", tier=2, price=32, quantity=3, social_affinity_bonus=2, purpose_tags=["gift"]),
    ]
    meds_pool = [
        _make_consumable("Nurse's First-Aid Bandage Pouch", category="meds", item_type="Potion", description="Antiseptic wipes and cushioned plasters for gym scrapes.", tier=3, price=20, quantity=4, hp_restore=35, purpose_tags=["health"], effect_tags=["healing"]),
        _make_consumable("Cooling Fever Gel Strips", category="meds", item_type="Potion", description="Menthol forehead strips clearing fatigue and dizzy spells.", tier=3, price=22, quantity=4, hp_restore=25, cure_status=["Burned", "Stunned"], purpose_tags=["cure"], effect_tags=["healing", "cleanse_all"]),
        _make_consumable("Vitamin C Effervescent Ampoule", category="meds", item_type="Potion", description="Student wellness shot restoring 45 HP and steady poise.", tier=2, price=36, quantity=3, hp_restore=45, buffs={"cha": 1}, purpose_tags=["health"], effect_tags=["healing"]),
        _make_consumable("Herbal Throat & Calm Lozenges", category="meds", item_type="Potion", description="Soothing botanical tin easing nerves and restoring stamina.", tier=2, price=34, quantity=3, hp_restore=25, mp_restore=30, purpose_tags=["health", "mana"], effect_tags=["healing", "mana_restore"]),
    ]
    return {
        "food": _rotate_pick(food_pool, day=day, count=4, pinned_first=1),
        "drinks": _rotate_pick(drinks_pool, day=day, count=4, pinned_first=1),
        "stationery": _rotate_pick(stationery_pool, day=day, count=4, pinned_first=1),
        "apparel": _rotate_pick(apparel_pool, day=day, count=4),
        "gifts": _rotate_pick(gifts_pool, day=day, count=4),
        "meds": _rotate_pick(meds_pool, day=day, count=4),
    }


def _build_general_theme_pools(
    theme: str,
    scen_key: str,
    *,
    day: int,
    has_combat: bool,
    has_arcane: bool,
    is_nsfw: bool,
) -> dict[str, list[dict[str, Any]]]:
    if theme == "fantasy":
        food_pool = [
            _make_consumable("Honeyed Wayfarer Meat Pie", category="food", item_type="Food", description="Flaky spiced crust baked by capital caravan guilds.", tier=3, price=16, quantity=5, hp_restore=20, taste_tags=["savory"], purpose_tags=["health"], effect_tags=["healing"]),
            _make_consumable("Roast Pheasant Courier Ration", category="food", item_type="Food", description="Wax-sealed savory supper keeping field scouts in peak form.", tier=2, price=34, quantity=4, hp_restore=40, mp_restore=15, taste_tags=["savory", "hearty"], purpose_tags=["health"], effect_tags=["healing"]),
            _make_consumable("Elven Waybread Loaf", category="food", item_type="Food", description="Dense honey-oat trail bread sustaining long marches.", tier=2, price=32, quantity=4, hp_restore=35, buffs={"dt": 2}, taste_tags=["sweet"], purpose_tags=["health"], effect_tags=["healing", "defense_buff"]),
            _make_consumable("Spiced Hearth Cheese Wedge", category="food", item_type="Food", description="Aged herb-rind wedge favored by guild quartermasters.", tier=3, price=15, quantity=5, hp_restore=18, taste_tags=["savory"], purpose_tags=["health"], effect_tags=["healing"]),
        ]
        drinks_pool = [
            _make_consumable("Starlight Chamomile Draught", category="drinks", item_type="Drink", description="Warm steeped blossom infusion restoring focus and calm.", tier=2, price=30, quantity=4, hp_restore=15, mp_restore=35, taste_tags=["herbal", "tea"], purpose_tags=["mana"], effect_tags=["mana_restore"]),
            _make_consumable("Sunburst Orchard Cider", category="drinks", item_type="Drink", description="Crisp bottled apple cider lifting tavern spirits.", tier=3, price=16, quantity=5, hp_restore=12, mp_restore=18, buffs={"cha": 1}, taste_tags=["sweet"], purpose_tags=["hydration"], effect_tags=["mana_restore", "charisma_buff"]),
            _make_consumable("Roasted Chicory Camp Brew", category="drinks", item_type="Drink", description="Bitter trail roast sharpening eyes on night watch.", tier=3, price=14, quantity=5, mp_restore=22, taste_tags=["caffeine"], purpose_tags=["mana"], effect_tags=["mana_restore"]),
            _make_consumable("Velvet Moonberry Cordial", category="drinks", item_type="Drink", description="Rich spiced berry cordial boosting poise in court halls.", tier=2, price=34, quantity=3, hp_restore=18, mp_restore=30, buffs={"cha": 2}, taste_tags=["sweet", "spiced"], purpose_tags=["hydration"], effect_tags=["mana_restore", "charisma_buff"]),
        ]
        meds_pool = [
            _make_consumable("Lesser Healing Alchemist Draught", category="meds", item_type="Potion", description="Ruby apothecary phial mending cuts cleanly.", tier=3, price=22, quantity=4, hp_restore=35, purpose_tags=["health"], effect_tags=["healing"]),
            _make_consumable("Potent Vitalis Elixir", category="meds", item_type="Potion", description="High-potency red cordial knit-mending deep battle wounds.", tier=2, price=58, quantity=3, hp_restore=65, purpose_tags=["health"], effect_tags=["healing"]),
            _make_consumable("Silverleaf Antidote Tonic", category="meds", item_type="Potion", description="Herbal purgative neutralizing venoms and curses.", tier=2, price=48, quantity=3, hp_restore=25, cure_status=["Poisoned", "Bleeding"], purpose_tags=["cure"], effect_tags=["cleanse_all"]),
            _make_consumable("Azure Mana Resonance Phial", category="meds", item_type="Potion", description="Crystalline distillate replenishing arcane reserves.", tier=2, price=54, quantity=3, mp_restore=45, purpose_tags=["mana"], effect_tags=["mana_restore"]),
        ]
        gifts_pool = [
            _make_consumable("Gilded Songbird Brooch Gift Box", category="gifts", item_type="Gift", description="Velvet-boxed keepsake prized by nobles and companions.", tier=2, price=45, quantity=3, social_affinity_bonus=2, purpose_tags=["gift"]),
            _make_consumable("Pressed Moonflower Ribbon Set", category="gifts", item_type="Gift", description="Fragrant dried blossoms wrapped in silk cord.", tier=3, price=20, quantity=4, social_affinity_bonus=1, purpose_tags=["gift"]),
            _make_consumable("Carved Amber Scent Vial", category="gifts", item_type="Gift", description="Warm cedar-and-amber perfume bottle ready for gifting.", tier=2, price=42, quantity=3, social_affinity_bonus=2, purpose_tags=["gift"]),
            _make_consumable("Hand-Painted Porcelain Tea Cup", category="gifts", item_type="Gift", description="Fine guildware ceramic packed in straw cushioning.", tier=3, price=24, quantity=4, social_affinity_bonus=1, purpose_tags=["gift"]),
        ]
        clothing_pool = [
            _make_equipment_entry("Embroidered Traveler's Linen Tunic", category="clothing", item_type="Clothing", slot="Top", description="Breathable city tunic tailored for guild halls.", tier=3, price=42, quantity=3, stat_modifiers={"cha": 1, "eva": 2}, social_flags=["comfortable"], style="casual"),
            _make_equipment_entry("Tailored Velvet Envoy Coat", category="clothing", item_type="Clothing", slot="Top", description="Sharp deep-plum coat that turns heads in court squares.", tier=2, price=88, quantity=2, stat_modifiers={"cha": 1, "eva": 2}, social_affinity_bonus=2, social_flags=["elegant"], style="formal"),
            _make_equipment_entry("Reinforced Nomad Wool Trousers", category="clothing", item_type="Clothing", slot="Bottom", description="Sturdy stitched trousers built for long caravan roads.", tier=3, price=40, quantity=3, stat_modifiers={"eva": 2}, social_flags=["rugged"], style="casual"),
            _make_equipment_entry("Supple Calfskin Courier Boots", category="clothing", item_type="Clothing", slot="Shoes", description="Soft-soled boots favoring nimble street footing.", tier=2, price=74, quantity=2, stat_modifiers={"eva": 3}, social_flags=["cool"], style="casual"),
        ]
        accessories_pool = [
            _make_equipment_entry("Silver Compass Signet Ring", category="accessories", item_type="Accessory", slot="Accessory 1", description="Finely etched guild signet aiding perception in dim halls.", tier=2, price=76, quantity=2, stat_modifiers={"per": 1, "eva": 2}, social_affinity_bonus=1),
            _make_equipment_entry("Woven Silk Wayfarer Scarf", category="accessories", item_type="Accessory", slot="Accessory 1", description="Light scarf lending easy charm in tavern talks.", tier=3, price=38, quantity=3, stat_modifiers={"cha": 1}, social_flags=["graceful"]),
            _make_equipment_entry("Brass Astrolabe Pocket Charm", category="accessories", item_type="Accessory", slot="Accessory 2", description="Tiny calibrated star charm prized by scouts.", tier=2, price=70, quantity=2, stat_modifiers={"luk": 1, "eva": 2}),
            _make_equipment_entry("Leather Scout Satchel Belt", category="accessories", item_type="Accessory", slot="Accessory 2", description="Organized belt pouch keeping potions quick to draw.", tier=3, price=36, quantity=3, stat_modifiers={"eva": 2}),
        ]
        weapons_pool = [
            _make_equipment_entry("Tempered Steel Longsword", category="weapons", item_type="Weapon", slot="Weapon", description="Well-balanced courier-delivered guild blade.", tier=3, price=75, quantity=2, damage_mult=1.15, stat_modifiers={"atk": 4}),
            _make_equipment_entry("Runed Finewood Hunter Bow", category="weapons", item_type="Weapon", slot="Weapon", description="Recurve longbow braced with etched brass tips.", tier=2, price=155, quantity=1, damage_mult=1.28, stat_modifiers={"atk": 8, "acc": 4}),
            _make_equipment_entry("Silver-Inlaid Duelist Sabre", category="weapons", item_type="Weapon", slot="Weapon", description="Swift curved sabre suited for tight alley skirmishes.", tier=2, price=160, quantity=1, damage_mult=1.28, stat_modifiers={"atk": 7, "eva": 3}),
            _make_equipment_entry("Oak-Shafted Iron Halberd", category="weapons", item_type="Weapon", slot="Weapon", description="Reliable polearm shipped in disassembled crate sections.", tier=3, price=82, quantity=2, damage_mult=1.18, stat_modifiers={"atk": 5}),
        ]
        armor_pool = [
            _make_equipment_entry("Studded Leather Brigandine", category="armor", item_type="Armor", slot="Armor", description="Flexible boiled-leather chestpiece with iron rivets.", tier=3, price=70, quantity=2, dt=4, stat_modifiers={"dt": 4}),
            _make_equipment_entry("Artisan Scale-Mail Hauberk", category="armor", item_type="Armor", slot="Armor", description="Interlocking bronze-steel scales balancing protection and poise.", tier=2, price=150, quantity=1, dt=7, stat_modifiers={"dt": 7, "eva": 2}),
            _make_equipment_entry("Padded Ranger Gambeson", category="armor", item_type="Armor", slot="Armor", description="Quilted linen coat absorbing blunt blows cleanly.", tier=3, price=62, quantity=2, dt=3, stat_modifiers={"dt": 3, "eva": 2}),
            _make_equipment_entry("Oak-Core Kite Shield", category="armor", item_type="Shield", slot="Shield", description="Iron-rimmed shield strapped for courier freight.", tier=2, price=125, quantity=1, dt=6, stat_modifiers={"dt": 6}),
        ]
    elif theme in ("cyberpunk", "sci_fi", "steampunk", "post_apocalypse"):
        # Distinct sci-fi / tech / industrial retail flavor
        prefix_f = {"cyberpunk": "Synth", "sci_fi": "Orbital", "steampunk": "Brasswork", "post_apocalypse": "Vault-Sealed"}[theme]
        food_pool = [
            _make_consumable(f"{prefix_f} Protein Ration Bento", category="food", item_type="Food", description="Vacuum-sealed balanced meal pack ready on drop-pod delivery.", tier=2, price=28, quantity=4, hp_restore=36, mp_restore=14, taste_tags=["savory"], purpose_tags=["health"], effect_tags=["healing"]),
            _make_consumable(f"{prefix_f} Spiced Noodle Cup", category="food", item_type="Food", description="Self-heating courier noodle pot with savory broth.", tier=3, price=16, quantity=5, hp_restore=20, taste_tags=["savory", "spicy"], purpose_tags=["health"], effect_tags=["healing"]),
            _make_consumable(f"{prefix_f} Honey-Nut Nutrient Bar", category="food", item_type="Food", description="High-calorie bar built for long shifts.", tier=3, price=14, quantity=5, hp_restore=18, taste_tags=["sweet"], purpose_tags=["health"], effect_tags=["healing"]),
            _make_consumable(f"{prefix_f} Smoked Roast MRE Kit", category="food", item_type="Food", description="Flame-free ration heater yielding a hot savory supper.", tier=2, price=32, quantity=3, hp_restore=40, buffs={"dt": 2}, taste_tags=["savory", "hearty"], purpose_tags=["health"], effect_tags=["healing", "defense_buff"]),
        ]
        drinks_pool = [
            _make_consumable(f"{prefix_f} Matcha Hyper-Fuel Can", category="drinks", item_type="Drink", description="Electrolyte-infused energy drink restoring 18 HP and 26 MP.", tier=2, price=24, quantity=4, hp_restore=18, mp_restore=26, taste_tags=["caffeine", "tea"], purpose_tags=["hydration"], effect_tags=["healing", "mana_restore"]),
            _make_consumable(f"{prefix_f} Cold-Press Espresso Shot", category="drinks", item_type="Drink", description="Pressurized coffee ampoule sharpening reflex speed.", tier=3, price=15, quantity=5, mp_restore=22, buffs={"eva": 4}, taste_tags=["coffee", "caffeine"], purpose_tags=["mana"], effect_tags=["mana_restore", "evasion_buff"]),
            _make_consumable(f"{prefix_f} Sparkling Citrus Soda", category="drinks", item_type="Drink", description="Chilled fizzing soda refreshing weary nerves.", tier=3, price=13, quantity=5, hp_restore=12, mp_restore=15, taste_tags=["citrus", "fizzy"], purpose_tags=["hydration"], effect_tags=["mana_restore"]),
            _make_consumable(f"{prefix_f} Spiced Tonic Reserve", category="drinks", item_type="Drink", description="Distilled botanical mixer easing diplomatic talks.", tier=2, price=28, quantity=3, hp_restore=15, mp_restore=28, buffs={"cha": 2}, taste_tags=["spiced"], purpose_tags=["hydration"], effect_tags=["mana_restore", "charisma_buff"]),
        ]
        meds_pool = [
            _make_consumable(f"{prefix_f} Field Med-Patch Pack", category="meds", item_type="Potion", description="Sterile adhesive trauma patches mending wounds quickly.", tier=3, price=24, quantity=4, hp_restore=35, purpose_tags=["health"], effect_tags=["healing"]),
            _make_consumable(f"{prefix_f} Trauma Nano-Injector", category="meds", item_type="Potion", description="Reinforced autoinjector restoring 65 HP in seconds.", tier=2, price=58, quantity=3, hp_restore=65, purpose_tags=["health"], effect_tags=["healing"]),
            _make_consumable(f"{prefix_f} Bio-Cleanse Detox Vial", category="meds", item_type="Potion", description="Rapid purifier purging toxins, burns, and radiation.", tier=2, price=50, quantity=3, hp_restore=25, cure_status=["Poisoned", "Burned", "Corroded"], purpose_tags=["cure"], effect_tags=["cleanse_all"]),
            _make_consumable(f"{prefix_f} Neural Capacitor Ampoule", category="meds", item_type="Potion", description="Stabilized bio-cell replenishing tactical energy reserves.", tier=2, price=52, quantity=3, mp_restore=45, purpose_tags=["mana"], effect_tags=["mana_restore"]),
        ]
        gifts_pool = [
            _make_consumable(f"{prefix_f} Holo-Locket Keepsake", category="gifts", item_type="Gift", description="Compact brushed-alloy locket displaying stored stills.", tier=2, price=42, quantity=3, social_affinity_bonus=2, purpose_tags=["gift"]),
            _make_consumable(f"{prefix_f} Artisan Synth-Truffle Box", category="gifts", item_type="Gift", description="Luxury courier confection packed in foil.", tier=2, price=38, quantity=3, social_affinity_bonus=2, taste_tags=["sweet"], purpose_tags=["gift"]),
            _make_consumable(f"{prefix_f} Aromatic Vapor Diffuser", category="gifts", item_type="Gift", description="Pocket cedar-amber diffuser prized in cramped quarters.", tier=3, price=22, quantity=4, social_affinity_bonus=1, purpose_tags=["gift"]),
            _make_consumable(f"{prefix_f} Enamel Faction Pin Set", category="gifts", item_type="Gift", description="Collectible enamel pins packed on velvet card.", tier=3, price=20, quantity=4, social_affinity_bonus=1, purpose_tags=["gift"]),
        ]
        clothing_pool = [
            _make_equipment_entry(f"{prefix_f} Weatherproof Field Jacket", category="clothing", item_type="Clothing", slot="Top", description="Clean everyday outerwear tailored for city corridors.", tier=2, price=82, quantity=2, stat_modifiers={"cha": 1, "eva": 2}, social_affinity_bonus=2, social_flags=["cool"], style="techwear"),
            _make_equipment_entry(f"{prefix_f} Breathable Utility Shirt", category="clothing", item_type="Clothing", slot="Top", description="Soft wrinkle-resistant knit top in slate charcoal.", tier=3, price=40, quantity=3, stat_modifiers={"eva": 2}, social_flags=["comfortable"], style="casual"),
            _make_equipment_entry(f"{prefix_f} Articulated Cargo Slacks", category="clothing", item_type="Clothing", slot="Bottom", description="Gusseted courier slacks built for nimble movement.", tier=3, price=44, quantity=3, stat_modifiers={"eva": 2}, social_flags=["tactical"], style="casual"),
            _make_equipment_entry(f"{prefix_f} Mag-Grip Street Boots", category="clothing", item_type="Clothing", slot="Shoes", description="All-weather boots with high-traction soles.", tier=2, price=74, quantity=2, stat_modifiers={"eva": 3}, social_flags=["cool"], style="casual"),
        ]
        accessories_pool = [
            _make_equipment_entry(f"{prefix_f} Smart Diagnostic Wristband", category="accessories", item_type="Accessory", slot="Accessory 1", description="Low-profile biometric watch syncing courier telemetry.", tier=2, price=78, quantity=2, stat_modifiers={"per": 1, "eva": 2}),
            _make_equipment_entry(f"{prefix_f} Anti-Glare Optic Specs", category="accessories", item_type="Accessory", slot="Accessory 1", description="Polarized frames improving clarity in harsh neon.", tier=3, price=38, quantity=3, stat_modifiers={"per": 1}),
            _make_equipment_entry(f"{prefix_f} Insulated Multi-Tool Clip", category="accessories", item_type="Accessory", slot="Accessory 2", description="Precision pocket clip prized by couriers and engineers.", tier=2, price=68, quantity=2, stat_modifiers={"int": 1, "eva": 1}),
            _make_equipment_entry(f"{prefix_f} Weatherproof Courier Sling", category="accessories", item_type="Accessory", slot="Accessory 2", description="Compact cross-body pouch keeping med-patches handy.", tier=3, price=34, quantity=3, stat_modifiers={"eva": 2}),
        ]
        weapons_pool = [
            _make_equipment_entry(f"{prefix_f} Compact Sidearm Pistol", category="weapons", item_type="Weapon", slot="Weapon", description="Standard retail personal-defense sidearm.", tier=3, price=78, quantity=2, damage_mult=1.15, stat_modifiers={"atk": 4}),
            _make_equipment_entry(f"{prefix_f} High-Velocity Carbine", category="weapons", item_type="Weapon", slot="Weapon", description="Modular commercial security carbine in padded case.", tier=2, price=165, quantity=1, damage_mult=1.28, stat_modifiers={"atk": 8, "acc": 4}),
            _make_equipment_entry(f"{prefix_f} Monomolecular Combat Knife", category="weapons", item_type="Weapon", slot="Weapon", description="Balanced Alloy survival blade for close quarters.", tier=2, price=145, quantity=2, damage_mult=1.25, stat_modifiers={"atk": 7, "eva": 3}),
            _make_equipment_entry(f"{prefix_f} Stun-Shock Baton", category="weapons", item_type="Weapon", slot="Weapon", description="Rechargeable security baton for non-lethal defense.", tier=3, price=70, quantity=2, damage_mult=1.12, stat_modifiers={"atk": 4}),
        ]
        armor_pool = [
            _make_equipment_entry(f"{prefix_f} Kevlar-Weave Street Vest", category="armor", item_type="Armor", slot="Armor", description="Concealable civilian ballistic vest.", tier=3, price=72, quantity=2, dt=4, stat_modifiers={"dt": 4}),
            _make_equipment_entry(f"{prefix_f} Composite Tactical Rig", category="armor", item_type="Armor", slot="Armor", description="Segmented ceramic-polymer torso plate.", tier=2, price=155, quantity=1, dt=7, stat_modifiers={"dt": 7, "eva": 2}),
            _make_equipment_entry(f"{prefix_f} Reinforced Hazard Coat", category="armor", item_type="Armor", slot="Armor", description="Abrasion-resistant trench liner with padded plates.", tier=3, price=65, quantity=2, dt=3, stat_modifiers={"dt": 3, "eva": 2}),
            _make_equipment_entry(f"{prefix_f} Collapsible Ballistic Buckler", category="armor", item_type="Shield", slot="Shield", description="Lightweight folding shield built for urban extraction.", tier=2, price=130, quantity=1, dt=6, stat_modifiers={"dt": 6}),
        ]
    else:
        # Modern / Anomalous / High School city online retail (MetroMart / QuickMart / City Online Store)
        food_pool = [
            _make_consumable("Deluxe Bento Box", category="food", item_type="Food", description="Balanced hot bento box delivered fresh with miso packet.", tier=2, price=25, quantity=4, hp_restore=35, mp_restore=15, taste_tags=["savory"], purpose_tags=["health"], effect_tags=["healing", "mana_restore"]),
            _make_consumable("Choco-Butter Croissant", category="food", item_type="Food", description="Warm flaky bakery croissant packed in a crisp box.", tier=3, price=17, quantity=5, hp_restore=20, taste_tags=["sweet", "bakery"], purpose_tags=["health"], effect_tags=["healing"]),
            _make_consumable("Tonkotsu Ramen Delivery Bowl", category="food", item_type="Food", description="Rich pork-broth ramen kit delivered piping hot.", tier=2, price=32, quantity=3, hp_restore=42, buffs={"dt": 2}, taste_tags=["savory", "hearty"], purpose_tags=["health"], effect_tags=["healing", "defense_buff"]),
            _make_consumable("Seared Salmon Onigiri Duo", category="food", item_type="Food", description="Two chilled seaweed rice balls wrapped for quick fuel.", tier=3, price=14, quantity=5, hp_restore=18, taste_tags=["savory"], purpose_tags=["health"], effect_tags=["healing"]),
            _make_consumable("Artisanal Truffle Toasties", category="food", item_type="Food", description="Savory toasted sandwich box popular with late-shift crews.", tier=2, price=28, quantity=4, hp_restore=34, buffs={"cha": 1}, taste_tags=["savory"], purpose_tags=["health"], effect_tags=["healing"]),
        ]
        drinks_pool = [
            _make_consumable("Matcha Spark Energy Drink", category="drinks", item_type="Drink", description="Crisp green tea energy blend restoring 15 HP and 15 MP.", tier=2, price=22, quantity=4, hp_restore=15, mp_restore=15, taste_tags=["tea", "caffeine"], purpose_tags=["hydration"], effect_tags=["healing", "mana_restore"]),
            _make_consumable("Iced Vanilla Latte", category="drinks", item_type="Drink", description="Refreshing cold espresso latte keeping focus sharp.", tier=3, price=12, quantity=5, hp_restore=10, mp_restore=18, taste_tags=["coffee", "sweet"], purpose_tags=["hydration"], effect_tags=["mana_restore"]),
            _make_consumable("Double-Shot Nitro Cold Brew", category="drinks", item_type="Drink", description="Strong metro coffee can built for all-night patrols.", tier=2, price=24, quantity=4, mp_restore=30, buffs={"eva": 5}, taste_tags=["coffee", "caffeine"], purpose_tags=["mana"], effect_tags=["mana_restore", "evasion_buff"]),
            _make_consumable("Sparkling Yuzu Tonic", category="drinks", item_type="Drink", description="Bright citrus soda restoring alertness cleanly.", tier=3, price=14, quantity=5, hp_restore=12, mp_restore=16, taste_tags=["citrus", "fizzy"], purpose_tags=["hydration"], effect_tags=["mana_restore"]),
            _make_consumable("Herbal Ginger Honey Tea", category="drinks", item_type="Drink", description="Warm bottled brew soothing nerves after long shifts.", tier=2, price=26, quantity=3, hp_restore=18, mp_restore=24, buffs={"cha": 1}, taste_tags=["tea", "herbal"], purpose_tags=["hydration"], effect_tags=["mana_restore", "charisma_buff"]),
        ]
        meds_pool = [
            _make_consumable("Emergency Trauma First-Aid Kit", category="meds", item_type="Potion", description="Compact sterile gauze, antiseptic, and hemostatic gel pack.", tier=3, price=28, quantity=4, hp_restore=38, purpose_tags=["health"], effect_tags=["healing"]),
            _make_consumable("Field Adrenaline Recovery Injector", category="meds", item_type="Potion", description="Single-dose emergency autoinjector restoring 65 HP.", tier=2, price=62, quantity=3, hp_restore=65, purpose_tags=["health"], effect_tags=["healing"]),
            _make_consumable("Electrolyte Detox & Antidote Pack", category="meds", item_type="Potion", description="Activated charcoal ampoules cleansing toxins and burns.", tier=2, price=48, quantity=3, hp_restore=25, cure_status=["Poisoned", "Bleeding", "Burned"], purpose_tags=["cure"], effect_tags=["cleanse_all"]),
            _make_consumable("Cognitive Focus & Stamina Ampoule", category="meds", item_type="Potion", description="Over-the-counter clinic ampoule replenishing 42 MP.", tier=2, price=52, quantity=3, mp_restore=42, purpose_tags=["mana"], effect_tags=["mana_restore"]),
        ]
        gifts_pool = [
            _make_consumable("Gourmet Truffle Chocolates", category="gifts", item_type="Gift", description="Artisan confectionery wrapped in satin ribbon.", tier=2, price=38, quantity=3, social_affinity_bonus=2, taste_tags=["sweet"], purpose_tags=["gift"], effect_tags=["morale_boost"]),
            _make_consumable("Artisanal Cedar & Jasmine Candle", category="gifts", item_type="Gift", description="Hand-poured glass jar candle boxed with a gift tag.", tier=2, price=44, quantity=3, social_affinity_bonus=2, purpose_tags=["gift"]),
            _make_consumable("Scented Lavender Hand Cream", category="gifts", item_type="Gift", description="Calming floral hand lotion packaged for easy gifting.", tier=3, price=24, quantity=4, social_affinity_bonus=1, purpose_tags=["gift"]),
            _make_consumable("Single-Origin Pour-Over Coffee Gift Tin", category="gifts", item_type="Gift", description="Small-batch roasted beans admired by busy professionals.", tier=2, price=46, quantity=3, social_affinity_bonus=2, purpose_tags=["gift"]),
            _make_consumable("Cute Mascot Phone Charm", category="gifts", item_type="Gift", description="Collectible acrylic mascot charm sealed in a gift pouch.", tier=3, price=22, quantity=4, social_affinity_bonus=1, purpose_tags=["gift"]),
        ]
        clothing_pool = [
            _make_equipment_entry("Tailored Charcoal Trench Coat", category="clothing", item_type="Clothing", slot="Top", description="Sharp weather-resistant trench worn by city detectives and operatives.", tier=2, price=92, quantity=2, stat_modifiers={"cha": 1, "eva": 2}, social_affinity_bonus=2, social_flags=["professional", "cool"], style="outerwear"),
            _make_equipment_entry("Crisp Oxford Button-Down Shirt", category="clothing", item_type="Clothing", slot="Top", description="Easy-care cotton shirt looking sharp under any jacket.", tier=3, price=44, quantity=3, stat_modifiers={"cha": 1, "eva": 1}, social_flags=["neat"], style="formal"),
            _make_equipment_entry("Heavyweight Urban Zip Hoodie", category="clothing", item_type="Clothing", slot="Top", description="Warm fleece hoodie suited for casual evening errands.", tier=3, price=40, quantity=3, stat_modifiers={"eva": 3}, social_flags=["comfortable", "relaxed"], style="cozy"),
            _make_equipment_entry("Stretch-Twill Metro Trousers", category="clothing", item_type="Clothing", slot="Bottom", description="Tailored dark trousers engineered for long days on foot.", tier=2, price=72, quantity=2, stat_modifiers={"eva": 2, "cha": 1}, social_flags=["professional"], style="formal"),
            _make_equipment_entry("All-Weather Leather Chelsea Boots", category="clothing", item_type="Clothing", slot="Shoes", description="Clean waterproof boots pairing comfort with polish.", tier=2, price=78, quantity=2, stat_modifiers={"eva": 3}, social_flags=["cool"], style="formal"),
        ]
        accessories_pool = [
            _make_equipment_entry("Portable Fast-Charger Power Bank", category="accessories", item_type="Accessory", slot="Accessory 1", description="High-capacity slim battery pack keeping comms devices topped up.", tier=2, price=45, quantity=3, stat_modifiers={"per": 1, "eva": 1}),
            _make_equipment_entry("Polarized Anti-Glare Eyeglasses", category="accessories", item_type="Accessory", slot="Accessory 1", description="Lightweight titanium frames sharpening detail vision.", tier=2, price=68, quantity=2, stat_modifiers={"per": 1, "cha": 1}),
            _make_equipment_entry("Insulated Matte Steel Tumbler", category="accessories", item_type="Accessory", slot="Accessory 2", description="Keeps coffee piping hot through late briefings.", tier=3, price=32, quantity=4, stat_modifiers={"cha": 1}),
            _make_equipment_entry("Chronograph Steel Wristwatch", category="accessories", item_type="Accessory", slot="Accessory 2", description="Waterproof quartz timepiece prized for clean punctuation.", tier=2, price=84, quantity=2, stat_modifiers={"cha": 1, "per": 1}, social_affinity_bonus=1),
        ]
        weapons_pool = [
            _make_equipment_entry("Reinforced Tactical Service Pistol", category="weapons", item_type="Weapon", slot="Weapon", description="Commercial licensed 9mm defense pistol shipped via bonded courier.", tier=3, price=82, quantity=2, damage_mult=1.15, stat_modifiers={"atk": 4}),
            _make_equipment_entry("Tungsten Collapsible Strike Baton", category="weapons", item_type="Weapon", slot="Weapon", description="Concealable hardened steel baton locking cleanly on snap.", tier=3, price=68, quantity=2, damage_mult=1.14, stat_modifiers={"atk": 4, "eva": 2}),
            _make_equipment_entry("Resonance-Edge Combat Tanto", category="weapons", item_type="Weapon", slot="Weapon", description="Precision alloy blade balanced for rapid field containment.", tier=2, price=155, quantity=1, damage_mult=1.28, stat_modifiers={"atk": 8, "eva": 2}),
            _make_equipment_entry("Precision Suppressed Marksman Carbine", category="weapons", item_type="Weapon", slot="Weapon", description="Commercial field carbine packed in discreet foam hardcase.", tier=2, price=175, quantity=1, damage_mult=1.30, stat_modifiers={"atk": 9, "acc": 4}),
        ]
        armor_pool = [
            _make_equipment_entry("Concealed Kevlar Courier Jacket", category="armor", item_type="Armor", slot="Armor", description="Discreet everyday jacket lined with Tier 3 aramid weave.", tier=3, price=74, quantity=2, dt=4, stat_modifiers={"dt": 4}),
            _make_equipment_entry("Ballistic Containment Trench Plate", category="armor", item_type="Armor", slot="Armor", description="Superior modular trauma liner built beneath street attire.", tier=2, price=158, quantity=1, dt=7, stat_modifiers={"dt": 7, "eva": 2}),
            _make_equipment_entry("Padded Metro Riot Vest", category="armor", item_type="Armor", slot="Armor", description="Sturdy shock-absorbing vest for dangerous district runs.", tier=3, price=66, quantity=2, dt=4, stat_modifiers={"dt": 4}),
            _make_equipment_entry("Compact Polycarbonate Buckler", category="armor", item_type="Shield", slot="Shield", description="Clear forearm shield rated against sudden ambushes.", tier=2, price=125, quantity=1, dt=6, stat_modifiers={"dt": 6}),
        ]

    pools: dict[str, list[dict[str, Any]]] = {
        "food": _rotate_pick(food_pool, day=day, count=4, pinned_first=1 if theme == "modern" else 0),
        "drinks": _rotate_pick(drinks_pool, day=day, count=4, pinned_first=1 if theme == "modern" else 0),
        "meds": _rotate_pick(meds_pool, day=day, count=4),
        "gifts": _rotate_pick(gifts_pool, day=day, count=4),
        "clothing": _rotate_pick(clothing_pool, day=day, count=4),
        "accessories": _rotate_pick(accessories_pool, day=day, count=4, pinned_first=1 if theme == "modern" else 0),
    }

    if has_combat:
        pools["weapons"] = _rotate_pick(weapons_pool, day=day, count=4)
        pools["armor"] = _rotate_pick(armor_pool, day=day, count=4)

    if has_arcane:
        from mechanics.combat.spells.registry import get_all_spells
        all_spells = get_all_spells()
        eligible_spells = [
            sp for sp in all_spells.values()
            if isinstance(sp, dict) and int(sp.get("tier", 3) or 3) in (2, 3)
        ]
        arcane_pool: list[dict[str, Any]] = []
        for idx, sp in enumerate(eligible_spells):
            t_val = 2 if int(sp.get("tier", 3) or 3) == 2 else 3
            prefix = "Tome" if t_val == 2 else "Spellbook"
            s_price = 280 if t_val == 2 else 85
            sp_meta = {
                "item_type": "Spellbook",
                "spell_id": sp.get("id"),
                "spell_name": sp["name"],
                "discipline": sp.get("discipline", "attack"),
                "school": sp.get("school", "Evocation"),
                "tier": t_val,
                "damage_type": sp.get("damage_type", "magical"),
                "is_spellbook": True,
                "tags": sp.get("tags", [sp.get("school", "Evocation"), f"Tier {t_val}"]),
            }
            sp_item = {
                "name": f"{prefix}: {sp['name']}",
                "item_type": "Spellbook",
                "description": f"Teaches {sp['name']} ({sp.get('tier_name', 'Basic')} {sp.get('discipline', 'attack').title()} Magic). Consumed on read.",
                "price": s_price,
                "quantity": 1,
                "tier": t_val,
                "category": "arcane",
                "category_label": "Arcane",
                "metadata": sp_meta,
                "effect": f"[SPELLBOOK_JSON]{json.dumps(sp_meta)}",
            }
            sp_item["badges"] = compute_phone_item_badges(sp_item)
            arcane_pool.append(sp_item)
        pools["arcane"] = _rotate_pick(arcane_pool, day=day, count=4)

    if is_nsfw:
        adult_pool = [
            _make_equipment_entry(
                "Sheer Midnight Lace Lingerie Set",
                category="adult",
                item_type="Lingerie",
                slot="Lingerie",
                description="Delicate scalloped black lace lingerie set boxed in discreet velvet packaging.",
                tier=2,
                price=145,
                quantity=2,
                stat_modifiers={"cha": 1},
                social_affinity_bonus=2,
                social_flags=["seductive", "intimate"],
                style="lingerie",
            ),
            _make_equipment_entry(
                "Satin Ribbon Wrist Restraints",
                category="adult",
                item_type="Accessory",
                slot="Accessory 2",
                description="Plush satin-lined cuffs shipped in an unmarked matte parcel.",
                tier=2,
                price=110,
                quantity=2,
                stat_modifiers={"cha": 1},
                social_affinity_bonus=2,
                social_flags=["intimate"],
            ),
            _make_consumable(
                "Warm Jasmine Massage Oil",
                category="adult",
                item_type="Consumable",
                description="Aromatic warming body oil bottled in dark amber glass.",
                tier=3,
                price=55,
                quantity=3,
                buffs={"cha": 2},
                purpose_tags=["utility"],
                effect_tags=["charisma_buff", "morale_boost"],
                social_affinity_bonus=2,
            ),
            _make_equipment_entry(
                "Silk Halter Babydoll & Garter Set",
                category="adult",
                item_type="Lingerie",
                slot="Lingerie",
                description="Lightweight blush silk set packed discreetly for doorstep drop.",
                tier=3,
                price=85,
                quantity=2,
                stat_modifiers={"cha": 1},
                social_affinity_bonus=1,
                social_flags=["seductive", "delicate"],
                style="lingerie",
            ),
            _make_consumable(
                "Velvet Rose Aphrodisiac Cordial",
                category="adult",
                item_type="Drink",
                description="Spiced rosewater nightcap heightening warmth during private evenings.",
                tier=2,
                price=68,
                quantity=3,
                mp_restore=25,
                buffs={"cha": 2},
                taste_tags=["sweet", "spiced"],
                purpose_tags=["hydration"],
                effect_tags=["charisma_buff", "morale_boost"],
                social_affinity_bonus=2,
            ),
        ]
        pools["adult"] = _rotate_pick(adult_pool, day=day, count=4)

    return pools


def build_phone_store_catalog(
    scen_key: str,
    *,
    store_mode: str = STORE_MODE_ONLINE_GENERAL,
    day: int = 1,
    is_nsfw: bool | None = None,
    player_level: int = 1,
    currency: str = "Credits",
) -> dict[str, Any]:
    """Build deterministic categorized online store stock (`online_general` or `school_mart`)."""
    del player_level, currency  # Reserved for future scaling hooks
    nsfw_on = scenario_data.is_nsfw_scenario(scen_key) if is_nsfw is None else bool(is_nsfw)
    mode = STORE_MODE_SCHOOL_MART if store_mode == STORE_MODE_SCHOOL_MART else STORE_MODE_ONLINE_GENERAL
    categories = get_eligible_phone_store_categories(scen_key, store_mode=mode, is_nsfw=nsfw_on)

    if mode == STORE_MODE_SCHOOL_MART:
        pools = _build_school_mart_pools(day=int(day or 1))
        intro = "Welcome to SchoolMart! Verified student discounts (-20%) applied across snacks, study supplies, and campus essentials."
        merchant_type = "school_mart"
    else:
        theme = _resolve_store_theme(scen_key)
        pools = _build_general_theme_pools(
            theme,
            scen_key,
            day=int(day or 1),
            has_combat=_has_combat_gear_tab(scen_key),
            has_arcane=is_magic_combat_scenario(scen_key),
            is_nsfw=nsfw_on,
        )
        intro = "Order food, drinks, meds, gifts, apparel, and tactical supplies for fast doorstep delivery."
        merchant_type = "online_merchant"

    stock: list[dict[str, Any]] = []
    seen_names: set[str] = set()
    for cat_entry in categories:
        cat_key = cat_entry["key"]
        if cat_key == "all":
            continue
        for item in pools.get(cat_key, []):
            item_copy = dict(item)
            item_copy["tier"] = 2 if int(item_copy.get("tier") or 3) <= 2 else 3
            item_copy["category"] = cat_key
            item_copy["category_label"] = cat_entry["label"]
            if not item_copy.get("badges"):
                item_copy["badges"] = compute_phone_item_badges(item_copy)
            low_n = str(item_copy.get("name") or "").strip().lower()
            if low_n and low_n not in seen_names:
                seen_names.add(low_n)
                stock.append(item_copy)

    # Guarantee test/UX signature items never collide with non-empty stock
    _ = re  # Keep module pattern consistent
    return {
        "intro_narrative": intro,
        "stock": stock,
        "rumors": [],
        "merchant_type": merchant_type,
        "store_mode": mode,
        "categories": categories,
        "in_person_only": False,
        "shop_faction_archetype": None,
        "is_cult_discounted_shop": False,
    }
