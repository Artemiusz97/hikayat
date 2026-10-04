import json
import re
import random
import game_engine
from game_engine.core import *
from game_engine.core import _get_npc_name, _norm_dialogue_name


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





def format_dialogue_stall_directive(

    stall_count: int,

    dialogue_type: str,

    partner_str: str,

    bounty_title: str = ""

) -> str:

    """

    Returns the correct, non-contradictory stall directive for the given dialogue mode.



    dialogue_type must be one of:

      'bounty'  — NPC is a bounty/commission client: urge advancing the specific task.

      'quest'   — Story quest investigation: demand a decisive move or ultimatum.

      'social'  — Casual hangout, date, or phone meetup: natural pacing with no hostility.

    """

    if stall_count < 2:

        return ""



    if dialogue_type == "bounty":

        task_ref = f" on the task '{bounty_title}'" if bounty_title else ""

        if stall_count >= 3:

            return (

                f"- ⚠️ BOUNTY STALL WARNING: The conversation with {partner_str} has continued for "

                f"{stall_count} turns without committing{task_ref}. "

                f"Have {partner_str} firmly urge the player to accept and act on the bounty task now. "

                f"Generate at least 1 choice that directly commits to the task.\n"

            )

        return (

            f"- ⚠️ BOUNTY DEPTH: After {stall_count} conversational turns, "

            f"ensure at least 1 choice commits to or advances the bounty task{task_ref}.\n"

        )



    if dialogue_type == "quest":

        if stall_count >= 3:

            return (

                f"- ⚠️ QUEST INVESTIGATION LOOP DETECTED ({stall_count} consecutive Proposal/Suggest/Analyze turns): "

                f"The conversation MUST reach a concrete turning point this turn. "

                f"Have {partner_str} issue a direct demand, ultimatum, revelation, or personal challenge. "

                f"BANNED THIS TURN: 'Propose...', 'Suggest...', 'Analyze...', 'Outline...'. Replace with direct, committal choices.\n"

            )

        return (

            f"- ⚠️ DEPTH WARNING: After {stall_count} planning turns, ensure at least 1 choice this turn "

            f"is a CONCRETE COMMITMENT or skill check — not another proposal.\n"

        )



    # Social / casual hangout / phone meetup

    if stall_count >= 3:

        return (

            f"- ☕ SOCIAL HANGOUT PROGRESSION: The casual conversation with {partner_str} has continued for "

            f"{stall_count} turns. Keep the mood warm, relaxed, and natural. Advance the interaction naturally "

            f"(e.g. order refreshments, share a personal memory/joke, transition to an activity, or conclude the meetup). "

            f"STRICTLY FORBIDDEN: Do NOT turn this into a challenge, trial, or ultimatum!\n"

        )

    return (

        f"- ☕ SOCIAL HANGOUT MOMENTUM: Keep dialogue grounded in personal connection, authentic reactions, "

        f"and humor rather than analytical proposals.\n"

    )





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



    # 1. Ticking Clock & Scene Escalation Tracker

    history = session.get("history") or []



    tension_keywords = (

        "hammer", "hammering", "patrol", "patrols", "sentry", "sentries", "guard", "guards",

        "barricade", "barricaded", "breach", "breaching", "alarm", "alarms", "countdown",

        "seconds away", "moments before", "collapse", "collapsing", "timer", "intruder",

        "intruders", "ward-lines", "backlash", "locked in", "forced entry", "pounding",

        "shattered circle", "defender", "defenders", "assault", "assaulting", "siege",

        "standoff", "stand-off", "hostile", "ambush"

    )



    recent_tension_count = sum(1 for h in history[-6:] if any(kw in str(h).lower() for kw in tension_keywords))



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



