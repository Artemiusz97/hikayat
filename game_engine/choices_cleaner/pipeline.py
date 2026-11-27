"""Core multi-stage choice normalization, open-hub NPC injection, pruning, and enrichment pipeline."""
from __future__ import annotations

import re
from typing import Any, List

import db
from db import STAT_COLUMN
import game_engine
import namegen
import scenario_data
from game_engine.matching import matches_keyword_boundary
from mechanics.world.mobility import is_dialogue_partner as _is_dialogue_partner
from .dialogue_stage import _filter_and_enrich_dialogue_choices, _hydrate_intimate_scene_state
from .inventory_rules import (
    _extract_offered_item_and_target,
    _get_player_inventory_items,
    _is_exempt_offering,
    _is_item_in_inventory,
    infer_choice_stat_and_dc,
    is_exempt_free_action,
    is_malformed_choice_label,
)
from .stems import (
    DEFAULT_STAT_FALLBACK_LABELS,
    _RECRUIT_CHOICE_KEYWORDS,
    _get_effective_first_name,
    _is_generic_examine_choice,
    _safe_int,
    _strip_leading_emojis,
    _strip_wrapping_quotes,
    deduplicate_redundant_choices,
)

_PRESERVED_EXTRA_CHOICE_KEYS = (
    "hit_chance",
    "choice_type",
    "attack_type",
    "action_category",
    "dual_wield",
    "stance",
    "label_detail",
    "spell_id",
    "combat_target",
    "combat_tactical_archetype",
    "item_name",
    "item",
    "item_consumed",
    "skip_minutes",
    "sleep_mode",
    "approach",
    "gold_cost",
    "dc_mod",
    "clue_source_id",
    "is_bonus_clue",
    "_priority_slot",
    "clue_pair_ids",
    "is_phase2_choice",
    "incursion_action",
    "incursion_id",
    "breach_id",
    "offering_item_name",
    "trap_choice_kind",
    "is_anomaly_inquiry",
    "_npc_speak_choice",
    "_pinned_dialogue_exit",
    "sapience",
    "dossier_revealed",
    "taboo_exploited_stat",
    "property_id",
    "price",
    "topic_id",
    "category",
    "is_covert_ability",
    "is_direct_reply",
    "is_cruel",
    "_seed_reconciled",
    "_band",
    "_privacy_nudge",
    "is_privacy_nudge",
    "_convince_stay",
    "departure_action",
    "event_key",
    "_active_quest_inquiry",
    "_is_world_rumor_inquiry",
    "_is_break_the_news",
    "linked_quest_id",
    "_topic_sig",
    "_deterministic_supplement",
    "_quest_dialogue_handoff",
    "_access_barrier",
    "site_action",
    "site_id",
    "_intimate_scene_choice",
    "pickup_item_name",
    "_stealth_injected",
)


