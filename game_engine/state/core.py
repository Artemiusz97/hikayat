from .constants import *
from .constants import _GOLD_GAIN_RE, _GOLD_LOSS_RE, _MAX_GOLD_LEAKAGE_PATCH, _DAMAGE_RE, _ITEM_GRANT_RE, _ITEM_BLOCKLIST
import db
import re
import json
import random
import logging
from config import LLM_PASS1_TIMEOUT
from scenario_data import is_nsfw_scenario
from game_engine.core import STATE_ARBITER_SCHEMA
import game_engine
from db import adb
import mechanics.narrative.event_handlers
from mechanics.narrative.events import bus, LocationChangedEvent, NPCSpawnedEvent, NPCStatusChangedEvent, ItemGiftedEvent, ItemGainedEvent, FactionLeadershipChangedEvent, QuestCompletedEvent

log = logging.getLogger(__name__)

def extract_scene_fields(
    data: dict,
    session: dict | None = None,
    default_narrative: str = "",
) -> tuple[list[dict], str, str, object, list]:
    """Canonical helper to extract and normalize choices, narrative, scene_title, dialogue_partner, and npcs from LLM scene/outcome dicts."""
    if not data or not isinstance(data, dict):
        data = {}

    raw_choices = (
        data.get("next_choices")
        or data.get("choices")
        or data.get("actions")
        or data.get("options")
        or data.get("suggested_actions")
        or data.get("next_actions")
        or []
    )
    normalized_choices = [
        c if isinstance(c, dict) else (c.model_dump(exclude_unset=True) if hasattr(c, "model_dump") else {"label": str(c)})
        for c in raw_choices if c
    ]

    next_narrative = str(
        data.get("next_narrative")
        or data.get("narrative")
        or data.get("outcome_narrative")
        or data.get("story")
        or data.get("scene_text")
        or data.get("description")
        or (session.get("narrative") if isinstance(session, dict) and default_narrative else "")
        or default_narrative
        or ""
    ).strip()

    scene_title = str(
        data.get("scene_title")
        or data.get("title")
        or data.get("name")
        or data.get("scene_name")
        or (session.get("scene_title") if isinstance(session, dict) else None)
        or "Hikayat"
    ).strip()

    partner_arg = (
        data.get("dialogue_partners")
        if data.get("dialogue_partners") is not None
        else data.get("dialogue_partner")
    )

    if data.get("npcs_present") is not None:
        npcs_arg = data.get("npcs_present")
    elif data.get("current_npcs") is not None:
        npcs_arg = data.get("current_npcs")
    elif isinstance(session, dict):
        npcs_arg = session.get("current_npcs", [])
    else:
        npcs_arg = []

    return normalized_choices, next_narrative, scene_title, partner_arg, npcs_arg

def get_combined_narrative(outcome: dict) -> str:
    """Canonical helper to extract and combine all narrative fields from an outcome dict."""
    if not outcome or not isinstance(outcome, dict):
        return ""
    return (
        str(outcome.get("outcome_narrative") or "") + " " +
        str(outcome.get("next_narrative") or "") + " " +
        str(outcome.get("narrative") or "")
    ).strip()

def is_check_success(check_obj, default_if_none: bool = True) -> bool:
    """Canonical evaluator for stat/skill check success across all engine structures.
    Safely handles CheckResult objects, dicts, and uppercase/lowercase tier strings.
    """
    if not check_obj:
        return default_if_none
    if hasattr(check_obj, "succeeded") and check_obj.succeeded is not None:
        return bool(check_obj.succeeded)
    if hasattr(check_obj, "is_success") and check_obj.is_success is not None:
        return bool(check_obj.is_success)
    if hasattr(check_obj, "tier") and check_obj.tier is not None:
        return str(check_obj.tier).lower() in ("success", "critical_success", "crit_success", "partial_success")
    if isinstance(check_obj, dict):
        if check_obj.get("succeeded") is not None:
            return bool(check_obj["succeeded"])
        if check_obj.get("is_success") is not None:
            return bool(check_obj["is_success"])
        tier_val = check_obj.get("tier")
        if tier_val is not None:
            return str(tier_val).lower() in ("success", "critical_success", "crit_success", "partial_success")
    return default_if_none

