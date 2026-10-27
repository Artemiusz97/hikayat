from __future__ import annotations
from typing import Any
from .constants import ENABLE_DYNAMIC_MULTIPASS, _ITEM_BLOCKLIST
import db
import re
import json
import random
import logging
from config import LLM_PASS1_TIMEOUT
from scenario_data import is_nsfw_scenario, uses_nsfw_model
import game_engine
from db import adb
import mechanics.narrative.event_handlers
from mechanics.narrative.events import bus, LocationChangedEvent, NPCSpawnedEvent, NPCStatusChangedEvent, ItemGiftedEvent, ItemGainedEvent, FactionLeadershipChangedEvent, QuestCompletedEvent

log = logging.getLogger(__name__)

def extract_scene_fields(
    data: dict,
    session: dict | None = None,
    default_narrative: str = "",
) -> tuple[list[dict], str, str, object, list]:
    """Canonical helper to extract and normalize choices, narrative, scene_title, dialogue_partner, and npcs from LLM scene/outcome dicts."""
    if not data or not isinstance(data, dict):
        data = {}

    raw_choices = (
        data.get("next_choices")
        or data.get("choices")
        or data.get("actions")
        or data.get("options")
        or data.get("suggested_actions")
        or data.get("next_actions")
        or []
    )
    normalized_choices = [
        c if isinstance(c, dict) else (c.model_dump(exclude_unset=True) if hasattr(c, "model_dump") else {"label": str(c)})
        for c in raw_choices if c
    ]

    next_narrative = str(
        data.get("next_narrative")
        or data.get("narrative")
        or data.get("outcome_narrative")
        or data.get("story")
        or data.get("scene_text")
        or data.get("description")
        or (session.get("narrative") if isinstance(session, dict) and default_narrative else "")
        or default_narrative
        or ""
    ).strip()

    scene_title = str(
        data.get("scene_title")
        or data.get("title")
        or data.get("name")
        or data.get("scene_name")
        or (session.get("scene_title") if isinstance(session, dict) else None)
        or "Hikayat"
    ).strip()

    partner_arg = (
        data.get("dialogue_partners")
        if data.get("dialogue_partners") is not None
        else data.get("dialogue_partner")
    )

    if data.get("npcs_present") is not None:
        npcs_arg = data.get("npcs_present")
    elif data.get("current_npcs") is not None:
        npcs_arg = data.get("current_npcs")
    elif isinstance(session, dict):
        npcs_arg = session.get("current_npcs", [])
    else:
        npcs_arg = []

    has_exited = bool(
        data.get("has_exited_convo")
        or (session and session.get("has_exited_convo"))
    )

    if partner_arg == "__NOOP__":
        partner_arg = None

    if has_exited:
        # Player explicitly exited the conversation: strictly clear dialogue partner
        partner_arg = None

    return normalized_choices, next_narrative, scene_title, partner_arg, npcs_arg

def get_combined_narrative(outcome: dict) -> str:
    """Canonical helper to extract and combine all narrative fields from an outcome dict."""
    if not outcome or not isinstance(outcome, dict):
        return ""
    return (
        str(outcome.get("outcome_narrative") or "") + " " +
        str(outcome.get("next_narrative") or "") + " " +
        str(outcome.get("narrative") or "")
    ).strip()

def is_check_success(check_obj, default_if_none: bool = True) -> bool:
    """Canonical evaluator for stat/skill check success across all engine structures.
    Safely handles CheckResult objects, dicts, and uppercase/lowercase tier strings.
    """
    if not check_obj:
        return default_if_none
    if hasattr(check_obj, "succeeded") and check_obj.succeeded is not None:
        return bool(check_obj.succeeded)
    if hasattr(check_obj, "is_success") and check_obj.is_success is not None:
        return bool(check_obj.is_success)
    if hasattr(check_obj, "tier") and check_obj.tier is not None:
        return str(check_obj.tier).lower() in ("success", "critical_success", "crit_success", "partial_success")
    if isinstance(check_obj, dict):
        if check_obj.get("succeeded") is not None:
            return bool(check_obj["succeeded"])
        if check_obj.get("is_success") is not None:
            return bool(check_obj["is_success"])
        tier_val = check_obj.get("tier")
        if tier_val is not None:
            return str(tier_val).lower() in ("success", "critical_success", "crit_success", "partial_success")
    return default_if_none

