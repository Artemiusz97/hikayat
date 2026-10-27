from __future__ import annotations
from typing import Any
import json
import re
import random
import game_engine
from game_engine.core import *
from game_engine.core import _get_npc_name, _norm_dialogue_name
from game_engine.matching import matches_keyword_boundary


# ── Canonical dialogue stall verb registry (single source of truth for both npcs.py and turn.py)

DIALOGUE_STALL_VERBS: tuple = (

    "propose", "suggest", "analyze", "examine", "consider", "evaluate", "assess", "outline",

    "elaborate", "detail", "explain", "describe", "discuss", "review", "reflect", "theorize",

    "hypothesize", "present", "lay out", "walk through", "break down", "summarize",

    "plan", "strategize", "coordinate", "draft", "formulate",

)





def count_dialogue_stall_turns(history: list, window: int = 8) -> int:

    """

    Counts how many of the last `window` action labels match proposal/analysis stall verbs.

    Uses the canonical DIALOGUE_STALL_VERBS registry — the single source of truth.

    """

    labels = []

    for h in (history or [])[-window:]:

        act = (h.get("action_label") or h.get("action") or "") if isinstance(h, dict) else str(h)

        if act:

            labels.append(act.lower())

    return sum(

        1 for lbl in labels

        if any(lbl.strip().startswith(v) or f" {v} " in lbl for v in DIALOGUE_STALL_VERBS)

    )





def compute_scene_beat_linger_turns(
    history: list,
    session: dict = None,
    active_partners: list = None,
) -> int:
    """
    Counts consecutive turns in the same scene beat with the same dialogue partner(s)
    where no location change, quest milestone, combat, or physical state shift occurred.
    """
    if not history or not isinstance(history, list):
        return 0

    curr_loc = str((session or {}).get("current_location", "")).lower()
    partners = [
        str(p).strip().lower()
        for p in (active_partners or ((session or {}).get("dialogue_partners") or ([session["dialogue_partner"]] if (session or {}).get("dialogue_partner") else [])))
        if p
    ]
    import namegen
    partner_tokens = set()
    for p in partners:
        partner_tokens.add(p)
        partner_tokens |= namegen.get_unique_person_tokens(p, peer_names=partners, min_len=2)

    linger_turns = 0
    for h in reversed(history):
        if not isinstance(h, dict):
            break
        # Opening scene records are not dialogue turns
        if h.get("type") == "scene":
            break
        h_loc = str(h.get("location") or h.get("current_location") or "").lower()
        if curr_loc and h_loc and h_loc != curr_loc:
            break
        h_intent = str(h.get("intent") or h.get("action_intent") or "").lower().strip()
        if h_intent in ("movement", "dialogue_exit"):
            break
        lbl = str(h.get("label") or h.get("action_label") or h.get("action") or "").lower()
        movement_kws = (
            "travel to", "head to", "walk to", "go to", "leave room", "step away",
            "depart", "move to", "walk away", "exit", "farewell", "goodbye", "bye", "head out"
        )
        if matches_keyword_boundary(lbl, movement_kws, allow_negated=False):
            break

        # Only break on quest updates if an actual milestone was reached (completed or failed)
        if h.get("completed_sub_quest_ids"):
            break
        q_updates = h.get("quest_updates") or []
        if isinstance(q_updates, list) and any(
            isinstance(q, dict) and str(q.get("status") or "").lower() in ("completed", "failed")
            for q in q_updates
        ):
            break

        if h.get("combat_encounter") or h.get("nearby_enemies"):
            break

        # Partner continuity check: if active partners exist, ensure turn involved at least one partner
        if partner_tokens:
            h_target = str(h.get("target_npc") or "").lower().strip()
            if h_target and any(matches_keyword_boundary(h_target, tok) for tok in partner_tokens):
                # Explicit target matches partner
                pass
            else:
                wits = [str(w).strip().lower() for w in (h.get("witnessed_by") or []) if w]
                wit_match = any(any(matches_keyword_boundary(w, tok) for tok in partner_tokens) for w in wits)
                nar_text = str(h.get("outcome_narrative") or h.get("narrative") or "").lower()
                text_match = any(matches_keyword_boundary(lbl, tok) or matches_keyword_boundary(nar_text, tok) for tok in partner_tokens)
                if wits and not wit_match and not text_match:
                    break

        linger_turns += 1

    return linger_turns