def reconcile_narrative_leakage(outcome: dict, party: list, actions: list | None = None) -> dict:
    """Post-LLM Audit Pass: scans outcome_narrative and next_narrative for
    explicit transactions (gold, damage, items) that the LLM described in
    prose but omitted from character_outcomes, then patches the outcome dict
    in-memory before any DB writes occur.

    Rules:
    - Gold: Patches when gold_change == 0 and a clear numeric transaction
      is mentioned in the narrative.
    - Damage: Only patches on failed/crit_fail checks, when hp_change == 0,
      and the narrative mentions a numeric damage figure.
    - Items: Patches when item names (>= 4 chars) are mentioned as given/found
      and are not already in items_gained, subject to a false-positive blocklist.
    - Combat turns: Skipped entirely - combat is fully deterministic via
      precompute_combat_turn/reconcile_combat_results and must not be touched.
    """
    # Safety coercion in case a Pydantic model slips through from a direct caller
    if getattr(outcome, "model_dump", None):
        outcome = outcome.model_dump(exclude_unset=False)
    if not isinstance(outcome, dict):
        return outcome
    if actions is None:
        actions = []

    # Never interfere with active combat turns - already deterministically resolved
    is_combat = bool(
        outcome.get("_combat_log") or
        outcome.get("_enemy_attack_notice") or
        game_engine.get_active_enemies(outcome)
    )
    if is_combat:
        return outcome

    narrative = get_combined_narrative(outcome)
    if not narrative:
        return outcome

    # Build list of party characters
    party_chars = []
    for p in party:
        char = p[0] if isinstance(p, (tuple, list)) else p
        if isinstance(char, dict):
            party_chars.append(char)
    if not party_chars:
        return outcome

    # Acting character is the first in party
    acting_char = party_chars[0]
    char_name = acting_char.get("name", "Hero")

    # Find or create the character_outcome entry for the acting character
    outcomes = outcome.get("character_outcomes") or []
    co = None
    for c in outcomes:
        if isinstance(c, dict) and c.get("name", "").lower() == char_name.lower():
            co = c
            break
    if co is None:
        co = {
            "name": char_name,
            "hp_change": 0,
            "mp_change": 0,
            "gold_change": 0,
            "items_gained": [],
            "items_lost": [],
            "status_effects": [],
        }
        outcome.setdefault("character_outcomes", []).append(co)

    patched_fields = []

    # ---- 1. Gold Leakage Audit ----
    if co.get("gold_change", 0) == 0:
        gain_match = _GOLD_GAIN_RE.search(narrative)
        loss_match = _GOLD_LOSS_RE.search(narrative)
        if gain_match:
            amount = min(int(gain_match.group(1)), _MAX_GOLD_LEAKAGE_PATCH)
            co["gold_change"] = amount
            patched_fields.append(f"gold_change=+{amount} ('{gain_match.group(0)}')")
        elif loss_match:
            amount = min(int(loss_match.group(1)), _MAX_GOLD_LEAKAGE_PATCH)
            co["gold_change"] = -amount
            patched_fields.append(f"gold_change=-{amount} ('{loss_match.group(0)}')")

    # ---- 2. Non-Combat Damage Leakage Audit ----
    # Only patch when the action failed - successes don't cause hazard damage
    is_failed_action = any(
        getattr(a.get("check"), "tier", "") in ("fail", "crit_fail")
        for a in actions
    )
    if is_failed_action and co.get("hp_change", 0) == 0:
        dmg_match = _DAMAGE_RE.search(narrative)
        if dmg_match:
            dmg = int(dmg_match.group(1))
            if 1 <= dmg <= 200:  # Sanity bounds: ignore implausible values
                co["hp_change"] = -dmg
                patched_fields.append(f"hp_change=-{dmg} ('{dmg_match.group(0)}')")

    # ---- 3. Item Grant Leakage Audit ----
    existing_gained_lower = [i.lower() for i in (co.get("items_gained") or [])]
    for raw_item in _ITEM_GRANT_RE.findall(narrative):
        clean = raw_item.strip().strip("'\"").title()
        clean_lower = clean.lower()
        if (
            len(clean) >= 4 and
            clean_lower not in _ITEM_BLOCKLIST and
            not any(block == w for w in clean_lower.split() for block in _ITEM_BLOCKLIST) and
            clean_lower not in existing_gained_lower
        ):
            co.setdefault("items_gained", []).append(clean)
            existing_gained_lower.append(clean_lower)
            patched_fields.append(f"items_gained='{clean}'")

    if patched_fields:
        log.info(
            "[LeakageGuard] Patched '%s' outcome: %s",
            char_name, " | ".join(patched_fields)
        )

    return outcome

