"""Active bounties, historical quest log, investigation Caseboard, and notice board embeds."""
from __future__ import annotations

import discord

import db
import game_engine
from mechanics.narrative.bounty import get_quest_type_icon as _quest_type_icon
from mechanics.world.locations import clean_narrative_location_arrows, format_clean_location_badge
from .quests import (
    _build_campaign_goals_embed,
    _build_main_quest_embed,
    _format_fow_dossier_embed_fields,
    _format_structured_quest_embed_fields,
    _get_quest_scenario_labels,
    _resolve_reveal_all,
    _resolve_session_ui_lang,
)


def _build_bounties_embed(session_id: int, selected_quest_id: str | None = None) -> discord.Embed:
    session = db.get_session(session_id)
    scen_key = session.get("scenario", "fantasy") if session else "fantasy"
    cur_loc = session.get("current_location", "") if session else ""
    ui_lang = _resolve_session_ui_lang(session_id, session)
    reveal_all = _resolve_reveal_all(session_id, session)
    labels = _get_quest_scenario_labels(scen_key)

    all_active = db.get_session_quests(session_id, status="Active")
    active_bounties = [
        q for q in all_active
        if not (q.get("is_story_quest") or q.get("quest_type") in ("Story Quest", "Main Quest"))
        and q.get("title") and q["title"] not in ("Active Objective", "Complete objective.", "")
    ]
    seen = set()
    deduped = []
    for b in active_bounties:
        qid = b.get("quest_id") or b.get("title")
        if qid not in seen:
            seen.add(qid)
            deduped.append(b)
    active_bounties = deduped

    # Detailed Inspector Mode
    if selected_quest_id:
        raw_bounty = next((b for b in active_bounties if b.get("quest_id") == selected_quest_id), None)
        if not raw_bounty:
            raw_bounty = db.get_quest_by_id(session_id, selected_quest_id)

        if raw_bounty:
            target_bounty = game_engine.redact_quest_for_fog_of_war(session_id, raw_bounty, reveal_all=reveal_all)
            b_id = target_bounty.get("quest_id", "")
            title = clean_narrative_location_arrows(target_bounty.get("title", "Bounty Details"))
            q_type = target_bounty.get("quest_type", "Side Bounty")
            icon = _quest_type_icon(q_type)
            obj = clean_narrative_location_arrows(target_bounty.get("objective", ""))
            clues = target_bounty.get("current_clues", "")

            embed = discord.Embed(
                title=f"{icon} {labels['bounties_tab']} Detail: {title}",
                description=f"**Type:** {q_type}\n**Status:** ⏳ In Progress\n\n**Objective:**\n{obj}",
                color=discord.Color.teal()
            )

            if target_bounty.get("has_structured_objectives"):
                _format_structured_quest_embed_fields(embed, session_id, target_bounty, lang=ui_lang)
            else:
                wps = db.get_quest_waypoints(session_id, b_id, sub_obj_id=None)
                active_wp = db.get_active_waypoint(session_id, b_id, sub_obj_id=None)

                # 1. Progression Roadmap & Stage Checklist (Legacy Fallback)
                if wps:
                    completed_count = len([w for w in wps if w.get("status") == "completed"])
                    total_stages = len(wps)
                    pct = int((completed_count / total_stages) * 100) if total_stages > 0 else 0
                    bar = "█" * (pct // 10) + "░" * (10 - (pct // 10))
                    cur_stage_idx = active_wp.get("stage_index", total_stages) if active_wp else total_stages

                    stage_lines = []
                    for wp in wps:
                        st_idx = wp.get("stage_index", 1)
                        st_status = wp.get("status", "locked")
                        st_lbl = clean_narrative_location_arrows(wp.get("stage_label", ""))
                        raw_st_loc = str(wp.get("target_location") or "").strip()
                        st_loc = "" if raw_st_loc == "Hidden Lair" else format_clean_location_badge(raw_st_loc)
                        st_npc = wp.get("target_npc", "")

                        if st_status == "completed":
                            chk = "☑️"
                            status_str = "Completed"
                            stage_lines.append(f"{chk} **Stage {st_idx} ({status_str}):** *{st_lbl}*")
                        elif st_status == "active":
                            chk = "📍"
                            status_str = "Active Lead"
                            loc_display = f"\n   ↳ 📍 **Target Location:** `{st_loc}`" if st_loc else ""
                            npc_display = f"\n   ↳ 👤 **Contact / NPC:** `{st_npc}`" if st_npc else ""

                            res_tgt = wp.get("resource_target", 0)
                            res_col = wp.get("resource_collected", 0)
                            res_display = ""
                            if res_tgt > 0:
                                res_pct = int(min(1.0, res_col / res_tgt) * 10)
                                res_bar = "█" * res_pct + "░" * (10 - res_pct)
                                res_display = f"\n   ↳ 📦 **Gathering Progress:** `{res_col}/{res_tgt}` [{res_bar}]"

                            stage_lines.append(f"{chk} **Stage {st_idx} ({status_str}):** *{st_lbl}*{loc_display}{npc_display}{res_display}")
                        else:
                            chk = "🔒"
                            status_str = "Locked"
                            stage_lines.append(f"{chk} **Stage {st_idx} ({status_str}):** *{st_lbl}*")

                    header_text = f"[{bar}] Stage {cur_stage_idx} of {total_stages} ({pct}%)"
                    embed.add_field(
                        name="📊 Progression Roadmap",
                        value=f"**Milestone Progress:** `{header_text}`\n\n" + "\n".join(stage_lines),
                        inline=False
                    )
                else:
                    raw_prog = target_bounty.get("progress") or "In Progress"
                    embed.add_field(name="📊 Progression Status", value=f"**Status:** `{raw_prog}`", inline=False)

                if active_wp:
                    action_lines = [f"**Current Task:** {clean_narrative_location_arrows(active_wp.get('stage_label', ''))}"]
                    raw_act_loc = str(active_wp.get("target_location") or "").strip()
                    if raw_act_loc and raw_act_loc != "Hidden Lair":
                        action_lines.append(f"📍 **Destination:** `{format_clean_location_badge(raw_act_loc)}`")
                    if active_wp.get("target_npc"):
                        action_lines.append(f"👤 **Key Contact:** `{active_wp['target_npc']}`")
                    trig = active_wp.get("completion_trigger", "arrival")
                    trig_str = "Travel to destination" if trig == "arrival" else "Pass thematic skill check / investigation"
                    action_lines.append(f"🎲 **Requirement:** *{trig_str}*")
                    embed.add_field(name="🎯 Current Milestone Action", value="\n".join(action_lines), inline=False)

            # 3. Contract Intel & Clues
            if clues:
                embed.add_field(name="🔍 Bounty Intel & Notes", value=clean_narrative_location_arrows(clues)[:1024], inline=False)

            # 4. Rewards
            _format_fow_dossier_embed_fields(embed, session_id, target_bounty, raw_quest=raw_bounty)
            rxp = target_bounty.get("reward_xp", 100)
            rgold = target_bounty.get("reward_gold", 25)
            ritem = target_bounty.get("reward_item", "")
            rewards = []
            if rxp:
                rewards.append(f"{rxp} XP")
            if rgold:
                rewards.append(f"{rgold} Gold")
            if ritem:
                rewards.append(f"🎒 Item: {ritem}")
            embed.add_field(name="Contract Rewards", value=", ".join(rewards) if rewards else "Standard", inline=False)
            return embed

    # Summary Overview Mode
    embed = discord.Embed(
        title=f"{labels['bounties_emoji']} {labels['bounties_tab']} ({len(active_bounties)} Active)",
        description="Select a contract from the dropdown menu below to inspect detailed progression, waypoints, or manage the bounty.",
        color=discord.Color.teal()
    )

    if not active_bounties:
        from mechanics.world.locations import location_has_bounty_board
        has_board = location_has_bounty_board(cur_loc, scen_key=scen_key)
        if has_board:
            embed.description = (
                "You currently have no active side bounties in your log.\n\n"
                f"📋 **{labels['board_label']} Available Here!**\n"
                f"Click the **{labels['board_label']}** button below to accept new postings!"
            )
        else:
            embed.description = (
                "You currently have no active side bounties in your log.\n\n"
                "Visit a local Guild Hall, Campus Bulletin, Tavern, or Hub to accept new commissions."
            )
        embed.add_field(name="Empty Contract Log", value="Accept commissions from notice boards across the world.", inline=False)
        return embed

    for idx, raw_b in enumerate(active_bounties[:5], start=1):
        b = game_engine.redact_quest_for_fog_of_war(session_id, raw_b, reveal_all=reveal_all)
        q_type = b.get("quest_type", "Side Bounty")
        icon = _quest_type_icon(q_type)
        obj = clean_narrative_location_arrows(b.get("objective", ""))
        if len(obj) > 200:
            obj = obj[:197].rstrip() + "..."
        opt_count = len(b.get("optional_objectives") or [])
        mo_b = b.get("main_objective") or {}
        if b.get("has_structured_objectives") and isinstance(mo_b, dict) and mo_b.get("total_stages"):
            total_b_st = max(1, int(mo_b.get("total_stages") or 2))
            cur_b_st = min(total_b_st, max(1, int(mo_b.get("current_stage") or 1)))
            struct_tag = f" • `Stage {cur_b_st}/{total_b_st} + {opt_count} Optional`"
        elif b.get("has_structured_objectives"):
            struct_tag = f" • `1 Main + {opt_count} Optional`"
        else:
            struct_tag = ""

        embed.add_field(
            name=f"{idx}. {icon} {clean_narrative_location_arrows(b['title'])} [{q_type}]",
            value=f"**Objective:** {obj}{struct_tag}",
            inline=False
        )

    return embed


def _build_history_embed(session_id: int, selected_quest_id: str | None = None) -> discord.Embed:
    session = db.get_session(session_id)
    ui_lang = _resolve_session_ui_lang(session_id, session)
    reveal_all = _resolve_reveal_all(session_id, session)
    all_quests = db.get_session_quests(session_id)
    history_quests = [
        q for q in all_quests
        if q.get("status") in ("Completed", "Failed", "Abandoned")
        and q.get("title") and q["title"] not in ("Active Objective", "Complete objective.", "")
    ]
    seen = set()
    deduped = []
    for q in history_quests:
        qid = q.get("quest_id") or q.get("title")
        if qid not in seen:
            seen.add(qid)
            deduped.append(q)
    history_quests = deduped

    # Detailed Inspector Mode for a specific past quest
    if selected_quest_id:
        raw_q = next((q for q in history_quests if q.get("quest_id") == selected_quest_id), None)
        if not raw_q:
            raw_q = db.get_quest_by_id(session_id, selected_quest_id)

        if raw_q:
            target_q = game_engine.redact_quest_for_fog_of_war(session_id, raw_q, reveal_all=reveal_all)
            title = target_q.get("title", "Past Quest Record")
            status = target_q.get("status", "Completed")
            is_sq = bool(target_q.get("is_story_quest") or target_q.get("quest_type") in ("Story Quest", "Main Quest"))
            icon = "⭐" if is_sq else _quest_type_icon(target_q.get("quest_type"))
            badge = "✅ Completed" if status == "Completed" else ("🛑 Failed" if status == "Failed" else "⏸️ Abandoned")

            embed = discord.Embed(
                title=f"{icon} Historical Record: {title}",
                description=f"**Type:** {'Story Chapter' if is_sq else target_q.get('quest_type', 'Side Bounty')}\n**Outcome:** {badge}\n\n**Objective:**\n{target_q.get('objective', '')}",
                color=discord.Color.gold() if status == "Completed" else discord.Color.dark_grey()
            )

            if target_q.get("has_structured_objectives"):
                _format_structured_quest_embed_fields(embed, session_id, target_q, lang=ui_lang)
            elif is_sq:
                sub_objs = target_q.get("sub_objectives", []) or []
                if sub_objs:
                    sub_lines = []
                    for so in sub_objs:
                        chk = "☑️" if so.get("completed") else "☐"
                        arch = f" [{so['archetype']}]" if so.get("archetype") else ""
                        sub_lines.append(f"{chk}{arch} {so.get('text', '')}")
                    embed.add_field(name="Sub-Objectives Record", value="\n".join(sub_lines)[:1024], inline=False)

            rxp = target_q.get("reward_xp", 100)
            rgold = target_q.get("reward_gold", 25)
            ritem = target_q.get("reward_item", "")
            rewards = []
            if rxp:
                rewards.append(f"{rxp} XP")
            if rgold:
                rewards.append(f"{rgold} Gold")
            if ritem:
                rewards.append(f"🎒 Item: {ritem}")
            embed.add_field(name="Rewards Earned", value=", ".join(rewards) if rewards else "Standard", inline=False)
            return embed

    # Summary Overview Mode
    completed_sq = [q for q in history_quests if (q.get("is_story_quest") or q.get("quest_type") in ("Story Quest", "Main Quest")) and q.get("status") == "Completed"]
    completed_bnt = [q for q in history_quests if not (q.get("is_story_quest") or q.get("quest_type") in ("Story Quest", "Main Quest")) and q.get("status") == "Completed"]
    total_xp = sum(q.get("reward_xp", 0) for q in history_quests if q.get("status") == "Completed")
    total_gold = sum(q.get("reward_gold", 0) for q in history_quests if q.get("status") == "Completed")

    embed = discord.Embed(
        title="📜 Quest Log — History & Archive",
        description=(
            f"📊 **Career Record:** `{len(completed_sq)}` Chapters Completed • `{len(completed_bnt)}` Bounties Finished\n"
            f"💰 **Total Rewards Earned:** `+{total_xp:,} XP` • `+{total_gold:,} Gold`\n\n"
            "*Select an archived quest from the dropdown below to inspect full records and past sub-objectives.*"
        ),
        color=discord.Color.gold()
    )

    if not history_quests:
        embed.add_field(name="No Past Records", value="No completed or archived quests found in your history log yet.", inline=False)
        return embed

    history_lines = []
    for q in history_quests[:12]:
        status = q.get("status", "Completed")
        badge = "✅" if status == "Completed" else ("🛑" if status == "Failed" else "⏸️")
        is_sq = bool(q.get("is_story_quest") or q.get("quest_type") in ("Story Quest", "Main Quest"))
        q_label = "Story Quest" if is_sq else q.get("quest_type", "Side Bounty")
        icon = "⭐" if is_sq else _quest_type_icon(q.get("quest_type"))
        history_lines.append(f"• {badge} {icon} **{q['title']}** *({q_label})*")

    embed.add_field(
        name=f"Archived Quests ({len(history_quests)} Total)",
        value="\n".join(history_lines)[:1024],
        inline=False
    )

    return embed


def _build_caseboard_embed(session_id: int, selected_suspect: str | None = None) -> discord.Embed:
    all_clues = db.get_session_clues(session_id)

    cur_ch = db.get_session_chapter(session_id) or 1
    suspect_filter = None if selected_suspect in (None, "__all__", "") else selected_suspect
    clues = [c for c in all_clues if not suspect_filter or (c.get("linked_npc") and suspect_filter.lower() in c["linked_npc"].lower())]

    embed = discord.Embed(
        title="🗂️ Campaign Investigation Caseboard",
        description=(
            f"Campaign Dossier — **Chapter {cur_ch} of 11** • Total Evidence: `{len(all_clues)}` Leads\n"
            + (f"🔍 *Filtered by suspect:* **{suspect_filter}**\n" if suspect_filter else "*All verified findings, witness testimonies, and physical traces recorded across all chapters.*\n")
        ),
        color=discord.Color.dark_teal()
    )

    if not clues:
        embed.add_field(
            name="Empty Case File",
            value="*No evidence recorded yet. Complete investigation waypoints, uncover phone rumors, or question local contacts to log leads!*",
            inline=False
        )
        return embed

    deductions = [c for c in clues if c.get("category") == "deduction"]
    if deductions:
        ded_lines = [f"⚡ **{d['title']}**\n*{d['lead_text']}*" for d in deductions[:4]]
        embed.add_field(
            name=f"⚡ Breakthrough Deductions ({len(deductions)})",
            value="\n\n".join(ded_lines)[:1024],
            inline=False
        )

    categories = [
        ("physical", "🔍 Physical Evidence"),
        ("testimonial", "🗣️ Witness Testimony"),
        ("digital", "💾 Digital & Phone Records"),
        ("document", "📄 Documents & Files")
    ]

    for cat_key, cat_label in categories:
        cat_clues = [c for c in clues if c.get("category") == cat_key]
        if cat_clues:
            lines = []
            for c in cat_clues[:5]:
                if c.get("is_consumed"):
                    status_icon = "🔗 [Used]"
                elif c.get("is_verified"):
                    status_icon = "✅ [Verified]"
                else:
                    status_icon = "⏳ [Open Lead]"
                loc_str = f"📍 {format_clean_location_badge(c['source_location'])}" if c.get("source_location") else "📍 Unspecified"
                npc_str = f" • 👤 {c['linked_npc']}" if c.get("linked_npc") else ""
                lines.append(
                    f"{status_icon} **{c['title']}**\n"
                    f"*{c['lead_text'][:120]}*\n"
                    f"↳ `{loc_str}`{npc_str} `[Ch. {c.get('chapter', 1)}]`"
                )
            embed.add_field(
                name=f"{cat_label} ({len(cat_clues)})",
                value="\n".join(lines)[:1024],
                inline=False
            )

    return embed


def _build_quest_log_embed(session_id: int, tab: str = "Main Quest", selected_quest_id: str | None = None, selected_suspect: str | None = None) -> discord.Embed:
    if tab in ("Main Quest", "Active", "Notes"):
        return _build_main_quest_embed(session_id)
    elif tab in ("Bounties", "Active Bounties"):
        return _build_bounties_embed(session_id, selected_quest_id=selected_quest_id)
    elif tab == "Goals":
        return _build_campaign_goals_embed(session_id)
    elif tab == "Caseboard":
        return _build_caseboard_embed(session_id, selected_suspect=selected_suspect)
    elif tab == "History":
        return _build_history_embed(session_id, selected_quest_id=selected_quest_id)
    return _build_main_quest_embed(session_id)


def _build_bounty_board_embed(session: dict, bounties: list[dict]) -> discord.Embed:
    from mechanics.narrative.bounty import get_bounty_board_title_name
    from mechanics.world.locations import get_zone_location_name
    scen_key = session.get("scenario", "fantasy") if session else "fantasy"
    raw_loc = session.get("current_location", "Local Region") if session else "Local Region"
    loc = get_zone_location_name(raw_loc)
    board_title, board_emoji = get_bounty_board_title_name(scen_key)

    embed = discord.Embed(
        title=f"{board_emoji} {board_title} — {loc}",
        description="Pick a posting from the dropdown below to accept it into your active Quest Log!",
        color=discord.Color.gold()
    )

    if not bounties:
        embed.add_field(name="No Bounties Available", value="Click **Refresh Board** to request new postings from local contacts.", inline=False)
        return embed

    for idx, b in enumerate(bounties, start=1):
        rxp = b.get("reward_xp", 150)
        rgold = b.get("reward_gold", 40)
        ritem = b.get("reward_item", "")
        rew_parts = [f"{rxp} XP", f"{rgold} Gold"]
        if ritem:
            rew_parts.append(f"Item: {ritem}")
        rew_str = ", ".join(rew_parts)
        q_type = b.get("quest_type", "Side Bounty")
        icon = _quest_type_icon(q_type)

        embed.add_field(
            name=f"{idx}. {icon} {clean_narrative_location_arrows(b['title'])} [{q_type}]",
            value=f"**Objective:** {clean_narrative_location_arrows(b['objective'])}\n**Rewards:** {rew_str}",
            inline=False
        )

    return embed
