from __future__ import annotations

import asyncio
import json
import logging
import threading
import time
from collections import OrderedDict
from typing import Any, Dict, Optional, Tuple

import db
from db import adb
import llm_client
import scenario_data
from mechanics.narrative.examine import build_examine_snapshot, scrub_examine_prose

log = logging.getLogger(__name__)

_MAX_CACHE_ENTRIES = 256
_MAX_EPOCH_ENTRIES = 4096
_CACHE_TTL_SEC = 1800.0

_CACHE_LOCK = threading.Lock()
_EXAMINE_CACHE: "OrderedDict[Tuple[Any, ...], Tuple[float, str]]" = OrderedDict()
_INFLIGHT_LOCKS: Dict[Tuple[Any, ...], asyncio.Lock] = {}
_INFLIGHT_WAITERS: Dict[Tuple[Any, ...], int] = {}
_SESSION_EPOCHS: "OrderedDict[int, int]" = OrderedDict()


def invalidate_examine_cache(session_id: int) -> None:
    """Purges cached Examine prose for a session when state changes (turn, stealth, rollback)."""
    try:
        sid = int(session_id)
    except (TypeError, ValueError):
        return
    with _CACHE_LOCK:
        _SESSION_EPOCHS[sid] = _SESSION_EPOCHS.get(sid, 0) + 1
        _SESSION_EPOCHS.move_to_end(sid)
        while len(_SESSION_EPOCHS) > _MAX_EPOCH_ENTRIES:
            _SESSION_EPOCHS.popitem(last=False)
        stale_keys = [k for k in list(_EXAMINE_CACHE.keys()) if k and k[0] == sid]
        for k in stale_keys:
            _EXAMINE_CACHE.pop(k, None)
        stale_locks = [
            k for k in list(_INFLIGHT_LOCKS.keys())
            if isinstance(k, tuple) and len(k) == 2 and isinstance(k[1], tuple) and k[1] and k[1][0] == sid
        ]
        for k in stale_locks:
            if _INFLIGHT_WAITERS.get(k, 0) <= 0 and not _INFLIGHT_LOCKS[k].locked():
                _INFLIGHT_LOCKS.pop(k, None)
                _INFLIGHT_WAITERS.pop(k, None)


def _clear_examine_cache_all() -> None:
    """Test helper to clear all cached Examine prose."""
    with _CACHE_LOCK:
        _EXAMINE_CACHE.clear()
        _INFLIGHT_LOCKS.clear()
        _INFLIGHT_WAITERS.clear()
        _SESSION_EPOCHS.clear()


db.register_session_rollback_hook = getattr(db, "register_session_rollback_hook", None)
if callable(db.register_session_rollback_hook):
    db.register_session_rollback_hook(invalidate_examine_cache)


def _make_examine_cache_key(
    session: Dict[str, Any],
    snapshot: Dict[str, Any],
    user_id: int,
    user_settings: Optional[Dict[str, Any]],
) -> Tuple[Any, ...]:
    sid = int(session.get("id") or snapshot.get("session_id") or 0)
    turn_num = int(session.get("turn_count") or len(session.get("history") or []) or 0)
    env = snapshot.get("environment") or {}
    loc = str(env.get("location") or "")
    sub_loc = str(env.get("sub_location") or "")
    node_id = str(session.get("current_node_id") or "")
    lang = str(
        (user_settings or {}).get("narration_language")
        or (user_settings or {}).get("language")
        or session.get("narration_language")
        or session.get("language")
        or "en"
    ).strip().lower()
    st_blk = snapshot.get("stealth_and_epistemic") or {}
    stealth_sig = (
        bool(st_blk.get("is_hidden")),
        str(st_blk.get("alert_level") or ""),
        int(st_blk.get("detection_meter") or 0),
    )
    enemies_sig = tuple(
        (
            str(e.get("name") or ""),
            str(e.get("condition_label") or ""),
            tuple(e.get("status_effects") or ()),
            str(e.get("intent") or ""),
            tuple(e.get("weaknesses") or ()),
            tuple(e.get("resistances") or ()),
            tuple(e.get("immunities") or ()),
        )
        for e in (snapshot.get("combat_intel") or [])
    )
    npcs_sig = tuple(
        (
            str(n.get("name") or ""),
            str(n.get("activity") or ""),
            str(n.get("posture") or ""),
            str(n.get("holding") or ""),
        )
        for n in (snapshot.get("present_npcs") or [])
    )
    objects_sig = tuple(
        (
            str(o.get("display_name") or ""),
            str(o.get("description") or ""),
            str(o.get("kind") or ""),
        )
        for o in (snapshot.get("objects") or [])
    )
    clues_sig = tuple(
        (
            str(c.get("title") or ""),
            str(c.get("lead_text") or ""),
            str(c.get("category") or ""),
        )
        for c in (snapshot.get("clues") or [])
    )
    return (
        sid,
        turn_num,
        loc,
        sub_loc,
        node_id,
        int(user_id),
        str(snapshot.get("per_tier") or "medium"),
        str(snapshot.get("scene_mode") or "exploration"),
        lang,
        bool(snapshot.get("show_enemy_hp", True)),
        bool(snapshot.get("show_enemy_intent", True)),
        stealth_sig,
        enemies_sig,
        npcs_sig,
        objects_sig,
        clues_sig,
    )


