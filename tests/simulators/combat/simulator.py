from __future__ import annotations
"""
Tactical Combat Simulator and Fuzzing Test Harness.

Executes generative, headless combat encounters across all game scenarios
to audit combat math, status effects, equipment, spells, consumables,
and AI edge cases without requiring LLM or Discord dependencies.
"""
import random
import sys
import time
import traceback
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

import db
import character_data as cd
from skill_check import resolve_check, CheckResult
from mechanics.combat.core import precompute_combat_turn, reconcile_combat_results
from mechanics.combat.formulas import tick_status_timers, TYPE_AFFINITIES, DAMAGE_TYPE_ALIASES
from mechanics.combat.enemies import (
    generate_scenario_enemy,
    generate_balanced_encounter,
    build_companion_stat_sheet,
    build_enemy_stat_sheet,
    get_enemy_armor_profile,
    get_enemy_weapon_profile,
    SCENARIO_ENEMY_TEMPLATES
)
from mechanics.combat.equipment import (
    generate_random_equipment,
    parse_equipment_metadata,
    build_equipment_effect_str
)
from mechanics.combat.spells import (
    get_starter_spells,
    get_spell,
    get_all_spells,
    generate_procedural_spell
)
from mechanics.combat.items.consumables.generators import (
    generate_procedural_potion,
    generate_procedural_food,
    generate_procedural_drink
)
from mechanics.combat.items.consumables import parse_item_effect
from mechanics.social.attributes import calculate_combat_attributes


def safe_print(msg: str = "") -> None:
    """Print helper that safely handles console encoding on Windows without crashing on emojis."""
    try:
        print(msg, flush=True)
    except UnicodeEncodeError:
        try:
            sys.stdout.buffer.write((str(msg) + "\n").encode("utf-8", errors="replace"))
            sys.stdout.buffer.flush()
        except Exception:
            print(str(msg).encode("ascii", errors="replace").decode("ascii"), flush=True)


SUPPORTED_SCENARIOS = [
    "fantasy", "scifi", "cyberpunk", "steampunk",
    "dark_fantasy", "isekai_fantasy", "high_school_drama", "postapoc",
    "slice_of_life", "highschool", "nuclear_post_apocalypse", "sci_fi",
    "anomalous_incursions", "urban_anomalies", "urban_fantasy",
]

COMBAT_ARCHETYPES = [
    "balanced", "berserker", "defender", "infiltrator", "chaos_fuzzer"
]


@dataclass
class SimulationResult:
    """Outcome and telemetry for a single simulated combat encounter."""
    battle_id: int
    scenario: str
    archetype: str
    level: int
    seed: int
    outcome: str  # "victory", "defeat", "fled", "stalemate", "crash"
    turns_taken: int
    player_start_hp: int
    player_end_hp: int
    party_size: int
    enemy_count: int
    enemies: List[Dict[str, Any]]
    combat_log: List[str]
    violations: List[str] = field(default_factory=list)
    exception: Optional[str] = None
    gold_gained: int = 0
    xp_gained: int = 0
    duration_ms: float = 0.0