from mechanics.world.locations import extract_movement_destination

def should_trigger_state_arbiter_pass(session: dict, actions: list, party: list = None) -> bool:
    """Evaluate whether this turn requires a high-reliability State Arbiter Pass (Pass 1).
    Routinely bypasses standard/routine turns to preserve fast latency and minimize token costs.
    """
    if not ENABLE_DYNAMIC_MULTIPASS:
        return False

    scen_key = session.get("scenario", "fantasy")
    cur_loc = session.get("current_location", "")

    # 1. Critical Failures or catastrophic fail-forward checks
    for a in actions:
        chk = a.get("check")
        if chk and getattr(chk, "tier", "") == "crit_fail":
            return True

    # 2. Zone/Establishment travel or movement transitions
    for a in actions:
        lbl = a.get("label", "")
        dest = extract_movement_destination(lbl, session.get("id", 0), current_zone=cur_loc, scen_key=scen_key)
        if dest:
            return True

    # 3. Multi-NPC summits (3+ NPCs in room)
    npcs = session.get("current_npcs") or []
    if len(npcs) >= 3:
        return True

    # 4. Dialogue exits or major conversational departures
    from mechanics.world.mobility import get_session_dialogue_partners
    partners = get_session_dialogue_partners(session)
    if partners:
        from mechanics.narrative.intent import is_conversational_exit
        for a in actions:
            lbl = str(a.get("label") or "")
            if is_conversational_exit(lbl):
                return True

    # 5. Pending story quest milestones or boss transitions
    if session.get("pending_story_milestone") or session.get("in_boss_phase_transition"):
        return True

    return False

async def execute_state_arbiter_pass(session: dict, party: list, actions: list, actions_text: str = "") -> dict | None:
    """Pass 1: Micro-State Arbiter.
    Quickly resolves mechanical state deltas, entity presence, and dramatic consequences.
    Uses LLM_UTILITY_MODEL and LLM_PASS1_TIMEOUT. On any timeout or error, returns None for fallback.
    """
    if not ENABLE_DYNAMIC_MULTIPASS:
        return None

    arbiter_system_prompt = (
        "You are the State Arbiter for the Hikayat RPG engine. Your ONLY job is to evaluate the mechanical and dramatic state transitions for this turn.\n"
        "Be concise, logical, and strictly adhere to check tiers:\n"
        "- 'Critical Failure' / 'Failure': Enforce FAIL-FORWARD complications (loss, traps, alarms, ambushes).\n"
        "- 'Success' / 'Critical Success': Enforce clean progress, discoveries, or advantages.\n"
        "- Track NPC departures: if an NPC leaves, walks away, or says goodbye, list them in departed_characters.\n"
        f"Respond with JSON matching this exact structure:\n{STATE_ARBITER_SCHEMA}"
    )

    cur_npcs = [game_engine._get_npc_name(n) for n in (session.get("current_npcs") or []) if n]
    
    # Check for active commitments involving current NPCs to allow the arbiter to resolve them
    from db.memory import get_active_commitments
    active_commitments = get_active_commitments(session.get("id"))
    relevant_commitments = []
    for c in active_commitments:
        # Include if the target is in the room or it's a general promise to someone present
        if (c["target_entity"] in cur_npcs or c["source_entity"] in cur_npcs or 
            c["target_entity"].lower() == "player" or c["source_entity"].lower() == "player"):
            relevant_commitments.append(f"ID {c['id']}: [{c['commitment_type'].upper()}] {c['source_entity']} -> {c['target_entity']} : {c['description']}")
    
    commitment_block = f"ACTIVE COMMITMENTS:\n" + "\n".join(relevant_commitments) if relevant_commitments else "ACTIVE COMMITMENTS: None"

    from mechanics.social.physical_state import build_physical_prompt_block
    phys_prompt = build_physical_prompt_block(
        session, party,
        is_combat=bool(game_engine.get_active_enemies(session)),
        is_nsfw=is_nsfw_scenario(session.get("scenario"))
    )

    arbiter_user_prompt = (
        f"SCENARIO: {session.get('scenario', 'fantasy')}\n"
        f"LOCATION: {session.get('current_location', 'Unknown')}\n"
        f"PARTY:\n{game_engine._party_sheet_text(party)}\n"
        f"CURRENT NPCS IN ROOM: {cur_npcs}\n"
        f"PHYSICAL CONTINUITY ANCHOR:\n{phys_prompt}\n\n"
        f"{commitment_block}\n"
        f"ACTIONS TAKEN:\n{actions_text}\n"
        "Evaluate the mechanical state changes and output ONLY the JSON object. Check if any ACTIVE COMMITMENTS were 'fulfilled_commitments' or 'broken_commitments' (output their integer IDs)."
    )

    try:
        result = await game_engine.call_llm_json(
            arbiter_system_prompt,
            arbiter_user_prompt,
            temperature=0.2,
            max_tokens=512,
            retries=0,
            is_nsfw=is_nsfw_scenario(session.get("scenario")),
            use_utility=True,
            timeout=LLM_PASS1_TIMEOUT
        )
        if isinstance(result, dict) and (
            result.get("director_reasoning") or 
            result.get("character_outcomes") or 
            result.get("departed_characters") or
            result.get("fail_forward_complication")
        ):
            return result
    except Exception as e:
        log.warning("State Arbiter Pass 1 timed out or encountered error: %s. Collapsing to code fallback.", e)

    return None

