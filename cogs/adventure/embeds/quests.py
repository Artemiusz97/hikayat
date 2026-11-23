"""Main story quest, structured objectives, Fog-of-War dossier, campaign goals, and tapestry embeds."""
from __future__ import annotations

from typing import Optional

import discord

import db
import game_engine
from localization import get_quest_ui_label
from mechanics.world.locations import clean_narrative_location_arrows, format_clean_location_badge
try:
    from mechanics.narrative.threat_clock import format_threat_consequence
except ImportError:
    format_threat_consequence = None  # type: ignore


def _get_quest_scenario_labels(scen_key: str = None) -> dict:
    """Returns scenario-adaptive terminology and emojis for the Quest UI tabs and notice boards."""
    from mechanics.world.locations import is_school_scenario
    scen = str(scen_key or "").lower()
    if is_school_scenario(scen):
        return {
            "main_tab": "Story Chapter",
            "main_emoji": "⭐",
            "bounties_tab": "Campus Favors",
            "bounties_emoji": "🎯",
            "board_label": "Campus Bulletin",
            "board_emoji": "📋"
        }
    if "cyberpunk" in scen or "sci_fi" in scen or "space" in scen:
        return {
            "main_tab": "Main Op",
            "main_emoji": "⭐",
            "bounties_tab": "Contracts",
            "bounties_emoji": "🎯",
            "board_label": "Terminal Postings",
            "board_emoji": "💾"
        }
    if "apocalypse" in scen:
        return {
            "main_tab": "Main Mission",
            "main_emoji": "⭐",
            "bounties_tab": "Dispatches",
            "bounties_emoji": "🎯",
            "board_label": "Radio Dispatch",
            "board_emoji": "📻"
        }
    return {
        "main_tab": "Main Quest",
        "main_emoji": "⭐",
        "bounties_tab": "Bounties",
        "bounties_emoji": "🎯",
        "board_label": "Notice Board",
        "board_emoji": "📋"
    }


def _resolve_session_ui_lang(session_id: int, session: Optional[dict] = None) -> str:
    try:
        sess = session if isinstance(session, dict) else (db.get_session(session_id) or {})
        host_uid = sess.get("host_user_id")
        if host_uid:
            ui_lang = str((db.get_settings(host_uid) or {}).get("ui_language") or "").strip().lower()
            if ui_lang:
                return ui_lang
        return str(sess.get("narration_language") or sess.get("language") or "en").strip().lower() or "en"
    except Exception:
        return "en"


def _resolve_reveal_all(session_id: int, session: Optional[dict] = None) -> bool:
    try:
        sess = session if isinstance(session, dict) else (db.get_session(session_id) or {})
        host_uid = sess.get("host_user_id")
        return bool(int((db.get_settings(host_uid) or {}).get("debug_reveal_all_info") or 0)) if host_uid else False
    except Exception:
        return False