@dataclass
class SimulationReport:
    """Aggregated statistics and issue ledger across multiple battles."""
    total_battles: int = 0
    victories: int = 0
    defeats: int = 0
    fled: int = 0
    stalemates: int = 0
    crashes: int = 0
    total_turns: int = 0
    total_duration_ms: float = 0.0
    total_xp_gained: int = 0
    total_gold_gained: int = 0
    violations_by_type: Dict[str, int] = field(default_factory=dict)
    failing_seeds: List[Dict[str, Any]] = field(default_factory=list)
    scenario_stats: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    archetype_stats: Dict[str, Dict[str, Any]] = field(default_factory=dict)

    @property
    def win_rate(self) -> float:
        resolved = self.victories + self.defeats + self.fled + self.stalemates
        return (self.victories / resolved * 100.0) if resolved > 0 else 0.0

    @property
    def avg_turns(self) -> float:
        return (self.total_turns / self.total_battles) if self.total_battles > 0 else 0.0

    def add_result(self, res: SimulationResult) -> None:
        self.total_battles += 1
        self.total_turns += res.turns_taken
        self.total_duration_ms += res.duration_ms
        self.total_xp_gained += res.xp_gained
        self.total_gold_gained += res.gold_gained

        if res.outcome == "victory":
            self.victories += 1
        elif res.outcome == "defeat":
            self.defeats += 1
        elif res.outcome == "fled":
            self.fled += 1
        elif res.outcome == "stalemate":
            self.stalemates += 1
        elif res.outcome == "crash":
            self.crashes += 1

        # Track archetype specific stats
        arch = res.archetype or "balanced"
        if arch not in self.archetype_stats:
            self.archetype_stats[arch] = {"total": 0, "wins": 0, "losses": 0, "turns": 0, "crashes": 0}
        a_stat = self.archetype_stats[arch]
        a_stat["total"] += 1
        a_stat["turns"] += res.turns_taken
        if res.outcome == "victory":
            a_stat["wins"] += 1
        elif res.outcome == "defeat":
            a_stat["losses"] += 1
        elif res.outcome == "crash":
            a_stat["crashes"] += 1

        # Track scenario specific stats
        scen = res.scenario
        if scen not in self.scenario_stats:
            self.scenario_stats[scen] = {"total": 0, "wins": 0, "losses": 0, "turns": 0, "crashes": 0, "xp": 0, "gold": 0}
        s_stat = self.scenario_stats[scen]
        s_stat["total"] += 1
        s_stat["turns"] += res.turns_taken
        s_stat["xp"] = s_stat.get("xp", 0) + res.xp_gained
        s_stat["gold"] = s_stat.get("gold", 0) + res.gold_gained
        if res.outcome == "victory":
            s_stat["wins"] += 1
        elif res.outcome == "defeat":
            s_stat["losses"] += 1
        elif res.outcome == "crash":
            s_stat["crashes"] += 1

        # Track violations
        if res.violations or res.exception:
            self.failing_seeds.append({
                "battle_id": res.battle_id,
                "seed": res.seed,
                "scenario": res.scenario,
                "level": res.level,
                "outcome": res.outcome,
                "violations": list(res.violations),
                "exception": res.exception
            })
            for v in res.violations:
                v_key = v.split(":")[0] if ":" in v else v[:40]
                self.violations_by_type[v_key] = self.violations_by_type.get(v_key, 0) + 1
            if res.exception:
                self.violations_by_type["CRASH_EXCEPTION"] = self.violations_by_type.get("CRASH_EXCEPTION", 0) + 1

    def to_dict(self) -> Dict[str, Any]:
        return {
            "total_battles": self.total_battles,
            "victories": self.victories,
            "defeats": self.defeats,
            "fled": self.fled,
            "stalemates": self.stalemates,
            "crashes": self.crashes,
            "win_rate": round(self.win_rate, 2),
            "avg_turns": round(self.avg_turns, 2),
            "total_duration_ms": round(self.total_duration_ms, 2),
            "violations_by_type": self.violations_by_type,
            "failing_seeds_count": len(self.failing_seeds),
            "scenario_stats": self.scenario_stats,
            "failing_seeds": self.failing_seeds[:50]  # capped sample
        }

    def format_summary(self) -> str:
        lines = [
            "============================================================",
            "             COMBAT SIMULATION & AUDIT REPORT               ",
            "============================================================",
            f" Total Battles Simulated : {self.total_battles}",
            f" Victories               : {self.victories} ({self.win_rate:.1f}%)",
            f" Defeats                 : {self.defeats}",
            f" Fled Battles            : {self.fled}",
            f" Stalemates (>40 turns)  : {self.stalemates}",
            f" Crashes / Uncaught Errs : {self.crashes}",
            f" Average Turns / Battle  : {self.avg_turns:.2f}",
            f" Total Simulation Time   : {self.total_duration_ms:.1f} ms",
            "------------------------------------------------------------",
            " SCENARIO BREAKDOWN:"
        ]
        for scen, s in sorted(self.scenario_stats.items()):
            w_pct = (s["wins"] / s["total"] * 100.0) if s["total"] > 0 else 0.0
            avg_t = (s["turns"] / s["total"]) if s["total"] > 0 else 0.0
            lines.append(f"   * {scen:<15}: {s['total']:>3} battles | Win: {w_pct:>5.1f}% | Avg Turns: {avg_t:>4.1f} | Crashes: {s['crashes']}")

        lines.append("------------------------------------------------------------")
        lines.append(" INVARIANT VIOLATIONS & ANOMALIES:")
        if not self.violations_by_type:
            lines.append("   🎉 ZERO INVARIANT VIOLATIONS DETECTED!")
        else:
            for v_name, count in sorted(self.violations_by_type.items(), key=lambda x: -x[1]):
                lines.append(f"   ⚠️  [{count}x] {v_name}")

        if self.failing_seeds:
            lines.append("------------------------------------------------------------")
            lines.append(f" REPRODUCTION SEEDS ({len(self.failing_seeds)} occurrences):")
            for f_info in self.failing_seeds[:10]:
                lines.append(f"   - Seed {f_info['seed']} (Battle #{f_info['battle_id']}, {f_info['scenario']} Lvl {f_info['level']}): {f_info['outcome']}")
                for v in f_info['violations'][:2]:
                    lines.append(f"       * {v}")
                if f_info['exception']:
                    first_err_line = f_info['exception'].strip().splitlines()[-1]
                    lines.append(f"       * Error: {first_err_line}")
            if len(self.failing_seeds) > 10:
                lines.append(f"   ... and {len(self.failing_seeds) - 10} more failing battles.")

        lines.append("============================================================")
        return "\n".join(lines)


