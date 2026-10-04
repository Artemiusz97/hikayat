from __future__ import annotations
"""
Turn precomputation, LLM prompt schemas, and combat state reconciliation.
"""
import random
import re
import json
from typing import Optional, Dict, Any, List, Tuple

from scenario_data import is_mechanic_enabled
from mechanics.combat.spells import calculate_spell_damage
import db

from .formulas import (
    calculate_opposed_dc,
    get_elemental_multiplier,
    try_inflict_status,
    calculate_tactical_damage,
    calculate_turn_damage,
    tick_status_timers
)
from .sparring import (
    is_sparring_monster,
    resolve_sparring_defeat,
    make_sparring_monster,
    call_faction_reinforcements
)

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
                    "requirement": {"type": "integer"}
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

def _get_entity_stat(target: dict, stat_name: str) -> int:
    """Safely extracts a SPECIAL stat value from either a player character or an NPC companion."""
    if not isinstance(target, dict):
        return 5
    s_up = stat_name.upper()
    s_low = stat_name.lower()
    s_trail = f"{s_low}_"
    if s_trail in target:
        try:
            return int(target[s_trail])
        except (ValueError, TypeError):
            pass
    if s_low in target:
        try:
            return int(target[s_low])
        except (ValueError, TypeError):
            pass
    stats_dict = target.get("stats")
    if isinstance(stats_dict, dict):
        if s_up in stats_dict:
            try:
                return int(stats_dict[s_up])
            except (ValueError, TypeError):
                pass
        if s_low in stats_dict:
            try:
                return int(stats_dict[s_low])
            except (ValueError, TypeError):
                pass
    return 5

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
                    import json
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

    # 2. Gather all friendly NPC companions from session["current_npcs"]
    friendly_npcs = []
    current_npcs = [dict(npc) for npc in (session.get("current_npcs") or [])]
    for npc in current_npcs:
        if isinstance(npc, dict) and npc.get("hp") is not None:
            if not npc.get("stats") or not isinstance(npc.get("stats"), dict):
                npc["stats"] = build_companion_stat_sheet(npc.get("level", 1), npc.get("archetype", "Companion"))
            if "max_hp" not in npc:
                npc["max_hp"] = npc.get("hp", 50)
            friendly_npcs.append(npc)

    # Living Allies pool (all players with hp > 0 + all friendly companions with hp > 0)
    living_allies = [p for p in player_chars if p.get("hp", 1) > 0] + [c for c in friendly_npcs if c.get("hp", 1) > 0]
    if not living_allies and player_chars:
        living_allies = [player_chars[0]]

    combat_log = []
    player_damage_by_name = {p.get("name", "Hero"): 0 for p in player_chars}
    player_heal_by_name = {p.get("name", "Hero"): 0 for p in player_chars}
    player_mp_change_by_name = {p.get("name", "Hero"): 0 for p in player_chars}
    companion_damage_by_name = {c.get("name", "Companion"): 0 for c in friendly_npcs}
    total_enemy_damage = 0
    dead_enemies = []
    yielded_enemies = []
    fled_enemies = []
    fled_battle = False

    def _register_kill(m):
        if m.get("hp", 0) <= 0 and m["name"] not in dead_enemies and m["name"] not in yielded_enemies and m["name"] not in fled_enemies:
            if m.get("sparring"):
                yielded_enemies.append(m["name"])
                m["hp"] = 1
                combat_log.append(f"⚔️ **{m['name']}** yields!")
            else:
                dead_enemies.append(m["name"])
                combat_log.append(f"💀 **{m['name']}** was defeated!")
                
                # Volatile Death Explosion
                if "Volatile" in m.get("affixes", []):
                    burst_dmg = max(10, int(m.get("max_hp", 60) * 0.25))
                    target_player = living_allies[0] if living_allies else None
                    if target_player:
                        target_player["hp"] = max(0, target_player.get("hp", 100) - burst_dmg)
                        p_name = target_player.get("name", "Hero")
                        player_damage_by_name[p_name] = player_damage_by_name.get(p_name, 0) + burst_dmg
                        combat_log.append(f"💥 **DEATH THROES!** **{m['name']}** violently detonated! Dealt **{burst_dmg} explosive damage** to **{p_name}**!")

    def _apply_damage_to_enemy(m, dmg):
        """Applies damage to an enemy with Temp HP absorption & Boss Phase 2 death & threshold intercept."""
        temp_hp = m.get("temp_hp", 0)
        actual_dmg = dmg
        if temp_hp > 0:
            if temp_hp >= dmg:
                m["temp_hp"] = temp_hp - dmg
                return dmg
            else:
                actual_dmg = dmg - temp_hp
                m["temp_hp"] = 0

        max_hp = m.get("max_hp", 100)
        curr_hp = m.get("hp", max_hp)
        tier_rank = m.get("tier_rank", 1)
        is_boss = tier_rank >= 5
        phase_triggered = m.get("phase_2_triggered", False)

        new_hp = curr_hp - actual_dmg

        # Boss Phase 2 Intercept: triggers when crossing the 50% threshold or facing lethal damage
        if is_boss and not phase_triggered and (new_hp < max_hp * 0.5):
            m["phase_2_triggered"] = True
            heal_amt = int(max_hp * 0.2)
            transition_hp = max(int(max_hp * 0.5), new_hp) + heal_amt
            m["hp"] = min(max_hp, max(1, transition_hp))

            cur_eff = m.get("status_effects")
            if isinstance(cur_eff, str):
                try:
                    import json
                    m["status_effects"] = json.loads(cur_eff) if cur_eff.strip().startswith("[") else ([cur_eff] if cur_eff.strip() else [])
                except Exception:
                    m["status_effects"] = [cur_eff] if cur_eff.strip() else []
            elif not isinstance(cur_eff, list):
                m["status_effects"] = []

            m["status_effects"].append("Enraged [3 turns]")
            combat_log.append(f"⚠️ **BOSS PHASE TRANSITION!** **{m['name']}** survives the blow and enters Phase 2! Healed **{heal_amt} HP** and became **Enraged**!")
            return dmg

        m["hp"] = max(0, new_hp)
        if m["hp"] <= 0:
            _register_kill(m)
        return dmg

    # --- PHASE 1: ACTIVE PLAYER ACTION ---
    import db
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

    action = actions[0] if actions else {"choice_type": "MELEE_ATTACK", "label": "Attack"}
    c_type = action.get("choice_type", "MELEE_ATTACK")
    stat_name = action.get("stat", "STR")
    req_val = action.get("requirement", 10)

    # Dynamic target resolver: prioritize requested target entity, then label match, then first living
    req_target = str(action.get("target_entity") or action.get("target_npc") or action.get("target_enemy") or action.get("target") or "").strip().lower()
    target_enemy = None

    if req_target:
        target_enemy = next(
            (m for m in enemies if m.get("hp", 0) > 0 and (
                m["name"].lower() == req_target or req_target in m["name"].lower() or m["name"].lower() in req_target
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
            "immunities": target_enemy.get("immunities", [])
        })
        
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

        # 1. MAGIC & SPELLS RESOLUTION
        if (
            c_type in ("MAGIC_SPELL", "MAGIC_ATTACK")
            or action.get("action_category") == "magic"
            or "spell_id" in action
            or (stat_name == "INT" and c_type not in ("DEFENSIVE_GUARD", "DIPLOMACY_TAUNT", "WEAKNESS_EXPLOIT", "EVADE_TACTICAL_FLEE", "ENVIRONMENTAL_TRAP"))
        ):
            spell_id = action.get("spell_id")
            from mechanics.combat.spells import get_spell, calculate_spell_damage
            spell = get_spell(spell_id) if spell_id else None
            
            # Deduct MP
            mp_cost = spell.get("mp_cost", action.get("mp_cost", 0)) if spell else action.get("mp_cost", 0)
            if mp_cost > 0:
                acting_char_data["mp"] = max(0, acting_char_data.get("mp", 0) - mp_cost)
                player_mp_change_by_name[acting_char_name] = player_mp_change_by_name.get(acting_char_name, 0) - mp_cost

            if spell:
                discipline = spell.get("discipline", "attack")
                target_type = spell.get("target_type", "single")

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
                        "immunities": m.get("immunities", [])
                    })
                    elem_mult = get_elemental_multiplier(
                        {spell.get("damage_type", "magical"): 1.0}, m_armor, m_attrs
                    )
                    base_dmg = calculate_spell_damage(
                        player_attrs.get("matk", 20), spell, elem_mult,
                        defender_attrs=m_attrs,
                        armor_type_dt=m_armor.get("type_dt", {}),
                        armor_base_dt=m_armor.get("base_dt", 0)
                    )
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
                    # ── FULL AOE ─────────────────────────────────────────────
                    if target_type == "aoe":
                        is_glancing = tier in ("fail", "failure", "crit_fail")
                        first = True
                        for m in enemies:
                            if m.get("hp", 0) <= 0:
                                continue
                            raw_dmg, _, m_attrs = _apply_spell_to_enemy(m)
                            dmg = _resolve_hit_tier(raw_dmg, tier)
                            _apply_damage_to_enemy(m, dmg)
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
                            _apply_damage_to_enemy(m, dmg)
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
                        elem_mult = get_elemental_multiplier(
                            {spell.get("damage_type", "magical"): 1.0}, enemy_armor, enemy_attrs
                        )
                        m_dmg = calculate_spell_damage(
                            player_attrs.get("matk", 20), spell, elem_mult,
                            defender_attrs=enemy_attrs,
                            armor_type_dt=enemy_armor.get("type_dt", {}),
                            armor_base_dt=enemy_armor.get("base_dt", 0)
                        )
                        m_dmg = _resolve_hit_tier(m_dmg, tier)

                        if m_dmg > 0:
                            _apply_damage_to_enemy(target_enemy, m_dmg)
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
                    if "cleansing" in spell_affixes and acting_char_data.get("status_effects"):
                        cleansed = acting_char_data["status_effects"].pop(0)
                        combat_log.append(f"✨ **{acting_char_name}** cleansed **{cleansed}**!")



                elif discipline == "support":
                    if "heal_amount" in spell:
                        heal_val = spell["heal_amount"]
                        if tier == "crit_success":
                            heal_val = int(round(heal_val * 1.4))
                        acting_char_data["hp"] = min(acting_char_data.get("max_hp", 100), acting_char_data.get("hp", 0) + heal_val)
                        player_heal_by_name[acting_char_name] = player_heal_by_name.get(acting_char_name, 0) + heal_val
                        combat_log.append(f"💚 **{acting_char_name}** cast **{spell['name']}**: Restored **{heal_val} HP**.")
                    elif "mp_amount" in spell:
                        mp_gain = spell["mp_amount"]
                        acting_char_data["mp"] = min(acting_char_data.get("max_mp", 100), acting_char_data.get("mp", 0) + mp_gain)
                        player_mp_change_by_name[acting_char_name] = player_mp_change_by_name.get(acting_char_name, 0) + mp_gain
                        combat_log.append(f"💙 **{acting_char_name}** cast **{spell['name']}**: Restored **{mp_gain} MP**.")
                    else:
                        buff_tag = spell.get("status_ailment", "Fortified")
                        dur = spell.get("duration", 2)
                        acting_char_data.setdefault("status_effects", []).append(f"{buff_tag} [{dur} turns]")
                        buff_pct = int(spell.get("buff_pct", 0.15) * 100)
                        combat_log.append(f"✨ **{acting_char_name}** cast **{spell['name']}**: Gained **+{buff_pct}% {spell.get('stat_target', 'DEF')}** for {dur} turns.")

                elif discipline == "curse":
                    debuff_tag = spell.get("status_ailment", "Weakened")
                    dur = spell.get("duration", 2)
                    debuff_pct = int(spell.get("debuff_pct", 0.15) * 100)
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
                    db.remove_item_by_name(acting_user_id, consume_item_name)
                    action["item_consumed"] = True

            # 1. Throwables & Explosives targeting enemy
            if parsed_item.get("damage", 0) > 0 or any(w in label_lower for w in ["bomb", "grenade", "flask", "throw", "acid", "poison", "molotov", "damage"]):
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
                combat_log.append(f"👁️ **{acting_char_name}** scanned **{target_enemy['name']}**! {w_str} | {r_str}{i_str}.")
            else:
                combat_log.append(f"👁️ **{acting_char_name}** scanned **{target_enemy['name']}**, but could not expose a clear weakness.")

        # 6. TACTICAL FLEE
        elif c_type == "EVADE_TACTICAL_FLEE" or action.get("action_category") == "flee" or "flee" in action.get("label", "").lower() or "disengage" in action.get("label", "").lower():
            if tier in ("crit_success", "success"):
                fled_battle = True
                combat_log.append(f"🏃 **{acting_char_name}** successfully disengaged and fled from combat!")
            else:
                combat_log.append(f"🏃 **{acting_char_name}** attempted to disengage, but was cut off by **{target_enemy['name']}**!")

        # 7. ENVIRONMENTAL TRAP
        elif c_type == "ENVIRONMENTAL_TRAP" or action.get("action_category") == "trap":
            if tier in ("crit_success", "success"):
                trap_stat = max(player_attrs.get("matk", 20), player_attrs.get("atk", 20))
                trap_dmg = max(12, int(trap_stat * 1.25))
                if tier == "crit_success":
                    trap_dmg = int(round(trap_dmg * 1.5))
                applied_dmg = _apply_damage_to_enemy(target_enemy, trap_dmg)
                total_enemy_damage += applied_dmg
                target_enemy.setdefault("status_effects", []).append("Staggered [1 turn]")
                crit_tag = " *(Critical hit!)*" if tier == "crit_success" else ""
                combat_log.append(f"⚙️ **{acting_char_name}** sprung an environmental trap on **{target_enemy['name']}**: Dealt **{applied_dmg} damage** and Staggered them{crit_tag}!")
            else:
                combat_log.append(f"⚙️ **{acting_char_name}** attempted to spring an environmental trap on **{target_enemy['name']}**, but it failed to trigger!")

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

            # Instant execution threshold for wounded targets on crit
            if tier == "crit_success" and (target_enemy.get("hp", 100) / max(1, target_enemy.get("max_hp", 100))) <= 0.60:
                if random.random() < 0.30:
                    m_dmg = target_enemy.get("hp", 100)

            if tier in ("crit_success", "success") and m_dmg > 0:
                total_enemy_damage += m_dmg
                _apply_damage_to_enemy(target_enemy, m_dmg)

                tags_log = []
                if tactical_res.get("dual_wield") or action_stance == "dual_wield" or action.get("dual_wield"):
                    tags_log.append("*(Dual-Wield Flurry! +15% damage)*")
                if tactical_res.get("versatile_2h"):
                    tags_log.append("*(Two-Handed Grip! +15% damage)*")
                if tactical_res.get("ambush_strike"):
                    tags_log.append("*(Ambush Strike! +20% damage)*")
                if tactical_res.get("brawler_synergy"):
                    tags_log.append("*(Brawler Synergy! +25% unarmed strike)*")
                if tactical_res.get("ap_ratio", 0) > 0:
                    ap_pct = int(round(tactical_res["ap_ratio"] * 100))
                    tags_log.append(f"*(Armor Pierced {ap_pct}%)*")
                tag_str = (" " + " ".join(tags_log)) if tags_log else ""
                combat_log.append(f"⚔️ **{acting_char_name}** attacked **{target_enemy['name']}**: Dealt **{m_dmg} damage**{tag_str}.")
            else:
                combat_log.append(f"⚔️ **{acting_char_name}** attacked **{target_enemy['name']}**: Attack failed / deflected.")

            if tactical_res.get("stagger_inflicted"):
                acting_char_data.setdefault("status_effects", []).append("Staggered [1 turn]")
                combat_log.append(f"🛡️ **{target_enemy['name']}**'s heavy tank armor countered the blow! **{acting_char_name}** is Staggered!")

    # --- PHASE 2: FRIENDLY ALLIES (Automated Companions & Party Members) ---
    living_companions = [a for a in living_allies if a.get("name") != acting_char_name and a.get("hp", 0) > 0]
    for comp in living_companions:
        living_enemies = [m for m in enemies if m.get("hp", 0) > 0]
        if not living_enemies:
            break
        target_m = random.choice(living_enemies)
        comp_stats = comp.get("stats", {})
        comp_name = comp.get("name", "Companion")

        # Pick highest offensive stat for companion
        best_comp_stat = max(["STR", "AGI", "INT", "PER"], key=lambda s: comp_stats.get(s, 3))
        comp_stat_val = comp_stats.get(best_comp_stat, 3)
        m_def_val = target_m.get("stats", {}).get("END", 3)

        hit_chance = max(20, min(90, 55 + (comp_stat_val - m_def_val) * 7))
        roll = random.randint(1, 100)

        if roll <= hit_chance:
            comp_lvl = comp.get("level", 1)
            base_dmg = int(target_m.get("max_hp", 100) * random.uniform(0.12, 0.22)) + (comp_lvl * 2)
            comp_dmg = max(4, min(target_m.get("hp", 100), base_dmg))
            _apply_damage_to_enemy(target_m, comp_dmg)
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
            
            # Low-Morale Routing for Minions & Skirmishers
            routing_archetypes = {"Skirmisher", "Scavenger", "Scrap-Scavenger", "Rival Debater", "Gossip Monger", "Coward"}
            is_demoralized = any("Demoralized" in str(s) for s in enemy.get("status_effects", []))
            hp_pct = enemy.get("hp", 100) / max(1, enemy.get("max_hp", 100))
            
            if tier_rank <= 2 and (enemy_arch in routing_archetypes or is_demoralized):
                if hp_pct < 0.15 or is_demoralized:
                    # Roll morale check against END and CHA
                    stats = enemy.get("stats", {})
                    morale = stats.get("END", 1) + stats.get("CHA", 1)
                    if random.random() > (morale / 20.0):
                        fled_enemies.append(enemy["name"])
                        enemy["hp"] = 0  # Remove from combat
                        combat_log.append(f"🏃💨 **{enemy['name']}**'s morale broke! They dropped their weapon and fled the battlefield!")
                        continue
                        
            # Check for Crowd-Control Turn Suppression
            enemy_effects = [str(s).lower() for s in enemy.get("status_effects", [])]
            cc_keywords = ("stunned", "staggered", "frozen", "paralyzed", "asleep", "sleep")
            active_cc = next((s for s in enemy_effects if any(k in s for k in cc_keywords)), None)
            
            if active_cc:
                cc_label = active_cc.split("[")[0].strip().title()
                combat_log.append(f"💫 **{enemy['name']}** is **{cc_label}** and cannot act this turn!")
                continue

            active_targets = [a for a in living_allies if a.get("hp", 0) > 0]
            if not active_targets:
                break

            # Archetype-Aware Targeting (Using normalized _get_entity_stat)
            if enemy_arch in ("Stalker", "Assassin", "Chrome Cyberhound"):
                chosen_target = min(active_targets, key=lambda t: t.get("hp", 100))
            elif enemy_arch in ("Caster", "Psionic Alien", "Netrunner Spec-Op"):
                # Caster targets lowest LUK
                chosen_target = min(active_targets, key=lambda t: _get_entity_stat(t, "LUK"))
            elif enemy_arch in ("Brute", "Heavy Mech", "Heavy Borg"):
                # Brute targets highest STR (the tank/melee)
                chosen_target = max(active_targets, key=lambda t: _get_entity_stat(t, "STR"))
            else:
                chosen_target = random.choice(active_targets)

            target_name = chosen_target.get("name", "Hero")
            target_max_hp = chosen_target.get("max_hp", 100)

            enemy_weapon = dict(get_enemy_weapon_profile(enemy_arch))
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

            # --- Telegraphed Move (Intent) Execution ---
            cur_intent = str(enemy.get("intent") or "").strip()
            is_heavy_intent = any(k in cur_intent.lower() for k in ("heavy swing", "devastating crush", "overcharging"))
            is_magic_intent = any(k in cur_intent.lower() for k in ("channeling a massive spell", "drawing arcane energy", "preparing a burst"))
            is_ambush_intent = any(k in cur_intent.lower() for k in ("preparing to ambush", "fading into shadows", "targeting the weak"))
            is_defensive_intent = any(k in cur_intent.lower() for k in ("defensive posture", "shielding allies", "preparing a counter"))
            is_swarm_intent = any(k in cur_intent.lower() for k in ("preparing to swarm", "multiplying rapidly"))

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

            if is_magic_intent:
                mana_cost = 6 + (enemy.get("level", 1) * 2)
                current_mp = enemy.get("mp", enemy.get("max_mp", 20))
                if current_mp >= mana_cost:
                    enemy["mp"] = current_mp - mana_cost
                    enemy_atk_attrs["matk"] = int(enemy_atk_attrs.get("matk", 15) * 1.3)
                    enemy_weapon["damage_types"] = {"magical": 1.0}
                else:
                    # Out of mana -> spell fizzles into a weak physical struggle
                    is_magic_intent = False
                    combat_log.append(f"💨 **{enemy['name']}** attempted to channel arcane energy, but is out of mana!")

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
                    player_damage_by_name[target_name] = player_damage_by_name.get(target_name, 0) + e_dmg
                    total_player_damage += e_dmg
                    t_temp = chosen_target.get("temp_hp", 0)
                    if t_temp > 0:
                        if t_temp >= e_dmg:
                            chosen_target["temp_hp"] = t_temp - e_dmg
                            actual_dmg = 0
                        else:
                            actual_dmg = e_dmg - t_temp
                            chosen_target["temp_hp"] = 0
                    else:
                        actual_dmg = e_dmg
                    chosen_target["hp"] = max(0, chosen_target.get("hp", target_max_hp) - actual_dmg)
                    intent_note = ""
                    if is_heavy_intent:
                        intent_note = " *(Telegraphed Heavy Strike!)*"
                    elif is_magic_intent:
                        intent_note = " *(Telegraphed Arcane Burst!)*"
                    elif is_ambush_intent:
                        intent_note = " *(Telegraphed Ambush!)*"
                    combat_log.append(f"💥 **{enemy['name']}** attacked **{target_name}**: Dealt **{e_dmg} damage**{intent_note}.")

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
                    companion_damage_by_name[target_name] = companion_damage_by_name.get(target_name, 0) + e_dmg
                    t_temp = chosen_target.get("temp_hp", 0)
                    if t_temp > 0:
                        if t_temp >= e_dmg:
                            chosen_target["temp_hp"] = t_temp - e_dmg
                            actual_dmg = 0
                        else:
                            actual_dmg = e_dmg - t_temp
                            chosen_target["temp_hp"] = 0
                    else:
                        actual_dmg = e_dmg
                    chosen_target["hp"] = max(0, chosen_target.get("hp", target_max_hp) - actual_dmg)
                    # Sync companion HP back to current_npcs
                    for npc in current_npcs:
                        if npc.get("name") == target_name:
                            npc["hp"] = chosen_target["hp"]
                    if chosen_target.get("is_summon"):
                        combat_log.append(f"💥 **{enemy['name']}** struck summon **{target_name}**: Dealt **{e_dmg} damage**.")
                        if chosen_target["hp"] <= 0:
                            combat_log.append(f"💀 **{target_name}** was destroyed!")
                    else:
                        combat_log.append(f"💥 **{enemy['name']}** attacked **{target_name}**: Dealt **{e_dmg} damage**.")
                        if chosen_target["hp"] <= 0:
                            combat_log.append(f"⚠️ **{target_name}** was knocked down!")

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
        session["nearby_enemies"] = []
        session["nearby_enemies"] = []
        surviving_enemies = []
    else:
        for m in enemies:
            if m["name"] in yielded_enemies:
                pass # Removed from fight, no XP/Gold, but NOT dead and NOT surviving to attack next turn.
            elif m["name"] in fled_enemies:
                pass # Fled from fight, no XP/Gold.
            elif m.get("hp", 0) <= 0:
                if m["name"] not in dead_enemies:
                    dead_enemies.append(m["name"])
                
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

    session["nearby_enemies"] = surviving_enemies
    session["nearby_enemies"] = surviving_enemies
    session["current_npcs"] = current_npcs

    # Narrative Directive for LLM
    directive_lines = [
        "### DETERMINISTIC COMBAT ROUND OUTCOME (Follow in Story Narrative):",
        f"- Combat Events this turn:\n  " + "\n  ".join(combat_log),
        "- STRICT IMMERSION RULE: Describe these tactical actions and physical consequences in prose without mentioning numeric HP numbers, damage digits, or stat math."
    ]
    if yielded_enemies:
        from mechanics.combat import resolve_sparring_defeat
        directive_lines.append(resolve_sparring_defeat({"name": yielded_enemies[0]}))

    if fled_enemies:
        names = ", ".join(fled_enemies)
        directive_lines.append(f"- Enemies Fled: {names} broke rank and fled the battlefield.")

    if fled_battle:
        directive_lines.append("- Escape: The party successfully disengaged and fled from combat. Narrate their tactical retreat.")
    elif surviving_enemies:
        names = ", ".join(m["name"] for m in surviving_enemies)
        directive_lines.append(f"- Living Enemies: The {names} is/are STILL ALIVE and fighting. Do NOT narrate their defeat.")
    else:
        if not yielded_enemies and not fled_enemies:
            directive_lines.append("- Victory: All hostiles are DEFEATED. Narrate their final defeat and victory.")

    directive = "\n".join(directive_lines)

    return {
        "directive": directive,
        "combat_log": combat_log,
        "fled_battle": fled_battle,
        "player_damage_by_name": player_damage_by_name,
        "player_heal_by_name": player_heal_by_name,
        "player_mp_change_by_name": player_mp_change_by_name,
        "companion_damage_by_name": companion_damage_by_name,
        "player_damage_taken": player_damage_by_name.get(acting_char_name, 0),
        "total_player_damage": total_player_damage,
        "xp_gain": xp_gain,
        "gold_gain": gold_gain,
        "dead_enemies": dead_enemies,
        "dead_monsters": dead_enemies,
        "yielded_enemies": yielded_enemies,
        "yielded_monsters": yielded_enemies,
        "fled_enemies": fled_enemies,
        "fled_monsters": fled_enemies,
        "enemy_damage": total_enemy_damage,
        "monster_damage": total_enemy_damage,
        "surviving_enemies": surviving_enemies,
        "surviving_monsters": surviving_enemies,
        "attackers_against_player": attackers_against_player,
        "acting_char_name": acting_char_name,
        "player_stats": acting_char_data,
        "current_npcs": current_npcs
    }


