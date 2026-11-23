"""Scene, outcome, synchronized co-op, image attachment, and world-map Discord embeds."""
from __future__ import annotations

import json
import logging
import os

import discord

import db
import game_engine
from .party import (
    _RESULT_COLORS,
    _RESULT_TITLES,
    _location_text,
    _party_vitals_text,
    _safe_add_field,
    _safe_int,
    _tracker_group_text,
    _tracker_header,
    _truncate_embed_text,
    _truncate_field_name,
)

logger = logging.getLogger("hikayat.adventure")


def build_outcome_embeds(
    outcome: dict,
    check_field_name: str,
    check_field_value: str,
    loot_text: str,
    result_display: str,
    xp_by_user: dict | None = None,
    session_id: int | None = None,
    primary_tier: str = "success",
) -> list[discord.Embed]:
    """Build the Result embed for both solo/turn-based and sync modes.

    Args:
        outcome:           The raw LLM outcome dict.
        check_field_name:  Name for the check field (e.g. '🎯 Check' / '🎯 Checks').
        check_field_value: Formatted check summary text.
        loot_text:         Pre-formatted loot string (empty string if none).
        result_display:    'detailed' or 'compact'.
        xp_by_user:        Optional {char_name: xp_gained} for Detailed XP display.
        session_id:        Optional session ID to look up story clue progress.
        primary_tier:      The dominant check tier for colour/title selection.
    """
    color = _RESULT_COLORS.get(primary_tier, discord.Color.orange())
    title = _RESULT_TITLES.get(primary_tier, "Result")

    desc = (
        outcome.get("outcome_narrative")
        or outcome.get("narrative")
        or outcome.get("action_outcome")
        or outcome.get("resolution")
        or outcome.get("scene_text")
        or outcome.get("story")
        or outcome.get("description")
        or ""
    ).strip()

    if outcome.get("fallback_reason") == "empty_prose":
        desc = "⚠️ *The engine struggled to narrate the outcome. Showing placeholder.* ⚠️\n\n" + desc

    story_embed = discord.Embed(
        title=title,
        description=desc,
        color=color,
    )

    # Check summary — always shown
    _safe_add_field(story_embed, name=check_field_name, value=check_field_value, inline=False)

    breakdown_embed = discord.Embed(
        title="📊 Action Breakdown & Rewards",
        color=discord.Color.from_str("#2B2D31")
    )

    if result_display == "detailed":
        # ── Unified Combat Log & Vitals Block ──────────────────────────────
        combat_log = outcome.get("_combat_log") or []
        enemy_attack_notice = outcome.get("_enemy_attack_notice")
        char_outcomes = outcome.get("character_outcomes") or []
        npcs_present = outcome.get("npcs_present") or []

        summary_lines = []
        if combat_log:
            summary_lines.extend(combat_log)
        elif enemy_attack_notice:
            summary_lines.append(enemy_attack_notice)
        refr_toast = outcome.get("_refractory_recovered_notice")
        if refr_toast:
            summary_lines.append(refr_toast)

        vitals_lines = []
        for co in char_outcomes:
            if not isinstance(co, dict):
                continue
            name = str(co.get("name", "")).strip()
            if not name or name.startswith("_") or len(name) > 60:
                continue
            parts = []
            hp = _safe_int(co.get("hp_change"), default=0)
            mp = _safe_int(co.get("mp_change"), default=0)
            gold = _safe_int(co.get("gold_change"), default=0)
            status_new = [s for s in (co.get("status_effects") or []) if s]
            if hp:
                parts.append(f"{'❤️' if hp < 0 else '💚'} HP {hp:+d}")
            if mp:
                parts.append(f"{'💙' if mp < 0 else '✨'} MP {mp:+d}")
            if gold:
                parts.append(f"💰 Gold {gold:+d}")
            if status_new:
                parts.append(f"⚡ Status: {', '.join(status_new)}")
            xp_gained = (xp_by_user or {}).get(name, 0)
            if not xp_gained and xp_by_user and len(xp_by_user) == 1:
                first_k = next(iter(xp_by_user.keys()))
                if name.lower() == str(first_k).lower():
                    xp_gained = xp_by_user[first_k]
            if xp_gained:
                parts.append(f"⭐ XP +{xp_gained}")
            if parts:
                prefix = f"❤️ **{name}**: " if name else ""
                vitals_lines.append(prefix + " | ".join(parts))

        # Include friendly companions in combat vitals
        if combat_log and npcs_present:
            for npc in npcs_present:
                if isinstance(npc, dict) and npc.get("hp") is not None:
                    n_name = npc.get("name", "Companion")
                    n_hp = _safe_int(npc.get("hp"), default=0)
                    n_max = _safe_int(npc.get("max_hp"), default=n_hp)
                    vitals_lines.append(f"❤️ **{n_name}**: 💚 HP {n_hp}/{n_max}")

        if summary_lines or vitals_lines:
            header_title = "⚔️ Combat Summary" if (combat_log or enemy_attack_notice) else "📊 Turn Summary"
            full_block = []
            if summary_lines:
                full_block.extend(summary_lines)
            if vitals_lines:
                if summary_lines:
                    full_block.append("")  # Blank line separator
                full_block.extend(vitals_lines)
            _safe_add_field(breakdown_embed, name=header_title, value="\n".join(full_block), inline=False)

        # ── NPC Relationships, Factions & World Events ─────────────────────
        from namegen import is_valid_entity_name
        social_lines = []
        for rel in (outcome.get("relationship_updates") or []):
            if not isinstance(rel, dict):
                continue
            npc = rel.get("npc_name") or rel.get("name", "")
            if not is_valid_entity_name(npc):
                continue
            delta = int(rel.get("delta_score", 0))
            traits = rel.get("new_traits") or []
            prefs = rel.get("new_preferences") or []
            disc_items = []
            if traits:
                disc_items.extend(traits[:2])
            if prefs:
                disc_items.extend(prefs[:2])
            if rel.get("intimate_revealed"):
                disc_items.append("Intimate Profile")
                rev_attrs = rel.get("revealed_attributes") or []
                if isinstance(rev_attrs, str):
                    rev_attrs = [rev_attrs]
                rev_set = {str(a).lower().strip() for a in rev_attrs if a}
                if rel.get("sensitive_spots_revealed") or rel.get("new_sensitive_spots") or "sensitive_spots" in rev_set:
                    disc_items.append("Sensitive Spots")
                if rel.get("turn_ons_revealed") or rel.get("new_turn_ons") or "turn_ons" in rev_set:
                    disc_items.append("Turn-Ons")
                if rel.get("fetishes_revealed") or rel.get("new_fetishes") or "fetishes" in rev_set:
                    disc_items.append("Fetishes")
                if rel.get("demeanor_revealed") or rel.get("new_demeanor") or "demeanor" in rev_set or "intimate_demeanor" in rev_set:
                    disc_items.append("Intimate Demeanor")
                if rel.get("dynamic_revealed") or rel.get("new_dynamic") or "dynamic" in rev_set or "intimate_dynamic" in rev_set:
                    disc_items.append("Intimate Dynamic")
                if rel.get("intercourse_revealed") or "intercourse" in rev_set:
                    disc_items.append("Intercourse Experience")
                if rel.get("oral_revealed") or "oral" in rev_set:
                    disc_items.append("Oral Experience")
            if npc and (delta or disc_items):
                sign = "+" if delta > 0 else ""
                disc_str = f" [Discovered: {', '.join(disc_items[:3])}]" if disc_items else ""
                social_lines.append(f"🤝 {npc}: {sign}{delta}{disc_str}")
        for fac in (outcome.get("faction_updates") or []):
            if not isinstance(fac, dict):
                continue
            fname = fac.get("faction_name") or fac.get("name", "")
            if not is_valid_entity_name(fname):
                continue
            fdelta = int(fac.get("delta_score", 0))
            if fname and fdelta:
                from cogs.factions import get_faction_emoji
                f_emoji = get_faction_emoji(fname)
                sign = "+" if fdelta > 0 else ""
                social_lines.append(f"{f_emoji} {fname}: {sign}{fdelta} Rep")
        for ev in (outcome.get("world_event_updates") or []):
            if not isinstance(ev, dict):
                continue
            etitle = ev.get("title", "")
            estage = ev.get("stage", "")
            if etitle:
                stage_str = f" → {estage.capitalize()}" if estage else ""
                social_lines.append(f"🌍 {etitle}{stage_str}")
        for pill_txt in (outcome.get("social_feedback_pills") or []):
            if isinstance(pill_txt, dict):
                p_clean = str(pill_txt.get("label") or "").strip()
                if not p_clean and pill_txt.get("key"):
                    from mechanics.social import locales as _pill_loc
                    p_clean = _pill_loc.format_feedback_pill(str(pill_txt["key"]), detail=str(pill_txt.get("detail") or ""))
            else:
                p_clean = str(pill_txt or "").strip()
            if p_clean:
                social_lines.append(f"💬 *{p_clean}*")
        if social_lines:
            _safe_add_field(breakdown_embed, name="🤝 Social & Faction Updates",
                             value="\n".join(social_lines), inline=False)

        # ── Newly Discovered Factions ─────────────────────────────────
        new_facs = outcome.get("_newly_discovered_factions") or []
        for nf in new_facs:
            if isinstance(nf, dict):
                nf_name = nf.get("name", "")
                nf_hq = nf.get("hq", "")
                from cogs.factions import get_faction_emoji
                emoji = get_faction_emoji(nf_name, template=nf.get("template", ""))
                hq_part = f" | 📍 HQ: **{nf_hq}**" if nf_hq else ""
                _safe_add_field(breakdown_embed, name="✨ Faction Discovered",
                                value=f"{emoji} **{nf_name}**{hq_part}", inline=False)

        # ── Story Clue Discoveries ──────────────────────────────────────
        new_clue = outcome.get("_newly_discovered_clue")
        if new_clue:
            _safe_add_field(breakdown_embed, name="🔍 Story Discovery",
                             value=f"🔍 **New Investigation Note:** *{new_clue}*", inline=False)
    else:
        # Compact mode fallback for combat summary
        combat_log = outcome.get("_combat_log") or []
        enemy_attack_notice = outcome.get("_enemy_attack_notice")
        if combat_log:
            _safe_add_field(breakdown_embed, name="⚔️ Combat Summary", value="\n".join(combat_log), inline=False)
        elif enemy_attack_notice:
            _safe_add_field(breakdown_embed, name="⚔️ Combat Summary", value=enemy_attack_notice, inline=False)
        refr_toast = outcome.get("_refractory_recovered_notice")
        if refr_toast:
            _safe_add_field(breakdown_embed, name="⚡ Stamina Recovered", value=refr_toast, inline=False)

    # ── Intimate Excitement Progress ───────────────────────────────────────
    intimate_up = outcome.get("intimate_update")
    if intimate_up and isinstance(intimate_up, dict) and intimate_up.get("active"):
        from mechanics.social.intimate_excitement import format_compact_discord_meter
        lead_name = "Player"
        if outcome.get("character_outcomes"):
            lead_name = outcome["character_outcomes"][0].get("name", "Player")
        elif xp_by_user:
            lead_name = next(iter(xp_by_user.keys()), "Player")
        partner_name = intimate_up.get("partner_name") or outcome.get("dialogue_partner")
        if not partner_name and outcome.get("dialogue_partners"):
            _dps = outcome.get("dialogue_partners")
            if isinstance(_dps, list) and _dps:
                partner_name = str(_dps[0])
            elif isinstance(_dps, str):
                try:
                    _parsed = json.loads(_dps)
                    partner_name = str(_parsed[0]) if isinstance(_parsed, list) and _parsed else _dps
                except Exception:
                    partner_name = _dps
        lead_name = str(lead_name or "Player")
        partner_name = str(partner_name or "Partner")
        p_val = intimate_up.get("player_meter", 0)
        n_val = intimate_up.get("partner_meter", 0)
        n_climax = intimate_up.get("partner_climaxed", False)
        discord_meter_line = format_compact_discord_meter(
            player_name=lead_name,
            player_meter=p_val,
            partner_name=partner_name,
            partner_meter=n_val,
            partner_climaxed=n_climax,
            actors=intimate_up.get("actors"),
            partner_meters=intimate_up.get("partner_meters"),
        )
        field_val = discord_meter_line
        if intimate_up.get("mutual_group_climax"):
            field_val += "\n✨ **Mutual Group Climax!** Shared peak in passionate release."
        elif intimate_up.get("simultaneous_partner_climax"):
            field_val += "\n✨ **Simultaneous Climax!** Multiple partners peak together."
        if intimate_up.get("sensitive_spot_matched") and intimate_up.get("matched_spot"):
            field_val += f"\n✨ **Sensitive Spot:** {intimate_up['matched_spot']} (+6% bonus)"
        if intimate_up.get("premature_finish"):
            unsat_list = intimate_up.get("unsatisfied_partners") or []
            if len(unsat_list) >= 2:
                field_val += f"\n⚠️ **Spent:** Stamina depleted while {', '.join(unsat_list[:-1])} and {unsat_list[-1]} remain unsatisfied."
            elif intimate_up.get("unsatisfied_partner"):
                field_val += f"\n⚠️ **Spent:** Stamina depleted while {intimate_up['unsatisfied_partner']} remains unsatisfied."
            else:
                field_val += "\n⚠️ **Spent:** Stamina depleted while partner remains unsatisfied."
        _safe_add_field(breakdown_embed, name="💋 Intimate Excitement", value=field_val, inline=False)

    # ── Combat Resolution — victory / defeat notices ───────────────────────
    combat_notice = outcome.get("_combat_resolved_notice")
    if combat_notice:
        _safe_add_field(breakdown_embed, name="⚔️ Combat Resolved", value=str(combat_notice).replace("\\n", "\n"), inline=False)

    defeat_notice = outcome.get("_party_defeated_notice")
    if defeat_notice:
        _safe_add_field(breakdown_embed, name="💀 Party Defeated", value=str(defeat_notice).replace("\\n", "\n"), inline=False)

    # ── Loot — always shown ────────────────────────────────────────────────
    if loot_text:
        _safe_add_field(breakdown_embed, name="🎒 Loot", value=loot_text, inline=False)

    # ── Quest completion notice(s) — shown for every completed quest ──────────
    rn_list = outcome.get("_quest_reward_notices") or []
    for rn in rn_list:
        if not rn or not rn.get("claimed"):
            continue
        reward_parts = []
        if rn.get("xp"):
            reward_parts.append(f"+{rn['xp']} XP")
        if rn.get("gold"):
            reward_parts.append(f"+{rn['gold']} Gold")
        rew_str = ", ".join(reward_parts) or "Claimed"
        _safe_add_field(
            breakdown_embed,
            name=f"🎉 Quest Completed: {rn.get('title')}",
            value=f"**Rewards:** {rew_str}",
            inline=False,
        )

    # ── Sub-Quest completion notice(s) ────────────────────────────────────────
    completed_sqs = outcome.get("_completed_sub_quests") or []
    for sq_info in completed_sqs:
        arch = f" [{sq_info['archetype']}]" if sq_info.get("archetype") else ""
        _safe_add_field(
            breakdown_embed,
            name="☑️ Sub-Quest Completed",
            value=f"{arch} **{sq_info.get('text', '')}**",
            inline=False
        )

    # ── Waypoint Progression notice(s) ────────────────────────────────────────
    wp_notices = outcome.get("_waypoint_notices") or []
    for wp in wp_notices:
        trigger = wp.get("trigger")
        if trigger == "arrival":
            icon = "📌"
            action = "Reached Destination"
        elif trigger == "skill_check":
            icon = "🎯"
            action = "Objective Completed"
        elif trigger == "resource_progress":
            icon = "📦"
            action = "Resources Gathered"
        else:
            icon = "▶️"
            action = "Stage Progress"

        stage_completed = wp.get("stage_completed")
        stage_label = wp.get("stage_label", "")
        next_wp = wp.get("next_waypoint")
        quest_complete = wp.get("all_stages_complete")

        lines = []
        if stage_completed is not None:
            lines.append(f"**{action}:** {stage_label}")
        if trigger == "resource_progress" or (trigger == "skill_check" and wp.get("resource_target")):
            lines.append(f"**Progress:** {wp.get('resource_collected', 0)} / {wp.get('resource_target', 0)}")

        if not quest_complete and next_wp:
            lines.append(f"**Next:** {next_wp.get('stage_label', 'Continue quest')}")
        elif quest_complete:
            lines.append("**Status:** Waypoint chain completed!")

        qid = wp.get("quest_id")
        quest_label = ""
        if qid and session_id:
            try:
                q = db.get_quest_by_id(session_id, qid)
                if q:
                    if q.get("is_story_quest"):
                        quest_label = "Story Quest"
                    else:
                        quest_label = q.get("title", "Bounty")[:30]
            except Exception:
                pass

        header_title = f"{icon} {quest_label} Waypoint" if quest_label else f"{icon} Waypoint Updated"
        _safe_add_field(
            breakdown_embed,
            name=header_title,
            value="\n".join(lines),
            inline=False
        )

    if len(breakdown_embed.fields) > 0:
        return [story_embed, breakdown_embed]

    return [story_embed]


