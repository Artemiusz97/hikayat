"""Active 1-on-1/group dialogue lock, intimate state blueprints, recruitment, and confession milestone stage."""
from __future__ import annotations

from typing import Any, Dict, List, Optional

import db
import game_engine
import namegen
import scenario_data
from game_engine.matching import matches_keyword_boundary
from mechanics.world.mobility import is_dialogue_partner as _is_dialogue_partner
from .inventory_rules import infer_choice_stat_and_dc, is_exempt_free_action
from .stems import _RECRUIT_CHOICE_KEYWORDS


def _hydrate_intimate_scene_state(
    *,
    partners_list: List[str],
    session_id: int | None,
    char: dict | None,
    raw_choices_empty: bool,
) -> dict[str, Any]:
    """Hydrate physical, excitement, refractory, and blueprint state for active dialogue/intimate partners."""
    from mechanics.social.intimate_excitement import (
        build_intimate_choice_blueprints,
        infer_last_act_from_state,
        is_in_refractory_cooldown,
    )
    from mechanics.social.physical_state import _match_actor_key, is_erotic_intimate_contact
    from mechanics.world.mobility import get_session_dialogue_partners

    is_active_intimate = False
    bp = None
    player_already_finished = False
    player_spent_and_finished = False
    partner_climaxed = False
    premature_finish = False
    partner_demanded = True
    in_refr_cooldown = False
    player_in_refr_cooldown = False
    last_act = "foreplay_nongenital"
    player_meter = 0
    partner_meter = 0
    player_posture = ""
    partner_posture = ""
    sensitive_spots = None
    partner_actors_list: List[Dict[str, Any]] = []
    partner_climaxes_map: Optional[Dict[str, bool]] = None
    contacts_list: List[Dict[str, Any]] = []
    ic_str = ""
    climax_st: Dict[str, Any] = {}
    phys_st = None
    primary_partner = partners_list[0] if partners_list else ""

    if partners_list:
        if session_id:
            try:
                phys_st = db.get_session_physical_state(session_id)
                sess = db.get_session(session_id) or {}
                if phys_st:
                    ic_str = str(phys_st.get("intimate_contact", "")).lower()
                    is_active_intimate = is_erotic_intimate_contact(ic_str)
                    climax_st = phys_st.get("climax_state", {}) or {}
                    raw_pc_map = (
                        climax_st.get("partner_climaxes") if isinstance(climax_st, dict) else None
                    )
                    partner_climaxes_map = (
                        dict(raw_pc_map) if isinstance(raw_pc_map, dict) else None
                    )
                    player_already_finished = bool(climax_st.get("player_climaxed", False))
                    player_spent_and_finished = (
                        player_already_finished and "hypersensitive ongoing" not in ic_str
                    )
                    partner_climaxed = (
                        bool(climax_st.get("partner_climaxed", False))
                        or "partner reached climax" in ic_str
                        or "partner peaked" in ic_str
                    )
                    exc_st = phys_st.get("excitement", {}) or {}
                    last_act = infer_last_act_from_state(phys_st)
                    premature_finish = (
                        bool(exc_st.get("premature_finish", False))
                        or "player reached climax spent, partner unsatisfied" in ic_str
                    )
                    partner_demanded = bool(exc_st.get("partner_demanded", True))
                    in_refr_cooldown, _ = is_in_refractory_cooldown(sess, phys_st)
                    if (
                        in_refr_cooldown
                        and isinstance(exc_st.get("refractory_partners"), dict)
                        and exc_st.get("refractory_partners")
                    ):
                        if partner_climaxes_map is None:
                            partner_climaxes_map = {}
                        for rp_k, rp_v in exc_st["refractory_partners"].items():
                            if rp_v:
                                partner_climaxes_map[rp_k] = True
                        if any(partner_climaxes_map.values()):
                            partner_climaxed = True
                    if exc_st.get("player_in_refractory") is not None:
                        player_in_refr_cooldown = bool(
                            in_refr_cooldown and exc_st.get("player_in_refractory")
                        )
                    else:
                        player_in_refr_cooldown = bool(
                            in_refr_cooldown
                            and (player_already_finished or "ongoing for player" not in ic_str)
                        )

                    char_name_val = (
                        str(char.get("name", "")).strip() if isinstance(char, dict) else ""
                    )
                    exc_actors = exc_st.get("actors", {}) or {}
                    p_exc_match = (
                        _match_actor_key(char_name_val, exc_actors) if char_name_val else ""
                    )
                    n_exc_match = (
                        _match_actor_key(primary_partner, exc_actors) if primary_partner else ""
                    )
                    for k_act, v_act in exc_actors.items():
                        if not isinstance(v_act, dict):
                            continue
                        if (n_exc_match and k_act == n_exc_match) or _is_dialogue_partner(
                            k_act, [primary_partner]
                        ):
                            partner_meter = int(v_act.get("meter", 0) or 0)
                        elif (p_exc_match and k_act == p_exc_match) or (
                            char_name_val and _is_dialogue_partner(k_act, [char_name_val])
                        ):
                            player_meter = int(v_act.get("meter", 0) or 0)
                        elif not player_meter and not p_exc_match:
                            player_meter = int(v_act.get("meter", 0) or 0)

                    phys_actors = phys_st.get("actors", {}) or {}
                    p_pa_match = (
                        _match_actor_key(char_name_val, phys_actors) if char_name_val else ""
                    )
                    n_pa_match = (
                        _match_actor_key(primary_partner, phys_actors) if primary_partner else ""
                    )
                    for k_pa, v_pa in phys_actors.items():
                        if not isinstance(v_pa, dict):
                            continue
                        if (n_pa_match and k_pa == n_pa_match) or _is_dialogue_partner(
                            k_pa, [primary_partner]
                        ):
                            partner_posture = str(v_pa.get("posture", ""))
                        elif (p_pa_match and k_pa == p_pa_match) or (
                            char_name_val and _is_dialogue_partner(k_pa, [char_name_val])
                        ):
                            player_posture = str(v_pa.get("posture", ""))
                        elif not player_posture and not p_pa_match:
                            player_posture = str(v_pa.get("posture", ""))

                    contacts_list = db.get_contacts(session_id) or []
                    for c_rec in contacts_list:
                        if _is_dialogue_partner(str(c_rec.get("name", "")), [primary_partner]):
                            c_appr = c_rec.get("appearance") or {}
                            if isinstance(c_appr, dict) and (
                                c_appr.get("sensitive_spots_revealed")
                                or c_appr.get("turn_ons_revealed")
                            ):
                                sensitive_spots = c_appr.get("sensitive_spots")
                            break

                    if sess:
                        try:
                            for _dpm in get_session_dialogue_partners(sess):
                                _dpm_str = str(_dpm).strip()
                                if _dpm_str and not any(
                                    _is_dialogue_partner(_dpm_str, [p]) for p in partners_list
                                ):
                                    partners_list.append(_dpm_str)
                        except Exception:
                            _dp_multi = sess.get("dialogue_partners")
                            if isinstance(_dp_multi, list) and len(_dp_multi) >= 2:
                                for _dpm in _dp_multi:
                                    _dpm_str = str(_dpm).strip()
                                    if _dpm_str and not any(
                                        _is_dialogue_partner(_dpm_str, [p]) for p in partners_list
                                    ):
                                        partners_list.append(_dpm_str)
                    if is_active_intimate:
                        for _cp_item in exc_st.get("current_partners") or []:
                            _cp_str = str(_cp_item or "").strip()
                            if (
                                _cp_str
                                and _cp_str.lower() not in ("partner", "none")
                                and (
                                    not char_name_val
                                    or not _is_dialogue_partner(_cp_str, [char_name_val])
                                )
                                and not any(
                                    _is_dialogue_partner(_cp_str, [p]) for p in partners_list
                                )
                            ):
                                partners_list.append(_cp_str)
                        _raw_ic_str = str(phys_st.get("intimate_contact", ""))
                        if " with " in _raw_ic_str:
                            _rec_p = _raw_ic_str.split(" with ", 1)[1].split("(")[0].strip()
                            if _rec_p and _rec_p.lower() != "partner":
                                for _chunk in _rec_p.split(","):
                                    for _sp in _chunk.split(" and "):
                                        _sp_str = _sp.strip()
                                        if (
                                            _sp_str
                                            and _sp_str.lower() not in ("partner", "none")
                                            and (
                                                not char_name_val
                                                or not _is_dialogue_partner(
                                                    _sp_str, [char_name_val]
                                                )
                                            )
                                            and not any(
                                                _is_dialogue_partner(_sp_str, [p])
                                                for p in partners_list
                                            )
                                        ):
                                            partners_list.append(_sp_str)

                    if len(partners_list) >= 2:
                        for p_cand in partners_list:
                            p_meter_cand = 0
                            p_cand_match = _match_actor_key(p_cand, exc_actors) if p_cand else ""
                            for k_act, v_act in exc_actors.items():
                                if not isinstance(v_act, dict):
                                    continue
                                if (p_cand_match and k_act == p_cand_match) or _is_dialogue_partner(
                                    k_act, [p_cand]
                                ):
                                    p_meter_cand = int(v_act.get("meter", 0) or 0)
                                    break

                            p_posture_cand = ""
                            p_pa_cand = _match_actor_key(p_cand, phys_actors) if p_cand else ""
                            for k_pa, v_pa in phys_actors.items():
                                if not isinstance(v_pa, dict):
                                    continue
                                if (p_pa_cand and k_pa == p_pa_cand) or _is_dialogue_partner(
                                    k_pa, [p_cand]
                                ):
                                    p_posture_cand = str(v_pa.get("posture", ""))
                                    break

                            p_spots_cand = None
                            p_gender_cand = "Female"
                            for c_rec in contacts_list:
                                if _is_dialogue_partner(str(c_rec.get("name", "")), [p_cand]):
                                    p_gender_cand = (
                                        c_rec.get("gender")
                                        or (c_rec.get("appearance") or {}).get("gender")
                                        or "Female"
                                    )
                                    c_appr = c_rec.get("appearance") or {}
                                    if isinstance(c_appr, dict) and (
                                        c_appr.get("sensitive_spots_revealed")
                                        or c_appr.get("turn_ons_revealed")
                                    ):
                                        p_spots_cand = c_appr.get("sensitive_spots")
                                    break

                            p_clim_cand = False
                            if partner_climaxes_map and isinstance(partner_climaxes_map, dict):
                                p_clim_k = _match_actor_key(p_cand, partner_climaxes_map)
                                p_clim_cand = bool(
                                    partner_climaxes_map.get(p_clim_k or p_cand, False)
                                )
                            else:
                                p_clim_cand = partner_climaxed

                            partner_actors_list.append(
                                {
                                    "name": p_cand,
                                    "meter": p_meter_cand,
                                    "posture": p_posture_cand,
                                    "climaxed": p_clim_cand,
                                    "sensitive_spots": p_spots_cand,
                                    "gender": p_gender_cand,
                                }
                            )
            except Exception:
                pass
        else:
            player_in_refr_cooldown = False

        if partner_actors_list:
            partner_meter = max(int(p.get("meter", 0) or 0) for p in partner_actors_list)

        primary_gender = "Female"
        for c_rec in contacts_list:
            if _is_dialogue_partner(str(c_rec.get("name", "")), [primary_partner]):
                primary_gender = (
                    c_rec.get("gender")
                    or (c_rec.get("appearance") or {}).get("gender")
                    or "Female"
                )
                break

        bp = build_intimate_choice_blueprints(
            partner_name=primary_partner,
            last_act=last_act,
            player_posture=player_posture,
            partner_posture=partner_posture,
            player_meter=player_meter,
            partner_meter=partner_meter,
            partner_climaxed=partner_climaxed,
            player_climaxed=bool(player_spent_and_finished or player_in_refr_cooldown),
            premature_finish=premature_finish,
            partner_demanded=partner_demanded,
            sensitive_spots=sensitive_spots,
            partner_actors=partner_actors_list if len(partner_actors_list) >= 2 else None,
            partner_gender=primary_gender,
        )
        if raw_choices_empty and bp and isinstance(bp.get("choices"), list):
            for fb_c in bp["choices"]:
                fb_c["is_fallback"] = True

    return {
        "is_active_intimate": is_active_intimate,
        "bp": bp,
        "player_already_finished": player_already_finished,
        "player_spent_and_finished": player_spent_and_finished,
        "partner_climaxed": partner_climaxed,
        "premature_finish": premature_finish,
        "partner_demanded": partner_demanded,
        "in_refr_cooldown": in_refr_cooldown,
        "player_in_refr_cooldown": player_in_refr_cooldown,
        "last_act": last_act,
        "player_meter": player_meter,
        "partner_meter": partner_meter,
        "player_posture": player_posture,
        "partner_posture": partner_posture,
        "partner_climaxes_map": partner_climaxes_map,
        "ic_str": ic_str,
        "climax_st": climax_st,
        "phys_st": phys_st,
        "primary_partner": primary_partner,
    }