def extract_speaking_npcs_from_narrative(narrative_text: str, npcs_present: list) -> list[str]:

    """

    Scans the narrative for speech quotes and action verbs to identify ALL NPCs who

    actively speak, converse, or directly participate in dialogue during the scene.

    """

    if not narrative_text or not npcs_present:

        return []



    nar_norm = game_engine._norm_dialogue_name(narrative_text)

    has_quotes = any(q in narrative_text for q in ('"', '“', '”', '‘', "'"))



    speech_verbs = {

        "speak", "speaks", "spoke", "speaking", "say", "says", "said", "saying",

        "ask", "asks", "asked", "asking", "reply", "replies", "replied", "replying",

        "whisper", "whispers", "whispered", "whispering", "answer", "answers", "answered", "answering",

        "inquire", "inquires", "inquired", "inquiring", "murmur", "murmurs", "murmured", "murmuring",

        "state", "states", "stated", "stating", "add", "adds", "added", "adding",

        "note", "notes", "noted", "noting", "argue", "argues", "argued", "arguing",

        "interject", "interjects", "interjected", "interjecting",

        "agree", "agrees", "agreed", "agreeing", "agreement",

        "nod", "nods", "nodded", "nodding", "propose", "proposes", "proposed", "proposing",

        "explain", "explains", "explained", "explaining", "demand", "demands", "demanded", "demanding",

        "counter", "counters", "countered", "countering", "declare", "declares", "declared", "declaring",

        "remark", "remarks", "remarked", "remarking", "sigh", "sighs", "sighed", "sighing",

        "chuckle", "chuckles", "chuckled", "chuckling", "scoff", "scoffs", "scoffed", "scoffing",

        "tell", "tells", "told", "telling", "suggest", "suggests", "suggested", "suggesting",

        "mutter", "mutters", "muttered", "muttering", "respond", "responds", "responded", "responding",

        "reassure", "reassures", "reassured", "reassuring", "insist", "insists", "insisted", "insisting",

        "continue", "continues", "continued", "continuing", "concur", "concurs", "concurred", "concurring",

        "question", "questions", "questioned", "questioning", "warn", "warns", "warned", "warning",

        "advise", "advises", "advised", "advising", "discuss", "discusses", "discussed", "discussing",

        "debate", "debates", "debated", "debating", "address", "addresses", "addressed", "addressing",

        "confront", "confronts", "confronted", "confronting", "challenge", "challenges", "challenged", "challenging",

        "call", "calls", "called", "calling", "greet", "greets", "greeted", "greeting",

        "shout", "shouts", "shouted", "shouting", "yell", "yells", "yelled", "yelling",

        "exclaim", "exclaims", "exclaimed", "exclaiming", "chime", "chimes", "chimed", "chiming",

        "tease", "teases", "teased", "teasing", "laugh", "laughs", "laughed", "laughing",

        "smirk", "smirks", "smirked", "smirking", "smile", "smiles", "smiled", "smiling",

        "snap", "snaps", "snapped", "snapping", "wave", "waves", "waved", "waving"

    }



    title_words = {

        "the", "elder", "lord", "lady", "sir", "madam", "captain", "dr", "mr", "ms", "mrs",

        "druid", "scholar", "guardian", "student", "council", "president", "vice", "secretary",

        "representative", "officer", "member", "guildmaster", "archivist", "warden", "guard",

        "patron", "shopkeeper", "innkeeper", "headmaster", "dean", "professor", "teacher"

    }



    nar_attrib_only = nar_norm

    if has_quotes:

        nar_attrib_only = re.sub(r'["“][^"”]*([.!?])["”]', r'\1', nar_norm)

        nar_attrib_only = re.sub(r'["“][^"”]*["”]', ' ', nar_attrib_only)

        nar_attrib_only = re.sub(r"['‘][^'’]*([.!?])['’]", r'\1', nar_attrib_only)

        nar_attrib_only = re.sub(r"['‘][^'’]*['’]", ' ', nar_attrib_only)



    speaking_npcs = []



    for npc in npcs_present:

        n_name = game_engine._get_npc_name(npc)

        if not n_name or n_name.lower() == "none":

            continue

        n_norm = game_engine._norm_dialogue_name(n_name)

        n_tokens = [t for t in n_norm.split() if len(t) > 2 and t not in title_words]

        if not n_tokens and len(n_norm) > 2:

            n_tokens = [n_norm]



        target_text = nar_attrib_only if has_quotes else nar_norm

        sentences = [s.strip() for s in re.split(r'[.!?\n]+', target_text) if s.strip()]



        is_speaking = False

        for s in sentences:

            if n_norm in s or any(t in s for t in n_tokens):

                s_words = set(re.findall(r"\b\w+\b", s))

                if s_words & speech_verbs:

                    is_speaking = True

                    break



        if is_speaking and n_name not in speaking_npcs:

            speaking_npcs.append(n_name)



    return speaking_npcs



def is_npc_invited_in_action(npc_name: str, actions: list) -> bool:

    """Checks if any player action explicitly invites or recruits an NPC to travel."""

    if not npc_name or not actions:

        return False

    n_low = npc_name.lower().strip()

    first_token = n_low.split()[0] if n_low else ""



    invitation_verbs = (

        "invite ", "ask ", "bring ", "take ", "tell ", "call ", "convince ",

        "recruit ", "hire ", "command ", "lead ", "request ", "guide ", "steer ", "usher ", "escort ", "thank "

    )

    follow_terms = ("join", "come with", "come along", "follow", "accompany", "with us", "travel with", "explore with", "together", "walk with", "head home with", "head with")



    for a in actions:

        label = (a.get("label") if isinstance(a, dict) else str(a)).lower()

        if n_low in label or (len(first_token) >= 3 and first_token in label):

            if any(iv in label for iv in invitation_verbs) or any(ft in label for ft in follow_terms):

                return True

    return False