def format_organic_npc_initiative_directive(
    linger_turns: int,
    npc: dict,
    current_location: str = "",
    time_slot: str = "",
    dialogue_type: str = "social",
    bounty_title: str = "",
    current_minute: int = 480,
    scen_key: str = "fantasy",
) -> str:
    """
    Formats graduated, organic in-character initiative directives based on linger turns:
      - linger_turns < 2: "" (natural early flow)
      - linger_turns == 2 (Stage 1 — Organic Beat Pivot): Proactive topic transition grounded in agenda, active prop, or task
      - linger_turns >= 3 (Stage 2 — Physical & Schedule Initiative): Proactive physical movement, schedule transition, or decisive move
    """
    if linger_turns < 2:
        return ""

    partner_str = _get_npc_name(npc) if isinstance(npc, dict) else str(npc)
    if not partner_str or partner_str == "None":
        partner_str = "Dialogue Partner"

    task_ref = f" on the task '{bounty_title}'" if bounty_title else ""

    if dialogue_type == "bounty":
        if linger_turns >= 3:
            return (
                f"- ⚠️ BOUNTY STALL WARNING: The conversation with {partner_str} has continued for "
                f"{linger_turns} turns without committing{task_ref}. "
                f"Have {partner_str} firmly urge the player to accept and act on the bounty task now. "
                f"Generate at least 1 choice that directly commits to the task.\n"
            )
        return (
            f"- ⚠️ BOUNTY DEPTH: After {linger_turns} conversational turns, "
            f"ensure at least 1 choice commits to or advances the bounty task{task_ref}.\n"
        )

    if dialogue_type == "quest":
        if linger_turns >= 3:
            return (
                f"- ⚠️ QUEST INVESTIGATION LOOP DETECTED ({linger_turns} consecutive Proposal/Suggest/Analyze turns): "
                f"The conversation MUST reach a concrete turning point this turn. "
                f"Have {partner_str} issue a direct demand, ultimatum, revelation, or personal challenge. "
                f"BANNED THIS TURN: 'Propose...', 'Suggest...', 'Analyze...', 'Outline...'. Replace with direct, committal choices.\n"
            )
        return (
            f"- ⚠️ DEPTH WARNING: After {linger_turns} planning turns, ensure at least 1 choice this turn "
            f"is a CONCRETE COMMITMENT or skill check — not another proposal.\n"
        )

    # Social / casual hangout / phone meetup
    blocking = npc.get("micro_blocking") if isinstance(npc, dict) and isinstance(npc.get("micro_blocking"), dict) else {}
    active_prop = blocking.get("active_prop", "their belongings") if isinstance(blocking, dict) else "their belongings"
    agenda = (npc.get("immediate_agenda") if isinstance(npc, dict) else "") or ""
    open_thread = (npc.get("open_thread") if isinstance(npc, dict) else "") or ""

    if linger_turns == 2:
        pivot_topic = open_thread or agenda or f"their task with {active_prop}"
        return (
            f"- ☕ SOCIAL HANGOUT MOMENTUM (Stage 1 — Natural Beat Pivot): Keep dialogue grounded in personal connection, authentic reactions, "
            f"and humor rather than analytical proposals. {partner_str} naturally pivots the topic to something authentic to them: {pivot_topic} (Active Prop: {active_prop}).\n"
        )

    # Stage 2: linger_turns >= 3
    sched_hint = ""
    if isinstance(npc, dict):
        try:
            from mechanics.world.schedules import get_npc_scheduled_location
            sl = get_npc_scheduled_location(npc, current_minute=current_minute, scen_key=scen_key, time_slot=time_slot)
            if sl and str(sl).strip().lower() != str(current_location or "").strip().lower():
                sched_hint = f" or invites walking toward {sl}"
        except Exception:
            pass

    return (
        f"- ☕ SOCIAL HANGOUT PROGRESSION: The casual conversation with {partner_str} has continued for "
        f"{linger_turns} turns. Keep the mood warm, relaxed, and natural. Advance the interaction naturally "
        f"(e.g. order refreshments, share a personal memory/joke, transition to an activity, help with {active_prop}{sched_hint}, or conclude the meetup). "
        f"STRICTLY FORBIDDEN: Do NOT turn this into a challenge, trial, or ultimatum!\n"
    )


def format_dialogue_stall_directive(
    stall_count: int,
    dialogue_type: str,
    partner_str: str,
    bounty_title: str = ""
) -> str:
    """
    Compatibility wrapper forwarding to format_organic_npc_initiative_directive.
    """
    return format_organic_npc_initiative_directive(
        linger_turns=stall_count,
        npc={"name": partner_str},
        dialogue_type=dialogue_type,
        bounty_title=bounty_title,
    )


_TENSION_ESCALATION_KEYWORDS = (
    "hammer", "hammering", "patrol", "patrols", "sentry", "sentries",
    "barricade", "barricaded", "breach", "breaching", "alarm", "alarms", "countdown",
    "seconds away", "moments before", "collapse", "collapsing", "intruder",
    "intruders", "ward-lines", "backlash", "locked in", "forced entry", "pounding",
    "shattered circle", "defender", "defenders", "assault", "assaulting", "siege",
    "standoff", "stand-off", "hostile standoff", "ambush",
)


