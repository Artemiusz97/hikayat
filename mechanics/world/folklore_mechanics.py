from __future__ import annotations
"""
Deep Folklore Modeling Primitives (`mechanics/world/folklore_mechanics.py`).

Shared across Canonical Folklore Codex entries (Track B) and ~30% of compatible
Procedural Unknown Anomalies (Track A):
1. Human / Prop Disguise Concealment & True-Form Reveal (`disguise_state`)
2. Soft-Lock-Safe 2-Stage Vessel / Master Tether (`tether_state`: 25% HP reform + `[🏺 Sever/Seal]` vs. 60% XP dispersion)
3. Playable Binary Question / Riddle Traps (`dialogue_trap` in Anomaly Parley + freeform keyword evaluation)
4. Dual Inventory + Improvised Folklore Offerings & Wards (`appeasement_tags` + 8 shop consumables granting `-5` DC)
5. Paradoxical Proximity Omens (`omen_paradox`: inverted sensory distance hooks for Stage 1 Clues & `👁️ Observe`).
"""

import json
import random
import re
from typing import Any, Dict, List, Optional, Tuple

import db
from mechanics.world.folklore_codex import load_procedural_pools

# -----------------------------------------------------------------------------
# 8 Canonical Folklore Ward & Offering Consumables
# -----------------------------------------------------------------------------
FOLKLORE_WARD_OFFERING_CATALOG: List[Dict[str, Any]] = [
    {
        "name": "Fresh River Cucumber",
        "appeasement_tag": "fresh_cucumber",
        "price": 18,
        "item_type": "Consumable",
        "shop_pools": ["urban_market", "shrine", "quartermaster"],
        "desc": "Crisp riverside cucumber carved with a polite ward-glyph. Prized offering for Kappa, Azukiarai, and freshwater spirits (-5 Containment DC).",
    },
    {
        "name": "Inari Fried Tofu Pouch",
        "appeasement_tag": "fried_tofu",
        "price": 22,
        "item_type": "Consumable",
        "shop_pools": ["urban_market", "shrine", "quartermaster"],
        "desc": "Sweet soy-simmered abura-age tofu wrapped in shrine paper. Traditional offering for Kitsune, Tanuki, Huli Jing, and fox/trickster spirits (-5 Containment DC).",
    },
    {
        "name": "Iron Nail & Kaffir Lime Kit",
        "appeasement_tag": "iron_nail",
        "secondary_tags": ["kaffir_lime"],
        "price": 35,
        "item_type": "Consumable",
        "shop_pools": ["shrine", "quartermaster"],
        "desc": "Cold wrought-iron nape spike paired with fragrant kaffir limes. Classical Nusantara & European ward against Pontianak, Saka blades, Rusalka, and Fae (-5 Containment DC).",
    },
    {
        "name": "Glutinous Rice & Cinnabar Talisman",
        "appeasement_tag": "glutinous_rice",
        "secondary_tags": ["paper_talisman"],
        "price": 32,
        "item_type": "Consumable",
        "shop_pools": ["shrine", "quartermaster"],
        "desc": "Uncooked nuomi glutinous rice pouch with a yellow cinnabar forehead seal. Binds Jiangshi, Aka Manto, Ungaikyō, and restless revenants (-5 Containment DC).",
    },
    {
        "name": "Coarse Shrine Salt & Counting Beans",
        "appeasement_tag": "coarse_salt",
        "secondary_tags": ["counting_beans"],
        "price": 20,
        "item_type": "Consumable",
        "shop_pools": ["urban_market", "shrine", "quartermaster"],
        "desc": "Purified sea-salt mixed with crimson adzuki beans and glass marbles. Distracts compulsive counters (Toyol, Churel, Azukiarai) and purifies miasma (-5 Containment DC).",
    },
    {
        "name": "Sweet Hearth Milk & Honey Cake",
        "appeasement_tag": "sweet_milk",
        "price": 20,
        "item_type": "Consumable",
        "shop_pools": ["urban_market", "quartermaster"],
        "desc": "Sealed flask of sweet cream with honey shortbread. Appeases domestic Boggarts, Nenek Kebayan, Changelings, and snuffs Hand of Glory tallow (-5 Containment DC).",
    },
    {
        "name": "Pressed Silver-Reed Charm",
        "appeasement_tag": "silver_reed",
        "price": 45,
        "item_type": "Consumable",
        "shop_pools": ["shrine", "quartermaster"],
        "desc": "Thin gold-and-silver ward leaf woven with bitter wormwood. Halts apex omens like the Dullahan, Banshee, Gumiho, and Substation Harbingers (-5 Containment DC).",
    },
    {
        "name": "White Kemenyan & Paper Effigy",
        "appeasement_tag": "white_incense",
        "secondary_tags": ["paper_talisman"],
        "price": 28,
        "item_type": "Consumable",
        "shop_pools": ["shrine", "urban_market", "quartermaster"],
        "desc": "Fragrant benzoin kemenyan incense sticks with ceremonial paper money. Satisfies Hantu Raya pacts, Heibai Wardens, Ghost Markets, and roadside shades (-5 Containment DC).",
    },
]

