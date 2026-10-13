from .generation import get_narrative_requirements, log
from .constants import *
from mechanics.world.locations import *
from mechanics.social.persona import *
from mechanics.narrative.intent import *
from .dialogue import _build_dialogue_prompt_block, _compute_dialogue_intent
from .prompts import _build_quest_and_bounty_directives, _build_player_actions_text, _build_history_context
from game_engine.turn_context import TurnContext
import json
import random
from config import LLM_PASS2_TIMEOUT
import scenario_data
from game_engine.core import SYSTEM_PROMPT, OUTCOME_SCHEMA, is_nsfw_scenario, uses_nsfw_model
import namegen
from mechanics.combat.merchant import merchant_prompt_note
import logging
import game_engine
import re
from models.llm_schemas import TurnOutcome, ActionClassification, OpeningScene


def _get_enemy_base_name(name: str) -> str:
    return re.sub(r'\s+(?:#?\d+|[A-Z])$', '', str(name or "").strip())


def _is_enemy_mentioned_in_narrative(enemy_name: str, narrative_text: str) -> bool:
    base = _get_enemy_base_name(enemy_name)
    if not base:
        return True
    nar_low = str(narrative_text or "").lower()
    base_low = base.lower()
    if base_low in nar_low:
        return True
    tokens = [w for w in re.split(r'[\s\-]+', base_low) if len(w) >= 4]
    if tokens:
        head_noun = tokens[-1]
        if re.search(rf'\b{re.escape(head_noun)}s?\b', nar_low):
            return True
    return False


def _format_enemy_with_article(name: str) -> str:
    base = _get_enemy_base_name(name)
    if not base:
        return "a hostile enemy"
    low = base.lower()
    if low.startswith(("the ", "a ", "an ")):
        return base
    article = "an" if low[0] in "aeiou" else "a"
    return f"{article} {base}"


def _join_natural(items: list[str]) -> str:
    clean = [str(x).strip() for x in items if str(x).strip()]
    if not clean:
        return ""
    if len(clean) == 1:
        return clean[0]
    if len(clean) == 2:
        return f"{clean[0]} and {clean[1]}"
    return f"{', '.join(clean[:-1])}, and {clean[-1]}"


def ensure_enemy_encounter_narrative(
    result: dict,
    session: dict,
    party: list,
    actions: list = None,
    pre_turn_enemy_names: set = None,
) -> tuple[dict, str]:
    """Guarantees that whenever an enemy is encountered on a turn (or active hostiles are present
    and completely omitted from the LLM prose), the narrative explicitly describes how the enemy
    appeared and how the player and any present characters/NPCs react to the encounter."""
    if not isinstance(result, dict):
        return result, ""
    if result.get("_combat_resolved_notice"):
        return result, ""

    raw_enemies = result.get("nearby_enemies")
    if raw_enemies is None:
        raw_enemies = session.get("nearby_enemies") or []
    active_enemies = [
        m for m in (raw_enemies or [])
        if isinstance(m, dict) and m.get("hp", 1) > 0 and m.get("name")
    ]
    if not active_enemies:
        return result, ""

    pre_names = {str(n).lower() for n in (pre_turn_enemy_names or set())}
    newly_spawned = [
        m for m in active_enemies
        if _get_enemy_base_name(m.get("name", "")).lower() not in pre_names
    ]

    outcome_nar = str(result.get("outcome_narrative") or "").strip()
    next_nar = str(result.get("next_narrative") or result.get("narrative") or "").strip()
    combined_nar = f"{outcome_nar}\n{next_nar}".strip()

    if newly_spawned:
        missing_enemies = [
            m for m in newly_spawned
            if not _is_enemy_mentioned_in_narrative(m.get("name", ""), combined_nar)
        ]
    else:
        any_mentioned = any(
            _is_enemy_mentioned_in_narrative(m.get("name", ""), combined_nar)
            for m in active_enemies
        )
        missing_enemies = list(active_enemies) if not any_mentioned else []

    party_names = []
    for entry in (party or []):
        c_obj = entry[0] if isinstance(entry, (tuple, list)) else entry
        if isinstance(c_obj, dict) and c_obj.get("name"):
            party_names.append(str(c_obj["name"]).strip())
    lead_player = party_names[0] if party_names else "The adventurer"
    other_players = party_names[1:]

    enemy_base_lowers = {_get_enemy_base_name(m.get("name", "")).lower() for m in active_enemies}
    player_lowers = {p.lower() for p in party_names}
    raw_npcs = result.get("npcs_present")
    if raw_npcs is None:
        raw_npcs = session.get("current_npcs") or []
    present_npc_names = []
    for n in (raw_npcs or []):
        n_name = game_engine._get_npc_name(n) if n else ""
        if not n_name or n_name.lower() == "none":
            continue
        if n_name.lower() in enemy_base_lowers or n_name.lower() in player_lowers:
            continue
        if n_name not in present_npc_names:
            present_npc_names.append(n_name)

    raw_loc = str(result.get("location") or session.get("current_location") or "the area").strip()
    loc_parts = [p.strip() for p in raw_loc.split("➔") if p.strip()]
    if len(loc_parts) >= 2:
        loc_display = loc_parts[1] if loc_parts[-1].lower() in ("main area", "entrance", "exterior", "interior") else loc_parts[-1]
    elif loc_parts:
        loc_display = loc_parts[0]
    else:
        loc_display = "the area"

    appended_paragraph = ""
    if missing_enemies:
        formatted_enemies = []
        seen_bases = set()
        for m in missing_enemies:
            b_name = _get_enemy_base_name(m.get("name", ""))
            if b_name.lower() not in seen_bases:
                seen_bases.add(b_name.lower())
                formatted_enemies.append(_format_enemy_with_article(b_name))
        enemy_list_str = _join_natural(formatted_enemies)
        is_plural_enemies = len(formatted_enemies) > 1
        threat_noun = "hostile figures emerge" if is_plural_enemies else "a hostile threat emerges"

        appearance_sentence = (
            f"Before another moment can pass at {loc_display}, the atmosphere shifts violently as {threat_noun} "
            f"from the surrounding approaches—{enemy_list_str} suddenly lunging into view to spring an ambush and cut off any easy retreat!"
        )

        if present_npc_names:
            npc_str = _join_natural(present_npc_names)
            npc_verb = (
                "tense sharply at the sudden ambush, calling out urgent warnings and shifting"
                if len(present_npc_names) > 1
                else "tenses sharply at the sudden ambush, calling out an urgent warning and shifting"
            )
            actor_str = _join_natural([lead_player] + other_players)
            actor_verb = (
                "immediately pivot toward the emerging danger and drop into combat-ready stances with weapons drawn"
                if other_players
                else "immediately pivots toward the emerging danger and drops into a combat-ready stance with weapon drawn"
            )
            reaction_sentence = (
                f"{actor_str} {actor_verb}, while {npc_str} {npc_verb} into a defensive position as the confrontation erupts."
            )
        elif other_players:
            actor_str = _join_natural([lead_player] + other_players)
            reaction_sentence = (
                f"{actor_str} immediately pivot toward the emerging danger, drawing their weapons and dropping into a tight defensive formation as the confrontation erupts."
            )
        else:
            reaction_sentence = (
                f"{lead_player} immediately pivots toward the emerging danger, drawing their weapon and dropping into a combat-ready stance as the confrontation erupts."
            )

        appended_paragraph = f"{appearance_sentence} {reaction_sentence}"
    elif newly_spawned and present_npc_names:
        # Enemies were named by the LLM, but verify present NPCs' reaction wasn't omitted
        nar_low = combined_nar.lower()
        unmentioned_npcs = [
            n for n in present_npc_names
            if n.lower() not in nar_low and not any(tok in nar_low for tok in n.lower().split() if len(tok) >= 4)
        ]
        if unmentioned_npcs:
            npc_str = _join_natural(unmentioned_npcs)
            npc_verb = "react" if len(unmentioned_npcs) > 1 else "reacts"
            appended_paragraph = (
                f"Beside {lead_player}, {npc_str} {npc_verb} immediately to the sudden emergence of the hostiles, "
                f"calling out a sharp warning and bracing in a defensive posture as battle is joined."
            )

    if appended_paragraph:
        if next_nar:
            result["next_narrative"] = f"{next_nar}\n\n{appended_paragraph}"
        else:
            result["next_narrative"] = appended_paragraph
        if result.get("narrative"):
            result["narrative"] = result["next_narrative"]

    return result, appended_paragraph