def _parse_and_normalize_raw_choices(
    cls,
    choices: list,
    *,
    scenario: str,
    location: str,
    char: dict | None,
    dialogue_partner: str | list | None,
    current_npcs: list | None,
    session_id: int | None,
    is_non_combat: bool,
) -> tuple[list[dict], List[str]]:
    """Stage 1: Parse dialogue partners, normalize raw choice entries, and apply appointment embargo."""
    from mechanics.narrative.intent import IntentContext, resolve_action_intent
    from mechanics.social.anomalous_npc_tags import TAG_CIVILIAN, classify_anomalous_npc_tag
    from mechanics.social.intimate_excitement import is_intimate_action_label
    from mechanics.social.physical_state import is_erotic_intimate_contact
    from mechanics.social.relationships import normalize_recruitment_choice_label
    from mechanics.world.locations.core import get_primary_location_name
    from mechanics.world.mobility import get_session_dialogue_partners
    from mechanics.world.waypoints import check_location_matches_waypoint

    partners_list: List[str] = []
    if dialogue_partner:
        raw_dp_items = (
            dialogue_partner if isinstance(dialogue_partner, list) else [dialogue_partner]
        )
        for raw_dp in raw_dp_items:
            for chunk in str(raw_dp).split(","):
                for sp in chunk.split(" and "):
                    if sp.strip():
                        partners_list.append(sp.strip())

    active_appts: list = []
    if session_id:
        try:
            active_appts = db.get_active_rendezvous_appointments(session_id) or []
        except Exception:
            active_appts = []

    cleaned: list[dict] = []
    if isinstance(choices, list):
        for c in choices[:25]:
            if isinstance(c, str):
                label_str = game_engine.sanitize_internal_tags_and_raw_stats(str(c).strip()).strip()
                if not label_str or is_malformed_choice_label(label_str):
                    continue
                stat, req_v = infer_choice_stat_and_dc(label_str, char=char)
                if label_str.startswith("[") and "]" in label_str:
                    prefix = label_str[1 : label_str.index("]")].upper()
                    if prefix in (
                        "AGI",
                        "CHA",
                        "STR",
                        "INT",
                        "PER",
                        "END",
                        "LUK",
                        "WIS",
                        "VIT",
                        "ITEM",
                        "NONE",
                        "FREE",
                    ):
                        stat = prefix
                        req_v = (
                            10
                            if prefix
                            in ("AGI", "CHA", "STR", "INT", "PER", "END", "LUK", "WIS", "VIT")
                            else 0
                        )
                c = {
                    "label": label_str,
                    "stat": stat,
                    "requirement": req_v,
                    "mp_cost": 0,
                    "is_phase2_choice": True,
                }
            elif not isinstance(c, dict):
                continue

            raw_label = c.get("label") or c.get("text") or c.get("action")
            label_str = (
                game_engine.sanitize_internal_tags_and_raw_stats(str(raw_label).strip()).strip()
                if raw_label is not None
                else ""
            )
            if not label_str or is_malformed_choice_label(label_str):
                continue
            if _is_generic_examine_choice(c, label_str):
                continue
            label_lower = label_str.lower()

            stat = c.get("stat")
            if not isinstance(stat, str) or (
                stat not in STAT_COLUMN and stat not in ("ITEM", "NONE", "FREE")
            ):
                if label_str.startswith("[") and "]" in label_str:
                    prefix = label_str[1 : label_str.index("]")].upper()
                    stat = (
                        prefix
                        if (prefix in STAT_COLUMN or prefix in ("ITEM", "NONE", "FREE"))
                        else "AGI"
                    )
                else:
                    stat = "AGI"

            req_val = c.get("requirement")
            if req_val is None:
                req_val = c.get("dc", 6)
            requirement = (
                cls._safe_int(req_val, default=6)
                if cls is not None and hasattr(cls, "_safe_int")
                else _safe_int(req_val, default=6)
            )

            mp_val = c.get("mp_cost", 0)
            mp_cost = (
                cls._safe_int(mp_val, default=0)
                if cls is not None and hasattr(cls, "_safe_int")
                else _safe_int(mp_val, default=0)
            )

            is_party_recruit = c.get("intent") == "party_recruit" or matches_keyword_boundary(
                label_lower, _RECRUIT_CHOICE_KEYWORDS
            )
            if is_non_combat and is_party_recruit:
                continue
            t_npc_rec = str(c.get("target_npc") or "").strip()
            if not t_npc_rec and partners_list:
                for p_cand in partners_list:
                    if p_cand and p_cand.lower() in label_lower:
                        t_npc_rec = p_cand
                        break
                if not t_npc_rec and len(partners_list) == 1:
                    t_npc_rec = partners_list[0]
            if is_party_recruit and session_id:
                try:
                    if scenario_data.is_anomalous_incursions_scenario(scenario):
                        scene_ent_cc = next(
                            (
                                n
                                for n in (current_npcs or [])
                                if isinstance(n, dict)
                                and t_npc_rec
                                and str(n.get("name") or "").strip().lower() == t_npc_rec.lower()
                            ),
                            None,
                        )
                        if (
                            t_npc_rec
                            and classify_anomalous_npc_tag(
                                scene_ent_cc or t_npc_rec, session_id=session_id, scen_key=scenario
                            )
                            == TAG_CIVILIAN
                        ):
                            continue
                except Exception:
                    pass

            has_explicit_quest_tag = bool(
                c.get("is_quest_action")
                or c.get("is_story_quest")
                or c.get("is_climax_action")
                or "sq-" in str(c.get("quest_id", "")).lower()
                or any(
                    k in label_lower
                    for k in (
                        "[story climax",
                        "[höhepunkt der geschichte",
                        "[kemuncak cerita",
                        "[punkt kulminacyjny",
                        "[剧情高潮",
                        "[story quest",
                        "[hauptquest",
                        "[misi utama",
                        "[zadanie główne",
                        "[主线任务",
                        "[bounty",
                        "[kopfgeld",
                        "[ganjaran",
                        "[zlecenie",
                        "[悬赏",
                    )
                )
            )
            _preserve_anom_brackets = bool(
                c.get("is_anomaly_inquiry")
                or c.get("intent") == "property_purchase"
                or c.get("incursion_action")
                or c.get("trap_choice_kind")
                or (c.get("_server_stamped") and c.get("sapience"))
                or str(c.get("approach") or "").startswith(("nh_", "anomaly_", "question_trap"))
            )
            if _preserve_anom_brackets and not has_explicit_quest_tag:
                clean_label_str = label_str.strip()
            else:
                clean_label_str = (
                    re.sub(
                        r"^(?:[⭐🎯⚡💌🔹🌙⏳🤝\s]+|\s*\[(?:Main|Side|Optional[^\]\r\n]*|Quest|Meetup|Treffen|Pertemuan|Spotkanie|碰头|碰面|会面|Story Quest(?:\s*\|[^\]\r\n]+)?|Hauptquest(?:\s*\|[^\]\r\n]+)?|Misi Utama(?:\s*\|[^\]\r\n]+)?|Zadanie Główne(?:\s*\|[^\]\r\n]+)?|主线任务(?:\s*\|[^\]\r\n]+)?|Bounty(?:\s*\|[^\]\r\n]+)?|Kopfgeld(?:\s*\|[^\]\r\n]+)?|Ganjaran(?:\s*\|[^\]\r\n]+)?|Zlecenie(?:\s*\|[^\]\r\n]+)?|悬赏(?:\s*\|[^\]\r\n]+)?|Story Climax(?:\s*-\s*[^\]\r\n]+)?|Höhepunkt der Geschichte(?:\s*-\s*[^\]\r\n]+)?|Kemuncak Cerita(?:\s*-\s*[^\]\r\n]+)?|Punkt Kulminacyjny(?:\s*-\s*[^\]\r\n]+)?|剧情高潮(?:\s*-\s*[^\]\r\n]+)?)\]\s*)+",
                        "",
                        _strip_leading_emojis(label_str),
                        flags=re.IGNORECASE,
                    ).strip()
                    or _strip_leading_emojis(label_str)
                )
            clean_label_str = game_engine.sanitize_internal_tags_and_raw_stats(
                clean_label_str
            ).strip()
            if (
                not clean_label_str
                or clean_label_str.lower() in ("act", "action", "choice", "none", "null")
                or is_malformed_choice_label(clean_label_str)
            ):
                clean_label_str = getattr(
                    cls, "STAT_FALLBACK_LABELS", DEFAULT_STAT_FALLBACK_LABELS
                ).get(stat, "Take action")
            elif is_party_recruit:
                try:
                    clean_label_str = normalize_recruitment_choice_label(
                        clean_label_str, scenario=scenario, target_npc=t_npc_rec
                    )
                except Exception:
                    pass

            if active_appts:
                try:
                    is_embargoed_leak = False
                    for appt in active_appts:
                        if appt.get("is_confidential") and appt.get("topic"):
                            appt_loc = appt.get("rendezvous_location", "")
                            if not (
                                check_location_matches_waypoint(location, appt_loc)
                                or check_location_matches_waypoint(appt_loc, location)
                            ):
                                top_words = [
                                    w
                                    for w in re.split(r"\W+", appt["topic"].lower())
                                    if len(w) >= 4
                                    and w
                                    not in ("with", "about", "that", "this", "from", "the", "their")
                                ]
                                if any(w in label_lower for w in top_words):
                                    is_embargoed_leak = True
                                    break
                    if is_embargoed_leak:
                        continue

                    for appt in active_appts:
                        appt_loc = appt.get("rendezvous_location", "")
                        n_name = appt.get("npc_name", "")
                        if appt_loc and n_name:
                            appt_p = get_primary_location_name(appt_loc).lower()
                            if (
                                appt_p
                                and appt_p in label_lower
                                and "(meetup:" not in clean_label_str.lower()
                            ):
                                clean_label_str = f"{clean_label_str} (Meetup: {n_name})"
                                break
                except Exception:
                    pass

            _is_intimate_lbl = is_intimate_action_label(clean_label_str)
            _dp_items = (
                dialogue_partner
                if isinstance(dialogue_partner, list)
                else ([dialogue_partner] if dialogue_partner else [])
            )
            _dp_str = str(_dp_items[0] if _dp_items else "").strip()
            ctx_early = IntentContext(
                dialogue_partner=_dp_str,
                dialogue_partners=[str(p).strip() for p in _dp_items if p],
                current_zone=location,
                present_npcs=current_npcs or [],
                scenario=scenario,
            )
            parsed_early = resolve_action_intent(
                c if isinstance(c, dict) else clean_label_str, ctx_early
            )
            early_intent = c.get("intent") or (
                parsed_early.category.value if parsed_early else "general_action"
            )
            early_sub_intent = c.get("sub_intent") or (
                parsed_early.sub_target if parsed_early else ""
            )
            early_target_npc = _strip_wrapping_quotes(
                c.get("target_npc") or (parsed_early.target_entity if parsed_early else "")
            )

            _is_server_stamped = bool(
                c.get("_server_stamped") or c.get("_python_verified_quest") or c.get("_priority_slot")
            )
            if _is_intimate_lbl:
                _verified_quest = False
            elif "_python_verified_quest" in c:
                _verified_quest = bool(c.get("_python_verified_quest"))
            elif _is_server_stamped or not session_id:
                _verified_quest = bool(c.get("is_quest_action", False))
            else:
                _verified_quest = False

            _has_legit_mp_mechanic = bool(
                c.get("spell_id")
                or c.get("is_covert_ability")
                or _is_server_stamped
                or c.get("_deterministic_supplement")
                or c.get("incursion_action")
            )
            safe_mp_cost = max(0, min(250, mp_cost)) if _has_legit_mp_mechanic else 0

            entry_dict = {
                "label": clean_label_str[:190],
                "stat": stat,
                "requirement": max(0, min(20, requirement)),
                "mp_cost": safe_mp_cost,
                "gold_spent": max(
                    0, _safe_int(c.get("gold_spent", c.get("gold_cost", 0)), default=0) or 0
                ),
                "triggers_loot_roll": bool(c.get("triggers_loot_roll", False)),
                "is_fallback": bool(c.get("is_fallback", False)),
                "_server_stamped": bool(_is_server_stamped or _verified_quest),
                "_python_verified_quest": _verified_quest,
                "is_quest_action": _verified_quest,
                "is_climax_action": bool(c.get("is_climax_action", False) and _verified_quest),
                "is_premature_climax": bool(
                    c.get("is_premature_climax", False) and _verified_quest
                ),
                "rush_climax": bool(
                    c.get("rush_climax", False)
                    and (_verified_quest or _is_server_stamped or not session_id)
                ),
                "off_hours_fallback": bool(
                    c.get("off_hours_fallback", False)
                    and (_verified_quest or _is_server_stamped or not session_id)
                ),
                "is_story_quest": bool(c.get("is_story_quest", False) and _verified_quest),
                "breakthrough_leveraged": bool(c.get("breakthrough_leveraged", False))
                if (_is_server_stamped or _verified_quest or not session_id)
                else False,
                "intent": early_intent,
                "sub_intent": early_sub_intent,
                "target_npc": early_target_npc,
                "ends_dialogue": bool(c.get("ends_dialogue", False)),
                "dismisses_npc": bool(c.get("dismisses_npc", False)),
                "target_node_id": str(c.get("target_node_id") or "")
                if (_is_server_stamped or not session_id)
                else "",
                "target_location": str(c.get("target_location") or ""),
                "quest_id": c.get("quest_id", "")
                if (_verified_quest or _is_server_stamped or not session_id)
                else "",
                "sub_obj_id": c.get("sub_obj_id")
                if (_verified_quest or _is_server_stamped or not session_id)
                else None,
                "_raw_sub_obj_id": c.get("sub_obj_id")
                if (_is_server_stamped or not session_id)
                else None,
                "stage_index": c.get("stage_index") if _verified_quest else None,
                "contract_type": c.get("contract_type", "") if _verified_quest else "",
            }
            for _extra_k in _PRESERVED_EXTRA_CHOICE_KEYS:
                if _extra_k in c and c[_extra_k] is not None:
                    val_extra = c[_extra_k]
                    if _extra_k in ("topic_id", "category") and isinstance(val_extra, str):
                        val_extra = _strip_wrapping_quotes(val_extra)
                    entry_dict[_extra_k] = val_extra
            cleaned.append(entry_dict)

    if not partners_list and session_id:
        try:
            _cc_phys = db.get_session_physical_state(session_id) or {}
            _cc_ic = str(_cc_phys.get("intimate_contact", ""))
            if is_erotic_intimate_contact(_cc_ic):
                if " with " in _cc_ic:
                    _rec_p = _cc_ic.split(" with ", 1)[1].split("(")[0].strip()
                    if _rec_p and _rec_p.lower() != "partner":
                        for _chunk in _rec_p.split(","):
                            for _sp in _chunk.split(" and "):
                                if _sp.strip() and _sp.strip().lower() != "partner":
                                    partners_list.append(_sp.strip())
                if not partners_list:
                    _cc_sess = db.get_session(session_id) or {}
                    try:
                        partners_list = get_session_dialogue_partners(_cc_sess)
                    except Exception:
                        _dp_val = _cc_sess.get("dialogue_partners") or _cc_sess.get(
                            "dialogue_partner"
                        )
                        if isinstance(_dp_val, list):
                            partners_list = [str(p).strip() for p in _dp_val if str(p).strip()]
                        elif isinstance(_dp_val, str) and _dp_val.strip():
                            partners_list = [_dp_val.strip()]
        except Exception:
            pass

    return cleaned, partners_list