_TAG_TO_OFFERING_NAMES: Dict[str, List[str]] = {}
for _it in FOLKLORE_WARD_OFFERING_CATALOG:
    _all_tags = [_it["appeasement_tag"]] + list(_it.get("secondary_tags") or [])
    for _tg in _all_tags:
        _TAG_TO_OFFERING_NAMES.setdefault(_tg, []).append(_it["name"])


def build_folklore_shop_stock_items(pool_key: str = "shrine") -> List[Dict[str, Any]]:
    """Returns serialized merchant stock entries for `shrine`, `urban_market`, or `quartermaster` shops."""
    out: List[Dict[str, Any]] = []
    for spec in FOLKLORE_WARD_OFFERING_CATALOG:
        if pool_key not in (spec.get("shop_pools") or []):
            continue
        tags = [spec["appeasement_tag"]] + list(spec.get("secondary_tags") or [])
        effect_payload = {
            "desc": spec["desc"],
            "description": spec["desc"],
            "effect_desc": spec["desc"],
            "folklore_ward": True,
            "appeasement_tags": tags,
            "hp_restore": 15,
            "mp_restore": 15,
        }
        out.append({
            "name": spec["name"],
            "type": "Consumable",
            "item_type": "Consumable",
            "price": int(spec["price"]),
            "effect": f"[CONSUMABLE_JSON]{json.dumps(effect_payload, ensure_ascii=False)}",
            "desc": spec["desc"],
            "appeasement_tags": tags,
        })
    return out


def deduce_anomaly_category_tag(
    anom_type: str,
    sapience: str,
    physicality: str,
    primary_elem: str,
) -> str:
    """Canonical classification for anomaly category tags shared across Track A and Track B."""
    if anom_type == "phenomenon":
        return "spatial_warp"
    elif sapience == "sapient" and primary_elem in ("aether", "electric", "wind"):
        return "cognito_hazard"
    elif physicality == "non_corporeal":
        return "spectral_manifestation"
    elif anom_type == "object":
        return "cursed_relic"
    return "bio_aberration"


# -----------------------------------------------------------------------------
# 1. Disguise Concealment & True-Form Reveal
# -----------------------------------------------------------------------------
def is_blueprint_disguised(blueprint: Optional[Dict[str, Any]], dossier_revealed: Optional[bool] = None) -> bool:
    """Returns True if the anomaly currently wears an active mundane disguise and is not yet verified."""
    if not isinstance(blueprint, dict):
        return False
    is_rev = bool(blueprint.get("dossier_revealed")) if dossier_revealed is None else bool(dossier_revealed)
    if is_rev:
        return False
    d_state = blueprint.get("disguise_state")
    return bool(isinstance(d_state, dict) and d_state.get("is_disguised") and d_state.get("disguise_alias"))


