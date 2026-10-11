import game_engine
from .core import *

def create_contextual_story_quest_data(
    session_id: int,
    session: dict,
    chapter_num: int = 1,
    starting_hook_context: dict = None,
    previous_completed_title: str = None
) -> dict:
    """Deterministic, scenario-tailored Story Quest generator.
    Guarantees a rich Story Quest with exactly 3 distinct sub-quests and 3-stage
    progressive waypoints even if the LLM is completely unreachable or times out."""
    scen_key = session.get("scenario", "fantasy")
    loc = session.get("current_location") or "the central area"
    from mechanics.world.locations import get_discovered_primary_locations, is_school_scenario, sanitize_location_target, process_llm_location_update
    from mechanics.world.waypoints import ensure_multi_stage_waypoints

    zones_dict = get_discovered_primary_locations(session_id, scen_key)
    avail_locs_list = []
    for z, prims in zones_dict.items():
        for p in prims[:2]:
            avail_locs_list.append(f"{z} -> {p}")

    loc1 = avail_locs_list[0] if len(avail_locs_list) > 0 else loc
    loc2 = avail_locs_list[1] if len(avail_locs_list) > 1 else loc
    loc3 = avail_locs_list[2] if len(avail_locs_list) > 2 else loc

    if is_school_scenario(scen_key):
        from mechanics.social.school_roster import ensure_school_directory_exists
        roster = ensure_school_directory_exists(session)
        clean_loc = loc.split("➔")[-1].strip() or "the Academy"
        title = f"Chapter #{chapter_num}: Whispers at {clean_loc}"
        archetype = "Campus Investigation"
        objective = (
            f"Unsettling rumors and hidden rivalries are spreading through {loc}. "
            f"Investigate the initial disturbance, gather vital testimonies from students across campus facilities, "
            f"and uncover who is pulling the strings before the situation spirals out of control."
        )
        sub_objs = [
            {
                "id": 1,
                "archetype": "Investigation",
                "text": f"Search for physical evidence and inspect the disturbance site at {loc1}.",
                "completed": False
            },
            {
                "id": 2,
                "archetype": "Infiltration",
                "text": f"Infiltrate the restricted records or quiet corners of {loc2} to gather confidential intel.",
                "completed": False
            },
            {
                "id": 3,
                "archetype": "Diplomacy",
                "text": f"Interview key student leads and negotiate with club representatives at {loc3}.",
                "completed": False
            }
        ]
    elif starting_hook_context and chapter_num == 1:
        arch_title = starting_hook_context.get("archetype_title") or starting_hook_context.get("archetype", "hub_launchpad").replace("_", " ").title()
        title = f"Chapter #1: The {arch_title} Resolution"
        archetype = "Inciting Incident"
        objective = (
            f"The repercussions of the {arch_title.lower()} incident have begun to unfold across {loc}. "
            f"Investigate the physical trail left in the wake of the disturbance, secure the surrounding regional thresholds, "
            f"and confront the rising threat before it spreads further."
        )
        sub_objs = [
            {
                "id": 1,
                "archetype": "Investigation",
                "text": f"Investigate the primary site of the {arch_title.lower()} incident and collect key leads.",
                "completed": False
            },
            {
                "id": 2,
                "archetype": "Infiltration",
                "text": f"Scout the perimeter and bypass security barriers around {loc2}.",
                "completed": False
            },
            {
                "id": 3,
                "archetype": "Diplomacy",
                "text": f"Confront the regional instigator or coordinate countermeasures with allies at {loc3}.",
                "completed": False
            }
        ]
    elif "cyber" in scen_key.lower():
        title = f"Chapter #{chapter_num}: Encrypted Subnets"
        archetype = "Corporate Espionage"
        objective = (
            f"Hostile corporate factions have initiated surveillance across the district of {loc}. "
            f"Infiltrate protected networks, recover encrypted data chips, and establish counter-measures "
            f"before your squad is tracked down by automated enforcement units."
        )
        sub_objs = [
            {
                "id": 1,
                "archetype": "Investigation",
                "text": f"Hack into the local comms hub at {loc1} and decrypt illicit network chatter.",
                "completed": False
            },
            {
                "id": 2,
                "archetype": "Infiltration",
                "text": f"Bypass automated firewalls and stealthily breach the mainframe sector at {loc2}.",
                "completed": False
            },
            {
                "id": 3,
                "archetype": "Diplomacy",
                "text": f"Deliver extracted intelligence to black-market contacts or extract assets at {loc3}.",
                "completed": False
            }
        ]
    else:
        title = f"Chapter #{chapter_num}: Shadows Over {loc.split('➔')[-1].strip() or 'the Frontier'}"
        archetype = "Frontier Delve"
        objective = (
            f"Dark forces and unexplained anomalies threaten the stability of {loc}. "
            f"Explore uncharted reaches, collect critical relics of power, and coordinate with regional guardians "
            f"to neutralize the gathering peril."
        )
        sub_objs = [
            {
                "id": 1,
                "archetype": "Investigation",
                "text": f"Examine the anomaly and recover physical evidence from the threshold of {loc1}.",
                "completed": False
            },
            {
                "id": 2,
                "archetype": "Infiltration",
                "text": f"Delve into hazardous ruins and bypass mystical barriers at {loc2}.",
                "completed": False
            },
            {
                "id": 3,
                "archetype": "Diplomacy",
                "text": f"Negotiate with faction scouts or confront the regional champion at {loc3}.",
                "completed": False
            }
        ]

    sub_waypoints = {}
    for idx, so in enumerate(sub_objs, 1):
        arch = so.get("archetype", "Investigation")
        sub_waypoints[idx] = ensure_multi_stage_waypoints([], default_loc=loc, archetype=arch)

    sub_waypoints = game_engine._distribute_fallback_locations(session_id, scen_key, sub_waypoints, sub_objs)

    for so_id, wps in sub_waypoints.items():
        for wp in wps:
            t_loc = wp.get("target_location", "").strip()
            if t_loc:
                clean_t = sanitize_location_target(t_loc, session_id=session_id, scen_key=scen_key)
                process_llm_location_update(session_id, clean_t, scen_key)

    return {
        "title": title,
        "archetype": archetype,
        "objective": objective,
        "sub_objectives": sub_objs,
        "sub_waypoints": sub_waypoints,
    }

