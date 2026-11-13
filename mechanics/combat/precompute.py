from __future__ import annotations
"""
Turn precomputation, action intent classification, Dynamic Threat targeting,
Boss action telegraphing, ephemeral deck caching, and LLM prompt schemas.
"""
import json
import logging
import random
import re
from typing import Any, Dict, List, Optional, Set, Tuple

import db
import scenario_data
from scenario_data import is_mechanic_enabled
from mechanics.combat.spells import calculate_spell_damage

from .formulas import (
    calculate_opposed_dc,
    get_elemental_multiplier,
    try_inflict_status,
    calculate_tactical_damage,
    calculate_turn_damage,
    tick_status_timers,
)
from .sparring import (
    is_sparring_monster,
    resolve_sparring_defeat,
    make_sparring_monster,
    call_faction_reinforcements,
)
from .status_effects import (
    apply_status_effect,
    tick_status_instance_timers,
    format_status_badge,
    normalize_status_effect,
)
from .types import (
    CombatAction,
    CombatThreatLedger,
    CombatantState,
    BossTelegraphState,
    StatusEffectInstance,
    get_combatant_stat,
)
from .reconcile import _enemy_has_unsealed_tether, cleanup_anomalous_combat_session_state

logger = logging.getLogger(__name__)

_get_entity_stat = get_combatant_stat


def update_threat_on_action(
    threat_matrix: Dict[str, Dict[str, float]],
    acting_id: str,
    action_type: str,
    target_enemy_ids: List[str],
    all_living_enemy_ids: List[str],
    damage_dealt: int = 0,
    effective_healing: int = 0,
    is_taunt: bool = False,
    sticky_taunts: Optional[Dict[str, Dict[str, Any]]] = None,
) -> None:
    """Updates dynamic threat scores across living enemies based on damage, healing, or taunts.

    Formula:
      - Damage: +1.0 * damage_dealt on targeted enemies
      - Effective Healing: +0.75 * effective_healing distributed evenly across all living enemies
      - Taunt: +100.0 spike on targeted enemies + sticky taunt override for 2 turns
    """
    if damage_dealt > 0:
        for eid in target_enemy_ids:
            eid_str = str(eid)
            threat_matrix.setdefault(eid_str, {})[acting_id] = (
                threat_matrix.get(eid_str, {}).get(acting_id, 0.0) + (damage_dealt * 1.0)
            )

    if effective_healing > 0 and all_living_enemy_ids:
        heal_threat = (effective_healing * 0.75) / max(1, len(all_living_enemy_ids))
        for eid in all_living_enemy_ids:
            eid_str = str(eid)
            threat_matrix.setdefault(eid_str, {})[acting_id] = (
                threat_matrix.get(eid_str, {}).get(acting_id, 0.0) + round(heal_threat, 2)
            )

    if is_taunt:
        for eid in target_enemy_ids:
            eid_str = str(eid)
            threat_matrix.setdefault(eid_str, {})[acting_id] = (
                threat_matrix.get(eid_str, {}).get(acting_id, 0.0) + 100.0
            )
            if sticky_taunts is not None:
                sticky_taunts[eid_str] = {
                    "target_id": acting_id,
                    "remaining_turns": 2,
                }


def resolve_threat_target(
    enemy_id: str,
    living_party_actors: List[Dict[str, Any]],
    threat_matrix: Dict[str, Dict[str, float]],
    sticky_taunts: Optional[Dict[str, Dict[str, Any]]] = None,
) -> Optional[Dict[str, Any]]:
    """Resolves which party actor an enemy targets based on sticky taunts and dynamic threat scores."""
    if not living_party_actors:
        return None

    eid = str(enemy_id)

    def _cand_keys(a: Dict[str, Any]) -> Set[str]:
        keys = set()
        for k in ("name", "id", "user_id", "npc_id"):
            val = a.get(k)
            if val is not None:
                s_val = str(val).strip()
                if s_val and s_val.lower() != "none":
                    keys.add(s_val)
        return keys

    # 1. Sticky Taunt override
    if sticky_taunts and eid in sticky_taunts:
        taunt_id = str(sticky_taunts[eid].get("target_id", ""))
        for a in living_party_actors:
            if taunt_id in _cand_keys(a):
                return a

    # 2. Highest threat score
    enemy_threats = threat_matrix.get(eid, {})
    if enemy_threats:
        best_actor = None
        best_score = -1.0
        for a in living_party_actors:
            cand = _cand_keys(a)
            score = max((enemy_threats.get(k, 0.0) for k in cand), default=0.0)
            if score > best_score:
                best_score = score
                best_actor = a
        if best_actor is not None and best_score > 0:
            return best_actor

    # 3. Default fallback: None, allowing Archetype-aware targeting to select target
    return None


def arm_boss_telegraph(
    enemy: Dict[str, Any],
    turn_count: int,
    boss_telegraph_state: Dict[str, Any],
) -> Optional[Dict[str, Any]]:
    """Arms a telegraphed supreme boss move if conditions (turn cadence or <50% HP) are met."""
    if not isinstance(enemy, dict):
        return None

    hp = int(enemy.get("hp", 100))
    if hp <= 0:
        return None

    is_boss = bool(
        enemy.get("is_boss")
        or int(enemy.get("tier_rank", 1) or 1) >= 4
        or "boss" in str(enemy.get("archetype", "")).lower()
        or "boss" in str(enemy.get("combat_archetype", "")).lower()
    )
    if not is_boss:
        return None

    if enemy.get("telegraphed_skill"):
        return enemy["telegraphed_skill"]

    hp = int(enemy.get("hp", 100))
    max_hp = int(enemy.get("max_hp", 100))
    cadence_met = (turn_count > 0 and turn_count % 3 == 0) or (hp <= 0.5 * max_hp and not enemy.get("_phase2_telegraphed"))

    if not cadence_met:
        return None

    if hp <= 0.5 * max_hp:
        enemy["_phase2_telegraphed"] = True

    threshold = max(10, int(0.15 * max_hp))
    skill_name = enemy.get("supreme_skill_name") or f"{enemy.get('name', 'Boss')}'s Cataclysmic Onslaught"
    label = enemy.get("supreme_skill_label") or f"charging up an earth-shattering blow ({skill_name})"

    telegraph = {
        "enemy_id": str(enemy.get("id") or enemy.get("name")),
        "skill_name": skill_name,
        "telegraphed_label": label,
        "interrupt_threshold": threshold,
        "accumulated_interrupt_damage": 0,
        "damage_mult": 1.75,
        "turns_remaining": 1,
    }
    enemy["telegraphed_skill"] = telegraph
    boss_telegraph_state[str(enemy.get("id") or enemy.get("name"))] = telegraph
    return telegraph


def check_boss_telegraph_interrupt(
    enemy: Dict[str, Any],
    accumulated_damage: int,
    boss_telegraph_state: Dict[str, Any],
    combat_log: Optional[List[str]] = None,
) -> bool:
    """Checks if accumulated party damage interrupts the boss's telegraphed attack and inflicts Staggered."""
    telegraph = enemy.get("telegraphed_skill")
    if not telegraph:
        return False

    threshold = telegraph.get("interrupt_threshold", 9999)
    if accumulated_damage >= threshold:
        enemy["telegraphed_skill"] = None
        eid = str(enemy.get("id") or enemy.get("name"))
        boss_telegraph_state.pop(eid, None)

        apply_status_effect(
            enemy,
            {
                "name": "Staggered",
                "category": "combat",
                "duration_type": "turns",
                "remaining_duration": 1,
                "max_duration": 1,
                "duration": 1,
                "intensity_stacks": 1,
                "potency": 0.0,
                "metadata": {"damage_taken_mult": 1.25, "stagger_vulnerable": True},
            },
            source="party_interrupt",
        )
        if combat_log is not None:
            enemy_name = enemy.get("name", "The foe")
            combat_log.append(
                f"⚡ **CRITICAL INTERRUPTION!** The concentrated assault shatters **{enemy_name}**'s stance! "
                f"Its deadly strike is aborted and it is **Staggered**!"
            )
        return True
    return False

COMBAT_SYSTEM_PROMPT = """You are the Game Master in COMBAT ENCOUNTER state.
Active Hostile Enemies are attacking the party!
RULES:
- Every choice in `next_choices` MUST be an immediate, tactical action addressing the CURRENT state of the enemy.
- Do NOT offer passive exploration or room investigation choices while combat is active.
- DYNAMIC CHOICE VARIETY:
  * The 4 choices in `next_choices` MUST change and adapt dynamically every turn based on the enemy's current injuries, posture, and tactical complications narrated in `outcome_narrative` & `next_narrative`.
  * NEVER generate identical choice labels or repeated item actions from previous turns.
  * Offer a diverse mix of tactical approaches across DIFFERENT stats (STR, AGI, END, INT, PER, CHA, LUK):
    - Melee / Weapon Strike (STR/AGI)
    - Ranged / Firearms (PER/AGI)
    - Environmental / Ley-Line / Spell Trap (INT/PER)
    - Weakness Exploit / Anatomical Target (INT/PER)
    - Taunt / Intimidation / Distraction (CHA)
    - Guard / Parry / Brace (END)
    - Tactical Dodge / Flank / Counter (AGI/LUK)
- STRICT IMMERSION RULE (NO NUMBERS / STATS IN NARRATIVE):
  * NEVER write raw mechanical stats, numeric HP values, roll numbers, or damage point numbers inside `outcome_narrative` or `next_narrative`.
  * STRICTLY PROHIBITED in story prose: "75/100 HP", "25 points of force", "loses 9 HP, dropping to 51/60", "INT check success".
  * Describe ALL injuries, damage, and stamina purely through immersive physical & sensory descriptions (e.g., "splintered wooden torso", "heavy crack against her ribs", "staggered but holding firm").
  * All numeric HP changes and resource tracking belong strictly in `character_outcomes` and UI embeds, NEVER in the story prose!
- ENEMY HEALTH & DEFEAT RULES:
  * Read the DETERMINISTIC COMBAT RESULT directive carefully for the enemy's health status!
  * IF THE ENEMY HAS HP REMAINING (HP > 0): The enemy is STILL ALIVE, STANDING, AND FIGHTING. Describe it as wounded, staggered, or damaged, but STILL ACTIVE and attacking. Do NOT narrate its death, explosion, collapse, or destruction.
  * IF THE DIRECTIVE DECLARES "ENEMY DEFEATED" (HP <= 0): You MUST narrate the enemy's complete collapse, destruction, or death in this turn's narrative.
  * When an enemy is vanquished (HP 0), generate dynamic post-combat exploration choices in `next_choices`.
- NO INVESTIGATION CLUES IN COMBAT: Do NOT generate or discover new investigation clues or story notes during active combat. Focus purely on immediate tactical combat actions.
- Status Effects: `status_effects` for characters/enemies MUST be short 1-3 word tags (e.g., "Bleeding", "Stunned", "Prone", "Poisoned"). NO narrative action phrases. Prune when resolved (max 4).
- If a player check fails, narrate the enemy retaliating with physical or magical HP damage.
- The player characters and enemies are locked in a life-or-death struggle. Make descriptions visceral and high-stakes.
"""

COMBAT_CHOICE_SCHEMA = {
    "type": "object",
    "properties": {
        "outcome_narrative": {
            "type": "string",
            "description": "Dynamic, visceral story about the combat outcomes and enemy retaliation."
        },
        "next_choices": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "label": {"type": "string", "description": "Specific action text incorporating player's equipped items."},
                    "stat": {"type": "string", "enum": ["STR", "AGI", "END", "INT", "PER", "CHA", "LUK"]},
                    "requirement": {"type": "integer", "description": "Difficulty from 2 to 12"},
                    "choice_type": {
                        "type": "string",
                        "enum": [
                            "MELEE_SLASHING_PIERCING",
                            "MELEE_BLUNT",
                            "RANGED_ATTACK",
                            "MAGIC_ATTACK",
                            "ENVIRONMENTAL_TRAP",
                            "WEAKNESS_EXPLOIT",
                            "DIPLOMACY_TAUNT",
                            "DEFENSIVE_GUARD",
                            "EVADE_TACTICAL_FLEE"
                        ]
                    },
                    "incursion_action": {
                        "type": "string",
                        "description": "Optional deterministic incursion action key when resolving an anomalous breach."
                    }
                },
                "required": ["label", "stat", "requirement", "choice_type"]
            },
            "minItems": 4,
            "maxItems": 7,
            "description": "Provide 4-7 distinct combat choices. Note: Python will replace these with code-driven choices — just output valid choices."
        },
        "choices": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "label": {"type": "string"},
                    "stat": {"type": "string"},
                    "requirement": {"type": "integer"},
                    "incursion_action": {"type": "string"}
                }
            }
        },
        "nearby_enemies": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "name": {"type": "string"},
                    "level": {"type": "integer"},
                    "hp": {"type": "integer"},
                    "max_hp": {"type": "integer"}
                }
            }
        },
        "character_outcomes": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "name": {"type": "string"},
                    "hp_change": {"type": "integer"},
                    "mp_change": {"type": "integer"},
                    "gold_change": {"type": "integer"},
                    "items_gained": {"type": "array", "items": {"type": "string"}},
                    "items_lost": {"type": "array", "items": {"type": "string"}},
                    "status_effects": {"type": "array", "items": {"type": "string"}}
                }
            }
        },
        "image_prompt": {
            "type": "string",
            "description": "Short (1-2 sentence) visual description of the combat scene."
        }
    },
    "required": ["outcome_narrative", "next_choices"]
}

def is_in_combat(session: dict) -> bool:
    """Return True ONLY if tactical_combat is allowed for scenario AND hostiles are present."""
    if not session:
        return False
    scen_key = session.get("scenario", "fantasy")
    import game_engine
    has_hostiles = bool(game_engine.get_active_enemies(session))
    return is_mechanic_enabled(scen_key, "tactical_combat") and has_hostiles

def get_combat_prompt_and_schema(session: dict, party: list):
    """Returns specialized prompt & schema for combat turns."""
    return COMBAT_SYSTEM_PROMPT, COMBAT_CHOICE_SCHEMA

from .types import get_combatant_stat
_get_entity_stat = get_combatant_stat

