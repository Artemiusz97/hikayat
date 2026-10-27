import json
import logging
import asyncio

import db
from models.llm_schemas import NarrationOutcome, DeterministicTurnNarration, DeterministicCombatNarration
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
- PROTAGONIST GENDER & PRONOUN FIDELITY: Never misgender the protagonist. If the protagonist is male, always use he/him/his (never she/her). If female, always use she/her/hers. When NPCs flirt or banter with the protagonist, ensure their romantic dialogue targets the protagonist's canon gender (e.g. female NPCs flirting with a male protagonist ask what he looks for in a woman/girl/partner, NEVER invert attraction to ask what he looks for in a guy).
- CANON RELATIONSHIP & VIRGINITY INTEGRITY: NPCs asked about their past romance, boyfriends, dating suitors, or sexual experience must speak the truth according to their profile. A virgin character with no past relationship history (empty ex_partners) must NEVER claim to have had past boyfriends, suitors, or practice juggling partners on their schedule.
- SPECIES & BIOLOGY FIDELITY: Strictly adhere to the protagonist's canonical race and biology. If the character is human, NEVER narrate animal traits such as animal ears twitching, tail wagging, purring, scales, or fur.
- ANTHROPOMORPHIC & BEASTFOLK SPECIES DIVERSITY: In beastfolk and furry scenarios, ensure rich and varied species distribution across students, staff, and club members. Do NOT over-index on rabbits or mice; actively incorporate avians/birds, felines (cats, tigers, cheetahs, lions), canines (wolves, foxes, fennecs), bears, and reptiles.
- STRICT PHYSICAL PRESENCE: ONLY depict characters physically present in the room according to the frozen state. DO NOT introduce or narrate physical actions for characters who are stationed elsewhere.
- CANON UNDERGARMENT & COMMANDO FIDELITY: Strictly adhere to each character's canonical undergarment state. If a character is wearing NO underwear / panties (Commando) or NO bra (Bra-less), when their skirt, dress, pants, or shirt is lifted, parted, or removed, they are completely bare underneath! Third-person narration and dialogue MUST NEVER narrate peeling back, sliding aside, snapping, or removing phantom panties, bras, or underwear when the character is commando or bra-less.
- NARRATOR RESTRAINT ON UNREVEALED INTIMATE TRAITS: Never describe an NPC's hidden intimate traits (such as underwear styles, secret erogenous spots, or intimate anatomy) before they have been revealed through player action, clothing removal, or intimacy progression.
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
    # Include Protagonist Character Sheet in context if available
    char_sheet_str = ""
    lead_char_obj = actions[0].get("char") if actions and isinstance(actions[0], dict) else None
    if not isinstance(lead_char_obj, dict) and session.get("user_id"):
        try:
            lead_char_obj = db.get_character(session["user_id"])
        except Exception:
            pass
    if isinstance(lead_char_obj, dict):
        inv = []
        if session.get("user_id"):
            try:
                inv = db.get_inventory(session["user_id"])
            except Exception:
                inv = []
        char_sheet_str = f"\n\nPROTAGONIST CHARACTER SHEET:\n{game_engine._character_sheet_text(lead_char_obj, inv)}"

    context_str = f"{scenario_str}\n\n{style_str}\n\n{known_world_str}{char_sheet_str}{contact_block}{phys_block_str}\n\nRECENT HISTORY:\n{history_str}"
    
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
    
    sys_prompt = NARRATION_SYSTEM_PROMPT.replace(
        "{actions_text}", actions_text
    ).replace(
        "{frozen_state_text}", frozen_state_text
    )
    
    # Ensure lead character gender is populated if available
    lead_char_obj = actions[0].get("char") if actions and isinstance(actions[0], dict) else None
    if not session.get("lead_character_gender") and isinstance(lead_char_obj, dict):
        session["lead_character_gender"] = lead_char_obj.get("gender", "male")

    from game_engine.prompt_layout import build_language_directive
    lang_dir = build_language_directive(session)
    if lang_dir:
        sys_prompt += f"\n\n{lang_dir}"
    
    # Check for conversational exit intent in retry pass
    from mechanics.narrative.intent import is_dialogue_exit_action
    has_exited_convo = any(is_dialogue_exit_action(a) for a in actions)
    departure_directive = ""
    if has_exited_convo:
        departure_directive = (
            "\n\n[CONVERSATIONAL DEPARTURE & SCENE TRANSITION DIRECTIVE]:\n"
            "The player has explicitly concluded the conversation, stepped away, or departed.\n"
            "- In `outcome_narrative`, narrate only the immediate parting gesture or departure (e.g. nodding, thanking them, stepping away). "
            "EVERY character present in the scene MUST STOP talking with the player! DO NOT have any NPCs continue or initiate conversation with the player this turn! DO NOT reopen the conversation!\n"
            "- In `next_narrative`, transition the scene forward into open exploration, room atmosphere, or next destination. NO NPC should be talking to the player.\n"
            "- In `choices`, generate OPEN EXPLORATION, room inspection, or travel choices. DO NOT generate active dialogue choices."
        )

    user_prompt = f"Context & Lore:\n{context_str}\n\nPlease generate the narration and next choices now based strictly on the frozen mechanics.{departure_directive}"
    
    # Temperature bump for manual retries (attempt 1 is auto-recovery, attempt 2+ is manual)
    base_temp = 0.7
    if attempt > 1:
        base_temp = min(1.2, base_temp + (attempt - 1) * 0.15)
        
    is_nsfw = uses_nsfw_model(session.get("scenario"))
    
    retry_schema = DeterministicCombatNarration if bool(snapshot.get("applied", {}).get("nearby_enemies")) else DeterministicTurnNarration

    if stream_callback:
        result = await call_llm_json_stream(
            system_prompt=sys_prompt,
            user_prompt=user_prompt,
            on_narrative_token=stream_callback,
            temperature=base_temp,
            is_nsfw=is_nsfw,
            response_model=retry_schema,
        )
    else:
        result = await call_llm_json(
            system_prompt=sys_prompt,
            user_prompt=user_prompt,
            temperature=base_temp,
            is_nsfw=is_nsfw,
            response_model=retry_schema,
        )
    
    # Convert NarrationOutcome to dict
    raw_dict = dict(result) if hasattr(result, "keys") else (result.model_dump() if hasattr(result, "model_dump") else {})
    # Strict contract: narration pass only provides prose and choices, never alters mechanics or location
    allowed_keys = {"outcome_narrative", "next_narrative", "scene_title", "next_choices", "choices", "_is_fallback_narrative"}
    out = {k: v for k, v in raw_dict.items() if k in allowed_keys}

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

