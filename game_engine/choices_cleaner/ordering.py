"""Canonical choice tier sorting, label tag sanitization, scaling, and free-utility injection."""
from __future__ import annotations

import re
from typing import Any, Dict, Tuple

import game_engine


def _sanitize_choice_labels(choices: list) -> list:
    """Strip any leaked internal tags or raw HP/MP/DC tokens from final choice labels."""
    for ch in choices:
        if isinstance(ch, dict) and isinstance(ch.get("label"), str) and ch["label"]:
            ch["label"] = (
                game_engine.sanitize_internal_tags_and_raw_stats(ch["label"]).strip()[:190]
                or ch["label"]
            )
    return choices


def order_choices_canonically(
    choices: list,
    *,
    in_dialogue: bool = False,
    in_combat: bool = False,
    in_intimate: bool = False,
) -> list:
    """Stably sort non-combat/non-intimate choices: Barriers -> Story Quest -> Bounty/Quest -> Engine Priority -> General -> Utilities/Exits."""
    if not choices:
        return []
    items = list(choices)
    if in_combat or in_intimate or any(not isinstance(c, dict) for c in items):
        return items
    if any(
        c.get("_intimate_scene_choice")
        or c.get("_stage_2_ultimatum_locked")
        or str(c.get("sub_intent") or "").startswith("combat_")
        or str(c.get("choice_type") or "") in ("attack", "spell", "tactic", "flee")
        for c in items
    ):
        return items

    def _sort_key(c: Dict[str, Any]) -> Tuple[int, int]:
        lbl_low = str(c.get("label") or "").strip().lower()
        intent_low = str(c.get("intent") or "").strip().lower()
        sub_intent_low = str(c.get("sub_intent") or "").strip().lower()
        stat_up = str(c.get("stat") or "NONE").strip().upper()
        qid_up = str(c.get("quest_id") or "").strip().upper()
        ctype_low = str(c.get("contract_type") or "").strip().lower()

        is_q_handoff = bool(c.get("_quest_dialogue_handoff"))
        is_verified_q = bool(
            c.get("is_quest_action")
            or c.get("_python_verified_quest")
            or is_q_handoff
            or (c.get("incursion_action") and qid_up)
        )
        is_story_q = bool(c.get("is_story_quest") or (is_verified_q and qid_up.startswith("SQ-")))
        is_climax_q = bool(c.get("is_climax_action") or ctype_low == "climax")
        is_premature_climax = bool(c.get("is_premature_climax") or c.get("rush_climax"))

        # Tier 0: Hard scene locks / barriers / restraint break-free overrides
        if (
            c.get("_access_barrier")
            or "break free from" in lbl_low
            or "cut the bindings" in lbl_low
            or lbl_low.startswith("cover yourself")
        ):
            return (0, 0)

        # Tier 1: Main / Story Quest (ALWAYS FIRST)
        if is_climax_q and not is_premature_climax:
            return (1, 0)
        if is_story_q and not is_premature_climax:
            return (1, 1)
        if (is_climax_q or is_story_q) and is_premature_climax:
            return (1, 2)

        # Tier 2: Bounty / Side Quest / Caseboard Synthesis (IMMEDIATELY AFTER STORY QUEST)
        if is_verified_q:
            return (2, 0)
        if sub_intent_low == "deduce_clues" or bool(c.get("clue_pair_ids")):
            return (2, 1)

        # Tier 5: Trailing exits & free utility actions
        if not is_q_handoff and (
            c.get("_pinned_dialogue_exit")
            or intent_low == "dialogue_exit"
            or bool(c.get("ends_dialogue"))
        ):
            return (5, 2)
        if "observe your surroundings" in lbl_low or (
            intent_low == "area_scout"
            and stat_up in ("FREE", "NONE", "")
            and int(c.get("requirement") or 0) <= 0
        ):
            return (5, 1)
        if (
            sub_intent_low == "redress"
            or "redress / get dressed" in lbl_low
            or "put down what you are carrying" in lbl_low
            or "retrieve your clothes and get dressed" in lbl_low
        ):
            return (5, 0)

        # Dialogue Band 3 Pre-Exit Utilities (stay right before dialogue_exit)
        if in_dialogue and (
            intent_low
            in ("phone_contact_exchange", "party_recruit", "join_activity", "epistemic_containment")
            or bool(c.get("_convince_stay") or c.get("departure_action") == "convince_stay")
            or bool(
                c.get("is_privacy_nudge")
                or c.get("_privacy_nudge")
                or sub_intent_low == "privacy_nudge"
            )
            or "walk with " in lbl_low
            or "for privacy" in lbl_low
            or (intent_low == "movement" and "quieter" in lbl_low)
        ):
            return (4, 1)

        # Tier 3: Non-quest priority engine slots & ambient scene encounters (open exploration)
        if not in_dialogue:
            if c.get("_priority_slot"):
                return (3, 0)
            if any(k in lbl_low for k in ("[meetup]", "[wait]")):
                return (3, 1)
            if intent_low in ("anomalous_incursion_action", "anomalous_site_action") or bool(
                c.get("site_action") or c.get("site_id")
            ):
                return (3, 2)

        # Tier 4: Contextual roleplay, skill checks, present-NPC speak, and non-quest travel
        return (4, 0)

    return sorted(items, key=_sort_key)