def _normalize_and_inject_open_hub_choices(
    cleaned: list[dict],
    *,
    scenario: str,
    location: str,
    char: dict | None,
    current_npcs: list | None,
    partners_list: List[str],
    session_id: int | None,
) -> list[dict]:
    """Open Hub Free-Action Normalizer + present-NPC Speak auto-injector."""
    from mechanics.narrative.intent import IntentContext
    from mechanics.world.waypoints.matching import get_story_quest_climax_location

    npc_names = [game_engine._get_npc_name(n) for n in (current_npcs or []) if n]
    ctx_hub = IntentContext(
        current_zone=location or "", present_npcs=npc_names, scenario=scenario
    )
    for c in cleaned:
        lbl = c.get("label", "")
        if is_exempt_free_action(c, in_dialogue_mode=False, context=ctx_hub):
            c["stat"] = "NONE"
            c["requirement"] = 0
            c["mp_cost"] = 0
        elif c.get("stat") in ("NONE", "FREE", None, "") or c.get("requirement", 0) <= 0:
            c["stat"], c["requirement"] = infer_choice_stat_and_dc(
                lbl, default_stat="CHA", default_dc=6, char=char
            )

    if current_npcs and isinstance(current_npcs, list):
        active_npcs = []
        for n in current_npcs:
            if not n:
                continue
            if isinstance(n, dict):
                if (
                    n.get("is_anomalous_entity")
                    or n.get("non_hostile_anomaly")
                    or n.get("uncanny_presence")
                ):
                    continue
                n_name = (n.get("name") or "").strip()
                status_list = n.get("status_effects") or []
                status_str = " ".join(
                    str(s.get("name", s) if isinstance(s, dict) else s) for s in status_list
                ).lower()
                if any(s in status_str for s in ["unconscious", "fallen", "dead", "defeated"]):
                    continue
                role = n.get("role") or ""
                if n_name:
                    active_npcs.append((n_name, role))
            elif isinstance(n, str) and n.strip():
                active_npcs.append((n.strip(), ""))

        all_active_npc_names = [nm for nm, _ in active_npcs]
        missing_npc_choices = []
        for n_name, n_role in active_npcs:
            n_low = n_name.lower()
            unique_tokens = [
                t.lower()
                for t in namegen.get_unique_person_tokens(n_name, peer_names=all_active_npc_names)
                if len(t) >= 3
                and t.lower()
                not in (
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
                    "coach",
                    "officer",
                )
            ]
            already_represented = _is_dialogue_partner(n_name, partners_list)
            if not already_represented:
                for c_existing in cleaned:
                    if not isinstance(c_existing, dict):
                        continue
                    c_lbl_low = str(c_existing.get("label") or "").lower()
                    c_t_npc = str(c_existing.get("target_npc") or "").strip().lower()
                    c_intent = str(c_existing.get("intent") or "").lower()
                    name_matched = bool(
                        c_t_npc == n_low
                        or re.search(rf"\b{re.escape(n_low)}\b", c_lbl_low)
                        or any(re.search(rf"\b{re.escape(tok)}\b", c_lbl_low) for tok in unique_tokens)
                    )
                    if not name_matched:
                        continue
                    has_social_verb = c_intent in ("dialogue_init", "dialogue_turn") or any(
                        v in c_lbl_low
                        for v in (
                            "speak",
                            "talk",
                            "ask",
                            "greet",
                            "approach",
                            "chat",
                            "confront",
                            "join",
                            "call out",
                            "introduce",
                            "check on",
                            "sit with",
                            "wave to",
                            "listen to",
                        )
                    )
                    if has_social_verb or c_t_npc == n_low:
                        c_existing["_npc_speak_choice"] = True
                        if not c_existing.get("target_npc"):
                            c_existing["target_npc"] = n_name
                        already_represented = True
                        break
            if not already_represented:
                role_suffix = f" ({n_role})" if n_role and len(n_name) + len(n_role) < 32 else ""
                missing_npc_choices.append(
                    {
                        "label": f"Speak with {n_name}{role_suffix}",
                        "stat": "NONE",
                        "requirement": 0,
                        "mp_cost": 0,
                        "intent": "dialogue_init",
                        "target_npc": n_name,
                        "_npc_speak_choice": True,
                        "is_fallback": not bool(cleaned),
                    }
                )

        if missing_npc_choices:
            if len(cleaned) + len(missing_npc_choices) > 5:
                travel_choices = []
                non_travel_choices = []
                observe_choices = []
                active_wp_leaves: set[str] = set()
                if session_id:
                    try:
                        raw_wp_locs: list[str] = []
                        for wp_row in db.get_all_session_active_waypoints(session_id) or []:
                            if isinstance(wp_row, dict) and wp_row.get("target_location"):
                                raw_wp_locs.append(str(wp_row["target_location"]))
                        _, climax_loc_tr = get_story_quest_climax_location(session_id)
                        if climax_loc_tr:
                            raw_wp_locs.append(str(climax_loc_tr))
                        for r_loc in raw_wp_locs:
                            for part in r_loc.replace("->", "➔").split("➔"):
                                p_clean = part.strip().lower()
                                if len(p_clean) >= 4 and p_clean not in ("main area", "area"):
                                    active_wp_leaves.add(p_clean)
                    except Exception:
                        pass
                for c in cleaned:
                    raw_l = c.get("label", "").lower()
                    if "observe your surroundings" in raw_l:
                        observe_choices.append(c)
                        continue
                    is_tr = any(
                        k in raw_l
                        for k in [
                            "travel ",
                            "head for ",
                            "head to ",
                            "head toward ",
                            "leave the ",
                            "slip through ",
                        ]
                    )
                    if is_tr:
                        travel_choices.append(c)
                    else:
                        non_travel_choices.append(c)
                protected_tr = []
                other_tr = []
                for tc in travel_choices:
                    tc_lbl = str(tc.get("label") or "").lower()
                    is_protected_tr = bool(
                        tc.get("is_quest_action")
                        or tc.get("is_story_quest")
                        or tc.get("quest_id")
                        or any(leaf in tc_lbl for leaf in active_wp_leaves)
                    )
                    if is_protected_tr:
                        protected_tr.append(tc)
                    else:
                        other_tr.append(tc)
                travel_choices = protected_tr + other_tr[:2]
                cleaned = non_travel_choices + travel_choices + observe_choices

            if cleaned and (
                any(
                    k in cleaned[0].get("label", "").lower()
                    for k in (
                        "step through",
                        "enter the",
                        "breach the",
                        "investigate the",
                        "set out toward",
                        "travel toward",
                        "head toward",
                        "journey toward",
                        "scout deeper",
                    )
                )
                or cleaned[0].get("stat") in ("PER", "INT", "STR", "END", "AGI", "CHA", "LUK")
            ):
                cleaned = [cleaned[0]] + missing_npc_choices + cleaned[1:]
            else:
                cleaned = missing_npc_choices + cleaned

    if session_id:
        try:
            from mechanics.world.locations.realms import get_portal_choices_at_node
            _sess_portal = db.get_session(session_id)
            _cur_nid_p = (_sess_portal or {}).get("current_node_id") or (
                db.resolve_node_id_from_location(session_id, location) if location else None
            )
            if _cur_nid_p:
                portal_opts = get_portal_choices_at_node(session_id, str(_cur_nid_p)) or []
                existing_p_keys = {
                    (
                        str(c.get("sub_intent") or "").lower(),
                        str(c.get("target_node_id") or ""),
                        str(c.get("target_realm_id") or ""),
                    )
                    for c in cleaned
                    if isinstance(c, dict)
                }
                to_add_p: list[dict] = []
                for po in portal_opts[:3]:
                    pk = (
                        str(po.get("sub_intent") or "").lower(),
                        str(po.get("target_node_id") or ""),
                        str(po.get("target_realm_id") or ""),
                    )
                    if pk not in existing_p_keys:
                        to_add_p.append(dict(po))
                        existing_p_keys.add(pk)
                if to_add_p:
                    if len(cleaned) >= 1 and cleaned[0].get("stat") in ("PER", "INT", "STR", "END", "AGI", "CHA", "LUK"):
                        cleaned = [cleaned[0]] + to_add_p + cleaned[1:]
                    else:
                        cleaned = to_add_p + cleaned
        except Exception:
            pass

    return cleaned