async def resolve_turn(session: dict, party: list, actions: list, stream_callback=None, is_retry: bool = False) -> TurnOutcome:
    from mechanics.system.time_engine import format_llm_time_context, calculate_action_time_cost, advance_time, apply_sleep_rest, is_sleep_action
    session_id_val = session.get('id')
    ctx = TurnContext(session_id_val, session)

    pre_turn_enemy_names = {
        _get_enemy_base_name(m.get("name", "")).lower()
        for m in (session.get("nearby_enemies") or [])
        if isinstance(m, dict) and m.get("hp", 1) > 0 and m.get("name")
    }

    actions_text = _build_player_actions_text(actions, session=session)

    new_partners, has_exited_convo = _compute_dialogue_intent(session, actions)

    import db
    from mechanics.world.mobility import get_session_dialogue_partners
    from mechanics.social.physical_state import (
        build_physical_prompt_block,
        is_erotic_intimate_contact as _core_is_erotic,
        detect_intimate_disengagement as _core_is_disengage,
    )
    from mechanics.social.intimate_excitement import classify_intimate_act as _core_classify_act

    _pre_phys = (db.get_session_physical_state(session.get("id")) if session.get("id") else None) or session.get("physical_state") or {}
    _pre_ic_str = str(_pre_phys.get("intimate_contact", "") if isinstance(_pre_phys, dict) else "")
    _pre_act_str = " ".join(str(a.get("label", "") if isinstance(a, dict) else a) for a in (actions or []))
    _pre_act_ok = True
    for _pa in (actions or []):
        if isinstance(_pa, dict):
            _pchk = _pa.get("check")
            _ptier = getattr(_pchk, "tier", None) or (_pchk.get("tier") if isinstance(_pchk, dict) else None)
            if _pa.get("success") is False or _ptier in ("fail", "crit_fail"):
                _pre_act_ok = False
                break
    _cand_core_partners = list(new_partners or [])
    for _existing_dp in get_session_dialogue_partners(session):
        if _existing_dp and _existing_dp not in _cand_core_partners:
            _cand_core_partners.append(_existing_dp)
    if not _cand_core_partners:
        _cand_core_partners = ["Partner"]
    _initiating_erotic_act = False
    if _pre_act_ok and _pre_act_str:
        for _cp_cand in _cand_core_partners:
            if _core_classify_act(_pre_act_str, intimate_contact_str=_pre_ic_str, partner_name=_cp_cand).get("act_type", "none") not in ("none", "foreplay_nongenital"):
                _initiating_erotic_act = True
                break
    _in_intimate_for_core = (
        not _core_is_disengage(actions)
        and (_core_is_erotic(_pre_ic_str) or _initiating_erotic_act)
    )
    _in_aftercare_for_core = (not _core_is_disengage(actions)) and ("aftercare" in _pre_ic_str.lower())

    simultaneity_note = ""
    if len(actions) > 1:
        simultaneity_note = (
            "\nThese actions happened AT THE SAME TIME, not in sequence. Decide "
            "whether they synergize (e.g. a flanking attack plus a distraction "
            "compound for a better result), conflict/waste each other (e.g. one "
            "blocks the other's approach), or are simply independent -- and let "
            "that shape both the shared narrative and each character's individual "
            "hp_change/mp_change/etc in character_outcomes.\n"
        )

    import game_engine.prompt_layout as prompt_layout

    active_quests_str = ""
    if not _in_intimate_for_core and not _in_aftercare_for_core:
        story_quest_context, side_bounties_context = _build_quest_and_bounty_directives(session, ctx)
        if story_quest_context.strip():
            active_quests_str += f"### PRIMARY STORY QUEST\n{story_quest_context}\n\n"
        if side_bounties_context.strip():
            active_quests_str += f"### SECONDARY SIDE BOUNTIES\n{side_bounties_context}\n\n"
        if active_quests_str:
            active_quests_str += "[QUEST PRESENCE NOTE: Characters mentioned in the above quests or bounties are NOT necessarily in the current room. Do NOT include them in the scene or dialogue unless they are explicitly listed in `NPCs currently present` or actively introduced.]\n\n"

    from mechanics.combat import is_in_combat, precompute_combat_turn, reconcile_combat_results
    mode = "combat" if is_in_combat(session) else "narrative"
    precomputed = None
    if mode == "combat":
        precomputed = precompute_combat_turn(session, party, actions)

    from mechanics.system.memory.budget import DynamicTokenBudget
    budget = DynamicTokenBudget.from_session(session, party, actions)
    
    await db.update_missing_lorebook_embeddings(session_id_val)
    
    hist_text, query_embedding = await _build_history_context(session, ctx, budget=budget)
    
    directive_note = ""
    if precomputed and precomputed.get("directive"):
        directive_note = f"\n{precomputed['directive']}\n"

    # in_dialogue_mode prevents duplicate stall directive injection — dialogue_prompt_block
    # is the single authoritative prompt section for dialogue stall notes.
    _in_dialogue_mode = bool(get_session_dialogue_partners(session))

    if not _in_intimate_for_core and not _in_aftercare_for_core:
        escalation_directives = game_engine.build_scene_escalation_and_consequence_directives(
            session, party, actions, ctx.story_quest, in_dialogue_mode=_in_dialogue_mode
        )
        if escalation_directives:
            directive_note += f"\n{escalation_directives}\n"

    # --- HYBRID ENCOUNTER ENGINE (5-10% chance in dangerous/non-combat locations) ---
    ambush_triggered = False
    ambush_monsters = []
    scen_key = session.get("scenario", "fantasy")
    if (
        not is_in_combat(session)
        and not is_retry
        and not _in_intimate_for_core
        and not _in_aftercare_for_core
        and scenario_data.is_mechanic_enabled(scen_key, "tactical_combat")
        and not is_hub_location(session.get("current_location", ""))
    ):
        if random.random() < 0.08:
            from mechanics.combat.enemies import generate_balanced_encounter
            party_dicts = [char for char, _ in party] if party else []
            cur_chapter = session.get("current_chapter", 1)
            new_monsters, xp_mult = generate_balanced_encounter(
                party_dicts, scen_key, session.get("current_location", "area"), cur_chapter,
                language=session.get("narration_language") or session.get("language", "en")
            )
            # Pre-inject them into session so they appear in prompt
            session["nearby_enemies"] = new_monsters
            ambush_triggered = True
            ambush_monsters = list(new_monsters)
            # Break peaceful 1-on-1 dialogue lock when an ambush interrupts the scene
            new_partners = []
            _in_dialogue_mode = False
            names = ", ".join(m["name"] for m in new_monsters if m.get("name"))
            party_names_str = ", ".join(
                c.get("name", "Hero")
                for c, _ in (party or [])
                if isinstance(c, dict) and c.get("name")
            ) or "the player"
            present_npc_names = [
                game_engine._get_npc_name(n)
                for n in (session.get("current_npcs") or [])
                if game_engine._get_npc_name(n) and game_engine._get_npc_name(n).lower() != "none"
            ]
            npc_react_clause = (
                f" and present characters ({', '.join(present_npc_names)})"
                if present_npc_names
                else ""
            )
            directive_note += (
                f"\n[MANDATORY AMBUSH DIRECTIVE]: Enemies ({names}) have suddenly ambushed the party! "
                f"You MUST narrate their sudden appearance and attack in `outcome_narrative` and `next_narrative`, "
                f"and explicitly describe how {party_names_str}{npc_react_clause} react to the encounter "
                f"(drawing weapons, shouting warnings, taking defensive stances). "
                f"DO NOT resolve the fight this turn; just spring the trap!\n"
            )



    movement_dest_str = ''
    # --- TRAVEL & TRANSIT DIRECTIVE ---

    if not is_in_combat(session):

        for a in actions:

            label = a.get("label", "")

            raw_curr = session.get("current_location", "")

            parsed_z = get_zone_location_name(raw_curr) if raw_curr else ""

            action_dest = extract_movement_destination(label, session["id"], current_zone=parsed_z, scen_key=scen_key)

            if action_dest:

                dest_z, dest_p = action_dest
                movement_dest_str = f'{dest_z} \u2794 {dest_p}'

                cur_loc = session.get("current_location", "")

                old_primary = get_primary_location_name(cur_loc)

                is_crit_fail = bool(a.get("check") and getattr(a["check"], "tier", "") == "crit_fail")

                if is_crit_fail:

                    directive_note += (

                        f"\n[TRAVEL COMPLICATION DIRECTIVE]: The party attempted to travel to [{dest_z} ➔ {dest_p}] but suffered a Critical Failure! "

                        f"Narrate a sudden catastrophe, ambush, or hazard blocking their journey on route.\n"

                    )

                else:

                    traveling_companions, left_behind_patrons = game_engine.classify_scene_npcs(session, actions, old_primary=old_primary, dest_primary=dest_p)

                    comp_names = [c["name"] for c in traveling_companions if c.get("name")]

                    patron_names = [p["name"] for p in left_behind_patrons if p.get("name")]

                    

                    comp_str = ", ".join(comp_names) if comp_names else "None (traveling solo)"

                    # Check if action or active quest specifies a target resident / station within dest_p
                    target_station_sub = None
                    target_resident_name = None
                    lbl_lower = (label or "").lower()

                    facility_residents = []
                    try:
                        facility_residents = db.get_school_characters_by_facility(session["id"], f"{dest_z} ➔ {dest_p}", limit=6)
                    except Exception:
                        facility_residents = []

                    # 1. Check if action mentions one of the facility residents
                    for fr in facility_residents:
                        fr_nm = (fr.get("name") or "").strip().lower()
                        if fr_nm and (fr_nm in lbl_lower or (len(fr_nm.split()) > 1 and fr_nm.split()[0] in lbl_lower)):
                            fr_fac = fr.get("primary_facility") or ""
                            if fr_fac:
                                _, _, fr_s = parse_tiered_location(fr_fac, scen_key, session_id=session["id"])
                                if fr_s and fr_s not in ("Main Area", ""):
                                    target_station_sub = fr_s
                                    target_resident_name = fr.get("name")
                                    break

                    # 2. Check active quest sub-objectives if not found yet
                    if not target_station_sub:
                        try:
                            with db.get_conn() as _c_conn:
                                q_rows = _c_conn.execute("SELECT sub_objectives_json FROM quests WHERE session_id=? AND status='Active'", (session["id"],)).fetchall()
                                for qr in q_rows:
                                    sub_objs = json.loads(qr["sub_objectives_json"] or "[]")
                                    for so in sub_objs:
                                        if not so.get("completed"):
                                            t_loc = so.get("target_location", "")
                                            t_npc = (so.get("target_npc") or "").strip().lower()
                                            if t_loc:
                                                qz, qp, qs = parse_tiered_location(t_loc, scen_key, session_id=session["id"])
                                                if qp.lower() == dest_p.lower() and qs and qs not in ("Main Area", ""):
                                                    if not t_npc or (t_npc in lbl_lower or (len(t_npc.split()) > 1 and t_npc.split()[0] in lbl_lower)):
                                                        target_station_sub = qs
                                                        target_resident_name = so.get("target_npc")
                                                        break
                                    if target_station_sub:
                                        break
                        except Exception:
                            pass

                    loc_prompt_target = target_station_sub or "[Specific Sub-Area]"
                    directive_note += (
                        f"\n[TRAVEL ARRIVAL & ESTABLISHMENT DEPARTURE DIRECTIVE]:\n"
                        f"- The party has departed [{old_primary}] and arrived at [{dest_z} ➔ {dest_p}].\n"
                        f"- Set `location` to '{dest_z} ➔ {dest_p} ➔ {loc_prompt_target}'.\n"
                    )
                    if target_resident_name and target_station_sub:
                        directive_note += f"- Target Resident: {target_resident_name} is stationed at {target_station_sub}.\n"
                    directive_note += f"- Companions traveling with the party: {comp_str}.\n"

                    if patron_names:
                        patron_str = ", ".join(patron_names)
                        directive_note += (
                            f"- Patrons left behind at {old_primary} (DO NOT NARRATE OR INCLUDE IN `npcs_present`): {patron_str}.\n"
                        )
                    directive_note += f"- Local environment: Introduce or focus on local NPCs native to {dest_p}.\n"

                    if facility_residents:
                        resident_lines = []
                        for fr in facility_residents:
                            fr_name = fr.get("name")
                            fr_role = fr.get("role") or ""
                            fr_gender = fr.get("gender") or ""
                            fr_fac = fr.get("primary_facility") or ""
                            _, _, fr_s = parse_tiered_location(fr_fac, scen_key, session_id=session["id"]) if fr_fac else ("", "", "")
                            station_txt = f" @ {fr_s}" if fr_s and fr_s not in ("Main Area", "") else ""
                            gender_txt = f", {fr_gender}" if fr_gender else ""
                            resident_lines.append(f"  * {fr_name} ({fr_role}{gender_txt}){station_txt}")
                        if resident_lines:
                            directive_note += (
                                f"- Canonical Facility Occupants stationed at {dest_p}:\n"
                                + "\n".join(resident_lines) + "\n"
                                f"- Roster & Presence Guidance: Focus interaction on the active scene characters. Other room occupants may be working quietly at their designated stations or away in class. Do not seat one character at another occupant's specific desk or station.\n"
                            )



                    # Check for pending phone appointments at this arrival destination

                    try:

                        from mechanics.world.waypoints import check_location_matches_waypoint

                        dest_full = f"{dest_z} ➔ {dest_p}"

                        pending_appts = ctx.pending_appointments

                        for appt in pending_appts:

                            appt_loc = appt.get("rendezvous_location", "")

                            npc_name = appt.get("npc_name", "")

                            if appt_loc and npc_name and check_location_matches_waypoint(dest_full, appt_loc):

                                directive_note += (

                                    f"\n[MANDATORY MEETUP RENDEZVOUS ON ARRIVAL ({npc_name})]:\n"

                                    f"- {npc_name} agreed via DM to meet here at {appt_loc} and is actively waiting for the player.\n"

                                    f"- This is a PRIVATE meeting/rendezvous between the player and {npc_name}. Uninvited peers or classmates from prior locations (such as homeroom or hallways) are NOT present and must NOT be mentioned in this scene.\n"

                                    f"- You MUST narrate {npc_name}'s greeting and presence in `outcome_narrative` and `next_narrative`.\n"

                                    f"- You MUST include {npc_name} in `present_named_characters`, `npcs_present`, and generate direct conversational choices with {npc_name} in `next_choices`.\n"

                                    f"- Set the location's sub-area to match the rendezvous if applicable (e.g. '{appt_loc}').\n"

                                )

                    except Exception:

                        pass

                break



    quest_prompt_req = (

        "- `quest_updates`: Update active quest status if relevant. Do NOT output clues during combat.\n"

        if is_in_combat(session)

        else "- `quest_updates`: For every active quest listed under PRIMARY STORY QUEST / SECONDARY SIDE BOUNTIES, include one entry. Set status=Completed if the objective was achieved, Failed if it failed, or Active if ongoing. Update `objective` and `current_clues` to reflect what happened this turn.\n"

    )



    phys_prompt_block = build_physical_prompt_block(

        session, party,

        is_combat=is_in_combat(session),

        is_nsfw=is_nsfw_scenario(session.get("scenario")),

        actions=actions

    )




    dialogue_prompt_block = _build_dialogue_prompt_block(session, ctx, new_partners, party, actions)

    curr_day, curr_min, _ = db.get_session_time(session["id"])

    time_prompt_block = format_llm_time_context(curr_day, curr_min, scen_key)



    arbiter_result = None

    if not ambush_triggered and game_engine.should_trigger_state_arbiter_pass(session, actions, party):

        arbiter_result = await game_engine.execute_state_arbiter_pass(session, party, actions, actions_text)

        if arbiter_result:

            arb_lines = ["[CONFIRMED STATE ARBITER CONSEQUENCES (AUTHORITATIVE - DO NOT CONTRADICT)]:"]

            if arbiter_result.get("director_reasoning"):

                arb_lines.append(f"- Consequence Summary: {arbiter_result['director_reasoning']}")

            if arbiter_result.get("fail_forward_complication"):

                arb_lines.append(f"- Irreversible Complication: {arbiter_result['fail_forward_complication']}")

            if arbiter_result.get("departed_characters"):

                d_str = ", ".join(str(d) for d in arbiter_result["departed_characters"] if d)

                if d_str:

                    arb_lines.append(f"- NPCs who departed / exited the scene: {d_str} (Omit from npcs_present)")

            if arbiter_result.get("speaking_characters"):

                s_str = ", ".join(str(s) for s in arbiter_result["speaking_characters"] if s)

                if s_str:

                    arb_lines.append(f"- Speaking NPCs: {s_str}")

            if arbiter_result.get("deceased_characters"):

                dec_str = ", ".join(str(d) for d in arbiter_result["deceased_characters"] if d)

                if dec_str:

                    arb_lines.append(f"- Deceased / Slain NPCs & Enemies: {dec_str} (Must be narrated as dead, drop weapons)")

            if arbiter_result.get("character_outcomes"):

                arb_lines.append(f"- Mechanical Character Outcomes: {json.dumps(arbiter_result['character_outcomes'])}")

            directive_note += "\n" + "\n".join(arb_lines) + "\n"



    # --- DYNAMIC TOKEN BUDGETING ---





    # Trim individual components to fit elastic budgets based on scene mode

    # KNOWN WORLD is split by volatility (see prompt_layout docstring):
    #   canon -> Z1b (cached; fixed cap, independent of scene mode)
    #   scene -> Z2  (per turn; "lore" budget)
    #   board -> Z3  (waypoints: "quest" budget, caseboard: "caseboard" budget)
    world_bundle = game_engine._load_known_world(session['id'])
    raw_scene_ctx = game_engine._scene_context_text(
        session['id'], session.get('current_location', ''), current_npcs=session.get('current_npcs', []),
        history_text=hist_text, world=world_bundle
    )
    trimmed_scene_ctx = budget.trim(raw_scene_ctx, "lore")
    quest_board_text = ""
    if not _in_intimate_for_core and not _in_aftercare_for_core:
        wp_block, caseboard_block = game_engine._quest_board_parts(
            session['id'], session.get('current_location', ''), destination_location=movement_dest_str
        )
        quest_board_text = "".join(
            f"{b}\n\n" for b in (budget.trim(wp_block, "quest"), budget.trim(caseboard_block, "caseboard")) if b
        )
        if quest_board_text:
            quest_board_text += "[CASEBOARD & WAYPOINT PRESENCE NOTE: NPCs named or referenced in clues, caseboard entries, or waypoints (e.g. clue sources, suspects, archivists) are background investigation records. They are NOT physically present in the current room unless explicitly listed in 'NPCs currently present'. NEVER narrate them acting, watching, or standing in this scene.]\n\n"

    trimmed_history = budget.trim(hist_text, "history")

    trimmed_dialogue = budget.trim(dialogue_prompt_block, "dialogue")



    active_recall_blocks = []

    for a in actions:

        if a.get("active_recall"):

            active_recall_blocks.extend(a["active_recall"])

            

    active_recall_text = ""

    if active_recall_blocks:

        # Deduplicate and format

        unique_recalls = list(dict.fromkeys(active_recall_blocks))

        recall_lines = "\n".join(f"• {r}" for r in unique_recalls)

        active_recall_text = f"\n\n[PLAYER ACTIVE RECALL - The player explicitly searched their memory. You MUST weave these facts into your response]:\n{recall_lines}"

    ambush_req_note = ""
    if ambush_triggered and ambush_monsters:
        e_names = ", ".join(m["name"] for m in ambush_monsters if m.get("name"))
        p_names = ", ".join(c.get("name", "Hero") for c, _ in (party or []) if isinstance(c, dict) and c.get("name")) or "the player"
        pres_npcs = [
            game_engine._get_npc_name(n)
            for n in (session.get("current_npcs") or [])
            if game_engine._get_npc_name(n) and game_engine._get_npc_name(n).lower() != "none"
        ]
        react_who = f"{p_names} and {', '.join(pres_npcs)}" if pres_npcs else p_names
        ambush_req_note = (
            f"- MANDATORY ENEMY ENCOUNTER NARRATION: Hostile enemies ({e_names}) appear in this turn! "
            f"Your prose in `outcome_narrative` and `next_narrative` MUST explicitly name {e_names}, describe how they appeared/attacked, "
            f"and describe how {react_who} reacted to the encounter.\n"
        )
    else:
        ambush_req_note = (
            "- ENEMY ENCOUNTER CONSISTENCY: Whenever hostile enemies are present in `nearby_enemies` or introduced in `new_entities`, "
            "your narrative MUST explicitly describe how those enemies appeared in the scene and how the player and any present characters/NPCs react to the encounter.\n"
        )

    if any(w in actions_text.lower() for w in ("observe your surroundings", "inspect those present", "survey the room and present")):
        directive_note += (
            "\n[OBSERVATION DIRECTIVE]: The player is actively inspecting the room and characters. "
            "In your narrative, output a vivid Perception-based vignette detailing the immediate physical environment, "
            "hidden details, and the postures/expressions of present characters.\n"
        )

    if has_exited_convo:
        directive_note += (
            "\n[CONVERSATIONAL DEPARTURE & SCENE TRANSITION DIRECTIVE]:\n"
            "The player has explicitly concluded the conversation and excused themselves or departed.\n"
            "- In `outcome_narrative`, narrate only the immediate parting gesture or departure (e.g. nodding, thanking them, stepping away). "
            "DO NOT reopen the conversation, do not renegotiate previously agreed deals, and do not repeat the partner's prior dialogue.\n"
            "- In `next_narrative`, transition the scene forward to the new environment, surrounding atmosphere, or the player's next destination.\n"
        )

    # --- 4-Zone Prompt Caching Architecture ---
    enemies_list = session.get('nearby_enemies', [])
    enemies_str = ""
    if enemies_list:
        enemies_str = "\nENEMIES CURRENTLY NEARBY:\n" + "\n".join(
            game_engine._describe_tracked_entity(e) for e in enemies_list
        ) + "\n"

    if party and not session.get("lead_character_gender"):
        lead_c = party[0][0] if isinstance(party[0], (tuple, list)) else party[0]
        if isinstance(lead_c, dict):
            session["lead_character_gender"] = lead_c.get("gender", "male")

    zone_0 = prompt_layout.build_static_core(mode, "turn")
    zone_1 = prompt_layout.build_session_zone(session)
    zone_1b = prompt_layout.build_world_canon_zone(session, world=world_bundle)
    # Z2 ordered least -> most volatile; the clock changes every turn so it goes last.
    zone_2 = "\n".join(p for p in [
        f"CHARACTER SHEET(S):\n{game_engine._party_sheet_text(party)}",
        f"{prompt_layout.SCENE_CONTEXT_HEADER}\n{trimmed_scene_ctx}",
        enemies_str.strip(),
        f"PHYSICAL CONTINUITY ANCHOR:\n{phys_prompt_block}",
        time_prompt_block,
    ] if p)
    
    user_prompt = (
        f"{active_quests_str}"
        f"{quest_board_text}"
        f"RECENT HISTORY:\n{trimmed_history}{active_recall_text}\n\n"
        f"ACTIONS:\n{actions_text}\n{simultaneity_note}\n{directive_note}\n\n"
        f"{trimmed_dialogue}"
        f"{ambush_req_note}"
        f"{prompt_layout.CLOSING_REMINDER}"
    )
    
    final_system_prompt_list = prompt_layout.assemble_system_prompt(zone_0, zone_1, zone_1b, zone_2)
    log.debug("prompt zones %s sizes %s",
              prompt_layout.zone_fingerprints(zone_0, zone_1, zone_1b, zone_2),
              [len(z) for z in (zone_0, zone_1, zone_1b, zone_2)])

    is_nsfw_flag = uses_nsfw_model(session.get("scenario"))
    
    if stream_callback:
        result = await game_engine.call_llm_json_stream(
            final_system_prompt_list, user_prompt,
            on_narrative_token=stream_callback,
            is_nsfw=is_nsfw_flag,
            timeout=LLM_PASS2_TIMEOUT,
            response_model=TurnOutcome
        )
    else:
        result = await game_engine.call_llm_json(
            final_system_prompt_list, user_prompt,
            is_nsfw=is_nsfw_flag,
            timeout=LLM_PASS2_TIMEOUT,
            response_model=TurnOutcome
        )

    # Safety coercion: llm_client now returns dicts, but guard against Pydantic objects leaking through

    if getattr(result, "model_dump", None):

        result = result.model_dump(exclude_unset=False)



    if isinstance(result, dict):
        result["_llm_system_prompt_list"] = final_system_prompt_list
        act_label = actions[0].get("label", "") if actions and isinstance(actions[0], dict) else ""
        lead_char_name = party[0][0].get("name", "You") if party and party[0] else "You"

        if result.get("outcome_narrative"):
            result["outcome_narrative"] = game_engine.sanitize_comparative_cliches(result["outcome_narrative"])
            result["outcome_narrative"] = game_engine.sanitize_meta_objective_leaks(result["outcome_narrative"])
            result["outcome_narrative"] = game_engine.sanitize_narrative_context_echo(
                result["outcome_narrative"], session, action_label=act_label, character_name=lead_char_name
            )
            result["outcome_narrative"] = game_engine.sanitize_absent_npc_hallucinations(
                result["outcome_narrative"], session=session, result=result, actions=actions, party=party
            )
            result["outcome_narrative"] = game_engine.sanitize_npc_pronoun_consistency(
                result["outcome_narrative"], session=session, result=result, actions=actions, party=party
            )

        if result.get("next_narrative"):
            result["next_narrative"] = game_engine.sanitize_comparative_cliches(result["next_narrative"])
            result["next_narrative"] = game_engine.sanitize_meta_objective_leaks(result["next_narrative"])
            result["next_narrative"] = game_engine.sanitize_narrative_context_echo(
                result["next_narrative"], session, action_label="", character_name=lead_char_name, is_next_narrative=True
            )
            result["next_narrative"] = game_engine.sanitize_absent_npc_hallucinations(
                result["next_narrative"], session=session, result=result, actions=actions, party=party
            )
            result["next_narrative"] = game_engine.sanitize_npc_pronoun_consistency(
                result["next_narrative"], session=session, result=result, actions=actions, party=party
            )

        result = game_engine.sync_hostile_entities(result, session)

        # --- DYNAMIC MULTI-PASS: SOCIAL & WORLD ARBITER (PASS 3) ---
        from game_engine.state.core import should_trigger_social_arbiter_pass, execute_social_arbiter_pass
        if should_trigger_social_arbiter_pass(session, actions, party, result):
            social_result = await execute_social_arbiter_pass(session, party, actions, actions_text, result)
            if social_result:
                if social_result.get("relationship_updates"):
                    result["relationship_updates"] = social_result["relationship_updates"]
                if social_result.get("new_entities"):
                    result["new_entities"] = social_result["new_entities"]
                if social_result.get("quest_updates"):
                    result["quest_updates"] = social_result["quest_updates"]
                if social_result.get("npc_memories"):
                    result["npc_memories"] = social_result["npc_memories"]

        if arbiter_result:

            # Reconcile Pass 1 departures and entity presence

            p1_departed = [str(d).strip() for d in arbiter_result.get("departed_characters", []) if d]

            if p1_departed:

                p1_dep_set = set(d.lower() for d in p1_departed)

                curr_deps = result.get("npc_departures") or []

                curr_dep_names = set(str(d).strip().lower() for d in curr_deps)

                for dep in p1_departed:

                    if dep.lower() not in curr_dep_names:

                        curr_deps.append(dep)

                result["npc_departures"] = curr_deps



                if result.get("npcs_present"):

                    result["npcs_present"] = [

                        npc for npc in result["npcs_present"]

                        if game_engine._get_npc_name(npc).lower() not in p1_dep_set

                    ]



            # Backfill character_outcomes if Pass 2 dropped them

            if arbiter_result.get("character_outcomes") and not result.get("character_outcomes"):

                result["character_outcomes"] = arbiter_result["character_outcomes"]



            # Preserve discovered clue from Pass 1 if present
            p1_clue = arbiter_result.get("quest_progress", {}).get("clue_discovered")
            if p1_clue:
                if result.get("quest_updates"):
                    for qu in result["quest_updates"]:
                        if isinstance(qu, dict) and not qu.get("current_clues"):
                            qu["current_clues"] = p1_clue
                else:
                    # Synthesize quest update to preserve Pass 1 clue when Pass 3 omitted quest_updates
                    import db as local_db
                    active_sq = local_db.get_active_story_quest(session.get("id"))
                    q_id = active_sq.get("quest_id", "SQ-Active") if active_sq else "SQ-Active"
                    q_title = active_sq.get("title", "Active Quest") if active_sq else "Active Quest"
                    result["quest_updates"] = [{
                        "quest_id": q_id,
                        "title": q_title,
                        "current_clues": p1_clue,
                        "status": "Active"
                    }]

            # Preserve commitment resolutions from Pass 1
            if arbiter_result.get("fulfilled_commitments"):
                result["fulfilled_commitments"] = arbiter_result["fulfilled_commitments"]
            if arbiter_result.get("broken_commitments"):
                result["broken_commitments"] = arbiter_result["broken_commitments"]

            # Preserve entity death/slaying
            if arbiter_result.get("deceased_characters"):
                result["deceased_characters"] = arbiter_result["deceased_characters"]

            # Preserve & Merge NPC episodic memories across passes (Pass 3 + Pass 1)
            if arbiter_result.get("npc_memories"):
                existing_mems = result.get("npc_memories") or []
                result["npc_memories"] = list(existing_mems) + list(arbiter_result["npc_memories"])





        if precomputed is not None:

            result = reconcile_combat_results(session, result, precomputed)

            

        # --- CODE-DRIVEN COMBAT CHOICES (replaces LLM choices during active combat) ---

        active_monsters = game_engine.get_active_enemies(session) or game_engine.get_active_enemies(result)

        if active_monsters:

            from mechanics.narrative.choice_generator import generate_categorized_combat_actions

            cat = generate_categorized_combat_actions(

                party=party,

                monster=active_monsters[0],

                location=session.get("current_location", "area"),

                scenario=session.get("scenario", "fantasy")

            )

            code_choices = [a["label"] for a in cat.get("attacks", [])] + \
                           [m["label"] for m in cat.get("magic", [])] + \
                           [t["label"] for t in cat.get("tactics", [])]

            if cat.get("flee"):

                code_choices.append(cat["flee"]["label"])

            if code_choices:

                result["next_choices"] = code_choices

                result["choices"] = code_choices

        elif not _in_intimate_for_core and not _in_aftercare_for_core:
            _post_phys_upd = result.get("physical_updates") if isinstance(result.get("physical_updates"), dict) else {}
            _post_ic_str = str(_post_phys_upd.get("intimate_contact", "") or "")
            if not _core_is_erotic(_post_ic_str) and "aftercare" not in _post_ic_str.lower():
                # --- DYNAMIC QUEST ACTION TAGGING & DEDUPLICATION ---
                from mechanics.world.waypoints import tag_and_enrich_quest_choices
                lead_char = party[0][0] if party and party[0] else None
                raw_c = result.get("next_choices") or result.get("choices") or []
                prelim_loc = result.get("location") or movement_dest_str or session.get("current_location", "")
                enriched_c = tag_and_enrich_quest_choices(
                    raw_c, session["id"], prelim_loc,
                    scen_key=session.get("scenario", "fantasy"), char=lead_char
                )
                if enriched_c:
                    result["next_choices"] = enriched_c[:5]
                    result["choices"] = enriched_c[:5]




        # --- HYBRID STATUS EFFECT TIMER TICK ---

        from mechanics.combat import tick_status_timers

        for entry in party:

            char = entry[0] if isinstance(entry, (tuple, list)) else entry

            if isinstance(char, dict) and char.get("status_effects"):

                tick_status_timers(char)



        hostiles = session.get("nearby_enemies") or []

        surviving_hostiles = []

        dot_xp_gain = 0

        dot_gold_gain = 0

        dot_dead = []

        for monster in hostiles:

            if isinstance(monster, dict):

                if monster.get("status_effects"):

                    tick_status_timers(monster)

                if monster.get("hp", 1) > 0:

                    surviving_hostiles.append(monster)

                else:

                    dot_dead.append(monster.get("name", "Enemy"))

                    tier = monster.get("tier_rank", 1)

                    mult = monster.get("xp_multiplier", 1.0)

                    xp, gold = {1: (40, 15), 2: (75, 25), 3: (150, 60), 4: (260, 120), 5: (450, 250)}.get(tier, (75, 25))

                    dot_xp_gain += int(xp * mult)

                    dot_gold_gain += int(gold * mult)

            else:

                surviving_hostiles.append(monster)

        session["nearby_enemies"] = surviving_hostiles

        session["nearby_enemies"] = surviving_hostiles

        

        if dot_dead and isinstance(result, dict):

            c_outcomes = result.setdefault("character_outcomes", [])

            if not c_outcomes and party and party[0]:

                c_name = party[0][0].get("name", "Hero") if isinstance(party[0][0], dict) else "Hero"

                c_outcomes.append({"name": c_name, "hp_change": 0, "mp_change": 0, "xp_change": 0, "gold_change": 0})

            for co in c_outcomes:

                if isinstance(co, dict):

                    co["xp_change"] = co.get("xp_change", 0) + dot_xp_gain

                    co["gold_change"] = co.get("gold_change", 0) + dot_gold_gain

            

            result["dead_enemies"] = result.get("dead_enemies", []) + dot_dead

            result["dead_monsters"] = result.get("dead_monsters", []) + dot_dead

            result["nearby_enemies"] = surviving_hostiles

            result["nearby_enemies"] = surviving_hostiles

            

            if not surviving_hostiles:

                msg = f"⚔️ Victory! {', '.join(dot_dead)} succumbed to their wounds!\n**Rewards:** +{dot_xp_gain} XP, +{dot_gold_gain} Gold"

                if result.get("_combat_resolved_notice"):

                    if ", ".join(dot_dead) not in result["_combat_resolved_notice"]:

                        result["_combat_resolved_notice"] += "\n" + msg

                else:

                    result["_combat_resolved_notice"] = msg

                # Inject a loot choice

                loot_choice = {

                    "label": f"Search and loot the fallen enemies",

                    "stat": "FREE",

                    "requirement": 0,

                    "mp_cost": 0

                }

                c_list = result.get("next_choices") or result.get("choices") or []

                c_list = [loot_choice] + [c for c in c_list if not any(kw in (str(c.get("label", "")) if isinstance(c, dict) else str(c)).lower() for kw in ("attack", "strike with", "loot", "search the fallen"))][:3]

                result["next_choices"] = c_list

                result["choices"] = c_list

                # Despawn summons

                session["current_npcs"] = [npc for npc in session.get("current_npcs", []) if not npc.get("is_summon")]

                result["npcs_present"] = session["current_npcs"]



    import character_data

    from mechanics.social.relationships import safe_clamp_delta

    if isinstance(result, dict):
        result["_llm_system_prompt_list"] = final_system_prompt_list
        result["_llm_user_prompt"] = user_prompt

        # Determine if this turn is non-combat or a social interaction without combat
        scen_key = session.get("scenario", "fantasy") if session else "fantasy"
        is_non_combat_scen = scenario_data.is_non_combat_scenario(scen_key)
        active_enemies = (game_engine.get_active_enemies(result) or game_engine.get_active_enemies(session)) if result else []
        is_combat_turn = bool(active_enemies or (result and (result.get("_combat_log") or result.get("_enemy_attack_notice"))))

        from mechanics.social.intimate_excitement import is_intimate_action_label, matches_boundary
        from mechanics.social.physical_state import is_erotic_intimate_contact
        _sess_phys = (session.get("physical_state") if isinstance(session, dict) else None) or {}
        _res_phys_upd = (result.get("physical_updates") if isinstance(result, dict) else None) or {}
        _is_intimate_turn = (
            is_erotic_intimate_contact(str(_sess_phys.get("intimate_contact", "")))
            or is_erotic_intimate_contact(str(_res_phys_upd.get("intimate_contact", "")))
        )

        is_social_turn = not is_combat_turn and (
            _is_intimate_turn
            or any(
                str(a.get("action_category") or "").lower() in (
                    "dialogue", "disclosure_inquiry", "affection", "social_invite", "romantic_confession", "party_recruit", "social", "conversation", "chat", "flirt"
                ) or
                str(a.get("stat") or "").upper() == "CHA" or
                is_intimate_action_label(str(a.get("label") or "")) or
                bool(session.get("dialogue_partner") and matches_boundary(str(a.get("label") or "").lower(), ("talk", "speak", "ask", "tell", "say", "flirt", "tease", "confess", "whisper", "joke", "challenge", "inquire", "chat", "greet")))
                for a in (actions or [])
            )
        )

        if "character_outcomes" in result and isinstance(result["character_outcomes"], list):
            party_by_name = {char["name"].lower(): char for char, inv in party}
            filtered_outcomes = []
            has_failed_check = any(
                getattr(a.get("check"), "tier", "") in ("fail", "crit_fail") or
                (isinstance(a.get("check"), dict) and a["check"].get("tier") in ("fail", "crit_fail"))
                for a in (actions or [])
            )

            for outcome in result["character_outcomes"]:
                if isinstance(outcome, dict) and outcome.get("name"):
                    c_name = str(outcome["name"]).strip()
                    if c_name.lower() in party_by_name:
                        char = party_by_name[c_name.lower()]
                        if is_non_combat_scen or is_social_turn:
                            raw_hp = outcome.get("hp_change", 0)
                            if raw_hp and int(raw_hp) < 0:
                                log.info("[VitalsGuard] Suppressed non-combat HP damage (%s) for '%s' in non-combat/social scene.", raw_hp, c_name)
                                outcome["hp_change"] = 0
                            if outcome.get("temp_hp_change", 0) and int(outcome["temp_hp_change"]) < 0:
                                outcome["temp_hp_change"] = 0

                        reconciled = character_data.reconcile_character_outcomes(char, outcome, is_non_combat=(is_non_combat_scen or is_social_turn))
                        outcome["hp_change"] = reconciled["actual_hp_delta"]
                        outcome["mp_change"] = reconciled["actual_mp_delta"]
                        outcome["gold_change"] = reconciled["actual_gold_delta"]
                        filtered_outcomes.append(outcome)
            result["character_outcomes"] = filtered_outcomes

            # Enforce that failed checks in social/non-combat scenes impact relationship affinity rather than physical HP
            if (is_non_combat_scen or is_social_turn) and has_failed_check:
                from mechanics.world.mobility import get_session_dialogue_partners
                dp_list = get_session_dialogue_partners(session) if isinstance(session, dict) else []
                target_npc = dp_list[0] if dp_list else None
                if not target_npc and actions:
                    for a in actions:
                        if a.get("target_npc"):
                            target_npc = a["target_npc"]
                            break
                        if a.get("combat_target"):
                            target_npc = a["combat_target"]
                            break

                if target_npc:
                    rel_updates = result.setdefault("relationship_updates", [])
                    target_ru = next(
                        (ru for ru in rel_updates if isinstance(ru, dict) and str(ru.get("npc_name", "")).strip().lower() == target_npc.lower()),
                        None
                    )
                    check_tier = "fail"
                    for a in (actions or []):
                        t = getattr(a.get("check"), "tier", None) or (a.get("check", {}).get("tier") if isinstance(a.get("check"), dict) else None)
                        if t in ("fail", "crit_fail"):
                            check_tier = t
                            break
                    penalty = -2 if check_tier == "crit_fail" else -1

                    if target_ru is not None:
                        if target_ru.get("delta_score", 0) >= 0:
                            target_ru["delta_score"] = penalty
                            log.info("[VitalsGuard] Converted failed check consequence for %s into relationship delta: %s", target_npc, penalty)
                    else:
                        lead_name = party[0][0].get("name", "Player") if party and party[0] else "Player"
                        rel_updates.append({
                            "npc_name": target_npc,
                            "delta_score": penalty,
                            "track": "platonic",
                            "memory_summary": f"Felt awkward or put off after {lead_name}'s misstep."
                        })
                        log.info("[VitalsGuard] Added affinity penalty (%s) for %s due to failed social check.", penalty, target_npc)



        if "relationship_updates" in result and isinstance(result["relationship_updates"], list):

            for ru in result["relationship_updates"]:

                if isinstance(ru, dict) and "delta_score" in ru:

                    ru["delta_score"] = safe_clamp_delta(ru["delta_score"], -20, 20)



        if "faction_updates" in result and isinstance(result["faction_updates"], list):

            for fu in result["faction_updates"]:

                if isinstance(fu, dict) and "delta_score" in fu:

                    fu["delta_score"] = safe_clamp_delta(fu["delta_score"], -20, 20)



        outcome_narrative = (

            result.get("outcome_narrative")

            or result.get("action_outcome")

            or result.get("resolution")

            or result.get("story")

            or result.get("scene_text")

            or result.get("description")

            or result.get("narrative")

            or result.get("text")

            or result.get("content")

            or result.get("next_narrative")

            or ""

        ).strip()

        

        next_narrative = (

            result.get("next_narrative")

            or result.get("narrative")

            or result.get("scene_text")

            or result.get("story")

            or result.get("description")

            or result.get("text")

            or result.get("content")

            or ""

        ).strip()



        if not outcome_narrative:
            a_label = actions[0].get("label", "acts") if actions else "acts"
            c_name = party[0][0].get("name", "The party") if party and party[0] else "The party"
            is_second_person = str(c_name).strip().lower() in ("you", "i")
            obs_keywords = ("observe", "inspect", "look", "examine", "survey", "perceive", "listen", "watch", "glance")
            if any(kw in a_label.lower() for kw in obs_keywords):
                take_verb = "take" if is_second_person else "takes"
                outcome_narrative = f"{c_name} {take_verb} a moment to carefully observe the surroundings and inspect those present."
            elif any(a_label.lower().startswith(pfx) for pfx in ("i travel to ", "travel to ", "i head to ", "head to ", "i walk to ", "walk to ")):
                dest_clean = a_label
                for pfx in ("i travel to ", "travel to ", "i head to ", "head to ", "i walk to ", "walk to "):
                    if a_label.lower().startswith(pfx):
                        dest_clean = a_label[len(pfx):].strip().rstrip(".")
                        break
                travel_verb = "travel" if is_second_person else "travels"
                outcome_narrative = f"{c_name} {travel_verb} to {dest_clean}."
            else:
                act_verb = "act" if is_second_person else "acts"
                outcome_narrative = f"{c_name} {act_verb} with deliberate intent: {a_label}."
            result["is_fallback"] = True
            result["_is_fallback_narrative"] = True



        if not next_narrative or next_narrative == outcome_narrative:

            curr_loc = session.get("current_location", "the area")

            lead_npc = next((game_engine._get_npc_name(n) for n in (session.get("current_npcs") or []) if n), None)

            npc_mention = f" beside {lead_npc}" if lead_npc else ""

            next_narrative = f"The atmosphere settles around {curr_loc}{npc_mention} as the immediate action resolves. The surrounding area remains active with subtle movement and tension, awaiting the party's next move."

            result["is_fallback"] = True

            result["_is_fallback_narrative"] = True



        result["outcome_narrative"] = outcome_narrative

        result["next_narrative"] = next_narrative



    result = namegen.resolve_tokens_deep(result, scenario=scen_key)

    game_engine._sanitize_outcome_person_names(result, session["id"], scen_key)

    if isinstance(result, dict):
        result["_llm_system_prompt_list"] = final_system_prompt_list
        act_label = actions[0].get("label", "") if actions and isinstance(actions[0], dict) else ""
        lead_char_name = party[0][0].get("name", "You") if party and party[0] else "You"
        session_for_next = dict(session)
        if result.get("outcome_narrative"):
            result["outcome_narrative"] = game_engine.sanitize_meta_objective_leaks(result["outcome_narrative"])
            result["outcome_narrative"] = game_engine.sanitize_narrative_context_echo(
                result["outcome_narrative"], session, action_label=act_label, character_name=lead_char_name
            )
            result["outcome_narrative"] = game_engine.sanitize_absent_npc_hallucinations(
                result["outcome_narrative"], session, result=result, actions=actions, party=party
            )
            session_for_next["narrative"] = result["outcome_narrative"]
        if result.get("next_narrative"):
            result["next_narrative"] = game_engine.sanitize_meta_objective_leaks(result["next_narrative"])
            result["next_narrative"] = game_engine.sanitize_narrative_context_echo(
                result["next_narrative"], session_for_next, action_label="", character_name=lead_char_name, is_next_narrative=True
            )
            result["next_narrative"] = game_engine.sanitize_absent_npc_hallucinations(
                result["next_narrative"], session_for_next, result=result, actions=actions, party=party
            )
        if result.get("narrative"):
            result["narrative"] = game_engine.sanitize_meta_objective_leaks(result["narrative"])
            result["narrative"] = game_engine.sanitize_narrative_context_echo(
                result["narrative"], session_for_next, action_label="", character_name=lead_char_name, is_next_narrative=True
            )
            result["narrative"] = game_engine.sanitize_absent_npc_hallucinations(
                result["narrative"], session_for_next, result=result, actions=actions, party=party
            )

        outcome_narrative = (result.get("outcome_narrative") or outcome_narrative).strip()
        next_narrative = (result.get("next_narrative") or next_narrative).strip()




    if isinstance(result, dict) and is_location_engine_enabled(scen_key):

        old_loc = session.get("current_location", "")

        s_nar = (result.get("next_narrative") or result.get("narrative") or result.get("outcome_narrative") or "").strip()

        action_text = " ".join(str(a.get("label", "")) for a in actions if isinstance(a, dict))

        action_check_tier = actions[0]["check"].tier if actions and actions[0].get("check") else "success"

        new_loc = game_engine.reconcile_movement_location(

            session["id"], old_loc, result.get("location", ""),

            action_text=action_text, narrative=s_nar,

            scen_key=scen_key, char_name=char.get("name", ""),

            check_tier=action_check_tier

        )

        result["location"] = new_loc

        



        # --- SCENE TRANSITION & NPC LIFECYCLE ---

        result["npcs_present"] = game_engine.process_scene_npcs(result, session, new_loc, old_loc, actions=actions)



        # Automatically detect speaking NPCs from the narrative or rendezvous targets if dialogue wasn't explicitly exited
        if not has_exited_convo and result.get("npcs_present"):
            full_nar = f"{outcome_narrative}\n{next_narrative}\n{s_nar}"
            pres_names = [game_engine._get_npc_name(n) for n in result["npcs_present"] if game_engine._get_npc_name(n)]
            retained_partners = [p for p in new_partners if any(game_engine.is_dialogue_partner(p, [pn]) for pn in pres_names)]

            speaking_npcs = game_engine.extract_speaking_npcs_from_narrative(full_nar, result["npcs_present"])

            # Also check speaking_characters from entity_audit (only if they converse with the player / no prior partner)
            audit_speaking = (result.get("entity_audit") or {}).get("speaking_characters") or []
            if isinstance(audit_speaking, list):
                for asp in audit_speaking:
                    if isinstance(asp, str) and asp.strip():
                        matched_n = next((
                            game_engine._get_npc_name(n)
                            for n in result["npcs_present"]
                            if game_engine.is_dialogue_partner(asp, [game_engine._get_npc_name(n)])
                        ), None)
                        if matched_n and matched_n not in speaking_npcs:
                            # If already in dialogue with another NPC, allow legitimate chime-ins (quest, party, focal speech)
                            if game_engine.can_chime_in_to_dialogue(
                                matched_n,
                                retained_partners=retained_partners,
                                actions=actions,
                                narrative=full_nar,
                                session=session,
                                party=party,
                                npcs_present=result["npcs_present"],
                            ):
                                speaking_npcs.append(matched_n)

            if not speaking_npcs:
                from mechanics.world.mobility import is_rendezvous_target
                for n in result["npcs_present"]:
                    n_nm = game_engine._get_npc_name(n)
                    if n_nm and n_nm.lower() != "none" and is_rendezvous_target(n_nm, actions=actions, session_id=session.get("id"), new_loc=new_loc):
                        speaking_npcs.append(n_nm)

            same_primary = bool(
                old_loc == new_loc
                or (
                    get_primary_location_name(old_loc)
                    and get_primary_location_name(old_loc).lower() == get_primary_location_name(new_loc).lower()
                )
            )

            # Merge existing partners (who are still present) with newly detected speaking NPCs
            merged = list(retained_partners) if same_primary else []
            for sn in speaking_npcs:
                if not any(game_engine.is_dialogue_partner(sn, [m]) for m in merged):
                    # Allow legitimate chime-ins (quest, companion, directly engaged participants) to join active dialogue
                    if game_engine.can_chime_in_to_dialogue(
                        sn,
                        retained_partners=retained_partners,
                        actions=actions,
                        narrative=full_nar,
                        session=session,
                        party=party,
                        npcs_present=result["npcs_present"],
                    ):
                        merged.append(sn)

            new_partners = merged if merged else retained_partners



        # Keep only partners who are physically present in the room

        if result.get("npcs_present") and new_partners:

            pres_names = [game_engine._get_npc_name(n) for n in result["npcs_present"] if game_engine._get_npc_name(n)]

            new_partners = [p for p in new_partners if any(game_engine.is_dialogue_partner(p, [pn]) for pn in pres_names)]

        else:

            new_partners = []



        result["dialogue_partners"] = new_partners

        result["dialogue_partner"] = new_partners[0] if new_partners else None

        from mechanics.social.physical_state import is_erotic_intimate_contact
        _pre_ic = str(((session.get("physical_state") or {}).get("intimate_contact") or "")).lower()
        _upd_ic = str(((result.get("physical_updates") or {}).get("intimate_contact") or "")).lower()
        _is_erotic_turn = (
            _in_intimate_for_core
            or is_erotic_intimate_contact(_pre_ic)
            or is_erotic_intimate_contact(_upd_ic)
            or "aftercare" in _pre_ic
            or "aftercare" in _upd_ic
        )

        if not _is_erotic_turn and not (game_engine.get_active_enemies(session) or game_engine.get_active_enemies(result)):
            from mechanics.world.waypoints import tag_and_enrich_quest_choices
            lead_char = party[0][0] if party and party[0] else None
            raw_c = result.get("next_choices") or result.get("choices") or []
            enriched_c = tag_and_enrich_quest_choices(
                raw_c,
                session["id"],
                new_loc or session.get("current_location", ""),
                scen_key=scen_key,
                char=lead_char,
                dialogue_partner=new_partners,
                current_npcs=result.get("npcs_present"),
            )
            if enriched_c:
                result["next_choices"] = enriched_c[:5]
                result["choices"] = enriched_c[:5]

    if isinstance(result, dict):
        result["_llm_system_prompt_list"] = final_system_prompt_list
        result["_llm_user_prompt"] = user_prompt
        result, appended_encounter_text = ensure_enemy_encounter_narrative(
            result,
            session,
            party,
            actions=actions,
            pre_turn_enemy_names=pre_turn_enemy_names,
        )
        if appended_encounter_text:
            next_narrative = str(result.get("next_narrative") or "").strip()
            if stream_callback:
                try:
                    if getattr(stream_callback, "_accepts_field", False):
                        await stream_callback(f"\n\n{appended_encounter_text}", "next_narrative")
                    else:
                        await stream_callback(f"\n\n{appended_encounter_text}")
                except Exception:
                    pass

    res = result



    # --- ADVANCE IN-GAME TIME & DAY/NIGHT PROGRESSION ---
    if not is_retry:
        party_uids = [
            (char["user_id"] if isinstance(char, dict) else char[0]["user_id"])
            for char in party if char
        ]
        if actions and any(is_sleep_action(a.get("label", "")) for a in actions if isinstance(a, dict)):
            sleep_info = apply_sleep_rest(session["id"], party_uids, wake_minute=450)
            if isinstance(res, dict):
                res["_sleep_info"] = sleep_info
                # Ensure outcome narrative reflects a refreshing sleep
                if not res.get("outcome_narrative") or "sleep" not in res.get("outcome_narrative", "").lower():
                    c_name = (party[0][0].get("name") if party and party[0] else "You") if isinstance(party[0], (tuple, list)) else "You"
                    res["outcome_narrative"] = f"{c_name} turned in for the night, resting deeply until morning light broke across the horizon at 07:30 AM. Vitals and energy are fully restored."
        else:
            first_act = actions[0] if actions else {}
            is_dialogue_active = bool(new_partners)
            is_combat_active = bool(game_engine.get_active_enemies(session) or (isinstance(res, dict) and game_engine.get_active_enemies(res)))
            old_loc_val = session.get("current_location", "")
            new_loc_val = (res.get("location") if isinstance(res, dict) else None) or old_loc_val
            time_delta = calculate_action_time_cost(
                first_act,
                scen_key=scen_key,
                old_loc=old_loc_val,
                new_loc=new_loc_val,
                is_dialogue=is_dialogue_active,
                is_combat=is_combat_active
            )
            time_report = advance_time(session["id"], time_delta, party_uids=party_uids)
            if isinstance(res, dict):
                res["_time_info"] = time_report



    # Subsystem 3: Deterministic Invariant Verifier (Hallucination Guardrail)

    if isinstance(res, dict):

        dead_list = session.get("dead_characters", [])

        if res.get("deceased_characters"):

            dead_list.extend(res["deceased_characters"])

        

        # Cross-reference speaking characters against known dead

        if res.get("speaking_characters"):

            speakers = [s.strip().lower() for s in res["speaking_characters"]]

            for dead in dead_list:

                d_lower = dead.strip().lower()

                if d_lower in speakers:

                    log.warning(f"Invariant Violation caught: Deceased NPC '{dead}' spoke. Applying hallucination mask.")

                    if res.get("next_narrative"):
                        res["next_narrative"] += f"\n\n*(A cold wind blows. The words of {dead} echo in your mind, but they are gone. It is merely a memory...)*"

        # Check physical state for redress, tether overrides, and observation actions
        curr_choices = res.get("choices") if "choices" in res else res.get("next_choices")
        if curr_choices is not None and isinstance(curr_choices, list):
            import db
            from mechanics.social.physical_state import _match_actor_key, is_erotic_intimate_contact
            phys = db.get_session_physical_state(session.get("id")) or {}
            if res.get("physical_updates"):
                from mechanics.social.physical_state import merge_physical_state_updates
                phys = merge_physical_state_updates(
                    phys, res["physical_updates"],
                    party=party, scen_key=session.get("scenario", "fantasy")
                )
            res["_physical_state"] = phys
            actors = phys.get("actors", {})
            in_active_intimate_turn = bool(
                not _core_is_disengage(actions)
                and (is_erotic_intimate_contact(str(phys.get("intimate_contact", ""))) or _in_intimate_for_core)
            )
            in_active_dialogue_turn = bool(new_partners)


            # 1. Redress free action check across party members (outside active erotic scenes)
            if not in_active_intimate_turn:
                for entry in party:
                    char = entry[0] if isinstance(entry, (tuple, list)) else entry
                    if not isinstance(char, dict) or not char.get("name"):
                        continue
                    c_name = char["name"]
                    m_key = _match_actor_key(c_name, actors)
                    if m_key in actors:
                        c_data = actors[m_key]
                        cloth = c_data.get("clothing", {})
                        top = str(cloth.get("top", "")).lower()
                        bottom = str(cloth.get("bottom", "")).lower()
                        if any(w in top or w in bottom for w in ("none", "stripped", "removed", "naked", "bare", "undressed")):
                            if not any("redress" in str(c.get("label", "")).lower() or "get dressed" in str(c.get("label", "")).lower() for c in curr_choices if isinstance(c, dict)):
                                curr_choices.append({
                                    "label": f"Redress / Get dressed ({c_name})",
                                    "stat": "FREE",
                                    "requirement": 0,
                                    "mp_cost": 0
                                })

            # 2. Tether choice overriding for the lead/player character (party[0]) (outside active erotic scenes)
            is_player_restrained = False
            lead_char = party[0][0] if party and isinstance(party[0], (tuple, list)) else (party[0] if party and isinstance(party[0], dict) else None)
            if not in_active_intimate_turn and lead_char and lead_char.get("name"):
                m_key = _match_actor_key(lead_char["name"], actors)
                if m_key in actors:
                    lead_phys = actors[m_key]
                    tether = str(lead_phys.get("tether", "")).strip()
                    if tether and tether.lower() not in ("none", "false", ""):
                        tether_lower = tether.lower()
                        if any(w in tether_lower for w in ("carry", "holding", "carrying")):
                            # Filter out attack actions while burdened
                            curr_choices = [c for c in curr_choices if isinstance(c, dict) and "attack" not in str(c.get("label", "")).lower() and "strike" not in str(c.get("label", "")).lower()]
                            curr_choices.append({
                                "label": f"Put down what you are carrying / {tether}",
                                "stat": "FREE",
                                "requirement": 0,
                                "mp_cost": 0
                            })
                        else:
                            # Grappled / Restrained: player cannot move or attack freely
                            is_player_restrained = True
                            curr_choices = [
                                {
                                    "label": f"Struggle with all your might to break free from: {tether}",
                                    "stat": "STR",
                                    "requirement": 14,
                                    "mp_cost": 0
                                },
                                {
                                    "label": f"Attempt a swift maneuver to slip out of: {tether}",
                                    "stat": "AGI",
                                    "requirement": 14,
                                    "mp_cost": 0
                                }
                            ]

            # 3. Persistent observation choice (only in open exploration outside active combat, restraints, dialogue, and intimacy)
            import game_engine as local_game_engine
            is_combat = bool(local_game_engine.get_active_enemies(session) or local_game_engine.get_active_enemies(res))
            if not is_combat and not is_player_restrained and not in_active_dialogue_turn and not in_active_intimate_turn:
                if not any("observe your surroundings" in str(c.get("label", "")).lower() for c in curr_choices if isinstance(c, dict)):
                    curr_choices.append({
                        "label": "Observe your surroundings and inspect those present",
                        "stat": "FREE",
                        "requirement": 0,
                        "mp_cost": 0
                    })

            res["choices"] = curr_choices
            res["next_choices"] = curr_choices

    return res