def evaluate_and_tick_scene_tension_timer(
    session: dict,
    actions: list = None,
    is_movement: bool = False,
    access_gated: bool = False,
) -> dict:
    """
    Deterministically tracks and increments `session['scene_tension_timer']`.
    When `scene_tension_timer >= 2`, spawns a canonical patrol NPC (in non-combat scenarios)
    or a hostile enemy (in combat scenarios) directly into the pre-turn stage state.

    Returns:
      {
        "timer": int,
        "expired": bool,
        "spawned_patrol_npc": dict | None,
        "spawned_hostile_enemy": dict | None,
        "stage_direction": str,
      }
    """
    if not isinstance(session, dict):
        return {"timer": 0, "expired": False, "spawned_patrol_npc": None, "spawned_hostile_enemy": None, "stage_direction": ""}

    import scenario_data
    from mechanics.social.physical_state import is_erotic_intimate_contact

    scen_key = session.get("scenario") or "fantasy"
    is_non_combat = scenario_data.is_non_combat_scenario(scen_key)
    phys_st = session.get("physical_state") or {}
    if is_erotic_intimate_contact(str(phys_st.get("intimate_contact", ""))):
        session["scene_tension_timer"] = 0
        return {"timer": 0, "expired": False, "spawned_patrol_npc": None, "spawned_hostile_enemy": None, "stage_direction": ""}

    # Reset timer if the player successfully moved to a new location (without being halted at a gate)
    if is_movement and not access_gated:
        session["scene_tension_timer"] = 0
        return {"timer": 0, "expired": False, "spawned_patrol_npc": None, "spawned_hostile_enemy": None, "stage_direction": ""}

    # Do not tick or spawn tension-timer enemies inside safe Hub locations or during peaceful 1-on-1 NPC dialogue
    from mechanics.world.locations import is_hub_location
    from mechanics.world.mobility import get_session_dialogue_partners
    curr_loc_str = str(session.get("current_location") or "")
    if not access_gated and (is_hub_location(curr_loc_str) or bool(get_session_dialogue_partners(session))):
        session["scene_tension_timer"] = 0
        return {"timer": 0, "expired": False, "spawned_patrol_npc": None, "spawned_hostile_enemy": None, "stage_direction": ""}

    curr_timer = int(session.get("scene_tension_timer") or 0)
    history = session.get("history") or []
    intimate_prose_markers = ("climax", "orgasm", "aftercare", "aftershocks", "moan", "kiss", "thighs", "arousal", "cunnilingus", "fellatio")

    # Check if latest history entry or current state has active tension
    history_tension_count = 0
    for h in history[-6:]:
        if isinstance(h, dict):
            h_nar = f"{h.get('outcome_narrative') or ''} {h.get('narrative') or ''} {h.get('next_narrative') or ''}".lower()
        elif isinstance(h, str):
            h_nar = h.lower()
        else:
            continue
        if h_nar.strip():
            has_t = matches_keyword_boundary(h_nar, _TENSION_ESCALATION_KEYWORDS, allow_negated=False)
            has_i = matches_keyword_boundary(h_nar, intimate_prose_markers, allow_negated=False)
            if has_t and not has_i:
                history_tension_count += 1

    # Also check if player is trespassing on campus after hours or repeatedly failing at a locked gate
    has_failed_gate_action = False
    if access_gated and actions:
        for a in actions:
            if isinstance(a, dict):
                chk = a.get("check")
                tier = getattr(chk, "tier", None) or (chk.get("tier") if isinstance(chk, dict) else None)
                if a.get("success") is False or tier in ("fail", "crit_fail"):
                    has_failed_gate_action = True
                    break

    if history_tension_count > 0 or has_failed_gate_action:
        curr_timer = max(curr_timer + 1 if history_tension_count >= 1 or has_failed_gate_action else curr_timer, history_tension_count)
    else:
        curr_timer = 0

    session["scene_tension_timer"] = curr_timer
    if curr_timer < 2:
        return {"timer": curr_timer, "expired": False, "spawned_patrol_npc": None, "spawned_hostile_enemy": None, "stage_direction": ""}

    # Timer expired (>= 2)! Deterministically spawn patrol NPC or hostile enemy if not already present
    curr_npcs = session.get("current_npcs") or []
    curr_enemies = session.get("nearby_enemies") or []
    spawned_patrol = None
    spawned_enemy = None
    stage_dir = ""

    if is_non_combat:
        # Check if a patrol / disciplinary / authority NPC is already on stage
        has_authority = any(
            any(k in str((n.get("role") if isinstance(n, dict) else "") or "").lower() for k in ("guard", "monitor", "prefect", "teacher", "security", "patrol", "faculty"))
            for n in curr_npcs
        )
        if not has_authority:
            import namegen
            patrol_role = "Disciplinary Prefect" if "school" in str(scen_key).lower() else "Security Guard"
            patrol_name = namegen.generate_person_name(scenario=scen_key)
            spawned_patrol = {
                "name": patrol_name,
                "role": patrol_role,
                "status_effects": ["Present", "Alert"],
                "stage_role": "active_partner",
                "attention_ring": "ring_1_primary",
            }
            stage_dir = (
                f"[STAGE DIRECTION — TENSION TIMER EXPIRED]: {patrol_name} ({patrol_role}) arrives on the scene "
                f"to investigate the commotion and directly confronts the party!"
            )
    else:
        # Combat-capable scenario: if no active enemies yet and history had sentry/patrol tension, spawn a sentry
        if not curr_enemies and history_tension_count >= 2:
            try:
                from mechanics.combat.enemies import generate_scenario_enemy
                spawned_enemy = generate_scenario_enemy(
                    scenario=scen_key,
                    location=session.get("current_location", "area"),
                    chapter=int(session.get("chapter", 1) or 1),
                )
                enemy_nm = spawned_enemy.get("name", "Sentry")
                stage_dir = (
                    f"[STAGE DIRECTION — TENSION TIMER EXPIRED]: The standoff breaches! "
                    f"{enemy_nm} forces entry into the scene ({spawned_enemy.get('hp', 20)} HP)!"
                )
            except Exception:
                pass

    return {
        "timer": curr_timer,
        "expired": True,
        "spawned_patrol_npc": spawned_patrol,
        "spawned_hostile_enemy": spawned_enemy,
        "stage_direction": stage_dir,
    }