def prepare_discord_image(image_val) -> tuple[str | None, discord.File | None]:
    """
    Resolves an image value to (embed_url, discord_file).
    Supports GeneratedImage, local /images/ paths, local filesystem paths, or remote URLs.
    """
    if not image_val:
        return None, None

    local_path = getattr(image_val, "local_path", None)
    remote_url = getattr(image_val, "remote_url", None)
    filename = getattr(image_val, "filename", None)

    if not local_path and isinstance(image_val, str):
        val_str = image_val.strip()
        if val_str.startswith("/images/") or (not val_str.startswith("http://") and not val_str.startswith("https://")):
            from config import GENERATED_IMAGES_DIR
            base_name = os.path.basename(val_str)
            candidate = os.path.join(GENERATED_IMAGES_DIR, base_name)
            if os.path.exists(candidate):
                local_path = candidate
                filename = base_name

    if local_path and os.path.exists(local_path):
        fname = filename or os.path.basename(local_path)
        try:
            dfile = discord.File(local_path, filename=fname)
            return f"attachment://{fname}", dfile
        except Exception as e:
            logger.warning("Failed to create discord.File from %s: %s", local_path, e)

    if remote_url and (remote_url.startswith("http://") or remote_url.startswith("https://")):
        return remote_url, None
    if isinstance(image_val, str) and (image_val.startswith("http://") or image_val.startswith("https://")):
        return image_val, None

    return None, None