def should_trigger_social_arbiter_pass(session: dict, actions: list, party: list, pass2_result: dict) -> bool:
    """Evaluate whether Pass 3 is needed for this turn."""
    if not ENABLE_DYNAMIC_MULTIPASS:
        return False
        
    # Trigger if NPCs are present before or after the turn
    if session.get("current_npcs") or pass2_result.get("npcs_present") or pass2_result.get("npc_departures"):
        return True
        
    # Trigger if action has conversational intent
    for a in actions:
        lbl = str(a.get("label") or "").lower()
        if any(w in lbl for w in ("talk", "speak", "ask", "greet", "tell", "say", "flirt")):
            return True
            
    # Trigger if any quests are active in the session
    if session.get("story_quests") or session.get("side_quests"):
        return True
        
    # Trigger if narrative introduces someone
    nar = get_combined_narrative(pass2_result).lower()
    if any(w in nar for w in ("approaches", "stranger", "arrives", "appears", "meets")):
        return True
        
    return False

async def execute_social_arbiter_pass(session: dict, party: list, actions: list, actions_text: str, pass2_result: dict) -> dict | None:
    """Pass 3: Post-Turn Social & World Arbiter.
    Offloads relationships, lore generation, and deep profile processing from the main narrative loop.
    Uses LLM_UTILITY_MODEL.
    """
    if not ENABLE_DYNAMIC_MULTIPASS:
        return None

    from game_engine.core import SOCIAL_ARBITER_SCHEMA
    from models.llm_schemas import SocialArbiterOutcome

    arbiter_system_prompt = (
        "You are the Social & World Arbiter for the Hikayat RPG engine. Your ONLY job is to read the latest narrative outcome and "
        "extract the mechanical updates for relationships, new character generation, quest updates, and NPC memories.\n"
        "Be concise, logical, and STRICTLY adhere to the JSON schema.\n"
        f"Respond with JSON matching this exact structure:\n{SOCIAL_ARBITER_SCHEMA}"
    )

    cur_npcs = [game_engine._get_npc_name(n) for n in (pass2_result.get("npcs_present") or session.get("current_npcs") or []) if n]
    pass2_narrative = get_combined_narrative(pass2_result)

    arbiter_user_prompt = (
        f"SCENARIO: {session.get('scenario', 'fantasy')}\n"
        f"PARTY:\n{game_engine._party_sheet_text(party)}\n"
        f"CURRENT NPCS IN ROOM: {cur_npcs}\n"
        f"ACTIONS TAKEN:\n{actions_text}\n"
        f"NARRATIVE OUTCOME:\n{pass2_narrative}\n"
        "Extract the social and world state changes implied by the narrative and output ONLY the JSON object."
    )

    try:
        # We give it more tokens since it might generate deep profiles and quest updates
        result = await game_engine.call_llm_json(
            arbiter_system_prompt,
            arbiter_user_prompt,
            temperature=0.2,
            max_tokens=2048,
            retries=0,
            is_nsfw=is_nsfw_scenario(session.get("scenario")),
            use_utility=True,
            timeout=20.0,
            response_model=SocialArbiterOutcome
        )
        if getattr(result, "model_dump", None):
            result = result.model_dump(exclude_unset=False)
        if isinstance(result, dict):
            return result
    except Exception as e:
        log.warning("Social Arbiter Pass 3 timed out or encountered error: %s", e)

    return None

