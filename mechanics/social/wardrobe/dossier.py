from __future__ import annotations
"""
Fog-of-War Witnessed Wardrobe Dossier Builders & Batch Discovery Recorders (Spec #7).
"""

from typing import Any, Mapping, Sequence

from .catalog import build_npc_wardrobe_presets, format_wardrobe_summary
from .constants import (
    ACTIVITY_KITS,
    CORE_WARDROBE_PRESETS,
    PRESET_CASUAL,
    PRESET_DUTY,
    PRESET_SLEEPWEAR,
    safe_json_dict,
)
from .resolver import resolve_actor_wardrobe_state

WARDROBE_FACT_CATEGORY = "wardrobe_preset"


def prepare_witnessed_wardrobe_entries(
    present_contacts: Sequence[Mapping[str, Any]],
    actors_state: Mapping[str, Mapping[str, Any]],
) -> list[dict[str, Any]]:
    """
    Extracts normalized discovery entries for all present contacts whose active preset
    is grounded in `actors_state`. Zero DB I/O.
    """
    if not present_contacts or not isinstance(actors_state, Mapping):
        return []

    actor_by_lower: dict[str, Mapping[str, Any]] = {}
    for a_key, a_val in actors_state.items():
        if not isinstance(a_val, Mapping):
            continue
        if str(a_val.get("actor_type") or "").lower() == "player":
            continue
        aname = str(a_val.get("actor_name") or a_key).strip().lower()
        if aname:
            actor_by_lower[aname] = a_val

    entries: list[dict[str, Any]] = []
    seen_keys: set[str] = set()
    for c in present_contacts:
        if not isinstance(c, Mapping):
            continue
        npc_id_str = str(c.get("npc_id") or c.get("npc_key") or "").strip()
        cname_raw = str(c.get("name") or "").strip()
        cid_raw = c.get("contact_id") or c.get("id")
        try:
            cid = int(cid_raw) if cid_raw is not None else 0
        except Exception:
            cid = 0
        key_id = npc_id_str or cname_raw or (str(cid) if cid > 0 else "")
        if not key_id or key_id.lower() in seen_keys:
            continue
        cname = cname_raw.lower()
        actor = actor_by_lower.get(cname) or actor_by_lower.get(npc_id_str.lower())
        if not actor:
            continue
        preset = str(actor.get("active_outfit_preset") or "").strip()
        if preset not in CORE_WARDROBE_PRESETS and preset not in ACTIVITY_KITS:
            continue
        clothing = actor.get("clothing") if isinstance(actor.get("clothing"), Mapping) else {}
        summary = format_wardrobe_summary(clothing)
        if not summary or summary.lower() == "clothed":
            continue
        seen_keys.add(key_id.lower())
        entries.append(
            {
                "npc_id": key_id,
                "contact_id": cid,
                "contact_name": cname_raw or key_id,
                "fact_category": WARDROBE_FACT_CATEGORY,
                "fact_key": f"preset:{preset}",
                "fact_value": summary,
            }
        )
    return entries


def record_witnessed_wardrobe_preset(
    session_id: int,
    character_id: int,
    npc_id: str | int,
    preset_key: str,
    summary_text: str,
    *,
    turn_number: int = 0,
    conn: Any = None,
) -> int:
    """Persists a single witnessed wardrobe preset discovery via db facade."""
    npc_key = str(npc_id or "").strip()
    if not session_id or not npc_key or not preset_key:
        return 0
    import db
    entries = [
        {
            "npc_id": npc_key,
            "fact_key": f"preset:{preset_key}",
            "fact_value": str(summary_text or "").strip(),
        }
    ]
    return int(
        db.upsert_wardrobe_preset_discoveries_batch(
            session_id,
            character_id,
            entries,
            turn_number=int(turn_number or 0),
            conn=conn,
        )
        or 0
    )