def reconcile_combat_results(session: dict, llm_outcome: dict, precomputed: dict, party: list = None) -> dict:
    """Applies precomputed outcomes to the final LLM response and handles post-combat choices."""
    if not precomputed:
        return llm_outcome

    if "next_choices" in llm_outcome and "choices" not in llm_outcome:
        llm_outcome["choices"] = llm_outcome["next_choices"]
    elif "choices" in llm_outcome and "next_choices" not in llm_outcome:
        llm_outcome["next_choices"] = llm_outcome["choices"]

    # Session enemies and NPCs were already mutated by precompute_combat_turn
    enemies = session.get("nearby_enemies", [])
    llm_outcome["nearby_enemies"] = enemies
    llm_outcome["nearby_enemies"] = enemies
    llm_outcome["npcs_present"] = session.get("current_npcs", [])

    if isinstance(precomputed, list):
        actions = precomputed
        precomputed = {
            "dead_enemies": [],
            "dead_monsters": [],
            "yielded_enemies": [],
            "yielded_monsters": [],
            "combat_log": [],
            "player_damage_taken": 0,
            "xp_gain": 0,
            "gold_gain": 0
        }
        for act in actions:
            tier = act.get("tier")
            char_info = act.get("char", {})
            if tier == "crit_success":
                dmg = 45
                if enemies:
                    enemies[0]["hp"] = max(0, enemies[0].get("hp", 30) - dmg)
                    if enemies[0]["hp"] == 0:
                        dead_m = enemies.pop(0)
                        precomputed["dead_enemies"].append(dead_m.get("name", "Enemy"))
                        precomputed["dead_monsters"].append(dead_m.get("name", "Enemy"))
            elif tier == "crit_fail":
                char_name = char_info.get("name", "Hero")
                precomputed["acting_char_name"] = char_name
                precomputed["player_damage_taken"] = 25

    dead_enemies = precomputed.get("dead_enemies") or precomputed.get("dead_monsters", [])
    total_xp_gain = precomputed.get("xp_gain", 0)
    total_gold_gain = precomputed.get("gold_gain", 0)
    combat_log = precomputed.get("combat_log", [])
    player_damage_by_name = precomputed.get("player_damage_by_name", {})
    player_damage_taken = precomputed.get("player_damage_taken", 0)

    if combat_log:
        llm_outcome["_combat_log"] = combat_log

    yielded_enemies = precomputed.get("yielded_enemies") or precomputed.get("yielded_monsters", [])
    fled_enemies = precomputed.get("fled_enemies") or precomputed.get("fled_monsters", [])
    if yielded_enemies and not enemies:
        llm_outcome["_combat_resolved_notice"] = f"⚔️ Duel Concluded! {', '.join(yielded_enemies)} yielded!"
        llm_outcome["faction_promotion_result"] = "success"
    elif fled_enemies and not enemies:
        llm_outcome["_combat_resolved_notice"] = f"⚔️ Encounter Survived! {', '.join(fled_enemies)} fled the battle!"
    elif dead_enemies and not enemies:
        llm_outcome["_combat_resolved_notice"] = f"⚔️ Victory! {', '.join(dead_enemies)} defeated!\n**Rewards:** +{total_xp_gain} XP, +{total_gold_gain} Gold"

    if player_damage_taken > 0:
        acting_name = precomputed.get("acting_char_name", "Hero")
        attackers = precomputed.get("attackers_against_player", [])
        if len(attackers) == 1:
            llm_outcome["_enemy_attack_notice"] = f"💥 **{attackers[0]} Counter-Attack:** Dealt **{player_damage_taken} damage** to {acting_name}"
        elif len(attackers) > 1:
            llm_outcome["_enemy_attack_notice"] = f"💥 **Enemy Counter-Attacks ({', '.join(attackers)}):** Dealt **{player_damage_taken} total damage** to {acting_name}"
        else:
            target_name = enemies[0].get("name", "Enemy") if enemies else "Enemy"
            llm_outcome["_enemy_attack_notice"] = f"💥 **{target_name} Counter-Attack:** Dealt **{player_damage_taken} damage** to {acting_name}"

    # Process next choices
    llm_choices = llm_outcome.get("next_choices") or []

    if enemies and isinstance(llm_choices, list):
        target_m = enemies[0]
        m_stats = target_m.get("stats", {})
        p_stats = precomputed.get("player_stats", {})
        p_luk = p_stats.get("luk", 5)

        # Keep track of labels to prevent duplicates
        seen_labels = set()
        for c in llm_choices:
            if isinstance(c, dict):
                c_stat_name = c.get("stat", "STR")
                c_stat_key = f"{c_stat_name.lower()}_" if c_stat_name in ("STR", "PER", "END", "INT") else c_stat_name.lower()

                p_stat_val = p_stats.get(c_stat_key, 5)
                m_stat_val = m_stats.get(c_stat_name, 3)

                c["requirement"] = calculate_opposed_dc(p_stat_val, m_stat_val, p_luk)

                # Sanitize exact duplicates
                lbl = str(c.get("label", ""))
                if lbl in seen_labels:
                    c["label"] = f"{lbl} (Alternate Approach)"
                seen_labels.add(c["label"])

    # IF ALL ENEMIES DEFEATED -> Clear combat state and ensure dynamic post-combat choices!
    if not enemies:
        loc = session.get("current_location") or "area"
        llm_choices = llm_outcome.get("next_choices") or llm_outcome.get("choices") or []

        # 1. Dynamically identify or construct the dedicated Free Loot Choice at the top (Slot 1)
        dynamic_loot_label = None
        if isinstance(llm_choices, list):
            for c in llm_choices:
                if isinstance(c, dict):
                    lbl = str(c.get("label", "")).strip()
                    lbl_lower = lbl.lower()
                    if any(kw in lbl_lower for kw in ("loot", "search the fallen", "scavenge the fallen", "search the bodies", "search and loot", "inspect the fallen", "scavenge the remains", "gather spoils")):
                        dynamic_loot_label = lbl
                        break

        if not dynamic_loot_label:
            if dead_enemies and len(dead_enemies) == 1:
                e_name = dead_enemies[0].get("name") if isinstance(dead_enemies[0], dict) else str(dead_enemies[0])
                dynamic_loot_label = f"Search and loot the fallen {e_name}"
            else:
                dynamic_loot_label = "Search and loot the fallen enemies"

        loot_choice = None
        if dead_enemies:
            loot_choice = {
                "label": dynamic_loot_label[:100],
                "stat": "FREE",
                "requirement": 0,
                "mp_cost": 0
            }

        # 2. Filter LLM's natural scene/conversation/event choices (discarding leftover weapon attack actions against dead foes)
        contextual_choices = []
        if isinstance(llm_choices, list):
            for c in llm_choices:
                if isinstance(c, dict):
                    lbl = str(c.get("label", "")).strip()
                    lbl_lower = lbl.lower()
                    # Skip leftover combat attacks targeting dead hostiles
                    if any(kw in lbl_lower for kw in ("attack", "strike with", "slash with", "thrust into", "fire 9mm", "shoot with", "channel spell against", "roundhouse kick")):
                        continue
                    # Skip duplicate loot options generated by LLM
                    if any(kw in lbl_lower for kw in ("loot", "search the body", "search the bodies", "search the fallen", "inspect the corpse", "strip the gear")):
                        continue
                    contextual_choices.append({
                        "label": lbl[:120],
                        "stat": c.get("stat", "AGI"),
                        "requirement": max(0, min(20, int(c.get("requirement", 5)))),
                        "mp_cost": max(0, int(c.get("mp_cost", 0)))
                    })

        # 3. If LLM returned fewer than 3 valid contextual choices, supplement with procedural scene choices
        if len(contextual_choices) < 3:
            from mechanics.narrative.choice_generator import generate_procedural_scene_choices
            scen_key = session.get("scenario", "fantasy")
            supplements = generate_procedural_scene_choices(scenario=scen_key, location=loc, char=precomputed.get("player_stats"))
            for s in supplements:
                if len(contextual_choices) >= 3:
                    break
                s_lbl = str(s.get("label", "")).strip()
                if not any(s_lbl.lower() in cc["label"].lower() for cc in contextual_choices):
                    contextual_choices.append(s)

        # 4. Final choices: Slot 1 is ALWAYS the Loot Option (if applicable), followed by contextual choices
        final_post_combat_choices = ([loot_choice] if loot_choice else []) + contextual_choices[:3]

        llm_outcome["next_choices"] = final_post_combat_choices
        llm_outcome["choices"] = final_post_combat_choices

        # Despawn all active summons immediately upon combat victory so they never linger in exploration scenes
        session["current_npcs"] = [npc for npc in session.get("current_npcs", []) if not npc.get("is_summon")]
        llm_outcome["npcs_present"] = session["current_npcs"]

    # HARD CODE ENFORCEMENT: Strip any clues or note discovery from combat turns
    llm_outcome.pop("_newly_discovered_clue", None)
    if "quest_updates" in llm_outcome and isinstance(llm_outcome["quest_updates"], list):
        for qu in llm_outcome["quest_updates"]:
            if isinstance(qu, dict):
                qu.pop("current_clues", None)

    # Set deterministic character outcomes (PREVENT DOUBLE DAMAGE SUBTRACTION BUG!)
    if "character_outcomes" not in llm_outcome or not isinstance(llm_outcome["character_outcomes"], list):
        llm_outcome["character_outcomes"] = []

    acting_char_name = precomputed.get("acting_char_name", "Hero")
    if not player_damage_by_name:
        player_damage_by_name = {acting_char_name: player_damage_taken}

    player_heal_by_name = precomputed.get("player_heal_by_name", {})
    player_mp_change_by_name = precomputed.get("player_mp_change_by_name", {})
    all_participant_names = set(list(player_damage_by_name.keys()) + list(player_heal_by_name.keys()) + list(player_mp_change_by_name.keys()))

    for p_name in all_participant_names:
        p_dmg = player_damage_by_name.get(p_name, 0)
        p_heal = player_heal_by_name.get(p_name, 0)
        net_hp = p_heal - p_dmg
        p_mp_delta = player_mp_change_by_name.get(p_name, 0)

        found = False
        for co in llm_outcome["character_outcomes"]:
            if isinstance(co, dict) and co.get("name", "").lower() == p_name.lower():
                co["hp_change"] = net_hp
                if p_mp_delta != 0 or co.get("mp_change") is None:
                    co["mp_change"] = p_mp_delta
                co["gold_change"] = co.get("gold_change", 0) + total_gold_gain
                co["xp_change"] = co.get("xp_change", 0) + total_xp_gain
                found = True
                break
        if not found and (net_hp != 0 or p_mp_delta != 0 or total_xp_gain > 0 or total_gold_gain > 0):
            llm_outcome["character_outcomes"].append({
                "name": p_name,
                "hp_change": net_hp,
                "mp_change": p_mp_delta,
                "gold_change": total_gold_gain,
                "xp_change": total_xp_gain
            })

    session_id = session.get("id", 0) if session else 0
    import db
    party_npcs = db.get_session_party_npcs(session_id) if session_id else []

    # If combat victory and player is downed with companions standing, auto-revive at 1 HP
    if not enemies and (party_npcs or (party and len(party) > 1)):
        for co in llm_outcome.get("character_outcomes", []):
            if isinstance(co, dict):
                p_char = next((char for char, _ in (party or []) if char.get("name", "").lower() == co.get("name", "").lower()), None)
                if p_char:
                    projected_hp = p_char.get("hp", 10) + co.get("hp_change", 0)
                    if projected_hp <= 0:
                        co["hp_change"] = 1 - p_char.get("hp", 0)
                        co["status_effects"] = ["Exhausted / Recovering"]
                        llm_outcome["_combat_resolved_notice"] = (str(llm_outcome.get("_combat_resolved_notice", "")) + "\n🩹 Your companion tended to your wounds — revived with **1 HP**!").strip()

    # If hostiles remain and all party players + companions are downed -> Complete Party Defeat Recovery
    if enemies and party:
        all_downed = True
        for char, _ in party:
            c_name = char.get("name", "").lower()
            matching_co = next((co for co in llm_outcome.get("character_outcomes", []) if isinstance(co, dict) and co.get("name", "").lower() == c_name), None)
            c_proj_hp = char.get("hp", 10) + (matching_co.get("hp_change", 0) if matching_co else 0)
            if c_proj_hp > 0:
                all_downed = False
                break
        if all_downed and party_npcs:
            for npc in party_npcs:
                if npc.get("hp", 0) > 0:
                    all_downed = False
                    break

        if all_downed:
            session["nearby_enemies"] = []
            session["nearby_enemies"] = []
            llm_outcome["nearby_enemies"] = []
            llm_outcome["nearby_enemies"] = []

            for char, _ in party:
                uid = char.get("user_id")
                max_hp = char.get("max_hp", 30)
                revive_hp = max(1, max_hp // 2)
                cur_hp = char.get("hp", 0)
                matching_co = next((co for co in llm_outcome.get("character_outcomes", []) if isinstance(co, dict) and co.get("name", "").lower() == char.get("name", "").lower()), None)
                if matching_co:
                    matching_co["hp_change"] = revive_hp - cur_hp
                    matching_co["status_effects"] = ["Exhausted / Recovering"]
                else:
                    llm_outcome.setdefault("character_outcomes", []).append({
                        "name": char.get("name", "Hero"),
                        "hp_change": revive_hp - cur_hp,
                        "mp_change": 0,
                        "gold_change": 0,
                        "status_effects": ["Exhausted / Recovering"]
                    })
                if uid:
                    db.set_status_effects(uid, ["Exhausted / Recovering"])

            if party_npcs:
                updated_npcs = []
                for c in party_npcs:
                    c["hp"] = max(1, c.get("max_hp", 20) // 2)
                    c["status_effects"] = ["Exhausted / Recovering"]
                    updated_npcs.append(c)
                db.set_session_party_npcs(session_id, updated_npcs)
                session["current_npcs"] = updated_npcs

            llm_outcome["_party_defeated_notice"] = "💀 **Party Defeated!** You were overwhelmed and fell in battle, but were recovered to safety. You awaken stabilized, nursing your injuries."
            llm_outcome["next_choices"] = [
                {"label": "Rest and recuperate from your injuries", "stat": "END", "requirement": 4, "mp_cost": 0},
                {"label": "Assess your surroundings and check equipment", "stat": "PER", "requirement": 4, "mp_cost": 0},
                {"label": "Consult with companions about what happened", "stat": "CHA", "requirement": 4, "mp_cost": 0}
            ]
            llm_outcome["choices"] = llm_outcome["next_choices"]

    # Scale companion levels when party gains XP
    if not enemies and total_xp_gain > 0 and party_npcs and party and party[0]:
        p_lvl = party[0][0].get("level", 1)
        updated_npcs = []
        for c in party_npcs:
            c_lvl = max(c.get("level", 1), p_lvl)
            c["level"] = c_lvl
            c["max_hp"] = 15 + c_lvl * 3
            c["max_mp"] = 10 + c_lvl * 2
            c["hp"] = min(c.get("hp", c["max_hp"]), c["max_hp"])
            c["mp"] = min(c.get("mp", c["max_mp"]), c["max_mp"])
            updated_npcs.append(c)
        db.set_session_party_npcs(session_id, updated_npcs)

    return llm_outcome