def _prune_absent_completed_and_unowned(
    cleaned: list[dict],
    *,
    location: str,
    char: dict | None,
    current_npcs: list | None,
    partners_list: List[str],
    session_id: int | None,
) -> list[dict]:
    """Prune absent contacts, completed sub-objective actions/sites, unowned item offers, and duplicate speak choices."""
    if session_id and cleaned:
        present_npc_tokens = set()
        if current_npcs and isinstance(current_npcs, list):
            for n in current_npcs:
                if not n:
                    continue
                n_name_val = game_engine._get_npc_name(n).lower()
                if n_name_val:
                    present_npc_tokens.add(n_name_val)
                    for tok in n_name_val.split():
                        if len(tok) > 2:
                            present_npc_tokens.add(tok)

        if partners_list:
            for dp in partners_list:
                dp_val = str(dp or "").strip().lower()
                if dp_val:
                    present_npc_tokens.add(dp_val)
                    for tok in dp_val.split():
                        if len(tok) > 2:
                            present_npc_tokens.add(tok)

        try:
            for p in db.get_session_party_npcs(session_id):
                p_name_val = str(p.get("name") or "").strip().lower()
                if p_name_val:
                    present_npc_tokens.add(p_name_val)
                    for tok in p_name_val.split():
                        if len(tok) > 2:
                            present_npc_tokens.add(tok)
        except Exception:
            pass

        present_full_names = {tok for tok in present_npc_tokens if " " in tok} | {
            str(dp or "").strip().lower() for dp in (partners_list or []) if str(dp or "").strip()
        }
        try:
            all_session_contacts = db.get_contacts(session_id)
        except Exception:
            all_session_contacts = []
        all_choice_peer_names = list(present_full_names) + [
            str(cr.get("name") or "").strip() for cr in all_session_contacts if cr.get("name")
        ]
        present_disambig_tokens: set[str] = set()
        for pfn in present_full_names:
            present_disambig_tokens |= namegen.get_unique_person_tokens(
                pfn, peer_names=all_choice_peer_names, min_len=2
            )
        for s_tok in present_npc_tokens:
            if " " not in s_tok and s_tok.rstrip(".") not in namegen.NAME_PARTICLES_AND_HONORIFICS:
                if not any(s_tok in pfn.split() for pfn in present_full_names):
                    present_disambig_tokens.add(s_tok)

        known_absent_names = set()
        absent_disambig_map: dict[str, set[str]] = {}
        for c_rec in all_session_contacts:
            c_nm = str(c_rec.get("name") or c_rec.get("npc_id") or "").strip().lower()
            if not c_nm or c_nm in present_full_names or c_nm in present_disambig_tokens:
                continue
            c_toks = namegen.get_unique_person_tokens(
                c_nm, peer_names=all_choice_peer_names, min_len=3
            )
            if not (c_toks & present_disambig_tokens):
                known_absent_names.add(c_nm)
                absent_disambig_map[c_nm] = c_toks

        if known_absent_names:
            filtered_absent_choices = []
            for c in cleaned:
                lbl = c.get("label", "").lower()
                is_phone = any(
                    pkw in lbl
                    for pkw in (
                        "[phone]",
                        "call ",
                        "text ",
                        "message ",
                        "dm ",
                        "send a message",
                        "phone call",
                    )
                )
                is_travel_back = any(
                    tv in lbl
                    for tv in (
                        "travel to",
                        "travel toward",
                        "head toward",
                        "head to",
                        "return to",
                        "go to",
                        "seek out",
                    )
                )
                if not is_phone and not is_travel_back:
                    targets_absent = False
                    for an in known_absent_names:
                        an_pats = [
                            rf"\b(?:glance|look|turn|wink|smile|nod|step|walk|reach|listen|talk|speak|converse|chat|greet|approach|meet|interview|interrogate|tell|ask|signal)\s+(?:at|to|toward|with)?\s*{re.escape(an)}\b",
                            rf"\b(?:hand|give|offer|pass|show)\s+.*?\bto\s+{re.escape(an)}\b",
                        ]
                        for an_tok in absent_disambig_map.get(an, set()):
                            if (
                                an_tok != an
                                and len(an_tok) >= 3
                                and an_tok
                                not in (
                                    "the",
                                    "and",
                                    "one",
                                    "two",
                                    "red",
                                    "old",
                                    "new",
                                    "man",
                                    "guy",
                                    "boy",
                                    "her",
                                    "she",
                                    "him",
                                    "his",
                                    "well",
                                    "will",
                                    "can",
                                    "may",
                                )
                            ):
                                an_pats.append(
                                    rf"\b(?:glance|look|turn|wink|smile|nod|step|walk|reach|listen|talk|speak|converse|chat|greet|approach|meet|interview|interrogate|tell|ask|signal)\s+(?:at|to|toward|with)?\s*{re.escape(an_tok)}\b"
                                )
                                an_pats.append(
                                    rf"\b(?:hand|give|offer|pass|show)\s+.*?\bto\s+{re.escape(an_tok)}\b"
                                )
                        for pat in an_pats:
                            if re.search(pat, lbl):
                                targets_absent = True
                                break
                        if targets_absent:
                            break
                    if targets_absent:
                        continue
                filtered_absent_choices.append(c)
            if filtered_absent_choices:
                cleaned = filtered_absent_choices

    # Completed Sub-Objective Location & Action Pruning
    if session_id and cleaned:
        try:
            active_quests = db.get_session_quests(session_id, status="Active")
            completed_site_keywords = set()
            completed_sub_ids = set()
            completed_action_phrases = []
            stopwords = {
                "enter",
                "trace",
                "source",
                "before",
                "collapses",
                "recover",
                "sanctum",
                "where",
                "which",
                "whose",
                "their",
                "trust",
                "proving",
                "threatens",
                "explain",
                "memory",
                "living",
                "ancient",
                "overgrown",
                "flooded",
                "roots",
                "forest",
                "woods",
                "party",
                "hero",
                "with",
                "from",
                "that",
                "this",
                "into",
                "after",
                "then",
                "your",
                "will",
                "have",
                "turn",
                "seek",
                "about",
                "finding",
                "learn",
                "investigate",
                "evidence",
                "order",
                "tackle",
                "report",
                "return",
                "consult",
                "records",
                "public",
                "ledger",
                "fire",
                "blue",
                "check",
                "stage",
                "task",
                "objective",
                "reach",
                "travel",
                "area",
                "place",
                "room",
            }
            for q in active_quests:
                sub_objs = q.get("sub_objectives") or []
                for so in sub_objs:
                    if isinstance(so, dict) and so.get("completed"):
                        so_id = so.get("id")
                        if so_id is not None:
                            completed_sub_ids.add(str(so_id))
                        raw_txt = str(so.get("text", ""))
                        completed_action_phrases.append(raw_txt.lower())
                        so_text = (raw_txt + " " + str(so.get("archetype", ""))).lower()
                        for token in re.findall(r"\b[a-z]{4,}\b", so_text):
                            if token not in stopwords:
                                completed_site_keywords.add(token)

            if completed_site_keywords or completed_sub_ids:
                cur_loc_lower = str(location or "").lower()
                filtered_choices = []
                for c in cleaned:
                    raw_lbl = c.get("label", "").lower()
                    raw_sub_id = (
                        c.get("sub_obj_id")
                        if c.get("sub_obj_id") is not None
                        else c.get("_raw_sub_obj_id")
                    )
                    c_sub_id = str(raw_sub_id) if raw_sub_id is not None else ""
                    if c_sub_id and c_sub_id in completed_sub_ids:
                        continue

                    is_travel_or_guide = any(
                        v in raw_lbl
                        for v in [
                            "travel",
                            "head to",
                            "head toward",
                            "journey to",
                            "journey toward",
                            "walk to",
                            "guide to",
                            "guide toward",
                            "lead to",
                            "lead toward",
                            "lead the way",
                            "return to",
                            "toward the",
                            "towards the",
                            "path to",
                            "route to",
                            "way to",
                        ]
                    )
                    targets_completed_travel = is_travel_or_guide and any(
                        kw in raw_lbl for kw in completed_site_keywords if kw not in cur_loc_lower
                    )
                    if targets_completed_travel:
                        continue

                    targets_completed_action = False
                    for phrase in completed_action_phrases:
                        p_keywords = [
                            w
                            for w in re.findall(r"\b[a-z]{4,}\b", phrase)
                            if w not in stopwords and w != "left"
                        ]
                        matched_kws = [kw for kw in p_keywords if kw in raw_lbl]
                        if len(p_keywords) >= 2 and (
                            len(matched_kws) >= 3 or len(matched_kws) == len(p_keywords)
                        ):
                            targets_completed_action = True
                            break
                    if targets_completed_action:
                        continue

                    filtered_choices.append(c)

                if len(filtered_choices) >= 2:
                    cleaned = filtered_choices
        except Exception:
            pass

    for _c_tmp in cleaned:
        if isinstance(_c_tmp, dict):
            _c_tmp.pop("_raw_sub_obj_id", None)

    # Unowned Item Offering & Inventory Possession Guardrail
    player_inv = _get_player_inventory_items(char=char, session_id=session_id)
    filtered_inventory_choices = []
    for c in cleaned:
        lbl = c.get("label", "")
        _, offered_item = _extract_offered_item_and_target(lbl)
        if offered_item:
            if _is_exempt_offering(offered_item) or _is_item_in_inventory(offered_item, player_inv):
                filtered_inventory_choices.append(c)
            continue
        filtered_inventory_choices.append(c)
    cleaned = filtered_inventory_choices

    # Deduplication & Speak-Choice Consolidation Pass
    dedup_ignore_names = list(partners_list or []) + [
        game_engine._get_npc_name(n) for n in (current_npcs or []) if n
    ]
    if cleaned:
        unique_choices = []
        seen_labels = set()
        seen_speak_npcs = set()
        for c in cleaned:
            lbl = str(c.get("label") or "").strip()
            if not lbl:
                continue
            lbl_norm = lbl.lower()
            if lbl_norm in seen_labels:
                continue
            speak_match = re.match(
                r"^(?:speak|talk|converse)\s+(?:with|to)\s+([A-Za-z0-9_\-'\s]+?)(?:\s*\(.*?\))?$",
                lbl_norm,
                re.IGNORECASE,
            )
            if speak_match:
                target_npc = speak_match.group(1).strip().lower()
                if target_npc in seen_speak_npcs:
                    continue
                seen_speak_npcs.add(target_npc)
            seen_labels.add(lbl_norm)
            unique_choices.append(c)
        cleaned = deduplicate_redundant_choices(unique_choices, ignore_names=dedup_ignore_names)

    return cleaned


