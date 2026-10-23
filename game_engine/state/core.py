from .constants import *
from .constants import _GOLD_GAIN_RE, _GOLD_LOSS_RE, _MAX_GOLD_LEAKAGE_PATCH, _DAMAGE_RE, _ITEM_GRANT_RE, _ITEM_BLOCKLIST
import db
import re
import json
import random
import logging
from config import LLM_PASS1_TIMEOUT
from scenario_data import is_nsfw_scenario, uses_nsfw_model
from game_engine.core import STATE_ARBITER_SCHEMA
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

    if has_exited:
        # Player explicitly exited the conversation: strictly clear dialogue partner
        partner_arg = None
    elif (not partner_arg or partner_arg == "__NOOP__") and npcs_arg:
        try:
            party_arg = session.get("party") if isinstance(session, dict) else None
            p_name = session.get("player_character", {}).get("name") if isinstance(session, dict) and isinstance(session.get("player_character"), dict) else None
            combined_nar = (
                str(data.get("outcome_narrative") or "") + "\n" +
                str(next_narrative or "") + "\n" +
                str(data.get("narrative") or "")
            ).strip()
            if combined_nar:
                spk = game_engine.extract_speaking_npcs_from_narrative(
                    combined_nar, npcs_arg, party=party_arg, player_name=p_name
                )
                if spk:
                    partner_arg = spk[0] if len(spk) == 1 else spk
        except Exception:
            pass

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
) -> dict:
    """
    Deterministic Pre-Turn Vitals, Gold Spending, and Procedural Loot Engine.
    Executes before calling the Narrator LLM so all resource mutations are locked in Python:
      1. Deducts ActionCommand.gold_spent on successful check.
      2. Rolls procedural loot from mechanics/combat/items/ when ActionCommand.triggers_loot_roll succeeds.
      3. Applies bounded non-combat hazard HP loss (5% on fail, 10% on crit_fail) on failed physical checks
         in combat-capable scenarios.
    Returns:
      {
        "character_outcomes": list[dict],
        "stage_directives": list[str],
        "loot_items_rolled": list[str],
      }
    """
    import scenario_data
    from mechanics.combat import is_in_combat

    if not actions:
        return {"character_outcomes": [], "stage_directives": [], "loot_items_rolled": []}

    if is_in_combat(session):
        return {"character_outcomes": [], "stage_directives": [], "loot_items_rolled": []}

    party_chars = []
    for p in (party or []):
        char = p[0] if isinstance(p, (tuple, list)) else p
        if isinstance(char, dict):
            party_chars.append(char)
    if not party_chars:
        return {"character_outcomes": [], "stage_directives": [], "loot_items_rolled": []}

    acting_char = party_chars[0]
    char_name = acting_char.get("name", "Hero")
    char_level = int(acting_char.get("level", 1) or 1)
    char_gold = int(acting_char.get("gold", 0) or 0)
    max_hp = max(1, int(acting_char.get("max_hp", 100) or 100))
    scen_key = session.get("scenario", "fantasy") if isinstance(session, dict) else "fantasy"
    is_non_combat_scen = scenario_data.is_non_combat_scenario(scen_key)

    hp_delta = 0
    gold_delta = 0
    items_gained: list[str] = []
    items_lost: list[str] = []
    gifted_items: list[dict] = []
    media_captured: list[dict] = []
    consumed_items: list[dict] = []
    status_effects: list[str] = []
    stage_directives: list[str] = []

    session_id = session.get("id") if isinstance(session, dict) else 0
    user_id = acting_char.get("user_id") or 0
    party_inv = (
        party[0][1]
        if (party and isinstance(party[0], (tuple, list)) and len(party[0]) > 1 and isinstance(party[0][1], list))
        else (db.get_inventory(user_id) if user_id else [])
    ) or []

    from mechanics.social.intimate_excitement import is_intimate_action_label
    from mechanics.narrative.intent import classify_action_intent, IntentCategory, IntentContext
    from mechanics.system.phone import scenario_has_smartphone

    for act in actions:
        if not isinstance(act, dict):
            continue
        chk = act.get("check")
        succeeded = is_check_success(chk, default_if_none=True)
        tier = str(
            getattr(chk, "tier", None)
            or (chk.get("tier") if isinstance(chk, dict) else None)
            or ("success" if succeeded else "fail")
        ).lower()
        stat = str(act.get("stat") or "NONE").upper()
        intent = str(act.get("intent") or act.get("action_category") or "").lower()
        lbl = str(act.get("label") or act.get("action") or "")
        lbl_low = lbl.lower()

        is_social_act = (
            intent in ("dialogue", "disclosure_inquiry", "affection", "social_invite", "romantic_confession", "party_recruit", "social", "intimate")
            or stat == "CHA"
            or is_intimate_action_label(lbl)
        )

        # 1. Gold Spending
        raw_gold_spent = int(act.get("gold_spent") or 0)
        if raw_gold_spent > 0 and succeeded:
            actual_spend = min(char_gold, raw_gold_spent) if char_gold > 0 else raw_gold_spent
            if actual_spend > 0:
                if not act.get("_gold_already_deducted"):
                    gold_delta -= actual_spend
                    act["_gold_already_deducted"] = True
                stage_directives.append(
                    f"[STAGE DIRECTION — GOLD TRANSACTION]: {char_name} spent {actual_spend} Gold."
                )
        if act.get("_gold_shortfall_note"):
            stage_directives.append(str(act["_gold_shortfall_note"]))

        # 2. Procedural Loot Roll OR Scene Prop / Foraging Pickup
        if bool(act.get("triggers_loot_roll")) and succeeded and not is_social_act:
            try:
                from mechanics.combat.items.consumables.generators import generate_random_consumable
                rolled_item = generate_random_consumable(scenario=scen_key, party_level=char_level)
                item_str = rolled_item.get("formatted_string") or rolled_item.get("name")
                item_display = rolled_item.get("name") or "Supply Cache"
                if item_str:
                    items_gained.append(item_str)
                    stage_directives.append(
                        f"[STAGE DIRECTION — LOOT DISCOVERED]: {char_name}'s search succeeded and uncovered '{item_display}'. "
                        f"Narrate finding '{item_display}' in `outcome_narrative`."
                    )
            except Exception:
                pass
        elif succeeded and not is_social_act and any(
            kw in lbl_low for kw in ("pick up", "take the", "grab the", "collect the", "gather ", "forage ", "harvest ")
        ):
            # Check if picking up a tracked scene prop or dropped item
            phys_st = (session.get("physical_state") if isinstance(session, dict) else None) or (
                db.get_session_physical_state(session_id) if session_id else None
            ) or {}
            props_map = phys_st.get("props") if isinstance(phys_st, dict) else {}
            dropped_list = phys_st.get("dropped_items") if isinstance(phys_st, dict) else []
            matched_prop = None
            if isinstance(props_map, dict):
                for pk in list(props_map.keys()):
                    if pk and pk.lower() in lbl_low:
                        matched_prop = pk
                        props_map.pop(pk, None)
                        break
            if not matched_prop and isinstance(dropped_list, list):
                for di in list(dropped_list):
                    if di and str(di).lower() in lbl_low:
                        matched_prop = str(di)
                        dropped_list.remove(di)
                        break
            if matched_prop and matched_prop not in items_gained:
                items_gained.append(matched_prop)
                if isinstance(session, dict) and isinstance(phys_st, dict):
                    session["physical_state"] = phys_st
                    if session_id:
                        try:
                            db.update_session_physical_state(session_id, phys_st)
                        except Exception:
                            pass
                stage_directives.append(
                    f"[STAGE DIRECTION — ITEM ACQUIRED]: {char_name} picked up '{matched_prop}'. Narrate acquiring it."
                )
            elif any(kw in lbl_low for kw in ("forage ", "harvest ")) and not items_gained:
                try:
                    from mechanics.combat.items.consumables.generators import generate_random_consumable
                    rolled_item = generate_random_consumable(scenario=scen_key, party_level=char_level)
                    item_display = rolled_item.get("name") or "Foraged Supplies"
                    if item_display:
                        items_gained.append(item_display)
                        stage_directives.append(
                            f"[STAGE DIRECTION — FORAGING SUCCESS]: {char_name} foraged '{item_display}'. Narrate gathering it."
                        )
                except Exception:
                    pass

        # 3. Pre-Turn Gift Offer Validation & Consumption
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
                if parsed_intent.category == IntentCategory.GIFT_OFFER and party_inv:
                    gift_cand = (parsed_intent.sub_target or parsed_intent.metadata.get("item_name", "") or "").strip()
                    if gift_cand and gift_cand.lower() not in ("gift", "present"):
                        for inv_it in party_inv:
                            it_name = str(inv_it.get("name", "")).strip()
                            if it_name and (gift_cand.lower() in it_name.lower() or it_name.lower() in gift_cand.lower()):
                                target_recipient = (
                                    parsed_intent.target_entity
                                    or act.get("target_npc")
                                    or (session.get("dialogue_partner") if isinstance(session, dict) else None)
                                    or "NPC"
                                )
                                gifted_items.append({
                                    "user_id": user_id,
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
                        "user_id": user_id,
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
            hp_delta -= dmg
            stage_directives.append(
                f"[STAGE DIRECTION — HAZARD CONSEQUENCE]: {char_name} suffered -{dmg} HP from the failed {stat} attempt. "
                f"Narrate the physical scrape or strain."
            )

        # 5. Deterministic Consumable Usage (Decision A1, A7)
        is_consumable_act = (
            stat == "ITEM"
            or intent in ("use_item", "consumable")
            or act.get("sub_intent") in ("use_item", "consumable")
            or any(kw in lbl_low for kw in ("drink potion", "use potion", "consume potion", "take potion", "drink mana", "use healing", "drink elixir"))
        )
        if is_consumable_act and party_inv:
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
            for inv_it in party_inv:
                inv_n = str(inv_it.get("name", "")).strip().lower()
                if cand_clean and (cand_clean in inv_n or inv_n in cand_clean):
                    matched_item = inv_it
                    break

            if matched_item:
                target_char = acting_char
                recip_uid = user_id
                target_uid_spec = act.get("target_user_id")
                target_name_spec = str(act.get("target_character") or act.get("target_npc") or "").strip().lower()
                if target_uid_spec:
                    for pc in party_chars:
                        if pc.get("user_id") == target_uid_spec:
                            target_char = pc
                            recip_uid = target_uid_spec
                            break
                elif target_name_spec:
                    for pc in party_chars:
                        if str(pc.get("name", "")).strip().lower() == target_name_spec:
                            target_char = pc
                            recip_uid = pc.get("user_id", user_id)
                            break

                recip_hp = int(target_char.get("hp", 0) or 0)
                recip_max_hp = max(1, int(target_char.get("max_hp", 100) or 100))
                recip_mp = int(target_char.get("mp", 0) or 0)
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
                    if it_id:
                        db.remove_item(user_id, it_id)
                    else:
                        db.remove_item_by_name(user_id, matched_item["name"])
                    items_lost.append(matched_item["name"])
                    consumed_items.append({
                        "user_id": recip_uid,
                        "item_name": matched_item["name"],
                        "hp_restore": hp_rest,
                        "mp_restore": mp_rest,
                    })
                    if hp_rest > 0 or mp_rest > 0:
                        db.apply_hp_mp_delta(recip_uid, hp_delta=hp_rest, mp_delta=mp_rest)
                        if recip_uid == user_id:
                            hp_delta += hp_rest
                    stage_directives.append(
                        f"[STAGE DIRECTION — ITEM CONSUMED]: {char_name} consumed '{matched_item['name']}' (+{hp_rest} HP, +{mp_rest} MP). Narrate using this item."
                    )

        # 6. Deterministic Pickpocketing & Theft (Decision A2, A4)
        sub_intent_act = str(act.get("sub_intent") or "").lower()
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

                import random
                if is_noble_or_merchant:
                    base_gold = random.randint(50, 100)
                else:
                    base_gold = random.randint(10, 25)
                bounty = base_gold + luk_bonus

                gold_delta += bounty
                pockets_emptied.append(target_npc)
                if isinstance(session, dict):
                    session["physical_state"] = phys_st
                    if session_id:
                        try:
                            db.update_session_physical_state(session_id, phys_st)
                        except Exception:
                            pass
                stage_directives.append(
                    f"[STAGE DIRECTION — PICKPOCKET SUCCESS]: {char_name} pickpocketed {bounty} Gold from {target_npc}."
                )
            else:
                if session_id and target_npc:
                    try:
                        db.update_relationship_score(session_id, target_npc, delta_score=-15)
                    except Exception:
                        pass
                stage_directives.append(
                    f"[STAGE DIRECTION — PICKPOCKET CAUGHT]: {target_npc} caught {char_name} red-handed! (-15 Affinity). Guards are alerted."
                )

    outcomes = []
    if hp_delta != 0 or gold_delta != 0 or items_gained or items_lost or status_effects:
        outcomes.append({
            "name": char_name,
            "hp_change": hp_delta,
            "mp_change": 0,
            "gold_change": gold_delta,
            "items_gained": items_gained,
            "items_lost": items_lost,
            "status_effects": status_effects,
        })

    return {
        "character_outcomes": outcomes,
        "stage_directives": stage_directives,
        "loot_items_rolled": items_gained,
        "gifted_items": gifted_items,
        "media_captured": media_captured,
        "consumed_items": consumed_items,
        "items_lost": items_lost,
        "gold_delta": gold_delta,
        "hp_delta": hp_delta,
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
        scen_key_curr = session.get("scenario", "fantasy") if session else "fantasy"
        game_engine._sanitize_outcome_person_names(outcome, session_id, scen_key_curr)

        items_gained_by_user: dict = {}
        _reduce_quests_and_waypoints(session_id, session, party_uids, outcome, actions, items_gained_by_user)
        scen_key = session.get("scenario", "fantasy") if session else "fantasy"

        is_combat = bool(outcome and (outcome.get("_combat_log") or outcome.get("_enemy_attack_notice") or game_engine.get_active_enemies(outcome)))
        first_char_id = party[0][0]["id"] if party else 0
        first_char_name = party[0][0].get("name", "Player") if party else "Player"
        _reduce_vitals_and_inventory(session_id, session, party, outcome, mp_already_spent, scen_key, is_combat, items_gained_by_user, actions=actions)
        _reduce_media_capture(session_id, session, party, outcome, actions, scen_key, items_gained_by_user)
        _reduce_entities_and_gifts(session_id, session, outcome, party, actions, is_combat, scen_key)
        _reduce_social_and_milestones(session_id, session, party, outcome, actions, scen_key, items_gained_by_user, first_char_id, first_char_name)
        _reduce_factions(session_id, session, outcome, party, first_char_id)

        _reduce_deterministic_waypoints(session_id, session, outcome, party_uids, actions)
        _reduce_physical_state_and_memories(session_id, session, outcome, party, scen_key, actions)
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
