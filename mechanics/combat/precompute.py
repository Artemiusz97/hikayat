"""mechanics/combat/precompute.py

Unified Tactical Combat Round orchestrator (Phases 1-3): initializes
session combatants/ledgers, delegates Phase 1 (Player), Phase 2 (Allies),
and Phase 3 (Enemies), aggregates rewards/summons/telemetry, and builds
the zero-stat-leakage LLM narrative directive.
"""
from __future__ import annotations

import json
import logging
import random
import re
from typing import Any, Dict, List

import db
import scenario_data
from mechanics.combat.awakened_resonance import (
    ensure_autonomous_construct,
    init_enemy_stability_profile,
    tick_enemy_breach_recovery,
)
from mechanics.combat.damage import apply_damage_to_combatant
from mechanics.combat.enemies import build_companion_stat_sheet, build_enemy_stat_sheet
from mechanics.stealth import clear_all_combat_vanished
from scenario_data import is_mechanic_enabled

from .ally_turn import resolve_ally_combat_phase
from .enemy_turn import resolve_enemy_combat_phase
from .loadouts import TIER_RANK_TO_ROLE, ensure_combatant_loadout, reset_combatant_cooldowns
from .player_turn import resolve_player_combat_phase
from .reconcile import cleanup_anomalous_combat_session_state
from .sparring import resolve_sparring_defeat
from .status_effects import apply_status_effect
from .targeting import (
    apply_boss_cc_stagger_surge,
    arm_boss_telegraph,
    check_boss_telegraph_interrupt,
    compute_party_scaled_interrupt_threshold,
    populate_enemy_hud_telemetry,
    resolve_threat_target,
    update_threat_on_action,
)
from .types import get_combatant_stat

logger = logging.getLogger(__name__)
_get_entity_stat = get_combatant_stat

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
        "outcome_narrative": {"type": "string", "description": "Dynamic, visceral story about the combat outcomes and enemy retaliation."},
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
                            "MELEE_SLASHING_PIERCING", "MELEE_BLUNT", "RANGED_ATTACK", "MAGIC_ATTACK",
                            "ENVIRONMENTAL_TRAP", "WEAKNESS_EXPLOIT", "DIPLOMACY_TAUNT",
                            "DEFENSIVE_GUARD", "EVADE_TACTICAL_FLEE",
                        ],
                    },
                    "incursion_action": {"type": "string", "description": "Optional deterministic incursion action key when resolving an anomalous breach."},
                },
                "required": ["label", "stat", "requirement", "choice_type"],
            },
            "minItems": 4,
            "maxItems": 7,
            "description": "Provide 4-7 distinct combat choices. Note: Python will replace these with code-driven choices — just output valid choices.",
        },
        "choices": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {"label": {"type": "string"}, "stat": {"type": "string"}, "requirement": {"type": "integer"}, "incursion_action": {"type": "string"}},
            },
        },
        "nearby_enemies": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {"name": {"type": "string"}, "level": {"type": "integer"}, "hp": {"type": "integer"}, "max_hp": {"type": "integer"}},
            },
        },
        "character_outcomes": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "name": {"type": "string"}, "hp_change": {"type": "integer"}, "mp_change": {"type": "integer"},
                    "gold_change": {"type": "integer"}, "items_gained": {"type": "array", "items": {"type": "string"}},
                    "items_lost": {"type": "array", "items": {"type": "string"}}, "status_effects": {"type": "array", "items": {"type": "string"}},
                },
            },
        },
        "image_prompt": {"type": "string", "description": "Short (1-2 sentence) visual description of the combat scene."},
    },
    "required": ["outcome_narrative", "next_choices"],
}