def _finalize_post_enrichment_filters(
    cleaned: list[dict],
    *,
    scenario: str,
    location: str,
    char: dict | None,
    dialogue_partner: str | list | None,
    partners_list: List[str],
    current_npcs: list | None,
    session_id: int | None,
    departed_npcs: list | None,
    is_non_combat: bool,
    intimate_ctx: dict,
) -> list[dict]:
    """Sleep gating, quest waypoint tagging, universal intent stamping, replenishment, and stealth pruning."""
    from mechanics.narrative.choice_generator import (
        generate_procedural_scene_choices,
        get_scenario_dialogue_fallbacks,
    )
    from mechanics.narrative.intent import IntentContext, resolve_action_intent
    from mechanics.social.anomalous_npc_tags import (
        TAG_FOLKLORE_VILLAGER,
        TAG_SPECIAL_AGENT,
        classify_anomalous_npc_tag,
    )
    from mechanics.social.conversation_choices import (
        get_npc_departure_states,
        is_choice_allowed_for_partner_profile,
        resolve_partner_conversation_profile,
    )
    from mechanics.stealth import (
        any_actor_hidden,
        is_stealth_choice_locked_out,
        is_stealth_context_warranted,
    )
    from mechanics.system.time_engine import (
        format_clock,
        get_location_sleep_context,
        is_nap_action,
        is_sleep_action,
        is_sleep_time,
    )
    from mechanics.world.waypoints import tag_and_enrich_quest_choices
    from mechanics.world.world_schedule import get_scenario_wake_minute

    is_active_intimate = bool(intimate_ctx["is_active_intimate"])
    bp = intimate_ctx["bp"]
    dedup_ignore_names = list(partners_list or []) + [
        game_engine._get_npc_name(n) for n in (current_npcs or []) if n
    ]

    # 8. Nighttime / Bedtime Sleep Action Gating & Auto-Injection
    if session_id and not partners_list:
        try:
            _, curr_min, _ = db.get_session_time(session_id)
            sleep_ctx = get_location_sleep_context(location, scenario=scenario, session_id=session_id)
            if not sleep_ctx.get("can_sleep", False):
                cleaned = [
                    c
                    for c in cleaned
                    if not is_sleep_action(c.get("label", ""))
                    and not is_nap_action(c.get("label", ""))[0]
                    and c.get("intent") != "rest_sleep"
                ]
            elif is_sleep_time(curr_min, scen_key=scenario):
                has_sleep = any(is_sleep_action(c.get("label", "")) for c in cleaned)
                if not has_sleep:
                    wake_clock = format_clock(get_scenario_wake_minute(scenario))
                    surf = sleep_ctx.get("surface", "bed")
                    if surf == "bed":
                        lbl = f"🛏️ [Rest] Sleep in bed until morning ({wake_clock} AM)"
                    elif surf == "couch":
                        lbl = f"🛋️ [Rest] Sleep on sofa until morning ({wake_clock} AM)"
                    else:
                        lbl = f"🏕️ [Rest] Camp and sleep until morning ({wake_clock} AM)"
                    cleaned.append(
                        {
                            "label": lbl,
                            "stat": "NONE",
                            "requirement": 0,
                            "mp_cost": 0,
                            "is_fallback": False,
                            "intent": "rest_sleep",
                        }
                    )
        except Exception:
            pass

    # 8.5. Dynamic Quest Waypoint Metadata Tagging
    if session_id and location and cleaned and not is_active_intimate:
        try:
            tagged = tag_and_enrich_quest_choices(
                cleaned,
                session_id,
                location,
                scen_key=scenario,
                char=char,
                dialogue_partner=partners_list if partners_list else dialogue_partner,
                current_npcs=current_npcs,
                allow_fallback=False,
            )
            if tagged:
                for tc in tagged:
                    if isinstance(tc, dict) and tc.get("label"):
                        tc["label"] = _strip_leading_emojis(tc["label"])[:190]
                cleaned = deduplicate_redundant_choices(tagged, ignore_names=dedup_ignore_names)
        except Exception:
            pass

    # 9. Universal Intent Stamping
    try:
        npc_names = [game_engine._get_npc_name(n) for n in (current_npcs or []) if n]
        ctx = IntentContext(
            dialogue_partner=partners_list[0] if partners_list else "",
            dialogue_partners=partners_list,
            present_npcs=npc_names,
            scenario=scenario,
        )
        for c in cleaned:
            parsed = resolve_action_intent(c, ctx)
            if not c.get("intent") or c.get("intent") == "general_action":
                c["intent"] = parsed.category.value
            if not c.get("sub_intent") and parsed.sub_target:
                c["sub_intent"] = parsed.sub_target
            if not c.get("target_npc") and parsed.target_entity:
                c["target_npc"] = parsed.target_entity
            elif not c.get("target_npc") and partners_list:
                lbl_low = str(c.get("label", "")).lower()
                if any(re.search(rf"\b{pr}\b", lbl_low) for pr in ("her", "him", "she", "he", "them")) or parsed.category.value in (
                    "dialogue",
                    "social_interaction",
                    "flirt",
                    "gift_offer",
                ):
                    c["target_npc"] = partners_list[0]
    except Exception:
        pass

    if departed_npcs:
        departed_clean = [str(d).lower().strip() for d in departed_npcs if d]
        if departed_clean:
            filtered_departed = []
            for c in cleaned:
                lbl = str(c.get("label", "")).lower()
                tgt = str(c.get("target_npc", "")).lower()
                targets_departed = False
                for dep in departed_clean:
                    dep_first = _get_effective_first_name(dep)
                    if (
                        dep == tgt
                        or (dep_first and dep_first == tgt)
                        or re.search(rf"\b{re.escape(dep)}\b", lbl)
                        or (len(dep_first) >= 3 and re.search(rf"\b{re.escape(dep_first)}\b", lbl))
                    ):
                        targets_departed = True
                        break
                if not targets_departed:
                    filtered_departed.append(c)
            cleaned = filtered_departed

    partner_profile = None
    if session_id and partners_list and not is_active_intimate:
        try:
            sess_obj = db.get_session(session_id) or {
                "id": session_id,
                "scenario": scenario,
                "current_location": location,
            }
            partner_profile = resolve_partner_conversation_profile(
                sess_obj,
                partners_list[0],
                party=[(char, [])] if isinstance(char, dict) else None,
                current_npcs=current_npcs,
            )
            dep_st = get_npc_departure_states(sess_obj)
            allow_stay = any(
                dep_st.get(re.sub(r"\s+", " ", str(p).strip().lower()), {}).get("stage")
                in ("stage_1_warning", "stage_2_ultimatum")
                for p in partners_list
            )
            cleaned = [
                c
                for c in cleaned
                if is_choice_allowed_for_partner_profile(
                    c, partner_profile, session=sess_obj, allow_convince_stay=allow_stay
                )
            ]
        except Exception:
            partner_profile = None

    in_dlg = bool(partners_list)
    substantive_now = [c for c in cleaned if not is_exempt_free_action(c, in_dialogue_mode=in_dlg)]
    exit_now = [c for c in cleaned if is_exempt_free_action(c, in_dialogue_mode=in_dlg)]

    if in_dlg and not exit_now and partners_list:
        if len(partners_list) == 1:
            exit_label = f"Thank {partners_list[0]}, excuse yourself, and look around the room"
        elif len(partners_list) == 2:
            exit_label = f"Thank {partners_list[0]} and {partners_list[1]}, excuse yourself, and look around the room"
        else:
            exit_label = "Thank everyone, excuse yourself, and look around the room"
        exit_now.append(
            {
                "label": exit_label,
                "stat": "NONE",
                "requirement": 0,
                "mp_cost": 0,
                "is_fallback": False,
                "intent": "dialogue_exit",
            }
        )
        cleaned = substantive_now + exit_now

    needs_replenishment = (len(substantive_now) < 3) if in_dlg else (len(cleaned) < 4)
    if needs_replenishment:
        existing_labels = {str(c.get("label", "")).strip().lower() for c in cleaned}
        if partners_list:
            primary_partner = partners_list[0]
            if is_active_intimate and bp:
                dialogue_fallbacks = [dict(fb_c) for fb_c in bp["choices"]]
            else:
                bystanders = [
                    n
                    for n in (current_npcs or [])
                    if game_engine._get_npc_name(n)
                    and not _is_dialogue_partner(game_engine._get_npc_name(n), partners_list)
                ]
                dialogue_fallbacks = get_scenario_dialogue_fallbacks(
                    primary_partner,
                    scenario=scenario,
                    present_bystanders=bystanders,
                    location=location,
                    char=char,
                    affinity_score=int(partner_profile["score"]) if partner_profile else 0,
                    relationship_track=str(partner_profile["track"])
                    if partner_profile
                    else "platonic",
                    is_private_meetup=bool(partner_profile["is_private_meetup"])
                    if partner_profile
                    else False,
                )
            for fb in dialogue_fallbacks:
                fb_label = str(fb.get("label", "")).strip().lower()
                if fb_label not in existing_labels:
                    if is_exempt_free_action(fb, in_dialogue_mode=True):
                        if not any(ex.get("stat") in ("NONE", "FREE") for ex in exit_now):
                            exit_now.append(fb)
                    else:
                        substantive_now.append(fb)
                    existing_labels.add(fb_label)
                    if len(substantive_now) >= 4:
                        break
            cleaned = substantive_now + exit_now
        else:
            fallbacks = generate_procedural_scene_choices(scenario, location, char)
            for fb in fallbacks:
                fb_label = str(fb.get("label", "")).strip().lower()
                if fb_label and fb_label not in existing_labels:
                    if is_exempt_free_action(fb, in_dialogue_mode=False):
                        fb["stat"] = "NONE"
                        fb["requirement"] = 0
                        fb["mp_cost"] = 0
                    cleaned.append(fb)
                    existing_labels.add(fb_label)
                    if len(cleaned) >= 4:
                        break

    if is_non_combat:
        cleaned = [
            c
            for c in cleaned
            if not (
                c.get("intent") == "party_recruit"
                or matches_keyword_boundary(c.get("label", "").lower(), _RECRUIT_CHOICE_KEYWORDS)
            )
        ]
    elif session_id:
        try:
            if scenario_data.is_anomalous_incursions_scenario(scenario):
                filtered_anom_rec = []
                for c in cleaned:
                    c_lbl_low = str(c.get("label", "") if isinstance(c, dict) else "").lower()
                    is_rec_c = isinstance(c, dict) and (
                        c.get("intent") == "party_recruit"
                        or matches_keyword_boundary(c_lbl_low, _RECRUIT_CHOICE_KEYWORDS)
                    )
                    if is_rec_c:
                        t_n = str(c.get("target_npc") or "").strip()
                        if not t_n and partners_list:
                            for p_cand in partners_list:
                                if p_cand and p_cand.lower() in c_lbl_low:
                                    t_n = p_cand
                                    break
                            if not t_n and len(partners_list) == 1:
                                t_n = partners_list[0]
                        if t_n and classify_anomalous_npc_tag(
                            t_n, session_id=session_id, scen_key=scenario
                        ) not in (TAG_SPECIAL_AGENT, TAG_FOLKLORE_VILLAGER):
                            continue
                    filtered_anom_rec.append(c)
                cleaned = filtered_anom_rec
        except Exception:
            pass

    if session_id and partners_list:
        try:
            for p in partners_list:
                if p and db.get_contact_request_cooldown(session_id, p) > 0:
                    p_low = p.lower().strip()
                    p_first = p_low.split()[0] if p_low else ""
                    cleaned = [
                        c
                        for c in cleaned
                        if not (
                            any(
                                kw in str(c.get("label", "") if isinstance(c, dict) else c).lower()
                                for kw in ("phone number", "contact info", "line id")
                            )
                            and (
                                p_low
                                in str(c.get("label", "") if isinstance(c, dict) else c).lower()
                                or (
                                    p_first
                                    and p_first
                                    in str(c.get("label", "") if isinstance(c, dict) else c).lower()
                                )
                                or len(partners_list) == 1
                            )
                        )
                    ]
        except Exception:
            pass

    # Prune unwarranted stealth choices and locked-out failed stealth choices
    try:
        sess_st_check = (
            db.get_session(session_id)
            if session_id
            else {"scenario": scenario, "current_location": location}
        )
        if isinstance(sess_st_check, dict):
            sess_st_check = dict(sess_st_check)
            if location:
                sess_st_check["current_location"] = location
            if scenario:
                sess_st_check["scenario"] = scenario
        st_warranted = is_stealth_context_warranted(sess_st_check) or bool(
            any_actor_hidden(sess_st_check)
        )
        filtered_st: list[dict] = []
        for c in cleaned:
            if not isinstance(c, dict):
                continue
            c_lbl = str(c.get("label") or "")
            c_lbl_low = c_lbl.lower()
            if is_stealth_choice_locked_out(sess_st_check, label=c_lbl):
                continue
            is_barrier_c = bool(
                c.get("_priority_slot")
                or c.get("_stealth_injected")
                or c.get("is_phase2_choice")
                or "outside the locked entrance" in str(location or "").lower()
            )
            if not st_warranted and not is_barrier_c:
                if c.get("is_quest_action"):
                    if any(
                        tag in c_lbl_low
                        for tag in (
                            "[stealth & infiltration]",
                            "[diversion & stealth]",
                            "[careful bypass]",
                        )
                    ):
                        new_lbl = re.sub(
                            r"\[(stealth & infiltration|diversion & stealth|careful bypass)\]",
                            "[Methodical Survey]",
                            c_lbl,
                            flags=re.IGNORECASE,
                        )
                        new_lbl = re.sub(
                            r"\bslip past the sentries and\b",
                            "carefully inspect the area to",
                            new_lbl,
                            flags=re.IGNORECASE,
                        )
                        new_lbl = re.sub(
                            r"\busing stealth and careful footing\b",
                            "with careful observation",
                            new_lbl,
                            flags=re.IGNORECASE,
                        )
                        c["label"] = new_lbl
                        c["stat"] = "PER"
                        c["approach"] = "direct"
                        c["is_stealth"] = False
                        c.pop("stance", None)
                else:
                    is_unwarranted_stealth_c = bool(
                        str(c.get("intent") or "").lower() in ("stealth_covert", "stealth")
                        or str(c.get("action_category") or "").lower() == "stealth"
                        or bool(c.get("is_stealth"))
                        or c.get("stance") == "stealth"
                        or any(
                            kw in c_lbl_low
                            for kw in (
                                "shadow step",
                                "[stealth",
                                "[diversion & stealth]",
                                "sneak past",
                                "sneak into",
                                "sneak through",
                                "creep past",
                                "creep through",
                                "infiltrate ",
                                "pickpocket ",
                                "silent takedown",
                                "lockpick ",
                                "pick the lock",
                                "slip past the sentr",
                                "slip past the guard",
                            )
                        )
                    )
                    if is_unwarranted_stealth_c:
                        continue
            filtered_st.append(c)
        if filtered_st or not cleaned:
            cleaned = filtered_st
    except Exception:
        pass

    return cleaned