def resolve_pre_turn_vitals_and_resources(
    session: dict,
    party: list,
    actions: list | None = None,
    persist_db: bool = True,
) -> dict:
    """
    Deterministic Pre-Turn Vitals, Gold Spending, and Procedural Loot Engine.
    Executes before calling the Narrator LLM so all resource mutations are locked in Python:
      1. Deducts ActionCommand.gold_spent on successful check (or forfeited gamble wager on fail, D7).
      2. Rolls procedural loot from mechanics/combat/items/ when ActionCommand.triggers_loot_roll succeeds.
      3. Applies bounded non-combat hazard HP loss (5% on fail, 10% on crit_fail) on failed physical checks
         in combat-capable scenarios.
      4. Supports multiplayer co-op per-actor resolution (D15) and atomic post-narration DB staging (D3)
         when persist_db=False.
    """
    import scenario_data
    from mechanics.combat import is_in_combat

    if not actions:
        return {"character_outcomes": [], "stage_directives": [], "loot_items_rolled": []}

    if is_in_combat(session):
        return {"character_outcomes": [], "stage_directives": [], "loot_items_rolled": []}

    party_chars: list[dict] = []
    inv_by_uid: dict[int, list[dict]] = {}
    char_by_uid: dict[int, dict] = {}
    char_by_name: dict[str, dict] = {}
    for idx, p in enumerate(party or []):
        char = p[0] if isinstance(p, (tuple, list)) else p
        if not isinstance(char, dict):
            continue
        party_chars.append(char)
        c_uid = int(char.get("user_id") or -(idx + 1))
        char_by_uid[c_uid] = char
        if char.get("name"):
            char_by_name[str(char["name"]).strip().lower()] = char
        if isinstance(p, (tuple, list)) and len(p) > 1 and isinstance(p[1], list):
            inv_by_uid[c_uid] = list(p[1])
        elif c_uid > 0:
            inv_by_uid[c_uid] = list(db.get_inventory(c_uid) or [])
        else:
            inv_by_uid[c_uid] = []

    if not party_chars:
        return {"character_outcomes": [], "stage_directives": [], "loot_items_rolled": []}

    scen_key = session.get("scenario", "fantasy") if isinstance(session, dict) else "fantasy"
    is_non_combat_scen = scenario_data.is_non_combat_scenario(scen_key)
    session_id = session.get("id") if isinstance(session, dict) else 0

    def _ensure_actor_state(c_dict: dict) -> tuple[int, dict]:
        a_uid = int(c_dict.get("user_id") or 0)
        if a_uid not in actor_states:
            actor_states[a_uid] = {
                "char": c_dict,
                "name": c_dict.get("name", "Hero"),
                "hp_delta": 0,
                "mp_delta": 0,
                "gold_delta": 0,
                "items_gained": [],
                "items_lost": [],
                "status_effects": [],
                "authorized_gold_spend": 0,
                "authorized_gold_gain": 0,
                "authorized_hazard_dmg": 0,
                "consumable_hp_gain": 0,
                "consumable_mp_gain": 0,
            }
        return a_uid, actor_states[a_uid]

    actor_states: dict[int, dict] = {}
    _ensure_actor_state(party_chars[0])

    all_items_gained: list[str] = []
    all_items_lost: list[str] = []
    gifted_items: list[dict] = []
    media_captured: list[dict] = []
    consumed_items: list[dict] = []
    staged_consumable_removals: list[dict] = []
    staged_pickpocket_penalties: list[dict] = []
    staged_physical_state_dirty = False
    stage_directives: list[str] = []

    from mechanics.social.intimate_excitement import is_intimate_action_label
    from mechanics.narrative.intent import classify_action_intent, IntentCategory, IntentContext
    from mechanics.system.phone import scenario_has_smartphone

    for act in actions:
        if not isinstance(act, dict):
            continue

        # Resolve acting character for multiplayer co-op parity (D15)
        act_char_obj = act.get("char") if isinstance(act.get("char"), dict) else {}
        cand_uid = act.get("user_id") or act_char_obj.get("user_id")
        cand_name_actor = str(act_char_obj.get("name") or act.get("character_name") or "").strip().lower()
        acting_char = None
        if cand_uid is not None:
            try:
                acting_char = char_by_uid.get(int(cand_uid))
            except (ValueError, TypeError):
                acting_char = None
        if acting_char is None and cand_name_actor:
            acting_char = char_by_name.get(cand_name_actor)
        if acting_char is None:
            acting_char = party_chars[0]

        actor_uid, a_st = _ensure_actor_state(acting_char)
        char_name = a_st["name"]
        char_level = int(acting_char.get("level", 1) or 1)
        max_hp = max(1, int(acting_char.get("max_hp", 100) or 100))
        actor_inv = inv_by_uid.get(actor_uid)
        if actor_inv is None:
            actor_inv = list(db.get_inventory(actor_uid) or []) if actor_uid > 0 else []
            inv_by_uid[actor_uid] = actor_inv

        chk = act.get("check")
        succeeded = is_check_success(chk, default_if_none=True)
        tier = str(
            getattr(chk, "tier", None)
            or (chk.get("tier") if isinstance(chk, dict) else None)
            or ("success" if succeeded else "fail")
        ).lower()
        stat = str(act.get("stat") or "NONE").upper()
        intent = str(act.get("intent") or act.get("action_category") or "").lower()
        sub_intent_act = str(act.get("sub_intent") or "").lower()
        lbl = str(act.get("label") or act.get("action") or "")
        lbl_low = lbl.lower()

        is_social_act = (
            intent in ("dialogue", "disclosure_inquiry", "affection", "social_invite", "romantic_confession", "party_recruit", "social", "intimate")
            or stat == "CHA"
            or is_intimate_action_label(lbl)
        )

        # 0. Staged MP Cost (D3)
        act_mp_spent = int(act.get("mp_spent") or 0)
        if act_mp_spent > 0 and not act.get("_mp_already_deducted"):
            a_st["mp_delta"] -= act_mp_spent

        # 1. Gold Spending & Gamble Wager Rule (D7, D3)
        raw_gold_spent = int(act.get("gold_spent") or 0)
        is_gamble = sub_intent_act == "gamble" or intent == "gamble"
        if raw_gold_spent > 0:
            if succeeded or is_gamble:
                if "gold" in acting_char:
                    avail_gold = max(0, int(acting_char.get("gold", 0) or 0) - a_st["authorized_gold_spend"])
                    actual_spend = min(avail_gold, raw_gold_spent)
                else:
                    actual_spend = raw_gold_spent
                if actual_spend > 0:
                    if not act.get("_gold_already_deducted"):
                        a_st["gold_delta"] -= actual_spend
                        a_st["authorized_gold_spend"] += actual_spend
                        if persist_db:
                            act["_gold_already_deducted"] = True
                    if is_gamble and not succeeded:
                        stage_directives.append(
                            f"[STAGE DIRECTION — GAMBLE LOST]: {char_name} lost the wager and forfeited {actual_spend} Gold."
                        )
                    else:
                        stage_directives.append(
                            f"[STAGE DIRECTION — GOLD TRANSACTION]: {char_name} spent {actual_spend} Gold."
                        )
            else:
                act["_gold_spend_blocked_on_fail"] = True
                stage_directives.append(
                    f"[STAGE DIRECTION — TRANSACTION FAILED]: {char_name}'s attempt failed; 0 Gold was spent."
                )
        if act.get("_gold_shortfall_note"):
            stage_directives.append(str(act["_gold_shortfall_note"]))

        # 2. Procedural Loot Roll OR Scene Prop / Floor Drop / Foraging Pickup
        if bool(act.get("triggers_loot_roll")) and succeeded and not is_social_act:
            confiscate_loot_roll = False
            try:
                if scenario_data.is_anomalous_incursions_scenario(scen_key):
                    from mechanics.narrative.bounty import should_confiscate_anomalous_combat_loot
                    confiscate_loot_roll = should_confiscate_anomalous_combat_loot(
                        int(session_id or 0),
                        session=session,
                        user_id=actor_uid,
                    )
            except Exception:
                confiscate_loot_roll = False
            if confiscate_loot_roll:
                stage_directives.append(
                    f"[STAGE DIRECTION — TAXPAYER MANDATE]: {char_name} tags all anomalous residue and evidence for Public Agency HQ confiscation (0 personal loot)."
                )
            else:
                try:
                    from mechanics.combat.items.consumables.generators import generate_random_consumable
                    rolled_item = generate_random_consumable(scenario=scen_key, party_level=char_level)
                    item_str = rolled_item.get("formatted_string") or rolled_item.get("name")
                    item_display = rolled_item.get("name") or "Supply Cache"
                    if item_str:
                        a_st["items_gained"].append(item_str)
                        all_items_gained.append(item_str)
                        stage_directives.append(
                            f"[STAGE DIRECTION — LOOT DISCOVERED]: {char_name}'s search succeeded and uncovered '{item_display}'. "
                            f"Narrate finding '{item_display}' in `outcome_narrative`."
                        )
                except Exception:
                    pass
        elif succeeded and not is_social_act and any(
            kw in lbl_low for kw in ("pick up", "take the", "grab the", "collect the", "gather ", "forage ", "harvest ")
        ):
            phys_st = (session.get("physical_state") if isinstance(session, dict) else None) or (
                db.get_session_physical_state(session_id) if session_id else None
            ) or {}
            props_map = phys_st.get("props") if isinstance(phys_st, dict) else {}
            dropped_list = phys_st.get("dropped_items") if isinstance(phys_st, dict) else []
            matched_prop = None
            matched_display = None
            if isinstance(props_map, dict):
                for pk in list(props_map.keys()):
                    if pk and pk.lower() in lbl_low:
                        matched_prop = pk
                        matched_display = pk
                        props_map.pop(pk, None)
                        break
            if not matched_prop and isinstance(dropped_list, list):
                for di in list(dropped_list):
                    di_str = str(di or "").strip()
                    if not di_str:
                        continue
                    clean_di = re.sub(r"\s*\[(?:GEAR|ITEM)_JSON:.*$", "", di_str).strip()
                    if (clean_di and clean_di.lower() in lbl_low) or di_str.lower() in lbl_low:
                        matched_prop = di_str
                        matched_display = clean_di or di_str
                        dropped_list.remove(di)
                        break
            if matched_prop and matched_prop not in a_st["items_gained"]:
                a_st["items_gained"].append(matched_prop)
                all_items_gained.append(matched_prop)
                if isinstance(session, dict) and isinstance(phys_st, dict):
                    session["physical_state"] = phys_st
                    if persist_db and session_id:
                        try:
                            db.update_session_physical_state(session_id, phys_st)
                        except Exception:
                            pass
                    else:
                        staged_physical_state_dirty = True
                stage_directives.append(
                    f"[STAGE DIRECTION — ITEM ACQUIRED]: {char_name} picked up '{matched_display or matched_prop}'. Narrate acquiring it."
                )
            elif any(kw in lbl_low for kw in ("forage ", "harvest ")) and not a_st["items_gained"]:
                try:
                    from mechanics.combat.items.consumables.generators import generate_random_consumable
                    rolled_item = generate_random_consumable(scenario=scen_key, party_level=char_level)
                    item_display = rolled_item.get("name") or "Foraged Supplies"
                    if item_display:
                        a_st["items_gained"].append(item_display)
                        all_items_gained.append(item_display)
                        stage_directives.append(
                            f"[STAGE DIRECTION — FORAGING SUCCESS]: {char_name} foraged '{item_display}'. Narrate gathering it."
                        )
                except Exception:
                    pass

        # 3. Pre-Turn Gift Offer Validation & Media Capture
        if succeeded and lbl:
            try:
                present_npc_names = [
                    (n.get("name") if isinstance(n, dict) else str(n))
                    for n in (session.get("current_npcs") or [])
                    if n
                ] if isinstance(session, dict) else []
                ictx = IntentContext(
                    current_zone=session.get("current_location", "") if isinstance(session, dict) else "",
                    present_npcs=present_npc_names,
                    scenario=scen_key,
                )
                parsed_intent = classify_action_intent(lbl, context=ictx)
                if (parsed_intent.category == IntentCategory.GIFT_OFFER or act.get("sub_intent") == "gift_offer") and actor_inv:
                    gift_cand = (act.get("item_name") or parsed_intent.sub_target or parsed_intent.metadata.get("item_name", "") or "").strip()
                    if gift_cand and gift_cand.lower() not in ("gift", "present"):
                        for inv_it in actor_inv:
                            it_name = str(inv_it.get("name", "")).strip()
                            if it_name and (gift_cand.lower() in it_name.lower() or it_name.lower() in gift_cand.lower()):
                                target_recipient = (
                                    parsed_intent.target_entity
                                    or act.get("target_npc")
                                    or (session.get("dialogue_partner") if isinstance(session, dict) else None)
                                    or "NPC"
                                )
                                gifted_items.append({
                                    "user_id": actor_uid,
                                    "npc_name": target_recipient,
                                    "item_name": it_name,
                                })
                                stage_directives.append(
                                    f"[STAGE DIRECTION — GIFT PRESENTED]: {char_name} gifted '{it_name}' from their inventory to {target_recipient}. Narrate {target_recipient} receiving and reacting to '{it_name}'."
                                )
                                break
                elif parsed_intent.category == IntentCategory.MEDIA_CAPTURE and scenario_has_smartphone(scen_key):
                    media_type = parsed_intent.metadata.get("media_type", "photo")
                    subject = (
                        parsed_intent.target_entity
                        or act.get("target_npc")
                        or (session.get("dialogue_partner") if isinstance(session, dict) else None)
                        or "Scene"
                    )
                    media_captured.append({
                        "user_id": actor_uid,
                        "media_type": media_type,
                        "subject": subject,
                        "location": session.get("current_location", "Local Area") if isinstance(session, dict) else "Local Area",
                    })
                    stage_directives.append(
                        f"[STAGE DIRECTION — MEDIA CAPTURED]: {char_name} captured a {media_type} of {subject} on their smartphone (saved to Photo Vault). Narrate taking the {media_type}."
                    )
            except Exception:
                pass

        # 4. Non-Combat Physical Hazard Damage on Failed STR/AGI/END Checks
        if (
            not succeeded
            and not is_non_combat_scen
            and not is_social_act
            and stat in ("STR", "AGI", "END")
            and tier in ("fail", "failure", "crit_fail", "critical_failure")
        ):
            pct = 0.10 if "crit" in tier else 0.05
            dmg = max(1, min(25, int(round(max_hp * pct))))
            a_st["hp_delta"] -= dmg
            a_st["authorized_hazard_dmg"] -= dmg
            stage_directives.append(
                f"[STAGE DIRECTION — HAZARD CONSEQUENCE]: {char_name} suffered -{dmg} HP from the failed {stat} attempt. "
                f"Narrate the physical scrape or strain."
            )

        # 5. Deterministic Consumable Usage (D3 Atomic Staging when persist_db=False)
        is_consumable_act = (
            stat == "ITEM"
            or intent in ("use_item", "consumable")
            or sub_intent_act in ("use_item", "consumable")
            or any(kw in lbl_low for kw in ("drink potion", "use potion", "consume potion", "take potion", "drink mana", "use healing", "drink elixir"))
        )
        if is_consumable_act and actor_inv:
            cand_name = (
                (act.get("item") or {}).get("name")
                or act.get("item_name")
                or ""
            )
            if not cand_name:
                m_use = re.search(r"^(?:Use|Drink|Consume|Eat)\s+(.+?)(?:\s+on|\s+at|$)", lbl, re.IGNORECASE)
                if m_use:
                    cand_name = m_use.group(1).strip()
                else:
                    cand_name = lbl.strip()

            matched_item = None
            cand_clean = cand_name.lower().strip()
            for inv_it in actor_inv:
                inv_n = str(inv_it.get("name", "")).strip().lower()
                if cand_clean and (cand_clean in inv_n or inv_n in cand_clean):
                    matched_item = inv_it
                    break

            if matched_item:
                target_char = acting_char
                recip_uid = actor_uid
                target_uid_spec = act.get("target_user_id")
                target_name_spec = str(act.get("target_character") or act.get("target_npc") or "").strip().lower()
                if target_uid_spec:
                    for pc in party_chars:
                        if pc.get("user_id") == target_uid_spec:
                            target_char = pc
                            recip_uid = int(target_uid_spec)
                            break
                elif target_name_spec:
                    for pc in party_chars:
                        if str(pc.get("name", "")).strip().lower() == target_name_spec:
                            target_char = pc
                            recip_uid = int(pc.get("user_id") or actor_uid)
                            break

                _, recip_st = _ensure_actor_state(target_char)
                recip_hp = int(target_char.get("hp", 0) or 0) + recip_st["consumable_hp_gain"]
                recip_max_hp = max(1, int(target_char.get("max_hp", 100) or 100))
                recip_mp = int(target_char.get("mp", 0) or 0) + recip_st["consumable_mp_gain"]
                recip_max_mp = max(1, int(target_char.get("max_mp", 50) or 50))

                from mechanics.combat.items.consumables import parse_item_effect
                parsed_eff = parse_item_effect(matched_item) if isinstance(matched_item, dict) else {}
                hp_rest = int(parsed_eff.get("hp_restore", 0) or 0)
                mp_rest = int(parsed_eff.get("mp_restore", 0) or 0)

                raw_eff = str(matched_item.get("effect", "") or "")
                if hp_rest == 0:
                    m_hp = re.search(r'(?:heal|restor(?:e|es)|\+)\s*(\d+)\s*hp', raw_eff, re.I)
                    if m_hp:
                        hp_rest = int(m_hp.group(1))
                if mp_rest == 0:
                    m_mp = re.search(r'(?:restor(?:e|es)|\+)\s*(\d+)\s*mp', raw_eff, re.I)
                    if m_mp:
                        mp_rest = int(m_mp.group(1))

                if hp_rest == 0 and mp_rest == 0:
                    it_low = matched_item.get("name", "").lower()
                    if any(k in it_low for k in ("health", "healing", "heal", "salve", "potion")):
                        hp_rest = 35
                    elif any(k in it_low for k in ("mana", "magic", "ether")):
                        mp_rest = 20

                is_hp_full = recip_hp >= recip_max_hp
                is_mp_full = recip_mp >= recip_max_mp

                wasted = False
                if hp_rest > 0 and mp_rest == 0 and is_hp_full:
                    wasted = True
                elif mp_rest > 0 and hp_rest == 0 and is_mp_full:
                    wasted = True
                elif hp_rest > 0 and mp_rest > 0 and is_hp_full and is_mp_full:
                    wasted = True

                if wasted:
                    stage_directives.append(
                        f"[STAGE DIRECTION — ITEM UNUSED]: {char_name} reached for '{matched_item['name']}', but {target_char.get('name', 'their')} vitals are already full. Item was not consumed."
                    )
                else:
                    it_id = matched_item.get("id")
                    try:
                        actor_inv.remove(matched_item)
                    except ValueError:
                        pass
                    a_st["items_lost"].append(matched_item["name"])
                    all_items_lost.append(matched_item["name"])
                    consumed_items.append({
                        "user_id": recip_uid,
                        "actor_user_id": actor_uid,
                        "item_id": it_id,
                        "item_name": matched_item["name"],
                        "hp_restore": hp_rest,
                        "mp_restore": mp_rest,
                        "_persisted_in_db": bool(persist_db),
                    })
                    recip_st["hp_delta"] += hp_rest
                    recip_st["mp_delta"] += mp_rest
                    recip_st["consumable_hp_gain"] += hp_rest
                    recip_st["consumable_mp_gain"] += mp_rest
                    if persist_db:
                        if it_id:
                            db.remove_item(actor_uid, it_id)
                        else:
                            db.remove_item_by_name(actor_uid, matched_item["name"])
                        if hp_rest > 0 or mp_rest > 0:
                            db.apply_hp_mp_delta(recip_uid, hp_delta=hp_rest, mp_delta=mp_rest)
                    else:
                        staged_consumable_removals.append({
                            "user_id": actor_uid,
                            "item_id": it_id,
                            "item_name": matched_item["name"],
                        })
                    stage_directives.append(
                        f"[STAGE DIRECTION — ITEM CONSUMED]: {char_name} consumed '{matched_item['name']}' (+{hp_rest} HP, +{mp_rest} MP). Narrate using this item."
                    )

        # 6. Deterministic Pickpocketing & Theft (D3, D17)
        if sub_intent_act == "pickpocket" or (not is_social_act and any(kw in lbl_low for kw in ("pickpocket", "pick pocket", "steal from", "lift purse", "steal coin"))):
            target_npc = str(act.get("target_npc") or (session.get("dialogue_partner") if isinstance(session, dict) else None) or "target").strip()
            phys_st = (session.get("physical_state") if isinstance(session, dict) else None) or (
                db.get_session_physical_state(session_id) if session_id else None
            ) or {}
            pockets_emptied = phys_st.setdefault("pockets_emptied", [])
            target_clean = target_npc.lower().strip()

            if target_clean in [p.lower().strip() for p in pockets_emptied]:
                stage_directives.append(
                    f"[STAGE DIRECTION — PICKPOCKET FAILED]: {target_npc}'s pockets are already empty. No gold found."
                )
            elif succeeded:
                is_noble_or_merchant = any(kw in target_clean for kw in ("noble", "merchant", "shopkeeper", "aristocrat", "lord", "lady", "official", "guildmaster", "wealthy", "banker"))
                luk_stat = int(acting_char.get("luk_", 10) or 10)
                luk_bonus = max(0, (luk_stat - 10) * 2)

                if is_noble_or_merchant:
                    base_gold = random.randint(50, 100)
                else:
                    base_gold = random.randint(10, 25)
                bounty = base_gold + luk_bonus

                a_st["gold_delta"] += bounty
                a_st["authorized_gold_gain"] += bounty
                pockets_emptied.append(target_npc)
                if isinstance(session, dict):
                    session["physical_state"] = phys_st
                    if persist_db and session_id:
                        try:
                            db.update_session_physical_state(session_id, phys_st)
                        except Exception:
                            pass
                    else:
                        staged_physical_state_dirty = True
                stage_directives.append(
                    f"[STAGE DIRECTION — PICKPOCKET SUCCESS]: {char_name} pickpocketed {bounty} Gold from {target_npc}."
                )
            else:
                if persist_db and session_id and target_npc:
                    try:
                        db.update_relationship_score(session_id, target_npc, delta_score=-15)
                    except Exception:
                        pass
                elif session_id and target_npc:
                    staged_pickpocket_penalties.append({"npc_name": target_npc, "delta_score": -15})
                stage_directives.append(
                    f"[STAGE DIRECTION — PICKPOCKET CAUGHT]: {target_npc} caught {char_name} red-handed! (-15 Affinity). Guards are alerted."
                )

    outcomes: list[dict] = []
    total_hp_delta = 0
    total_gold_delta = 0
    authorized_gold_spend_by_user: dict[int, int] = {}
    authorized_gold_gain_by_user: dict[int, int] = {}
    authorized_hazard_dmg_by_user: dict[int, int] = {}
    consumable_hp_by_user: dict[int, int] = {}
    consumable_mp_by_user: dict[int, int] = {}

    for a_uid, st in actor_states.items():
        total_hp_delta += st["hp_delta"]
        total_gold_delta += st["gold_delta"]
        if st["authorized_gold_spend"] > 0:
            authorized_gold_spend_by_user[a_uid] = st["authorized_gold_spend"]
        if st["authorized_gold_gain"] > 0:
            authorized_gold_gain_by_user[a_uid] = st["authorized_gold_gain"]
        if st["authorized_hazard_dmg"] < 0:
            authorized_hazard_dmg_by_user[a_uid] = st["authorized_hazard_dmg"]
        if st["consumable_hp_gain"] > 0:
            consumable_hp_by_user[a_uid] = st["consumable_hp_gain"]
        if st["consumable_mp_gain"] > 0:
            consumable_mp_by_user[a_uid] = st["consumable_mp_gain"]
        if (
            st["hp_delta"] != 0
            or st["mp_delta"] != 0
            or st["gold_delta"] != 0
            or st["items_gained"]
            or st["items_lost"]
            or st["status_effects"]
        ):
            outcomes.append({
                "name": st["name"],
                "hp_change": st["hp_delta"],
                "mp_change": st["mp_delta"],
                "gold_change": st["gold_delta"],
                "items_gained": list(st["items_gained"]),
                "items_lost": list(st["items_lost"]),
                "status_effects": list(st["status_effects"]),
            })

    return {
        "character_outcomes": outcomes,
        "stage_directives": stage_directives,
        "loot_items_rolled": all_items_gained,
        "gifted_items": gifted_items,
        "media_captured": media_captured,
        "consumed_items": consumed_items,
        "staged_consumable_removals": staged_consumable_removals,
        "staged_pickpocket_penalties": staged_pickpocket_penalties,
        "staged_physical_state": (session.get("physical_state") if staged_physical_state_dirty and isinstance(session, dict) else None),
        "authorized_gold_spend_by_user": authorized_gold_spend_by_user,
        "authorized_gold_gain_by_user": authorized_gold_gain_by_user,
        "authorized_hazard_dmg_by_user": authorized_hazard_dmg_by_user,
        "consumable_hp_by_user": consumable_hp_by_user,
        "consumable_mp_by_user": consumable_mp_by_user,
        "_persisted_pre_turn": bool(persist_db),
        "items_lost": all_items_lost,
        "gold_delta": total_gold_delta,
        "hp_delta": total_hp_delta,
    }