def _scale_open_exploration_choices(merged_choices: list[dict], eff_npcs: list) -> list[dict]:
    """Preserve priority slots, quest actions, and present-NPC speak prompts while capping generic filler."""
    present_npc_lowers = {
        game_engine._get_npc_name(n).strip().lower()
        for n in (eff_npcs or [])
        if n and game_engine._get_npc_name(n)
    }

    def _is_essential_open_choice(ch: dict) -> bool:
        if not isinstance(ch, dict):
            return False
        if (
            ch.get("_priority_slot")
            or ch.get("is_quest_action")
            or ch.get("is_climax_action")
            or ch.get("_npc_speak_choice")
        ):
            return True
        t_npc_low = str(ch.get("target_npc") or "").strip().lower()
        ch_lbl_low = str(ch.get("label") or "").strip().lower()
        if t_npc_low and t_npc_low in present_npc_lowers:
            return True
        if ch_lbl_low.startswith(
            ("speak with ", "talk to ", "talk with ", "approach ", "greet ")
        ):
            if any(p_nm in ch_lbl_low for p_nm in present_npc_lowers if p_nm):
                return True
        return False

    essential_count = sum(1 for ch in merged_choices if _is_essential_open_choice(ch))
    max_filler = 3 if essential_count >= 3 else max(2, 5 - essential_count)
    filler_kept = 0
    scaled_choices: list[dict] = []
    for ch in merged_choices:
        if len(scaled_choices) >= 22:
            break
        if _is_essential_open_choice(ch):
            scaled_choices.append(ch)
        elif filler_kept < max_filler:
            filler_kept += 1
            scaled_choices.append(ch)
    return scaled_choices


def _append_utility_free_actions(
    merged_choices: list[dict],
    *,
    party: list | None,
    actors: dict,
    carrying_tether: str | None,
    in_active_intimate_turn: bool,
    phys: dict,
) -> list[dict]:
    """Append Redress, Put Down Burden, and Dropped-Item Pickup utility actions."""
    from mechanics.social.physical_state import _match_actor_key

    for entry in party or []:
        char_obj = entry[0] if isinstance(entry, (tuple, list)) else entry
        if not isinstance(char_obj, dict) or not char_obj.get("name"):
            continue
        c_name = char_obj["name"]
        m_key = _match_actor_key(c_name, actors)
        if m_key in actors:
            cloth = actors[m_key].get("clothing", {})
            top = str(cloth.get("top", "")).lower()
            bottom = str(cloth.get("bottom", "")).lower()
            if any(
                w in top or w in bottom
                for w in ("none", "stripped", "removed", "naked", "bare", "undressed")
            ):
                if not any(
                    "redress" in str(c.get("label", "")).lower()
                    or "get dressed" in str(c.get("label", "")).lower()
                    for c in merged_choices
                ):
                    merged_choices.append(
                        {
                            "label": f"Redress / Get dressed ({c_name})",
                            "stat": "FREE",
                            "requirement": 0,
                            "mp_cost": 0,
                            "intent": "general_action",
                            "sub_intent": "redress",
                            "_server_stamped": True,
                        }
                    )

    if carrying_tether:
        merged_choices.append(
            {
                "label": f"Put down what you are carrying / {carrying_tether}",
                "stat": "FREE",
                "requirement": 0,
                "mp_cost": 0,
                "intent": "general_action",
                "_server_stamped": True,
            }
        )

    if not in_active_intimate_turn:
        pickable_candidates: list[tuple[str, str]] = []
        seen_pick_lows: set[str] = set()
        for d_item in (phys.get("dropped_items") or [] if isinstance(phys, dict) else []):
            raw_d = (
                str(d_item.get("name") or "").strip()
                if isinstance(d_item, dict)
                else str(d_item or "").strip()
            )
            clean_d = re.sub(
                r"\s*\[(?:GEAR|ITEM|CONSUMABLE|SPELLBOOK|DIGITAL)_JSON:.*$",
                "",
                raw_d,
                flags=re.IGNORECASE,
            ).strip()
            if clean_d and clean_d.lower() not in seen_pick_lows:
                seen_pick_lows.add(clean_d.lower())
                pickable_candidates.append((clean_d, raw_d))
        props_map_ch = (
            phys.get("props") if isinstance(phys, dict) and isinstance(phys.get("props"), dict) else {}
        )
        for pk, pv in props_map_ch.items():
            clean_pk = str(pk or "").strip()
            state_low = str(pv or "").strip().lower()
            if (
                clean_pk
                and clean_pk.lower() not in seen_pick_lows
                and any(
                    w in state_low
                    for w in (
                        "dropped",
                        "floor",
                        "ground",
                        "table",
                        "desk",
                        "counter",
                        "loose",
                        "discarded",
                        "left behind",
                    )
                )
            ):
                seen_pick_lows.add(clean_pk.lower())
                pickable_candidates.append((clean_pk, clean_pk))
        existing_pick_lbls = {
            str(c.get("label") or "").strip().lower()
            for c in merged_choices
            if isinstance(c, dict)
        }
        for clean_nm, raw_nm in pickable_candidates[:3]:
            pick_lbl = f"Pick up {clean_nm}"
            if pick_lbl.lower() not in existing_pick_lbls and not any(
                clean_nm.lower() in ex and "pick up" in ex for ex in existing_pick_lbls
            ):
                merged_choices.append(
                    {
                        "label": pick_lbl,
                        "stat": "FREE",
                        "requirement": 0,
                        "mp_cost": 0,
                        "intent": "general_action",
                        "sub_intent": "pickup_item",
                        "pickup_item_name": raw_nm,
                        "_server_stamped": True,
                    }
                )
                existing_pick_lbls.add(pick_lbl.lower())

    return merged_choices