def apply_outcome(session_id: int, party: list, outcome, mp_already_spent: dict | None = None,
                    actions: list | None = None) -> dict:
  
      """Returns {user_id: [item_name, ...]} -- every item each character gained
      this turn, in the order the LLM listed them (duplicates preserved, so a
      caller can count "(xN)" for multiple copies of the same item). A user
      with no gains this turn is simply absent from the dict. This is purely
      additive: existing callers that ignore the return value are unaffected.
      """
      # Coerce Pydantic model to dict so all downstream .get() / [] calls work
      if getattr(outcome, "model_dump", None):
          outcome = outcome.model_dump(exclude_unset=False)
      if mp_already_spent is None:
          mp_already_spent = {}
      if actions is None:
          actions = []
  
      # Post-LLM Audit: patch any gold/damage/item transactions the LLM described
      # in narrative prose but omitted from character_outcomes. Runs before any DB writes.
      outcome = reconcile_narrative_leakage(outcome, party, actions)
  
  
      with db.UnitOfWork():
          party_uids = [char["user_id"] for char, _ in party]
          session = db.get_session(session_id)
          scen_key_curr = session.get("scenario", "fantasy") if session else "fantasy"
          game_engine._sanitize_outcome_person_names(outcome, session_id, scen_key_curr)
  
          items_gained_by_user: dict = {}
          _reduce_quests_and_waypoints(session_id, session, party_uids, outcome, actions, items_gained_by_user)
          scen_key = session.get("scenario", "fantasy") if session else "fantasy"

          is_combat = bool(outcome and (outcome.get("_combat_log") or outcome.get("_enemy_attack_notice") or game_engine.get_active_enemies(outcome)))
          first_char_id = party[0][0]["id"] if party else 0
          first_char_name = party[0][0].get("name", "Player") if party else "Player"
          _reduce_vitals_and_inventory(session_id, session, party, outcome, mp_already_spent, scen_key, is_combat, items_gained_by_user)
          _reduce_media_capture(session_id, session, party, outcome, actions, scen_key, items_gained_by_user)
          _reduce_entities_and_gifts(session_id, session, outcome, party, actions, is_combat, scen_key)
          _reduce_social_and_milestones(session_id, session, party, outcome, actions, scen_key, items_gained_by_user, first_char_id, first_char_name)
          _reduce_factions(session_id, session, outcome, party, first_char_id)
  
          _reduce_deterministic_waypoints(session_id, session, outcome, party_uids, actions)
          _reduce_physical_state_and_memories(session_id, session, outcome, party, scen_key, actions)
      # ── Background Digest Trigger ────────────────────────────────────────────
      # Schedule a non-blocking arc digest if an arc boundary was crossed this
      # turn (zone travel, dialogue exit, sub-quest completion, or history full).
      # This runs AFTER all DB writes so the digest captures a fully-committed state.
      try:
          session_for_digest = db.get_session(session_id)
          if session_for_digest:
              from mechanics.system.memory.digest import fire_digest_if_needed
              fire_digest_if_needed(
                  session=session_for_digest,
                  actions=actions or [],
                  outcome=outcome,
                  history_to_archive=session_for_digest.get("history") or [],
              )
      except Exception:
          pass  # digest is best-effort - never block the turn response
  
      return items_gained_by_user

def push_history(history: list, entry: str, limit: int | None = None) -> list:
    """
    Appends a new turn narrative to the session history.
    The default limit is RAW_HISTORY_LIMIT (4) from mechanics.system.memory.digest.
    """
    from mechanics.system.memory.digest import RAW_HISTORY_LIMIT
    import game_engine
    
    if limit is None:
        limit = RAW_HISTORY_LIMIT
        
    # Anti-cliche filtering
    if hasattr(game_engine, 'sanitize_comparative_cliches'):
        entry = game_engine.sanitize_comparative_cliches(entry)
    
    # De-echoing: don't push identical back-to-back entries
    if history and history[-1] == entry:
        return history
        
    new_hist = history + [entry]
    if len(new_hist) > limit:
        new_hist = new_hist[-limit:]
    return new_hist



from .reducers import _evaluate_npc_milestones, _reduce_quests_and_waypoints, _reduce_vitals_and_inventory, _reduce_factions, _reduce_deterministic_waypoints, _reduce_physical_state_and_memories, _reduce_entities_and_gifts, _reduce_media_capture
from .social import _reduce_social_and_milestones