def get_public_anomaly_name(
    blueprint: Optional[Dict[str, Any]],
    dossier_revealed: Optional[bool] = None,
    fallback: str = "Unidentified Anomaly",
) -> str:
    """
    Returns `disguise_alias` when `is_blueprint_disguised()` is True (preventing Bounty/SMS/Tracker spoilers),
    or the canonical/true anomaly name once unmasked or Dossier-verified.
    """
    if not isinstance(blueprint, dict):
        return fallback
    if is_blueprint_disguised(blueprint, dossier_revealed=dossier_revealed):
        alias = str((blueprint.get("disguise_state") or {}).get("disguise_alias") or "").strip()
        if alias:
            return alias
    return str(
        blueprint.get("canonical_name")
        or blueprint.get("name")
        or blueprint.get("entity_name")
        or fallback
    ).strip()


def unmask_blueprint_disguise(blueprint: Optional[Dict[str, Any]]) -> Tuple[Optional[Dict[str, Any]], str]:
    """
    Flips `disguise_state.is_disguised = False` on `blueprint` if disguised, returning `(updated_bp, unmask_notice)`.
    """
    if not isinstance(blueprint, dict):
        return blueprint, ""
    d_state = blueprint.get("disguise_state")
    if not isinstance(d_state, dict) or not (d_state.get("is_disguised") or (d_state.get("is_disguised") is None and d_state.get("disguise_alias"))):
        return blueprint, ""
    bp_copy = dict(blueprint)
    new_ds = dict(d_state)
    alias = str(new_ds.get("disguise_alias") or "Mundane Guise")
    new_ds["is_disguised"] = False
    bp_copy["disguise_state"] = new_ds
    true_name = str(bp_copy.get("canonical_name") or bp_copy.get("name") or "Anomalous Entity")
    cue = str(new_ds.get("unmask_cue") or f"The '{alias}' facade unravels, revealing **{true_name}**!")
    return bp_copy, f"🎭 **True Form Unmasked ({alias} ➔ {true_name}):** {cue}"