def _get_cached_prose(cache_key: Tuple[Any, ...]) -> Optional[str]:
    with _CACHE_LOCK:
        entry = _EXAMINE_CACHE.get(cache_key)
        if not entry:
            return None
        ts, prose = entry
        if (time.monotonic() - ts) > _CACHE_TTL_SEC:
            _EXAMINE_CACHE.pop(cache_key, None)
            return None
        _EXAMINE_CACHE.move_to_end(cache_key)
        return prose


def _store_cached_prose_unlocked(cache_key: Tuple[Any, ...], prose: str) -> None:
    if not prose:
        return
    _EXAMINE_CACHE[cache_key] = (time.monotonic(), prose)
    _EXAMINE_CACHE.move_to_end(cache_key)
    while len(_EXAMINE_CACHE) > _MAX_CACHE_ENTRIES:
        _EXAMINE_CACHE.popitem(last=False)


def _store_cached_prose(cache_key: Tuple[Any, ...], prose: str) -> None:
    if not prose:
        return
    with _CACHE_LOCK:
        _store_cached_prose_unlocked(cache_key, prose)


def _build_examine_prompts(
    session: Dict[str, Any],
    snapshot: Dict[str, Any],
    char: Dict[str, Any],
    user_settings: Optional[Dict[str, Any]],
) -> Tuple[str, str]:
    sess_for_lang = dict(session or {})
    if isinstance(user_settings, dict):
        if user_settings.get("narration_language"):
            sess_for_lang["narration_language"] = user_settings["narration_language"]
        if user_settings.get("language"):
            sess_for_lang.setdefault("language", user_settings["language"])
    if isinstance(char, dict) and char.get("gender"):
        sess_for_lang.setdefault("lead_character_gender", char["gender"])

    lang_block = ""
    try:
        from game_engine.prompt_layout import build_language_directive
        lang_block = build_language_directive(sess_for_lang, kind="opening")
    except Exception:
        lang_block = ""

    per_tier = str(snapshot.get("per_tier") or "medium")
    per_guidance = {
        "low": "Focus strictly on obvious surface sights, broad layout, and openly visible people or items.",
        "medium": "Note clear spatial details plus subtle posture cues, ambient sounds, and visible mood tells listed in the snapshot.",
        "high": "Highlight fine environmental textures, tactical vantage points, subtle body-language tells, and revealed vulnerabilities.",
        "keen": "Deliver razor-sharp observational clarity across spatial geometry, micro-expressions, sound cues, and tactical angles.",
    }.get(per_tier, "Describe the immediate surroundings accurately.")

    system_prompt = (
        "You are an observational narrator describing ONLY what the protagonist perceives right now during a quick look around.\n"
        "Strict Rules:\n"
        "- Write 1 to 2 tight, evocative paragraphs (55 to 120 words total) in plain prose.\n"
        "- Ground every single detail strictly in the structured snapshot JSON below. NEVER invent new rooms, doors, loot, enemies, or secrets.\n"
        "- NEVER reveal hidden secrets, unrevealed NPC traits, game-mechanic terms, HP/MP numbers, dice percentages, DC integers, JSON tags, or choice lists.\n"
        "- Do NOT advance time, resolve actions, or add headings like Title/Choices.\n"
        f"- Perception insight guidance: {per_guidance}\n"
    )
    if lang_block:
        system_prompt += (
            f"\n{lang_block}\n"
            "- Output plain narrative prose ONLY (ignore any JSON key / choice formatting mentioned in the language block)."
        )

    safe_payload = {
        "scene_mode": snapshot.get("scene_mode"),
        "environment": snapshot.get("environment"),
        "present_npcs": snapshot.get("present_npcs"),
        "objects": [
            {k: o.get(k) for k in ("display_name", "description", "kind")}
            for o in (snapshot.get("objects") or [])
        ],
        "clues": [
            {k: c.get(k) for k in ("title", "lead_text", "category")}
            for c in (snapshot.get("clues") or [])
        ],
        "stealth_and_epistemic": snapshot.get("stealth_and_epistemic"),
        "combat_intel": [
            {k: e.get(k) for k in ("name", "condition_label", "status_effects", "intent", "weaknesses", "resistances", "immunities")}
            for e in (snapshot.get("combat_intel") or [])
        ],
    }
    user_prompt = (
        "Render a grounded sensory observation of this scene from the snapshot below:\n"
        f"{json.dumps(safe_payload, ensure_ascii=False)}"
    )
    return system_prompt, user_prompt


