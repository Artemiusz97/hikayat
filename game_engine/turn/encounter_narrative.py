from __future__ import annotations

import re
import game_engine

def _get_enemy_base_name(name: str) -> str:
    return re.sub(r'\s+(?:#?\d+|[A-Z])$', '', str(name or "").strip())


_INCURSION_SUBDUE_PHRASES = (
    "subdue & contain",
    "obezwładnij i zabezpiecz", "obezwładnij anomalię",
    "tumpaskan & kurung", "tundukkan & kurung",
    "制服并收容", "压制并收容",
    "überwältigen & eindämmen", "überwältigen und eindämmen",
)
_INCURSION_COMBAT_PERSUADE_PHRASES = (
    "persuade / calm", "(de-escalate)",
    "przekonaj / uspokój", "(deeskalacja)",
    "pujuk / tenangkan", "(redakan)",
    "劝说 / 安抚", "劝说/安抚", "（缓和局势）",
    "überreden / beruhigen", "(deeskalieren)",
)
_INCURSION_PACIFY_PREFIXES = (
    "🕊️ pacify & contain", "pacify & contain",
    "🕊️ uspokój i zabezpiecz", "uspokój i zabezpiecz",
    "🕊️ tenangkan & kurung", "tenangkan & kurung",
    "🕊️ 安抚并收容", "安抚并收容",
    "🕊️ besänftigen & eindämmen", "besänftigen & eindämmen",
)
_INCURSION_ANALYZE_PREFIXES = (
    "🔬 analyze & seal", "analyze & seal",
    "🔬 przeanalizuj i zapieczętuj", "przeanalizuj i zapieczętuj",
    "🔬 analisis & meterai", "analisis & meterai",
    "🔬 分析并封印", "分析并封印",
    "🔬 analysieren & versiegeln", "analysieren & versiegeln",
)
_INCURSION_SCAN_PREFIXES = (
    "🔍 scan anomaly dossier", "scan anomaly dossier",
    "🔍 przeskanuj akta anomalii", "przeskanuj akta anomalii",
    "🔍 imbas fail anomali", "imbas fail anomali",
    "🔍 扫描异常档案", "扫描异常档案",
    "🔍 anomalie-akte scannen", "anomalie-akte scannen",
)
_INCURSION_SEAL_ABILITY_PREFIXES = (
    "✨ use sealing ability", "use sealing ability",
    "✨ użyj zdolności pieczętującej", "użyj zdolności pieczętującej",
    "✨ guna kebolehan pemeterai", "guna kebolehan pemeterai",
    "✨ 使用封印技能", "使用封印技能",
    "✨ versiegelungsfähigkeit nutzen", "versiegelungsfähigkeit nutzen",
)
_INCURSION_ATTACK_PREFIXES = (
    "⚔️ engage anomaly breach", "⚔️ engage anomalous breach", "engage anomaly breach",
    "⚔️ zaatakuj wyłom anomalii", "zaatakuj wyłom anomalii",
    "⚔️ gempur rekahan anomali", "gempur rekahan anomali",
    "⚔️ 迎击异常裂隙", "迎击异常裂隙",
    "⚔️ anomalie-riss angreifen", "anomalie-riss angreifen",
)
_INCURSION_TETHER_PHRASES = (
    "sever/seal", "przetnij/zapieczętuj", "putuskan/meterai", "斩断/封印", "trennen/versiegeln",
)
_INCURSION_RITE_PHRASES = (
    "folklore counter-rite", "kontrrytuał folkloru", "upacara balas folklor", "民俗反制仪轨", "folklore-gegenritus",
)
_INCURSION_INQUIRY_PREFIXES = (
    "💬 converse with", "💬 [origins", "🔍 [nature", "🧭 [motive",
    "👁️ study ", "👁️ [vocal", "🔍 [trigger", "🕯️ [courtesy",
    "💬 [riddle trap]", "🧠 [folklore evasion]",
    "💬 porozmawiaj z", "💬 berbual dengan", "💬 与", "💬 mit ",
    "👁️ zbadaj ", "👁️ teliti ", "👁️ 观察", "👁️ untersuche ",
)


