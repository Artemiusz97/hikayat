from .constants import *
import db
import re
import json
import random
import logging
import scenario_data
from mechanics.world.locations import *
from mechanics.social.persona import *
import game_engine
from db import adb
import asyncio
from game_engine.turn_context import TurnContext
from models.llm_schemas import TurnOutcome, ActionClassification, OpeningScene

def _build_quest_and_bounty_directives(session: dict, ctx) -> tuple[str, str]:
    """Extracted Phase 2A Builder for Story Quests and Bounties."""
    cur_chapter = db.get_session_chapter(session["id"])

    campaign_goals = db.get_session_campaign_goals(session["id"])



    goals_lines = []

    for g in campaign_goals:

        pct = g.get("progress_pct", 0)

        bar = "█" * (pct // 10) + "░" * (10 - (pct // 10))

        goals_lines.append(f"- [{g['id']}] **{g['title']}** `[{bar}] {pct}%`\n  *{g.get('description', '')}*")

    goals_context = "\n".join(goals_lines) if goals_lines else "• No campaign end goals established yet."



    game_engine.ensure_story_quest_exists(session)

    story_quest = ctx.story_quest

    if story_quest:

        clues_str = story_quest.get("current_clues") or ""

        parsed_clues = game_engine.parse_clue_list(clues_str)

        clue_count = len(parsed_clues)



        sub_objs = story_quest.get("sub_objectives", []) or []

        sub_obj_lines = []

        for so in sub_objs:

            box = "[x]" if so.get("completed") else "[ ]"

            arch_str = f" [{so['archetype']}]" if so.get("archetype") else ""

            sub_obj_lines.append(f"  {box} Sub-Quest #{so.get('id', '?')}{arch_str}: {so.get('text', '')}")

        sub_objs_context = "\n".join(sub_obj_lines) if sub_obj_lines else "  (No sub-quests listed)"



        concise_clues = "\n".join(f"• {c}" for c in parsed_clues[:6]) if parsed_clues else "• No clues discovered yet."



        all_sub_objs_done = sub_objs and all(so.get("completed") for so in sub_objs)



        climax_note = ""

        goals_all_complete = campaign_goals and all(g.get("progress_pct", 0) >= 100 for g in campaign_goals)

        if goals_all_complete and all_sub_objs_done:

            climax_note = (

                "\n🏆 [GRAND CAMPAIGN FINALE ENCOUNTER]:\n"

                "All Campaign End Goals are achieved and all sub-quests are complete! You MUST stage the ultimate Grand Finale Encounter this turn!\n"

                "- Resolve every active Campaign End Goal with an epic final showdown or climax.\n"

                "- Require a decisive action or check to achieve total campaign victory!"

            )

        elif all_sub_objs_done:

            climax_note = (

                "\n⚡ [STORY QUEST CLIMAX ENCOUNTER READY]:\n"

                "All sub-quests are completed! You MUST generate a mandatory High-Stakes Climax Encounter this turn:\n"

                "- High School / Modern: Confronting the Big Bully, a tense public debate, or a major social exposure check.\n"

                "- Fantasy / Sci-Fi / Cyberpunk: A boss fight, high-DC magic sealing ritual, or intense escape.\n"

                "- Do NOT mark the story quest as Completed unless the player SUCCESSFULLY OVERCOMES this Climax Encounter!"

            )



        story_quest_context = (

            f"### 🏆 LONG-TERM CAMPAIGN END GOALS\n"

            f"{goals_context}\n\n"

            f"### 📜 ACTIVE STORY QUEST\n"

            f"- **Quest ID:** {story_quest['quest_id']}\n"

            f"- **Title:** {story_quest['title']}\n"

            f"- **Type / Archetype:** {story_quest.get('quest_type', 'Story Quest')}\n"

            f"- **Main Objective:** {story_quest['objective']}\n"

            f"- **Sub-Quests (Players can tackle in any order):**\n{sub_objs_context}\n"

            f"- **Investigation Notes ({clue_count} discovered, narrative flavor only):**\n"

            f"{concise_clues}"

            f"{climax_note}"

        )

    else:

        story_quest_context = "No active Story Quest."



    active_bounties = [q for q in (ctx.active_quests + ctx.active_bounties) if not q.get("is_story_quest") and q.get("quest_type") not in ("Story Quest", "Main Quest")]

    if active_bounties:

        bounty_lines = []

        for b in active_bounties[:3]:

            qid = b.get("quest_id", "")

            active_wp = db.get_active_waypoint(session["id"], qid, sub_obj_id=None) if qid else None

            wp_info = ""

            if active_wp:

                s_idx = active_wp.get("stage_index", 1)

                s_lbl = active_wp.get("stage_label", "")

                s_loc = active_wp.get("target_location", "")

                s_npc = active_wp.get("target_npc", "")

                parts = [f"Stage {s_idx}: {s_lbl}"]

                if s_loc: parts.append(f"Location: {s_loc}")

                if s_npc: parts.append(f"Target NPC: {s_npc}")

                wp_info = f" [Current Task: {' | '.join(parts)}]"

            bounty_lines.append(f"- [quest_id: {qid}] [{b['quest_type']}] {b['title']}: {b['objective']}{wp_info}")

        side_bounties_context = "\n".join(bounty_lines)

    else:

        side_bounties_context = "No active side bounties."
    return story_quest_context, side_bounties_context

def _build_player_actions_text(actions: list) -> str:
    """Extracted Phase 2A Builder for Player Actions."""
    action_lines = []
    for a in actions:

        mp_note = f" (spent {a['mp_spent']} MP)" if a["mp_spent"] else ""

        stat = a.get("stat")

        tier = a["check"].tier

        if stat in ("NONE", "FREE") or (a["check"].chance == 100 and tier == "success"):

            tier_directive = "Free Action / Standard Choice (Clean execution, no roll check needed)"

        elif tier == "crit_fail":

            from skill_check import calculate_hazard_damage

            req = getattr(a["check"], "requirement", 10)

            hazard_dmg = calculate_hazard_damage(req, tier, a["char"].get("max_hp", 100))

            tier_directive = (

                f"Critical Failure (FAIL FORWARD: Catastrophic disaster, major trap trigger, or sudden ambush that flips scene stakes). "

                f"[MANDATORY HAZARD MATH]: If a physical trap or hazard hits {a['char']['name']}, it MUST deal exactly {hazard_dmg} damage!"

            )

        elif tier == "fail":

            from skill_check import calculate_hazard_damage

            req = getattr(a["check"], "requirement", 10)

            hazard_dmg = calculate_hazard_damage(req, tier, a["char"].get("max_hp", 100))

            tier_directive = (

                f"Failure (FAIL FORWARD: Suffer a complication, escalation, or success-at-a-cost; keep momentum moving!). "

                f"[MANDATORY HAZARD MATH]: If a physical trap or hazard hits {a['char']['name']}, it MUST deal exactly {hazard_dmg} damage!"

            )

        elif tier == "crit_success":

            tier_directive = "Critical Success (Flawless outcome + bonus insight, loot, or tactical advantage)"

        else:

            tier_directive = "Success (Standard clean outcome)"



        action_lbl = str(a.get("label", ""))

        action_lower = action_lbl.lower()

        if any(kw in action_lower for kw in ("loot", "search the fallen", "scavenge the fallen", "search the bodies", "search and loot", "inspect the fallen", "scavenge the remains", "gather spoils")):

            per_val = int(a["char"].get("per_", a["char"].get("per", 5)))

            luk_val = int(a["char"].get("luk", a["char"].get("luk", 5)))

            tier_directive += (

                f"\n  * BATTLEFIELD LOOTING & SPOILS SCALING (Perception: {per_val}, Luck: {luk_val}):\n"

                f"    - Free Action: The character successfully searches and loots the fallen enemies.\n"

                f"    - Perception ({per_val}): Directly controls the quantity and thoroughness of discoveries (e.g. concealed daggers, hidden coin pouches, keys, letters, enemy equipment).\n"

                f"    - Luck ({luk_val}): Directly controls item quality and rare bonus finds (e.g. pristine condition gear, rare materials, bonus currency in `gold_change`, magical/tech accessories).\n"

                f"    - Populate all scavenged items and gear in `items_gained` and currency in `gold_change`."

            )



        action_lines.append(

            f"- {a['char']['name']} chose to: \"{action_lbl}\"{mp_note} -> "

            f"Outcome (already determined, do not contradict): {tier_directive} "

            f"(success chance was {a['check'].chance}%)"

        )

    actions_text = "\n".join(action_lines)
    return "\n".join(action_lines)

async def _build_history_context(session: dict, ctx, budget=None) -> str:
    """Extracted Phase 2A Builder for Memory and History."""
    import game_engine
    # Build hybrid FTS5 query context for past arc memory retrieval

    q_loc = session.get('current_location', '')

    q_npcs = " ".join(n.get("name", "") if isinstance(n, dict) else str(n) for n in session.get("current_npcs", []))

    q_quest = ctx.story_quest.get("objective", "") if ctx.story_quest else ""

    query_context = f"{q_loc} {q_npcs} {q_quest}"

    from llm_client import get_embedding
    query_embedding = await get_embedding(query_context)

    hist_text = game_engine._history_text(session['history'], session_id=session.get('id'), query_context=query_context, budget=budget, query_embedding=query_embedding)
    return hist_text, query_embedding