async def evaluate_action(
    session_id: int,
    user_action: str,
    party: list,
    current_location: str = "",
    current_npcs: list | None = None,
    nearby_enemies: list | None = None,
    history_text: str = "",
) -> dict:
    """Evaluate a synthetic or system-initiated action against a session via resolve_turn."""
    import db
    from skill_check import CheckResult
    session = db.get_session(session_id) or {
        "id": session_id,
        "current_location": current_location,
        "current_npcs": current_npcs or [],
        "nearby_enemies": nearby_enemies or [],
        "history": [history_text] if history_text else [],
    }
    session.setdefault("history", [history_text] if history_text else [])
    actor_char = (
        party[0][0]
        if party and isinstance(party[0], (list, tuple)) and party[0]
        else (party[0] if party and isinstance(party[0], dict) else {"name": "Adventurer", "user_id": 0, "max_hp": 100})
    )
    actions = [{
        "char": actor_char,
        "character": actor_char,
        "label": user_action,
        "action": user_action,
        "mp_spent": 0,
        "check": CheckResult(
            chance=100, roll=100.0, tier="success",
            tier_label="Success", succeeded=True, requirement=0
        ),
        "roll": None,
        "stat": "CHA",
        "stat_mod": 0,
        "total": None,
    }]
    outcome = await resolve_turn(session, party, actions)
    if hasattr(outcome, "to_dict"):
        d = outcome.to_dict()
    elif isinstance(outcome, dict):
        d = dict(outcome)
    else:
        d = {}
    d.setdefault("outcome_narrative", d.get("next_narrative") or d.get("narrative", ""))
    d.setdefault("npcs_present", d.get("current_npcs", current_npcs or []))
    d.setdefault("location", d.get("new_location") or current_location)
    return d