def _infer_incursion_action_from_label(
    inc_lbl_low: str,
    *,
    is_inc_tagged: bool = False,
    has_subdue_enemy_now: bool = False,
    first_inc_act: dict | None = None,
) -> str:
    """Infers canonical incursion_action key across all 5 locales (en, pl, ms, zh, de) when unstamped."""
    lbl = str(inc_lbl_low or "").strip().lower()
    act = first_inc_act if isinstance(first_inc_act, dict) else {}
    if not lbl and not act:
        return ""

    if lbl.startswith("🛡️") and any(p in lbl for p in _INCURSION_SUBDUE_PHRASES):
        return "subdue"
    if any(p in lbl for p in _INCURSION_SUBDUE_PHRASES):
        return "subdue"
    if lbl.startswith("👑") or "invoke patron authority" in lbl:
        return "invoke_patron_authority"
    if lbl.startswith("🩸") and ("accept entity covenant" in lbl or "forfeit bounty" in lbl):
        return "accept_boss_pact_surrender"
    if lbl.startswith("🗣️") and any(p in lbl for p in _INCURSION_COMBAT_PERSUADE_PHRASES):
        return "combat_persuade"
    if has_subdue_enemy_now and any(p in lbl for p in _INCURSION_COMBAT_PERSUADE_PHRASES):
        return "combat_persuade"

    if is_inc_tagged:
        if any(tag in lbl for tag in ("[persuade]", "[przekonaj]", "[pujuk]", "[劝说]", "[überreden]")):
            return "persuade"
        if any(tag in lbl for tag in ("[calm]", "[uspokój]", "[tenangkan]", "[安抚]", "[beruhigen]")):
            return "calm"
        if any(tag in lbl for tag in ("[outwit]", "[przechytrz]", "[perdaya]", "[智取]", "[überlisten]")):
            return "outwit"
        if any(tag in lbl for tag in ("[use environment]", "[użyj otoczenia]", "[guna persekitaran]", "[利用环境]", "[umgebung nutzen]")):
            return "environment"

    if lbl.startswith(_INCURSION_PACIFY_PREFIXES):
        return "pacify"
    if lbl.startswith(_INCURSION_ANALYZE_PREFIXES):
        return "analyze"
    if lbl.startswith(_INCURSION_SCAN_PREFIXES):
        return "reveal_dossier"
    if lbl.startswith(_INCURSION_SEAL_ABILITY_PREFIXES):
        return "seal_ability"
    if lbl.startswith(_INCURSION_ATTACK_PREFIXES):
        return "attack"
    if lbl.startswith("🏺") or any(p in lbl for p in _INCURSION_TETHER_PHRASES):
        return "sever_tether"
    if (is_inc_tagged or has_subdue_enemy_now) and any(p in lbl for p in _INCURSION_RITE_PHRASES):
        return "folklore_offering_rite"
    if (
        act.get("is_anomaly_inquiry")
        or str(act.get("approach") or "").startswith(("anomaly_inquiry", "anomaly_pattern", "question_trap"))
        or lbl.startswith(_INCURSION_INQUIRY_PREFIXES)
    ):
        return str(act.get("incursion_action") or act.get("approach") or "anomaly_inquiry")
    return ""


def _is_enemy_mentioned_in_narrative(enemy_name: str, narrative_text: str) -> bool:
    base = _get_enemy_base_name(enemy_name)
    if not base:
        return True
    nar_low = str(narrative_text or "").lower()
    base_low = base.lower()
    if base_low in nar_low:
        return True
    tokens = [w for w in re.split(r'[\s\-]+', base_low) if len(w) >= 4]
    if tokens:
        head_noun = tokens[-1]
        if re.search(rf'\b{re.escape(head_noun)}s?\b', nar_low):
            return True
    return False


def _format_enemy_with_article(name: str) -> str:
    base = _get_enemy_base_name(name)
    if not base:
        return "a hostile enemy"
    low = base.lower()
    if low.startswith(("the ", "a ", "an ")):
        return base
    article = "an" if low[0] in "aeiou" else "a"
    return f"{article} {base}"


def _join_natural(items: list[str]) -> str:
    clean = [str(x).strip() for x in items if str(x).strip()]
    if not clean:
        return ""
    if len(clean) == 1:
        return clean[0]
    if len(clean) == 2:
        return f"{clean[0]} and {clean[1]}"
    return f"{', '.join(clean[:-1])}, and {clean[-1]}"