_UNSET = object()


def clean_choices_impl(
    cls,
    choices: Any = _UNSET,
    scenario: str = "fantasy",
    location: str = "",
    char: dict = None,
    dialogue_partner: str = None,
    current_npcs: list = None,
    session_id: int = None,
    departed_npcs: list = None,
) -> list:
    if choices is _UNSET:
        choices = cls if isinstance(cls, list) else []
        cls = None
    is_non_combat = (
        scenario_data.is_non_combat_scenario(scenario)
        or scenario_data.has_tag(scenario, "non_combat")
        or not scenario_data.is_mechanic_enabled(scenario, "tactical_combat")
    )

    cleaned, partners_list = _parse_and_normalize_raw_choices(
        cls,
        choices,
        scenario=scenario,
        location=location,
        char=char,
        dialogue_partner=dialogue_partner,
        current_npcs=current_npcs,
        session_id=session_id,
        is_non_combat=is_non_combat,
    )
    raw_choices_empty = not bool(cleaned)

    intimate_ctx = _hydrate_intimate_scene_state(
        partners_list=partners_list,
        session_id=session_id,
        char=char,
        raw_choices_empty=raw_choices_empty,
    )

    if (cleaned or intimate_ctx["is_active_intimate"]) and partners_list:
        cleaned = _filter_and_enrich_dialogue_choices(
            cleaned,
            partners_list=partners_list,
            intimate_ctx=intimate_ctx,
            scenario=scenario,
            location=location,
            char=char,
            current_npcs=current_npcs,
            session_id=session_id,
            is_non_combat=is_non_combat,
            raw_choices_empty=raw_choices_empty,
        )
    else:
        cleaned = _normalize_and_inject_open_hub_choices(
            cleaned,
            scenario=scenario,
            location=location,
            char=char,
            current_npcs=current_npcs,
            partners_list=partners_list,
            session_id=session_id,
        )

    cleaned = _prune_absent_completed_and_unowned(
        cleaned,
        location=location,
        char=char,
        current_npcs=current_npcs,
        partners_list=partners_list,
        session_id=session_id,
    )

    return _finalize_post_enrichment_filters(
        cleaned,
        scenario=scenario,
        location=location,
        char=char,
        dialogue_partner=dialogue_partner,
        partners_list=partners_list,
        current_npcs=current_npcs,
        session_id=session_id,
        departed_npcs=departed_npcs,
        is_non_combat=is_non_combat,
        intimate_ctx=intimate_ctx,
    )


def sanitize_and_diversify_choices(
    choices: list,
    scenario: str = "fantasy",
    location: str = "",
    char: dict = None,
    dialogue_partner: str | list = None,
    current_npcs: list = None,
    session_id: int = None,
    departed_npcs: list = None,
) -> list:
    """Framework-agnostic entrypoint for cleaning and diversifying scene choices."""
    return clean_choices_impl(
        None,
        choices,
        scenario=scenario,
        location=location,
        char=char,
        dialogue_partner=dialogue_partner,
        current_npcs=current_npcs,
        session_id=session_id,
        departed_npcs=departed_npcs,
    )