def precompute_combat_turn(session: dict, party: list, actions: list) -> dict:
    """
    Called before LLM generation. Executes a Unified 3-Phase Tactical Combat Round:
    Phase 1: Active Player Action vs Enemy (Deals player damage to targeted enemy)
    Phase 2: Friendly Allies Actions (Automated companions & party members target living enemies)
    Phase 3: Enemy Actions (Living enemies randomly target living allies: player or companions)
    """
    from mechanics.combat.enemies import build_enemy_stat_sheet, build_companion_stat_sheet
    has_hostiles = session.get("nearby_enemies", [])
    if not has_hostiles:
        return {}

    enemies = [dict(m) for m in has_hostiles]
    for m in enemies:
        if not m.get("stats") or not isinstance(m.get("stats"), dict):
            m["stats"] = build_enemy_stat_sheet(m.get("level") or 1, m.get("archetype") or "Brute")
        if "max_hp" not in m:
            m["max_hp"] = 100
        if "hp" not in m:
            m["hp"] = m["max_hp"]

    # 1. Gather all party players
    player_chars = []
    for p in party:
        char_obj = p[0] if isinstance(p, (tuple, list)) else p
        if isinstance(char_obj, dict):
            se = char_obj.get("status_effects")
            if isinstance(se, str):
                try:
                    char_obj["status_effects"] = json.loads(se) if se.strip().startswith("[") else ([se] if se.strip() else [])
                except Exception:
                    char_obj["status_effects"] = [se] if se.strip() else []
            elif not isinstance(se, list):
                char_obj["status_effects"] = []
            player_chars.append(char_obj)

    acting_char_data = player_chars[0] if player_chars else {}
    acting_char_name = acting_char_data.get("name", "Hero")
    player_max_hp = acting_char_data.get("max_hp", 100)
    player_luk_val = acting_char_data.get("luk", 5)

    # 2. Gather all friendly NPC companions from session["party_npcs"] + eligible session["current_npcs"]
    import scenario_data as _sd_cbt
    is_anom_combat = bool(isinstance(session, dict) and _sd_cbt.is_anomalous_incursions_scenario(session.get("scenario", "")))
    sess_id_cbt = int(session.get("id") or 0) if isinstance(session, dict) else 0
    scen_cbt = str(session.get("scenario") or "fantasy") if isinstance(session, dict) else "fantasy"
    lead_lvl_cbt = int(acting_char_data.get("level", 1) or 1)
    from mechanics.combat.awakened_resonance import (
        apply_stability_and_break,
        compute_attribute_matchup_modifiers,
        compute_stability_shred,
        ensure_autonomous_construct,
        get_starting_encounter_pips,
        init_enemy_stability_profile,
        tick_enemy_breach_recovery,
        update_encounter_pips,
    )
    from mechanics.combat.spells.awakened_kits import (
        derive_default_3axis,
        get_awakened_basic_strike,
        normalize_anomalous_attribute,
    )
    if is_anom_combat:
        for _em in enemies:
            init_enemy_stability_profile(_em)

    # Phase 3 Combat Evolution: Dynamic Threat Ledger & Boss Telegraph Initialization
    threat_ledger: Dict[str, Any] = session.setdefault("combat_threat_ledger", {})
    if not isinstance(threat_ledger, dict):
        threat_ledger = {}
        session["combat_threat_ledger"] = threat_ledger
    threat_matrix: Dict[str, Dict[str, float]] = threat_ledger.setdefault("threat_matrix", {})
    sticky_taunts: Dict[str, Dict[str, Any]] = threat_ledger.setdefault("sticky_taunts", {})

    boss_telegraph_state: Dict[str, Any] = session.setdefault("combat_boss_telegraph", {})
    if not isinstance(boss_telegraph_state, dict):
        boss_telegraph_state = {}
        session["combat_boss_telegraph"] = boss_telegraph_state

    # Check and arm boss telegraphs for eligible bosses
    turn_count_cbt = int(session.get("turn_count", 0) or 0)
    for _em in enemies:
        arm_boss_telegraph(_em, turn_count_cbt, boss_telegraph_state)


    friendly_npcs = []
    seen_ally_names: set[str] = set()
    active_party_npcs = []
    if isinstance(session, dict):
        raw_p_npcs = session.get("party_npcs")
        if raw_p_npcs is None and sess_id_cbt:
            try:
                raw_p_npcs = db.get_session_party_npcs(sess_id_cbt)
            except Exception:
                raw_p_npcs = []
        active_party_npcs = [dict(p) for p in (raw_p_npcs or []) if isinstance(p, dict)]

    for p_comp in active_party_npcs:
        p_name_c = str(p_comp.get("name") or "").strip()
        if not p_name_c:
            continue
        if is_anom_combat:
            from mechanics.social.anomalous_npc_tags import hydrate_anomalous_npc_profile
            prof = hydrate_anomalous_npc_profile(
                p_comp,
                session_id=sess_id_cbt,
                scen_key=scen_cbt,
                player_level=lead_lvl_cbt,
                is_party_companion=True,
            )
            p_comp.setdefault("anomalous_npc_tag", prof["anomalous_npc_tag"])
            p_comp.setdefault("is_special_agent", prof["is_special_agent"])
            p_comp.setdefault("agent_tier", prof["agent_tier"])
            p_comp.setdefault("agent_class", prof["agent_class"])
            p_comp.setdefault("innate_abilities", prof["innate_abilities"])
            p_comp.setdefault("weapon_profile", prof["weapon_profile"])
            if not p_comp.get("stats") or not isinstance(p_comp.get("stats"), dict):
                p_comp["stats"] = prof["stats"]
            if p_comp.get("max_hp", 0) < 100 and prof["anomalous_npc_tag"] in ("special_agent", "folklore_villager"):
                p_comp["max_hp"] = prof["max_hp"]
                p_comp["hp"] = min(prof["max_hp"], max(p_comp.get("hp", prof["hp"]), prof["hp"]))
                p_comp["max_mp"] = prof["max_mp"]
                p_comp["mp"] = min(prof["max_mp"], max(p_comp.get("mp", prof["mp"]), prof["mp"]))
            p_comp.setdefault("attribute", prof.get("attribute"))
            p_comp.setdefault("combat_archetype", prof.get("combat_archetype"))
            p_comp.setdefault("ability_medium", prof.get("ability_medium"))
        else:
            if not p_comp.get("stats") or not isinstance(p_comp.get("stats"), dict):
                p_comp["stats"] = build_companion_stat_sheet(p_comp.get("level", 1), p_comp.get("archetype", "Companion"))
            if "max_hp" not in p_comp:
                p_comp["max_hp"] = p_comp.get("hp", 50)
            if "hp" not in p_comp:
                p_comp["hp"] = p_comp["max_hp"]
        p_comp["_is_party_npc"] = True
        friendly_npcs.append(p_comp)
        seen_ally_names.add(p_name_c.lower())

    current_npcs = [dict(npc) for npc in (session.get("current_npcs") or []) if isinstance(npc, dict)]
    for npc in current_npcs:
        n_nm = str(npc.get("name") or "").strip()
        if not n_nm or n_nm.lower() in seen_ally_names:
            continue
        if npc.get("is_summon"):
            if not npc.get("stats") or not isinstance(npc.get("stats"), dict):
                npc["stats"] = build_companion_stat_sheet(npc.get("level", 1), npc.get("archetype", "Companion"))
            if "max_hp" not in npc:
                npc["max_hp"] = npc.get("hp", 50)
            if npc.get("level") is None:
                npc["level"] = 1
            friendly_npcs.append(npc)
            seen_ally_names.add(n_nm.lower())
            continue
        if is_anom_combat:
            from mechanics.social.anomalous_npc_tags import (
                TAG_CIVILIAN,
                TAG_FOLKLORE_VILLAGER,
                TAG_SPECIAL_AGENT,
                hydrate_anomalous_npc_profile,
                is_civilian_forced_to_fight_as_ally,
            )
            prof_n = hydrate_anomalous_npc_profile(
                npc,
                session_id=sess_id_cbt,
                scen_key=scen_cbt,
                player_level=lead_lvl_cbt,
                is_party_companion=False,
            )
            npc["anomalous_npc_tag"] = prof_n["anomalous_npc_tag"]
            npc["is_special_agent"] = prof_n["is_special_agent"]
            if prof_n["anomalous_npc_tag"] in (TAG_SPECIAL_AGENT, TAG_FOLKLORE_VILLAGER):
                if npc.get("hp") is None:
                    npc["hp"] = prof_n["hp"]
                npc["max_hp"] = prof_n["max_hp"]
                if npc.get("mp") is None:
                    npc["mp"] = prof_n["mp"]
                npc["max_mp"] = prof_n["max_mp"]
                npc["stats"] = npc.get("stats") or prof_n["stats"]
                if npc.get("level") is None:
                    npc["level"] = prof_n.get("level") or 1
                npc["agent_tier"] = prof_n["agent_tier"]
                npc["agent_class"] = prof_n["agent_class"]
                npc["innate_abilities"] = prof_n["innate_abilities"]
                npc["weapon_profile"] = prof_n["weapon_profile"]
                npc["attribute"] = prof_n.get("attribute")
                npc["combat_archetype"] = prof_n.get("combat_archetype")
                npc["ability_medium"] = prof_n.get("ability_medium")
                if prof_n["anomalous_npc_tag"] == TAG_FOLKLORE_VILLAGER:
                    npc["is_folklore_villager"] = True
                    npc["is_beast_companion"] = bool(prof_n.get("is_beast_companion"))
                    npc["folklore_village"] = prof_n.get("folklore_village")
                friendly_npcs.append(npc)
                seen_ally_names.add(n_nm.lower())
            elif prof_n["anomalous_npc_tag"] == TAG_CIVILIAN:
                # Civilians: 100 HP / 0 MP, zero abilities; fight only if armed role, cornered, or explicitly in combat
                if npc.get("hp") is not None or is_civilian_forced_to_fight_as_ally(npc, session):
                    npc["max_hp"] = 100
                    if npc.get("hp") is None:
                        npc["hp"] = 100
                    else:
                        npc["hp"] = min(100, int(npc["hp"]))
                    npc["mp"] = 0
                    npc["max_mp"] = 0
                    if npc.get("level") is None:
                        npc["level"] = 1
                    npc["innate_abilities"] = []
                    npc["stats"] = npc.get("stats") or prof_n["stats"]
                    npc["weapon_profile"] = npc.get("weapon_profile") or prof_n["weapon_profile"]
                    friendly_npcs.append(npc)
                    seen_ally_names.add(n_nm.lower())
        elif npc.get("hp") is not None:
            if not npc.get("stats") or not isinstance(npc.get("stats"), dict):
                npc["stats"] = build_companion_stat_sheet(npc.get("level", 1), npc.get("archetype", "Companion"))
            if "max_hp" not in npc:
                npc["max_hp"] = npc.get("hp", 50)
            if npc.get("level") is None:
                npc["level"] = 1
            friendly_npcs.append(npc)
            seen_ally_names.add(n_nm.lower())

    slain_civilians: list[dict] = []

    # Living Allies pool (all players with hp > 0 + all friendly companions with hp > 0 + combat constructs)
    living_allies = [p for p in player_chars if p.get("hp", 1) > 0] + [c for c in friendly_npcs if c.get("hp", 1) > 0]
    if not living_allies and player_chars:
        living_allies = [player_chars[0]]

    active_constructs: list[dict] = []
    if is_anom_combat and isinstance(session, dict):
        for c_unit in [dict(c) for c in (session.get("_active_constructs") or []) if isinstance(c, dict)]:
            c_skey = c_unit.get("summoner_key") or c_unit.get("owner_id") or c_unit.get("name")
            if not any(n.get("is_summon") and (n.get("summoner_key") or n.get("owner_id") or n.get("name")) == c_skey for n in current_npcs):
                current_npcs.append(c_unit)
            if int(c_unit.get("hp", 0) or 0) > 0 and not any(a.get("is_summon") and (a.get("summoner_key") or a.get("owner_id") or a.get("name")) == c_skey for a in living_allies):
                living_allies.append(c_unit)
            active_constructs.append(c_unit)
        for p_ch in player_chars:
            if str(p_ch.get("ability_medium") or "").strip().lower() == "autonomous_construct":
                owner_key = str(p_ch.get("id") or p_ch.get("name") or "player")
                owner_uid = p_ch.get("user_id") or p_ch.get("id")
                already_tracked = any(
                    isinstance(c, dict)
                    and c.get("is_summon")
                    and (
                        c.get("summoner_key") == owner_key
                        or (owner_uid is not None and c.get("owner_id") == owner_uid)
                    )
                    for c in (current_npcs + living_allies)
                )
                spawned = ensure_autonomous_construct(
                    p_ch,
                    living_allies,
                    force_resummon=(not already_tracked and not session.get("_construct_initialized_this_combat")),
                    current_npcs=current_npcs,
                )
                if spawned and spawned not in active_constructs:
                    active_constructs.append(spawned)
        session["_construct_initialized_this_combat"] = True

    combat_log = []
    if isinstance(session, dict):
        session["_pre_combat_enemies"] = [dict(e) for e in enemies if isinstance(e, dict)]
    player_damage_by_name = {p.get("name", "Hero"): 0 for p in player_chars}
    player_heal_by_name = {p.get("name", "Hero"): 0 for p in player_chars}
    player_mp_change_by_name = {p.get("name", "Hero"): 0 for p in player_chars}
    companion_damage_by_name = {c.get("name", "Companion"): 0 for c in friendly_npcs}
    enemy_damage_by_name = {m.get("name", "Enemy"): 0 for m in enemies}
    total_enemy_damage = 0
    dead_enemies = []
    dead_enemy_dicts = []
    yielded_enemies = []
    fled_enemies = []
    surrendered_enemies = []
    surrendered_enemy_dicts = []
    fled_battle = False
    items_consumed_this_turn = []

    from mechanics.combat.damage import apply_damage_to_combatant
    is_non_lethal_active = bool(
        (isinstance(session, dict) and session.get("non_lethal_mode"))
        or any(isinstance(a, dict) and a.get("is_non_lethal") for a in (actions or []))
    )

    def _register_kill(m):
        if m.get("hp", 0) <= 0 and m["name"] not in dead_enemies and m["name"] not in yielded_enemies and m["name"] not in fled_enemies:
            if m.get("sparring"):
                yielded_enemies.append(m["name"])
                m["hp"] = 1
                combat_log.append(f"⚔️ **{m['name']}** yields!")
            elif is_non_lethal_active:
                yielded_enemies.append(m["name"])
                combat_log.append(f"🎯 **{m['name']}** was cleanly subdued and contained!")
            elif m.get("requires_non_lethal_subdue"):
                dead_enemies.append(m["name"])
                dead_enemy_dicts.append(dict(m))
                combat_log.append(f"💀 **{m['name']}** was destroyed by lethal force — specimen lost!")
            else:
                dead_enemies.append(m["name"])
                dead_enemy_dicts.append(dict(m))
                combat_log.append(f"💀 **{m['name']}** was defeated!")
                
                # Volatile Death Explosion (absorbed by temp_hp and shields)
                if "Volatile" in m.get("affixes", []):
                    burst_dmg = max(10, int(m.get("max_hp", 60) * 0.25))
                    target_player = living_allies[0] if living_allies else None
                    if target_player:
                        actual_burst = apply_damage_to_combatant(
                            target=target_player,
                            dmg=burst_dmg,
                            attacker=m,
                            combat_log=combat_log,
                            is_anom_combat=is_anom_combat,
                        )
                        p_name = target_player.get("name", "Hero")
                        player_damage_by_name[p_name] = player_damage_by_name.get(p_name, 0) + actual_burst
                        combat_log.append(f"💥 **DEATH THROES!** **{m['name']}** violently detonated! Dealt **{burst_dmg} explosive damage** to **{p_name}**!")

    def _apply_damage_to_enemy(m, dmg, attacker=None):
        """Applies damage to an enemy with Breach Vulnerability, Temp HP absorption, Boss Phase 2 & True Execute."""
        if attacker is None:
            attacker = {"name": acting_char_name, "team": "ally", "entity_type": "player"}
        p_pierce = bool(m.get("_pierce_temp_hp_this_hit"))
        actual_dmg = apply_damage_to_combatant(
            target=m,
            dmg=dmg,
            attacker=attacker,
            combat_log=combat_log,
            is_anom_combat=is_anom_combat,
            non_lethal_mode=is_non_lethal_active,
            pierce_temp_hp=p_pierce,
        )
        m_name = m.get("name", "Enemy")
        enemy_damage_by_name[m_name] = enemy_damage_by_name.get(m_name, 0) + actual_dmg

        # Phase 3 Combat Evolution: Dynamic Threat update & Boss Interrupt check
        if actual_dmg > 0:
            atk_id = str(attacker.get("name") or acting_char_name)
            target_eid = str(m.get("id") or m.get("name"))
            all_eids = [str(e.get("id") or e.get("name")) for e in enemies if e.get("hp", 0) > 0]
            update_threat_on_action(
                threat_matrix,
                atk_id,
                "attack",
                [target_eid],
                all_eids,
                damage_dealt=actual_dmg,
                sticky_taunts=sticky_taunts,
            )
            if m.get("telegraphed_skill"):
                cur_acc = m["telegraphed_skill"].setdefault("accumulated_interrupt_damage", 0) + actual_dmg
                m["telegraphed_skill"]["accumulated_interrupt_damage"] = cur_acc
                check_boss_telegraph_interrupt(m, cur_acc, boss_telegraph_state, combat_log)

        if m.get("hp", 0) <= 0:
            if is_anom_combat:
                from mechanics.world.folklore_mechanics import get_enemy_tether_state, try_resolve_zero_hp_tether
                if get_enemy_tether_state(m):
                    teth_res = try_resolve_zero_hp_tether(m)
                    if teth_res.get("outcome") == "reformed":
                        combat_log.append(teth_res["message"])
                        return actual_dmg
                    elif teth_res.get("outcome") == "unsealed_dispersion":
                        m["xp_multiplier"] = round(float(m.get("xp_multiplier", 1.0)) * float(teth_res.get("xp_mult", 0.60)), 2)
                        m["prevent_vault_capture"] = True
                        combat_log.append(teth_res["message"])
            _register_kill(m)
        elif m.get("requires_non_lethal_subdue") or is_non_lethal_active:
            sub_pct = float(m.get("subdue_threshold_pct") or 0.35)
            max_hp = int(m.get("max_hp", 100) or 100)
            if m["hp"] <= max(1, int(max_hp * sub_pct)):
                if not m.get("_containment_window_logged"):
                    m["_containment_window_logged"] = True
                    combat_log.append(
                        f"⚡ **{m['name']}** is weakened into the containment window — "
                        f"use **[🛡️ Subdue & Contain]** or **[🗣️ Persuade / Calm]** now before lethal damage kills it!"
                    )
        return actual_dmg

    # --- PHASE 1: ACTIVE PLAYER ACTION ---
    from mechanics.social.attributes import calculate_combat_attributes
    acting_user_id = acting_char_data.get("user_id")
    player_equip = db.get_equipment(acting_user_id) if acting_user_id else {}
    equipped_list = [item for item in player_equip.values() if item] if player_equip else []
    
    weapon_item = player_equip.get("Weapon") if player_equip else None
    armor_item = player_equip.get("Armor") if player_equip else None
    
    from mechanics.combat.equipment import parse_equipment_metadata
    player_weapon = parse_equipment_metadata(weapon_item) if weapon_item else {}
    player_armor = parse_equipment_metadata(armor_item) if armor_item else {}
    player_attrs = calculate_combat_attributes(acting_char_data, equipped_list, scenario=session.get("scenario", "fantasy"))
    player_attrs["combat_turn"] = session.get("combat_turn", 1)
    if any(t in player_attrs.get("tags", []) for t in ("precision", "optics", "hud", "smart_link")):
        player_attrs["acc"] += 5

    anom_passives: dict = dict(player_attrs.get("anomalous_passives") or {})
    if is_anom_combat and not anom_passives:
        try:
            from mechanics.combat.items.anomalous_gear import aggregate_equipped_anomalous_passives
            anom_passives = aggregate_equipped_anomalous_passives(player_equip)
            if anom_passives.get("elemental_amp"):
                player_attrs["elemental_amp"] = dict(anom_passives["elemental_amp"])
        except Exception:
            anom_passives = {}

    action = actions[0] if actions else {"choice_type": "MELEE_ATTACK", "label": "Attack"}
    from mechanics.stealth import is_actor_hidden, is_actor_combat_vanished, set_actor_combat_vanished, clear_all_combat_vanished
    is_hidden_now = bool(is_actor_hidden(session, acting_user_id) or action.get("is_stealth") or action.get("stance") == "stealth")
    is_vanished = bool(is_actor_combat_vanished(session, acting_user_id) or any("Hidden in Shadows" in str(s) for s in acting_char_data.get("status_effects", [])))
    player_attrs["combat_vanished"] = is_vanished
    player_attrs["is_ambush"] = bool(session.get("is_ambush") or (is_hidden_now and player_attrs["combat_turn"] <= 1))

    # Pre-Combat Ambush Surprise Round on Turn 1
    if player_attrs["is_ambush"] and player_attrs["combat_turn"] <= 1:
        for m in enemies:
            if m.get("hp", 0) > 0 and not any("Surprised" in str(s) for s in m.get("status_effects", [])):
                m.setdefault("status_effects", []).append("Surprised [1 turn]")
        combat_log.append("⚡ **Surprise Round!** Caught completely off-guard by the ambush, enemies are stunned for Turn 1!")

    c_type = action.get("choice_type", "MELEE_ATTACK")
    stat_name = action.get("stat", "STR")
    req_val = action.get("requirement", 10)

    # Awakened Resonance player state setup
    p_attr, p_arch, p_med = ("physical", "vanguard", "direct_manifestation")
    pips_map: dict[str, int] = {}
    uid_pip_key = str(acting_user_id or acting_char_name)
    turn_hit_landed = False
    turn_triggered_break = False
    turn_extra_pips = 0
    turn_cast_ultimate = False

    if is_anom_combat:
        def_a, def_ar, def_m = derive_default_3axis(
            char_class=str(acting_char_data.get("char_class") or ""),
            seed=acting_char_name,
        )
        p_attr = normalize_anomalous_attribute(acting_char_data.get("attribute") or def_a, fallback=def_a)
        p_arch = str(acting_char_data.get("combat_archetype") or def_ar).strip().lower()
        p_med = str(acting_char_data.get("ability_medium") or def_m).strip().lower()
        if isinstance(session, dict):
            raw_pm = session.get("player_resonance_pips")
            if isinstance(raw_pm, dict):
                pips_map = dict(raw_pm)
            elif isinstance(raw_pm, (int, float)):
                pips_map = {uid_pip_key: max(0, min(3, int(raw_pm)))}
            else:
                pips_map = {}
            if uid_pip_key not in pips_map:
                pips_map[uid_pip_key] = get_starting_encounter_pips(int(acting_char_data.get("level", 1) or 1))

    def _pre_mark_anomalous_hit(m_obj: dict, base_shred: int, atk_attr: str) -> tuple[int, str]:
        if not is_anom_combat:
            return 0, "physical"
        norm_atk_a = normalize_anomalous_attribute(atk_attr, fallback=p_attr)
        cat_bonus = 0.25 if any("Harmony" in str(s) for s in acting_char_data.get("status_effects", [])) else 0.0
        shred_val = compute_stability_shred(base_shred, norm_atk_a, p_arch, p_attr, m_obj, catalyst_bonus=cat_bonus)
        if not m_obj.get("is_breached") and int(m_obj.get("max_stability", 0) or 0) > 0:
            if int(m_obj.get("stability", 100)) - shred_val <= 0:
                m_obj["_will_breach_this_hit"] = True
        if norm_atk_a == "aether":
            m_obj["_pierce_temp_hp_this_hit"] = True
        return shred_val, norm_atk_a

    def _post_resolve_anomalous_hit(m_obj: dict, shred_val: int, norm_atk_a: str) -> None:
        nonlocal turn_hit_landed, turn_triggered_break, turn_extra_pips, total_enemy_damage
        if not is_anom_combat:
            return
        m_obj.pop("_will_breach_this_hit", None)
        m_obj.pop("_pierce_temp_hp_this_hit", None)
        turn_hit_landed = True
        if m_obj.get("hp", 0) <= 0 and not m_obj.get("is_breached"):
            return
        atk_power = max(player_attrs.get("matk", 20), player_attrs.get("atk", 20))
        br_res = apply_stability_and_break(m_obj, shred_val, norm_atk_a, atk_power, combat_log, non_lethal_mode=is_non_lethal_active)
        if br_res["triggered_break"]:
            m_obj["_breached_this_round"] = True
            turn_triggered_break = True
            turn_extra_pips += int(br_res.get("bonus_pips", 0) or 0)
            if br_res.get("mp_refund", 0) > 0:
                mp_ref = int(br_res["mp_refund"])
                acting_char_data["mp"] = min(acting_char_data.get("max_mp", 100), acting_char_data.get("mp", 0) + mp_ref)
                player_mp_change_by_name[acting_char_name] = player_mp_change_by_name.get(acting_char_name, 0) + mp_ref
            if br_res.get("squad_heal", 0) > 0:
                sh_amt = int(br_res["squad_heal"])
                acting_char_data["hp"] = min(acting_char_data.get("max_hp", 100), acting_char_data.get("hp", 0) + sh_amt)
                player_heal_by_name[acting_char_name] = player_heal_by_name.get(acting_char_name, 0) + sh_amt
            other_foes = [f for f in enemies if f is not m_obj and f.get("hp", 0) > 0]
            if splash := int(br_res.get("aoe_splash_damage", 0) or 0):
                if other_foes:
                    for of in other_foes:
                        _apply_damage_to_enemy(of, splash)
                        total_enemy_damage += splash
                    combat_log.append(f"🌪️ **Vacuum Shear (AoE Splash):** Dealt **{splash} damage** to secondary foes!")
            elif chain := int(br_res.get("chain_damage", 0) or 0):
                if other_foes:
                    _apply_damage_to_enemy(other_foes[0], chain)
                    total_enemy_damage += chain
                    combat_log.append(f"⚡ **Grid Overload (Chain Arc):** Arced to **{other_foes[0]['name']}** for **{chain} damage**!")
        elif br_res.get("super_break_damage", 0) > 0:
            sb = int(br_res["super_break_damage"])
            _apply_damage_to_enemy(m_obj, sb)
            total_enemy_damage += sb

    # Dynamic target resolver: prioritize requested target entity, then label match, then first living
    req_target = str(action.get("combat_target") or action.get("target_entity") or action.get("target_npc") or action.get("target_enemy") or action.get("target") or "").strip().lower()
    target_enemy = None

    if req_target:
        # Two-pass: exact matches first to prevent substring hijacking
        target_enemy = next(
            (m for m in enemies if m.get("hp", 0) > 0 and (
                str(m.get("id")) == req_target or str(m.get("enemy_id")) == req_target or m["name"].lower() == req_target
            )), None
        ) or next(
            (m for m in enemies if m.get("hp", 0) > 0 and (
                req_target in m["name"].lower() or m["name"].lower() in req_target
            )), None
        )

    if not target_enemy and action.get("label"):
        lbl_lower = action["label"].lower()
        target_enemy = next(
            (m for m in enemies if m.get("hp", 0) > 0 and m["name"].lower() in lbl_lower),
            None
        )

    if not target_enemy:
        target_enemy = next((m for m in enemies if m.get("hp", 0) > 0), enemies[0] if enemies else None)

    from mechanics.combat.enemies import get_enemy_armor_profile, get_enemy_weapon_profile

    if target_enemy:
        enemy_arch = target_enemy.get("archetype", "Brute")
        enemy_armor = get_enemy_armor_profile(enemy_arch)
        enemy_weapon = get_enemy_weapon_profile(enemy_arch)
        enemy_attrs = calculate_combat_attributes(target_enemy.get("stats", {}))
        enemy_attrs.update({
            "weaknesses": target_enemy.get("weaknesses", []),
            "resistances": target_enemy.get("resistances", []),
            "immunities": target_enemy.get("immunities", []),
            "physicality": target_enemy.get("physicality", "corporeal"),
        })

        # Evaluate Folklore/SCP Taboo interaction on anomalous targets (skip on non-damage containment turns to prevent duplicate trigger)
        if is_anom_combat and not action.get("incursion_non_damage_turn") and not action.get("is_subdue_contain") and (target_enemy.get("taboo") or isinstance(target_enemy.get("anomaly_blueprint"), dict)):
            try:
                from mechanics.world.anomaly_engine import evaluate_taboo_interaction
                bp_eval = target_enemy.get("anomaly_blueprint") if isinstance(target_enemy.get("anomaly_blueprint"), dict) else {
                    "name": target_enemy.get("name", "Anomaly"),
                    "taboo": target_enemy.get("taboo") or {},
                }
                act_cat_low = str(action.get("action_category") or "").lower()
                is_non_attack_tactic = (
                    c_type in ("DEFENSIVE_GUARD", "DIPLOMACY_TAUNT", "WEAKNESS_EXPLOIT", "EVADE_TACTICAL_FLEE", "STEALTH_VANISH")
                    or act_cat_low in ("tactics", "flee", "item", "consumable")
                    or bool(action.get("is_subdue_contain"))
                    or bool(action.get("is_taboo_exploit"))
                    or str(action.get("incursion_action") or "").lower() in ("subdue", "combat_persuade", "exploit_taboo", "sever_tether", "folklore_offering_rite")
                )
                if is_non_attack_tactic:
                    elem_eval = str(action.get("element") or "").lower()
                elif action.get("spell_id"):
                    from mechanics.combat.spells import get_spell as _get_sp_tb
                    sp_id_tb = action.get("spell_id")
                    if action.get("is_basic_strike") or str(sp_id_tb or "").startswith("awk_basic_"):
                        sp_tb = get_awakened_basic_strike(p_attr, p_med, equipped_weapon=weapon_item)
                    else:
                        sp_tb = _get_sp_tb(sp_id_tb)
                    sp_disc_tb = str((sp_tb or {}).get("discipline") or "attack").lower()
                    if sp_disc_tb in ("heal", "buff", "support", "shield", "cleanse"):
                        elem_eval = str(action.get("element") or "").lower()
                    else:
                        elem_eval = str(
                            action.get("element")
                            or (sp_tb or {}).get("damage_type")
                            or (sp_tb or {}).get("element")
                            or ""
                        ).lower()
                else:
                    elem_eval = str(
                        action.get("element")
                        or player_weapon.get("anomalous_element")
                        or p_attr
                        or ""
                    ).lower()
                taboo_res = evaluate_taboo_interaction(
                    bp_eval,
                    action=action,
                    stat_used=stat_name,
                    element_used=elem_eval,
                    action_text=str(action.get("label") or ""),
                )
                if taboo_res.get("exploited"):
                    target_enemy["taboo_exploited"] = True
                    target_enemy["taboo_seal_unlocked"] = True
                    req_val = max(2, int(req_val) - 3)
                    enemy_attrs["def"] = max(1, int(enemy_attrs.get("def", 15)) - 6)
                    enemy_attrs["mdef"] = max(1, int(enemy_attrs.get("mdef", 15)) - 6)
                    combat_log.append(f"🔓 **Taboo Exploited!** {taboo_res['message']} (**[🛡️ Subdue & Contain]** seal unlocked!)")
                elif taboo_res.get("violated"):
                    v_eff = taboo_res.get("violation_effect") or {}
                    combat_log.append(f"⚠️ **Taboo Violated!** {taboo_res['message']}")
                    if v_eff.get("type") == "heal_enemy":
                        h_e = max(4, int(target_enemy.get("max_hp", 80) * 0.12))
                        target_enemy["hp"] = min(target_enemy.get("max_hp", 80), target_enemy.get("hp", 10) + h_e)
                    else:
                        b_dmg = int(v_eff.get("value", 8) or 8)
                        acting_char_data["hp"] = max(1, acting_char_data.get("hp", 50) - b_dmg)
                        player_damage_by_name[acting_char_name] = player_damage_by_name.get(acting_char_name, 0) + b_dmg
            except Exception:
                pass
        
        # Roll Player Success Tier
        if "check" in action:
            tier = action["check"].tier if hasattr(action["check"], "tier") else getattr(action["check"], "get", lambda k, d=None: d)("tier", "success")
        elif "tier" in action:
            tier = action["tier"]
        else:
            from skill_check import resolve_check
            actor_stat = acting_char_data.get(f"{stat_name.lower()}_", acting_char_data.get(stat_name, 5))
            res = resolve_check(actor_stat, req_val, player_luk_val)
            tier = res.tier

        # 0. PRE-RESOLVED ANOMALOUS CONTAINMENT / TETHER / RITE TURN (Non-Damage)
        if action.get("incursion_non_damage_turn"):
            combat_log.append(
                f"🛡️ **{acting_char_name}** focused on containment procedures against **{target_enemy['name']}** without dealing lethal damage!"
            )

        # 1. MAGIC & SPELLS RESOLUTION
        elif (
            c_type in ("MAGIC_SPELL", "MAGIC_ATTACK")
            or action.get("action_category") == "magic"
            or "spell_id" in action
            or (stat_name == "INT" and c_type not in ("DEFENSIVE_GUARD", "DIPLOMACY_TAUNT", "WEAKNESS_EXPLOIT", "EVADE_TACTICAL_FLEE", "ENVIRONMENTAL_TRAP"))
        ):
            spell_id = action.get("spell_id")
            from mechanics.combat.spells import get_spell, calculate_spell_damage
            if is_anom_combat and (action.get("is_basic_strike") or str(spell_id or "").startswith("awk_basic_")):
                spell = get_awakened_basic_strike(p_attr, p_med, equipped_weapon=weapon_item)
            else:
                spell = get_spell(spell_id) if spell_id else None
            
            # Deduct MP
            mp_cost = spell.get("mp_cost", action.get("mp_cost", 0)) if spell else action.get("mp_cost", 0)
            if mp_cost > 0:
                acting_char_data["mp"] = max(0, acting_char_data.get("mp", 0) - mp_cost)
                player_mp_change_by_name[acting_char_name] = player_mp_change_by_name.get(acting_char_name, 0) - mp_cost

            if spell:
                import json as _sp_json
                raw_sp_prog = acting_char_data.get("skill_progress") if isinstance(acting_char_data, dict) else None
                if isinstance(raw_sp_prog, str):
                    try:
                        raw_sp_prog = _sp_json.loads(raw_sp_prog)
                    except Exception:
                        raw_sp_prog = {}
                emp_list = (raw_sp_prog or {}).get("empowered_granted_spells") if isinstance(raw_sp_prog, dict) else None
                is_dup_emp = bool(spell_id in emp_list) if isinstance(emp_list, list) else bool(spell.get("duplicate_empowered"))
                eff_spell = dict(spell, duplicate_empowered=is_dup_emp)
                emp_mult = 1.20 if is_dup_emp else 1.0
                if spell.get("unavoidable") and tier in ("fail", "failure", "crit_fail"):
                    tier = "success"
                if spell.get("is_pact_skill") and action.get("is_lethal_overdraw"):
                    combat_log.append(
                        f"🩸 **LETHAL OVERDRAW!** **{acting_char_name}** pours their remaining lifeblood into **{spell['name']}** — the invocation erupts at full power before collapse!"
                    )

                discipline = spell.get("discipline", "attack")
                target_type = spell.get("target_type", "single")
                if is_anom_combat:
                    if spell.get("is_ultimate"):
                        turn_cast_ultimate = True
                    if spell.get("resummons_construct") and p_med == "autonomous_construct":
                        re_c = ensure_autonomous_construct(acting_char_data, living_allies, force_resummon=True, current_npcs=current_npcs)
                        if re_c and re_c not in active_constructs:
                            active_constructs.append(re_c)
                        combat_log.append(f"🤖 **{acting_char_name}** re-deployed **{re_c['name']}** via Heavy Resonance!")

                crit_bonus = spell.get("crit_bonus", 0.0)
                glance_floor = spell.get("glance_floor", 0.35)

                def _apply_spell_to_enemy(m, damage_mult=1.0):
                    """Compute and apply spell damage to one enemy. Returns dmg dealt."""
                    m_arch = m.get("archetype", "Brute")
                    m_armor = get_enemy_armor_profile(m_arch)
                    m_attrs = calculate_combat_attributes(m.get("stats", {}))
                    m_attrs.update({
                        "weaknesses": m.get("weaknesses", []),
                        "resistances": m.get("resistances", []),
                        "immunities": m.get("immunities", []),
                        "physicality": m.get("physicality", "corporeal"),
                    })
                    sp_dmg_t = str(spell.get("damage_type") or spell.get("source_element") or "magical").lower()
                    if str(m.get("physicality") or "").lower() == "non_corporeal" and sp_dmg_t in ("physical", "ballistic", "slash", "blunt", "thrust"):
                        return 0, m_armor, m_attrs
                    elem_mult = get_elemental_multiplier(
                        {sp_dmg_t: 1.0}, m_armor, m_attrs
                    )
                    amp_map = player_attrs.get("elemental_amp") or {}
                    if isinstance(amp_map, dict) and sp_dmg_t in amp_map:
                        elem_mult *= (1.0 + max(0.0, float(amp_map[sp_dmg_t])))
                    base_dmg = calculate_spell_damage(
                        player_attrs.get("matk", 20), eff_spell, elem_mult,
                        defender_attrs=m_attrs,
                        armor_type_dt={} if spell.get("pierces_dt") else m_armor.get("type_dt", {}),
                        armor_base_dt=0 if spell.get("pierces_dt") else m_armor.get("base_dt", 0)
                    )
                    if spell.get("strips_shields") and int(m.get("temp_hp", 0) or 0) > 0:
                        m["temp_hp"] = 0
                    base_dmg = int(round(base_dmg * damage_mult))
                    return base_dmg, m_armor, m_attrs

                def _resolve_hit_tier(dmg, tier_val, is_chain_bounce=False):
                    """Apply crit / fail modifiers to raw spell damage."""
                    if tier_val == "crit_success":
                        crit_mult = 1.5 + crit_bonus
                        return int(round(dmg * crit_mult))
                    elif tier_val in ("fail", "failure", "crit_fail"):
                        if target_type == "aoe":
                            # AOE Glancing Blast Floor — never a total miss
                            return max(1, int(round(dmg * glance_floor)))
                        elif is_chain_bounce:
                            # Chain ricochets partially connect
                            return max(1, int(round(dmg * 0.5)))
                        else:
                            # Single-target spell misses completely on failed roll
                            return 0
                    return dmg

                if discipline == "attack":
                    if is_vanished or any("Invisib" in str(s) for s in acting_char_data.get("status_effects", [])):
                        acting_char_data["status_effects"] = [
                            s for s in acting_char_data.get("status_effects", [])
                            if "Hidden in Shadows" not in str(s) and "invisib" not in str(s).lower()
                        ]
                        if isinstance(session, dict):
                            set_actor_combat_vanished(session, False, user_id=acting_user_id, also_set_hidden=False)
                    # ── FULL AOE ─────────────────────────────────────────────
                    if target_type == "aoe":
                        is_glancing = tier in ("fail", "failure", "crit_fail")
                        first = True
                        for m in enemies:
                            if m.get("hp", 0) <= 0:
                                continue
                            raw_dmg, _, m_attrs = _apply_spell_to_enemy(m)
                            dmg = _resolve_hit_tier(raw_dmg, tier)
                            _shred_aoe, _attr_aoe = _pre_mark_anomalous_hit(
                                m, int(spell.get("stability_shred", 20) or 20), spell.get("awakened_attribute") or spell.get("source_element") or p_attr
                            )
                            _apply_damage_to_enemy(m, dmg)
                            if dmg > 0:
                                _post_resolve_anomalous_hit(m, _shred_aoe, _attr_aoe)
                            total_enemy_damage += dmg
                            glance_tag = " *(Glancing blast!)*" if is_glancing else ""
                            if first:
                                combat_log.append(
                                    f"🔮 **{acting_char_name}** cast **{spell['name']}** on "
                                    f"**{m['name']}**: Dealt **{dmg} damage**{glance_tag}."
                                )
                                first = False
                            else:
                                combat_log.append(
                                    f"   ↳ **{m['name']}**: **{dmg} damage**{glance_tag}."
                                )
                            if spell.get("status_ailment"):
                                try_inflict_status(m, m_attrs, f"{spell['status_ailment']} [{spell.get('duration', 2)} turns]", combat_log)

                    # ── BOUNCING CHAIN ────────────────────────────────────────
                    elif target_type == "chain":
                        living = [m for m in enemies if m.get("hp", 0) > 0]
                        max_bounces = spell.get("max_bounces", 3)
                        decay_rate = spell.get("decay_rate", 0.25)
                        targets = living[:max_bounces]
                        for bounce_idx, m in enumerate(targets):
                            bounce_mult = (1.0 - decay_rate) ** bounce_idx  # 1.0, 0.75, 0.50
                            raw_dmg, _, m_attrs = _apply_spell_to_enemy(m, damage_mult=bounce_mult)
                            dmg = _resolve_hit_tier(raw_dmg, tier, is_chain_bounce=(bounce_idx > 0))
                            _shred_ch, _attr_ch = _pre_mark_anomalous_hit(
                                m, int(spell.get("stability_shred", 20) or 20), spell.get("awakened_attribute") or spell.get("source_element") or p_attr
                            )
                            _apply_damage_to_enemy(m, dmg)
                            if dmg > 0:
                                _post_resolve_anomalous_hit(m, _shred_ch, _attr_ch)
                            total_enemy_damage += dmg
                            if bounce_idx == 0:
                                combat_log.append(
                                    f"⚡ **{acting_char_name}** cast **{spell['name']}** on "
                                    f"**{m['name']}**: Dealt **{dmg} damage**."
                                )
                            else:
                                pct = int(bounce_mult * 100)
                                combat_log.append(
                                    f"   ↳ Arc ricochets to **{m['name']}** ({pct}%): **{dmg} damage**."
                                )
                            if spell.get("status_ailment"):
                                try_inflict_status(m, m_attrs, f"{spell['status_ailment']} [{spell.get('duration', 2)} turns]", combat_log)

                    # ── SINGLE-TARGET ─────────────────────────────────────────
                    else:
                        sp_dmg_st = str(spell.get("damage_type") or spell.get("source_element") or "magical").lower()
                        if str(target_enemy.get("physicality") or "").lower() == "non_corporeal" and sp_dmg_st in ("physical", "ballistic", "slash", "blunt", "thrust"):
                            m_dmg = 0
                            combat_log.append(
                                f"🛡️ **{target_enemy['name']}** is **Non-Corporeal** — physical resonance from **{spell['name']}** phased harmlessly through it (0 damage)!"
                            )
                        else:
                            elem_mult = get_elemental_multiplier(
                                {sp_dmg_st: 1.0}, enemy_armor, enemy_attrs
                            )
                            amp_map_st = player_attrs.get("elemental_amp") or {}
                            if isinstance(amp_map_st, dict) and sp_dmg_st in amp_map_st:
                                elem_mult *= (1.0 + max(0.0, float(amp_map_st[sp_dmg_st])))
                            if spell.get("strips_shields") and int(target_enemy.get("temp_hp", 0) or 0) > 0:
                                target_enemy["temp_hp"] = 0
                            m_dmg = calculate_spell_damage(
                                player_attrs.get("matk", 20), eff_spell, elem_mult,
                                defender_attrs=enemy_attrs,
                                armor_type_dt={} if spell.get("pierces_dt") else enemy_armor.get("type_dt", {}),
                                armor_base_dt=0 if spell.get("pierces_dt") else enemy_armor.get("base_dt", 0)
                            )
                            m_dmg = _resolve_hit_tier(m_dmg, tier)

                        if m_dmg > 0:
                            _shred_st, _attr_st = _pre_mark_anomalous_hit(
                                target_enemy,
                                int(spell.get("stability_shred", 20) or 20),
                                spell.get("attack_attribute") or spell.get("awakened_attribute") or spell.get("source_element") or p_attr,
                            )
                            _apply_damage_to_enemy(target_enemy, m_dmg)
                            _post_resolve_anomalous_hit(target_enemy, _shred_st, _attr_st)
                            total_enemy_damage += m_dmg
                            crit_tag = " *(Critical hit!)*" if tier == "crit_success" else ""
                            combat_log.append(
                                f"🔮 **{acting_char_name}** cast **{spell['name']}** on "
                                f"**{target_enemy['name']}**: Dealt **{m_dmg} damage**{crit_tag}."
                            )
                            if spell.get("status_ailment"):
                                try_inflict_status(target_enemy, enemy_attrs, f"{spell['status_ailment']} [{spell.get('duration', 2)} turns]", combat_log)
                        else:
                            combat_log.append(
                                f"💨 **{acting_char_name}** cast **{spell['name']}** on "
                                f"**{target_enemy['name']}**, but the spell missed!"
                            )

                    # ── METAMAGIC IN-COMBAT TRIGGERS ─────────────────────────
                    spell_affixes = spell.get("affixes", [])
                    if total_enemy_damage > 0:
                        # Vampiric: 25% lifesteal of dealt damage
                        if "vampiric" in spell_affixes:
                            leech_val = max(1, int(round(total_enemy_damage * 0.25)))
                            max_hp = acting_char_data.get("max_hp", 100)
                            old_hp = acting_char_data.get("hp", 0)
                            acting_char_data["hp"] = min(max_hp, old_hp + leech_val)
                            actual_leech = acting_char_data["hp"] - old_hp
                            player_heal_by_name[acting_char_name] = player_heal_by_name.get(acting_char_name, 0) + actual_leech
                            combat_log.append(f"🩸 **{acting_char_name}** siphoned **{actual_leech} HP** with Vampiric Touch!")

                        # Twinned: 25% chance of secondary echoing strike
                        if "twinned" in spell_affixes and random.random() < 0.25 and target_enemy.get("hp", 0) > 0:
                            echo_dmg = max(1, int(round(total_enemy_damage * 0.5)))
                            _apply_damage_to_enemy(target_enemy, echo_dmg)
                            total_enemy_damage += echo_dmg
                            combat_log.append(f"✨ **Twinned** echo triggers! **{target_enemy['name']}** struck for **{echo_dmg} damage**!")

                    # Cleansing: remove 1 debuff from caster
                    if ("cleansing" in spell_affixes or spell.get("cleanses_debuff") or spell.get("cleanses_party")) and acting_char_data.get("status_effects"):
                        if spell.get("cleanses_party"):
                            acting_char_data["status_effects"] = [
                                s for s in acting_char_data["status_effects"]
                                if not any(neg in str(s) for neg in ("Bleed", "Poison", "Burn", "Stun", "Weak", "Blind", "Chill", "Curse", "Disrupt"))
                            ]
                            combat_log.append(f"✨ **{acting_char_name}**'s Entity Covenant purged negative afflictions!")
                        else:
                            cleansed = acting_char_data["status_effects"].pop(0)
                            combat_log.append(f"✨ **{acting_char_name}** cleansed **{cleansed}**!")
                    if spell.get("is_pact_skill"):
                        if total_enemy_damage > 0 and spell.get("lifesteal_pct") and not action.get("is_lethal_overdraw"):
                            _ls_val = max(1, int(round(total_enemy_damage * float(spell["lifesteal_pct"]))))
                            _old_h = int(acting_char_data.get("hp", 0) or 0)
                            acting_char_data["hp"] = min(int(acting_char_data.get("max_hp", 100) or 100), _old_h + _ls_val)
                            _gained_h = acting_char_data["hp"] - _old_h
                            if _gained_h > 0:
                                player_heal_by_name[acting_char_name] = player_heal_by_name.get(acting_char_name, 0) + _gained_h
                                combat_log.append(f"🩸 **{acting_char_name}** devoured **{_gained_h} HP** via **{spell['name']}**!")
                        if spell.get("execute_threshold") and target_enemy.get("hp", 0) > 0 and not target_enemy.get("is_boss") and not target_enemy.get("sparring"):
                            _ex_cap = max(1, int(round(target_enemy.get("max_hp", 100) * float(spell["execute_threshold"]))))
                            if target_enemy["hp"] <= _ex_cap:
                                target_enemy["hp"] = 0
                                _register_kill(target_enemy)
                                combat_log.append(f"⚰️ **COVENANT EXECUTION!** **{spell['name']}** reaped **{target_enemy['name']}** outright!")
                        if spell.get("enters_stealth"):
                            acting_char_data.setdefault("status_effects", []).append("Hidden in Shadows [2 turns]")
                            if isinstance(session, dict):
                                set_actor_combat_vanished(session, True, user_id=acting_user_id, also_set_hidden=False)
                            combat_log.append(f"🌑 **{acting_char_name}** slipped into anomalous shadow veil!")
                        if spell.get("grants_temp_hp_pct"):
                            _thp_p = max(4, int(round(acting_char_data.get("max_hp", 70) * float(spell["grants_temp_hp_pct"]))))
                            acting_char_data["temp_hp"] = max(int(acting_char_data.get("temp_hp", 0) or 0), _thp_p)
                            combat_log.append(f"🛡️ **{acting_char_name}** gained **+{_thp_p} Temp Barrier**!")
                        if spell.get("self_status_ailment"):
                            acting_char_data.setdefault("status_effects", []).append(str(spell["self_status_ailment"]))
                    if is_anom_combat and spell.get("party_temp_hp_shield"):
                        sh_v = int(spell["party_temp_hp_shield"])
                        acting_char_data["temp_hp"] = max(int(acting_char_data.get("temp_hp", 0) or 0), sh_v)
                    if is_anom_combat and p_med == "autonomous_construct" and not spell.get("is_ultimate"):
                        c_unit = next((c for c in living_allies if c.get("is_autonomous_construct") and c.get("hp", 0) > 0), None)
                        if c_unit is not None:
                            c_unit["queued_windup"] = {
                                "name": f"{spell['name']} Overdrive",
                                "damage": max(12, int(round(c_unit.get("atk", 15) * 1.35))),
                                "attr": p_attr,
                                "_queued_this_round": True,
                            }



                elif discipline == "support":
                    if spell.get("temp_hp_shield"):
                        acting_char_data["temp_hp"] = max(int(acting_char_data.get("temp_hp", 0) or 0), int(spell["temp_hp_shield"]))
                    if spell.get("grants_temp_hp_pct"):
                        _sup_thp = max(4, int(round(acting_char_data.get("max_hp", 70) * float(spell["grants_temp_hp_pct"]))))
                        acting_char_data["temp_hp"] = max(int(acting_char_data.get("temp_hp", 0) or 0), _sup_thp)
                    if spell.get("cleanses_party") and acting_char_data.get("status_effects"):
                        acting_char_data["status_effects"] = [
                            s for s in acting_char_data["status_effects"]
                            if not any(neg in str(s) for neg in ("Bleed", "Poison", "Burn", "Stun", "Weak", "Blind", "Chill", "Curse", "Disrupt"))
                        ]
                    if spell.get("enters_stealth"):
                        acting_char_data.setdefault("status_effects", []).append("Hidden in Shadows [2 turns]")
                        if isinstance(session, dict):
                            set_actor_combat_vanished(session, True, user_id=acting_user_id, also_set_hidden=False)
                    if spell.get("self_status_ailment"):
                        acting_char_data.setdefault("status_effects", []).append(str(spell["self_status_ailment"]))
                    if spell.get("mono_attribute_buff"):
                        acting_char_data.setdefault("status_effects", []).append(f"Harmony ({spell['mono_attribute_buff'].title()}) [2 turns]")
                    if spell.get("heal_self_pct") or spell.get("heals_party_pct"):
                        _hp_pct_s = float(spell.get("heals_party_pct") or spell.get("heal_self_pct") or 0.25)
                        heal_val = max(4, int(round(acting_char_data.get("max_hp", 70) * _hp_pct_s * emp_mult)))
                        if not action.get("is_lethal_overdraw"):
                            acting_char_data["hp"] = min(acting_char_data.get("max_hp", 100), acting_char_data.get("hp", 0) + heal_val)
                            player_heal_by_name[acting_char_name] = player_heal_by_name.get(acting_char_name, 0) + heal_val
                        combat_log.append(f"💚 **{acting_char_name}** invoked **{spell['name']}**: Restored **{heal_val} HP**.")
                    elif "heal_amount" in spell:
                        heal_val = int(round(spell["heal_amount"] * emp_mult))
                        if tier == "crit_success":
                            heal_val = int(round(heal_val * 1.4))
                        acting_char_data["hp"] = min(acting_char_data.get("max_hp", 100), acting_char_data.get("hp", 0) + heal_val)
                        player_heal_by_name[acting_char_name] = player_heal_by_name.get(acting_char_name, 0) + heal_val
                        combat_log.append(f"💚 **{acting_char_name}** cast **{spell['name']}**: Restored **{heal_val} HP**.")
                    elif "mp_amount" in spell:
                        mp_gain = int(round(spell["mp_amount"] * emp_mult))
                        acting_char_data["mp"] = min(acting_char_data.get("max_mp", 100), acting_char_data.get("mp", 0) + mp_gain)
                        player_mp_change_by_name[acting_char_name] = player_mp_change_by_name.get(acting_char_name, 0) + mp_gain
                        combat_log.append(f"💙 **{acting_char_name}** cast **{spell['name']}**: Restored **{mp_gain} MP**.")
                    else:
                        buff_tag = spell.get("status_ailment", "Fortified")
                        dur = spell.get("duration", 2)
                        acting_char_data.setdefault("status_effects", []).append(f"{buff_tag} [{dur} turns]")
                        buff_pct = int(round(spell.get("buff_pct", 0.15) * emp_mult * 100))
                        combat_log.append(f"✨ **{acting_char_name}** cast **{spell['name']}**: Gained **+{buff_pct}% {spell.get('stat_target', 'DEF')}** for {dur} turns.")

                elif discipline == "curse":
                    debuff_tag = spell.get("status_ailment", "Weakened")
                    dur = spell.get("duration", 2)
                    debuff_pct = int(round(spell.get("debuff_pct", 0.15) * emp_mult * 100))
                    if target_type == "aoe":
                        for m in enemies:
                            m.setdefault("status_effects", []).append(f"{debuff_tag} [{dur} turns]")
                        combat_log.append(f"💀 **{acting_char_name}** cast **{spell['name']}** over all enemies: Inflicted **-{debuff_pct}% {spell.get('stat_target', 'ATK')}** for {dur} turns.")
                    else:
                        target_enemy.setdefault("status_effects", []).append(f"{debuff_tag} [{dur} turns]")
                        combat_log.append(f"💀 **{acting_char_name}** cast **{spell['name']}** on **{target_enemy['name']}**: Inflicted **-{debuff_pct}% {spell.get('stat_target', 'ATK')}** for {dur} turns.")

                elif discipline == "summon":
                    from mechanics.combat.spells import SUMMON_TEMPLATES
                    template_key = spell.get("summon_template", "spirit_wolf")
                    template = SUMMON_TEMPLATES.get(template_key, SUMMON_TEMPLATES["spirit_wolf"])
                    
                    s_count = spell.get("summon_count", template.get("count", 1))
                    s_dur = spell.get("summon_duration", template.get("duration", 3))
                    s_arch = spell.get("summon_archetype", template.get("archetype", "Skirmisher"))
                    c_lvl = acting_char_data.get("level", 1)
                    s_hp = template.get("base_hp", 20) + (c_lvl * template.get("hp_per_level", 5))
                    s_name = template.get("name", "Summoned Minion")
                    
                    for idx in range(s_count):
                        minion_name = f"{s_name} #{idx+1}" if s_count > 1 else s_name
                        summon_npc = {
                            "name": minion_name,
                            "archetype": s_arch,
                            "level": c_lvl,
                            "hp": s_hp,
                            "max_hp": s_hp,
                            "summon_duration": s_dur,
                            "is_summon": True,
                            "stats": {
                                "STR": 4 + c_lvl, "AGI": 4 + c_lvl, "INT": 4 + c_lvl,
                                "PER": 4 + c_lvl, "END": 4 + c_lvl, "CHA": 1, "LUK": 1
                            }
                        }
                        current_npcs.append(summon_npc)
                        living_allies.append(summon_npc)
                    
                    combat_log.append(f"🔮 **{acting_char_name}** cast **{spell['name']}**: Summoned **{s_count}x {s_name}** for {s_dur} turns!")
            else:
                if tier in ("fail", "failure", "crit_fail"):
                    combat_log.append(f"💨 **{acting_char_name}** cast magic on **{target_enemy['name']}**, but the spell missed!")
                else:
                    m_dmg = max(10, int(player_attrs.get("matk", 20) * 1.2))
                    if tier == "crit_success":
                        m_dmg = int(round(m_dmg * 1.5))
                    applied_dmg = _apply_damage_to_enemy(target_enemy, m_dmg)
                    total_enemy_damage += applied_dmg
                    crit_tag = " *(Critical hit!)*" if tier == "crit_success" else ""
                    combat_log.append(f"🔮 **{acting_char_name}** cast magic on **{target_enemy['name']}**: Dealt **{applied_dmg} damage**{crit_tag}.")

        elif stat_name == "ITEM":
            label_lower = action.get("label", "").lower()
            item_obj = action.get("item") or {}
            from mechanics.combat.items.consumables import parse_item_effect
            parsed_item = parse_item_effect(item_obj) if item_obj else parse_item_effect({"name": action.get("label", ""), "effect": ""})

            item_available = True
            # Deduct item from inventory if not already consumed upstream (safeguard against infinite combat items)
            if not action.get("item_consumed") and acting_user_id:
                consume_item_name = (
                    (action.get("item") or {}).get("name")
                    or action.get("item_name")
                )
                if not consume_item_name:
                    import re
                    m_use = re.search(r"^(?:Use|Throw)\s+(.+?)(?:\s+on|\s+at|$)", action.get("label", ""), re.IGNORECASE)
                    if m_use:
                        consume_item_name = m_use.group(1).strip()
                    else:
                        consume_item_name = action.get("label", "").strip()
                if consume_item_name:
                    found_in_inv = False
                    if party and isinstance(party[0], (tuple, list)) and len(party[0]) > 1:
                        p_inv = party[0][1]
                        if isinstance(p_inv, list):
                            for idx, itm in enumerate(p_inv):
                                if isinstance(itm, dict) and itm.get("name", "").strip().lower() == consume_item_name.lower():
                                    p_inv.pop(idx)
                                    found_in_inv = True
                                    break
                    elif acting_user_id:
                        found_in_inv = any(i.get("name", "").strip().lower() == consume_item_name.lower() for i in db.get_inventory(acting_user_id))
                    else:
                        found_in_inv = True

                    if not found_in_inv:
                        item_available = False
                        combat_log.append(f"⚠️ **{acting_char_name}** reached for **{consume_item_name}**, but had none left in inventory!")
                    else:
                        action["item_consumed"] = True
                        items_consumed_this_turn.append(consume_item_name)

            if not item_available:
                pass
            # 1. Throwables & Explosives targeting enemy
            elif parsed_item.get("damage", 0) > 0 or any(w in label_lower for w in ["bomb", "grenade", "flask", "throw", "acid", "poison", "molotov", "damage"]):
                base_throw_dmg = parsed_item.get("damage", 0)
                if base_throw_dmg <= 0:
                    base_throw_dmg = max(20, int(target_enemy.get("max_hp", 100) * 0.40) + 15)
                applied_dmg = _apply_damage_to_enemy(target_enemy, base_throw_dmg)
                total_enemy_damage += applied_dmg
                combat_log.append(f"💣 **{acting_char_name}** threw **{action.get('label', 'Explosive')}**: Dealt **{applied_dmg} damage** to {target_enemy['name']}!")
                if parsed_item.get("inflict_status"):
                    target_enemy.setdefault("status_effects", []).extend(parsed_item["inflict_status"])

            # 2. Healing & Recovery Items
            elif parsed_item.get("hp_restore", 0) > 0 or parsed_item.get("mp_restore", 0) > 0:
                h_val = parsed_item.get("hp_restore", 0)
                m_val = parsed_item.get("mp_restore", 0)
                acting_char_data["hp"] = min(acting_char_data.get("max_hp", 100), acting_char_data.get("hp", 0) + h_val)
                player_heal_by_name[acting_char_name] = player_heal_by_name.get(acting_char_name, 0) + h_val
                if m_val > 0:
                    acting_char_data["mp"] = min(acting_char_data.get("max_mp", 100), acting_char_data.get("mp", 0) + m_val)
                    player_mp_change_by_name[acting_char_name] = player_mp_change_by_name.get(acting_char_name, 0) + m_val
                combat_log.append(f"🧪 **{acting_char_name}** consumed **{action.get('label', 'Potion')}**: Restored **+{h_val} HP**" + (f", **+{m_val} MP**" if m_val > 0 else "") + ".")
                if h_val > 0:
                    all_eids = [str(e.get("id") or e.get("name")) for e in enemies if e.get("hp", 0) > 0]
                    update_threat_on_action(
                        threat_matrix,
                        str(acting_char_name),
                        "heal",
                        [],
                        all_eids,
                        effective_healing=h_val,
                        sticky_taunts=sticky_taunts,
                    )

            # 3. Defensive / Offensive Buffs
            elif parsed_item.get("buffs"):
                buffs = parsed_item["buffs"]
                log_buffs = []
                dur = 3
                if "dt" in buffs:
                    acting_char_data.setdefault("status_effects", []).append(f"Iron Skin [+{buffs['dt']} DT] [{dur} turns]")
                    log_buffs.append(f"+{buffs['dt']} DT")
                if "dr" in buffs:
                    acting_char_data.setdefault("status_effects", []).append(f"Aegis Warding [+{int(buffs['dr'] * 100)}% DR] [{dur} turns]")
                    log_buffs.append(f"+{int(buffs['dr'] * 100)}% DR")
                if "atk_pct" in buffs:
                    acting_char_data.setdefault("status_effects", []).append(f"Combat Booster [+{int(buffs['atk_pct'] * 100)}% ATK] [{dur} turns]")
                    log_buffs.append(f"+{int(buffs['atk_pct'] * 100)}% ATK")
                if "eva" in buffs:
                    acting_char_data.setdefault("status_effects", []).append(f"Quickstep [+{buffs['eva']}% EVA] [{dur} turns]")
                    log_buffs.append(f"+{buffs['eva']}% EVA")
                combat_log.append(f"✨ **{acting_char_name}** consumed **{action.get('label', 'Booster')}**: Gained **{', '.join(log_buffs)}** for {dur} turns.")

            else:
                combat_log.append(f"🎒 **{acting_char_name}** used item: {action.get('label', 'Item')}.")

        # 3. DEFENSIVE GUARD & BRACE
        elif c_type == "DEFENSIVE_GUARD" or action.get("action_category") == "guard":
            acting_char_data.setdefault("status_effects", []).append("Defensive Guard [+6 DT, +30% Block] [1 turn]")
            player_attrs["base_dt"] = player_attrs.get("base_dt", 0) + 6
            player_attrs["block_chance"] = player_attrs.get("block_chance", 0) + 30
            combat_log.append(f"🛡️ **{acting_char_name}** braces and assumes a defensive guard! (+6 DT and +30% Block chance for incoming attacks!)")

        # 4. DIPLOMACY & TAUNT
        elif c_type == "DIPLOMACY_TAUNT" or action.get("action_category") == "taunt":
            if tier in ("crit_success", "success"):
                debuff_val = 25 if tier == "crit_success" else 15
                target_enemy.setdefault("status_effects", []).append(f"Demoralized [-{debuff_val}% ATK] [2 turns]")
                combat_log.append(f"🗣️ **{acting_char_name}** intimidates **{target_enemy['name']}**! They are demoralized and suffer -{debuff_val}% ATK!")
                target_eid = str(target_enemy.get("id") or target_enemy.get("name"))
                all_eids = [str(e.get("id") or e.get("name")) for e in enemies if e.get("hp", 0) > 0]
                update_threat_on_action(
                    threat_matrix,
                    str(acting_char_name),
                    "taunt",
                    [target_eid],
                    all_eids,
                    is_taunt=True,
                    sticky_taunts=sticky_taunts,
                )
            else:
                combat_log.append(f"🗣️ **{acting_char_name}** attempted to taunt **{target_enemy['name']}**, but they brushed off the insult!")

        # 5. WEAKNESS EXPLOIT / SCAN
        elif c_type == "WEAKNESS_EXPLOIT" or action.get("action_category") == "exploit" or "scan" in action.get("label", "").lower():
            if tier in ("crit_success", "success"):
                res_list = target_enemy.get("resistances", [])
                weak_list = target_enemy.get("weaknesses", [])
                imm_list = target_enemy.get("immunities", [])
                r_str = f"Resistances: {', '.join(res_list)}" if res_list else "No resistances"
                w_str = f"Weaknesses: {', '.join(weak_list)}" if weak_list else "No weaknesses"
                i_str = f" | Immunities: {', '.join(imm_list)}" if imm_list else ""
                acting_char_data.setdefault("status_effects", []).append("Weakpoint Analyzed [+15% ACC] [2 turns]")
                scan_extra = ""
                if target_enemy.get("taboo") or isinstance(target_enemy.get("anomaly_blueprint"), dict):
                    target_enemy["dossier_revealed"] = True
                    if isinstance(target_enemy.get("anomaly_blueprint"), dict):
                        from mechanics.world.folklore_mechanics import unmask_blueprint_disguise
                        unmasked_bp, unmask_msg = unmask_blueprint_disguise(target_enemy["anomaly_blueprint"])
                        unmasked_bp["dossier_revealed"] = True
                        target_enemy["anomaly_blueprint"] = unmasked_bp
                        if unmask_msg:
                            target_enemy["name"] = str(unmasked_bp.get("canonical_name") or unmasked_bp.get("name") or target_enemy["name"])
                            target_enemy["is_disguised"] = False
                            scan_extra += f" | {unmask_msg}"
                        if sess_id_cbt:
                            try:
                                db.record_session_anomaly_field_log(int(sess_id_cbt), unmasked_bp, stage="verified")
                                if unmasked_bp.get("codex_id"):
                                    db.record_folklore_codex_progress(
                                        db.get_session_participant_user_ids(int(sess_id_cbt)) or ([acting_user_id] if acting_user_id else []),
                                        str(unmasked_bp["codex_id"]),
                                        stage="verified",
                                    )
                            except Exception:
                                pass
                        # Persist the scan's dossier reveal back to the linked breach / quest so fleeing or
                        # re-engaging never resets the anomaly to an unrevealed, disguised state.
                        if sess_id_cbt and (target_enemy.get("incursion_id") or target_enemy.get("breach_id") or target_enemy.get("linked_quest_id")):
                            try:
                                from mechanics.world.anomalous_events import reveal_anomaly_dossier
                                _scan_inc = str(target_enemy.get("incursion_id") or target_enemy.get("breach_id") or "")
                                reveal_anomaly_dossier(
                                    session_id=int(sess_id_cbt),
                                    quest_id=str(target_enemy.get("linked_quest_id") or ""),
                                    incursion_id=_scan_inc,
                                    breach_id=_scan_inc,
                                )
                            except Exception:
                                pass
                    tb_scan = (
                        target_enemy.get("taboo")
                        or (target_enemy.get("anomaly_blueprint") or {}).get("taboo")
                        or {}
                    )
                    rule_txt = tb_scan.get("rule_text") or tb_scan.get("taboo_rule") or ""
                    hint_txt = tb_scan.get("exploit_hint") or tb_scan.get("containment_protocol") or ""
                    if isinstance(tb_scan, dict) and (rule_txt or hint_txt):
                        scan_extra += f" | 📜 Taboo: {rule_txt} ({hint_txt})"
                combat_log.append(f"👁️ **{acting_char_name}** scanned **{target_enemy['name']}**! {w_str} | {r_str}{i_str}.{scan_extra}")
            else:
                combat_log.append(f"👁️ **{acting_char_name}** scanned **{target_enemy['name']}**, but could not expose a clear weakness.")

        # 6. TACTICAL FLEE
        elif c_type == "EVADE_TACTICAL_FLEE" or action.get("action_category") == "flee" or "flee" in action.get("label", "").lower() or "disengage" in action.get("label", "").lower():
            if tier in ("crit_success", "success"):
                fled_battle = True
                combat_log.append(f"🏃 **{acting_char_name}** successfully disengaged and fled from combat!")
            else:
                combat_log.append(f"🏃 **{acting_char_name}** attempted to disengage, but was cut off by **{target_enemy['name']}**!")

        # 8. VANISH INTO SHADOWS / COVERT STEALTH
        elif (
            c_type == "STEALTH_VANISH"
            or action.get("action_category") == "stealth"
            or "vanish" in action.get("label", "").lower()
            or "hide in shadows" in action.get("label", "").lower()
        ):
            if tier in ("crit_success", "success"):
                if isinstance(session, dict):
                    set_actor_combat_vanished(session, True, user_id=acting_user_id, also_set_hidden=True)
                crit_note = " *(Perfect Shadow Blend!)*" if tier == "crit_success" else ""
                acting_char_data.setdefault("status_effects", []).append("Hidden in Shadows [+50% Next Attack, Aggro Shed] [1 turn]")
                combat_log.append(f"💨 **{acting_char_name}** slipped into the shadows and vanished from enemy sight!{crit_note}")
            else:
                combat_log.append(f"💨 **{acting_char_name}** attempted to vanish into the shadows, but **{target_enemy['name']}** kept line-of-sight!")

        # 7. ENVIRONMENTAL TRAP OR FREEFORM ENVIRONMENTAL HAZARD
        elif (
            c_type == "ENVIRONMENTAL_TRAP"
            or action.get("action_category") == "trap"
            or action.get("combat_tactical_archetype") == "environmental_hazard"
        ):
            if tier in ("crit_success", "success"):
                trap_stat = max(player_attrs.get("matk", 20), player_attrs.get("atk", 20))
                mult = 1.85 if tier == "crit_success" else 1.25
                trap_dmg = max(12, int(round(trap_stat * mult)))
                applied_dmg = _apply_damage_to_enemy(target_enemy, trap_dmg)
                total_enemy_damage += applied_dmg
                target_enemy.setdefault("status_effects", []).append("Staggered [1 turn]")
                crit_tag = " *(Critical hit!)*" if tier == "crit_success" else ""
                combat_log.append(f"⚙️ **{acting_char_name}** triggered an environmental hazard on **{target_enemy['name']}**: Dealt **{applied_dmg} damage** and Staggered them{crit_tag}!")
            else:
                combat_log.append(f"⚙️ **{acting_char_name}** attempted to use the environment against **{target_enemy['name']}**, but it failed to trigger!")

        # 8. FREEFORM COMBAT PARLEY (Morale-Gated Surrender / Intimidation / Non-Hostile De-escalation)
        elif action.get("combat_tactical_archetype") == "combat_parley":
            enemy_tier_rank = int(target_enemy.get("tier_rank", 2) or 2)
            enemy_hp_pct = target_enemy.get("hp", 100) / max(1, target_enemy.get("max_hp", 100))
            if target_enemy.get("requires_non_lethal_subdue"):
                if tier in ("crit_success", "success"):
                    target_enemy["hp"] = 0
                    target_enemy["surrendered"] = True
                    target_enemy["contained_via_parley"] = True
                    surrendered_enemies.append(target_enemy["name"])
                    surrendered_enemy_dicts.append(dict(target_enemy))
                    fled_enemies.append(target_enemy["name"])
                    combat_log.append(
                        f"🗣️ **{acting_char_name}** calmed **{target_enemy['name']}**'s agitation! "
                        f"**{target_enemy['name']}** lowered its guard and entered containment willingly!"
                    )
                else:
                    combat_log.append(
                        f"🗣️ **{acting_char_name}** attempted to calm **{target_enemy['name']}**, "
                        f"but its agitated resonance lashed back!"
                    )
            elif (
                target_enemy.get("is_anomalous_manifestation")
                and str(target_enemy.get("sapience") or "").lower() in ("instinctual", "non_sapient")
                and not target_enemy.get("taboo_seal_unlocked")
            ):
                combat_log.append(
                    f"🗣️ **{acting_char_name}** attempted to parley with **{target_enemy['name']}**, "
                    f"but the {target_enemy.get('sapience', 'non-sapient')} anomaly cannot be reasoned with verbally!"
                )
            elif (
                target_enemy.get("is_anomalous_manifestation")
                and str(target_enemy.get("sapience") or "").lower() == "compulsive"
                and not (
                    target_enemy.get("dossier_revealed")
                    or (target_enemy.get("anomaly_blueprint") or {}).get("dossier_revealed")
                    or target_enemy.get("taboo_seal_unlocked")
                )
            ):
                # Pattern-bound anomalies only yield to the verified counter-rite (same gate as containment actions)
                combat_log.append(
                    f"🗣️ **{acting_char_name}** tried to talk **{target_enemy['name']}** down, but its compulsive loop "
                    f"ignores words until its folklore pattern is understood!"
                )
            elif _enemy_has_unsealed_tether(target_enemy):
                combat_log.append(
                    f"🏺 **{target_enemy['name']}** wavers at **{acting_char_name}**'s words, but its bound vessel keeps "
                    f"re-anchoring it—seal the tether before it can be contained!"
                )
            elif tier == "crit_success" or (tier == "success" and enemy_tier_rank <= 3 and enemy_hp_pct <= 0.50):
                surrendered_enemies.append(target_enemy["name"])
                fled_enemies.append(target_enemy["name"])
                target_enemy["hp"] = 0
                target_enemy["surrendered"] = True
                if target_enemy.get("is_anomalous_manifestation"):
                    target_enemy["contained_via_parley"] = True
                    surrendered_enemy_dicts.append(dict(target_enemy))
                combat_log.append(
                    f"🏳️ **{acting_char_name}** broke **{target_enemy['name']}**'s will to fight! "
                    f"**{target_enemy['name']}** dropped their weapon and surrendered!"
                )
            elif tier == "success":
                target_enemy.setdefault("status_effects", []).append("Hesitating / Demoralized [-25% ATK] [2 turns]")
                target_enemy.setdefault("status_effects", []).append("Staggered [1 turn]")
                combat_log.append(
                    f"🗣️ **{acting_char_name}** shook **{target_enemy['name']}**'s resolve! "
                    f"They are **Hesitating / Demoralized (-25% ATK)** and **Staggered** for 1 turn!"
                )
            else:
                combat_log.append(
                    f"🗣️ **{acting_char_name}** attempted to parley with **{target_enemy['name']}**, "
                    f"but they refused to yield!"
                )

        # 9. FREEFORM TACTICAL DEBUFF (Sabotage / Blind / Feint)
        elif action.get("combat_tactical_archetype") == "tactical_debuff":
            if tier in ("crit_success", "success"):
                target_enemy.setdefault("status_effects", []).append("Vulnerable [-25% EVA, -20% ATK] [2 turns]")
                target_enemy.setdefault("status_effects", []).append("Staggered [1 turn]")
                combat_log.append(
                    f"🎯 **{acting_char_name}** executed a tactical disruption on **{target_enemy['name']}**: "
                    f"Inflicted **Vulnerable (-25% EVA, -20% ATK)** and **Staggered [1 turn]**!"
                )
            else:
                combat_log.append(
                    f"🎯 **{acting_char_name}** attempted a tactical disruption against **{target_enemy['name']}**, "
                    f"but they anticipated the feint!"
                )

        # 10. FREEFORM REPOSITION (Break Tether / Evasion + Flanking Primer)
        elif action.get("combat_tactical_archetype") == "reposition":
            if tier in ("crit_success", "success"):
                acting_char_data.setdefault("status_effects", []).append("Evasive Maneuver [+30% EVA] [1 turn]")
                acting_char_data.setdefault("status_effects", []).append("Flanking Advantage [+25% ACC, +20% ATK] [2 turns]")
                player_attrs["dodge_chance"] = min(85, player_attrs.get("dodge_chance", 5) + 30)
                # Clear any active grapple/restraint tether in physical_state
                try:
                    phys = session.get("physical_state") if isinstance(session, dict) else None
                    if isinstance(phys, dict) and isinstance(phys.get("actors"), dict):
                        for ak, av in phys["actors"].items():
                            if ak.lower() == acting_char_name.lower() and isinstance(av, dict):
                                av["tether"] = "none"
                except Exception:
                    pass
                combat_log.append(
                    f"💨 **{acting_char_name}** repositioned with agile footwork! "
                    f"Cleared restraints, gained **+30% Evasion** this turn, and secured **Flanking Advantage (+25% ACC, +20% ATK)**!"
                )
            else:
                combat_log.append(
                    f"💨 **{acting_char_name}** tried to reposition around **{target_enemy['name']}**, "
                    f"but was forced back!"
                )

        # 11. FREEFORM CALLED SHOT (Precision Targeted Strike + 40% DT Pierce + Body-Part Debuff)
        elif action.get("combat_tactical_archetype") == "called_shot":
            if is_vanished:
                acting_char_data["status_effects"] = [s for s in acting_char_data.get("status_effects", []) if "Hidden in Shadows" not in str(s)]
                if isinstance(session, dict):
                    set_actor_combat_vanished(session, False, user_id=acting_user_id)
            if tier in ("crit_success", "success"):
                reduced_armor = dict(enemy_armor)
                reduced_armor["base_dt"] = int(reduced_armor.get("base_dt", 0) * 0.60)
                tactical_res = calculate_tactical_damage(
                    attacker_attrs=player_attrs,
                    defender_attrs=enemy_attrs,
                    weapon_meta=player_weapon,
                    armor_meta=reduced_armor,
                    tier="success",
                    attacker_level=acting_char_data.get("level", 1),
                    defender_max_hp=target_enemy.get("max_hp", 100),
                )
                mult = 1.60 if tier == "crit_success" else 1.15
                cs_dmg = max(6, int(round(tactical_res["damage"] * mult)))
                applied_dmg = _apply_damage_to_enemy(target_enemy, cs_dmg)
                total_enemy_damage += applied_dmg

                lbl_low = str(action.get("label", "")).lower()
                if any(w in lbl_low for w in ("eye", "eyes", "head", "face", "visor", "sensor", "helm")):
                    part_status = "Blinded [-25% ACC] [2 turns]"
                elif any(w in lbl_low for w in ("hand", "wrist", "arm", "weapon", "grip", "blade", "gun")):
                    part_status = "Disarmed [-25% ATK] [2 turns]"
                else:
                    part_status = "Crippled [-25% EVA] [2 turns]"
                    target_enemy.setdefault("status_effects", []).append("Staggered [1 turn]")
                target_enemy.setdefault("status_effects", []).append(part_status)
                crit_tag = " *(Critical Called Shot!)*" if tier == "crit_success" else ""
                combat_log.append(
                    f"🎯 **{acting_char_name}** landed a precision called shot on **{target_enemy['name']}**: "
                    f"Dealt **{applied_dmg} damage** (piercing 40% armor) and inflicted **{part_status.split('[')[0].strip()}**{crit_tag}!"
                )
            else:
                combat_log.append(
                    f"🎯 **{acting_char_name}** aimed a called shot at **{target_enemy['name']}**, "
                    f"but the narrow target slipped out of reach!"
                )

        else:
            action_stance = action.get("stance")
            attack_type = action.get("attack_type")
            tactical_res = calculate_tactical_damage(
                attacker_attrs=player_attrs,
                defender_attrs=enemy_attrs,
                weapon_meta=player_weapon,
                armor_meta=enemy_armor,
                tier=tier,
                attacker_level=acting_char_data.get("level", 1),
                defender_max_hp=target_enemy.get("max_hp", 100),
                attack_type=attack_type,
                stance=action_stance
            )
            m_dmg = tactical_res["damage"]
            if tactical_res["blocked"]:
                combat_log.append(f"🛡️ **{target_enemy['name']}** raised their guard, mitigating 60% damage!")

            # Instant execution threshold for wounded targets on crit (disabled for non-lethal subdue targets)
            if not target_enemy.get("requires_non_lethal_subdue") and tier == "crit_success" and (target_enemy.get("hp", 100) / max(1, target_enemy.get("max_hp", 100))) <= 0.60:
                if random.random() < 0.30:
                    m_dmg = target_enemy.get("hp", 100)

            if tier in ("crit_success", "success") and m_dmg > 0:
                total_enemy_damage += m_dmg
                _basic_info = get_awakened_basic_strike(p_attr, p_med, equipped_weapon=weapon_item) if is_anom_combat else {}
                _shred_m, _attr_m = _pre_mark_anomalous_hit(
                    target_enemy, int(_basic_info.get("stability_shred", 12) or 12), _basic_info.get("attack_attribute", p_attr)
                )
                _apply_damage_to_enemy(target_enemy, m_dmg)
                _post_resolve_anomalous_hit(target_enemy, _shred_m, _attr_m)

                tags_log = []
                if tactical_res.get("dual_wield") or action_stance == "dual_wield" or action.get("dual_wield"):
                    tags_log.append("*(Dual-Wield Flurry! +15% damage)*")
                if tactical_res.get("versatile_2h"):
                    tags_log.append("*(Two-Handed Grip! +15% damage)*")
                if tactical_res.get("flanking_backstab"):
                    tags_log.append("*(Flanking Backstab! +50% damage)*")
                    acting_char_data["status_effects"] = [s for s in acting_char_data.get("status_effects", []) if "Hidden in Shadows" not in str(s)]
                    if isinstance(session, dict):
                        set_actor_combat_vanished(session, False, user_id=acting_user_id)
                elif tactical_res.get("ambush_strike"):
                    tags_log.append("*(Ambush Strike! +50% surprise damage)*")
                    if isinstance(session, dict):
                        set_actor_combat_vanished(session, False, user_id=acting_user_id, also_set_hidden=False)
                if tactical_res.get("brawler_synergy"):
                    tags_log.append("*(Brawler Synergy! +25% unarmed strike)*")
                if tactical_res.get("ap_ratio", 0) > 0:
                    ap_pct = int(round(tactical_res["ap_ratio"] * 100))
                    tags_log.append(f"*(Armor Pierced {ap_pct}%)*")
                tag_str = (" " + " ".join(tags_log)) if tags_log else ""
                combat_log.append(f"⚔️ **{acting_char_name}** attacked **{target_enemy['name']}**: Dealt **{m_dmg} damage**{tag_str}.")
            else:
                if tactical_res.get("flanking_backstab") or is_vanished:
                    acting_char_data["status_effects"] = [s for s in acting_char_data.get("status_effects", []) if "Hidden in Shadows" not in str(s)]
                    if isinstance(session, dict):
                        set_actor_combat_vanished(session, False, user_id=acting_user_id)
                if tactical_res.get("ambush_strike") or player_attrs.get("is_ambush"):
                    if isinstance(session, dict):
                        set_actor_combat_vanished(session, False, user_id=acting_user_id, also_set_hidden=False)
                combat_log.append(f"⚔️ **{acting_char_name}** attacked **{target_enemy['name']}**: Attack failed / deflected.")

            if tactical_res.get("stagger_inflicted"):
                acting_char_data.setdefault("status_effects", []).append("Staggered [1 turn]")
                combat_log.append(f"🛡️ **{target_enemy['name']}**'s heavy tank armor countered the blow! **{acting_char_name}** is Staggered!")

        # Anomalous Wearable On-Hit Debuff Procs
        if is_anom_combat and turn_hit_landed and target_enemy and target_enemy.get("hp", 0) > 0:
            for db_proc in (anom_passives.get("on_hit_debuffs") or []):
                if isinstance(db_proc, dict) and db_proc.get("status"):
                    if random.random() < float(db_proc.get("chance", 0.20)):
                        try_inflict_status(target_enemy, enemy_attrs, f"{db_proc['status']} [2 turns]", combat_log)

    if is_anom_combat and isinstance(session, dict):
        pips_map[uid_pip_key] = update_encounter_pips(
            pips_map.get(uid_pip_key, 0),
            hit_landed=turn_hit_landed,
            triggered_break_this_turn=turn_triggered_break,
            cast_ultimate=turn_cast_ultimate,
            extra_break_pips=turn_extra_pips,
        )
        session["player_resonance_pips"] = pips_map

    # Additional synchronized player actions (co-op sync turns or multi-action batches)
    for extra_act in (actions[1:] if isinstance(actions, list) and len(actions) > 1 else []):
        if not isinstance(extra_act, dict):
            continue
        living_for_extra = [m for m in enemies if m.get("hp", 0) > 0]
        if not living_for_extra:
            break
        ex_foe = living_for_extra[0]
        raw_ex_target = extra_act.get("target_enemy") or extra_act.get("combat_target") or extra_act.get("target")
        if isinstance(raw_ex_target, dict) and raw_ex_target.get("hp", 0) > 0:
            ex_foe = raw_ex_target
        elif isinstance(raw_ex_target, str) and raw_ex_target.strip():
            ex_t_low = raw_ex_target.strip().lower()
            ex_foe = next((m for m in living_for_extra if str(m.get("name") or "").lower() == ex_t_low), ex_foe)
        elif isinstance(extra_act.get("target_index"), int) and 0 <= extra_act["target_index"] < len(enemies):
            cand_foe = enemies[extra_act["target_index"]]
            if isinstance(cand_foe, dict) and cand_foe.get("hp", 0) > 0:
                ex_foe = cand_foe
        ex_char = extra_act.get("char") if isinstance(extra_act.get("char"), dict) else acting_char_data
        ex_name = ex_char.get("name", acting_char_name)
        ex_uid = extra_act.get("user_id") or ex_char.get("user_id") or acting_user_id
        ex_attrs = (
            calculate_combat_attributes(ex_char, scenario=session.get("scenario", "fantasy") if isinstance(session, dict) else "fantasy")
            if isinstance(ex_char, dict) and ex_char is not acting_char_data
            else player_attrs
        )
        ex_tier = extra_act.get("tier") or (
            extra_act["check"].tier if "check" in extra_act and hasattr(extra_act["check"], "tier") else "success"
        )
        if ex_tier in ("crit_success", "success"):
            ex_dmg = max(8, int(ex_attrs.get("atk", 20)))
            if ex_tier == "crit_success":
                ex_dmg = int(round(ex_dmg * 1.5))
            if is_anom_combat:
                ex_attr = normalize_anomalous_attribute(ex_char.get("attribute") or p_attr, fallback=p_attr)
                ex_arch = str(ex_char.get("combat_archetype") or p_arch).strip().lower()
                ex_cat_bonus = 0.25 if any("Harmony" in str(s) for s in ex_char.get("status_effects", [])) else 0.0
                _sh_ex = compute_stability_shred(12, ex_attr, ex_arch, ex_attr, ex_foe, catalyst_bonus=ex_cat_bonus)
                if not ex_foe.get("is_breached") and int(ex_foe.get("max_stability", 0) or 0) > 0:
                    if int(ex_foe.get("stability", 100)) - _sh_ex <= 0:
                        ex_foe["_will_breach_this_hit"] = True
                if ex_attr == "aether":
                    ex_foe["_pierce_temp_hp_this_hit"] = True
                _apply_damage_to_enemy(ex_foe, ex_dmg)
                ex_foe.pop("_will_breach_this_hit", None)
                ex_foe.pop("_pierce_temp_hp_this_hit", None)
                ex_triggered_break = False
                ex_extra_pips = 0
                if ex_foe.get("hp", 0) > 0:
                    ex_atk_power = max(ex_attrs.get("matk", 20), ex_attrs.get("atk", 20))
                    ex_br = apply_stability_and_break(ex_foe, _sh_ex, ex_attr, ex_atk_power, combat_log)
                    if ex_br.get("triggered_break"):
                        ex_foe["_breached_this_round"] = True
                        ex_triggered_break = True
                        ex_extra_pips = int(ex_br.get("bonus_pips", 0) or 0)
                        if ex_br.get("mp_refund", 0) > 0 and isinstance(ex_char, dict):
                            mp_ref = int(ex_br["mp_refund"])
                            ex_char["mp"] = min(ex_char.get("max_mp", 100), ex_char.get("mp", 0) + mp_ref)
                            player_mp_change_by_name[ex_name] = player_mp_change_by_name.get(ex_name, 0) + mp_ref
                        if ex_br.get("squad_heal", 0) > 0 and isinstance(ex_char, dict):
                            sh_amt = int(ex_br["squad_heal"])
                            ex_char["hp"] = min(ex_char.get("max_hp", 100), ex_char.get("hp", 0) + sh_amt)
                            player_heal_by_name[ex_name] = player_heal_by_name.get(ex_name, 0) + sh_amt
                        ex_other_foes = [f for f in enemies if f is not ex_foe and f.get("hp", 0) > 0]
                        if ex_splash := int(ex_br.get("aoe_splash_damage", 0) or 0):
                            if ex_other_foes:
                                for of in ex_other_foes:
                                    _apply_damage_to_enemy(of, ex_splash)
                                    total_enemy_damage += ex_splash
                                combat_log.append(f"🌪️ **Synchronized Vacuum Shear (AoE Splash):** Dealt **{ex_splash} damage** to secondary foes!")
                        elif ex_chain := int(ex_br.get("chain_damage", 0) or 0):
                            if ex_other_foes:
                                _apply_damage_to_enemy(ex_other_foes[0], ex_chain)
                                total_enemy_damage += ex_chain
                                combat_log.append(f"⚡ **Synchronized Grid Overload (Chain Arc):** Arced to **{ex_other_foes[0]['name']}** for **{ex_chain} damage**!")
                    elif ex_br.get("super_break_damage", 0) > 0:
                        sb = int(ex_br["super_break_damage"])
                        _apply_damage_to_enemy(ex_foe, sb)
                        total_enemy_damage += sb
                ex_pip_key = str(ex_uid or ex_name)
                pips_map[ex_pip_key] = update_encounter_pips(
                    pips_map.get(ex_pip_key, 0),
                    hit_landed=True,
                    triggered_break_this_turn=ex_triggered_break,
                    cast_ultimate=False,
                    extra_break_pips=ex_extra_pips,
                )
                if isinstance(session, dict):
                    session["player_resonance_pips"] = pips_map
            else:
                _apply_damage_to_enemy(ex_foe, ex_dmg)
            total_enemy_damage += ex_dmg
            combat_log.append(f"⚔️ **{ex_name}** attacked **{ex_foe['name']}**: Dealt **{ex_dmg} damage**.")

    # --- PHASE 2: FRIENDLY ALLIES (Automated Companions, Autonomous Constructs & Party Members) ---
    if is_anom_combat:
        for c_unit in [a for a in living_allies if a.get("is_autonomous_construct") and a.get("hp", 0) > 0]:
            windup = c_unit.get("queued_windup")
            if not windup:
                continue
            if windup.get("_queued_this_round"):
                windup.pop("_queued_this_round", None)
                combat_log.append(f"⚙️ **{c_unit['name']}** charges **{windup['name']}** for next turn!")
                continue
            engageable_c = [
                e for e in enemies
                if e.get("hp", 0) > 0 and not (
                    e.get("requires_non_lethal_subdue") and (
                        e.get("is_breached")
                        or e.get("hp", 100) <= 1
                        or (e.get("hp", 100) / max(1, e.get("max_hp", 100))) <= float(e.get("subdue_threshold_pct") or 0.35)
                    )
                )
            ]
            c_unit["queued_windup"] = None
            if engageable_c:
                t_foe = engageable_c[0]
                w_dmg = int(windup.get("damage", 16))
                _apply_damage_to_enemy(t_foe, w_dmg)
                total_enemy_damage += w_dmg
                if t_foe.get("hp", 0) > 0 and int(t_foe.get("max_stability", 0) or 0) > 0:
                    c_shred = compute_stability_shred(15, str(windup.get("attr") or "aether"), "vanguard", str(windup.get("attr") or "aether"), t_foe)
                    c_br = apply_stability_and_break(t_foe, c_shred, str(windup.get("attr") or "aether"), w_dmg, combat_log)
                    if c_br.get("triggered_break"):
                        t_foe["_breached_this_round"] = True
                    elif c_br.get("super_break_damage", 0) > 0:
                        sb = int(c_br["super_break_damage"])
                        _apply_damage_to_enemy(t_foe, sb)
                        total_enemy_damage += sb
                combat_log.append(
                    f"🤖 **{c_unit['name']}** executed queued **{windup['name']}** on **{t_foe['name']}**: Dealt **{w_dmg} damage**!"
                )

    living_companions = [
        a for a in living_allies
        if a.get("name") != acting_char_name and a.get("hp", 0) > 0 and not a.get("is_autonomous_construct")
    ]
    for comp in living_companions:
        living_enemies = [m for m in enemies if m.get("hp", 0) > 0]
        if not living_enemies:
            break
        if is_anom_combat and not comp.get("is_summon") and (
            comp.get("anomalous_npc_tag") in ("special_agent", "civilian", "folklore_villager")
            or comp.get("is_folklore_villager")
        ):
            from mechanics.social.anomalous_npc_tags import resolve_anomalous_ally_combat_action
            resolve_anomalous_ally_combat_action(
                comp=comp,
                living_enemies=living_enemies,
                living_allies=living_allies,
                current_npcs=current_npcs,
                apply_damage_fn=_apply_damage_to_enemy,
                combat_log=combat_log,
            )
            continue

        comp_name = comp.get("name", "Companion")
        comp_arch = comp.get("archetype", "Companion")
        comp_stats = comp.get("stats", {})
        comp_mp = int(comp.get("mp", 20) or 0)

        # 1. Deterministic Priority Heuristic 1: Emergency Ally Healing (Cycle 1 Locked)
        critically_wounded = [
            a for a in living_allies
            if a.get("hp", 0) > 0 and (float(a.get("hp", 100)) / max(1.0, float(a.get("max_hp", 100)))) <= 0.30
        ]
        is_healer = comp_arch in ("Caster", "Support", "Medic", "Cleric", "Sage") or comp_stats.get("INT", 3) >= 5
        if critically_wounded and is_healer and comp_mp >= 6:
            heal_target = min(critically_wounded, key=lambda a: float(a.get("hp", 100)) / max(1.0, float(a.get("max_hp", 100))))
            heal_amt = int(comp.get("level", 1) * 6 + 15)
            comp["mp"] = comp_mp - 6
            t_hp = int(heal_target.get("hp", 100) or 0)
            t_max = int(heal_target.get("max_hp", 100) or 100)
            heal_target["hp"] = min(t_max, t_hp + heal_amt)
            actual_healed = heal_target["hp"] - t_hp
            t_name = heal_target.get("name", "Ally")
            if t_name in player_heal_by_name:
                player_heal_by_name[t_name] += actual_healed
            combat_log.append(f"✨ **{comp_name}** channeled restorative aid into **{t_name}**: Restored **+{actual_healed} HP**!")
            if actual_healed > 0:
                all_eids = [str(e.get("id") or e.get("name")) for e in living_enemies if e.get("hp", 0) > 0]
                update_threat_on_action(
                    threat_matrix,
                    str(comp_name),
                    "heal",
                    [],
                    all_eids,
                    effective_healing=actual_healed,
                    sticky_taunts=sticky_taunts,
                )
            continue

        # 2. Deterministic Priority Heuristic 2: Safe Target Selection (Honoring non-lethal & capture)
        if is_non_lethal_active:
            target_m = min(living_enemies, key=lambda e: e.get("hp", 100))
        else:
            safe_pool = [
                e for e in living_enemies
                if not (
                    e.get("requires_non_lethal_subdue") and (
                        e.get("is_breached")
                        or e.get("hp", 100) <= 1
                        or (e.get("hp", 100) / max(1, e.get("max_hp", 100))) <= float(e.get("subdue_threshold_pct") or 0.35)
                    )
                )
            ]
            target_m = random.choice(safe_pool) if safe_pool else living_enemies[0]

        # 3. Deterministic Priority Heuristic 3: Tactical Weapon Attack
        best_comp_stat = max(["STR", "AGI", "INT", "PER"], key=lambda s: get_combatant_stat(comp, s, default=3))
        comp_stat_val = get_combatant_stat(comp, best_comp_stat, default=3)
        m_def_val = get_combatant_stat(target_m, "END", default=3)

        hit_chance = max(25, min(95, 55 + (comp_stat_val - m_def_val) * 7))
        roll = random.randint(1, 100)

        if roll <= hit_chance:
            comp_lvl = comp.get("level", 1)
            stat_bonus = max(1, comp_stat_val * 2)
            base_dmg = max(5, int(stat_bonus + comp_lvl * 3 + random.randint(2, 6)))
            comp_dmg = max(4, min(target_m.get("hp", 100), base_dmg))
            _apply_damage_to_enemy(target_m, comp_dmg, attacker=comp)
            if comp.get("is_summon"):
                combat_log.append(f"🐾 **{comp_name}** attacked **{target_m['name']}**: Dealt **{comp_dmg} damage**.")
            else:
                combat_log.append(f"🎯 **{comp_name}** attacked **{target_m['name']}**: Dealt **{comp_dmg} damage**.")
        else:
            combat_log.append(f"🎯 **{comp_name}** attacked **{target_m['name']}**: Attack deflected by {target_m['name']}.")

    # --- PHASE 3: ENEMY COUNTER-ATTACKS (Surviving Enemies) ---
    living_enemies = [m for m in enemies if m.get("hp", 0) > 0]
    total_player_damage = 0
    attackers_against_player = []

    if living_enemies and not fled_battle:
        for enemy in living_enemies:
            if enemy.get("hp", 0) <= 0:
                continue

            enemy_arch = enemy.get("archetype", "Brute")
            tier_rank = enemy.get("tier_rank", 2)
            
            # Low-Morale Routing & Surrender for Minions & Skirmishers (Cycle 2 Locked)
            routing_archetypes = {"Skirmisher", "Scavenger", "Scrap-Scavenger", "Rival Debater", "Gossip Monger", "Coward"}
            is_demoralized = any("Demoralized" in str(s) for s in enemy.get("status_effects", []))
            hp_pct = enemy.get("hp", 100) / max(1, enemy.get("max_hp", 100))
            
            if tier_rank <= 2 and (enemy_arch in routing_archetypes or is_demoralized):
                if hp_pct < 0.15 or is_demoralized:
                    # Roll morale check against END and CHA
                    stats = enemy.get("stats", {})
                    morale = stats.get("END", 1) + stats.get("CHA", 1)
                    if random.random() > (morale / 20.0):
                        if is_non_lethal_active or enemy.get("requires_non_lethal_subdue") or (isinstance(session, dict) and session.get("active_capture_quest")):
                            surrendered_enemies.append(enemy["name"])
                            surrendered_enemy_dicts.append(dict(enemy))
                            enemy["hp"] = 1
                            enemy["is_subdued"] = True
                            enemy["is_subdued_ready"] = True
                            combat_log.append(f"🏳️ **{enemy['name']}** threw down their weapons and surrendered as a captive!")
                            continue
                        else:
                            fled_enemies.append(enemy["name"])
                            enemy["hp"] = 0  # Remove from combat
                            combat_log.append(f"🏃💨 **{enemy['name']}**'s morale broke! They dropped their weapon and fled the battlefield!")
                            continue
                        
            # Check for Crowd-Control Turn Suppression & Fresh Anomalous Breach Stagger
            if is_anom_combat and enemy.get("is_breached") and enemy.get("_breached_this_round"):
                combat_log.append(f"⚡ **{enemy['name']}** is **ANOMALY BREACHED** and staggered this turn!")
                continue
            enemy_effects = [str(s).lower() for s in enemy.get("status_effects", [])]
            cc_keywords = ("stunned", "staggered", "frozen", "paralyzed", "asleep", "sleep", "surprised", "petrified")
            active_cc = next((s for s in enemy_effects if any(k in s for k in cc_keywords)), None)
            
            if active_cc:
                cc_label = active_cc.split("[")[0].strip().title()
                combat_log.append(f"💫 **{enemy['name']}** is **{cc_label}** and cannot act this turn!")
                continue

            active_targets = [a for a in living_allies if a.get("hp", 0) > 0]
            if not active_targets:
                break

            # Covert Vanish Rule: Enemies cannot target a vanished/hidden player if visible companions are present!
            def _is_ally_vanished(ally_obj: dict) -> bool:
                if any("Hidden in Shadows" in str(s) for s in ally_obj.get("status_effects", [])):
                    return True
                a_uid = ally_obj.get("user_id")
                if isinstance(session, dict):
                    if a_uid is not None:
                        return is_actor_combat_vanished(session, a_uid)
                    if ally_obj.get("name") == acting_char_name:
                        return is_actor_combat_vanished(session, acting_user_id)
                return False