def _format_epistemic_watch_text(session: dict) -> str:
    """Format strictly Fog-of-War-safe player_aware==1 epistemic status for Discord embeds."""
    ep_hud = session.get("epistemic_hud")
    if not isinstance(ep_hud, dict) and session.get("id"):
        try:
            ep_hud = db.build_player_fog_of_war_summary(int(session["id"]))
        except Exception:
            ep_hud = {}
    if not isinstance(ep_hud, dict) or not ep_hud:
        return ""
    leak_risk = str(ep_hud.get("leak_risk") or "none").lower()
    spotted = list(ep_hud.get("spotted_witnesses") or [])
    known_w = list(ep_hud.get("known_witnesses") or [])
    alibis = list(ep_hud.get("active_alibis") or [])
    secrets = list(ep_hud.get("held_npc_secrets") or [])
    if leak_risk == "none" and not spotted and not known_w and not alibis and not secrets:
        return ""
    lines = []
    if leak_risk != "none":
        risk_icon = {"critical": "🔴", "high": "🔴", "moderate": "🟠", "medium": "🟠", "low": "🟡"}.get(leak_risk, "🟡")
        lines.append(f"{risk_icon} **Leak Risk:** `{leak_risk.upper()}`")
    if spotted:
        names = ", ".join(
            str(w.get("holder_actor_key") or w.get("subject_actor_key") or "Someone").replace("_", " ").title()
            for w in spotted[:4]
            if isinstance(w, dict)
        )
        if names:
            lines.append(f"👀 **Spotted:** {names}")
    if known_w:
        lines.append(f"👤 **Known Witnesses:** {len(known_w)}")
    if alibis:
        lines.append(f"🎭 **Alibis Active:** {len(alibis)}")
    if secrets:
        lines.append(f"🗝️ **Secrets Held:** {len(secrets)}")
    return "\n".join(lines)[:1024]