_TIER_REWARD_SCALING: Dict[int, tuple[int, int]] = {
    1: (40, 15),
    2: (75, 25),
    3: (150, 60),
    4: (260, 120),
    5: (450, 250),
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


def _parse_status_list(char_obj: Dict[str, Any]) -> None:
    se = char_obj.get("status_effects")
    if isinstance(se, str):
        try:
            char_obj["status_effects"] = json.loads(se) if se.strip().startswith("[") else ([se] if se.strip() else [])
        except Exception:
            char_obj["status_effects"] = [se] if se.strip() else []
    elif not isinstance(se, list):
        char_obj["status_effects"] = []


def _sanitize_log_for_narrative(log_lines: List[str]) -> List[str]:
    qualitative_lines: List[str] = []
    def _dmg_sub(m: re.Match[str]) -> str:
        try:
            val = int(m.group(1))
        except Exception:
            val = 15
        if val >= 40:
            return "struck with devastating force"
        if val >= 20:
            return "landed a heavy blow"
        if val >= 10:
            return "landed a solid strike"
        return "landed a glancing hit"

    for line in log_lines:
        s = line
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


def _hydrate_friendly_allies(
    session: Any,
    player_chars: List[Dict[str, Any]],
    is_anom_combat: bool,
    sess_id_cbt: int,
    scen_cbt: str,
    lead_lvl_cbt: int,
) -> tuple[List[Dict[str, Any]], List[Dict[str, Any]], List[Dict[str, Any]], List[Dict[str, Any]], List[Dict[str, Any]]]:
    friendly_npcs: List[Dict[str, Any]] = []
    seen_ally_names: set[str] = set()
    active_party_npcs: List[Dict[str, Any]] = []

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
                p_comp, session_id=sess_id_cbt, scen_key=scen_cbt, player_level=lead_lvl_cbt, is_party_companion=True
            )
            for fk in ("anomalous_npc_tag", "is_special_agent", "agent_tier", "agent_class", "innate_abilities", "weapon_profile", "attribute", "combat_archetype", "ability_medium"):
                if p_comp.get(fk) is None:
                    p_comp[fk] = prof.get(fk)
            if not p_comp.get("stats") or not isinstance(p_comp.get("stats"), dict):
                p_comp["stats"] = prof["stats"]
            cur_max_hp = int(p_comp.get("max_hp") or 0)
            if cur_max_hp < 100 and prof["anomalous_npc_tag"] in ("special_agent", "folklore_villager"):
                p_comp["max_hp"] = prof["max_hp"]
                cur_hp = prof["hp"] if p_comp.get("hp") is None else int(p_comp["hp"])
                p_comp["hp"] = min(prof["max_hp"], max(cur_hp, prof["hp"]))
                p_comp["max_mp"] = prof["max_mp"]
                cur_mp = prof["mp"] if p_comp.get("mp") is None else int(p_comp["mp"])
                p_comp["mp"] = min(prof["max_mp"], max(cur_mp, prof["mp"]))
            else:
                if p_comp.get("max_hp") is None:
                    p_comp["max_hp"] = prof["max_hp"]
                if p_comp.get("hp") is None:
                    p_comp["hp"] = p_comp["max_hp"]
                if p_comp.get("max_mp") is None:
                    p_comp["max_mp"] = prof["max_mp"]
                if p_comp.get("mp") is None:
                    p_comp["mp"] = prof["mp"]
        else:
            if not p_comp.get("stats") or not isinstance(p_comp.get("stats"), dict):
                p_comp["stats"] = build_companion_stat_sheet(p_comp.get("level") or 1, p_comp.get("archetype") or "Companion")
            if p_comp.get("max_hp") is None:
                p_comp["max_hp"] = int(p_comp["hp"]) if p_comp.get("hp") is not None else 50
            if p_comp.get("hp") is None:
                p_comp["hp"] = p_comp["max_hp"]
        p_comp["_is_party_npc"] = True
        friendly_npcs.append(p_comp)
        seen_ally_names.add(p_name_c.lower())

    current_npcs = [dict(npc) for npc in (session.get("current_npcs") or []) if isinstance(npc, dict)] if isinstance(session, dict) else []
    for npc in current_npcs:
        n_nm = str(npc.get("name") or "").strip()
        if not n_nm or n_nm.lower() in seen_ally_names:
            continue
        if npc.get("is_summon"):
            if not npc.get("stats") or not isinstance(npc.get("stats"), dict):
                npc["stats"] = build_companion_stat_sheet(npc.get("level") or 1, npc.get("archetype") or "Companion")
            if npc.get("max_hp") is None:
                npc["max_hp"] = int(npc["hp"]) if npc.get("hp") is not None else 50
            if npc.get("hp") is None:
                npc["hp"] = npc["max_hp"]
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
                npc, session_id=sess_id_cbt, scen_key=scen_cbt, player_level=lead_lvl_cbt, is_party_companion=False
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
                for fk in ("agent_tier", "agent_class", "innate_abilities", "weapon_profile", "attribute", "combat_archetype", "ability_medium"):
                    npc[fk] = prof_n.get(fk)
                if prof_n["anomalous_npc_tag"] == TAG_FOLKLORE_VILLAGER:
                    npc["is_folklore_villager"] = True
                    npc["is_beast_companion"] = bool(prof_n.get("is_beast_companion"))
                    npc["folklore_village"] = prof_n.get("folklore_village")
                friendly_npcs.append(npc)
                seen_ally_names.add(n_nm.lower())
            elif prof_n["anomalous_npc_tag"] == TAG_CIVILIAN:
                if npc.get("hp") is not None or is_civilian_forced_to_fight_as_ally(npc, session):
                    npc["max_hp"] = 100
                    npc["hp"] = 100 if npc.get("hp") is None else min(100, int(npc["hp"]))
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
                npc["stats"] = build_companion_stat_sheet(npc.get("level") or 1, npc.get("archetype") or "Companion")
            if npc.get("max_hp") is None:
                npc["max_hp"] = int(npc["hp"])
            if npc.get("level") is None:
                npc["level"] = 1
            friendly_npcs.append(npc)
            seen_ally_names.add(n_nm.lower())

    dedup_names: set[str] = set()
    living_allies: List[Dict[str, Any]] = []
    for actor in (
        [p for p in player_chars if (p.get("hp") if p.get("hp") is not None else 1) > 0]
        + [c for c in friendly_npcs if (c.get("hp") if c.get("hp") is not None else 1) > 0]
    ):
        k_nm = str(actor.get("name") or "").strip().lower()
        if k_nm and k_nm in dedup_names:
            continue
        if k_nm:
            dedup_names.add(k_nm)
        living_allies.append(actor)
    if not living_allies and player_chars:
        living_allies = [player_chars[0]]

    active_constructs: List[Dict[str, Any]] = []
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
                    and (c.get("summoner_key") == owner_key or (owner_uid is not None and c.get("owner_id") == owner_uid))
                    for c in (current_npcs + living_allies)
                )
                spawned = ensure_autonomous_construct(
                    p_ch, living_allies, force_resummon=(not already_tracked and not session.get("_construct_initialized_this_combat")), current_npcs=current_npcs
                )
                if spawned and spawned not in active_constructs:
                    active_constructs.append(spawned)
        session["_construct_initialized_this_combat"] = True

    return friendly_npcs, active_party_npcs, current_npcs, living_allies, active_constructs