def apply_outcome(session_id: int, party: list, outcome, mp_already_spent: dict | None = None,
                  actions: list | None = None) -> dict:
    """Returns {user_id: [item_name, ...]} -- every item each character gained
    this turn, in the order the LLM listed them (duplicates preserved, so a
    caller can count "(xN)" for multiple copies of the same item). A user
    with no gains this turn is simply absent from the dict. This is purely
    additive: existing callers that ignore the return value are unaffected.
    """
    # Coerce Pydantic model to dict so all downstream .get() / [] calls work
    if getattr(outcome, "model_dump", None):
        outcome = outcome.model_dump(exclude_unset=False)
    if mp_already_spent is None:
        mp_already_spent = {}
    if actions is None:
        actions = []

    with db.UnitOfWork():
        party_uids = [char["user_id"] for char, _ in party]
        session = db.get_session(session_id)

        # ── D3 Atomic Commit Step 1: Staged Spatial Graph Unlocks & Key Items ──
        if isinstance(outcome, dict) and isinstance(outcome.get("_staged_spatial_mutations"), dict):
            sp_mut = outcome["_staged_spatial_mutations"]
            try:
                from mechanics.world.locations.access_gate import record_node_unlock
                for v_nid in (sp_mut.get("unlocked_nodes") or []):
                    if v_nid:
                        record_node_unlock(session_id, str(v_nid))
            except Exception as _sp_e:
                log.warning("Failed committing staged unlocked_nodes: %s", _sp_e)
            try:
                unlocked_edges = sp_mut.get("unlocked_edges") or []
                if unlocked_edges:
                    with db.get_conn() as conn:
                        for edge_pair in unlocked_edges:
                            if isinstance(edge_pair, (tuple, list)) and len(edge_pair) == 2:
                                u_n, v_n = edge_pair
                                conn.execute(
                                    "UPDATE world_edges SET is_locked = 0 WHERE session_id = ? AND ((from_node_id = ? AND to_node_id = ?) OR (from_node_id = ? AND to_node_id = ? AND is_bidirectional = 1))",
                                    (session_id, u_n, v_n, v_n, u_n),
                                )
            except Exception as _ed_e:
                log.warning("Failed committing staged unlocked_edges: %s", _ed_e)
            for k_it in (sp_mut.get("consumed_key_items") or []):
                if isinstance(k_it, dict) and k_it.get("user_id"):
                    try:
                        if k_it.get("item_id"):
                            db.remove_item(int(k_it["user_id"]), int(k_it["item_id"]))
                        elif k_it.get("name"):
                            db.remove_item_by_name(int(k_it["user_id"]), str(k_it["name"]))
                    except Exception:
                        pass

        # ── D3 Atomic Commit Step 2: Staged Clock / Sleep / Nap Progression ────
        if isinstance(outcome, dict) and isinstance(outcome.get("_staged_time_op"), dict) and session_id:
            t_op = outcome["_staged_time_op"]
            op_kind = str(t_op.get("op") or "")
            t_uids = list(t_op.get("party_uids") or party_uids)
            try:
                from mechanics.system.time_engine import apply_sleep_rest, apply_nap_rest, advance_time
                def _merge_time_fields_from_db(include_npcs: bool = False):
                    fresh_s = db.get_session(session_id)
                    if isinstance(fresh_s, dict) and isinstance(session, dict):
                        for _tk in ("current_day", "current_minute", "consecutive_days_awake", "physical_state"):
                            if _tk in fresh_s:
                                session[_tk] = fresh_s[_tk]
                        if include_npcs and "current_npcs" in fresh_s:
                            session["current_npcs"] = fresh_s["current_npcs"]

                if op_kind == "sleep":
                    sl_info = apply_sleep_rest(
                        session_id,
                        t_uids,
                        scen_key=str(t_op.get("scen_key") or (session.get("scenario", "fantasy") if session else "fantasy")),
                        recovery_ratio=float(t_op.get("recovery_ratio", 1.0)),
                        surface_label=str(t_op.get("surface_label") or "Bed"),
                    )
                    outcome["_sleep_info"] = sl_info
                    if isinstance(sl_info.get("morning_npcs"), list):
                        outcome["npcs_present"] = sl_info["morning_npcs"]
                    _merge_time_fields_from_db(include_npcs=True)
                    party = [(db.get_character(c["user_id"]) or c, inv) for c, inv in party]
                elif op_kind == "nap":
                    np_info = apply_nap_rest(
                        session_id,
                        t_uids,
                        nap_minutes=int(t_op.get("nap_minutes", 120) or 120),
                        recovery_ratio=float(t_op.get("recovery_ratio", 1.0)),
                        surface_label=str(t_op.get("surface_label") or "Bed"),
                    )
                    outcome["_sleep_info"] = np_info
                    _merge_time_fields_from_db(include_npcs=False)
                    party = [(db.get_character(c["user_id"]) or c, inv) for c, inv in party]
                elif op_kind == "advance":
                    tm_info = advance_time(
                        session_id,
                        int(t_op.get("delta_minutes", 0) or 0),
                        party_uids=t_uids,
                    )
                    outcome["_time_info"] = tm_info
                    _merge_time_fields_from_db(include_npcs=False)
            except Exception as _tm_e:
                log.warning("Failed committing staged time op (%s): %s", op_kind, _tm_e)

        # ── D3 Atomic Commit Step 3: Staged Rendezvous & Cast State ────────────
        if isinstance(outcome, dict) and outcome.get("_completed_appointment_npc_ids") and session_id:
            for appt_npc_id in (outcome.get("_completed_appointment_npc_ids") or []):
                if appt_npc_id:
                    try:
                        db.update_phone_appointment_status(session_id, str(appt_npc_id), "completed")
                    except Exception:
                        pass
        if isinstance(outcome, dict) and isinstance(outcome.get("_staged_cast_state"), dict) and isinstance(session, dict):
            try:
                from game_engine.npcs.cast_planner import save_cast_state
                save_cast_state(session, outcome["_staged_cast_state"], persist_db=True)
            except Exception as _cs_e:
                log.warning("Failed committing staged cast_state: %s", _cs_e)

        scen_key_curr = session.get("scenario", "fantasy") if session else "fantasy"
        game_engine._sanitize_outcome_person_names(outcome, session_id, scen_key_curr)

        items_gained_by_user: dict = {}
        _reduce_quests_and_waypoints(session_id, session, party_uids, outcome, actions, items_gained_by_user)
        scen_key = session.get("scenario", "fantasy") if session else "fantasy"

        is_combat = bool(outcome and (outcome.get("_combat_log") or outcome.get("_enemy_attack_notice") or game_engine.get_active_enemies(outcome)))
        first_char_id = party[0][0]["id"] if party else 0
        first_char_name = party[0][0].get("name", "Player") if party else "Player"
        _reduce_vitals_and_inventory(session_id, session, party, outcome, mp_already_spent, scen_key, is_combat, items_gained_by_user, actions=actions)

        # ── 0-HP Recovery: Anomalous Extraction OR D8 Non-Combat Hazard Knockout ──
        try:
            import scenario_data
            if scenario_data.is_anomalous_incursions_scenario(scen_key) and party_uids and not (isinstance(outcome, dict) and outcome.get("_anomalous_extracted")):
                lead_uid = party_uids[0]
                fresh_char = db.get_character(lead_uid)
                if fresh_char and int(fresh_char.get("hp", 1) or 0) <= 0:
                    from mechanics.world.anomalous_events import resolve_anomalous_emergency_extraction
                    ext_res = resolve_anomalous_emergency_extraction(session_id, lead_uid)
                    for extra_uid in party_uids[1:]:
                        p_ch = db.get_character(extra_uid)
                        if p_ch and int(p_ch.get("hp", 1) or 0) <= 0:
                            t_hp = max(1, int(p_ch.get("max_hp", 20) or 20) // 2)
                            t_mp = max(1, int(p_ch.get("max_mp", 10) or 10) // 2)
                            db.apply_hp_mp_delta(
                                extra_uid,
                                hp_delta=max(0, t_hp - int(p_ch.get("hp", 0) or 0)),
                                mp_delta=max(0, t_mp - int(p_ch.get("mp", 0) or 0)),
                            )
                    if ext_res.get("extracted") and isinstance(outcome, dict):
                        outcome["_anomalous_extracted"] = True
                        outcome["location"] = ext_res["destination_location"]
                        outcome["current_node_id"] = ext_res["destination_node_id"]
                        outcome["focal_point"] = None
                        outcome["nearby_enemies"] = []
                        ext_note = ext_res.get("narrative", "")
                        if ext_note:
                            outcome["outcome_narrative"] = f"{outcome.get('outcome_narrative', '')}\n\n{ext_note}".strip()
                        rec_choices = [
                            {"label": "Check medical telemetry and stabilize your psychic resonance", "stat": "END", "requirement": 4, "mp_cost": 0, "_server_stamped": True},
                            {"label": "Review field logs and inspect your tactical loadout", "stat": "PER", "requirement": 4, "mp_cost": 0, "_server_stamped": True},
                            {"label": "Debrief with triage staff before redeploying to the breach", "stat": "CHA", "requirement": 4, "mp_cost": 0, "_server_stamped": True},
                        ]
                        outcome.pop("_hybrid_choices_built", None)
                        outcome["choices"] = rec_choices
                        outcome["next_choices"] = rec_choices
                        session = db.get_session(session_id) or session
            elif (
                not is_combat
                and not scenario_data.is_non_combat_scenario(scen_key)
                and party_uids
                and isinstance(outcome, dict)
                and not outcome.get("_party_defeated_notice")
            ):
                downed_chars = []
                for p_uid in party_uids:
                    f_ch = db.get_character(p_uid)
                    if f_ch and int(f_ch.get("hp", 1) or 0) <= 0:
                        downed_chars.append(f_ch)
                if downed_chars:
                    for d_ch in downed_chars:
                        d_uid = d_ch["user_id"]
                        d_max_hp = max(1, int(d_ch.get("max_hp", 30) or 30))
                        revive_hp = max(1, d_max_hp // 2)
                        cur_hp = int(d_ch.get("hp", 0) or 0)
                        db.apply_hp_mp_delta(d_uid, hp_delta=max(1, revive_hp - cur_hp))
                        cur_effs = db.get_status_effects(d_uid)
                        if "Exhausted / Recovering" not in cur_effs:
                            cur_effs.append("Exhausted / Recovering")
                        db.set_status_effects(d_uid, cur_effs)
                    if session_id:
                        from mechanics.system.time_engine import advance_time
                        ko_time = advance_time(session_id, 60, party_uids=party_uids)
                        outcome["_time_info"] = ko_time
                        session = db.get_session(session_id) or session
                    outcome["_party_defeated_notice"] = (
                        "💀 **Knocked Out!** Overwhelmed by severe physical hazards, you collapsed unconscious—awakening an hour later, battered and stabilized."
                    )
                    ko_choices = [
                        {"label": "Rest and recuperate from your injuries", "stat": "END", "requirement": 4, "mp_cost": 0, "_server_stamped": True},
                        {"label": "Assess your surroundings and check equipment", "stat": "PER", "requirement": 4, "mp_cost": 0, "_server_stamped": True},
                        {"label": "Consult with companions about what happened", "stat": "CHA", "requirement": 4, "mp_cost": 0, "_server_stamped": True},
                    ]
                    outcome.pop("_hybrid_choices_built", None)
                    outcome["choices"] = ko_choices
                    outcome["next_choices"] = ko_choices
        except Exception as e:
            log.warning("Failed 0-HP recovery check: %s", e)

        _reduce_media_capture(session_id, session, party, outcome, actions, scen_key, items_gained_by_user)
        _reduce_entities_and_gifts(session_id, session, outcome, party, actions, is_combat, scen_key)
        _reduce_social_and_milestones(session_id, session, party, outcome, actions, scen_key, items_gained_by_user, first_char_id, first_char_name)
        _reduce_factions(session_id, session, outcome, party, first_char_id)

        _reduce_deterministic_waypoints(session_id, session, outcome, party_uids, actions)
        _reduce_physical_state_and_memories(session_id, session, outcome, party, scen_key, actions)

        # ── D16 Atomic Commit: Stealth Persistence, Spatial Reset & 100% Escalation ──
        try:
            from mechanics.stealth import reduce_stealth_turn_outcome
            reduce_stealth_turn_outcome(session_id, session, party, outcome, actions, scen_key, is_combat)
        except Exception as _st_e:
            log.warning("Failed reducing stealth turn outcome: %s", _st_e)

        # ── D3 Atomic Commit Step 4: Staged Scene Residue ──────────────────────
        if isinstance(outcome, dict) and isinstance(outcome.get("_staged_scene_residue"), dict) and session_id:
            sr_info = outcome["_staged_scene_residue"]
            if sr_info.get("node_id"):
                try:
                    from mechanics.world.locations.access_gate import record_turn_scene_residue
                    record_turn_scene_residue(
                        session_id,
                        str(sr_info["node_id"]),
                        session or {},
                        outcome,
                        actions,
                        unlocked_by=str(sr_info.get("unlocked_by") or ""),
                    )
                except Exception as _sr_e:
                    log.warning("Failed recording turn scene residue: %s", _sr_e)
    # ── Background Digest Trigger ────────────────────────────────────────────
    # Schedule a non-blocking arc digest if an arc boundary was crossed this
    # turn (zone travel, dialogue exit, sub-quest completion, or history full).
    # This runs AFTER all DB writes so the digest captures a fully-committed state.
    try:
        session_for_digest = db.get_session(session_id)
        if session_for_digest:
            from mechanics.system.memory.digest import fire_digest_if_needed
            fire_digest_if_needed(
                session=session_for_digest,
                actions=actions or [],
                outcome=outcome,
                history_to_archive=session_for_digest.get("history") or [],
            )
    except Exception:
        pass  # digest is best-effort - never block the turn response

    return items_gained_by_user

def push_history(history: list, entry: str, limit: int | None = None) -> list:
    """
    Appends a new turn narrative to the session history.
    The default limit is RAW_HISTORY_LIMIT (4) from mechanics.system.memory.digest.
    """
    from mechanics.system.memory.digest import RAW_HISTORY_LIMIT
    import game_engine
    
    if limit is None:
        limit = RAW_HISTORY_LIMIT
        
    # Anti-cliche filtering
    if hasattr(game_engine, 'sanitize_comparative_cliches'):
        entry = game_engine.sanitize_comparative_cliches(entry)
    
    # De-echoing: don't push identical back-to-back entries
    if history and history[-1] == entry:
        return history
        
    new_hist = history + [entry]
    if len(new_hist) > limit:
        new_hist = new_hist[-limit:]
    return new_hist



from .reducers import _evaluate_npc_milestones, _reduce_quests_and_waypoints, _reduce_vitals_and_inventory, _reduce_factions, _reduce_deterministic_waypoints, _reduce_physical_state_and_memories, _reduce_entities_and_gifts, _reduce_media_capture
from .social import _reduce_social_and_milestones