def _crowd_density_badge(session: dict) -> str:
    cs = session.get("crowd_state") if isinstance(session, dict) else None
    if not isinstance(cs, dict):
        return ""
    dens = str(cs.get("density") or "").strip().lower()
    if not dens or dens in ("empty", "none"):
        return ""
    lang = str(session.get("language") or "en").strip().lower()
    try:
        from localization import LOCALES
        mod = LOCALES.get(lang, LOCALES["en"])
        lbl = (getattr(mod, "CROWD_DENSITY_LABELS", None) or {}).get(dens)
    except Exception:
        lbl = None
    return f" • {lbl or dens.title()}"


def _append_dialogue_mood_field(
    dash_embed: discord.Embed,
    session: dict,
    dialogue_partners: list,
    enemies: list,
    c_day: int | str,
    c_min: int | str,
) -> None:
    """Appends qualitative Dialogue Mood when conversing outside combat and erotic scenes."""
    from mechanics.social.physical_state import is_session_in_erotic_dialogue

    mood_info = session.get("active_dialogue_mood")
    if not mood_info and dialogue_partners and session.get("id") and not enemies and not is_session_in_erotic_dialogue(session):
        try:
            from mechanics.social import locales as _emb_loc
            from mechanics.social import pacing as _emb_pac
            _dp0 = str(dialogue_partners[0]).strip()
            if _dp0:
                _comp_e = _emb_pac.sync_and_get_composure(int(session["id"]), _dp0, current_day=int(c_day), current_minute=int(c_min))
                _mk, _ = _emb_pac.derive_mood_and_dc_mod(
                    int(_comp_e.get("current_composure", 100)),
                    int(_comp_e.get("max_composure", 100)),
                    str(_comp_e.get("composure_state") or "composed"),
                    clear_the_air_required=bool(int(_comp_e.get("clear_the_air_required") or 0) == 1),
                )
                mood_info = {"npc_name": _dp0, "mood_key": _mk, "mood_label": _emb_loc.get_mood_label(_mk, lang=str(session.get("language") or "en"))}
        except Exception:
            mood_info = None
    if isinstance(mood_info, dict) and mood_info.get("mood_label"):
        _m_emoji = {"Engaged": "🟢", "Guarded": "🟡", "Drained": "⚪", "Upset": "🔴"}.get(str(mood_info.get("mood_key") or ""), "💬")
        _m_who = f"**{mood_info['npc_name']}**: " if mood_info.get("npc_name") else ""
        _safe_add_field(dash_embed, name="💬 Dialogue Mood", value=f"{_m_emoji} {_m_who}`{mood_info['mood_label']}`", inline=False)


