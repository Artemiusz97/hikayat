import json
import logging
import asyncio

import db
from models.llm_schemas import NarrationOutcome
from llm_client import call_llm_json, call_llm_json_stream
from scenario_data import is_nsfw_scenario, uses_nsfw_model
import game_engine

log = logging.getLogger(__name__)


NARRATION_SYSTEM_PROMPT = """You are a highly skilled interactive fiction engine (the "Narrator").
Your ONLY job right now is to regenerate the prose (the narrative description of what just happened and what is happening next) and the next available choices.

You MUST NOT change the mechanical outcome of the turn. The facts are absolute and frozen. You are just describing them in vivid, second-person prose according to the player's preferences.

## FROZEN STATE (Authoritative Facts)
The player took the following action(s):
{actions_text}

The engine already resolved the outcome and these are the unchangeable facts:
{frozen_state_text}

## YOUR TASK
1. 'outcome_narrative': Describe the immediate result of the NEW player's action(s). Write exactly what happens based on the frozen mechanics. NEVER repeat, re-state, or re-quote dialogue or events that already happened in previous turns.
2. 'next_narrative': Describe the current state of the scene right after the action is resolved. Detail the environment, who is still here, and the immediate atmosphere.
3. 'scene_title': A short 2-5 word title for the current situation.
4. 'next_choices': Propose 2-5 logical, contextual actions the player can take next, given the new situation.

## GUIDELINES
- STRICT PHYSICAL PRESENCE: ONLY depict characters physically present in the room according to the frozen state. DO NOT introduce or narrate physical actions for characters who are stationed elsewhere.
- FORWARD TEMPORAL MOMENTUM: Start immediately from the player's new action and move the clock forward. NEVER write a summary or recap paragraph of earlier conversation turns.
- Respect the verbosity and dialogue preferences.
- If characters died, describe their fall.
- If an item was gained, mention it naturally in the prose.
- Do NOT generate markdown formatting unless it's bold/italics for emphasis. No code blocks.
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
            lines.append(f" - {c_name}: HP {hp_c}, MP {mp_c}, Status Effects: {status}")
            
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
        lines.append(f"XP gained: {xp}")
        
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
        
    return "\n".join(lines)


async def run_narration_pass(session: dict, snapshot: dict, attempt: int = 1, stream_callback=None) -> dict:
    """
    Lightweight generation pass that ONLY rewrites narrative and choices,
    treating the provided snapshot's mechanical state as authoritative ground truth.
    """
    session_id = session.get("id", 0)
    
    # 1. Provide context (recent history, known world, scenario, style)
    raw_hist = list(session.get("history") or [])
    # CRITICAL: On a retry narration pass, the turn being retried is at history[-1],
    # so effective history leading up to the action must exclude it!
    effective_history = raw_hist[:-1] if raw_hist else []
    history_str = game_engine._history_text(effective_history, session_id=session_id)
    known_world_str = game_engine._known_world_text(
        session_id,
        session.get("current_location", ""),
        current_npcs=session.get("current_npcs", [])
    )
    style_str = game_engine._style_block(session)
    scenario_str = game_engine._scenario_block(session)
    
    # 2. Build actions text
    actions = snapshot.get("actions", [])
    action_lines = []
    for a in actions:
        tier_label = a.get("check", {}).get("tier_label", "Action") if isinstance(a.get("check"), dict) else getattr(a.get("check"), "tier_label", "Action")
        action_lines.append(f"[{tier_label}] {a.get('label')}")
    actions_text = "\n".join(action_lines)

    # 1B. Build contact & topic-aware grounding for present NPCs
    contact_lines = []
    from mechanics.social.genealogy import build_topic_aware_npc_context
    present_npcs = snapshot.get("applied", {}).get("npcs_present", []) or session.get("current_npcs", [])
    for n in present_npcs:
        n_name = n.get("name") if isinstance(n, dict) else str(n)
        if n_name:
            contact = db.get_contact(session_id, n_name)
            if contact:
                c_details = []
                c_track = contact.get("track", "platonic")
                c_details.append(f"Track: {c_track}")
                c_score = contact.get("relationship_score", 0)
                c_details.append(f"Affinity: {c_score}")
                topic_ctx = build_topic_aware_npc_context(
                    contact,
                    actions=actions,
                    session_history=effective_history,
                    scenario=session.get("scenario", "fantasy")
                )
                line = f"  * {n_name}: " + " | ".join(c_details)
                if topic_ctx:
                    line += "\n" + topic_ctx
                contact_lines.append(line)

    contact_block = ""
    if contact_lines:
        contact_block = "\n\nKNOWN CHARACTER CONTEXT & RELATIONSHIPS:\n" + "\n".join(contact_lines)

    # 1C. Build physical & intimate state continuity block
    phys_block_str = ""
    try:
        from mechanics.social.physical_state import build_physical_prompt_block
        lead_char_obj = actions[0].get("char") if actions and isinstance(actions[0], dict) else None
        party_for_phys = [(lead_char_obj, [])] if isinstance(lead_char_obj, dict) else []
        phys_block = build_physical_prompt_block(
            session,
            party_for_phys,
            is_combat=bool(snapshot.get("applied", {}).get("nearby_enemies")),
            is_nsfw=is_nsfw_scenario(session.get("scenario")),
            actions=actions,
        )
        if phys_block:
            phys_block_str = f"\n\n[ACTIVE PHYSICAL & INTIMATE STATE CONTINUITY]:\n{phys_block}"
    except Exception:
        pass

    context_str = f"{scenario_str}\n\n{style_str}\n\n{known_world_str}{contact_block}{phys_block_str}\n\nRECENT HISTORY:\n{history_str}"
    
    # 3. Build frozen state text
    frozen_state_text = _build_frozen_state_text(snapshot)
    
    sys_prompt = NARRATION_SYSTEM_PROMPT.replace(
        "{actions_text}", actions_text
    ).replace(
        "{frozen_state_text}", frozen_state_text
    )
    
    # Check for conversational exit intent in retry pass
    from mechanics.narrative.intent import is_conversational_exit
    has_exited_convo = any(is_conversational_exit(str(a.get("label") or "")) for a in actions)
    departure_directive = ""
    if has_exited_convo:
        departure_directive = (
            "\n\n[CONVERSATIONAL DEPARTURE & SCENE TRANSITION DIRECTIVE]:\n"
            "The player has explicitly concluded the conversation and excused themselves or departed.\n"
            "- In `outcome_narrative`, narrate only the immediate parting gesture or departure (e.g. nodding, thanking them, stepping away). "
            "DO NOT reopen the conversation, do not renegotiate previously agreed deals, and do not repeat previous dialogue.\n"
            "- In `next_narrative`, transition the scene forward to the new environment, surrounding atmosphere, or next destination."
        )

    user_prompt = f"Context & Lore:\n{context_str}\n\nPlease generate the narration and next choices now based strictly on the frozen mechanics.{departure_directive}"
    
    # Temperature bump for manual retries (attempt 1 is auto-recovery, attempt 2+ is manual)
    base_temp = 0.7
    if attempt > 1:
        base_temp = min(1.2, base_temp + (attempt - 1) * 0.15)
        
    is_nsfw = uses_nsfw_model(session.get("scenario"))
    
    if stream_callback:
        result = await call_llm_json_stream(
            system_prompt=sys_prompt,
            user_prompt=user_prompt,
            on_narrative_token=stream_callback,
            temperature=base_temp,
            is_nsfw=is_nsfw,
            response_model=NarrationOutcome,
        )
    else:
        result = await call_llm_json(
            system_prompt=sys_prompt,
            user_prompt=user_prompt,
            temperature=base_temp,
            is_nsfw=is_nsfw,
            response_model=NarrationOutcome,
        )
    
    # Convert NarrationOutcome to dict
    raw_dict = dict(result) if hasattr(result, "keys") else (result.model_dump() if hasattr(result, "model_dump") else {})
    # Strict contract: narration pass only provides prose and choices, never alters mechanics or location
    allowed_keys = {"outcome_narrative", "next_narrative", "scene_title", "next_choices", "choices", "_is_fallback_narrative"}
    out = {k: v for k, v in raw_dict.items() if k in allowed_keys}

    # Sanitize narrative echoes on retry output
    lead_char_dict = actions[0].get("char", {}) if actions and isinstance(actions[0], dict) else {}
    lead_char_name = lead_char_dict.get("name", "You") if isinstance(lead_char_dict, dict) else "You"
    act_label = actions[0].get("label", "") if actions else ""
    session_for_echo = dict(session)
    session_for_echo["history"] = effective_history
    session_for_next = dict(session_for_echo)
    applied = snapshot.get("applied", {})
    if out.get("outcome_narrative"):
        out["outcome_narrative"] = game_engine.sanitize_meta_objective_leaks(out["outcome_narrative"])
        out["outcome_narrative"] = game_engine.sanitize_narrative_context_echo(
            out["outcome_narrative"], session_for_echo, action_label=act_label, character_name=lead_char_name
        )
        out["outcome_narrative"] = game_engine.sanitize_absent_npc_hallucinations(
            out["outcome_narrative"], session=session_for_echo, result=applied, actions=actions
        )
        session_for_next["narrative"] = out["outcome_narrative"]
    if out.get("next_narrative"):
        out["next_narrative"] = game_engine.sanitize_meta_objective_leaks(out["next_narrative"])
        out["next_narrative"] = game_engine.sanitize_narrative_context_echo(
            out["next_narrative"], session_for_next, action_label="", character_name=lead_char_name, is_next_narrative=True
        )
        out["next_narrative"] = game_engine.sanitize_absent_npc_hallucinations(
            out["next_narrative"], session=session_for_echo, result=applied, actions=actions
        )

    # Clean and validate retry choices against current session/physical state
    try:
        from game_engine.choices_cleaner import clean_choices_impl
        raw_retry_choices = out.get("next_choices") if out.get("next_choices") is not None else out.get("choices")
        if raw_retry_choices is not None:
            dlg_p = (
                applied.get("dialogue_partners")
                or applied.get("dialogue_partner")
                or session.get("dialogue_partners")
                or session.get("dialogue_partner")
            )
            eff_loc = applied.get("location") or session.get("current_location", "")
            cleaned_retry = clean_choices_impl(
                None,
                choices=raw_retry_choices,
                scenario=session.get("scenario", "fantasy"),
                location=eff_loc,
                char=lead_char_dict if isinstance(lead_char_dict, dict) and lead_char_dict else None,
                dialogue_partner=dlg_p,
                session_id=session_id,
            )
            out["next_choices"] = cleaned_retry
            out["choices"] = cleaned_retry
    except Exception:
        pass

    return out

