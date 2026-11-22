from __future__ import annotations
import logging

import db
from models.llm_schemas import DeterministicTurnNarration, DeterministicCombatNarration
import llm_client
from llm_client import GM_SHARED_RULES, call_llm_json, call_llm_json_stream
from scenario_data import is_nsfw_scenario, uses_nsfw_model
import game_engine

log = logging.getLogger(__name__)


NARRATION_SYSTEM_PROMPT = """You are a highly skilled interactive fiction engine (the "Narrator").
Your ONLY job right now is to regenerate the prose (the narrative description of what just happened and what is happening next) and the next available choices.

You MUST NOT change the mechanical outcome of the turn. The facts provided in the user prompt's FROZEN STATE block are absolute and frozen. You are just describing them in second-person prose strictly obeying the active Narrative Style, Pacing, and Dialogue Style directives.

## YOUR TASK (OUTPUT USING SENTINEL SECTIONS — NO JSON OR CODE FENCES)
1. `@@TITLE: <2-5 word title>`: A short evocative title for the current situation.
2. `@@OUTCOME`: Describe the immediate result of the NEW player action(s) based strictly on the frozen mechanics. NEVER repeat, re-state, or re-quote dialogue or events from previous turns.
3. `@@NEXT`: Describe the current state of the scene right after the action resolves (environment, who is still here, immediate atmosphere).
4. `@@CHOICES`: Propose 2-5 logical, contextual actions as `- <STR|PER|END|CHA|INT|AGI|LUK|ITEM|NONE> | <0-12> | [optional: topic_id=<id> | category=<cat> | ends_dialogue=true | target=<Exact NPC Name>] | <label>` lines (when in active conversation with an NPC, keep choices in-conversation and include 1 `NONE | 0 | ends_dialogue=true | ...` exit option).
5. `@@META` (optional): Emit `pose: <Actor Name> | <posture> | <holding>` or `memory: <1-sentence NPC memory fact>` lines only when warranted.

## GUIDELINES
- PROTAGONIST GENDER & PRONOUN FIDELITY: Never misgender the protagonist. If the protagonist is male, always use he/him/his (never she/her). If female, always use she/her/hers. When NPCs flirt or banter with the protagonist, ensure their romantic dialogue targets the protagonist's canon gender (e.g. female NPCs flirting with a male protagonist ask what he looks for in a woman/girl/partner, NEVER invert attraction to ask what he looks for in a guy).
- CANON RELATIONSHIP & VIRGINITY INTEGRITY: NPCs asked about their past romance, boyfriends, dating suitors, or sexual experience must speak the truth according to their profile. A virgin character with no past relationship history (empty ex_partners) must NEVER claim to have had past boyfriends, suitors, or practice juggling partners on their schedule.
- SPECIES & BIOLOGY FIDELITY: Strictly adhere to the protagonist's canonical race and biology. If the character is human, NEVER narrate animal traits such as animal ears twitching, tail wagging, purring, scales, or fur.
- ANTHROPOMORPHIC & BEASTFOLK SPECIES DIVERSITY: In beastfolk and furry scenarios, ensure rich and varied species distribution across students, staff, and club members. Do NOT over-index on rabbits or mice; actively incorporate avians/birds, felines (cats, tigers, cheetahs, lions), canines (wolves, foxes, fennecs), bears, and reptiles.
- STRICT PHYSICAL PRESENCE: ONLY depict characters physically present in the room according to the frozen state. DO NOT introduce or narrate physical actions for characters who are stationed elsewhere.
- PROTAGONIST TITLE EXCLUSIVITY: Refer to the protagonist only as "you" or by name, never by their class/role title, and never describe an NPC using the protagonist's own class/role title.
- NO PHANTOM COMBAT WHEN NEARBY_ENEMIES IS EMPTY: If `Enemies present in the scene` is omitted/empty in the frozen state, do NOT narrate active physical combat, hostile entities lunging to attack, or weapon exchanges; keep any anomalies strictly atmospheric or investigative.
- CANON UNDERGARMENT & COMMANDO FIDELITY: Strictly adhere to each character's canonical undergarment state. If a character is wearing NO underwear / panties (Commando) or NO bra (Bra-less), when their skirt, dress, pants, or shirt is lifted, parted, or removed, they are completely bare underneath! Third-person narration and dialogue MUST NEVER narrate peeling back, sliding aside, snapping, or removing phantom panties, bras, or underwear when the character is commando or bra-less.
- NARRATOR RESTRAINT ON UNREVEALED INTIMATE TRAITS: Never describe an NPC's hidden intimate traits (such as underwear styles, secret erogenous spots, or intimate anatomy) before they have been revealed through player action, clothing removal, or intimacy progression.
- FORWARD TEMPORAL MOMENTUM: Start immediately from the player's new action and move the clock forward. NEVER write a summary or recap paragraph of earlier conversation turns.
- Strictly obey the active Narrative Style, Pacing, and Dialogue Style directives.
- If characters died, describe their fall.
- If an item was gained, mention it naturally in the prose.
- Output raw prose under `@@OUTCOME` and `@@NEXT` with NO JSON braces or markdown code blocks.
"""