def _append_conversation_pause_field(dash_embed: discord.Embed, choices: list, enemies: list) -> None:
    """Explains a trimmed dialogue menu when the partner's daily small-talk budget is exhausted."""
    if enemies or not isinstance(choices, list):
        return
    paused = next((c for c in choices if isinstance(c, dict) and c.get("_conversation_paused")), None)
    if paused and paused.get("pause_notice"):
        _safe_add_field(dash_embed, name="⏸️ Conversation Paused", value=str(paused["pause_notice"]), inline=False)


def scene_embed(session: dict, actor_char: dict, scene_title: str, narrative: str,
                 choices: list, image_url: str | None = None) -> list[discord.Embed]:
    story_embed = discord.Embed(title=_truncate_field_name(scene_title or "Hikayat", 256), description=_truncate_embed_text(narrative),
                           color=discord.Color.dark_gold())
    if image_url:
        embed_url, _ = prepare_discord_image(image_url)
        if embed_url:
            story_embed.set_image(url=embed_url)

    dash_embed = discord.Embed(title="⚙️ Game Dashboard", color=discord.Color.gold())
    _safe_add_field(dash_embed, name="📍 Location", value=_location_text(session, char_name=actor_char.get("name", "")), inline=False)

    from mechanics.system.time_engine import format_time_header
    c_day = session.get("current_day") or 1
    c_min = session.get("current_minute") if session.get("current_minute") is not None else 480
    _safe_add_field(dash_embed, name="📅 Time & Day", value=format_time_header(c_day, c_min), inline=False)

    enemies = session.get("nearby_enemies", [])
    enemy_names = {game_engine._get_npc_name(e).lower() for e in enemies if e}

    raw_npcs = session.get("current_npcs") or []
    party_char_names = set()
    if actor_char and actor_char.get("name"):
        party_char_names.add(str(actor_char["name"]).strip().lower())
    if session.get("turn_order"):
        for uid in session["turn_order"]:
            try:
                with db.get_conn() as conn:
                    c_rows = conn.execute("SELECT name FROM characters WHERE user_id = ?", (uid,)).fetchall()
                    for cr in c_rows:
                        if cr["name"]:
                            party_char_names.add(str(cr["name"]).strip().lower())
            except Exception:
                pass

    npcs = [
        n for n in raw_npcs
        if game_engine._get_npc_name(n).lower() not in enemy_names
        and game_engine._get_npc_name(n).lower() not in party_char_names
    ]
    scen_key = session.get("scenario", "fantasy")
    from scenario_data import is_mechanic_enabled
    combat_enabled = is_mechanic_enabled(scen_key, "tactical_combat")

    if npcs:
        from mechanics.world.mobility import get_session_dialogue_partners
        dialogue_partners = get_session_dialogue_partners(session)
        _safe_add_field(dash_embed, name=_tracker_header("🧑‍🤝‍🧑", "Character", "Characters", len(npcs)) + _crowd_density_badge(session),
                         value=_tracker_group_text(npcs, dialogue_partners=dialogue_partners, show_vitals=combat_enabled), inline=False)
        _append_dialogue_mood_field(dash_embed, session, dialogue_partners, enemies, c_day, c_min)
        _append_conversation_pause_field(dash_embed, choices, enemies)

    if enemies:
        _safe_add_field(
            dash_embed,
            name=_tracker_header("👹", "Enemy", "Enemies", len(enemies)),
            value=_tracker_group_text(
                enemies,
                show_vitals=combat_enabled,
                show_enemy_hp=bool(session.get("show_enemy_hp", 1)),
                show_enemy_intent=bool(session.get("show_enemy_intent", 1)),
            ),
            inline=False,
        )

    if combat_enabled:
        vitals_header = _tracker_header("📊", "Party", "Party", 1)
    else:
        vitals_header = _tracker_header("📊", "Player", "Players", len(session.get("turn_order", [])))
    _safe_add_field(dash_embed, name=vitals_header,
                     value=_party_vitals_text(session), inline=False)

    ep_watch = _format_epistemic_watch_text(session)
    if ep_watch:
        _safe_add_field(dash_embed, name="🕵️ Epistemic Watch", value=ep_watch, inline=False)

    return [story_embed, dash_embed]