def build_scene_escalation_and_consequence_directives(

    session: dict,

    party: list,

    actions: list,

    story_quest: dict = None,

    in_dialogue_mode: bool = False,

) -> str:

    """

    Detects if a scene is stalling in a high-tension loop, investigation saturation,

    dialogue loop, or ticking-clock crisis, and injects mandatory escalation directives.



    When `in_dialogue_mode=True` (set by resolve_turn when dialogue_prompt_block is active),

    the dialogue stall directive is intentionally skipped here because dialogue_prompt_block

    in turn.py is the single authoritative insertion point — preventing duplicate injection.

    """

    directives = []



    # 1. Ticking Clock & Scene Escalation Tracker (Combat / Hazard scenarios outside active intimacy)
    import scenario_data
    from mechanics.social.physical_state import is_erotic_intimate_contact
    scen_key = (session.get("scenario") if isinstance(session, dict) else None) or "fantasy"
    phys_st = (session.get("physical_state") if isinstance(session, dict) else None) or {}
    if not phys_st and isinstance(session, dict) and session.get("id"):
        try:
            phys_st = db.get_session_physical_state(session["id"]) or {}
        except Exception:
            phys_st = {}
    history = session.get("history") or []
    is_intimate_scene = is_erotic_intimate_contact(str(phys_st.get("intimate_contact", "")))
    is_non_combat = scenario_data.is_non_combat_scenario(scen_key)

    if not is_intimate_scene and not is_non_combat:

        tension_keywords = (
            "hammer", "hammering", "patrol", "patrols", "sentry", "sentries",
            "barricade", "barricaded", "breach", "breaching", "alarm", "alarms", "countdown",
            "seconds away", "moments before", "collapse", "collapsing", "intruder",
            "intruders", "ward-lines", "backlash", "locked in", "forced entry", "pounding",
            "shattered circle", "defender", "defenders", "assault", "assaulting", "siege",
            "standoff", "stand-off", "hostile standoff", "ambush"
        )
        intimate_prose_markers = (
            "climax", "orgasm", "aftercare", "aftershocks", "moan", "kiss", "thighs", "arousal", "cunnilingus", "fellatio"
        )

        recent_tension_count = 0
        for h in history[-6:]:
            if isinstance(h, dict):
                h_narrative = (
                    str(h.get("outcome_narrative") or "") + " " +
                    str(h.get("narrative") or "") + " " +
                    str(h.get("next_narrative") or "")
                ).lower()
            elif isinstance(h, str):
                h_narrative = h.lower()
            else:
                continue

            if not h_narrative.strip():
                continue
            has_tension = matches_keyword_boundary(h_narrative, tension_keywords, allow_negated=False)
            has_intimacy = matches_keyword_boundary(h_narrative, intimate_prose_markers, allow_negated=False)
            if has_tension and not has_intimacy:
                recent_tension_count += 1

        if recent_tension_count >= 2:
            directives.append(
                "⚡ [MANDATORY SCENE ESCALATION & TICKING CLOCK DIRECTIVE]:\n"
                "The ticking clock has EXPIRED! High tension / impending threats (e.g. sentries outside, collapsing architecture, alarms, breaching guards) CANNOT remain in a static 'seconds away' or 'hammering' state any longer.\n"
                "- You MUST force the breach / catastrophe / confrontation THIS TURN in `outcome_narrative`!\n"
                "- If guards/enemies were pounding on doors or barriers, the doors SMASH OPEN or the trap TRIGGERS now!\n"
                "- If the player failed or lingered, apply immediate consequences (HP damage in character_outcomes, being spotted, cornered status, or direct combat encounter).\n"
                "- STRICTLY PROHIBITED: Do NOT write that the threat is 'still waiting outside' or 'seconds away'."
            )



    # 2. Investigation Node Saturation & Clue Cap

    clues_list = game_engine.parse_clue_list(story_quest.get("current_clues")) if story_quest else []

    if len(clues_list) >= 3:

        directives.append(

            f"🔍 [INVESTIGATION SATURATED - NO MORE CLUES IN THIS NODE]:\n"

            f"The party has already uncovered {len(clues_list)} investigation clues from this area. The current anomaly/room has yielded ALL its forensic secrets.\n"

            "- STRICTLY PROHIBITED: Do NOT output further investigation notes in `current_clues` for this same object/room.\n"

            "- In `next_choices`, do NOT generate repetitive '[INT] Decode / Appraise / Analyze' choices for this room's anomaly. All choices MUST be active forward momentum (movement, dialogue resolution, confrontation, or using discovered knowledge to escape)."

        )



    # 3. Dialogue Loop / Conversation Stall Detection

    # When resolve_turn is in dialogue mode, dialogue_prompt_block is the single injection point.

    # Skip here to avoid contradictory or duplicated stall directives in the LLM prompt.

    if not in_dialogue_mode:

        stall_count = count_dialogue_stall_turns(history)

        current_dp = get_session_dialogue_partners(session)
        is_in_dialogue = bool(current_dp)



        if is_in_dialogue and stall_count >= 2:

            session_id_val = session.get("id")

            partner_names_lower = [p.lower() for p in current_dp]



            has_phone_meetup = False

            target_of_quest = False

            is_bounty_contact = False

            bounty_title = ""

            action_was_quest = any(bool(a.get("is_quest_action") or a.get("is_climax_action")) for a in (actions or []))



            if session_id_val:

                try:

                    appts = db.get_phone_appointments(session_id_val, status="pending") + db.get_phone_appointments(session_id_val, status="arrived")

                    for appt in appts:

                        a_name = str(appt.get("npc_name", "")).lower().strip()

                        if a_name and any(pn in a_name or a_name in pn for pn in partner_names_lower):

                            has_phone_meetup = True

                            break



                    active_wps = db.get_all_session_active_waypoints(session_id_val)



                    # Check for active bounty/commission contact first

                    side_quests = [q for q in db.get_session_quests(session_id_val, status="Active")

                                   if not q.get("is_story_quest") and q.get("quest_type") not in ("Story Quest", "Main Quest")]

                    for bq in side_quests:

                        bq_text = f"{bq.get('title', '')} {bq.get('objective', '')}".lower()

                        bq_wps = db.get_quest_waypoints(session_id_val, bq.get("quest_id", ""), sub_obj_id=None) if bq.get("quest_id") else []

                        for pn in partner_names_lower:

                            matched = any(pn in (str(w.get("target_npc", "")).lower()) or pn in bq_text

                                          for w in bq_wps) or pn in bq_text

                            if matched:

                                is_bounty_contact = True

                                bounty_title = bq.get("title", "")

                                break

                        if is_bounty_contact:

                            break



                    if not is_bounty_contact:

                        for wp in active_wps:

                            t_npc = str(wp.get("target_npc", "")).lower().strip()

                            if t_npc and any(pn in t_npc or t_npc in pn for pn in partner_names_lower):

                                target_of_quest = True

                                break

                            wp_text = f"{wp.get('title', '')} {wp.get('objective', '')} {wp.get('notes', '')} {wp.get('stage_label', '')}".lower()

                            for pn in partner_names_lower:

                                if pn in wp_text:

                                    target_of_quest = True

                                    break

                            if target_of_quest:

                                break



                    if story_quest and not target_of_quest and not is_bounty_contact:

                        sq_text = f"{story_quest.get('title', '')} {story_quest.get('objective', '')}".lower()

                        for so in (story_quest.get("sub_objectives") or []):

                            if isinstance(so, dict):

                                sq_text += f" {so.get('text', '')}".lower()

                        for pn in partner_names_lower:

                            if pn in sq_text:

                                target_of_quest = True

                                break

                except Exception:

                    pass



            partner_str = ", ".join(current_dp)



            # Use unified formatter — bounty takes priority over quest/social to prevent contradiction

            if is_bounty_contact and not has_phone_meetup:

                dialogue_type = "bounty"

            elif (target_of_quest or action_was_quest) and not has_phone_meetup:

                dialogue_type = "quest"

            else:

                dialogue_type = "social"



            stall_directive = format_dialogue_stall_directive(stall_count, dialogue_type, partner_str, bounty_title)

            if stall_directive:

                # Emit as a proper QUEST/SOCIAL label in directive_note for non-turn.py callers

                if dialogue_type == "bounty":

                    directives.append(

                        f"⚠️ [BOUNTY CONTACT DIALOGUE STALL]:\n{stall_directive.lstrip('- ')}"

                    )

                elif dialogue_type == "quest":

                    directives.append(

                        f"🔄 [QUEST INVESTIGATION LOOP]:\n{stall_directive.lstrip('- ')}"

                    )

                else:

                    directives.append(

                        f"☕ [SOCIAL DIALOGUE MOMENTUM]:\n{stall_directive.lstrip('- ')}"

                    )



    # 4. Contextual Sub-Objective Progression Guidance

    if story_quest:

        sub_objs = story_quest.get("sub_objectives") or []

        completed = [so for so in sub_objs if isinstance(so, dict) and so.get("completed")]

        uncompleted = [so for so in sub_objs if isinstance(so, dict) and not so.get("completed")]



        if completed:

            comp_lines = []

            for so in completed:

                comp_lines.append(f"- Sub-Objective #{so.get('id')} [{so.get('archetype', 'Cleared')}]: {so.get('text', '')[:70]}... (COMPLETED)")

            comp_block = "\n".join(comp_lines)

            directives.append(

                f"🚫 [COMPLETED OBJECTIVES & CLEARED SITES - STRICTLY FORBIDDEN IN CHOICES]:\n"

                f"The following sub-objectives and physical sites have ALREADY been fully cleared:\n{comp_block}\n"

                "- STRICTLY PROHIBITED IN `next_choices`: NEVER generate travel choices, return actions, or dialogue options suggesting traveling back to, looking for, or asking directions toward these completed locations!\n"

                "- Direct all travel choices and forward momentum exclusively toward the REMAINING ACTIVE objectives or new exploration!"

            )



        if uncompleted:

            cur_loc_lower = str(session.get("current_location", "")).lower()

            action_text_lower = " ".join(str(a.get("label", "")).lower() for a in actions)

            

            # Check if any uncompleted sub-objective matches the CURRENT LOCATION.

            matching_so = None

            for so in uncompleted:

                so_text = (str(so.get("text", "")) + " " + str(so.get("archetype", ""))).lower()

                stopwords = {"the", "and", "with", "from", "that", "this", "into", "before", "after", "then", "your", "their", "will", "have", "turn", "hero", "party"}

                tokens = [t.strip(".,'\"():;[]") for t in so_text.split() if len(t.strip(".,'\"():;[]")) > 4 and t not in stopwords]

                if any(t in cur_loc_lower for t in tokens):

                    matching_so = so

                    break

            

            if matching_so:

                target_id = matching_so.get("id", 1)

                directives.append(
                    f"📜 [SUB-QUEST PROGRESSION GUIDANCE (Sub-Objective #{target_id})]:\n"
                    f"The party is actively in the location/context for Sub-Objective #{target_id} ('{matching_so.get('text', '')[:80]}...').\n"
                    f"- If the chosen action SUCCEEDS in resolving this specific obstacle, mark it complete via `completed_sub_quest_ids: [{target_id}]`.\n"
                    f"- If the action FAILS, apply fail-forward consequences (damage, complication, or crisis) without a clean checkmark.\n"
                    f"- CRITICAL FAILURE: The objective fails or triggers a major catastrophe/capture.\n"
                    f"- 🚫 STRICT IN-CHARACTER IMMERSION RULE: NEVER write 'Sub-Objective #{target_id}', 'Sub-Objective', 'Sub-Quest', or internal tracker IDs in character dialogue or story narration. In-universe, characters must naturally refer to the actual plot element (e.g. investigating the rumors, interrogating the witness, uncovering the sabotage)!"
                )


            else:

                next_targets = ", ".join(f"#{so.get('id')} ({so.get('archetype', 'Objective')})" for so in uncompleted[:2])

                directives.append(

                    f"🧭 [SUB-QUEST TRANSITION GUIDANCE]:\n"

                    f"Active uncompleted sub-quests: {next_targets}.\n"

                    "- The party is not currently at these quest locations. Guide travel and choice options toward these destinations.\n"

                    "- STRICTLY PROHIBITED: Do NOT mark unvisited sub-quests as completed in `completed_sub_quest_ids` until the party physically arrives at the target location and resolves its obstacle!"

                )

        elif story_quest and completed and not uncompleted:

            from mechanics.world.waypoints import get_story_quest_climax_location, check_location_matches_waypoint

            _, climax_loc = get_story_quest_climax_location(session["id"])

            cur_loc = session.get("current_location", "")

            at_climax = bool(climax_loc and check_location_matches_waypoint(cur_loc, climax_loc))



            if at_climax:

                directives.append(

                    f"⚡ [STORY QUEST CLIMAX ENCOUNTER READY — FINAL RESOLUTION]:\n"

                    f"All preliminary sub-objectives for '{story_quest.get('title', 'Story Quest')}' are COMPLETED!\n"

                    f"The party is physically at the Climax destination ({climax_loc}).\n"

                    f"- This turn MUST stage or conclusively resolve the final chapter showdown / climax confrontation!\n"

                    f"- When the chosen action succeeds, you MUST output `status: \"Completed\"` in `quest_updates` for this quest.\n"

                    f"- When `status: \"Completed\"`, you MUST provide `next_chapter_quest` with the title, archetype, objective, and 3-5 fresh sub-objectives for the NEXT story quest chapter!\n"

                    f"- Include at least 1 dedicated forward-advancing climax action in `next_choices` marked with ⚡."

                )

            else:

                directives.append(

                    f"⚡ [STORY QUEST CLIMAX READY — TRAVEL TO DESTINATION]:\n"

                    f"All preliminary sub-objectives are completed! The final showdown is waiting at {climax_loc}.\n"

                    f"- Guide the player to travel to {climax_loc} for the Climax Encounter.\n"

                    f"- Provide travel and movement choices in `next_choices`."

                )



    return "\n\n".join(directives)