COMBAT_NARRATION_SYSTEM_PROMPT = """You are a highly skilled interactive fiction engine (the "Narrator") in active COMBAT ENCOUNTER mode.
Your ONLY job right now is to regenerate the battle prose (the immediate combat exchange and aftermath) strictly matching the FROZEN STATE block.

You MUST NOT change mechanical damage, defeats, or positions. Do NOT emit `@@CHOICES` (tactical combat decks are supplied deterministically).

## YOUR TASK (OUTPUT USING SENTINEL SECTIONS — NO JSON OR CODE FENCES)
1. `@@TITLE: <2-5 word combat heading>`: A short evocative battle title.
2. `@@OUTCOME`: Depict the player action and any enemy counter-attack strictly from frozen facts. NEVER mention numeric HP, damage digits, or roll percentages in prose.
3. `@@NEXT`: Describe the immediate battlefield stance, enemy conditions, and tactical tension.
4. `@@META` (optional): Emit `pose: <Actor Name> | <posture> | <holding>` or `memory: <1-sentence combat turning point>` lines if warranted.
- Strictly obey the active Narrative Style, Pacing, and Dialogue Style directives.
"""

def _build_frozen_state_text(snapshot: dict) -> str:
    lines = []
    applied = snapshot.get("applied", {})
    
    # Check outcomes
    char_outcomes = applied.get("character_outcomes", [])
    if char_outcomes:
        lines.append("Character Consequences:")
        for co in char_outcomes:
            c_dict = co if isinstance(co, dict) else co.__dict__
            c_name = c_dict.get("name", "Unknown")
            hp_c = c_dict.get("hp_change", 0)
            mp_c = c_dict.get("mp_change", 0)
            status = c_dict.get("status_effects_gained", [])
            cond = "critically wounded" if int(hp_c or 0) < -25 else ("severely injured" if int(hp_c or 0) < -10 else ("wounded" if int(hp_c or 0) < 0 else ("rejuvenated" if int(hp_c or 0) > 0 else "steady")))
            mp_desc = "drained of focus" if int(mp_c or 0) < -15 else ("exerted" if int(mp_c or 0) < 0 else ("energized" if int(mp_c or 0) > 0 else "steady"))
            lines.append(f" - {c_name}: physical condition is {cond}, magical focus is {mp_desc}, Status Effects: {status}")
            
    # Location
    loc = applied.get("location")
    if loc:
        lines.append(f"Current Location: {loc}")
        
    # Entities
    npcs = applied.get("npcs_present", [])
    if npcs:
        lines.append(f"NPCs present in the scene: {[n.get('name', '') if isinstance(n, dict) else n for n in npcs]}")
        
    enemies = applied.get("nearby_enemies", [])
    if enemies:
        lines.append(f"Enemies present in the scene: {[e.get('name', '') if isinstance(e, dict) else e for e in enemies]}")
        
    # Loot / XP
    loot = applied.get("items_gained", {})
    if any(loot.values()):
        lines.append(f"Loot gained: {loot}")
        
    xp = applied.get("xp_gained", {})
    if any(xp.values()):
        lines.append("Combat and adventuring experience was gained from the engagement.")
        
    # Time / Sleep
    t_info = applied.get("time_info", {})
    if t_info:
        lines.append(f"Time advanced. It is now day {t_info.get('day', '?')}, {t_info.get('time', '?')}")

    # Intimate & Physical State
    phys_st = applied.get("_physical_state") or {}
    ic_stage = phys_st.get("intimate_contact") if isinstance(phys_st, dict) else None
    if ic_stage and ic_stage != "none":
        lines.append(f"Intimate Contact Stage: {ic_stage}")
    int_up = applied.get("intimate_update")
    if isinstance(int_up, dict) and int_up.get("active"):
        p_meters = int_up.get("partner_meters") or []
        p_climaxes = int_up.get("partner_climaxes") or {}
        if isinstance(p_meters, list) and len(p_meters) >= 2:
            p_summary_str = ", ".join(
                f"{item.get('name', 'Partner')}={item.get('meter', 0)}% (Climaxed={bool(item.get('climaxed', p_climaxes.get(item.get('name', ''), False)))})"
                for item in p_meters
                if isinstance(item, dict)
            )
            lines.append(
                f"Intimate Act & Excitement: Act={int_up.get('act_type', 'none')}, "
                f"{int_up.get('player_name', 'Player')}={int_up.get('player_meter', 0)}%, "
                f"Partners=[{p_summary_str}], "
                f"Player Climaxed={int_up.get('player_climaxed', False)}, "
                f"Premature Finish={int_up.get('premature_finish', False)}"
            )
        elif isinstance(p_meters, dict) and len(p_meters) >= 2:
            p_summary_str = ", ".join(
                f"{p_n}={p_v}% (Climaxed={bool(p_climaxes.get(p_n, False))})"
                for p_n, p_v in p_meters.items()
            )
            lines.append(
                f"Intimate Act & Excitement: Act={int_up.get('act_type', 'none')}, "
                f"{int_up.get('player_name', 'Player')}={int_up.get('player_meter', 0)}%, "
                f"Partners=[{p_summary_str}], "
                f"Player Climaxed={int_up.get('player_climaxed', False)}, "
                f"Premature Finish={int_up.get('premature_finish', False)}"
            )
        else:
            lines.append(
                f"Intimate Act & Excitement: Act={int_up.get('act_type', 'none')}, "
                f"{int_up.get('player_name', 'Player')}={int_up.get('player_meter', 0)}%, "
                f"{int_up.get('partner_name', 'Partner')}={int_up.get('partner_meter', 0)}%, "
                f"Partner Climaxed={int_up.get('partner_climaxed', False)}, "
                f"Player Climaxed={int_up.get('player_climaxed', False)}, "
                f"Premature Finish={int_up.get('premature_finish', False)}"
            )

    if not lines:
        lines.append("(No significant mechanical changes)")
    lines.append("[PROSE GUARD]: Describe all physical and tactical consequences qualitatively; never mention numeric HP/MP numbers or XP digits in story prose.")
        
    return "\n".join(lines)