def _format_structured_quest_embed_fields(
    embed: discord.Embed,
    session_id: int,
    redacted_q: dict,
    lang: str = "en",
) -> None:
    """Renders structured `1 Main Objective (2–3 stages) + 1–3 (Optional) Tactical Routes` on Discord embeds."""
    fow = redacted_q.get("fow") if isinstance(redacted_q.get("fow"), dict) else {}
    mo = redacted_q.get("main_objective") or fow.get("main_objective") or {}
    opts = redacted_q.get("optional_objectives") or fow.get("optional_objectives") or []
    leads_by_id = {
        str(ld.get("optional_id") or ld.get("lead_id") or ""): ld
        for ld in (fow.get("leads") or [])
        if isinstance(ld, dict)
    }

    if isinstance(mo, dict) and mo:
        stages = list(mo.get("stages") or [])
        total_st = max(1, int(mo.get("total_stages") or len(stages) or 2))
        cur_st = min(total_st, max(1, int(mo.get("current_stage") or 1)))
        comp_st = int(mo.get("completed_stages") or sum(1 for s in stages if isinstance(s, dict) and s.get("completed")))
        pct = int((comp_st / total_st) * 100) if total_st > 0 else 0
        bar = "█" * (pct // 10) + "░" * (10 - (pct // 10))

        stage_lbl = get_quest_ui_label('stage_short', lang)
        tags = [f"`[{bar}] {stage_lbl} {cur_st}/{total_st}`"]
        if fow.get("is_peak_chapter"):
            tags.append(f"⚡ `{get_quest_ui_label('peak_chapter', lang)}`")
        if int(mo.get("aid_dc_reduction") or 0) > 0:
            tags.append(f"🛡️ `{get_quest_ui_label('aid_active', lang)}`")
        if mo.get("bypass_unlocked"):
            tags.append(f"⏭️ `{get_quest_ui_label('shortcut_active', lang)}`")

        mo_title = clean_narrative_location_arrows(str(mo.get("title") or mo.get("text") or redacted_q.get("objective") or ""))
        stage_lines = [f"**{mo_title}**\n" + " • ".join(tags)]
        for idx_s, st in enumerate(stages, start=1):
            if not isinstance(st, dict):
                continue
            s_idx = int(st.get("stage_index") or idx_s)
            s_stat = str(st.get("status") or "locked").lower()
            s_done = bool(st.get("completed")) or s_stat in ("completed", "bypassed")
            s_lbl = clean_narrative_location_arrows(str(st.get("stage_label") or st.get("text") or f"{stage_lbl} {s_idx}"))
            raw_s_loc = str(st.get("target_location") or "").strip()
            s_loc = "" if raw_s_loc == "Hidden Lair" else format_clean_location_badge(raw_s_loc)
            s_npc = str(st.get("target_npc") or "").strip()

            if st.get("bypassed") or s_stat == "bypassed":
                stage_lines.append(f"⏭️ **{stage_lbl} {s_idx} (`[{get_quest_ui_label('bypassed', lang)}]`):** *{s_lbl}*")
            elif s_done:
                stage_lines.append(f"☑️ **{stage_lbl} {s_idx}:** *{s_lbl}*")
                for b_src in (st.get("clue_sources") or []):
                    if isinstance(b_src, dict) and b_src.get("bonus") and str(b_src.get("status") or "").lower() == "closed":
                        b_loc = format_clean_location_badge(str(b_src.get("location") or ""))
                        b_hint = clean_narrative_location_arrows(str(b_src.get("approach_hint") or b_src.get("label") or ""))
                        stage_lines.append(
                            f"   ↳ ⭐ `{get_quest_ui_label('source_bonus', lang)}` — *{b_hint}* (`{b_loc}`)"
                        )
            elif s_stat == "active" or s_idx == cur_st:
                loc_part = f"\n   ↳ 📍 `{s_loc}`" if s_loc else ""
                npc_part = f" • 👤 `{s_npc}`" if s_npc else ""
                stage_lines.append(f"📍 **{stage_lbl} {s_idx}:** *{s_lbl}*{loc_part}{npc_part}")
                clue_srcs = [s for s in (st.get("clue_sources") or []) if isinstance(s, dict)]
                for c_src in clue_srcs[:4]:
                    c_stat = str(c_src.get("status") or "open").lower()
                    c_icon = "☑️" if c_stat == "claimed" else ("🔥" if c_stat == "burned" else ("❄️" if c_stat == "cold" else "🔎"))
                    c_loc = format_clean_location_badge(str(c_src.get("location") or ""))
                    c_hint = clean_narrative_location_arrows(str(c_src.get("approach_hint") or c_src.get("label") or ""))
                    stat_key = f"source_{c_stat}" if c_stat in ("open", "burned", "cold", "claimed") else "source_open"
                    stat_lbl = get_quest_ui_label(stat_key, lang)
                    loc_sfx = f" (`{c_loc}`)" if c_loc else ""
                    if c_stat in ("burned", "cold"):
                        stage_lines.append(f"   ↳ {c_icon} ~~*{c_hint}*~~{loc_sfx} `[{stat_lbl}]`")
                    else:
                        stage_lines.append(f"   ↳ {c_icon} *{c_hint}*{loc_sfx}")
            else:
                stage_lines.append(f"🔒 **{stage_lbl} {s_idx}:** *{s_lbl}*")

        embed.add_field(
            name=f"★ {get_quest_ui_label('main_objective', lang)}",
            value="\n".join(stage_lines)[:1024],
            inline=False,
        )

    if opts:
        opt_lines = []
        role_label_keys = {
            "aid": "optional_aid",
            "bypass": "optional_bypass",
            "alternative": "optional_alternative",
            "threatened": "optional_threatened",
        }
        for opt in opts[:4]:
            if not isinstance(opt, dict):
                continue
            role = str(opt.get("role") or "aid").lower()
            role_badge = clean_narrative_location_arrows(
                str(opt.get("badge") or get_quest_ui_label(role_label_keys.get(role, "optional_aid"), lang))
            )
            st = str(opt.get("status") or "active").lower()
            if st == "completed" or opt.get("completed"):
                bonus_tag = f" `[{get_quest_ui_label('bonus_claimed', lang)}]`" if opt.get("bonus_claimed") else ""
                icon = f"☑️{bonus_tag}"
            elif st == "failed" or opt.get("failed"):
                icon = f"❌ `[{get_quest_ui_label('failed_route', lang)}]`"
            elif st == "bypassed" or opt.get("bypassed"):
                icon = "⏭️ `[Bypassed]`"
            elif st == "locked_out" or opt.get("locked_out"):
                icon = f"🔒 `[{get_quest_ui_label('locked_out', lang)}]`"
            else:
                icon = "🧭"

            apprs = []
            for a in (opt.get("approaches") or [])[:4]:
                if not isinstance(a, dict):
                    continue
                lbl = str(a.get("stat") or a.get("approach_id") or "").upper()
                if lbl:
                    apprs.append(f"~~{lbl}~~" if a.get("burned") else f"`{lbl}`")
            appr_str = f" — {' / '.join(apprs)}" if apprs else ""

            opt_title = clean_narrative_location_arrows(str(opt.get("title") or opt.get("text") or "Optional Lead"))
            line = f"{icon} `[{role_badge}]` **{opt_title}**{appr_str}"

            if st == "active" and opt.get("target_location"):
                loc_clean = format_clean_location_badge(str(opt.get("target_location") or ""))
                if loc_clean:
                    line += f"\n   ↳ 📍 `{loc_clean}`"

            hint = clean_narrative_location_arrows(str(opt.get("stakes_hint") or "").strip())
            if hint:
                line += f"\n   ↳ *{hint}*"

            opt_key = str(opt.get("optional_id") or opt.get("lead_id") or "")
            matched_ld = leads_by_id.get(opt_key) or {}
            if matched_ld.get("scouted_enemies"):
                names = ", ".join(str(e.get("name") or "Hostile") for e in matched_ld["scouted_enemies"][:3])
                line += f"\n   ↳ 👁️ *Scouted Pack:* {names}"

            opt_lines.append(line)

        if opt_lines:
            embed.add_field(
                name=f"🧭 {get_quest_ui_label('optional_routes', lang)}",
                value="\n".join(opt_lines)[:1024],
                inline=False,
            )


def _format_fow_dossier_embed_fields(
    embed: discord.Embed,
    session_id: int,
    quest: dict,
    raw_quest: Optional[dict] = None,
) -> None:
    """Appends Fog-of-War Alert Meter, Multi-Approach Leads, Bypassed badges, and Uncovered Twist intel."""
    reveal_all = False
    ui_lang = "en"
    try:
        sess = db.get_session(session_id) or {}
        ui_lang = _resolve_session_ui_lang(session_id, sess)
        reveal_all = _resolve_reveal_all(session_id, sess)
        anom_src = raw_quest if isinstance(raw_quest, dict) else (quest or {})
        q_notes_raw = str(anom_src.get("quest_notes") or "")
        has_anom_bp = (
            "anomaly_bp:" in q_notes_raw
            or "anomaly_blueprint:" in q_notes_raw
            or bool(isinstance(anom_src.get("anomaly_blueprint"), dict) and anom_src.get("anomaly_blueprint"))
            or str(anom_src.get("anomaly_blueprint_json") or "").strip() not in ("", "{}")
        )
        if has_anom_bp:
            from mechanics.world.anomaly_engine import (
                format_anomaly_dossier_summary,
                parse_blueprint_from_notes,
            )
            bp_q = parse_blueprint_from_notes(anom_src)
            if bp_q:
                is_rev = bool(reveal_all or "dossier_revealed:1" in q_notes_raw or bp_q.get("dossier_revealed"))
                dossier_obj = format_anomaly_dossier_summary(bp_q, revealed=is_rev)
                dossier_txt = dossier_obj.get("summary_text", "") if isinstance(dossier_obj, dict) else str(dossier_obj or "")
                if dossier_txt:
                    embed.add_field(
                        name="👁️ Anomaly Dossier (Revealed)" if is_rev else "🔒 Anomaly Dossier (Unrevealed)",
                        value=dossier_txt[:1024],
                        inline=False,
                    )
        fow = (
            quest.get("fow")
            if isinstance((quest or {}).get("fow"), dict)
            else game_engine.build_fog_of_war_quest_payload(session_id, quest, reveal_all=reveal_all)
        )
    except Exception:
        return
    if not isinstance(fow, dict) or fow.get("dossier_stage") != "compiled":
        return

    alert = int(fow.get("alert_level") or 0)
    max_alert = max(2, int(fow.get("max_alert") or 4))
    pips = "🔴" * alert + "⚪" * max(0, max_alert - alert)
    shield_badge = " • 🛡️ Companion Shield Ready" if not fow.get("rescue_shield_used") else " • 🛡️ Shield Spent"
    embed.add_field(
        name="🚨 Alert & Vigilance",
        value=f"{pips} `{alert}/{max_alert}`{shield_badge}",
        inline=True,
    )

    tc = fow.get("threat_clock")
    if isinstance(tc, dict) and tc.get("enabled"):
        tc_max = max(2, int(tc.get("max_segments") or 6))
        tc_filled = min(tc_max, max(0, int(tc.get("filled") or 0)))
        tc_pips = "🟧" * tc_filled + "⬜" * max(0, tc_max - tc_filled)
        consequence_note = ""
        last_ev = tc.get("last_consequence_event")
        if isinstance(last_ev, dict) and callable(format_threat_consequence):
            try:
                consequence_note = format_threat_consequence(last_ev, lang=ui_lang)
            except Exception:
                consequence_note = ""
        if not consequence_note:
            consequence_note = str(tc.get("last_consequence_note") or "").strip()
        raw_tc_note = consequence_note or str(tc.get("next_threshold_teaser") or "").strip()
        tc_note = clean_narrative_location_arrows(raw_tc_note) if raw_tc_note else ""
        tc_flags = []
        if tc.get("paused"):
            tc_flags.append(f"⏸️ {get_quest_ui_label('threat_paused', ui_lang)}")
        if tc.get("pushed_back"):
            tc_flags.append(f"⏪ {get_quest_ui_label('threat_pushed_back', ui_lang)}")
        if tc.get("engaged") is False:
            tc_flags.append(f"💤 {get_quest_ui_label('threat_dormant', ui_lang)}")
        if tc.get("reinforced"):
            tc_flags.append(f"⚠️ {get_quest_ui_label('threat_reinforced', ui_lang)}")
        if tc.get("world_scar_pending"):
            tc_flags.append(f"🌑 {get_quest_ui_label('threat_scar_pending', ui_lang)}")
        tc_extra = f"\n*{tc_note}*" if tc_note else ""
        if tc_flags:
            tc_extra += f"\n{' • '.join(tc_flags)}"
        embed.add_field(
            name=f"⏳ {get_quest_ui_label('threat_clock', ui_lang)}",
            value=f"{tc_pips} `{tc_filled}/{tc_max}`{tc_extra}"[:1024],
            inline=True,
        )

    leads = fow.get("leads") or []
    if leads and not fow.get("has_structured_objectives"):
        lead_lines = []
        for ld in leads[:4]:
            st = str(ld.get("status") or "active").lower()
            if st == "completed":
                badge = "☑️"
            elif st == "bypassed":
                badge = "⏭️ `[Bypassed]`"
            elif st == "failed":
                badge = "❌ `[Failed]`"
            elif st == "locked_out":
                badge = "🔒 `[Locked Out]`"
            else:
                badge = "📍"
            apprs = []
            for a in (ld.get("approaches") or [])[:4]:
                lbl = str(a.get("stat") or a.get("approach_id") or "").upper()
                apprs.append(f"~~{lbl}~~" if a.get("burned") else f"`{lbl}`")
            appr_str = f" — {' / '.join(apprs)}" if apprs else ""
            scout_str = ""
            if ld.get("scouted_enemies"):
                names = ", ".join(str(e.get("name") or "Hostile") for e in ld["scouted_enemies"][:3])
                scout_str = f"\n   ↳ 👁️ *Scouted Pack:* {names}"
            lead_lines.append(f"{badge} **{ld.get('title', 'Lead')}**{appr_str}{scout_str}")
        embed.add_field(name="🧭 Known Leads (Any Order)", value="\n".join(lead_lines)[:1024], inline=False)

    twist = fow.get("twist") or {}
    if twist.get("is_discovered") and twist.get("summary"):
        embed.add_field(
            name="⚡ Uncovered Twist",
            value=f"*{twist['summary']}*",
            inline=False,
        )


def _build_chronicle_tapestry_embed(session_id: int, slide_idx: int = 0) -> discord.Embed:
    """Renders the 4-Slide Chronicle Tapestry (`World`, `Factions`, `Bonds`, `Earned Title`) for Discord."""
    session = db.get_session(session_id) or {}
    ui_lang = _resolve_session_ui_lang(session_id, session)
    spine = db.get_campaign_spine(session_id) or {}
    tapestry = (spine.get("chronicle_tapestry") or session.get("chronicle_tapestry") or {})
    slides = list(tapestry.get("slides") or [])
    is_fallen = bool(
        tapestry.get("is_fallen_world")
        or str(tapestry.get("ending_archetype") or tapestry.get("ending_id") or "") == "fallen_world"
        or session.get("fallen_world")
    )

    if not slides:
        return discord.Embed(
            title=f"📜 {get_quest_ui_label('chronicle_tapestry', ui_lang)}",
            description="Complete Chapter 11 to weave your 4-slide Chronicle Tapestry.",
            color=discord.Color.dark_red() if is_fallen else discord.Color.gold(),
        )

    safe_idx = max(0, min(int(slide_idx or 0), len(slides) - 1))
    slide = slides[safe_idx] or {}
    slide_id = str(slide.get("slide_id") or slide.get("id") or "")
    slide_icons = {"world": "🌍", "factions": "🛡️", "bonds": "🤝", "title": "👑"}
    s_icon = slide_icons.get(slide_id, "📜")

    ending_title = clean_narrative_location_arrows(
        str(tapestry.get("ending_title") or get_quest_ui_label("chronicle_tapestry", ui_lang))
    )
    earned_title = clean_narrative_location_arrows(str(tapestry.get("earned_title") or ""))
    heading = clean_narrative_location_arrows(str(slide.get("heading") or f"Slide {safe_idx + 1}"))
    body = clean_narrative_location_arrows(str(slide.get("text") or slide.get("body") or ""))

    embed = discord.Embed(
        title=f"📜 {ending_title}",
        description=f"🏅 **{earned_title}**" if earned_title else None,
        color=discord.Color.dark_red() if is_fallen else discord.Color.gold(),
    )
    embed.add_field(
        name=f"{s_icon} {heading} ({safe_idx + 1}/{len(slides)})",
        value=body[:1024] or "—",
        inline=False,
    )
    nav_pills = []
    for idx_s, sl in enumerate(slides):
        sl_head = clean_narrative_location_arrows(str((sl or {}).get("heading") or f"#{idx_s + 1}"))
        nav_pills.append(f"**[{idx_s + 1}. {sl_head}]**" if idx_s == safe_idx else f"{idx_s + 1}. {sl_head}")
    embed.set_footer(text=" • ".join(nav_pills)[:2048])
    return embed


def _build_campaign_goals_embed(session_id: int) -> discord.Embed:
    session = db.get_session(session_id) or {}
    ui_lang = _resolve_session_ui_lang(session_id, session)
    spine = db.get_campaign_spine(session_id) or {}
    goals = db.get_session_campaign_goals(session_id)
    cur_ch = db.get_session_chapter(session_id) or 1
    peak_note = f" • ⚡ `{get_quest_ui_label('peak_chapter', ui_lang)}`" if int(cur_ch) in (3, 6, 8, 9, 10) else ""
    status_banner = ""
    if session.get("campaign_game_over"):
        status_banner = "\n💀 **FALLEN WORLD — CAMPAIGN DEFEAT (Chapter 10 Climax Lost)**"
    elif session.get("fallen_world") and not session.get("epilogue_ready") and not session.get("campaign_archived"):
        status_banner = f"\n🌑 **{get_quest_ui_label('fallen_world_epilogue', ui_lang).upper()}**"
    elif session.get("epilogue_ready"):
        status_banner = "\n🌅 **CHAPTER 11 EPILOGUE READY** — Choose Archive or Endless World!"
    elif session.get("endless_mode_unlocked"):
        status_banner = "\n♾️ **ENDLESS POST-CAMPAIGN WORLD ACTIVE**"

    embed = discord.Embed(
        title="🏆 Campaign End Goals",
        description=(
            f"Current Progress: **Chapter {cur_ch} of 11**{peak_note}{status_banner}\n"
            "Long-term campaign objectives tracking overall story progression."
        ),
        color=(
            discord.Color.dark_red()
            if (session.get("campaign_game_over") or session.get("fallen_world"))
            else discord.Color.gold()
        ),
    )

    tapestry = spine.get("chronicle_tapestry") or session.get("chronicle_tapestry") or {}
    if isinstance(tapestry, dict) and tapestry.get("slides"):
        e_title = clean_narrative_location_arrows(str(tapestry.get("ending_title") or "Chronicle Tapestry"))
        ep_badge = f" • 🏅 `{clean_narrative_location_arrows(str(tapestry['earned_title']))}`" if tapestry.get("earned_title") else ""
        embed.add_field(
            name=f"📜 {get_quest_ui_label('chronicle_tapestry', ui_lang)}",
            value=f"**{e_title}**{ep_badge}\n*Click **Chronicle Tapestry** below to inspect all 4 slides.*",
            inline=False,
        )

    scars = [
        e
        for e in (db.get_world_events(session_id, statuses=("active",)) or [])
        if (
            str(e.get("event_type") or "") == "world_scar"
            or (isinstance(e.get("metadata"), dict) and e["metadata"].get("is_world_scar"))
            or str(e.get("template_key") or "").startswith("world_scar_")
            or str(e.get("event_key") or "").startswith("scar_")
        )
    ]
    if scars:
        scar_lines = []
        for s in scars[:5]:
            meta = s.get("metadata") if isinstance(s.get("metadata"), dict) else {}
            s_tier = str(meta.get("scar_tier") or "bounty").lower()
            rem_type = str(meta.get("remediation_type") or "").lower()
            if s_tier == "peak":
                tier_tag = f" `[{get_quest_ui_label('peak_scar', ui_lang)}]`"
            elif s_tier == "buildup" or rem_type == "liberation":
                tier_tag = f" `[{get_quest_ui_label('liberation_op', ui_lang)}]`"
            else:
                tier_tag = ""
            scar_lines.append(
                f"• 🔥 **{s.get('title', 'World Scar')}** (`{s.get('location_name', 'Region')}`){tier_tag}"
            )
        embed.add_field(name=f"⚠️ Active World Scars ({len(scars)})", value="\n".join(scar_lines)[:1024], inline=False)
    if not goals:
        embed.add_field(name="No Campaign Goals", value="No long-term campaign goals are currently active.", inline=False)
        return embed

    for g in goals:
        pct = g.get("progress_pct", 0)
        bar = "█" * (pct // 10) + "░" * (10 - (pct // 10))
        status_icon = "🏆" if pct >= 100 else ("🎯" if pct > 0 else "📌")
        embed.add_field(
            name=f"{status_icon} {g['title']} [{bar}] {pct}%",
            value=f"*{g.get('description', '')}*",
            inline=False
        )
    return embed


def _build_main_quest_embed(session_id: int) -> discord.Embed:
    session = db.get_session(session_id)
    scen_key = session.get("scenario", "fantasy") if session else "fantasy"
    ui_lang = _resolve_session_ui_lang(session_id, session)
    reveal_all = _resolve_reveal_all(session_id, session)
    labels = _get_quest_scenario_labels(scen_key)
    raw_sq = db.get_active_story_quest(session_id)

    if not raw_sq:
        embed = discord.Embed(
            title=f"{labels['main_emoji']} {labels['main_tab']} — No Active Objective",
            description="You currently have no active main story chapter. Explore the world, interact with key characters, or check local notice boards to unlock the next chapter!",
            color=discord.Color.blue()
        )
        embed.add_field(
            name="Exploration Guidance",
            value="Use **/adventure resume** to continue your current journey or visit points of interest on the world map.",
            inline=False
        )
        return embed

    active_sq = game_engine.redact_quest_for_fog_of_war(session_id, raw_sq, reveal_all=reveal_all)
    has_structured = bool(active_sq.get("has_structured_objectives"))
    title = clean_narrative_location_arrows(active_sq.get("title", "Active Chapter"))
    obj = clean_narrative_location_arrows(active_sq.get("objective", ""))

    if has_structured:
        mo = active_sq.get("main_objective") or {}
        is_peak = bool(active_sq.get("is_peak_chapter"))
        all_main_done = bool(mo.get("completed"))
        hdr_icon = "⚡" if (is_peak or all_main_done) else "⭐"
        peak_suffix = f" [{get_quest_ui_label('peak_chapter', ui_lang).upper()}]" if is_peak else ""
        embed = discord.Embed(
            title=f"{hdr_icon} {labels['main_tab'].upper()}{peak_suffix}: {title}",
            description=f"**Objective:** {obj}",
            color=discord.Color.purple() if (is_peak or all_main_done) else discord.Color.blue(),
        )
        _format_structured_quest_embed_fields(embed, session_id, active_sq, lang=ui_lang)
    else:
        sub_objs = active_sq.get("sub_objectives", []) or []
        all_so_done = bool(sub_objs and all(isinstance(so, dict) and so.get("completed") for so in sub_objs))

        if all_so_done:
            embed = discord.Embed(
                title=f"⚡ {labels['main_tab'].upper()} (CLIMAX READY): {title}",
                description=f"**Objective:** {obj}",
                color=discord.Color.purple()
            )
        else:
            embed = discord.Embed(
                title=f"⭐ {labels['main_tab'].upper()}: {title}",
                description=f"**Objective:** {obj}",
                color=discord.Color.blue()
            )

        # Legacy Waypoint / Stage Compass Quick-Tracker for in-progress stage
        legacy_stage_total = 3
        if sub_objs:
            sq_qid_leg = str(active_sq.get("quest_id") or "")
            if sq_qid_leg:
                try:
                    dos_leg = db.get_quest_dossier(session_id, sq_qid_leg) or {}
                    ms_leg = (dos_leg.get("climax_spec") or {}).get("main_stages") or []
                    if ms_leg:
                        legacy_stage_total = len(ms_leg)
                    else:
                        wps_leg = db.get_quest_waypoints(session_id, sq_qid_leg, sub_obj_id=0) or []
                        if wps_leg:
                            legacy_stage_total = len(wps_leg)
                except Exception:
                    pass
        active_wp_lead = None
        if sub_objs and not all_so_done:
            for so in sub_objs:
                if not so.get("completed") and so.get("id") is not None:
                    try:
                        wp = so.get("active_waypoint") or db.get_active_waypoint(session_id, active_sq.get("quest_id"), so["id"])
                        if wp and wp.get("target_location"):
                            active_wp_lead = wp
                            break
                    except Exception:
                        pass

        if active_wp_lead:
            s_idx = active_wp_lead.get("stage_index", 1)
            s_lbl = clean_narrative_location_arrows(active_wp_lead.get("stage_label", ""))
            raw_wp_loc = str(active_wp_lead.get("target_location") or "").strip()
            s_loc = "" if raw_wp_loc == "Hidden Lair" else format_clean_location_badge(raw_wp_loc)
            lead_val = f"**Stage {s_idx}/{legacy_stage_total}:** *{s_lbl}*"
            if s_loc:
                lead_val += f"\n➔ 📍 **Target Location:** `{s_loc}`"
            embed.add_field(
                name="📍 Current Waypoint Lead",
                value=lead_val,
                inline=False
            )

        if sub_objs:
            sub_lines = []
            for so in sub_objs:
                is_done = bool(so.get("completed"))
                chk = "☑️" if is_done else "☐"
                arch = f" [{so['archetype']}]" if so.get("archetype") else ""
                raw_text = clean_narrative_location_arrows(str(so.get("text", "")).strip())
                if len(raw_text) > 175:
                    raw_text = raw_text[:172].rstrip() + "..."
                line = f"{chk}{arch} {raw_text}"
                if not is_done and so.get("id") is not None:
                    try:
                        wp = so.get("active_waypoint") or db.get_active_waypoint(session_id, active_sq.get("quest_id"), so["id"])
                        if wp:
                            s_idx = wp.get("stage_index", 1)
                            s_lbl = clean_narrative_location_arrows(wp.get("stage_label", ""))
                            raw_so_loc = str(wp.get("target_location") or "").strip()
                            s_loc = "" if raw_so_loc == "Hidden Lair" else format_clean_location_badge(raw_so_loc)
                            loc_display = f" ➔ 📍 `{s_loc}`" if s_loc else ""
                            line += f"\n   ↳ *Stage {s_idx}/{legacy_stage_total}: {s_lbl}{loc_display}*"
                    except Exception:
                        pass
                sub_lines.append(line)

            sub_val = "\n".join(sub_lines)
            if all_so_done:
                from mechanics.world.waypoints import get_story_quest_climax_location
                fow_meta = (active_sq.get("fow") or {}).get("climax") or {}
                sq_dos = db.get_quest_dossier(session_id, str(active_sq.get("quest_id") or ""))
                climax_spec_sq = (sq_dos or {}).get("climax_spec") or {}
                climax_open = bool(
                    reveal_all
                    or str(climax_spec_sq.get("gate_type") or climax_spec_sq.get("gate_mode") or "").lower() == "open"
                    or climax_spec_sq.get("is_unlocked")
                    or fow_meta.get("is_unlocked")
                )
                from mechanics.narrative.quest_engines import get_masked_climax_teaser
                _, climax_loc = get_story_quest_climax_location(session_id)
                sq_sess_em = db.get_session(session_id) or {}
                sq_lang_em = str(sq_sess_em.get("narration_language") or sq_sess_em.get("language") or "en").strip().lower() or "en"
                sq_teaser_em = get_masked_climax_teaser(
                    str((sq_dos or {}).get("engine") or active_sq.get("engine") or "MYSTERY_CASE"),
                    climax_spec_sq,
                    lang=sq_lang_em,
                )
                climax_display = (
                    f"`{format_clean_location_badge(climax_loc)}`"
                    if (climax_loc and climax_open)
                    else f"*{sq_teaser_em}*"
                )
                sub_val += (
                    f"\n\n⚡ **CLIMAX READY — FINAL SHOWDOWN:**\n"
                    f"• All preliminary sub-objectives completed!\n"
                    f"• 📍 **Destination:** {climax_display}\n"
                    f"• *Proceed to the destination to confront the climax encounter and conclude this chapter!*"
                )
            embed.add_field(name="Sub-Objectives (Tackle in any order)", value=sub_val[:1024], inline=False)

    # Streamlined Investigation Notes / Clues Dossier
    clues_str = active_sq.get("current_clues") or ""
    parsed_clues = game_engine.parse_clue_list(clues_str)
    if not parsed_clues:
        cur_ch = db.get_session_chapter(session_id) or 1
        ch_clues = db.get_session_clues(session_id, chapter=cur_ch)
        if ch_clues:
            parsed_clues = [f"{c.get('title', 'Lead')}: {c.get('lead_text', '')}" for c in ch_clues]
    if parsed_clues:
        clue_lines = "\n".join(f"**{i}.** {c}" for i, c in enumerate(parsed_clues, 1))
        embed.add_field(
            name=f"🔍 Investigation Notes ({len(parsed_clues)} Discovered)",
            value=clue_lines[:1024],
            inline=False
        )
    else:
        embed.add_field(
            name="🔍 Investigation Notes",
            value="*No clues discovered for this chapter yet. Search locations and converse with contacts to uncover leads.*",
            inline=False
        )

    # Rewards (100% Base Payout guaranteed on Main Completion; Optionals grant Field Bonuses)
    _format_fow_dossier_embed_fields(embed, session_id, active_sq, raw_quest=raw_sq)
    rxp = active_sq.get("reward_xp", 100)
    rgold = active_sq.get("reward_gold", 25)
    ritem = active_sq.get("reward_item", "")
    rewards = []
    if rxp:
        rewards.append(f"{rxp} XP")
    if rgold:
        rewards.append(f"{rgold} Gold")
    if ritem:
        rewards.append(f"🎒 Item: {ritem}")
    embed.add_field(
        name=get_quest_ui_label("base_reward_note", ui_lang),
        value=", ".join(rewards) if rewards else "Standard",
        inline=False,
    )

    return embed