def precompute_combat_turn(session: dict, party: list, actions: list) -> dict:
    """Executes the Unified 3-Phase Tactical Combat Round before LLM narration."""
    has_hostiles = session.get("nearby_enemies", [])
    if not has_hostiles:
        return {}

    scen_cbt = str(session.get("scenario") or "fantasy") if isinstance(session, dict) else "fantasy"
    enemies = [dict(m) for m in has_hostiles]
    for m in enemies:
        if not m.get("stats") or not isinstance(m.get("stats"), dict):
            role_t = TIER_RANK_TO_ROLE.get(int(m.get("tier_rank", 2) or 2), "standard")
            m["stats"] = build_enemy_stat_sheet(m.get("level") or 1, m.get("archetype") or "Brute", role_tier=role_t)
        if m.get("max_hp") is None:
            m["max_hp"] = 100
        if m.get("hp") is None:
            m["hp"] = m["max_hp"]
        ensure_combatant_loadout(m, scenario_key=scen_cbt)

    known_npc_names = {
        str(x.get("name") or "").strip().lower()
        for x in ((session.get("party_npcs") or []) + (session.get("current_npcs") or []))
        if isinstance(x, dict) and x.get("name")
    }
    player_chars: List[Dict[str, Any]] = []
    for idx_p, p in enumerate(party):
        char_obj = p[0] if isinstance(p, (tuple, list)) else p
        if not isinstance(char_obj, dict):
            continue
        _parse_status_list(char_obj)
        nm_low = str(char_obj.get("name") or "").strip().lower()
        is_companion_entry = (
            idx_p > 0
            and char_obj.get("user_id") is None
            and (nm_low in known_npc_names or str(char_obj.get("id") or "").startswith("npc:") or char_obj.get("_is_party_npc"))
        )
        if not is_companion_entry:
            player_chars.append(char_obj)

    acting_char_data = player_chars[0] if player_chars else {}
    acting_char_name = acting_char_data.get("name", "Hero")
    player_luk_val = acting_char_data.get("luk", 5)

    is_anom_combat = bool(isinstance(session, dict) and scenario_data.is_anomalous_incursions_scenario(scen_cbt))
    sess_id_cbt = int(session.get("id") or 0) if isinstance(session, dict) else 0
    lead_lvl_cbt = int(acting_char_data.get("level", 1) or 1)
    if is_anom_combat:
        for _em in enemies:
            init_enemy_stability_profile(_em)

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

    turn_count_cbt = int(
        session.get("_target_turn")
        or session.get("combat_turn")
        or session.get("turn_count")
        or 0
    )

    friendly_npcs, active_party_npcs, current_npcs, living_allies, active_constructs = _hydrate_friendly_allies(
        session, player_chars, is_anom_combat, sess_id_cbt, scen_cbt, lead_lvl_cbt
    )

    slain_civilians: List[Dict[str, Any]] = []
    combat_log: List[str] = []
    if isinstance(session, dict):
        session["_pre_combat_enemies"] = [dict(e) for e in enemies if isinstance(e, dict)]

    player_damage_by_name = {p.get("name", "Hero"): 0 for p in player_chars}
    player_heal_by_name = {p.get("name", "Hero"): 0 for p in player_chars}
    player_mp_change_by_name = {p.get("name", "Hero"): 0 for p in player_chars}
    companion_damage_by_name = {c.get("name", "Companion"): 0 for c in friendly_npcs}
    companion_actions: List[Dict[str, Any]] = []
    enemy_damage_by_name = {m.get("name", "Enemy"): 0 for m in enemies}
    attackers_against_player: List[str] = []
    dead_enemies: List[str] = []
    dead_enemy_dicts: List[Dict[str, Any]] = []
    yielded_enemies: List[str] = []
    fled_enemies: List[str] = []
    surrendered_enemies: List[str] = []
    surrendered_enemy_dicts: List[Dict[str, Any]] = []
    items_consumed_this_turn: List[str] = []

    is_non_lethal_active = bool(
        (isinstance(session, dict) and session.get("non_lethal_mode"))
        or any(isinstance(a, dict) and a.get("is_non_lethal") for a in (actions or []))
    )

    def _register_kill(m: Dict[str, Any]) -> None:
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
                if "Volatile" in m.get("affixes", []):
                    burst_dmg = max(10, int(m.get("max_hp", 60) * 0.25))
                    target_player = living_allies[0] if living_allies else None
                    if target_player:
                        actual_burst = apply_damage_to_combatant(
                            target=target_player, dmg=burst_dmg, attacker=m, combat_log=combat_log, is_anom_combat=is_anom_combat
                        )
                        p_name = target_player.get("name", "Hero")
                        player_damage_by_name[p_name] = player_damage_by_name.get(p_name, 0) + actual_burst
                        combat_log.append(f"💥 **DEATH THROES!** **{m['name']}** violently detonated! Dealt **{burst_dmg} explosive damage** to **{p_name}**!")

    def _apply_damage_to_enemy(m: Dict[str, Any], dmg: int, attacker: Any = None) -> int:
        if attacker is None:
            attacker = {"name": acting_char_name, "team": "ally", "entity_type": "player"}
        p_pierce = bool(m.get("_pierce_temp_hp_this_hit"))
        actual_dmg = apply_damage_to_combatant(
            target=m, dmg=dmg, attacker=attacker, combat_log=combat_log, is_anom_combat=is_anom_combat,
            non_lethal_mode=is_non_lethal_active, pierce_temp_hp=p_pierce,
        )
        m_name = m.get("name", "Enemy")
        enemy_damage_by_name[m_name] = enemy_damage_by_name.get(m_name, 0) + actual_dmg

        if actual_dmg > 0:
            atk_id = str(attacker.get("name") or acting_char_name)
            target_eid = str(m.get("id") or m.get("name"))
            all_eids = [str(e.get("id") or e.get("name")) for e in enemies if e.get("hp", 0) > 0]
            update_threat_on_action(
                threat_matrix, atk_id, "attack", [target_eid], all_eids, damage_dealt=actual_dmg, sticky_taunts=sticky_taunts
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
            if m["hp"] <= max(1, int(max_hp * sub_pct)) and not m.get("_containment_window_logged"):
                m["_containment_window_logged"] = True
                combat_log.append(
                    f"⚡ **{m['name']}** is weakened into the containment window — "
                    f"use **[🛡️ Subdue & Contain]** or **[🗣️ Persuade / Calm]** now before lethal damage kills it!"
                )
        return actual_dmg

    ctx: Dict[str, Any] = {
        "session": session, "party": party, "actions": actions, "enemies": enemies,
        "player_chars": player_chars, "acting_char_data": acting_char_data, "acting_char_name": acting_char_name,
        "player_luk_val": player_luk_val, "is_anom_combat": is_anom_combat, "sess_id_cbt": sess_id_cbt, "scen_cbt": scen_cbt,
        "friendly_npcs": friendly_npcs, "active_party_npcs": active_party_npcs, "current_npcs": current_npcs,
        "living_allies": living_allies, "active_constructs": active_constructs, "slain_civilians": slain_civilians,
        "combat_log": combat_log, "player_damage_by_name": player_damage_by_name,
        "player_heal_by_name": player_heal_by_name, "player_mp_change_by_name": player_mp_change_by_name,
        "companion_damage_by_name": companion_damage_by_name, "companion_actions": companion_actions,
        "enemy_damage_by_name": enemy_damage_by_name, "total_enemy_damage": 0, "total_player_damage": 0,
        "attackers_against_player": attackers_against_player, "dead_enemies": dead_enemies, "dead_enemy_dicts": dead_enemy_dicts,
        "yielded_enemies": yielded_enemies, "fled_enemies": fled_enemies,
        "surrendered_enemies": surrendered_enemies, "surrendered_enemy_dicts": surrendered_enemy_dicts,
        "fled_battle": False, "items_consumed_this_turn": items_consumed_this_turn,
        "is_non_lethal_active": is_non_lethal_active, "threat_ledger": threat_ledger, "threat_matrix": threat_matrix,
        "sticky_taunts": sticky_taunts, "boss_telegraph_state": boss_telegraph_state,
        "turn_count_cbt": turn_count_cbt, "apply_damage_to_enemy": _apply_damage_to_enemy, "register_kill": _register_kill,
        "player_status_sync_by_name": {},
    }

    resolve_player_combat_phase(ctx)
    resolve_ally_combat_phase(ctx)
    resolve_enemy_combat_phase(ctx)

    current_npcs = ctx["current_npcs"]
    fled_battle = bool(ctx.get("fled_battle"))
    total_enemy_damage = int(ctx.get("total_enemy_damage", 0) or 0)
    total_player_damage = int(ctx.get("total_player_damage", 0) or 0)
    anom_passives = ctx.get("anom_passives") or {}

    surviving_npcs: List[Dict[str, Any]] = []
    for npc in current_npcs:
        if npc.get("is_summon"):
            npc["summon_duration"] = int(npc.get("summon_duration") if npc.get("summon_duration") is not None else 1) - 1
            npc_hp = int(npc.get("hp") or 0)
            if npc["summon_duration"] <= 0 or npc_hp <= 0:
                if npc["summon_duration"] <= 0 and npc_hp > 0:
                    combat_log.append(f"✨ **{npc['name']}**'s duration expired and dissipated back to its planar realm.")
                continue
        surviving_npcs.append(npc)
    current_npcs = surviving_npcs

    xp_gain = 0
    gold_gain = 0
    surviving_enemies: List[Dict[str, Any]] = []

    if fled_battle:
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
                _parse_status_list(p_comp)
                apply_status_effect(p_comp, "Critical Trauma [-25% All Stats] [5 turns]", source="emergency_extraction")
                combat_log.append(f"🩹 **{p_comp.get('name', 'Companion')}** was rescued at 1 HP but suffers from **Critical Trauma**!")
        session["nearby_enemies"] = []
    else:
        for m in enemies:
            if m["name"] in yielded_enemies:
                pass
            elif m["name"] in fled_enemies:
                if (m.get("surrendered") or m["name"] in surrendered_enemies) and not m.get("contained_via_parley"):
                    t_rank = m.get("tier_rank")
                    if not t_rank:
                        t_name = str(m.get("tier", "standard")).lower()
                        t_rank = 5 if t_name == "boss" else (4 if t_name == "miniboss" else (3 if t_name == "elite" else (1 if t_name == "minion" else 2)))
                    base_xp, base_gold = _TIER_REWARD_SCALING.get(t_rank, (75, 25))
                    mult = m.get("xp_multiplier", 1.0)
                    xp_gain += int(base_xp * mult)
                    gold_gain += int(base_gold * mult)
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
                    base_xp, base_gold = _TIER_REWARD_SCALING.get(t_rank, (75, 25))
                    mult = m.get("xp_multiplier", 1.0)
                    xp_gain += int(base_xp * mult)
                    gold_gain += int(base_gold * mult)
            else:
                surviving_enemies.append(m)

    for m in surviving_enemies:
        if m.pop("_primed_intent_this_turn", False):
            continue
        m_anom_tag = str(m.get("anomalous_npc_tag") or "").strip().lower()
        if m_anom_tag == "civilian":
            w_nm = str((m.get("weapon_profile") or {}).get("name") or "weapon")
            m["intent"] = f"Brandishing {w_nm} defensively"
            continue
        if m_anom_tag == "special_agent":
            m["intent"] = random.choice(["Calibrating anomalous resonance", "Preparing a tactical ability", "Lining up a mana-infused strike"])
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

    combat_over = bool(not surviving_enemies or fled_battle)
    session["nearby_enemies"] = surviving_enemies
    session["current_npcs"] = current_npcs
    if is_anom_combat and isinstance(session, dict):
        if combat_over:
            cleanup_anomalous_combat_session_state(session)
        else:
            for c_alive in living_allies:
                if isinstance(c_alive, dict) and c_alive.get("is_autonomous_construct") and c_alive not in current_npcs:
                    current_npcs.append(c_alive)
            session["current_npcs"] = current_npcs
            session["_active_constructs"] = [c for c in living_allies if c.get("is_autonomous_construct")]

    if active_party_npcs and isinstance(session, dict):
        persisted_party_npcs = []
        for p_comp in active_party_npcs:
            p_clean = {k: v for k, v in p_comp.items() if k != "_is_party_npc"}
            if combat_over:
                p_clean.pop("_used_ultimate_this_combat", None)
                reset_combatant_cooldowns(p_clean)
            persisted_party_npcs.append(p_clean)
        session["party_npcs"] = persisted_party_npcs
        if combat_over:
            for p_raw in party:
                p_obj = p_raw[0] if isinstance(p_raw, (tuple, list)) else p_raw
                if isinstance(p_obj, dict) and p_obj not in player_chars:
                    reset_combatant_cooldowns(p_obj)
        if sess_id_cbt:
            try:
                db.set_session_party_npcs(sess_id_cbt, persisted_party_npcs)
            except Exception:
                pass

    if combat_over and isinstance(session, dict):
        clear_all_combat_vanished(session)

    qualitative_events = _sanitize_log_for_narrative(combat_log)
    directive_lines = [
        "### DETERMINISTIC COMBAT ROUND OUTCOME (Follow in Story Narrative):",
        "- Combat Events this turn:\n  " + "\n  ".join(qualitative_events),
        "- STRICT IMMERSION RULE: Describe these tactical actions and physical consequences in prose without mentioning numeric HP numbers, damage digits, or stat math.",
    ]
    if yielded_enemies:
        directive_lines.append(resolve_sparring_defeat({"name": yielded_enemies[0]}))
    if surrendered_enemies:
        directive_lines.append(f"- Enemies Surrendered: {', '.join(surrendered_enemies)} dropped weapons and yielded to the party. Narrate their surrender.")
    if fled_enemies:
        actual_fled = [n for n in fled_enemies if n not in surrendered_enemies]
        if actual_fled:
            directive_lines.append(f"- Enemies Fled: {', '.join(actual_fled)} broke rank and fled the battlefield.")
    if fled_battle:
        directive_lines.append("- Escape: The party successfully disengaged and fled from combat. Narrate their tactical retreat.")
    elif surviving_enemies:
        names = ", ".join(m["name"] for m in surviving_enemies)
        directive_lines.append(f"- Living Enemies: The {names} is/are STILL ALIVE and fighting. Do NOT narrate their defeat.")
        for _se in surviving_enemies:
            _tel = _se.get("telegraphed_skill")
            if isinstance(_tel, dict) and _tel:
                _s_lbl = str(_tel.get("skill_name") or "devastating strike")
                directive_lines.append(
                    f"- Boss Telegraph Windup: {_se['name']} is visibly gathering overwhelming power for {_s_lbl}! "
                    f"Narrate the urgent danger and interrupt opportunity qualitatively (zero raw numbers)."
                )
    elif not yielded_enemies and not fled_enemies:
        directive_lines.append("- Victory: All hostiles are DEFEATED. Narrate their final defeat and victory.")

    if slain_civilians:
        slain_desc = ", ".join(f"{sc['name']} (slain by {sc['killer']})" for sc in slain_civilians)
        directive_lines.append(
            f"- Civilian Permadeath: {slain_desc} lacked any mana barrier and died permanently in the anomalous assault. "
            f"Narrate their fatal death with grim urban-horror gravity (zero raw HP digits)."
        )

    return {
        "directive": "\n".join(directive_lines),
        "slain_civilians": slain_civilians,
        "combat_log": combat_log,
        "fled_battle": fled_battle,
        "player_damage_by_name": player_damage_by_name,
        "player_heal_by_name": player_heal_by_name,
        "player_mp_change_by_name": player_mp_change_by_name,
        "player_status_sync_by_name": ctx.get("player_status_sync_by_name", {}),
        "companion_damage_by_name": companion_damage_by_name,
        "companion_actions": companion_actions,
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