# -----------------------------------------------------------------------------
# 2. Soft-Lock-Safe 2-Stage Vessel / Master Tether
# -----------------------------------------------------------------------------
def get_enemy_tether_state(enemy_or_bp: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    if not isinstance(enemy_or_bp, dict):
        return None
    ts = enemy_or_bp.get("tether_state")
    if isinstance(ts, dict) and ts.get("has_tether"):
        return ts
    bp = enemy_or_bp.get("anomaly_blueprint")
    if isinstance(bp, dict) and isinstance(bp.get("tether_state"), dict) and bp["tether_state"].get("has_tether"):
        return bp["tether_state"]
    return None


def try_resolve_zero_hp_tether(enemy: Dict[str, Any]) -> Dict[str, Any]:
    """
    Evaluates a tethered anomaly reaching `<= 0 HP` in combat:
    - If `sealed` is already True: normal full capture/defeat (`outcome = 'sealed_defeat'`).
    - Stage 1 (`reformed_once == False`): restores enemy to `25% Max HP`, sets `reformed_once = True`,
      unlocks `[🏺 Sever/Seal <Vessel>]`, and keeps enemy alive (`outcome = 'reformed'`).
    - Stage 2 (`reformed_once == True` and still unsealed): triggers safe **Unsealed Dispersion**
      (`outcome = 'unsealed_dispersion'`, `xp_mult = 0.60`, `prevent_vault_capture = True`) so brute-force builds never soft-lock!
    """
    ts = get_enemy_tether_state(enemy)
    if not ts:
        return {"outcome": "normal"}
    if ts.get("sealed") or enemy.get("tether_sealed") or enemy.get("taboo_exploited"):
        return {"outcome": "sealed_defeat", "xp_mult": 1.0, "prevent_vault_capture": False}

    vessel = str(ts.get("vessel_name") or "Binding Vessel")
    ename = str(enemy.get("name") or "The Anomaly")
    if not ts.get("reformed_once") and not enemy.get("tether_reformed_once"):
        max_hp = max(40, int(enemy.get("max_hp") or 100))
        revive_hp = max(12, int(round(max_hp * 0.25)))
        new_ts = dict(ts)
        new_ts["reformed_once"] = True
        enemy["tether_state"] = new_ts
        enemy["tether_reformed_once"] = True
        enemy["hp"] = revive_hp
        if isinstance(enemy.get("anomaly_blueprint"), dict):
            enemy["anomaly_blueprint"]["tether_state"] = dict(new_ts)
        msg = (
            f"🏺 **Tether Reform!** **{ename}**'s bound **{vessel}** pulses violently—knitting its projection back to "
            f"**{revive_hp}/{max_hp} HP**! Use **[🏺 Sever/Seal {vessel}]** for full Vault containment, or strike again to force dispersion!"
        )
        return {
            "outcome": "reformed",
            "revived_hp": revive_hp,
            "vessel_name": vessel,
            "message": msg,
        }

    enemy["tether_dispersed_unsealed"] = True
    msg = (
        f"💨 **Unsealed Dispersion:** Without sealing **{vessel}**, **{ename}**'s projection unravels back toward its hidden anchor "
        f"(threat cleared at **60% XP**; seal the tether next time for a permanent Containment Vault capture!)."
    )
    return {
        "outcome": "unsealed_dispersion",
        "xp_mult": 0.60,
        "prevent_vault_capture": True,
        "vessel_name": vessel,
        "message": msg,
    }


def seal_enemy_tether(enemy: Dict[str, Any]) -> Dict[str, Any]:
    """Marks a tethered enemy's vessel as sealed so it can be immediately contained for 100% rewards."""
    ts = get_enemy_tether_state(enemy) or {"has_tether": True, "vessel_name": "Binding Vessel"}
    vessel = str(ts.get("vessel_name") or "Binding Vessel")
    new_ts = dict(ts)
    new_ts["sealed"] = True
    enemy["tether_state"] = new_ts
    enemy["tether_sealed"] = True
    if isinstance(enemy.get("anomaly_blueprint"), dict):
        enemy["anomaly_blueprint"]["tether_state"] = dict(new_ts)
    return {
        "sealed": True,
        "vessel_name": vessel,
        "message": f"🏺 **Tether Sealed!** You locked **{vessel}**, severing **{enemy.get('name', 'the anomaly')}**'s escape anchor!",
    }


# -----------------------------------------------------------------------------
# 3. Playable Binary Question / Riddle Traps
# -----------------------------------------------------------------------------
def has_active_dialogue_trap(blueprint: Optional[Dict[str, Any]]) -> bool:
    if not isinstance(blueprint, dict):
        return False
    dt = blueprint.get("dialogue_trap")
    return bool(isinstance(dt, dict) and dt.get("prompt_question") and not dt.get("resolved"))


def build_dialogue_trap_choices(
    blueprint: Dict[str, Any],
    entity_name: str,
    *,
    quest_id: str = "",
    sub_obj_id: Optional[int] = None,
    incursion_id: str = "",
    is_story_quest: bool = False,
) -> List[Dict[str, Any]]:
    """
    Renders playable Question-Trap choices (the 2 binary trap choices + the folklore-savvy evasive 3rd answer)
    during Anomaly Parley or direct encounter with a Question-Trap folklore entity.
    """
    dt = blueprint.get("dialogue_trap")
    if not isinstance(dt, dict) or not dt.get("prompt_question"):
        return []

    pub_name = get_public_anomaly_name(blueprint, fallback=entity_name)
    base_meta = {
        "intent": "quest_action" if quest_id else "incursion_action",
        "sub_intent": "anomaly_question_trap",
        "quest_id": quest_id,
        "sub_obj_id": sub_obj_id,
        "incursion_id": incursion_id,
        "breach_id": incursion_id,
        "is_story_quest": is_story_quest,
        "entity_name": pub_name,
        "_server_stamped": True,
    }
    return [
        {
            **base_meta,
            "label": f"💬 [Riddle Trap] {dt.get('trap_yes_label', 'Answer Yes')}",
            "stat": "CHA",
            "dc": 15,
            "requirement": 15,
            "trap_choice_kind": "trap_yes",
            "incursion_action": "question_trap_yes",
        },
        {
            **base_meta,
            "label": f"💬 [Riddle Trap] {dt.get('trap_no_label', 'Answer No')}",
            "stat": "CHA",
            "dc": 15,
            "requirement": 15,
            "trap_choice_kind": "trap_no",
            "incursion_action": "question_trap_no",
        },
        {
            **base_meta,
            "label": f"🧠 [Folklore Evasion] {dt.get('evasive_label', 'Give a non-committal third answer')}",
            "stat": "INT",
            "dc": 9,
            "requirement": 9,
            "trap_choice_kind": "evasive",
            "incursion_action": "question_trap_evasive",
        },
    ]


def _matches_folklore_keyword(text_low: str, kw: str) -> bool:
    kw_clean = str(kw or "").strip().lower()
    if not kw_clean or not text_low:
        return False
    return bool(re.search(rf"(?<![a-z0-9_]){re.escape(kw_clean)}(?![a-z0-9_])", text_low))


def evaluate_dialogue_trap_response(
    blueprint: Optional[Dict[str, Any]],
    player_text: str = "",
    trap_choice_kind: str = "",
) -> Dict[str, Any]:
    """
    Deterministically evaluates a Question-Trap reply from either structured choice buttons or freeform text:
    - `evasive` -> `satisfied=True`, `dc_mod=-4`, reveals Dossier & unmasks disguise!
    - `trap_yes` / `trap_no` -> `triggered_trap=True`, `strike_delta=1`, `backlash_damage=10`.
    """
    if not isinstance(blueprint, dict) or not isinstance(blueprint.get("dialogue_trap"), dict):
        return {"matched": False}
    dt = blueprint["dialogue_trap"]
    kind = str(trap_choice_kind or "").strip().lower()
    txt_low = str(player_text or "").strip().lower()

    evasive_kws = [str(k).lower() for k in (dt.get("evasive_keywords") or [])]
    trap_kws = [str(k).lower() for k in (dt.get("trap_keywords") or [])]

    if kind == "evasive" or (txt_low and any(_matches_folklore_keyword(txt_low, kw) for kw in evasive_kws)):
        return {
            "matched": True,
            "satisfied": True,
            "triggered_trap": False,
            "dc_mod": -4,
            "strike_delta": 0,
            "reveal_dossier": True,
            "message": f"🧠 **Question-Trap Broken!** {dt.get('success_note', 'Your ambiguous answer broke its binary curse contract!')}",
        }

    if kind in ("trap_yes", "trap_no") or (txt_low and any(_matches_folklore_keyword(txt_low, kw) for kw in trap_kws)):
        return {
            "matched": True,
            "satisfied": False,
            "triggered_trap": True,
            "dc_mod": 2,
            "strike_delta": 1,
            "backlash_damage": 10,
            "reveal_dossier": True,
            "message": f"⚠️ **Question-Trap Triggered!** {dt.get('fail_note', 'Answering its binary question directly fulfilled its curse condition!')}",
        }

    return {"matched": False}


# -----------------------------------------------------------------------------
# 4. Dual Inventory + Improvised Offerings & Wards
# -----------------------------------------------------------------------------
def _extract_item_appeasement_tags(inv_item: Dict[str, Any]) -> List[str]:
    name_low = str(inv_item.get("name") or "").strip().lower()
    tags: List[str] = []
    eff = str(inv_item.get("effect") or "")
    for prefix in ("[CONSUMABLE_JSON]", "[ITEM_JSON]", "[GEAR_JSON]"):
        if eff.startswith(prefix):
            try:
                meta = json.loads(eff[len(prefix):])
                if isinstance(meta, dict) and isinstance(meta.get("appeasement_tags"), list):
                    tags.extend(str(t).lower() for t in meta["appeasement_tags"])
            except Exception:
                pass
    for cat_it in FOLKLORE_WARD_OFFERING_CATALOG:
        if cat_it["name"].lower() == name_low:
            tags.append(cat_it["appeasement_tag"])
            tags.extend(cat_it.get("secondary_tags") or [])
    if not any(ex in name_low for ex in _IMPROVISED_OFFERING_EXCLUDE_TOKENS):
        for pattern, tag in _IMPROVISED_OFFERING_PATTERNS:
            if pattern.search(name_low):
                tags.append(tag)
    return list(dict.fromkeys(tags))


# Word-boundary heuristics for improvised offerings (avoids "beanie"->beans, "slime"->lime, "smelling salts"->salt)
_IMPROVISED_OFFERING_PATTERNS: List[Tuple["re.Pattern[str]", str]] = [
    (re.compile(r"\bcucumbers?\b"), "fresh_cucumber"),
    (re.compile(r"\b(?:fried\s+)?tofu\b|\babura(?:age)?\b"), "fried_tofu"),
    (re.compile(r"\b(?:kaffir\s+)?limes?\b"), "kaffir_lime"),
    (re.compile(r"\biron\s+nails?\b|\bcold[-\s]iron\b"), "iron_nail"),
    (re.compile(r"\bglutinous\s+rice\b|\bnuomi\b"), "glutinous_rice"),
    (re.compile(r"\b(?:paper\s+)?talismans?\b|\bofuda\b"), "paper_talisman"),
    (re.compile(r"\b(?:coarse|rock|sea|ritual|purifying)\s+salt\b|^salt\b"), "coarse_salt"),
    (re.compile(r"\b(?:counting\s+)?beans\b|\bmarbles\b"), "counting_beans"),
    (re.compile(r"\b(?:sweet\s+)?milk\b|\bhoney\s+cake\b"), "sweet_milk"),
    (re.compile(r"\bincense\b|\bkemenyan\b"), "white_incense"),
    (re.compile(r"\bsilver[-\s]reed\b|\bwormwood\b"), "silver_reed"),
]
_IMPROVISED_OFFERING_EXCLUDE_TOKENS: Tuple[str, ...] = (
    "smelling salt", "shrapnel", "road flare", "smokebomb", "smoke bomb", "grenade", "[anomalous]",
)
_OFFERING_ELIGIBLE_ITEM_TYPES: Tuple[str, ...] = (
    "consumable", "food", "drink", "potion", "misc", "ingredient", "material", "offering", "",
)


def _is_offering_eligible_inventory_row(row: Dict[str, Any]) -> bool:
    """Equipped gear, quest/key-locked items, reusable tools, and [GEAR_JSON] equipment are never offerings."""
    if int(row.get("quantity", 1) or 0) <= 0:
        return False
    if row.get("equipped") or row.get("is_quest_locked") or str(row.get("linked_quest_id") or "").strip():
        return False
    if row.get("is_quest_item"):
        return False
    if str(row.get("item_type") or "").strip().lower() not in _OFFERING_ELIGIBLE_ITEM_TYPES:
        return False
    eff = str(row.get("effect") or "")
    if eff.startswith("[GEAR_JSON]"):
        return False
    if eff.startswith("[ITEM_JSON]"):
        try:
            meta = json.loads(eff[len("[ITEM_JSON]"):])
            if isinstance(meta, dict) and (meta.get("slot") or meta.get("is_anomalous")):
                return False
        except Exception:
            pass
    return True


def find_matching_offering_in_inventory(
    user_id: Optional[int],
    blueprint: Optional[Dict[str, Any]],
    inventory_rows: Optional[List[Dict[str, Any]]] = None,
) -> Optional[Dict[str, Any]]:
    """Checks if the player carries an inventory item matching any of `blueprint['appeasement_tags']`."""
    if not isinstance(blueprint, dict):
        return None
    wanted = {str(t).strip().lower() for t in (blueprint.get("appeasement_tags") or []) if t}
    if not wanted:
        return None
    rows = inventory_rows
    if rows is None and user_id and int(user_id) > 0:
        try:
            rows = db.get_inventory(int(user_id)) or []
        except Exception:
            rows = []
    for row in (rows or []):
        if not isinstance(row, dict) or not _is_offering_eligible_inventory_row(row):
            continue
        item_tags = set(_extract_item_appeasement_tags(row))
        matched = wanted & item_tags
        if matched:
            return {
                "item_name": str(row.get("name") or "Folklore Ward"),
                "matched_tags": sorted(matched),
                "inventory_row": row,
            }
    return None


def consume_folklore_offering_item(user_id: Optional[int], item_name: str) -> bool:
    """Consumes 1 unit of `item_name` from `user_id`'s inventory when executing an Offering Counter-Rite."""
    if not user_id or int(user_id) <= 0 or not item_name:
        return False
    try:
        rows = db.get_inventory(int(user_id)) or []
        target_low = str(item_name).strip().lower()
        if not any(
            isinstance(r, dict)
            and str(r.get("name") or "").strip().lower() == target_low
            and _is_offering_eligible_inventory_row(r)
            for r in rows
        ):
            return False
        return bool(db.remove_item_by_name(int(user_id), str(item_name)))
    except Exception:
        return False


def build_offering_counter_rite_choice(
    blueprint: Optional[Dict[str, Any]],
    entity_name: str,
    *,
    user_id: Optional[int] = None,
    inventory_rows: Optional[List[Dict[str, Any]]] = None,
    base_dc: int = 12,
    quest_id: str = "",
    sub_obj_id: Optional[int] = None,
    incursion_id: str = "",
    is_story_quest: bool = False,
) -> Optional[Dict[str, Any]]:
    """
    If the player carries a matching Folklore Ward/Offering item, builds a `-5 DC`
    strike-free `[🎁 Folklore Offering: <Item>]` choice that consumes `1` item on execution.
    """
    match = find_matching_offering_in_inventory(user_id, blueprint, inventory_rows=inventory_rows)
    if not match:
        return None
    it_name = match["item_name"]
    pub_name = get_public_anomaly_name(blueprint, fallback=entity_name)
    eff_dc = max(5, int(base_dc) - 5)
    out_choice: Dict[str, Any] = {
        "label": f"🎁 [Folklore Counter-Rite] Present {it_name} to appease/ward {pub_name} (-5 DC)",
        "stat": "INT",
        "dc": eff_dc,
        "requirement": eff_dc,
        "intent": "quest_action" if quest_id else "incursion_action",
        "sub_intent": "folklore_offering_rite",
        "offering_item_name": it_name,
        "quest_id": quest_id,
        "sub_obj_id": sub_obj_id,
        "incursion_id": incursion_id,
        "breach_id": incursion_id,
        "is_story_quest": is_story_quest,
        "entity_name": pub_name,
        "_server_stamped": True,
    }
    if incursion_id or not quest_id:
        out_choice["incursion_action"] = "folklore_offering_rite"
    return out_choice


# -----------------------------------------------------------------------------
# 5. Paradoxical Proximity Omens & Track A Procedural Primitive Roller
# -----------------------------------------------------------------------------
def evaluate_omen_paradox(
    blueprint: Optional[Dict[str, Any]],
    *,
    dossier_revealed: bool = False,
    is_observation: bool = False,
) -> Dict[str, Any]:
    """
    Evaluates inverted sensory distance omens (`omen_paradox`, e.g. faint crying = right behind you):
    - During `👁️ Observe` or Stage 1 investigation: reveals the paradox warning and grants `-2` DC!
    - Reckless blind rush before Dossier verification: adds `+1` ambush agitation warning.
    """
    if not isinstance(blueprint, dict) or not isinstance(blueprint.get("omen_paradox"), dict):
        return {"has_paradox": False, "dc_mod": 0, "note": ""}
    op = blueprint["omen_paradox"]
    if is_observation or dossier_revealed:
        return {
            "has_paradox": True,
            "recognized": True,
            "dc_mod": -2,
            "note": f"👂 **Paradoxical Omen Read:** {op.get('observe_hint') or op.get('rule_summary', '')}",
        }
    return {
        "has_paradox": True,
        "recognized": False,
        "dc_mod": 1,
        "ambush_agitation": 1,
        "note": f"⚠️ **Deceptive Proximity Omen!** {op.get('rule_summary', 'Its sensory distance was inverted!')}",
    }


def roll_procedural_folklore_primitives(
    rng: random.Random,
    *,
    anom_type: str,
    anom_form: str,
    sapience: str,
    probability: float = 0.30,
) -> Dict[str, Any]:
    """
    Contextual ~30% roll giving Track A Procedural Unknowns rich folklore primitives
    (`disguise_state`, `tether_state`, `dialogue_trap`, `omen_paradox`, `appeasement_tags`).
    """
    out: Dict[str, Any] = {
        "disguise_state": None,
        "tether_state": None,
        "dialogue_trap": None,
        "omen_paradox": None,
        "appeasement_tags": [],
    }
    if rng.random() >= float(probability):
        return out

    pools = load_procedural_pools()
    prim = pools.get("procedural_primitive_templates") or {}

    # Always assign 1-2 compatible appeasement tags when primitive roll hits
    app_pool = prim.get("appeasement_pool") or []
    if app_pool:
        out["appeasement_tags"] = list(rng.choice(app_pool))

    compatible_slots: List[str] = ["omen_paradox"]
    disg_cands = [
        d for d in (prim.get("disguise_profiles") or [])
        if anom_type in (d.get("compatible_types") or []) and anom_form in (d.get("compatible_forms") or [])
    ]
    if disg_cands:
        compatible_slots.append("disguise")

    teth_cands = [
        t for t in (prim.get("tether_profiles") or [])
        if anom_type in (t.get("compatible_types") or [])
    ]
    if teth_cands:
        compatible_slots.append("tether")

    trap_cands = [
        tr for tr in (prim.get("dialogue_traps") or [])
        if sapience in (tr.get("compatible_sapience") or []) and anom_type == "entity"
    ]
    if trap_cands:
        compatible_slots.append("dialogue_trap")

    chosen_slot = rng.choice(compatible_slots)
    if chosen_slot == "disguise" and disg_cands:
        d = rng.choice(disg_cands)
        out["disguise_state"] = {
            "is_disguised": True,
            "disguise_alias": str(d["disguise_alias"]),
            "cover_desc": str(d.get("cover_desc") or ""),
            "unmask_cue": str(d.get("unmask_cue") or ""),
        }
    elif chosen_slot == "tether" and teth_cands:
        t = rng.choice(teth_cands)
        out["tether_state"] = {
            "has_tether": True,
            "vessel_name": str(t["vessel_name"]),
            "sever_stat": str(t.get("sever_stat") or "INT"),
            "tether_hint": str(t.get("tether_hint") or ""),
            "reformed_once": False,
            "sealed": False,
        }
    elif chosen_slot == "dialogue_trap" and trap_cands:
        out["dialogue_trap"] = dict(rng.choice(trap_cands))
    else:
        paradoxes = prim.get("omen_paradoxes") or []
        if paradoxes:
            out["omen_paradox"] = dict(rng.choice(paradoxes))

    return out