def build_known_wardrobe_payload(
    npc: Mapping[str, Any],
    *,
    phys_actor_state: Mapping[str, Any] | None = None,
    discovered_facts: Sequence[Any] | None = None,
    is_colocated: bool = False,
    reveal_debug: bool = False,
    session: Mapping[str, Any] | None = None,
    scen_key: str = "",
    current_day: int = 1,
    current_minute: int = 480,
) -> dict[str, Any]:
    """
    Constructs the Fog-of-War masked `known_wardrobe` dossier payload for Web & Discord.
    Spec #7: Exposes `currently_wearing` ONLY when `is_colocated` is True.
    """
    sess = session if isinstance(session, Mapping) else {}
    resolved_scen = str(scen_key or sess.get("scenario_key") or npc.get("scenario_key") or "fantasy").strip()
    sess_id = int(sess.get("id") or sess.get("session_id") or npc.get("session_id") or 0)
    bundle = build_npc_wardrobe_presets(npc, scen_key=resolved_scen, session_id=sess_id)
    presets_catalog = bundle["presets"]
    kits_catalog = bundle["activity_kits"]

    witnessed_keys: set[str] = set()
    witnessed_values: dict[str, str] = {}
    for row in (discovered_facts or []):
        if isinstance(row, str):
            witnessed_keys.add(row.strip())
            continue
        if not isinstance(row, Mapping):
            continue
        fcat = str(row.get("fact_category") or "").strip().lower()
        fkey = str(row.get("fact_key") or "").strip()
        if fcat == WARDROBE_FACT_CATEGORY or fkey.startswith("preset:"):
            witnessed_keys.add(fkey)
            if row.get("fact_value"):
                witnessed_values[fkey] = str(row.get("fact_value"))

    currently_wearing: dict[str, Any] | None = None
    if is_colocated:
        active_preset = ""
        active_clothing: dict[str, Any] = {}
        if isinstance(phys_actor_state, Mapping) and isinstance(phys_actor_state.get("clothing"), Mapping):
            active_preset = str(phys_actor_state.get("active_outfit_preset") or "").strip()
            active_clothing = dict(phys_actor_state["clothing"])
        if not active_preset or not active_clothing:
            live = resolve_actor_wardrobe_state(
                npc,
                session=sess,
                scen_key=resolved_scen,
                current_day=current_day,
                current_minute=current_minute,
                is_colocated_with_player=True,
            )
            active_preset = active_preset or str(live.get("active_outfit_preset") or PRESET_DUTY)
            if not active_clothing:
                active_clothing = dict(live.get("clothing") or {})

        summary_now = format_wardrobe_summary(active_clothing)
        if active_preset:
            witnessed_keys.add(f"preset:{active_preset}")
        safe_clothing = dict(active_clothing)
        if not reveal_debug:
            safe_clothing.pop("under_top", None)
            safe_clothing.pop("under_bottom", None)
        currently_wearing = {
            "preset": active_preset or PRESET_DUTY,
            "summary": summary_now,
            "clothing": safe_clothing,
        }

    basic = safe_json_dict(npc.get("basic_info") or npc.get("basic_info_json"))
    gifted_by_preset = safe_json_dict(basic.get("gifted_wardrobe_by_preset"))

    preset_entries: dict[str, dict[str, Any]] = {}
    for pkey in (PRESET_DUTY, PRESET_CASUAL, PRESET_SLEEPWEAR):
        fkey = f"preset:{pkey}"
        is_known = bool(reveal_debug or fkey in witnessed_keys)
        catalog_summary = format_wardrobe_summary(presets_catalog.get(pkey))
        preset_entries[pkey] = {
            "known": is_known,
            "summary": (catalog_summary or witnessed_values.get(fkey)) if is_known else "???",
            "has_gift": bool(gifted_by_preset.get(pkey)),
        }

    kit_entries: dict[str, dict[str, Any]] = {}
    for kkey in ACTIVITY_KITS:
        if kkey not in kits_catalog:
            continue
        fkey = f"preset:{kkey}"
        is_known = bool(reveal_debug or fkey in witnessed_keys)
        if is_known:
            summary_val = format_wardrobe_summary(kits_catalog.get(kkey)) or witnessed_values.get(fkey)
            if summary_val:
                kit_entries[kkey] = {
                    "known": True,
                    "summary": summary_val,
                }

    gifted_items: list[str] = []
    for bucket_name, slot_dict in gifted_by_preset.items():
        if isinstance(slot_dict, Mapping):
            for _s, item_lbl in slot_dict.items():
                if item_lbl:
                    gifted_items.append(f"{item_lbl} ({bucket_name})")

    return {
        "is_colocated": bool(is_colocated),
        "currently_wearing": currently_wearing,
        "presets": preset_entries,
        "activity_kits": kit_entries,
        "gifted_items": gifted_items,
    }