def sync_scene_embed(session: dict, party: list, scene_title: str, narrative: str,
                      choices: list, waiting_on: list, image_url: str | None = None) -> list[discord.Embed]:
    story_embed = discord.Embed(title=_truncate_field_name(scene_title or "Hikayat", 256), description=_truncate_embed_text(narrative),
                           color=discord.Color.dark_teal())
    if image_url:
        embed_url, _ = prepare_discord_image(image_url)
        if embed_url:
            story_embed.set_image(url=embed_url)

    first_p = party[0][0] if (party and isinstance(party[0], (tuple, list)) and party[0]) else (party[0] if party else None)
    first_char_name = first_p.get("name", "") if isinstance(first_p, dict) else ""
    dash_embed = discord.Embed(title="⚙️ Game Dashboard", color=discord.Color.teal())
    _safe_add_field(dash_embed, name="📍 Location", value=_location_text(session, char_name=first_char_name), inline=False)
    c_day = session.get("current_day") or 1
    c_min = session.get("current_minute") if session.get("current_minute") is not None else 480

    enemies = session.get("nearby_enemies", [])
    enemy_names = {game_engine._get_npc_name(e).lower() for e in enemies if e}

    party_char_names = set()
    if party:
        for p in party:
            p_char = p[0] if (isinstance(p, (tuple, list)) and p) else p
            if isinstance(p_char, dict) and p_char.get("name"):
                party_char_names.add(str(p_char["name"]).strip().lower())
    if session.get("turn_order"):
        for uid in session["turn_order"]:
            try:
                with db.get_conn() as conn:
                    c_rows = conn.execute("SELECT name FROM characters WHERE user_id = ?", (uid,)).fetchall()
                    for cr in c_rows:
                        if cr["name"]:
                            party_char_names.add(str(cr["name"]).strip().lower())
            except Exception:
                pass

    raw_npcs = session.get("current_npcs") or []
    npcs = [
        n for n in raw_npcs
        if game_engine._get_npc_name(n).lower() not in enemy_names
        and game_engine._get_npc_name(n).lower() not in party_char_names
    ]
    scen_key = session.get("scenario", "fantasy")
    from scenario_data import is_mechanic_enabled
    combat_enabled = is_mechanic_enabled(scen_key, "tactical_combat")

    if npcs:
        from mechanics.world.mobility import get_session_dialogue_partners
        dialogue_partners = get_session_dialogue_partners(session)
        _safe_add_field(dash_embed, name=_tracker_header("🧑‍🤝‍🧑", "Character", "Characters", len(npcs)) + _crowd_density_badge(session),
                         value=_tracker_group_text(npcs, dialogue_partners=dialogue_partners, show_vitals=combat_enabled), inline=False)
        _append_dialogue_mood_field(dash_embed, session, dialogue_partners, enemies, c_day, c_min)
        _append_conversation_pause_field(dash_embed, choices, enemies)

    if enemies:
        _safe_add_field(
            dash_embed,
            name=_tracker_header("👹", "Enemy", "Enemies", len(enemies)),
            value=_tracker_group_text(
                enemies,
                show_vitals=combat_enabled,
                show_enemy_hp=bool(session.get("show_enemy_hp", 1)),
                show_enemy_intent=bool(session.get("show_enemy_intent", 1)),
            ),
            inline=False,
        )

    if combat_enabled:
        vitals_header = _tracker_header("📊", "Party", "Party", 1)
    else:
        vitals_header = _tracker_header("📊", "Player", "Players", len(session.get("turn_order", [])))
    _safe_add_field(dash_embed, name=vitals_header,
                     value=_party_vitals_text(session), inline=False)

    ep_watch = _format_epistemic_watch_text(session)
    if ep_watch:
        _safe_add_field(dash_embed, name="🕵️ Epistemic Watch", value=ep_watch, inline=False)

    if waiting_on:
        mentions = ", ".join(f"<@{uid}>" for uid in waiting_on)
        _safe_add_field(dash_embed, name="⏳ Waiting on", value=mentions, inline=False)

    return [story_embed, dash_embed]