def _filter_and_enrich_dialogue_choices(
    cleaned: list[dict],
    *,
    partners_list: List[str],
    intimate_ctx: dict[str, Any],
    scenario: str,
    location: str,
    char: dict | None,
    current_npcs: list | None,
    session_id: int | None,
    is_non_combat: bool,
    raw_choices_empty: bool,
) -> list[dict]:
    """Enforce strict conversation lock, intimate safety net, companion recruitment, confession milestones, and dialogue check rules."""
    from mechanics.narrative.choice_generator import get_scenario_dialogue_fallbacks
    from mechanics.narrative.intent import (
        IntentCategory,
        classify_action_intent,
        is_conversational_exit,
    )
    from mechanics.social.agent_roster import evaluate_anomalous_companion_recruitment
    from mechanics.social.anomalous_npc_tags import TAG_CIVILIAN, classify_anomalous_npc_tag
    from mechanics.social.intimate_excitement import (
        INTIMATE_CHOICE_KEYWORDS,
        INTIMATE_EXIT_KEYWORDS,
        has_state_contradiction_in_choice,
        matches_boundary,
        sanitize_scunthorpe_text,
    )
    from mechanics.social.relationships import (
        can_trigger_romantic_confession,
        get_scenario_recruitment_phrasing,
        is_romantic_confession_intent,
    )

    is_active_intimate = bool(intimate_ctx["is_active_intimate"])
    bp = intimate_ctx["bp"]
    player_already_finished = bool(intimate_ctx["player_already_finished"])
    player_spent_and_finished = bool(intimate_ctx["player_spent_and_finished"])
    partner_climaxed = bool(intimate_ctx["partner_climaxed"])
    premature_finish = bool(intimate_ctx["premature_finish"])
    in_refr_cooldown = bool(intimate_ctx["in_refr_cooldown"])
    player_in_refr_cooldown = bool(intimate_ctx["player_in_refr_cooldown"])
    last_act = str(intimate_ctx["last_act"] or "foreplay_nongenital")
    player_meter = int(intimate_ctx["player_meter"] or 0)
    partner_meter = int(intimate_ctx["partner_meter"] or 0)
    player_posture = str(intimate_ctx["player_posture"] or "")
    partner_climaxes_map = intimate_ctx["partner_climaxes_map"]
    ic_str = str(intimate_ctx["ic_str"] or "")
    climax_st = intimate_ctx["climax_st"] or {}
    phys_st = intimate_ctx["phys_st"]
    primary_partner = partners_list[0] if partners_list else ""
    player_has_climaxed = False

    partner_names_lower = [p.lower() for p in partners_list]
    partner_tokens = set()
    for p in partners_list:
        for t in p.lower().split():
            if len(t) > 2 and t not in (
                "the",
                "elder",
                "lord",
                "lady",
                "sir",
                "madam",
                "captain",
                "dr",
                "mr",
                "ms",
                "mrs",
                "scholar",
                "guardian",
                "druid",
                "guildmaster",
                "archivist",
                "warden",
            ):
                partner_tokens.add(t)

    other_npc_tokens = set()
    if current_npcs and isinstance(current_npcs, list):
        for n in current_npcs:
            n_name = game_engine._get_npc_name(n)
            if not n_name or _is_dialogue_partner(n_name, partners_list):
                continue
            n_low = n_name.lower()
            other_npc_tokens.add(n_low)
            for t in n_low.split():
                if len(t) > 2 and t not in (
                    "the",
                    "elder",
                    "lord",
                    "lady",
                    "sir",
                    "madam",
                    "captain",
                    "dr",
                    "mr",
                    "ms",
                    "mrs",
                    "scholar",
                    "guardian",
                    "druid",
                    "guildmaster",
                    "archivist",
                    "warden",
                    "guards",
                    "guard",
                    "patrons",
                    "locals",
                ):
                    other_npc_tokens.add(t)

    dialogue_filtered = []
    has_exit = False

    for c in cleaned:
        lbl = c["label"].lower()
        clean_lbl = c["label"]

        c_intent_str = str(c.get("intent") or "").lower().strip()
        if c_intent_str and c_intent_str != "general_action":
            try:
                intent_cat = IntentCategory(c_intent_str)
            except ValueError:
                intent_cat = classify_action_intent(clean_lbl).category
        else:
            intent_cat = classify_action_intent(clean_lbl).category

        is_intimate_exit_lbl = any(k in lbl for k in INTIMATE_EXIT_KEYWORDS)
        is_exit = not c.get("_quest_dialogue_handoff") and (
            bool(c.get("ends_dialogue"))
            or is_intimate_exit_lbl
            or intent_cat == IntentCategory.DIALOGUE_EXIT
            or is_exempt_free_action(c, in_dialogue_mode=True)
            or (
                is_conversational_exit(clean_lbl)
                and (c["stat"] in ("NONE", "FREE") or c.get("requirement", 0) <= 0)
            )
        )
        if is_exit:
            if not has_exit:
                has_exit = True
                c["stat"] = "NONE"
                c["requirement"] = 0
                c["mp_cost"] = 0
                dialogue_filtered.append(c)
            continue

        target_npc_low = str(c.get("target_npc") or "").lower().strip()
        is_other_target = bool(
            target_npc_low
            and any(ont == target_npc_low or target_npc_low.startswith(ont) for ont in other_npc_tokens)
            and not (
                any(pn in target_npc_low for pn in partner_names_lower)
                or any(pt in target_npc_low for pt in partner_tokens)
            )
        )
        has_partner_in_lbl = any(pn in lbl for pn in partner_names_lower) or matches_keyword_boundary(
            lbl, list(partner_tokens)
        )
        has_other_in_lbl = matches_keyword_boundary(lbl, list(other_npc_tokens))
        is_other_npc = (is_other_target or has_other_in_lbl) and not has_partner_in_lbl
        if is_other_npc and not c.get("is_phase2_choice"):
            continue

        if intent_cat == IntentCategory.MOVEMENT:
            if c.get("is_phase2_choice") or c.get("_quest_dialogue_handoff"):
                dialogue_filtered.append(c)
                continue
            if any(
                p in lbl
                for p in (
                    "walk with",
                    "step into",
                    "turn back",
                    "step away",
                    "head with",
                    "sneak in",
                    "pick the lock",
                    "ring the intercom",
                )
            ):
                dialogue_filtered.append(c)
                continue
            continue

        if intent_cat == IntentCategory.REST_SLEEP:
            continue

        if intent_cat in (IntentCategory.INSPECT_BOARD, IntentCategory.AREA_SCOUT) and not any(
            pn in lbl for pn in partner_names_lower
        ):
            continue
        if "observe your surroundings" in lbl:
            continue
        if is_active_intimate and any(
            k in lbl for k in ("redress", "get dressed", "don clothes", "put on clothes")
        ):
            continue

        is_initiation = False
        for pn in partners_list:
            p_low = pn.lower()
            p_toks = (
                namegen.get_unique_person_tokens(pn, peer_names=partners_list, min_len=2)
                if pn
                else set()
            )
            p_variants = {p_low} | {t for t in p_toks if len(t) >= 2}
            init_prefixes = (
                "greet and talk with ",
                "greet and speak with ",
                "greet ",
                "approach ",
                "start conversation with ",
                "initiate conversation with ",
                "introduce yourself to ",
                "meet with ",
                "meet up with ",
                "talk to ",
                "talk with ",
                "speak with ",
                "speak to ",
                "chat with ",
                "converse with ",
                "strike up a conversation with ",
                "greet and ",
            )
            for ip in init_prefixes:
                if lbl.startswith(ip):
                    sub_rest = lbl[len(ip) :].strip().rstrip(".")
                    if (
                        sub_rest in p_variants
                        or any(sub_rest.startswith(f"{pv} ") for pv in p_variants)
                        or any(
                            filler in sub_rest
                            for filler in (
                                "take a seat",
                                "by the benches",
                                "at the benches",
                                "take a chair",
                                "sit down",
                            )
                        )
                    ):
                        if (
                            c.get("stat") in ("NONE", "FREE")
                            or c.get("requirement", 0) <= 0
                            or any(
                                kw in lbl
                                for kw in ("take a seat", "greet", "approach", "by the benches")
                            )
                        ):
                            is_initiation = True
                            break
            if is_initiation:
                break
            greet_phrases = [
                f"greet and talk with {p_low}",
                f"greet {p_low}",
                f"speak with {p_low}",
                f"talk to {p_low}",
            ] + [f"greet {pv}" for pv in p_variants]
            if any(kw in lbl for kw in greet_phrases) and (
                c.get("stat") in ("NONE", "FREE") or c.get("requirement", 0) <= 0
            ):
                if not is_exit:
                    is_initiation = True
                    break

        if is_initiation:
            continue

        for pn in partners_list:
            p_low = pn.lower()
            for pfx in (
                f"speak with {p_low} about ",
                f"speak to {p_low} about ",
                f"talk with {p_low} about ",
                f"talk to {p_low} about ",
                f"speak with {p_low} regarding ",
                f"discuss with {p_low} regarding ",
                f"discuss with {p_low} about ",
            ):
                if lbl.startswith(pfx):
                    sub_text = clean_lbl[len(pfx) :].strip()
                    clean_lbl = f"Inquire about {sub_text}"
                    c["label"] = clean_lbl
                    break
                elif f"speak with {p_low}" in lbl or f"talk to {p_low}" in lbl:
                    clean_lbl = clean_lbl.replace(f"Speak with {pn}", "Converse with").replace(
                        f"speak with {p_low}", "converse with"
                    )
                    c["label"] = clean_lbl

        dialogue_filtered.append(c)

    # Hybrid Guided Intimate System (Layer 2)
    is_filtering_intimate = bool(
        is_active_intimate
        or in_refr_cooldown
        or player_spent_and_finished
        or "aftercare" in ic_str
        or (climax_st and (climax_st.get("player_climaxed") or climax_st.get("partner_climaxed")))
    )
    if is_filtering_intimate:
        player_is_spent = bool(player_spent_and_finished or player_in_refr_cooldown)
        player_has_climaxed = bool(
            player_already_finished
            or player_spent_and_finished
            or player_meter >= 100
            or player_in_refr_cooldown
            or "player reached climax"
            in str(getattr(phys_st, "get", lambda *_: "")("intimate_contact", "")).lower()
        )
        non_contradictory = []
        for c in dialogue_filtered:
            if is_exempt_free_action(c, in_dialogue_mode=True):
                if has_state_contradiction_in_choice(
                    c.get("label", ""),
                    last_act,
                    partner_climaxed,
                    player_meter,
                    partner_meter,
                    player_posture,
                    player_spent=player_is_spent,
                    partner_climaxes=partner_climaxes_map,
                    player_climaxed=player_has_climaxed,
                ) or any(
                    kw in c.get("label", "").lower() for kw in ("thank ", "look around the room")
                ):
                    c["label"] = bp["exit_label"]
                non_contradictory.append(c)
                continue
            if has_state_contradiction_in_choice(
                c.get("label", ""),
                last_act,
                partner_climaxed,
                player_meter,
                partner_meter,
                player_posture,
                player_spent=player_is_spent,
                partner_climaxes=partner_climaxes_map,
                player_climaxed=player_has_climaxed,
            ):
                continue
            non_contradictory.append(c)
        dialogue_filtered = non_contradictory

        substantive_choices = [
            c for c in dialogue_filtered if not is_exempt_free_action(c, in_dialogue_mode=True)
        ]
        exit_choices = [
            c for c in dialogue_filtered if is_exempt_free_action(c, in_dialogue_mode=True)
        ]
        if exit_choices:
            has_exit = True

        if (player_spent_and_finished or player_in_refr_cooldown) and premature_finish:
            has_dynamic_post_climax = any(
                matches_boundary(
                    c.get("label", "").lower(),
                    (
                        "finger",
                        "fingers",
                        "hand",
                        "hands",
                        "tongue",
                        "mouth",
                        "lick",
                        "please",
                        "pleasure",
                        "climax",
                        "edge",
                        "stroke",
                        "touch",
                        "kiss",
                        "apologize",
                    ),
                )
                for c in substantive_choices
            )
            target_sub_count = max(2, len(bp["choices"]) - 1)
            if not has_dynamic_post_climax:
                dialogue_filtered = [dict(fb_c) for fb_c in bp["choices"]]
                has_exit = True
            elif len(substantive_choices) < target_sub_count:
                existing_lbls = {c.get("label", "").lower() for c in substantive_choices}
                for fb_c in bp["choices"][:-1]:
                    if fb_c["label"].lower() not in existing_lbls:
                        substantive_choices.append(dict(fb_c))
                        existing_lbls.add(fb_c["label"].lower())
                    if len(substantive_choices) >= target_sub_count:
                        break
                dialogue_filtered = substantive_choices + exit_choices
        elif (player_spent_and_finished or player_in_refr_cooldown) and not premature_finish:
            has_valid_aftercare = any(
                matches_boundary(
                    c.get("label", "").lower(),
                    (
                        "aftercare",
                        "cuddle",
                        "hold",
                        "kiss",
                        "caress",
                        "hair",
                        "tender",
                        "warmth",
                        "breath",
                        "rest",
                        "whisper",
                        "pillow",
                        "talk",
                        "drink",
                        "water",
                        "blanket",
                        "dress",
                    ),
                )
                for c in substantive_choices
            )
            if not has_valid_aftercare:
                dialogue_filtered = [dict(fb_c) for fb_c in bp["choices"]]
                has_exit = True
            else:
                target_sub_count = max(2, len(bp["choices"]) - 1)
                if len(substantive_choices) < target_sub_count:
                    existing_lbls = {c.get("label", "").lower() for c in substantive_choices}
                    for fb_c in bp["choices"][:-1]:
                        if fb_c["label"].lower() not in existing_lbls:
                            substantive_choices.append(dict(fb_c))
                            existing_lbls.add(fb_c["label"].lower())
                        if len(substantive_choices) >= target_sub_count:
                            break
                dialogue_filtered = substantive_choices + exit_choices
        else:
            has_valid_intimate = any(
                matches_boundary(
                    sanitize_scunthorpe_text(c.get("label", "").lower()), INTIMATE_CHOICE_KEYWORDS
                )
                for c in substantive_choices
            )
            if not has_valid_intimate:
                dialogue_filtered = [dict(fb_c) for fb_c in bp["choices"][:3]] + exit_choices
            elif len(substantive_choices) < 3:
                existing_lbls = {c.get("label", "").lower() for c in substantive_choices}
                for fb_c in bp["choices"][:3]:
                    if fb_c["label"].lower() not in existing_lbls:
                        substantive_choices.append(dict(fb_c))
                        existing_lbls.add(fb_c["label"].lower())
                    if len(substantive_choices) >= 3:
                        break
                dialogue_filtered = substantive_choices + exit_choices

        if not player_has_climaxed:
            sanitized_dialogue = []
            for c in dialogue_filtered:
                c_lbl = str(c.get("label", "")).lower()
                if any(kw in c_lbl for kw in ("aftercare", "post-coital", "post-climax")):
                    if is_exempt_free_action(c, in_dialogue_mode=True):
                        clean_exit = bp.get("exit_label", "") if bp else ""
                        if not clean_exit or any(
                            kw in clean_exit.lower()
                            for kw in ("aftercare", "post-coital", "post-climax")
                        ):
                            clean_exit = (
                                f"Slow your rhythm, gently withdraw, and hold {primary_partner} close"
                                if last_act in ("penetrative", "anal_give", "anal_receive")
                                else f"Ease back gently, pause to catch your breath, and hold {primary_partner} close"
                            )
                        c["label"] = clean_exit
                        sanitized_dialogue.append(c)
                    else:
                        continue
                else:
                    sanitized_dialogue.append(c)
            dialogue_filtered = sanitized_dialogue

            sub_now = [
                c for c in dialogue_filtered if not is_exempt_free_action(c, in_dialogue_mode=True)
            ]
            if len(sub_now) < 3 and bp and isinstance(bp.get("choices"), list):
                existing_lbls = {c.get("label", "").lower() for c in dialogue_filtered}
                exit_items = [
                    c for c in dialogue_filtered if is_exempt_free_action(c, in_dialogue_mode=True)
                ]
                for fb_c in bp["choices"][:3]:
                    if fb_c["label"].lower() not in existing_lbls and not any(
                        kw in fb_c["label"].lower()
                        for kw in ("aftercare", "post-coital", "post-climax")
                    ):
                        sub_now.append(dict(fb_c))
                        existing_lbls.add(fb_c["label"].lower())
                        if len(sub_now) >= 3:
                            break
                dialogue_filtered = sub_now + exit_items

        for _ic_choice in dialogue_filtered:
            _ic_choice["is_quest_action"] = False
            _ic_choice["is_climax_action"] = False
            _ic_choice["is_story_quest"] = False
            _ic_choice["quest_id"] = ""
            _ic_choice["sub_obj_id"] = None
            _ic_choice["stage_index"] = None
            _ic_choice["contract_type"] = ""

    # Ensure at least 1-2 substantive dialogue choices exist if everything was stripped
    if not any(df for df in dialogue_filtered if not is_exempt_free_action(df, in_dialogue_mode=True)):
        if is_active_intimate and bp:
            for fb_c in reversed(bp["choices"][:3]):
                dialogue_filtered.insert(0, dict(fb_c))
        else:
            bystanders = [
                n
                for n in (current_npcs or [])
                if game_engine._get_npc_name(n)
                and not _is_dialogue_partner(game_engine._get_npc_name(n), partners_list)
            ]
            scen_fbs = get_scenario_dialogue_fallbacks(
                primary_partner,
                scenario=scenario,
                present_bystanders=bystanders,
                location=location,
                char=char,
            )
            for fb_item in reversed(scen_fbs[:2]):
                fb_copy = dict(fb_item)
                fb_copy["is_fallback"] = raw_choices_empty
                dialogue_filtered.insert(0, fb_copy)

    # Guarantee that a free exit choice exists
    if not has_exit:
        if is_active_intimate:
            exit_label = bp["exit_label"]
            if not player_has_climaxed and any(
                kw in exit_label.lower() for kw in ("aftercare", "post-coital", "post-climax")
            ):
                exit_label = (
                    f"Slow your rhythm, gently withdraw, and hold {primary_partner} close"
                    if last_act in ("penetrative", "anal_give", "anal_receive")
                    else f"Ease back gently, pause to catch your breath, and hold {primary_partner} close"
                )
        elif len(partners_list) == 1:
            exit_label = f"Thank {partners_list[0]}, excuse yourself, and look around the room"
        elif len(partners_list) == 2:
            exit_label = f"Thank {partners_list[0]} and {partners_list[1]}, excuse yourself, and look around the room"
        else:
            exit_label = "Thank everyone, excuse yourself, and look around the room"
        dialogue_filtered.append(
            {
                "label": exit_label,
                "stat": "NONE",
                "requirement": 0,
                "mp_cost": 0,
                "is_fallback": False,
            }
        )

    # Party Companion Recruitment Auto-Injector
    if is_non_combat:
        dialogue_filtered = [
            c
            for c in dialogue_filtered
            if not (
                c.get("intent") == "party_recruit"
                or matches_keyword_boundary(c.get("label", "").lower(), _RECRUIT_CHOICE_KEYWORDS)
            )
        ]
    elif (
        not is_active_intimate
        and not is_non_combat
        and scenario_data.is_mechanic_enabled(scenario, "tactical_combat")
        and session_id
    ):
        is_anom_cc = bool(
            scenario_data.is_anomalous_incursions_scenario(scenario)
            or scenario_data.is_anomalous_high_school_scenario(scenario)
            or "urban_anomalies" in str(scenario).lower()
        )
        sess = db.get_session(session_id)
        lore_people = db.get_lorebook(session_id).get("person", []) if session_id else []
        for p_name in partners_list:
            if not p_name:
                continue
            ineligible_anom_partner = False
            if is_anom_cc:
                try:
                    lore_ent_strip = next(
                        (p for p in lore_people if p.get("name", "").lower() == p_name.lower()), {}
                    )
                    if (
                        classify_anomalous_npc_tag(
                            lore_ent_strip or p_name, session_id=session_id, scen_key=scenario
                        )
                        == TAG_CIVILIAN
                    ):
                        ineligible_anom_partner = True
                    else:
                        lead_uid_st = (char.get("user_id") if isinstance(char, dict) else 0) or (
                            sess.get("host_user_id") if isinstance(sess, dict) else 0
                        )
                        c_rec_st = db.get_contact(session_id, p_name)
                        aff_st = int((c_rec_st or {}).get("relationship_score", 0) or 0)
                        lvl_st = int((char.get("level", 1) if isinstance(char, dict) else 1) or 1)
                        cand_st = dict(lore_ent_strip or {})
                        if isinstance(c_rec_st, dict):
                            cand_st.update(c_rec_st)
                        cand_st["name"] = p_name
                        eval_st = evaluate_anomalous_companion_recruitment(
                            sess or {"id": session_id, "scenario": scenario},
                            lead_uid_st,
                            cand_st,
                            aff_st,
                            lvl_st,
                        )
                        if not eval_st.get("allowed"):
                            ineligible_anom_partner = True
                except Exception:
                    pass
            if ineligible_anom_partner or db.get_recruitment_cooldown(session_id, p_name) > 0:
                dialogue_filtered = [
                    c
                    for c in dialogue_filtered
                    if not (
                        (
                            c.get("intent") == "party_recruit"
                            or any(
                                kw in c.get("label", "").lower() for kw in _RECRUIT_CHOICE_KEYWORDS
                            )
                            or "recruit" in c.get("label", "").lower()
                        )
                        and (p_name.lower() in c.get("label", "").lower() or len(partners_list) == 1)
                    )
                ]

        party_npcs = db.get_session_party_npcs(session_id)
        human_count = len(sess.get("turn_order", [])) if sess else 1
        if human_count + len(party_npcs) < 4:
            enemy_list = (
                game_engine.get_active_enemies(sess)
                if hasattr(game_engine, "get_active_enemies")
                else []
            )
            enemy_names = {game_engine._get_npc_name(e).lower() for e in enemy_list if e}

            has_recruit = any(
                c.get("intent") == "party_recruit"
                or any(kw in c.get("label", "").lower() for kw in _RECRUIT_CHOICE_KEYWORDS)
                or "recruit" in c.get("label", "").lower()
                for c in dialogue_filtered
            )
            if not has_recruit:
                for p_name in partners_list:
                    if (
                        not p_name
                        or p_name.lower() in enemy_names
                        or any(p.get("name", "").lower() == p_name.lower() for p in party_npcs)
                    ):
                        continue
                    lore_ent = next(
                        (p for p in lore_people if p.get("name", "").lower() == p_name.lower()), {}
                    )
                    t_role = str(
                        lore_ent.get("role")
                        or lore_ent.get("occupation")
                        or lore_ent.get("description")
                        or ""
                    ).lower()
                    if any(
                        m in t_role
                        for m in ("merchant", "shopkeeper", "vendor", "apothecary", "peddler", "trader")
                    ):
                        continue
                    if is_anom_cc:
                        try:
                            if (
                                classify_anomalous_npc_tag(
                                    lore_ent or p_name, session_id=session_id, scen_key=scenario
                                )
                                == TAG_CIVILIAN
                            ):
                                continue
                            lead_uid_cc = (
                                char.get("user_id") if isinstance(char, dict) else 0
                            ) or (sess.get("host_user_id") if isinstance(sess, dict) else 0)
                            c_rec_cc = db.get_contact(session_id, p_name)
                            aff_cc = int((c_rec_cc or {}).get("relationship_score", 0) or 0)
                            lvl_cc = int(
                                (char.get("level", 1) if isinstance(char, dict) else 1) or 1
                            )
                            cand_cc = dict(lore_ent or {})
                            if isinstance(c_rec_cc, dict):
                                cand_cc.update(c_rec_cc)
                            cand_cc["name"] = p_name
                            eval_cc = evaluate_anomalous_companion_recruitment(
                                sess or {"id": session_id, "scenario": scenario},
                                lead_uid_cc,
                                cand_cc,
                                aff_cc,
                                lvl_cc,
                            )
                            if not eval_cc.get("allowed"):
                                continue
                            cost_cc = int(eval_cc.get("cost", 0) or 0)
                            if eval_cc.get("anomalous_npc_tag") == "folklore_villager":
                                rec_label = (
                                    f"Invite {p_name} to join your party beyond the sanctuary veil"
                                )
                            elif cost_cc > 0:
                                rec_label = f"Hire Special Agent {p_name} onto your field team ({cost_cc}G)"
                            else:
                                rec_label = f"Ask Special Agent {p_name} to partner up and join your field team"
                            cd = db.get_recruitment_cooldown(session_id, p_name)
                            if cd == 0:
                                recruit_choice = {
                                    "label": rec_label,
                                    "stat": "NONE",
                                    "requirement": 0,
                                    "mp_cost": 0,
                                    "intent": "party_recruit",
                                    "target_npc": p_name,
                                    "_server_stamped": True,
                                    "is_fallback": False,
                                }
                                if (
                                    len(dialogue_filtered) > 1
                                    and dialogue_filtered[-1].get("stat") == "NONE"
                                ):
                                    dialogue_filtered.insert(
                                        len(dialogue_filtered) - 1, recruit_choice
                                    )
                                else:
                                    dialogue_filtered.append(recruit_choice)
                                break
                            continue
                        except Exception:
                            continue
                    if "slice_of_life" in str(scenario).lower() or (
                        "high_school" in str(scenario).lower()
                        and "anomalous" not in str(scenario).lower()
                    ):
                        continue
                    c_rec_std = db.get_contact(session_id, p_name)
                    if (
                        isinstance(c_rec_std, dict)
                        and int(c_rec_std.get("relationship_score", 0) or 0) < 0
                    ):
                        continue
                    cd = db.get_recruitment_cooldown(session_id, p_name)
                    if cd == 0:
                        rec_phrasing = get_scenario_recruitment_phrasing(scenario, p_name)
                        recruit_choice = {
                            "label": rec_phrasing["choice_label"],
                            "stat": "CHA",
                            "requirement": 6,
                            "mp_cost": 0,
                            "intent": "party_recruit",
                            "target_npc": p_name,
                            "is_fallback": False,
                        }
                        if (
                            len(dialogue_filtered) > 1
                            and dialogue_filtered[-1].get("stat") == "NONE"
                        ):
                            dialogue_filtered.insert(len(dialogue_filtered) - 1, recruit_choice)
                        else:
                            dialogue_filtered.append(recruit_choice)
                        break

    # Romantic Confession Milestone Auto-Injector & Dynamic Filter
    if session_id:
        char_id = (
            char.get("id") if isinstance(char, dict) else (char if isinstance(char, int) else None)
        )
        if not char_id and session_id:
            try:
                s_row = db.get_session(session_id)
                turn_ord = s_row.get("turn_order", []) if s_row else []
                if turn_ord:
                    c_active = db.get_active_character(turn_ord[0])
                    if c_active:
                        char_id = c_active.get("id")
            except Exception:
                pass

        pruned_dialogue = []
        for c in dialogue_filtered:
            if c.get("intent") == "romantic_confession" or is_romantic_confession_intent(
                c.get("label", "")
            ):
                t_npc = c.get("target_npc")
                if not t_npc:
                    for p_name in partners_list:
                        if p_name.lower() in str(c.get("label", "")).lower():
                            t_npc = p_name
                            break
                if not t_npc and partners_list:
                    t_npc = partners_list[0]

                if t_npc and not can_trigger_romantic_confession(
                    session_id, char_id, t_npc, scenario=scenario
                ):
                    continue
            pruned_dialogue.append(c)
        dialogue_filtered = pruned_dialogue

        has_confession_choice = any(
            c.get("intent") == "romantic_confession"
            or is_romantic_confession_intent(c.get("label", ""))
            for c in dialogue_filtered
        )
        if not has_confession_choice and not is_active_intimate:
            for p_name in partners_list:
                if can_trigger_romantic_confession(
                    session_id, char_id, p_name, scenario=scenario
                ):
                    confession_choice = {
                        "label": f"Confess your feelings and ask {p_name} to pursue a romantic relationship",
                        "stat": "CHA",
                        "requirement": 8,
                        "mp_cost": 0,
                        "is_fallback": False,
                        "intent": "romantic_confession",
                        "target_npc": p_name,
                    }
                    if len(dialogue_filtered) > 1 and dialogue_filtered[-1].get("stat") == "NONE":
                        dialogue_filtered.insert(len(dialogue_filtered) - 1, confession_choice)
                    else:
                        dialogue_filtered.append(confession_choice)

    # Every dialogue choice requires a skill check except the dedicated exit choice
    for c in dialogue_filtered:
        clean_lbl = c.get("label", "")
        if is_exempt_free_action(c, in_dialogue_mode=True):
            c["stat"] = "NONE"
            c["requirement"] = 0
            c["mp_cost"] = 0
        elif c.get("stat") in ("NONE", "FREE", None, "") or c.get("requirement", 0) <= 0:
            c["stat"], c["requirement"] = infer_choice_stat_and_dc(
                clean_lbl, default_stat="CHA", default_dc=6, char=char
            )

    return dialogue_filtered