# Phase 3 Evolution: Check Staggered status (skip attack if staggered)
            if any("stagger" in str(s.get("name", s) if isinstance(s, dict) else s).lower() for s in enemy.get("status_effects", [])):
                enemy_name_dsp = enemy.get("name", "The enemy")
                combat_log.append(f"💫 **{enemy_name_dsp}** is **Staggered** and reels helplessly, unable to strike this turn!")
                continue

            visible_targets = [a for a in active_targets if not _is_ally_vanished(a)]
            target_pool = visible_targets if visible_targets else active_targets
            construct_decoys = [a for a in target_pool if a.get("is_autonomous_construct") and a.get("hp", 0) > 0]

            eid_cur = str(enemy.get("id") or enemy.get("name"))
            # Threat Ledger target resolution: Sticky Taunts > Construct Decoys > Archetype Priority > Threat Score > Random
            if sticky_taunts and eid_cur in sticky_taunts:
                threat_target = resolve_threat_target(eid_cur, target_pool, threat_matrix, sticky_taunts)
                chosen_target = threat_target or random.choice(target_pool)
            elif construct_decoys and random.random() < 0.60:
                chosen_target = construct_decoys[0]
            elif enemy_arch in ("Stalker", "Assassin", "Chrome Cyberhound"):
                chosen_target = min(target_pool, key=lambda t: t.get("hp", 100))
            elif enemy_arch in ("Caster", "Psionic Alien", "Netrunner Spec-Op"):
                chosen_target = min(target_pool, key=lambda t: _get_entity_stat(t, "LUK"))
            elif enemy_arch in ("Brute", "Heavy Mech", "Heavy Borg"):
                chosen_target = max(target_pool, key=lambda t: _get_entity_stat(t, "STR"))
            elif threat_target := resolve_threat_target(eid_cur, target_pool, threat_matrix):
                chosen_target = threat_target
            else:
                chosen_target = random.choice(target_pool)

            target_name = chosen_target.get("name", "Hero")
            target_max_hp = chosen_target.get("max_hp", 100)

            enemy_weapon = dict(get_enemy_weapon_profile(enemy_arch))
            if isinstance(enemy.get("weapon_profile"), dict) and enemy["weapon_profile"]:
                enemy_weapon.update(enemy["weapon_profile"])
            enemy_atk_attrs = calculate_combat_attributes(enemy.get("stats", {}))
            enemy_atk_attrs.update({
                "weaknesses": enemy.get("weaknesses", []),
                "resistances": enemy.get("resistances", []),
                "immunities": enemy.get("immunities", [])
            })

            # Check for Status Effects and Elite Passives
            if any("Demoralized" in str(s) for s in enemy.get("status_effects", [])):
                enemy_atk_attrs["atk"] = max(1, int(enemy_atk_attrs.get("atk", 10) * 0.8))
                enemy_atk_attrs["matk"] = max(1, int(enemy_atk_attrs.get("matk", 10) * 0.8))
                
            if any("Weakened" in str(s) for s in enemy.get("status_effects", [])):
                enemy_atk_attrs["atk"] = max(1, int(enemy_atk_attrs.get("atk", 10) * 0.7))
                enemy_atk_attrs["matk"] = max(1, int(enemy_atk_attrs.get("matk", 10) * 0.7))
                
            if any("Enraged" in str(s) for s in enemy.get("status_effects", [])):
                enemy_atk_attrs["atk"] = int(enemy_atk_attrs.get("atk", 10) * 1.3)
                enemy_atk_attrs["matk"] = int(enemy_atk_attrs.get("matk", 10) * 1.3)
                
            if "Overclocked" in enemy.get("affixes", []):
                enemy_atk_attrs["atk"] = int(enemy_atk_attrs.get("atk", 10) * 1.25)
                enemy_atk_attrs["matk"] = int(enemy_atk_attrs.get("matk", 10) * 1.25)
                enemy_atk_attrs["acc"] = enemy_atk_attrs.get("acc", 66) + 15

            enemy_atk_attrs["atk"] += enemy_weapon.get("atk_bonus", 0)
            enemy_atk_attrs["matk"] += enemy_weapon.get("matk_bonus", 0)

            # Target defender attributes & gear (Calculated before intent execution so status effects can check gear tags)
            t_user_id = chosen_target.get("user_id", 0)
            t_equipped = db.get_equipment(t_user_id) if t_user_id else {}
            t_equipped_items = [i for i in t_equipped.values() if i] if t_equipped else []
            target_attrs = calculate_combat_attributes(chosen_target, t_equipped_items)
            target_armor = parse_equipment_metadata(t_equipped.get("Armor") or t_equipped.get("Top") or {})

            if "Phasing" in enemy.get("affixes", []):
                target_attrs["base_dt"] = max(0, int(target_attrs.get("base_dt", 0) * 0.5))
                target_attrs["block_chance"] = 0

            # --- Telegraphed Move (Intent) Execution (Cycle 1 & Cycle 2 Locked) ---
            from mechanics.combat.enemies import get_intent_code
            cur_intent = str(enemy.get("intent") or "").strip()
            cur_intent_code = enemy.get("intent_code") or get_intent_code(cur_intent)
            is_heavy_intent = (cur_intent_code == "heavy")
            is_magic_intent = (cur_intent_code == "magic")
            is_ambush_intent = (cur_intent_code == "ambush")
            is_defensive_intent = (cur_intent_code == "defensive")
            is_swarm_intent = (cur_intent_code == "swarm")

            if is_defensive_intent:
                enemy_atk_attrs["base_dt"] = enemy_atk_attrs.get("base_dt", 0) + 8
                enemy_atk_attrs["block_chance"] = min(85, enemy_atk_attrs.get("block_chance", 0) + 25)
                combat_log.append(f"🛡️ **{enemy['name']}** holds their defensive posture! (+8 DT, +25% Block)")

            if is_swarm_intent:
                if "multiplying" in cur_intent.lower():
                    heal_amt = int(enemy.get("max_hp", 50) * 0.20)
                    enemy["hp"] = min(enemy.get("max_hp", 50), enemy.get("hp", 0) + heal_amt)
                    combat_log.append(f"🌀 **{enemy['name']}** multiplies rapidly! Restored **+{heal_amt} HP** and expanded the swarm!")
                else:
                    enemy_atk_attrs["acc"] = enemy_atk_attrs.get("acc", 66) + 15
                    try_inflict_status(chosen_target, target_attrs, "Swarmed [-10% ACC] [2 turns]", combat_log)

            enemy_anom_tag = str(enemy.get("anomalous_npc_tag") or "").strip().lower()
            hostile_sa_cast_note = ""
            if enemy_anom_tag == "civilian":
                enemy["mp"] = 0
                enemy["max_mp"] = 0
                is_magic_intent = False
            elif enemy_anom_tag == "special_agent":
                from mechanics.social.anomalous_npc_tags import resolve_hostile_special_agent_ability_modifier
                sa_mod = resolve_hostile_special_agent_ability_modifier(enemy, combat_log)
                if isinstance(sa_mod, dict):
                    if sa_mod.get("skip_attack"):
                        continue
                    sp_e = sa_mod.get("spell") or {}
                    mult_e = float(sa_mod.get("damage_mult", 1.25) or 1.25)
                    enemy_atk_attrs["atk"] = int(enemy_atk_attrs.get("atk", 12) * mult_e)
                    enemy_atk_attrs["matk"] = int(enemy_atk_attrs.get("matk", 12) * mult_e)
                    if sp_e.get("damage_type"):
                        enemy_weapon["damage_types"] = {str(sp_e["damage_type"]): 1.0}
                    if sp_e.get("name"):
                        hostile_sa_cast_note = f" *(Cast **{sp_e['name']}** — -{sa_mod.get('cost', 8)} MP!)*"
                is_magic_intent = False

            if is_magic_intent:
                mana_cost = 6 + (enemy.get("level", 1) * 2)
                current_mp = enemy.get("mp", enemy.get("max_mp", 20))
                if current_mp >= mana_cost:
                    enemy["mp"] = current_mp - mana_cost
                    enemy_atk_attrs["matk"] = int(enemy_atk_attrs.get("matk", 15) * 1.3)
                    enemy_weapon["damage_types"] = {"magical": 1.0}
                else:
                    # Out of mana -> spell fizzles into a weak physical struggle (40% damage penalty)
                    is_magic_intent = False
                    enemy_atk_attrs["atk"] = max(1, int(enemy_atk_attrs.get("atk", 10) * 0.6))
                    enemy_weapon["damage_types"] = {"physical": 1.0}
                    combat_log.append(f"💨 **{enemy['name']}** attempted to channel arcane energy, but is out of mana! Reverting to a desperate struggle strike!")

            if is_ambush_intent:
                enemy_weapon["armor_penetration"] = 0.40

            # If the acting player chose a 2H versatile strike this turn, temporarily suppress shield defense for this exchange
            if t_user_id == acting_user_id and action.get("stance") == "2H":
                shield_item = t_equipped.get("Shield")
                if shield_item:
                    shield_meta = parse_equipment_metadata(shield_item)
                    shield_dt = shield_meta.get("base_dt", shield_meta.get("dt_contribution", 0))
                    target_attrs["block_chance"] = 0
                    if shield_dt > 0:
                        target_attrs["base_dt"] = max(0, target_attrs.get("base_dt", 0) - shield_dt)

            # If the acting player used Defensive Guard, apply the temporary DT and Block buff
            if t_user_id == acting_user_id and (c_type == "DEFENSIVE_GUARD" or action.get("action_category") == "guard"):
                target_attrs["base_dt"] = target_attrs.get("base_dt", 0) + 6
                target_attrs["block_chance"] = min(90, target_attrs.get("block_chance", 0) + 30)

            # Accuracy vs Evasion hit check (Optics / Precision counter)
            has_optics = any(t in enemy_atk_attrs.get("tags", []) for t in ("precision", "optics", "hud", "smart_link"))
            optics_bonus = 5 if has_optics else 0
            base_hit = 50 + (enemy_atk_attrs.get("acc", 66) - (target_attrs.get("eva", 11) - optics_bonus))
            if t_user_id == acting_user_id and action.get("tier") in ("fail", "failure", "crit_fail"):
                base_hit += 25
            hit_chance = max(20, min(95, base_hit))
            roll = random.randint(1, 100)

            if roll <= 10:
                e_tier = "crit_success"
            elif roll <= hit_chance:
                e_tier = "success"
            else:
                e_tier = "fail"

            e_res = calculate_tactical_damage(
                attacker_attrs=enemy_atk_attrs,
                defender_attrs=target_attrs,
                weapon_meta=enemy_weapon,
                armor_meta=target_armor,
                tier=e_tier,
                attacker_level=enemy.get("level") or 1,
                defender_max_hp=target_max_hp,
                is_enemy_attacker=True
            )
            e_dmg = e_res["damage"]

            # Phase 3 Combat Evolution: Unleash and consume armed Boss Telegraph
            telegraph = enemy.get("telegraphed_skill")
            supreme_note = ""
            if telegraph and isinstance(telegraph, dict):
                s_name = telegraph.get("skill_name", "Supreme Strike")
                supreme_note = f" *(Supreme Attack: {s_name}!)*"
                if e_tier != "fail":
                    dmg_mult = float(telegraph.get("damage_mult", 1.75))
                    e_dmg = max(1, int(e_dmg * dmg_mult))
                    combat_log.append(f"💥 **SUPREME ATTACK UNLEASHED!** **{enemy['name']}** unleashed **{s_name}**!")
                else:
                    combat_log.append(f"💨 **{enemy['name']}** unleashed **{s_name}**, but **{target_name}** narrowly dodged the apocalyptic blow!")
                # Consume telegraph regardless of hit/miss so it never persists indefinitely
                enemy["telegraphed_skill"] = None
                boss_telegraph_state.pop(eid_cur, None)

            if is_heavy_intent and not e_res["blocked"]:
                e_dmg = int(e_dmg * 1.35)
                if any(p.get("name") == target_name for p in player_chars):
                    # Check if player guarded
                    if not (c_type == "DEFENSIVE_GUARD" or action.get("action_category") == "guard"):
                        try_inflict_status(chosen_target, target_attrs, "Staggered [1 turn]", combat_log)

            if e_res["blocked"]:
                combat_log.append(f"🛡️ **{target_name}** blocked **{enemy['name']}**'s strike with their shield!")

            if e_res.get("stagger_inflicted"):
                enemy.setdefault("status_effects", []).append("Staggered [1 turn]")
                combat_log.append(f"🛡️ **{target_name}**'s heavy tank armor countered the blow! **{enemy['name']}** is Staggered!")

            if e_dmg > 0:
                e_dmg = max(1, e_dmg)
                # If enemy has poison or toxic ailment, attempt to inflict with Hazmat repel check
                if enemy_weapon.get("damage_types", {}).get("poison", 0) > 0 or any(w in enemy_arch.lower() for w in ["poison", "toxic", "venom", "spider", "snake"]):
                    try_inflict_status(chosen_target, target_attrs, "Poisoned [2 turns]", combat_log)
                # Check if target is a party player or friendly companion
                if any(p.get("name") == target_name for p in player_chars):
                    if enemy["name"] not in attackers_against_player:
                        attackers_against_player.append(enemy["name"])
                    actual_dmg = apply_damage_to_combatant(
                        target=chosen_target,
                        dmg=e_dmg,
                        attacker=enemy,
                        combat_log=combat_log,
                        is_anom_combat=is_anom_combat,
                    )
                    player_damage_by_name[target_name] = player_damage_by_name.get(target_name, 0) + actual_dmg
                    total_player_damage += actual_dmg
                    intent_note = hostile_sa_cast_note or supreme_note
                    if not intent_note:
                        if is_heavy_intent:
                            intent_note = " *(Telegraphed Heavy Strike!)*"
                        elif is_magic_intent:
                            intent_note = " *(Telegraphed Arcane Burst!)*"
                        elif is_ambush_intent:
                            intent_note = " *(Telegraphed Ambush!)*"
                    combat_log.append(f"💥 **{enemy['name']}** attacked **{target_name}**: Dealt **{e_dmg} damage**{intent_note}.")

                    # Reactive Anomalous Wearable On-Hit / Retaliation Debuff Procs
                    if is_anom_combat and e_dmg > 0 and enemy.get("hp", 0) > 0 and target_attrs.get("on_hit_debuffs"):
                        for _r_deb in (target_attrs.get("on_hit_debuffs") or []):
                            if isinstance(_r_deb, dict) and random.random() < float(_r_deb.get("proc_chance", 0.0) or 0.0):
                                _r_ail = str(_r_deb.get("ailment") or "Staggered")
                                _r_eff_str = f"{_r_ail} [2 turns]"
                                if not any(_r_ail.lower() in str(s).lower() for s in enemy.get("status_effects", [])):
                                    enemy.setdefault("status_effects", []).append(_r_eff_str)
                                    combat_log.append(
                                        f"⚡ **Anomalous Retaliation Ward:** **{target_name}**'s gear inflicted **{_r_ail}** on **{enemy['name']}**!"
                                    )

                    # Temporary cosmetic garment degradation if fighting unarmored
                    has_combat_armor = bool(t_equipped.get("Armor")) or (target_attrs.get("base_dt", 0) > 2)
                    if not has_combat_armor:
                        is_severe = (
                            e_dmg >= 8
                            or e_tier == "crit_success"
                            or any(d in enemy_weapon.get("damage_types", {}) for d in ("fire", "acid", "slashing"))
                            or any(a in enemy_weapon.get("attack_types", []) for a in ("slash", "hack", "thrust"))
                        )
                        if is_severe:
                            inflicted = try_inflict_status(chosen_target, target_attrs, "Torn / Scorched Clothes [-1 CHA] [2 turns]", combat_log)
                            if inflicted:
                                combat_log.append(f"🧵 **{target_name}**'s civilian clothes were torn and scorched by the blow! (-1 CHA for 2 turns)")
                                if t_user_id:
                                    try:
                                        db.set_status_effects(t_user_id, chosen_target.get("status_effects", []))
                                    except Exception:
                                        pass
                else:
                    actual_dmg = apply_damage_to_combatant(
                        target=chosen_target,
                        dmg=e_dmg,
                        attacker=enemy,
                        combat_log=combat_log,
                        is_anom_combat=is_anom_combat,
                    )
                    companion_damage_by_name[target_name] = companion_damage_by_name.get(target_name, 0) + actual_dmg
                    # Sync companion HP back to current_npcs and active_party_npcs
                    for npc in current_npcs:
                        if npc.get("name") == target_name:
                            npc["hp"] = chosen_target["hp"]
                            npc["mp"] = chosen_target.get("mp", npc.get("mp", 0))
                    for p_comp in active_party_npcs:
                        if p_comp.get("name") == target_name:
                            p_comp["hp"] = chosen_target["hp"]
                            p_comp["mp"] = chosen_target.get("mp", p_comp.get("mp", 0))
                    h_note = hostile_sa_cast_note or supreme_note
                    if chosen_target.get("is_summon"):
                        combat_log.append(f"💥 **{enemy['name']}** struck summon **{target_name}**: Dealt **{e_dmg} damage**{h_note}.")
                        if chosen_target["hp"] <= 0:
                            combat_log.append(f"💀 **{target_name}** was destroyed!")
                    elif is_anom_combat and chosen_target.get("anomalous_npc_tag") == "civilian":
                        combat_log.append(f"💥 **{enemy['name']}** attacked **{target_name}** (*Civilian*): Dealt **{e_dmg} damage**{h_note}.")
                        if chosen_target["hp"] <= 0:
                            from mechanics.social.anomalous_npc_tags import (
                                apply_civilian_permadeath,
                                is_supernatural_anomalous_entity,
                            )
                            if is_supernatural_anomalous_entity(enemy):
                                apply_civilian_permadeath(sess_id_cbt, session, target_name, enemy.get("name", "Anomalous Entity"))
                                slain_civilians.append({"name": target_name, "killer": enemy.get("name", "Anomalous Entity")})
                                current_npcs = [n for n in current_npcs if n.get("name") != target_name]
                                combat_log.append(
                                    f"💀 **{target_name}** (*Civilian — No Mana Barrier*) could not withstand **{enemy['name']}** and was **permanently killed**!"
                                )
                            else:
                                chosen_target.setdefault("status_effects", []).append("Incapacitated")
                                combat_log.append(f"⚠️ **{target_name}** (*Civilian*) was knocked unconscious!")
                    elif is_anom_combat and chosen_target.get("anomalous_npc_tag") == "special_agent":
                        combat_log.append(f"💥 **{enemy['name']}** attacked **{target_name}** (*Special Agent*): Dealt **{e_dmg} damage**{h_note}.")
                        if chosen_target["hp"] <= 0:
                            if "Incapacitated" not in (chosen_target.get("status_effects") or []):
                                chosen_target.setdefault("status_effects", []).append("Incapacitated")
                            for p_comp in active_party_npcs:
                                if p_comp.get("name") == target_name and "Incapacitated" not in (p_comp.get("status_effects") or []):
                                    p_comp.setdefault("status_effects", []).append("Incapacitated")
                            combat_log.append(
                                f"⚠️ **{target_name}**'s mana barrier shattered — they are **Knocked Out / Incapacitated**!"
                            )
                    else:
                        combat_log.append(f"💥 **{enemy['name']}** attacked **{target_name}**: Dealt **{e_dmg} damage**{h_note}.")
                        if chosen_target["hp"] <= 0:
                            combat_log.append(f"⚠️ **{target_name}** was knocked down!")

                # Tier 4+ Boss Multi-Target Cleave (Cycle 2 & Cycle 3 Locked Decisions)
                is_boss_unit = bool(tier_rank >= 4 or enemy.get("is_boss"))
                if is_boss_unit and e_dmg > 0 and len(target_pool) > 1:
                    sec_pool = [a for a in target_pool if a.get("name") != target_name and a.get("hp", 0) > 0]
                    if sec_pool:
                        sec_target = max(sec_pool, key=lambda t: get_combatant_stat(t, "END") + get_combatant_stat(t, "STR"))
                        sec_name = sec_target.get("name", "Ally")
                        splash_dmg = max(1, int(e_dmg * 0.50))
                        actual_splash = apply_damage_to_combatant(
                            target=sec_target,
                            dmg=splash_dmg,
                            attacker=enemy,
                            combat_log=combat_log,
                            is_anom_combat=is_anom_combat,
                        )
                        if any(p.get("name") == sec_name for p in player_chars):
                            player_damage_by_name[sec_name] = player_damage_by_name.get(sec_name, 0) + actual_splash
                            total_player_damage += actual_splash
                        else:
                            companion_damage_by_name[sec_name] = companion_damage_by_name.get(sec_name, 0) + actual_splash
                            for npc in current_npcs:
                                if npc.get("name") == sec_name:
                                    npc["hp"] = sec_target["hp"]
                                    npc["mp"] = sec_target.get("mp", npc.get("mp", 0))
                            for p_comp in active_party_npcs:
                                if p_comp.get("name") == sec_name:
                                    p_comp["hp"] = sec_target["hp"]
                                    p_comp["mp"] = sec_target.get("mp", p_comp.get("mp", 0))
                        combat_log.append(f"🌊 **CLEAVE!** **{enemy['name']}**'s sweeping strike cleaved into **{sec_name}**: Dealt **{splash_dmg} splash damage**!")

                # In-Combat Affix Passives (Vampiric, Corrosive)
                if "Vampiric" in enemy.get("affixes", []):
                    leech = max(1, int(e_dmg * 0.25))
                    enemy["hp"] = min(enemy.get("max_hp", 100), enemy.get("hp", 0) + leech)
                    combat_log.append(f"🩸 **{enemy['name']}** siphoned life! Healed **+{leech} HP**.")
                
                if "Corrosive" in enemy.get("affixes", []):
                    try_inflict_status(chosen_target, target_attrs, "Corroded Armor [-2 DT] [2 turns]", combat_log)

            elif e_res.get("blocked"):
                # Already logged shield block, do not log "Attack missed"
                pass
            elif e_res.get("hit") and not e_res.get("blocked"):
                combat_log.append(f"🛡️ **{enemy['name']}** struck **{target_name}**, but the blow was completely absorbed by their armor!")
            else:
                combat_log.append(f"💨 **{enemy['name']}** attacked **{target_name}**: Attack missed.")

    # Decrement Summon Durations and purge expired summons
    surviving_npcs = []
    for npc in current_npcs:
        if npc.get("is_summon"):
            npc["summon_duration"] = npc.get("summon_duration", 1) - 1
            if npc["summon_duration"] <= 0 or npc.get("hp", 0) <= 0:
                if npc["summon_duration"] <= 0 and npc.get("hp", 0) > 0:
                    combat_log.append(f"✨ **{npc['name']}**'s duration expired and dissipated back to its planar realm.")
                continue
        surviving_npcs.append(npc)
    current_npcs = surviving_npcs

    # Calculate rewards for dead enemies scaled by Tier Rank
    TIER_REWARD_SCALING = {
        1: (40, 15),    # Minion
        2: (75, 25),    # Standard
        3: (150, 60),   # Elite
        4: (260, 120),  # Miniboss
        5: (450, 250),  # Boss
    }
    xp_gain = 0
    gold_gain = 0
    surviving_enemies = []

    if fled_battle:
        # Player disengaged and escaped: hostiles remain alive elsewhere but encounter ends
        # Emergency Field Extraction (Cycle 3 Locked Decision):
        # Drag downed companions out clamped to 1 HP with Critical Trauma and 20% gold loss
        gold_penalty = 0
        if isinstance(session, dict):
            current_gold = int(session.get("gold", 0) or 0)
            has_downed = any(c.get("hp", 0) <= 0 for c in active_party_npcs)
            if has_downed and current_gold > 0:
                gold_penalty = max(1, int(current_gold * 0.20))
                session["gold"] = max(0, current_gold - gold_penalty)
                gold_gain = -gold_penalty
                combat_log.append(f"⚠️ **EMERGENCY EXTRACTION:** You dragged your fallen allies to safety, but lost **{gold_penalty} gold** in abandoned supplies!")
        for p_comp in active_party_npcs:
            if p_comp.get("hp", 0) <= 0:
                p_comp["hp"] = 1
                curr_status = p_comp.get("status_effects")
                if isinstance(curr_status, str):
                    try:
                        curr_status = json.loads(curr_status)
                    except Exception:
                        curr_status = [curr_status] if curr_status else []
                if not isinstance(curr_status, list):
                    curr_status = []
                p_comp["status_effects"] = curr_status
                if "Critical Trauma [-25% All Stats, 5 turns]" not in p_comp["status_effects"]:
                    p_comp["status_effects"].append("Critical Trauma [-25% All Stats, 5 turns]")
                combat_log.append(f"🩹 **{p_comp.get('name', 'Companion')}** was rescued at 1 HP but suffers from **Critical Trauma**!")
        session["nearby_enemies"] = []
        surviving_enemies = []
    else:
        for m in enemies:
            if m["name"] in yielded_enemies:
                pass # Removed from fight, no XP/Gold, but NOT dead and NOT surviving to attack next turn.
            elif m["name"] in fled_enemies:
                if (m.get("surrendered") or m["name"] in surrendered_enemies) and not m.get("contained_via_parley"):
                    t_rank = m.get("tier_rank")
                    if not t_rank:
                        t_name = str(m.get("tier", "standard")).lower()
                        t_rank = 5 if t_name == "boss" else (4 if t_name == "miniboss" else (3 if t_name == "elite" else (1 if t_name == "minion" else 2)))
                    base_xp, base_gold = TIER_REWARD_SCALING.get(t_rank, (75, 25))
                    multiplier = m.get("xp_multiplier", 1.0)
                    xp_gain += int(base_xp * multiplier)
                    gold_gain += int(base_gold * multiplier)
                else:
                    pass # Fled from fight (or contained via anomalous parley), no generic combat loot.
            elif m.get("hp", 0) <= 0:
                if is_anom_combat and m["name"] not in dead_enemies:
                    from mechanics.world.folklore_mechanics import get_enemy_tether_state, try_resolve_zero_hp_tether
                    if get_enemy_tether_state(m):
                        teth_res = try_resolve_zero_hp_tether(m)
                        if teth_res.get("outcome") == "reformed":
                            combat_log.append(teth_res["message"])
                            surviving_enemies.append(m)
                            continue
                        elif teth_res.get("outcome") == "unsealed_dispersion":
                            m["xp_multiplier"] = round(float(m.get("xp_multiplier", 1.0)) * float(teth_res.get("xp_mult", 0.60)), 2)
                            m["prevent_vault_capture"] = True
                            combat_log.append(teth_res["message"])
                if m["name"] not in dead_enemies:
                    dead_enemies.append(m["name"])
                    dead_enemy_dicts.append(dict(m))
                if not m.get("requires_non_lethal_subdue"):
                    t_rank = m.get("tier_rank")
                    if not t_rank:
                        t_name = str(m.get("tier", "standard")).lower()
                        t_rank = 5 if t_name == "boss" else (4 if t_name == "miniboss" else (3 if t_name == "elite" else (1 if t_name == "minion" else 2)))
                    base_xp, base_gold = TIER_REWARD_SCALING.get(t_rank, (75, 25))
                    multiplier = m.get("xp_multiplier", 1.0)
                    xp_gain += int(base_xp * multiplier)
                    gold_gain += int(base_gold * multiplier)
            else:
                surviving_enemies.append(m)

    # Telegraphed Move Engine (Intent Telemetry)
    for m in surviving_enemies:
        m_anom_tag = str(m.get("anomalous_npc_tag") or "").strip().lower()
        if m_anom_tag == "civilian":
            w_nm = str((m.get("weapon_profile") or {}).get("name") or "weapon")
            m["intent"] = f"Brandishing {w_nm} defensively"
            continue
        if m_anom_tag == "special_agent":
            m["intent"] = random.choice([
                "Calibrating anomalous resonance",
                "Preparing a tactical ability",
                "Lining up a mana-infused strike",
            ])
            continue
        if m.get("tier_rank", 1) >= 3:
            arch = m.get("archetype", "Brute")
            intents = ["Preparing next strike", "Analyzing targets", "Shifting stance"]
            if arch in ("Stalker", "Assassin", "Dark Elf Assassin"):
                intents = ["Preparing to Ambush", "Fading into shadows", "Targeting the weak"]
            elif arch in ("Caster", "Psionic Alien", "Netrunner Spec-Op"):
                intents = ["Channeling a massive spell", "Drawing arcane energy", "Preparing a burst"]
            elif arch in ("Brute", "Heavy Mech", "Heavy Borg"):
                intents = ["Winding up a heavy swing", "Preparing a devastating crush", "Overcharging weapons"]
            elif arch in ("Guardian", "Corrupted Treant"):
                intents = ["Assuming a defensive posture", "Shielding allies", "Preparing a counter"]
            elif arch == "Void Swarm":
                intents = ["Preparing to swarm", "Multiplying rapidly"]
            m["intent"] = random.choice(intents)

    if is_anom_combat:
        for _sm in surviving_enemies:
            if _sm.get("_breached_this_round"):
                _sm.pop("_breached_this_round", None)
            elif _sm.get("is_breached"):
                tick_enemy_breach_recovery(_sm, combat_log)
        if surviving_enemies and not fled_battle and anom_passives:
            reg_pct = float(anom_passives.get("turn_regen_pct", 0.0) or 0.0)
            if reg_pct > 0 and acting_char_data.get("hp", 0) > 0:
                reg_hp = max(1, int(round(acting_char_data.get("max_hp", 100) * reg_pct)))
                reg_mp = max(1, int(round(acting_char_data.get("max_mp", 50) * reg_pct)))
                acting_char_data["hp"] = min(acting_char_data.get("max_hp", 100), acting_char_data.get("hp", 1) + reg_hp)
                acting_char_data["mp"] = min(acting_char_data.get("max_mp", 50), acting_char_data.get("mp", 0) + reg_mp)
                player_heal_by_name[acting_char_name] = player_heal_by_name.get(acting_char_name, 0) + reg_hp
                combat_log.append(f"✨ **Anomalous Vitality Pulse:** Restored **+{reg_hp} HP** and **+{reg_mp} MP**.")
            curse_drain = int(anom_passives.get("cursed_hp_drain_per_turn", 0) or 0)
            if curse_drain > 0 and acting_char_data.get("hp", 0) > 1:
                actual_drain = min(acting_char_data.get("hp", 1) - 1, curse_drain)
                if actual_drain > 0:
                    acting_char_data["hp"] -= actual_drain
                    player_damage_by_name[acting_char_name] = player_damage_by_name.get(acting_char_name, 0) + actual_drain
                    combat_log.append(f"🩸 **Cursed Relic Drain:** Parasitic resonance drained **-{actual_drain} HP**.")

    session["nearby_enemies"] = surviving_enemies
    session["current_npcs"] = current_npcs
    if is_anom_combat and isinstance(session, dict):
        if not surviving_enemies or fled_battle:
            cleanup_anomalous_combat_session_state(session)
        else:
            for c_alive in living_allies:
                if isinstance(c_alive, dict) and c_alive.get("is_autonomous_construct") and c_alive not in current_npcs:
                    current_npcs.append(c_alive)
            session["current_npcs"] = current_npcs
            session["_active_constructs"] = [
                c for c in living_allies if c.get("is_autonomous_construct")
            ]

    if active_party_npcs and isinstance(session, dict):
        combat_over = bool(not surviving_enemies or fled_battle)
        persisted_party_npcs = []
        for p_comp in active_party_npcs:
            p_clean = {k: v for k, v in p_comp.items() if k != "_is_party_npc"}
            if combat_over:
                p_clean.pop("_used_ultimate_this_combat", None)
            persisted_party_npcs.append(p_clean)
        session["party_npcs"] = persisted_party_npcs
        sess_id_cbt = session.get("id") if isinstance(session, dict) else None
        if sess_id_cbt:
            try:
                db.set_session_party_npcs(sess_id_cbt, persisted_party_npcs)
            except Exception:
                pass

    if (not surviving_enemies or fled_battle) and isinstance(session, dict):
        clear_all_combat_vanished(session)

    # Narrative Directive for LLM (Sanitized qualitative summary - Zero Stat Leakage per AGENTS.md §4)
    import re
    def _sanitize_log_for_narrative(log_lines: list[str]) -> list[str]:
        qualitative_lines = []
        for line in log_lines:
            s = line
            def _dmg_sub(m):
                try:
                    val = int(m.group(1))
                except Exception:
                    val = 15
                if val >= 40: return "struck with devastating force"
                elif val >= 20: return "landed a heavy blow"
                elif val >= 10: return "landed a solid strike"
                else: return "landed a glancing hit"
            s = re.sub(r"(?:Dealt \*\*|for \*\*|dealing \*\*)(\d+)(?: explosive| splash)? damage\*\*", _dmg_sub, s, flags=re.IGNORECASE)
            s = re.sub(r"(?:Restored|Healed) \*\*\+?(\d+) HP\*\*", "restored vitality", s, flags=re.IGNORECASE)
            s = re.sub(r"\(\d+/\d+ HP\)", "(weakened)", s, flags=re.IGNORECASE)
            s = re.sub(r"\b\d+\s*HP\b", "vitality", s, flags=re.IGNORECASE)
            s = re.sub(r"\*\*\+\d+ MP\*\*", "restoring mana", s, flags=re.IGNORECASE)
            s = re.sub(r"drained \*\*-\d+ HP\*\*", "drained vitality", s, flags=re.IGNORECASE)
            s = re.sub(r"-\d+ MP", "expending mana", s, flags=re.IGNORECASE)
            s = re.sub(r"\b\d+%\s*(?:damage|reduction|mitigation)?", "substantial force", s, flags=re.IGNORECASE)
            s = re.sub(r"\b\+\d+%\s*[^)]*", "augmented force", s, flags=re.IGNORECASE)
            s = re.sub(r"lost \*\*\d+ gold\*\*", "lost vital supplies", s, flags=re.IGNORECASE)
            s = re.sub(r"\[-?\d+%\s*[^\]]*\]", "", s)
            s = re.sub(r"\[\d+\s*turns?\]", "", s, flags=re.IGNORECASE)
            s = re.sub(r"\*\*(\d+)\*\*", r"\1", s)
            s = re.sub(r"\b\d+\b", "", s)
            qualitative_lines.append(s)
        return qualitative_lines

    qualitative_events = _sanitize_log_for_narrative(combat_log)
    directive_lines = [
        "### DETERMINISTIC COMBAT ROUND OUTCOME (Follow in Story Narrative):",
        f"- Combat Events this turn:\n  " + "\n  ".join(qualitative_events),
        "- STRICT IMMERSION RULE: Describe these tactical actions and physical consequences in prose without mentioning numeric HP numbers, damage digits, or stat math."
    ]
    if yielded_enemies:
        from mechanics.combat import resolve_sparring_defeat
        directive_lines.append(resolve_sparring_defeat({"name": yielded_enemies[0]}))

    if surrendered_enemies:
        names = ", ".join(surrendered_enemies)
        directive_lines.append(f"- Enemies Surrendered: {names} dropped weapons and yielded to the party. Narrate their surrender.")

    if fled_enemies:
        actual_fled = [n for n in fled_enemies if n not in surrendered_enemies]
        if actual_fled:
            names = ", ".join(actual_fled)
            directive_lines.append(f"- Enemies Fled: {names} broke rank and fled the battlefield.")

    if fled_battle:
        directive_lines.append("- Escape: The party successfully disengaged and fled from combat. Narrate their tactical retreat.")
    elif surviving_enemies:
        names = ", ".join(m["name"] for m in surviving_enemies)
        directive_lines.append(f"- Living Enemies: The {names} is/are STILL ALIVE and fighting. Do NOT narrate their defeat.")
    else:
        if not yielded_enemies and not fled_enemies:
            directive_lines.append("- Victory: All hostiles are DEFEATED. Narrate their final defeat and victory.")

    if slain_civilians:
        slain_desc = ", ".join(f"{sc['name']} (slain by {sc['killer']})" for sc in slain_civilians)
        directive_lines.append(
            f"- Civilian Permadeath: {slain_desc} lacked any mana barrier and died permanently in the anomalous assault. "
            f"Narrate their fatal death with grim urban-horror gravity (zero raw HP digits)."
        )

    directive = "\n".join(directive_lines)

    return {
        "directive": directive,
        "slain_civilians": slain_civilians,
        "combat_log": combat_log,
        "fled_battle": fled_battle,
        "player_damage_by_name": player_damage_by_name,
        "player_heal_by_name": player_heal_by_name,
        "player_mp_change_by_name": player_mp_change_by_name,
        "companion_damage_by_name": companion_damage_by_name,
        "enemy_damage_by_name": enemy_damage_by_name,
        "items_consumed": items_consumed_this_turn,
        "player_damage_taken": player_damage_by_name.get(acting_char_name, 0),
        "total_player_damage": total_player_damage,
        "xp_gain": xp_gain,
        "gold_gain": gold_gain,
        "dead_enemies": dead_enemies,
        "dead_enemy_dicts": dead_enemy_dicts,
        "dead_monsters": dead_enemies,
        "yielded_enemies": yielded_enemies,
        "yielded_monsters": yielded_enemies,
        "fled_enemies": fled_enemies,
        "fled_monsters": fled_enemies,
        "surrendered_enemies": surrendered_enemies,
        "surrendered_enemy_dicts": surrendered_enemy_dicts,
        "surrendered_monsters": surrendered_enemies,
        "enemy_damage": total_enemy_damage,
        "monster_damage": total_enemy_damage,
        "surviving_enemies": surviving_enemies,
        "surviving_monsters": surviving_enemies,
        "attackers_against_player": attackers_against_player,
        "acting_char_name": acting_char_name,
        "player_stats": acting_char_data,
        "current_npcs": current_npcs,
        "party_npcs": session.get("party_npcs", []) if isinstance(session, dict) else [],
        "player_resonance_pips": session.get("player_resonance_pips", {}) if isinstance(session, dict) else {},
    }