def ensure_story_quest_exists(session: dict) -> dict | None:
    """Returns the active Story Quest if one exists with valid objectives.
    If an existing Story Quest is a generic placeholder with 0 sub-objectives,
    or if no Story Quest exists at all, heals/creates it using the contextual
    generator to guarantee 3 progressive sub-quests and waypoints are always present."""
    session_id = session["id"]
    cur_ch = db.get_session_chapter(session_id) or 1
    sq = db.get_active_story_quest(session_id)
    if sq:
        sub_objs = sq.get("sub_objectives") or []
        is_generic = (
            sq.get("title") == "Story Quest #1: A New Adventure Begins" or
            sq.get("objective") == "Explore the area and uncover what dangers or mysteries await." or
            len(sub_objs) == 0
        )
        if not is_generic and len(sub_objs) >= 1:
            return sq
        # Self-healing path: existing quest is missing objectives
        sq_id = sq["quest_id"]
    else:
        import uuid
        sq_id = f"SQ-{uuid.uuid4().hex[:8].upper()}"

    data = create_contextual_story_quest_data(session_id, session, chapter_num=cur_ch)
    sub_objs = data.get("sub_objectives") or []
    sub_waypoints = data.get("sub_waypoints") or {}

    healed_quest = db.upsert_quest(
        session_id=session_id,
        quest_id=sq_id,
        quest_type=data.get("archetype") or "Story Quest",
        title=data.get("title") or f"Chapter #{cur_ch} Objective",
        objective=data.get("objective") or "Explore the area and resolve regional mysteries.",
        progress=f"0/{len(sub_objs)} Cleared" if sub_objs else f"Quest #{cur_ch}",
        current_clues="",
        status="Active",
        reward_xp=250 + (cur_ch * 30),
        reward_gold=60 + (cur_ch * 10),
        is_story_quest=1,
        clues_required=len(sub_objs),
        sub_objectives=sub_objs
    )

    for so in sub_objs:
        so_id = so.get("id")
        wps = sub_waypoints.get(so_id) or []
        if wps:
            db.save_quest_waypoints(session_id=session_id, quest_id=sq_id, waypoints=wps, sub_obj_id=so_id)

    return healed_quest