class CombatFuzzer:
    """Generates procedural, valid entities conforming to Hikayat system constraints."""

    @staticmethod
    def generate_player(scenario: str, level: int, user_id: int) -> Tuple[Dict[str, Any], List[Dict[str, Any]]]:
        """Creates a fully equipped, level-scaled character in db for testing."""
        templates = cd.get_class_templates(scenario)
        if not templates:
            templates = cd.get_class_templates("fantasy")
        class_name = random.choice(list(templates.keys()))
        class_data = templates[class_name]

        # Allocate SPECIAL stats within realistic budget
        # Base budget: 35 points distributed across 7 SPECIAL stats (min 1, max 10)
        base_budget = 35 + max(0, level - 1)
        stats = {"STR": 1, "PER": 1, "END": 1, "CHA": 1, "INT": 1, "AGI": 1, "LUK": 1}
        remaining = base_budget - 7

        # Bias distribution toward primary class attributes if available
        primary_stat = class_data.get("primary_stat", "STR").upper()
        stat_keys = list(stats.keys())
        weights = [4 if s == primary_stat else 1 for s in stat_keys]

        for _ in range(remaining):
            chosen = random.choices(stat_keys, weights=weights, k=1)[0]
            if stats[chosen] < 10:
                stats[chosen] += 1
            else:
                # If capped, give to any available stat
                under_cap = [s for s in stat_keys if stats[s] < 10]
                if under_cap:
                    stats[random.choice(under_cap)] += 1

        endurance = stats["END"]
        max_hp = cd.derive_hp(endurance) + (level - 1) * 6
        max_mp = cd.derive_mp(endurance) + (level - 1) * 4

        # Clean existing test user records
        db.init_db()
        chars = db.get_user_characters(user_id)
        for c in chars:
            db.delete_character(user_id, c["id"])
        with db.get_conn() as conn:
            conn.execute("DELETE FROM inventory WHERE user_id = ?", (user_id,))
            conn.execute("DELETE FROM user_settings WHERE user_id = ?", (user_id,))

        char_row = db.create_character(
            user_id=user_id,
            name=f"SimHero_{user_id % 1000}",
            char_class=class_name,
            class_description=class_data.get("description", "Test Hero"),
            stats=stats
        )

        # Update level, HP, MP
        with db.get_conn() as conn:
            conn.execute(
                "UPDATE characters SET level=?, hp=?, max_hp=?, mp=?, max_mp=?, scenario=? WHERE user_id=?",
                (level, max_hp, max_hp, max_mp, max_mp, scenario, user_id)
            )

        char_dict = dict(db.get_character(user_id))
        char_dict["user_id"] = user_id
        char_dict["status_effects"] = []

        # Generate Equipment Loadout
        gear_tier = max(1, min(5, (level + 2) // 3))
        inventory_items = []

        # 1. Main Weapon
        weapon = cd.generate_equipment(scenario=scenario, slot="Weapon", tier=gear_tier)
        w_id = db.add_item(user_id, weapon["name"], "Weapon", weapon["effect"], force=True)
        db.equip_item(user_id, w_id, "Weapon")
        weapon["id"] = w_id
        weapon["equipped"] = 1
        weapon["slot"] = "Weapon"
        inventory_items.append(weapon)

        # 2. Armor / Clothing
        armor = cd.generate_equipment(scenario=scenario, slot="Armor", tier=gear_tier)
        armor_slot = armor.get("slot") or ("Top" if armor.get("item_type") == "Clothing" else "Armor")
        if armor.get("item_type") == "Clothing" and armor_slot not in ("Top", "Bottom"):
            armor_slot = "Top"
        elif armor.get("item_type") != "Clothing" and armor_slot != "Armor":
            armor_slot = "Armor"
        a_id = db.add_item(user_id, armor["name"], armor.get("item_type", "Armor"), armor["effect"], force=True)
        db.equip_item(user_id, a_id, armor_slot)
        armor["id"] = a_id
        armor["equipped"] = 1
        armor["slot"] = armor_slot
        inventory_items.append(armor)

        # 3. Offhand or Second Weapon (50% chance for Shield, 25% for Dual-Wield, 25% 2-Handed empty)
        offhand_roll = random.random()
        w_meta = parse_equipment_metadata(weapon)
        w_handed = w_meta.get("handedness", "1H")

        if w_handed != "2H":
            if offhand_roll < 0.50:
                shield = cd.generate_equipment(scenario=scenario, slot="Shield", tier=gear_tier)
                s_id = db.add_item(user_id, shield["name"], "Shield", shield["effect"], force=True)
                db.equip_item(user_id, s_id, "Shield")
                shield["id"] = s_id
                shield["equipped"] = 1
                shield["slot"] = "Shield"
                inventory_items.append(shield)
            elif offhand_roll < 0.75:
                # Dual wield offhand weapon (must not be 2H)
                off_w = cd.generate_equipment(scenario=scenario, slot="Weapon", tier=gear_tier)
                off_meta = parse_equipment_metadata(off_w)
                if off_meta.get("handedness") != "2H":
                    ow_id = db.add_item(user_id, off_w["name"], "Weapon", off_w["effect"], force=True)
                    db.equip_item(user_id, ow_id, "Shield")  # equipped to offhand
                    off_w["id"] = ow_id
                    off_w["equipped"] = 1
                    off_w["slot"] = "Shield"
                    inventory_items.append(off_w)

        # 3.5 Headwear, Gloves, Shoes, Accessory
        head = cd.generate_equipment(scenario=scenario, slot="Head", tier=gear_tier)
        h_id = db.add_item(user_id, head["name"], head.get("item_type", "Headwear"), head["effect"], force=True)
        db.equip_item(user_id, h_id, "Head")
        head["id"] = h_id
        head["equipped"] = 1
        head["slot"] = "Head"
        inventory_items.append(head)

        gloves = cd.generate_equipment(scenario=scenario, slot="Gloves", tier=gear_tier)
        g_id = db.add_item(user_id, gloves["name"], gloves.get("item_type", "Gloves"), gloves["effect"], force=True)
        db.equip_item(user_id, g_id, "Gloves")
        gloves["id"] = g_id
        gloves["equipped"] = 1
        gloves["slot"] = "Gloves"
        inventory_items.append(gloves)

        shoes = cd.generate_equipment(scenario=scenario, slot="Shoes", tier=gear_tier)
        s_id = db.add_item(user_id, shoes["name"], shoes.get("item_type", "Shoes"), shoes["effect"], force=True)
        db.equip_item(user_id, s_id, "Shoes")
        shoes["id"] = s_id
        shoes["equipped"] = 1
        shoes["slot"] = "Shoes"
        inventory_items.append(shoes)

        acc = cd.generate_equipment(scenario=scenario, slot="Accessory", tier=gear_tier)
        ac_id = db.add_item(user_id, acc["name"], acc.get("item_type", "Accessory"), acc["effect"], force=True)
        db.equip_item(user_id, ac_id, "Accessory 1")
        acc["id"] = ac_id
        acc["equipped"] = 1
        acc["slot"] = "Accessory 1"
        inventory_items.append(acc)

        # 4. Spells (Assign starter or procedural spells)
        int_val = stats["INT"]
        starter_spells = get_starter_spells(scenario, class_name, int_stat=int_val)
        if not starter_spells:
            starter_spells = ["magic_missile_t1_st", "mend_t1_st"]
        db.set_learned_spells(user_id, starter_spells)

        # 5. Consumables (1 Healing, 1 Mana, 1 Throwable / Utility)
        cons_tier = max(1, min(3, gear_tier))
        heal_pot = generate_procedural_potion(tier=cons_tier, effect_tags=["healing"], genre=scenario)
        hp_id = db.add_item(user_id, heal_pot["name"], heal_pot.get("item_type", "Potion"), heal_pot["effect"], force=True)
        heal_pot["id"] = hp_id
        heal_pot["equipped"] = 0
        inventory_items.append(heal_pot)

        mana_pot = generate_procedural_potion(tier=cons_tier, effect_tags=["mana_restore"], genre=scenario)
        mp_id = db.add_item(user_id, mana_pot["name"], mana_pot.get("item_type", "Potion"), mana_pot["effect"], force=True)
        mana_pot["id"] = mp_id
        mana_pot["equipped"] = 0
        inventory_items.append(mana_pot)

        throwable = generate_procedural_potion(tier=cons_tier, effect_tags=["corrosive_acid"], genre=scenario)
        t_id = db.add_item(user_id, throwable["name"], throwable.get("item_type", "Throwable"), throwable["effect"], force=True)
        throwable["id"] = t_id
        throwable["equipped"] = 0
        inventory_items.append(throwable)

        return char_dict, inventory_items


    @staticmethod
    def generate_party_companions(scenario: str, level: int, count: int) -> List[Dict[str, Any]]:
        """Generates automated companions scaled to the player level."""
        companions = []
        archetypes = ["Guardian", "Brute", "Skirmisher", "Caster", "Stalker"]
        for i in range(count):
            arch = random.choice(archetypes)
            c_stats = build_companion_stat_sheet(level, arch)
            end_val = c_stats.get("END", 3)
            c_hp = cd.derive_hp(end_val) + (level - 1) * 5
            companions.append({
                "name": f"Companion_{arch}_{i + 1}",
                "archetype": arch,
                "level": level,
                "hp": c_hp,
                "max_hp": c_hp,
                "stats": c_stats,
                "status_effects": [],
                "is_summon": False
            })
        return companions

    @staticmethod
    def generate_enemies(scenario: str, party: List[Dict[str, Any]], chapter: int = 1) -> List[Dict[str, Any]]:
        """Generates a balanced enemy encounter with full archetype stats, affixes, and intents."""
        enemies, _ = generate_balanced_encounter(party, scenario=scenario, location="Simulator Arena", chapter=chapter)
        if not enemies:
            # Fallback single enemy
            enemies = [generate_scenario_enemy(scenario, "Simulator Arena", chapter=chapter)]

        # Ensure all enemies have complete stat dictionaries and HP
        for m in enemies:
            if not m.get("stats") or not isinstance(m.get("stats"), dict):
                m["stats"] = build_enemy_stat_sheet(m.get("level", 1), m.get("archetype", "Brute"))
            if "max_hp" not in m:
                m["max_hp"] = m.get("hp", 80)
            if "hp" not in m:
                m["hp"] = m["max_hp"]
            if "status_effects" not in m:
                m["status_effects"] = []
        return enemies


class CombatantAI:
    """Heuristic goal-oriented combat decision maker supporting modern stances & archetypes."""

    @staticmethod
    def choose_action(
        acting_char: Dict[str, Any],
        party: List[Dict[str, Any]],
        enemies: List[Dict[str, Any]],
        inventory: List[Dict[str, Any]],
        learned_spells: List[str],
        scenario: str,
        combat_turn: int,
        archetype: str = "balanced"
    ) -> Dict[str, Any]:
        """Selects the most tactical, goal-oriented action based on survival and enemy vulnerability."""
        living_enemies = [e for e in enemies if e.get("hp", 0) > 0]
        if not living_enemies:
            return {"char": acting_char, "label": "Stand Guard", "stat": "END", "requirement": 2, "choice_type": "DEFENSIVE_GUARD"}

        # Target selection based on combat archetype
        if archetype == "berserker":
            target_enemy = min(living_enemies, key=lambda e: (e.get("hp", 100), -e.get("tier_rank", 1)))
        elif archetype == "defender":
            target_enemy = max(living_enemies, key=lambda e: (e.get("tier_rank", 1), e.get("hp", 100)))
        elif archetype == "infiltrator":
            target_enemy = min(living_enemies, key=lambda e: (e.get("max_hp", 100), e.get("hp", 100)))
        elif archetype == "chaos_fuzzer":
            target_enemy = random.choice(living_enemies)
        else:
            target_enemy = min(living_enemies, key=lambda e: (e.get("hp", 100), -e.get("tier_rank", 1)))

        target_name = target_enemy.get("name", "Enemy")
        target_arch = target_enemy.get("archetype", "Brute")

        curr_hp = acting_char.get("hp", 100)
        max_hp = acting_char.get("max_hp", 100)
        curr_mp = acting_char.get("mp", 20)
        hp_ratio = curr_hp / max(1, max_hp)

        # 0. INFILTRATOR STEALTH AMBUSH STRIKE (Turn 1 or Vanished)
        if archetype == "infiltrator" and (combat_turn == 1 or acting_char.get("combat_vanished")):
            return {
                "char": acting_char,
                "label": f"Ambush Backstab strike from shadows on {target_name}",
                "stat": "AGI",
                "requirement": 5,
                "mp_cost": 0,
                "choice_type": "MELEE_SLASHING_PIERCING",
                "attack_type": "thrust",
                "stance": "stealth",
                "is_stealth": True,
                "is_backstab": True,
                "target_enemy": target_name,
                "action_category": "attack"
            }

        # 1. EMERGENCY HEALING: Archetype-calibrated HP thresholds
        heal_threshold = 0.20 if archetype == "berserker" else (0.50 if archetype == "defender" else 0.35)
        if hp_ratio <= heal_threshold:
            # Check consumables for HP restore
            for idx, item in enumerate(inventory):
                if not item.get("equipped") and (item.get("hp_restore", 0) > 0 or "heal" in item.get("name", "").lower()):
                    chosen = item
                    return {
                        "char": acting_char,
                        "label": f"Use {chosen['name']}",
                        "stat": "ITEM",
                        "item": chosen,
                        "item_name": chosen["name"],
                        "requirement": 0,
                        "mp_cost": 0,
                        "action_category": "item"
                    }

            # Check learned spells for healing (mend, heal)
            for s_id in learned_spells:
                spell = get_spell(s_id)
                if spell and spell.get("discipline") == "heal":
                    mp_cost = spell.get("mp_cost", 10)
                    if curr_mp >= mp_cost:
                        return {
                            "char": acting_char,
                            "label": f"Cast {spell.get('name', 'Heal')}",
                            "stat": "INT",
                            "spell_id": s_id,
                            "requirement": 5,
                            "mp_cost": mp_cost,
                            "choice_type": "MAGIC_SPELL",
                            "action_category": "magic"
                        }

        # 2. TELEGRAPHED ATTACK DEFENSE: Guard or Brace
        enemy_intent = str(target_enemy.get("intent") or "").lower()
        if any(kw in enemy_intent for kw in ("heavy", "crush", "overcharge", "burst", "massive")):
            guard_chance = 0.0 if archetype == "berserker" else (1.0 if archetype == "defender" else 0.65)
            if random.random() < guard_chance:
                return {
                    "char": acting_char,
                    "label": f"Brace & Guard in defensive stance against {target_name}",
                    "stat": "END",
                    "requirement": 5,
                    "mp_cost": 0,
                    "stance": "defensive",
                    "choice_type": "DEFENSIVE_GUARD",
                    "action_category": "guard"
                }

        # 2.5 MANA RECOVERY: If MP is exhausted (< 6) and character has high INT, drink mana flask
        if curr_mp < 6 and acting_char.get("int_", acting_char.get("INT", 1)) >= 5:
            for idx, item in enumerate(inventory):
                if not item.get("equipped") and (item.get("mp_restore", 0) > 0 or "mana" in item.get("name", "").lower()):
                    chosen = item
                    return {
                        "char": acting_char,
                        "label": f"Use {chosen['name']}",
                        "stat": "ITEM",
                        "item": chosen,
                        "item_name": chosen["name"],
                        "requirement": 0,
                        "mp_cost": 0,
                        "action_category": "item"
                    }

        # 3. WEAKNESS EXPLOIT / ELEMENTAL SPELL
        # If enemy has elemental weakness or high physical defense (Guardian/Heavy Mech), cast magic
        is_armored = target_arch in ("Guardian", "Heavy Mech", "Heavy Borg")
        weaknesses = target_enemy.get("weaknesses", [])
        immunities = target_enemy.get("immunities", [])

        if (is_armored or weaknesses) and learned_spells:
            for s_id in learned_spells:
                spell = get_spell(s_id)
                if not spell or spell.get("discipline") != "attack":
                    continue
                mp_cost = spell.get("mp_cost", 8)
                if curr_mp >= mp_cost:
                    elem = spell.get("damage_type", "magical")
                    # Do not cast spells into an active immunity
                    if elem in immunities:
                        continue
                    if elem in weaknesses or is_armored:
                        return {
                            "char": acting_char,
                            "label": f"Cast {spell.get('name', 'Spell')} on {target_name}",
                            "stat": "INT",
                            "spell_id": s_id,
                            "requirement": 6,
                            "mp_cost": mp_cost,
                            "choice_type": "MAGIC_SPELL",
                            "action_category": "magic",
                            "target_enemy": target_name
                        }

        # 4. THROWABLE EXPLOSIVES (if enemy group > 2 or high threat)
        if len(living_enemies) >= 2 or target_enemy.get("tier_rank", 1) >= 3:
            for idx, item in enumerate(inventory):
                if not item.get("equipped") and (item.get("damage", 0) > 0 or any(k in item.get("name", "").lower() for k in ("bomb", "grenade", "flask", "vial"))):
                    chosen = item
                    return {
                        "char": acting_char,
                        "label": f"Throw {chosen['name']} at {target_name}",
                        "stat": "ITEM",
                        "item": chosen,
                        "item_name": chosen["name"],
                        "requirement": 0,
                        "mp_cost": 0,
                        "target_enemy": target_name,
                        "action_category": "item"
                    }


        # 5. WEAPON ATTACK (Dual Wield, 2H Versatile, or Standard Strike)
        weapon_item = next((i for i in inventory if i.get("equipped") and i.get("slot") == "Weapon"), None)
        offhand_item = next((i for i in inventory if i.get("equipped") and i.get("slot") == "Shield"), None)

        w_meta = parse_equipment_metadata(weapon_item) if weapon_item else {}
        off_meta = parse_equipment_metadata(offhand_item) if offhand_item else {}

        is_dual_wield = bool(
            weapon_item and offhand_item and (off_meta.get("item_type") == "Weapon" or "attack_types" in off_meta)
        )
        is_versatile = (w_meta.get("handedness") == "Versatile" and not offhand_item)

        # Resolve combat stance based on archetype and equipment
        if archetype == "berserker":
            assigned_stance = "2H" if is_versatile else "offensive"
        elif archetype == "defender":
            assigned_stance = "defensive"
        elif archetype == "infiltrator":
            assigned_stance = "stealth"
        elif archetype == "chaos_fuzzer":
            assigned_stance = random.choice(["offensive", "defensive", "balanced", "stealth", "dual_wield", "2H"])
        elif is_dual_wield:
            assigned_stance = "dual_wield"
        elif is_versatile:
            assigned_stance = "2H"
        else:
            assigned_stance = "balanced"

        req_val = 5
        if archetype == "chaos_fuzzer" and random.random() < 0.15:
            req_val = random.choice([0, 1, 99])

        if is_dual_wield:
            return {
                "char": acting_char,
                "label": f"Dual Flurry strike on {target_name} [{assigned_stance.upper()}]",
                "stat": "AGI",
                "requirement": req_val,
                "mp_cost": 0,
                "choice_type": "MELEE_SLASHING_PIERCING",
                "attack_type": (w_meta.get("attack_types") or ["slash"])[0],
                "stance": assigned_stance,
                "dual_wield": True,
                "target_enemy": target_name,
                "action_category": "attack"
            }
        elif is_versatile and assigned_stance in ("2H", "offensive"):
            return {
                "char": acting_char,
                "label": f"Two-Handed Heavy Cleave on {target_name} [{assigned_stance.upper()}]",
                "stat": "STR",
                "requirement": req_val,
                "mp_cost": 0,
                "choice_type": "MELEE_SLASHING_PIERCING",
                "attack_type": (w_meta.get("attack_types") or ["slash"])[0],
                "stance": assigned_stance,
                "target_enemy": target_name,
                "action_category": "attack"
            }
        else:
            atk_type = (w_meta.get("attack_types") or ["slash"])[0] if w_meta else "blunt"
            stat_used = "PER" if atk_type == "ranged" else ("AGI" if atk_type == "thrust" else "STR")
            return {
                "char": acting_char,
                "label": f"Attack {target_name} with {weapon_item.get('name', 'Fists') if weapon_item else 'Bare Fists'} [{assigned_stance.upper()}]",
                "stat": stat_used,
                "requirement": req_val,
                "mp_cost": 0,
                "choice_type": "MELEE_SLASHING_PIERCING" if atk_type != "blunt" else "MELEE_BLUNT",
                "attack_type": atk_type,
                "stance": assigned_stance,
                "target_enemy": target_name,
                "action_category": "attack"
            }


class CombatInvariantAuditor:
    """Rigorous audit assertions checked after every single turn."""

    @staticmethod
    def audit_turn(
        turn: int,
        session: Dict[str, Any],
        party: List[Any],
        action: Dict[str, Any],
        precomputed: Dict[str, Any]
    ) -> List[str]:
        violations = []

        # 1. Check Player Characters Health and MP Invariants
        player_chars = []
        for p in party:
            c = p[0] if isinstance(p, (tuple, list)) else p
            if isinstance(c, dict):
                player_chars.append(c)

        for c in player_chars:
            name = c.get("name", "Unknown")
            hp = c.get("hp")
            max_hp = c.get("max_hp")
            mp = c.get("mp")
            max_mp = c.get("max_mp")

            if hp is None or not isinstance(hp, (int, float)):
                violations.append(f"HP_NULL_OR_INVALID: Character '{name}' has non-numeric HP: {hp}")
            elif hp < 0:
                violations.append(f"NEGATIVE_HP: Character '{name}' has negative HP: {hp}")
            elif max_hp is not None and hp > max_hp:
                violations.append(f"OVERHEAL_EXCEEDED: Character '{name}' HP ({hp}) exceeds max_hp ({max_hp})")

            if mp is not None:
                if not isinstance(mp, (int, float)):
                    violations.append(f"MP_NON_NUMERIC: Character '{name}' has non-numeric MP: {mp}")
                elif mp < 0:
                    violations.append(f"NEGATIVE_MP: Character '{name}' has negative MP: {mp}")
                elif max_mp is not None and mp > max_mp:
                    violations.append(f"OVERMANA_EXCEEDED: Character '{name}' MP ({mp}) exceeds max_mp ({max_mp})")
            if c.get("temp_hp", 0) < 0:
                violations.append(f"NEGATIVE_TEMP_HP: Character '{name}' has negative temp_hp: {c.get('temp_hp')}")

        # 1.5 Check Friendly Companions
        companions = session.get("current_npcs", [])
        for comp in companions:
            if isinstance(comp, dict):
                c_name = comp.get("name", "Companion")
                c_hp = comp.get("hp")
                c_max = comp.get("max_hp")
                if c_hp is not None and c_hp < 0:
                    violations.append(f"NEGATIVE_COMPANION_HP: Companion '{c_name}' has negative HP: {c_hp}")
                if c_max is not None and c_hp is not None and c_hp > c_max:
                    violations.append(f"OVERHEAL_COMPANION: Companion '{c_name}' HP ({c_hp}) exceeds max_hp ({c_max})")
                if comp.get("temp_hp", 0) < 0:
                    violations.append(f"NEGATIVE_COMPANION_TEMP_HP: Companion '{c_name}' has negative temp_hp: {comp.get('temp_hp')}")

        # 2. Check Enemies Health and State Invariants
        surviving = session.get("nearby_enemies", [])
        dead_enemies = precomputed.get("dead_enemies", [])
        fled_enemies = precomputed.get("fled_enemies", [])
        yielded_enemies = precomputed.get("yielded_enemies", [])

        for m in surviving:
            m_name = m.get("name", "Enemy")
            m_hp = m.get("hp")
            m_max = m.get("max_hp")

            if m_hp is None or not isinstance(m_hp, (int, float)):
                violations.append(f"ENEMY_HP_INVALID: Enemy '{m_name}' has non-numeric HP: {m_hp}")
            elif m_hp <= 0:
                violations.append(f"ZOMBIE_SURVIVOR: Enemy '{m_name}' in surviving_enemies but has HP <= 0 ({m_hp})")
            elif m_max is not None and m_hp > m_max:
                violations.append(f"ENEMY_OVERHEAL: Enemy '{m_name}' HP ({m_hp}) exceeds max_hp ({m_max})")

            if m.get("temp_hp", 0) < 0:
                violations.append(f"NEGATIVE_ENEMY_TEMP_HP: Enemy '{m_name}' has negative temp_hp: {m.get('temp_hp')}")

            # Check Boss Phase 2 Transition Integrity
            if m.get("tier_rank", 1) >= 5:
                if m.get("phase_2_triggered"):
                    effects = [str(s).lower() for s in m.get("status_effects", [])]
                    if not any("enraged" in eff for eff in effects):
                        violations.append(f"BOSS_PHASE2_MISSING_ENRAGE: Boss '{m_name}' triggered Phase 2 without Enraged status")

        # 3. Check Damage Math Non-Negativity
        p_dmg = precomputed.get("total_player_damage", 0)
        e_dmg = precomputed.get("enemy_damage", 0)
        if p_dmg < 0:
            violations.append(f"NEGATIVE_PLAYER_DAMAGE: total_player_damage is negative: {p_dmg}")
        if e_dmg < 0:
            violations.append(f"NEGATIVE_ENEMY_DAMAGE: enemy_damage is negative: {e_dmg}")

        # 4. Check Status Effect Format and Integrity
        all_entities = player_chars + surviving + [c for c in companions if isinstance(c, dict)]
        for entity in all_entities:
            raw_eff = entity.get("status_effects", [])
            if isinstance(raw_eff, str):
                try:
                    import json
                    raw_eff = json.loads(raw_eff) if raw_eff.strip().startswith("[") else ([raw_eff] if raw_eff.strip() else [])
                except Exception:
                    raw_eff = [raw_eff] if raw_eff.strip() else []
            if isinstance(raw_eff, list):
                if len(raw_eff) > 6:
                    violations.append(f"STATUS_EFFECT_OVERFLOW: Entity '{entity.get('name')}' has {len(raw_eff)} status effects (max 6)")
                for eff in raw_eff:
                    if not isinstance(eff, str):
                        violations.append(f"STATUS_EFFECT_NON_STR: Entity '{entity.get('name')}' has non-string effect: {eff}")
                    elif len(eff.split()) > 10:
                        violations.append(f"STATUS_EFFECT_PROSE_LEAK: Status effect contains prose narrative: '{eff}'")

        # 5. Check Consumable Item Consumption
        if action.get("stat") == "ITEM":
            if not action.get("item_consumed"):
                violations.append(f"ITEM_NOT_CONSUMED: Action used item '{action.get('label')}' but item_consumed is False")

        # 6. Check Target Invariant (Entity targeted should exist in turn's active entities)
        target_req = action.get("target_enemy")
        if target_req:
            all_known_names = [e.get("name") for e in surviving] + list(dead_enemies) + list(fled_enemies) + list(yielded_enemies)
            if not any(target_req.lower() in (k or "").lower() for k in all_known_names):
                violations.append(f"TARGET_NOT_FOUND: Action targeted '{target_req}' which was not in combat encounter")

        # 7. Check Rewards Math (Non-negative rewards)
        xp_gain = precomputed.get("xp_gain", 0)
        gold_gain = precomputed.get("gold_gain", 0)
        if xp_gain < 0:
            violations.append(f"NEGATIVE_XP_GAIN: xp_gain is negative: {xp_gain}")
        if gold_gain < 0:
            violations.append(f"NEGATIVE_GOLD_GAIN: gold_gain is negative: {gold_gain}")

        return violations


class CombatSimulator:
    """Harness that orchestrates and executes batches of simulated combats."""

    def __init__(self, base_user_id: int = 900000):
        self.base_user_id = base_user_id

    def run_battle(
        self,
        battle_id: int = 1,
        scenario: str = "fantasy",
        level: int = 1,
        party_size: int = 1,
        seed: Optional[int] = None,
        verbose: bool = False,
        max_turns: int = 40,
        archetype: str = "balanced"
    ) -> SimulationResult:
        """Executes a single end-to-end combat encounter."""
        if seed is None:
            seed = random.randint(100000, 9999999)
        random.seed(seed)

        start_time = time.perf_counter()
        user_id = self.base_user_id + (battle_id % 1000)

        # 1. Generate Player and Equipment
        player_dict, inventory = CombatFuzzer.generate_player(scenario, level, user_id)
        learned_spells = db.get_learned_spells(user_id)

        # 2. Generate Companions (0 to party_size - 1)
        companion_count = max(0, party_size - 1)
        companions = CombatFuzzer.generate_party_companions(scenario, level, companion_count)

        party = [(player_dict, inventory)]
        session_npcs = list(companions)

        # 3. Generate Enemies
        allies_for_scaling = [player_dict] + companions
        enemies = CombatFuzzer.generate_enemies(scenario, allies_for_scaling, chapter=max(1, (level + 1) // 3))

        session = {
            "id": battle_id,
            "scenario": scenario,
            "combat_turn": 1,
            "nearby_enemies": enemies,
            "current_npcs": session_npcs
        }

        all_logs: List[str] = []
        all_violations: List[str] = []
        outcome = "stalemate"
        current_turn = 1
        exception_trace = None
        total_xp = 0
        total_gold = 0

        if verbose:
            safe_print(f"\n--- BATTLE #{battle_id} [{scenario.upper()} | Level {level} | Party {party_size} vs {len(enemies)} Enemies | Seed: {seed}] ---")

        try:
            while current_turn <= max_turns:
                session["combat_turn"] = current_turn

                # Check victory condition before turn
                living_enemies = [e for e in session.get("nearby_enemies", []) if e.get("hp", 0) > 0]
                if not living_enemies:
                    outcome = "victory"
                    break

                # Check player defeat condition before turn
                living_allies = [player_dict] if player_dict.get("hp", 0) > 0 else []
                living_allies += [c for c in session.get("current_npcs", []) if c.get("hp", 0) > 0]
                if not living_allies:
                    outcome = "defeat"
                    break

                # AI decides player action
                action = CombatantAI.choose_action(
                    acting_char=player_dict,
                    party=party,
                    enemies=living_enemies,
                    inventory=inventory,
                    learned_spells=learned_spells,
                    scenario=scenario,
                    combat_turn=current_turn,
                    archetype=archetype
                )

                # Skill check resolution
                stat_used = action.get("stat", "STR")
                if stat_used not in ("ITEM", "FREE"):
                    actor_stat = player_dict.get(f"{stat_used.lower()}_", player_dict.get(stat_used, 5))
                    req_val = action.get("requirement", 5)
                    luk_val = player_dict.get("luk", 5)
                    chk_res = resolve_check(actor_stat, req_val, luk_val)
                    action["check"] = chk_res
                    action["tier"] = chk_res.tier
                else:
                    action["tier"] = "success"

                # Execute Combat Turn via Engine
                precomputed = precompute_combat_turn(session, party, [action])
                total_xp += precomputed.get("xp_gain", 0)
                total_gold += precomputed.get("gold_gain", 0)

                turn_logs = precomputed.get("combat_log", [])
                all_logs.extend(turn_logs)
                if verbose:
                    for l in turn_logs:
                        safe_print(f"  [T{current_turn}] {l}")

                # Check Flee outcome
                if precomputed.get("fled_battle"):
                    outcome = "fled"
                    break

                # Audit Invariants for this Turn
                t_violations = CombatInvariantAuditor.audit_turn(current_turn, session, party, action, precomputed)
                if t_violations:
                    for tv in t_violations:
                        all_violations.append(f"Turn {current_turn}: {tv}")
                        if verbose:
                            safe_print(f"  ⚠️ AUDIT VIOLATION: {tv}")

                # Tick Status Timers for All Living Entities (DoT & duration decay)
                if player_dict.get("status_effects"):
                    tick_status_timers(player_dict)
                for comp in session.get("current_npcs", []):
                    if comp.get("status_effects"):
                        tick_status_timers(comp)
                for enemy in session.get("nearby_enemies", []):
                    if enemy.get("status_effects"):
                        tick_status_timers(enemy)

                # Remove any enemies defeated by DoTs
                session["nearby_enemies"] = [m for m in session.get("nearby_enemies", []) if m.get("hp", 0) > 0]

                # Check if all enemies defeated
                if not session.get("nearby_enemies"):
                    outcome = "victory"
                    break

                # Check if party completely wiped
                if player_dict.get("hp", 0) <= 0 and not any(c.get("hp", 0) > 0 for c in session.get("current_npcs", [])):
                    outcome = "defeat"
                    break

                current_turn += 1

            if current_turn > max_turns and outcome == "stalemate":
                all_violations.append(f"STALEMATE_DETECTED: Combat reached max limit ({max_turns} turns) without conclusion.")
                if verbose:
                    safe_print(f"  ⚠️ STALEMATE: Battle did not resolve within {max_turns} turns.")

        except Exception as exc:
            outcome = "crash"
            exception_trace = traceback.format_exc()
            all_violations.append(f"CRASH_EXCEPTION: {type(exc).__name__}: {str(exc)}")
            if verbose:
                safe_print(f"  💥 CRASH: {exception_trace}")

        finally:
            # Thorough cleanup of test user data from db
            try:
                db.delete_character(user_id, player_dict.get("id", 0))
            except Exception:
                pass
            try:
                with db.get_conn() as conn:
                    conn.execute("DELETE FROM inventory WHERE user_id = ?", (user_id,))
                    conn.execute("DELETE FROM user_settings WHERE user_id = ?", (user_id,))
                    conn.execute("DELETE FROM characters WHERE user_id = ?", (user_id,))
            except Exception:
                pass

        duration_ms = (time.perf_counter() - start_time) * 1000.0

        return SimulationResult(
            battle_id=battle_id,
            scenario=scenario,
            archetype=archetype,
            level=level,
            seed=seed,
            outcome=outcome,
            turns_taken=min(current_turn, max_turns),
            player_start_hp=player_dict.get("max_hp", 100),
            player_end_hp=max(0, player_dict.get("hp", 0)),
            party_size=party_size,
            enemy_count=len(enemies),
            enemies=enemies,
            combat_log=all_logs,
            violations=all_violations,
            exception=exception_trace,
            gold_gained=total_gold,
            xp_gained=total_xp,
            duration_ms=duration_ms
        )


    def run_batch(
        self,
        count: int = 100,
        scenarios: Optional[List[str]] = None,
        level_range: Tuple[int, int] = (1, 10),
        party_range: Tuple[int, int] = (1, 4),
        fail_fast: bool = False,
        verbose: bool = False,
        seed: Optional[int] = None,
        archetypes: Optional[List[str]] = None
    ) -> SimulationReport:
        """Executes a batch of randomized simulations across requested scenarios and level ranges."""
        report = SimulationReport()
        if not scenarios:
            scenarios = list(SUPPORTED_SCENARIOS)

        archetype_pool = archetypes or COMBAT_ARCHETYPES
        min_lvl, max_lvl = level_range
        min_party, max_party = party_range
        base_seed = seed if seed is not None else random.randint(100000, 9999999)
        batch_rng = random.Random(base_seed)

        for b_id in range(1, count + 1):
            scen = batch_rng.choice(scenarios)
            arch = archetype_pool[(b_id - 1) % len(archetype_pool)]
            lvl = batch_rng.randint(min_lvl, max_lvl)
            p_size = batch_rng.randint(min_party, max_party)
            b_seed = batch_rng.randint(100000, 9999999)

            res = self.run_battle(
                battle_id=b_id,
                scenario=scen,
                level=lvl,
                party_size=p_size,
                seed=b_seed,
                verbose=verbose,
                archetype=arch
            )
            report.add_result(res)

            if fail_fast and (res.violations or res.exception or res.outcome == "crash"):
                break

        return report