def ensure_enemy_encounter_narrative(
    result: dict,
    session: dict,
    party: list,
    actions: list = None,
    pre_turn_enemy_names: set = None,
) -> tuple[dict, str]:
    """Guarantees that whenever an enemy is encountered on a turn (or active hostiles are present
    and completely omitted from the LLM prose), the narrative explicitly describes how the enemy
    appeared and how the player and any present characters/NPCs react to the encounter."""
    if not isinstance(result, dict):
        return result, ""
    if result.get("_combat_resolved_notice"):
        return result, ""

    raw_enemies = result.get("nearby_enemies")
    if not raw_enemies:
        raw_enemies = session.get("nearby_enemies") or []
    active_enemies = [
        m for m in (raw_enemies or [])
        if isinstance(m, dict) and m.get("hp", 1) > 0 and m.get("name")
    ]
    if not active_enemies:
        return result, ""

    pre_names = {str(n).lower() for n in (pre_turn_enemy_names or set())}
    newly_spawned = [
        m for m in active_enemies
        if _get_enemy_base_name(m.get("name", "")).lower() not in pre_names
    ]

    outcome_nar = str(result.get("outcome_narrative") or "").strip()
    next_nar = str(result.get("next_narrative") or result.get("narrative") or "").strip()
    combined_nar = f"{outcome_nar}\n{next_nar}".strip()

    if newly_spawned:
        missing_enemies = [
            m for m in newly_spawned
            if not _is_enemy_mentioned_in_narrative(m.get("name", ""), combined_nar)
        ]
    else:
        any_mentioned = any(
            _is_enemy_mentioned_in_narrative(m.get("name", ""), combined_nar)
            for m in active_enemies
        )
        missing_enemies = list(active_enemies) if not any_mentioned else []

    party_names = []
    for entry in (party or []):
        c_obj = entry[0] if isinstance(entry, (tuple, list)) else entry
        if isinstance(c_obj, dict) and c_obj.get("name"):
            party_names.append(str(c_obj["name"]).strip())
    lead_player = party_names[0] if party_names else "The adventurer"
    other_players = party_names[1:]

    enemy_base_lowers = {_get_enemy_base_name(m.get("name", "")).lower() for m in active_enemies}
    player_lowers = {p.lower() for p in party_names}
    raw_npcs = result.get("npcs_present")
    if raw_npcs is None:
        raw_npcs = session.get("current_npcs") or []
    present_npc_names = []
    for n in (raw_npcs or []):
        n_name = game_engine._get_npc_name(n) if n else ""
        if not n_name or n_name.lower() == "none":
            continue
        if n_name.lower() in enemy_base_lowers or n_name.lower() in player_lowers:
            continue
        if n_name not in present_npc_names:
            present_npc_names.append(n_name)

    raw_loc = str(result.get("location") or session.get("current_location") or "the area").strip()
    loc_parts = [p.strip() for p in raw_loc.split("➔") if p.strip()]
    if len(loc_parts) >= 2:
        loc_display = loc_parts[1] if loc_parts[-1].lower() in ("main area", "entrance", "exterior", "interior") else loc_parts[-1]
    elif loc_parts:
        loc_display = loc_parts[0]
    else:
        loc_display = "the area"

    appended_paragraph = ""
    if missing_enemies:
        formatted_enemies = []
        seen_bases = set()
        for m in missing_enemies:
            b_name = _get_enemy_base_name(m.get("name", ""))
            if b_name.lower() not in seen_bases:
                seen_bases.add(b_name.lower())
                formatted_enemies.append(_format_enemy_with_article(b_name))
        enemy_list_str = _join_natural(formatted_enemies)
        is_plural_enemies = len(formatted_enemies) > 1
        threat_noun = "hostile figures emerge" if is_plural_enemies else "a hostile threat emerges"

        appearance_sentence = (
            f"Before another moment can pass at {loc_display}, the atmosphere shifts violently as {threat_noun} "
            f"from the surrounding approaches—{enemy_list_str} suddenly lunging into view to spring an ambush and cut off any easy retreat!"
        )

        if present_npc_names:
            npc_str = _join_natural(present_npc_names)
            npc_verb = (
                "tense sharply at the sudden ambush, calling out urgent warnings and shifting"
                if len(present_npc_names) > 1
                else "tenses sharply at the sudden ambush, calling out an urgent warning and shifting"
            )
            actor_str = _join_natural([lead_player] + other_players)
            actor_verb = (
                "immediately pivot toward the emerging danger and drop into combat-ready stances with weapons drawn"
                if other_players
                else "immediately pivots toward the emerging danger and drops into a combat-ready stance with weapon drawn"
            )
            reaction_sentence = (
                f"{actor_str} {actor_verb}, while {npc_str} {npc_verb} into a defensive position as the confrontation erupts."
            )
        elif other_players:
            actor_str = _join_natural([lead_player] + other_players)
            reaction_sentence = (
                f"{actor_str} immediately pivot toward the emerging danger, drawing their weapons and dropping into a tight defensive formation as the confrontation erupts."
            )
        else:
            reaction_sentence = (
                f"{lead_player} immediately pivots toward the emerging danger, drawing their weapon and dropping into a combat-ready stance as the confrontation erupts."
            )

        appended_paragraph = f"{appearance_sentence} {reaction_sentence}"
    elif newly_spawned and present_npc_names:
        # Enemies were named by the LLM, but verify present NPCs' reaction wasn't omitted
        nar_low = combined_nar.lower()
        unmentioned_npcs = [
            n for n in present_npc_names
            if n.lower() not in nar_low and not any(tok in nar_low for tok in n.lower().split() if len(tok) >= 4)
        ]
        if unmentioned_npcs:
            npc_str = _join_natural(unmentioned_npcs)
            npc_verb = "react" if len(unmentioned_npcs) > 1 else "reacts"
            appended_paragraph = (
                f"Beside {lead_player}, {npc_str} {npc_verb} immediately to the sudden emergence of the hostiles, "
                f"calling out a sharp warning and bracing in a defensive posture as battle is joined."
            )

    if appended_paragraph:
        if next_nar:
            result["next_narrative"] = f"{next_nar}\n\n{appended_paragraph}"
        else:
            result["next_narrative"] = appended_paragraph
        if result.get("narrative"):
            result["narrative"] = result["next_narrative"]

    return result, appended_paragraph