def get_session_dialogue_partners(session: dict | None) -> list[str]:
    """Returns canonical list of active dialogue partners from session."""
    from mechanics.world.mobility import get_session_dialogue_partners as _mobility_get_dps
    return _mobility_get_dps(session)


def is_dialogue_partner(name: str, dialogue_partners: list | str = None, session: dict = None) -> bool:
    """Returns True if the entity name matches any active dialogue partner."""
    from mechanics.world.mobility import is_dialogue_partner as _mobility_is_dialogue_partner
    return _mobility_is_dialogue_partner(name, dialogue_partners, session=session)



DIALOGUE_TITLE_WORDS: set[str] = {
    "the", "elder", "lord", "lady", "sir", "madam", "captain", "dr", "mr", "ms", "mrs",
    "druid", "scholar", "guardian", "student", "council", "president", "vice", "secretary",
    "representative", "officer", "member", "guildmaster", "archivist", "warden", "guard",
    "patron", "shopkeeper", "innkeeper", "headmaster", "dean", "professor", "teacher",
    "coach", "trainer", "instructor", "principal", "referee", "sensei", "bartender", "nurse", "clerk", "vendor",
    "bin", "binti", "ibn", "bint", "van", "von", "der", "den", "het", "ten", "ter", "del", "della", "degli", "das", "dos"
}