def build_world_map_embed(session_id: int, scen_key: str, current_loc: str = "", char_name: str = "", zones: list = None) -> discord.Embed:
    """Builds the rich World Map Atlas embed summarizing all discovered Tier 1 Zones."""
    if zones is None:
        from mechanics.world.locations import get_zone_summary_tree
        zones = get_zone_summary_tree(session_id, scen_key, current_loc=current_loc, char_name=char_name)
    embed = discord.Embed(
        title="🗺️ World Map — Discovered Regions",
        description="Select a region from the dropdown below to explore its local places or travel across districts:",
        color=discord.Color.gold()
    )
    for z in zones[:25]:
        z_name = z["zone_name"]
        z_emoji = z.get("emoji", "📍")
        eta_tag = z.get("travel_tag") or ""
        curr_badge = " `[Current Region]`" if z.get("is_current") else (f" `[⏱️ {eta_tag}]`" if eta_tag else "")
        header = f"{'🧭 ' if z.get('is_current') else z_emoji + ' '}{z_name}{curr_badge}"
        lines = []
        theme_tag = z.get("theme")
        if theme_tag:
            lines.append(f"• **Type:** {theme_tag}")
        lines.append(f"• **Known Places:** {z.get('places_count', 0)} discovered")
        if z.get("active_tags"):
            lines.append(f"• **Highlights:** {' | '.join(z['active_tags'])}")
        _safe_add_field(embed, name=header, value="\n".join(lines) if lines else "—", inline=False)
    return embed