async def get_examine_payload(
    session_id: int,
    user_id: int,
    *,
    include_prose: bool = False,
) -> Dict[str, Any]:
    """
    Zero-turn inspection entrypoint shared by FastAPI GET /api/adventure/examine and Discord Examine.
    When include_prose=False, returns instant live structured state + cached prose if already warm.
    When include_prose=True, generates and caches concise sensory prose scoped to current turn/state.
    """
    def _hydrate_examine_bundle() -> Tuple[Dict[str, Any], Dict[str, Any], Dict[str, Any], Dict[str, Any]]:
        with db.ReadUnitOfWork():
            session_row = db.get_session(int(session_id))
            if not session_row:
                raise LookupError("Session not found")
            sess = dict(session_row)
            u_settings = db.get_settings(int(user_id)) or {}
            char_row = db.get_character(int(user_id), int(session_id), settings=u_settings)
            if not char_row:
                char_row = db.get_character(int(user_id), settings=u_settings)
            ch = dict(char_row) if char_row else {"user_id": int(user_id), "per_": 5}
            snap = build_examine_snapshot(
                sess,
                ch,
                user_settings=u_settings,
                user_id=int(user_id),
            )
            return sess, ch, u_settings, snap

    sid_int = int(session_id)
    with _CACHE_LOCK:
        start_epoch = _SESSION_EPOCHS.get(sid_int, 0)
    session, char, user_settings, snapshot = await adb(_hydrate_examine_bundle)

    cache_key = _make_examine_cache_key(session, snapshot, int(user_id), user_settings)
    cached_prose = _get_cached_prose(cache_key)
    if cached_prose:
        snapshot["narrative_prose"] = cached_prose
        snapshot["prose_ready"] = True
        snapshot["prose_cached"] = True
        return snapshot

    if not include_prose:
        snapshot["narrative_prose"] = None
        snapshot["prose_ready"] = False
        snapshot["prose_cached"] = False
        return snapshot

    lock_key = (id(asyncio.get_running_loop()), cache_key)
    with _CACHE_LOCK:
        lock = _INFLIGHT_LOCKS.get(lock_key)
        if lock is None:
            lock = asyncio.Lock()
            _INFLIGHT_LOCKS[lock_key] = lock
        _INFLIGHT_WAITERS[lock_key] = _INFLIGHT_WAITERS.get(lock_key, 0) + 1
    try:
        async with lock:
            cached_after = _get_cached_prose(cache_key)
            if cached_after:
                snapshot["narrative_prose"] = cached_after
                snapshot["prose_ready"] = True
                snapshot["prose_cached"] = True
                return snapshot

            with _CACHE_LOCK:
                is_stale_epoch = _SESSION_EPOCHS.get(sid_int, 0) != start_epoch
            if is_stale_epoch:
                snapshot["narrative_prose"] = snapshot.get("fallback_prose") or ""
                snapshot["prose_ready"] = True
                snapshot["prose_cached"] = False
                return snapshot

            scen_key = str(session.get("scenario") or char.get("scenario") or "fantasy")
            is_nsfw = bool(scenario_data.uses_nsfw_model(scen_key))
            sys_prompt, usr_prompt = _build_examine_prompts(session, snapshot, char, user_settings)

            prose_text = ""
            try:
                raw_resp = await llm_client.call_llm_text(
                    sys_prompt,
                    usr_prompt,
                    max_tokens=300,
                    retries=1,
                    is_nsfw=is_nsfw,
                    use_utility=False,
                    timeout=18.0,
                )
                prose_text = scrub_examine_prose(raw_resp)
            except Exception as exc:
                log.warning("Examine async prose generation failed (falling back): %s", exc)
                prose_text = ""

            if prose_text:
                with _CACHE_LOCK:
                    if _SESSION_EPOCHS.get(sid_int, 0) == start_epoch:
                        _store_cached_prose_unlocked(cache_key, prose_text)
                snapshot["narrative_prose"] = prose_text
                snapshot["prose_ready"] = True
                snapshot["prose_cached"] = False
            else:
                snapshot["narrative_prose"] = snapshot.get("fallback_prose") or ""
                snapshot["prose_ready"] = True
                snapshot["prose_cached"] = False
            return snapshot
    finally:
        with _CACHE_LOCK:
            remaining = _INFLIGHT_WAITERS.get(lock_key, 0) - 1
            if remaining > 0:
                _INFLIGHT_WAITERS[lock_key] = remaining
            else:
                _INFLIGHT_WAITERS.pop(lock_key, None)
                if _INFLIGHT_LOCKS.get(lock_key) is lock and not lock.locked():
                    _INFLIGHT_LOCKS.pop(lock_key, None)