def is_npc_invited_in_action(npc_name: str, actions: list, session: dict = None) -> bool:
    """Checks if any player action explicitly invites or recruits an NPC to travel."""
    if not npc_name or not actions:
        return False

    import namegen
    import re
    n_low = npc_name.lower().strip()
    given_token = namegen.get_given_name(npc_name).lower().strip()
    peer_pool = (session.get("current_npcs") or []) + (session.get("pre_turn_stage_npcs") or []) if isinstance(session, dict) else None
    disambig_toks = namegen.get_unique_person_tokens(npc_name, peer_names=peer_pool, min_len=2)
    token_candidates = {
        t for t in ({given_token} | disambig_toks)
        if len(t) >= 2 and t != n_low and t not in namegen.NAME_PARTICLES_AND_HONORIFICS
    }

    strict_dismissal_terms = (
        "goodbye", "farewell", "part ways", "split up", "alone",
        "dismiss", "see you later", "by yourself", "on your own"
    )
    solo_exit_terms = (
        "leave", "depart", "go home", "head home", "step away", "excuse yourself"
    )

    follow_terms = (
        "join", "come with", "come along", "follow", "accompany", "with us",
        "travel with", "explore with", "together", "walk with", "head home with", "head with",
        "bring along", "tag along", "carry", "escort", "guide", "lead", "help carry",
        "walk to class", "walk to homeroom", "walk together", "head out together"
    )

    is_dp = False
    if session:
        try:
            from mechanics.world.mobility import is_dialogue_partner
            is_dp = is_dialogue_partner(npc_name, session=session)
        except Exception:
            is_dp = False

    for a in actions:
        label = (a.get("label") if isinstance(a, dict) else str(a)).lower()
        t_npc = (str(a.get("target_npc") or "").strip().lower()) if isinstance(a, dict) else ""
        
        is_targeted = bool(
            t_npc and (t_npc == n_low or any(ft in t_npc for ft in token_candidates))
        )
        is_named_in_label = bool(
            n_low in label or any(ft in label for ft in token_candidates)
        )
        is_dp_escort = bool(
            is_dp and (
                any(ft in label for ft in follow_terms)
                or re.search(r"\b(?:carry|walk|escort|guide|lead|take|bring|help|accompany)\b.*\b(?:her|him|them)\b", label)
            )
        )

        if is_targeted or is_named_in_label or is_dp_escort:
            # If the action explicitly says goodbye, parts ways, or goes alone, it is NEVER an invitation
            if any(dt in label for dt in strict_dismissal_terms):
                return False
            if any(ft in label for ft in follow_terms):
                return True
            if any(k in label for k in ("invite", "recruit", "hire")) and any(kw in label for kw in ("party", "companion", "journey", "adventure", "travel")):
                return True
            if re.search(r"\b(?:carry|walk|escort|guide|lead|take|bring|help|accompany)\b", label):
                return True
            if any(dt in label for dt in solo_exit_terms):
                return False
            if is_targeted or is_dp_escort:
                return True

    return False