_format_frozen_state_for_prompt = _build_frozen_state_text


async def run_narration_pass(session: dict, snapshot: dict, attempt: int = 1, stream_callback=None) -> dict:
    """
    Lightweight generation pass that ONLY rewrites narrative and choices,
    treating the provided snapshot's mechanical state as authoritative ground truth.
    """
    session_id = session.get("id", 0)
    
    raw_hist = list(session.get("history") or [])
    # CRITICAL: On a retry narration pass, the turn being retried is at history[-1],
    # so effective history leading up to the action must exclude it!
    effective_history = raw_hist[:-1] if raw_hist else []
    actions = snapshot.get("actions", [])
    action_lines = []
    for a in actions:
        tier_label = a.get("check", {}).get("tier_label", "Action") if isinstance(a.get("check"), dict) else getattr(a.get("check"), "tier_label", "Action")
        action_lines.append(f"[{tier_label}] {a.get('label')}")
    actions_text = "\n".join(action_lines)

    from mechanics.social.genealogy import build_topic_aware_npc_context
    from mechanics.social.physical_state import build_physical_prompt_block

    style_str = game_engine._style_block(session, kind="turn")
    scenario_str = game_engine._scenario_block(session)
    present_npcs = snapshot.get("applied", {}).get("npcs_present", []) or session.get("current_npcs", [])
    is_combat_retry = bool(snapshot.get("applied", {}).get("nearby_enemies"))

    def _build_retry_db_context() -> tuple[str, str, str, str, str, str]:
        with db.UnitOfWork():
            h_str = game_engine._history_text(effective_history, session_id=session_id)
            kw_str = game_engine._known_world_text(
                session_id,
                session.get("current_location", ""),
                current_npcs=session.get("current_npcs", []),
            )
            all_contacts_map = {
                str(c.get("name") or "").strip().lower(): c
                for c in (db.get_contacts(session_id, ensure_scene=False) or [])
                if isinstance(c, dict) and c.get("name")
            }
            c_lines = []
            for n in present_npcs:
                n_name = n.get("name") if isinstance(n, dict) else str(n)
                if not n_name:
                    continue
                contact = all_contacts_map.get(n_name.strip().lower()) or db.get_contact(session_id, n_name)
                if contact:
                    c_details = [
                        f"Track: {contact.get('track', 'platonic')}",
                        f"Affinity: {contact.get('relationship_score', 0)}",
                    ]
                    topic_ctx = build_topic_aware_npc_context(
                        contact,
                        actions=actions,
                        session_history=effective_history,
                        scenario=session.get("scenario", "fantasy"),
                    )
                    line = f"  * {n_name}: " + " | ".join(c_details)
                    if topic_ctx:
                        line += "\n" + topic_ctx
                    c_lines.append(line)
            c_block = "\n\nKNOWN CHARACTER CONTEXT & RELATIONSHIPS:\n" + "\n".join(c_lines) if c_lines else ""

            p_block_str = ""
            try:
                lead_char_obj = actions[0].get("char") if actions and isinstance(actions[0], dict) else None
                party_for_phys = [(lead_char_obj, [])] if isinstance(lead_char_obj, dict) else []
                phys_block = build_physical_prompt_block(
                    session,
                    party_for_phys,
                    is_combat=is_combat_retry,
                    is_nsfw=is_nsfw_scenario(session.get("scenario")),
                    actions=actions,
                )
                if phys_block:
                    p_block_str = f"\n\n[ACTIVE PHYSICAL & INTIMATE STATE CONTINUITY]:\n{phys_block}"
            except Exception:
                pass

            ch_sheet_str = ""
            lead_char_obj = actions[0].get("char") if actions and isinstance(actions[0], dict) else None
            eff_uid = (
                (lead_char_obj.get("user_id") if isinstance(lead_char_obj, dict) else None)
                or session.get("user_id")
                or session.get("host_user_id")
            )
            if not isinstance(lead_char_obj, dict) and session.get("character_id"):
                try:
                    lead_char_obj = db.get_character_by_id(int(session["character_id"]))
                except Exception:
                    lead_char_obj = None
            if not isinstance(lead_char_obj, dict) and eff_uid:
                try:
                    lead_char_obj = db.get_character(int(eff_uid), session_id=session_id)
                except Exception:
                    lead_char_obj = None
            resolved_gender = ""
            if isinstance(lead_char_obj, dict):
                resolved_gender = str(lead_char_obj.get("gender") or "")
                inv = []
                inv_uid = eff_uid or lead_char_obj.get("user_id")
                if inv_uid:
                    try:
                        inv = db.get_inventory(int(inv_uid))
                    except Exception:
                        inv = []
                ch_sheet_str = f"\n\nPROTAGONIST CHARACTER SHEET:\n{game_engine._character_sheet_text(lead_char_obj, inv)}"

            return h_str, kw_str, c_block, p_block_str, ch_sheet_str, resolved_gender

    history_str, known_world_str, contact_block, phys_block_str, char_sheet_str, resolved_lead_gender = await db.adb(_build_retry_db_context)

    context_str = f"{known_world_str}{char_sheet_str}{contact_block}{phys_block_str}\n\nRECENT HISTORY:\n{history_str}"
    
    # 3. Build frozen state text + D13 frozen deterministic stage plan
    frozen_state_text = _build_frozen_state_text(snapshot)
    applied_snap = snapshot.get("applied", {})
    frozen_present = list(applied_snap.get("npcs_present") or session.get("current_npcs") or [])
    frozen_partners = list(
        applied_snap.get("dialogue_partners")
        if "dialogue_partners" in applied_snap
        else ([applied_snap["dialogue_partner"]] if applied_snap.get("dialogue_partner") else [])
    )
    from game_engine.npcs.cast_planner import CastPlan, render_stage_plan
    partner_lows = {str(p).strip().lower() for p in frozen_partners if p}
    frozen_bystanders = [
        (n.get("name") if isinstance(n, dict) else str(n)).strip()
        for n in frozen_present
        if n and (n.get("name") if isinstance(n, dict) else str(n)).strip().lower() not in partner_lows
    ]
    any_stealth_ok = any(
        isinstance(a, dict) and a.get("is_stealth") and (
            a.get("check", {}).get("succeeded", True) if isinstance(a.get("check"), dict) else getattr(a.get("check"), "succeeded", True)
        )
        for a in actions
    )
    frozen_cast_plan = CastPlan(
        present_npcs=[n if isinstance(n, dict) else {"name": str(n)} for n in frozen_present if n],
        dialogue_partners=frozen_partners,
        bystander_npcs=frozen_bystanders,
        departing_npcs=[],
        has_exited_convo=any(
            isinstance(a, dict) and (a.get("ends_dialogue") or a.get("intent") == "dialogue_exit")
            for a in actions
        ),
        stealth_active=any_stealth_ok,
    )
    stage_plan_block = render_stage_plan(frozen_cast_plan)
    frozen_state_text = f"{frozen_state_text}\n\n{stage_plan_block}"

    active_narration_prompt = COMBAT_NARRATION_SYSTEM_PROMPT if is_combat_retry else NARRATION_SYSTEM_PROMPT
    narration_core_zone = f"{GM_SHARED_RULES}\n\n{active_narration_prompt}"
    style_zone = style_str

    # Ensure lead character gender is populated if available
    lead_char_obj = actions[0].get("char") if actions and isinstance(actions[0], dict) else None
    if not session.get("lead_character_gender"):
        if isinstance(lead_char_obj, dict) and lead_char_obj.get("gender"):
            session["lead_character_gender"] = lead_char_obj.get("gender", "male")
        elif resolved_lead_gender:
            session["lead_character_gender"] = resolved_lead_gender

    from game_engine.prompt_layout import (
        build_anomalous_resonance_directive,
        build_language_directive,
        build_scenario_genre_zone_rules,
    )
    from mechanics.combat.merchant import merchant_prompt_note
    genre_rules = build_scenario_genre_zone_rules(session, kind="turn")
    anom_dir = build_anomalous_resonance_directive(session)
    merch_note = merchant_prompt_note(scen_key=session.get("scenario"))
    lang_dir = build_language_directive(session)
    sys_zones = tuple(
        z
        for z in (narration_core_zone, scenario_str, style_zone, genre_rules, anom_dir, merch_note, lang_dir)
        if z
    )
    sys_prompt = "\n\n".join(sys_zones)

    # Check for conversational exit intent in retry pass
    from mechanics.narrative.intent import is_dialogue_exit_action
    has_exited_convo = any(is_dialogue_exit_action(a) for a in actions)
    departure_directive = ""
    if has_exited_convo:
        departure_directive = (
            "\n\n[CONVERSATIONAL DEPARTURE & SCENE TRANSITION DIRECTIVE]:\n"
            "The player has explicitly concluded the conversation, stepped away, or departed.\n"
            "- In `@@OUTCOME`, narrate only the immediate parting gesture or departure (e.g. nodding, thanking them, stepping away). "
            "EVERY character present in the scene MUST STOP talking with the player! DO NOT have any NPCs continue or initiate conversation with the player this turn! DO NOT reopen the conversation!\n"
            "- In `@@NEXT`, transition the scene forward into open exploration, room atmosphere, or next destination. NO NPC should be talking to the player.\n"
            "- In `@@CHOICES`, generate OPEN EXPLORATION, room inspection, or travel choices. DO NOT generate active dialogue choices."
        )

    frozen_block = (
        f"## FROZEN STATE (Authoritative Facts)\n"
        f"The player took the following action(s):\n{actions_text}\n\n"
        f"The engine already resolved the outcome and these are the unchangeable facts:\n{frozen_state_text}\n\n"
    )
    closing_tail = game_engine.build_closing_reminder(session)
    user_prompt = (
        f"Context & Lore:\n{context_str}\n\n{frozen_block}"
        f"Please generate the narration and next choices now based strictly on the frozen mechanics.{departure_directive}\n\n"
        f"{closing_tail}"
    )

    is_nsfw = uses_nsfw_model(session.get("scenario"))
    profile_params = llm_client.resolve_narration_sampling_params(session, is_nsfw=is_nsfw)
    # Temperature bump for manual retries (attempt 1 uses style profile temperature, attempt 2+ bumps above profile)
    retry_temp = None if attempt <= 1 else min(1.2, round(profile_params["temperature"] + (attempt - 1) * 0.15, 2))

    retry_schema = DeterministicCombatNarration if bool(snapshot.get("applied", {}).get("nearby_enemies")) else DeterministicTurnNarration

    with llm_client.narration_sampling_context(session, is_nsfw=is_nsfw):
        if stream_callback:
            result = await call_llm_json_stream(
                system_prompt=sys_prompt,
                user_prompt=user_prompt,
                on_narrative_token=stream_callback,
                temperature=retry_temp,
                is_nsfw=is_nsfw,
                response_model=retry_schema,
                system_zones=sys_zones,
            )
        else:
            result = await call_llm_json(
                system_prompt=sys_prompt,
                user_prompt=user_prompt,
                temperature=retry_temp,
                is_nsfw=is_nsfw,
                response_model=retry_schema,
                system_zones=sys_zones,
            )
    
    # Convert NarrationOutcome to dict
    raw_dict = dict(result) if hasattr(result, "keys") else (result.model_dump() if hasattr(result, "model_dump") else {})
    # Strict contract: narration pass only provides prose and choices, never alters mechanics or location
    allowed_keys = {"outcome_narrative", "next_narrative", "scene_title", "next_choices", "choices", "_is_fallback_narrative"}
    out = {k: v for k, v in raw_dict.items() if k in allowed_keys}
    split_out, split_nxt = game_engine.split_outcome_and_next_paragraphs(
        out.get("outcome_narrative") or "",
        out.get("next_narrative") or "",
    )
    if split_out != (out.get("outcome_narrative") or "").strip() or split_nxt != (out.get("next_narrative") or "").strip():
        out["outcome_narrative"] = split_out
        out["next_narrative"] = split_nxt

    lead_char_dict = actions[0].get("char", {}) if actions and isinstance(actions[0], dict) else {}
    session_for_echo = dict(session)
    session_for_echo["history"] = effective_history
    applied = snapshot.get("applied", {})
    party_for_retry = [(lead_char_dict, [])] if isinstance(lead_char_dict, dict) and lead_char_dict else []

    game_engine.sanitize_narrator_prose(
        out,
        session=session_for_echo,
        party=party_for_retry,
        actions=actions,
        present_npcs=applied.get("npcs_present") or session.get("current_npcs"),
    )

    try:
        from game_engine.pronoun_resolver import tag_narrative_pronouns
        retry_npcs = applied.get("npcs_present") or session.get("current_npcs")
        retry_dp = applied.get("dialogue_partner") or session.get("dialogue_partner")
        for _p_key in ("outcome_narrative", "next_narrative"):
            if out.get(_p_key) and isinstance(out[_p_key], str):
                out[_p_key] = tag_narrative_pronouns(
                    out[_p_key],
                    session=session,
                    party=party_for_retry,
                    npcs_present=retry_npcs,
                    dialogue_partner=retry_dp,
                )
    except Exception:
        pass

    try:
        raw_retry_choices = out.get("next_choices") if out.get("next_choices") is not None else out.get("choices")
        merged_retry_state = dict(applied)
        cleaned_retry = game_engine.build_hybrid_turn_choices(
            raw_retry_choices or [],
            session=session,
            party=party_for_retry,
            result=merged_retry_state,
            actions=actions,
        )
        out["next_choices"] = cleaned_retry
        out["choices"] = cleaned_retry
    except Exception as e:
        log.warning("Failed to clean retry choices: %s", e)

    return out