def build_zone_places_embed(session_id: int, zone_name: str, scen_key: str, current_loc: str = "", char_name: str = "") -> discord.Embed:
    """Builds the regional places embed showing places within a selected zone."""
    from mechanics.world.locations import get_zone_emoji, get_zone_summary_tree
    zones = get_zone_summary_tree(session_id, scen_key, current_loc=current_loc, char_name=char_name)
    target_zone = next((z for z in zones if z["zone_name"].lower() == zone_name.lower()), None)
    z_emoji = target_zone.get("emoji", get_zone_emoji(zone_name, scen_key)) if target_zone else get_zone_emoji(zone_name, scen_key)
    z_eta = f" `[⏱️ {target_zone['travel_tag']}]`" if (target_zone and not target_zone.get("is_current") and target_zone.get("travel_tag")) else ""

    embed = discord.Embed(
        title=f"{z_emoji} Region: {zone_name}{z_eta}",
        color=discord.Color.gold()
    )
    if target_zone and target_zone.get("theme"):
        embed.description = f"**{target_zone['theme']}**\n\nSelect a destination within this region:"
    else:
        embed.description = "Select a destination within this region:"

    if target_zone and target_zone.get("active_tags"):
        _safe_add_field(embed, name="🏷️ Regional Highlights", value=" | ".join(target_zone["active_tags"]), inline=False)

    if target_zone:
        places = target_zone.get("primary_locations", [])
        if places:
            place_lines = []
            for p in places[:15]:
                arch_emoji = p.get("archetype_emoji") or p.get("emoji") or "📍"
                badges = p.get("badges", "")
                badge_str = f" {badges}" if badges else ""
                eta_tag = p.get("travel_tag") or ""
                eta_str = f" `[⏱️ {eta_tag}]`" if eta_tag else ""

                # Access and curfew indicators
                access_badge = p.get("access_badge")
                access_str = ""
                if access_badge:
                    if str(access_badge).startswith("For Sale"):
                        access_str = f" `🏷️ {access_badge}`"
                    elif access_badge in ("Owned Residence", "Starter Quarters"):
                        access_str = f" `🏠 {access_badge}`"
                    elif p.get("is_unlocked"):
                        access_str = " `🔓 Unlocked`"
                    elif p.get("is_curfew_active") or p.get("schedule_locked") or "Closed" in access_badge or "Locked" in access_badge or access_badge in ("Restricted", "Private"):
                        access_str = f" `🔒 {access_badge}`"
                    elif access_badge != "Open":
                        access_str = f" `[{access_badge}]`"

                line = f"• {arch_emoji} **{p['name']}**{badge_str}{eta_str}{access_str}"
                anom_meta = p.get("anomalous_site_meta") if isinstance(p.get("anomalous_site_meta"), dict) else None
                if anom_meta and anom_meta.get("badge"):
                    line += f" `{anom_meta['badge']}`"
                for sub_d in (p.get("sub_location_details") or []):
                    sub_m = sub_d.get("anomalous_site_meta") if isinstance(sub_d, dict) else None
                    if isinstance(sub_m, dict) and sub_m.get("badge"):
                        line += f"\n  ↳ 🧭 {sub_d.get('name', 'Wing')}: `{sub_m['badge']}`"

                # Live Occupancy (Known contacts, rendezvous partners, unmet roster students)
                occ_parts = []
                for kn in (p.get("known_npcs_here") or []):
                    kn_name = kn.get("name") if isinstance(kn, dict) else kn
                    if kn_name:
                        occ_parts.append(f"👤 {kn_name}")
                unmet = p.get("unmet_activity_count", 0)
                if unmet > 0:
                    occ_parts.append(f"👥 +{unmet} nearby")

                if occ_parts:
                    line += f"\n  ↳ {' | '.join(occ_parts)}"

                # Scene Memory Residue
                res = p.get("scene_residue")
                if res:
                    line += f"\n  *💭 \"{res[:65]}\"*"

                place_lines.append(line)
            _safe_add_field(embed, name="📍 Discovered Locations", value="\n".join(place_lines), inline=False)
    return embed


def build_facility_rooms_embed(zone_name: str, primary_item: dict) -> discord.Embed:
    """Builds a Tier-3 Room/Wing selector embed for a multi-room Building, Deck, or Complex."""
    p_name = primary_item.get("name", "Facility")
    p_emoji = primary_item.get("archetype_emoji") or primary_item.get("emoji") or "🏛️"
    eta_tag = primary_item.get("travel_tag") or ""
    eta_hdr = f" `[⏱️ {eta_tag}]`" if eta_tag else ""

    embed = discord.Embed(
        title=f"{p_emoji} {p_name}{eta_hdr}",
        description=f"📍 **Region:** `{zone_name}`\nSelect a specific room or wing below, or click **Enter Main Entrance**.",
        color=discord.Color.gold()
    )

    room_details = primary_item.get("sub_location_details") or []
    raw_subs = primary_item.get("sub_locations") or []
    room_lines = []
    if room_details:
        for rd in room_details[:15]:
            r_name = rd.get("name", "")
            if not r_name:
                continue
            r_eta = rd.get("travel_tag") or ""
            r_badge = rd.get("access_badge") or "Open"
            r_locked = (not rd.get("is_unlocked")) and (
                "Closed" in r_badge or "Locked" in r_badge or r_badge in ("Restricted", "Private")
            )
            icon = "📍" if rd.get("is_current_room") else ("🔒" if r_locked else "🚪")
            lock_str = f" `🔒 {r_badge}`" if r_locked else (" `🔓 Unlocked`" if rd.get("is_unlocked") and r_badge != "Open" else "")
            eta_str = f" `[⏱️ {r_eta}]`" if r_eta else ""
            props = rd.get("props") or []
            prop_str = f"\n  ↳ *In-Room Features: {', '.join(props[:4])}*" if props else ""
            room_lines.append(f"• {icon} **{r_name}**{eta_str}{lock_str}{prop_str}")
    else:
        for s_name in raw_subs[:15]:
            if s_name:
                room_lines.append(f"• 🚪 **{s_name}**")

    if room_lines:
        _safe_add_field(embed, name="🚪 Rooms & Wings", value="\n".join(room_lines), inline=False)
    return embed