def evaluate_scene_attention_transition(
    npc_name: str,
    *,
    retained_partners: list[str] | None = None,
    actions: list | None = None,
    narrative: str | None = None,
    session: dict | None = None,
    party: list | None = None,
    npcs_present: list | None = None,
) -> bool:
    """
    Determines whether an NPC who speaks or acts in the turn can chime into an
    ongoing conversation with `retained_partners`.

    Rules:
    1. If no active conversation exists (not retained_partners), any speaker is allowed.
    2. If npc_name is already one of the active retained partners, allow.
    3. If player explicitly addresses or mentions the NPC in action choices, allow.
    4. If the NPC is a party companion (in player party or session_party_npcs), allow.
    5. If the NPC is relevant to an active quest (Story Quest target/objective,
       side quest, active waypoint, or rendezvous target), allow.
    6. If the NPC directly engages the player, retained partners, or ongoing dialogue
       in the narrative prose (e.g. addressed to 'you', mentions partner names,
       uses conversational/interjection verbs like interject/agree/propose/interrupt),
       and is NOT an ambient third-party interaction (e.g. barking orders at freshmen,
       shouting at drunken patrons), allow.
    """
    if not npc_name or str(npc_name).strip().lower() in ("none", ""):
        return False

    if not retained_partners:
        return True

    # 1. Already an active partner?
    if any(is_dialogue_partner(npc_name, [p]) for p in retained_partners):
        return True

    n_norm = game_engine._norm_dialogue_name(npc_name)
    n_tokens = [t for t in n_norm.split() if len(t) > 2 and t not in DIALOGUE_TITLE_WORDS]
    if not n_tokens and len(n_norm) > 2:
        n_tokens = [n_norm]

    # Collect player and party tokens to prevent player name collisions from triggering attention transitions
    party_tokens = set()
    if party:
        for p_entry in party:
            p_char = p_entry[0] if isinstance(p_entry, (list, tuple)) and p_entry else p_entry
            if isinstance(p_char, dict) and p_char.get("name"):
                for t in game_engine._norm_dialogue_name(str(p_char["name"])).split():
                    if len(t) > 2 and t not in DIALOGUE_TITLE_WORDS:
                        party_tokens.add(t)
    n_tokens_filtered = [t for t in n_tokens if t not in party_tokens]

    # 2. Player explicitly addressed or invited them in their action?
    if actions:
        act_txt = " ".join(
            str(a.get("label", "")) if isinstance(a, dict) else str(a)
            for a in actions
        ).lower()
        if n_norm in act_txt or (bool(n_tokens_filtered) and any(t in act_txt for t in n_tokens_filtered)):
            return True

    # 3. Party Companion?
    if session:
        p_npcs = session.get("party_npcs") or []
        if any(is_dialogue_partner(npc_name, [p.get("name") if isinstance(p, dict) else str(p)]) for p in p_npcs):
            return True

        sess_id = session.get("id")
        if sess_id:
            try:
                import db
                db_party = db.get_session_party_npcs(sess_id)
                if any(is_dialogue_partner(npc_name, [p.get("name") if isinstance(p, dict) else str(p)]) for p in db_party):
                    return True
            except Exception:
                pass

    if party:
        for p_entry in party:
            p_char = p_entry[0] if isinstance(p_entry, (list, tuple)) and p_entry else p_entry
            if isinstance(p_char, dict):
                p_nm = p_char.get("name", "")
                if p_nm and is_dialogue_partner(npc_name, [p_nm]):
                    return True

    # 4. Quest Relevance (Story Quest, Waypoints, Rendezvous)?
    if session:
        sess_id = session.get("id")
        if sess_id:
            try:
                import db
                # Active Story Quest
                sq = db.get_active_story_quest(sess_id)
                if sq:
                    sq_txt = f"{sq.get('target_npc', '')} {sq.get('title', '')} {sq.get('objective', '')}".lower()
                    for so in (sq.get("sub_objectives") or []):
                        if isinstance(so, dict) and not so.get("completed"):
                            sq_txt += f" {so.get('target_npc', '')} {so.get('text', '')}".lower()
                    if n_norm in sq_txt or any(t in sq_txt for t in n_tokens):
                        return True

                # Active Waypoints
                active_wps = db.get_all_session_active_waypoints(sess_id)
                for wp in (active_wps or []):
                    wp_tgt = str(wp.get("target_npc", "")).lower()
                    wp_txt = f"{wp.get('title', '')} {wp.get('stage_label', '')}".lower()
                    if (wp_tgt and (n_norm in wp_tgt or wp_tgt in n_norm)) or any(t in wp_tgt for t in n_tokens):
                        return True
                    if n_norm in wp_txt or any(t in wp_txt for t in n_tokens):
                        return True

                # Rendezvous targets
                from mechanics.world.mobility import is_rendezvous_target
                if is_rendezvous_target(npc_name, session_id=sess_id, actions=actions):
                    return True
            except Exception:
                pass

    # 5. Direct Narrative Engagement / Focal Interjection vs Ambient Background
    if narrative:
        nar_norm = game_engine._norm_dialogue_name(narrative)
        sentences = [s.strip() for s in re.split(r'[.!?\n]+', nar_norm) if s.strip()]

        # Collect player identifiers
        player_names = set()
        if party:
            for p_entry in party:
                p_char = p_entry[0] if isinstance(p_entry, (list, tuple)) and p_entry else p_entry
                if isinstance(p_char, dict) and p_char.get("name"):
                    player_names.add(game_engine._norm_dialogue_name(p_char["name"]))

        # Collect partner tokens
        partner_tokens = set()
        for rp in (retained_partners or []):
            rp_norm = game_engine._norm_dialogue_name(rp)
            for t in rp_norm.split():
                if len(t) > 2 and t not in DIALOGUE_TITLE_WORDS:
                    partner_tokens.add(t)

        chime_in_verbs = {
            "interject", "interjects", "interjected", "interjecting",
            "interrupt", "interrupts", "interrupted", "interrupting",
            "chime", "chimes", "chimed", "chiming",
            "agree", "agrees", "agreed", "agreeing",
            "concur", "concurs", "concurred", "concurring",
            "counter", "counters", "countered", "countering",
            "add", "adds", "added", "adding",
            "propose", "proposes", "proposed", "proposing",
            "suggest", "suggests", "suggested", "suggesting",
            "step", "steps", "stepped", "stepping",
            "turn", "turns", "turned", "turning",
            "approach", "approaches", "approached", "approaching",
            "respond", "responds", "responded", "responding",
            "reply", "replies", "replied", "replying",
            "join", "joins", "joined", "joining",
            "face", "faces", "faced", "facing",
            "address", "addresses", "addressed", "addressing",
            "confront", "confronts", "confronted", "confronting",
            "demand", "demands", "demanded", "demanding",
            "nod", "nods", "nodded", "nodding",
            "ask", "asks", "asked", "asking",
            "warn", "warns", "warned", "warning",
            "exclaim", "exclaims", "exclaimed", "exclaiming",
            "explain", "explains", "explained", "explaining",
            "argue", "argues", "argued", "arguing",
            "note", "notes", "noted", "noting",
            "state", "states", "stated", "stating",
            "point", "points", "pointed", "pointing",
            "remark", "remarks", "remarked", "remarking",
            "insist", "insists", "insisted", "insisting",
            "discuss", "discusses", "discussed", "discussing",
            "debate", "debates", "debated", "debating",
            "advise", "advises", "advised", "advising",
            "voice", "voices", "voiced", "voicing",
            "opine", "opines", "opined", "opining",
            "weigh", "weighs", "weighed", "weighing",
        }

        ambient_targets = (
            "freshmen", "freshman", "team", "players", "cadets", "recruits",
            "patron", "patrons", "customer", "customers", "crowd", "audience",
            "passersby", "passerby", "guards", "soldiers", "wagons", "carts", "animals", "dog", "horse"
        )

        for idx, s in enumerate(sentences):
            if n_norm in s or (bool(n_tokens_filtered) and any(t in s for t in n_tokens_filtered)):
                # If subsequent sentence continues with quotes or pronoun attribution, combine for analysis
                s_eval = s
                if idx + 1 < len(sentences):
                    next_s = sentences[idx + 1]
                    if any(q in next_s for q in ('"', '“', '‘')) or any(pr in next_s.split()[:2] for pr in ("she", "he", "they")):
                        s_eval = f"{s} {next_s}"

                words = set(re.findall(r"\b\w+\b", s_eval))

                # Check if this sentence specifically targets a third-party ambient entity
                is_ambient_shout = False
                for at in ambient_targets:
                    if at in s_eval and any(prep in s_eval for prep in (f"at the {at}", f"to the {at}", f"orders to {at}", f"orders at {at}")):
                        is_ambient_shout = True
                        break

                if is_ambient_shout:
                    continue

                # A) Direct address to player (you, player character name)
                if words & {"you", "your", "yours", "we", "us", "both"} or any(pn in s_eval for pn in player_names):
                    return True

                # B) Direct address / proximity to existing dialogue partner
                if partner_tokens & words:
                    return True

                # C) Chime-in conversational verb
                verb_matches = words & chime_in_verbs
                if "notes" in verb_matches or "note" in verb_matches:
                    if any(np in s_eval for np in ("taking notes", "takes notes", "took notes", "her notes", "his notes", "the notes", "their notes", "some notes")):
                        verb_matches = verb_matches - {"notes", "note"}

                if verb_matches:
                    return True

                # D) In an intimate or focused group meeting (<= 8 NPCs present) with direct quotes
                has_quotes = any(q in s_eval for q in ('"', '“', '”', '‘', "'"))
                if has_quotes and npcs_present and len(npcs_present) <= 8:
                    return True

    return False


can_chime_in_to_dialogue = evaluate_scene_attention_transition