async def generate_story_quest(session_id: int, session: dict, chapter_num: int, previous_completed_title: str = None, starting_hook_context: dict = None) -> dict:
    """Dedicated LLM generator for Story Quests (Chapter 1, 2, 3...).
    Generates a unique story quest with 3 distinct regional destination locations and 3-stage progressive waypoints."""
    scen_block = game_engine._scenario_block(session)
    loc = session.get("current_location", "the current area")
    goals = db.get_session_campaign_goals(session_id)
    goals_summary = "\n".join(
        f"- [{g['id']}] {g['title']} ({g.get('progress_pct', 0)}%): {g.get('description', '')}"
        for g in goals
    ) if goals else "No campaign goals defined."

    scen_key = session.get("scenario", "fantasy")
    from mechanics.world.locations import get_discovered_primary_locations, process_llm_location_update
    zones_dict = get_discovered_primary_locations(session_id, scen_key)
    avail_locs_list = []
    for z, prims in zones_dict.items():
        for p in prims[:2]:
            avail_locs_list.append(f"{z} -> {p}")
    avail_locs_text = ", ".join(avail_locs_list[:12]) if avail_locs_list else loc

    pacing_note = f"CAMPAIGN PACING: This is Chapter #{chapter_num} of {MAX_CAMPAIGN_CHAPTERS}.\n"
    if chapter_num >= MAX_CAMPAIGN_CHAPTERS:
        pacing_note += (
            "🏆 [GRAND FINALE CHAPTER]: This is the climactic 10th and final chapter of the campaign!\n"
            "The overarching objective and sub-quests MUST stage the ultimate culmination of the campaign, resolving the core mysteries and Campaign End Goals.\n"
        )
    elif chapter_num == (MAX_CAMPAIGN_CHAPTERS // 2):
        pacing_note += (
            "⚡ [MID-CAMPAIGN CLIMAX (Chapter 5/10)]: This is the halfway turning point of the campaign!\n"
            "Introduce major narrative escalations, shocking revelations, or rising stakes that propel the story into its darker or more intense second half.\n"
        )
    elif chapter_num == (MAX_CAMPAIGN_CHAPTERS - 1):
        pacing_note += (
            "⚔️ [PENULTIMATE CHAPTER (Chapter 9/10)]: The calm before the storm!\n"
            "The sub-quests should assemble the final keys, allies, preparations, and revelations needed for the upcoming grand finale in Chapter 10.\n"
        )

    system_prompt = (
        f"You are a Game Master creating a Story Quest for Chapter #{chapter_num} of a text RPG.\n"
        f"{pacing_note}"
        f"Generate a completely UNIQUE, EVOCATIVE Story Quest tied directly to the scenario lore.\n"
        f"CRITICAL REQUIREMENTS:\n"
        f"1. You MUST output EXACTLY 3 distinct, independent sub-quests in the `sub_quests` JSON array (id: 1, id: 2, id: 3).\n"
        f"2. The 3 sub-quests MUST target DIFFERENT locations across the region (e.g. {avail_locs_text}).\n"
        f"3. Each sub-quest MUST include EXACTLY 3 progressive waypoints:\n"
        f"   - Stage 1: Arrival / Travel to the lead or site threshold (`completion_trigger: 'arrival'`).\n"
        f"   - Stage 2: Investigation, bypassing barriers, or harvesting/infiltrating (`completion_trigger: 'skill_check'`).\n"
        f"   - Stage 3: Resolving, securing evidence/relic, or confronting/delivering (`completion_trigger: 'skill_check'`).\n"
        f"   - Sub-quests MAY span across multiple distinct locations across their 3 stages (e.g. Stage 1 @ Location A -> Stage 2 @ Location B -> Stage 3 @ Location C).\n"
        f"4. Respond with ONLY a single valid JSON object matching the schema exactly, no prose or code fences.\n"
        f"Schema:\n{NEXT_STORY_QUEST_SCHEMA}"
    )

    if previous_completed_title:
        context_line = f"Story Quest #{chapter_num - 1} just completed: '{previous_completed_title}'\n"
    elif starting_hook_context:
        arch_title = starting_hook_context.get("archetype_title") or starting_hook_context.get("archetype", "hub_launchpad").replace("_", " ").title()
        hook_text = starting_hook_context.get("hook_text", "")
        op_nar = starting_hook_context.get("opening_narrative", "")
        sc_title = starting_hook_context.get("scene_title", "")
        context_line = (
            f"This is Chapter #1: The opening chapter of the campaign.\n"
            f"OPENING INCITING INCIDENT [{arch_title}]: {hook_text}\n"
            + (f"OPENING SCENE TITLE: {sc_title}\n" if sc_title else "")
            + (f"OPENING NARRATIVE CONTEXT: {op_nar}\n" if op_nar else "")
            + f"DIRECTIVE FOR CHAPTER 1 QUEST: The Quest Title, primary overarching objective, and Sub-Quest #1 MUST be directly rooted in and continue from this opening {arch_title} incident. Sub-Quests #2 and #3 should expand into the broader regional mystery across other discovered locations.\n"
        )
    else:
        context_line = "This is Chapter #1: The opening chapter of the campaign.\n"

    school_context = ""
    from mechanics.world.locations import is_school_scenario
    if is_school_scenario(scen_key):
        from mechanics.social.school_roster import ensure_school_directory_exists
        roster = ensure_school_directory_exists(session)
        if roster:
            seniors = [c for c in roster if c.get("grade") == "Senior"]
            juniors = [c for c in roster if c.get("grade") == "Junior"]
            under = [c for c in roster if c.get("grade") in ("Sophomore", "Freshman")]
            faculty = [c for c in roster if c.get("grade") == "Faculty"]

            sample = []
            if seniors: sample.append(seniors[(session_id + chapter_num) % len(seniors)])
            if juniors: sample.append(juniors[(session_id + chapter_num + 1) % len(juniors)])
            if under: sample.append(under[(session_id + chapter_num + 2) % len(under)])
            if faculty: sample.append(faculty[(session_id + chapter_num + 3) % len(faculty)])

            leads = [
                f"- {c['name']} [{c.get('grade')}] ({c.get('role')} | Club: {c.get('club')}) @ {c.get('primary_facility')}"
                for c in sample
            ]
            school_context = (
                "CAMPUS DIRECTORY LEADS & GRADE DYNAMICS:\n"
                "Incorporate school facilities and the following students/faculty into the chapter sub-quests:\n"
                + "\n".join(leads) + "\n\n"
            )

    user_prompt = (
        f"{scen_block}\n"
        f"Current Starting Location: {loc}\n"
        f"{context_line}"
        f"{school_context}"
        f"Long-Term Campaign End Goals:\n{goals_summary}\n\n"
        f"Available Regional Locations for Sub-Quests:\n{avail_locs_text}\n\n"
        f"Generate Story Quest #{chapter_num} with: a rich multi-sentence main objective and EXACTLY 3 specific, independent sub-quests "
        f"spanning across DIFFERENT locations from the regional list that players can pursue in any order."
    )

    result = None
    # PASS 1: Rich Contextual Generation
    try:
        result = await game_engine.call_llm_json(
            system_prompt, user_prompt, temperature=0.9,
            max_tokens=4096, retries=2, is_nsfw=scenario_data.uses_nsfw_model(session.get("scenario")), use_utility=True
        )
    except Exception as e:
        import logging
        logging.getLogger(__name__).warning("generate_story_quest Pass 1 failed for Session %s: %s. Initiating Emergency Pass 2.", session_id, e)

    # PASS 2: Emergency Pass (Streamlined, low-latency prompt with standard model)
    if not result or not isinstance(result, dict) or not (result.get("sub_quests") or result.get("sub_objectives")):
        try:
            emergency_system = (
                f"You are a Game Master creating a Story Quest for Chapter #{chapter_num} of a text RPG.\n"
                f"CRITICAL REQUIREMENT: Output a single valid JSON object ONLY matching this schema:\n"
                f"{NEXT_STORY_QUEST_SCHEMA}"
            )
            emergency_user = (
                f"Scenario: {scen_key}. Location: {loc}.\n"
                f"{context_line}\n"
                f"Available Regional Locations:\n{avail_locs_text}\n\n"
                f"Generate Story Quest #{chapter_num} with a creative title, 2-sentence objective, and EXACTLY 3 distinct sub_quests across regional locations."
            )
            result = await game_engine.call_llm_json(
                emergency_system, emergency_user, temperature=0.7,
                max_tokens=2048, retries=1, is_nsfw=scenario_data.uses_nsfw_model(session.get("scenario")), use_utility=False
            )
        except Exception as e2:
            import logging
            logging.getLogger(__name__).warning("generate_story_quest Emergency Pass 2 failed for Session %s: %s. Using deterministic fallback.", session_id, e2)
            result = None

    # PASS 3: Deterministic Contextual Generator (Guarantees zero blank quests even offline)
    if not result or not isinstance(result, dict):
        return create_contextual_story_quest_data(
            session_id=session_id,
            session=session,
            chapter_num=chapter_num,
            starting_hook_context=starting_hook_context,
            previous_completed_title=previous_completed_title
        )

    raw_sub = result.get("sub_quests") or result.get("sub_objectives") or []
    sub_objs = []
    sub_waypoints = {}
    from mechanics.world.waypoints import ensure_multi_stage_waypoints
    if isinstance(raw_sub, list):
        for idx, item in enumerate(raw_sub, 1):
            if isinstance(item, str) and item.strip():
                sub_objs.append({"id": idx, "archetype": "Investigation", "text": item.strip(), "completed": False})
                sub_waypoints[idx] = ensure_multi_stage_waypoints([], default_loc=loc, archetype="Investigation")
            elif isinstance(item, dict):
                so_id = item.get("id", idx)
                arch = item.get("archetype", "Objective")
                text_val = (item.get("text") or item.get("objective") or "").strip()
                if text_val:
                    sub_objs.append({
                        "id": so_id,
                        "archetype": arch,
                        "text": text_val,
                        "completed": False
                    })
                    wp_list = item.get("waypoints") or []
                    sub_waypoints[so_id] = ensure_multi_stage_waypoints(wp_list, default_loc=loc, archetype=arch)

    # STRICT PYTHON GUARDRAIL: Guarantee EXACTLY 3 Sub-Objectives
    if len(sub_objs) < 3:
        existing_texts = [so["text"].lower() for so in sub_objs]
        obj_text = (result.get("objective") or "").strip()
        import re
        clauses = [c.strip() for c in re.split(r'[;.]|,\s*(?:and|then|to)\s*', obj_text) if len(c.strip()) > 15]
        for clause in clauses:
            if len(sub_objs) >= 3:
                break
            if not any(clause.lower() in et or et in clause.lower() for et in existing_texts):
                next_id = len(sub_objs) + 1
                arch = "Infiltration" if next_id == 2 else "Diplomacy"
                sub_objs.append({
                    "id": next_id,
                    "archetype": arch,
                    "text": clause,
                    "completed": False
                })
                sub_waypoints[next_id] = ensure_multi_stage_waypoints([], default_loc=loc, archetype=arch)
                existing_texts.append(clause.lower())

        archetype_fallbacks = [
            ("Investigation", "Investigate the primary disturbance and collect critical clues"),
            ("Infiltration", "Infiltrate the restricted sector and gather vital intelligence"),
            ("Diplomacy", "Form an alliance or confront the regional instigator")
        ]
        while len(sub_objs) < 3:
            next_id = len(sub_objs) + 1
            arch, default_text = archetype_fallbacks[next_id - 1]
            sub_objs.append({
                "id": next_id,
                "archetype": arch,
                "text": default_text,
                "completed": False
            })
            sub_waypoints[next_id] = ensure_multi_stage_waypoints([], default_loc=loc, archetype=arch)

    # Normalize IDs to 1, 2, 3
    for idx, so in enumerate(sub_objs[:3], 1):
        old_id = so["id"]
        so["id"] = idx
        if old_id != idx and old_id in sub_waypoints:
            sub_waypoints[idx] = sub_waypoints.pop(old_id)
    sub_objs = sub_objs[:3]

    # Distribute fallback locations so each sub-quest targets a DISTINCT location
    sub_waypoints = game_engine._distribute_fallback_locations(session_id, scen_key, sub_waypoints, sub_objs)

    # Auto-discover target locations in SQLite
    from mechanics.world.locations import sanitize_location_target
    for so_id, wps in sub_waypoints.items():
        for wp in wps:
            t_loc = wp.get("target_location", "").strip()
            if t_loc:
                clean_t = sanitize_location_target(t_loc, session_id=session_id, scen_key=scen_key)
                process_llm_location_update(session_id, clean_t, scen_key)

    return {
        "title": (result.get("title") or f"Chapter #{chapter_num} Objective").strip(),
        "archetype": (result.get("archetype") or "Story Quest").strip(),
        "objective": (result.get("objective") or "Complete chapter objectives.").strip(),
        "sub_objectives": sub_objs,
        "sub_waypoints": sub_waypoints,
    }

async def generate_next_story_quest(session_id: int, session: dict, completed_quest_update: dict) -> dict:
    """Wrapper calling the unified generate_story_quest for next chapters."""
    completed_title = completed_quest_update.get("title", "the previous story quest") if isinstance(completed_quest_update, dict) else "the previous story quest"
    cur_ch = db.get_session_chapter(session_id)
    return await game_engine.generate_story_quest(session_id, session, chapter_num=cur_ch + 1, previous_completed_title=completed_title)

def _is_valid_investigation_note(clue: str) -> bool:
    """Validates that an investigation note is a meaningful story clue string."""
    if not clue or not isinstance(clue, str):
        return False
    s = clue.strip()
    return 10 <= len(s) <= 250 and len(s.split()) <= 40

def _is_similar_clue(new_clue: str, existing_clues: list[str]) -> bool:
    import re
    if not new_clue or not new_clue.strip():
        return True
    new_clean = new_clue.strip().lower()
    for ex in existing_clues:
        ex_clean = ex.strip().lower()
        if new_clean == ex_clean:
            return True
        t_new = set(re.findall(r'\b[a-z]{3,}\b', new_clean))
        t_ex = set(re.findall(r'\b[a-z]{3,}\b', ex_clean))
        if t_new and t_ex:
            intersection = t_new.intersection(t_ex)
            union = t_new.union(t_ex)
            if union and (len(intersection) / float(len(union))) >= 0.45:
                return True
    return False

def apply_quest_update(session_id: int, quest_update: dict, party_user_ids: list[int] = None, outcome: dict = None, actions: list[dict] = None) -> dict | None:
    """Process a single quest update dict OR an outcome/scene dict containing quest_updates / _quest_update.
    Returns a reward notice dict if a quest was completed, otherwise None.
    """
    if not quest_update or not isinstance(quest_update, dict):
        return None

    # Handle outer outcome/scene dict containing quest_updates array
    if "quest_updates" in quest_update and isinstance(quest_update["quest_updates"], list):
        notices = []
        for qu in quest_update["quest_updates"]:
            if isinstance(qu, dict):
                n = game_engine.apply_quest_update(session_id, qu, party_user_ids=party_user_ids, outcome=outcome or quest_update, actions=actions)
                if n and n.get("claimed"):
                    notices.append(n)
        return notices[0] if notices else None

    title = quest_update.get("title")
    quest_type = quest_update.get("quest_type") or "Main Quest"
    objective = quest_update.get("objective")
    progress = quest_update.get("progress") or ""
    current_clues = quest_update.get("current_clues") or ""
    status = quest_update.get("status") or "Active"
    try:
        reward_xp = int(quest_update.get("reward_xp") if quest_update.get("reward_xp") is not None else 120)
    except (ValueError, TypeError):
        reward_xp = 120
    try:
        reward_gold = int(quest_update.get("reward_gold") if quest_update.get("reward_gold") is not None else 35)
    except (ValueError, TypeError):
        reward_gold = 35
    reward_item = str(quest_update.get("reward_item", "") or "")[:60]

    session = db.get_session(session_id)
    quest_id = quest_update.get("quest_id")

    # Try matching by quest_id first (most reliable), then by title
    matched_quest = None
    if quest_id:
        matched_quest = db.get_quest_by_id(session_id, quest_id)
        # If the quest_id didn't match (e.g. LLM invented an ID), fall through to title match
        if matched_quest and matched_quest.get("status") not in ("Active", "Available"):
            matched_quest = None  # Don't update already-completed quests

    if not matched_quest and title:
        active_quests = db.get_session_quests(session_id, status="Active")
        for q in active_quests:
            if q["title"].lower() == title.lower():
                matched_quest = q
                break

    if matched_quest:
        quest_id = matched_quest["quest_id"]
        if not title:
            title = matched_quest.get("title")
        if not objective:
            objective = matched_quest.get("objective")
        if not quest_type or quest_type == "Main Quest":
            quest_type = matched_quest.get("quest_type") or "Main Quest"
    elif not quest_id:
        import uuid
        prefix = "BNT" if "bounty" in str(quest_type).lower() else "QST"
        quest_id = f"{prefix}-{uuid.uuid4().hex[:8].upper()}"

    quest_notes = quest_update.get("quest_notes") or (session.get("quest_notes") if session else None)
    if quest_notes:
        quest_notes = game_engine.format_concise_bullets(quest_notes, max_bullets=5)

    is_sq = 1 if (str(quest_type).lower() in ("story quest", "main quest") or "chapter" in str(title or "").lower()) else 0
    if matched_quest and matched_quest.get("is_story_quest"):
        is_sq = 1

    # If this looks like a Story Quest update but has no specific title, update the active story quest instead
    if is_sq and not matched_quest:
        active_sq = db.get_active_story_quest(session_id)
        if active_sq:
            matched_quest = active_sq
            quest_id = active_sq["quest_id"]
            if not title or title in ("Active Objective", "Complete objective.", ""):
                title = active_sq["title"]
            if not objective or objective in ("Complete objective.", ""):
                objective = active_sq["objective"]

    # Update Goal Progress % with deterministic chapter floor and ceiling clamp
    cur_ch = db.get_session_chapter(session_id) or 1
    chapter_floor = min(100, int(((cur_ch - 1) / MAX_CAMPAIGN_CHAPTERS) * 100))
    chapter_ceiling = min(100, int((cur_ch / MAX_CAMPAIGN_CHAPTERS) * 100))
    goal_updates = quest_update.get("goal_progress_updates")
    goals = db.get_session_campaign_goals(session_id)
    if goals:
        dirty_goals = False
        for g in goals:
            gid = g.get("id")
            # Always ensure goal is at least at chapter floor
            if g.get("progress_pct", 0) < chapter_floor:
                g["progress_pct"] = chapter_floor
                dirty_goals = True
            if goal_updates and isinstance(goal_updates, dict) and gid in goal_updates:
                try:
                    val = int(goal_updates[gid])
                    # Clamp between chapter floor and ceiling (unless final chapter)
                    max_allowed = 100 if cur_ch >= MAX_CAMPAIGN_CHAPTERS else chapter_ceiling
                    clamped_val = max(chapter_floor, min(max_allowed, val))
                    if clamped_val != g.get("progress_pct", 0):
                        g["progress_pct"] = clamped_val
                        dirty_goals = True
                    if g["progress_pct"] >= 100:
                        g["status"] = "Completed"
                except Exception:
                    pass
        if dirty_goals:
            db.update_session_campaign_goals(session_id, goals)

    # Abort if still no real title — don't create garbage placeholder rows
    if not title or title in ("Active Objective", "Complete objective.", ""):
        return None

    # Preserve existing reward values for Story Quests and bounties (prevent turn LLMs from downgrading rewards)
    if matched_quest:
        if is_sq and matched_quest.get("reward_xp", 0) > 0:
            reward_xp = matched_quest["reward_xp"]
            reward_gold = matched_quest.get("reward_gold", reward_gold)
        else:
            if reward_xp <= 35 and matched_quest.get("reward_xp", 0) > 35:
                reward_xp = matched_quest["reward_xp"]
            if reward_gold <= 10 and matched_quest.get("reward_gold", 0) > 10:
                reward_gold = matched_quest["reward_gold"]
        if not reward_item and matched_quest.get("reward_item"):
            reward_item = matched_quest["reward_item"]

    # Merge existing clues with newly received clues. Cap new clues at 1 per turn. Keep up to 20 unique notes total.
    # DISABLE clues entirely during active combat sequence!
    session_enemies = game_engine.get_active_enemies(session)
    outcome_enemies = game_engine.get_active_enemies(outcome)
    is_combat = bool(session_enemies or outcome_enemies or (outcome and (outcome.get("_combat_log") or outcome.get("_enemy_attack_notice"))))

    existing_clues = game_engine.parse_clue_list(matched_quest.get("current_clues")) if matched_quest else []
    incoming_clues = [] if is_combat else game_engine.parse_clue_list(current_clues)
    merged_clues = list(existing_clues)
    new_added = 0
    newly_discovered_clue = None
    if not is_combat:
        for c in incoming_clues:
            if c and game_engine._is_valid_investigation_note(c) and not game_engine._is_similar_clue(c, merged_clues):
                merged_clues.append(c)
                new_added += 1
                if new_added >= 1:
                    newly_discovered_clue = c
                    try:
                        from mechanics.narrative.clues import categorize_clue
                        cur_loc = session.get("current_location", "") if session else ""
                        db.add_session_clue(
                            session_id=session_id,
                            title=c[:60],
                            lead_text=c,
                            category=categorize_clue(c),
                            source_location=cur_loc,
                            quest_id=quest_id or "",
                            chapter=cur_ch
                        )
                    except Exception:
                        pass
                    break
    if merged_clues:
        current_clues = "\n".join(f"• {c}" for c in merged_clues[:20])
    else:
        current_clues = ""

    # Sub-quest checkmarks logic: preserve completed status and merge updates
    existing_sub_objs = matched_quest.get("sub_objectives", []) if matched_quest else []
    already_completed_ids = set()
    already_completed_texts = set()
    for so in existing_sub_objs:
        if isinstance(so, dict) and so.get("completed"):
            already_completed_ids.add(str(so.get("id", "")))
            if so.get("text"): already_completed_texts.add(so.get("text", "").strip().lower())
            if so.get("archetype"): already_completed_texts.add(so.get("archetype", "").strip().lower())

    sub_objs = [dict(so) for so in existing_sub_objs if isinstance(so, dict)] if existing_sub_objs else []

    new_sub_objs = quest_update.get("sub_quests") or quest_update.get("sub_objectives")
    if new_sub_objs and isinstance(new_sub_objs, list):
        if not sub_objs:
            for idx, item in enumerate(new_sub_objs, 1):
                if isinstance(item, str):
                    sub_objs.append({"id": idx, "archetype": "Objective", "text": item.strip(), "completed": False})
                elif isinstance(item, dict):
                    sub_objs.append({
                        "id": item.get("id", idx),
                        "archetype": item.get("archetype", "Objective"),
                        "text": (item.get("text") or item.get("objective") or "").strip(),
                        "completed": bool(item.get("completed"))
                    })
        else:
            for idx, item in enumerate(new_sub_objs, 1):
                if idx <= len(sub_objs):
                    if isinstance(item, dict):
                        if item.get("text"): sub_objs[idx-1]["text"] = item["text"].strip()
                        if item.get("archetype"): sub_objs[idx-1]["archetype"] = item["archetype"].strip()
                        if item.get("completed"): sub_objs[idx-1]["completed"] = True
                else:
                    if isinstance(item, dict):
                        sub_objs.append({
                            "id": item.get("id", idx),
                            "archetype": item.get("archetype", "Objective"),
                            "text": (item.get("text") or item.get("objective") or "").strip(),
                            "completed": bool(item.get("completed"))
                        })

    # Restore completed status for any sub-objective that was ALREADY completed in DB
    for so in sub_objs:
        so_id_str = str(so.get("id", ""))
        so_text_lower = (so.get("text") or "").strip().lower()
        so_arch_lower = (so.get("archetype") or "").strip().lower()
        if so_id_str in already_completed_ids or so_text_lower in already_completed_texts or so_arch_lower in already_completed_texts:
            so["completed"] = True

    # Process explicit completion IDs sent by LLM in JSON
    completed_ids = quest_update.get("completed_sub_quest_ids") or quest_update.get("completed_sub_objective_ids") or []
    newly_completed = []
    if completed_ids and isinstance(completed_ids, list):
        active_enemies = (game_engine.get_active_enemies(outcome) or game_engine.get_active_enemies(session)) if outcome else []
        has_active_hostiles = bool(active_enemies and not outcome.get("_combat_resolved"))
        turn_count = len(session.get("history", [])) if session else 0

        for so in sub_objs:
            so_id_str = str(so.get("id", ""))
            so_text_lower = (so.get("text") or "").lower()
            so_arch_lower = (so.get("archetype") or "").lower()
            for cid in completed_ids:
                cid_str = str(cid).strip().lower()
                if cid_str == so_id_str or (cid_str and (cid_str in so_text_lower or cid_str in so_arch_lower or so_arch_lower in cid_str)):
                    # GUARDRAIL 1: Combat / delve / recovery sub-quests cannot complete while hostile enemies are active
                    requires_combat_or_delve = any(kw in so_text_lower for kw in ("survive", "defeat", "slay", "kill", "recover", "retrieve", "escape", "delve", "combat", "fight", "confront", "infiltrate"))
                    if has_active_hostiles and requires_combat_or_delve:
                        continue
                    # GUARDRAIL 2: Multi-step delve/recovery sub-quests cannot complete on Turn 1 / opening scene
                    if turn_count <= 1 and any(kw in so_text_lower for kw in ("survive", "recover the", "retrieve the", "slay the", "defeat the", "delve through")):
                        continue
                    # GUARDRAIL 3: WAYPOINT PROGRESSION GUARDRAIL: If this sub-objective has active/pending waypoint stages in DB, it CANNOT complete until all stages are finished
                    if quest_id and so.get("id") is not None:
                        active_wp = db.get_active_waypoint(session_id, quest_id, so["id"])
                        if active_wp is not None:
                            continue

                    if not so.get("completed"):
                        so["completed"] = True
                        newly_completed.append(so)
                    break

    # Deterministic Clue Grounding: If an investigation/clue sub-objective completed, append a structured clue note
    for nco in newly_completed:
        n_text = (nco.get("text") or "").strip()
        if any(k in n_text.lower() for k in ("investigate", "discover", "uncover", "search", "interview", "interrogate", "examine", "clue", "evidence", "find")):
            clue_cand = f"Discovered lead: {n_text}"
            if not game_engine._is_similar_clue(clue_cand, merged_clues):
                merged_clues.append(clue_cand)
                if not newly_discovered_clue:
                    newly_discovered_clue = clue_cand
                try:
                    from mechanics.narrative.clues import categorize_clue
                    cur_loc = session.get("current_location", "") if session else ""
                    db.add_session_clue(
                        session_id=session_id,
                        title=n_text[:60],
                        lead_text=n_text,
                        category=categorize_clue(n_text),
                        source_location=cur_loc,
                        linked_npc=str(nco.get("target_npc") or ""),
                        quest_id=quest_id or "",
                        chapter=cur_ch
                    )
                except Exception:
                    pass

    if merged_clues:
        current_clues = "\n".join(f"• {c}" for c in merged_clues[:20])

    # Two-Phase Climax State Machine:
    # 1. Story Quest CANNOT complete if any sub-objectives are pending.
    # 2. Phase 1 (Sub-Objective 3/3 Done on Turn N): Quest MUST stay 'Active' so the LLM stages the Climax Encounter!
    # 3. Phase 2 (Climax Overcome on Turn N+1): Only when all sub-objectives were ALREADY complete before this turn started
    #    AND the player successfully overcomes the Climax Encounter (LLM returns status='Completed') does it mark Completed.
    if is_sq and sub_objs:
        all_done = all(so.get("completed") for so in sub_objs)
        existing_all_done = bool(existing_sub_objs and len(existing_sub_objs) == len(sub_objs) and all(so.get("completed") for so in existing_sub_objs if isinstance(so, dict)))
        
        if not all_done:
            status = "Active"
        elif all_done:
            if not existing_all_done:
                # Phase 1: 3/3 sub-objectives just completed this turn!
                # Force status to Active so the Climax Encounter / Boss is fought and resolved.
                status = "Active"
            else:
                # Phase 2: All sub-objectives were already complete when the turn started.
                # If the player overcame the climax (successful climax check) or LLM requested completion, mark Completed!
                llm_requested_complete = (str(quest_update.get("status", "")).lower() == "completed")
                from mechanics.social.intimate_excitement import is_intimate_action_label as _q_is_intimate_lbl
                action_is_climax = any(
                    not _q_is_intimate_lbl(str(a.get("label", ""))) and (
                        bool(a.get("is_climax_action")) or
                        str(a.get("contract_type", "")).lower() == "climax" or
                        "[story climax]" in str(a.get("label", "")).lower() or
                        "⚡" in str(a.get("label", "")) or
                        "climax" in str(a.get("label", "")).lower()
                    )
                    for a in (actions or [])
                )
                action_succeeded = any(
                    (hasattr(a.get("check"), "succeeded") and a["check"].succeeded) or
                    (isinstance(a.get("check"), dict) and a["check"].get("succeeded")) or
                    (a.get("stat") in ("NONE", "FREE") or a.get("requirement", 0) <= 0)
                    for a in (actions or [])
                )
                if action_is_climax and action_succeeded:
                    status = "Completed"
                else:
                    status = "Completed" if llm_requested_complete else "Active"
    elif not is_sq:
        raw_status = str(quest_update.get("status", "")).strip().lower()
        if raw_status == "completed":
            status = "Completed"
        elif raw_status == "failed":
            status = "Failed"
        elif matched_quest and matched_quest.get("status") in ("Completed", "Failed"):
            status = matched_quest["status"]
        else:
            status = "Active"
    
    clues_req = len(sub_objs) if sub_objs else 3

    if is_sq and sub_objs:
        done_count = sum(1 for so in sub_objs if isinstance(so, dict) and so.get("completed"))
        total_count = len(sub_objs)
        progress = f"{done_count}/{total_count} Cleared"

    db.upsert_quest(
        session_id=session_id,
        quest_id=quest_id,
        quest_type=quest_type,
        title=title,
        objective=objective or "Complete objective.",
        progress=progress,
        current_clues=current_clues,
        status=status,
        reward_xp=reward_xp,
        reward_gold=reward_gold,
        reward_stat_points=0,
        reward_item=reward_item,
        is_story_quest=is_sq,
        clues_required=clues_req,
        quest_notes=quest_notes,
        sub_objectives=sub_objs
    )

    # Sync quest_waypoints status
    with db.get_conn() as conn:
        if sub_objs:
            for so in sub_objs:
                if isinstance(so, dict) and so.get("completed"):
                    so_id = so.get("id")
                    if so_id is not None:
                        conn.execute(
                            "UPDATE quest_waypoints SET status='completed', updated_at=? WHERE session_id=? AND quest_id=? AND sub_obj_id=?",
                            (time.time(), session_id, quest_id, so_id)
                        )
        if status == "Completed":
            conn.execute(
                "UPDATE quest_waypoints SET status='completed', updated_at=? WHERE session_id=? AND quest_id=?",
                (time.time(), session_id, quest_id)
            )
        elif status == "Failed":
            conn.execute(
                "UPDATE quest_waypoints SET status='failed', updated_at=? WHERE session_id=? AND quest_id=?",
                (time.time(), session_id, quest_id)
            )

    if status == "Completed" and party_user_ids:
        notice = db.claim_quest_reward(session_id, quest_id, party_user_ids)
        if notice and notice.get("claimed") and (notice.get("is_story_quest") or is_sq):
            cur_ch = db.get_session_chapter(session_id)
            next_ch = cur_ch + 1
            db.set_session_chapter(session_id, next_ch)

            # Deterministic Campaign Goal Advance on Chapter Completion
            goals = db.get_session_campaign_goals(session_id)
            if goals:
                new_floor = min(100, int((cur_ch / MAX_CAMPAIGN_CHAPTERS) * 100))
                for g in goals:
                    g["progress_pct"] = max(g.get("progress_pct", 0), new_floor)
                    if cur_ch >= MAX_CAMPAIGN_CHAPTERS or g["progress_pct"] >= 100:
                        g["progress_pct"] = 100
                        g["status"] = "Completed"
                db.update_session_campaign_goals(session_id, goals)

            # Write a contextual quest immediately so the DB is NEVER blank or generic,
            # then schedule the LLM call to replace it with a fully unique quest.
            session_obj = db.get_session(session_id)
            import uuid, asyncio
            next_sq_id = f"SQ-{uuid.uuid4().hex[:8].upper()}"
            fallback_data = create_contextual_story_quest_data(session_id, session_obj, chapter_num=next_ch)
            next_init_subs = fallback_data.get("sub_objectives") or []
            next_init_wps = fallback_data.get("sub_waypoints") or {}
            db.upsert_quest(
                session_id=session_id,
                quest_id=next_sq_id,
                quest_type=fallback_data.get("archetype") or "Story Quest",
                title=fallback_data.get("title") or f"Story Quest #{next_ch}",
                objective=fallback_data.get("objective") or "A new chapter is about to unfold...",
                progress=f"0/{len(next_init_subs)} Cleared" if next_init_subs else f"Quest #{next_ch}",
                current_clues="",
                status="Active",
                reward_xp=250 + (next_ch * 30),
                reward_gold=60 + (next_ch * 10),
                is_story_quest=1,
                clues_required=len(next_init_subs),
                sub_objectives=next_init_subs
            )
            for so in next_init_subs:
                so_id = so["id"]
                wps = next_init_wps.get(so_id) or []
                if wps:
                    db.save_quest_waypoints(session_id=session_id, quest_id=next_sq_id, waypoints=wps, sub_obj_id=so_id)

            async def _fill_next_quest():
                try:
                    data = await game_engine.generate_next_story_quest(session_id, session_obj, quest_update)
                    next_title = (data.get("title") or "").strip()
                    next_arch = (data.get("archetype") or "Story Quest").strip()
                    next_obj = (data.get("objective") or "").strip()
                    next_subs = data.get("sub_objectives") or []
                    next_sub_wps = data.get("sub_waypoints") or {}
                    if next_title and next_obj and next_subs:
                        db.upsert_quest(
                            session_id=session_id,
                            quest_id=next_sq_id,
                            quest_type=next_arch,
                            title=next_title,
                            objective=next_obj,
                            progress=f"Quest #{next_ch}",
                            current_clues="",
                            status="Active",
                            reward_xp=250 + (next_ch * 30),
                            reward_gold=60 + (next_ch * 10),
                            is_story_quest=1,
                            clues_required=len(next_subs),
                            sub_objectives=next_subs
                        )
                        # Persist waypoints for each sub-objective
                        from mechanics.world.waypoints import get_archetype_fallback_waypoints
                        for so in next_subs:
                            so_id = so["id"]
                            so_wps_raw = next_sub_wps.get(so_id) or []
                            validated_wps = []
                            for wp in so_wps_raw:
                                if isinstance(wp, dict) and wp.get("stage_label") and wp.get("target_location"):
                                    validated_wps.append({
                                        "stage_index": int(wp.get("stage_index") if wp.get("stage_index") is not None else (len(validated_wps) + 1)),
                                        "stage_label": str(wp.get("stage_label", ""))[:200],
                                        "target_location": str(wp.get("target_location", ""))[:200],
                                        "target_npc": str(wp.get("target_npc", "") or "")[:100],
                                        "completion_trigger": str(wp.get("completion_trigger", "arrival")),
                                        "resource_target": int(wp.get("resource_target") or 0),
                                    })
                            if not validated_wps:
                                validated_wps = get_archetype_fallback_waypoints(so.get("archetype", "default"))
                            if validated_wps:
                                db.save_quest_waypoints(session_id=session_id, quest_id=next_sq_id, waypoints=validated_wps, sub_obj_id=so_id)
                except Exception as e:
                    import logging
                    logging.getLogger(__name__).warning("generate_next_story_quest failed: %s", e)

            try:
                loop = asyncio.get_running_loop()
                loop.create_task(_fill_next_quest())
            except RuntimeError:
                pass  # No running loop: placeholder quest remains until next turn

        if newly_discovered_clue:
            notice["newly_discovered_clue"] = newly_discovered_clue
        return notice

    previously_claimed = bool(matched_quest and matched_quest.get("reward_claimed"))

    # If just claimed, return the notice, plus any newly completed sub-quests or clues
    if status == "Completed" and not previously_claimed:
        return {
            "title": title,
            "quest_type": quest_type,
            "claimed": True,
            "xp": reward_xp,
            "gold": reward_gold,
            "item": reward_item,
            "newly_completed_sub_quests": newly_completed,
            "newly_discovered_clue": newly_discovered_clue
        }
    
    if newly_completed or newly_discovered_clue:
        return {
            "title": title,
            "quest_type": quest_type,
            "claimed": False,
            "newly_completed_sub_quests": newly_completed,
            "newly_discovered_clue": newly_discovered_clue
        }
        
    return None

