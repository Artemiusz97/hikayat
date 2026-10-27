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
    loc = (session.get("current_location") if isinstance(session, dict) else "") or ""
    if not loc and starting_hook_context:
        loc = starting_hook_context.get("suggested_location") or ""
    if not loc and isinstance(session, dict) and session.get("current_node_id"):
        try:
            import db
            node = db.get_world_node(session_id, session["current_node_id"])
            if node:
                ancestors = db.get_node_ancestors(session_id, session["current_node_id"])
                chain = [a["name"] for a in reversed(ancestors)] + [node["name"]]
                loc = " ➔ ".join(chain)
        except Exception:
            pass

    from mechanics.world.locations import (
        get_discovered_primary_locations,
        is_school_scenario,
        sanitize_location_target,
        process_llm_location_update,
        resolve_session_location_tokens,
        format_clean_location_prose,
        clean_narrative_location_arrows,
    )
    from mechanics.world.waypoints import ensure_multi_stage_waypoints

    if loc and "{" in loc:
        loc = resolve_session_location_tokens(session_id, loc, scen_key)

    zones_dict = get_discovered_primary_locations(session_id, scen_key)
    avail_locs_list = []
    for z, prims in zones_dict.items():
        z_res = resolve_session_location_tokens(session_id, z, scen_key)
        for p in prims[:2]:
            p_res = resolve_session_location_tokens(session_id, p, scen_key)
            avail_locs_list.append(f"{z_res} -> {p_res}")

    if not loc:
        if avail_locs_list:
            loc = avail_locs_list[0]
        else:
            try:
                from mechanics.world.locations.seeding import get_default_tiered_location
                dz, dp, _ = get_default_tiered_location(scen_key, session_id=session_id)
                loc = f"{dz} -> {dp}"
            except Exception:
                loc = "Ashford Academy" if is_school_scenario(scen_key) else "the Realm"

    loc1 = avail_locs_list[0] if len(avail_locs_list) > 0 else loc
    loc2 = avail_locs_list[1] if len(avail_locs_list) > 1 else loc1
    loc3 = avail_locs_list[2] if len(avail_locs_list) > 2 else (avail_locs_list[0] if avail_locs_list else loc)

    loc_prose = format_clean_location_prose(loc, include_zone=True, preposition="in")
    loc_short = format_clean_location_prose(loc, include_zone=False)
    loc1_prose = format_clean_location_prose(loc1, include_zone=True, preposition="in")
    loc2_prose = format_clean_location_prose(loc2, include_zone=True, preposition="in")
    loc3_prose = format_clean_location_prose(loc3, include_zone=True, preposition="in")
    loc1_short = format_clean_location_prose(loc1, include_zone=False)
    loc2_short = format_clean_location_prose(loc2, include_zone=False)
    loc3_short = format_clean_location_prose(loc3, include_zone=False)

    import scenario_data
    if scenario_data.is_anomalous_incursions_scenario(scen_key):
        from mechanics.narrative.blueprints import generate_anomalous_campaign_blueprint
        bp = generate_anomalous_campaign_blueprint(session_id, session)
        ch_clamped = max(1, min(11, int(chapter_num or 1)))
        ch_spec = bp["chapters"].get(ch_clamped, bp["chapters"][1])
        anomaly = bp["world_ending_anomaly"]
        ent_name = anomaly.get("name", "The Non-Euclidean Convergence")
        ent_title = anomaly.get("title", "Sovereign of the Folded Horizon")
        omen = anomaly.get("foreshadow_sign", "geometric distortions and bleeding static")
        harbinger = anomaly.get("harbinger_name", "The Convergence Harbinger")

        title = ch_spec["title_template"]
        archetype = ch_spec["archetype"]
        sub_archs = ch_spec["sub_archetypes"]

        if ch_clamped == 1:
            objective = (
                f"Respond to an emerging containment breach at {loc1_prose} and stabilize the affected threshold. "
                f"Investigate anomalous telemetry readings across {loc2_short} and {loc3_prose}, culminating in an ominous resonance spike ({omen}) "
                f"that foreshadows the distant awakening of {ent_name}."
            )
        elif 2 <= ch_clamped <= 6:
            objective = (
                f"{ch_spec['pacing_directive']} Follow the trail of altered relics, spatial distortions, and clandestine interference "
                f"across {loc1_short}, {loc2_short}, and {loc3_prose} before the Cult and Syndicate complete their preparations for {ent_name}."
            )
        elif 7 <= ch_clamped <= 9:
            objective = (
                f"{ch_spec['pacing_directive']} Reinforce municipal quarantine cordons at {loc1_short}, intercept hostile manifestations at {loc2_short}, "
                f"and confront {harbinger}'s vanguard forces near {loc3_prose}."
            )
        elif ch_clamped == 10:
            objective = (
                f"Reality fractures across the metropolitan sky as {ent_name} ({ent_title}) manifests at the convergence epicenter! "
                f"Map the non-Euclidean breach at {loc1_short}, sever the final ritual anchors at {loc2_short}, and defeat {ent_name} at {loc3_prose} to save the world!"
            )
        else:
            objective = (
                f"With {ent_name} defeated and the cataclysm averted, seal the last lingering reality echoes at {loc1_short}, "
                f"suppress residual cognitohazard fallout at {loc2_short}, and attend your post-crisis commendation & debriefing at {loc3_prose}."
            )

        sub_objs = [
            {
                "id": 1,
                "archetype": sub_archs[0],
                "text": f"[{sub_archs[0]}] Execute primary field protocol and secure resonance telemetry at {loc1_prose}.",
                "completed": False,
            },
            {
                "id": 2,
                "archetype": sub_archs[1],
                "text": f"[{sub_archs[1]}] Stabilize secondary breach vectors and neutralize interference at {loc2_prose}.",
                "completed": False,
            },
            {
                "id": 3,
                "archetype": sub_archs[2],
                "text": (
                    f"[Boss Confrontation] Breach the convergence core and defeat {ent_name} at {loc3_prose}!"
                    if ch_clamped == 10
                    else (
                        f"[Foreshadowing Spike] Contain the breach leader at {loc3_prose} and record the ominous signature ({omen})."
                        if ch_clamped == 1
                        else f"[{sub_archs[2]}] Complete final chapter containment objective at {loc3_prose}."
                    )
                ),
                "completed": False,
            },
        ]
    elif is_school_scenario(scen_key):
        from mechanics.social.school_roster import ensure_school_directory_exists
        roster = ensure_school_directory_exists(session)
        from mechanics.world.locations.seeds import get_session_school_name
        school_name = get_session_school_name(session_id, scen_key) or "the Academy"
        title = f"Chapter #{chapter_num}: Whispers at {school_name}"
        archetype = "Campus Investigation"
        objective = (
            f"Unsettling rumors and hidden rivalries are spreading through {school_name}. "
            f"Investigate the initial disturbance, gather vital testimonies from students across campus facilities, "
            f"and uncover who is pulling the strings before the situation spirals out of control."
        )
        sub_objs = [
            {
                "id": 1,
                "archetype": "Investigation",
                "text": f"Search for physical evidence and inspect the disturbance site at {loc1_prose}.",
                "completed": False
            },
            {
                "id": 2,
                "archetype": "Infiltration",
                "text": f"Infiltrate the restricted records or quiet corners of {loc2_prose} to gather confidential intel.",
                "completed": False
            },
            {
                "id": 3,
                "archetype": "Diplomacy",
                "text": f"Interview key student leads and negotiate with club representatives at {loc3_prose}.",
                "completed": False
            }
        ]
    elif starting_hook_context and chapter_num == 1:
        arch_title = starting_hook_context.get("archetype_title") or starting_hook_context.get("archetype", "hub_launchpad").replace("_", " ").title()
        title = f"Chapter #1: The {arch_title} Resolution"
        archetype = "Inciting Incident"
        objective = (
            f"The repercussions of the {arch_title.lower()} incident have begun to unfold across {loc_prose}. "
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
                "text": f"Scout the perimeter and bypass security barriers around {loc2_prose}.",
                "completed": False
            },
            {
                "id": 3,
                "archetype": "Diplomacy",
                "text": f"Confront the regional instigator or coordinate countermeasures with allies at {loc3_prose}.",
                "completed": False
            }
        ]
    elif "cyber" in scen_key.lower():
        title = f"Chapter #{chapter_num}: Encrypted Subnets"
        archetype = "Corporate Espionage"
        objective = (
            f"Hostile corporate factions have initiated surveillance across {loc_prose}. "
            f"Infiltrate protected networks, recover encrypted data chips, and establish counter-measures "
            f"before your squad is tracked down by automated enforcement units."
        )
        sub_objs = [
            {
                "id": 1,
                "archetype": "Investigation",
                "text": f"Hack into the local comms hub at {loc1_prose} and decrypt illicit network chatter.",
                "completed": False
            },
            {
                "id": 2,
                "archetype": "Infiltration",
                "text": f"Bypass automated firewalls and stealthily breach the mainframe sector at {loc2_prose}.",
                "completed": False
            },
            {
                "id": 3,
                "archetype": "Diplomacy",
                "text": f"Deliver extracted intelligence to black-market contacts or extract assets at {loc3_prose}.",
                "completed": False
            }
        ]
    else:
        title = f"Chapter #{chapter_num}: Shadows Over {loc_short or 'the Frontier'}"
        archetype = "Frontier Delve"
        objective = (
            f"Dark forces and unexplained anomalies threaten the stability of {loc_prose}. "
            f"Explore uncharted reaches, collect critical relics of power, and coordinate with regional guardians "
            f"to neutralize the gathering peril."
        )
        sub_objs = [
            {
                "id": 1,
                "archetype": "Investigation",
                "text": f"Examine the anomaly and recover physical evidence from the threshold of {loc1_prose}.",
                "completed": False
            },
            {
                "id": 2,
                "archetype": "Infiltration",
                "text": f"Delve into hazardous ruins and bypass mystical barriers at {loc2_prose}.",
                "completed": False
            },
            {
                "id": 3,
                "archetype": "Diplomacy",
                "text": f"Negotiate with faction scouts or confront the regional champion at {loc3_prose}.",
                "completed": False
            }
        ]

    from mechanics.narrative.blueprints import get_blueprint_for_archetype, infer_required_item_and_count_from_text
    sub_waypoints = {}
    for idx, so in enumerate(sub_objs, 1):
        arch = so.get("archetype", "Investigation")
        so_bp = get_blueprint_for_archetype(arch, so.get("text", ""))
        so["blueprint_id"] = so_bp
        req_item, req_cnt = infer_required_item_and_count_from_text(so.get("text", "")) if so_bp == "ACQUISITION" else ("", 1)
        so["required_item"] = req_item
        so["required_item_count"] = req_cnt
        so_loc = loc1 if idx == 1 else (loc2 if idx == 2 else loc3)
        sub_waypoints[idx] = ensure_multi_stage_waypoints(
            [], default_loc=so_loc, archetype=arch, secondary_loc=so_loc,
            session_id=session_id, scen_key=scen_key, required_item=req_item
        )

    sub_waypoints = game_engine._distribute_fallback_locations(session_id, scen_key, sub_waypoints, sub_objs)

    for so_id, wps in sub_waypoints.items():
        for wp in wps:
            t_loc = wp.get("target_location", "").strip()
            if t_loc:
                clean_t = sanitize_location_target(t_loc, session_id=session_id, scen_key=scen_key)
                process_llm_location_update(session_id, clean_t, scen_key)

    title = clean_narrative_location_arrows(resolve_session_location_tokens(session_id, title, scen_key))
    objective = clean_narrative_location_arrows(resolve_session_location_tokens(session_id, objective, scen_key))
    for so in sub_objs:
        if "text" in so:
            so["text"] = clean_narrative_location_arrows(resolve_session_location_tokens(session_id, so["text"], scen_key))
    for so_id, wps in sub_waypoints.items():
        for wp in wps:
            if wp.get("target_location") and "{" in wp["target_location"]:
                wp["target_location"] = resolve_session_location_tokens(session_id, wp["target_location"], scen_key)
            if wp.get("stage_label"):
                wp["stage_label"] = clean_narrative_location_arrows(resolve_session_location_tokens(session_id, wp["stage_label"], scen_key))

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
            # Self-healing for unrendered location tokens or raw arrow strings in prose
            scen_key = session.get("scenario", "fantasy")
            raw_check = f"{sq.get('title', '')} {sq.get('objective', '')} {str(sub_objs)}"
            if ("{" in raw_check and "session_" in raw_check) or "➔" in raw_check or "->" in raw_check:
                from mechanics.world.locations import resolve_session_location_tokens, clean_narrative_location_arrows
                sq_title = clean_narrative_location_arrows(resolve_session_location_tokens(session_id, sq.get("title") or "", scen_key))
                sq_obj = clean_narrative_location_arrows(resolve_session_location_tokens(session_id, sq.get("objective") or "", scen_key))
                sq_sub = []
                for so in sub_objs:
                    so_c = dict(so)
                    if "text" in so_c:
                        so_c["text"] = clean_narrative_location_arrows(resolve_session_location_tokens(session_id, so_c["text"], scen_key))
                    sq_sub.append(so_c)
                db.upsert_quest(
                    session_id=session_id,
                    quest_id=sq["quest_id"],
                    quest_type=sq.get("quest_type") or "Story Quest",
                    title=sq_title,
                    objective=sq_obj,
                    progress=sq.get("progress") or "Active",
                    current_clues=sq.get("current_clues") or "",
                    status=sq.get("status") or "Active",
                    reward_xp=sq.get("reward_xp") or 250,
                    reward_gold=sq.get("reward_gold") or 60,
                    is_story_quest=1,
                    clues_required=sq.get("clues_required") or len(sq_sub),
                    sub_objectives=sq_sub
                )
                with db.get_conn() as conn:
                    wp_rows = conn.execute("SELECT id, target_location, stage_label FROM quest_waypoints WHERE session_id=? AND quest_id=?", (session_id, sq["quest_id"])).fetchall()
                    for wp_r in wp_rows:
                        tl = wp_r["target_location"] or ""
                        sl = wp_r["stage_label"] or ""
                        tl_f = resolve_session_location_tokens(session_id, tl, scen_key)
                        sl_f = clean_narrative_location_arrows(resolve_session_location_tokens(session_id, sl, scen_key))
                        if tl_f != tl or sl_f != sl:
                            conn.execute("UPDATE quest_waypoints SET target_location=?, stage_label=? WHERE id=?", (tl_f, sl_f, wp_r["id"]))
                sq = db.get_active_story_quest(session_id)
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

    import scenario_data
    from mechanics.narrative.blueprints import get_max_campaign_chapters, generate_anomalous_campaign_blueprint
    max_chapters = get_max_campaign_chapters(scen_key)
    is_anom_story = scenario_data.is_anomalous_incursions_scenario(scen_key)

    pacing_note = f"CAMPAIGN PACING: This is Chapter #{chapter_num} of {max_chapters}.\n"
    anom_story_context = ""
    if is_anom_story:
        bp = generate_anomalous_campaign_blueprint(session_id, session)
        ch_clamped = max(1, min(11, int(chapter_num or 1)))
        ch_spec = bp["chapters"].get(ch_clamped, bp["chapters"][1])
        anomaly = bp["world_ending_anomaly"]
        pacing_note += (
            f"ANOMALOUS INCURSIONS 11-CHAPTER ARC DIRECTIVE:\n"
            f"- World-Ending Antagonist: {anomaly.get('name')} ({anomaly.get('title')})\n"
            f"- Foreshadow Omen: {anomaly.get('foreshadow_sign')}\n"
            f"- {ch_spec['pacing_directive']}\n"
            f"- Required Sub-Quest Archetypes for this Chapter: {', '.join(ch_spec['sub_archetypes'])}\n"
            f"- NEVER use numeric threat grades (e.g. never say 'Grade-4').\n"
        )
        anom_story_context = (
            f"WORLD-ENDING ANOMALY DOSSIER: {anomaly.get('name')} — {ch_spec['pacing_directive']}\n"
            f"Use these 3 sub-quest archetypes in order: {', '.join(ch_spec['sub_archetypes'])}.\n\n"
        )
    elif chapter_num >= max_chapters:
        pacing_note += (
            "🏆 [GRAND FINALE CHAPTER]: This is the climactic 10th and final chapter of the campaign!\n"
            "The overarching objective and sub-quests MUST stage the ultimate culmination of the campaign, resolving the core mysteries and Campaign End Goals.\n"
        )
    elif chapter_num == (max_chapters // 2):
        pacing_note += (
            "⚡ [MID-CAMPAIGN CLIMAX (Chapter 5/10)]: This is the halfway turning point of the campaign!\n"
            "Introduce major narrative escalations, shocking revelations, or rising stakes that propel the story into its darker or more intense second half.\n"
        )
    elif chapter_num == (max_chapters - 1):
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
        f"{anom_story_context}"
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
            so_target = avail_locs_list[idx - 1] if idx - 1 < len(avail_locs_list) else loc
            if isinstance(item, str) and item.strip():
                sub_objs.append({"id": idx, "archetype": "Investigation", "text": item.strip(), "completed": False})
                sub_waypoints[idx] = ensure_multi_stage_waypoints([], default_loc=so_target, archetype="Investigation", session_id=session_id)
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
                    sub_waypoints[so_id] = ensure_multi_stage_waypoints(wp_list, default_loc=so_target, archetype=arch, session_id=session_id)

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
                sub_waypoints[next_id] = ensure_multi_stage_waypoints([], default_loc=loc, archetype=arch, session_id=session_id)
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
            sub_waypoints[next_id] = ensure_multi_stage_waypoints([], default_loc=loc, archetype=arch, session_id=session_id)

    from mechanics.narrative.blueprints import get_blueprint_for_archetype, infer_required_item_and_count_from_text
    # Normalize IDs to 1, 2, 3 and enrich with blueprints
    for idx, so in enumerate(sub_objs[:3], 1):
        old_id = so["id"]
        so["id"] = idx
        if old_id != idx and old_id in sub_waypoints:
            sub_waypoints[idx] = sub_waypoints.pop(old_id)
        arch = so.get("archetype", "Investigation")
        so_bp = get_blueprint_for_archetype(arch, so.get("text", ""))
        so["blueprint_id"] = so_bp
        req_item, req_cnt = infer_required_item_and_count_from_text(so.get("text", "")) if so_bp == "ACQUISITION" else ("", 1)
        so["required_item"] = req_item
        so["required_item_count"] = req_cnt
        if idx in sub_waypoints and req_item:
            for wp in sub_waypoints[idx]:
                if wp.get("stage_index") == len(sub_waypoints[idx]):
                    wp["required_item"] = req_item
    sub_objs = sub_objs[:3]

    # Distribute fallback locations so each sub-quest targets a DISTINCT location
    sub_waypoints = game_engine._distribute_fallback_locations(session_id, scen_key, sub_waypoints, sub_objs)

    # Auto-discover target locations in SQLite
    from mechanics.world.locations import sanitize_location_target, clean_narrative_location_arrows
    for so in sub_objs:
        if so.get("text"):
            so["text"] = clean_narrative_location_arrows(so["text"])
    for so_id, wps in sub_waypoints.items():
        for wp in wps:
            if wp.get("stage_label"):
                wp["stage_label"] = clean_narrative_location_arrows(wp["stage_label"])
            t_loc = wp.get("target_location", "").strip()
            if t_loc:
                clean_t = sanitize_location_target(t_loc, session_id=session_id, scen_key=scen_key)
                process_llm_location_update(session_id, clean_t, scen_key)

    return {
        "title": clean_narrative_location_arrows((result.get("title") or f"Chapter #{chapter_num} Objective").strip()),
        "archetype": (result.get("archetype") or "Story Quest").strip(),
        "objective": clean_narrative_location_arrows((result.get("objective") or "Complete chapter objectives.").strip()),
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

def sync_deterministic_campaign_goals(session_id: int) -> None:
    """Computes campaign_goals progress_pct deterministically from chapter + Story Quest completion (D11)."""
    if not session_id:
        return
    goals = db.get_session_campaign_goals(session_id)
    if not goals:
        return
    cur_ch = db.get_session_chapter(session_id) or 1
    active_sq = db.get_active_story_quest(session_id)
    sub_ratio = 0.0
    if active_sq and isinstance(active_sq.get("sub_objectives"), list) and active_sq["sub_objectives"]:
        subs = [s for s in active_sq["sub_objectives"] if isinstance(s, dict)]
        if subs:
            done_cnt = sum(1 for s in subs if s.get("completed"))
            sub_ratio = done_cnt / len(subs)
    det_pct = min(100, max(0, int(round(((max(1, cur_ch) - 1 + sub_ratio) / MAX_CAMPAIGN_CHAPTERS) * 100))))
    dirty_goals = False
    for g in goals:
        if det_pct > int(g.get("progress_pct", 0) or 0):
            g["progress_pct"] = det_pct
            dirty_goals = True
        if int(g.get("progress_pct", 0) or 0) >= 100 and g.get("status") != "Completed":
            g["status"] = "Completed"
            dirty_goals = True
    if dirty_goals:
        db.update_session_campaign_goals(session_id, goals)


def apply_quest_update(session_id: int, quest_update: dict, party_user_ids: list[int] = None, outcome: dict = None, actions: list[dict] = None, from_llm: bool = False) -> dict | None:
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
                n = game_engine.apply_quest_update(session_id, qu, party_user_ids=party_user_ids, outcome=outcome or quest_update, actions=actions, from_llm=from_llm)
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

    # Phase 5 Guard: Zero LLM Objective Authority (D1, D11)
    if from_llm and not quest_update.get("_server_authoritative"):
        if not matched_quest:
            return None
        status = matched_quest.get("status") or "Active"
        reward_xp = matched_quest.get("reward_xp", reward_xp)
        reward_gold = matched_quest.get("reward_gold", reward_gold)
        reward_item = matched_quest.get("reward_item", reward_item)

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

    # Update Goal Progress % deterministically from chapter & Story Quest completion (D11)
    cur_ch = db.get_session_chapter(session_id) or 1
    sync_deterministic_campaign_goals(session_id)

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
                        consume_quest_delivery_item_if_needed(session_id, matched_quest or quest_update, party_user_ids, sub_obj=so)
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
            session_obj = db.get_session(session_id) or {"id": session_id}
            scen_key_curr = str(session_obj.get("scenario") or "fantasy")
            import scenario_data as _sd_q
            from mechanics.narrative.blueprints import get_max_campaign_chapters
            max_ch_for_scen = get_max_campaign_chapters(scen_key_curr)

            cur_ch = db.get_session_chapter(session_id)

            # Deterministic Campaign Goal Advance on Chapter Completion
            goals = db.get_session_campaign_goals(session_id)
            if goals:
                new_floor = min(100, int((cur_ch / max_ch_for_scen) * 100))
                for g in goals:
                    g["progress_pct"] = max(g.get("progress_pct", 0), new_floor)
                    if cur_ch >= max_ch_for_scen or g["progress_pct"] >= 100:
                        g["progress_pct"] = 100
                        g["status"] = "Completed"
                db.update_session_campaign_goals(session_id, goals)

            # Anomalous Incursions Chapter 11 Completion -> Post-Game Epilogue & Endless Mode Choice!
            if _sd_q.is_anomalous_incursions_scenario(scen_key_curr) and cur_ch >= 11:
                epilogue_choices = [
                    {
                        "label": "🏁 Conclude Campaign (Archive Chronicle)",
                        "stat": "FREE",
                        "requirement": 0,
                        "mp_cost": 0,
                        "intent": "epilogue_conclude_campaign",
                    },
                    {
                        "label": "♾️ Continue in Endless Containment Mode",
                        "stat": "FREE",
                        "requirement": 0,
                        "mp_cost": 0,
                        "intent": "epilogue_endless_mode",
                    },
                ]
                db.update_session(session_id, extra={"epilogue_ready": True, "epilogue_choices": epilogue_choices})
                notice["epilogue_ready"] = True
                notice["epilogue_choices"] = epilogue_choices
                if isinstance(outcome, dict):
                    outcome["epilogue_ready"] = True
                    outcome["epilogue_choices"] = epilogue_choices
                if newly_discovered_clue:
                    notice["newly_discovered_clue"] = newly_discovered_clue
                return notice

            next_ch = cur_ch + 1
            db.set_session_chapter(session_id, next_ch)

            # Write a contextual quest immediately so the DB is NEVER blank or generic,
            # then schedule the LLM call to replace it with a fully unique quest.
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

def evaluate_quest_state_predicates(
    session_id: int,
    user_id: int = None,
    event_info: dict = None
) -> list[dict]:
    """
    Dual-layer predicate evaluator for active quests and sub-objectives.
    Runs pre-turn and on reactive event triggers (e.g. ItemGained, NPCStatusChanged).
    - ACQUISITION quests: checks player unequipped inventory against required_item & required_item_count.
      - If held >= required: auto-advances pre-final waypoints to completed, activates final delivery waypoint,
        and sets quest progress to 'Ready to deliver <item> (<held>/<req>)'.
      - If 0 < held < required: updates quest progress to '<held>/<req> <item> Collected'.
    - Also evaluates Story Quest sub-objectives with blueprint_id == 'ACQUISITION'.
    - NEUTRALIZATION / ESCORT quests: handles NPCStatusChangedEvent to advance waypoints if target NPC status changed.
    Returns list of notification/update dicts.
    """
    import db
    import time
    from mechanics.narrative.blueprints import (
        get_blueprint_for_archetype,
        infer_required_item_and_count_from_text,
        find_matching_inventory_items_for_quest,
    )

    if not session_id:
        return []

    party_uids = []
    if user_id:
        party_uids.append(user_id)
    sess = db.get_session(session_id)
    if sess:
        if sess.get("host_user_id") and sess["host_user_id"] not in party_uids:
            party_uids.append(sess["host_user_id"])
        if sess.get("user_id") and sess["user_id"] not in party_uids:
            party_uids.append(sess["user_id"])
    if not party_uids:
        try:
            with db.get_conn() as conn:
                row = conn.execute("SELECT user_id FROM characters LIMIT 1").fetchone()
                if row and row["user_id"]:
                    party_uids.append(row["user_id"])
        except Exception:
            pass
    if not party_uids:
        party_uids = [1]

    # Pool unequipped inventory items across party
    all_inventory = []
    for uid in party_uids:
        all_inventory.extend(db.get_inventory(uid))

    active_quests = db.get_session_quests(session_id, status="Active")
    results = []

    for q in active_quests:
        qid = q.get("quest_id")
        if not qid:
            continue
        bp = q.get("blueprint_id") or get_blueprint_for_archetype(q.get("quest_type", ""), q.get("objective", ""))

        # 1. Top-level ACQUISITION quest
        if bp == "ACQUISITION":
            req_item = (q.get("required_item") or "").strip()
            req_cnt = int(q.get("required_item_count") or 1)
            if not req_item:
                req_item, req_cnt = infer_required_item_and_count_from_text(q.get("objective", ""), q.get("title", ""))

            if req_item:
                matching = find_matching_inventory_items_for_quest(req_item, all_inventory, exclude_equipped=True)
                held_cnt = len(matching)

                wps = db.get_quest_waypoints(session_id, qid, None)
                if wps and len(wps) > 1:
                    max_stage = max(int(w.get("stage_index", 1)) for w in wps)
                    if held_cnt >= req_cnt:
                        with db.get_conn() as conn:
                            conn.execute(
                                "UPDATE quest_waypoints SET status='completed', updated_at=? WHERE session_id=? AND quest_id=? AND sub_obj_id IS NULL AND stage_index < ?",
                                (time.time(), session_id, qid, max_stage)
                            )
                            conn.execute(
                                "UPDATE quest_waypoints SET status='active', updated_at=? WHERE session_id=? AND quest_id=? AND sub_obj_id IS NULL AND stage_index = ?",
                                (time.time(), session_id, qid, max_stage)
                            )
                        new_prog = f"Ready to deliver {req_item} ({held_cnt}/{req_cnt})"
                        if q.get("progress") != new_prog:
                            with db.get_conn() as conn:
                                conn.execute(
                                    "UPDATE quests SET progress=?, required_item=?, required_item_count=?, updated_at=? WHERE session_id=? AND quest_id=?",
                                    (new_prog, req_item, req_cnt, time.time(), session_id, qid)
                                )
                            results.append({"quest_id": qid, "type": "inventory_ready", "progress": new_prog, "required_item": req_item, "held_count": held_cnt})
                    elif held_cnt > 0:
                        new_prog = f"{held_cnt}/{req_cnt} {req_item} Collected"
                        if q.get("progress") != new_prog:
                            with db.get_conn() as conn:
                                conn.execute(
                                    "UPDATE quests SET progress=?, required_item=?, required_item_count=?, updated_at=? WHERE session_id=? AND quest_id=?",
                                    (new_prog, req_item, req_cnt, time.time(), session_id, qid)
                                )
                            results.append({"quest_id": qid, "type": "partial_progress", "progress": new_prog, "required_item": req_item, "held_count": held_cnt})
                elif not wps and held_cnt >= req_cnt:
                    new_prog = f"Ready to deliver {req_item} ({held_cnt}/{req_cnt})"
                    if q.get("progress") != new_prog:
                        with db.get_conn() as conn:
                            conn.execute(
                                "UPDATE quests SET progress=?, required_item=?, required_item_count=?, updated_at=? WHERE session_id=? AND quest_id=?",
                                (new_prog, req_item, req_cnt, time.time(), session_id, qid)
                            )
                        results.append({"quest_id": qid, "type": "inventory_ready", "progress": new_prog, "required_item": req_item, "held_count": held_cnt})

        # 2. Sub-objectives (Story Quests & Multi-branch quests)
        sub_objs = q.get("sub_objectives") or []
        if isinstance(sub_objs, list) and sub_objs:
            sub_dirty = False
            for so in sub_objs:
                if not isinstance(so, dict) or so.get("completed"):
                    continue
                so_id = so.get("id")
                if not so_id:
                    continue
                so_bp = so.get("blueprint_id") or get_blueprint_for_archetype(so.get("archetype", ""), so.get("text", ""))
                if so_bp == "ACQUISITION":
                    so_req_item = (so.get("required_item") or "").strip()
                    so_req_cnt = int(so.get("required_item_count") or 1)
                    if not so_req_item:
                        so_req_item, so_req_cnt = infer_required_item_and_count_from_text(so.get("text", ""))
                        if so_req_item:
                            so["required_item"] = so_req_item
                            so["required_item_count"] = so_req_cnt
                            sub_dirty = True
                    
                    if so_req_item:
                        so_matching = find_matching_inventory_items_for_quest(so_req_item, all_inventory, exclude_equipped=True)
                        so_held = len(so_matching)

                        so_wps = db.get_quest_waypoints(session_id, qid, so_id)
                        if so_wps and len(so_wps) > 1:
                            so_max_stage = max(int(w.get("stage_index", 1)) for w in so_wps)
                            if so_held >= so_req_cnt:
                                with db.get_conn() as conn:
                                    conn.execute(
                                        "UPDATE quest_waypoints SET status='completed', updated_at=? WHERE session_id=? AND quest_id=? AND sub_obj_id=? AND stage_index < ?",
                                        (time.time(), session_id, qid, so_id, so_max_stage)
                                    )
                                    conn.execute(
                                        "UPDATE quest_waypoints SET status='active', updated_at=? WHERE session_id=? AND quest_id=? AND sub_obj_id=? AND stage_index = ?",
                                        (time.time(), session_id, qid, so_id, so_max_stage)
                                    )
                                new_so_prog = f"Ready to deliver {so_req_item} ({so_held}/{so_req_cnt})"
                                if so.get("progress") != new_so_prog:
                                    so["progress"] = new_so_prog
                                    sub_dirty = True
                                    results.append({"quest_id": qid, "sub_obj_id": so_id, "type": "inventory_ready", "progress": new_so_prog})
                            elif so_held > 0:
                                new_so_prog = f"{so_held}/{so_req_cnt} {so_req_item} Collected"
                                if so.get("progress") != new_so_prog:
                                    so["progress"] = new_so_prog
                                    sub_dirty = True
                                    results.append({"quest_id": qid, "sub_obj_id": so_id, "type": "partial_progress", "progress": new_so_prog})
            if sub_dirty:
                with db.get_conn() as conn:
                    conn.execute(
                        "UPDATE quests SET sub_objectives_json=?, updated_at=? WHERE session_id=? AND quest_id=?",
                        (json.dumps(sub_objs), time.time(), session_id, qid)
                    )

        # 3. Reactive NPCStatusChanged check
        if event_info and event_info.get("type") in ("NPCStatusChanged", "NPCStatusChangedEvent"):
            target_status = str(event_info.get("status") or "").strip().lower()
            changed_npc = str(event_info.get("name") or "").strip().lower()
            if target_status in ("deceased", "captured", "disappeared", "spared"):
                from mechanics.world.waypoints.matching import advance_waypoint_stage
                top_active_wp = db.get_active_waypoint(session_id, qid, None)
                if top_active_wp:
                    wp_npc = str(top_active_wp.get("target_npc") or "").strip().lower()
                    if wp_npc and (wp_npc in changed_npc or changed_npc in wp_npc):
                        adv_res = advance_waypoint_stage(session_id, qid, None)
                        results.append({"quest_id": qid, "type": "npc_status_advanced", "npc": changed_npc, "status": target_status, "adv_res": adv_res})

                if isinstance(sub_objs, list) and sub_objs:
                    for so in sub_objs:
                        if not isinstance(so, dict) or so.get("completed"):
                            continue
                        so_id = so.get("id")
                        if not so_id:
                            continue
                        so_active_wp = db.get_active_waypoint(session_id, qid, so_id)
                        if so_active_wp:
                            so_wp_npc = str(so_active_wp.get("target_npc") or "").strip().lower()
                            if so_wp_npc and (so_wp_npc in changed_npc or changed_npc in so_wp_npc):
                                adv_res = advance_waypoint_stage(session_id, qid, so_id)
                                results.append({"quest_id": qid, "sub_obj_id": so_id, "type": "npc_status_advanced", "npc": changed_npc, "status": target_status, "adv_res": adv_res})

    return results


def grant_stage_acquisition_item_if_needed(
    session_id: int,
    quest: dict,
    completed_stage_index: int,
    total_stages: int,
    party_user_ids: list[int] = None,
    sub_obj: dict = None,
) -> str | None:
    """
    When a non-final stage of an ACQUISITION quest/sub-objective completes, guarantees
    that the required item is in the player's inventory so the final delivery stage
    can consume it. Eliminates ghost item bugs.
    """
    if completed_stage_index >= total_stages:
        return None

    import db
    from mechanics.narrative.blueprints import (
        get_blueprint_for_archetype,
        infer_required_item_and_count_from_text,
        find_matching_inventory_items_for_quest,
    )

    bp = (sub_obj.get("blueprint_id") if sub_obj else (quest.get("blueprint_id") if quest else None)) or ""
    if not bp:
        bp = get_blueprint_for_archetype(
            (sub_obj.get("archetype") if sub_obj else (quest.get("quest_type") if quest else "")) or "",
            (sub_obj.get("text") if sub_obj else (quest.get("objective") if quest else "")) or ""
        )
    if bp != "ACQUISITION":
        return None

    req_item = (sub_obj.get("required_item") if sub_obj else (quest.get("required_item") if quest else "")) or ""
    req_cnt = int((sub_obj.get("required_item_count") if sub_obj else (quest.get("required_item_count") if quest else 1)) or 1)
    if not req_item:
        req_item, req_cnt = infer_required_item_and_count_from_text(
            (sub_obj.get("text") if sub_obj else (quest.get("objective") if quest else "")) or "",
            (quest.get("title") if quest else "") or ""
        )
    if not req_item:
        return None

    party_uids = list(party_user_ids or [])
    if not party_uids and session_id:
        sess = db.get_session(session_id)
        if sess:
            if sess.get("host_user_id"):
                party_uids.append(sess["host_user_id"])
            elif sess.get("user_id"):
                party_uids.append(sess["user_id"])
    if not party_uids:
        try:
            with db.get_conn() as conn:
                row = conn.execute("SELECT user_id FROM characters LIMIT 1").fetchone()
                if row and row["user_id"]:
                    party_uids.append(row["user_id"])
        except Exception:
            pass
    if not party_uids:
        party_uids = [1]

    matching = []
    for uid in party_uids:
        inv = db.get_inventory(uid)
        matching.extend(find_matching_inventory_items_for_quest(req_item, inv, exclude_equipped=True))
    held_cnt = len(matching)

    if held_cnt < req_cnt:
        needed = req_cnt - held_cnt
        target_uid = party_uids[0]
        label = sub_obj.get("text") if sub_obj else quest.get("title", "Quest")
        desc = f"Acquired for {label}"
        for _ in range(needed):
            db.add_item(target_uid, req_item, "Quest Item", desc, slot_cost=0, force=True)
        return req_item
    return None


def consume_quest_delivery_item_if_needed(
    session_id: int,
    quest: dict,
    party_user_ids: list[int] = None,
    sub_obj: dict = None,
) -> str | None:
    """
    When an ACQUISITION quest or sub-objective completes, removes the required number
    of unequipped matching items from player inventory. Strictly preserves equipped items.
    """
    import db
    if sub_obj and sub_obj.get("delivery_consumed"):
        return None

    qid = quest.get("quest_id") if quest else None
    q_full = db.get_quest_by_id(session_id, qid) if (session_id and qid) else quest
    if not sub_obj and q_full and q_full.get("delivery_consumed"):
        return None

    from mechanics.narrative.blueprints import (
        get_blueprint_for_archetype,
        infer_required_item_and_count_from_text,
        find_matching_inventory_items_for_quest,
    )

    bp = (sub_obj.get("blueprint_id") if sub_obj else (q_full.get("blueprint_id") if q_full else None)) or ""
    if not bp:
        bp = get_blueprint_for_archetype(
            (sub_obj.get("archetype") if sub_obj else (q_full.get("quest_type") if q_full else "")) or "",
            (sub_obj.get("text") if sub_obj else (q_full.get("objective") if q_full else "")) or ""
        )
    if bp != "ACQUISITION":
        return None

    req_item = (sub_obj.get("required_item") if sub_obj else (q_full.get("required_item") if q_full else "")) or ""
    req_cnt = int((sub_obj.get("required_item_count") if sub_obj else (q_full.get("required_item_count") if q_full else 1)) or 1)
    if not req_item:
        req_item, req_cnt = infer_required_item_and_count_from_text(
            (sub_obj.get("text") if sub_obj else (q_full.get("objective") if q_full else "")) or "",
            (q_full.get("title") if q_full else "") or ""
        )
    if not req_item:
        return None

    party_uids = list(party_user_ids or [])
    if not party_uids and session_id:
        sess = db.get_session(session_id)
        if sess:
            if sess.get("host_user_id"):
                party_uids.append(sess["host_user_id"])
            elif sess.get("user_id"):
                party_uids.append(sess["user_id"])
    if not party_uids:
        try:
            with db.get_conn() as conn:
                row = conn.execute("SELECT user_id FROM characters LIMIT 1").fetchone()
                if row and row["user_id"]:
                    party_uids.append(row["user_id"])
        except Exception:
            pass
    if not party_uids:
        party_uids = [1]

    consumed = 0
    for uid in party_uids:
        if consumed >= req_cnt:
            break
        inv = db.get_inventory(uid)
        matching = find_matching_inventory_items_for_quest(req_item, inv, exclude_equipped=True)
        for item in matching:
            if consumed >= req_cnt:
                break
            if db.remove_item(uid, item["id"]):
                consumed += 1

    if sub_obj:
        sub_obj["delivery_consumed"] = 1
    elif q_full:
        q_full["delivery_consumed"] = 1

    if consumed > 0:
        return f"Consumed {consumed}x {req_item}"
    return None


# -----------------------------------------------------------------------------
# Phase 4 Comms Engine & Cross-System Messaging
# -----------------------------------------------------------------------------

def send_quest_comms_message(
    session_id: int,
    sender_npc_id: str,
    msg_type: str,
    quest_title: str,
    target_npc: str = "",
    target_loc: str = "",
    scen_key: str = "fantasy",
) -> str | None:
    """
    Sends a scenario-appropriate Phone DM / Guild Courier message, persists it to phone_messages,
    and returns the narrator directive string (truthy on success, None on failure).
    """
    import db
    from mechanics.narrative.blueprints import format_quest_comms_message
    if not session_id or not sender_npc_id:
        return None
    try:
        channel_prefix, body = format_quest_comms_message(
            scen_key=scen_key,
            sender_name=sender_npc_id,
            msg_type=msg_type,
            quest_title=quest_title,
            target_npc=target_npc,
            target_loc=target_loc,
        )
        full_msg = f"{channel_prefix} {body}"
        db.save_phone_message(
            session_id=session_id,
            contact_npc_id=sender_npc_id,
            sender="npc",
            message=full_msg,
            intent="quest_comms",
        )
        return f"[INCOMING QUEST COMMS - {channel_prefix}]: {body}"
    except Exception:
        return None


def trigger_stage2_midquest_comms_if_eligible(
    session_id: int, quest: dict, session: dict = None
) -> str | None:
    """
    Checks if a quest has advanced to Stage >= 2 and dispatches the mid-quest tactical intel or plea DM.
    Returns the narrator directive string when sent (truthy), or None if not eligible.
    """
    import db
    from mechanics.narrative.blueprints import has_quest_note_flag
    from db.quests import append_quest_note_flag_in_db
    qid = quest.get("quest_id", "")
    if not qid:
        return None
    q_fresh = db.get_quest_by_id(session_id, qid) or quest
    q_notes = str(q_fresh.get("quest_notes") or "")
    if has_quest_note_flag(q_notes, "midquest_dm_sent"):
        return None
    cur_active_wp = db.get_active_waypoint(session_id, qid, None)
    if not cur_active_wp or int(cur_active_wp.get("stage_index") or 1) < 2:
        return None

    append_quest_note_flag_in_db(session_id, qid, "midquest_dm_sent", "1")
    scen = (session.get("scenario") if session else "") or "fantasy"
    bp = str(quest.get("blueprint_id") or "")
    client = quest.get("client_npc") or "Guild Handler"
    tgt_npc = cur_active_wp.get("target_npc") or quest.get("target_npc") or ""
    tgt_loc = cur_active_wp.get("target_location") or ""
    if bp in ("NEUTRALIZATION", "SOCIAL_MANIPULATION") and tgt_npc and tgt_npc.strip().lower() != client.strip().lower():
        return send_quest_comms_message(
            session_id=session_id,
            sender_npc_id=tgt_npc,
            msg_type="stage2_target_plea",
            quest_title=quest.get("title", "Quest"),
            target_npc=tgt_npc,
            target_loc=tgt_loc,
            scen_key=scen,
        )
    else:
        return send_quest_comms_message(
            session_id=session_id,
            sender_npc_id=client,
            msg_type="stage2_client_intel",
            quest_title=quest.get("title", "Quest"),
            target_npc=tgt_npc,
            target_loc=tgt_loc,
            scen_key=scen,
        )


# -----------------------------------------------------------------------------
# Phase 2 Multi-Approach Resolution & Failure Consequence Handlers
# -----------------------------------------------------------------------------

def apply_quest_approach_effects(
    session_id: int,
    quest: dict,
    waypoint: dict,
    approach: str,
    gold_cost: int,
    party_user_ids: list[int],
    sub_obj: dict = None,
    session: dict = None,
) -> dict:
    """
    Applies approach-specific deterministic side-effects (Buyout/Bribe gold deduction,
    Spare/Fake-Death contact & lorebook updates, or Counter-Offer Betrayal).
    Returns dict with optional 'directive', 'terminated_by_betrayal', etc.
    """
    import db
    from mechanics.narrative.blueprints import calculate_quest_buyout_cost
    app = (approach or "").lower()
    qid = quest.get("quest_id", "")
    lead_uid = party_user_ids[0] if party_user_ids else 1

    # 1. Gold Buyout / Bribery
    if app == "buyout_bribe" or "[buyout / bribe" in str(waypoint.get("stage_label", "")).lower():
        cost = gold_cost if gold_cost > 0 else calculate_quest_buyout_cost(quest)
        db.apply_hp_mp_delta(lead_uid, gold_delta=-cost)
        db.set_quest_resolution_approach(session_id, qid, "bought_or_bribed")
        stage_desc = waypoint.get("stage_label") or "objective"
        return {
            "directive": f"[MANDATORY QUEST BUYOUT RESOLUTION]: The player paid {cost} Gold to resolve stage '{stage_desc}' of '{quest.get('title')}' via buyout/bribery without risk."
        }

    # 2. Spare & Fake Death
    elif app == "spare_deceive" or "[spare & fake death]" in str(waypoint.get("stage_label", "")).lower():
        db.set_quest_resolution_approach(session_id, qid, "spared_deception")
        target_npc = waypoint.get("target_npc") or quest.get("target_npc") or ""
        if target_npc:
            try:
                db.upsert_lorebook_entity(session_id=session_id, entity_type="person", name=target_npc, status="disappeared")
            except Exception:
                pass
            try:
                db.update_relationship_score(session_id, target_npc, delta_score=15)
            except Exception:
                pass
        target_disp = target_npc or "the target"
        return {
            "directive": f"[MANDATORY SPARE & DECEIVE RESOLUTION]: The player spared {target_disp}, convinced them to vanish into hiding, and secured staged proof of elimination for '{quest.get('title')}'!"
        }

    # 3. Accept Counter-Offer / Betray Client
    elif app == "counter_offer" or "[accept counter-offer]" in str(waypoint.get("stage_label", "")).lower():
        betrayal_gold = int(round(int(quest.get("reward_gold") or 30) * 1.5))
        for uid in (party_user_ids or [lead_uid]):
            db.apply_hp_mp_delta(uid, gold_delta=betrayal_gold)
        target_npc = waypoint.get("target_npc") or quest.get("target_npc") or ""
        if target_npc:
            try:
                db.update_relationship_score(session_id, target_npc, delta_score=15)
            except Exception:
                pass
        # Phase 4 Rival Faction Ripple (+5 rep with rival factions when betraying sponsoring faction):
        q_notes = str(quest.get("quest_notes") or "")
        riv_ids = []
        for rm in re.finditer(r'rival_faction:\s*([A-Za-z0-9_-]+)', q_notes, re.IGNORECASE):
            r_val = rm.group(1).strip()
            if r_val and r_val not in riv_ids:
                riv_ids.append(r_val)
        fac_match = re.search(r'(?:^|\||\n)\s*faction:\s*([A-Za-z0-9_-]+)', q_notes, re.IGNORECASE)
        sponsor_fac_id = fac_match.group(1).strip() if fac_match else ""
        if sponsor_fac_id:
            try:
                s_fac = db.get_faction(session_id, sponsor_fac_id)
                if s_fac and s_fac.get("rival_faction_ids"):
                    for r in s_fac["rival_faction_ids"]:
                        if r and str(r).strip() not in riv_ids:
                            riv_ids.append(str(r).strip())
            except Exception:
                pass
        for rid in riv_ids:
            if rid and rid != sponsor_fac_id:
                try:
                    db.upsert_faction(session_id, rid, delta_score=5, notes=f"Betrayed rival operation '{quest.get('title')}'")
                except Exception:
                    pass
        apply_quest_failure_consequences(session_id, quest, party_user_ids, reason="betrayed_client", session=session)
        client_disp = quest.get("client_npc") or "the client"
        return {
            "terminated_by_betrayal": True,
            "betrayal_gold": betrayal_gold,
            "directive": f"[MANDATORY TARGET COUNTER-OFFER ACCEPTED]: The player betrayed {client_disp} and allied with {target_npc or 'the target'} for {betrayal_gold} Gold! The contract is voided and {client_disp} is enraged."
        }

    # 4. Companion Assist
    elif app == "companion_assist" or "[companion assist" in str(waypoint.get("stage_label", "")).lower():
        from mechanics.world.waypoints.choices import get_active_companion_for_waypoint
        active_comp = get_active_companion_for_waypoint(session_id, waypoint)
        if not active_comp:
            all_comps = list(db.get_session_party_npcs(session_id) or []) + list(db.get_temporary_companions(session_id) or [])
            active_comp = all_comps[0] if all_comps else None
        comp_name = (active_comp.get("name") if isinstance(active_comp, dict) else None) or "Companion"
        try:
            db.update_relationship_score(session_id, comp_name, delta_score=3)
        except Exception:
            pass
        return {
            "handled": True,
            "companion_assisted": True,
            "companion_name": comp_name,
            "directive": f"[MANDATORY COMPANION ASSIST]: {comp_name} actively assisted with their specialized expertise to resolve this stage smoothly (+3 Affinity with {comp_name})!",
        }

    # 5. Breakthrough Leverage
    elif app == "breakthrough_leverage" or "[breakthrough leverage]" in str(waypoint.get("stage_label", "")).lower():
        db.set_quest_resolution_approach(session_id, qid, "breakthrough_leverage")
        target_npc = waypoint.get("target_npc") or quest.get("target_npc") or "the target"
        return {
            "handled": True,
            "breakthrough_leveraged": True,
            "directive": f"[MANDATORY BREAKTHROUGH LEVERAGE]: The player confronted {target_npc} with undeniable deductions synthesized from the caseboard, shattering their resistance!",
        }

    # 6. Anomalous Incursions: Out-of-Combat Non-Hostile Entity Containment
    try:
        import scenario_data
        sess_chk = session if isinstance(session, dict) else (db.get_session(session_id) or {})
        scen_chk = str(sess_chk.get("scenario") or "fantasy")
        if scenario_data.is_anomalous_incursions_scenario(scen_chk):
            from mechanics.world.anomalous_events import (
                is_non_hostile_entity_containment_waypoint,
                extract_non_hostile_entity_name,
                record_contained_anomaly_to_vault_log,
            )
            so_id_val = waypoint.get("sub_obj_id") if isinstance(waypoint, dict) and waypoint.get("sub_obj_id") is not None else (sub_obj.get("id") if isinstance(sub_obj, dict) else None)
            all_wps_chk = db.get_quest_waypoints(session_id, qid, so_id_val) or []
            if app in ("nh_persuade", "nh_calm", "nh_outwit", "nh_environment") or is_non_hostile_entity_containment_waypoint(waypoint, all_wps=all_wps_chk, sub_obj=sub_obj, quest=quest):
                from db.quests import append_quest_note_flag_in_db
                ent_nm = extract_non_hostile_entity_name(quest, sub_obj)
                method_map = {
                    "nh_persuade": "Persuaded & Contained Willingly",
                    "nh_calm": "Calmed & Sealed Non-Lethally",
                    "nh_outwit": "Outwitted into Containment Snare",
                    "nh_environment": "Cornered via Environmental Containment",
                }
                method_str = method_map.get(app, "Narrative Field Containment")
                loc_str = str(sess_chk.get("current_location") or quest.get("client_location") or "Metropolitan Grid")
                vault_entry = record_contained_anomaly_to_vault_log(
                    session_id=session_id,
                    entity_name=ent_nm,
                    category_tag="spatial_warp",
                    subtype="non_hostile_entity",
                    location=loc_str,
                    containment_note=f"Contained alive during '{quest.get('title', 'Containment Operation')}'.",
                    resolution_method=method_str,
                    user_id=lead_uid,
                    quest_id=qid,
                    sub_obj_id=so_id_val,
                )
                secured_key = f"entity_secured_so_{so_id_val}" if so_id_val is not None else "entity_secured"
                append_quest_note_flag_in_db(session_id, qid, secured_key, "1")
                append_quest_note_flag_in_db(session_id, qid, "vault_logged", "1")
                db.set_quest_resolution_approach(session_id, qid, app if app.startswith("nh_") else "non_hostile_contained")
                return {
                    "handled": True,
                    "entity_contained": True,
                    "vault_entry": vault_entry,
                    "directive": (
                        f"[MANDATORY NON-HOSTILE CONTAINMENT SUCCESS]: The player successfully contained '{ent_nm}' alive "
                        f"via {method_str} without combat! Narrate sealing it safely into a portable containment unit "
                        f"(logged for {vault_entry['vault_facility']})."
                    ),
                }
    except Exception:
        pass

    return {}


def apply_quest_failure_consequences(
    session_id: int,
    quest: dict,
    party_user_ids: list[int],
    reason: str = "failed_strikes",
    session: dict = None,
) -> dict:
    """
    Applies hard failure to side/faction bounties, including client affinity drop,
    sponsoring faction reputation penalty, and queuing a Delayed Travel Ambush or PeerPulse scandal.
    """
    import db
    import time
    qid = quest.get("quest_id", "")
    client_npc = quest.get("client_npc") or ""
    lead_uid = party_user_ids[0] if party_user_ids else 1
    if reason == "betrayed_client":
        progress_note = "Failed (Betrayed Client)"
    elif reason == "entity_escaped":
        progress_note = "Failed (Non-Hostile Target Escaped)"
    elif reason == "killed_non_hostile_target":
        progress_note = "Failed (Non-Hostile Target Killed)"
    else:
        progress_note = "Failed (Target Alerted / Escaped)"
    db.fail_quest_and_waypoints(session_id, qid, resolution_approach=reason, progress_note=progress_note)

    # Client Affinity fallout
    if client_npc:
        client_delta = -15 if reason == "betrayed_client" else -10
        try:
            db.update_relationship_score(session_id, client_npc, delta_score=client_delta)
        except Exception:
            pass

    # Sponsoring Faction Reputation fallout
    q_notes = str(quest.get("quest_notes") or "")
    fac_match = re.search(r'faction:\s*(?:faction:)?([A-Za-z0-9_-]+)', q_notes, re.IGNORECASE)
    fac_id = fac_match.group(1) if fac_match else ""
    if fac_id:
        fac_norm = fac_id.lower()
        fac_spaced = fac_norm.replace("_", " ")
        try:
            with db.get_conn() as conn:
                conn.execute(
                    """UPDATE factions 
                       SET reputation_score = MAX(-100, MIN(100, reputation_score - 15)), updated_at=? 
                       WHERE session_id=? AND (faction_id=? OR faction_id=? OR lower(name)=? OR lower(name)=?)""",
                    (time.time(), session_id, fac_norm, fac_spaced, fac_norm, fac_spaced)
                )
        except Exception:
            pass

    sess_eff = session if isinstance(session, dict) else (db.get_session(session_id) or {})
    scen = str(sess_eff.get("scenario") or "fantasy")

    # Anomalous Incursions Mandatory Daily Bounty failure penalty (-15 Promotion Rep, guarded against midnight double-penalty)
    promotion_penalty_notice = ""
    try:
        import scenario_data
        if scenario_data.is_anomalous_incursions_scenario(scen) and (
            "mandatory_daily:1" in q_notes or str(qid).upper().startswith("MAND-")
        ):
            from mechanics.social.factions import (
                get_anomalous_faction_state,
                save_anomalous_faction_state,
                update_agent_promotion_reputation,
            )
            fac_st = get_anomalous_faction_state(session_id, user_id=lead_uid)
            if str(fac_st.get("faction_archetype_key") or "public_agency") != "freelancer" and not fac_st.get("mandatory_bounty_penalized_today", False):
                promo_res = update_agent_promotion_reputation(
                    session_id=session_id,
                    delta_rep=-15,
                    reason=f"Failed Mandatory Daily Dispatch '{quest.get('title', 'Mandatory Bounty')}'",
                    is_missed_mandatory=True,
                    user_id=lead_uid,
                )
                fac_st = promo_res.get("state") or get_anomalous_faction_state(session_id, user_id=lead_uid)
                fac_st["mandatory_bounty_penalized_today"] = True
                save_anomalous_faction_state(session_id, fac_st, user_id=lead_uid)
                promotion_penalty_notice = str(promo_res.get("message") or "")
    except Exception:
        pass

    # Delayed Travel Ambush for combat/criminal blueprints (skip for non-hostile anomaly escape/kill)
    bp = quest.get("blueprint_id") or ""
    if reason not in ("entity_escaped", "killed_non_hostile_target") and bp in ("NEUTRALIZATION", "HEIST_INFILTRATION", "CONTEST_RIVALRY", "EXPLORATION_HAZARD", ""):
        cur_loc = (sess_eff.get("current_location") if sess_eff else "") or ""
        enemy_name = f"{client_npc}'s Enforcer" if (reason == "betrayed_client" and client_npc) else (quest.get("target_npc") or "Vengeful Mercenary")
        retaliation_data = {
            "quest_id": qid,
            "quest_title": quest.get("title", "Bounty"),
            "reason": reason,
            "origin_location": cur_loc,
            "enemy_name": enemy_name,
            "enemy_role": "Mercenary / Bounty Hunter",
        }
        if session is not None:
            session["pending_retaliation"] = retaliation_data
        try:
            db.update_session(session_id, extra={"pending_retaliation": retaliation_data})
        except Exception:
            pass

    # PeerPulse Scandal for Social or School scenarios
    try:
        from mechanics.world.locations.seeds import is_school_scenario
        is_school = is_school_scenario(scen)
    except Exception:
        is_school = False
    if bp == "SOCIAL_MANIPULATION" or is_school:
        try:
            scandal_post = {
                "author_name": "Campus Gossip",
                "author_handle": "@CampusSpill",
                "content": f"Word on the street is someone completely botched their promise on '{quest.get('title')}'... embarrassing!",
                "tag": "#Scandal",
                "clue_hook": quest.get("title", ""),
                "time_ago": "Just now",
            }
            db.save_gossip_feed(session_id, [scandal_post])
        except Exception:
            pass

    promo_dir = f" {promotion_penalty_notice}" if promotion_penalty_notice else ""
    res_payload = {
        "failed": True,
        "reason": reason,
        "directive": f"[MANDATORY QUEST FAILURE & FALLOUT]: Quest '{quest.get('title')}' has FAILED ({reason}).{promo_dir} Narrate the consequences and strained relations vividly.",
    }
    if promotion_penalty_notice:
        res_payload["promotion_penalty_notice"] = promotion_penalty_notice
    return res_payload


def handle_failed_quest_skill_check(
    session_id: int,
    quest: dict,
    waypoint: dict,
    check_result_tier: str,
    party_user_ids: list[int],
    sub_obj: dict = None,
    session: dict = None,
) -> dict | None:
    """
    Handles a failed skill check on an active quest waypoint:
    - Stage 1 Immunity: Scouting checks never add strikes.
    - Stage >= 2: Adds +1 Strike (or +2 on Stage 3 critical failure).
    - At 1/2 Strikes: Emits complication directive.
    - At 2/2 Strikes: Deterministic Hard Failure for bounties, or Pyrrhic Breakthrough ('dire_cost') for Story Quests
      (or Temperament-Driven Escape vs Agitated Hostile Combat for Non-Hostile Anomalous Entities).
    """
    import db
    import time
    qid = quest.get("quest_id", "")
    sub_obj_id = waypoint.get("sub_obj_id")
    stage_idx = int(waypoint.get("stage_index", 1) or 1)

    all_wps = db.get_quest_waypoints(session_id, qid, sub_obj_id) or []
    if stage_idx <= 1 and len(all_wps) > 1:
        return None

    # Phase 4 Companion Strike Shield Check:
    # If the player has an active companion (party or temporary hangout) and hasn't used the shield yet for this quest
    from mechanics.narrative.blueprints import has_quest_note_flag
    from mechanics.world.waypoints.choices import get_active_companion_for_waypoint
    q_fresh = db.get_quest_by_id(session_id, qid) or quest
    q_notes = str(q_fresh.get("quest_notes") or quest.get("quest_notes") or "")
    active_comp = get_active_companion_for_waypoint(session_id, waypoint)
    if active_comp and not has_quest_note_flag(q_notes, "companion_shield_used"):
        from db.quests import append_quest_note_flag_in_db
        append_quest_note_flag_in_db(session_id, qid, "companion_shield_used", "1")
        comp_name = active_comp.get("name") or "Your companion"
        return {
            "status": "companion_shield_absorbed",
            "shield_absorbed": True,
            "failed": False,
            "companion_name": comp_name,
            "strikes": int(q_fresh.get("strike_count") or 0),
            "max_strikes": 2,
            "directive": f"[COMPANION STRIKE SHIELD ACTIVATED]: {comp_name} intervened to parry/deflect the complication! Strike count was NOT incremented (0 strikes accrued).",
        }

    # Anomalous Incursions Non-Hostile Entity Containment Branching (Timid Escape vs Volatile Hostile Combat)
    sess_eff = session if isinstance(session, dict) else (db.get_session(session_id) or {})
    scen_chk = str(sess_eff.get("scenario") or "fantasy")
    try:
        import scenario_data
        is_anom_scen = scenario_data.is_anomalous_incursions_scenario(scen_chk)
    except Exception:
        is_anom_scen = False

    if is_anom_scen:
        from mechanics.world.anomalous_events import (
            is_non_hostile_entity_containment_waypoint,
            extract_non_hostile_entity_name,
            get_non_hostile_entity_temperament,
            spawn_agitated_non_hostile_entity,
        )
        if is_non_hostile_entity_containment_waypoint(waypoint, all_wps=all_wps, sub_obj=sub_obj, quest=q_fresh):
            ent_nm = extract_non_hostile_entity_name(q_fresh, sub_obj)
            temp = get_non_hostile_entity_temperament(seed_key=qid, quest_notes=q_notes)
            strike_res = db.increment_quest_strikes(session_id, qid, delta=1)

            if not strike_res["failed"]:
                if temp == "timid":
                    warn_dir = (
                        f"[NON-HOSTILE CONTAINMENT COMPLICATION - {strike_res['strikes']}/{strike_res['max_strikes']} STRIKES]: "
                        f"The containment attempt on '{ent_nm}' faltered! Startled and skittish, it edges toward an unstable spatial seam—"
                        f"one more failed skill check and '{ent_nm}' will escape!"
                    )
                else:
                    warn_dir = (
                        f"[NON-HOSTILE CONTAINMENT COMPLICATION - {strike_res['strikes']}/{strike_res['max_strikes']} STRIKES]: "
                        f"The containment attempt on '{ent_nm}' faltered! Its territorial static arcs dangerously—"
                        f"one more failed skill check and '{ent_nm}' will turn hostile in combat!"
                    )
                return {
                    "status": "strike_warning",
                    "temperament": temp,
                    "strikes": strike_res["strikes"],
                    "max_strikes": strike_res["max_strikes"],
                    "failed": False,
                    "directive": warn_dir,
                }

            # Max strikes reached (2/2) -> Branch by temperament!
            if temp == "timid":
                if not q_fresh.get("is_story_quest"):
                    fail_res = apply_quest_failure_consequences(
                        session_id, q_fresh, party_user_ids, reason="entity_escaped", session=sess_eff
                    )
                    fail_res["escaped"] = True
                    fail_res["temperament"] = "timid"
                    fail_res["strikes"] = strike_res["strikes"]
                    fail_res["max_strikes"] = strike_res["max_strikes"]
                    promo_part = f" {fail_res['promotion_penalty_notice']}" if fail_res.get("promotion_penalty_notice") else ""
                    fail_res["directive"] = (
                        f"[NON-HOSTILE ENTITY ESCAPED — BOUNTY FAILED]: Startled by repeated failed containment attempts, "
                        f"'{ent_nm}' slipped through a spatial seam and vanished! Quest '{q_fresh.get('title')}' has FAILED.{promo_part}"
                    )
                    return fail_res
                else:
                    now = time.time()
                    with db.get_conn() as conn:
                        if sub_obj_id is not None:
                            conn.execute(
                                "UPDATE quest_waypoints SET status='completed', updated_at=? WHERE session_id=? AND quest_id=? AND sub_obj_id=?",
                                (now, session_id, qid, sub_obj_id),
                            )
                        else:
                            conn.execute(
                                "UPDATE quest_waypoints SET status='completed', updated_at=? WHERE session_id=? AND quest_id=?",
                                (now, session_id, qid),
                            )
                    if sub_obj:
                        sub_obj["completed"] = True
                        sub_obj["resolution_approach"] = "dire_cost"
                    db.set_quest_resolution_approach(session_id, qid, "dire_cost")
                    db.reset_quest_strikes(session_id, qid)
                    lead_uid = party_user_ids[0] if party_user_ids else 1
                    db.apply_hp_mp_delta(lead_uid, hp_delta=-5)
                    return {
                        "status": "dire_cost",
                        "escaped": True,
                        "temperament": "timid",
                        "failed": False,
                        "directive": (
                            f"[MANDATORY DIRE COST — SPECIMEN ESCAPED]: '{ent_nm}' bolted through a spatial tear in a burst of "
                            f"anomalous static (-5 HP backlash), escaping live capture! The player salvages only residual telemetry "
                            f"to press '{q_fresh.get('title')}' forward (NOT logged to Containment Vault)."
                        ),
                    }
            else:
                # Volatile temperament -> Spawns into combat WITHOUT failing the quest yet!
                db.reset_quest_strikes(session_id, qid)
                cur_loc_str = str(sess_eff.get("current_location") or waypoint.get("target_location") or "")
                enemy_obj = spawn_agitated_non_hostile_entity(
                    session_id=session_id,
                    entity_name=ent_nm,
                    location=cur_loc_str,
                    quest_id=qid,
                    sub_obj_id=sub_obj_id,
                    is_story_quest=bool(q_fresh.get("is_story_quest")),
                    session=session,
                )
                return {
                    "status": "agitated_combat",
                    "agitated": True,
                    "combat_started": True,
                    "temperament": "volatile",
                    "failed": False,
                    "strikes": strike_res["strikes"],
                    "max_strikes": strike_res["max_strikes"],
                    "enemy": enemy_obj,
                    "directive": (
                        f"[NON-HOSTILE ENTITY AGITATED INTO COMBAT]: Repeated failed containment attempts provoked '{ent_nm}' "
                        f"into lashing out! Combat has begun, but '{q_fresh.get('title')}' is NOT failed yet—the player can still "
                        f"attempt [🗣️ Persuade / Calm] in combat or weaken it to <= 35% HP for [🛡️ Subdue & Contain], "
                        f"whereas killing it (0 HP) will destroy the specimen and fail the bounty!"
                    ),
                }

    delta = 2 if (check_result_tier == "critical_failure" and stage_idx >= 3) else 1
    strike_res = db.increment_quest_strikes(session_id, qid, delta=delta)

    if not strike_res["failed"]:
        return {
            "status": "strike_warning",
            "strikes": strike_res["strikes"],
            "max_strikes": strike_res["max_strikes"],
            "failed": False,
            "directive": f"[QUEST COMPLICATION - {strike_res['strikes']}/{strike_res['max_strikes']} STRIKES]: The player failed a check on '{quest.get('title')}'. The opposition is now on high alert! One more failure will botch the contract."
        }

    # strikes >= max_strikes
    if not quest.get("is_story_quest"):
        fail_res = apply_quest_failure_consequences(session_id, quest, party_user_ids, reason="failed_strikes", session=session)
        fail_res["strikes"] = strike_res["strikes"]
        fail_res["max_strikes"] = strike_res["max_strikes"]
        return fail_res
    else:
        # Story Quest Fail-Forward: Pyrrhic Breakthrough ('dire_cost')
        now = time.time()
        with db.get_conn() as conn:
            conn.execute(
                "UPDATE quest_waypoints SET status='completed', updated_at=? WHERE session_id=? AND quest_id=? AND sub_obj_id=?",
                (now, session_id, qid, sub_obj_id)
            )
        if sub_obj:
            sub_obj["completed"] = True
            sub_obj["resolution_approach"] = "dire_cost"
        db.reset_quest_strikes(session_id, qid)
        lead_uid = party_user_ids[0] if party_user_ids else 1
        db.apply_hp_mp_delta(lead_uid, hp_delta=-5)
        return {
            "status": "dire_cost",
            "failed": False,
            "directive": f"[MANDATORY PYRRHIC BREAKTHROUGH / DIRE COST]: The sub-objective for '{quest.get('title')}' was forced through at a dire cost! Narrate the narrow escape and the physical/social toll."
        }


def trigger_pending_retaliation_if_eligible(
    session_id: int,
    current_location: str,
    session: dict = None,
) -> dict | None:
    """
    Checks if a pending retaliation ambush is scheduled and the player has traveled
    to a non-safe location away from the origin location.
    """
    if not session or not current_location:
        return None
    retaliation = session.get("pending_retaliation")
    if not retaliation or not isinstance(retaliation, dict):
        return None
    origin = retaliation.get("origin_location", "")
    if origin and current_location.strip().lower() == origin.strip().lower():
        return None
    safe_words = ("bedroom", "dorm", "quarters", "apartment", "sanctuary", "infirmary", "inn room")
    if any(sw in current_location.lower() for sw in safe_words):
        return None

    import db
    enemy_name = retaliation.get("enemy_name") or "Vengeful Mercenary"
    ambush_enemy = {
        "name": enemy_name,
        "enemy_name": enemy_name,
        "hp": 35,
        "max_hp": 35,
        "attack": 8,
        "defense": 4,
        "role": retaliation.get("enemy_role") or "Ambush Mercenary",
        "description": f"A hostile tracker sent in retaliation for the contract '{retaliation.get('quest_title')}'.",
        "is_retaliation_ambush": True,
    }
    nearby = list(session.get("nearby_enemies") or [])
    nearby.append(ambush_enemy)
    session["nearby_enemies"] = nearby
    session["pending_retaliation"] = None
    try:
        db.update_session(session_id, nearby_enemies=nearby, extra={"pending_retaliation": None})
    except Exception:
        pass

    return {
        "enemy_name": enemy_name,
        "quest_title": retaliation.get("quest_title", ""),
        "directive": f"[MANDATORY RETALIATION AMBUSH]: {enemy_name} ambushes the player at {current_location} in retaliation for '{retaliation.get('quest_title')}'! Narrate the surprise attack vividly."
    }


def is_quest_in_turn_in_grace_period(session_id: int, quest: dict | str) -> bool:
    """
    Returns True if the quest has reached its final Client Turn-In stage (Stage >= 3 or final stage
    targeting the client / delivery), freezing the deadline timer so it can never expire while turning in.
    """
    import db
    if isinstance(quest, str):
        qid = quest
        quest = db.get_quest_by_id(session_id, qid) or {}
    else:
        qid = (quest or {}).get("quest_id", "")
    all_wps = db.get_quest_waypoints(session_id, qid, None) or []
    active_wp = db.get_active_waypoint(session_id, qid, None)
    if not active_wp or len(all_wps) < 2:
        return False
    max_stage = max(int(w.get("stage_index", 1)) for w in all_wps)
    curr_stage = int(active_wp.get("stage_index", 1))
    if curr_stage < max_stage:
        return False
    lbl_low = str(active_wp.get("stage_label") or "").lower()
    client_npc = str(quest.get("client_npc") or "").strip().lower()
    wp_npc = str(active_wp.get("target_npc") or "").strip().lower()
    if client_npc and wp_npc == client_npc:
        return True
    if any(w in lbl_low for w in ("turn in", "deliver", "report", "hand over", "return to", "claim", "confirm")):
        return True
    if curr_stage >= 3:
        return True
    return False


def check_and_expire_overdue_quests(
    session_id: int,
    party_user_ids: list[int] = None,
    session: dict = None,
) -> dict:
    """
    Sweeps active non-story quests for expired deadlines.
    - Respects the Stage 3 Client Turn-In Grace Rule (never expires on the turn-in stage).
    - Applies Rival Claim / Expired Contract mild fallout (-5 client affinity, -5 faction rep, no ambush).
    - Tags quests within 24 hours of deadline with '[⏰ <24h Left]'.
    """
    import db
    import time
    if not session_id:
        return {"expired_quests": [], "directives": []}

    curr_day, curr_min, _ = db.get_session_time(session_id)
    active_quests = db.get_session_quests(session_id, status="Active") or []
    expired_quests = []
    directives = []

    for q in active_quests:
        if q.get("is_story_quest"):
            continue
        d_day = q.get("deadline_day")
        if d_day is None:
            continue
        d_day = int(d_day)
        d_min = int(q.get("deadline_minute") if q.get("deadline_minute") is not None else 1200)
        qid = q.get("quest_id", "")

        # Stage 3 Client Turn-In Grace Rule
        if is_quest_in_turn_in_grace_period(session_id, q):
            continue

        is_expired = (curr_day > d_day) or (curr_day == d_day and curr_min >= d_min)
        if is_expired:
            db.expire_quest_and_waypoints(session_id, qid)
            client_npc = q.get("client_npc") or ""
            if client_npc:
                try:
                    db.update_relationship_score(session_id, client_npc, delta_score=-5)
                except Exception:
                    pass
            q_notes = str(q.get("quest_notes") or "")
            fac_match = re.search(r'faction:\s*(?:faction:)?([A-Za-z0-9_\-\s]+?)(?:\||,|$|\n)', q_notes, re.IGNORECASE)
            fac_id = fac_match.group(1).strip() if fac_match else ""
            if not fac_id:
                fac_id = str(q.get("target_faction") or "").strip()
            if fac_id:
                fac_norm = fac_id.lower().replace(" ", "_")
                fac_spaced = fac_id.lower().replace("_", " ")
                try:
                    with db.get_conn() as conn:
                        conn.execute(
                            """UPDATE factions
                               SET reputation_score = MAX(-100, MIN(100, reputation_score - 5)), updated_at=?
                               WHERE session_id=? AND (faction_id=? OR faction_id=? OR lower(name)=? OR lower(name)=?)""",
                            (time.time(), session_id, fac_norm, fac_spaced, fac_norm, fac_spaced)
                        )
                except Exception:
                    pass
            expired_quests.append(qid)
            directives.append(
                f"[QUEST CONTRACT EXPIRED]: The deadline for '{q.get('title')}' has expired! A rival mercenary company claimed the target. Mild standing penalty applied (-5 affinity/reputation)."
            )
        else:
            # Check if within 24 hours (1440 mins)
            mins_remaining = (d_day - curr_day) * 1440 + (d_min - curr_min)
            if 0 < mins_remaining <= 1440:
                prog = str(q.get("progress") or "")
                if "[⏰ <24h Left]" not in prog:
                    new_prog = f"{prog} [⏰ <24h Left]".strip()
                    with db.get_conn() as conn:
                        conn.execute(
                            "UPDATE quests SET progress=?, updated_at=? WHERE session_id=? AND quest_id=?",
                            (new_prog, time.time(), session_id, qid)
                        )
                # Phase 4 Comms: Send 24h deadline reminder warning DM
                from mechanics.narrative.blueprints import has_quest_note_flag
                from db.quests import append_quest_note_flag_in_db
                q_notes = str(q.get("quest_notes") or "")
                if not has_quest_note_flag(q_notes, "deadline_dm_sent"):
                    append_quest_note_flag_in_db(session_id, qid, "deadline_dm_sent", "1")
                    sender = q.get("client_npc") or "Guild Registry"
                    scen = (session.get("scenario") if session else "") or "fantasy"
                    dm_dir = send_quest_comms_message(
                        session_id=session_id,
                        sender_npc_id=sender,
                        msg_type="deadline_24h_warning",
                        quest_title=q.get("title", "Bounty"),
                        scen_key=scen,
                    )
                    if dm_dir:
                        directives.append(dm_dir)

    return {
        "expired_quests": expired_quests,
        "expired_quest_ids": expired_quests,
        "directives": directives,
    }


def resolve_pre_turn_quests_and_clues(
    session: dict,
    party: list = None,
    actions: list = None,
    persist_db: bool = True,
) -> dict:
    """
    Deterministic pre-turn quest, clue, and chapter climax resolution engine.
    When persist_db=False (live turn pipeline), executes inside a rolled-back SQLite SAVEPOINT
    so LLM failures never mutate DB state, and commits atomically inside apply_outcome (D3).
    """
    import db
    session_id = (session.get("id") or 0) if isinstance(session, dict) else 0
    if not persist_db and session_id:
        pre_ch = session.get("chapter", 1) if isinstance(session, dict) else 1
        eff_loc = session.get("current_location") or ""
        with db.UnitOfWork() as uow_conn:
            uow_conn.execute("SAVEPOINT sp_pre_turn_quests")
            try:
                res = _resolve_pre_turn_quests_impl(session, party=party, actions=actions)
            finally:
                uow_conn.execute("ROLLBACK TO SAVEPOINT sp_pre_turn_quests")
                uow_conn.execute("RELEASE SAVEPOINT sp_pre_turn_quests")
        res["_needs_db_commit"] = True
        res["_pre_chapter"] = pre_ch
        res["_effective_location"] = eff_loc
        res["_party_snapshot"] = party
        if isinstance(session, dict):
            session["_pre_turn_quest_res"] = res
        return res
    return _resolve_pre_turn_quests_impl(session, party=party, actions=actions)


def _resolve_pre_turn_quests_impl(
    session: dict,
    party: list = None,
    actions: list = None,
) -> dict:
    import db
    from mechanics.world.waypoints import (
        try_advance_on_arrival,
        try_complete_on_skill_check,
        does_action_target_waypoint,
        get_story_quest_climax_location,
    )
    from mechanics.narrative.blueprints import classify_choice_approach
    from skill_check import is_check_success

    session_id = session.get("id") or 0
    cur_loc = session.get("current_location") or ""

    action_str = ""
    is_success = False
    fa = {}
    if actions:
        # D15 Multiplayer Co-op: prefer any action explicitly targeting a quest, climax, or clue deduction
        selected_raw = actions[0]
        for cand_a in actions:
            if isinstance(cand_a, dict) and (
                cand_a.get("is_quest_action")
                or cand_a.get("quest_id")
                or cand_a.get("is_climax_action")
                or str(cand_a.get("sub_intent") or "").lower() == "deduce_clues"
                or "story climax" in str(cand_a.get("label") or cand_a.get("action") or "").lower()
                or "⚡" in str(cand_a.get("label") or "")
            ):
                selected_raw = cand_a
                break
        fa = selected_raw if isinstance(selected_raw, dict) else {}
        if isinstance(selected_raw, dict):
            action_str = str(fa.get("label") or fa.get("action") or "")
            is_success = is_check_success(fa.get("check"), default_if_none=True)
        else:
            action_str = str(selected_raw or "")
            is_success = True
    act_low = action_str.lower()

    check_obj = fa.get("check") if isinstance(fa, dict) else None
    raw_tier = getattr(check_obj, "result_tier", None) or getattr(check_obj, "tier", None) if check_obj else None
    if raw_tier is None and isinstance(check_obj, dict):
        raw_tier = check_obj.get("result_tier") or check_obj.get("tier")
    check_tier = str(raw_tier or ("success" if is_success else "failure")).lower()
    is_quest_action = bool(fa.get("is_quest_action"))
    action_quest_id = str(fa.get("quest_id") or "")
    action_sub_obj_id = fa.get("sub_obj_id")
    act_approach = str(fa.get("approach") or classify_choice_approach(action_str))
    act_gold_cost = int(fa.get("gold_cost") or 0)
    act_wait_minutes = int(fa.get("wait_minutes") or 0)

    party_list = party or []
    party_uids = [
        (c[0]["user_id"] if isinstance(c, (tuple, list)) else c["user_id"])
        for c in party_list if isinstance(c, dict) or (isinstance(c, (tuple, list)) and isinstance(c[0], dict))
    ]
    if not party_uids and session.get("host_user_id"):
        party_uids = [session["host_user_id"]]
    if not party_uids and session.get("user_id"):
        party_uids = [session["user_id"]]
    if not party_uids:
        party_uids = [1]

    # Pre-turn evaluate quest state predicates (inventory pre-completion, etc.)
    if session_id:
        evaluate_quest_state_predicates(session_id=session_id, user_id=party_uids[0] if party_uids else None)

    directives = []

    # Fast-forward time if wait action selected
    if act_approach in ("wait_for_window", "wait_until_morning") and act_wait_minutes > 0 and session_id:
        try:
            from mechanics.system.time_engine import advance_time, format_clock, get_time_of_day_phase
            time_adv = advance_time(session_id, delta_minutes=act_wait_minutes, party_uids=party_uids)
            new_day = time_adv.get("new_day", 1)
            new_min = time_adv.get("new_minute", 480)
            if isinstance(session, dict):
                session["current_day"] = new_day
                session["current_minute"] = new_min
            clock_str = format_clock(new_min)
            phase_name, emoji, _ = get_time_of_day_phase(new_min)
            directives.append(f"⏳ Time passed: waited {act_wait_minutes} minutes ({clock_str}, {phase_name} {emoji}).")
        except Exception as e:
            logger.warning("Failed to advance time for wait action: %s", e)

    # Check and expire overdue quests (grace period protected)
    if session_id:
        exp_res = check_and_expire_overdue_quests(session_id, party_user_ids=party_uids, session=session)
        if exp_res.get("directives"):
            directives.extend(exp_res["directives"])

    # Check for pending travel retaliation ambush
    retaliation_res = trigger_pending_retaliation_if_eligible(session_id, cur_loc, session=session)
    if retaliation_res and retaliation_res.get("directive"):
        directives.append(retaliation_res["directive"])

    active_quests = db.get_session_quests(session_id, status="Active") if session_id else []
    completed_quests = []
    advanced_stages = []
    advanced_keys = []
    waypoint_notices = []
    completed_sub_quests = []

    resolves_so_id = None
    if actions and isinstance(actions[0], dict):
        resolves_so_id = actions[0].get("resolves_sub_obj_id")

    for q in active_quests:
        qid = q.get("quest_id")
        if not qid:
            continue
        dm_dir = trigger_stage2_midquest_comms_if_eligible(session_id, q, session=session)
        if dm_dir:
            directives.append(dm_dir)

        # 1. Check top-level quest waypoints (bounties / single-track quests)
        active_wp = db.get_active_waypoint(session_id, qid, None)
        if active_wp:
            trig = active_wp.get("completion_trigger") or "arrival"
            if trig == "arrival":
                if act_approach in ("wait_for_window", "wait_until_morning"):
                    continue
                res_adv = try_advance_on_arrival(session_id, qid, None, cur_loc)
                if res_adv:
                    advanced_stages.append({"quest_id": qid, "res": res_adv})
                    advanced_keys.append((qid, None))
                    waypoint_notices.append(res_adv)
                    if not res_adv.get("all_stages_complete"):
                        grant_stage_acquisition_item_if_needed(
                            session_id=session_id,
                            quest=q,
                            completed_stage_index=res_adv.get("completed_stage_index", 1),
                            total_stages=res_adv.get("total_stages", 2),
                            party_user_ids=party_uids,
                        )
                        dm_dir2 = trigger_stage2_midquest_comms_if_eligible(session_id, q, session=session)
                        if dm_dir2:
                            directives.append(dm_dir2)
                    if res_adv.get("all_stages_complete"):
                        completed_quests.append(q)
            elif trig in ("skill_check", "action", "inspect_prop", "talk_to_npc", "resource_progress", "defeat_target"):
                wp_match = does_action_target_waypoint(
                    session_id=session_id,
                    quest_id=qid,
                    sub_obj_id=None,
                    current_location=cur_loc,
                    action_text=action_str,
                    narrative="",
                    sub_obj_text="",
                    is_quest_action=is_quest_action,
                    action_quest_id=action_quest_id,
                    action_sub_obj_id=action_sub_obj_id,
                )
                if wp_match:
                    if act_approach in ("wait_for_window", "wait_until_morning"):
                        continue
                    if act_approach == "counter_offer":
                        betray_res = apply_quest_approach_effects(
                            session_id=session_id,
                            quest=q,
                            waypoint=active_wp,
                            approach="counter_offer",
                            gold_cost=0,
                            party_user_ids=party_uids,
                            session=session,
                        )
                        if betray_res.get("directive"):
                            directives.append(betray_res["directive"])
                        continue
                    elif is_success:
                        res_adv = try_complete_on_skill_check(
                            session_id=session_id,
                            quest_id=qid,
                            sub_obj_id=None,
                            current_location=cur_loc,
                            check_success=True,
                            check_result_tier=check_tier,
                            action_text=action_str,
                            is_quest_action=is_quest_action,
                            action_quest_id=action_quest_id,
                            action_sub_obj_id=action_sub_obj_id,
                        )
                        if res_adv:
                            advanced_stages.append({"quest_id": qid, "res": res_adv})
                            advanced_keys.append((qid, None))
                            waypoint_notices.append(res_adv)
                            appr_eff = apply_quest_approach_effects(
                                session_id=session_id,
                                quest=q,
                                waypoint=active_wp,
                                approach=act_approach,
                                gold_cost=act_gold_cost,
                                party_user_ids=party_uids,
                                session=session,
                            )
                            if appr_eff.get("directive"):
                                directives.append(appr_eff["directive"])
                            if not res_adv.get("all_stages_complete"):
                                grant_stage_acquisition_item_if_needed(
                                    session_id=session_id,
                                    quest=q,
                                    completed_stage_index=res_adv.get("completed_stage_index", 1),
                                    total_stages=res_adv.get("total_stages", 2),
                                    party_user_ids=party_uids,
                                )
                                dm_dir3 = trigger_stage2_midquest_comms_if_eligible(session_id, q, session=session)
                                if dm_dir3:
                                    directives.append(dm_dir3)

                            if res_adv.get("all_stages_complete"):
                                completed_quests.append(q)
                    else:
                        strike_res = handle_failed_quest_skill_check(
                            session_id=session_id,
                            quest=q,
                            waypoint=active_wp,
                            check_result_tier=check_tier,
                            party_user_ids=party_uids,
                            session=session,
                        )
                        if strike_res and strike_res.get("directive"):
                            directives.append(strike_res["directive"])

        # 2. Check sub-objective waypoints (Story Quests & multi-branch quests)
        sub_objs = q.get("sub_objectives") or []
        if isinstance(sub_objs, list) and sub_objs:
            sub_dirty = False
            for so in sub_objs:
                if not isinstance(so, dict) or so.get("completed"):
                    continue
                so_id = so.get("id")
                if not so_id:
                    continue
                so_wp = db.get_active_waypoint(session_id, qid, so_id)
                so_done = False
                if so_wp:
                    so_trig = so_wp.get("completion_trigger") or "arrival"
                    if so_trig == "arrival":
                        if act_approach in ("wait_for_window", "wait_until_morning"):
                            continue
                        res_so = try_advance_on_arrival(session_id, qid, so_id, cur_loc)
                        if res_so:
                            advanced_stages.append({"quest_id": qid, "sub_obj_id": so_id, "res": res_so})
                            advanced_keys.append((qid, so_id))
                            waypoint_notices.append(res_so)
                            if not res_so.get("all_stages_complete"):
                                grant_stage_acquisition_item_if_needed(
                                    session_id=session_id,
                                    quest=q,
                                    completed_stage_index=res_so.get("completed_stage_index", 1),
                                    total_stages=res_so.get("total_stages", 2),
                                    party_user_ids=party_uids,
                                    sub_obj=so,
                                )
                            if res_so.get("all_stages_complete"):
                                so_done = True
                    elif so_trig in ("skill_check", "action", "inspect_prop", "talk_to_npc", "resource_progress", "defeat_target"):
                        wp_match_so = does_action_target_waypoint(
                            session_id=session_id,
                            quest_id=qid,
                            sub_obj_id=so_id,
                            current_location=cur_loc,
                            action_text=action_str,
                            narrative="",
                            sub_obj_text=str(so.get("text") or ""),
                            is_quest_action=is_quest_action,
                            action_quest_id=action_quest_id,
                            action_sub_obj_id=action_sub_obj_id,
                        )
                        if wp_match_so:
                            if act_approach in ("wait_for_window", "wait_until_morning"):
                                break
                            if act_approach == "counter_offer":
                                betray_res = apply_quest_approach_effects(
                                    session_id=session_id,
                                    quest=q,
                                    waypoint=so_wp,
                                    approach="counter_offer",
                                    gold_cost=0,
                                    party_user_ids=party_uids,
                                    sub_obj=so,
                                    session=session,
                                )
                                if betray_res.get("directive"):
                                    directives.append(betray_res["directive"])
                                break
                            elif is_success:
                                res_so = try_complete_on_skill_check(
                                    session_id=session_id,
                                    quest_id=qid,
                                    sub_obj_id=so_id,
                                    current_location=cur_loc,
                                    check_success=True,
                                    check_result_tier=check_tier,
                                    action_text=action_str,
                                    sub_obj_text=str(so.get("text") or ""),
                                    is_quest_action=is_quest_action,
                                    action_quest_id=action_quest_id,
                                    action_sub_obj_id=action_sub_obj_id,
                                )
                                if res_so:
                                    advanced_stages.append({"quest_id": qid, "sub_obj_id": so_id, "res": res_so})
                                    advanced_keys.append((qid, so_id))
                                    waypoint_notices.append(res_so)
                                    appr_eff = apply_quest_approach_effects(
                                        session_id=session_id,
                                        quest=q,
                                        waypoint=so_wp,
                                        approach=act_approach,
                                        gold_cost=act_gold_cost,
                                        party_user_ids=party_uids,
                                        sub_obj=so,
                                        session=session,
                                    )
                                    if appr_eff.get("directive"):
                                        directives.append(appr_eff["directive"])
                                    if not res_so.get("all_stages_complete"):
                                        grant_stage_acquisition_item_if_needed(
                                            session_id=session_id,
                                            quest=q,
                                            completed_stage_index=res_so.get("completed_stage_index", 1),
                                            total_stages=res_so.get("total_stages", 2),
                                            party_user_ids=party_uids,
                                            sub_obj=so,
                                        )
                                    if res_so.get("all_stages_complete"):
                                        so_done = True
                            else:
                                strike_res = handle_failed_quest_skill_check(
                                    session_id=session_id,
                                    quest=q,
                                    waypoint=so_wp,
                                    check_result_tier=check_tier,
                                    party_user_ids=party_uids,
                                    sub_obj=so,
                                    session=session,
                                )
                                if strike_res and strike_res.get("directive"):
                                    directives.append(strike_res["directive"])
                                if strike_res and strike_res.get("status") == "dire_cost":
                                    so_done = True

                if not so_done and resolves_so_id and str(resolves_so_id) == str(so_id) and is_success:
                    so_done = True
                    advanced_keys.append((qid, so_id))
                if so_done:
                    so["completed"] = True
                    sub_dirty = True
                    consume_quest_delivery_item_if_needed(
                        session_id=session_id,
                        quest=q,
                        party_user_ids=party_uids,
                        sub_obj=so,
                    )
                    completed_sub_quests.append({
                        "quest_id": qid,
                        "quest_title": q.get("title", "Quest"),
                        "sub_obj_id": so_id,
                        "text": so.get("text", so_id),
                    })
                    directives.append(
                        f"[MANDATORY QUEST OBJECTIVE COMPLETE]: Sub-objective '{so.get('text', so_id)}' for quest '{q.get('title')}' is completed! Narrate the breakthrough/discovery vividly."
                    )
                    # Phase 5 Q2: Pre-Registered Objective Clue Discovery
                    c_lead = so.get("clue") or so.get("clue_lead")
                    if not c_lead:
                        t_text = str(so.get("text") or "")
                        if any(k in t_text.lower() for k in ("investigate", "discover", "uncover", "search", "interview", "interrogate", "examine", "clue", "evidence", "find")):
                            c_lead = f"Discovered lead: {t_text}"
                    if c_lead and session_id:
                        try:
                            from mechanics.narrative.clues import categorize_clue
                            cur_ch = session.get("chapter", 1) if session else 1
                            cid = db.add_session_clue(
                                session_id=session_id,
                                title=f"Lead: {str(so.get('text', 'Evidence'))[:40]}",
                                lead_text=str(c_lead),
                                category=categorize_clue(str(c_lead)),
                                source_location=cur_loc,
                                linked_npc=str(so_wp.get("target_npc") if so_wp else "") or str(q.get("target_npc") or ""),
                                quest_id=qid,
                                chapter=cur_ch,
                            )
                            if cid:
                                directives.append(
                                    f"[MANDATORY CLUE DISCOVERY]: Evidence recorded to Caseboard: '{c_lead}'"
                                )
                        except Exception as e:
                            logger.warning("Failed to record pre-registered clue: %s", e)
                    break
            if sub_dirty and session_id:
                try:
                    done_cnt = sum(1 for s in sub_objs if isinstance(s, dict) and s.get("completed"))
                    db.upsert_quest(
                        session_id=session_id,
                        quest_id=qid,
                        quest_type=q.get("quest_type") or "Story Quest",
                        title=q.get("title") or "Quest",
                        objective=q.get("objective") or "",
                        progress=f"{done_cnt}/{len(sub_objs)} Cleared",
                        current_clues=q.get("current_clues") or "",
                        status=q.get("status") or "Active",
                        reward_xp=int(q.get("reward_xp") or 100),
                        reward_gold=int(q.get("reward_gold") or 30),
                        is_story_quest=int(q.get("is_story_quest") or 0),
                        clues_required=int(q.get("clues_required") or len(sub_objs)),
                        sub_objectives=sub_objs,
                    )
                except Exception:
                    pass
                if not q.get("is_story_quest") and all(isinstance(s, dict) and s.get("completed") for s in sub_objs):
                    if q not in completed_quests:
                        completed_quests.append(q)

        # Check if climax action was executed for a story quest (standard or premature per A11)
        if q.get("is_story_quest"):
            sq, climax_loc = get_story_quest_climax_location(session_id, allow_premature=True)
            if sq and sq.get("quest_id") == qid:
                if ("story climax" in act_low or "⚡" in action_str):
                    sub_objs_done = all(isinstance(s, dict) and s.get("completed") for s in (q.get("sub_objectives") or []))
                    if is_success:
                        # Auto-mark all sub-objectives as cleared on successful climax
                        for s in (q.get("sub_objectives") or []):
                            if isinstance(s, dict):
                                s["completed"] = True
                        if q not in completed_quests:
                            completed_quests.append(q)
                    else:
                        if not sub_objs_done:
                            # Phase 5 A11: Premature confrontation failure -> immediate escape/escalation +2 strikes
                            strike_res = db.increment_quest_strikes(session_id, qid, delta=2)
                            directives.append(
                                f"[PREMATURE CLIMAX FAILED - {strike_res['strikes']}/{strike_res['max_strikes']} STRIKES]: Confronting the threat without full evidence backfired! The suspect evaded capture and opposition is on alert."
                            )
                        else:
                            strike_res = db.increment_quest_strikes(session_id, qid, delta=2 if check_tier == "critical_failure" else 1)
                            if strike_res["failed"] or check_tier == "critical_failure":
                                db.set_quest_resolution_approach(session_id, qid, "pyrrhic_climax")
                                q["resolution_approach"] = "pyrrhic_climax"
                                q["reward_xp"] = max(25, int(int(q.get("reward_xp") or 100) * 0.5))
                                q["reward_gold"] = max(10, int(int(q.get("reward_gold") or 30) * 0.5))
                                db.apply_hp_mp_delta(party_uids[0], hp_delta=-10)
                                directives.append(
                                    f"[MANDATORY PYRRHIC CLIMAX RESOLUTION]: The Chapter Climax '{q.get('title')}' concluded with bittersweet compromise and dark consequences! Complete the climax and narrate the heavy toll."
                                )
                                if q not in completed_quests:
                                    completed_quests.append(q)
                            else:
                                directives.append(
                                    f"[QUEST COMPLICATION - {strike_res['strikes']}/{strike_res['max_strikes']} STRIKES]: The Story Climax check met unexpected resistance! The stakes escalate for the final push."
                                )

    # Award rewards deterministically for newly completed quests
    import time
    reward_notices = []
    for cq in completed_quests:
        cq_id = cq["quest_id"]
        consume_quest_delivery_item_if_needed(
            session_id=session_id,
            quest=cq,
            party_user_ids=party_uids,
        )

        claim_res = None
        try:
            claim_res = db.claim_quest_reward(session_id, cq_id, party_uids)
        except Exception:
            try:
                with db.get_conn() as _conn:
                    _conn.execute("UPDATE quests SET status='Completed', updated_at=? WHERE session_id=? AND quest_id=?", (time.time(), session_id, cq_id))
            except Exception:
                pass

        xp = int(cq.get("reward_xp") or 100)
        gold = int(cq.get("reward_gold") or 30)
        ritem = cq.get("reward_item") or ""
        notice = {
            "claimed": True,
            "title": cq.get("title", "Quest"),
            "quest_type": cq.get("quest_type") or ("Story Quest" if cq.get("is_story_quest") else "Side Bounty"),
            "is_story_quest": bool(cq.get("is_story_quest") or cq.get("quest_type") in ("Story Quest", "Main Quest")),
            "xp": xp,
            "gold": gold,
            "item": ritem,
            "quest_id": cq_id,
            "levels_gained": (claim_res or {}).get("levels_gained", {}) if isinstance(claim_res, dict) else {},
            "_item_granted_in_db": bool(isinstance(claim_res, dict) and claim_res.get("_item_granted_in_db")),
        }
        reward_notices.append(notice)
        directives.append(
            f"[MANDATORY QUEST OBJECTIVE COMPLETE]: Quest '{cq.get('title')}' is completed! Narrate the breakthrough/success vividly."
        )

    # Interactive Caseboard Deductive Synthesis via explicit turn action (D18: no silent 0-XP auto-consumption)
    deduction_xp_bonus = 0
    is_deduce_action = (
        str(fa.get("sub_intent") or "").lower() == "deduce_clues"
        or str(fa.get("intent") or "").lower() == "deduce_clues"
        or "[synthesize leads]" in act_low
    )
    if session_id and is_deduce_action:
        if is_success:
            try:
                from mechanics.narrative.clues import evaluate_clue_deduction
                scen_k = session.get("scenario", "fantasy") if session else "fantasy"
                matched_deduction = None
                explicit_pair = fa.get("clue_pair_ids")
                if isinstance(explicit_pair, list) and len(explicit_pair) == 2:
                    ca = db.get_session_clue_by_id(int(explicit_pair[0]))
                    cb = db.get_session_clue_by_id(int(explicit_pair[1]))
                    if ca and cb and not ca.get("is_consumed") and not cb.get("is_consumed"):
                        ok_d, b_title, b_text = evaluate_clue_deduction(ca, cb, scen_key=scen_k)
                        if ok_d:
                            matched_deduction = (ca, cb, b_title, b_text)
                if not matched_deduction:
                    open_clues = [
                        c for c in (db.get_session_clues(session_id, is_verified=0) or [])
                        if not c.get("is_consumed") and c.get("category") != "deduction"
                    ]
                    for i in range(len(open_clues)):
                        for j in range(i + 1, len(open_clues)):
                            ca, cb = open_clues[i], open_clues[j]
                            ok_d, b_title, b_text = evaluate_clue_deduction(ca, cb, scen_key=scen_k)
                            if ok_d:
                                matched_deduction = (ca, cb, b_title, b_text)
                                break
                        if matched_deduction:
                            break
                if matched_deduction:
                    ca, cb, b_title, b_text = matched_deduction
                    db.synthesize_deduction_clue(
                        session_id,
                        [ca["id"], cb["id"]],
                        b_title,
                        b_text,
                        chapter=session.get("chapter", 1) if session else 1,
                    )
                    for uid in party_uids:
                        try:
                            db.add_xp(uid, 50)
                        except Exception:
                            pass
                    deduction_xp_bonus = 50
                    directives.append(
                        f"[STAGE DIRECTION — BREAKTHROUGH SYNTHESIZED]: Synthesized '{b_title}' from caseboard evidence (+50 XP)! {b_text}"
                    )
            except Exception as e:
                logger.warning("Failed during interactive caseboard deductive synthesis: %s", e)
        else:
            directives.append(
                "[STAGE DIRECTION — DEDUCTION INCONCLUSIVE]: You cross-referenced the evidence leads, but couldn't quite connect the full picture yet (leads remain unconsumed)."
            )

    # Two-Phase Chapter Climax System (Phase 5 Q4)
    chapter_climax = False
    cur_ch = session.get("chapter", 1) if session else 1
    has_completed_sq = bool(completed_quests and any(q.get("is_story_quest") for q in completed_quests))

    if has_completed_sq and session_id:
        import scenario_data as _sd_ep
        scen_key_ep = str(session.get("scenario") or "fantasy") if isinstance(session, dict) else "fantasy"
        cur_db_ch = db.get_session_chapter(session_id) or cur_ch
        effective_ch = max(cur_ch, cur_db_ch)
        if _sd_ep.is_anomalous_incursions_scenario(scen_key_ep) and effective_ch >= 11 and not (isinstance(session, dict) and session.get("endless_mode_unlocked")):
            epilogue_choices = [
                {
                    "label": "🏁 Conclude Campaign (Archive Chronicle)",
                    "stat": "FREE",
                    "requirement": 0,
                    "mp_cost": 0,
                    "intent": "epilogue_conclude_campaign",
                },
                {
                    "label": "♾️ Continue in Endless Containment Mode",
                    "stat": "FREE",
                    "requirement": 0,
                    "mp_cost": 0,
                    "intent": "epilogue_endless_mode",
                },
            ]
            db.update_session(session_id, extra={"epilogue_ready": True, "epilogue_choices": epilogue_choices})
            if isinstance(session, dict):
                session["epilogue_ready"] = True
                session["epilogue_choices"] = epilogue_choices
                session["chapter_climax_phase"] = "resolved"
            directives.append(
                "[MANDATORY CAMPAIGN EPILOGUE RESOLUTION]: Chapter 11 resolution & commendation completed! Present the Post-Game Epilogue choice to archive the chronicle or continue in Endless Containment Mode."
            )
            chapter_climax = True
        else:
            next_ch = cur_ch + 1
            if isinstance(session, dict):
                session["chapter"] = next_ch
                session["chapter_climax_phase"] = "resolved"
            try:
                db.set_session_chapter(session_id, next_ch)
            except Exception:
                pass
            directives.append(
                f"[MANDATORY CHAPTER CLIMAX RESOLUTION]: Chapter {cur_ch} climax successfully concluded! Transition into Chapter {next_ch}."
            )
            chapter_climax = True
            try:
                ensure_story_quest_exists(session)
            except Exception:
                pass
    elif session_id:
        active_sq = db.get_active_story_quest(session_id)
        if active_sq:
            sq_subs = active_sq.get("sub_objectives", []) or []
            if sq_subs and all(isinstance(s, dict) and s.get("completed") for s in sq_subs):
                if isinstance(session, dict):
                    session["chapter_climax_phase"] = "setup" 

    if session_id:
        try:
            sync_deterministic_campaign_goals(session_id)
        except Exception:
            pass

    res = {
        "completed_quests": [q.get("quest_id") for q in completed_quests],
        "reward_notices": reward_notices,
        "waypoint_notices": waypoint_notices,
        "completed_sub_quests": completed_sub_quests,
        "advanced_keys": advanced_keys,
        "directives": directives,
        "chapter_climax": chapter_climax,
        "deduction_xp_bonus": deduction_xp_bonus,
    }
    session["_pre_turn_quest_res"] = res
    return res

def forfeit_side_bounty(session_id: int, quest_id: str, party_user_ids: list[int] = None) -> dict:
    """
    Abandons/forfeits an active side bounty per Phase 5 contract A16:
    - Applies -5 client affinity penalty.
    - Clears associated waypoints.
    - Marks quest status = 'Abandoned'.
    - Queues zero retaliation ambushes.
    """
    import db
    import time
    q = db.get_quest_by_id(session_id, quest_id)
    if not q or q.get("is_story_quest"):
        return {"success": False, "reason": "Cannot forfeit story quest"}

    with db.get_conn() as conn:
        now = time.time()
        conn.execute("UPDATE quests SET status='Abandoned', updated_at=? WHERE session_id=? AND quest_id=?", (now, session_id, quest_id))
        conn.execute("UPDATE quest_waypoints SET status='abandoned', updated_at=? WHERE session_id=? AND quest_id=?", (now, session_id, quest_id))

    client_npc = q.get("client_npc") or ""
    if client_npc:
        try:
            db.update_relationship_score(session_id, client_npc, delta_score=-5)
        except Exception:
            pass

    return {
        "success": True,
        "quest_id": quest_id,
        "title": q.get("title", "Bounty"),
        "client_affinity_delta": -5,
        "directive": f"[SIDE BOUNTY FORFEITED]: The contract '{q.get('title')}' was abandoned (-5 Affinity with {client_npc or 'the client'})."
    }


def can_accept_side_bounty(session_id: int, quest: dict | None = None) -> bool:
    """Checks if session is below the max active side bounties concurrency cap of 3 (exempting mandatory daily dispatches)."""
    import db
    if isinstance(quest, dict):
        q_notes = str(quest.get("quest_notes") or "")
        if str(quest.get("quest_id") or "").upper().startswith("MAND-") or "mandatory_daily:1" in q_notes:
            return True
    active_bounties = [
        q for q in (db.get_session_quests(session_id, status="Active") or [])
        if not q.get("is_story_quest")
        and not str(q.get("quest_id") or "").upper().startswith("MAND-")
        and "mandatory_daily:1" not in str(q.get("quest_notes") or "")
    ]
    return len(active_bounties) < 3


def check_and_extract_defeated_suspect_evidence(session_id: int, defeated_npc_name: str, cur_loc: str = "") -> dict | None:
    """
    Fail-Forward Pocket Evidence Drop per Phase 5 contract A14:
    If an investigation suspect is defeated in combat before formal interrogation,
    extracts their vital evidence from personal effects into session_clues with genre-grounded wording.
    """
    import db
    if not session_id or not defeated_npc_name:
        return None
    d_low = defeated_npc_name.strip().lower()
    sess = db.get_session(session_id) or {}
    scen_low = str(sess.get("scenario") or "fantasy").lower()
    if any(k in scen_low for k in ("cyber", "sci", "space", "post_apoc")):
        artifact_desc = "an encrypted datapad and access passkey"
        cat_val = "digital"
    elif any(k in scen_low for k in ("school", "modern", "slice", "anomalous", "academy", "campus")):
        artifact_desc = "a hidden notebook and locker key"
        cat_val = "document"
    else:
        artifact_desc = "a wax-sealed ledger and signet key"
        cat_val = "document"

    active_quests = db.get_session_quests(session_id, status="Active") or []
    for q in active_quests:
        target_npc = str(q.get("target_npc") or "").strip().lower()
        sub_objs = q.get("sub_objectives") or []
        is_suspect = (target_npc and target_npc in d_low) or any(
            isinstance(so, dict) and d_low in str(so.get("text", "")).lower() for so in sub_objs
        ) or (d_low in str(q.get("objective", "")).lower())
        if is_suspect:
            cur_ch = db.get_session_chapter(session_id) or 1
            title = f"Pocket Evidence: {defeated_npc_name}"
            lead_text = f"Recovered from the personal effects of {defeated_npc_name}: {artifact_desc} confirming their involvement in '{q.get('title')}'."
            cid = db.add_session_clue(
                session_id=session_id,
                title=title,
                lead_text=lead_text,
                category=cat_val,
                source_location=cur_loc,
                linked_npc=defeated_npc_name,
                quest_id=q.get("quest_id", ""),
                chapter=cur_ch,
            )
            return {
                "clue_id": cid,
                "title": title,
                "lead_text": lead_text,
                "quest_id": q.get("quest_id", ""),
                "directive": f"[FAIL-FORWARD EVIDENCE RECOVERED]: Vital evidence extracted from {defeated_npc_name}'s personal effects!",
            }
    return None

